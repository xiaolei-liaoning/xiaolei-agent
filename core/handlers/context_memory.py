"""BFS上下文记忆管理"""

import logging
from typing import Dict, Any, List
from collections import deque

logger = logging.getLogger(__name__)

# 导入依赖
from ..workflow.bfs_processor import get_bfs_processor
from ..memory.short_term_memory import ShortTermMemoryManager

# 全局BFS处理器实例（单例，所有调用共享）
bfs_processor = get_bfs_processor()

# 全局短时记忆管理器（支持分层树状索引 + BFS队列）
short_term_memory = ShortTermMemoryManager(cache_size=50)


# 不需要BFS的技能类型（纯闲聊无需结构化上下文）
_SKIP_BFS_SKILLS = {"chat", "greeting"}


def add_to_context_memory(user_id: str, message: str, role: str = "user", skill_name: str = "chat"):
    """将消息添加到BFS上下文记忆中

    BFS仅在非纯闲聊技能时触发，避免每轮对话无效建树。

    使用树与队列的BFS机制管理上下文：
    - 第1层：全局唯一根节点（root_{user_id}）
    - 第2层：按 skill 分类的功能节点（func_{user_id}_{skill_name}）
    - 第3层：文本层节点（text_{user_id}_{序号}）
    - 第4层：段落层节点（para_{user_id}_{序号}）

    Args:
        user_id: 用户ID
        message: 消息内容
        role: 角色类型 (user/assistant)
        skill_name: 技能名称（用于第2层分类）

    Returns:
        上下文节点ID
    """
    try:
        need_bfs = skill_name not in _SKIP_BFS_SKILLS

        if need_bfs:
            bfs_result = bfs_processor.process_text(message)
            bfs_success = bfs_result.get("success", False)
            if not bfs_success:
                logger.debug("BFS上下文处理跳过: %s", bfs_result.get("error"))
        else:
            bfs_success = True

        context_type = f"{role}_{skill_name}"
        context_id = short_term_memory.add_context(
            user_id=str(user_id),
            content=message,
            context_type=context_type
        )

        logger.info("上下文记忆已更新 - 用户: %s, Skill: %s, BFS: %s, 节点数: %d",
                    user_id, skill_name, need_bfs, len(short_term_memory.nodes))

        return {
            "success": True,
            "context_id": context_id,
            "queue_size": len(short_term_memory.queue),
            "nodes_count": len(short_term_memory.nodes),
            "bfs_enabled": need_bfs
        }
    except Exception as e:
        logger.error("添加上下文记忆失败: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


def get_context_for_llm(user_id: str, depth: int = 2) -> str:
    """获取用于LLM的上下文消息
    
    从BFS队列中提取相关上下文，构建prompt格式
    
    Args:
        user_id: 用户ID
        depth: 展开深度 (1:功能层, 2:文本层, 3:段落层)
    
    Returns:
        格式化的上下文字符串
    """
    context_messages = short_term_memory.get_context(str(user_id), depth=depth)
    
    if not context_messages:
        return ""
    
    context_parts = []
    for msg in context_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        context_parts.append(f"{role}: {content}")
    
    return "\n".join(context_parts)


def search_context_by_keywords(user_id: str, keywords: List[str], top_k: int = 5) -> List[Dict[str, Any]]:
    """基于关键词搜索上下文记忆
    
    Args:
        user_id: 用户ID
        keywords: 关键词列表
        top_k: 返回数量
    
    Returns:
        相关上下文节点列表
    """
    try:
        queue_nodes = []
        for node_id in list(short_term_memory.queue):
            if node_id in short_term_memory.nodes:
                queue_nodes.append(short_term_memory.nodes[node_id])
        
        context_queue = deque(queue_nodes)
        results = bfs_processor.extract_context_by_keywords(context_queue, keywords, top_k)
        
        logger.info("上下文关键词检索完成 - 用户: %s, 找到: %d 个相关节点", 
                   user_id, len(results))
        
        return results
    except Exception as e:
        logger.error("上下文关键词检索失败: %s", e, exc_info=True)
        return []
