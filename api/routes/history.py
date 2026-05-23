"""历史记录相关API路由

包含：
- GET /api/history - 获取聊天历史
- GET /api/history/session/{session_id} - 获取会话历史
- GET /api/history/{history_id} - 获取单条历史记录详情
- DELETE /api/history/{history_id} - 删除单条历史记录
- DELETE /api/history - 清空聊天历史
- GET /api/task-logs - 获取任务日志
- GET /api/short-term-memory - 查看短期记忆内容
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["history"])

# 语义搜索缓存
_semantic_cache = {}

async def _semantic_search(user_id: int, query: str, limit: int = 20) -> list:
    """语义搜索 - 使用向量相似度匹配
    
    Args:
        user_id: 用户ID
        query: 搜索查询
        limit: 返回数量限制
    
    Returns:
        匹配的消息列表（按相似度排序）
    """
    try:
        # 尝试使用 sentence-transformers 进行语义匹配
        try:
            from sentence_transformers import SentenceTransformer, util
            import torch
            
            # 加载模型
            model = SentenceTransformer('all-MiniLM-L6-v2')
            
            # 获取用户所有消息内容
            from core.infrastructure.database import get_session, ChatHistory
            session = get_session()
            try:
                records = session.query(ChatHistory).filter_by(user_id=user_id).all()
                if not records:
                    return []
                
                # 编码查询和所有消息
                query_embedding = model.encode(query, convert_to_tensor=True)
                message_embeddings = model.encode(
                    [r.content for r in records], 
                    convert_to_tensor=True
                )
                
                # 计算相似度
                cos_scores = util.cos_sim(query_embedding, message_embeddings)[0]
                
                # 排序并返回前N个
                top_results = torch.topk(cos_scores, k=min(limit, len(records)))
                
                results = []
                for score, idx in zip(top_results.values, top_results.indices):
                    record = records[idx]
                    results.append({
                        "id": record.id,
                        "content": record.content,
                        "similarity": float(score),
                        "role": record.role,
                        "character_id": record.character_id,
                    })
                
                return results
            finally:
                session.close()
                
        except ImportError:
            # 如果没有 sentence-transformers，回退到关键词匹配
            logger.debug("sentence-transformers not available, falling back to keyword search")
            return []
            
    except Exception as e:
        logger.error("语义搜索失败: %s", e)
        return []


# ---------------------------------------------------------------------------
# API 端点：短期记忆
# ---------------------------------------------------------------------------
@router.get("/short-term-memory", summary="查看短期记忆内容")
async def get_short_term_memory(
    user_id: str = "1",
    depth: int = 2,
) -> Dict[str, Any]:
    """查看短期记忆内容
    
    Args:
        user_id: 用户ID
        depth: 展开深度 (1:功能层, 2:文本层, 3:段落层)
    
    Returns:
        短期记忆内容和统计信息
    """
    from core.handlers import short_term_memory
    
    # 获取统计信息
    stats = short_term_memory.get_stats()
    
    # 获取上下文内容（支持四层深度）
    context_messages = short_term_memory.get_context(user_id, depth=depth)
    
    # 获取队列节点详情
    queue_nodes = []
    for node_id in list(short_term_memory.queue):
        if node_id in short_term_memory.nodes:
            node = short_term_memory.nodes[node_id]
            queue_nodes.append({
                "node_id": node_id,
                "node_type": node.node_type,
                "content": node.content[:200],
                "summary": node.summary[:100] if node.summary else None,
                "children_count": len(node.children)
            })
    
    # 获取完整的树结构（包含所有层级）
    tree_structure = _build_tree_structure(user_id, depth)
    
    return {
        "success": True,
        "stats": stats,
        "context_messages": context_messages,
        "queue_nodes": queue_nodes,
        "tree_structure": tree_structure
    }


def _build_tree_structure(user_id: str, depth: int = 4) -> Dict[str, Any]:
    """构建完整的树结构
    
    Args:
        user_id: 用户ID
        depth: 展开深度 (1-4)
    
    Returns:
        树结构字典
    """
    from core.handlers import short_term_memory
    
    global_root_id = f"root_{user_id}"
    if global_root_id not in short_term_memory.nodes:
        return {"error": "No root node found"}
    
    def build_node_tree(node_id: str, current_depth: int) -> Optional[Dict[str, Any]]:
        """递归构建树节点"""
        if current_depth > depth or node_id not in short_term_memory.nodes:
            return None
        
        node = short_term_memory.nodes[node_id]
        result = {
            "node_id": node_id,
            "node_type": node.node_type,
            "content": node.content[:200] if len(node.content) > 200 else node.content,
            "summary": node.summary[:100] if node.summary and len(node.summary) > 100 else node.summary,
            "parent_id": node.parent_id,
            "children_count": len(node.children)
        }
        
        # 递归添加子节点
        if node.children and current_depth < depth:
            result["children"] = []
            for child_id in node.children:
                child_tree = build_node_tree(child_id, current_depth + 1)
                if child_tree:
                    result["children"].append(child_tree)
        
        return result
    
    # 从根节点开始构建
    root_node = short_term_memory.nodes[global_root_id]
    tree = {
        "node_id": global_root_id,
        "node_type": root_node.node_type,
        "content": root_node.content,
        "children_count": len(root_node.children),
        "children": []
    }
    
    # 添加功能层子节点
    for child_id in root_node.children:
        child_tree = build_node_tree(child_id, 2)
        if child_tree:
            tree["children"].append(child_tree)
    
    return tree


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
    semantic_search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by_session: bool = False,
    include_liked: bool = True,
    include_normal: bool = True,
    sort_by: str = "time",  # time, weight, accessed
) -> Dict[str, Any]:
    """获取用户聊天历史记录，支持分页、搜索、筛选和按会话分组。

    Args:
        user_id: 用户ID
        character_id: 角色ID筛选（可选）
        limit: 每页条数，最大 200
        offset: 偏移量
        search: 关键词搜索（在内容中模糊匹配）
        semantic_search: 语义搜索（使用向量相似度）
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        group_by_session: 是否按会话分组返回
        include_liked: 是否包含点赞消息
        include_normal: 是否包含普通消息
        sort_by: 排序方式 time/weight/accessed
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"history": [], "total": 0}
    
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    
    try:
        from core.infrastructure.database import get_session, ChatHistory
        from sqlalchemy import and_, desc, or_
        session = get_session()
        try:
            # 构建基础查询
            query = session.query(ChatHistory).filter_by(user_id=user_id)
            
            # 角色筛选
            if character_id:
                query = query.filter_by(character_id=character_id)
            
            # 点赞/普通消息筛选
            if not include_liked and not include_normal:
                return {"history": [], "total": 0}
            elif not include_liked:
                query = query.filter_by(is_liked=False)
            elif not include_normal:
                query = query.filter_by(is_liked=True)
            
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
                    logger.warning("日期过滤：start_date格式无效 %s", start_date)
            
            if end_date:
                try:
                    from datetime import datetime as dt, timedelta
                    end_dt = dt.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    query = query.filter(ChatHistory.created_at < end_dt)
                except ValueError:
                    logger.warning("日期过滤：end_date格式无效 %s", end_date)
            
            # 语义搜索（优先）
            semantic_results = []
            if semantic_search:
                # 先进行语义匹配，获取相关消息ID
                semantic_results = await _semantic_search(user_id, semantic_search, limit * 2)
                if semantic_results:
                    query = query.filter(ChatHistory.id.in_([r["id"] for r in semantic_results]))
            
            total = query.count()
            
            # 排序方式
            if sort_by == "weight":
                query = query.order_by(desc(ChatHistory.weight), desc(ChatHistory.created_at))
            elif sort_by == "accessed":
                query = query.order_by(desc(ChatHistory.last_accessed_at), desc(ChatHistory.created_at))
            else:
                query = query.order_by(desc(ChatHistory.created_at))
            
            # 按会话分组模式
            if group_by_session:
                records = query.all()
                
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
                            "message_count": 0,
                            "liked_count": 0,
                        }
                    
                    message_data = {
                        "id": r.id,
                        "role": r.role,
                        "content": r.content,
                        "tool_call": r.tool_call,
                        "is_liked": r.is_liked,
                        "weight": r.weight,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    sessions[session_key]["messages"].append(message_data)
                    sessions[session_key]["message_count"] += 1
                    if r.is_liked:
                        sessions[session_key]["liked_count"] += 1
                    
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
                        "liked_count": s["liked_count"],
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
                query.offset(offset)
                .limit(limit)
                .all()
            )
            
            # 更新访问计数
            for record in records:
                record.accessed_count += 1
                record.last_accessed_at = datetime.now()
            session.commit()
            
            return {
                "history": [
                    {
                        "id": r.id,
                        "character_id": r.character_id,
                        "role": r.role,
                        "content": r.content,
                        "tool_call": r.tool_call,
                        "is_liked": r.is_liked,
                        "weight": r.weight,
                        "accessed_count": r.accessed_count,
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
    include_liked: bool = True,
    include_normal: bool = True,
) -> Dict[str, Any]:
    """获取指定会话的聊天历史记录。

    Args:
        session_id: 会话ID（格式：character_id）
        user_id: 用户ID
        include_liked: 是否包含点赞消息
        include_normal: 是否包含普通消息
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"messages": []}
    
    try:
        from core.infrastructure.database import get_session, ChatHistory
        from sqlalchemy import desc
        session = get_session()
        try:
            character_id = session_id
            
            query = session.query(ChatHistory).filter_by(user_id=user_id, character_id=character_id)
            
            # 点赞/普通消息筛选
            if not include_liked and not include_normal:
                return {"messages": []}
            elif not include_liked:
                query = query.filter_by(is_liked=False)
            elif not include_normal:
                query = query.filter_by(is_liked=True)
            
            records = (
                query.order_by(desc(ChatHistory.created_at))
                .limit(100)
                .all()
            )
            
            messages = [
                {
                    "id": r.id,
                    "role": r.role,
                    "content": r.content,
                    "tool_call": r.tool_call,
                    "is_liked": r.is_liked,
                    "weight": r.weight,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in reversed(records)
            ]
            
            # 更新访问计数
            for record in records:
                record.accessed_count += 1
                record.last_accessed_at = datetime.now()
            session.commit()
            
            return {"messages": messages}
        finally:
            session.close()
    except Exception as e:
        logger.error("获取会话历史失败: %s", e)
        return {"messages": []}


@router.post("/history/{history_id}/like", summary="点赞/取消点赞消息")
async def toggle_like(
    history_id: int,
    user_id: int = 1,
) -> Dict[str, Any]:
    """点赞或取消点赞一条消息。点赞后的消息权重会增加，且不会被自动清理。

    Args:
        history_id: 历史记录ID
        user_id: 用户ID（用于权限验证）
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    
    try:
        from core.infrastructure.database import get_session, ChatHistory
        session = get_session()
        try:
            record = session.query(ChatHistory).filter_by(
                id=history_id,
                user_id=user_id
            ).first()
            
            if not record:
                return {"success": False, "detail": "记录不存在"}
            
            # 切换点赞状态
            record.is_liked = not record.is_liked
            
            # 调整权重：点赞后权重增加，取消点赞恢复默认
            if record.is_liked:
                record.weight = 10.0  # 点赞后权重设为10
                logger.info("消息点赞: history_id=%d, user_id=%d", history_id, user_id)
            else:
                record.weight = 1.0  # 取消点赞恢复默认权重
                logger.info("消息取消点赞: history_id=%d, user_id=%d", history_id, user_id)
            
            session.commit()
            
            return {
                "success": True,
                "id": history_id,
                "is_liked": record.is_liked,
                "weight": record.weight
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("点赞操作失败: %s", e)
        return {"success": False, "detail": str(e)}


@router.post("/history/{history_id}/weight", summary="手动设置消息权重")
async def set_message_weight(
    history_id: int,
    user_id: int = 1,
    weight: float = 1.0,
) -> Dict[str, Any]:
    """手动设置消息的权重，权重越高在检索时优先级越高。

    Args:
        history_id: 历史记录ID
        user_id: 用户ID（用于权限验证）
        weight: 权重值（建议范围 0.1-100）
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    
    # 权重范围限制
    weight = max(0.1, min(100.0, weight))
    
    try:
        from core.infrastructure.database import get_session, ChatHistory
        session = get_session()
        try:
            record = session.query(ChatHistory).filter_by(
                id=history_id,
                user_id=user_id
            ).first()
            
            if not record:
                return {"success": False, "detail": "记录不存在"}
            
            record.weight = weight
            session.commit()
            
            logger.info("设置消息权重: history_id=%d, weight=%.2f", history_id, weight)
            
            return {
                "success": True,
                "id": history_id,
                "weight": record.weight
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("设置权重失败: %s", e)
        return {"success": False, "detail": str(e)}


@router.get("/history/context", summary="智能检索获取上下文")
async def get_intelligent_context(
    user_id: int = 1,
    query: Optional[str] = None,
    character_id: Optional[str] = None,
    max_tokens: int = 4000,
    prefer_liked: bool = True,
    include_recent: bool = True,
    max_messages: int = 50,
) -> Dict[str, Any]:
    """智能检索获取对话上下文。根据查询语义和历史记录权重动态选择需要的消息。

    Args:
        user_id: 用户ID
        query: 当前查询（用于语义匹配）
        character_id: 角色ID筛选（可选）
        max_tokens: 最大token数限制
        prefer_liked: 是否优先选择点赞消息
        include_recent: 是否包含最近消息
        max_messages: 最大消息数量
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"context": [], "total_tokens": 0}
    
    try:
        from core.infrastructure.database import get_session, ChatHistory
        from sqlalchemy import desc, or_
        session = get_session()
        try:
            # 构建基础查询
            query_obj = session.query(ChatHistory).filter_by(user_id=user_id)
            
            if character_id:
                query_obj = query_obj.filter_by(character_id=character_id)
            
            # 获取候选消息
            candidates = []
            
            # 1. 获取点赞消息（权重最高）
            if prefer_liked:
                liked_messages = (
                    query_obj.filter_by(is_liked=True)
                    .order_by(desc(ChatHistory.weight), desc(ChatHistory.created_at))
                    .limit(max_messages // 2)
                    .all()
                )
                candidates.extend(liked_messages)
            
            # 2. 获取最近消息
            if include_recent:
                recent_messages = (
                    query_obj.order_by(desc(ChatHistory.created_at))
                    .limit(max_messages)
                    .all()
                )
                # 去重，保留已点赞的
                recent_ids = {m.id for m in recent_messages}
                liked_ids = {m.id for m in candidates}
                for msg in recent_messages:
                    if msg.id not in liked_ids:
                        candidates.append(msg)
            
            # 3. 如果有查询，进行语义匹配
            if query and len(candidates) > 0:
                semantic_results = await _semantic_search(user_id, query, limit=20)
                if semantic_results:
                    semantic_ids = {r["id"] for r in semantic_results}
                    # 将语义匹配到的消息优先放在前面
                    prioritized = []
                    remaining = []
                    for msg in candidates:
                        if msg.id in semantic_ids:
                            prioritized.append(msg)
                        else:
                            remaining.append(msg)
                    candidates = prioritized + remaining
            
            # 按权重和时间排序
            candidates.sort(key=lambda x: (x.weight, x.created_at), reverse=True)
            
            # 选择最终上下文（考虑token限制）
            context_messages = []
            total_tokens = 0
            
            # 粗略估算：1 token ≈ 4 字符
            for msg in candidates[:max_messages]:
                msg_tokens = len(msg.content) // 4
                if total_tokens + msg_tokens <= max_tokens:
                    context_messages.append({
                        "id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "character_id": msg.character_id,
                        "is_liked": msg.is_liked,
                        "weight": msg.weight,
                        "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    })
                    total_tokens += msg_tokens
                    msg.accessed_count += 1
                    msg.last_accessed_at = datetime.now()
            
            session.commit()
            
            return {
                "context": context_messages,
                "total_tokens": total_tokens,
                "message_count": len(context_messages),
                "strategy": "intelligent"
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("智能检索失败: %s", e)
        return {"context": [], "total_tokens": 0, "error": str(e)}


@router.delete("/history/cleanup", summary="清理过期的普通消息")
async def cleanup_expired_messages(
    user_id: int = 1,
    expire_days: int = 1,
) -> Dict[str, Any]:
    """清理过期的普通消息（未点赞的消息超过指定天数将被删除）。

    Args:
        user_id: 用户ID
        expire_days: 过期天数（默认1天）
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    
    try:
        from core.infrastructure.database import get_session, ChatHistory
        from datetime import datetime as dt, timedelta
        session = get_session()
        try:
            expire_time = dt.now() - timedelta(days=expire_days)
            
            # 只删除未点赞的消息
            query = session.query(ChatHistory).filter(
                ChatHistory.user_id == user_id,
                ChatHistory.is_liked == False,
                ChatHistory.created_at < expire_time
            )
            
            deleted_count = query.delete()
            session.commit()
            
            logger.info("清理过期消息: user_id=%d, deleted=%d, expire_days=%d", 
                       user_id, deleted_count, expire_days)
            
            return {
                "success": True,
                "deleted_count": deleted_count,
                "expire_days": expire_days,
                "expire_time": expire_time.isoformat()
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("清理过期消息失败: %s", e)
        return {"success": False, "detail": str(e)}


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
        from core.infrastructure.database import get_session, ChatHistory
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
        from core.infrastructure.database import get_session, ChatHistory
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
        from core.infrastructure.database import get_session, ChatHistory
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
        from core.infrastructure.database import get_session, TaskLog
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


