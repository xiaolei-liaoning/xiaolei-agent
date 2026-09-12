"""
MiddlewareChain — 模块化中间件管道

将 Agent 的 ReAct 执行流程拆分为多个可组合的中间件阶段。
每个中间件可拦截 on_start / on_llm_invoke / on_tool_invoke / on_tool_end / on_finish
五个生命周期钩子，实现关注点分离。
"""

import asyncio
import json
import logging
import time

from core.multi_agent_v2.tools.json_util import safe_parse_json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Callable

if TYPE_CHECKING:
    from .context_budget import ContextBudgetManager

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """单个计划步骤"""
    index: int
    description: str
    status: str = "pending"    # pending / running / done / failed
    tool_names: List[str] = field(default_factory=list)  # 预计使用的工具名
    result_summary: str = ""
    postconditions: List[str] = field(default_factory=list)
    # ponytail: 完成契约 — 字符串列表，标记 done 前全部满足
    # "file_exists:/path" — 文件必须在磁盘上存在
    # "tool_called:name"  — 工具 name 必须成功调用过


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
    # 修复 #003: 加 user_id 字段 — 透传用户身份用于记忆归因 + 反馈归因
    user_id: str = ""
    # ── Base Skill 集成 ──
    skill_personality: str = ""
    tool_preference: set = field(default_factory=set)
    guidance: str = ""
    # Agent 类型工具约束
    allowed_tools: Optional[List[str]] = None   # 工具白名单（None=不限制）
    disallowed_tools: Optional[List[str]] = None  # 工具黑名单
    profile: Dict[str, Any] = field(default_factory=lambda: {
        "use_shared_bus": True, "use_memory_store": False,
    })

    # ── 工具发现缓存（on_start 发现，on_llm_invoke 筛选）──
    _tool_cache: Optional[List[Any]] = None       # discover_all() 全量结果
    _filtered_tools: Optional[List[Any]] = None   # get_tools_for_task() 筛选结果（首轮缓存）

    # ── 执行状态（每轮变动）──
    iteration: int = 0
    interrupted: bool = False
    interrupted_reason: str = ""
    tool_results: List[Dict] = field(default_factory=list)
    last_error: Optional[str] = None
    exit_reason: str = ""  # 精确退出原因: plan_completed | empty_run_12_rounds | llm_timeout | ...
    warnings: List[str] = field(default_factory=list)
    final_answer: str = ""
    react_depth: int = 0
    consecutive_failures: Dict[str, int] = field(default_factory=dict)
    consecutive_idle_rounds: int = 0  # 连续空转轮次计数
    _failed_code_hashes: Dict[str, int] = field(default_factory=dict)  # code_hash → fail count

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

    # ── 并发控制 ──
    max_concurrent_tools: int = 5

    # ── 知识上下文（KEPA 注入，独立于 task_description）──
    knowledge_context: str = ""

    # ── 强制指令（独立于 task_description，不污染原始任务）──
    forced_instructions: str = ""
    # 标记当前是否处于审查/质量改进阶段，防止写入步骤被阻塞
    review_pending: bool = False

    # ── 上下文预算管理（ContextBudgetManager，可选）──
    context_budget: Optional[Any] = None

    # ── 对话历史累积（LLM 在后续轮次能看到之前的工具结果）──
    _conversation_history: List[Dict] = field(default_factory=list)

    # 子代理标记（由 spawn.py 设置，用于区分主/子代理）
    _is_subagent: bool = False

    # ── 记忆注入缓存（避免同 session 内重复查询 coordinator）──
    # 记录上次注入记忆时的 tool_results 长度，只有当有新工具结果时才重新注入
    _memory_injected_at_tool_count: int = 0

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

    def reset_task_state(self):
        """任务开始时重置中间件状态（子类可覆写）"""
        pass

    @property
    def agent(self):
        return self._agent

    @agent.setter
    def agent(self, value):
        self._agent = value

    async def on_start(self, ctx: RunContext) -> Optional[HookResult]:
        """执行开始"""
        pass

    async def on_llm_invoke(self, ctx: RunContext) -> Optional[HookResult]:
        """LLM 思考前"""
        pass

    async def on_tool_invoke(self, ctx: RunContext) -> Optional[HookResult]:
        """LLM 思考后"""
        pass

    async def on_plan_check(self, ctx: RunContext) -> Optional[HookResult]:
        """LLM 回复解析后、工具执行前 — 检查是否应执行计划中的工具调用"""
        pass

    async def on_tool_end(self, ctx: RunContext) -> Optional[HookResult]:
        """工具调用结束后"""
        pass

    async def on_wrap_tool_call(self, ctx: RunContext, next_mw: Callable) -> Any:
        """包裹工具调用（洋葱模式）"""
        return await next_mw()

    async def on_wrap_model_call(self, ctx: RunContext, next_mw: Callable) -> Any:
        """包裹 LLM 调用（洋葱模式）— 修复 #017。

        ⚠️ 当前为占位实现，react_core.py 直接调 router.chat_structured，
        还没有接入洋葱式 LLM 调用钩子。需要 MiddlewareChain 提供
        wrap_model_call() 串联方法（与 wrap_tool_call 对称）。
        """
        # TODO 修复 #017: 接入洋葱式 LLM 调用
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
        # 任务开始时重置中间件状态
        for mw in self._middlewares:
            try:
                mw.reset_task_state()
            except Exception as e:
                logger.warning(f"Middleware {mw} reset_task_state error: {e}")
        
        for mw in self._middlewares:
            if mw.HOOKS and "on_start" not in mw.HOOKS:
                continue
            try:
                hr = await mw.on_start(ctx)
                if hr and hr.jump_to != "continue":
                    return hr
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Middleware {mw} on_start error: {e}")
                mw_name = type(mw).__name__
                if "ReActCore" in mw_name or "Core" in mw_name:
                    ctx.interrupted = True
                    ctx.last_error = f"核心 middleware 异常: {e}"
                    return HookResult(jump_to="end")
        return HookResult()

    async def on_llm_invoke(self, ctx: RunContext) -> HookResult:
        for mw in self._middlewares:
            if mw.HOOKS and "on_llm_invoke" not in mw.HOOKS:
                continue
            try:
                hr = await mw.on_llm_invoke(ctx)
                if hr and hr.jump_to != "continue":
                    return hr
            except Exception as e:
                logger.warning(f"Middleware {mw} on_llm_invoke error: {e}")
                # 核心 middleware 失败时中断执行，避免静默空转
                mw_name = type(mw).__name__
                if "ReActCore" in mw_name or "Core" in mw_name:
                    ctx.interrupted = True
                    ctx.last_error = f"核心 middleware 异常: {e}"
                    return HookResult(jump_to="end")
        return HookResult()

    async def on_tool_invoke(self, ctx: RunContext) -> HookResult:
        for mw in self._middlewares:
            if mw.HOOKS and "on_tool_invoke" not in mw.HOOKS:
                continue
            try:
                hr = await mw.on_tool_invoke(ctx)
                if hr and hr.jump_to != "continue":
                    return hr
            except Exception as e:
                logger.warning(f"Middleware {mw} on_tool_invoke error: {e}")
        return HookResult()

    async def on_plan_check(self, ctx: RunContext) -> HookResult:
        """LLM 回复解析后、工具执行前调用"""
        for mw in self._middlewares:
            if mw.HOOKS and "on_plan_check" not in mw.HOOKS:
                continue
            try:
                hr = await mw.on_plan_check(ctx)
                if hr and hr.jump_to != "continue":
                    return hr
            except Exception as e:
                logger.warning(f"[{type(mw).__name__}] on_plan_check 异常: {e}")
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

    # TODO: on_wrap_model_call 当前未被调用（react_core.py 直接调 router.chat_structured）。
    # 如需给 LLM 调用加拦截（日志/限流/缓存），将 run_react 中的 LLM 调用改为走此链。
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
        # arguments 可能是 JSON 字符串，需要解析
        raw_args = tool_args.get("arguments", {})
        if isinstance(raw_args, str):
            raw_args = safe_parse_json(raw_args)
        ctx._current_tool_arguments = raw_args

        async def _run_chain(index: int) -> Dict:
            if index >= len(self._middlewares):
                from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                from core.multi_agent_v2.agents.tool_cache import get_tool_cache
                registry = get_tool_registry()
                cache = get_tool_cache()
                name = tool_args.get("name", "")
                args = raw_args

                # 缓存检查
                cached = await cache.get(name, args)
                if cached is not None:
                    return dict(cached)

                handler = registry.get_handler(name)
                if handler:
                    # 参数校验：执行前校验参数合法性
                    # 对标 Opencode 的 InvalidArgumentsError 回传机制：
                    # 校验失败 → 不执行 handler → forced_instructions 驱动 LLM 重试
                    valid, error_msg = registry.validate_arguments(name, args)
                    if not valid:
                        logger.warning(f"参数校验失败: {name} - {error_msg[:200]}")
                        ctx.forced_instructions = (
                            f"⚠️ 【参数错误】上一轮工具调用 '{name}' 的参数不正确，必须修正后重试：\n"
                            f"{error_msg}\n\n"
                            f"请根据正确的参数 Schema 重新调用 {name}，不要输出文本答案，不要执行其他无关操作。"
                        )
                        return {
                            "success": False,
                            "error": error_msg,
                            "result": {"error": error_msg},
                            "tool_call": tool_args,
                            "_validation_error": True,  # 标记校验错误，on_tool_invoke 据此跳过历史记录
                        }
                    try:
                        # ponytail: 需要 ctx 的 handler（如 write_todos 同步计划）按签名传 ctx
                        # 修复 #018: inspect.signature 每次调用都很贵，加 LRU 缓存
                        import inspect as _inspect
                        import functools
                        @functools.lru_cache(maxsize=256)
                        def _signature_accepts_ctx(handler_id, handler_ref):
                            try:
                                return 'ctx' in _inspect.signature(handler_ref).parameters
                            except (ValueError, TypeError):
                                return False
                        # 用 id(handler) 当 cache key — handler 不可哈希
                        _accepts_ctx = _signature_accepts_ctx(id(handler), handler)
                        if _accepts_ctx:
                            result = await handler(args, ctx=ctx)
                        else:
                            result = await handler(args)
                        # 注册表层统一输出截断（对标 opencode boundOutput）
                        from core.multi_agent_v2.tools.tool_result import bound_result
                        result = bound_result(name, result)
                        # 统一 ok/err 协议：兼容新旧格式
                        from core.multi_agent_v2.tools.tool_result import is_ok, extract_error
                        if not is_ok(result):
                            return {"success": False, "error": extract_error(result) or "工具执行失败", "result": result, "tool_call": tool_args}
                        response = {"success": True, "result": result, "tool_call": tool_args}
                        await cache.set(name, args, response)
                        return response
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
