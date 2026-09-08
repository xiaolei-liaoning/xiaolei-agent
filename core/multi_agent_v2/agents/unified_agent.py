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
    session_id: str = "",  # 修复(B): 跨回合记忆——透传给 run_react
) -> dict:
    """统一 Agent 执行入口 — 修复 #003

    修复 #003: 4 个被忽略参数（user_id / mode / worker_count / skill_id）现在显式标注状态：
      - user_id     → 透传给 _run_react_mode，由 react_core 写入 context.user_id
      - mode        → 仍然仅 "react" 有效，其他值 logger.warning 提示后降级
      - worker_count → 已弃用，V2 unified_agent 不再支持多 worker（与 subagent 协作不同）
      - skill_id    → 已弃用，统一走 allowed_tools/disallowed_tools

    Args:
        task_description: 任务描述
        max_rounds: 最大轮次（0=默认值）
        model: 模型覆盖
        personality_prompt: 角色提示词
        agent: WorkAgent 引用（CLI 端传入）
        allowed_tools: 工具白名单
        disallowed_tools: 工具黑名单
        tool_preference: 优先工具
        user_id: 用户 ID（用于记忆 + 反馈归因）
        mode: 保留参数，仅 "react" 有效
        worker_count: 已弃用（保留签名以兼容 V1 调用方）
        skill_id: 已弃用

    Returns:
        {"success": bool, "answer": str, "rounds": int, "error": str}
    """
    if max_rounds == 0:
        max_rounds = _DEFAULT_MAX_ROUNDS

    # 修复 #003: mode 仅 react 有效，其他值显式警告
    if mode != "react":
        logger.warning(
            f"run_unified: mode={mode!r} 已被废弃，仅 'react' 有效。"
            f"本次调用将降级到 react 模式。"
        )
        mode = "react"

    # worker_count 和 skill_id 显式标注弃用（用 logging 而非静默）
    if worker_count != 0:
        logger.debug(f"run_unified: worker_count={worker_count} 已弃用，V2 不再支持多 worker")
    if skill_id is not None:
        logger.debug(f"run_unified: skill_id={skill_id!r} 已弃用，请用 allowed_tools/disallowed_tools")

    return await _run_react_mode(
        task_description, max_rounds, model,
        personality_prompt, agent, allowed_tools, disallowed_tools,
        tool_preference,
        user_id=user_id,  # 修复 #003: 透传
        session_id=session_id,  # 修复(B): 跨回合记忆
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
    user_id: str = "",  # 修复 #003: 加 user_id 透传
    session_id: str = "",  # 修复(B): 跨回合记忆
) -> dict:
    """纯 ReAct 模式 — 委托给 react_core.run_react()，启用 SubAgent 工具"""
    from .subagent.tool_handler import register_subagent_tools
    try:
        register_subagent_tools()
    except Exception as e:
        # 修复 #004: 静默降级 → 升级到 logger.error + 让外层处理
        # 不再 raise 以保持向后兼容，但至少用户能看到日志
        logger.error(f"SubAgent 工具注册失败（降级到单 agent 模式）: {e}", exc_info=True)

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
        user_id=user_id,  # 修复 #003: 透传
        session_id=session_id,  # 修复(B): 跨回合记忆
    )
