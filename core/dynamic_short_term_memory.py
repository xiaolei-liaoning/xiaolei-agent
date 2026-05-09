"""改进的短时记忆管理系统

实现分层树状索引 + 动态数组的上下文管理方案
"""

import logging
from typing import Dict, Any, Optional, List
from collections import deque
from datetime import datetime
import json

logger = logging.getLogger(__name__)

_DB_WARNING_SHOWN = False


class ContextNode:
    """上下文节点"""
    def __init__(self, node_id: str, node_type: str, content: str, parent_id: Optional[str] = None):
        self.node_id = node_id
        self.node_type = node_type
        self.content = content
        self.parent_id = parent_id
        self.children: List[str] = []
        self.summary: Optional[str] = None
        self.created_at = datetime.now()
        self.token_count = self._estimate_tokens()

    def _estimate_tokens(self) -> int:
        chinese_chars = sum(1 for c in self.content if '\u4e00' <= c <= '\u9fff')
        english_chars = len(self.content) - chinese_chars
        return int(chinese_chars / 2 + english_chars / 1.3)

    def to_dict(self) -> Dict[str, Any]:
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
    """动态短时记忆管理器"""

    def __init__(self, max_tokens: int = 12000, max_nodes: int = 50):
        self.max_tokens = max_tokens
        self.max_nodes = max_nodes
        self.nodes: Dict[str, ContextNode] = {}
        self.context_array: List[str] = []
        self.root_nodes: List[str] = []
        self.db_session = None
        logger.info("DynamicShortTermMemory 初始化完成，max_tokens: %d, max_nodes: %d", max_tokens, max_nodes)

    def _get_db_session(self):
        global _DB_WARNING_SHOWN

        if self.db_session is None:
            try:
                from core.database import get_session
                self.db_session = get_session()
            except Exception as e:
                if not _DB_WARNING_SHOWN:
                    logger.debug("数据库会话初始化失败: %s，将使用纯内存模式", e)
                    _DB_WARNING_SHOWN = True
        return self.db_session

    def _save_node_to_db(self, node: ContextNode, user_id: str, array_index: Optional[int] = None):
        try:
            from core.database import DynamicContextNode
            session = self._get_db_session()
            if session is None:
                return
            existing = session.query(DynamicContextNode).filter_by(node_id=node.node_id).first()
            if existing:
                existing.content = node.content
                existing.summary = node.summary
                existing.parent_id = node.parent_id
                existing.children_ids = node.children
                existing.array_index = array_index
                existing.token_count = node.token_count
                existing.updated_at = datetime.now()
            else:
                new_node = DynamicContextNode(
                    node_id=node.node_id, user_id=user_id, node_type=node.node_type,
                    content=node.content, summary=node.summary, parent_id=node.parent_id,
                    children_ids=node.children, array_index=array_index, token_count=node.token_count
                )
                session.add(new_node)
            session.commit()
        except Exception as e:
            logger.error("保存节点到数据库失败: %s", e)
            if session:
                session.rollback()

    def _delete_node_from_db(self, node_id: str):
        try:
            from core.database import DynamicContextNode
            session = self._get_db_session()
            if session is None:
                return
            node = session.query(DynamicContextNode).filter_by(node_id=node_id).first()
            if node:
                session.delete(node)
                session.commit()
        except Exception as e:
            logger.error("从数据库删除节点失败: %s", e)
            if session:
                session.rollback()

    def load_from_db(self, user_id: str):
        try:
            from core.database import DynamicContextNode
            session = self._get_db_session()
            if session is None:
                return
            nodes = session.query(DynamicContextNode).filter_by(user_id=user_id).order_by(
                DynamicContextNode.created_at.asc()
            ).all()
            if not nodes:
                return
            for db_node in nodes:
                context_node = ContextNode(db_node.node_id, db_node.node_type, db_node.content, db_node.parent_id)
                context_node.summary = db_node.summary
                context_node.children = db_node.children_ids or []
                context_node.token_count = db_node.token_count
                context_node.created_at = db_node.created_at
                self.nodes[db_node.node_id] = context_node
                if db_node.node_type == "root":
                    self.root_nodes.append(db_node.node_id)
                if db_node.array_index is not None:
                    self.context_array.append(db_node.node_id)
            self._sort_context_array()
            self._trim_if_needed(user_id)
            logger.info("✅ 从数据库恢复了用户 %s 的记忆：共 %d 个节点", user_id, len(self.nodes))
        except Exception as e:
            logger.error("从数据库加载记忆失败: %s", e, exc_info=True)

    def _sort_context_array(self):
        self.context_array.sort(key=lambda node_id: self.nodes[node_id].created_at)

    def get_total_tokens(self) -> int:
        return sum(self.nodes[node_id].token_count for node_id in self.context_array if node_id in self.nodes)

    def add_context(self, user_id: str, content: str, context_type: str = "conversation") -> str:
        global_root_id = f"root_{user_id}"
        if global_root_id not in self.nodes:
            global_root = ContextNode(global_root_id, "root", f"User {user_id} Context Tree", None)
            self.nodes[global_root_id] = global_root
            self.root_nodes.append(global_root_id)
            self._save_node_to_db(global_root, user_id)

        global_root = self.nodes[global_root_id]
        function_node_id = f"function_{user_id}_{context_type}"

        if function_node_id not in self.nodes:
            function_node = ContextNode(function_node_id, "function", context_type, global_root_id)
            self.nodes[function_node_id] = function_node
            global_root.children.append(function_node_id)
            self._save_node_to_db(function_node, user_id)

        function_node = self.nodes[function_node_id]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        text_node_id = f"text_{user_id}_{timestamp}"
        text_node = ContextNode(text_node_id, "text", content, function_node_id)
        text_node.summary = content[:50] + "..." if len(content) > 50 else content

        self.nodes[text_node_id] = text_node
        function_node.children.append(text_node_id)

        paragraphs = content.split("\n\n")
        for i, para in enumerate(paragraphs):
            if para.strip():
                para_node_id = f"para_{user_id}_{timestamp}_{i}"
                para_node = ContextNode(para_node_id, "paragraph", para.strip(), text_node_id)
                self.nodes[para_node_id] = para_node
                text_node.children.append(para_node_id)
                self._save_node_to_db(para_node, user_id)

        self.context_array.append(text_node_id)
        self._save_node_to_db(text_node, user_id, len(self.context_array) - 1)
        self._save_node_to_db(function_node, user_id)
        self._trim_if_needed(user_id)

        return text_node_id

    def _trim_if_needed(self, user_id: str):
        total_tokens = self.get_total_tokens()
        total_nodes = len(self.context_array)

        if total_tokens <= self.max_tokens and total_nodes <= self.max_nodes:
            return

        removed_count = 0
        while (self.get_total_tokens() > self.max_tokens or len(self.context_array) > self.max_nodes):
            if not self.context_array:
                break
            removed_node_id = self.context_array.pop(0)
            removed_count += 1
            self._remove_node(removed_node_id, user_id)
            for i, node_id in enumerate(self.context_array):
                node = self.nodes[node_id]
                self._save_node_to_db(node, user_id, i)

        logger.info("裁剪完成！移除了 %d 个节点", removed_count)

    def _remove_node(self, node_id: str, user_id: str):
        if node_id in self.nodes:
            node = self.nodes[node_id]
            for child_id in node.children.copy():
                self._remove_node(child_id, user_id)
            if node.parent_id and node.parent_id in self.nodes:
                parent_node = self.nodes[node.parent_id]
                if node_id in parent_node.children:
                    parent_node.children.remove(node_id)
            if node.parent_id is None and node_id in self.root_nodes:
                self.root_nodes.remove(node_id)
            self._delete_node_from_db(node_id)
            del self.nodes[node_id]

    def get_context(self, user_id: str, depth: int = 2) -> List[Dict[str, Any]]:
        messages = []
        global_root_id = f"root_{user_id}"
        if global_root_id not in self.nodes:
            return messages

        global_root = self.nodes[global_root_id]

        if depth >= 1:
            messages.append({"role": "system", "content": f"[ROOT] {global_root.content}"})

        for node_id in self.context_array:
            if node_id not in self.nodes:
                continue
            text_node = self.nodes[node_id]
            function_node = self._find_parent(text_node, "function")
            if not function_node:
                continue
            if depth >= 2:
                messages.append({"role": "system", "content": f"[{function_node.content.upper()}]"})
            if depth >= 3:
                messages.append({"role": "user" if "user" in function_node.content.lower() else "assistant", "content": text_node.summary or text_node.content})
            if depth >= 4:
                for child_id in text_node.children:
                    if child_id in self.nodes:
                        para_node = self.nodes[child_id]
                        messages.append({"role": "user" if "user" in function_node.content.lower() else "assistant", "content": para_node.content})

        return messages

    def _find_parent(self, node: ContextNode, node_type: str) -> Optional[ContextNode]:
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
        user_nodes = [node_id for node_id in self.nodes if user_id in node_id]
        for node_id in user_nodes:
            if node_id in self.context_array:
                self.context_array.remove(node_id)
        for node_id in user_nodes.copy():
            self._remove_node(node_id, user_id)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self.nodes),
            "array_size": len(self.context_array),
            "max_tokens": self.max_tokens,
            "max_nodes": self.max_nodes,
            "current_tokens": self.get_total_tokens(),
            "root_nodes": len(self.root_nodes)
        }

    def export_memory(self, user_id: str, filepath: str) -> bool:
        try:
            data = {
                "user_id": user_id,
                "export_time": datetime.now().isoformat(),
                "stats": self.get_stats(),
                "nodes": [node.to_dict() for node_id, node in self.nodes.items() if user_id in node_id],
                "context_array": self.context_array
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("✅ 记忆已导出到: %s", filepath)
            return True
        except Exception as e:
            logger.error("导出记忆失败: %s", e)
            return False
