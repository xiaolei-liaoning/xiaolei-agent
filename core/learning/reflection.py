"""Reflection sinks - 包装层（不改原机制）
方案C 的核心原则：保留 3 个原机制不动，加 wrapper sink 让它们通过 FeedbackHub 被观测。
- auto_reviewer.review()  → ReviewerSink.handle()
- self_evolution.evolve() → EvolutionSink.handle()
- memory_middleware.process_turn() → MemorySink.handle()
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional
from .feedback import FeedbackSink, FeedbackEvent

logger = logging.getLogger(__name__)


class ReviewerSink(FeedbackSink):
    """包装 auto_reviewer - 任务完成时调用 review()"""

    def __init__(self, auto_reviewer_module):
        """传入 auto_reviewer 模块（动态 import 避免循环依赖）"""
        self.auto_reviewer = auto_reviewer_module
        self._name = "auto_reviewer_wrapper"

    @property
    def name(self) -> str:
        return self._name

    def interested_in(self, event: FeedbackEvent) -> bool:
        return event.event_type == "task_completion"

    def handle(self, event: FeedbackEvent) -> None:
        """委托给原 auto_reviewer - 不改它的实现"""
        try:
            reviewer = self.auto_reviewer.get_auto_reviewer()
            reviewer.review(
                task_id=event.task_id or "unknown",
                task_description=event.payload.get("description", ""),
                execution_logs=event.payload.get("logs", []),
            )
            logger.info(f"ReviewerSink: 任务 {event.task_id} 已复盘")
        except Exception as e:
            logger.error(f"ReviewerSink 调用 auto_reviewer 失败: {e}", exc_info=True)
            raise


class EvolutionSink(FeedbackSink):
    """包装 self_evolution - 差评时立即触发 evolve()"""

    def __init__(self, self_evolution_module):
        self.self_evolution = self_evolution_module
        self._name = "self_evolution_wrapper"

    @property
    def name(self) -> str:
        return self._name

    def interested_in(self, event: FeedbackEvent) -> bool:
        return event.event_type == "user_rating" and event.success is False

    def handle(self, event: FeedbackEvent) -> None:
        """委托给原 self_evolution - 差评立即触发"""
        try:
            from core.memory.self_evolution import get_evolution_engine
            reason = event.comment or f"rating={event.rating}"
            engine = get_evolution_engine()
            # 适配 SelfEvolutionEngine 真实 API
            if hasattr(engine, "force_evolve"):
                engine.force_evolve(user_id=event.user_id, reason=reason)
            elif hasattr(engine, "evolve"):
                engine.evolve(user_id=event.user_id, force=True, reason=reason)
            else:
                # 退化路径：只记录
                logger.warning(f"EvolutionSink: engine 没有 force_evolve/evolve 方法，仅记录")
            logger.info(f"EvolutionSink: 用户 {event.user_id} 差评已触发 force_evolve")
        except Exception as e:
            logger.error(f"EvolutionSink 调用 self_evolution 失败: {e}", exc_info=True)
            raise


class MemorySink(FeedbackSink):
    """包装 memory_middleware - 每轮对话时记录"""

    def __init__(self, memory_middleware_module):
        self.memory_middleware = memory_middleware_module
        self._name = "memory_middleware_wrapper"

    @property
    def name(self) -> str:
        return self._name

    def interested_in(self, event: FeedbackEvent) -> bool:
        # 接收 every_turn + task_completion + user_rating（记忆用户偏好）
        return event.event_type in ("every_turn", "task_completion", "user_rating")

    def handle(self, event: FeedbackEvent) -> None:
        """委托给原 memory_middleware（异步方法，用 ensure_future 调度）"""
        try:
            import asyncio
            from core.memory.memory_middleware import get_memory_middleware
            mw = get_memory_middleware()
            # 适配 MemoryMiddleware 真实 API - 用 process_turn 模拟反馈记录
            if event.comment:
                coro = mw.process_turn(
                    user_id=event.user_id,
                    user_message=f"[feedback:{event.event_type}] {event.comment}",
                    assistant_reply=f"recorded rating={event.rating}",
                )
            else:
                coro = mw.process_turn(
                    user_id=event.user_id,
                    user_message=f"[feedback:{event.event_type}]",
                    assistant_reply=f"recorded rating={event.rating}",
                )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(coro)
                else:
                    loop.run_until_complete(coro)
            except RuntimeError:
                asyncio.run(coro)
            logger.debug(f"MemorySink: 记录 {event.event_type}")
        except Exception as e:
            logger.error(f"MemorySink 调用 memory_middleware 失败: {e}", exc_info=True)
            raise


__all__ = ["ReviewerSink", "EvolutionSink", "MemorySink"]
