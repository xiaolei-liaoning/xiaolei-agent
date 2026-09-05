"""
Claude Code 风格的 JavaScript Workflow 引擎

特点：
  - 真正的 Node.js 运行时
  - 完整的 agent(), parallel(), pipeline(), phase(), log(), budget
  - 双向 IPC 通信
  - 真实的 schema 验证
  - 完全的官方兼容
  - Resume 缓存（同会话内自动缓存 agent 调用）
  - workflow() 嵌套子 Workflow
  - 多模型路由 + Budget 按模型追踪
"""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.multi_agent_v2.orchestration.orchestrator import agent as py_agent
from core.multi_agent_v2.workflow.models import Meta, PhaseRecord, WorkflowResult

logger = logging.getLogger(__name__)


@dataclass
class WorkflowConfig:
    node_path: str = "node"
    timeout: int = 1200  # ponytail: 大项目 LLM 慢，600→1200
    max_concurrent_agents: int = 16
    max_agents: int = 1000
    budget_total: int = 1_000_000
    resume_cache: bool = True
    agent_timeout: int = 600  # ponytail: LLM 慢时单 agent 可能需要 600s


class ClaudeCodeWorkflow:
    """完全官方兼容的 JavaScript Workflow 运行时"""

    def __init__(self, config: Optional[WorkflowConfig] = None):
        self.config = config or WorkflowConfig()
        self._phase_records: list = []
        self._current_phase: Optional[str] = None
        self._log_buffer: list = []
        self._agent_count: int = 0
        self._resume_cache: Dict[str, Any] = {}  # Resume 缓存
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._model_records: Dict[str, int] = {}  # 按模型统计 agent 调用次数
        # ── 并发控制（修复 parallel 假并行） ──
        self._ipc_semaphore = asyncio.Semaphore(
            config.max_concurrent_agents if config else 16
        )
        self._ipc_tasks: set = set()

    # ═══════════════════════════════════════════════════════════════
    # Resume 缓存（同会话）
    # ═══════════════════════════════════════════════════════════════

    def _make_cache_key(self, prompt: str, opts: Dict) -> str:
        """生成缓存键 — 排除动态注入的 _workflowContext 等字段"""
        canonical: Dict[str, Any] = {"prompt": prompt}
        # 只保留影响输出的静态 opts 字段
        for key in ("label", "model", "schema", "agentType",
                     "timeout", "max_turns", "max_rounds",
                     "temperature", "personality", "role",
                     "stripSchema"):
            if key in opts:
                canonical[key] = opts[key]
        # 排除纯运行时标志（不影响内容输出）
        _ = opts.get("fullResult")
        raw = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode()).hexdigest()

    def clear_cache(self) -> None:
        """手动清除 Resume 缓存"""
        self._resume_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def cache_stats(self) -> Dict[str, Any]:
        """缓存统计"""
        return {
            "size": len(self._resume_cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": (
                round(self._cache_hits / (self._cache_hits + self._cache_misses), 3)
                if (self._cache_hits + self._cache_misses) > 0
                else 0.0
            ),
        }

    # ═══════════════════════════════════════════════════════════════
    # Workflow 名称解析（用于 workflow() 嵌套）
    # ═══════════════════════════════════════════════════════════════

    def _resolve_workflow_by_name(self, name: str) -> str:
        """按名称查找 workflow 脚本

        查找顺序：
          1. {project_dir}/.claude/workflows/<name>.js
          2. {project_dir}/workflows/<name>.js
          3. ~/.claude/workflows/<name>.js
          4. 如果 name 包含 /，尝试作为相对路径读取

        Raises:
            FileNotFoundError: 找不到对应 workflow 文件
        """
        # 如果 name 本身就是文件路径
        if os.path.isfile(name):
            with open(name, "r", encoding="utf-8") as f:
                return f.read()

        # 带 .js 后缀的 name
        search_names = [
            name,
            name + ".js" if not name.endswith(".js") else name,
        ]

        search_dirs = [
            os.path.join(os.getcwd(), ".claude", "workflows"),
            os.path.join(os.getcwd(), "workflows"),
            os.path.join(os.path.expanduser("~"), ".claude", "workflows"),
        ]

        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue
            # 精确匹配
            for sname in search_names:
                filepath = os.path.join(search_dir, sname)
                if os.path.isfile(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        return f.read()
            # 递归扫描（处理嵌套目录如 "review/code"）
            for root, _, files in os.walk(search_dir):
                for f in files:
                    if not (f.endswith(".js") or f.endswith(".mjs")):
                        continue
                    rel_path = os.path.relpath(os.path.join(root, f), search_dir)
                    stem = os.path.splitext(rel_path)[0]
                    if stem == name or stem.endswith(f"/{name}"):
                        with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                            return fh.read()

        raise FileNotFoundError(
            f"Workflow '{name}' not found in {search_dirs}"
        )

    # ═══════════════════════════════════════════════════════════════
    # 主入口：run()
    # ═══════════════════════════════════════════════════════════════

    async def run(
        self,
        script: str,
        meta_overrides: Optional[Dict] = None,
        args: Any = None,
    ) -> WorkflowResult:
        """运行 JavaScript Workflow 脚本

        Args:
            script: JS 脚本字符串（export const meta + export default async function 或 export async function run）
            meta_overrides: 可选的 meta 字段覆盖
            args: 传入子 Workflow 的参数（对 workflow() 嵌套生效，JS 侧通过全局 args 访问）

        Returns:
            WorkflowResult
        """
        start_time = time.time()
        self._phase_records = []
        self._current_phase = None
        self._log_buffer = []
        self._agent_count = 0
        self._model_records = {}  # 每次 run 重置模型统计

        # 序列化 args 供桥接脚本注入
        args_json = json.dumps(args, ensure_ascii=False) if args is not None else "undefined"

        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. 准备脚本文件
            script_path = os.path.join(temp_dir, "workflow.js")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script)

            # 2. 准备 Node.js 桥接脚本
            bridge_path = os.path.join(temp_dir, "bridge.mjs")
            with open(bridge_path, "w", encoding="utf-8") as f:
                f.write(self._generate_node_bridge(
                    temp_dir,
                    budget_total=self.config.budget_total,
                    args_json=args_json,
                ))

            # 3. 启动进程
            process = await asyncio.create_subprocess_exec(
                self.config.node_path,
                bridge_path,
                script_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # 4. 处理 IPC
            stdin_queue = asyncio.Queue()
            output_queue = asyncio.Queue()

            async def read_stdout():
                try:
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        line_str = line.decode("utf-8").rstrip()
                        if line_str.startswith("__IPC__:"):
                            try:
                                msg = json.loads(line_str[8:])
                                await output_queue.put(msg)
                            except Exception as e:
                                print(f"[JS] Bad IPC: {e}")
                        else:
                            print(f"[JS] {line_str}")
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            async def read_stderr():
                try:
                    while True:
                        line = await process.stderr.readline()
                        if not line:
                            break
                        line_str = line.decode("utf-8").rstrip()
                        print(f"[JS!] {line_str}")
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            async def write_stdin():
                try:
                    while True:
                        msg = await stdin_queue.get()
                        try:
                            line = (
                                "__IPC__:" + json.dumps(msg, ensure_ascii=False) + "\n"
                            )
                            process.stdin.write(line.encode("utf-8"))
                            await process.stdin.drain()
                        except Exception as e:
                            print(f"[Write Error] {e}")
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            async def ipc_handler():
                try:
                    while True:
                        msg = await output_queue.get()
                        # ⭐ 用 create_task 代替 await：多个 agent 同时执行
                        #    之前是 await，导致 parallel 假并行
                        task = asyncio.create_task(
                            self._ipc_handle_with_sem(msg, stdin_queue)
                        )
                        self._ipc_tasks.add(task)
                        task.add_done_callback(self._ipc_tasks.discard)
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            stdout_task = asyncio.create_task(read_stdout())
            stderr_task = asyncio.create_task(read_stderr())
            stdin_task = asyncio.create_task(write_stdin())
            ipc_task = asyncio.create_task(ipc_handler())

            # 5. 等待结束
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=self.config.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                for task in [stdout_task, stderr_task, stdin_task, ipc_task]:
                    task.cancel()
                await asyncio.gather(
                    stdout_task, stderr_task, stdin_task, ipc_task,
                    return_exceptions=True,
                )
                try:
                    for t in list(self._ipc_tasks):
                        t.cancel()
                    if self._ipc_tasks:
                        await asyncio.gather(*self._ipc_tasks, return_exceptions=True)
                except RecursionError:
                    pass
                self._ipc_tasks.clear()
                return WorkflowResult(
                    success=False,
                    error=f"Timeout after {self.config.timeout}s",
                    elapsed=time.time() - start_time,
                    label="JS Workflow",
                )

            for task in [stdout_task, stderr_task, stdin_task, ipc_task]:
                task.cancel()
            await asyncio.gather(
                stdout_task, stderr_task, stdin_task, ipc_task,
                return_exceptions=True,
            )

            # 取消还在跑的 IPC 任务（create_task 产生的）
            # ponytail: Python 3.14 Task.cancel() 递归 bug，防止嵌套 workflow 时 RecursionError
            try:
                for t in list(self._ipc_tasks):
                    t.cancel()
                if self._ipc_tasks:
                    await asyncio.gather(*self._ipc_tasks, return_exceptions=True)
            except RecursionError:
                pass
            self._ipc_tasks.clear()

            if process.stdin:
                process.stdin.close()
                await process.stdin.wait_closed()

            # 6. 读取结果
            result_file = os.path.join(temp_dir, "result.json")
            if os.path.exists(result_file):
                with open(result_file, "r", encoding="utf-8") as f:
                    result_data = json.load(f)
                    return self._build_workflow_result(
                        result_data, start_time, time.time(), meta_overrides,
                    )

            return WorkflowResult(
                success=False,
                error="No result file",
                elapsed=time.time() - start_time,
                label="JS Workflow",
            )

    # ═══════════════════════════════════════════════════════════════
    # IPC 处理
    # ═══════════════════════════════════════════════════════════════

    async def _ipc_handle_with_sem(self, msg: Dict[str, Any], stdin_queue):
        """带并发限制的 IPC 处理（最多 max_concurrent_agents 个同时运行）"""
        async with self._ipc_semaphore:
            await self._handle_ipc(msg, stdin_queue)

    async def _handle_ipc(self, msg: Dict[str, Any], stdin_queue):
        """处理来自 JS 的 IPC 消息

        支持的消息类型：
          - agent:    调用子 Agent（支持 Resume 缓存、多模型追踪）
          - workflow: 嵌套执行子 Workflow
          - phase:    标记阶段进度
          - log:      输出日志
          - budget:   汇报 token 消耗
        """
        msg_type = msg.get("type")
        msg_id = msg.get("id")

        try:
            # ── agent: 调用子 Agent ──────────────────────────────
            if msg_type == "agent":
                prompt = msg.get("data", {}).get("prompt", "")
                opts = msg.get("data", {}).get("opts", {})

                label = opts.get("label", prompt[:40])
                model = opts.get("model", "default")

                # ── Resume 缓存命中检查 ──
                cache_key = None
                if self.config.resume_cache:
                    cache_key = self._make_cache_key(prompt, opts)
                    if cache_key in self._resume_cache:
                        self._cache_hits += 1
                        cached = self._resume_cache[cache_key]
                        print(f"    \033[36m♻️  {label} (缓存命中, model={model})\033[0m")
                        response = {
                            "id": msg_id,
                            "result": cached,
                        }
                        await stdin_queue.put(response)
                        return
                    self._cache_misses += 1

                # ponytail: 用 WorkflowConfig.agent_timeout 作为默认超时
                opts.setdefault("timeout", self.config.agent_timeout)
                
                # ── 提取并注入工作流上下文 ──
                wf_ctx = opts.pop("_workflowContext", {})
                if wf_ctx:
                    context_parts = []

                    global_task = wf_ctx.get("globalTask", "")
                    if global_task:
                        context_parts.append("## 全局任务\n" + global_task)

                    current_phase = wf_ctx.get("currentPhase", "")
                    if current_phase:
                        context_parts.append("## 当前阶段\n" + current_phase)

                    prev_results = wf_ctx.get("previousPhaseResults", {})
                    if prev_results and isinstance(prev_results, dict):
                        phase_parts = []
                        for phase_name, output in prev_results.items():
                            output_str = str(output)[:3000] if output else "(无输出)"
                            phase_parts.append(f"### {phase_name}\n{output_str}")
                        if phase_parts:
                            context_parts.append(
                                "## 前序阶段结果\n" + "\n\n".join(phase_parts)
                            )

                    agent_idx = wf_ctx.get("agentIndex", 0)
                    if agent_idx:
                        context_parts.append(
                            f"## Agent 角色\n你是本次多Agent协作中的第 {agent_idx} 个子任务。"
                        )

                    if context_parts:
                        context_header = (
                            "\n\n<workflow_context>\n"
                            + "\n\n".join(context_parts)
                            + "\n</workflow_context>"
                        )
                        prompt = context_header + "\n\n" + prompt

                # ── 中间 Agent 自动去掉 schema ──
                # 默认保留 schema（中间 agent 也可以有结构化输出）
                # 只有显式 stripSchema: true 才去掉
                if opts.pop("stripSchema", False):
                    opts.pop("schema", None)

                # ── 调用 agent ──
                subagent_type = opts.get("agentType") or opts.get("type")
                if subagent_type:
                    result = await py_agent(prompt, opts, subagent_type=subagent_type)
                else:
                    result = await py_agent(prompt, opts)

                output = result.output if result else None

                if opts.get("schema") and isinstance(output, str):
                    try:
                        output = json.loads(output)
                    except Exception:
                        pass

                response_result = {
                    "success": result.success if result else True,
                    "output": output,
                    "error": result.diagnostic if result and hasattr(result, 'diagnostic') else (result.error if result else None),
                    "exit_reason": result.exit_reason if result and hasattr(result, 'exit_reason') else "",
                    "artifacts": getattr(result, 'artifacts', {}) if result else {},
                    "executionTime": round(result.execution_time, 2) if result else 0.0,
                    "agentId": result.agent_id if result else "",
                    "metadata": result.metadata if result else {},
                }

                # ── 存入 Resume 缓存 ──
                if self.config.resume_cache and cache_key:
                    self._resume_cache[cache_key] = response_result

                # ── Phase 追踪：递增对应 phase 的 agent_calls ──
                phase_name = opts.get("phase", "")
                if phase_name and self._phase_records:
                    for pr in self._phase_records:
                        if pr.title == phase_name:
                            pr.agent_calls += 1
                            pr.elapsed += result.execution_time if result else 0
                            break

                # ── 多模型记录 ──
                self._model_records[model] = self._model_records.get(model, 0) + 1

                response = {"id": msg_id, "result": response_result}
                await stdin_queue.put(response)

                # ponytail: drain stdout queue after agent completes
                try:
                    from core.multi_agent_v2.agents.subagent.spawn import _drain_print_queue
                    await _drain_print_queue()
                except Exception:
                    pass

            # ── batch_agents: 并行执行一组 Agent（一次 IPC 搞定 parallel） ──
            elif msg_type == "batch_agents":
                agents_data = msg.get("data", {}).get("agents", [])
                batch_timeout = msg.get("data", {}).get("timeout", 120)

                from core.multi_agent_v2.orchestration.orchestrator import (
                    parallel as py_parallel,
                )

                tasks = []
                for i, a in enumerate(agents_data):
                    prompt = a.get("prompt", "")
                    opts = a.get("opts", {})
                    label = opts.get("label", prompt[:40])
                    tasks.append({
                        "prompt": prompt,
                        "label": label,
                        "model": opts.get("model"),
                        "subagent_type": opts.get("agentType") or opts.get("type"),
                        "timeout": opts.get("timeout", batch_timeout),
                    })

                results = await py_parallel(tasks, timeout=batch_timeout)

                response_results = []
                for r in results:
                    response_results.append({
                        "success": r.success,
                        "output": r.output,
                        "error": r.error,
                        "executionTime": round(r.execution_time, 2) if r else 0.0,
                        "agentId": r.agent_id if r else "",
                    })

                await stdin_queue.put({"id": msg_id, "result": response_results})

                # ponytail: drain stdout queue after parallel batch completes
                try:
                    from core.multi_agent_v2.agents.subagent.spawn import _drain_print_queue
                    await _drain_print_queue()
                except Exception:
                    pass

            # ── workflow: 嵌套子 Workflow ────────────────────────
            elif msg_type == "workflow":
                data = msg.get("data", {})
                name_or_ref = data.get("nameOrRef")
                wf_args = data.get("args", {})

                print(f"    \033[35m▸ Workflow 嵌套: {name_or_ref}\033[0m")

                # 递归深度限制（先于文件查找，避免误报 "not found"）
                if self._depth >= 5:
                    await stdin_queue.put({
                        "id": msg_id,
                        "error": f"Workflow nesting depth exceeded (max 5, current {self._depth})",
                    })
                    return

                # 解析 workflow 来源
                if isinstance(name_or_ref, str):
                    script = self._resolve_workflow_by_name(name_or_ref)
                elif isinstance(name_or_ref, dict) and "scriptPath" in name_or_ref:
                    sp = name_or_ref["scriptPath"]
                    if not os.path.isfile(sp):
                        raise FileNotFoundError(f"Workflow script not found: {sp}")
                    with open(sp, "r", encoding="utf-8") as f:
                        script = f.read()
                else:
                    await stdin_queue.put({
                        "id": msg_id,
                        "error": f"Invalid workflow reference: {name_or_ref}",
                    })
                    return

                # 递归执行子 workflow（传入 args）
                # 保存父 workflow 状态
                parent_phase = self._phase_records
                parent_current_phase = self._current_phase
                parent_log = self._log_buffer
                parent_count = self._agent_count
                parent_models = self._model_records
                # ponytail: 临时替换 _ipc_tasks 为空集，防子 workflow cleanup 误杀父任务
                parent_ipc_tasks = self._ipc_tasks
                self._ipc_tasks = set()
                
                sub_result = await self.run(script, args=wf_args)
                
                # 保存子 workflow 结果
                sub_phase = self._phase_records
                sub_log = self._log_buffer
                sub_count = self._agent_count
                sub_models = self._model_records
                
                # 恢复父 workflow 状态并合并子结果
                self._phase_records = parent_phase + sub_phase
                self._current_phase = parent_current_phase
                self._log_buffer = parent_log + sub_log
                self._agent_count = parent_count + sub_count
                self._model_records = {**parent_models, **sub_models}
                self._ipc_tasks = parent_ipc_tasks

                response = {
                    "id": msg_id,
                    "result": {
                        "success": sub_result.success,
                        "output": sub_result.output,
                        "error": sub_result.error,
                    },
                }
                await stdin_queue.put(response)

            # ── phase: 标记阶段 ──────────────────────────────────
            elif msg_type == "phase":
                title = msg.get("data", "")
                self._current_phase = title
                self._phase_records.append(
                    PhaseRecord(title=title, detail="", agent_calls=0, elapsed=0.0)
                )
                await stdin_queue.put({"id": msg_id, "result": "ok"})

            # ── log: 输出日志 ────────────────────────────────────
            elif msg_type == "log":
                msg_str = msg.get("data", "")
                self._log_buffer.append({"ts": time.time(), "msg": msg_str})
                await stdin_queue.put({"id": msg_id, "result": "ok"})

            # ── budget: token 消耗汇报 ────────────────────────────
            elif msg_type == "budget_report":
                spent_data = msg.get("data", {})
                # 更新全局 budget tracker（如果存在）
                from core.multi_agent_v2.orchestration.orchestrator import (
                    get_budget,
                )
                bt = get_budget()
                amount = spent_data.get("amount", 0)
                model = spent_data.get("model", "default")
                if bt:
                    bt.spend(amount, label=model)
                await stdin_queue.put({"id": msg_id, "result": "ok"})

            else:
                await stdin_queue.put({
                    "id": msg_id,
                    "result": {"error": f"Unknown type: {msg_type}"},
                })

        except Exception as e:
            import traceback
            await stdin_queue.put({
                "id": msg_id,
                "error": str(e),
                "stack": traceback.format_exc(),
            })

    # ═══════════════════════════════════════════════════════════════
    # Node.js 桥接脚本生成
    # ═══════════════════════════════════════════════════════════════

    def _generate_node_bridge(self, temp_dir: str, budget_total: int = 1_000_000, args_json: str = "undefined") -> str:
        """生成 Node.js 桥接脚本（ESM 模块）

        Args:
            temp_dir: 临时目录路径
            budget_total: 预算上限
            args_json: 传入的 args JSON 字符串或 "undefined"
        """
        js_budget = "null" if budget_total is None else str(budget_total)
        return f'''import {{ fileURLToPath }} from 'url';
import {{ dirname, join }} from 'path';
import {{ writeFile }} from 'fs/promises';
import {{ readFileSync }} from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const TEMP_DIR = "{temp_dir.replace(chr(92), chr(92)*2)}";
const RESULT_FILE = join(TEMP_DIR, 'result.json');

// ============================================
// IPC 层 — __IPC__: 协议
// ============================================

let msgId = 0;
const pending = new Map();

function send(type, data) {{
    const id = ++msgId;
    const p = new Promise((resolve, reject) => {{
        pending.set(id, {{ resolve, reject }});
    }});
    const line = `__IPC__:${{JSON.stringify({{ id, type, data }})}}\\n`;
    process.stdout.write(line);
    return p;
}}

function handleResponse(msg) {{
    const id = msg.id;
    const h = pending.get(id);
    if (!h) return;
    pending.delete(id);
    if (msg.error) {{
        h.reject(new Error(msg.error));
    }} else {{
        h.resolve(msg.result);
    }}
}}

let _inputBuffer = '';
process.stdin.on('data', data => {{
    _inputBuffer += data.toString();
    const lines = _inputBuffer.split('\\n');
    _inputBuffer = lines.pop() || '';
    for (const line of lines) {{
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {{
            if (trimmed.startsWith('__IPC__:')) {{
                const msg = JSON.parse(trimmed.substring(8));
                handleResponse(msg);
            }}
        }} catch (e) {{
            console.error('[Bridge] IPC parse error:', e);
        }}
    }}
}});

// ============================================
// Claude Code 兼容的原语
// ============================================

let currentPhase = null;
const phaseRecords = [];
const logs = [];

// 工作流上下文寄存器（由 JS 脚本设置）
globalThis._globalTask = '';
globalThis._prevResults = {{}};
globalThis._agentCount = 0;
globalThis._agentCalls = [];  // 跟踪每个 agent 调用用于协作图
globalThis._dagEdges = [];    // 跟踪 DAG 边用于协作图
globalThis._retryEvents = []; // 重试/重规划事件
globalThis._compressionWarnings = []; // 上下文压缩事件

// ── Budget 追踪（支持多模型） ──
let _budgetSpent = 0;
const _budgetModelSpent = {{}};

const budget = {{
    total: {js_budget},
    spent() {{
        return _budgetSpent;
    }},
    remaining() {{
        if (this.total === null) return Infinity;
        return Math.max(0, this.total - _budgetSpent);
    }},
    modelSpent: _budgetModelSpent,
    /** 汇报 token 消耗给 Python 端（全局 budget 同步） */
    async report(amount, model = 'default') {{
        _budgetSpent += amount;
        _budgetModelSpent[model] = (_budgetModelSpent[model] || 0) + amount;
        await send('budget_report', {{ amount, model }}).catch(() => {{}});
    }},
}};
globalThis.budget = budget;

// ── args: 外部传入的参数 ──
globalThis.args = {args_json};

// ── phase() ──
globalThis.phase = async function(title) {{
    currentPhase = title;
    phaseRecords.push({{ title, start: Date.now() }});
    console.log(`[Phase] === ${{title}} ===`);
    await send('phase', title);
}};

// ── log() ──
globalThis.log = async function(msg) {{
    logs.push({{ ts: Date.now(), msg }});
    console.log(`[Log] ${{msg}}`);
    await send('log', msg);
}};

// ── agent() — 调用子 Agent（支持多模型路由、Resume 缓存） ──
globalThis.agent = async function(prompt, opts = {{}}) {{
    const label = opts.label || `Agent #${{++globalThis._agentCount}}`;
    const startTime = Date.now();
    const callIdx = globalThis._agentCalls.length;
    globalThis._agentCalls.push({{label, prompt: ''+(prompt||'').substring(0,80), status: 'running', startTime, phase: currentPhase}});
    console.log(`[Agent] ${{label}}${{opts.model ? ' [' + opts.model + ']' : ''}}: ${{String(prompt).substr(0, 100)}}`);

    // 自动注入工作流上下文
    const ctx = {{
        globalTask: globalThis._globalTask || '',
        currentPhase: currentPhase || '',
        previousPhaseResults: globalThis._prevResults || {{}},
        agentIndex: globalThis._agentCount,
    }};
    const enhancedOpts = {{...opts, _workflowContext: ctx}};

    let result;
    try {{
        result = await send('agent', {{ prompt, opts: enhancedOpts }});
    }} catch (e) {{
        const call = globalThis._agentCalls[callIdx];
        call.status = 'failed';
        call.endTime = Date.now();
        call.duration = call.endTime - startTime;
        call.error = e.message;
        globalThis._retryEvents.push({{label, type: 'fail', time: Date.now()}});
        throw e;
    }}
    // ponytail: error grading — success=False always fails the workflow
    if (!result.success) {{
        const call = globalThis._agentCalls[callIdx];
        call.status = 'failed';
        call.endTime = Date.now();
        call.duration = call.endTime - startTime;
        call.error = result.error || result.diagnostic || result.exit_reason || 'agent failed';
        globalThis._retryEvents.push({{label, type: 'fail', time: Date.now()}});
        throw new Error(result.error || result.diagnostic || result.exit_reason || 'agent failed');
    }}
    // non-fatal diagnostic on success: log but return output
    if (result.exit_reason && result.exit_reason !== 'plan_completed' && result.exit_reason !== 'completed_with_answer') {{
        console.log(`[Agent] ${{label}}: succeeded with ${{result.exit_reason}}`);
    }}

    const call = globalThis._agentCalls[callIdx];
    call.status = 'done';
    call.endTime = Date.now();
    call.duration = call.endTime - startTime;
    call.model = opts.model || 'default';
    call.executionTime = result.executionTime || 0;
    if (result.metadata) {{
        call.metadata = result.metadata;
        if (result.metadata.truncated) {{
            globalThis._compressionWarnings.push({{label, type: 'truncation', detail: result.metadata.truncationDetail || '输出被截断'}});
        }}
    }}

    // Schema 解析
    if (opts.schema && result.output) {{
        try {{
            if (typeof result.output === 'string') {{
                result.output = JSON.parse(result.output);
            }}
        }} catch (e) {{
            console.warn('[Agent] Schema parse failed:', e.message);
        }}
    }}

    const _out = result.output;
    if (opts.fullResult) {{
        if (_out == null) result.output = "";
        return result;
    }}
    return _out ?? "";
}};

// ── batchAgents() — 批量并行执行 Agent（一次 IPC 搞定 parallel） ──
globalThis.batchAgents = async function(agentSpecs, timeout = 120) {{
    console.log(`[BatchAgents] Starting ${{agentSpecs.length}} agents...`);
    const result = await send('batch_agents', {{ agents: agentSpecs, timeout }});
    return result;
}};

// ── parallel() — 并行执行（有屏障） ──
globalThis.parallel = async function(thunks) {{
    console.log(`[Parallel] Starting ${{thunks.length}} tasks...`);
    const settled = await Promise.allSettled(
        thunks.map(t => {{
            try {{
                const r = typeof t === 'function' ? t() : t;
                return r instanceof Promise ? r : Promise.resolve(r);
            }} catch (e) {{
                return Promise.reject(e);
            }}
        }})
    );
    console.log(`[Parallel] ${{settled.length}} tasks completed`);
    return settled.map(r => {{
        if (r.status === 'rejected') return null;
        return r.value ?? null;
    }});
}};

// ── $dag() — 声明式 DAG 图编排 ──
globalThis.$dag = async function(nodes) {{
    const names = Object.keys(nodes);
    const graph = {{}}, edges = [];
    for (const name of names) {{
        const spec = nodes[name];
        if (typeof spec === 'function') {{
            graph[name] = {{ deps: [], task: spec, status: 'pending' }};
        }} else {{
            const deps = Array.isArray(spec.depends) ? spec.depends :
                         (spec.depends ? [spec.depends] : []);
            graph[name] = {{ deps, task: spec.task, status: 'pending' }};
            for (const dep of deps) {{
                edges.push({{ from: dep, to: name }});
                globalThis._dagEdges.push({{ from: dep, to: name }});
            }}
        }}
    }}
    const inDegree = {{}}, adj = {{}};
    for (const n of names) {{ inDegree[n] = 0; adj[n] = []; }}
    for (const [name, node] of Object.entries(graph)) {{
        for (const dep of node.deps) {{
            adj[dep] = adj[dep] || []; adj[dep].push(name); inDegree[name]++;
        }}
    }}
    const results = {{}};
    let ready = names.filter(n => inDegree[n] === 0);
    while (ready.length > 0) {{
        await Promise.allSettled(ready.map(async (name) => {{
            const node = graph[name];
            for (const dep of node.deps) {{
                if (graph[dep].status === 'failed') {{ node.status = 'skipped'; results[name] = null; return; }}
            }}
            const ctx = {{}};
            for (const dep of node.deps) ctx[dep] = results[dep];
            try {{
                results[name] = await node.task(ctx);
                graph[name].status = 'done';
            }} catch (e) {{
                graph[name].status = 'failed'; results[name] = null;
                console.warn('[DAG] "' + name + '" failed:', String(e).substring(0, 80));
            }}
        }}));
        ready = names.filter(n => graph[n].status === 'pending' &&
            graph[n].deps.every(d => graph[d].status === 'done' || graph[d].status === 'failed'));
    }}
    return results;
}};

// ── pipeline() — 无屏障流水线 ──
globalThis.pipeline = async function(items, ...stages) {{
    console.log(`[Pipeline] Processing ${{items.length}} items through ${{stages.length}} stages...`);

    const results = await Promise.all(
        items.map(async (item, index) => {{
            let current = item;
            try {{
                for (const stage of stages) {{
                    current = await (typeof stage === 'function' ? stage(current, item, index) : stage);
                }}
                return current;
            }} catch (e) {{
                console.error(`[Pipeline] Item error (index=${{index}}):`, e);
                return null;
            }}
        }})
    );

    console.log(`[Pipeline] All items completed`);
    return results;
}};

// ── workflow() — 嵌套子 Workflow ──
globalThis.workflow = async function(nameOrRef, args = {{}}) {{
    const nameStr = typeof nameOrRef === 'string' ? nameOrRef : nameOrRef.scriptPath || '';
    console.log(`[Workflow] Starting sub-workflow: ${{nameStr}}`);
    const result = await send('workflow', {{ nameOrRef, args }});
    if (result.error) throw new Error(result.error);
    if (result.output && typeof result.output === 'string') {{
        try {{ return JSON.parse(result.output); }} catch (e) {{ return result.output; }}
    }}
    return result.output;
}};

// ============================================
// 主入口
// ============================================

async function main() {{
    const scriptPath = process.argv[2];
    console.log('[Bridge] Loading workflow:', scriptPath);

    try {{
        const module = await import('file://' + scriptPath.replace(/\\\\/g, '/'));
        const meta = module.meta || {{ name: 'unnamed', description: '' }};

        console.log('[Bridge] Meta:', meta.name);

        let output;
        if (typeof module.default === 'function') {{
            console.log('[Bridge] Running default export...');
            output = await module.default();
        }} else if (typeof module.run === 'function') {{
            console.log('[Bridge] Running module.run()...');
            output = await module.run();
        }} else {{
            throw new Error('No default export or run() function');
        }}

        phaseRecords.forEach(pr => {{ if (!pr.end) pr.end = Date.now(); }});

        const resultPayload = {{
            success: true,
            output: output,
            meta: meta,
            phaseRecords: phaseRecords,
            logs: logs,
            agentCount: globalThis._agentCount,
            agentGraph: {{
                nodes: globalThis._agentCalls,
                edges: globalThis._dagEdges,
            }},
            budget: {{
                total: budget.total,
                spent: _budgetSpent,
                modelSpent: _budgetModelSpent,
            }},
        }};

        await writeFile(RESULT_FILE, JSON.stringify(resultPayload, null, 2));
        console.log('[Bridge] Done!');
    }} catch (e) {{
        console.error('[Bridge] Error:', e);
        await writeFile(RESULT_FILE, JSON.stringify({{
            success: false,
            error: String(e),
            stack: e.stack,
        }}, null, 2));
    }}
}}

main().finally(() => process.stdin?.destroy());
'''

    # ═══════════════════════════════════════════════════════════════
    # 结果构建
    # ═══════════════════════════════════════════════════════════════

    def _build_workflow_result(
        self,
        data: Dict[str, Any],
        start: float,
        end: float,
        meta_overrides: Optional[Dict],
    ) -> WorkflowResult:
        """构建标准 WorkflowResult"""
        meta_data = data.get("meta", {})
        if meta_overrides:
            meta_data.update(meta_overrides)

        meta = Meta(
            name=meta_data.get("name", "unnamed"),
            description=meta_data.get("description", ""),
            phases=meta_data.get("phases", []),
        )

        phase_records = []
        for pr in data.get("phaseRecords", []):
            title = pr.get("title", "")
            python_pr = next((p for p in self._phase_records if p.title == title), None)
            phase_records.append(
                PhaseRecord(
                    title=title,
                    detail="",
                    agent_calls=python_pr.agent_calls if python_pr else 0,
                    elapsed=python_pr.elapsed if python_pr else 0.0,
                )
            )

        return WorkflowResult(
            success=data.get("success", False),
            output=data.get("output"),
            error=data.get("error"),
            elapsed=end - start,
            label=meta.name,
            phases=phase_records,
            agent_graph=data.get("agentGraph"),
            metadata={
                "budget": data.get("budget", {}),
                "agent_count": data.get("agentCount", 0),
                "cache_stats": self.cache_stats(),
                "model_records": dict(self._model_records),
            },
        )


# 便捷函数
async def run_claude_workflow(
    script: str,
    config: Optional[WorkflowConfig] = None,
    args: Any = None,
) -> WorkflowResult:
    """运行 Claude Code 风格的 Workflow（便捷函数）"""
    runtime = ClaudeCodeWorkflow(config)
    return await runtime.run(script, args=args)
