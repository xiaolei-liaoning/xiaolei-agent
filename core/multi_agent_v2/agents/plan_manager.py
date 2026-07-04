"""计划生成与Replan

从 react_core.py 提取，负责：
- 任务拆解与计划生成（两步 LLM 调用）
- 计划进度显示
- 步骤状态更新
- 失败步骤重规划
"""

import asyncio
import logging
from typing import Any, List, Optional

from .middleware import PlanStep, RunContext

logger = logging.getLogger(__name__)


def _consolidate_subagent_steps(ctx: RunContext, current_step: PlanStep) -> None:
    """当前步骤是 task/orchestrate → 后续同类型 pending 步骤自动 done"""
    _subagent_tools = {"task", "orchestrate"}
    if current_step.tool_names and set(current_step.tool_names) & _subagent_tools:
        for _s in ctx.plan:
            if _s.status == "pending" and _s.tool_names and set(_s.tool_names) & _subagent_tools:
                _s.status = "done"
                logger.debug(f"步骤 {_s.index} 被步骤 {current_step.index} 覆盖，自动完成")


def _parse_plan_steps(text: str) -> List[PlanStep]:
    """从文本中解析计划步骤，支持 步骤|描述|工具 格式"""
    template_blacklist = {"步骤描述", "具体描述", "任务描述", "描述", "步骤一", "步骤二"}
    steps = []
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("步骤|"):
            continue
        parts = line.split("|")
        desc = parts[1].strip() if len(parts) > 1 else ""
        tools_str = parts[2].strip() if len(parts) > 2 else ""
        if "直接回答" in desc:
            return []
        if desc in template_blacklist or len(desc) < 3:
            continue
        tools = (
            [t.strip() for t in tools_str.split(",") if t.strip()]
            if tools_str
            else []
        )
        steps.append(
            PlanStep(index=len(steps) + 1, description=desc, tool_names=tools)
        )
    return steps


async def generate_plan(
    task_description: str, ctx: RunContext, retry_context: str = ""
) -> List[PlanStep]:
    """规划阶段 — 两步LLM调用：先理解任务，再制定结构化计划

    第一步：LLM输出自然语言任务拆解（理解阶段）
    第二步：根据工具信息结构化为步骤（规划阶段）
    """
    from core.engine.llm_backend import get_llm_router

    router = get_llm_router()
    if not router or not router.is_available():
        return []

    retry_hint = f"\n【重试背景】{retry_context}\n" if retry_context else ""

    # ── 第一步：理解任务，输出自然语言拆解 ──
    understand_prompt = (
        "请分析以下任务，用自然语言描述应该如何完成。\n\n"
        "要求：\n"
        "- 理解任务的核心目标\n"
        "- 思考需要哪些步骤\n"
        "- 每个步骤用一句话描述\n"
        f"任务：{task_description[:300]}"
        f"{retry_hint}\n"
        "直接输出理解分析，不要编号："
    )
    try:
        understand_resp = await asyncio.wait_for(
            router.chat(
                [{"role": "user", "content": understand_prompt}],
                temperature=0.3,
                max_tokens=300,
            ),
            timeout=10.0,
        )
        understanding = str(understand_resp).strip() if understand_resp else ""
    except Exception:
        understanding = ""

    # ── 第二步：根据理解 + 工具信息，生成结构化计划 ──
    # 动态工具列表，与 _SANDBOX_TOOL_DEFS 保持一致
    _plan_tool_lines = []
    try:
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
        for t in _SANDBOX_TOOL_DEFS:
            if t.server == "__builtin__" and t.name not in ("git", "search_files", "arbor_viz", "write_todos"):
                _plan_tool_lines.append(
                    f"  {t.name} — {t.description.split(chr(10))[0].rstrip('.')}"
                )
    except Exception:
        pass

    # 补充 MCP 工具（codegraph 等）
    try:
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry
        _reg = get_tool_registry()
        await _reg.discover_all()
        for _t in _reg._tools.values():
            if _t.server and _t.server != "__builtin__" and _t.server != "":
                _plan_tool_lines.append(
                    f"  {_t.name} — {_t.description.split(chr(10))[0].rstrip('.')}"
                )
    except Exception:
        pass

    _plan_tools_text = "\n".join(_plan_tool_lines) if _plan_tool_lines else (
        "  write_file — 写入文件\n  read_file — 读取文件\n  web_search — 搜索\n"
    )

    # 角色说明（如果有）
    _personality_hint = ""
    if ctx and ctx.personality_prompt:
        _first_lines = [l for l in ctx.personality_prompt.split("\n") if l.strip()][:3]
        if _first_lines:
            _personality_hint = f"\n【角色说明】\n" + "\n".join(_first_lines) + "\n"

    plan_prompt = (
        "根据任务理解和可用工具，将任务拆解为执行步骤。\n"
        "简单任务（如搜索、问答、单文件）：1-3 步\n"
        "复杂任务（如分析项目、多文件开发）：3-7 步\n\n"
        "【任务理解】\n"
        f"{understanding if understanding else task_description[:200]}\n"
        f"{_personality_hint}"
        "【⚡核心规则】\n"
        "- 每个步骤做一件事，创建单文件项目只需 1 步\n"
        "- 创建文件用 write_file，抓取网页用 web_search/fetch_url\n"
        "- 分析代码项目：用 codegraph_explore 看结构，替代逐文件 read_file\n"
        "- 需要深入探索/分析/开发的子任务用 task 启动子代理\n"
        "- 多个无关子任务用 orchestrate 并行执行\n"
        "- 直接输出，不要模板文字\n\n"
        "【可用工具】\n"
        f"{_plan_tools_text}\n\n"
        "【输出格式】每行：步骤|具体描述|工具名\n\n"
        "示例：\n"
        "步骤|搜索百度热搜|web_search\n"
        "步骤|用 write_file 在 ~/Desktop 创建 index.html|write_file\n"
        "步骤|用 codegraph_explore 看项目结构|codegraph_explore\n"
        "步骤|用 task 子代理分析核心模块|task\n"
        "步骤|直接回答\n\n"
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
            text = ""

        steps: List[PlanStep] = []
        if text:
            steps = _parse_plan_steps(text)

        if steps:
            return steps[:5]

        # ponytail: 首次失败 → 极简降级 prompt，更大概率成功
        logger.info("plan_generation 首次尝试无结果，降级极简 prompt")
        fallback_prompt = (
            "将任务拆为步骤。每行：步骤|描述|工具\n"
            f"任务：{task_description[:200]}\n"
            "开始："
        )
        resp2 = await asyncio.wait_for(
            router.chat(
                [{"role": "user", "content": fallback_prompt}],
                temperature=0.2,
                max_tokens=500,
            ),
            timeout=15.0,
        )
        text2 = str(resp2).strip() if resp2 else ""
        if text2 and "[LLM_MOCK]" not in text2:
            return _parse_plan_steps(text2)[:5]
        return []
    except Exception:
        return []


def display_plan(
    ctx: RunContext, header: str = "Plan", prefix: str = ""
) -> None:
    """显示计划进度 — 精致样式"""
    if not ctx.plan:
        return
    done = sum(1 for s in ctx.plan if s.status == "done")
    total = len(ctx.plan)

    bar_segments = []
    for step in ctx.plan:
        if step.status == "done":
            bar_segments.append("\033[32m▇\033[0m")
        elif step.status == "running":
            bar_segments.append("\033[1;37m▇\033[0m")
        elif step.status == "failed":
            bar_segments.append("\033[31m▇\033[0m")
        else:
            bar_segments.append("\033[2m▇\033[0m")
    bar = "".join(bar_segments)

    lines = [f"{prefix}    \033[1m{header}\033[0m  {bar}  \033[2m{done}/{total}\033[0m"]
    for step in ctx.plan:
        if step.status == "done":
            icon, color = "✓", "\033[32m"
        elif step.status == "running":
            icon, color = "▶", "\033[1;37m"
        elif step.status == "failed":
            icon, color = "✗", "\033[31m"
        else:
            icon, color = "·", "\033[2m"
        desc = step.description.replace("\n", " ")[:55]
        lines.append(f"{prefix}      {color}{icon}\033[0m \033[2m{desc}\033[0m")
    print("\n".join(lines))


def steps_summary(ctx: RunContext) -> str:
    """生成步骤状态的文本摘要（注入 system prompt），保持简短"""
    if not ctx.plan:
        return ""
    total = len(ctx.plan)
    done = sum(1 for s in ctx.plan if s.status == "done")
    failed = [s for s in ctx.plan if s.status == "failed"]
    next_step = next((s for s in ctx.plan if s.status == "pending"), None)

    parts = [f"\n【进度】{done}/{total}"]
    if next_step:
        step_desc = next_step.description.replace("\n", " ")[:60]
        tool = f" → {next_step.tool_names[0]}" if next_step.tool_names else ""
        parts.append(f"下一步：{step_desc}{tool}")
        # 行为约束：防止 LLM 跳步或重复已完成步骤
        parts.append("⚠️ 不要跳过当前步骤，不要重复已完成步骤")
    if failed:
        parts.append(f"失败：{len(failed)}步需重试")
    return " | ".join(parts)


def update_step_status(ctx: RunContext, prefix: str = "") -> None:
    """更新步骤状态：检查步骤中指定的工具是否都已调用完成

    增强功能：
    1. 支持语义匹配：步骤描述关键词 vs 工具调用参数
    2. 支持跳过失败步骤
    3. 支持自动重规划（通过 replan_failed）
    4. 支持结果感知：一次 write_file 覆盖多步时自动推进
    """
    if not ctx.plan:
        return

    # 本轮有工具调用吗
    if not ctx.tool_results:
        return

    last_result = ctx.tool_results[-1]
    last_success = last_result.get("success", False)
    tool_has_error = not last_success

    done_count = sum(1 for s in ctx.plan if s.status == "done")
    if done_count >= len(ctx.plan):
        return
    current_step = ctx.plan[done_count]

    # 核心修复：工具成功完成 → 直接标记步骤 done，不受 forced_instructions 影响
    if last_success and current_step.tool_names:
        from collections import Counter
        succeeded = Counter()
        for tr in ctx.tool_results:
            tn = tr.get("tool_call", {}).get("name", "")
            if tn and tr.get("success"):
                succeeded[tn] += 1
        step_tools = set(current_step.tool_names)
        # ponytail: 搜索工具互换（fetch_url/web_search 视为等价）
        _search_tools = {"web_search", "fetch_url", "fetch_json", "hot_search"}
        if step_tools & _search_tools:
            if succeeded.keys() & _search_tools:
                current_step.status = "done"
                _consolidate_subagent_steps(ctx, current_step)
                return
        # ponytail: task/orchestrate 互认等价
        _subagent_tools = {"task", "orchestrate"}
        if step_tools & _subagent_tools:
            if succeeded.keys() & _subagent_tools:
                current_step.status = "done"
                _consolidate_subagent_steps(ctx, current_step)
                return
        # ponytail: 探索类工具互换
        _explore_tools = {"codegraph_explore", "codegraph_files", "search_files", "execute_shell", "read_file"}
        if step_tools & _explore_tools:
            if succeeded.keys() & _explore_tools:
                current_step.status = "done"
                _consolidate_subagent_steps(ctx, current_step)
                return
        if step_tools & set(succeeded.keys()):
            current_step.status = "done"
            return

    # 工具失败 → 标记当前步骤为 failed 并触发重规划
    if tool_has_error:
        # 仅在工具失败时，额外检查结果中是否有明确的代码错误（如 SyntaxError）
        last_raw = str(last_result.get("result", last_result.get("error", "")))
        code_error = any(
            marker in last_raw
            for marker in ["SyntaxError", "NameError", "TypeError"]
        )
        if current_step.status != "failed":
            current_step.status = "failed"
            ctx._step_retries[current_step.index] = (
                ctx._step_retries.get(current_step.index, 0) + 1
            )
            print(f"{prefix}    \033[2mStep {current_step.index} failed\033[0m")
        return

    # ── 结果感知：write_file 成功但内容短 → 提示补充（不标记步骤完成）
    last_tc = last_result.get("tool_call", {})
    if last_tc.get("name") == "write_file" and last_result.get("success"):
        _content = str(last_tc.get("arguments", {}).get("content", ""))
        _path = str(last_tc.get("arguments", {}).get("path", ""))
        if len(_content) < 2000 and not ctx.forced_instructions:
            _pending_after = [s for s in ctx.plan if s.status == "pending"]
            if _pending_after:
                ctx.forced_instructions = (
                    f"⚠️ {_path} 仅 {len(_content)} 字符。先继续下一步（{_pending_after[0].description}），"
                    f"所有文件创建完成后再回来补充内容。立即调用下一步的工具！"
                )
            else:
                ctx.forced_instructions = (
                    f"⚠️ {_path} 仅 {len(_content)} 字符。"
                    f"请用 write_file 写入完整内容，不得截断或用占位符。"
                )
            logger.info(f"write_file 内容过短({len(_content)}字符)，不标记完成")

    # 重新计算 done_count
    done_count = sum(1 for s in ctx.plan if s.status == "done")
    if done_count >= len(ctx.plan):
        return
    current_step = ctx.plan[done_count]

    # 收集所有已调用的工具及其调用次数
    from collections import Counter
    succeeded_counts = Counter()
    for tr in ctx.tool_results:
        tc = tr.get("tool_call", {})
        tool_name = tc.get("name", "")
        if tool_name and tr.get("success"):
            succeeded_counts[tool_name] += 1

    # 如果步骤指定了工具，用快照对比法判断是否完成
    if current_step.tool_names:
        step_tools = set(current_step.tool_names)
        # 记录进入此 step 时的工具调用快照
        if not hasattr(ctx, '_step_tool_snapshots'):
            ctx._step_tool_snapshots = {}
        if current_step.index not in ctx._step_tool_snapshots:
            ctx._step_tool_snapshots[current_step.index] = dict(succeeded_counts)

        snapshot = ctx._step_tool_snapshots[current_step.index]
        all_tools_done = all(
            succeeded_counts.get(t, 0) > snapshot.get(t, 0) for t in step_tools
        )

        _search_tools = {"web_search", "fetch_url", "fetch_json", "hot_search"}
        if not all_tools_done and step_tools & _search_tools:
            if any(succeeded_counts.get(t, 0) > snapshot.get(t, 0) for t in _search_tools):
                all_tools_done = True
                current_step.tool_names = list(step_tools | _search_tools)

        _file_tools = {"write_file", "edit_file"}
        if not all_tools_done and step_tools & _file_tools:
            if any(succeeded_counts.get(t, 0) > snapshot.get(t, 0) for t in _file_tools):
                all_tools_done = True
                current_step.tool_names = list(step_tools | _file_tools)

        if all_tools_done:
            current_step.status = "done"
            _consolidate_subagent_steps(ctx, current_step)
            logger.debug(f"步骤 {current_step.index} 完成");
            _pending_after_tool = [s for s in ctx.plan if s.status == "pending"]
            if _pending_after_tool and not ctx.forced_instructions:
                _nxt = _pending_after_tool[0]
                _th = f" → {_nxt.tool_names[0]}" if _nxt.tool_names else ""
                ctx.forced_instructions = (
                    f"立即执行下一步：{_nxt.description}{_th}，不要输出解释文本"
                )
            return

    # 步骤没有 tool_names → 按成功调用次数 >= 已完成步骤数+1才推进
    if not current_step.tool_names:
        _total_ok = sum(1 for r in ctx.tool_results if r.get("success"))
        if _total_ok >= done_count + 1:
            current_step.status = "done"
            _consolidate_subagent_steps(ctx, current_step)
            _pending_after_no = [s for s in ctx.plan if s.status == "pending"]
            if _pending_after_no and not ctx.forced_instructions:
                _n = _pending_after_no[0]
                _t = f" → {_n.tool_names[0]}" if _n.tool_names else ""
                ctx.forced_instructions = f"立即执行下一步：{_n.description}{_t}"
            return

    # 兜底：步骤卡住多轮且全无进展（无一完成）→ 推进
    _any_done_backup = any(s.status == "done" for s in ctx.plan)
    if current_step.status != "done" and not _any_done_backup and ctx.react_depth >= 6:
        _has_substance = False
        for r in ctx.tool_results:
            if not r.get("success"):
                continue
            name = r.get("tool_call", {}).get("name", "")
            if name in ("write_file", "web_search", "fetch_url", "fetch_json", "hot_search", "execute_shell", "read_file"):
                _has_substance = True
                break
            if name == "execute_python":
                result_text = str(r.get("result", ""))
                if result_text and result_text != "None" and len(result_text) > 20:
                    _has_substance = True
                    break
        if _has_substance:
            logger.info(f"步骤 {current_step.index} 多轮未推进且有实质进展，兜底标记为 done")
            current_step.status = "done"

    # 编辑任务卡住检测：步骤 pending 且一直只调 read_file → 禁用 read_file 逼它换工具
    if current_step.status not in ("done", "failed") and ctx.react_depth >= 2:
        recent_tools = [r.get("tool_call", {}).get("name", "") for r in ctx.tool_results[-3:]]
        if all(t == "read_file" for t in recent_tools if t):
            _is_edit = False
            _flags = getattr(ctx, '_task_flags', None)
            if _flags:
                _is_edit = _flags.get("edit", False)
            if not _is_edit:
                desc_lower = (current_step.description + ctx.task_description).lower()
                _is_edit = any(kw in desc_lower for kw in ["替换", "修改", "编辑", "改", "replace", "edit", "change"])
            if _is_edit:
                ctx.disallowed_tools = list(set(ctx.disallowed_tools or []) | {"read_file"})
                ctx._filtered_tools = None  # 清缓存，下次 on_llm_invoke 重新过滤
                inst = (
                    "⚠️ read_file 已被禁用！你已经读取了文件内容，现在必须使用 edit_file 工具进行修改。"
                    "用法：edit_file(path='文件路径', old_string='要替换的原文', new_string='替换后的新内容')"
                )
                ctx.forced_instructions = inst
                logger.info(f"步骤 {current_step.index} 卡在 read_file，禁用 read_file，强制使用 edit_file")


async def replan_failed(ctx: RunContext) -> bool:
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

    _replan_hint = ""
    if ctx and ctx.personality_prompt:
        _first_lines = [l for l in ctx.personality_prompt.split("\n") if l.strip()][:2]
        if _first_lines:
            _replan_hint = "\n角色: " + " ".join(_first_lines)

    retry_prompt = (
        "任务需要重新规划后面的步骤。\n\n"
        f"已完成: {', '.join(done_descs) if done_descs else '无'}\n"
        f"失败的步骤: {', '.join(failed_descs) if failed_descs else '需要继续'}"
        f"{error_context}"
        f"{_replan_hint}\n\n"
        "注意：\n"
        "- 分析类子任务用 task 或 orchestrate 启动子代理，别自己读文件\n"
        "- 探索代码用 codegraph_explore 替代 read_file 遍历\n"
        "- 输出格式：步骤|步骤描述|预计使用的工具名(逗号分隔,可省略)\n"
        "开始："
    )

    new_steps = await generate_plan(
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
    # ponytail: 重置快照，避免新步骤读到旧快照导致完成检测错误
    if hasattr(ctx, '_step_tool_snapshots'):
        ctx._step_tool_snapshots.clear()
    return True
