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

_PROJECT_ANALYSIS_PROMPT = (
    "<project_analysis_protocol>\n"
    "你正在深度分析一个项目。\n\n"
    "【已提供的数据】\n"
    "- 项目结构概览：文件树、技术栈、依赖、git 统计、import 关系\n"
    "- 核心代码：选中的关键文件的头部（声明/import）和尾部（调用/main）\n\n"
    "【重要规则 — 违反以下规则将浪费时间】\n"
    "- 禁止在首轮调用任何工具（read_file / search_code / execute_shell 等）\n"
     "   → 首轮必须直接输出分析报告。所有数据已在上面「----」下方的代码区提供。\n"
    "- 禁止对已提供的文件调用 read_file → 工具会返回 [CACHED] 拒绝，浪费一轮\n"
    "- 禁止调用 execute_shell / search_files 重新扫描目录 → 文件树已在结构概览中\n"
    "- 只有在你确认某个核心文件的正文未提供且分析需要时，才从第 2 轮开始补充读\n\n"
    "【任务】\n"
    "基于已提供的数据输出完整的分析报告，覆盖以下维度：\n"
    "   - 项目概览（语言、框架、构建工具、依赖）\n"
    "   - 目录结构与各模块职责\n"
    "   - 核心技术栈分析\n"
    "   - 架构设计与分层\n"
    "   - 数据流与核心链路（入口 → 处理 → 输出）\n"
    "   - 关键模块的实现分析\n"
    "   - 错误处理与边界情况\n"
    "   - 代码质量评估\n"
    "   - 改进建议\n\n"
    "分析结构建议：先宏观（概览、架构）再微观（模块细节），最后总结建议。\n"
    "如果需要补充阅读（仅适用于未提供的文件），可以用 read_file 或 search_code。\n"
    "</project_analysis_protocol>"
)


def _trim_desc(desc: str) -> str:
    """保留任务描述开头（用户请求）和 Phase 1 关键数据（前 1500 字）"""
    idx = desc.find("\n===== 项目结构概览")
    if idx == -1:
        idx = desc.find("Phase 1 扫描")
    if idx > 0:
        head = desc[:idx].strip()[:200]
        phase = desc[idx:idx + 3000]  # 保留 Phase 1 前 3000 字
        return head + "\n\n" + phase
    return desc[:500]


def _filter_scan_tools(tool_defs: list) -> list:
    """Phase 1 数据就绪时移除目录扫描工具，只保留写报告工具"""
    _scan_tools = {"execute_shell", "read_file", "search_files", "grep"}
    return [t for t in tool_defs
            if t.get("function", {}).get("name") not in _scan_tools]


def _extract_text_from_json(s: str) -> str:
    """从带 tool_calls 的 JSON 回复中提取 content 文本"""
    try:
        obj = json.loads(s)
        for c in obj.get("choices", []):
            msg = c.get("message", {})
            content = msg.get("content", "")
            if content:
                return content
    except (json.JSONDecodeError, TypeError, KeyError, IndexError):
        pass
    return ""


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
            # ponytail: Phase 1 数据已就绪 → 屏蔽扫描工具，防 LLM 重新扫描目录
            if getattr(ctx, '_has_structure_data', False) and ctx.tool_defs:
                ctx.tool_defs = _filter_scan_tools(ctx.tool_defs)
        else:
            ctx.tool_defs = None

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
        modules = [_BASE_PROMPT]
        if _task_flags.get("code"):
            modules.append(_CODE_GEN_PROMPT)
            if _task_flags.get("game"):
                modules.append(_GAME_DEV_PROMPT)
        if _task_flags.get("report"):
            modules.append(_REPORT_PROMPT)

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

        # ── 项目分析任务：插入分析 prompt + 跳过冗余计划 ──
        if _task_flags.get("project_analysis"):
            modules.insert(1, _PROJECT_ANALYSIS_PROMPT)
            ctx.max_iterations = max(ctx.max_iterations, 15)
            ctx._skip_plan = True

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

        # 注入记忆上下文（MemoryMiddleware 写到 knowledge_context）
        if ctx.knowledge_context:
            system_content += f"\n\n── 记忆上下文 ──\n{ctx.knowledge_context}\n──"

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
        # ponytail: 注入失败历史，防止重复尝试已失败的方案
        failed = getattr(ctx, '_failed_approaches', None)
        if failed:
            dynamic_context += "<failed_approaches>\n以下方案已经失败，不要重复尝试:\n"
            for fa in failed[-5:]:
                name = fa.get("tool", "?")
                args_summary = fa.get("args_summary", "")
                err = fa.get("error", "")[:100]
                dynamic_context += f"- {name}({args_summary}): {err}\n"
            dynamic_context += "</failed_approaches>\n"
        dynamic_context += "</system_context>"
        system_content += dynamic_context
        ctx._pending_messages[0]["content"] = system_content  # ponytail: 写回，否则 dynamic_context 丢失

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
                    # ponytail: RAG → web_search 串行：先用知识库回答，再用联网补充最新信息
                    if _task_flags.get("search"):
                        messages[0]["content"] += "\n\n【搜索策略】知识库提供了基础信息，但对最新/未收录的内容可能不全。先用知识库回答主体，再用 web_search 补充最新数据和细节。禁止一轮就结束。"
            except Exception:
                pass

        if plan_context:
            messages[0]["content"] += plan_context

        # ── 3. 调用 LLM（最多 2 次，空转自动重试）──
        _last_reply = ""
        for _attempt in range(2):
            try:
                task = asyncio.create_task(router.chat(
                    messages,
                    temperature=0.7,
                    max_tokens=32768,
                    tools=ctx.tool_defs if ctx.tool_defs else None,
                ))
                try:
                    reply = await asyncio.wait_for(task, timeout=180)
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
                _ctx_text = reply if not reply.startswith("{") else _extract_text_from_json(reply) or reply[:200]
                ctx.knowledge_context += f"\nLLM第{ctx.react_depth}轮: {_ctx_text[:300]}"
                
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
                    ctx.consecutive_idle_rounds = 0  # 有工具调用，重置空转计数
                    break  # 有工具调用 → 跳出重试循环

                # 没有工具调用
                _last_reply = reply
                ctx.consecutive_idle_rounds = getattr(ctx, 'consecutive_idle_rounds', 0) + 1
                if ctx.consecutive_idle_rounds >= 3:
                    logger.warning(f"连续 {ctx.consecutive_idle_rounds} 轮空转，强制结束")
                    ctx.last_error = f"连续 {ctx.consecutive_idle_rounds} 轮空转无工具调用"
                    ctx.interrupted = True
                    if reply and len(reply) > 20:
                        ctx.final_answer = reply
                    break
                # ponytail: 最终答案判断 — 需要计划完成+回复有实质内容，或回复包含明确的报告结构
                _plan_done = ctx.plan and all(s.status == "done" for s in ctx.plan)
                _has_substance = len(reply) > 100 and not reply.startswith("{")
                if _plan_done and _has_substance:
                    ctx.final_answer = reply
                    ctx.interrupted = True
                    break
                # ponytail: 项目分析首轮是纯文本输出，不触发报告启发式/空跑重试，保存到历史后继续
                if "Phase 1 扫描" in ctx.task_description and _has_substance:
                    ctx._conversation_history.append({"role": "assistant", "content": reply})
                    ctx.final_answer = reply
                    break
                _looks_like_report = any(kw in reply for kw in ("## ", "### ", "**总结", "**结论", "## 总结", "## 结论"))
                if _looks_like_report and _has_substance:
                    ctx.final_answer = reply
                    ctx.interrupted = True
                    break
                # ponytail: 空跑重试 — 根据可用工具动态建议，不硬编码
                _avail = [t.get("function", {}).get("name", "") for t in (ctx.tool_defs or [])]
                _suggest = next((t for t in ["read_file", "web_search", "execute_python"] if t in _avail), "read_file")
                ctx.forced_instructions = (
                    f"你刚输出了思考但没调工具。请立即调用 {_suggest}，不要空转。"
                )
                # 重建消息（注入强制指令重试）
                _retry_sys = ctx._pending_messages[0]["content"]
                _retry_sys += f"\n\n<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>"
                messages = [{"role": "system", "content": _retry_sys},
                            {"role": "user", "content": ctx.task_description}]
                if ctx._conversation_history:
                    messages.extend(ctx._conversation_history)
                ctx.forced_instructions = ""  # 已内联，清除防重复
                logger.info(f"第{ctx.react_depth}轮空转，回合内重试 LLM...")
            except asyncio.TimeoutError:
                logger.warning(f"LLM 调用超时 (60s)")
                ctx.last_error = "LLM 调用超时"
                ctx.interrupted = True
                break
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                ctx.last_error = f"LLM 调用失败: {e}"
                ctx.interrupted = True
                break
        else:
            # 2 次都空转，用最后一次回复
            ctx._pending_reply = _last_reply
                
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

                # ponytail: 成功获取数据后标记，防止重复搜索
                if ok and tool_name in ("fetch_url", "web_search", "hot_search"):
                    _raw = str(result.get("result", {}))
                    if any(kw in _raw for kw in ("热搜", "热度:", "条热搜", "条/榜单")):
                        ctx._data_fetched = True
                        logger.info("数据已获取，后续将隐藏搜索工具防止重复")
                        # ponytail: 数据已就绪 → 强制 write_file 输出，防 LLM 画蛇添足调 execute_python
                        if not ctx.forced_instructions:
                            ctx.forced_instructions = (
                                "数据已获取完毕。直接用 write_file 在桌面生成报告，"
                                "不要再用 execute_python。"
                            )

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
                # ponytail: 参数校验错误不写入历史（已通过 forced_instructions 驱动重试）
                if result.get("_validation_error"):
                    logger.debug(f"跳过校验错误写入历史: {tool_name}")
                else:
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
    from .memory_middleware import MemoryMiddleware
    chain.add(MemoryMiddleware())
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
        TodoMiddleware,
        PermissionMiddleware,
        HookMiddleware,
        ReActDepthMiddleware,
        ReflectionMiddleware,
        TruncationMiddleware,
    )
    from .memory_middleware import MemoryMiddleware

    if memory:
        chain.add(MemoryMiddleware())
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
    tool_preference: Optional[set] = None,
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

    # ── 项目分析：禁止 read_file + 强制定 3 轮 ──
    if "Phase 1 扫描" in task_description or "项目结构概览" in task_description:
        ctx.max_iterations = 3
        ctx.disallowed_tools = list(set((ctx.disallowed_tools or []) + ["read_file"]))
        ctx.allowed_tools = ["write_file"]
    ctx.allowed_tools = allowed_tools
    ctx.disallowed_tools = disallowed_tools
    if tool_preference:
        ctx.tool_preference = tool_preference

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
    _has_structure_data = "Phase 1 扫描" in task_description or "项目结构概览" in task_description
    ctx._has_structure_data = _has_structure_data
    if _has_structure_data:
        # 新 Phase 1 已自包含完整分析，LLM 仅需格式化输出 HTML
        print(f"{prefix}    \033[2;37m📋 分析数据已就绪，LLM 负责格式化 HTML 输出\033[0m")
        # 项目分析只需要 3 轮（读数据 → 写 HTML → 收尾）
        ctx.max_iterations = 3
    else:
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
                _post_rounds = getattr(ctx, '_post_completion_rounds', 0) + 1
                ctx._post_completion_rounds = _post_rounds
                if _post_rounds >= 3:
                    print(f"{prefix}    \033[1;33m⚠️ 完成后已执行 {_post_rounds} 轮改进，强制结束\033[0m")
                    ctx.interrupted = True
                    break
                print(f"{prefix}    \033[1;33m⚠️ 计划已完成但有未处理的指令，继续执行({_post_rounds}/3)\033[0m")
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
            # ponytail: 优先用 LLM 压缩，回退到模板压缩
            try:
                compacted = await ctx.context_budget.async_check_and_compact(ctx)
            except Exception:
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

        # ponytail: on_plan_check 补丁 — 启用循环检测+澄清中间件
        hr_plan = await chain.on_plan_check(ctx)
        if hr_plan and hr_plan.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_plan.reason or "中间件终止(plan_check)"
            break
        if hr_plan and hr_plan.jump_to == "retry":
            continue

        hr_end = await chain.on_think_end(ctx)
        if hr_end and hr_end.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_end.reason or "中间件终止(think_end)"
            break

        # ponytail: 项目分析 — write_file 成功即跳出循环，不走空转，让 fallback 总结
        if _has_structure_data and ctx.tool_results:
            _last = ctx.tool_results[-1]
            if _last.get("success") and _last.get("tool_call", {}).get("name") == "write_file":
                ctx._write_file_done = True
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

        # ── 项目分析：检测连续 read_file 不输出分析 → 强制中断 ──
        if _has_structure_data:
            _recent_tools = [r.get("tool_call", {}).get("name", "") for r in ctx.tool_results[-4:]]
            if len(_recent_tools) >= 3 and all(t == "read_file" for t in _recent_tools[-3:]):
                if not ctx.forced_instructions:
                    ctx.forced_instructions = (
                        "⚠️ 你已经连续多次调 read_file 但没有输出分析。\n"
                        "现在必须停下来分析刚才读到的文件内容。\n"
                        "格式要求：对刚读的目录输出「📁 目录名: 职责分析（1-2句话）」\n"
                        "然后再决定下一步读哪个文件。"
                    )
                    print(f"{prefix}    \033[1;33m⚠️ 检测到连续 read_file 未分析，注入提醒\033[0m")

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
                                max_tokens=32768,
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
                                ctx.final_answer = _html_text
                        elif _html_text:
                            ctx.final_answer = _html_text
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
                            {"role": "system", "content": "基于工具执行结果，用完整详细的中文给出总结回答。覆盖项目概况、技术栈、目录结构、关键发现。直接输出结果，不要输出JSON。"},
                            {"role": "user", "content": f"原始任务: {_trim_desc(task_description)}\n\n工具执行结果:\n{summary}\n\n请给出最终总结。"},
                        ],
                        temperature=0.3,
                        max_tokens=32768,
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
                        ctx.final_answer = txt
                        break

    # ponytail: on_finish 必须在兜底之后调用，确保 final_answer 非空时写入记忆
    await chain.on_finish(ctx)

    return {
        "success": bool(ctx.final_answer),
        "answer": ctx.final_answer,
        "iterations": ctx.react_depth,
        "tool_results": ctx.tool_results,
        "error": ctx.last_error,
    }


