"""V2 统一入口 — 委托给 react_core.run_react()

Web 端和 CLI 端共用此入口。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ROUNDS = 10


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
    mode: str = "react",
    worker_count: int = 0,
    skill_id: Optional[str] = None,
) -> dict:
    """统一 Agent 执行入口 — 仅支持 mode="react"（其他模式已废弃）

    Args:
        task_description: 任务描述
        max_rounds: 最大轮次（0=默认值）
        model: 模型覆盖
        personality_prompt: 角色提示词
        agent: WorkAgent 引用（CLI 端传入）
        allowed_tools: 工具白名单
        disallowed_tools: 工具黑名单
        tool_preference: 优先工具
        user_id: 用户 ID（用于记忆，暂未使用）
        mode: 保留参数，仅 "react" 有效
        worker_count: 保留参数，已忽略
        skill_id: 保留参数，已忽略

    Returns:
        {"success": bool, "answer": str, "rounds": int, "error": str}
    """
    if max_rounds == 0:
        max_rounds = _DEFAULT_MAX_ROUNDS

    return await _run_react_mode(
        task_description, max_rounds, model,
        personality_prompt, agent, allowed_tools, disallowed_tools,
        tool_preference,
    )


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
    from .subagent.tool_handler import register_subagent_tools
    try:
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
