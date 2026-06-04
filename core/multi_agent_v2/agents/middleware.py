"""
MiddlewareChain - 模块化中间件管道

将 Agent 的 ReAct 执行流程拆分为多个可组合的中间件阶段。
每个中间件可拦截 on_start / on_think_start / on_think_end / on_tool_end / on_finish
五个生命周期钩子，实现关注点分离。

参考方案：小龙虾 agent 的 MiddlewareChain 架构
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class RunContext:
    """ReAct 执行上下文 — 全程共享的状态容器"""
    task_description: str
    max_iterations: int = 10
    trace: Any = None
    tool_defs: Optional[List[Dict]] = None

    # 循环状态
    iteration: int = 0
    interrupted: bool = False
    tool_results: List[Dict] = field(default_factory=list)
    last_error: Optional[str] = None
    final_answer: str = ""

    # 任务类型
    is_code_task: bool = False
    profile: Dict[str, Any] = field(default_factory=lambda: {
        "use_shared_bus": False,
        "use_memory_store": False,
        "use_rag": False,
        "use_mcp_fallback": True,
        "use_workspace": True,
        "use_sandbox": True,
        "has_explicit_path": False,
    })

    # 置信度
    confidence_total: float = 0.0
    confidence_scores: List[float] = field(default_factory=list)

    # 反思
    reflection_history: List[Dict] = field(default_factory=list)

    # ReAct 深度
    react_depth: int = 0
    consecutive_failures: Dict[str, int] = field(default_factory=dict)

    # 新工具类型追踪
    rag_results: List[Dict] = field(default_factory=list)
    skill_results: List[Dict] = field(default_factory=list)
    api_calls: List[Dict] = field(default_factory=list)
    reflect_results: List[Dict] = field(default_factory=list)
    kepa_states: List[str] = field(default_factory=list)

    # MiddlewareChain 引用（由 run_react 在 on_start 后设置，供 _execute 使用）
    _chain: Optional[Any] = None

    # 7阶段流水线（由 DynamicStageRoutingMiddleware 管理）
    stage: Optional[Dict] = None

    def get_latest_observation(self) -> str:
        """获取最近一条 Observation 文本"""
        if not self.tool_results:
            return ""
        last = self.tool_results[-1]
        try:
            res = last.get("result", {})
            if isinstance(res, dict):
                content = res.get("result", {}).get("content", [])
                if isinstance(content, list):
                    texts = [c.get("text", "") for c in content if isinstance(c, dict)]
                    return "\n".join(texts)
                if isinstance(content, str):
                    return content
            return str(last.get("result", ""))[:500]
        except Exception:
            return str(last.get("result", ""))[:500]

    def get_tool_summary(self) -> str:
        """获取工具执行摘要"""
        lines = []
        for r in self.tool_results[-5:]:
            tc = r.get("tool_call", {})
            name = tc.get("name", "?")
            ok = r.get("success", False)
            lines.append(f"  {'✓' if ok else '✗'} {name}")
        return "\n".join(lines)


class BaseMiddleware:
    """中间件基类 — 所有中间件继承此类"""

    def __init__(self):
        self._agent: Any = None

    @property
    def agent(self):
        return self._agent

    @agent.setter
    def agent(self, value):
        self._agent = value

    async def on_start(self, ctx: RunContext) -> None:
        """执行开始"""
        pass

    async def on_think_start(self, ctx: RunContext) -> None:
        """LLM 思考前"""
        pass

    async def on_think_end(self, ctx: RunContext) -> None:
        """LLM 思考后"""
        pass

    async def on_tool_end(self, ctx: RunContext) -> None:
        """工具调用结束后"""
        pass

    async def on_wrap_tool_call(self, ctx: RunContext, next_mw: Callable) -> Any:
        """包裹工具调用（洋葱模式）

        调用前可拦截/修改参数，调用后可修改/过滤结果。
        必须调用 await next_mw() 继续执行链。
        示例：安全检查、参数校验、结果过滤、错误重试
        """
        return await next_mw()

    async def on_finish(self, ctx: RunContext) -> None:
        """执行完成"""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class MiddlewareChain:
    """中间件链 — 按顺序执行所有中间件的各阶段钩子"""

    def __init__(self):
        self._middlewares: List[BaseMiddleware] = []

    def add(self, middleware: BaseMiddleware) -> 'MiddlewareChain':
        """添加中间件到链尾"""
        self._middlewares.append(middleware)
        return self

    def insert(self, index: int, middleware: BaseMiddleware) -> 'MiddlewareChain':
        """在指定位置插入中间件"""
        self._middlewares.insert(index, middleware)
        return self

    def remove(self, middleware_class: type) -> None:
        """移除指定类型的中间件"""
        self._middlewares = [m for m in self._middlewares if not isinstance(m, middleware_class)]

    def get(self, middleware_class: type) -> Optional[BaseMiddleware]:
        """获取指定类型的中间件实例"""
        for m in self._middlewares:
            if isinstance(m, middleware_class):
                return m
        return None

    async def on_start(self, ctx: RunContext) -> None:
        for mw in self._middlewares:
            try:
                await mw.on_start(ctx)
            except Exception as e:
                logger.warning(f"Middleware {mw} on_start error: {e}")

    async def on_think_start(self, ctx: RunContext) -> None:
        for mw in self._middlewares:
            try:
                await mw.on_think_start(ctx)
            except Exception as e:
                logger.warning(f"Middleware {mw} on_think_start error: {e}")

    async def on_think_end(self, ctx: RunContext) -> None:
        for mw in self._middlewares:
            try:
                await mw.on_think_end(ctx)
            except Exception as e:
                logger.warning(f"Middleware {mw} on_think_end error: {e}")

    async def on_tool_end(self, ctx: RunContext) -> None:
        for mw in self._middlewares:
            try:
                await mw.on_tool_end(ctx)
            except Exception as e:
                logger.warning(f"Middleware {mw} on_tool_end error: {e}")

    async def on_finish(self, ctx: RunContext) -> None:
        for mw in self._middlewares:
            try:
                await mw.on_finish(ctx)
            except Exception as e:
                logger.warning(f"Middleware {mw} on_finish error: {e}")

    async def on_wrap_tool_call(self, ctx: RunContext, tool_args: Dict) -> Dict:
        """洋葱式包裹工具调用 — 每个 middleware 可以拦截/修改/重试

        执行顺序：mw1(→mw2(→mw3(→实际工具调用)→mw3后置)→mw2后置)→mw1后置
        任意 middleware 可以不调 next_mw() 直接返回（拦截调用）
        """
        async def _run_chain(index: int) -> Dict:
            if index >= len(self._middlewares):
                # 执行实际工具调用
                from core.multi_agent_v2.agents.base.base_agent import BaseAgent
                agent = BaseAgent()
                return await agent._execute_single_tool_call(tool_args)
            mw = self._middlewares[index]
            return await mw.on_wrap_tool_call(ctx, lambda: _run_chain(index + 1))
        return await _run_chain(0)

    def __len__(self) -> int:
        return len(self._middlewares)

    def __repr__(self) -> str:
        return f"MiddlewareChain({len(self._middlewares)} middlewares)"


# ════════════════════════════════════════════════════════════════
# DynamicStageRoutingMiddleware — 7阶段流水线
# ════════════════════════════════════════════════════════════════

# 7阶段定义
STAGES = [
    {"name": "理解", "prompt": "理解用户需求，明确目标和约束条件。不要执行任何操作。"},
    {"name": "收集", "prompt": "通过工具调用收集所需的数据和信息。"},
    {"name": "分析", "prompt": "分析已收集的数据，得出结论或方案。"},
    {"name": "写", "prompt": "编写代码或文档，实现所需功能。"},
    {"name": "验证", "prompt": "验证已实现的方案是否正确。"},
    {"name": "导出", "prompt": "将结果保存到目标位置。"},
    {"name": "总结", "prompt": "总结完成情况，输出最终回复。"},
]


class DynamicStageRoutingMiddleware(BaseMiddleware):
    """7阶段动态流水线 — 根据任务类型自动选择阶段序列

    阶段：理解→收集→分析→写→验证→导出→总结
    根据执行画像裁剪，代码/搜索/简单任务走不同阶段序列。
    """

    def __init__(self):
        super().__init__()
        self._stage_index = 0
        self._stage_results: Dict[str, Any] = {}

    # 阶段序列映射
    _STAGE_SEQUENCES = {
        "code": STAGES[:],  # 全7阶段
        "search": [STAGES[0], STAGES[1], STAGES[2], STAGES[6]],  # 理解→收集→分析→总结
        "simple": [STAGES[0], STAGES[6]],  # 理解→总结
        "edit": [STAGES[0], STAGES[3], STAGES[4], STAGES[5], STAGES[6]],  # 理解→写→验证→导出→总结
    }

    async def on_start(self, ctx: RunContext) -> None:
        """根据执行画像选择阶段序列"""
        profile = ctx.profile
        if profile.get("has_explicit_path"):
            sequence = self._STAGE_SEQUENCES["edit"]
        elif ctx.is_code_task:
            sequence = self._STAGE_SEQUENCES["code"]
        elif profile.get("use_rag"):
            sequence = self._STAGE_SEQUENCES["search"]
        else:
            sequence = self._STAGE_SEQUENCES["search"]

        ctx._stage_sequence = sequence
        ctx._stage_index = 0
        ctx.stage = None
        self._stage_results = {}

        if sequence:
            ctx.stage = sequence[0]
            logger.info(f"阶段流水线: {' → '.join(s['name'] for s in sequence)}")

    async def on_think_start(self, ctx: RunContext) -> None:
        """如果当前阶段完成，进入下一阶段"""
        if not ctx._stage_sequence or ctx.interrupted:
            return

        # 检查当前阶段是否已完成
        stage = ctx.stage
        if stage and self._is_stage_done(stage, ctx):
            self._stage_results[stage["name"]] = {
                "result": ctx.tool_results[-1] if ctx.tool_results else None,
                "iteration": ctx.iteration,
            }
            # 进入下一阶段
            ctx._stage_index += 1
            if ctx._stage_index < len(ctx._stage_sequence):
                ctx.stage = ctx._stage_sequence[ctx._stage_index]
                logger.info(f"进入阶段: {ctx.stage['name']}")
            else:
                ctx.stage = None  # 所有阶段完成

    def _is_stage_done(self, stage: dict, ctx: RunContext) -> bool:
        """判断当前阶段是否完成"""
        if not ctx.tool_results:
            return False
        name = stage["name"]

        # 理解阶段：LLM 已输出推理即可
        if name == "理解":
            return ctx.iteration >= 1

        # 收集阶段：至少有一次成功的工具调用
        if name == "收集":
            success_calls = sum(1 for r in ctx.tool_results if r.get("success"))
            return success_calls >= 1

        # 分析阶段：已有收集阶段的结果
        if name == "分析":
            return self._stage_results.get("收集") is not None

        # 写阶段：已有 workspace_write_file 或 write_file 调用
        if name == "写":
            return any(
                r.get("tool_call", {}).get("name", "") in ("workspace_write_file", "write_file")
                for r in ctx.tool_results
            )

        # 验证阶段：调用过 execute_python 或 run_tests
        if name == "验证":
            return any(
                r.get("tool_call", {}).get("name", "") in ("execute_python", "run_tests", "execute_shell")
                for r in ctx.tool_results
            )

        # 导出阶段：有 workspace_export_file
        if name == "导出":
            return any(
                r.get("tool_call", {}).get("name", "") == "workspace_export_file"
                for r in ctx.tool_results
            )

        # 总结阶段：默认完成
        if name == "总结":
            return bool(ctx.final_answer)

        return False
