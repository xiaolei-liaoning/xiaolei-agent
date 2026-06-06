"""
ReActCore - V2 单 Agent 核心执行器

基于 MiddlewareChain + BaseMiddleware 的 ReAct 循环。
将 cli/middlewares.py 的 ReActMiddleware 逻辑迁入 core 层，
使 CLI 只保留交互职责。

增强: PlanAwareMiddleware — 让 Agent 先列计划、追踪进度、动态调整。
"""

import asyncio
import json
import logging
from typing import Optional

from .middleware import HookResult, RunContext, BaseMiddleware, MiddlewareChain
from .plan_tracker import PlanState, StepRecord, parse_plan_from_llm, PLAN_CREATION_PROMPT

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 2
_PLAN_ROUNDS = 12  # 计划模式下允许更多轮次


class ReActCoreMiddleware(BaseMiddleware):
    """ReAct 核心循环：LLM 自主决定调工具还是直接回答"""

    async def on_start(self, ctx: RunContext) -> None:
        """on_start 时获取工具定义"""
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
            reg = get_tool_registry()
            if not reg._initialized:
                try:
                    await asyncio.wait_for(reg.discover_all(), timeout=10)
                except asyncio.TimeoutError:
                    logger.warning("MCP 连接超时（10s），仅使用内置工具")
            raw = await reg.get_tools_for_task(ctx.task_description, max_tools=20)
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
        # 使用 ctx.max_iterations（PlanAwareMiddleware 可能已提升到 _PLAN_ROUNDS）
        effective_max = getattr(ctx, "max_iterations", _MAX_ROUNDS)
        if ctx.interrupted or ctx.react_depth >= effective_max:
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
            {"role": "system", "content": "你是多步骤计划的执行者。请按以下规则工作：\n\n【工具选择】\n1. 数据获取：优先用 search（搜索）或 fetch_url（抓取网页）\n2. 文件操作：优先用 file（action=write 写入，action=read 读取）\n3. 代码执行：用 execute_python\n4. 先看内置工具，不够再用专用工具\n\n【数据使用】\n5. 拿到数据后立刻分析使用，不要只获取不分析\n6. 如果已经获取到足够数据，直接处理并保存结果，不要继续搜索新URL\n7. 即使部分数据获取失败，用已有的数据继续完成任务\n\n【文件保存】\n8. 如果任务要求[保存到桌面/保存报告]，务必在最后调用 file(action=write) 保存结果\n9. 全部完成后总结输出\n\n可用工具列表中同时包含内置工具和专用工具。"},
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
            text = reply.strip()

            # 计划模式检测：如果 LLM 只输出计划文本但没有工具调用，
            # 不要当最终答案处理 — 将文本作为 assistant 消息继续
            plan_state = getattr(ctx, "plan_state", None)
            if plan_state and plan_state.created:
                # 检测是否是计划文本（有编号步骤）
                import re as _re
                plan_like = bool(_re.search(r'[1-5]\s*[.、）\)]', text)) and len(text) > 60
                # 或者是明确的步骤声明
                step_decl = any(kw in text for kw in ["步骤1", "第一步", "第1步", "step 1", "Step 1"])
                if plan_like or step_decl:
                    logger.info("检测到计划文本（无工具调用），继续下一轮执行")
                    # 把计划文本作为 assistant 消息加入，继续循环
                    if hasattr(ctx, '_pending_messages') and ctx._pending_messages:
                        ctx._pending_messages.append({"role": "assistant", "content": text})
                    # 不中断，让 LLM 下一轮执行动作
                    return

            # 纯文本 = 最终答案
            ctx.final_answer = text
            ctx.interrupted = True
            return

        # 并行执行所有工具调用，按原始顺序收集结果
        results = await self._execute_tool_calls_parallel(tool_calls, ctx)

        for tc, result in zip(tool_calls, results):
            name = tc.get("function", {}).get("name", "")
            try:
                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            logger.info("第%d轮 调用: %s", ctx.iteration, name)

            ok = result.get("success", False)
            ctx.tool_results.append({
                "tool_call": {"name": name, "arguments": args, "id": tc.get("id", "")},
                "success": ok,
                "result": result.get("result", result),
            })

            # 代码错误检测：语法/运行时错误时注入修复提示
            eff_max = getattr(ctx, "max_iterations", _MAX_ROUNDS)
            if not ok and ctx.react_depth < eff_max:
                err_text = str(result.get("result", {}))
                if any(kw in err_text for kw in ["SyntaxError", "NameError", "TypeError", "IndentationError"]):
                    ctx.task_description += f"\n[代码错误] 请修复上一轮的代码错误后重试。错误: {err_text[:200]}"
                    logger.info("代码错误检测，注入修复提示")

        eff_max = getattr(ctx, "max_iterations", _MAX_ROUNDS)
        if ctx.react_depth >= eff_max and not ctx.final_answer:
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

    async def _execute_tool_calls_parallel(self, tool_calls: list, ctx: RunContext) -> list:
        """并行执行多个工具调用，按原始顺序返回结果列表"""
        async def _run_one(tc):
            try:
                return await self._execute(tc, ctx)
            except Exception as e:
                return {"success": False, "result": {"error": str(e)}}

        results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
        return results

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


# ═══════════════════════════════════════════════════════════════════
# PlanAwareMiddleware — 计划感知
# ═══════════════════════════════════════════════════════════════════

class PlanAwareMiddleware(BaseMiddleware):
    """计划感知中间件

    让 Agent 能：
    1. on_start → 调用 LLM 生成初始计划（2-5 步）
    2. on_think_start → 每轮注入当前执行状态到 prompt
    3. on_think_end → 根据工具结果自动标记步骤完成/失败

    职责分离：只负责计划和追踪，不干涉工具调用逻辑。
    """

    MIN_PLAN_LENGTH = 15  # 低于此长度的任务跳过计划（中文场景，15个字以上即可）

    async def on_start(self, ctx: RunContext) -> None:
        """执行前创建计划 — 调用 LLM 生成结构化步骤"""
        if len(ctx.task_description) < self.MIN_PLAN_LENGTH:
            return  # 简短任务不需要计划

        # 避免重复创建（可能被多个中间件调用）
        if getattr(ctx, "plan_state", None) is not None:
            return

        plan_state = PlanState()
        ctx.plan_state = plan_state

        # 调用 LLM 创建计划
        try:
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()
            if not router.is_available():
                logger.debug("LLM 不可用，跳过计划创建")
                return

            resp = await asyncio.wait_for(
                router.chat([
                    {"role": "system", "content": PLAN_CREATION_PROMPT},
                    {"role": "user", "content": ctx.task_description},
                ], temperature=0.3, max_tokens=1200),
                timeout=15,
            )

            text = resp if isinstance(resp, str) else str(resp)
            ok = parse_plan_from_llm(text, plan_state)
            if not ok:
                logger.debug("LLM 未返回有效计划，继续无计划模式")
                return
        except Exception as e:
            logger.debug(f"计划创建异常（继续执行）: {e}")
            return

        # ── 计划创建成功 → 注入计划到任务描述 ──
        ctx.max_iterations = max(ctx.max_iterations, _PLAN_ROUNDS)
        ctx.task_description = (
            plan_state.plan_prompt_block() + "\n\n"
            + ctx.task_description + "\n\n"
            + "【执行规则】\n"
            + "1. 以上是已制定的执行计划\n"
            + "2. 从第1步开始，每轮执行一个步骤\n"
            + "3. 每步完成后会自动更新进度状态\n"
            + "4. 完成后总结输出\n"
            + "5. **不要只列出计划就停止** — 列出计划后立即开始执行第1步！"
        )
        logger.info(f"📋 计划已创建: {len(plan_state.steps)} 步, 上限 {_PLAN_ROUNDS} 轮")

    async def on_think_start(self, ctx: RunContext) -> None:
        """每轮 LLM 调用前：注入当前执行进度"""
        plan_state: PlanState = getattr(ctx, "plan_state", None)
        if not plan_state or not plan_state.created:
            return

        plan_state.round_count += 1
        plan_state.begin_current()  # 标记当前步骤为 in_progress

        # 生成进度文本并注入
        status = plan_state.status_prompt()
        if status and status != plan_state.last_status:
            # 替换上一次的状态文本（避免无限累积）
            if plan_state.last_status and plan_state.last_status in ctx.task_description:
                ctx.task_description = ctx.task_description.replace(
                    plan_state.last_status, ""
                ).rstrip()
            ctx.task_description += status
            plan_state.last_status = status

            logger.debug(f"📊 第{plan_state.round_count}轮 进度注入: "
                         f"{plan_state.progress()} 当前:{plan_state.current().name if plan_state.current() else '无'}")

    async def on_think_end(self, ctx: RunContext) -> None:
        """每轮 LLM 回复后：检测步骤完成，动态调整

        步骤完成判定条件（满足任一即可）：
        1. 成功的文件写入 → "写入文件" 类步骤完成
        2. 成功工具调用 + 已到轮次上限 → 收尾当前步骤
        3. final_answer 已设置 → 全部完成
        """
        plan_state: PlanState = getattr(ctx, "plan_state", None)
        if not plan_state or not plan_state.created:
            return

        if ctx.interrupted:
            return

        current = plan_state.current()
        if not current:
            return  # 所有步骤已处理完

        # ── 条件1: 文件写入成功 → 步骤完成 ──
        for tr in reversed(ctx.tool_results[-3:]):
            if tr.get("success") and tr.get("tool_call", {}).get("name") == "file":
                result = str(tr.get("result", ""))[:100]
                plan_state.finish_current(result)
                logger.info(f"✅ 步骤 [{current.id}] {current.name} 完成（文件写入）")

                # 检测是否所有步骤完成
                if plan_state.done():
                    ctx.final_answer = f"✅ 全部 {len(plan_state.steps)} 步执行完成！\n{plan_state.status_prompt()}"
                    ctx.interrupted = True
                return  # 完成一个步骤，当前轮不再继续

        # ── 条件2: 已到轮次上限 → 收尾 ──
        max_r = getattr(ctx, "max_iterations", _MAX_ROUNDS)
        if ctx.react_depth >= max_r and not ctx.final_answer:
            # 有成功结果就完成，否则失败
            has_ok = any(r.get("success") for r in ctx.tool_results[-5:])
            if has_ok:
                plan_state.finish_current("步骤完成（上限）")
            else:
                plan_state.fail_current("轮次上限，无成功结果")

            if plan_state.done():
                ctx.final_answer = (
                    f"{'✅' if plan_state.all_ok() else '⚠️'} 执行完毕\n"
                    f"{plan_state.status_prompt()}"
                )
                ctx.interrupted = True

    async def on_finish(self, ctx: RunContext) -> None:
        """执行结束：保存计划摘要到 profile"""
        plan_state: PlanState = getattr(ctx, "plan_state", None)
        if plan_state and plan_state.created:
            ctx.profile["plan"] = plan_state.to_dict()
            ctx.profile["plan_summary"] = plan_state.status_prompt()


def build_default_chain() -> MiddlewareChain:
    """构建默认中间件链：Profile → PlanAware → ReActDepth → ReActCore → ..."""
    chain = MiddlewareChain()
    from .middleware import DynamicStageRoutingMiddleware
    from .middlewares import (
        ProfileMiddleware, ReActDepthMiddleware,
        ConfidenceMiddleware, ReflectionMiddleware,
        KEPAMiddleware, BranchMiddleware,
        DataPipelineMiddleware, AskUserMiddleware,
        ReflectionCheckMiddleware,
        ToolCorrectionMiddleware,
    )
    chain.add(ProfileMiddleware())       # 任务画像
    chain.add(DynamicStageRoutingMiddleware())  # ⭐ 阶段流水线
    chain.add(PlanAwareMiddleware())     # ⭐ 计划感知 — 先列计划，追踪进度
    chain.add(ReActDepthMiddleware())    # 深度控制
    chain.add(ToolCorrectionMiddleware())# ⭐ 工具纠错 — 检测空结果，建议换工具
    chain.add(ReActCoreMiddleware())     # ReAct 核心循环
    chain.add(ReflectionCheckMiddleware())  # ⭐ 反思检查 — 替代主循环硬编码
    chain.add(DataPipelineMiddleware())  # ⭐ 数据流水线
    chain.add(ConfidenceMiddleware())    # 置信度评估
    chain.add(ReflectionMiddleware())    # 执行反思
    chain.add(KEPAMiddleware())          # KEPA 闭环
    chain.add(BranchMiddleware())        # 策略分支
    chain.add(AskUserMiddleware())       # ⭐ 用户交互
    return chain


async def run_react(task_description: str, max_rounds: int = 0) -> dict:
    """快捷入口：直接用 ReActCore 处理任务
    Args:
        task_description: 任务描述
        max_rounds: 最大轮数，0 表示自动判断（有计划模式→_PLAN_ROUNDS, 否则→默认）
    """
    if max_rounds == 0:
        # 计划模式由 PlanAwareMiddleware 在 on_start 中动态设置 ctx.max_iterations
        # 这里先设默认值，on_start 中可能提升
        if "[工具提示] 请使用工具" in task_description:
            max_rounds = 1
        elif "[工具提示] 立刻调用" in task_description:
            max_rounds = 2
        else:
            max_rounds = _MAX_ROUNDS
    ctx = RunContext(task_description)
    ctx.max_iterations = max_rounds  # 初始值，PlanAwareMiddleware.on_start 可能改写
    chain = build_default_chain()
    await chain.on_start(ctx)
    ctx._chain = chain  # 让 ReActCoreMiddleware 能调 chain.on_wrap_tool_call

    # 使用 PlanAwareMiddleware 可能提升后的 max_iterations
    effective_max = max_rounds
    plan_state = getattr(ctx, "plan_state", None)
    if plan_state and plan_state.created:
        effective_max = max(ctx.max_iterations, max_rounds)
        logger.info(f"🔄 计划模式启动: {len(plan_state.steps)} 步, 上限 {effective_max} 轮")

    while not ctx.interrupted and ctx.react_depth < effective_max:
        # on_think_start: 跳转处理
        hr_start = await chain.on_think_start(ctx)
        if hr_start.jump_to == "end":
            if hr_start.reason:
                ctx.last_error = hr_start.reason
                logger.warning(f"中间件终止: {hr_start.reason}")
            ctx.interrupted = True
            break
        elif hr_start.jump_to == "retry":
            ctx.task_description += f"\n[决策] {hr_start.reason} 重试。"
            logger.info(f"中间件决策: {hr_start.reason}")
            # 不让它空转，继续执行

        if ctx.interrupted:
            break

        hr_end = await chain.on_think_end(ctx)
        if hr_end.jump_to == "end":
            if hr_end.reason:
                ctx.last_error = hr_end.reason
                logger.warning(f"中间件终止: {hr_end.reason}")
            ctx.interrupted = True
            break
        elif hr_end.jump_to == "retry":
            ctx.task_description += f"\n[决策] {hr_end.reason} 重试。"
            logger.info(f"中间件决策: {hr_end.reason}")

        if ctx.interrupted:
            break

        # on_tool_end: 跳转处理
        hr_tool = await chain.on_tool_end(ctx)
        if hr_tool.jump_to == "end":
            if hr_tool.reason:
                ctx.last_error = hr_tool.reason
                logger.warning(f"中间件终止: {hr_tool.reason}")
            ctx.interrupted = True
            break
        elif hr_tool.jump_to == "retry":
            ctx.task_description += f"\n[决策] {hr_tool.reason} 重试。"
            logger.info(f"中间件决策: {hr_tool.reason}")

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
