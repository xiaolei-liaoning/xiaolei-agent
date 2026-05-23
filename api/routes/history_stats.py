"""历史记录和任务日志统计相关API路由

包含：
- GET /api/history/stats - 获取聊天历史统计
- GET /api/task-logs/stats - 任务统计
"""

import logging
from typing import Dict, Any, Optional

from api.routes.history import router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API 端点：聊天历史统计
# ---------------------------------------------------------------------------
@router.get("/history/stats", summary="获取聊天历史统计")
async def get_chat_history_stats(
    user_id: int = 1,
) -> Dict[str, Any]:
    """获取用户聊天历史的统计信息。

    Args:
        user_id: 用户ID

    Returns:
        包含总消息数、各角色消息数、时间分布等统计信息
    """
    from core.handlers import _db_initialized

    if not _db_initialized:
        return {"stats": {}}

    try:
        from core.infrastructure.database import get_session, ChatHistory
        from sqlalchemy import func
        session = get_session()
        try:
            total_count = session.query(func.count(ChatHistory.id)).filter_by(
                user_id=user_id
            ).scalar() or 0

            user_count = session.query(func.count(ChatHistory.id)).filter_by(
                user_id=user_id,
                role="user"
            ).scalar() or 0

            assistant_count = session.query(func.count(ChatHistory.id)).filter_by(
                user_id=user_id,
                role="assistant"
            ).scalar() or 0

            character_stats = session.query(
                ChatHistory.character_id,
                func.count(ChatHistory.id).label('count')
            ).filter_by(
                user_id=user_id
            ).group_by(
                ChatHistory.character_id
            ).all()

            character_breakdown = {
                row.character_id: row.count
                for row in character_stats
            }

            from datetime import datetime, timedelta
            seven_days_ago = datetime.now() - timedelta(days=7)

            daily_stats = session.query(
                func.date(ChatHistory.created_at).label('date'),
                func.count(ChatHistory.id).label('count')
            ).filter(
                ChatHistory.user_id == user_id,
                ChatHistory.created_at >= seven_days_ago
            ).group_by(
                func.date(ChatHistory.created_at)
            ).order_by(
                func.date(ChatHistory.created_at)
            ).all()

            daily_breakdown = {
                str(row.date): row.count
                for row in daily_stats
            }

            earliest = session.query(func.min(ChatHistory.created_at)).filter_by(
                user_id=user_id
            ).scalar()

            latest = session.query(func.max(ChatHistory.created_at)).filter_by(
                user_id=user_id
            ).scalar()

            return {
                "stats": {
                    "total_messages": total_count,
                    "user_messages": user_count,
                    "assistant_messages": assistant_count,
                    "character_breakdown": character_breakdown,
                    "daily_trend": daily_breakdown,
                    "earliest_message": earliest.isoformat() if earliest else None,
                    "latest_message": latest.isoformat() if latest else None,
                    "conversation_days": len(daily_breakdown),
                }
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("获取聊天历史统计失败: %s", e)
        return {"stats": {}, "error": str(e)}


# ---------------------------------------------------------------------------
# API 端点：任务日志统计
# ---------------------------------------------------------------------------
@router.get("/task-logs/stats", summary="任务统计")
async def get_task_stats(user_id: Optional[int] = None) -> Dict[str, Any]:
    """获取任务执行统计（成功率、各技能调用次数等）。

    Args:
        user_id: 按用户筛选（可选）
    """
    from core.handlers import _db_initialized

    if not _db_initialized:
        return {"total": 0, "success": 0, "failed": 0, "by_type": {}}

    try:
        from core.infrastructure.database import get_session, TaskLog, func
        session = get_session()
        try:
            query = session.query(TaskLog)
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            total = query.count()
            success = query.filter_by(status="success").count()
            failed = query.filter_by(status="failed").count()

            by_type = {}
            type_groups = session.query(
                TaskLog.task_type, func.count(TaskLog.id)
            )
            if user_id is not None:
                type_groups = type_groups.filter_by(user_id=user_id)
            type_groups = type_groups.group_by(TaskLog.task_type).all()
            for task_type, count in type_groups:
                if task_type:
                    by_type[task_type] = count

            return {
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": round(success / total * 100, 1) if total > 0 else 0,
                "by_type": by_type,
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("获取任务统计失败: %s", e)
        return {"total": 0, "error": str(e)}
