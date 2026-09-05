"""
ReActCore — V2 单 Agent 核心执行器（DEPRECATED）

⚠️  已废弃 — 请使用 core.multi_agent_v2.agents.unified_agent.run_unified()
    V1 架构已融入，提供 LeaderAgent + SubAgent 能力。

保留此文件用于:
  1. 向后兼容 (旧测试/旧 WorkAgent 代码可继续导入)
  2. run_unified(mode="react") 的回退路径

基于 MiddlewareChain 的 ReAct 循环：
  LLM → Tool → Observation → 继续/结束

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
import sys
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.agents.task_progress import TaskProgress
from core.multi_agent_v2.tools.json_util import safe_parse_json
from core.multi_agent_v2.prompts import get_builder

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
# 提示词模块 — 按任务类型按需组装（从 prompts/ .txt 文件加载）
# ═══════════════════════════════════════════════════════════════════

def _extract_text_from_json(s: str) -> str:
    """从带 tool_calls 的 JSON 回复中提取 content 文本"""
    try:
        obj = safe_parse_json(s)
        for c in obj.get("choices", []):
            msg = c.get("message", {})
            content = msg.get("content", "")
            if content:
                return content
    except (TypeError, KeyError, IndexError):
        pass
    return ""


def _get_prefix(agent: Any = None) -> str:
    """子代理显示简短灰色标签，主代理无前缀"""
    if agent and hasattr(agent, "_agent_label"):
        label = agent._agent_label
        short_label = label[:15] if len(label) > 15 else label
        return f"\033[2m[{short_label}]\033[0m "
    if agent and hasattr(agent, "name"):
        return f"\033[2m[{agent.name}]\033[0m "
    return ""

async def _ai_quality_check(content: str) -> str:
    """AI 质检 — 轻量 LLM 审查输出内容是否完整有效。返回空字符串表示 PASS。"""
    if not content or len(content) < 20:
        return "输出内容过短或为空"
    try:
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if not router or not router.is_available():
            return ""
        text = content[:3000]
        prompt = (
            "Review this output. Answer with one word: PASS if it's complete/valid output, "
            "or FAIL with a short reason if it's incomplete/placeholder/empty/only-tool-calls. "
            "Ignore minor formatting issues.\n\n"
            f"Output:\n{text}"
        )
        resp = await asyncio.wait_for(
            router.chat([{"role": "user", "content": prompt}], temperature=0, max_tokens=50),
            timeout=8.0,
        )
        result = str(resp).strip().upper() if resp else ""
        if result.startswith("PASS"):
            return ""
        return result[:80] if result else ""
    except Exception:
        return ""


def _check_deliverable_verified(ctx: RunContext, written_path: str) -> bool:
    """检测 agent 是否已观察/验证交付物（read_file 回读或执行它）。

    用于「observe 环节」：写完交付物后不能立即结束，必须先观察验证。
    """
    if not written_path:
        return True
    _exp = os.path.abspath(os.path.expanduser(written_path))
    for r in getattr(ctx, 'tool_results', []):
        tc = r.get("tool_call", {})
        name = tc.get("name", "")
        args = tc.get("arguments", {}) or {}
        if name == "read_file":
            p = args.get("path", args.get("filepath", ""))
            if p and os.path.abspath(os.path.expanduser(p)) == _exp:
                return True
        if name in ("execute_python", "execute_shell"):
            cmd = str(args.get("command", args.get("code", "")))
            if os.path.basename(_exp) in cmd or os.path.abspath(os.path.expanduser(cmd)) == _exp:
                return True
    return False


def _check_postcondition_exit_guard(ctx: RunContext) -> bool:
    """Plan 未完成时拦截退出，强制 LLM 执行剩余步骤

    Returns True if loop should continue (exit blocked), False if exit is OK.
    仅当 ctx.react_depth >= 3 且 ctx.final_answer 有值时触发检查。

    postcondition-aware：当前待执行步骤的后置条件已满足（file_exists/tool_called）
    或无后置条件时允许退出，避免在真实产出已达成时卡死循环。
    """
    if ctx.react_depth < 3 or not getattr(ctx, 'final_answer', None):
        return False
    if not ctx.plan:
        return False
    _done = sum(1 for s in ctx.plan if s.status == "done")
    if _done >= len(ctx.plan):
        return False

    # 当前待执行步骤
    _pending = ctx.plan[_done]

    # 无后置条件 → 不拦截（允许 LLM 直接产出并退出）
    if not _pending.postconditions:
        return False

    # 后置条件全部满足 → 允许退出
    _satisfied = True
    for cond in _pending.postconditions:
        if cond.startswith("file_exists:"):
            if not os.path.exists(os.path.expanduser(cond[12:])):
                _satisfied = False
                break
        elif cond.startswith("tool_called:"):
            _required = cond[12:]
            _called = any(
                r.get("tool_call", {}).get("name") == _required and r.get("success")
                for r in ctx.tool_results
            )
            if not _called:
                _satisfied = False
                break
    if _satisfied:
        return False

    # 计划未完成且后置条件未满足 → 拦截退出
    _tool = _pending.tool_names[0] if _pending.tool_names else "一个合适的工具"
    ctx.forced_instructions = (
        f"⚠️ 计划还有 {len(ctx.plan) - _done} 步未完成（共 {len(ctx.plan)} 步）。"
        f"当前：{_pending.description[:80]}"
        f" → 请立即调用 {_tool}，不要输出解释文本。"
    )
    ctx.final_answer = ""
    return True


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

    async def on_llm_invoke(self, ctx: RunContext) -> None:
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

        ctx.iteration = ctx.react_depth

        # ── 任务感知工具筛选（首轮筛选后缓存复用）──
        tool_cache = getattr(ctx, '_tool_cache', None) or []
        if tool_cache:
            filtered = getattr(ctx, '_filtered_tools', None)
            if filtered is None:
                from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                reg = get_tool_registry()
                try:
                    # 项目分析任务：不再限制工具，LLM 自主决定
                    # Phase 1+2 的数据已在 task_description 中提供
                    filtered = await reg.get_tools_for_task(
                        ctx.task_description,
                        max_tools=20,
                        allowed=ctx.allowed_tools,
                        disallowed=ctx.disallowed_tools,
                        tool_preference=ctx.tool_preference,
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
            # ponytail: 数据已获取 → 隐藏搜索工具，防重复
            if getattr(ctx, '_data_fetched', False) and ctx.tool_defs:
                _search_tools = {"web_search", "fetch_url", "fetch_json", "hot_search"}
                ctx.tool_defs = [t for t in ctx.tool_defs
                                 if t.get("function", {}).get("name") not in _search_tools]
        else:
            ctx.tool_defs = None

        if not ctx.tool_defs:
            logger.warning("⚠️ 无可用工具 — LLM 将无法调用工具，只能文字回复")
            if ctx.react_depth == 0:
                print(f"    \033[1;31m⚠️ 无可用工具，LLM 只能文字回复\033[0m")

        # 构建消息 — 注入计划进度让 agent 知晓已完成/未完成步骤
        plan_context = steps_summary(ctx) if ctx.plan else ""

        # ── LLM 任务分类：替代关键词匹配路由 ──
        _task_flags = getattr(ctx, '_task_flags', None)
        if _task_flags is None:
            _task_desc = (ctx.task_description or "")[:300]
            _task_flags = {"code": False, "game": False, "report": False, "project_analysis": False,
                           "desktop_save": False, "search": False, "file_operation": False, "edit": False}
            try:
                from core.engine.llm_backend import get_llm_router
                _router = get_llm_router()
                if _router and _router.is_available():
                    _resp = await _router.simple_chat(
                        "对以下请求，用逗号分隔输出8个数字（1=是，0=否）：\n"
                        "需要写代码/脚本/HTML？,需要开发游戏？,"
                        "需要生成报告/分析数据/查热搜？,需要分析项目结构/代码？,"
                        "需要在桌面保存/生成文件？,需要搜索网络/查百度/热搜？,"
                        "需要读写/操作文件？,需要替换/修改/编辑已有文件内容？\n请求：" + _task_desc,
                        temperature=0, max_tokens=32
                    )
                    _parts = str(_resp or "").strip().split(",")
                    if len(_parts) >= 8:
                        _task_flags = {
                            "code": _parts[0].strip() == "1",
                            "game": _parts[1].strip() == "1",
                            "report": _parts[2].strip() == "1",
                            "project_analysis": _parts[3].strip() == "1",
                            "desktop_save": _parts[4].strip() == "1",
                            "search": _parts[5].strip() == "1",
                            "file_operation": _parts[6].strip() == "1",
                            "edit": _parts[7].strip() == "1",
                        }
            except Exception:
                pass
            ctx._task_flags = _task_flags

        # Tool 过滤：桌面报告已就绪 → 隐藏 execute_python
        if _task_flags.get("desktop_save") and ctx.tool_defs:
            ctx.tool_defs = [t for t in ctx.tool_defs
                             if t.get("function", {}).get("name") != "execute_python"]

        # ── 按任务类型组装提示词模块 ──
        builder = get_builder()

        # ponytail: 角色 .md 定义优先于系统 base
        if getattr(ctx, 'personality_prompt'):
            modules = []
            if _task_flags.get("code"):
                modules.append("code_gen")
                if _task_flags.get("game"):
                    modules.append("game_dev")
            if _task_flags.get("report"):
                modules.append("report")
        else:
            modules = ["base"]
            if _task_flags.get("code"):
                modules.append("code_gen")
                if _task_flags.get("game"):
                    modules.append("game_dev")
            if _task_flags.get("report"):
                modules.append("report")

        # ponytail: task guidance now lives in tools/task.txt LLM gets it via tool definition
        # (no need to inject into system prompt separately)

        # ponytail: 工具连续失败 → 从 tool_defs 中移除，强制 LLM 换方案
        if ctx.tool_defs:
            _consecutive_fails = {}
            for r in (getattr(ctx, 'tool_results', []) or []):
                tn = r.get("tool_call", {}).get("name", "")
                if not r.get("success"):
                    _consecutive_fails[tn] = _consecutive_fails.get(tn, 0) + 1
                else:
                    _consecutive_fails.pop(tn, None)
            _dead_tools = {tn for tn, c in _consecutive_fails.items() if c >= 2}
            if _dead_tools:
                ctx.tool_defs = [t for t in ctx.tool_defs
                                  if t.get("function", {}).get("name") not in _dead_tools]
                logger.info(f"工具连续失败，已隐藏: {_dead_tools}")

        # ── 项目分析任务：更多轮次 ──
        if _task_flags.get("project_analysis"):
            ctx.max_iterations = max(ctx.max_iterations, 15)

        if ctx.plan:
            modules.append("plan")
        if ctx.forced_instructions or ctx.warnings:
            modules.append("debug")

        system_content = builder.assemble_system(modules)

        # ponytail: system architecture awareness block
        system_content += "\n\n" + builder.load("blocks/architecture")

        # ponytail: 注入项目根路径，防 LLM 路径幻觉
        import os as _os
        system_content += f"\n<project_root>{_os.getcwd()}</project_root>"

        # ponytail: 注入可用 skill 列表，LLM 按需调用 skill 工具加载
        try:
            from core.multi_agent_v2.skills.skill_loader import discover_skills, format_skills_xml
            _skills = discover_skills()
            if _skills:
                system_content += "\n" + format_skills_xml(_skills)
        except Exception:
            pass

        # 注入强制指令（如：文件写入失败需要重试）
        if ctx.forced_instructions:
            system_content += f"\n\n<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>"
            ctx._fi_consumed = True
        
        # 注入警告信息（如：循环检测警告）
        if ctx.warnings:
            warnings_text = "\n".join(ctx.warnings)
            system_content += f"\n\n<warnings>\n{warnings_text}\n</warnings>"
            ctx.warnings.clear()  # 用完清除
        
        if ctx.personality_prompt:
            system_content = f"{ctx.personality_prompt}\n\n{system_content}"

        # 用户消息：任务描述 + 记忆上下文 + 动态状态（与 system 分离，防截断影响角色定义）
        _user_content = ctx.task_description

        if ctx.knowledge_context:
            _user_content += f"\n\n── 上下文 ──\n{ctx.knowledge_context}\n──"

        # 动态上下文（执行状态 + 失败历史）
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d, %A")
        _user_content += f"\n\n<current_date>{current_date}</current_date>"
        if ctx.tool_results:
            total = len(ctx.tool_results)
            success = sum(1 for r in ctx.tool_results if r.get("success"))
            fail = total - success
            tools_used = list(set(r.get("tool_call", {}).get("name", "") for r in ctx.tool_results))
            _user_content += f"\n<execution_status>已执行{total}轮: {success}成功/{fail}失败, 工具: {', '.join(tools_used[:5])}</execution_status>"
        failed = getattr(ctx, '_failed_approaches', None)
        if failed:
            _user_content += "\n<failed_approaches>\n以下方案已经失败，不要重复尝试:"
            for fa in failed[-5:]:
                name = fa.get("tool", "?")
                args_summary = fa.get("args_summary", "")
                err = fa.get("error", "")[:100]
                _user_content += f"\n- {name}({args_summary}): {err}"
            _user_content += "\n</failed_approaches>"

        # ponytail: forced_instructions 也在 user message 前注入（LLM 更难忽略）
        if ctx.forced_instructions:
            _user_content = f"<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>\n\n{_user_content}"

        ctx._pending_messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": _user_content},
        ]

        # ── 2. 构建 LLM 消息（含对话历史 + RAG 增强 + 个性化）──
        messages = ctx._pending_messages.copy()

        # 注入对话历史（滑动窗口：最近 16 条全量，旧消息 LLM 摘要）
        if ctx._conversation_history:
            _MAX_WINDOW = 16
            _hist = ctx._conversation_history
            if len(_hist) > _MAX_WINDOW:
                _recent = _hist[-_MAX_WINDOW:]
                _old = _hist[:-_MAX_WINDOW]
                # 用 LLM 压缩旧消息为结构化摘要
                _summary = await self._summarize_history(_old)
                if _summary:
                    messages[0]["content"] += (
                        f"\n\n【历史摘要 — 以下 {len(_old)} 条消息已压缩】\n{_summary}"
                    )
                messages.extend(_recent)
            else:
                messages.extend(_hist)

        # RAG 检索增强
        if ctx.react_depth <= 2:
            try:
                rag_results = await self._rag_query(ctx.task_description)
                if rag_results:
                    messages[0]["content"] += f"\n\n【知识库参考】\n{rag_results}"
                    # ponytail: RAG → web_search 串行：先用知识库回答，再用联网补充最新信息
                    if _task_flags.get("search"):
                        messages[0]["content"] += "\n\n【搜索策略】知识库提供了基础信息，但对最新/未收录的内容可能不全。先用知识库回答主体，再用 web_search 补充最新数据和细节。禁止一轮就结束。"
            except Exception:
                pass

        if plan_context:
            messages[0]["content"] += plan_context

        # ── 3. 调用 LLM（最多 2 次，空转自动重试）──
        # 设置父代理状态（子代理生成时自动注入上下文）
        try:
            from .subagent.spawn import set_parent_state
            _conv_summary = ""
            if ctx._conversation_history:
                _recent = ctx._conversation_history[-6:]
                _conv_summary = "\n".join(
                    str(m.get("content", m.get("tool_call_id", "")))[:200]
                    for m in _recent
                )
            _tool_summary = ""
            if ctx.tool_results:
                _tool_summary = "\n".join(
                    f"[{r.get('tool_call', {}).get('name', '?')}]: "
                    f"{str(r.get('result', ''))[:200]}"
                    for r in ctx.tool_results[-3:]
                )
            _session_ad = ""
            try:
                from core.memory.session_manager import get_session_manager
                _ad_mgr = get_session_manager()
                _session_ad = _ad_mgr.artifacts_dir or ""
            except Exception:
                pass
            set_parent_state(
                task_description=ctx.task_description,
                conversation_summary=_conv_summary[:2000],
                tool_results_summary=_tool_summary[:3000],
                artifacts_dir=_session_ad,
            )
        except Exception:
            pass
        # ponytail: LLM 会在回复中输出 thinking 文本 + tool_calls，由 system prompt 引导
        _last_reply = ""
        _round_idle = True
        _has_successful_results = bool(ctx.tool_results and any(r.get("success") for r in ctx.tool_results))
        for _attempt in range(2):
            try:
                task = asyncio.create_task(router.chat_stream_compat(
                    messages,
                    temperature=0.7,
                    max_tokens=32768,
                    tools=ctx.tool_defs if ctx.tool_defs else None,
                ))
                try:
                    from cli.animated_spinner import shimmer_spinner
                    async with shimmer_spinner("Thinking…") as _shimmer:
                        # ponytail: 流式调用（token 逐个流出、连接持续活跃），
                        # 无动态超时收缩（deepseek-harness 原则：慢≠被杀）。
                        # 仅保留 300s 兜底防空连接挂死。
                        reply = await asyncio.wait_for(task, timeout=300)
                except asyncio.TimeoutError:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    raise
                except Exception as _inner_e:
                    _err_str = str(_inner_e).lower()
                    if "prompt_too_long" in _err_str or "too long" in _err_str or "413" in _err_str:
                        task.cancel()
                        try: await task
                        except asyncio.CancelledError: pass
                        # V1 ReactCompact: aggressive on-the-fly compaction
                        from core.memory.context_compactor import get_compactor
                        _compactor = get_compactor()
                        if ctx._conversation_history:
                            ctx._conversation_history = _compactor.handle_api_error(
                                ctx._conversation_history, _inner_e
                            )
                            messages = [{"role": "system", "content": ctx._pending_messages[0]["content"]},
                                        {"role": "user", "content": ctx.task_description}]
                            if ctx._conversation_history:
                                messages.extend(ctx._conversation_history)
                            logger.debug("V1 ReactCompact triggered for 413, retrying")
                            continue
                    if not task.done():
                        task.cancel()
                    raise
                reply = str(reply) if reply else ""
                is_truncated = getattr(reply, 'truncated', False) if hasattr(reply, 'truncated') else False

                # DEBUG: see what DeepSeek actually returned
                reply_preview = reply[:500].replace("\n", "\\n")
                logger.debug(f"LLM第{ctx.react_depth}轮回复({len(reply)}字符) truncated={is_truncated}")
                _ctx_text = reply if not reply.startswith("{") else _extract_text_from_json(reply) or reply[:200]
                ctx.knowledge_context += f"\nLLM第{ctx.react_depth}轮: {_ctx_text[:300]}"
                
                # 解析工具调用
                tool_calls = parse_tool_calls(reply)

                # ponytail: 截断且无tool_calls且无实质内容 → 注指令重试
                if is_truncated and not tool_calls and len(reply) < 50 and _attempt < 1:
                    ctx.forced_instructions = (
                        "你的上次回复被截断（输出token不够）。请简洁回答，"
                        "只输出最关键的结论或直接调用工具。不要输出冗长的前言或解释。"
                    )
                    logger.debug(f"第{ctx.react_depth}轮输出截断，注指令重试")
                    # 重建消息重试
                    _retry_sys = ctx._pending_messages[0]["content"]
                    _retry_sys += f"\n\n<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>"
                    messages = [{"role": "system", "content": _retry_sys},
                                {"role": "user", "content": ctx.task_description}]
                    if ctx._conversation_history:
                        messages.extend(ctx._conversation_history)
                    ctx.forced_instructions = ""
                    continue

                # 过滤：从 tool_defs 里排除掉的工具，解析出来的也不应该执行
                if tool_calls and ctx.tool_defs:
                    valid_names = {t.get("function", {}).get("name", "") for t in ctx.tool_defs}
                    tool_calls = [tc for tc in tool_calls
                                  if tc.get("function", {}).get("name", "") in valid_names]

                if tool_calls:
                    ctx._pending_tool_calls = tool_calls
                    ctx._pending_reply = reply
                    ctx.consecutive_idle_rounds = 0  # 有工具调用，重置空转计数
                    _round_idle = False
                    break  # 有工具调用 → 跳出重试循环

                # 没有工具调用 = 一次完成的轮次（deepseek-harness: no tool calls → completed）
                # 不强制重试；是否续轮由主循环的 goal-round 逻辑决策
                _last_reply = reply
                # ponytail: 从 JSON 响应中提取纯文本
                _plain = reply
                if _plain.startswith("{"):
                    _extracted = _extract_text_from_json(_plain)
                    if _extracted:
                        _plain = _extracted

                _plan_done = ctx.plan and all(s.status == "done" for s in ctx.plan)
                if _plan_done:
                    ctx.final_answer = _plain
                    ctx.interrupted = True
                    ctx.exit_reason = "plan_completed"
                    break
                # ponytail: 思考文本存入历史，续轮/兜底时可见（durable record）
                if _plain and len(_plain) > 20:
                    ctx._conversation_history.append({"role": "assistant", "content": _plain[:2000]})
            except asyncio.TimeoutError:
                logger.debug("LLM 调用超时 (60s)")
                ctx.last_error = "LLM 调用超时"
                ctx.exit_reason = "llm_timeout"
                ctx.interrupted = True
                break
            except Exception as e:
                logger.debug(f"LLM 调用失败: {e}")
                ctx.last_error = f"LLM 调用失败: {e}"
                ctx.exit_reason = "llm_error"
                ctx.interrupted = True
                break
        # ponytail: 文本轮次记账（deepseek-harness: 无工具调用=完成的轮次，
        # 是否续轮由主循环 goal-round 逻辑决策，这里只做记录，不强制不限制）
        if _round_idle:
            ctx.consecutive_idle_rounds = getattr(ctx, 'consecutive_idle_rounds', 0) + 1
            ctx._pending_reply = _last_reply
                
    async def on_tool_invoke(self, ctx: RunContext) -> None:
        """执行工具调用"""
        if not hasattr(ctx, '_pending_tool_calls') or not ctx._pending_tool_calls:
            return

        tool_calls = ctx._pending_tool_calls
        ctx._pending_tool_calls = None

        # 同轮内相同 (tool_name + 参数) 去重（必须在 assistant 消息构建前）
        if tool_calls:
            _seen = set()
            _unique = []
            for _tc in tool_calls:
                _fn = _tc.get("function", {})
                _args = _fn.get("arguments", {})
                if isinstance(_args, str):
                    try:
                        _args = json.loads(_args)
                    except (json.JSONDecodeError, TypeError):
                        _args = {}
                _key = (_fn.get("name", ""), json.dumps(_args, sort_keys=True))
                if _key not in _seen:
                    _seen.add(_key)
                    _unique.append(_tc)
            if len(_unique) < len(tool_calls):
                logger.debug(f"去重: {len(tool_calls)}→{len(_unique)} 个工具调用")
            tool_calls = _unique

        # ── 先累积 assistant 消息（含 tool_calls）到对话历史 ──
        # 顺序必须：assistant(tool_calls) → tool_result → tool_result → ...
        # 否则 DeepSeek 等 OpenAI 兼容 API 返回 400
        if tool_calls:
            _reply = (ctx._pending_reply or "").strip()
            # ponytail: 解析 JSON 格式回复，提取纯文本 + reasoning_content
            _reply_text = _reply
            _reasoning = ""
            if _reply.startswith("{"):
                _parsed = safe_parse_json(_reply)
                for _c in _parsed.get("choices", []):
                    _m = _c.get("message", {})
                    _reply_text = _m.get("content", "") or _reply_text
                    _reasoning = _m.get("reasoning_content", "") or ""
            _msg = {"role": "assistant", "content": _reply_text}
            if _reasoning:
                _msg["reasoning_content"] = _reasoning
            _history_calls = []
            for _tc in tool_calls:
                _tc_id = _tc.get("id", f"call_{_tc.get('function', {}).get('name', '?')}_{ctx.react_depth}")
                _tc_fn = _tc.get("function", {})
                _history_calls.append({
                    "id": _tc_id,
                    "type": "function",
                    "function": {
                        "name": _tc_fn.get("name", ""),
                        "arguments": json.dumps(_tc_fn.get("arguments", {}), ensure_ascii=False),
                    },
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
                arguments = safe_parse_json(tc.get("function", {}).get("arguments", ""))
                
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

                # ponytail: 记录失败方案，防止重复尝试
                if not ok and tool_name in ("execute_shell", "execute_python", "fetch_url", "write_file", "web_search"):
                    if not hasattr(ctx, '_failed_approaches'):
                        ctx._failed_approaches = []
                    _args_copy = {k: v for k, v in arguments.items() if k in ("command", "url", "mode")}
                    _args_summary = "; ".join(f"{k}={v}" for k, v in _args_copy.items())
                    _err_text = str(result.get("result", {}).get("error", "")) or str(result.get("result", ""))[:100]
                    ctx._failed_approaches.append({
                        "tool": tool_name,
                        "args_summary": _args_summary[:80],
                        "error": _err_text[:200],
                    })
                    if len(ctx._failed_approaches) > 50:
                        ctx._failed_approaches = ctx._failed_approaches[-50:]

                # ponytail: 成功获取数据后标记，防止重复搜索
                if ok and tool_name in ("fetch_url", "web_search", "hot_search"):
                    _raw = str(result.get("result", {}))
                    # 中文热搜 + 英文 trending/搜索结果均可触发
                    _data_keywords = (
                        "热搜", "热度:", "条热搜", "条/榜单",  # 中文
                        "trending", "stars", "fork", "repository",  # 英文 GitHub
                        "results", "search results",  # 通用搜索
                    )
                    if any(kw in _raw.lower() for kw in _data_keywords):
                        ctx._data_fetched = True
                        logger.info("数据已获取，后续将隐藏搜索工具防止重复")
                        # ponytail: 数据已就绪 → 强制 write_file 输出，防 LLM 画蛇添足调 execute_python
                        if not ctx.forced_instructions:
                            ctx.forced_instructions = (
                                "数据已获取完毕。直接用 write_file 在桌面生成报告，"
                                "不要再用 execute_python，不要再搜索。"
                            )

                # 打印结果 — 精致格式: ◆ tool  ·  context  ·  ✓/✗
                status = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
                _args_preview = ""
                if arguments:
                    _pairs = [f"{k}={str(v)[:30]}" for k, v in list(arguments.items())[:2]]
                    _args_preview = "  ·  " + ", ".join(_pairs)
                print(f"  \033[1;37m◆\033[0m \033[1m{tool_name}\033[0m{_args_preview}  ·  {status}")

                # edit_file 额外显示 diff
                if ok and tool_name == "edit_file":
                    raw = result.get("result", {})
                    if isinstance(raw, dict):
                        diff = raw.get("diff", "")
                        if diff:
                            for line in diff.splitlines():
                                if line.startswith("+"):
                                    print(f"    \033[32m{line}\033[0m")
                                elif line.startswith("-"):
                                    print(f"    \033[31m{line}\033[0m")
                                elif line.startswith("@@"):
                                    print(f"    \033[36m{line}\033[0m")

                # ── 累积 tool 结果到对话历史（紧跟在 assistant 消息之后）──
                _tool_id = tc.get("id", f"call_{tool_name}_{ctx.react_depth}")
                # 校验失败的结果不写入对话历史（已被 forced_instructions 处理，写进去只会污染）
                if result.get("_validation_error"):
                    continue
                # ponytail: task/orchestrate 结果可能极长，压缩到 1500 字避免撑爆上下文
                _tool_content = result_text
                if tool_name in ("task", "orchestrate"):
                    if len(_tool_content) > 1500:
                        _tool_content = _tool_content[:1500] + "\n...(子代理输出已截断，完整结果在之前的段落)"
                elif len(_tool_content) > 2000:
                    _tool_content = _tool_content[:2000]
                ctx._conversation_history.append({
                    "role": "tool",
                    "tool_call_id": _tool_id,
                    "content": _tool_content,
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

                        # ── 系统自动 observe：回读验证交付物，结果喂回 LLM ──
                        # 解决"写完交付物立即结束、无验证、observe 结果没回传"的问题
                        if actual is not None:
                            # 模板分段填充中的骨架（含 SECTION 占位）不算完成
                            _has_pending_sections = "<!-- section:" in actual.lower()
                            ctx._deliverable_verified = qa_passed and not _has_pending_sections
                            if _has_pending_sections:
                                _obs_note = (
                                    f"【系统观察】骨架已写入 {expanded_path}，"
                                    f"还有未填充的 SECTION 占位。请逐节 edit_file 填充（先 read_file 确认现状）。"
                                )
                            elif qa_passed:
                                _obs_note = (
                                    f"【系统观察】已回读验证交付物 {expanded_path}："
                                    f"文件存在，共 {len(actual)} 字节，结构/语法有效。"
                                )
                            else:
                                _obs_note = (
                                    f"【系统观察】回读 {expanded_path} 发现警告："
                                    f"{'; '.join(warnings)[:150]}。请修复后再完成。"
                                )
                            ctx._conversation_history.append({
                                "role": "tool",
                                "tool_call_id": f"observe:{path}",
                                "content": _obs_note,
                                "name": "observe",
                            })

                        # ── 迭代式质量改进：Write → Review → Improve ──
                        if qa_passed and not getattr(ctx, '_fi_consumed', False):
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

    async def _summarize_history(self, old_messages: list) -> str:
        """LLM 压缩旧消息为结构化摘要（OpenCode 风格）"""
        if not old_messages:
            return ""
        lines = []
        for m in old_messages[-20:]:
            role = m.get("role", "?")
            content = str(m.get("content", ""))[:150]
            if role == "tool":
                name = m.get("name", "?")
                lines.append(f"[{role}:{name}] {content}")
            elif role == "assistant":
                tc = m.get("tool_calls", [])
                tools = ",".join(t.get("function", {}).get("name", "") for t in tc[:3])
                lines.append(f"[{role}] called: {tools}")
            else:
                lines.append(f"[{role}] {content}")
        if not lines:
            return ""
        try:
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()
            if router and router.is_available():
                resp = await asyncio.wait_for(
                    router.simple_chat(
                        "将以下对话记录压缩为简短摘要（每个层级一行）：\n"
                        "1. 任务名称：用一句话概括要做什么\n"
                        "2. 关键操作：列出调用了哪些工具，做了什么\n"
                        "3. 产出结果：最终完成了什么或失败原因\n"
                        "4. 待办事项：还有什么没做\n\n"
                        + "\n".join(lines[:30]),
                        temperature=0.1,
                        max_tokens=200,
                    ),
                    timeout=8.0,
                )
                return str(resp).strip() if resp else ""
        except Exception:
            pass
        return "\n".join(lines[:8])


# ═══════════════════════════════════════════════════════════════════
# 链构建与运行
# ═══════════════════════════════════════════════════════════════════

def build_default_chain() -> MiddlewareChain:
    """构建默认中间件链"""
    chain = MiddlewareChain()
    from .memory_middleware import MemoryMiddleware
    from .middlewares import (
        ClarificationMiddleware,
        CompactionMiddleware,
        HookMiddleware,
        KEPAMiddleware,
        LoopDetectionMiddleware,
        PermissionMiddleware,
        QualityCheckMiddleware,
        ReActDepthMiddleware,
        ReasoningMiddleware,
        ReflectionMiddleware,
        TruncationMiddleware,
        TodoMiddleware,
    )
    chain.add(TodoMiddleware())
    chain.add(MemoryMiddleware())
    chain.add(CompactionMiddleware())
    chain.add(TruncationMiddleware())
    chain.add(LoopDetectionMiddleware())
    chain.add(ClarificationMiddleware())
    chain.add(ReasoningMiddleware())
    chain.add(PermissionMiddleware())
    chain.add(HookMiddleware())
    chain.add(ReActDepthMiddleware())
    chain.add(KEPAMiddleware())
    chain.add(ReActCoreMiddleware())
    chain.add(ReflectionMiddleware())
    return chain


def build_configured_chain(
    loop_detection: bool = True,
    clarification: bool = True,
    reasoning: bool = True,
    todo: bool = True,
    permission: bool = True,
    hook: bool = True,
    depth_limit: bool = True,
    reflection: bool = True,
    kepa: bool = True,
    summarization: bool = True,
    memory: bool = True,
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
        ReasoningMiddleware,
        TodoMiddleware,
        PermissionMiddleware,
        HookMiddleware,
        ReActDepthMiddleware,
        ReflectionMiddleware,
        TruncationMiddleware,
    )
    from .memory_middleware import MemoryMiddleware

    if todo:
        chain.add(TodoMiddleware())
    if memory:
        chain.add(MemoryMiddleware())
    if summarization:
        chain.add(TruncationMiddleware())
    if loop_detection:
        chain.add(LoopDetectionMiddleware(warn_threshold=loop_warn, hard_limit=loop_hard))
    if clarification:
        chain.add(ClarificationMiddleware())
    if reasoning:
        chain.add(ReasoningMiddleware())
    if permission:
        chain.add(PermissionMiddleware())
    if hook:
        chain.add(HookMiddleware())
    if depth_limit:
        mw = ReActDepthMiddleware()
        mw.MAX_DEPTH = depth_max
        chain.add(mw)
    if kepa:
        chain.add(KEPAMiddleware())
    chain.add(ReActCoreMiddleware())
    if reflection:
        chain.add(ReflectionMiddleware())
    return chain


async def run_react(
    task_description: str,
    max_rounds: int = 0,
    model: str = "",
    personality_prompt: str = "",
    agent: Any = None,
    allowed_tools: Optional[List[str]] = None,
    disallowed_tools: Optional[List[str]] = None,
    tool_preference: Optional[set] = None,
    is_subagent: bool = False,
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

    # ponytail: 不再对 "Phase 1 扫描" 做特殊限制，走通用 ReAct 流程
    ctx.allowed_tools = allowed_tools
    ctx.disallowed_tools = disallowed_tools
    if tool_preference:
        ctx.tool_preference = tool_preference
    ctx._is_subagent = is_subagent

    # 重置 read_file 重复计数器
    try:
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        _handle_read_file._read_count = {}
        _handle_read_file._unique_files = set()
    except Exception:
        pass

    # 默认启用上下文预算管理
    ctx.context_budget = ContextBudgetManager()

    chain = build_default_chain()
    if agent:
        chain.bind_agent(agent)

    # 先设置 _chain，再执行 on_start（中间件可能需要访问 chain）
    ctx._chain = chain
    await chain.on_start(ctx)

    # Session 初始化 — 将本轮对话的关键结果持久化为文件
    try:
        from core.memory.session_manager import get_session_manager
        _session_mgr = get_session_manager()
        _session_mgr.create_session(task_description)
    except Exception as e:
        logger.debug(f"Session init skipped: {e}")

    prefix = _get_prefix(agent)

    # ── 规划阶段 ──
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    ctx.plan = await generate_plan(task_description, ctx)
    if ctx.plan:
        display_plan(ctx, prefix=prefix)
    else:
        print(f"{prefix}    \033[2m◇ No plan generated\033[0m")

    # ponytail: TaskProgress 统一追踪，替代旧版 update_step_status
    ctx.task_progress = TaskProgress(ctx)
    if ctx.plan:
        ctx._progress_tool_snapshot = 0

    # 对话历史持久化：每轮保存。每个 run_react 用独立 session ID
    _sid = getattr(ctx, '_session_id', None) or os.urandom(6).hex()
    ctx._session_id = _sid
    _session_file = os.path.join(
        os.path.expanduser("~/.xiaolei/sessions"), f"{_sid}.json"
    )
    os.makedirs(os.path.dirname(_session_file), exist_ok=True)
    if os.path.exists(_session_file):
        try:
            with open(_session_file) as f:
                ctx._conversation_history = json.loads(f.read())
        except Exception:
            pass

    def _save_history():
        try:
            with open(_session_file, 'w') as f:
                json.dump(ctx._conversation_history[-30:], f, ensure_ascii=False)
        except Exception:
            pass

    while not ctx.interrupted and ctx.react_depth < ctx.max_iterations:
        round_idx = ctx.react_depth + 1
        if not prefix:
            bar = "─" * 30
            print(f"\n  \033[1;37m◇ \033[0m\033[2mRound {round_idx}/{ctx.max_iterations} {bar}\033[0m")

        if hasattr(ctx, '_fi_consumed'):
            delattr(ctx, '_fi_consumed')

        if ctx.plan:
            display_plan(ctx, prefix=prefix)

        if ctx.plan and all(s.status == "done" for s in ctx.plan):
            # 验证：任务要求产出文件时，必须有 file_written 能力
            _task = ctx.task_description or ""
            _need_output = any(kw in _task for kw in [
                "生成", "创建", "写", "保存", "输出", "报告", "文件",
                "create", "write", "generate", "save", "output", "report",
            ])
            _has_output = any(
                c.kind == "file_written"
                for c in getattr(ctx, 'task_progress', None) and ctx.task_progress.completed_capabilities or []
            )
            if _need_output and not _has_output:
                _last = ctx.plan[-1]
                _last.status = "pending"
                ctx.forced_instructions = (
                    f"⚠️ 所有步骤已标记完成，但实际没有创建任何文件！"
                    f"请立即 write_file 完成最终产出：{_last.description[:60]}"
                )
            else:
                # 写完交付物但还没 observe 验证 → 强制验证，不立即结束
                _written_path = next(
                    (c.metadata.get("path") for c in (ctx.task_progress.completed_capabilities if hasattr(ctx, 'task_progress') else [])
                     if c.kind == "file_written" and c.metadata.get("path")),
                    ""
                )
                if _has_output and not (getattr(ctx, '_deliverable_verified', False) or _check_deliverable_verified(ctx, _written_path)) and _written_path:
                    _v_attempts = getattr(ctx, '_deliverable_verify_attempts', 0) + 1
                    ctx._deliverable_verify_attempts = _v_attempts
                    if _v_attempts <= 3:
                        ctx.forced_instructions = (
                            f"⚠️ 交付物已写入：{_written_path}，但尚未验证。"
                            "请先 observe 验证再结束：\n"
                            f"1. read_file 读取 {_written_path} 检查内容完整性\n"
                            "2. 可运行的程序/游戏用 execute_python/execute_shell 运行验证\n"
                            "3. 确认无误后输出最终结果；有 bug 则用 edit_file 修复"
                        )
                        continue  # 继续循环让 agent 验证，不结束
                # 已验证 或 多次催验仍不验（≥3 次）→ 放行完成
                ctx.forced_instructions = ""
                print(f"{prefix}    \033[32m◇ All steps complete\033[0m")
                ctx.interrupted = True
                ctx.exit_reason = "plan_completed"
                break

        # ponytail: goal-round 续轮（deepseek-harness 原则1+2 的对齐实现）—
        # 上一轮是文本回复（无工具调用 = 完成的轮次）：
        #   目标已达成 → 该文本就是最终回答；目标未达成 → 注入续轮指令（inspect durable state），
        #   不强制、不硬限工具，agent 保持主动权；到 cap 由 round_limit blocker 收尾。
        if getattr(ctx, 'consecutive_idle_rounds', 0) > 0 and not getattr(ctx, 'final_answer', None):
            _reply_text = getattr(ctx, '_pending_reply', '') or ''
            if _reply_text.startswith('{'):
                _x = _extract_text_from_json(_reply_text)
                if _x:
                    _reply_text = _x
            _task = ctx.task_description or ""
            _is_production = any(kw in _task for kw in [
                "写", "创建", "生成", "报告", "文件", "保存", "输出",
                "write", "create", "generate", "save", "output", "report",
            ])
            _tp = getattr(ctx, 'task_progress', None)
            _deliverable_ok = getattr(ctx, '_deliverable_verified', False) or (
                _tp and any(c.kind == "file_written" for c in _tp.completed_capabilities)
            )
            if _is_production and not _deliverable_ok:
                # 目标未达成 → 续轮指令（goal-round 风格，durable state 为权威）
                _files = [
                    c.metadata.get("path") for c in (_tp.completed_capabilities if _tp else [])
                    if c.kind == "file_written" and c.metadata.get("path")
                ]
                _ndata = len(_tp.completed_capabilities) if _tp else 0
                _next_step = next((s.description[:60] for s in ctx.plan if s.status == "pending"), "") if ctx.plan else ""
                ctx.forced_instructions = (
                    f"<goal_round>\n"
                    f"Objective: {_task[:200]}\n"
                    f"Round: {ctx.react_depth + 1}/{ctx.max_iterations}\n\n"
                    f"Continue working toward the objective in this same session. Treat the current "
                    f"workspace, tool results, and durable session state as authoritative; inspect them "
                    f"instead of assuming earlier narration is still current. Current state:\n"
                    f"- 已写入文件: {', '.join(_files[:3]) or '无'}\n"
                    f"- 已收集数据: {_ndata} 项\n"
                    f"- 交付物尚未完成写入。\n"
                    + (f"- 当前步骤: {_next_step}\n" if _next_step else "")
                    + f"Make concrete progress and verify the result: 用 write_file 把交付物写入磁盘"
                    f"（大文件先写骨架再逐节 edit_file 填充）。完成后输出简短总结即可结束。\n"
                    f"</goal_round>"
                )
                logger.info(f"Goal-round continuation: deliverable missing, round {ctx.react_depth + 1}/{ctx.max_iterations}")
            else:
                # 目标已达成 或 非产出型任务 → 文本即最终回答（no tool calls = completed）
                if _reply_text and _reply_text.strip():
                    ctx.final_answer = _reply_text.strip()
                ctx.interrupted = True
                ctx.exit_reason = "completed_with_answer"
                break

        # ponytail: AI 质检 — 有 final_answer 且即将退出时，先审查质量
        _exiting_with_answer = (
            ctx.react_depth >= 3
            and getattr(ctx, 'final_answer', None)
            and not getattr(ctx, '_quality_checked', False)
        )
        if _exiting_with_answer:
            _feedback = await _ai_quality_check(ctx.final_answer)
            if _feedback:
                print(f"{prefix}    \033[1;33m◇ Quality: {_feedback}\033[0m")
                ctx.forced_instructions = (
                    f"⚠️ 质检未通过：{_feedback}。请立刻修正并输出完整有效内容。"
                )
                ctx.final_answer = ""
                ctx.interrupted = False
                ctx._quality_checked = True  # 只给一次修正机会
                continue

        # ponytail: 多轮无进展且有实质内容 → 中间退出，不浪费轮次
        if ctx.react_depth >= 3 and getattr(ctx, 'final_answer', None):
            if _check_postcondition_exit_guard(ctx):
                continue
            ctx.interrupted = True
            ctx.exit_reason = "completed_with_answer"
            break

        if ctx.react_depth >= 3 and ctx.plan:
            done_count = sum(1 for s in ctx.plan if s.status == "done")
            if done_count == 0 and ctx.react_depth >= 8:
                print(f"{prefix}    \033[31m◇ No progress after {ctx.react_depth} rounds\033[0m")
                ctx.interrupted = True
                ctx.exit_reason = "no_progress_8_rounds"
                break

        if ctx.react_depth == ctx.max_iterations - 1:
            print(f"{prefix}    \033[33m◇ Final round\033[0m")

        ctx.react_depth += 1
        hr_start = await chain.on_llm_invoke(ctx)
        if hr_start and hr_start.jump_to == "end":
            ctx.interrupted = True
            ctx.exit_reason = "middleware_kill_llm"
            ctx.last_error = hr_start.reason or "中间件终止(think_start)"
            break
        if hr_start and hr_start.jump_to == "retry":
            continue

        # ponytail: on_plan_check 补丁 — 启用循环检测+澄清中间件
        hr_plan = await chain.on_plan_check(ctx)
        if hr_plan and hr_plan.jump_to == "end":
            ctx.interrupted = True
            ctx.exit_reason = "middleware_kill_plan"
            ctx.last_error = hr_plan.reason or "中间件终止(plan_check)"
            break
        if hr_plan and hr_plan.jump_to == "retry":
            continue

        hr_end = await chain.on_tool_invoke(ctx)
        if hr_end and hr_end.jump_to == "end":
            ctx.interrupted = True
            ctx.exit_reason = "middleware_kill_tool"
            ctx.last_error = hr_end.reason or "中间件终止(think_end)"
            break

        # ponytail: TaskProgress — 统一能力追踪，替代旧版 update_step_status
        _tp = getattr(ctx, 'task_progress', None)
        if _tp is not None:
            ctx.task_progress.update()

            # ponytail: 产出催促 — 数据已收集足够但仍未写交付物 → 强制 write_file
            # 防止 agent 在"分析+报告"任务上反复跑代码/读文件却从不产出
            if ctx.plan:
                _pending = [s for s in ctx.plan if s.status == "pending"]
                if _pending:
                    _last = _pending[-1]
                    _is_produce = any(
                        kw in (_last.description or "").lower() for kw in
                        ["写", "报告", "文件", "生成", "输出", "产出", "编写",
                         "write", "report", "generate", "output", "save"]
                    )
                    _data_collected = sum(
                        1 for c in _tp.completed_capabilities
                        if c.kind in ("file_read", "web_search", "url_fetched", "code_executed", "tool_called")
                    )
                    _has_output = any(c.kind == "file_written" for c in _tp.completed_capabilities)
                    if _is_produce and _data_collected >= 3 and not _has_output:
                        # ponytail: 协作式提示（不硬限工具 — deepseek-harness 保持 agent 主动权）
                        ctx.forced_instructions = (
                            f"⚠️ 数据已收集足够（{_data_collected}项）。"
                            f"立即调用 write_file 生成完整交付物：{_last.description[:50]}。"
                            "不要再运行代码/读取/搜索了，直接写出完整内容！"
                        )

            # ponytail: 自适应重规划 — 卡住 5 轮后才重规划 (先让 forced_instructions 在 stuck>=4 有机会生效)
            if ctx.task_progress.stuck_counter >= 5 and ctx.plan:
                _pending = [s for s in ctx.plan if s.status == "pending"]
                if _pending:
                    replanned = await ctx.task_progress.adaptive_replan()
                    if replanned:
                        ctx.forced_instructions = ""
                        print(f"{prefix}    \033[33m◇ Replanned remaining steps\033[0m")
                        display_plan(ctx, prefix=prefix)

            # ponytail: 硬限制工具 — 卡住 3+ 轮后强制引导
            if ctx.task_progress.stuck_counter >= 3:
                _pending_steps = [s for s in ctx.plan if s.status == "pending"]
                if _pending_steps:
                    _step_desc = _pending_steps[0].description
                    _step_tool = _pending_steps[0].tool_names[0] if _pending_steps[0].tool_names else "write_file"
                    _searches = sum(1 for r in ctx.tool_results if r.get("tool_call",{}).get("name") in ("web_search","fetch_url","hot_search"))
                    _reads = sum(1 for r in ctx.tool_results if r.get("tool_call",{}).get("name") in ("read_file","search_files","codegraph_explore"))
                    _hint = ""
                    if _reads >= 5:
                        _hint = f"你已经读了{_reads}个文件，不要再读了！用 task(explore) 委托子代理探索，你自己只负责写输出。"
                    elif _searches >= 3:
                        _hint = f"你已经搜了{_searches}次，数据足够。立即调用 {_step_tool} 输出结果，不要再搜了。"
                    ctx.forced_instructions = (
                        f"⚠️ 连续 {ctx.task_progress.stuck_counter} 轮没有实质进展！"
                        f"{_hint}"
                        f"当前还需完成：{_step_desc}。"
                        f"请立即调用 {_step_tool} 输出结果，不要再搜索/阅读了。"
                    )
                    # ponytail: 卡了 6+ 轮 → 硬限制工具，只允许当前步骤需要的
                    if ctx.task_progress.stuck_counter >= 6:
                        _need = set(_pending_steps[0].tool_names) if _pending_steps[0].tool_names else {"write_file"}
                        _saved = getattr(ctx, '_allow_restore', ctx.allowed_tools)
                        if ctx.task_progress.stuck_counter == 6:  # first time hitting 6
                            ctx._allow_restore = ctx.allowed_tools
                        ctx.allowed_tools = list(_need)
                        ctx._filtered_tools = None
                        logger.info(f"Stuck {ctx.task_progress.stuck_counter} rounds, tools limited to {_need}")
            elif hasattr(ctx, '_allow_restore'):
                # stuck resolved → restore toolset
                ctx.allowed_tools = ctx._allow_restore
                ctx._allow_restore = None
                ctx._filtered_tools = None
        elif ctx.plan:
            # fallback: 没有 task_progress 时用旧版 update_step_status
            update_step_status(ctx, prefix)

            # 计划强制执行：当前步骤要求 task/orchestrate 但 LLM 绕路时强制引导
            _done_count = sum(1 for s in ctx.plan if s.status == "done")
            if _done_count < len(ctx.plan):
                _cur = ctx.plan[_done_count]
                if _cur.tool_names and {"task", "orchestrate"} & set(_cur.tool_names):
                    if ctx.react_depth >= 2 and not ctx.forced_instructions:
                        _recent_tools = set(
                            r.get("tool_call", {}).get("name", "")
                            for r in (ctx.tool_results or [])[-4:]
                        )
                        if not (_recent_tools & {"task", "orchestrate"}):
                            ctx.forced_instructions = (
                                f"⚠️ 当前步骤「{_cur.description}」要求使用 task 或 orchestrate，"
                                f"但你还没有调用。请立即调用 task 或 orchestrate 启动子代理，"
                                f"不要再自己逐个文件读了。"
                            )

            failed_steps = [s for s in ctx.plan if s.status == "failed"]
            for step in failed_steps:
                retries = ctx._step_retries.get(step.index, 0)
                if retries < 2:
                    replanned = await replan_failed(ctx)
                    if replanned:
                        print(f"{prefix}    \033[33m◇ \033[0m\033[2mStep {step.index} failed, replanning\033[0m")
                        break

        # ponytail: 交付物观察/验证 — 写完交付物后不能立即结束，必须先 observe 验证
        # 解决"agent 写完文件就跳过验证"的问题；observe 结果会回传 LLM 供自我修正
        if ctx.plan and not ctx.interrupted:
            _tp = getattr(ctx, 'task_progress', None)
            _has_output = any(
                c.kind == "file_written"
                for c in (_tp.completed_capabilities if _tp else [])
            )
            _pending = [s for s in ctx.plan if s.status == "pending"]
            _remaining_need_output = any(
                s.tool_names and set(s.tool_names) & {"write_file", "edit_file"}
                for s in _pending
            ) if _pending else False
            _task = ctx.task_description or ""
            _is_production = any(kw in _task for kw in [
                "写", "创建", "生成", "报告", "文件", "保存", "输出",
                "write", "create", "generate", "save", "output", "report",
            ])
            if _has_output and _is_production and not _remaining_need_output:
                _written_path = next(
                    (c.metadata.get("path") for c in (_tp.completed_capabilities if _tp else [])
                     if c.kind == "file_written" and c.metadata.get("path")),
                    ""
                )
                # 已验证 = 系统回读确认(_deliverable_verified) 或 agent 主动 read_file/运行
                if getattr(ctx, '_deliverable_verified', False) or _check_deliverable_verified(ctx, _written_path):
                    # 已验证 → 允许完成
                    if not getattr(ctx, 'final_answer', None):
                        ctx.final_answer = (
                            f"✅ 任务已完成，产出已写入：{os.path.expanduser(_written_path)}"
                            if _written_path else "✅ 任务已完成。"
                        )
                    print(f"{prefix}    \033[32m◇ \033[0m\033[2mDeliverable verified, finalizing\033[0m")
                    ctx.interrupted = True
                    ctx.exit_reason = "deliverable_complete"
                    break
                else:
                    # 未验证 → 触发观察指令（不立即结束），并回传观察结果给 LLM
                    if _written_path:
                        ctx._deliverable_verify_attempts = getattr(ctx, '_deliverable_verify_attempts', 0) + 1
                        if ctx._deliverable_verify_attempts <= 3:
                            ctx.forced_instructions = (
                                f"⚠️ 你已写入交付物：{_written_path}。"
                                "请先观察/验证它，不要立即结束：\n"
                                f"1. 立即 read_file 读取 {_written_path}，检查内容是否完整正确\n"
                                "2. 若为可运行的程序/游戏，用 execute_python/execute_shell 运行它验证\n"
                                "3. 确认无误后输出最终结果；若发现 bug，用 edit_file 修复后再输出"
                            )

        hr_tool = await chain.on_tool_end(ctx)
        if hr_tool and hr_tool.jump_to == "end":
            # 循环检测 → 询问用户如何恢复
            if getattr(ctx, 'needs_user_intervention', False) and sys.stdin.isatty():
                _tool_name = ctx.last_error.split("工具 ")[1].split(" 已调用")[0] if "工具 " in ctx.last_error else ""
                _hard = int(ctx.last_error.split("阈值=")[1].split(")")[0]) if "阈值=" in ctx.last_error else 8
                print(f"\n  \033[1;33m⚠️  {ctx.last_error}\033[0m")
                print(f"  \033[2m如何处理？\033[0m")
                print(f"  \033[1;37m[1]\033[0m 继续执行 — 本次提高 {_tool_name} 上限到 {_hard * 3}")
                print(f"  \033[1;37m[2]\033[0m 跳过搜索，用已有数据直接生成报告")
                print(f"  \033[1;37m[3]\033[0m 中止任务")
                try:
                    _choice = input("  \033[1;36m›\033[0m ").strip()
                except (EOFError, KeyboardInterrupt):
                    _choice = "3"
                if _choice == "1":
                    ctx.interrupted = False
                    ctx.needs_user_intervention = False
                    ctx.last_error = ""
                    for _mw in ctx._chain._middlewares:
                        if hasattr(_mw, 'TOOL_FREQ_LIMITS') and _tool_name in _mw.TOOL_FREQ_LIMITS:
                            _mw.TOOL_FREQ_LIMITS[_tool_name]["hard"] = _hard * 3
                        if hasattr(_mw, '_tool_freq'):
                            _mw._tool_freq = {}
                    print(f"  \033[32m✓\033[0m {_tool_name} 上限已提高到 {_hard * 3}，继续执行...")
                    ctx._consecutive_idle_rounds = 0
                    ctx._consecutive_empty_run_rounds = 0
                    ctx._conversation_history = ctx._conversation_history[:-1] if ctx._conversation_history else []
                    continue
                elif _choice == "2":
                    print(f"  \033[33m→\033[0m 跳过搜索阶段，用现有数据生成报告...")
                    ctx.needs_user_intervention = False
                    ctx.interrupted = False
                    ctx.last_error = ""
                    break
                else:
                    print(f"  \033[31m→\033[0m 任务已中止")
                    ctx.last_error = "用户中止"
                    ctx.exit_reason = "user_aborted"
                    break
                break
            ctx.interrupted = True
            ctx.exit_reason = "loop_detected"
            ctx.last_error = ctx.last_error or hr_tool.reason or "中间件终止(tool_end)"
            break
        if hr_tool and hr_tool.jump_to == "retry":
            ctx.warnings.append(f"[重试] {hr_tool.reason}。")
            if ctx.plan:
                for step in ctx.plan:
                    if step.status == "running":
                        step.status = "failed"
                        ctx._step_retries[step.index] = ctx._step_retries.get(step.index, 0) + 1
            continue

    # ── 搜索报告自动生成兜底 ──
    _save_history()
    # ponytail: blocker 语义 — 轮次耗尽时收尾必须可诊断（对齐 goal-round-driver 的 round-limit）
    _round_limit_hit = (
        not ctx.interrupted
        and ctx.react_depth >= ctx.max_iterations
        and not getattr(ctx, 'exit_reason', '')
    )
    if _round_limit_hit:
        ctx.exit_reason = "round_limit"
        _done_steps = sum(1 for s in ctx.plan if s.status == "done") if ctx.plan else 0
        _total_steps = len(ctx.plan) if ctx.plan else 0
        _last_pending = next((s.description[:50] for s in ctx.plan if s.status == "pending"), "") if ctx.plan else ""
        ctx.warnings.append(
            f"[round-limit] 已达轮次上限（{ctx.max_iterations}轮）。"
            f"进度：{_done_steps}/{_total_steps} 步。"
            f"未完成：{_last_pending or '最终收尾'}。"
        )
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

            # ponytail: agent 已把完整 HTML 报告当文本输出 → 直接落盘，不重新生成
            _agent_html = (getattr(ctx, '_pending_reply', '') or '').lstrip()
            if _agent_html.startswith('{'):
                _extracted = _extract_text_from_json(_agent_html)
                if _extracted:
                    _agent_html = _extracted.lstrip()
            if _agent_html.startswith(('<!DOCTYPE', '<!doctype', '<html')):
                # 剥离可能的 markdown 代码栏
                if "```html" in _agent_html:
                    _agent_html = _agent_html.split("```html")[1].split("```")[0]
                elif "```" in _agent_html:
                    _agent_html = _agent_html.split("```")[1].split("```")[0]
                if len(_agent_html) > 1000 and ("</html>" in _agent_html.lower()):
                    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                    _reg = get_tool_registry()
                    _wf_handler = _reg.get_handler("write_file")
                    if _wf_handler:
                        _task_hint = (ctx.task_description or "")[:60]
                        _safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in _task_hint).strip().replace(" ", "_")[:40] or "report"
                        _report_path = os.path.expanduser(f"~/Desktop/{_safe_name}.html")
                        await _wf_handler({"path": _report_path, "content": _agent_html})
                        print(f"{prefix}    \033[32m◇ \033[0m\033[2mSaved agent output: \033[0m{_report_path}")
                        ctx.final_answer = f"✅ 分析报告已生成在桌面: {_safe_name}.html"

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
                print(f"{prefix}    \033[1;37m◇ \033[0m\033[2mGenerating report...\033[0m")
                _report_prompt = (
                    "基于以下搜索结果数据，生成一份完整的中文 HTML 分析报告。\n\n"
                    "要求：\n"
                    "- 完整的 <!DOCTYPE html> 格式，内嵌 CSS 样式\n"
                    "- 包含标题、发布日期、数据分类、趋势分析、总结\n"
                    "- 样式美观，背景用渐变色，字体优雅\n"
                    "- 所有内容用中文，数据逐条列出（禁止省略或截断）\n"
                    "- 保持精炼：总长度控制在 6KB 以内，避免冗余装饰\n"
                    f"数据：\n{chr(10).join(_search_outputs[:3])}\n\n"
                    "直接输出完整的 HTML 代码，不要输出其他内容。"
                )
                try:
                    from core.engine.llm_backend import get_llm_router
                    _router = get_llm_router()
                    if _router and _router.is_available():
                        from cli.animated_spinner import shimmer_spinner
                        async with shimmer_spinner("Generating report…"):
                            _html_resp = await asyncio.wait_for(
                                _router.chat(
                                    [{"role": "user", "content": _report_prompt}],
                                    temperature=0.3,
                                    max_tokens=8000,
                                ),
                                timeout=90,
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
                                # 根据任务描述动态生成文件名
                                _task_hint = (ctx.task_description or "")[:60]
                                _safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in _task_hint).strip().replace(" ", "_")[:40]
                                if not _safe_name:
                                    _safe_name = "report"
                                _report_path = os.path.expanduser(f"~/Desktop/{_safe_name}.html")
                                await _wf_handler({"path": _report_path, "content": _html_text})
                                print(f"{prefix}    \033[32m◇ \033[0m\033[2mReport: \033[0m{_report_path}")
                                ctx.final_answer = f"✅ 分析报告已生成在桌面: {_safe_name}.html"
                            else:
                                ctx.final_answer = _html_text
                        elif _html_text:
                            ctx.final_answer = _html_text
                except Exception as _e:
                    logger.debug(f"自动生成报告失败: {_e}")

    # 兜底：无 final_answer 时从最近回复提取（不限 tool_results 有无）
    if not ctx.final_answer:
        _last_reply = getattr(ctx, '_pending_reply', '') or ''
        if _last_reply.startswith('{'):
            extracted = _extract_text_from_json(_last_reply)
            if extracted:
                _last_reply = extracted
        if _last_reply and len(_last_reply) > 20:
            ctx.final_answer = _last_reply

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
                # ponytail: 优先保留 task/orchestrate 的子代理结果，其次按顺序
                _excerpt = txt[:2000] if name in ("task", "orchestrate") else txt[:500]
                outputs.append(f"[{name}] {_excerpt}")
        if outputs:
            # ponytail: 子代理结果优先，其余按时间顺序，最多 8 条
            _subagent = [o for o in outputs if o.startswith("[task]") or o.startswith("[orchestrate]")]
            _others = [o for o in outputs if o not in _subagent]
            _selected = (_subagent + _others)[:8]
            summary = "\n\n".join(_selected)
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()
            try:
                from cli.animated_spinner import shimmer_spinner
                async with shimmer_spinner("Summarizing…"):
                    final_resp = await asyncio.wait_for(
                        router.chat(
                            [
                                {"role": "system", "content": "基于工具执行结果，用完整详细的中文给出总结回答。覆盖项目概况、技术栈、目录结构、关键发现。直接输出结果，不要输出JSON。"},
                                {"role": "user", "content": f"原始任务: {task_description[:500]}\n\n工具执行结果:\n{summary}\n\n请给出最终总结。"},
                            ],
                            temperature=0.3,
                            max_tokens=32768,
                        ),
                        timeout=30,
                    )
                text = str(final_resp) if final_resp else ""
                if text.startswith("{"):
                    extracted = _extract_text_from_json(text)
                    if extracted:
                        text = extracted
                if text and text != "None" and len(text) > 20:
                    ctx.final_answer = text
            except Exception:
                pass
        # 兜底：纯文本提取最后的成功工具结果
        if not ctx.final_answer:
            from core.multi_agent_v2.tools.tool_result import from_handler as _fmt_result2
            for last in reversed(ctx.tool_results):
                if last.get("success"):
                    raw = last.get("result", "")
                    txt = _fmt_result2(raw)
                    if txt and txt != "None" and txt != "(无输出)":
                        ctx.final_answer = txt
                        break

    # 持久化对话记录到 session artifact
    if ctx._conversation_history and not ctx._is_subagent:
        try:
            from core.memory.session_manager import get_session_manager
            _sm = get_session_manager()
            _conv_text = "\n\n".join(
                f"[{m.get('role','?')}] {str(m.get('content',''))[:500]}"
                for m in ctx._conversation_history[-30:]  # 最近30轮
            )
            if _conv_text:
                _sm.record_artifact("conversation_log", f"# Conversation Log\n\n{_conv_text}")
        except Exception:
            pass

    # ponytail: final_answer 自动保存到桌面（>=50字），仅主代理写入，子代理不污染
    if ctx.final_answer and len(ctx.final_answer) >= 50 and not ctx._is_subagent:
        _path = os.path.expanduser("~/Desktop/v2_result.txt")
        try:
            with open(_path, "w", encoding="utf-8") as _f:
                _f.write(ctx.final_answer)
            print(f"    \033[32m◇ \033[0m\033[2mSaved result to \033[0m{_path}")
        except Exception:
            pass

    # ponytail: 已有 final_answer 但 plan 还显示 pending → 兜底补齐。
    # BUT: file_written(path=...) steps must verify the file exists on disk.
    if ctx.final_answer and ctx.plan:
        for step in ctx.plan:
            if step.status != "pending":
                continue
            _can_advance = True
            for cond in step.postconditions:
                if cond.startswith("capability:file_written(path="):
                    _path = cond[len("capability:file_written(path="):].rstrip(")")
                    if not os.path.exists(os.path.expanduser(_path)):
                        _can_advance = False
                        break
            if _can_advance:
                step.status = "done"

    # ponytail: on_finish 必须在兜底之后调用，确保 final_answer 非空时写入记忆
    await chain.on_finish(ctx)

    # ponytail: round_limit → final_answer 附带 blocker 说明，可诊断而非静默
    if _round_limit_hit:
        _blocker = next((w for w in ctx.warnings if w.startswith("[round-limit]")), "")
        if _blocker and ctx.final_answer and _blocker not in ctx.final_answer:
            ctx.final_answer = f"{ctx.final_answer}\n\n{_blocker}"

    return {
        "success": bool(ctx.final_answer),
        "answer": ctx.final_answer,
        "iterations": ctx.react_depth,
        "tool_results": ctx.tool_results,
        "exit_reason": getattr(ctx, 'exit_reason', 'completed_with_answer' if ctx.final_answer else 'no_progress_8_rounds'),
        "diagnostic": ctx.last_error or "",
        "error": ctx.last_error or "",
    }


