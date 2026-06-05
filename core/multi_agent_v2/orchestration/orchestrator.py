"""
Orchestrator — 多Agent 编排引擎

参考 Claude Code CLI Workflow 设计：
  - @workflow 装饰器定义编排脚本
  - agent() 从池中借 WorkAgent 实例（light_mode），执行子任务
  - parallel() 多 Agent 真正并发执行
  - pipeline() 无屏障流水线
  - phase() / log() 阶段可视化

优化:
  - AgentPool 复用 WorkAgent 实例，避免每次 new
  - light_mode 子 Agent 走 ReAct 快路径（跳过 StepPlanner/记忆全链路）
  - 修复 _publish_to_bus 逻辑 bug
"""

import asyncio
import json
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# AgentPool — WorkAgent 复用池
# ═══════════════════════════════════════════════════════════════════

_DEFAULT_POOL_SIZE = 8


class AgentPool:
    """轻量 WorkAgent 复用池

    预创建 light_mode WorkAgent，agent() 调用时借出、用完归还，
    避免每次都 new WorkAgent（含 Mind/能力/记忆系统全链路初始化）。
    """

    def __init__(self, size: int = _DEFAULT_POOL_SIZE):
        self._size = size
        self._pool: asyncio.Queue = asyncio.Queue()
        self._initialized = False

    async def _ensure(self) -> None:
        if self._initialized:
            return
        from core.multi_agent_v2.agents.base.work_agent import WorkAgent
        for i in range(self._size):
            agent = WorkAgent(
                agent_id=f"pool_{i:03d}",
                name=f"worker_{i}",
                light_mode=True,
            )
            self._pool.put_nowait(agent)
        self._initialized = True
        logger.info(f"AgentPool: {self._size} 个 WorkAgent 已预热")

    async def acquire(self, label: str = "") -> Any:
        """从池中借一个 WorkAgent"""
        await self._ensure()
        try:
            return await asyncio.wait_for(self._pool.get(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("AgentPool 耗尽，临时创建新 Agent")
            from core.multi_agent_v2.agents.base.work_agent import WorkAgent
            return WorkAgent(
                agent_id=f"tmp_{uuid.uuid4().hex[:6]}",
                name=label or "tmp_worker",
                light_mode=True,
            )

    def release(self, agent: Any) -> None:
        """归还 WorkAgent 到池"""
        try:
            self._pool.put_nowait(agent)
        except asyncio.QueueFull:
            pass  # 池满就丢掉

    @property
    def available(self) -> int:
        return self._pool.qsize() if self._initialized else self._size

    @property
    def total(self) -> int:
        return self._size


# 全局 AgentPool
_agent_pool = AgentPool()

# ═══════════════════════════════════════════════════════════════════
# 数据类型
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AgentResult:
    """子Agent执行结果"""
    success: bool = False
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    label: str = ""
    agent_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def text(self) -> str:
        """提取纯文本输出

        覆盖 WorkAgent 返回的多种格式:
          - str                   → 直接返回
          - dict[final_answer]    → ReactCore 输出
          - dict[answer]          → results 字段
          - long str(N 步报告)    → WorkAgent 拼接的步骤摘要
        """
        output = self.output
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            for k in ("final_answer", "answer", "output", "result", "text",
                      "summary", "report"):
                v = output.get(k)
                if v and isinstance(v, (str, int, float)):
                    return str(v)
            return str(output)
        if isinstance(output, list):
            # WorkAgent 步骤摘要格式
            texts = []
            for item in output:
                if isinstance(item, dict):
                    for k in ("text", "result", "content", "summary"):
                        v = item.get(k)
                        if v:
                            texts.append(str(v)[:300])
            if texts:
                return "\n".join(texts)
            return str(output)[:2000]
        return str(output or "")

    def data(self) -> Any:
        """提取结构化数据（如 schema 模式下返回的 dict）"""
        if isinstance(self.output, dict):
            for k in ("final_answer", "answer", "output"):
                if k in self.output and self.output[k]:
                    return self.output[k]
            return self.output
        if isinstance(self.output, list):
            return [item for item in self.output if isinstance(item, dict)]
        return self.output

    def __bool__(self):
        return self.success


@dataclass
class WorkflowMeta:
    """编排脚本元信息"""
    name: str
    description: str
    phases: List[Dict[str, str]] = field(default_factory=list)


T = TypeVar("T")


# ═══════════════════════════════════════════════════════════════════
# 编排运行上下文
# ═══════════════════════════════════════════════════════════════════

class RunContext:
    """一次编排运行的上下文

    追踪: 阶段、Agent计数、预算、已启动的任务
    """

    def __init__(self, budget: Optional[int] = None):
        self._phases: List[str] = []
        self._agent_count: int = 0
        self._budget_total: Optional[int] = budget
        self._budget_spent: int = 0
        self._agents: List[Dict] = []
        self._start_time: float = 0.0
        self._logs: List[str] = []

    @property
    def phases(self) -> List[str]:
        return list(self._phases)

    @property
    def agent_count(self) -> int:
        return self._agent_count

    @property
    def remaining_budget(self) -> int:
        if self._budget_total is None:
            return 999999
        return max(0, self._budget_total - self._budget_spent)


# 当前运行上下文（线程不安全，但 asyncio 单线程 OK）
_current_ctx: Optional[RunContext] = None


# ═══════════════════════════════════════════════════════════════════
# 编排 API
# ═══════════════════════════════════════════════════════════════════

def phase(title: str) -> None:
    """开始一个新阶段。后续 agent() 调用归入此阶段。"""
    ctx = _current_ctx
    if ctx is not None:
        ctx._phases.append(title)
    _print(f"  \033[36m📌 阶段: {title}\033[0m")


def log(message: str) -> None:
    """输出进度消息。"""
    ctx = _current_ctx
    if ctx is not None:
        ctx._logs.append(message)
    _print(f"    \033[2m📝 {message}\033[0m")


async def agent(
    prompt: str,
    opts: Optional[Dict] = None,
) -> AgentResult:
    """启动一个子 Agent 执行子任务。

    从 AgentPool 借 WorkAgent（light_mode），执行完归还。

    可以在编排脚本内外使用：
      - 脚本内：自动归入当前 RunContext（阶段追踪 / budget / 计数）
      - 脚本外：独立运行，无阶段追踪

    Args:
        prompt: 子任务描述
        opts:
            label:   显示标签
            timeout: 超时秒数（默认 120）
            schema:  JSON Schema dict（输出会校验为结构化数据）

    Returns:
        AgentResult
    """
    ctx = _current_ctx
    opts = opts or {}
    label = opts.get("label", prompt[:40])
    timeout = opts.get("timeout", 120)

    # 无运行上下文时（独立调用），自动创建
    if ctx is None:
        return await _execute_agent(prompt, label, timeout, opts)

    ctx._agent_count += 1
    agent_id = f"agent_{ctx._agent_count:03d}_{uuid.uuid4().hex[:6]}"

    # 预算检查
    est_tokens = max(len(prompt) * 2, 2000)
    if ctx.remaining_budget < est_tokens:
        _print(f"    \033[33m⚠️ 预算不足，跳过 {label}\033[0m")
        return AgentResult(success=False, error="预算不足", label=label)

    ctx._agents.append({
        "label": label, "agent_id": agent_id, "phase": ctx.phases[-1] if ctx.phases else "",
    })
    _print(f"    \033[34m🚀 [{ctx._agent_count}] {label}\033[0m")

    ar = await _execute_agent(prompt, label, timeout, opts)
    ctx._budget_spent += est_tokens

    return ar


async def _execute_agent(
    prompt: str,
    label: str,
    timeout: int,
    opts: Dict,
) -> AgentResult:
    """核心：从池借 Agent → 执行 → 归还"""
    from core.multi_agent_v2.agents.base.work_agent import WorkAgent as _WA
    from core.multi_agent_v2.agents.base.models import Task

    pool_agent = await _agent_pool.acquire(label)
    agent_id = f"ex_{uuid.uuid4().hex[:6]}"
    pool_agent.agent_id = agent_id
    pool_agent.agent_name = label

    task = Task(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        type="general",
        description=prompt,
    )

    try:
        start = time.time()
        result = await asyncio.wait_for(pool_agent.execute(task), timeout=timeout)
        elapsed = time.time() - start

        ar = AgentResult(
            success=result.success,
            output=result.output,
            error=result.error,
            execution_time=elapsed,
            label=label,
            agent_id=agent_id,
            metadata=result.metadata or {},
        )

        schema = opts.get("schema")
        if schema and result.success:
            validated = _validate_schema(result.output, schema)
            if validated is not None:
                ar.output = validated

        icon = "✅" if result.success else "⚠️"
        detail = f"({elapsed:.1f}s)"
        if not result.success and result.error:
            detail += f" {result.error[:60]}"
        _print(f"    \033[32m{icon} {label} {detail}\033[0m")
        return ar

    except asyncio.TimeoutError:
        _print(f"    \033[33m⏰ {label} (超时)\033[0m")
        return AgentResult(success=False, error="超时", label=label)
    except Exception as e:
        _print(f"    \033[31m❌ {label}: {str(e)[:80]}\033[0m")
        logger.warning(f"Agent [{label}] 异常: {traceback.format_exc()}")
        return AgentResult(success=False, error=str(e), label=label)
    finally:
        _agent_pool.release(pool_agent)


async def parallel(
    thunks: List[Callable[[], Any]],
    max_concurrent: int = 4,
) -> List[AgentResult]:
    """并发执行多个子 Agent。

    Args:
        thunks: 异步函数列表，每个应调 agent(...) 返回 AgentResult
        max_concurrent: 最大并发数

    Returns:
        所有 AgentResult 列表
    """
    n = len(thunks)
    if n == 0:
        return []

    if max_concurrent > 0 and max_concurrent < n:
        log(f"并行 {n} 个 Agent (并发 {max_concurrent})")
        results = []
        for i in range(0, n, max_concurrent):
            batch = thunks[i:i + max_concurrent]
            batch_rs = await _run_parallel_batch(batch)
            results.extend(batch_rs)
        return results

    log(f"并行 {n} 个 Agent")
    return await _run_parallel_batch(thunks)


async def _run_parallel_batch(thunks: List[Callable]) -> List[AgentResult]:
    """执行一批并行任务"""
    tasks = [asyncio.create_task(_run_safe(t)) for t in thunks]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    results = []
    for r in raw:
        if isinstance(r, Exception):
            results.append(AgentResult(success=False, error=str(r)))
        elif isinstance(r, AgentResult):
            results.append(r)
        else:
            results.append(AgentResult(success=True, output=str(r)))
    return results


async def _run_safe(thunk: Callable) -> Any:
    result = thunk()
    if asyncio.iscoroutine(result):
        return await result
    return result


async def pipeline(
    items: List[Any],
    *stages: Callable,
) -> List[Any]:
    """流水线：每个 item 独立流经所有 stage，无等待屏障。

    stage 签名: (prevResult, originalItem, index) -> newResult
    """
    n_items = len(items)
    n_stages = len(stages)
    if n_items == 0 or n_stages == 0:
        return list(items)

    log(f"流水线: {n_items} 个 × {n_stages} 个阶段")

    async def process_one(item, index):
        current = item
        for si, stage in enumerate(stages):
            try:
                r = stage(current, item, index)
                current = await r if asyncio.iscoroutine(r) else r
            except Exception as e:
                logger.warning(f"pipeline #{index} stage {si}: {e}")
                return None
        return current

    raw = await asyncio.gather(
        *[process_one(item, i) for i, item in enumerate(items)],
        return_exceptions=True,
    )
    return [r for r in raw if not isinstance(r, Exception)]


# ═══════════════════════════════════════════════════════════════════
# 工作流注册与运行
# ═══════════════════════════════════════════════════════════════════

class Workflow:
    """一个编排脚本

    用法:
        @workflow(name="调研", description="并行调研多个方案",
                  phases=[{"title": "调研"}, {"title": "分析"}, {"title": "汇总"}])
        async def research_workflow(topic: str):
            phase("调研")
            results = await parallel([
                lambda: agent(f"搜索 {topic} 方案A", {"label": "方案A"}),
                lambda: agent(f"搜索 {topic} 方案B", {"label": "方案B"}),
            ])
            phase("汇总")
            return await agent(f"综合结果给出建议", {"label": "汇总"})
    """

    def __init__(self, name: str, description: str = "",
                 phases: Optional[List[Dict[str, str]]] = None):
        self.meta = WorkflowMeta(name=name, description=description, phases=phases or [])
        self._fn: Optional[Callable] = None

    def __call__(self, fn: Callable):
        self._fn = fn
        _workflow_registry[self.meta.name] = self
        return self

    async def run(self, *args, **kwargs) -> Any:
        """执行此工作流"""
        if self._fn is None:
            raise RuntimeError(f"工作流 {self.meta.name} 未绑定函数")
        return await run_workflow_script(self._fn, *args, **kwargs)


class JSWorflow:
    """JS 编排脚本工作流 — 注册一段 JS 脚本为命名工作流

    用法:
        @js_workflow(name="调研JS", description="JS 实现的编排",
                     phases=[{"title": "搜索"}, {"title": "汇总"}])
        const script = `export const meta = { name: "调研JS", ... };
        export default async function main() { ... }`

    JS 脚本中可直接使用: agent(), parallel(), pipeline(), phase(), log(), budget
    """

    def __init__(self, name: str, description: str = "",
                 phases: Optional[List[Dict[str, str]]] = None):
        self.meta = WorkflowMeta(name=name, description=description, phases=phases or [])
        self._script: Optional[str] = None

    def __call__(self, script: str):
        self._script = script
        _workflow_registry[self.meta.name] = self
        return self

    async def run(self, *args, **kwargs) -> Any:
        """通过 JS 运行时执行脚本"""
        if not self._script:
            raise RuntimeError(f"JS 工作流 {self.meta.name} 未绑定脚本")

        # 注入参数：将 kwargs 注入为 JS 全局变量
        script = self._script
        for k, v in kwargs.items():
            if k not in ("meta",) and not script.startswith("//"):
                # 在 meta 前注入变量
                script = script.replace(
                    "export const meta",
                    f"const {k} = {json.dumps(v)};\nexport const meta",
                )

        from core.multi_agent_v2.orchestration.js_orchestrator import \
            run_js_workflow as _run_js
        return await _run_js(script)


# 工作流注册表
_workflow_registry: Dict[str, Workflow] = {}

# 简写装饰器，与 Workflow 类等价
workflow = Workflow

# JS 编排简写
js_workflow = JSWorflow


def get_workflow(name: str) -> Optional[Workflow]:
    """按名称获取已注册的工作流"""
    return _workflow_registry.get(name)


def list_workflows() -> List[str]:
    """列出所有已注册的工作流名称"""
    return list(_workflow_registry.keys())


async def run_workflow(name: str, *args, **kwargs) -> Any:
    """按名称运行已注册的工作流"""
    wf = _workflow_registry.get(name)
    if wf is None:
        raise ValueError(f"未知工作流: {name}，可用: {list_workflows()}")
    return await wf.run(*args, **kwargs)


async def run_workflow_script(
    script_fn: Callable,
    *args,
    budget: Optional[int] = None,
    **kwargs,
) -> Any:
    """运行一个编排脚本函数"""
    global _current_ctx
    ctx = RunContext(budget=budget)
    ctx._start_time = time.time()
    prev = _current_ctx
    _current_ctx = ctx

    try:
        # 执行编排脚本
        result = await script_fn(*args, **kwargs)
        elapsed = time.time() - ctx._start_time

        _print(f"\n  \033[36m━━━ 编排完成 ━━━\033[0m")
        _print(f"  Agent: {ctx.agent_count} 个  ·  耗时: {elapsed:.1f}s")
        if ctx._budget_total:
            _print(f"  预算: {ctx._budget_spent}/{ctx._budget_total} tokens")
        _print(f"  阶段: {' → '.join(ctx.phases) if ctx.phases else '-'}")

        return result
    except Exception as e:
        logger.error(f"编排脚本异常: {traceback.format_exc()}")
        raise
    finally:
        _current_ctx = prev


# ═══════════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════════

def _print(text: str) -> None:
    """统一输出"""
    try:
        print(text, flush=True)
    except Exception:
        pass


def _validate_schema(output: Any, schema: Dict) -> Optional[Any]:
    """简易 schema 校验（仅检查必填字段存在）"""
    if not isinstance(schema, dict):
        return None
    if not isinstance(output, dict):
        return None
    required = schema.get("required", [])
    for field_name in required:
        if field_name not in output:
            logger.warning(f"schema 校验: 缺少必填字段 {field_name}")
            return {"_error": f"缺少 {field_name}", **output}
    return output


def reset() -> None:
    """重置全局状态"""
    global _current_ctx
    _current_ctx = None


__all__ = [
    "phase", "log", "agent", "AgentResult",
    "parallel", "pipeline",
    "Workflow", "workflow",
    "JSWorflow", "js_workflow",
    "get_workflow", "list_workflows", "run_workflow",
    "run_workflow_script", "reset",
]
