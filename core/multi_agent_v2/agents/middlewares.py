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
    HOOKS = ("on_think_start", "on_tool_end")

    MAX_DEPTH = 30

    async def on_think_start(self, ctx: RunContext) -> None:
        if ctx.react_depth > self.MAX_DEPTH:
            ctx.interrupted = True
            logger.warning(f"ReAct 深度超过 {self.MAX_DEPTH}，终止执行")

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
    - on_think_start: 查询 SharedBus 中的共享知识 → 注入到 LLM 提示词
    """
    HOOKS = ("on_think_start", "on_tool_end", "on_finish")

    async def on_think_start(self, ctx: RunContext) -> None:
        """在 LLM 思考前注入跨 Agent 共享知识"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.tool_results or ctx.iteration < 2:
            return

        try:
            shared = await self._fetch_shared_knowledge(ctx)
            knowledge_text = self._build_knowledge(ctx)
            evaluation_text = self._build_evaluation(ctx)
            planning_text = self._build_planning(ctx)

            lines = [KEPA_PREFIX]
            if shared:
                lines.append(f"[跨Agent知识] 其他Agent提供了: {shared}")
            lines.append(f"知识: {knowledge_text}")
            lines.append(f"评估: {evaluation_text}")
            lines.append(f"规划: {planning_text}")
            lines.append("──")
            kepa_text = f"\n{chr(10).join(lines)}\n"
            ctx.knowledge_context += kepa_text
        except Exception as e:
            logger.debug(f"KEPA 分析注入失败: {e}")

    async def _fetch_shared_knowledge(self, ctx: RunContext) -> str:
        """从 SharedBus 获取其他 Agent 沉淀的知识"""
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()

            desc_lower = ctx.task_description.lower()
            relevant_tags = set()
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
                return ""

            snippets = []
            for tag in relevant_tags:
                results = await bus.search_knowledge(tag)
                for key, entry in results.items():
                    meta = entry.get("meta", {})
                    summary = meta.get("summary", "")
                    source = meta.get("source", "")
                    if summary and len(str(summary)) > 10:
                        snippets.append(f"[{source}]: {summary[:200]}")
            if snippets:
                return " | ".join(snippets[:3])
            return ""
        except Exception:
            return ""

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
        """执行完成：最终知识摘要到 SharedBus"""
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
        except Exception:
            pass

    def _build_knowledge(self, ctx: RunContext) -> str:
        if not ctx.tool_results:
            return "尚未收集到数据"
        lines = []
        for r in ctx.tool_results[-5:]:
            tc = r.get("tool_call", {})
            name = tc.get("name", "?")
            ok = "成功" if r.get("success") else "失败"
            preview = str(r.get("result", ""))[:80]
            lines.append(f"[{ok}] {name}: {preview}")
        return "\n".join(lines)

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
    """双层循环检测：哈希 + 频率，防止工具调用死循环

    Layer 1: 滑动窗口内相同工具调用哈希重复检测
    Layer 2: 单工具累计调用频率检测
    """
    HOOKS = ("on_think_end",)

    def __init__(
        self,
        warn_threshold: int = 3,
        hard_limit: int = 5,
        tool_freq_warn: int = 5,
        tool_freq_hard_limit: int = 10,
        window_size: int = 20,
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

    def _hash_tool_calls(self, tool_calls: List[Dict]) -> str:
        """对一组工具调用取哈希，用于滑动窗口比较"""
        items = []
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except (json.JSONDecodeError, TypeError):
                args = {}
            # 仅用关键字段做稳定哈希
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

    async def on_think_end(self, ctx: RunContext) -> None:
        if not ctx.tool_results:
            return

        # 从最近一轮 tool_results 重建工具调用信息
        last_results = ctx.tool_results[-1:]
        if not last_results:
            return

        tool_calls = []
        for r in last_results:
            tc = r.get("tool_call", {})
            tool_calls.append(
                {
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": json.dumps(
                            tc.get("arguments", {}), default=str
                        ),
                    }
                }
            )

        if not tool_calls:
            return

        call_hash = self._hash_tool_calls(tool_calls)

        # 滑动窗口
        self._history.append(call_hash)
        if len(self._history) > self.window_size:
            self._history = self._history[-self.window_size :]

        # Layer 1: 哈希检测
        count = self._history.count(call_hash)
        if count >= self.hard_limit:
            ctx.interrupted = True
            ctx.last_error = (
                f"循环检测：相同工具调用重复 {count} 次，强制停止"
            )
            return HookResult(jump_to="end", reason=ctx.last_error)

        if count >= self.warn_threshold and call_hash not in self._warned_hashes:
            self._warned_hashes.add(call_hash)
            ctx.task_description += (
                "\n[循环警告] 你正在重复相同的工具调用。"
                "请立即停止调用工具，输出最终答案。"
            )

        # Layer 2: 频率检测
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            if not name:
                continue
            self._tool_freq[name] = self._tool_freq.get(name, 0) + 1

            if self._tool_freq[name] >= self.tool_freq_hard_limit:
                ctx.interrupted = True
                ctx.last_error = (
                    f"循环检测：工具 {name} 已调用 "
                    f"{self._tool_freq[name]} 次，强制停止"
                )
                return HookResult(jump_to="end", reason=ctx.last_error)

            if (
                self._tool_freq[name] >= self.tool_freq_warn
                and name not in self._warned_tools
            ):
                self._warned_tools.add(name)
                ctx.task_description += (
                    f"\n[循环警告] 工具 {name} 已调用 "
                    f"{self._tool_freq[name]} 次。"
                    "请考虑换用其他工具或直接输出结果。"
                )

        # Layer 3: 文件写入路径检测（防止反复写同一文件）
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            if name not in ("write_file", "file"):
                continue
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except (json.JSONDecodeError, TypeError):
                args = {}
            path = args.get("path", args.get("filepath", ""))
            if not path:
                continue
            path_key = f"write:{os.path.basename(path)}"
            self._tool_freq[path_key] = self._tool_freq.get(path_key, 0) + 1
            if self._tool_freq[path_key] >= 3:
                ctx.interrupted = True
                ctx.last_error = (
                    f"循环检测：文件 {path} 已被写入 {self._tool_freq[path_key]} 次，"
                    "请停止重复写入，直接输出最终结果"
                )
                return HookResult(jump_to="end", reason=ctx.last_error)


# ════════════════════════════════════════════════════════════════
# ClarificationMiddleware — 澄清请求拦截
# ════════════════════════════════════════════════════════════════

class ClarificationMiddleware(BaseMiddleware):
    """拦截 LLM 输出中的澄清请求模式，中断执行等待用户确认

    在 on_think_end 阶段检测 LLM 回复中是否包含结构化澄清请求
    （如 [CLARIFICATION] 标记或问号密集段落），若命中则中断并输出问题。
    """
    HOOKS = ("on_think_end",)

    # 匹配 LLM 可能输出的澄清请求模式
    CLARIFICATION_PATTERNS = [
        "[CLARIFICATION]",
        "[需要确认]",
        "[请确认]",
        "[clarification]",
    ]

    async def on_think_end(self, ctx: RunContext) -> Optional[HookResult]:
        # 仅在 LLM 产生 final_answer 时检查
        if not ctx.final_answer:
            return None

        answer_lower = ctx.final_answer.lower()

        # 检查是否包含澄清标记
        for pattern in self.CLARIFICATION_PATTERNS:
            if pattern.lower() in answer_lower:
                ctx.interrupted = True
                # 清除 final_answer，改为提示用户确认
                ctx.final_answer = (
                    f"需要您的确认：\n\n{ctx.final_answer}"
                )
                return HookResult(jump_to="end", reason="需要用户澄清")

        # 启发式检测：短回复 + 大量问号 → 可能是澄清请求
        if len(ctx.final_answer) < 500 and ctx.final_answer.count("?") + ctx.final_answer.count("？") >= 2:
            # 如果之前有工具调用结果，说明不是首次回复，可能是中途澄清
            if ctx.tool_results and len(ctx.tool_results) > 1:
                ctx.interrupted = True
                ctx.final_answer = (
                    f"需要您的确认：\n\n{ctx.final_answer}"
                )
                return HookResult(jump_to="end", reason="需要用户澄清")


# ════════════════════════════════════════════════════════════════
# TodoMiddleware — 任务完整性保护
# ════════════════════════════════════════════════════════════════

class TodoMiddleware(BaseMiddleware):
    """防止 agent 在有未完成任务时过早退出

    当工具调用失败率过高且 agent 试图输出 final_answer 时，
    注入提醒并清除 final_answer，强制继续执行。
    """
    HOOKS = ("on_think_end",)

    _MAX_REMINDERS = 2

    def __init__(self):
        self._reminder_count = 0

    async def on_think_end(self, ctx: RunContext) -> None:
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
            ctx.task_description += (
                f"\n[任务未完成] 已执行 {total} 次工具调用，"
                f"其中 {fail} 次失败。"
                "请检查失败原因并重试，不要过早结束。"
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
    HOOKS = ("on_think_start",)

    def __init__(self, keep_recent: int = 3, max_messages: int = 40):
        self.keep_recent = keep_recent
        self.max_messages = max_messages

    async def on_think_start(self, ctx: RunContext) -> None:
        """在构建消息前，清理过旧的 tool_results"""
        if not ctx.tool_results or len(ctx.tool_results) <= self.keep_recent:
            return

        # 只保留最近 N 轮的 tool_results
        # 旧的已经被 progressive truncation 处理了，这里进一步清理
        n_to_remove = len(ctx.tool_results) - self.keep_recent * 2
        if n_to_remove > 0:
            ctx.tool_results = ctx.tool_results[n_to_remove:]


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
    HOOKS = ()  # 使用 on_wrap_tool_call，不需要其他钩子

    def __init__(self, config_path: Optional[str] = None, sandbox_mode: bool = False):
        from core.multi_agent_v2.tools.permission import get_permission_service
        from core.multi_agent_v2.tools.shell_guard import get_shell_guard
        self.permission_service = get_permission_service(config_path)
        self.shell_guard = get_shell_guard(sandbox_mode)

    async def on_wrap_tool_call(self, ctx: RunContext, next_mw: Callable) -> Any:
        """在工具执行前实时检查权限和安全性（洋葱模式）"""
        # 提取工具名和参数
        if not isinstance(next_mw, dict):
            # 从 ctx 获取工具调用信息
            tool_name = getattr(ctx, '_current_tool_name', '')
            arguments = getattr(ctx, '_current_tool_arguments', {})
        else:
            tool_name = next_mw.get('name', '')
            arguments = next_mw.get('arguments', {})

        if not tool_name:
            return await next_mw() if callable(next_mw) else None

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
                        ctx.task_description += (
                            f"\n[安全警告] 检测到中危风险: {risk_desc}。"
                            "请确保操作安全。"
                        )

        # 权限检查通过，继续执行
        return await next_mw()


# ════════════════════════════════════════════════════════════════
# HookMiddleware — 工具调用前后 Hook 拦截器
# ════════════════════════════════════════════════════════════════

class HookMiddleware(BaseMiddleware):
    """工具调用前后 Hook 拦截器

    在工具执行前后调用注册的 Hook，支持：
    - BeforeTool: 修改参数、跳过执行、终止流程
    - AfterTool: 修改结果、缓存结果
    - OnError: 重试、错误处理
    """
    HOOKS = ("on_think_end",)

    def __init__(self):
        from core.multi_agent_v2.tools.hooks import get_hook_manager
        self.hook_manager = get_hook_manager()

    async def on_think_end(self, ctx: RunContext) -> None:
        """在工具执行前后调用 Hook"""
        if not ctx.tool_results:
            return

        # 获取最近一轮的工具调用
        last_result = ctx.tool_results[-1]
        tool_call = last_result.get("tool_call", {})
        tool_name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})

        if not tool_name:
            return

        # 调用 BeforeTool Hook（如果工具还没执行）
        if not last_result.get("success") and last_result.get("result") is None:
            before_result = await self.hook_manager.run_before(tool_name, arguments)

            if before_result.skip:
                # 跳过工具执行
                last_result["success"] = True
                last_result["result"] = before_result.reason or "Hook 跳过了此工具调用"
                logger.info(f"Hook 跳过工具: {tool_name}")
                return

            if before_result.abort:
                # 终止整个流程
                ctx.interrupted = True
                ctx.final_answer = before_result.abort_reason or "Hook 终止了执行流程"
                logger.warning(f"Hook 终止流程: {tool_name}")
                return

            # 如果修改了参数，更新工具调用
            if before_result.modify_args and before_result.args:
                tool_call["arguments"] = before_result.args

        # 调用 AfterTool Hook（如果工具已执行）
        if last_result.get("success"):
            after_result = await self.hook_manager.run_after(tool_name, arguments, last_result.get("result"))

            if after_result.modify_result and after_result.result:
                last_result["result"] = after_result.result

        # 调用 OnError Hook（如果工具执行失败）
        if not last_result.get("success") and last_result.get("error"):
            error_msg = last_result.get("error", "")
            try:
                error = RuntimeError(error_msg)
            except Exception:
                error = Exception(error_msg)

            error_result = await self.hook_manager.run_error(tool_name, arguments, error)

            if error_result.retry:
                # 标记重试
                last_result["retry"] = True
                logger.info(f"Hook 请求重试: {tool_name}")
