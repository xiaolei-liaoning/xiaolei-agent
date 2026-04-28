"""短时记忆管理系统

实现分层树状索引 + BFS队列滑动窗口的上下文管理方案
- 分层树状结构：功能层→文本层→段落层
- BFS队列滑动窗口：只保留最近N层/节点
- 按需加载：从高层到细节的按需展开
"""

import logging
from typing import Dict, Any, Optional, List, Deque
from collections import deque

logger = logging.getLogger(__name__)


class ContextNode:
    """上下文节点"""
    def __init__(self, node_id: str, node_type: str, content: str, parent_id: Optional[str] = None):
        """
        Args:
            node_id: 节点ID
            node_type: 节点类型 (function/text/paragraph)
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
    
    实现分层树状索引 + BFS队列滑动窗口的上下文管理
    """
    
    def __init__(self, window_size: int = 10):
        """
        Args:
            window_size: 滑动窗口大小，即保留的最近节点数
        """
        self.window_size = window_size
        self.nodes: Dict[str, ContextNode] = {}  # 所有节点
        self.queue: Deque[str] = deque(maxlen=window_size)  # BFS队列
        self.root_nodes: List[str] = []  # 根节点列表
        logger.info("ShortTermMemoryManager 初始化完成，窗口大小: %d", window_size)
    
    def add_context(self, user_id: str, content: str, context_type: str = "conversation"):
        """添加新的上下文
        
        Args:
            user_id: 用户ID
            content: 上下文内容
            context_type: 上下文类型
        
        Returns:
            根节点ID
        """
        # 创建功能层节点
        function_node_id = f"func_{user_id}_{len(self.nodes)}"
        function_node = ContextNode(
            node_id=function_node_id,
            node_type="function",
            content=context_type,
            parent_id=None
        )
        self.nodes[function_node_id] = function_node
        self.root_nodes.append(function_node_id)
        
        # 创建文本层节点
        text_node_id = f"text_{user_id}_{len(self.nodes)}"
        text_node = ContextNode(
            node_id=text_node_id,
            node_type="text",
            content=content[:100] + "..." if len(content) > 100 else content,  # 文本概要
            parent_id=function_node_id
        )
        text_node.summary = content[:50] + "..." if len(content) > 50 else content
        self.nodes[text_node_id] = text_node
        function_node.children.append(text_node_id)
        
        # 创建段落层节点
        paragraphs = content.split('\n')
        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():
                para_node_id = f"para_{user_id}_{len(self.nodes)}"
                para_node = ContextNode(
                    node_id=para_node_id,
                    node_type="paragraph",
                    content=paragraph,
                    parent_id=text_node_id
                )
                self.nodes[para_node_id] = para_node
                text_node.children.append(para_node_id)
        
        # 将文本节点加入队列
        self.queue.append(text_node_id)
        
        # 维护队列大小
        if len(self.queue) > self.window_size:
            removed_node_id = self.queue.popleft()
            # 移除相关节点
            self._remove_node(removed_node_id)
        
        logger.info("添加新上下文，用户: %s，内容长度: %d", user_id, len(content))
        return function_node_id
    
    def get_context(self, user_id: str, depth: int = 2) -> List[Dict[str, Any]]:
        """获取上下文
        
        Args:
            user_id: 用户ID
            depth: 展开深度 (1: 只展开功能层, 2: 展开到文本层, 3: 展开到段落层)
        
        Returns:
            上下文消息列表
        """
        messages = []
        
        # BFS遍历队列中的节点
        for node_id in list(self.queue):
            if node_id in self.nodes:
                node = self.nodes[node_id]
                # 从文本节点向上找到功能节点
                function_node = self._find_parent(node, "function")
                if function_node:
                    # 添加功能层信息
                    if depth >= 1:
                        messages.append({
                            "role": "system",
                            "content": f"[{function_node.content}]"
                        })
                    
                    # 添加文本层信息
                    if depth >= 2:
                        messages.append({
                            "role": "user" if "user" in node_id else "assistant",
                            "content": node.summary or node.content
                        })
                    
                    # 添加段落层信息
                    if depth >= 3:
                        for child_id in node.children:
                            if child_id in self.nodes:
                                child_node = self.nodes[child_id]
                                messages.append({
                                    "role": "user" if "user" in child_id else "assistant",
                                    "content": child_node.content
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
            # 移除节点
            del self.nodes[node_id]
    
    def clear_context(self, user_id: str):
        """清除指定用户的上下文"""
        # 找出该用户的所有节点
        user_nodes = [node_id for node_id in self.nodes if user_id in node_id]
        # 从队列中移除
        for node_id in user_nodes:
            if node_id in self.queue:
                self.queue.remove(node_id)
        # 移除节点
        for node_id in user_nodes:
            self._remove_node(node_id)
        logger.info("已清除用户 %s 的上下文", user_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_nodes": len(self.nodes),
            "queue_size": len(self.queue),
            "window_size": self.window_size,
            "root_nodes": len(self.root_nodes)
        }