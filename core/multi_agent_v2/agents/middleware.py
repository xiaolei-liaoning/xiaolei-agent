"""
MiddlewareChain — 模块化中间件管道

将 Agent 的 ReAct 执行流程拆分为多个可组合的中间件阶段。
每个中间件可拦截 on_start / on_think_start / on_think_end / on_tool_end / on_finish
五个生命周期钩子，实现关注点分离。
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """单个计划步骤"""
    index: int
    description: str
    status: str = "pending"    # pending / running / done / failed
    tool_names: List[str] = field(default_factory=list)  # 预计使用的工具名
    result_summary: str = ""


@dataclass
class RunContext:
    """ReAct 执行上下文 — 包含配置+状态+运行时"""

    # ── 执行配置（一次性设置，执行中不变）──
    task_description: str
    max_iterations: int = 10
    trace: Any = None
    tool_defs: Optional[List[Dict]] = None
    is_code_task: bool = False
    model_override: Optional[str] = None
    personality_prompt: str = ""
    # Agent 类型工具约束
    allowed_tools: Optional[List[str]] = None   # 工具白名单（None=不限制）
    disallowed_tools: Optional[List[str]] = None  # 工具黑名单
    profile: Dict[str, Any] = field(default_factory=lambda: {
        "use_shared_bus": True, "use_memory_store": False,
    })

    # ── 工具发现缓存（on_start 发现，on_think_start 筛选）──
    _tool_cache: Optional[List[Any]] = None       # discover_all() 全量结果
    _filtered_tools: Optional[List[Any]] = None   # get_tools_for_task() 筛选结果（首轮缓存）

    # ── 执行状态（每轮变动）──
    iteration: int = 0
    interrupted: bool = False
    tool_results: List[Dict] = field(default_factory=list)
    last_error: Optional[str] = None
    final_answer: str = ""
    react_depth: int = 0
    consecutive_failures: Dict[str, int] = field(default_factory=dict)
    consecutive_idle_rounds: int = 0  # 连续空转轮次计数

    # ── 计划（plan-then-execute）──
    plan: List[PlanStep] = field(default_factory=list)
    plan_generation: int = 0         # 计划版本号，每次 re-plan 递增
    _step_retries: Dict[int, int] = field(default_factory=dict)

    # ── 工具调用上下文（由 on_wrap_tool_call 设置）──
    _current_tool_name: str = ""
    _current_tool_arguments: Dict = field(default_factory=dict)

    # ── 中间件数据 ──
    confidence_total: float = 0.0
    confidence_scores: List[float] = field(default_factory=list)
    reflection_history: List[Dict] = field(default_factory=list)

    # ── 知识上下文（KEPA 注入，独立于 task_description）──
    knowledge_context: str = ""

    # ── 强制指令（独立于 task_description，不污染原始任务）──
    forced_instructions: str = ""

    # MiddlewareChain 引用（由 run_react 设置）
    _chain: Optional[Any] = None
    _pending_messages: Optional[List[Dict]] = None
    _last_reply: Any = None


@dataclass
class HookResult:
    """中间件钩子返回值 — 控制执行流程

    jump_to:
      "continue" — 正常继续
      "end"     — 终止执行
      "retry"   — 重试当前轮
    """
    jump_to: Literal["continue", "end", "retry"] = "continue"
    reason: str = ""


class BaseMiddleware:
    """中间件基类 — 所有中间件继承此类

    HOOKS: 声明此中间件使用的钩子列表
           - () 或 None: 所有钩子都触发
           - ("on_start", "on_tool_end"): 只触发这些钩子
    """
    HOOKS: tuple = ()

    def __init__(self):
        self._agent: Any = None

    @property
    def agent(self):
        return self._agent

    @agent.setter
    def agent(self, value):
        self._agent = value

    async def on_start(self, ctx: RunContext) -> Optional[HookResult]:
        """执行开始"""
        pass

    async def on_think_start(self, ctx: RunContext) -> Optional[HookResult]:
        """LLM 思考前"""
        pass

    async def on_think_end(self, ctx: RunContext) -> Optional[HookResult]:
        """LLM 思考后"""
        pass

    async def on_tool_end(self, ctx: RunContext) -> Optional[HookResult]:
        """工具调用结束后"""
        pass

    async def on_wrap_tool_call(self, ctx: RunContext, next_mw: Callable) -> Any:
        """包裹工具调用（洋葱模式）"""
        return await next_mw()

    async def on_wrap_model_call(self, ctx: RunContext, next_mw: Callable) -> Any:
        """包裹 LLM 调用（洋葱模式）"""
        return await next_mw()

    async def on_finish(self, ctx: RunContext) -> Optional[HookResult]:
        """执行完成"""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class MiddlewareChain:
    """中间件链 — 按顺序执行所有中间件的各阶段钩子"""

    def __init__(self):
        self._middlewares: List[BaseMiddleware] = []

    def add(self, middleware: BaseMiddleware) -> 'MiddlewareChain':
        self._middlewares.append(middleware)
        return self

    def remove(self, middleware_class: type) -> None:
        self._middlewares = [m for m in self._middlewares if not isinstance(m, middleware_class)]

    def get(self, middleware_class: type) -> Optional[BaseMiddleware]:
        for m in self._middlewares:
            if isinstance(m, middleware_class):
                return m
        return None

    def bind_agent(self, agent: Any) -> None:
        for mw in self._middlewares:
            mw._agent = agent

    async def on_start(self, ctx: RunContext) -> HookResult:
        for mw in self._middlewares:
            if mw.HOOKS and "on_start" not in mw.HOOKS:
                continue
            try:
                hr = await mw.on_start(ctx)
                if hr and hr.jump_to != "continue":
                    return hr
            except Exception as e:
                logger.warning(f"Middleware {mw} on_start error: {e}")
                mw_name = type(mw).__name__
                if "ReActCore" in mw_name or "Core" in mw_name:
                    ctx.interrupted = True
                    ctx.last_error = f"核心 middleware 异常: {e}"
                    return HookResult(jump_to="end")
        return HookResult()

    async def on_think_start(self, ctx: RunContext) -> HookResult:
        for mw in self._middlewares:
            if mw.HOOKS and "on_think_start" not in mw.HOOKS:
                continue
            try:
                hr = await mw.on_think_start(ctx)
                if hr and hr.jump_to != "continue":
                    return hr
            except Exception as e:
                logger.warning(f"Middleware {mw} on_think_start error: {e}")
                # 核心 middleware 失败时中断执行，避免静默空转
                mw_name = type(mw).__name__
                if "ReActCore" in mw_name or "Core" in mw_name:
                    ctx.interrupted = True
                    ctx.last_error = f"核心 middleware 异常: {e}"
                    return HookResult(jump_to="end")
        return HookResult()

    async def on_think_end(self, ctx: RunContext) -> HookResult:
        for mw in self._middlewares:
            if mw.HOOKS and "on_think_end" not in mw.HOOKS:
                continue
            try:
                hr = await mw.on_think_end(ctx)
                if hr and hr.jump_to != "continue":
                    return hr
            except Exception as e:
                logger.warning(f"Middleware {mw} on_think_end error: {e}")
        return HookResult()

    async def on_tool_end(self, ctx: RunContext) -> HookResult:
        for mw in self._middlewares:
            if mw.HOOKS and "on_tool_end" not in mw.HOOKS:
                continue
            try:
                hr = await mw.on_tool_end(ctx)
                if hr and hr.jump_to != "continue":
                    return hr
            except Exception as e:
                logger.warning(f"Middleware {mw} on_tool_end error: {e}")
        return HookResult()

    async def on_finish(self, ctx: RunContext) -> HookResult:
        for mw in self._middlewares:
            if mw.HOOKS and "on_finish" not in mw.HOOKS:
                continue
            try:
                hr = await mw.on_finish(ctx)
                if hr and hr.jump_to != "continue":
                    return hr
            except Exception as e:
                logger.warning(f"Middleware {mw} on_finish error: {e}")
        return HookResult()

    async def on_wrap_model_call(self, ctx: RunContext, llm_fn: Callable) -> Any:
        async def _run_chain(index: int) -> Any:
            if index >= len(self._middlewares):
                return await llm_fn()
            mw = self._middlewares[index]
            return await mw.on_wrap_model_call(ctx, lambda: _run_chain(index + 1))
        return await _run_chain(0)

    async def on_wrap_tool_call(self, ctx: RunContext, tool_args: Dict) -> Dict:
        # 设置工具调用信息到 ctx，供 PermissionMiddleware 等中间件使用
        ctx._current_tool_name = tool_args.get("name", "")
        ctx._current_tool_arguments = tool_args.get("arguments", {})

        async def _run_chain(index: int) -> Dict:
            if index >= len(self._middlewares):
                from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                registry = get_tool_registry()
                name = tool_args.get("name", "")
                args = tool_args.get("arguments", {})
                handler = registry.get_handler(name)
                if handler:
                    try:
                        result = await handler(args)
                        # 检查统一 ok/err 协议：ok=False 视为失败
                        if isinstance(result, dict) and result.get("ok") is False:
                            return {"success": False, "error": result.get("error", "工具执行失败"), "result": result, "tool_call": tool_args}
                        return {"success": True, "result": result, "tool_call": tool_args}
                    except Exception as e:
                        return {"success": False, "error": str(e), "tool_call": tool_args}
                return {"success": False, "error": f"no handler for {name}", "tool_call": tool_args}
            mw = self._middlewares[index]
            return await mw.on_wrap_tool_call(ctx, lambda: _run_chain(index + 1))
        return await _run_chain(0)

    def __len__(self) -> int:
        return len(self._middlewares)

    def __repr__(self) -> str:
        return f"MiddlewareChain({len(self._middlewares)} middlewares)"
