"""
MemoryMiddleware — V2 记忆中间件

直接调 V1 的 memory_middleware（统一引擎），
不再用 importlib 绕路、不再硬编码 user_id。

三阶段钩子：
  on_think_start  — 读取短期记忆 + 用户画像 + RAG → 注入 personality
  on_tool_end     — 记录工具执行经验到 temp_memory
  on_finish       — 写入短期/长期记忆（V1 process_turn 统一处理）
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .middleware import BaseMiddleware, RunContext

logger = logging.getLogger(__name__)

_NUDGE_INTERVAL = 10


class MemoryMiddleware(BaseMiddleware):
    """记忆中间件 — V2 读写 V1 同一套记忆引擎"""
    HOOKS = ("on_think_start", "on_tool_end", "on_finish")

    def __init__(self):
        super().__init__()
        self._v1_mw = None
        self._tool_experiences: List[Dict] = []
        self._start_time = 0.0
        self._v1_mw_broken = False

    # ── 工具 ───────────────────────────────────────────────

    def _get_user_id(self) -> str:
        """获取当前用户 ID（从 agent 取，默认 cli_user）"""
        if self._agent is not None and hasattr(self._agent, 'user_id'):
            uid = self._agent.user_id
            if uid:
                return str(uid)
        return "cli_user"

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

    # ── on_think_start — 记忆注入 ──────────────────────────

    async def on_think_start(self, ctx: RunContext) -> None:
        """每轮 LLM 思考前注入短期记忆 + 用户画像 + RAG"""
        user_input = ctx.task_description
        if not user_input:
            return

        user_id = self._get_user_id()
        v1_mw = self._ensure_v1_mw()
        if v1_mw is None:
            return

        try:
            context = await v1_mw.get_user_context(user_id, user_input)
            if context:
                ctx.knowledge_context += (
                    f"\n── 记忆上下文 ──\n注意：下方 [最近对话] 中的信息优先级最高，"
                    f"它反映了用户在本轮对话中刚说过的话。"
                    f"如果 [最近对话] 与 [用户画像] 或 [相关记忆] 有冲突，以 [最近对话] 为准。"
                    f"\n\n{context}\n──"
                )
                if len(ctx.knowledge_context) > 8000:
                    ctx.knowledge_context = ctx.knowledge_context[-8000:]
                print(f"    \033[1;35m🧠 记忆: {len(context)} 字符上下文已注入\033[0m")
            else:
                print(f"    \033[2;35m🧠 记忆: 无相关历史\033[0m")
        except Exception as e:
            logger.debug(f"V1 记忆检索失败: {e}")

    # ── on_tool_end — 经验记录 + 写入 STM ────────────

    async def on_tool_end(self, ctx: RunContext) -> None:
        if not ctx.tool_results:
            return
        latest = ctx.tool_results[-1]
        if not latest:
            return

        tc = latest.get("tool_call", {})
        exp = {
            "tool": tc.get("name", "?"),
            "success": latest.get("success", False),
            "result_summary": str(latest.get("result", ""))[:200],
            "iteration": ctx.iteration,
            "timestamp": time.time(),
        }
        self._tool_experiences.append(exp)

        if self._agent is not None and hasattr(self._agent, 'temp_memory'):
            self._agent.temp_memory["memory_experiences"] = self._tool_experiences[-10:]

        # 工具结果写入 STM，供下轮 on_think_start 读取
        try:
            from core.memory.short_term_memory import get_memory_manager
            stm = get_memory_manager()
            summary = f"[工具执行: {tc.get('name', '?')}] "
            if latest.get("success"):
                summary += str(latest.get("result", ""))[:300]
            else:
                summary += f"失败: {latest.get('error', '未知错误')[:200]}"
            stm.add(self._get_user_id(), "assistant", summary)
        except Exception as e:
            logger.debug(f"工具结果写入 STM 失败: {e}")

    # ── on_finish — 持久化记忆 ─────────────────────────────

    async def on_finish(self, ctx: RunContext) -> None:
        """任务结束时：调 V1 process_turn 统一写入短期+长期记忆"""
        final_answer = ctx.final_answer
        if not final_answer:
            return

        user_id = self._get_user_id()
        v1_mw = self._ensure_v1_mw()
        if v1_mw is not None:
            try:
                await v1_mw.process_turn(user_id, ctx.task_description, final_answer)
                print(f"    \033[1;35m🧠 记忆: 已持久化当前对话\033[0m")
            except Exception as e:
                logger.debug(f"V1 process_turn 失败: {e}")

        self._tool_experiences.clear()
        asyncio.ensure_future(self._after_finish_nudge(user_id, ctx))

    async def _after_finish_nudge(self, user_id: str, ctx: RunContext) -> None:
        """任务后推动：触发进化 + 向量库清理"""
        try:
            from core.memory.memory_nudge import get_memory_nudge
            if get_memory_nudge().increment(user_id):
                logger.info(f"🧠 nudge 触发: user={user_id}")
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
                        logger.info(f"🧠 nudge 清理: user={user_id}")
                except Exception:
                    logger.debug("nudge 清理失败")
        except Exception:
            pass
