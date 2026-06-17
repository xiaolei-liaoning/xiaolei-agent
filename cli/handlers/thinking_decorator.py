"""_with_thinking() 装饰器 — 将 think_start→analyze→plan→step→complete→summarize 模式抽象为可复用装饰器"""

import asyncio
import functools
from typing import Any, Callable, Dict, List, Optional

from cli.thinking_engine import (
    think_analyze,
    think_complete,
    think_log,
    think_plan,
    think_start,
    think_step,
    think_summarize,
)


def with_thinking(
    name: str,
    category: str = "",
    plan_steps: Optional[List[Dict[str, str]]] = None,
) -> Callable:
    """Decorator that wraps an async method with standard thinking lifecycle.

    Injects think_start / think_analyze / think_plan before the function
    body, and wraps with try/except to always call think_summarize.

    The decorated function receives an extra kwarg ``_thinking`` — a
    ``ThinkingCtx`` helper with .step(n, msg), .complete(n, ...) shortcuts.

    Usage::

        @with_thinking("数据分析", "数据分析", [
            {"title": "执行分析", "description": "正在分析数据"},
            {"title": "生成结果", "description": "生成报告"},
        ])
        async def handle_analyze(self, parsed_cmd, _thinking=None):
            _thinking.step(1, "Running analysis …")
            result = await do_work()
            _thinking.complete(1, success=True)
            return result
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            think_start(name)
            if category:
                think_analyze(category)
            if plan_steps:
                think_plan(plan_steps)

            ctx = ThinkingCtx()

            kwargs["_thinking"] = ctx
            try:
                result = await func(self, *args, **kwargs)
                if not ctx._suppressed_summarize:
                    think_summarize(True, result)
                return result
            except Exception as e:
                if not ctx._suppressed_summarize:
                    think_summarize(False, str(e))
                raise

        return wrapper

    return decorator


class ThinkingCtx:
    """Helper injected into the decorated function by ``with_thinking``."""

    def __init__(self) -> None:
        self._suppressed_summarize = False

    @staticmethod
    def step(n: int, msg: str = "") -> None:
        """Mark a step and optionally log a message."""
        think_step(n)
        if msg:
            think_log(msg)

    @staticmethod
    def complete(n: int, success: bool = True, error: Optional[str] = None) -> None:
        """Complete a step."""
        think_complete(n, success=success, error=error)

    def suppress_summarize(self) -> None:
        """Call inside the function body to prevent the auto-generated summary."""
        self._suppressed_summarize = True
