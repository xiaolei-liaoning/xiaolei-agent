"""历史记录相关API路由

包含：
- GET /api/history - 获取聊天历史
- GET /api/history/session/{session_id} - 获取会话历史
- GET /api/history/{history_id} - 获取单条历史记录详情
- DELETE /api/history/{history_id} - 删除单条历史记录
- DELETE /api/history - 清空聊天历史
- GET /api/history/stats - 获取聊天历史统计
- GET /api/task-logs - 获取任务日志
- GET /api/task-logs/stats - 任务统计
"""

import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["history"])


# ---------------------------------------------------------------------------
# API 端点：聊天历史
# ---------------------------------------------------------------------------
@router.get("/history", summary="获取聊天历史")
async def get_chat_history(
    user_id: int = 1,
    character_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by_session: bool = False,
) -> Dict[str, Any]:
    """获取用户聊天历史记录，支持分页、搜索、筛选和按会话分组。

    Args:
        user_id: 用户ID
        character_id: 角色ID筛选（可选）
        limit: 每页条数，最大 200
        offset: 偏移量
        search: 搜索关键词（在内容中搜索）
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        group_by_session: 是否按会话分组返回
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"history": [], "total": 0}
    
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    
    try:
        from core.database import get_session, ChatHistory
        from sqlalchemy import and_, desc
        session = get_session()
        try:
            # 构建基础查询
            query = session.query(ChatHistory).filter_by(user_id=user_id)
            
            # 角色筛选
            if character_id:
                query = query.filter_by(character_id=character_id)
            
            # 关键词搜索
            if search:
                query = query.filter(ChatHistory.content.like(f"%{search}%"))
            
            # 日期范围筛选
            if start_date:
                try:
                    from datetime import datetime as dt
                    start_dt = dt.strptime(start_date, "%Y-%m-%d")
                    query = query.filter(ChatHistory.created_at >= start_dt)
                except ValueError:
                    pass
            
            if end_date:
                try:
                    from datetime import datetime as dt, timedelta
                    end_dt = dt.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    query = query.filter(ChatHistory.created_at < end_dt)
                except ValueError:
                    pass
            
            total = query.count()
            
            # 按会话分组模式
            if group_by_session:
                records = query.order_by(desc(ChatHistory.created_at)).all()
                
                sessions = {}
                for r in records:
                    session_key = f"{r.character_id}"
                    
                    if session_key not in sessions:
                        sessions[session_key] = {
                            "session_id": session_key,
                            "character_id": r.character_id,
                            "messages": [],
                            "first_message_time": r.created_at,
                            "last_message_time": r.created_at,
                            "message_count": 0
                        }
                    
                    sessions[session_key]["messages"].append({
                        "id": r.id,
                        "role": r.role,
                        "content": r.content,
                        "tool_call": r.tool_call,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    })
                    sessions[session_key]["message_count"] += 1
                    
                    if r.created_at < sessions[session_key]["first_message_time"]:
                        sessions[session_key]["first_message_time"] = r.created_at
                    if r.created_at > sessions[session_key]["last_message_time"]:
                        sessions[session_key]["last_message_time"] = r.created_at
                
                session_list = list(sessions.values())
                session_list.sort(key=lambda x: x["last_message_time"], reverse=True)
                
                paged_sessions = session_list[offset:offset+limit]
                
                formatted_sessions = []
                for s in paged_sessions:
                    preview_msg = ""
                    for msg in s["messages"]:
                        if msg["role"] == "user":
                            preview_msg = msg["content"][:100]
                            break
                    
                    formatted_sessions.append({
                        "session_id": s["session_id"],
                        "character_id": s["character_id"],
                        "preview": preview_msg,
                        "message_count": s["message_count"],
                        "first_message_time": s["first_message_time"].isoformat() if s["first_message_time"] else None,
                        "last_message_time": s["last_message_time"].isoformat() if s["last_message_time"] else None,
                        "messages": s["messages"][:10],
                    })
                
                return {
                    "sessions": formatted_sessions,
                    "total": len(session_list),
                    "limit": limit,
                    "offset": offset,
                }
            
            # 普通模式：返回单条消息
            records = (
                query.order_by(desc(ChatHistory.created_at))
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "history": [
                    {
                        "id": r.id,
                        "character_id": r.character_id,
                        "role": r.role,
                        "content": r.content,
                        "tool_call": r.tool_call,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in reversed(records)
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("获取聊天历史失败: %s", e)
        return {"history": [], "total": 0, "error": str(e)}


@router.get("/history/session/{session_id}", summary="获取会话历史")
async def get_session_history(
    session_id: str,
    user_id: int = 1,
) -> Dict[str, Any]:
    """获取指定会话的聊天历史记录。

    Args:
        session_id: 会话ID（格式：character_id）
        user_id: 用户ID
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"messages": []}
    
    try:
        from core.database import get_session, ChatHistory
        from sqlalchemy import desc
        session = get_session()
        try:
            character_id = session_id
            
            records = (
                session.query(ChatHistory)
                .filter_by(user_id=user_id, character_id=character_id)
                .order_by(desc(ChatHistory.created_at))
                .limit(100)
                .all()
            )
            
            messages = [
                {
                    "id": r.id,
                    "role": r.role,
                    "content": r.content,
                    "tool_call": r.tool_call,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in reversed(records)
            ]
            
            return {"messages": messages}
        finally:
            session.close()
    except Exception as e:
        logger.error("获取会话历史失败: %s", e)
        return {"messages": []}


@router.get("/history/{history_id}", summary="获取单条历史记录详情")
async def get_chat_history_detail(
    history_id: int,
    user_id: int = 1,
) -> Dict[str, Any]:
    """获取单条聊天记录的详细信息。

    Args:
        history_id: 历史记录ID
        user_id: 用户ID（用于权限验证）
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"detail": None}
    
    try:
        from core.database import get_session, ChatHistory
        session = get_session()
        try:
            record = session.query(ChatHistory).filter_by(
                id=history_id,
                user_id=user_id
            ).first()
            
            if not record:
                return {"detail": None, "error": "记录不存在"}
            
            return {
                "detail": {
                    "id": record.id,
                    "user_id": record.user_id,
                    "character_id": record.character_id,
                    "role": record.role,
                    "content": record.content,
                    "tool_call": record.tool_call,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                }
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("获取历史记录详情失败: %s", e)
        return {"detail": None, "error": str(e)}


@router.delete("/history/{history_id}", summary="删除单条历史记录")
async def delete_chat_history_item(
    history_id: int,
    user_id: int = 1,
) -> Dict[str, Any]:
    """删除单条聊天记录。

    Args:
        history_id: 历史记录ID
        user_id: 用户ID（用于权限验证）
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    
    try:
        from core.database import get_session, ChatHistory
        session = get_session()
        try:
            record = session.query(ChatHistory).filter_by(
                id=history_id,
                user_id=user_id
            ).first()
            
            if not record:
                return {"success": False, "detail": "记录不存在"}
            
            session.delete(record)
            session.commit()
            logger.info("删除聊天记录: history_id=%d, user_id=%d", history_id, user_id)
            return {"success": True, "deleted_id": history_id}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("删除聊天记录失败: %s", e)
        return {"success": False, "detail": str(e)}


@router.delete("/history", summary="清空聊天历史")
async def clear_chat_history(
    user_id: int = 1,
    character_id: Optional[str] = None,
) -> Dict[str, Any]:
    """清空用户聊天历史。可按角色筛选删除。

    Args:
        user_id: 用户ID
        character_id: 角色ID筛选（可选，为空则清空全部）
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    
    try:
        from core.database import get_session, ChatHistory
        session = get_session()
        try:
            query = session.query(ChatHistory).filter_by(user_id=user_id)
            if character_id:
                query = query.filter_by(character_id=character_id)
            deleted = query.delete()
            session.commit()
            logger.info("清空聊天历史: user_id=%d, character_id=%s, deleted=%d",
                        user_id, character_id, deleted)
            return {"success": True, "deleted": deleted}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("清空聊天历史失败: %s", e)
        return {"success": False, "detail": str(e)}


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
        from core.database import get_session, ChatHistory
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
# API 端点：任务日志
# ---------------------------------------------------------------------------
@router.get("/task-logs", summary="获取任务日志")
async def get_task_logs(
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """获取任务执行日志，支持多维筛选和分页。

    Args:
        user_id: 按用户筛选（可选）
        status: 按状态筛选 success/failed（可选）
        task_type: 按任务类型（技能名）筛选（可选）
        limit: 每页条数，最大 200
        offset: 偏移量
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"logs": [], "total": 0}
    
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    
    try:
        from core.database import get_session, TaskLog
        session = get_session()
        try:
            query = session.query(TaskLog)
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            if status:
                query = query.filter_by(status=status)
            if task_type:
                query = query.filter_by(task_type=task_type)
            total = query.count()
            logs = (
                query.order_by(TaskLog.id.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                "logs": [
                    {
                        "id": lg.id,
                        "user_id": lg.user_id,
                        "task_type": lg.task_type,
                        "status": lg.status,
                        "duration": lg.duration,
                        "params": lg.params,
                        "result": lg.result,
                        "created_at": lg.created_at.isoformat() if lg.created_at else None,
                    }
                    for lg in logs
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("获取任务日志失败: %s", e)
        return {"logs": [], "total": 0, "error": str(e)}


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
        from core.database import get_session, TaskLog, func
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
