"""改进的短时记忆管理系统

实现分层树状索引 + 动态数组的上下文管理方案
- 分层树状结构：根→功能层(skill)→文本层→段落层
- 动态数组：基于内容长度动态调整，而不是固定N个节点
- 按需加载：从高层到细节的按需展开
- MySQL持久化：自动保存到数据库，重启后恢复
- Token估算：基于内容长度估算token数量，智能裁剪
"""

import logging
from typing import Dict, Any, Optional, List
from collections import deque
from datetime import datetime
import json

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
        self.created_at = datetime.now()
        self.token_count = self._estimate_tokens()  # 估算token数量
    
    def _estimate_tokens(self) -> int:
        """估算token数量（简化版）"""
        # 假设中文字符约1 token/2字符，英文约1 token/1.3字符
        chinese_chars = sum(1 for c in self.content if '\u4e00' <= c <= '\u9fff')
        english_chars = len(self.content) - chinese_chars
        return int(chinese_chars / 2 + english_chars / 1.3)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'node_id': self.node_id,
            'node_type': self.node_type,
            'content': self.content,
            'parent_id': self.parent_id,
            'children': self.children,
            'summary': self.summary,
            'created_at': self.created_at.isoformat(),
            'token_count': self.token_count
        }


class DynamicShortTermMemory:
    """动态短时记忆管理器
    
    实现分层树状索引 + 动态数组的上下文管理
    支持 MySQL 持久化，重启后自动恢复
    """
    
    def __init__(self, max_tokens: int = 12000, max_nodes: int = 50):
        """
        Args:
            max_tokens: 最大总token数（默认12k，约等于GPT-4的1/8上下文）
            max_nodes: 最大节点数（兜底保护）
        """
        self.max_tokens = max_tokens
        self.max_nodes = max_nodes
        
        self.nodes: Dict[str, ContextNode] = {}  # 所有节点（内存缓存）
        self.context_array: List[str] = []  # 动态数组，按时间顺序存储node_id
        self.root_nodes: List[str] = []  # 根节点列表
        self.db_session = None
        
        logger.info("DynamicShortTermMemory 初始化完成，max_tokens: %d, max_nodes: %d", 
                   max_tokens, max_nodes)
    
    def _get_db_session(self):
        """获取数据库会话"""
        if self.db_session is None:
            try:
                from core.database import get_session
                self.db_session = get_session()
            except Exception as e:
                logger.warning("数据库会话初始化失败: %s，将使用纯内存模式", e)
        return self.db_session
    
    def _save_node_to_db(self, node: ContextNode, user_id: str, array_index: Optional[int] = None):
        """保存节点到数据库"""
        try:
            from core.database import DynamicContextNode
            
            session = self._get_db_session()
            if session is None:
                return
            
            # 检查是否已存在
            existing = session.query(DynamicContextNode).filter_by(node_id=node.node_id).first()
            
            if existing:
                # 更新
                existing.content = node.content
                existing.summary = node.summary
                existing.parent_id = node.parent_id
                existing.children_ids = node.children
                existing.array_index = array_index
                existing.token_count = node.token_count
                existing.updated_at = datetime.now()
            else:
                # 插入
                new_node = DynamicContextNode(
                    node_id=node.node_id,
                    user_id=user_id,
                    node_type=node.node_type,
                    content=node.content,
                    summary=node.summary,
                    parent_id=node.parent_id,
                    children_ids=node.children,
                    array_index=array_index,
                    token_count=node.token_count
                )
                session.add(new_node)
            
            session.commit()
            logger.debug("节点已保存到数据库: %s", node.node_id)
        except Exception as e:
            logger.error("保存节点到数据库失败: %s", e)
            if session:
                session.rollback()
    
    def _delete_node_from_db(self, node_id: str):
        """从数据库删除节点"""
        try:
            from core.database import DynamicContextNode
            
            session = self._get_db_session()
            if session is None:
                return
            
            node = session.query(DynamicContextNode).filter_by(node_id=node_id).first()
            if node:
                session.delete(node)
                session.commit()
                logger.debug("节点已从数据库删除: %s", node_id)
        except Exception as e:
            logger.error("从数据库删除节点失败: %s", e)
            if session:
                session.rollback()
    
    def load_from_db(self, user_id: str):
        """从数据库加载用户的记忆
        
        Args:
            user_id: 用户ID
        """
        try:
            from core.database import DynamicContextNode
            
            session = self._get_db_session()
            if session is None:
                logger.warning("数据库不可用，跳过加载")
                return
            
            # 查询该用户的所有节点，按创建时间排序
            nodes = session.query(DynamicContextNode).filter_by(user_id=user_id).order_by(
                DynamicContextNode.created_at.asc()
            ).all()
            
            if not nodes:
                logger.info("用户 %s 没有历史记忆数据", user_id)
                return
            
            # 重建节点映射
            for db_node in nodes:
                context_node = ContextNode(
                    node_id=db_node.node_id,
                    node_type=db_node.node_type,
                    content=db_node.content,
                    parent_id=db_node.parent_id
                )
                context_node.summary = db_node.summary
                context_node.children = db_node.children_ids or []
                context_node.token_count = db_node.token_count
                context_node.created_at = db_node.created_at
                
                self.nodes[db_node.node_id] = context_node
                
                # 记录根节点
                if db_node.node_type == "root":
                    self.root_nodes.append(db_node.node_id)
                
                # 恢复动态数组（按array_index排序）
                if db_node.array_index is not None:
                    self.context_array.append(db_node.node_id)
            
            # 确保数组按array_index正确排序
            self._sort_context_array()
            
            # 检查是否超过限制，可能需要裁剪
            self._trim_if_needed(user_id)
            
            logger.info("✅ 从数据库恢复了用户 %s 的记忆：共 %d 个节点，动态数组大小 %d，总tokens: %d", 
                       user_id, len(self.nodes), len(self.context_array), self.get_total_tokens())
        except Exception as e:
            logger.error("从数据库加载记忆失败: %s", e, exc_info=True)
    
    def _sort_context_array(self):
        """按创建时间排序context_array"""
        self.context_array.sort(key=lambda node_id: self.nodes[node_id].created_at)
    
    def get_total_tokens(self) -> int:
        """获取当前总token数"""
        return sum(self.nodes[node_id].token_count 
                  for node_id in self.context_array 
                  if node_id in self.nodes)
    
    def add_context(self, user_id: str, content: str, context_type: str = "conversation") -> str:
        """添加新的上下文
        
        Args:
            user_id: 用户ID
            content: 上下文内容
            context_type: 上下文类型 (conversation/user/assistant/system)
        
        Returns:
            文本节点ID
        """
        # 创建唯一的全局根节点（如果不存在）
        global_root_id = f"root_{user_id}"
        
        if global_root_id not in self.nodes:
            global_root = ContextNode(
                node_id=global_root_id,
                node_type="root",
                content=f"User {user_id} Context Tree",
                parent_id=None
            )
            self.nodes[global_root_id] = global_root
            self.root_nodes.append(global_root_id)
            self._save_node_to_db(global_root, user_id)
        
        global_root = self.nodes[global_root_id]
        
        # 创建功能层节点（user/assistant/system）
        function_node_id = f"function_{user_id}_{context_type}"
        
        if function_node_id not in self.nodes:
            function_node = ContextNode(
                node_id=function_node_id,
                node_type="function",
                content=context_type,
                parent_id=global_root_id
            )
            self.nodes[function_node_id] = function_node
            global_root.children.append(function_node_id)
            self._save_node_to_db(function_node, user_id)
        
        function_node = self.nodes[function_node_id]
        
        # 创建文本层节点（实际消息内容）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        text_node_id = f"text_{user_id}_{timestamp}"
        text_node = ContextNode(
            node_id=text_node_id,
            node_type="text",
            content=content,
            parent_id=function_node_id
        )
        
        # 生成摘要（前50个字符）
        text_node.summary = content[:50] + "..." if len(content) > 50 else content
        
        self.nodes[text_node_id] = text_node
        function_node.children.append(text_node_id)
        
        # 简单的段落分割
        paragraphs = content.split("\n\n")
        for i, para in enumerate(paragraphs):
            if para.strip():
                para_node_id = f"para_{user_id}_{timestamp}_{i}"
                para_node = ContextNode(
                    node_id=para_node_id,
                    node_type="paragraph",
                    content=para.strip(),
                    parent_id=text_node_id
                )
                self.nodes[para_node_id] = para_node
                text_node.children.append(para_node_id)
                self._save_node_to_db(para_node, user_id)
        
        # 将新节点添加到动态数组末尾
        self.context_array.append(text_node_id)
        
        # 保存节点到数据库
        self._save_node_to_db(text_node, user_id, len(self.context_array) - 1)
        self._save_node_to_db(function_node, user_id)
        
        # 检查是否超过限制，可能需要裁剪
        self._trim_if_needed(user_id)
        
        logger.info("添加新上下文，用户: %s，类型: %s，tokens: %d，数组大小: %d，总tokens: %d", 
                   user_id, context_type, text_node.token_count, 
                   len(self.context_array), self.get_total_tokens())
        
        return text_node_id
    
    def _trim_if_needed(self, user_id: str):
        """按需裁剪记忆，保持在token限制内"""
        total_tokens = self.get_total_tokens()
        total_nodes = len(self.context_array)
        
        if total_tokens <= self.max_tokens and total_nodes <= self.max_nodes:
            return
        
        logger.warning("超过限制！总tokens: %d/%d，节点数: %d/%d，开始裁剪...", 
                      total_tokens, self.max_tokens, total_nodes, self.max_nodes)
        
        # 从数组开头（最旧的）开始裁剪，直到满足限制
        removed_count = 0
        while (self.get_total_tokens() > self.max_tokens or 
               len(self.context_array) > self.max_nodes):
            
            if not self.context_array:
                break
            
            # 移除最旧的节点
            removed_node_id = self.context_array.pop(0)
            removed_count += 1
            
            logger.debug("裁剪移除节点: %s", removed_node_id)
            
            # 从树中移除节点
            self._remove_node(removed_node_id, user_id)
            
            # 更新剩余节点的array_index
            for i, node_id in enumerate(self.context_array):
                node = self.nodes[node_id]
                self._save_node_to_db(node, user_id, i)
        
        logger.info("裁剪完成！移除了 %d 个节点，当前数组大小: %d，总tokens: %d", 
                   removed_count, len(self.context_array), self.get_total_tokens())
    
    def _remove_node(self, node_id: str, user_id: str):
        """移除节点及其子节点"""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            
            # 递归移除子节点
            for child_id in node.children.copy():
                self._remove_node(child_id, user_id)
            
            # 从父节点的子节点列表中移除
            if node.parent_id and node.parent_id in self.nodes:
                parent_node = self.nodes[node.parent_id]
                if node_id in parent_node.children:
                    parent_node.children.remove(node_id)
            
            # 从根节点列表中移除
            if node.parent_id is None and node_id in self.root_nodes:
                self.root_nodes.remove(node_id)
            
            # 从数据库删除
            self._delete_node_from_db(node_id)
            
            # 移除节点
            del self.nodes[node_id]
    
    def get_context(self, user_id: str, depth: int = 2) -> List[Dict[str, Any]]:
        """获取上下文
        
        Args:
            user_id: 用户ID
            depth: 展开深度 
                   - 1: 只返回根节点信息
                   - 2: 展开到功能层（session/user/assistant/system）
                   - 3: 展开到文本层（消息概要）
                   - 4: 展开到段落层（详细内容）
        
        Returns:
            上下文消息列表
        """
        messages = []
        
        # 获取全局根节点
        global_root_id = f"root_{user_id}"
        if global_root_id not in self.nodes:
            return messages
        
        global_root = self.nodes[global_root_id]
        
        # Depth 1: 根节点信息
        if depth >= 1:
            messages.append({
                "role": "system",
                "content": f"[ROOT] {global_root.content} [Total Tokens: {self.get_total_tokens()}]"
            })
        
        # 按时间顺序遍历动态数组（从旧到新）
        for node_id in self.context_array:
            if node_id not in self.nodes:
                continue
            
            text_node = self.nodes[node_id]
            
            # 向上查找功能层节点
            function_node = self._find_parent(text_node, "function")
            if not function_node:
                continue
            
            # Depth 2: 功能层信息
            if depth >= 2:
                messages.append({
                    "role": "system",
                    "content": f"[{function_node.content.upper()}] [Tokens: {text_node.token_count}]"
                })
            
            # Depth 3: 文本层信息
            if depth >= 3:
                messages.append({
                    "role": "user" if "user" in function_node.content.lower() else "assistant",
                    "content": text_node.summary or text_node.content
                })
            
            # Depth 4: 段落层信息
            if depth >= 4:
                for child_id in text_node.children:
                    if child_id in self.nodes:
                        para_node = self.nodes[child_id]
                        messages.append({
                            "role": "user" if "user" in function_node.content.lower() else "assistant",
                            "content": para_node.content
                        })
        
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
    
    def clear_context(self, user_id: str):
        """清除指定用户的上下文"""
        # 找出该用户的所有节点
        user_nodes = [node_id for node_id in self.nodes if user_id in node_id]
        
        # 从数组中移除
        for node_id in user_nodes:
            if node_id in self.context_array:
                self.context_array.remove(node_id)
        
        # 移除节点
        for node_id in user_nodes.copy():
            self._remove_node(node_id, user_id)
        
        logger.info("已清除用户 %s 的上下文", user_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_nodes": len(self.nodes),
            "array_size": len(self.context_array),
            "max_tokens": self.max_tokens,
            "max_nodes": self.max_nodes,
            "current_tokens": self.get_total_tokens(),
            "root_nodes": len(self.root_nodes)
        }
    
    def export_memory(self, user_id: str, filepath: str) -> bool:
        """导出记忆到JSON文件"""
        try:
            data = {
                "user_id": user_id,
                "export_time": datetime.now().isoformat(),
                "stats": self.get_stats(),
                "nodes": [
                    node.to_dict() 
                    for node_id, node in self.nodes.items() 
                    if user_id in node_id
                ],
                "context_array": self.context_array
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info("✅ 记忆已导出到: %s", filepath)
            return True
        except Exception as e:
            logger.error("导出记忆失败: %s", e)
            return False
