"""
MemoryMiddleware — V2 记忆中间件

统一经 MemoryCoordinator 协调三层记忆存储，
不再直接调 STM/Session/Vector。
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

from .middleware import BaseMiddleware, RunContext

logger = logging.getLogger(__name__)


def _memory_layer_stats(context: str) -> str:
    """解析 <memory type=...> 标记，返回各层字符数统计（记忆分层显示）。"""
    import re as _re
    layers: dict = {}
    for _m in _re.finditer(r"<memory type=(\w+)>\n(.*?)\n</memory>", context, _re.DOTALL):
        _ly, _body = _m.group(1), _m.group(2)
        layers[_ly] = layers.get(_ly, 0) + len(_body)
    if not layers:
        return ""
    return " | ".join(f"{k}:{v}字" for k, v in layers.items())


class MemoryMiddleware(BaseMiddleware):
    """记忆中间件 — V2 读写三层记忆（经 coordinator）"""
    HOOKS = ("on_llm_invoke", "on_tool_end", "on_finish")

    def __init__(self):
        super().__init__()
        self._v1_mw = None
        self._v1_mw_broken = False
        self._coordinator = None

    def _get_coordinator(self):
        if self._coordinator is None:
            try:
                from core.memory.coordinator import get_coordinator
                self._coordinator = get_coordinator()
            except Exception:
                pass
        return self._coordinator

    # ── on_llm_invoke — 记忆注入 ──

    async def on_llm_invoke(self, ctx: RunContext) -> None:
        """每轮 LLM 思考前注入记忆（经 Coordinator 统一读路径）"""
        # 修复(N1): 子代理不注入记忆 —— 子代理拿不到 agent.user_id 会 fallback
        # 到 "cli_user"，把 192 条工具流水当"记忆"吃进上下文（还全标 assistant）。
        # 子代理任务短平快，注入 2 万字符垃圾纯浪费 token。
        if getattr(ctx, '_is_subagent', False):
            return

        user_input = ctx.task_description
        if not user_input:
            return

        user_id = self._get_user_id(ctx)
        coordinator = self._get_coordinator()

        if coordinator is not None:
            try:
                # 修复(B1): 透传当前会话 id —— STM 注入只取当前会话条目，
                # 跨会话烂尾任务不再复活
                context = await coordinator.get_context_for_llm(
                    user_id, user_input,
                    session_id=str(getattr(ctx, '_session_id', '') or ''),
                )
                if context:
                    ctx.knowledge_context += (
                        f"\n{context}"
                    )
                    if len(ctx.knowledge_context) > 20000:
                        ctx.knowledge_context = ctx.knowledge_context[-20000:]
                    # 记忆分层显示（可观测性）: 解析 <memory type=...> 标记，统计各层字符数
                    _detail = _memory_layer_stats(context)
                    if _detail:
                        print(f"    \033[1;35m🧠 记忆: {len(context)} 字符已注入 [分层] {_detail}\033[0m")
                    else:
                        print(f"    \033[1;35m🧠 记忆: {len(context)} 字符上下文已注入\033[0m")
                else:
                    print(f"    \033[2;35m🧠 记忆: 无相关历史\033[0m")
            except Exception as e:
                logger.debug(f"记忆检索失败: {e}")

    # ── on_tool_end — 工具结果记录 ──

    async def on_tool_end(self, ctx: RunContext) -> None:
        coordinator = self._get_coordinator()
        if coordinator is None:
            return

        if not ctx.tool_results:
            return

        latest = ctx.tool_results[-1]
        tc = latest.get("tool_call", {})
        tool_name = tc.get("name", "")
        success = latest.get("success", False)
        result_raw = latest.get("result", {})
        is_subagent = getattr(ctx, '_is_subagent', False)

        await coordinator.record_tool(
            tool_name=tool_name,
            success=success,
            result_raw=result_raw,
            round_idx=ctx.react_depth,
            is_subagent=is_subagent,
            # 修复(B3): 与读路径同门的 user_id（不再落进死门 cli_user）
            user_id=self._get_user_id(ctx),
        )

    # ── on_finish — 会话结束 ──

    async def on_finish(self, ctx: RunContext) -> None:
        coordinator = self._get_coordinator()
        if coordinator is None:
            return

        final_answer = ctx.final_answer
        if not final_answer:
            return

        user_id = self._get_user_id(ctx)
        is_subagent = getattr(ctx, '_is_subagent', False)

        await coordinator.finalize(
            user_id=user_id,
            task=ctx.task_description,
            final_answer=final_answer,
            is_subagent=is_subagent,
            # 修复(B1): finalize 写入 STM 时带上 session_id，
            # 下个会话读取时才能按会话边界过滤
            session_id=str(getattr(ctx, '_session_id', '') or ''),
        )

        if not is_subagent:
            print(f"    \033[1;35m🧠 记忆: 已持久化当前对话\033[0m")
        if not is_subagent:
            asyncio.ensure_future(self._after_finish_nudge(user_id))

    # ── 工具 ──

    def _get_user_id(self, ctx=None) -> str:
        # 修复(N2/B3): user_id 统一真相源 —— 优先 ctx.user_id（run_react
        # #003 透传链路，此前是死代码），其次 agent.user_id（V2 链路）。
        # 两处都没有时才 fallback（不再写死 cli_user，用 default_user 对齐
        # 读路径 enhanced_cli.py 的取值，写读同门）。
        if ctx is not None:
            src = str(getattr(ctx, 'user_id', '') or '')
            if src:
                return src
        if self._agent is not None and hasattr(self._agent, 'user_id'):
            uid = self._agent.user_id
            if uid:
                return str(uid)
        return "default_user"

    def _ensure_v1_mw(self):
        if self._v1_mw_broken:
            return None
        if self._v1_mw is not None:
            return self._v1_mw
        try:
            from core.memory.memory_middleware import get_memory_middleware
            self._v1_mw = get_memory_middleware()
            return self._v1_mw
        except Exception as e:
            logger.debug(f"V1 记忆中间件不可用（降级）: {e}")
            self._v1_mw_broken = True
            return None

    async def _after_finish_nudge(self, user_id: str) -> None:
        try:
            from core.memory.memory_nudge import get_memory_nudge
            if get_memory_nudge().increment(user_id):
                logger.info(f"nudge 触发: user={user_id}")
                try:
                    from core.memory.self_evolution import get_evolution_engine
                    await get_evolution_engine().check_and_evolve(user_id, new_experience_count=1)
                except Exception:
                    logger.debug("nudge 进化触发失败")
                try:
                    from core.memory.vector_memory import VectorMemoryStore
                    vm = VectorMemoryStore()
                    if vm.wait_for_collection(timeout=2.0):
                        vm.cleanup_old_memories(keep_last=2000)
                        logger.info(f"nudge 清理: user={user_id}")
                except Exception:
                    logger.debug("nudge 清理失败")
        except Exception:
            pass
