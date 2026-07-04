"""V2 统一单 Agent 入口 — V1 LeaderAgent + OpenCode 子代理能力

取代 react_core.run_react() 作为 V2 单 Agent 的统一入口。

模式:
  - "leader": V1 LeaderAgent 模式（队长+Worker，think→delegate→observe）
  - "react":  纯 ReAct 直通模式（兼容旧 run_react，无 Worker 池）
  - "unified": LeaderAgent + subagent 可选项

Web 端和 CLI 端共用此入口。
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ROUNDS = 10
_DEFAULT_WORKER_COUNT = 3

# ── 全局 V1LeaderPool 单例 ──
_pool: Optional[Any] = None
_pool_lock = asyncio.Lock()


async def _get_global_pool():
    """获取全局 V1LeaderPool（懒加载+锁保护）"""
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                from .unified.leader import V1LeaderPool
                _pool = V1LeaderPool()
                await _pool._ensure_tool_registry()
                _pool._load_agent_configs()
                logger.info("V1LeaderPool 全局单例已初始化")
    return _pool


# ════════════════════════════════════════════════════════════════
# run_unified — 统一 Agent 执行入口
# ════════════════════════════════════════════════════════════════

async def run_unified(
    task_description: str,
    max_rounds: int = 0,
    model: str = "",
    personality_prompt: str = "",
    agent: Any = None,
    allowed_tools: Optional[List[str]] = None,
    disallowed_tools: Optional[List[str]] = None,
    tool_preference: Optional[set] = None,
    user_id: str = "",
    mode: str = "leader",
    worker_count: int = _DEFAULT_WORKER_COUNT,
    skill_id: Optional[str] = None,
) -> dict:
    """统一 Agent 执行入口

    Args:
        task_description: 任务描述
        max_rounds: 最大轮次（0=默认值）
        model: 模型覆盖
        personality_prompt: 角色提示词
        agent: WorkAgent 引用（CLI 端传入）
        allowed_tools: 工具白名单
        disallowed_tools: 工具黑名单
        tool_preference: 优先工具
        user_id: 用户 ID（用于记忆）
        mode: "leader" | "react" | "unified"
        worker_count: Worker 数量（leader/unified 模式）
        skill_id: Skill 覆盖（None=自动匹配）

    Returns:
        {"success": bool, "answer": str, "rounds": int, "error": str}
    """
    if max_rounds == 0:
        max_rounds = _DEFAULT_MAX_ROUNDS

    mode = mode or "react"

    if mode == "react":
        return await _run_react_mode(
            task_description, max_rounds, model,
            personality_prompt, agent, allowed_tools, disallowed_tools,
            tool_preference,
        )

    if mode in ("leader", "unified"):
        return await _run_leader_mode(
            task_description, max_rounds, model,
            personality_prompt, agent,
            user_id, worker_count, skill_id,
            with_subagent=(mode == "unified"),
        )

    raise ValueError(f"未知模式: {mode}，支持: leader, react, unified")


# ════════════════════════════════════════════════════════════════
# Leader 模式 — V1 LeaderAgent + Worker 池
# ════════════════════════════════════════════════════════════════

async def _run_leader_mode(
    task: str,
    max_rounds: int,
    model: str = "",
    personality_prompt: str = "",
    agent: Any = None,
    user_id: str = "",
    worker_count: int = _DEFAULT_WORKER_COUNT,
    skill_id: Optional[str] = None,
    with_subagent: bool = False,
) -> dict:
    """V1 LeaderAgent 模式：队长分解任务 → Worker 执行 → 队长分析 → 循环"""
    from .unified.leader import LeaderAgent
    from .unified.skill_router import V1SkillRouter

    pool = await _get_global_pool()
    start_time = time.time()

    # Skill 匹配
    if not skill_id:
        try:
            router = V1SkillRouter()
            skill_id = await router.match(task)
            logger.info(f"Skill 匹配: {skill_id}")
        except Exception as e:
            logger.debug(f"Skill 匹配失败: {e}")
            skill_id = "general"

    # 获取 Worker
    workers = []
    for _ in range(min(worker_count, 5)):
        w = await pool.get_worker(skill_id=skill_id)
        if w:
            workers.append(w)

    if not workers or len(workers) < 2:
        # 降级：创建临时团队
        leader, workers = await pool.create_team(
            worker_count=worker_count, max_workers=worker_count
        )
        is_temp_team = True
    else:
        # 创建临时队长
        leader = LeaderAgent(
            name=f"leader_{int(time.time())}",
            max_workers=len(workers),
            tool_registry=pool._tool_registry,
        )
        leader._pool = pool
        is_temp_team = False

    # 设置 user_id
    leader.user_id = user_id
    for w in workers:
        w.user_id = user_id

    # 注入 personality
    if personality_prompt and agent:
        try:
            if hasattr(agent, 'personality') and not agent.personality:
                agent.personality = personality_prompt
        except Exception:
            pass

    print(f"    \033[1;36m👥 队长模式: {len(workers)} 个 Worker (skill={skill_id})\033[0m")

    try:
        result = await leader.supervise_task(
            task_description=task,
            workers=workers,
            active_count=len(workers),
            max_rounds=max_rounds,
            skill_id=skill_id,
        )
    finally:
        if is_temp_team:
            await pool.discard(workers + [leader])

    elapsed = time.time() - start_time
    success = result.get("success", False)
    react_rounds = result.get("rounds", 0)

    # 提取最终答案
    final_answer = ""
    for r in result.get("results", []):
        rdata = r.get("result", {})
        if isinstance(rdata, dict):
            summary = rdata.get("tool_result_summary", rdata.get("content", ""))
            if summary:
                final_answer = summary
                break

    if not final_answer:
        final_answer = "任务已完成"
        if not success:
            error_msgs = []
            for r in result.get("results", []):
                if not r.get("success"):
                    rdata = r.get("result", {})
                    if isinstance(rdata, dict):
                        err = rdata.get("error", "")
                        if err:
                            error_msgs.append(err[:200])
            if error_msgs:
                final_answer = "; ".join(error_msgs)

    print(f"    \033[1;32m{'✅' if success else '❌'} {react_rounds}轮 · {elapsed:.1f}s\033[0m")

    # Web 端兼容：同时返回顶层字段和 agent_result
    return {
        "success": success,
        "answer": final_answer,
        "rounds": react_rounds,
        "react_rounds": react_rounds,
        # Web 兼容字段
        "results": result.get("results", []),
        "total_subtasks": result.get("total_subtasks", 0),
        "react_history": result.get("react_history", []),
        # ──
        "error": "" if success else "部分子任务失败",
        "iterations": react_rounds,
        "tool_results": [],
        "agent_result": result,
    }


# ════════════════════════════════════════════════════════════════
# ReAct 模式 — 纯 ReAct 直通（兼容旧 run_react）
# ════════════════════════════════════════════════════════════════

async def _run_react_mode(
    task: str,
    max_rounds: int,
    model: str = "",
    personality_prompt: str = "",
    agent: Any = None,
    allowed_tools: Optional[List[str]] = None,
    disallowed_tools: Optional[List[str]] = None,
    tool_preference: Optional[set] = None,
) -> dict:
    """纯 ReAct 模式 — 委托给 react_core.run_react()，启用 SubAgent 工具"""
    # 注册 SubAgent 工具到 ToolRegistry（幂等）
    try:
        from .subagent.tool_handler import register_subagent_tools
        register_subagent_tools()
    except Exception as e:
        logger.debug(f"SubAgent 工具注册失败: {e}")

    from .react_core import run_react
    return await run_react(
        task_description=task,
        max_rounds=max_rounds,
        model=model,
        personality_prompt=personality_prompt,
        agent=agent,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        tool_preference=tool_preference,
    )


# ════════════════════════════════════════════════════════════════
# Subagent 集成便捷接口
# ════════════════════════════════════════════════════════════════

async def delegate_to_subagent(
    task_description: str,
    profile: str = "general",
    background: bool = False,
    model: str = "",
) -> Dict[str, Any]:
    """从统一 Agent 中委派子代理执行任务

    在 Leader 的 process_results 阶段调用，将复杂子任务交给专门的子代理。
    """
    from .subagent.spawn import task as subagent_task
    return await subagent_task(
        description=task_description,
        agent=profile,
        background=background,
        model=model,
    )


async def parallel_delegate(
    tasks: List[Dict[str, Any]],
    model: str = "",
    max_concurrent: int = 5,
) -> Dict[str, Any]:
    """并行委派多个子代理（DAG 编排）

    tasks 格式: [{"id": str, "prompt": str, "agent": str, "depends_on": [str]}]
    """
    from .subagent.spawn import orchestrate as orch_run
    return await orch_run(
        tasks=tasks,
        model=model,
        max_concurrent=max_concurrent,
    )
