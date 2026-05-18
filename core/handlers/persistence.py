"""数据持久化辅助函数"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def save_chat_history(
    user_id: int,
    character_id: str,
    role: str,
    content: str,
    tool_call: Optional[Dict[str, Any]] = None,
    db_initialized: bool = False
) -> Optional[int]:
    """保存聊天记录到 MySQL，返回消息ID。

    Args:
        user_id: 用户ID
        character_id: 角色ID
        role: 角色 (user / assistant)
        content: 消息内容
        tool_call: 工具调用信息（可选）
        db_initialized: 数据库是否已初始化

    Returns:
        消息ID，失败返回 None
    """
    if not db_initialized:
        return None
    
    if not content or not content.strip():
        logger.debug("空内容不保存到聊天历史")
        return None
    
    try:
        from ..infrastructure.database import get_session, ChatHistory
        session = get_session()
        try:
            record = ChatHistory(
                user_id=user_id,
                character_id=character_id,
                role=role,
                content=content[:5000],
                tool_call=tool_call,
                user_message=content if role == "user" else "",
                ai_response=content if role == "assistant" else "",
            )
            session.add(record)
            session.commit()
            return record.id
        finally:
            session.close()
    except Exception as e:
        logger.debug("保存聊天历史失败: %s", e)
        return None


def save_task_log(
    user_id: int,
    task_type: str,
    success: bool,
    params: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    duration: float = 0.0,
    db_initialized: bool = False
) -> None:
    """异步保存任务日志到 MySQL（失败静默）。

    Args:
        user_id: 用户ID
        task_type: 任务类型（技能名）
        success: 是否成功
        params: 任务参数
        result: 任务结果
        duration: 耗时（秒）
        db_initialized: 数据库是否已初始化
    """
    if not db_initialized:
        return
    try:
        from ..infrastructure.database import get_session, TaskLog
        session = get_session()
        try:
            log = TaskLog(
                user_id=user_id,
                task_type=task_type,
                status="success" if success else "failed",
                params=params,
                result=_safe_json(result),
                duration=round(duration, 3),
            )
            session.add(log)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        logger.debug("保存任务日志失败: %s", e)


def _safe_json(data: Any) -> Optional[Dict[str, Any]]:
    """安全地序列化数据为 JSON 可存储的字典。"""
    if data is None:
        return None
    try:
        if isinstance(data, dict):
            return {
                str(k): str(v)[:2000] if not isinstance(v, (int, float, bool, type(None))) else v
                for k, v in data.items()
            }
        return {"raw": str(data)[:2000]}
    except Exception:
        return {"raw": "unserializable"}


def get_system_prompt(agent_id: str, db_initialized: bool = False) -> str:
    """获取Agent的 system_prompt。优先从数据库读取。

    Args:
        agent_id: Agent ID
        db_initialized: 数据库是否已初始化

    Returns:
        系统提示词字符串
    """
    _builtin_prompts: Dict[str, str] = {
        "default": "你是小雷版小龙虾AI助手，友好、专业、高效。简洁回答用户问题。",
        "first_love": "你是温柔体贴的初恋角色，说话温柔，善解人意。",
        "bestfriend": "你是用户的知心闺蜜，可以畅所欲言。",
        "goddess": "你是高冷女神，说话简洁有力。",
        "libai": "你是诗仙李白，性格豪放，说话常带诗意。",
    }

    if not db_initialized:
        return _builtin_prompts.get(agent_id, _builtin_prompts["default"])

    try:
        from ..infrastructure.database import get_session, Character
        session = get_session()
        try:
            character = session.query(Character).filter_by(
                character_id=agent_id
            ).first()
            if character and character.system_prompt:
                return character.system_prompt
        finally:
            session.close()
    except Exception as e:
        logger.warning("读取Agent system_prompt 失败: %s", e)

    return _builtin_prompts.get(agent_id, _builtin_prompts["default"])
