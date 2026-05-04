"""短时记忆管理系统

实现分层树状索引 + BFS队列滑动窗口的上下文管理方案
- 分层树状结构：根→功能层(skill)→文本层→段落层
- BFS队列滑动窗口：只保留最近N层/节点
- 按需加载：从高层到细节的按需展开
- **MySQL持久化**：自动保存到数据库，重启后恢复
"""

import logging
from typing import Dict, Any, Optional, List
from collections import OrderedDict
from datetime import datetime

logger = logging.getLogger(__name__)


class ContextNode:
    """上下文节点"""
    def __init__(self, node_id: str, node_type: str, content: str, parent_id: Optional[str] = None):
        """
        Args:
            node_id: 节点ID
            node_type: 节点类型 (root/function/text/paragraph)
            content: 节点内容
            parent_id: 父节点ID
        """
        self.node_id = node_id
        self.node_type = node_type
        self.content = content
        self.parent_id = parent_id
        self.children: List[str] = []
        self.summary: Optional[str] = None  # 节点概要


class ShortTermMemoryManager:
    """短时记忆管理器
    
    实现全量持久化 + LRU缓存的上下文管理方案
    - 所有节点持久化到MySQL,保证数据可靠性
    - 内存使用LRU缓存最近访问的节点,固定内存占用
    - 批量写入优化,减少数据库事务次数
    - 支持按需查询,灵活的检索能力
    """
    
    def __init__(self, cache_size: int = 50):
        """
        Args:
            cache_size: LRU缓存大小,控制内存占用上限
        """
        self.cache_size = cache_size
        self.context_cache: OrderedDict[str, ContextNode] = OrderedDict()  # LRU缓存
        self.db_session = None  # 数据库会话
        
        logger.info("ShortTermMemoryManager 初始化完成，缓存大小: %d", cache_size)
    
    def _get_db_session(self):
        """获取数据库会话"""
        if self.db_session is None:
            try:
                from core.database import get_session
                self.db_session = get_session()
            except Exception as e:
                logger.warning("数据库会话初始化失败: %s，将使用纯内存模式", e)
        return self.db_session
    
    def _save_node_to_db(self, node: ContextNode, user_id: str, queue_order: Optional[int] = None):
        """保存节点到数据库"""
        try:
            from core.database import BFSContextNode
            
            session = self._get_db_session()
            if session is None:
                return
            
            # 检查是否已存在
            existing = session.query(BFSContextNode).filter_by(node_id=node.node_id).first()
            
            if existing:
                # 更新
                existing.content = node.content
                existing.summary = node.summary
                existing.parent_id = node.parent_id
                existing.children_ids = node.children
                existing.queue_order = queue_order
                existing.updated_at = datetime.now()
            else:
                # 插入
                new_node = BFSContextNode(
                    node_id=node.node_id,
                    user_id=user_id,
                    node_type=node.node_type,
                    content=node.content,
                    summary=node.summary,
                    parent_id=node.parent_id,
                    children_ids=node.children,
                    queue_order=queue_order
                )
                session.add(new_node)
            
            session.commit()
            logger.debug("节点已保存到数据库: %s", node.node_id)
        except Exception as e:
            logger.error("保存节点到数据库失败: %s", e)
            if session:
                session.rollback()
    
    def _save_nodes_batch(self, nodes: List[ContextNode], user_id: str):
        """批量保存节点到数据库（单次事务）
        
        Args:
            nodes: 节点列表
            user_id: 用户ID
        """
        try:
            from core.database import BFSContextNode
            
            session = self._get_db_session()
            if session is None:
                return
            
            # 收集需要插入的节点
            nodes_to_insert = []
            
            for node in nodes:
                # 检查是否已存在
                existing = session.query(BFSContextNode).filter_by(node_id=node.node_id).first()
                
                if not existing:
                    # 准备插入
                    new_node = BFSContextNode(
                        node_id=node.node_id,
                        user_id=user_id,
                        node_type=node.node_type,
                        content=node.content,
                        summary=node.summary,
                        parent_id=node.parent_id,
                        children_ids=node.children
                    )
                    nodes_to_insert.append(new_node)
            
            # ✅ 批量插入：一次性提交
            if nodes_to_insert:
                session.add_all(nodes_to_insert)
                session.commit()
                logger.debug("批量保存节点完成: %d 个新增", len(nodes_to_insert))
        except Exception as e:
            logger.error("批量保存节点到数据库失败: %s", e)
            if 'session' in locals() and session:
                session.rollback()
    
    def _batch_save_nodes_to_db(self, nodes_with_queue_order: List[tuple], user_id: str):
        """批量保存节点到数据库（优化版）
        
        Args:
            nodes_with_queue_order: 节点列表，每个元素为 (node, queue_order) 元组
            user_id: 用户ID
        """
        try:
            from core.database import BFSContextNode
            
            session = self._get_db_session()
            if session is None:
                return
            
            nodes_to_insert = []
            nodes_to_update = []
            
            for node, queue_order in nodes_with_queue_order:
                # 检查是否已存在
                existing = session.query(BFSContextNode).filter_by(node_id=node.node_id).first()
                
                if existing:
                    # 准备更新
                    existing.content = node.content
                    existing.summary = node.summary
                    existing.parent_id = node.parent_id
                    existing.children_ids = node.children
                    existing.queue_order = queue_order
                    existing.updated_at = datetime.now()
                    nodes_to_update.append(existing)
                else:
                    # 准备插入
                    new_node = BFSContextNode(
                        node_id=node.node_id,
                        user_id=user_id,
                        node_type=node.node_type,
                        content=node.content,
                        summary=node.summary,
                        parent_id=node.parent_id,
                        children_ids=node.children,
                        queue_order=queue_order
                    )
                    nodes_to_insert.append(new_node)
            
            # ✅ 批量操作：一次性提交所有变更
            if nodes_to_insert:
                session.add_all(nodes_to_insert)
            
            # 更新操作已经在上面直接修改了对象，只需提交
            session.commit()
            
            logger.debug("批量保存节点完成: %d 个新增, %d 个更新", 
                        len(nodes_to_insert), len(nodes_to_update))
        except Exception as e:
            logger.error("批量保存节点到数据库失败: %s", e)
            if session:
                session.rollback()
    
    def _delete_node_from_db(self, node_id: str):
        """从数据库删除节点"""
        try:
            from core.database import BFSContextNode
            
            session = self._get_db_session()
            if session is None:
                return
            
            node = session.query(BFSContextNode).filter_by(node_id=node_id).first()
            if node:
                session.delete(node)
                session.commit()
                logger.debug("节点已从数据库删除: %s", node_id)
        except Exception as e:
            logger.error("从数据库删除节点失败: %s", e)
            if session:
                session.rollback()
    
    def load_from_db(self, user_id: str):
        """从数据库加载用户的BFS树到缓存
        
        Args:
            user_id: 用户ID
        """
        try:
            from core.database import BFSContextNode
            
            session = self._get_db_session()
            if session is None:
                logger.warning("数据库不可用，跳过加载")
                return
            
            # 查询该用户的所有节点
            nodes = session.query(BFSContextNode).filter_by(user_id=user_id).order_by(
                BFSContextNode.created_at.asc()
            ).all()
            
            if not nodes:
                logger.info("用户 %s 没有历史记忆数据", user_id)
                return
            
            # 重建节点映射到缓存
            for db_node in nodes:
                context_node = ContextNode(
                    node_id=db_node.node_id,
                    node_type=db_node.node_type,
                    content=db_node.content,
                    parent_id=db_node.parent_id
                )
                context_node.summary = db_node.summary
                context_node.children = db_node.children_ids or []
                
                self.context_cache[db_node.node_id] = context_node
            
            logger.info("✅ 从数据库恢复了用户 %s 的记忆：共 %d 个节点", 
                       user_id, len(self.context_cache))
        except Exception as e:
            logger.error("从数据库加载记忆失败: %s", e, exc_info=True)
    
    def add_context(self, user_id: str, content: str, context_type: str = "conversation"):
        """添加新的上下文
        
        Args:
            user_id: 用户ID
            content: 上下文内容
            context_type: 上下文类型 (conversation/user/assistant/system)
        
        Returns:
            文本节点ID
        """
        # 创建唯一的全局根节点（如果不存在）- 不加入LRU缓存
        global_root_id = f"root_{user_id}"
        
        if global_root_id not in self.context_cache:
            global_root = ContextNode(
                node_id=global_root_id,
                node_type="root",
                content=f"User {user_id} Context Tree",
                parent_id=None
            )
            self.context_cache[global_root_id] = global_root
        
        global_root = self.context_cache[global_root_id]
        
        # 第2层：功能层 - 根据context_type分类 - 不加入LRU缓存
        function_node_id = f"func_{user_id}_{context_type}"
        
        if function_node_id not in self.context_cache:
            function_node = ContextNode(
                node_id=function_node_id,
                node_type="function",
                content=context_type,
                parent_id=global_root_id
            )
            self.context_cache[function_node_id] = function_node
            global_root.children.append(function_node_id)
        
        function_node = self.context_cache[function_node_id]
        
        # 第3层：文本层节点 - 加入LRU缓存
        text_node_id = f"text_{user_id}_{datetime.now().timestamp()}"
        text_node = ContextNode(
            node_id=text_node_id,
            node_type="text",
            content=content[:100] + "..." if len(content) > 100 else content,
            parent_id=function_node_id
        )
        text_node.summary = content[:50] + "..." if len(content) > 50 else content
        function_node.children.append(text_node_id)
        
        # 第4层：段落层节点 - 不加入缓存,只持久化
        paragraph_nodes = []
        paragraphs = content.split('\n')
        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():
                para_node_id = f"para_{user_id}_{datetime.now().timestamp()}_{i}"
                para_node = ContextNode(
                    node_id=para_node_id,
                    node_type="paragraph",
                    content=paragraph,
                    parent_id=text_node_id
                )
                paragraph_nodes.append(para_node)
                text_node.children.append(para_node_id)
        
        # ✅ 批量持久化到数据库（单次事务）
        all_nodes = [global_root, function_node, text_node] + paragraph_nodes
        self._save_nodes_batch(all_nodes, user_id)
        
        # ✅ 更新LRU缓存（只缓存text节点，控制内存）
        self._update_cache(text_node_id, text_node)
        
        logger.info("添加新上下文，用户: %s，类型: %s，内容长度: %d", 
                   user_id, context_type, len(content))
        return text_node_id
    
    def _update_cache(self, node_id: str, node: ContextNode):
        """更新LRU缓存（只管理text节点）
        
        Args:
            node_id: 节点ID
            node: 节点对象
        """
        # 移动到末尾（标记为最近使用）
        if node_id in self.context_cache:
            self.context_cache.move_to_end(node_id)
        
        # 添加到缓存
        self.context_cache[node_id] = node
        
        # LRU淘汰：如果超出容量，删除最久未使用的
        while len(self.context_cache) > self.cache_size:
            oldest_key, oldest_node = next(iter(self.context_cache.items()))
            # 只淘汰text节点，保留root/function
            if oldest_node.node_type == "text":
                del self.context_cache[oldest_key]
                logger.debug("LRU缓存淘汰: %s", oldest_key)
            else:
                # 如果是root/function，跳过并继续检查下一个
                self.context_cache.move_to_end(oldest_key)
                break  # 避免死循环
    
    def get_context(self, user_id: str, depth: int = 2, limit: int = 10) -> List[Dict[str, Any]]:
        """获取上下文
        
        Args:
            user_id: 用户ID
            depth: 展开深度 
                   - 1: 只返回根节点信息
                   - 2: 展开到功能层（session/user/assistant/system）
                   - 3: 展开到文本层（消息概要）
                   - 4: 展开到段落层（详细内容）
            limit: 返回最近的消息数量
        
        Returns:
            上下文消息列表
        """
        messages = []
        
        # ✅ 从数据库查询最近的text节点
        try:
            from core.database import BFSContextNode
            
            session = self._get_db_session()
            if session is None:
                logger.warning("数据库不可用，返回空上下文")
                return messages
            
            # 查询最近的limit条text节点
            text_nodes = session.query(BFSContextNode).filter_by(
                user_id=user_id,
                node_type="text"
            ).order_by(
                BFSContextNode.created_at.desc()
            ).limit(limit).all()
            
            if not text_nodes:
                logger.info("用户 %s 没有历史消息", user_id)
                return messages
            
            # 反转顺序，从旧到新
            text_nodes.reverse()
            
            # 获取根节点信息
            root_node = session.query(BFSContextNode).filter_by(
                user_id=user_id,
                node_type="root"
            ).first()
            
            # Depth 1: 根节点信息
            if depth >= 1 and root_node:
                messages.append({
                    "role": "system",
                    "content": f"[ROOT] {root_node.content}"
                })
            
            # 遍历每个text节点
            for text_db_node in text_nodes:
                # 向上查找功能层节点
                function_node = None
                if text_db_node.parent_id:
                    function_node = session.query(BFSContextNode).filter_by(
                        node_id=text_db_node.parent_id
                    ).first()
                
                if not function_node:
                    continue
                
                # Depth 2: 功能层信息
                if depth >= 2:
                    messages.append({
                        "role": "system",
                        "content": f"[{function_node.content.upper()}]"
                    })
                
                # Depth 3: 文本层信息
                if depth >= 3:
                    messages.append({
                        "role": "user" if "user" in function_node.content.lower() else "assistant",
                        "content": text_db_node.summary or text_db_node.content
                    })
                
                # Depth 4: 段落层信息
                if depth >= 4 and text_db_node.children_ids:
                    for para_id in text_db_node.children_ids:
                        para_node = session.query(BFSContextNode).filter_by(
                            node_id=para_id
                        ).first()
                        if para_node:
                            messages.append({
                                "role": "user" if "user" in function_node.content.lower() else "assistant",
                                "content": para_node.content
                            })
            
            return messages
            
        except Exception as e:
            logger.error("获取上下文失败: %s", e, exc_info=True)
            return messages
    
    def _find_parent(self, node: ContextNode, node_type: str) -> Optional[ContextNode]:
        """查找指定类型的父节点"""
        current = node
        while current:
            if current.node_type == node_type:
                return current
            if current.parent_id and current.parent_id in self.nodes:
                current = self.nodes[current.parent_id]
            else:
                break
        return None
    
    def _remove_node(self, node_id: str):
        """移除节点及其子节点"""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            # 递归移除子节点
            for child_id in node.children:
                self._remove_node(child_id)
            # 从父节点的子节点列表中移除
            if node.parent_id and node.parent_id in self.nodes:
                parent_node = self.nodes[node.parent_id]
                if node_id in parent_node.children:
                    parent_node.children.remove(node_id)
            # 从根节点列表中移除
            if node.parent_id is None and node_id in self.root_nodes:
                self.root_nodes.remove(node_id)
            
            # ✅ 从数据库删除
            self._delete_node_from_db(node_id)
            
            # 移除节点
            del self.nodes[node_id]
    
    def clear_context(self, user_id: str):
        """清除指定用户的上下文
        
        Args:
            user_id: 用户ID
        """
        try:
            from core.database import BFSContextNode
            
            session = self._get_db_session()
            if session is None:
                logger.warning("数据库不可用，跳过清理")
                return
            
            # 从数据库删除该用户的所有节点
            deleted_count = session.query(BFSContextNode).filter_by(
                user_id=user_id
            ).delete()
            
            session.commit()
            
            # 清空缓存中该用户的节点
            keys_to_remove = [key for key in self.context_cache if user_id in key]
            for key in keys_to_remove:
                del self.context_cache[key]
            
            logger.info("已清除用户 %s 的上下文，共删除 %d 个节点", user_id, deleted_count)
        except Exception as e:
            logger.error("清除上下文失败: %s", e, exc_info=True)
            if 'session' in locals() and session:
                session.rollback()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "cache_size": len(self.context_cache),
            "max_cache_size": self.cache_size
        }

































