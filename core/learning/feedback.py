"""统一反馈中心 (FeedbackHub)
把所有反馈事件（用户评价、任务完成、每轮对话、自我进化触发）汇总到一个入口。
- 先同步写 JSONL 日志（不丢）
- 再 fan-out 到各 sink（每个 sink 独立处理感兴趣的事件类型）
- 失败时写错误日志（不静默吞）
"""
from __future__ import annotations
import json
import time
import asyncio
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal, Optional, List, TYPE_CHECKING

logger = logging.getLogger(__name__)

FEEDBACK_LOG = Path("data/feedback_events.jsonl")
ERROR_LOG = Path("data/feedback_errors.jsonl")

EventType = Literal[
    "user_rating",        # 用户主动打分 1-5
    "user_comment",       # 用户主动评论
    "task_completion",    # 任务完成（auto_reviewer 入口）
    "every_turn",         # 每轮对话（memory_middleware 入口）
    "nudge_evolution",    # 周期触发（self_evolution 入口）
]


@dataclass
class FeedbackEvent:
    """统一反馈事件——任何来源都先转成这个"""
    user_id: str
    event_type: str
    timestamp: float = field(default_factory=time.time)
    source: str = "unknown"
    task_id: Optional[str] = None
    success: Optional[bool] = None
    rating: Optional[int] = None
    comment: Optional[str] = None
    payload: dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class FeedbackSink:
    """每个机制继承这个——只实现 interested_in + handle"""
    name: str = "anonymous"

    def interested_in(self, event: FeedbackEvent) -> bool:
        """路由：哪些事件类型要处理"""
        raise NotImplementedError

    def handle(self, event: FeedbackEvent) -> None:
        """实际处理——失败要 raise，不要 pass"""
        raise NotImplementedError


class FeedbackHub:
    """单例——所有反馈都过这里"""
    _instance: Optional["FeedbackHub"] = None

    def __init__(self) -> None:
        self.sinks: List[FeedbackSink] = []
        self.events_log: List[FeedbackEvent] = []
        self.errors_log: List[FeedbackEvent] = []
        self._lock = asyncio.Lock()
        FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> "FeedbackHub":
        if cls._instance is None:
            cls._instance = FeedbackHub()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """仅用于测试"""
        cls._instance = None

    def register(self, sink: FeedbackSink) -> None:
        if sink not in self.sinks:
            self.sinks.append(sink)
            logger.info(f"FeedbackHub: registered sink '{sink.name}'")

    async def emit(self, event: FeedbackEvent) -> None:
        """唯一入口——所有反馈都过这里"""
        # 1. 写盘（同步，保证不丢）
        self._append_log(FEEDBACK_LOG, event)
        self.events_log.append(event)

        # 2. fan-out 到所有 sink
        async with self._lock:
            tasks = []
            for sink in self.sinks:
                if not sink.interested_in(event):
                    continue
                tasks.append(self._safe_call(sink, event))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(self, sink: FeedbackSink, event: FeedbackEvent) -> None:
        try:
            sink.handle(event)
        except Exception as e:
            err = FeedbackEvent(
                user_id=event.user_id,
                event_type=event.event_type,
                source=sink.name,
                task_id=event.task_id,
                error=f"{type(e).__name__}: {e}",
                payload=event.payload,
            )
            self._append_log(ERROR_LOG, err)
            self.errors_log.append(err)
            logger.error(f"FeedbackHub: sink '{sink.name}' failed: {e}", exc_info=True)

    @staticmethod
    def _append_log(path: Path, event: FeedbackEvent) -> None:
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"FeedbackHub: failed to write log {path}: {e}")


# 便利函数
def get_hub() -> FeedbackHub:
    return FeedbackHub.get_instance()


# 事件工厂
def create_user_rating_event(user_id: str, rating: int, comment: Optional[str] = None,
                              task_id: Optional[str] = None, source: str = "user") -> FeedbackEvent:
    return FeedbackEvent(
        user_id=user_id,
        event_type="user_rating",
        source=source,
        task_id=task_id,
        success=(rating >= 3),
        rating=rating,
        comment=comment,
        payload={"rating": rating, "comment": comment},
    )


def create_task_completion_event(user_id: str, task_id: str, success: bool,
                                  source: str = "auto_reviewer") -> FeedbackEvent:
    return FeedbackEvent(
        user_id=user_id,
        event_type="task_completion",
        source=source,
        task_id=task_id,
        success=success,
        payload={"task_id": task_id, "success": success},
    )


def create_user_comment_event(user_id: str, comment: str, task_id: Optional[str] = None,
                               source: str = "user") -> FeedbackEvent:
    return FeedbackEvent(
        user_id=user_id,
        event_type="user_comment",
        source=source,
        task_id=task_id,
        comment=comment,
        payload={"comment": comment},
    )


__all__ = [
    "FEEDBACK_LOG",
    "ERROR_LOG",
    "EventType",
    "FeedbackEvent",
    "FeedbackSink",
    "FeedbackHub",
    "get_hub",
    "create_user_rating_event",
    "create_task_completion_event",
    "create_user_comment_event",
]
