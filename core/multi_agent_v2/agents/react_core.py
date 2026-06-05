"""
ReActCore - V2 单 Agent 核心执行器

基于 MiddlewareChain + BaseMiddleware 的 ReAct 循环。
将 cli/middlewares.py 的 ReActMiddleware 逻辑迁入 core 层，
使 CLI 只保留交互职责。
"""

import asyncio
import json
import logging
from typing import Optional

from .middleware import RunContext, BaseMiddleware, MiddlewareChain

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 2


class ReActCoreMiddleware(BaseMiddleware):
    """ReAct 核心循环：LLM 自主决定调工具还是直接回答"""

    async def on_start(self, ctx: RunContext) -> None:
        """on_start 时获取工具定义"""
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
            reg = get_tool_registry()
            if not reg._initialized:
                await reg.discover_all()
            raw = await reg.get_tools_for_task(ctx.task_description, max_tools=100)
            # 暴露所有工具给 LLM（内置 + 已连接的 MCP 工具）
            # MCP 工具通过 Server 字段路由到对应的 MCP 服务器
            ctx.tool_defs = [
                {"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.parameters},
                 "_server":t.server,"_tool_name":t.tool_name}
                for t in raw
            ]
            n_builtin = sum(1 for t in raw if t.server == "__builtin__")
            n_mcp = sum(1 for t in raw if t.server not in ("__builtin__", ""))
            logger.info(f"暴露 {len(ctx.tool_defs)} 个工具 ({n_builtin} 内置 + {n_mcp} MCP)")
        except Exception as e:
            logger.debug("获取工具定义失败: %s", e)
            ctx.tool_defs = []

    async def on_think_start(self, ctx: RunContext) -> None:
        """每轮 LLM 调用 — 通过 chain.on_wrap_model_call 走洋葱包裹"""
        if ctx.interrupted or ctx.react_depth >= _MAX_ROUNDS:
            return

        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if not router.is_available():
            ctx.interrupted = True
            ctx.last_error = "LLM 不可用"
            return

        ctx.react_depth += 1
        ctx.iteration = ctx.react_depth

        # 构建消息，存到 ctx 供中间件读取
        ctx._pending_messages = [
            {"role": "system", "content": "你是多步骤计划的执行者。当前步骤已有明确任务，直接执行即可，无需重新选择工具类型。\n\n可用的工具列表中包含了大量专用工具（如 send_notification 发通知、get_art 获取ASCII艺术、multiply 计算乘法、get_forecast 查天气等），优先选用名称最匹配的专用工具，而不是自己写代码实现。"},
            {"role": "user", "content": ctx.task_description},
        ]
        if ctx.tool_results:
            for r in ctx.tool_results:
                tc = r.get("tool_call", {})
                ctx._pending_messages.append({
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": tc.get("id", "call_%d" % ctx.iteration),
                        "type": "function",
                        "function": {"name": tc.get("name", ""), "arguments": json.dumps(tc.get("arguments", {}))},
                    }]
                })
                ctx._pending_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call_%d" % ctx.iteration),
                    "content": json.dumps(r.get("result", {"error": "无结果"}))[:3000],
                })

        async def _llm_call():
            return await asyncio.wait_for(
                router.chat(ctx._pending_messages, temperature=0.3, max_tokens=2000,
                           tools=ctx.tool_defs or None),
                timeout=30,
            )

        try:
            if ctx._chain:
                reply = await ctx._chain.on_wrap_model_call(ctx, _llm_call)
            else:
                reply = await _llm_call()
            ctx._last_reply = reply
        except asyncio.TimeoutError:
            ctx.interrupted = True
            ctx.last_error = "LLM 超时"
        except Exception as e:
            ctx.interrupted = True
            ctx.last_error = str(e)

    async def on_think_end(self, ctx: RunContext) -> None:
        """解析 LLM 回复，执行工具或输出答案"""
        if ctx.interrupted:
            return

        reply = getattr(ctx, "_last_reply", "")
        if not reply:
            return

        tool_calls = self._parse_tool_calls(reply)

        if not tool_calls:
            # 纯文本 = 最终答案
            text = reply.strip()
            ctx.final_answer = text
            ctx.interrupted = True
            return

        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            try:
                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            logger.info("第%d轮 调用: %s", ctx.iteration, name)
            result = await self._execute(tc, ctx)

            ok = result.get("success", False)
            ctx.tool_results.append({
                "tool_call": {"name": name, "arguments": args, "id": tc.get("id", "")},
                "success": ok,
                "result": result.get("result", result),
            })

            # 代码错误检测：语法/运行时错误时注入修复提示
            if not ok and ctx.react_depth < _MAX_ROUNDS:
                err_text = str(result.get("result", {}))
                if any(kw in err_text for kw in ["SyntaxError", "NameError", "TypeError", "IndentationError"]):
                    ctx.task_description += f"\n[代码错误] 请修复上一轮的代码错误后重试。错误: {err_text[:200]}"
                    logger.info("代码错误检测，注入修复提示")

        if ctx.react_depth >= _MAX_ROUNDS and not ctx.final_answer:
            # 检查所有轮次中是否有成功的工具调用
            has_success = any(r.get("success") for r in ctx.tool_results)

            if has_success:
                last = ctx.tool_results[-1]
                text = str(last.get("result", last.get("error", "")))
                if text and text != "None":
                    ctx.final_answer = text[:500]
                if not ctx.final_answer:
                    ctx.last_error = "步骤未实际执行任何工具调用"
            else:
                ctx.last_error = "步骤未实际执行任何工具调用"
            ctx.interrupted = True

    async def _execute(self, tc: dict, ctx: Optional[RunContext] = None) -> dict:
        """执行单个工具调用 — 通过 chain.on_wrap_tool_call 走洋葱包裹"""
        tool_args = {
            "name": tc.get("function", {}).get("name", ""),
            "arguments": json.loads(tc.get("function", {}).get("arguments", "{}")),
            "_tool_name": tc.get("function", {}).get("name", ""),
            "_server": self._lookup_server(tc.get("function", {}).get("name", ""), ctx),
        }
        # 如果有 chain 引用，走 wrap 链
        if ctx and hasattr(ctx, '_chain') and ctx._chain:
            try:
                return await ctx._chain.on_wrap_tool_call(ctx, tool_args)
            except Exception as e:
                return {"success": False, "result": {"error": str(e)}}
        # 无 chain 引用时直接调
        from core.multi_agent_v2.agents.base.base_agent import BaseAgent
        agent = BaseAgent()
        try:
            return await agent._execute_single_tool_call(tool_args)
        except Exception as e:
            return {"success": False, "result": {"error": str(e)}}

    @staticmethod
    def _lookup_server(tool_name: str, ctx: RunContext) -> str:
        """从 ctx.tool_defs 中根据工具名称查找对应的 _server"""
        if not ctx or not ctx.tool_defs or not tool_name:
            return ""
        for td in ctx.tool_defs:
            if td.get("function", {}).get("name") == tool_name:
                return td.get("_server", "")
        return ""

    @staticmethod
    def _parse_tool_calls(reply: str) -> list:
        """解析 LLM 返回中的 tool_calls"""
        try:
            data = json.loads(reply)
            if isinstance(data, dict):
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                    return msg.get("tool_calls", [])
                return data.get("tool_calls", [])
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return []


def build_default_chain() -> MiddlewareChain:
    """构建默认中间件链：Profile → ReActDepth → ReActCore → Confidence → Reflection → KEPA → Branch"""
    chain = MiddlewareChain()
    from .middlewares import (
        ProfileMiddleware, ReActDepthMiddleware,
        ConfidenceMiddleware, ReflectionMiddleware,
        KEPAMiddleware, BranchMiddleware,
    )
    chain.add(ProfileMiddleware())       # 任务画像
    chain.add(ReActDepthMiddleware())    # 深度控制
    chain.add(ReActCoreMiddleware())     # ReAct 核心循环
    chain.add(ConfidenceMiddleware())    # 置信度评估（低置信度注入换策略提示）
    chain.add(ReflectionMiddleware())    # 执行反思（全部失败时注入反馈）
    chain.add(KEPAMiddleware())          # KEPA 闭环（发布到 SharedBus + 记录 kepa_states）
    chain.add(BranchMiddleware())        # 策略分支（连续失败注入切换提示）
    return chain


async def run_react(task_description: str, max_rounds: int = 0) -> dict:
    """快捷入口：直接用 ReActCore 处理任务
    Args:
        task_description: 任务描述
        max_rounds: 最大轮数，0 表示使用默认 _MAX_ROUNDS(2)，有工具提示时自动降为1
    """
    if max_rounds == 0:
        # 有文件工具提示时 1 轮（file工具简单直接）；有MCP工具提示时 2 轮（LLM可能需要多一轮尝试）
        if "[工具提示] 请使用工具" in task_description:
            max_rounds = 1
        elif "[工具提示] 立刻调用" in task_description:
            max_rounds = 2  # MCP工具提示 — 给 LLM 两轮机会
        else:
            max_rounds = _MAX_ROUNDS
    ctx = RunContext(task_description)
    chain = build_default_chain()
    await chain.on_start(ctx)
    ctx._chain = chain  # 让 ReActCoreMiddleware 能调 chain.on_wrap_tool_call
    while not ctx.interrupted and ctx.react_depth < max_rounds:
        await chain.on_think_start(ctx)
        await chain.on_think_end(ctx)
        await chain.on_tool_end(ctx)  # 触发 KEPA/反思/置信度中间件
        # 检测反思反馈：工具全部失败且无产出时提前中断，防止空转
        if ctx.profile.get("reflection_feedback") and not ctx.final_answer:
            ctx.interrupted = True
            logger.warning("检测到反思反馈且无产出，提前终止空转")
        # 消费中间件决策信号
        while ctx.decisions:
            d = ctx.decisions.pop(0)
            if d.get("action") == "retry" and not ctx.interrupted:
                ctx.task_description += f"\n[决策] {d.get('reason','')} 重试。"
                logger.info(f"中间件决策: {d.get('reason','')}")
            elif d.get("action") == "abort":
                ctx.interrupted = True
                ctx.last_error = d.get("reason", "中间件终止执行")
                logger.warning(f"中间件终止: {d.get('reason','')}")

        # 检查反思历史：如果连续2轮都失败且有反思记录，将失败信息注入下一轮提示
        if ctx.reflection_history and not ctx.final_answer:
            last_ref = ctx.reflection_history[-1]
            if last_ref.get("success_rate", 1) == 0 and last_ref.get("total_calls", 0) > 0:
                # 在下一轮 task_description 注入提示
                if not ctx.task_description.endswith("[反思]"):
                    ctx.task_description += "\n[反思] 上一轮全部失败，请换一种方法（换工具或直接回答）。"
                    logger.info("已注入反思提示到下一轮")
    await chain.on_finish(ctx)
    # 如果没设 final_answer 但有成功工具调用，用最后工具结果当 answer
    if not ctx.final_answer and ctx.tool_results:
        last = ctx.tool_results[-1]
        text = str(last.get("result", last.get("error", "")))
        if text and text != "None":
            ctx.final_answer = text[:500]
    return {
        "success": bool(ctx.final_answer),
        "answer": ctx.final_answer,
        "iterations": ctx.react_depth,
        "tool_results": ctx.tool_results,
        "error": ctx.last_error,
    }
