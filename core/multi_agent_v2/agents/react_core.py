"""
ReActCore — V2 单 Agent 核心执行器

基于 MiddlewareChain 的 ReAct 循环：
  LLM → Tool → Observation → 继续/结束

4层中间件链: [ReActDepth → ReActCore ★ → Reflection → KEPA]

简化点：
  - 去掉 PlanAwareMiddleware（不预设计划）
  - 去掉复杂兜底逻辑（只在必用时触发 LLM 汇总）
  - 去掉了 DynamicStageRouting / DataPipeline / Confidence 等
  - 保留核心：LLM ↔ 工具 ↔ 观察 ↔ 循环
"""

import asyncio
import json
import logging
from typing import Any, List, Optional

from .middleware import BaseMiddleware, MiddlewareChain, PlanStep, RunContext

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 10


class ReActCoreMiddleware(BaseMiddleware):
    """ReAct 核心循环：LLM 自主决定调工具还是直接回答"""

    def _get_prefix(self, ctx: RunContext) -> str:
        """从上下文获取Agent前缀"""
        if hasattr(ctx, "_chain") and ctx._chain and hasattr(ctx._chain, "_agent"):
            agent = ctx._chain._agent
            return _get_prefix(agent)
        return ""

    async def on_start(self, ctx: RunContext) -> None:
        """on_start 时获取工具定义"""
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry

        reg = get_tool_registry()
        try:
            await asyncio.wait_for(reg.discover_all(), timeout=10)
            raw = list(reg._tools.values()) if reg._tools else []
            ctx.tool_defs = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                    "_server": t.server,
                    "_tool_name": t.tool_name,
                }
                for t in raw[:20]
            ]
            n_builtin = sum(1 for t in raw if t.server == "__builtin__")
            n_mcp = len(raw) - n_builtin
            logger.info(
                f"暴露 {len(ctx.tool_defs)} 个工具 ({n_builtin} 内置 + {n_mcp} MCP)"
            )
        except asyncio.TimeoutError:
            logger.warning("工具发现超时（10s），仅用内置工具")
            try:
                from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS

                ctx.tool_defs = [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        },
                        "_server": "__builtin__",
                        "_tool_name": t.name,
                    }
                    for t in _SANDBOX_TOOL_DEFS
                ]
            except Exception:
                ctx.tool_defs = []
        except Exception as e:
            logger.debug(f"工具发现失败: {e}")
            ctx.tool_defs = []

    async def on_think_start(self, ctx: RunContext) -> None:
        """每轮 LLM 调用"""
        if ctx.interrupted or ctx.react_depth >= ctx.max_iterations:
            return

        from core.engine.llm_backend import get_llm_router

        router = get_llm_router()
        if not router.is_available():
            logger.error("❌ LLM 不可用")
            ctx.interrupted = True
            ctx.last_error = "LLM 不可用"
            return

        ctx.react_depth += 1
        ctx.iteration = ctx.react_depth

        # 构建消息 — 注入计划进度让 agent 知晓已完成/未完成步骤
        plan_context = _steps_summary(ctx) if ctx.plan else ""

        system_content = (
            "你是AI助手，通过调用可用工具来完成任务。\n\n"
            "【关键规则】\n"
            "- 搜索资讯 → 调用 search 工具\n"
            "- 抓取网页内容（热搜、新闻、页面数据等）→ 优先用 Playwright MCP 的 browser_navigate + browser_snapshot\n"
            "- 读写文件 → 调用 file 工具\n"
            "- 查看目录 → 调用 execute_shell 工具\n"
            "- 执行代码 → 调用 execute_python 工具\n"
            "- 生成大文件 → 调用 execute_python 工具，用open().write()写入\n\n"
            "【并行调用】\n"
            "- 如果多个工具之间没有依赖关系，可以在一次回复中同时调用多个工具！\n"
            "- 例如：搜索+读文件、或 执行代码+查天气 都可以同时调用\n"
            "- 这样可以大幅减少轮数，更快完成任务\n\n"
            "【注意】\n"
            "- 必须调用工具函数来执行操作，不要只输出命令文本\n"
            "- 写文件必须一次性写入完整内容，不要口头输出\n"
            "- 如果任务要求写在桌面或保存到文件或生成报告，最后一步必须用 execute_python 调用 open().write() 写入桌面文件\n"
            "- 拿到数据立刻分析使用\n"
            "- 最终用文本输出结果"
        )
        if plan_context:
            system_content += plan_context
        if ctx.personality_prompt:
            system_content = f"{ctx.personality_prompt}\n\n{system_content}"
        ctx._pending_messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": ctx.task_description},
        ]
        if ctx.tool_results:
            for r in ctx.tool_results:
                tc = r.get("tool_call", {})
                ctx._pending_messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tc.get("id", f"call_{ctx.iteration}"),
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", ""),
                                    "arguments": json.dumps(tc.get("arguments", {})),
                                },
                            }
                        ],
                    }
                )
                ctx._pending_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{ctx.iteration}"),
                        "content": json.dumps(r.get("result", {"error": "无结果"}))[
                            :3000
                        ],
                    }
                )

        prefix = self._get_prefix(ctx)
        print(
            f"{prefix}    \033[1;36m🤔 LLM思考第{ctx.react_depth}/{ctx.max_iterations}轮...\033[0m"
        )

        async def _llm_call():
            try:
                llm_timeout = 60 if ctx.react_depth <= 2 else 30
                llm_max_tokens = 4000 if ctx.react_depth <= 2 else 2000
                _model = ctx.model_override or None
                return await asyncio.wait_for(
                    router.chat(
                        ctx._pending_messages,
                        temperature=0.3,
                        max_tokens=llm_max_tokens,
                        tools=ctx.tool_defs or None,
                        model=_model,
                    ),
                    timeout=llm_timeout,
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ 第{ctx.react_depth}轮 LLM调用超时({llm_timeout}s)")
                raise

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

        prefix = self._get_prefix(ctx)
        reply = getattr(ctx, "_last_reply", "")
        if not reply:
            logger.warning(f"第{ctx.react_depth}轮 LLM返回空响应")
            if any(r.get("success") for r in ctx.tool_results):
                ctx.final_answer = "已通过工具获取到结果。"
            else:
                ctx.last_error = "LLM返回空响应"
            ctx.interrupted = True
            return

        tool_calls = self._parse_tool_calls(reply)

        if not tool_calls:
            text = reply.strip()
            # 检测 LLM mock 响应
            if any(sig in text for sig in ["[LLM_MOCK]", "系统正在处理您的请求"]):
                logger.warning("检测到LLM mock/fallback响应，跳过此轮")
                ctx.task_description += "\n[注意] 上轮LLM返回了空响应，请重新尝试。"
                return

            # 纯文本 = 最终答案
            print(f"{prefix}    \033[32m✅ LLM输出最终答案\033[0m")
            ctx.final_answer = text
            ctx.interrupted = True
            return

        # 执行工具调用
        tool_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
        print(f"{prefix}    \033[1;33m🔧 调用: {', '.join(tool_names)}\033[0m")

        results = await self._execute_tool_calls_parallel(tool_calls, ctx)

        for tc, result in zip(tool_calls, results):
            name = tc.get("function", {}).get("name", "?")
            ok = result.get("success", False)
            icon = "✅" if ok else "⚠️"
            detail = ""
            if ok:
                result_preview = str(result.get("result", ""))[:80]
                if result_preview and name not in ("file", "execute_python"):
                    detail = f" → {result_preview[:60]}"
            else:
                # 错误可能在顶层 (MiddlewareChain) 或 result.error 下 (超时/异常)
                err = (
                    result.get("error")
                    or result.get("result", {}).get("error", "")
                    or str(result.get("result", ""))[:60]
                )
                detail = f" {err[:60]}" if err else " (执行失败，无错误信息)"
            print(f"{prefix}    \033[1;32m{icon} {name}{detail}\033[0m")

            try:
                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            ok = result.get("success", False)
            ctx.tool_results.append(
                {
                    "tool_call": {
                        "name": name,
                        "arguments": args,
                        "id": tc.get("id", ""),
                    },
                    "success": ok,
                    "result": result.get("result", result),
                }
            )

            # 代码错误修复提示（检查 result 内容，不仅靠 success 标志）
            if ctx.react_depth < ctx.max_iterations:
                raw = str(result.get("result", {}))
                err_text = raw[:500]
                if any(
                    kw in err_text
                    for kw in ["❌", "SyntaxError", "NameError", "TypeError", "Error:"]
                ):
                    ctx.task_description += (
                        f"\n[代码错误] 上次代码出错，请修复后重试: {err_text[:400]}"
                    )
                    print(f"{prefix}    \033[1;31m⚠️ 代码出错，已注入修复提示\033[0m")

        # 达到轮次上限且没有 final_answer → 用已有结果
        if ctx.react_depth >= ctx.max_iterations and not ctx.final_answer:
            has_success = any(r.get("success") for r in ctx.tool_results)
            if has_success:
                last = ctx.tool_results[-1]
                text = str(last.get("result", last.get("error", "")))
                ctx.final_answer = text[:500] if text and text != "None" else ""
            if not ctx.final_answer:
                ctx.last_error = "步骤未实际执行任何工具调用"
            ctx.interrupted = True

    _TOOL_TIMEOUTS = {
        "search": 45,
        "fetch_url": 30,
        "execute_python": 20,
        "execute_shell": 15,
        "file": 10,
        "rag_search": 20,
    }
    _DEFAULT_TIMEOUT = 15

    async def _execute(self, tc: dict, ctx: Optional[RunContext] = None) -> dict:
        tool_name = tc.get("function", {}).get("name", "")
        tool_args = {
            "name": tool_name,
            "arguments": json.loads(tc.get("function", {}).get("arguments", "{}")),
            "_tool_name": tool_name,
            "_server": self._lookup_server(tool_name, ctx),
        }
        timeout = self._TOOL_TIMEOUTS.get(tool_name, self._DEFAULT_TIMEOUT)

        async def _do_execute():
            if ctx and hasattr(ctx, "_chain") and ctx._chain:
                return await ctx._chain.on_wrap_tool_call(ctx, tool_args)
            return {"success": False, "error": "no chain", "tool_call": tool_args}

        try:
            return await asyncio.wait_for(_do_execute(), timeout=timeout)
        except asyncio.TimeoutError:
            return {
                "success": False,
                "result": {"error": f"工具 {tool_name} 执行超时({timeout}s)"},
            }
        except Exception as e:
            return {"success": False, "result": {"error": str(e)}}

    async def _execute_tool_calls_parallel(
        self, tool_calls: list, ctx: RunContext
    ) -> list:
        async def _run_one(tc):
            try:
                return await self._execute(tc, ctx)
            except Exception as e:
                return {"success": False, "result": {"error": str(e)}}

        return await asyncio.gather(*[_run_one(tc) for tc in tool_calls])

    @staticmethod
    def _lookup_server(tool_name: str, ctx: RunContext) -> str:
        if not ctx or not ctx.tool_defs or not tool_name:
            return ""
        for td in ctx.tool_defs:
            if td.get("function", {}).get("name") == tool_name:
                return td.get("_server", "")
        return ""

    @staticmethod
    def _parse_tool_calls(reply: str) -> list:
        try:
            data = json.loads(reply)
            if isinstance(data, dict):
                choices = data.get("choices", [])
                if choices:
                    msg = (
                        choices[0].get("message", {})
                        if isinstance(choices[0], dict)
                        else {}
                    )
                    return msg.get("tool_calls", [])
                return data.get("tool_calls", [])
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return []


def build_default_chain() -> MiddlewareChain:
    """构建默认中间件链：ReActDepth → ReActCore → Reflection → KEPA"""
    chain = MiddlewareChain()
    from .middlewares import (
        KEPAMiddleware,
        ReActDepthMiddleware,
        ReflectionMiddleware,
    )

    chain.add(ReActDepthMiddleware())  # 深度保护 + 连续失败检测
    chain.add(ReActCoreMiddleware())  # ★ ReAct 核心循环
    chain.add(ReflectionMiddleware())  # 定期反思，写入 temp_memory
    chain.add(KEPAMiddleware())  # KEPA 知识闭环
    return chain


async def _generate_plan(
    task_description: str, ctx: RunContext, retry_context: str = ""
) -> List[PlanStep]:
    """规划阶段 — LLM 将任务拆解为结构化步骤计划"""
    from core.engine.llm_backend import get_llm_router

    router = get_llm_router()
    if not router or not router.is_available():
        return []

    retry_hint = f"\n【重试背景】{retry_context}\n" if retry_context else ""
    plan_prompt = (
        "将任务拆解为1-2个执行步骤，不要拆分过细。\n\n"
        "可用工具（从以下选，不要编造）：\n"
        '  execute_shell — 执行Shell命令。百度热搜用此工具，command="python3 scripts/fetch_baidu_hotsearch.py"\n'
        "  execute_python — 执行Python代码。写文件唯一途径！生成文件到桌面、写代码都只有这个工具能用\n"
        "  search — 联网搜索\n"
        "  open_app — 打开Mac应用\n\n"
        "示例：\n"
        "步骤|抓取百度热搜并写分析报告到桌面|execute_shell,execute_python\n"
        "步骤|写八数码游戏HTML到桌面文件|execute_python\n"
        "步骤|打开QQ应用|open_app\n\n"
        f"任务：{task_description[:300]}"
        f"{retry_hint}\n"
        "如果不需要工具：步骤|直接回答\n"
        "开始："
    )
    try:
        resp = await asyncio.wait_for(
            router.chat(
                [{"role": "user", "content": plan_prompt}],
                temperature=0.2,
                max_tokens=500,
            ),
            timeout=15.0,
        )
        text = str(resp).strip() if resp else ""
        if not text or "[LLM_MOCK]" in text:
            return []

        steps: List[PlanStep] = []
        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("步骤|"):
                continue
            parts = line.split("|")
            desc = parts[1].strip() if len(parts) > 1 else ""
            tools_str = parts[2].strip() if len(parts) > 2 else ""
            if "直接回答" in desc:
                return []
            tools = (
                [t.strip() for t in tools_str.split(",") if t.strip()]
                if tools_str
                else []
            )
            steps.append(
                PlanStep(index=len(steps) + 1, description=desc, tool_names=tools)
            )
        return steps[:5]
    except Exception:
        return []


def _display_plan(
    ctx: RunContext, header: str = "📋 执行计划", prefix: str = ""
) -> None:
    """显示计划进度条"""
    if not ctx.plan:
        return
    done = sum(1 for s in ctx.plan if s.status == "done")
    total = len(ctx.plan)
    color = "\033[1;34m"
    reset = "\033[0m"

    lines = [f"{prefix}    {color}{header}（{done}/{total}）:{reset}"]
    for step in ctx.plan:
        if step.status == "done":
            icon = "✅"
        elif step.status == "running":
            icon = "➡️"
        elif step.status == "failed":
            icon = "❌"
        else:
            icon = "  "
        desc = step.description.replace("\n", " ")[:60]
        lines.append(f"{prefix}      {icon} {desc}")
    print("\n".join(lines))


def _steps_summary(ctx: RunContext) -> str:
    """生成步骤状态的文本摘要（注入 system prompt）"""
    if not ctx.plan:
        return ""
    lines = ["\n\n【计划进度】"]
    for step in ctx.plan:
        if step.status == "done":
            lines.append(f"  ✅ 第{step.index}步: {step.description}")
        elif step.status == "running":
            lines.append(f"  ➡️  第{step.index}步: {step.description}（当前步骤）")
        elif step.status == "failed":
            lines.append(
                f"  ❌ 第{step.index}步: {step.description} — 失败需重试或跳过"
            )
        else:
            lines.append(f"  ⬜ 第{step.index}步: {step.description}")
    lines.append("— 已完成步骤不要重复做。优先推进未完成的步骤。")
    return "\n".join(lines)


def _update_step_status(ctx: RunContext) -> None:
    """简单的轮次计数器：每轮有成功的工具调用就推进一个步骤"""
    if not ctx.plan:
        return

    # 本轮有工具调用吗
    has_any_call = bool(ctx.tool_results)
    if not has_any_call:
        return

    # 检查最近一次工具调用的结果中是否包含错误
    last_result = ctx.tool_results[-1]
    last_raw = str(last_result.get("result", last_result.get("error", "")))
    has_error = any(
        marker in last_raw
        for marker in ["❌", "SyntaxError", "NameError", "TypeError", "Error:"]
    )

    # 如果有代码错误，不推进步骤（让 LLM 原地修复）
    if has_error:
        return

    # 计算已完成步骤数，推进下一个
    done_count = sum(1 for s in ctx.plan if s.status == "done")
    if done_count >= len(ctx.plan):
        return

    ctx.plan[done_count].status = "done"


async def _replan_failed(ctx: RunContext) -> bool:
    """重新规划失败的步骤，保留已完成步骤"""
    done_descs = [
        f"第{s.index}步: {s.description}" for s in ctx.plan if s.status == "done"
    ]
    failed = [s for s in ctx.plan if s.status == "failed" or s.status == "pending"]
    failed_descs = [f"第{s.index}步: {s.description}" for s in failed]

    error_context = ""
    if ctx.last_error:
        error_context = f"\n错误: {ctx.last_error}"
    if ctx.tool_results:
        last = ctx.tool_results[-1]
        if not last.get("success"):
            error_context += f"\n工具执行错误: {last.get('error', '') or last.get('result', {}).get('error', '')}"

    retry_prompt = (
        "任务需要重新规划后面的步骤。\n\n"
        f"已完成: {', '.join(done_descs) if done_descs else '无'}\n"
        f"失败的步骤: {', '.join(failed_descs) if failed_descs else '需要继续'}"
        f"{error_context}\n\n"
        "请重新规划未完成的步骤，忽略已完成的。\n"
        "输出格式：步骤|步骤描述|预计使用的工具名(逗号分隔,可省略)\n"
        "开始："
    )

    new_steps = await _generate_plan(
        ctx.task_description, ctx, retry_context=retry_prompt
    )
    if not new_steps:
        return False

    # 保留已完成步骤，用新步骤替换未完成的
    kept = [s for s in ctx.plan if s.status == "done"]
    offset = len(kept)
    for i, s in enumerate(new_steps):
        s.index = offset + i + 1
        s.status = "pending"
    ctx.plan = kept + new_steps
    ctx.plan_generation += 1
    return True


def _get_prefix(agent: Any = None) -> str:
    """获取Agent前缀标签"""
    if agent and hasattr(agent, "_agent_label"):
        label = agent._agent_label
        # 截取合适的长度
        short_label = label[:15] if len(label) > 15 else label
        return f"[{short_label}] "
    return ""


async def run_react(
    task_description: str,
    max_rounds: int = 0,
    model: str = "",
    personality_prompt: str = "",
    agent: Any = None,
) -> dict:
    """快捷入口：直接用 ReActCore 处理任务

    Args:
        task_description: 任务描述
        max_rounds: 最大轮数，0 表示默认 _MAX_ROUNDS
        model: 指定使用的 LLM 模型名
        personality_prompt: Agent 个性/角色提示
        agent: 关联的 WorkAgent 实例
    """
    if max_rounds == 0:
        max_rounds = _MAX_ROUNDS

    ctx = RunContext(task_description)
    ctx.max_iterations = max_rounds
    if model:
        ctx.model_override = model
    if personality_prompt:
        ctx.personality_prompt = personality_prompt

    chain = build_default_chain()
    if agent:
        chain.bind_agent(agent)

    await chain.on_start(ctx)
    ctx._chain = chain

    # 获取前缀
    prefix = _get_prefix(agent)

    # ── 规划阶段：先制定计划，再执行 ──
    ctx.plan = await _generate_plan(task_description, ctx)
    if ctx.plan:
        _display_plan(ctx, prefix=prefix)
    else:
        print(f"{prefix}    \033[2;37m📋 无显式计划，自动按 ReAct 循环执行\033[0m")

    while not ctx.interrupted and ctx.react_depth < ctx.max_iterations:
        round_idx = ctx.react_depth + 1
        print(
            f"\n{prefix}    \033[1;37m━━━ 第 {round_idx}/{ctx.max_iterations} 轮 ━━━\033[0m"
        )

        # 显示计划进度
        if ctx.plan:
            _display_plan(ctx, prefix=prefix)

        # 全部步骤完成 → 结束
        if ctx.plan and all(s.status == "done" for s in ctx.plan):
            print(f"{prefix}    \033[1;32m✅ 所有计划步骤已完成\033[0m")
            ctx.interrupted = True
            break

        # 检测轮次上限：如果连续 K 轮没有推进计划，直接输出已有结果
        if ctx.react_depth >= 3 and ctx.plan:
            done_count = sum(1 for s in ctx.plan if s.status == "done")
            if done_count == 0 and ctx.react_depth >= 8:
                print(f"{prefix}    \033[1;33m⚠️ 多轮未见推进，提前结束\033[0m")
                ctx.interrupted = True
                break

        # 最后一轮提示
        if ctx.react_depth == ctx.max_iterations - 1:
            print(f"{prefix}    \033[1;31m⚠️ 最后轮次 — 直接输出最终答案\033[0m")
            ctx.task_description += (
                "\n\n[最后轮次] 本轮后结束。如果主要任务已经完成，直接输出结果。"
            )

        # 阶段1: on_think_start（深度检查/KEPA查询）
        hr_start = await chain.on_think_start(ctx)
        if hr_start and hr_start.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_start.reason or "中间件终止(think_start)"
            break
        if hr_start and hr_start.jump_to == "retry":
            continue

        # 阶段2: on_think_end（LLM思考 + 工具执行）
        hr_end = await chain.on_think_end(ctx)
        if hr_end and hr_end.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_end.reason or "中间件终止(think_end)"
            break

        # ── 更新计划步骤状态 ──
        if ctx.plan:
            _update_step_status(ctx)

        # 阶段3: on_tool_end（反思/KEPA决策）
        hr_tool = await chain.on_tool_end(ctx)
        if hr_tool and hr_tool.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_tool.reason or "中间件终止(tool_end)"
            break
        if hr_tool and hr_tool.jump_to == "retry":
            ctx.task_description += f"\n[重试] {hr_tool.reason}。"

            # 标记重试步骤为 failed，让下次循环检测并 re-plan
            for step in ctx.plan:
                if step.status == "running":
                    step.status = "failed"
                    ctx._step_retries[step.index] = (
                        ctx._step_retries.get(step.index, 0) + 1
                    )
            continue

    await chain.on_finish(ctx)

    # 兜底：有工具结果但无 final_answer 时让 LLM 总结
    if not ctx.final_answer and ctx.tool_results:
        outputs = []
        for tr in ctx.tool_results:
            tc = tr.get("tool_call", {})
            name = tc.get("name", "?")
            ok = tr.get("success", False)
            raw = tr.get("result", "")
            txt = ""
            if isinstance(raw, dict):
                c = raw.get("content")
                if isinstance(c, list) and c:
                    txt = (
                        str(c[0].get("text", ""))
                        if isinstance(c[0], dict)
                        else str(c[0])
                    )
                else:
                    txt = str(raw)
            else:
                txt = str(raw)
            txt = txt.strip()
            if ok and txt and txt != "None" and txt != "(无输出)":
                outputs.append(f"[{name}] {txt[:300]}")
        if outputs:
            summary = "\n\n".join(outputs[:3])
            from core.engine.llm_backend import get_llm_router

            router = get_llm_router()
            try:
                final_resp = await asyncio.wait_for(
                    router.chat(
                        [
                            {
                                "role": "system",
                                "content": "基于工具执行结果，用简洁的中文给出总结回答。直接输出结果，不要输出JSON。",
                            },
                            {
                                "role": "user",
                                "content": f"原始任务: {task_description}\n\n工具执行结果:\n{summary}\n\n请给出最终总结。",
                            },
                        ],
                        temperature=0.3,
                        max_tokens=2000,
                    ),
                    timeout=30,
                )
                text = str(final_resp) if final_resp else ""
                if text and text != "None" and len(text) > 20:
                    ctx.final_answer = text
            except Exception:
                pass
        if not ctx.final_answer:
            for last in reversed(ctx.tool_results):
                if last.get("success"):
                    raw = last.get("result", "")
                    txt = ""
                    if isinstance(raw, dict):
                        c = raw.get("content")
                        if isinstance(c, list) and c:
                            txt = (
                                str(c[0].get("text", ""))
                                if isinstance(c[0], dict)
                                else str(c[0])
                            )
                        else:
                            txt = str(raw)
                    else:
                        txt = str(raw)
                    txt = txt.strip()
                    if txt and txt != "None" and txt != "(无输出)":
                        ctx.final_answer = txt[:1000]
                        break

    return {
        "success": bool(ctx.final_answer),
        "answer": ctx.final_answer,
        "iterations": ctx.react_depth,
        "tool_results": ctx.tool_results,
        "error": ctx.last_error,
    }
