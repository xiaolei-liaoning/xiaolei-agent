"""中间件系统 — 与 deerflow/LangGraph AgentMiddleware 风格一致

用法:
    class MyMiddleware(AgentMiddleware):
        async def abefore_request(self, ctx):
            print("前处理")

        async def awrap_execution(self, ctx, handler):
            print("包裹前")
            await handler(ctx)   # 继续
            print("包裹后")

        async def aafter_request(self, ctx):
            print("后处理")

    pipeline = MiddlewarePipeline()
    pipeline.use(MyMiddleware())
    pipeline.use(OtherMiddleware())
    ctx = await pipeline.run(Context("你好"))
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


# ── Context — 流过整条链的请求/响应/状态 ──────────────────────────────

@dataclass
class Context:
    """流过中间件链的上下文

    属性:
        request:   用户原始请求
        response:  最终输出
        state:     中间件间共享的临时数据区
        chat_history: 聊天历史
        session_id: 会话标识
        start_time: 请求开始时间戳
        error:     链中产生的错误
        aborted:   是否被中间件中止（短路）
    """
    request: str
    response: Dict[str, Any] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    session_id: str = ""
    start_time: float = field(default_factory=time.time)
    error: Optional[str] = None
    aborted: bool = False

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    def abort(self, reason: str = ""):
        self.aborted = True
        self.error = reason if reason else ""


# ── AgentMiddleware 基类 — 继承并 override 需要的 hook ────────────────

class AgentMiddleware:
    """中间件基类

    子类 override 以下 hook：

    abefore_request(ctx)      — 前置：按注册顺序执行，可阻断
    awrap_execution(ctx, fn)  — 包裹：洋葱模型围绕核心，不调 fn() 则短路
    aafter_request(ctx)       — 后置：按注册逆序执行
    """
    name: str = ""

    async def abefore_request(self, ctx: Context) -> None:
        pass

    async def awrap_execution(self, ctx: Context, handler: Callable) -> None:
        return await handler()

    async def aafter_request(self, ctx: Context) -> None:
        pass


# ── MiddlewarePipeline — 组合 + 运行 ──────────────────────────────────

NextFn = Callable[[], Awaitable[None]]


class MiddlewarePipeline:
    """中间件管道 — 组合 AgentMiddleware 列表并调度执行"""

    def __init__(self):
        self._middlewares: List[AgentMiddleware] = []

    def use(self, mw: AgentMiddleware) -> "MiddlewarePipeline":
        self._middlewares.append(mw)
        return self

    async def run(self, ctx: Context) -> Context:
        """运行整条中间件链"""
        # 1. before_request — 全部按注册顺序前置处理
        for mw in self._middlewares:
            if ctx.aborted:
                break
            try:
                await mw.abefore_request(ctx)
            except Exception as e:
                logger.error("[%s] abefore_request failed: %s", mw.name, e)
                ctx.abort(str(e))
                break

        # 2. wrap_execution — 洋葱组合
        if not ctx.aborted:
            wrapper = self._compose()
            try:
                await wrapper(ctx)
            except Exception as e:
                logger.error("execution failed: %s", e)
                ctx.abort(str(e))

        # 3. after_request — 逆序后置处理
        for mw in reversed(self._middlewares):
            if ctx.aborted:
                break
            try:
                await mw.aafter_request(ctx)
            except Exception:
                logger.warning("[%s] aafter_request failed (non-fatal)", mw.name)

        # 记录总耗时
        ctx.state.setdefault("_timings", {})["_total"] = time.time() - ctx.start_time
        return ctx

    def _compose(self) -> NextFn:
        """洋葱组合（koa-compose 风格）"""
        middlewares = self._middlewares

        async def dispatch(index: int, ctx: Context) -> None:
            if ctx.aborted or index >= len(middlewares):
                return
            mw = middlewares[index]

            async def next_fn():
                await dispatch(index + 1, ctx)

            await mw.awrap_execution(ctx, next_fn)

        return lambda ctx: dispatch(0, ctx)

    def list(self) -> List[AgentMiddleware]:
        return list(self._middlewares)
