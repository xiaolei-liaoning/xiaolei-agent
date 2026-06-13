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
    plan_prompt = (
        "根据任务理解和可用工具，将任务拆解为1-2个执行步骤。\n\n"
        "【任务理解】\n"
        f"{understanding if understanding else task_description[:200]}\n\n"
        "【重要规则】\n"
        "- 最多2个步骤，不要拆分过细\n"
        "- 每个步骤只能包含一个工具调用\n"
        "- ⚠️ 创建文件（游戏/HTML/脚本）必须用 write_file，不要用 execute_python！\n"
        "- 抓取网页数据（热搜/新闻/搜索结果）→ 用 web_search 或 fetch_url\n"
        "- ⚠️ 请直接输出你的计划，不要输出模板文字\n\n"
        "【可用工具】\n"
        "  write_file — 写入文件到指定路径（创建游戏/HTML/脚本必用！）\n"
        "  edit_file — 精确替换文件内容（改代码必用！先 read_file 读取，再用 edit_file 替换）\n"
        "  read_file — 读取文件内容\n"
        "  execute_python — 执行Python代码（仅用于数据处理、计算，不能创建持久文件）\n"
        "  web_search — 网页搜索\n"
        "  fetch_url — HTTP GET获取网页/API数据\n\n"
        "【输出格式】每行一个步骤，格式：步骤|具体描述|工具名\n"
        "⚠️ 「具体描述」必须包含具体文件路径，不要写泛泛的描述\n\n"
        "示例（参考格式，不要照抄内容）：\n"
        "任务: 搜索百度热搜 → 步骤|搜索百度热搜获取数据|web_search\n"
        "任务: 写八数码游戏到桌面 → 步骤|用 write_file 在 ~/Desktop 创建 eight_puzzle.html（完整游戏代码）|write_file\n"
        "任务: 打开QQ → 步骤|打开QQ应用|open_app\n"
        "任务: 修改文件里的文字 → 步骤|把文件中的 hello 改为 world|edit_file\n\n"
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
        # 模板文本黑名单 - LLM 可能照抄模板
        template_blacklist = {"步骤描述", "具体描述", "任务描述", "描述", "步骤一", "步骤二"}
        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("步骤|"):
                continue
            parts = line.split("|")
            desc = parts[1].strip() if len(parts) > 1 else ""
            tools_str = parts[2].strip() if len(parts) > 2 else ""
            if "直接回答" in desc:
                return []
            # 跳过模板文本（LLM 照抄了示例格式）
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
        return steps[:5]
    except Exception:
        return []


def display_plan(
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

    # 检查最近一次工具调用的结果中是否包含错误
    last_result = ctx.tool_results[-1]
    last_raw = str(last_result.get("result", last_result.get("error", "")))
    has_error = any(
        marker in last_raw
        for marker in ["❌", "SyntaxError", "NameError", "TypeError", "Error:", "需要", "失败"]
    )

    # 获取当前正在执行的步骤（第一个未完成的步骤）
    done_count = sum(1 for s in ctx.plan if s.status == "done")
    if done_count >= len(ctx.plan):
        return

    current_step = ctx.plan[done_count]

    # 如果有代码错误，标记当前步骤为 failed 并触发重规划
    if has_error:
        if current_step.status != "failed":
            current_step.status = "failed"
            ctx._step_retries[current_step.index] = (
                ctx._step_retries.get(current_step.index, 0) + 1
            )
            print(f"{prefix}    \033[1;31m❌ 步骤 {current_step.index} 执行失败，将触发重规划\033[0m")
        return

    # ── 结果感知：write_file 成功后检查是否覆盖了后续步骤 ──
    last_tc = last_result.get("tool_call", {})
    if last_tc.get("name") == "write_file" and last_result.get("success"):
        _advance_steps_by_result(ctx, last_tc, prefix)

    # 重新计算 done_count（可能被 _advance_steps_by_result 更新）
    done_count = sum(1 for s in ctx.plan if s.status == "done")
    if done_count >= len(ctx.plan):
        return
    current_step = ctx.plan[done_count]

    # 收集所有已调用的工具名称（成功调用）
    succeeded_tools = set()
    for tr in ctx.tool_results:
        tc = tr.get("tool_call", {})
        tool_name = tc.get("name", "")
        if tool_name and tr.get("success"):
            succeeded_tools.add(tool_name)

    # 如果步骤指定了工具，检查是否都已调用成功
    if current_step.tool_names:
        step_tools = set(current_step.tool_names)
        # 所有步骤指定的工具都已成功调用，才标记为完成
        if step_tools.issubset(succeeded_tools):
            current_step.status = "done"
        # else: 未完成，保持 pending 状态，等待下一轮
    else:
        # 没有指定工具名：不自动完成，等 LLM 真正调了合适的工具再说
        pass

    # 兜底：有实质进展且步骤已运行多轮 → 推进
    if current_step.status != "done" and ctx.react_depth >= 3:
        _has_substance = False
        for r in ctx.tool_results:
            if not r.get("success"):
                continue
            name = r.get("tool_call", {}).get("name", "")
            # 只有产出数据的工具才算实质进展
            if name in ("write_file", "web_search", "fetch_url", "fetch_json"):
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
            desc_lower = (current_step.description + ctx.task_description).lower()
            if any(kw in desc_lower for kw in ["替换", "修改", "编辑", "改", "replace", "edit", "change"]):
                ctx.disallowed_tools = list(set(ctx.disallowed_tools or []) | {"read_file"})
                ctx._filtered_tools = None  # 清缓存，下次 on_think_start 重新过滤
                inst = (
                    "⚠️ read_file 已被禁用！你已经读取了文件内容，现在必须使用 edit_file 工具进行修改。"
                    "用法：edit_file(path='文件路径', old_string='要替换的原文', new_string='替换后的新内容')"
                )
                ctx.forced_instructions = inst
                logger.info(f"步骤 {current_step.index} 卡在 read_file，禁用 read_file，强制使用 edit_file")


def _advance_steps_by_result(ctx: RunContext, tool_call: dict, prefix: str = "") -> None:
    """结果感知：write_file 成功后，检查是否覆盖了后续 pending 步骤

    策略：
    1. 提取写入的文件路径和内容关键词
    2. 检查后续 pending 步骤是否描述了同一文件或类似操作
    3. 如果覆盖，自动标记为 done
    """
    tc_args = tool_call.get("arguments", {})
    if isinstance(tc_args, str):
        import json
        try:
            tc_args = json.loads(tc_args)
        except (json.JSONDecodeError, TypeError):
            tc_args = {}

    written_path = tc_args.get("path", "")
    written_content = tc_args.get("content", "")
    if not written_path or not written_content:
        return

    written_filename = written_path.rsplit("/", 1)[-1] if "/" in written_path else written_path
    written_name_base = written_filename.rsplit(".", 1)[0] if "." in written_filename else written_filename
    content_lower = written_content.lower()

    # 收集内容中的关键特征
    content_features = set()
    if "<html" in content_lower or "<!doctype" in content_lower:
        content_features.add("html")
    if "class " in content_lower or "def " in content_lower:
        content_features.add("code")
    if any(kw in content_lower for kw in ["game", "puzzle", "游戏", "棋"]):
        content_features.add("game")
    if any(kw in content_lower for kw in ["<script", "javascript", "function "]):
        content_features.add("js")
    if any(kw in content_lower for kw in ["<style", "css", "background"]):
        content_features.add("css")

    done_count = sum(1 for s in ctx.plan if s.status == "done")

    for step in ctx.plan[done_count:]:
        if step.status != "pending":
            continue
        desc_lower = step.description.lower()

        # 匹配条件 1：步骤描述中提到同一文件名
        same_file = False
        if written_filename in desc_lower or written_name_base in desc_lower:
            same_file = True
        # 匹配条件 2：步骤指定的工具也是 write_file，且内容特征匹配
        elif "write_file" in step.tool_names:
            step_has_game = any(kw in desc_lower for kw in ["game", "puzzle", "游戏", "棋", "html", "界面", "逻辑"])
            step_has_code = any(kw in desc_lower for kw in ["代码", "脚本", "code", "script", "创建", "写入"])
            if (step_has_game and "game" in content_features) or (step_has_code and "code" in content_features):
                same_file = True
        # 匹配条件 3：步骤描述是"设计/创建"类，且写入内容覆盖了该功能
        elif any(kw in desc_lower for kw in ["设计", "创建", "布局", "界面"]):
            if content_features & {"html", "game", "js", "css"}:
                same_file = True

        if same_file:
            step.status = "done"
            print(f"{prefix}    \033[1;32m✅ 步骤 {step.index} 已被写入结果覆盖，自动标记完成\033[0m")


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

    retry_prompt = (
        "任务需要重新规划后面的步骤。\n\n"
        f"已完成: {', '.join(done_descs) if done_descs else '无'}\n"
        f"失败的步骤: {', '.join(failed_descs) if failed_descs else '需要继续'}"
        f"{error_context}\n\n"
        "请重新规划未完成的步骤，忽略已完成的。\n"
        "输出格式：步骤|步骤描述|预计使用的工具名(逗号分隔,可省略)\n"
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
    return True
