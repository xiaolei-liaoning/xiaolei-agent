"""计划生成与Replan

从 react_core.py 提取，负责：
- 任务拆解与计划生成（两步 LLM 调用）
- 计划进度显示
- 步骤状态更新
- 失败步骤重规划
"""

import asyncio
import logging
import os
import re
from typing import Any, List, Optional

from core.multi_agent_v2.prompts import get_builder
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


def _verify_step_completion(step: PlanStep, ctx: RunContext) -> bool:
    """检查步骤的所有后置条件是否满足。返回 False 时设置 forced_instructions。"""
    if not step.postconditions:
        return True
    for cond in step.postconditions:
        if cond.startswith("file_exists:"):
            path = os.path.expanduser(cond[12:])
            if not os.path.exists(path):
                logger.info(f"步骤 {step.index} 后置条件未满足: 文件 {path} 不存在")
                ctx.forced_instructions = (
                    f"⚠️ 当前步骤要求创建文件 {path}，但文件尚不存在。"
                    "请立即使用 write_file 写入完整内容！"
                )
                return False
        elif cond.startswith("capability:file_written"):
            if "(" in cond and "path=" in cond:
                import re
                _m = re.search(r"path=([^)]+)", cond)
                if _m:
                    _path = _m.group(1)
                    if not os.path.exists(os.path.expanduser(_path)):
                        logger.info(f"步 {step.index} 后置条件未满足: capability:file_written 文件 {_path} 不存在")
                        ctx.forced_instructions = (
                            f"⚠️ 当前步骤要求创建文件 {_path}，但文件尚不存在。请 write_file 完成！"
                        )
                        return False
            elif not any(
                r.get("tool_call", {}).get("name") in ("write_file", "edit_file") and r.get("success")
                for r in ctx.tool_results
            ):
                logger.info(f"步 {step.index} 后置条件未满足: write_file 未成功调用")
                ctx.forced_instructions = "⚠️ 当前步骤要求 write_file，但尚未成功调用。请立即执行！"
                return False
        elif cond.startswith("tool_called:"):
            required = cond[12:]
            if not any(
                r.get("tool_call", {}).get("name") == required and r.get("success")
                for r in ctx.tool_results
            ):
                logger.info(f"步骤 {step.index} 后置条件未满足: 工具 {required} 未成功调用")
                ctx.forced_instructions = (
                    f"⚠️ 当前步骤要求调用 {required}，但尚未成功调用。"
                    f"请立即使用 {required} 完成此步骤！"
                )
                return False
    return True


def _infer_postconditions(step: PlanStep, task_description: str) -> List[str]:
    """根据步骤工具名推断后置条件 — 验证产出真实达成

    ponytail: write/edit 步骤 → capability:file_written；搜索 → web_search；
    执行 → code_executed；读取/探索 → file_read。确保步骤推进后有真实产出，
    与 deepseek-harness 的「后置条件验证执行效果」思路一致。
    无工具绑定的通用步骤不设后置条件，靠实质产出自然推进，避免卡死。
    """
    if not step.tool_names:
        return []
    conds = []
    for tool in step.tool_names:
        if tool in ("write_file", "edit_file"):
            conds.append("capability:file_written")
        elif tool in ("web_search", "fetch_url", "fetch_json", "hot_search"):
            conds.append("capability:web_search")
        elif tool in ("execute_python", "execute_shell"):
            conds.append("capability:code_executed")
        elif tool == "read_file":
            conds.append("capability:file_read")
        elif tool in ("codegraph_explore", "codegraph_search", "codegraph_files", "search_files"):
            conds.append("capability:file_read")
    # 未知/假工具名（如"文件系统操作"）→ 不设后置条件，靠 _can_advance 推进，避免误卡
    return conds


def _clean_md(text: str) -> str:
    """清理步骤描述中的 markdown 格式（**、`、<br>、[链接]等），保留下划线（工具名）"""
    import re as _re
    text = _re.sub(r'<br\s*/?>', ' ', text)
    text = _re.sub(r'[`*~]', '', text)
    text = _re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = text.replace('**', '').replace('|', ' ').strip()
    return text


def _parse_tools_cell(cell: str) -> List[str]:
    """从 markdown 表格的工具列提取工具名。
    兼容 'write_file'、'终端'、'文件读取'、'write_file, execute_shell' 等。
    未知工具名 → 返回 []（不强制 write_file，靠 _can_advance 推进）。
    """
    cell = _clean_md(cell)
    # 已知真实工具名
    _known = {"write_file", "edit_file", "read_file", "web_search", "fetch_url",
              "fetch_json", "hot_search", "execute_python", "execute_shell",
              "codegraph_explore", "codegraph_search", "codegraph_files",
              "search_files", "glob", "task", "orchestrate", "text_analyzer"}
    # 中文/缩写工具名映射
    _map = {
        "终端": "execute_shell", "命令行": "execute_shell", "shell": "execute_shell",
        "文件读取": "read_file", "读取": "read_file", "读文件": "read_file",
        "文本编辑器": "read_file", "编辑器": "read_file", "cat命令": "execute_shell",
        "文件系统": "execute_shell", "目录": "execute_shell", "浏览": "execute_shell",
        "搜索": "web_search", "网络": "web_search", "网页": "fetch_url",
        "写入": "write_file", "写文件": "write_file", "生成": "write_file", "输出": "write_file",
        "代码分析": "codegraph_explore", "静态分析": "codegraph_explore",
    }
    found = []
    for tok in cell.replace(',', ' ').replace('、', ' ').split():
        tok = tok.strip()
        if tok in _known:
            found.append(tok)
        elif tok in _map:
            found.append(_map[tok])
    # 中文关键字包含匹配（处理 '终端（ls, find）' 等带括号/说明的写法）
    if not found:
        for kw, tool in sorted(_map.items(), key=lambda x: -len(x[0])):
            if kw in cell:
                found.append(tool)
                break
    return found


def _is_preamble(line: str) -> bool:
    """识别 LLM 输出的前言/说明文字（非步骤）。

    规则：
    - 以冒号结尾 → 标题/前言
    - 以明显前言词开头（好的/我将/以下是/下面/首先/这里/注意/说明等）→ 前言
    - 含格式指令（每行格式/格式为/输出格式）→ 前言
    """
    stripped = line.lstrip("：:，,。 ")
    if stripped.rstrip().endswith(("：", ":")):
        return True
    _start_markers = ("好的", "我将", "我会", "让我", "下面", "以下",
                      "为了", "你好", "这里", "我们", "可以", "总结", "备注",
                      "注意", "说明", "这个", "那么")
    if stripped.startswith(_start_markers):
        return True
    _fmt_markers = ("每行格式", "格式为", "输出格式", "格式如下", "步骤格式",
                    "拆解步骤", "如下", "任务步骤", "的步骤", "步骤为")
    if any(m in stripped for m in _fmt_markers) and len(stripped) > 20:
        return True
    return False


def _parse_plan_steps(text: str) -> List[PlanStep]:
    """从文本中解析计划步骤。支持三种格式：
    - 旧 步骤|描述|工具 或 1|描述|工具
    - 新 每行一段描述（OpenCode 风格，无工具绑定）
    - Markdown 表格 | 步骤 | 描述 | 工具 |（LLM 常见输出，需跳过 preamble）
    """
    import re as _re
    template_blacklist = {"步骤描述", "具体描述", "任务描述", "描述", "步骤一", "步骤二"}
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # ── 检测 Markdown 表格格式 ──
    table_rows = [l for l in lines if l.startswith("|") and l.count("|") >= 3]
    is_md_table = len(table_rows) >= 2 and any(
        "步骤" in row or "描述" in row for row in table_rows[:2]
    )

    if is_md_table:
        steps = []
        for row in table_rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            if len(cells) < 2:
                continue
            # 表头/分隔行（步骤/描述 或 ---/---）
            _c0 = _clean_md(cells[0])
            if _c0 in ("步骤", "序号", "#", "") or _re.match(r'^:?-+$', _c0):
                continue
            if _c0 == "描述" or _c0 == "工具":
                continue
            desc = _clean_md(cells[1]) if len(cells) > 1 else ""
            tools_str = cells[2] if len(cells) > 2 else ""
            if len(desc) < 3 or desc in template_blacklist:
                continue
            tools = _parse_tools_cell(tools_str)
            steps.append(PlanStep(index=len(steps) + 1, description=desc, tool_names=tools))
        return steps

    # ── 非表格格式：逐行解析，跳过 preamble ──
    steps = []
    for line in lines:
        # 旧格式：步骤|描述|工具 或 1|描述|工具
        if line.startswith("步骤|") or _re.match(r'^\d+\|', line):
            parts = line.split("|")
            desc = parts[1].strip() if len(parts) > 1 else ""
            tools_str = parts[2].strip() if len(parts) > 2 else ""
            if "直接回答" in desc or desc in template_blacklist or len(desc) < 3:
                continue
            tools = ([t.strip() for t in tools_str.split(",") if t.strip()] if tools_str else []) or ["write_file"]
            steps.append(PlanStep(index=len(steps) + 1, description=desc, tool_names=tools))
            continue

        # 跳过编号、前缀、示例标记
        if _re.match(r'^(步骤\s*[一二三四五六七八九十\d]|[一二三四五六七八九十\d]+[\.\、\)）]|[-*•]|#)', line):
            continue
        # 跳过太短的行
        if len(line) < 4:
            continue
        # 跳过前言/说明文字
        if _is_preamble(line):
            continue

        # 纯文本行 → 新格式步骤
        steps.append(PlanStep(
            index=len(steps) + 1,
            description=line,
            tool_names=[],  # 不绑定工具
        ))

    return steps


def _insert_explore_before_write(steps: List[PlanStep]) -> List[PlanStep]:
    """Insert explore step before write_file steps that lack preceding exploration.

    ponytail: explore step is a warmup — postconditions left empty so it advances
    as soon as any real capability is detected, never blocking progress.
    """
    _write_tools = {"write_file", "edit_file"}
    _explore_tools = {"execute_shell", "codegraph_explore", "read_file", "search_files", "glob"}
    new_steps = []
    for i, step in enumerate(steps):
        if step.tool_names and set(step.tool_names) & _write_tools:
            prev_is_explore = (
                i > 0
                and steps[i-1].tool_names
                and set(steps[i-1].tool_names) & _explore_tools
            )
            if not prev_is_explore:
                explore_step = PlanStep(
                    index=0,
                    description="探索项目结构，确认目录和前置文件存在",
                    tool_names=["execute_shell", "codegraph_explore", "read_file"],
                    postconditions=[],
                )
                explore_step._is_warmup = True
                new_steps.append(explore_step)
        new_steps.append(step)
    for idx, s in enumerate(new_steps):
        s.index = idx + 1
    return new_steps


def _ensure_deliverable_step(steps: List[PlanStep], task_description: str) -> List[PlanStep]:
    """确保产出型任务的计划以「写交付物」步骤结尾。

    根因：LLM 规划"分析项目+写报告"时，常只列出分析步骤而遗漏产出步骤，
    导致 agent 分析到底却从不写交付物（跑满 max_rounds 无输出）。
    若任务为产出型且计划无 write/edit 步骤，追加一个 write_file 步骤。
    """
    _prod_kw = [
        "写", "创建", "生成", "报告", "文件", "保存", "输出", "产出",
        "write", "create", "generate", "save", "output", "report", "build",
    ]
    if not any(kw in task_description.lower() for kw in _prod_kw):
        return steps
    # 用「写」相关关键词识别步骤是否已在产出交付物（不依赖 tool_names，
    # 因为 LLM 可能填假工具名如 终端/文本编辑器）
    _write_kw = ["写", "生成", "输出", "创建", "产出", "编写", "保存",
                 "write", "generate", "save", "output", "create", "report"]
    _has_write = any(
        (s.tool_names and set(s.tool_names) & {"write_file", "edit_file"})
        or any(kw in s.description.lower() for kw in _write_kw)
        for s in steps
    )
    if _has_write:
        return steps
    deliverable = PlanStep(
        index=len(steps) + 1,
        description="编写并输出最终交付物文件",
        tool_names=["write_file"],
        postconditions=["capability:file_written"],
    )
    steps.append(deliverable)
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
        logger.debug("plan_generation: router not available")
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
    except Exception as _e:
        logger.debug(f"plan_generation understanding step failed: {_e}")
        understanding = ""

    # ── 第二步：根据理解 + 工具信息，生成结构化计划 ──
    # 动态工具列表，与 _SANDBOX_TOOL_DEFS 保持一致
    _plan_tool_lines = []
    try:
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
        for t in _SANDBOX_TOOL_DEFS:
            if t.server == "__builtin__" and t.name not in ("git", "arbor_viz", "write_todos"):
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

    _plan_template = get_builder().load("system/plan_generation")
    # ponytail: 用原始任务作为权威描述，避免理解文本漂移导致计划跑偏（如贪吃蛇→AI工具搜索）
    _plan_desc = task_description[:300]
    if understanding and len(understanding) > 30:
        _plan_desc = f"{task_description[:200]}\n理解: {understanding[:200]}"
    _plan_role = _personality_hint if _personality_hint else ""
    plan_prompt = _plan_template.replace("{task_description}", _plan_desc).replace("{tool_list}", _plan_tools_text).replace("{role_description}", _plan_role)
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
            steps = _insert_explore_before_write(steps[:5])
            # ponytail: 确保产出型任务以写交付物结尾，防止只分析不产出
            steps = _ensure_deliverable_step(steps, task_description)
            for s in steps:
                # ponytail: only skip inference for explicitly marked warmup steps
                if hasattr(s, '_is_warmup') and s._is_warmup:
                    s.postconditions = []
                else:
                    s.postconditions = _infer_postconditions(s, task_description)
            return steps

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
            fb_steps = _insert_explore_before_write(_parse_plan_steps(text2)[:5])
            fb_steps = _ensure_deliverable_step(fb_steps, task_description)
            for s in fb_steps:
                if hasattr(s, '_is_warmup') and s._is_warmup:
                    s.postconditions = []
                else:
                    s.postconditions = _infer_postconditions(s, task_description)
            return fb_steps
        return []
    except Exception as _e:
        logger.warning(f"plan_generation step failed: {_e}")
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

    # ponytail: 标记当前待执行步骤为 "running" 以便显示 ▶ 而非 ·
    _first_pending = next((s for s in ctx.plan if s.status == "pending"), None)
    if _first_pending:
        _first_pending._display_active = True

    lines = [f"{prefix}    \033[1m{header}\033[0m  {bar}  \033[2m{done}/{total}\033[0m"]
    for step in ctx.plan:
        if step.status == "done":
            icon, color = "✓", "\033[32m"
        elif step.status == "running" or getattr(step, '_display_active', False):
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
    """更新步骤状态 — 委托给 TaskProgress（能力追踪模式）

    ponytail: 旧版工具等价组 + deadlock breaker 逻辑已废弃，
    保留函数签名供 react_core 调用，内部走 TaskProgress。
    无 task_progress 时回退到 legacy 逻辑（测试/兼容路径）。
    """
    if not ctx.plan:
        return
    _tp = getattr(ctx, 'task_progress', None)
    if _tp is not None:
        _tp.update()
    else:
        _update_step_status_legacy(ctx, prefix)


def _update_step_status_legacy(ctx: RunContext, prefix: str = "") -> None:
    """旧版步骤状态更新 — 仅作参考，disabled by default

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
                if not _verify_step_completion(current_step, ctx):
                    return
                current_step.status = "done"
                _consolidate_subagent_steps(ctx, current_step)
                return
        # ponytail: task/orchestrate 互认等价
        _subagent_tools = {"task", "orchestrate"}
        if step_tools & _subagent_tools:
            if succeeded.keys() & _subagent_tools:
                if not _verify_step_completion(current_step, ctx):
                    return
                current_step.status = "done"
                _consolidate_subagent_steps(ctx, current_step)
                return
        # ponytail: 探索类工具互换
        _explore_tools = {"codegraph_explore", "codegraph_files", "search_files", "execute_shell", "read_file"}
        if step_tools & _explore_tools:
            if succeeded.keys() & _explore_tools:
                if not _verify_step_completion(current_step, ctx):
                    return
                current_step.status = "done"
                _consolidate_subagent_steps(ctx, current_step)
                return
        # ponytail: 写文件/编辑步骤可被探索工具推进（LLM 写代码前先 ls/mkdir 探路）
        _write_tools = {"write_file", "edit_file"}
        if step_tools & _write_tools:
            if succeeded.keys() & _explore_tools:
                # ponytail: guard — only swap if agent has written a file before
                # Prevents first write_file from being skipped when LLM calls mkdir/ls
                # Postconditions (file_exists:/path) add another safety net below.
                _ever_written = any(
                    tr.get("tool_call", {}).get("name") in _write_tools and tr.get("success")
                    for tr in ctx.tool_results
                )
                if _ever_written:
                    if not _verify_step_completion(current_step, ctx):
                        return
                    current_step.status = "done"
                    _consolidate_subagent_steps(ctx, current_step)
                    return
        # ponytail: 探索步骤也可被写文件工具推进（LLM 跳过探索直接写）
        if step_tools & _explore_tools:
            if succeeded.keys() & _write_tools:
                if not _verify_step_completion(current_step, ctx):
                    return
                current_step.status = "done"
                _consolidate_subagent_steps(ctx, current_step)
                return
        if step_tools & set(succeeded.keys()):
            if not _verify_step_completion(current_step, ctx):
                return
            current_step.status = "done"
            return

    # 工具失败 → 判断是否是当前步骤需要的工具
    if tool_has_error:
        last_tc = last_result.get("tool_call", {})
        last_name = last_tc.get("name", "")
        # 失败的工具不是当前步骤需要的 → 忽略（LLM 思考扩展出去的附加调用）
        if current_step.tool_names and last_name not in current_step.tool_names:
            return
        # 当前步骤需要的工具失败 → 标记步骤失败并触发重规划
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
            if not _verify_step_completion(current_step, ctx):
                return
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
            if not _verify_step_completion(current_step, ctx):
                return
            current_step.status = "done"
            _consolidate_subagent_steps(ctx, current_step)
            _pending_after_no = [s for s in ctx.plan if s.status == "pending"]
            if _pending_after_no and not ctx.forced_instructions:
                _n = _pending_after_no[0]
                _t = f" → {_n.tool_names[0]}" if _n.tool_names else ""
                ctx.forced_instructions = f"立即执行下一步：{_n.description}{_t}"
            return

    # ponytail: 步骤卡住多轮 → 检查是否有实质进展（工具产生了有效输出），有则推进
    # 修复 #064: read_file 从"实质进展"名单移除——读文件不改变世界状态，
    # 把它算进展会让 stuck 永远涨不上去，步骤卡死循环。如需读文件进展，
    # 必须伴随产出（execute_python 结果、写入等）。
    if current_step.status != "done" and ctx.react_depth >= 4:
        _has_substance = False
        for r in ctx.tool_results:
            if not r.get("success"):
                continue
            name = r.get("tool_call", {}).get("name", "")
            if name in ("write_file", "edit_file", "web_search", "fetch_url", "fetch_json", "hot_search", "execute_shell"):
                _has_substance = True
                break
            if name == "execute_python":
                result_text = str(r.get("result", ""))
                if result_text and result_text != "None" and len(result_text) > 20:
                    _has_substance = True
                    break
        # ponytail: LLM 无有效输出且步骤有指定工具 → 强制提示调用
        if not _has_substance and current_step.tool_names and ctx.react_depth >= 5:
            _required = ", ".join(current_step.tool_names[:3])
            ctx.forced_instructions = (
                f"⚠️ 当前步骤需要调用 {_required}。不要输出解释文本，请直接调用 {_required} 完成任务！"
            )
            logger.info(f"步骤 {current_step.index} LLM 无输出，强制提示调用 {_required}")
            return
        if _has_substance:
            # ponytail: don't skip write_file steps that haven't written yet
            _write_tools = {"write_file", "edit_file"}
            if current_step.tool_names and set(current_step.tool_names) & _write_tools:
                _ever_written = any(
                    r.get("tool_call", {}).get("name") in _write_tools and r.get("success")
                    for r in ctx.tool_results
                )
                if not _ever_written:
                    ctx.forced_instructions = (
                        "⚠️ 当前步骤要求创建文件，但你尚未成功调用 write_file。"
                        "请立即使用 write_file 写入完整内容，不要再执行其他工具！"
                    )
                    logger.info(f"步骤 {current_step.index} 卡在 write_file 前，设置 forced_instructions")
                    return
            logger.info(f"步骤 {current_step.index} 多轮未推进且有实质进展，兜底标记为 done")
            if not _verify_step_completion(current_step, ctx):
                return
            current_step.status = "done"
            _consolidate_subagent_steps(ctx, current_step)
            _pending_after_fallback = [s for s in ctx.plan if s.status == "pending"]
            if _pending_after_fallback and not ctx.forced_instructions:
                _nxt_f = _pending_after_fallback[0]
                _tf = f" → {_nxt_f.tool_names[0]}" if _nxt_f.tool_names else ""
                ctx.forced_instructions = f"立即执行下一步：{_nxt_f.description}{_tf}"

    # 任务卡住检测：步骤 pending 且一直只调 read_file → 禁用 read_file 逼它换工具
    # 修复 #065: 加 len 守卫——空列表/1条时 all() 恒 True，会误触发禁 read_file
    if current_step.status not in ("done", "failed") and ctx.react_depth >= 2:
        recent_tools = [r.get("tool_call", {}).get("name", "") for r in ctx.tool_results[-3:]]
        if len(recent_tools) >= 2 and all(t == "read_file" for t in recent_tools if t):
            _is_edit = False
            _flags = getattr(ctx, '_task_flags', None)
            if _flags:
                _is_edit = _flags.get("edit", False)
            desc_lower = (current_step.description + ctx.task_description).lower()
            if not _is_edit:
                _is_edit = any(kw in desc_lower for kw in ["替换", "修改", "编辑", "改", "replace", "edit", "change"])
            _is_write = any(kw in desc_lower for kw in ["创建", "写", "生成", "写入", "creat", "write"])
            if _is_edit:
                ctx.disallowed_tools = list(set(ctx.disallowed_tools or []) | {"read_file"})
                ctx._filtered_tools = None
                inst = (
                    "⚠️ read_file 已被禁用！你已经读取了文件内容，现在必须使用 edit_file 工具进行修改。"
                    "用法：edit_file(path='文件路径', old_string='要替换的原文', new_string='替换后的新内容')"
                )
                ctx.forced_instructions = inst
                logger.info(f"步骤 {current_step.index} 卡在 read_file，禁用 read_file，强制使用 edit_file")
            elif _is_write:
                ctx.disallowed_tools = list(set(ctx.disallowed_tools or []) | {"read_file"})
                ctx._filtered_tools = None
                inst = (
                    "⚠️ read_file 已被禁用！你已经读取了足够的信息，现在必须使用 write_file 工具写入完整文件内容。"
                    "不要再继续读取或探索，直接 write_file！"
                )
                ctx.forced_instructions = inst
                logger.info(f"步骤 {current_step.index} 卡在 read_file，禁用 read_file，强制使用 write_file")


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
