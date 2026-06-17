"""
ReActCore — V2 单 Agent 核心执行器（精简版）

基于 MiddlewareChain 的 ReAct 循环：
  LLM → Tool → Observation → 继续/结束

4层中间件链: [ReActDepth → ReActCore ★ → Reflection → KEPA]

拆分后的模块：
  - tool_evaluator: 工具结果评估与格式化
  - tool_parser: 工具调用解析
  - tool_executor: 工具执行与并行调度
  - file_validator: 文件内容检测与补全
  - plan_manager: 计划生成与Replan
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from .context_budget import ContextBudgetManager
from .middleware import BaseMiddleware, MiddlewareChain, PlanStep, RunContext

# 导入拆分后的模块
from .tool_evaluator import format_tool_result, get_error_suggestion
from .tool_parser import parse_tool_calls
from .tool_executor import (
    execute_tool_call,
    execute_tool_calls_parallel,
    lookup_server,
    TOOL_TIMEOUTS,
    DEFAULT_TIMEOUT,
)
from .file_validator import validate_file_content
from .plan_manager import (
    generate_plan,
    display_plan,
    steps_summary,
    update_step_status,
    replan_failed,
)

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 10

# ═══════════════════════════════════════════════════════════════════
# 提示词模块 — 按任务类型按需组装
# ═══════════════════════════════════════════════════════════════════

_BASE_PROMPT = (
    "先思考再行动：\n"
    "1. 任务目标是什么？当前进度在哪里？\n"
    "2. 需要工具就调用，有数据就回答，信息不够继续追问\n"
    "3. 不要输出思考过程描述，直接行动\n\n"
    "关键规则：\n"
    "- 每轮必须输出工具调用或最终答案，禁止空转\n"
    "- 如果任务明确，直接执行，不要描述'我将...'\n"
    "- 创建文件用 write_file 一次性写入完整代码\n"
    "- 修改代码用 edit_file（精确字符串替换）\n"
    "- 禁止输出被截断/不完整的代码"
)

_CODE_GEN_PROMPT = (
    "<code_generation_workflow>\n"
    "首次创建：用 write_file 一次性写入完整可运行的代码。\n"
    "修改/修复顺序：先 read_file 确认当前内容 → "
    "再用 edit_file(old_string, new_string) 精确替换（old_string 需提供足够上下文确保唯一匹配）\n"
    "质量要求：功能完整、无占位符/TODO、无语法错误。\n"
    "错误恢复：内容被截断 → 重新完整写入，不要留 '需要自行添加'。\n"
    "</code_generation_workflow>"
)

_GAME_DEV_PROMPT = (
    "<game_quality_requirements>\n"
    "1. 必须监听交互事件（keydown / click / touchstart）\n"
    "2. 必须有渲染/更新函数，状态变化后调用\n"
    "3. 必须有游戏状态变量\n"
    "4. 禁止静态展示 — 用户必须能操作，操作后界面更新\n"
    "5. 生成后自检：事件监听? 渲染函数? 状态变量? 可操作? 界面更新?\n"
    "</game_quality_requirements>"
)

_REPORT_PROMPT = (
    "<report_workflow>\n"
    "1. 先用 web_search/fetch_url 获取真实数据，禁止编造\n"
    "2. 用 write_file 生成 HTML 报告，嵌入真实数据\n"
    "3. 样式要求：渐变背景、卡片布局、响应式设计\n"
    "</report_workflow>"
)

_PLAN_PROMPT = (
    "【计划执行】严格按照计划顺序执行。不要重复已完成步骤，不要跳过当前步骤。"
)

_DEBUG_PROMPT = (
    "【错误恢复】内容不完整/被截断 → 重新完整写入。工具失败 → 换替代方式。"
    "不要留'需要自行添加'给用户。"
)


def _get_prefix(agent: Any = None) -> str:
    """获取Agent前缀标签"""
    if agent and hasattr(agent, "_agent_label"):
        label = agent._agent_label
        short_label = label[:15] if len(label) > 15 else label
        return f"[{short_label}] "
    if agent and hasattr(agent, "name"):
        return f"[{agent.name}] "
    return ""


class ReActCoreMiddleware(BaseMiddleware):
    """ReAct 核心循环：LLM 自主决定调工具还是直接回答"""

    def _get_prefix(self, ctx: RunContext) -> str:
        """从上下文获取Agent前缀"""
        if hasattr(ctx, "_chain") and ctx._chain and hasattr(ctx._chain, "_agent"):
            agent = ctx._chain._agent
            return _get_prefix(agent)
        return ""

    async def on_start(self, ctx: RunContext) -> None:
        """on_start 时发现全部工具并缓存，不做任务筛选"""
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry, _SANDBOX_TOOL_DEFS

        reg = get_tool_registry()
        
        try:
            await asyncio.wait_for(reg.discover_all(), timeout=15)
            ctx._tool_cache = list(reg._tools.values())
            n_builtin = sum(1 for t in ctx._tool_cache if t.server == "__builtin__")
            n_mcp = len(ctx._tool_cache) - n_builtin
            logger.info(f"工具发现完成: {len(ctx._tool_cache)} 个 ({n_builtin} 内置 + {n_mcp} MCP)")
        except asyncio.TimeoutError:
            discovered = list(reg._tools.values())
            if discovered:
                ctx._tool_cache = discovered
                logger.info(f"工具发现部分超时，使用已注册的 {len(ctx._tool_cache)} 个工具")
            else:
                ctx._tool_cache = list(_SANDBOX_TOOL_DEFS)
                logger.warning("工具发现完全超时，仅用内置工具")
        except Exception as e:
            ctx._tool_cache = list(_SANDBOX_TOOL_DEFS)
            logger.debug(f"工具发现异常: {e}")

    async def on_think_start(self, ctx: RunContext) -> None:
        """每轮 LLM 调用"""
        if ctx.interrupted or ctx.react_depth >= ctx.max_iterations:
            return

        # 防御：确保 task_description 是字符串
        if not isinstance(ctx.task_description, str):
            ctx.task_description = str(ctx.task_description) if ctx.task_description else ""

        from core.engine.llm_backend import get_llm_router

        router = get_llm_router()
        if not router.is_available():
            logger.error("❌ LLM 不可用")
            ctx.interrupted = True
            ctx.last_error = "LLM 不可用"
            return

        ctx.react_depth += 1
        ctx.iteration = ctx.react_depth

        # ── 任务感知工具筛选（首轮筛选后缓存复用）──
        tool_cache = getattr(ctx, '_tool_cache', None) or []
        if tool_cache:
            filtered = getattr(ctx, '_filtered_tools', None)
            if filtered is None:
                from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                reg = get_tool_registry()
                try:
                    filtered = await reg.get_tools_for_task(
                        ctx.task_description,
                        max_tools=20,
                        allowed=ctx.allowed_tools,
                        disallowed=ctx.disallowed_tools,
                    )
                except Exception:
                    filtered = tool_cache[:20]
                ctx._filtered_tools = filtered

            # 构建工具定义列表
            raw_defs = [
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
                for t in filtered
            ]

            # 模型感知 Schema 适配
            from core.multi_agent_v2.tools.schema import get_schema_adapter
            adapter = get_schema_adapter(ctx.model_override)
            ctx.tool_defs = adapter.adapt(raw_defs)
        else:
            ctx.tool_defs = None

        # 构建消息 — 注入计划进度让 agent 知晓已完成/未完成步骤
        plan_context = steps_summary(ctx) if ctx.plan else ""

        # ── 按任务类型组装提示词模块 ──
        task_lower = ctx.task_description.lower()
        modules = [_BASE_PROMPT]
        if any(kw in task_lower for kw in ["写", "创建", "代码", "文件", "html", "脚本", "game",
                                            "游戏", "生成", "编写", "编辑", "爬", "search"]):
            modules.append(_CODE_GEN_PROMPT)
            if any(kw in task_lower for kw in ["游戏", "game", "棋", "puzzle"]):
                modules.append(_GAME_DEV_PROMPT)
        if any(kw in task_lower for kw in ["报告", "热搜", "分析", "数据", "总结", "report", "dashboard"]):
            modules.append(_REPORT_PROMPT)
        if ctx.plan:
            modules.append(_PLAN_PROMPT)
        if ctx.forced_instructions or ctx.warnings:
            modules.append(_DEBUG_PROMPT)

        system_content = "\n\n".join(modules)

        # 注入强制指令（如：文件写入失败需要重试）
        if ctx.forced_instructions:
            system_content += f"\n\n<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>"
            ctx.forced_instructions = ""  # 用完清除
        
        # 注入警告信息（如：循环检测警告）
        if ctx.warnings:
            warnings_text = "\n".join(ctx.warnings)
            system_content += f"\n\n<warnings>\n{warnings_text}\n</warnings>"
            ctx.warnings.clear()  # 用完清除
        
        if ctx.personality_prompt:
            system_content = f"{ctx.personality_prompt}\n\n{system_content}"

        ctx._pending_messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": ctx.task_description},
        ]

        # ── 1. 动态上下文注入（保持 base prompt 静态用于缓存）──
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d, %A")

        dynamic_context = f"\n\n<system_context>\n<current_date>{current_date}</current_date>\n"
        if ctx.tool_results:
            total = len(ctx.tool_results)
            success = sum(1 for r in ctx.tool_results if r.get("success"))
            fail = total - success
            tools_used = list(set(r.get("tool_call", {}).get("name", "") for r in ctx.tool_results))
            dynamic_context += f"<execution_status>已执行{total}轮: {success}成功/{fail}失败, 工具: {', '.join(tools_used[:5])}</execution_status>\n"
        dynamic_context += "</system_context>"
        system_content += dynamic_context

        # ── 2. 构建 LLM 消息（含对话历史 + RAG 增强 + 个性化）──
        messages = ctx._pending_messages.copy()

        # 注入对话历史（让 LLM 看到之前的工具调用和结果）
        if ctx._conversation_history:
            messages.extend(ctx._conversation_history)

        # RAG 检索增强
        if ctx.react_depth <= 2:
            try:
                rag_results = await self._rag_query(ctx.task_description)
                if rag_results:
                    messages[0]["content"] += f"\n\n【知识库参考】\n{rag_results}"
            except Exception:
                pass

        if plan_context:
            messages[0]["content"] += plan_context

        # ── 3. 调用 LLM ──
        try:
            task = asyncio.create_task(router.chat(
                messages,
                temperature=0.7,
                max_tokens=16384,
                tools=ctx.tool_defs if ctx.tool_defs else None,
            ))
            try:
                reply = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise
            except Exception:
                if not task.done():
                    task.cancel()
                raise
            reply = str(reply) if reply else ""

            # DEBUG: see what DeepSeek actually returned
            reply_preview = reply[:500].replace("\n", "\\n")
            logger.info(f"LLM第{ctx.react_depth}轮回复({len(reply)}字符): {reply_preview}")
            ctx.knowledge_context += f"\nLLM第{ctx.react_depth}轮: {reply[:300]}"
            
            # 解析工具调用
            tool_calls = parse_tool_calls(reply)

            # 过滤：从 tool_defs 里排除掉的工具，解析出来的也不应该执行
            if tool_calls and ctx.tool_defs:
                valid_names = {t.get("function", {}).get("name", "") for t in ctx.tool_defs}
                tool_calls = [tc for tc in tool_calls
                              if tc.get("function", {}).get("name", "") in valid_names]

            if tool_calls:
                ctx._pending_tool_calls = tool_calls
                ctx._pending_reply = reply
            else:
                # 没有工具调用，可能是最终答案
                if len(reply) > 50 and not reply.startswith("{"):
                    ctx.final_answer = reply
                    ctx.interrupted = True
                ctx._pending_reply = reply
                
        except asyncio.TimeoutError:
            logger.warning(f"LLM 调用超时 (60s)")
            ctx.last_error = "LLM 调用超时"
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            ctx.last_error = f"LLM 调用失败: {e}"

    async def on_think_end(self, ctx: RunContext) -> None:
        """执行工具调用"""
        if not hasattr(ctx, '_pending_tool_calls') or not ctx._pending_tool_calls:
            return

        tool_calls = ctx._pending_tool_calls
        ctx._pending_tool_calls = None

        # ── 先累积 assistant 消息（含 tool_calls）到对话历史 ──
        # 顺序必须：assistant(tool_calls) → tool_result → tool_result → ...
        # 否则 DeepSeek 等 OpenAI 兼容 API 返回 400
        if tool_calls:
            _reply = (ctx._pending_reply or "").strip()
            _msg = {"role": "assistant", "content": _reply}
            _history_calls = []
            for _tc in tool_calls:
                _tc_id = _tc.get("id", f"call_{_tc.get('function', {}).get('name', '?')}_{ctx.react_depth}")
                _tc_fn = _tc.get("function", {})
                _history_calls.append({
                    "id": _tc_id,
                    "type": "function",
                    "function": {"name": _tc_fn.get("name", ""), "arguments": _tc_fn.get("arguments", "{}")},
                })
            if _history_calls:
                _msg["tool_calls"] = _history_calls
            ctx._conversation_history.append(_msg)

        prefix = self._get_prefix(ctx)

        # 执行工具调用
        if tool_calls:
            # 并行执行
            results = await execute_tool_calls_parallel(
                tool_calls,
                ctx=ctx,
                execute_fn=lambda tc, c: self._execute(tc, c),
                max_concurrent=ctx.max_concurrent_tools,
            )

            # 处理结果
            for tc, result in zip(tool_calls, results):
                tool_name = tc.get("function", {}).get("name", "")
                ok = result.get("success", False)
                
                # 格式化结果
                try:
                    arguments = json.loads(tc.get("function", {}).get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                
                result_text = format_tool_result(
                    tool_name,
                    result.get("result") if result.get("result") is not None else result,
                    ok,
                    arguments
                )
                from core.multi_agent_v2.agents.output_bounder import bound_tool_output
                result_text = bound_tool_output(tool_name, result_text)
                
                # 保存到上下文
                ctx.tool_results.append({
                    "tool_call": {"name": tool_name, "arguments": arguments},
                    "success": ok,
                    "result": result.get("result", {}),
                    "quality": result.get("quality", "unknown"),
                })

                # 打印结果
                status = "✅" if ok else "❌"
                print(f"{prefix}    {status} {tool_name} → {result_text[:200]}")

                # edit_file 额外显示 diff
                if ok and tool_name == "edit_file":
                    raw = result.get("result", {})
                    if isinstance(raw, dict):
                        diff = raw.get("diff", "")
                        if diff:
                            for line in diff.splitlines():
                                if line.startswith("+"):
                                    print(f"{prefix}      \033[32m{line}\033[0m")
                                elif line.startswith("-"):
                                    print(f"{prefix}      \033[31m{line}\033[0m")
                                elif line.startswith("@@"):
                                    print(f"{prefix}      \033[36m{line}\033[0m")

                # ── 累积 tool 结果到对话历史（紧跟在 assistant 消息之后）──
                _tool_id = tc.get("id", f"call_{tool_name}_{ctx.react_depth}")
                ctx._conversation_history.append({
                    "role": "tool",
                    "tool_call_id": _tool_id,
                    "content": result_text[:2000],
                    "name": tool_name,
                })

                # 文件验证（write_file 特殊处理）
                if ok and tool_name == "write_file":
                    path = arguments.get("path", "")
                    content = arguments.get("content", "")
                    if path and content:
                        expanded_path = os.path.expanduser(path)
                        try:
                            if os.path.exists(expanded_path):
                                with open(expanded_path, 'r', encoding='utf-8') as f:
                                    actual = f.read()
                            else:
                                actual = None
                        except Exception:
                            actual = None
                        warnings = validate_file_content(path, content, actual, ctx, agent=None)
                        qa_passed = not warnings  # 无警告 = 通过

                        # ── 迭代式质量改进：Write → Review → Improve ──
                        if qa_passed and not ctx.forced_instructions:
                            _iter_key = f"write_iter:{path}"
                            if not hasattr(ctx, '_file_iterations'):
                                ctx._file_iterations = {}
                            count = ctx._file_iterations.get(_iter_key, 0) + 1
                            ctx._file_iterations[_iter_key] = count

                            if count == 1:
                                ctx.forced_instructions = (
                                    f"【质量改进】文件 {path} 第一版已完成，内容正确。\n"
                                    "现在请执行质量管理流程：\n"
                                    "1. 先 read_file 读取你刚写入的文件\n"
                                    "2. 按以下标准逐项检查：\n"
                                    "   - 功能完整性：所有功能都已实现？有无 TODO/占位符？\n"
                                    "   - 交互性：有无事件监听(keydown/click)？操作后界面是否更新？\n"
                                    "   - 视觉质量：UI 是否美观？有无样式缺陷？\n"
                                    "3. 如果发现可改进项，用 edit_file 精确修改\n"
                                    "4. 如果已满意，直接输出最终结果"
                                )
                            elif count == 2:
                                ctx.forced_instructions = (
                                    f"【二次改进】文件 {path} 已改进过一次。\n"
                                    "请再审视一次代码质量：\n"
                                    "1. read_file 读取最新内容\n"
                                    "2. 检查：有无边界情况未处理？UX 是否流畅？\n"
                                    "3. 如需改进用 edit_file，满意则输出最终结果\n"
                                    "本轮是最后一次改进机会。"
                                )

    async def _execute(self, tc: dict, ctx: Optional[RunContext] = None) -> dict:
        """执行单个工具调用（委托给 tool_executor）"""
        return await execute_tool_call(
            tc,
            chain=ctx._chain if ctx else None,
            ctx=ctx,
            tool_defs=ctx.tool_defs if ctx else None,
        )

    async def _rag_query(self, query: str) -> str:
        """RAG 检索增强"""
        try:
            from core.search.rag_search_engine import RAGSearchEngine
            engine = RAGSearchEngine()
            result = await engine.search_and_learn(query, max_results=3, learn=False, use_query_cache=True)
            items = result.get("results", result.get("items", []))
            if items:
                return "\n".join(
                    f"- {r.get('content', r.get('text', ''))[:200]}"
                    for r in items if r
                )
        except Exception as e:
            logger.debug(f"RAG 检索失败: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════
# 链构建与运行
# ═══════════════════════════════════════════════════════════════════

def build_default_chain() -> MiddlewareChain:
    """构建默认中间件链"""
    chain = MiddlewareChain()
    from .middlewares import (
        ClarificationMiddleware,
        HookMiddleware,
        KEPAMiddleware,
        LoopDetectionMiddleware,
        PermissionMiddleware,
        ReActDepthMiddleware,
        ReflectionMiddleware,
        TruncationMiddleware,
        TodoMiddleware,
    )

    chain.add(TruncationMiddleware())
    chain.add(LoopDetectionMiddleware())
    chain.add(ClarificationMiddleware())
    chain.add(TodoMiddleware())
    chain.add(PermissionMiddleware())
    chain.add(HookMiddleware())
    chain.add(ReActDepthMiddleware())
    chain.add(ReActCoreMiddleware())
    chain.add(ReflectionMiddleware())
    chain.add(KEPAMiddleware())
    return chain


def build_configured_chain(
    loop_detection: bool = True,
    clarification: bool = True,
    todo: bool = True,
    permission: bool = True,
    hook: bool = True,
    depth_limit: bool = True,
    reflection: bool = True,
    kepa: bool = True,
    summarization: bool = True,
    loop_warn: int = 3,
    loop_hard: int = 5,
    depth_max: int = 30,
) -> MiddlewareChain:
    """可配置的中间件链构建器"""
    chain = MiddlewareChain()
    from .middlewares import (
        KEPAMiddleware,
        LoopDetectionMiddleware,
        ClarificationMiddleware,
        TodoMiddleware,
        PermissionMiddleware,
        HookMiddleware,
        ReActDepthMiddleware,
        ReflectionMiddleware,
        TruncationMiddleware,
    )

    if summarization:
        chain.add(TruncationMiddleware())
    if loop_detection:
        chain.add(LoopDetectionMiddleware(warn_threshold=loop_warn, hard_limit=loop_hard))
    if clarification:
        chain.add(ClarificationMiddleware())
    if todo:
        chain.add(TodoMiddleware())
    if permission:
        chain.add(PermissionMiddleware())
    if hook:
        chain.add(HookMiddleware())
    if depth_limit:
        mw = ReActDepthMiddleware()
        mw.MAX_DEPTH = depth_max
        chain.add(mw)
    chain.add(ReActCoreMiddleware())
    if reflection:
        chain.add(ReflectionMiddleware())
    if kepa:
        chain.add(KEPAMiddleware())
    return chain


async def run_react(
    task_description: str,
    max_rounds: int = 0,
    model: str = "",
    personality_prompt: str = "",
    agent: Any = None,
    allowed_tools: Optional[List[str]] = None,
    disallowed_tools: Optional[List[str]] = None,
) -> dict:
    """快捷入口：直接用 ReActCore 处理任务"""
    if max_rounds == 0:
        max_rounds = _MAX_ROUNDS

    ctx = RunContext(task_description)
    ctx.max_iterations = max_rounds
    if model:
        ctx.model_override = model
    if personality_prompt:
        ctx.personality_prompt = personality_prompt
    ctx.allowed_tools = allowed_tools
    ctx.disallowed_tools = disallowed_tools

    # 默认启用上下文预算管理
    ctx.context_budget = ContextBudgetManager()

    chain = build_default_chain()
    if agent:
        chain.bind_agent(agent)

    # 先设置 _chain，再执行 on_start（中间件可能需要访问 chain）
    ctx._chain = chain
    await chain.on_start(ctx)

    prefix = _get_prefix(agent)

    # ── 规划阶段 ──
    ctx.plan = await generate_plan(task_description, ctx)
    if ctx.plan:
        display_plan(ctx, prefix=prefix)
    else:
        print(f"{prefix}    \033[2;37m📋 无显式计划，自动按 ReAct 循环执行\033[0m")

    while not ctx.interrupted and ctx.react_depth < ctx.max_iterations:
        round_idx = ctx.react_depth + 1
        print(
            f"\n{prefix}    \033[1;37m━━━ 第 {round_idx}/{ctx.max_iterations} 轮 ━━━\033[0m"
        )

        if ctx.plan:
            display_plan(ctx, prefix=prefix)

        if ctx.plan and all(s.status == "done" for s in ctx.plan):
            if ctx.forced_instructions:
                print(f"{prefix}    \033[1;33m⚠️ 计划已完成但有未处理的指令，继续执行\033[0m")
            else:
                print(f"{prefix}    \033[1;32m✅ 所有计划步骤已完成\033[0m")
                ctx.interrupted = True
                break

        if ctx.react_depth >= 3 and ctx.plan:
            done_count = sum(1 for s in ctx.plan if s.status == "done")
            if done_count == 0 and ctx.react_depth >= 8:
                print(f"{prefix}    \033[1;33m⚠️ 多轮未见推进，提前结束\033[0m")
                ctx.interrupted = True
                break

        if ctx.react_depth == ctx.max_iterations - 1:
            print(f"{prefix}    \033[1;31m⚠️ 最后轮次 — 直接输出最终答案\033[0m")
            ctx.warnings.append("[最后轮次] 本轮后结束。如果主要任务已经完成，直接输出结果。")

        # ── 上下文预算检查（主动压缩）──
        if ctx.context_budget is not None:
            compacted = ctx.context_budget.check_and_compact(ctx)
            if compacted:
                print(f"{prefix}    \033[1;33m📦 上下文压缩: 释放了 tokens 预算\033[0m")

        hr_start = await chain.on_think_start(ctx)
        if hr_start and hr_start.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_start.reason or "中间件终止(think_start)"
            break
        if hr_start and hr_start.jump_to == "retry":
            continue

        hr_end = await chain.on_think_end(ctx)
        if hr_end and hr_end.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_end.reason or "中间件终止(think_end)"
            break

        if ctx.plan:
            update_step_status(ctx, prefix)
            failed_steps = [s for s in ctx.plan if s.status == "failed"]
            for step in failed_steps:
                retries = ctx._step_retries.get(step.index, 0)
                if retries < 2:
                    replanned = await replan_failed(ctx)
                    if replanned:
                        print(f"{prefix}    \033[1;33m🔄 步骤 {step.index} 失败，已重新规划\033[0m")
                        break

        hr_tool = await chain.on_tool_end(ctx)
        if hr_tool and hr_tool.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_tool.reason or "中间件终止(tool_end)"
            break
        if hr_tool and hr_tool.jump_to == "retry":
            ctx.warnings.append(f"[重试] {hr_tool.reason}。")
            for step in ctx.plan:
                if step.status == "running":
                    step.status = "failed"
                    ctx._step_retries[step.index] = ctx._step_retries.get(step.index, 0) + 1
            continue

    await chain.on_finish(ctx)

    # ── 搜索报告自动生成兜底 ──
    if not ctx.final_answer:
        _has_search_data = any(
            r.get("tool_call", {}).get("name") in ("web_search", "fetch_url", "fetch_json")
            and r.get("success")
            for r in ctx.tool_results
        )
        _has_report_file = any(
            r.get("tool_call", {}).get("name") == "write_file" and r.get("success")
            for r in ctx.tool_results
        )
        if _has_search_data and not _has_report_file:
            from core.multi_agent_v2.tools.tool_result import from_handler as _fmt_search
            _search_outputs = []
            for tr in ctx.tool_results:
                tc = tr.get("tool_call", {})
                name = tc.get("name", "?")
                if name in ("web_search", "fetch_url", "fetch_json") and tr.get("success"):
                    raw = tr.get("result", "")
                    txt = _fmt_search(raw)
                    if txt and txt != "None" and txt != "(无输出)":
                        _search_outputs.append(f"[{name}] {txt[:3000]}")
            if _search_outputs:
                print(f"{prefix}    \033[1;33m📝 有搜索数据未生成文件，自动生成 HTML 报告...\033[0m")
                _report_prompt = (
                    "基于以下搜索结果数据，生成一份完整的中文 HTML 分析报告。\n\n"
                    "要求：\n"
                    "- 完整的 <!DOCTYPE html> 格式，内嵌 CSS 样式\n"
                    "- 包含标题、发布日期、数据分类、趋势分析、总结\n"
                    "- 样式美观，背景用渐变色，字体优雅\n"
                    "- 所有内容用中文，数据逐条列出（禁止省略或截断）\n"
                    f"数据：\n{chr(10).join(_search_outputs[:3])}\n\n"
                    "直接输出完整的 HTML 代码，不要输出其他内容。"
                )
                try:
                    from core.engine.llm_backend import get_llm_router
                    _router = get_llm_router()
                    if _router and _router.is_available():
                        _html_resp = await asyncio.wait_for(
                            _router.chat(
                                [{"role": "user", "content": _report_prompt}],
                                temperature=0.3,
                                max_tokens=6000,
                            ),
                            timeout=60,
                        )
                        _html_text = str(_html_resp) if _html_resp else ""
                        if "```html" in _html_text:
                            _html_text = _html_text.split("```html")[1].split("```")[0]
                        elif "```" in _html_text:
                            _html_text = _html_text.split("```")[1].split("```")[0]
                        if "<!DOCTYPE html>" in _html_text or "<html" in _html_text:
                            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                            _reg = get_tool_registry()
                            _wf_handler = _reg.get_handler("write_file")
                            if _wf_handler:
                                _report_path = os.path.expanduser("~/Desktop/baidu_hot_search_report.html")
                                await _wf_handler({"path": _report_path, "content": _html_text})
                                print(f"{prefix}    \033[1;32m✅ 分析报告已生成: {_report_path}\033[0m")
                                ctx.final_answer = "✅ 分析报告已生成在桌面: baidu_hot_search_report.html"
                            else:
                                ctx.final_answer = _html_text[:2000]
                        elif _html_text:
                            ctx.final_answer = _html_text[:2000]
                except Exception as _e:
                    logger.debug(f"自动生成报告失败: {_e}")

    # 兜底：有工具结果但无 final_answer 时让 LLM 总结
    if not ctx.final_answer and ctx.tool_results:
        from core.multi_agent_v2.tools.tool_result import from_handler as _fmt_result
        outputs = []
        for tr in ctx.tool_results:
            tc = tr.get("tool_call", {})
            name = tc.get("name", "?")
            ok = tr.get("success", False)
            raw = tr.get("result", "")
            txt = _fmt_result(raw)
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
                            {"role": "system", "content": "基于工具执行结果，用简洁的中文给出总结回答。直接输出结果，不要输出JSON。"},
                            {"role": "user", "content": f"原始任务: {task_description}\n\n工具执行结果:\n{summary}\n\n请给出最终总结。"},
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
            from core.multi_agent_v2.tools.tool_result import from_handler as _fmt_result2
            for last in reversed(ctx.tool_results):
                if last.get("success"):
                    raw = last.get("result", "")
                    txt = _fmt_result2(raw)
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
