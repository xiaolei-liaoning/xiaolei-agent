"""Subagent 生成与编排 — OpenCode 风格子代理执行"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.prompts import get_builder
from .types import (
    AgentProfile, PROFILE_PERMISSIONS,
    SubagentSession, OrchestrationTask, OrchestrationResult,
    get_session_manager,
)

logger = logging.getLogger(__name__)

_MAX_SUBAGENT_ROUNDS = 10  # 子代理最大执行轮次
_MAX_ORCH_CONCURRENCY = 5  # 编排最大并发数

# ponytail: stdout 重定向堆栈，支持并发子代理嵌套
import io, sys
_stdout_stack: list = []

def _push_stdout():
    _stdout_stack.append(sys.stdout)
    sys.stdout = io.StringIO()

def _pop_stdout() -> str:
    buf = sys.stdout
    sys.stdout = _stdout_stack.pop()
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════
# 父代理上下文传递（全局状态，由 run_react 设置）
# ════════════════════════════════════════════════════════════════
_parent_state: Dict[str, Any] = {}


def set_parent_state(
    task_description: str = "",
    conversation_summary: str = "",
    tool_results_summary: str = "",
    artifacts_dir: str = "",
):
    """由主代理的 ReAct 循环在每轮 LLM 调用前设置
    
    子代理生成时会自动注入这些上下文，避免从零开始。
    task_description: 当前主代理的原始任务
    conversation_summary: 已执行的工具轮次摘要
    tool_results_summary: 已有工具结果的关键发现
    artifacts_dir: 父代理 artifact 目录路径，子代理可 read_file 读取
    """
    global _parent_state
    _parent_state = {
        "task": task_description,
        "conversation": conversation_summary,
        "tool_results": tool_results_summary,
        "artifacts_dir": artifacts_dir,
    }


def _build_parent_context() -> str:
    """构建父代理上下文块 — 从 prompts/blocks/parent_context.txt 加载模板"""
    ctx = _parent_state
    if not ctx or not any(ctx.values()):
        return ""
    return get_builder().get_block("parent_context",
        task=(ctx.get("task") or "")[:500],
        conversation=(ctx.get("conversation") or "")[:1000],
        tool_results=(ctx.get("tool_results") or "")[:2000],
        artifacts=ctx.get("artifacts_dir", ""),
    )


# ════════════════════════════════════════════════════════════════
# 单个子代理生成
# ════════════════════════════════════════════════════════════════

async def spawn_subagent(
    task_description: str,
    profile: AgentProfile = AgentProfile.GENERAL,
    parent_id: str = "",
    model: str = "",
    parent_allowed: Optional[List[str]] = None,
    parent_disallowed: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """生成单个子代理并等待完成

    Args:
        task_description: 子任务描述
        profile: 代理类型
        parent_id: 父会话 ID
        model: 模型覆盖
        parent_allowed: 父代理工具白名单（用于权限派生）
        parent_disallowed: 父代理工具黑名单（用于权限派生）

    Returns:
        {"success": bool, "output": str, "session_id": str, "error": str}
    """
    sess_mgr = get_session_manager()
    session = sess_mgr.create(
        parent_id=parent_id,
        profile=profile,
        task=task_description,
    )

    perm = PROFILE_PERMISSIONS.get(profile, PROFILE_PERMISSIONS[AgentProfile.GENERAL])
    allowed = perm["allowed"]
    disallowed = list(perm["disallowed"] or [])
    hint = perm["system_hint"]

    # 权限派生：合并父代理限制
    #   1. 父代理的 disallowed 列表继承给子代理
    #   2. 如果父代理有 allowed 白名单，子代理的 allowed 必须与之取交集
    if parent_disallowed:
        disallowed = list(set(disallowed + parent_disallowed))
    if parent_allowed and allowed:
        allowed = [t for t in allowed if t in parent_allowed]
    elif parent_allowed:
        allowed = list(parent_allowed)

    # 默认：子代理禁止递归生成子子代理
    if "task" not in (allowed or []):
        disallowed.append("task")
    if "orchestrate" not in (allowed or []):
        disallowed.append("orchestrate")

    # 构建子代理的完整任务 — 角色提示词 + 工具范围 + 父上下文 + 任务要求
    full_task = hint

    # 注入可用工具列表
    if allowed:
        full_task += (
            "\n\n## 可用工具\n"
            f"You may use：{', '.join(sorted(allowed))}。\n"
            ""
        )
    if disallowed:
        full_task += (
            f"\nDisallowed：{', '.join(sorted(disallowed))}。\n"
        )

    full_task += f"\n\n---\n## Task from Main Agent\n\n{task_description}"

    logger.info(f"Subagent [{session.session_id}] ({profile.value}) 启动: {task_description[:80]}")

    session.state = "running"
    session.start_time = time.time()

    try:
        # ponytail: 移进 try 块 — _build_parent_context 的 .format() 遇到值里的 {/} 会抛异常
        parent_ctx = _build_parent_context()
        if parent_ctx:
            full_task += parent_ctx

        from core.multi_agent_v2.agents.react_core import run_react
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry

        # ponytail: 捕获子代理输出，加前缀后集中打印，防止与主代理混叠
        _push_stdout()
        try:
            result = await asyncio.wait_for(
                run_react(
                    task_description=full_task,
                    max_rounds=_MAX_SUBAGENT_ROUNDS,
                    model=model,
                    allowed_tools=allowed,
                    disallowed_tools=disallowed,
                    is_subagent=True,
                ),
                timeout=300,  # 5 分钟超时
            )
        finally:
            # ponytail: try/except 防止栈损坏遮盖原始异常（"During handling..." 来源）
            try:
                _captured = _pop_stdout()
            except IndexError:
                _captured = ""
                logger.warning("子代理 stdout 栈损坏，跳过恢复")
            except Exception:
                _captured = ""
        if _captured.strip():
            _tag = f"子代理 {profile.value}"
            _lines = _captured.splitlines()
            # ponytail: 只显示首尾摘要，避免大量子代理输出污染主终端
            if len(_lines) <= 3:
                for _line in _lines:
                    print(f"  \033[2m[{_tag}]\033[0m {_line}")
            else:
                print(f"  \033[2m[{_tag}]\033[0m {_lines[0]}")
                print(f"  \033[2m[{_tag}]\033[0m \033[2m... {len(_lines)-2} lines omitted\033[0m")
                print(f"  \033[2m[{_tag}]\033[0m {_lines[-1]}")

        output = result.get("answer", "")
        success = result.get("success", False)
        error = result.get("error", "")

        if success and output:
            session.state = "completed"
            session.result = output
            logger.info(f"Subagent [{session.session_id}] 完成: {len(output)} 字符")
        else:
            session.state = "error"
            session.error = error or "子代理未返回有效结果"
            logger.warning(f"Subagent [{session.session_id}] 失败: {session.error}")

    except asyncio.TimeoutError:
        session.state = "error"
        session.error = "子代理执行超时 (300s)"
        success = False
        output = ""
        logger.error(f"Subagent [{session.session_id}] 超时")

    except Exception as e:
        session.state = "error"
        session.error = f"子代理异常: {e}"
        success = False
        output = ""
        logger.error(f"Subagent [{session.session_id}] 异常: {e}")

    session.end_time = time.time()
    elapsed = session.end_time - session.start_time
    logger.info(f"Subagent [{session.session_id}] 耗时: {elapsed:.1f}s")

    # 获取子代理的 artifact 路径
    _artifact_dir = ""
    try:
        from core.memory import session_manager as _art_mgr
        _sm = _art_mgr.get_session_manager()
        _artifact_dir = _sm.artifacts_dir or ""
    except Exception:
        pass

    return {
        "success": success,
        "output": output,
        "session_id": session.session_id,
        "error": session.error,
        "elapsed": elapsed,
        "artifacts_dir": _artifact_dir,
    }


# ════════════════════════════════════════════════════════════════
# 后台子代理（fire-and-forget）
# ════════════════════════════════════════════════════════════════

async def spawn_background(
    task_description: str,
    profile: AgentProfile = AgentProfile.GENERAL,
    parent_id: str = "",
    model: str = "",
) -> str:
    """后台生成子代理（不等待结果，返回 session_id）

    子代理完成后自动通知：写入 ~/.xiaolei/subagent_sessions/{session_id}.json，
    主代理下次查询时可获取结果。
    """
    sess_mgr = get_session_manager()
    session = sess_mgr.create(
        parent_id=parent_id,
        profile=profile,
        task=task_description,
    )
    session.state = "running"
    sess_mgr._save_session(session)

    async def _bg_run():
        try:
            result = await spawn_subagent(
                task_description=task_description,
                profile=profile,
                parent_id=parent_id,
                model=model,
            )
            session = sess_mgr.get(session.session_id)
            if session:
                session.state = "completed" if result["success"] else "error"
                session.result = result.get("output", "")
                session.error = result.get("error", "")
                session.end_time = time.time()
                sess_mgr._save_session(session)
                logger.info(f"后台子代理 [{session.session_id}] 完成 "
                            f"({'成功' if result['success'] else '失败'})")
        except Exception as e:
            session = sess_mgr.get(session.session_id)
            if session:
                session.state = "error"
                session.error = str(e)
                session.end_time = time.time()
                sess_mgr._save_session(session)
            logger.error(f"后台子代理 [{session.session_id}] 异常: {e}")

    asyncio.ensure_future(_bg_run())
    logger.info(f"后台子代理 [{session.session_id}] 已启动: {task_description[:60]}")
    print(f"    \033[2mBackground subagent [{session.session_id}] started\033[0m")
    return session.session_id


# ════════════════════════════════════════════════════════════════
# DAG 编排（OpenCode 风格 orchestrate）
# ════════════════════════════════════════════════════════════════

def _build_dag(tasks: List[OrchestrationTask]) -> tuple:
    """拓扑排序 + 循环检测 (Kahn 算法)"""
    in_degree = {t.id: len(t.depends_on) for t in tasks}
    children = {t.id: [] for t in tasks}
    id_to_task = {t.id: t for t in tasks}

    for t in tasks:
        for dep in t.depends_on:
            if dep in children:
                children[dep].append(t.id)

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    levels = []
    visited = set()

    while queue:
        levels.append(list(queue))
        next_queue = []
        for tid in queue:
            visited.add(tid)
            for child in children[tid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_queue.append(child)
        queue = next_queue

    if len(visited) != len(tasks):
        remaining = [t.id for t in tasks if t.id not in visited]
        raise ValueError(f"DAG 循环依赖: {remaining}")

    return levels, id_to_task


async def orchestrate_subagents(
    tasks: List[Dict[str, Any]],
    parent_id: str = "",
    model: str = "",
    max_concurrent: int = _MAX_ORCH_CONCURRENCY,
) -> Dict[str, Any]:
    """DAG 编排多个子代理并行执行

    Args:
        tasks: [{"id": str, "description": str, "prompt": str, "agent": str, "depends_on": [str]}]
        parent_id: 父会话 ID
        model: 模型覆盖
        max_concurrent: 最大并发数

    Returns:
        {"success": bool, "results": [OrchestrationResult], "total": int, "completed": int}
    """
    orch_tasks = [
        OrchestrationTask(
            id=t.get("id", f"task_{i}"),
            description=t.get("description", ""),
            prompt=t.get("prompt", ""),
            agent=AgentProfile(t["agent"]) if t.get("agent") in AgentProfile.__members__.values() else None,
            depends_on=t.get("depends_on", []),
        )
        for i, t in enumerate(tasks)
    ]

    try:
        levels, id_to_task = _build_dag(orch_tasks)
    except ValueError as e:
        return {"success": False, "error": str(e), "results": []}

    logger.info(f"编排: {len(orch_tasks)} 个任务, {len(levels)} 层")
    all_results: Dict[str, OrchestrationResult] = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    for level_idx, level in enumerate(levels):
        logger.debug(f"编排 第{level_idx + 1}层: {level}")

        async def run_task(tid: str) -> OrchestrationResult:
            task = id_to_task[tid]
            prompt = task.prompt

            # 注入依赖结果（大结果自动压缩，避免撑爆上下文）
            if task.depends_on:
                dep_outputs = []
                for dep_id in task.depends_on:
                    if dep_id in all_results:
                        dep = all_results[dep_id]
                        if dep.success:
                            _out = dep.output
                            if len(_out) > 3000:
                                _out = _out[:3000] + "\n...(输出已截断)"  # ponytail: 3000字上限
                            dep_outputs.append(f"[{dep_id}] {_out}")
                if dep_outputs:
                    prompt = (
                        f"{prompt}\n\n## 前置任务结果（已压缩，不要重复获取这些信息）\n"
                        + "\n".join(dep_outputs)
                    )

            async with semaphore:
                profile = task.agent or AgentProfile.GENERAL
                result = await spawn_subagent(
                    task_description=prompt,
                    profile=profile,
                    parent_id=parent_id,
                    model=model,
                )
                return OrchestrationResult(
                    task_id=tid,
                    success=result["success"],
                    output=result.get("output", ""),
                    error=result.get("error", ""),
                )

        level_results = await asyncio.gather(
            *[run_task(tid) for tid in level],
            return_exceptions=True,
        )

        for i, r in enumerate(level_results):
            tid = level[i]
            if isinstance(r, Exception):
                all_results[tid] = OrchestrationResult(
                    task_id=tid, success=False, error=str(r)
                )
            else:
                all_results[tid] = r

    results = list(all_results.values())
    completed = sum(1 for r in results if r.success)
    total = len(results)

    logger.info(f"编排完成: {completed}/{total} 成功")

    return {
        "success": completed > 0,
        "results": [
            {"id": r.task_id, "success": r.success,
             "output": r.output[:2000], "error": r.error}
            for r in results
        ],
        "total": total,
        "completed": completed,
    }


# ════════════════════════════════════════════════════════════════
# 便捷函数 — 对外接口
# ════════════════════════════════════════════════════════════════

async def task(
    description: str,
    agent: str = "general",
    background: bool = False,
    parent_id: str = "",
    model: str = "",
) -> Dict[str, Any]:
    """OpenCode 风格 task 工具 — 生成子代理

    Args:
        description: 3-5 词简短描述
        agent: 代理类型 (explore/build/general/analyze)
        background: 是否后台执行
        parent_id: 父会话 ID

    返回格式与 OpenCode task 工具一致:
        <task id="..." state="completed|running|error">
          <summary>...</summary>
          <task_result>...</task_result>
        </task>
    """
    profile = AgentProfile(agent) if agent in AgentProfile.__members__.values() else AgentProfile.GENERAL

    if background:
        session_id = await spawn_background(
            task_description=description,
            profile=profile,
            parent_id=parent_id,
            model=model,
        )
        return {
            "success": True,
            "output": (
                f"<task id=\"{session_id}\" state=\"running\">\n"
                f"<summary>后台任务已启动: {description[:100]}</summary>\n"
                f"<task_result>子代理正在后台执行，请勿重复此工作。</task_result>\n"
                f"</task>"
            ),
        }

    result = await spawn_subagent(
        task_description=description,
        profile=profile,
        parent_id=parent_id,
        model=model,
    )

    session_id = result["session_id"]
    state = "completed" if result["success"] else "error"
    output = result.get("output", result.get("error", ""))
    summary = output[:200] if output else "无输出"
    _artifacts = result.get("artifacts_dir", "")

    _artifact_note = ""
    if _artifacts and result["success"]:
        _artifact_note = f"\n<artifacts>{_artifacts}</artifacts>\n"

    return {
        "success": result["success"],
        "artifacts_dir": _artifacts,
        "output": (
            f"<task id=\"{session_id}\" state=\"{state}\">\n"
            f"<summary>{summary}</summary>\n"
            f"<task_result>\n{output}\n</task_result>\n"
            f"{_artifact_note}"
            f"</task>"
        ),
    }


async def orchestrate(
    tasks: List[Dict[str, Any]],
    parent_id: str = "",
    model: str = "",
    max_concurrent: int = 5,
) -> Dict[str, Any]:
    """OpenCode 风格 orchestrate 工具 — DAG 并行编排

    返回格式与 OpenCode orchestrate 工具一致:
        <orchestration-results>
          <task id="..." state="...">...</task>
        </orchestration-results>
    """
    result = await orchestrate_subagents(
        tasks=tasks,
        parent_id=parent_id,
        model=model,
        max_concurrent=max_concurrent,
    )

    if not result["success"] and result.get("error"):
        return {"success": False, "output": f"<orchestration_error>{result['error']}</orchestration_error>"}

    lines = ["<orchestration-results>"]
    for r in result["results"]:
        lines.append(
            f"  <task id=\"{r['id']}\" "
            f"state=\"{'completed' if r['success'] else 'error'}\">"
            f"{r.get('output', r.get('error', ''))[:1000]}"
            f"</task>"
        )
    lines.append(f"  <summary>{result['completed']}/{result['total']} 任务完成</summary>")
    lines.append("</orchestration-results>")

    return {"success": result["success"], "output": "\n".join(lines)}
