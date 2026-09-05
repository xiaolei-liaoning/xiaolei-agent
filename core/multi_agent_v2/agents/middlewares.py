"""
中间件实现库 — 精简版

只保留核心中间件：
  - ReActDepthMiddleware       — 深度控制 + 连续失败检测
  - ReflectionMiddleware       — 定期反思，写入 temp_memory
  - KEPAMiddleware             — 知识沉淀 + 跨 Agent 共享（SharedBus）
  - LoopDetectionMiddleware    — 双层循环检测：哈希 + 频率
  - ClarificationMiddleware    — 拦截澄清请求，中断等待用户确认
  - TodoMiddleware             — 防止 agent 在有未完成任务时过早退出
  - PermissionMiddleware       — 三级权限控制 + Shell 命令安全检查
  - HookMiddleware             — 工具调用前后 Hook 拦截器
"""

import asyncio
import hashlib
import json
import logging

from core.multi_agent_v2.tools.json_util import safe_parse_json
import os
import time
from typing import Any, Callable, Dict, List, Optional

from .middleware import BaseMiddleware, RunContext, HookResult

logger = logging.getLogger(__name__)

KEPA_PREFIX = "── KEPA 分析 ──"


# ════════════════════════════════════════════════════════════════
# ReActDepthMiddleware — ReAct 深度控制
# ════════════════════════════════════════════════════════════════

class ReActDepthMiddleware(BaseMiddleware):
    """追踪 ReAct 深度，防止无限循环 + 检测连续失败"""
    HOOKS = ("on_llm_invoke", "on_tool_end")

    MAX_DEPTH = 30

    async def on_llm_invoke(self, ctx: RunContext) -> None:
        max_depth = max(self.MAX_DEPTH, ctx.max_iterations)
        if ctx.react_depth > max_depth:
            ctx.interrupted = True
            logger.warning(f"ReAct 深度超过 {max_depth}，终止执行")

    async def on_tool_end(self, ctx: RunContext) -> None:
        if ctx.tool_results:
            last = ctx.tool_results[-1]
            tc = last.get("tool_call", {})
            name = tc.get("name", "")
            if name and not last.get("success"):
                ctx.consecutive_failures[name] = ctx.consecutive_failures.get(name, 0) + 1
            elif name:
                ctx.consecutive_failures[name] = 0


# ════════════════════════════════════════════════════════════════
# ReflectionMiddleware — 执行反思
# ════════════════════════════════════════════════════════════════

class ReflectionMiddleware(BaseMiddleware):
    """定期对执行结果进行反思，沉淀经验到 temp_memory"""
    HOOKS = ("on_tool_end",)

    REFLECTION_INTERVAL = 3  # 每 N 轮反思一次

    async def on_tool_end(self, ctx: RunContext) -> None:
        if ctx.iteration < 2:
            return
        if ctx.iteration % self.REFLECTION_INTERVAL != 0:
            return

        recent = ctx.tool_results[-self.REFLECTION_INTERVAL:]
        success = sum(1 for r in recent if r.get("success"))
        total = len(recent)

        reflection = {
            "iteration": ctx.iteration,
            "success_rate": success / total if total > 0 else 0,
            "total_calls": len(ctx.tool_results),
            "timestamp": time.time(),
        }
        ctx.reflection_history.append(reflection)

        if success == 0 and total > 0:
            logger.warning(f"反思: 连续 {total} 次工具调用全部失败")
            if self.agent:
                self.agent.temp_memory["reflection"] = {
                    "problem": f"连续 {total} 次工具调用全部失败",
                    "tools_used": [r.get("tool_call", {}).get("name", "?") for r in recent],
                    "suggestion": "换工具或直接回答",
                    "iteration": ctx.iteration,
                }


# ════════════════════════════════════════════════════════════════
# KEPAMiddleware — KEPA 闭环
# ════════════════════════════════════════════════════════════════

class KEPAMiddleware(BaseMiddleware):
    """KEPA 闭环 — 知识沉淀 + 跨 Agent 共享

    - on_tool_end: 从工具结果提取知识 → 存入 SharedBus 共享存储
    - on_llm_invoke: 查询 SharedBus 中的共享知识 → 注入到 LLM 提示词
    """
    HOOKS = ("on_llm_invoke", "on_tool_end", "on_finish")
    PROACTIVE_INTERVAL = 3  # 每 N 轮主动读一次 bus

    def __init__(self):
        super().__init__()
        self._injected_bus_keys: set = set()

    async def on_llm_invoke(self, ctx: RunContext) -> None:
        """注入 KEPA 分析（两种路径：异常触发 + 主动每 N 轮）"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.tool_results or ctx.iteration < 2:
            return

        total = len(ctx.tool_results)
        success = sum(1 for r in ctx.tool_results if r.get("success"))
        fail = total - success
        has_issues = fail >= 2 or (total >= 3 and success / total < 0.5)
        is_proactive = ctx.iteration % self.PROACTIVE_INTERVAL == 0

        if not has_issues and not ctx.last_error and not is_proactive:
            return

        try:
            shared, new_keys = await self._fetch_new_knowledge(ctx)
            evaluation_text = self._build_evaluation(ctx)
            planning_text = self._build_planning(ctx)

            lines = [f"\n{KEPA_PREFIX}"]
            if shared:
                lines.append(f"[跨Agent参考] {shared}")
            if has_issues or ctx.last_error:
                lines.append(f"评估: {evaluation_text}")
                lines.append(f"规划: {planning_text}")
            lines.append("──")
            kepa_text = "\n".join(lines)
            ctx.knowledge_context += kepa_text
            if len(ctx.knowledge_context) > 3000:
                ctx.knowledge_context = ctx.knowledge_context[-3000:]

            self._injected_bus_keys.update(new_keys)
        except Exception as e:
            logger.debug(f"KEPA 分析注入失败: {e}")

    async def _fetch_new_knowledge(self, ctx: RunContext):
        """从 SharedBus 获取新的（未被注入过的）知识
        
        Returns:
            (summary_text, new_keys_set)
        """
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()

            relevant_tags = set()
            _flags = getattr(ctx, '_task_flags', None)
            if _flags:
                if _flags.get("search"):
                    relevant_tags.add("search")
                if _flags.get("code"):
                    relevant_tags.add("code")
                if _flags.get("report") or _flags.get("project_analysis"):
                    relevant_tags.add("analysis")
                if _flags.get("file_operation") or _flags.get("desktop_save") or _flags.get("edit"):
                    relevant_tags.add("file")
            else:
                desc_lower = ctx.task_description.lower()
                if any(kw in desc_lower for kw in ["搜索", "查询", "百度", "热搜", "search"]):
                    relevant_tags.add("search")
                if any(kw in desc_lower for kw in ["代码", "程序", "脚本", "code", "python"]):
                    relevant_tags.add("code")
                if any(kw in desc_lower for kw in ["数据", "分析", "统计", "data", "analysis"]):
                    relevant_tags.add("analysis")
                if any(kw in desc_lower for kw in ["文件", "写入", "保存", "file", "write"]):
                    relevant_tags.add("file")
            relevant_tags.add("kepa")

            if not relevant_tags:
                return "", set()

            snippets = []
            new_keys = set()
            for tag in relevant_tags:
                results = await bus.search_knowledge(tag)
                for key, entry in results.items():
                    if key in self._injected_bus_keys:
                        continue
                    meta = entry.get("meta", {})
                    summary = meta.get("summary", "")
                    source = meta.get("source", "")
                    if summary and len(str(summary)) > 10:
                        snippets.append(f"[{source}]: {summary[:200]}")
                        new_keys.add(key)
            if snippets:
                return " | ".join(snippets[:3]), new_keys
            return "", set()
        except Exception:
            return "", set()

    async def on_tool_end(self, ctx: RunContext) -> None:
        """工具执行后：提取知识 → 存入 SharedBus + temp_memory"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.tool_results:
            return

        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()

            for r in reversed(ctx.tool_results):
                if not r.get("success"):
                    continue
                tc = r.get("tool_call", {})
                name = tc.get("name", "")
                if not name:
                    continue

                result_str = str(r.get("result", ""))
                summary = result_str[:200]
                if len(summary) < 10:
                    continue

                tags = {"kepa"}
                if name in ("search", "fetch_url", "rag_search"):
                    tags.add("search")
                elif name in ("execute_python", "execute_shell"):
                    tags.add("code")
                elif name == "write_file":
                    tags.add("file")
                if "分析" in ctx.task_description or "analysis" in ctx.task_description:
                    tags.add("analysis")
                # 中文关键词 tag — 让 WorkAgent 用中文也能搜到
                import re
                cn_kw = set(re.findall(r'[一-鿟]{2,}', ctx.task_description)[:3])
                tags.update(cn_kw)

                key = f"kepa:{name}:{ctx.iteration}"
                source = ctx.profile.get("agent_id", "unknown")
                await bus.store_knowledge(key, {"result": summary, "tool": name},
                                          tags=tags, source=source, summary=summary)

                if self.agent:
                    self.agent.temp_memory["kepa_summary"] = {
                        "tool": name,
                        "summary": summary[:100],
                        "iteration": ctx.iteration,
                        "tags": list(tags),
                    }
                break
        except Exception as e:
            logger.debug(f"KEPA 知识沉淀失败: {e}")

    async def on_finish(self, ctx: RunContext) -> None:
        """执行完成：最终知识摘要到 SharedBus + 清理过期知识"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.final_answer:
            return
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()
            source = ctx.profile.get("agent_id", "unknown")
            await bus.store_knowledge(
                f"kepa:final:{source}",
                {"final": ctx.final_answer[:500]},
                tags={"kepa", "final"},
                source=source,
                summary=f"最终结果: {ctx.final_answer[:200]}",
            )
            # 任务结束，清理过期知识（默认30分钟）
            await bus.cleanup_old_knowledge()
        except Exception:
            pass

    def _build_evaluation(self, ctx: RunContext) -> str:
        if not ctx.tool_results:
            return "尚未开始执行，需要收集数据"
        success_rate = sum(1 for r in ctx.tool_results if r.get("success")) / max(len(ctx.tool_results), 1)
        if success_rate > 0.7:
            return "执行顺利，可继续当前策略"
        elif any(count >= 2 for count in ctx.consecutive_failures.values()):
            return "存在连续失败，建议切换方法"
        return "需要继续收集信息"

    def _build_planning(self, ctx: RunContext) -> str:
        if not ctx.tool_results:
            return "开始执行"
        fail_count = sum(1 for r in ctx.tool_results if not r.get("success"))
        if fail_count >= 3:
            return "连续失败，建议换用替代工具或直接输出结果"
        return "继续当前任务"


# ════════════════════════════════════════════════════════════════
# LoopDetectionMiddleware — 双层循环检测
# ════════════════════════════════════════════════════════════════

class LoopDetectionMiddleware(BaseMiddleware):
    """多层循环检测：哈希 + 频率 + doom loop，防止工具调用死循环

    Layer 1: 滑动窗口内相同工具调用哈希重复检测 (参考 deerflow)
    Layer 2: 单工具累计调用频率检测（支持工具级阈值覆盖）
    Layer 3: Doom Loop 检测 — 同轮内相同工具重复 ≥3 次 (参考 opencode)
    Layer 4: MCP 错误结果重复检测
    Layer 5: 文件写入路径重复检测
    Layer 6: 跨多轮工具调用模式循环检测

    同时检测历史已执行工具（ctx.tool_results）和 LLM 刚生成待执行的工具
    （ctx._pending_tool_calls），避免晚一轮检测。
    """
    HOOKS = ("on_plan_check",)

    # 工具级频率阈值覆盖（参考 deerflow 的 per-tool config）
    TOOL_FREQ_LIMITS = {
        "read_file": {"warn": 30, "hard": 999},  # 不设硬上限
        "execute_shell": {"warn": 12, "hard": 25},
        "execute_python": {"warn": 6, "hard": 12},
        "web_search": {"warn": 8, "hard": 20},    # ponytail: 搜索分析类任务需要更多次
        "fetch_url": {"warn": 8, "hard": 20},
        "write_file": {"warn": 5, "hard": 10},
        "edit_file": {"warn": 5, "hard": 10},
        "search_files": {"warn": 15, "hard": 30},
        "codegraph_explore": {"warn": 40, "hard": 80},
        "codegraph_files": {"warn": 40, "hard": 100},
    }

    def __init__(
        self,
        warn_threshold: int = 8,
        hard_limit: int = 20,
        tool_freq_warn: int = 8,
        tool_freq_hard_limit: int = 20,
        window_size: int = 50,
    ):
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.tool_freq_warn = tool_freq_warn
        self.tool_freq_hard_limit = tool_freq_hard_limit
        self.window_size = window_size
        self._history: List[str] = []
        self._tool_freq: Dict[str, int] = {}
        self._warned_hashes: set = set()
        self._warned_tools: set = set()
        # Layer 4: error dedup — track error messages per tool
        self._tool_errors: Dict[str, List[str]] = {}
        self._warned_duplicate_errors: set = set()

    def reset_task_state(self):
        """任务开始时重置循环检测状态"""
        self._history = []
        self._tool_freq = {}
        self._warned_hashes = set()
        self._warned_tools = set()
        self._tool_errors = {}
        self._warned_duplicate_errors = set()

    def _get_tool_limits(self, name: str) -> tuple:
        """获取工具级频率阈值（支持覆盖），参考 deerflow 的 per-tool config"""
        limits = self.TOOL_FREQ_LIMITS.get(name)
        if limits:
            return limits["warn"], limits["hard"]
        return self.tool_freq_warn, self.tool_freq_hard_limit

    _PROFILE_THRESHOLDS = {
        "game": {"write_file": {"warn": 4, "hard": 8}},
        "code": {"write_file": {"warn": 3, "hard": 6}},
        "design": {"write_file": {"warn": 4, "hard": 8}},
        "report": {"write_file": {"warn": 3, "hard": 5}},
    }

    def set_profile_thresholds(self, profile_id: str) -> None:
        """根据任务画像动态调整工具频率阈值

        游戏/设计类任务需要反复迭代文件写入，放宽阈值；
        代码/报告类任务保持较严格限制。
        """
        override = self._PROFILE_THRESHOLDS.get(profile_id)
        if override:
            for tool_name, limits in override.items():
                old = self.TOOL_FREQ_LIMITS.get(tool_name, {"warn": self.tool_freq_warn, "hard": self.tool_freq_hard_limit})
                self.TOOL_FREQ_LIMITS[tool_name] = limits
                logger.info(
                    f"LoopDetection: profile={profile_id}, {tool_name} 阈值 "
                    f"warn: {old['warn']}→{limits['warn']}, hard: {old['hard']}→{limits['hard']}"
                )

    def _normalize_read_file_args(self, args: Dict) -> Dict:
        """read_file 参数归一化：将行区间分桶到 200 行块

        参考 deerflow 的 line-range bucketing
        """
        salient = {}
        for k, v in args.items():
            if k in ("path", "filepath"):
                salient[k] = v
            elif k in ("offset", "start_line", "end_line", "limit"):
                try:
                    val = int(v) if v else 0
                    bucket = (val // 200) * 200
                    salient[k] = f"{bucket}+"
                except (ValueError, TypeError):
                    salient[k] = v
        return salient

    def _hash_tool_calls(self, tool_calls: List[Dict]) -> str:
        """对一组工具调用取哈希，用于滑动窗口比较

        参考 deerflow：
        - read_file：行区间分桶到 200 行块，避免频繁换行误报
        - write_file/edit_file：完整参数哈希（含内容差异）
        - 其他工具：仅关键字段
        """
        items = []
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                args = safe_parse_json(args_str) if isinstance(args_str, str) else args_str


            except (json.JSONDecodeError, TypeError):
                args = {}

            if name == "read_file":
                salient = self._normalize_read_file_args(args if isinstance(args, dict) else {})
            elif name in ("write_file", "edit_file"):
                salient = dict(args) if isinstance(args, dict) else {}
            else:
                salient = {
                    k: v
                    for k, v in (args if isinstance(args, dict) else {}).items()
                    if k in ("path", "url", "query", "command", "code")
                }

            items.append(
                f"{name}:{json.dumps(salient, sort_keys=True, default=str)}"
            )
        items.sort()
        blob = json.dumps(items, sort_keys=True)
        return hashlib.md5(blob.encode()).hexdigest()[:12]

    def _normalize_to_function_calls(self, ctx: RunContext) -> List[Dict]:
        """将历史已执行工具 + 本轮待执行工具归一化为统一格式"""
        calls = []

        # 1. 历史已执行工具（来自 tool_results）
        if ctx.tool_results:
            last_results = ctx.tool_results[-self.window_size:]
            for r in last_results:
                tc = r.get("tool_call", {})
                if tc.get("name"):
                    calls.append({
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("arguments", {}), default=str),
                        }
                    })

        # 2. 本轮 LLM 刚生成但尚未执行的工具（来自 _pending_tool_calls）
        pending = getattr(ctx, '_pending_tool_calls', None)
        if pending:
            for tc in pending:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                if name:
                    calls.append({
                        "function": {
                            "name": name,
                            "arguments": fn.get("arguments", "{}"),
                        }
                    })

        return calls

    async def on_plan_check(self, ctx: RunContext) -> None:
        tool_calls = self._normalize_to_function_calls(ctx)
        if not tool_calls:
            return

        # Layer 0: 检测 LLM 是否在重复写已完成步骤的文件
        if ctx.plan and any(s.status == "done" for s in ctx.plan):
            _pending = [s for s in ctx.plan if s.status == "pending"]
            if _pending:
                for tc in tool_calls:
                    name = tc.get("function", {}).get("name", "")
                    args_str = tc.get("function", {}).get("arguments", "{}")
                    try:
                        args = safe_parse_json(args_str) if isinstance(args_str, str) else args_str
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    _path = args.get("path", "")
                    if name == "write_file" and _path:
                        _pending_next = _pending[0]
                        _next_has_path = any(kw in (_pending_next.description or "").lower()
                                            for kw in _path.lower().split("/")[-1].replace(".", " ").split())
                        if not _next_has_path:
                            ctx.forced_instructions = (
                                f"⚠️ 不要写已完成步骤的文件！当前应该执行：{_pending_next.description}"
                            )
                            return HookResult(jump_to="retry",
                                reason=f"文件 {_path} 不属于当前步骤，请执行：{_pending_next.description}")
                    if name == "write_file" and _path:
                        # 检查这个路径在当前步骤已完成列表里
                        _done_paths = set()
                        for _tr in (ctx.tool_results or []):
                            _tc = _tr.get("tool_call", {})
                            if _tc.get("name") == "write_file" and _tr.get("success"):
                                _p = _tc.get("arguments", {}).get("path", "")
                                if _p:
                                    _done_paths.add(os.path.expanduser(_p))
                        _exp_path = os.path.expanduser(_path)
                        if _exp_path in _done_paths and _pending:
                            _pstep = _pending[0]
                            ctx.forced_instructions = (
                                f"⚠️ {_path} 已写入完成！立即执行下一步：{_pstep.description}"
                            )
                            return HookResult(jump_to="retry",
                                reason=f"{_path} 已经写完，请执行下一步：{_pstep.description}")

        call_hash = self._hash_tool_calls(tool_calls)

        # 滑动窗口
        self._history.append(call_hash)
        if len(self._history) > self.window_size:
            self._history = self._history[-self.window_size :]

        # Layer 1: 哈希检测
        count = self._history.count(call_hash)
        if count >= self.hard_limit:
            ctx.interrupted = True
            ctx.interrupted_reason = (
                f"循环检测：相同工具调用重复 {count} 次，强制停止"
            )
            ctx.last_error = (
                f"循环检测：相同工具调用重复 {count} 次，强制停止"
            )
            return HookResult(jump_to="end", reason=ctx.last_error)

        if count >= self.warn_threshold and call_hash not in self._warned_hashes:
            self._warned_hashes.add(call_hash)
            ctx.warnings.append(
                "[循环警告] 你正在重复相同的工具调用。请立即停止调用工具，输出最终答案。"
            )

        # Layer 2: 频率检测（支持工具级阈值，参考 deerflow）
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            if not name:
                continue
            self._tool_freq[name] = self._tool_freq.get(name, 0) + 1

            _warn, _hard = self._get_tool_limits(name)
            if self._tool_freq[name] >= _hard:
                ctx.interrupted = True
                ctx.needs_user_intervention = True
                ctx.interrupted_reason = (
                    f"循环检测：工具 {name} 已调用 "
                    f"{self._tool_freq[name]} 次（阈值={_hard}），强制停止"
                )
                ctx.last_error = (
                    f"循环检测：工具 {name} 已调用 "
                    f"{self._tool_freq[name]} 次（阈值={_hard}），强制停止"
                )
                return HookResult(jump_to="end", reason=ctx.last_error)

            if (
                self._tool_freq[name] >= _warn
                and name not in self._warned_tools
            ):
                self._warned_tools.add(name)
                ctx.warnings.append(
                    f"[循环警告] 工具 {name} 已调用 {self._tool_freq[name]} 次（阈值={_warn}）。"
                    "请考虑换用其他工具或直接输出结果。"
                )

        # Layer 3: Doom Loop 检测 — 同轮内相同工具+参数 ≥3 次 (参考 opencode)
        _pending = getattr(ctx, '_pending_tool_calls', None)
        if _pending and len(_pending) >= 3:
            _name_counter: Dict[str, int] = {}
            for _tc in _pending:
                _n = _tc.get("function", {}).get("name", "")
                if _n:
                    _name_counter[_n] = _name_counter.get(_n, 0) + 1
            for _n, _c in _name_counter.items():
                if _c >= 3:
                    ctx.warnings.append(
                        f"[Doom Loop] 本轮内工具 {_n} 被重复调用 {_c} 次。"
                        "请立即停止，不要重复调用相同工具。"
                    )
                    break

        # Layer 4: 错误结果重复检测（MCP 工具返回相同错误 ≥2 次 → 强制切换策略）
        # 跳过环境限制错误（沙盒超时、GUI 库不支持等），这些不应触发重试警告
        if ctx.tool_results and len(ctx.tool_results) >= 2:
            _last = ctx.tool_results[-1]
            _prev = ctx.tool_results[-2]
            _last_name = _last.get("tool_call", {}).get("name", "")
            _prev_name = _prev.get("tool_call", {}).get("name", "")
            if not _last.get("success") and _last_name and _last_name == _prev_name:
                _last_err = str(_last.get("result", _last.get("error", "")))[:200]
                _prev_err = str(_prev.get("result", _prev.get("error", "")))[:200]
                # 跳过环境限制错误
                _is_env_error = "[环境限制]" in _last_err or "[环境限制]" in _prev_err
                if not _is_env_error and _last_err and _prev_err and _last_err == _prev_err:
                    _err_key = f"{_last_name}:{_last_err[:80]}"
                    if _err_key not in self._warned_duplicate_errors:
                        self._warned_duplicate_errors.add(_err_key)
                        ctx.warnings.append(
                            f"[重复错误] 工具 {_last_name} 连续返回相同错误。请换用其他工具或方法，不要再重试此工具。"
                        )

        # Layer 5: 文件写入路径检测（防止反复写同一文件）
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            if name not in ("write_file", "file"):
                continue
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                args = safe_parse_json(args_str) if isinstance(args_str, str) else args_str


            except (json.JSONDecodeError, TypeError):
                args = {}
            path = args.get("path", args.get("filepath", ""))
            if not path:
                continue
            path_key = f"write:{os.path.abspath(os.path.expanduser(path))}"
            self._tool_freq[path_key] = self._tool_freq.get(path_key, 0) + 1
            if self._tool_freq[path_key] == 5:
                ctx.warnings.append(
                    f"[循环警告] 文件 {path} 已被写入5次。"
                    "请使用 force=true 参数覆盖，或换用其他文件名，或直接输出结果。"
                )
                return HookResult(jump_to="continue", reason="循环警告")
            if self._tool_freq[path_key] >= 10:
                ctx.interrupted = True
                ctx.interrupted_reason = (
                    f"循环检测：文件 {path} 已被写入 {self._tool_freq[path_key]} 次，"
                    "请停止重复写入，直接输出最终结果"
                )
                ctx.last_error = (
                    f"循环检测：文件 {path} 已被写入 {self._tool_freq[path_key]} 次，"
                    "请停止重复写入，直接输出最终结果"
                )
                return HookResult(jump_to="end", reason=ctx.last_error)

        # Layer 6: 模式循环检测
        if len(ctx.tool_results) >= 8:
            recent_names = [r.get("tool_call", {}).get("name", "") for r in ctx.tool_results[-8:]]
            for pattern_len in range(2, 5):
                if len(recent_names) >= pattern_len * 2:
                    pattern = recent_names[-pattern_len:]
                    prev = recent_names[-pattern_len*2:-pattern_len]
                    if prev == pattern and all(n for n in pattern):
                        ctx.warnings.append(
                            f"[模式循环] 检测到工具重复模式: {' → '.join(pattern)}。请跳出循环！"
                        )
                        break

# ════════════════════════════════════════════════════════════════
# ClarificationMiddleware — 澄清请求拦截
# ════════════════════════════════════════════════════════════════

class ClarificationMiddleware(BaseMiddleware):
    """拦截 LLM 输出中的澄清请求模式，中断执行等待用户确认

    在 on_plan_check 阶段检测 LLM 回复中是否包含结构化澄清请求
    （如 [CLARIFICATION] 标记或问号密集段落），若命中则中断并输出问题。
    """
    HOOKS = ("on_plan_check",)

    # 匹配 LLM 可能输出的澄清请求模式
    CLARIFICATION_PATTERNS = [
        "[CLARIFICATION]",
        "[需要确认]",
        "[请确认]",
        "[clarification]",
    ]

    async def on_plan_check(self, ctx: RunContext) -> Optional[HookResult]:
        # 检查 final_answer 或 _pending_reply（含工具调用场景的澄清）
        reply_text = ctx.final_answer or getattr(ctx, '_pending_reply', '')
        if not reply_text:
            return None

        answer_lower = reply_text.lower()

        for pattern in self.CLARIFICATION_PATTERNS:
            if pattern.lower() in answer_lower:
                ctx.interrupted = True
                ctx._pending_tool_calls = None
                ctx.final_answer = f"需要您的确认：\n\n{reply_text}"
                return HookResult(jump_to="end", reason="需要用户澄清")

        if len(reply_text) < 500 and reply_text.count("?") + reply_text.count("？") >= 2:
            if ctx.tool_results and len(ctx.tool_results) > 1:
                ctx.interrupted = True
                ctx._pending_tool_calls = None
                ctx.final_answer = f"需要您的确认：\n\n{reply_text}"
                return HookResult(jump_to="end", reason="需要用户澄清")


# ════════════════════════════════════════════════════════════════
# ReasoningMiddleware — 每轮先思考再调工具
# ════════════════════════════════════════════════════════════════

class ReasoningMiddleware(BaseMiddleware):
    """展示 LLM 思考过程，不强制"""
    HOOKS = ("on_plan_check",)

    async def on_plan_check(self, ctx: RunContext) -> Optional[HookResult]:
        pending = getattr(ctx, '_pending_tool_calls', None)
        if not pending:
            return None
        reply = getattr(ctx, '_pending_reply', '') or ''
        import re
        m = re.search(r'<thinking>(.*?)</thinking>', reply, re.DOTALL)
        if m:
            txt = m.group(1).strip()[:200]
            print(f"    \033[2mThought: {txt}\033[0m")
        return None


# ════════════════════════════════════════════════════════════════
# TodoMiddleware — 任务完整性保护
# ════════════════════════════════════════════════════════════════

class TodoMiddleware(BaseMiddleware):
    """防止 agent 在有未完成任务时过早退出

    当工具调用失败率过高且 agent 试图输出 final_answer 时，
    注入提醒并清除 final_answer，强制继续执行。
    """
    HOOKS = ("on_finish",)

    _MAX_REMINDERS = 2

    def __init__(self):
        self._reminder_count = 0

    def reset_task_state(self):
        """任务开始时重置提醒计数"""
        self._reminder_count = 0

    async def on_finish(self, ctx: RunContext) -> None:
        # 仅在 agent 试图输出 final_answer 时检查
        if not ctx.final_answer:
            return

        if not ctx.tool_results:
            return

        total = len(ctx.tool_results)
        success = sum(1 for r in ctx.tool_results if r.get("success"))
        fail = total - success

        # 失败过半 + 至少 2 次失败 + 还有提醒额度 → 阻止过早退出
        if fail > success and fail >= 2 and self._reminder_count < self._MAX_REMINDERS:
            self._reminder_count += 1
            ctx.warnings.append(
                f"[任务未完成] 已执行 {total} 次工具调用，其中 {fail} 次失败。请检查失败原因并重试，不要过早结束。"
            )
            ctx.final_answer = ""
            ctx.interrupted = False  # 不中断，让 ReAct 继续循环


# ════════════════════════════════════════════════════════════════
# SummarizationMiddleware — 长对话自动压缩
# ════════════════════════════════════════════════════════════════

class TruncationMiddleware(BaseMiddleware):
    """历史截断 — 当消息历史过长时截断旧的 tool 交互

    不使用 LLM 摘要（避免额外开销），而是直接截断旧的工具调用结果，
    只保留最近 N 轮的完整交互。

    注: 原名 SummarizationMiddleware，因实际只做截断而改名。
    """
    HOOKS = ("on_llm_invoke",)

    def __init__(self, keep_recent: int = 5, max_messages: int = 40):
        self.keep_recent = keep_recent
        self.max_messages = max_messages

    async def on_llm_invoke(self, ctx: RunContext) -> None:
        """在构建消息前，清理过旧的 tool_results"""
        if not ctx.tool_results or len(ctx.tool_results) <= self.keep_recent:
            return

        # 只保留最近 N 轮的 tool_results
        # 旧的已经被 progressive truncation 处理了，这里进一步清理
        n_to_remove = len(ctx.tool_results) - self.keep_recent * 2
        if n_to_remove > 0:
            ctx.tool_results = ctx.tool_results[n_to_remove:]


# ════════════════════════════════════════════════════════════════
# CompactionMiddleware — 智能上下文压缩（对标 Opencode compaction）
# ════════════════════════════════════════════════════════════════

class CompactionMiddleware(BaseMiddleware):
    """智能上下文压缩中间件 — 复用 ctx.context_budget，不覆盖"""
    HOOKS = ("on_llm_invoke",)

    async def on_llm_invoke(self, ctx: RunContext) -> None:
        """LLM 调用前检查上下文是否溢出，必要时压缩"""
        budget = getattr(ctx, 'context_budget', None)
        if budget is None:
            from .context_budget import ContextBudgetManager
            budget = ContextBudgetManager()
            ctx.context_budget = budget
        try:
            await budget.async_check_and_compact(ctx)
        except Exception:
            budget.check_and_compact(ctx)


# ════════════════════════════════════════════════════════════════
# PermissionMiddleware — 三级权限控制
# ════════════════════════════════════════════════════════════════

class PermissionMiddleware(BaseMiddleware):
    """三级权限控制 + Shell 命令安全检查

    在工具执行前检查权限和安全性：
    1. 调用 PermissionService 检查权限级别
    2. 调用 ShellGuard 扫描命令安全性
    3. 根据结果决定执行/拒绝/询问用户
    """
    HOOKS = ("on_wrap_tool_call",)  # 只注册洋葱模式钩子

    def __init__(self, config_path: Optional[str] = None, sandbox_mode: bool = False):
        from core.multi_agent_v2.tools.permission import get_permission_service
        from core.multi_agent_v2.tools.shell_guard import get_shell_guard
        self.permission_service = get_permission_service(config_path)
        self.shell_guard = get_shell_guard(sandbox_mode)

    async def on_wrap_tool_call(self, ctx: RunContext, next_mw: Callable) -> Any:
        """在工具执行前实时检查权限和安全性（洋葱模式）"""
        tool_name = getattr(ctx, '_current_tool_name', '')
        arguments = getattr(ctx, '_current_tool_arguments', {})

        if not tool_name:
            return await next_mw()

        # 检查权限
        perm_result = self.permission_service.check(tool_name, arguments)

        if not perm_result.allowed:
            if perm_result.need_ask:
                # 需要用户确认
                return {
                    "success": False,
                    "result": {
                        "error": f"权限检查：需要您的确认\n\n工具: {tool_name}\n原因: {perm_result.reason}\n\n请回复 '允许' 或 '拒绝' 继续执行。"
                    },
                    "tool_call": {"name": tool_name, "arguments": arguments},
                }
            else:
                # 禁止执行
                logger.warning(f"权限拒绝：{tool_name} - {perm_result.reason}")
                return {
                    "success": False,
                    "result": {
                        "error": f"权限拒绝：{tool_name}\n\n原因: {perm_result.reason}\n\n该操作已被安全策略禁止。"
                    },
                    "tool_call": {"name": tool_name, "arguments": arguments},
                }

        # 如果是 Shell 命令，额外进行安全扫描
        if tool_name in ("execute_shell", "execute_command", "execute_script"):
            command = arguments.get("command", "") or arguments.get("code", "")
            if command:
                scan_result = self.shell_guard.scan(command)

                if not scan_result.safe:
                    high_risks = [r for r in scan_result.risks if r.level == "high"]
                    if high_risks:
                        risk_desc = "\n".join([f"  - {r.description}" for r in high_risks])
                        logger.warning(f"安全扫描失败：{tool_name} - {risk_desc}")
                        return {
                            "success": False,
                            "result": {
                                "error": f"安全扫描失败：检测到高危操作\n\n命令: {command}\n\n风险项:\n{risk_desc}\n\n建议: 请修改命令或联系管理员。"
                            },
                            "tool_call": {"name": tool_name, "arguments": arguments},
                        }

                    # 中危风险，记录警告但继续执行
                    medium_risks = [r for r in scan_result.risks if r.level == "medium"]
                    if medium_risks:
                        risk_desc = "、".join([r.description for r in medium_risks])
                        ctx.warnings.append(
                            f"[安全警告] 检测到中危风险: {risk_desc}。请确保操作安全。"
                        )

        # 权限检查通过，继续执行
        return await next_mw()


# ════════════════════════════════════════════════════════════════
# HookMiddleware — 工具调用前后 Hook 拦截器
# ════════════════════════════════════════════════════════════════

class HookMiddleware(BaseMiddleware):
    """工具调用前后 Hook 拦截器（BeforeTool / AfterTool / OnError）

    使用 on_wrap_tool_call（洋葱模式）实现 BeforeTool 拦截，
    使用 on_tool_end 实现 AfterTool / OnError 后处理。
    """
    HOOKS = ("on_wrap_tool_call", "on_tool_end")

    def __init__(self):
        from core.multi_agent_v2.tools.hooks import get_hook_manager
        self.hook_manager = get_hook_manager()

    async def on_wrap_tool_call(self, ctx: RunContext, next_mw: Callable) -> Any:
        """BeforeTool: 工具执行前调用 Before Hook"""
        tool_name = getattr(ctx, '_current_tool_name', '')
        arguments = getattr(ctx, '_current_tool_arguments', {})

        if not tool_name:
            return await next_mw()

        # 执行所有 BeforeTool Hook
        before_result = await self.hook_manager.run_before(tool_name, arguments)

        # 处理 skip（跳过工具执行）
        if before_result.skip:
            logger.info(f"BeforeTool 跳过 {tool_name}: {before_result.reason}")
            return {
                "success": False,
                "error": f"工具被跳过: {before_result.reason}",
                "result": {"error": f"工具被跳过: {before_result.reason}"},
                "tool_call": {"name": tool_name, "arguments": arguments},
            }

        # 处理 abort（终止整个执行流程）
        if before_result.abort:
            logger.warning(f"BeforeTool 终止 {tool_name}: {before_result.abort_reason}")
            ctx.interrupted = True
            ctx.last_error = before_result.abort_reason
            return {
                "success": False,
                "error": f"执行终止: {before_result.abort_reason}",
                "result": {"error": f"执行终止: {before_result.abort_reason}"},
                "tool_call": {"name": tool_name, "arguments": arguments},
            }

        # 继续执行（参数修改暂不支持，需架构级改造）
        return await next_mw()

    async def on_tool_end(self, ctx: RunContext) -> HookResult:
        """工具执行后调用 AfterTool / OnError Hook"""
        if not ctx.tool_results:
            return HookResult()

        last_result = ctx.tool_results[-1]
        tool_call = last_result.get("tool_call", {})
        tool_name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})

        if not tool_name:
            return HookResult()

        # 调用 AfterTool Hook（工具已成功执行）
        if last_result.get("success"):
            after_result = await self.hook_manager.run_after(tool_name, arguments, last_result.get("result"))

            if after_result.modify_result and after_result.result:
                last_result["result"] = after_result.result

        # 调用 OnError Hook（工具执行失败）
        if not last_result.get("success") and last_result.get("error"):
            error_msg = last_result.get("error", "")
            try:
                error = RuntimeError(error_msg)
            except Exception:
                error = Exception(error_msg)

            error_result = await self.hook_manager.run_error(tool_name, arguments, error)

            if error_result.retry:
                logger.info(f"Hook 请求重试: {tool_name}")
                return HookResult(jump_to="retry", reason=f"Hook 请求重试 {tool_name}")

        return HookResult()


# ════════════════════════════════════════════════════════════════
# QualityCheckMiddleware — AI 质检
# ════════════════════════════════════════════════════════════════

class QualityCheckMiddleware(BaseMiddleware):
    """AI 质检中间件 — agent 输出后由轻量 LLM 审查质量。

    挂载在 on_tool_end 钩子。若 final_answer 不合格：
    - 清除 final_answer
    - 注入质检反馈到 forced_instructions
    - 把 ctx.interrupted 改回 False 让 ReAct 继续执行
    """
    HOOKS = ("on_tool_end",)
    _MAX_RETRIES = 2

    def __init__(self):
        super().__init__()
        self._retry_count = 0

    def reset_task_state(self):
        self._retry_count = 0

    async def on_tool_end(self, ctx: RunContext) -> None:
        if not ctx.final_answer:
            return
        if self._retry_count >= self._MAX_RETRIES:
            return

        from core.multi_agent_v2.agents.react_core import _ai_quality_check
        feedback = await _ai_quality_check(ctx.final_answer)
        if not feedback:
            return

        self._retry_count += 1
        logger.warning(f"质检 #{self._retry_count}: {feedback}")
        ctx.forced_instructions = (
            f"⚠️ 质检未通过（第{self._retry_count}/{self._MAX_RETRIES}次）：{feedback}。"
            "请立刻修正以上问题，直接输出完整有效的内容。"
        )
        ctx.final_answer = ""
        ctx.interrupted = False
