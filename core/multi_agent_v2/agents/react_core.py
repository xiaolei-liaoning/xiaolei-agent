"""
ReActCore - V2 单 Agent 核心执行器

基于 MiddlewareChain + BaseMiddleware 的 ReAct 循环。
将 cli/middlewares.py 的 ReActMiddleware 逻辑迁入 core 层，
使 CLI 只保留交互职责。
"""

import asyncio
import json
import logging

from .middleware import RunContext, BaseMiddleware, MiddlewareChain

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 3


class ReActCoreMiddleware(BaseMiddleware):
    """ReAct 核心循环：LLM 自主决定调工具还是直接回答"""

    async def on_start(self, ctx: RunContext) -> None:
        """on_start 时获取工具定义"""
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry, _HANDLER_MAP
            reg = get_tool_registry()
            if not reg._initialized:
                await reg.discover_all()
            raw = reg.get_tools_for_task(ctx.task_description, max_tools=25)
            ctx.tool_defs = [
                {"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.parameters},
                 "_server":t.server,"_tool_name":t.tool_name}
                for t in raw if t.name in _HANDLER_MAP or t.handler
            ]
        except Exception as e:
            logger.debug("获取工具定义失败: %s", e)
            ctx.tool_defs = []

    async def on_think_start(self, ctx: RunContext) -> None:
        """每轮 LLM 调用"""
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

        messages = [{"role": "user", "content": ctx.task_description}]
        if ctx.tool_results:
            # 有前序结果时构建完整对话
            for r in ctx.tool_results:
                tc = r.get("tool_call", {})
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.get("id", "call_%d" % ctx.iteration),
                        "type": "function",
                        "function": {"name": tc.get("name", ""), "arguments": json.dumps(tc.get("arguments", {}))},
                    }]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call_%d" % ctx.iteration),
                    "content": json.dumps(r.get("result", {"error": "无结果"}))[:3000],
                })

        try:
            reply = await asyncio.wait_for(
                router.chat(messages, temperature=0.3, max_tokens=2000, tools=ctx.tool_defs or None),
                timeout=30,
            )
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
            result = await self._execute(tc)

            ok = result.get("success", False)
            ctx.tool_results.append({
                "tool_call": {"name": name, "arguments": args, "id": tc.get("id", "")},
                "success": ok,
                "result": result.get("result", result),
            })

        # 未达上限则继续
        if ctx.react_depth >= _MAX_ROUNDS:
            # 超限，强制 LLM 给结论
            asyncio.ensure_future(self._force_answer(ctx))

    async def _execute(self, tc: dict) -> dict:
        """执行单个工具调用"""
        from core.multi_agent_v2.agents.base.base_agent import BaseAgent
        agent = BaseAgent()
        try:
            return await agent._execute_single_tool_call({
                "name": tc.get("function", {}).get("name", ""),
                "arguments": json.loads(tc.get("function", {}).get("arguments", "{}")),
                "_tool_name": tc.get("function", {}).get("name", ""),
                "_server": "",
            })
        except Exception as e:
            return {"success": False, "result": {"error": str(e)}}

    async def _force_answer(self, ctx: RunContext) -> None:
        """超出最大轮次时强制 LLM 给结论"""
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if not router:
            return
        try:
            reply = await asyncio.wait_for(
                router.chat(
                    [{"role": "user", "content": "请基于已有的信息给出最终回答。"}],
                    temperature=0.3, max_tokens=1000,
                ),
                timeout=15,
            )
            ctx.final_answer = reply.strip()
        except Exception:
            pass

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
    """构建默认中间件链：ReActCore 为核心"""
    chain = MiddlewareChain()
    chain.add(ReActCoreMiddleware())
    return chain


async def run_react(task_description: str) -> dict:
    """快捷入口：直接用 ReActCore 处理任务"""
    ctx = RunContext(task_description)
    chain = build_default_chain()
    await chain.on_start(ctx)
    while not ctx.interrupted and ctx.react_depth < _MAX_ROUNDS:
        await chain.on_think_start(ctx)
        await chain.on_think_end(ctx)
    await chain.on_finish(ctx)
    return {
        "success": bool(ctx.final_answer),
        "answer": ctx.final_answer,
        "iterations": ctx.react_depth,
        "tool_results": ctx.tool_results,
        "error": ctx.last_error,
    }
