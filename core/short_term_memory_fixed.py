"""改进的短时记忆管理系统 - 修复内存泄漏和节点膨胀问题

实现分层树状索引 + BFS队列滑动窗口的上下文管理方案
- 分层树状结构：根→功能层(skill)→文本层→段落层
- BFS队列滑动窗口：只保留最近N层/节点
- 按需加载：从高层到细节的按需展开
- **MySQL持久化**：批量写入，重启后恢复
- **垃圾回收**：定期清理孤立节点
- **内存监控**：监控内存使用情况
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Set
from collections import deque
from datetime import datetime, timedelta
from contextlib import contextmanager
import gc

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
        self.last_accessed = datetime.now()  # 最后访问时间
        self.access_count = 0  # 访问计数
        self.is_orphan = False  # 是否为孤立节点
        self.marked_for_deletion = False  # 标记为待删除


class ShortTermMemoryManager:
    """短时记忆管理器 - 修复内存泄漏版本

    实现分层树状索引 + BFS队列滑动窗口的上下文管理
    支持 MySQL 持久化，重启后自动恢复
    """

    def __init__(self, window_size: int = 10, batch_size: int = 50, gc_interval: int = 300):
        """
        Args:
            window_size: 滑动窗口大小，即保留的最近节点数
            batch_size: 批量写入数据库的大小
            gc_interval: 垃圾回收间隔（秒）
        """
        self.window_size = window_size
        self.batch_size = batch_size
        self.gc_interval = gc_interval

        self.nodes: Dict[str, ContextNode] = {}  # 所有节点（内存缓存）
        self.queue: deque = deque(maxlen=window_size)  # BFS队列
        self.root_nodes: List[str] = []  # 根节点列表
        self.db_session = None

        # 批量写入缓冲区
        self._write_buffer: List[ContextNode] = []
        self._write_buffer_user_ids: Set[str] = set()

        # 垃圾回收状态
        self._gc_running = False
        self._last_gc_time = datetime.now()

        # 内存监控
        self._max_memory_nodes = 1000  # 最大节点数限制
        self._memory_warning_threshold = 0.8  # 内存警告阈值

        logger.info("ShortTermMemoryManager 初始化完成，窗口大小: %d, 批量大小: %d, GC间隔: %ds",
                   window_size, batch_size, gc_interval)

    def _get_db_session(self):
        """获取数据库会话"""
        if self.db_session is None:
            try:
                from core.database import get_session
                self.db_session = get_session()
            except Exception as e:
                logger.warning("数据库会话初始化失败: %s，将使用纯内存模式", e)
        return self.db_session

    @contextmanager
    def _db_transaction(self):
        """数据库事务上下文管理器"""
        session = self._get_db_session()
        if session is None:
            yield None
            return

        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("数据库事务失败: %s", e)
            raise

    def _batch_save_nodes_to_db(self, nodes: List[ContextNode], user_id: str):
        """批量保存节点到数据库

        Args:
            nodes: 节点列表
            user_id: 用户ID
        """
        if not nodes:
            return

        try:
            from core.database import BFSContextNode

            session = self._get_db_session()
            if session is None:
                return

            # 批量查询已存在的节点
            node_ids = [node.node_id for node in nodes]
            existing_nodes = session.query(BFSContextNode).filter(
                BFSContextNode.node_id.in_(node_ids)
            ).all()
            existing_map = {node.node_id: node for node in existing_nodes}

            # 批量插入或更新
            for node in nodes:
                existing = existing_map.get(node.node_id)

                if existing:
                    # 更新
                    existing.content = node.content
                    existing.summary = node.summary
                    existing.parent_id = node.parent_id
                    existing.children_ids = node.children
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
                        created_at=node.created_at,
                        updated_at=datetime.now()
                    )
                    session.add(new_node)

            session.commit()
            logger.debug("批量保存 %d 个节点到数据库", len(nodes))
        except Exception as e:
            logger.error("批量保存节点到数据库失败: %s", e)
            if session:
                session.rollback()

    def _flush_write_buffer(self, user_id: str):
        """刷新写入缓冲区到数据库"""
        if not self._write_buffer:
            return

        try:
            self._batch_save_nodes_to_db(self._write_buffer, user_id)
            logger.info("刷新写入缓冲区: %d 个节点", len(self._write_buffer))
        except Exception as e:
            logger.error("刷新写入缓冲区失败: %s", e)
        finally:
            self._write_buffer.clear()
            self._write_buffer_user_ids.clear()

    def _queue_node_for_write(self, node: ContextNode, user_id: str):
        """将节点加入写入队列"""
        self._write_buffer.append(node)
        self._write_buffer_user_ids.add(user_id)

        # 达到批量大小时刷新
        if len(self._write_buffer) >= self.batch_size:
            self._flush_write_buffer(user_id)

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

    def _batch_delete_nodes_from_db(self, node_ids: List[str]):
        """批量删除节点"""
        if not node_ids:
            return

        try:
            from core.database import BFSContextNode

            session = self._get_db_session()
            if session is None:
                return

            session.query(BFSContextNode).filter(
                BFSContextNode.node_id.in_(node_ids)
            ).delete(synchronize_session=False)
            session.commit()
            logger.debug("批量删除 %d 个节点", len(node_ids))
        except Exception as e:
            logger.error("批量删除节点失败: %s", e)
            if session:
                session.rollback()

    def load_from_db(self, user_id: str):
        """从数据库加载用户的BFS树

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
                context_node.created_at = db_node.created_at

                self.nodes[db_node.node_id] = context_node

                # 记录根节点
                if db_node.node_type == "root":
                    self.root_nodes.append(db_node.node_id)

                # 恢复BFS队列（只包含text类型的节点）
                if db_node.node_type == "text" and db_node.queue_order is not None:
                    self.queue.append(db_node.node_id)

            # 标记孤立节点
            self._mark_orphan_nodes()

            logger.info("✅ 从数据库恢复了用户 %s 的记忆：共 %d 个节点，队列大小 %d，孤立节点: %d",
                       user_id, len(self.nodes), len(self.queue), self._count_orphan_nodes())
        except Exception as e:
            logger.error("从数据库加载记忆失败: %s", e, exc_info=True)

    def _mark_orphan_nodes(self):
        """标记孤立节点（没有父节点引用的节点）"""
        # 重置所有孤立标记
        for node in self.nodes.values():
            node.is_orphan = False

        # 从根节点开始遍历，标记可达节点
        visited = set()

        for root_id in self.root_nodes:
            if root_id in self.nodes:
                self._mark_reachable_nodes(root_id, visited)

        # 标记未访问的节点为孤立节点
        for node_id, node in self.nodes.items():
            if node_id not in visited:
                node.is_orphan = True

    def _mark_reachable_nodes(self, node_id: str, visited: Set[str]):
        """递归标记可达节点"""
        if node_id in visited or node_id not in self.nodes:
            return

        visited.add(node_id)
        node = self.nodes[node_id]
        node.last_accessed = datetime.now()
        node.access_count += 1

        for child_id in node.children:
            self._mark_reachable_nodes(child_id, visited)

    def _count_orphan_nodes(self) -> int:
        """统计孤立节点数量"""
        return sum(1 for node in self.nodes.values() if node.is_orphan)

    async def _garbage_collect(self, user_id: str):
        """垃圾回收：清理孤立节点和过期节点"""
        try:
            # 标记孤立节点
            self._mark_orphan_nodes()

            # 收集待删除的节点
            orphan_nodes = [
                node_id for node_id, node in self.nodes.items()
                if node.is_orphan and node_id not in self.root_nodes
            ]

            if not orphan_nodes:
                return

            logger.info("开始垃圾回收，发现 %d 个孤立节点", len(orphan_nodes))

            # 批量删除孤立节点
            self._batch_delete_nodes_from_db(orphan_nodes)

            # 从内存中移除
            for node_id in orphan_nodes:
                if node_id in self.nodes:
                    del self.nodes[node_id]
                if node_id in self.queue:
                    self.queue.remove(node_id)

            logger.info("垃圾回收完成，清理了 %d 个孤立节点", len(orphan_nodes))

            # 强制垃圾回收
            gc.collect()

        except Exception as e:
            logger.error("垃圾回收失败: %s", e)

    def _check_memory_pressure(self) -> bool:
        """检查内存压力"""
        total_nodes = len(self.nodes)
        memory_pressure = total_nodes / self._max_memory_nodes

        if memory_pressure > self._memory_warning_threshold:
            logger.warning("内存压力过高: %d/%d (%.1f%%)",
                          total_nodes, self._max_memory_nodes, memory_pressure * 100)
            return True
        return False

    def add_context(self, user_id: str, content: str, context_type: str = "conversation") -> str:
        """添加新的上下文

        Args:
            user_id: 用户ID
            content: 上下文内容
            context_type: 上下文类型 (conversation/user/assistant/system)

        Returns:
            文本节点ID（用于加入队列）
        """
        # 检查内存压力
        if self._check_memory_pressure():
            # 触发垃圾回收
            asyncio.create_task(self._garbage_collect(user_id))

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
            self._queue_node_for_write(global_root, user_id)

        global_root = self.nodes[global_root_id]

        # 第2层：功能层 - 根据context_type分类
        function_node_id = f"func_{user_id}_{context_type}"

        if function_node_id not in self.nodes:
            function_node = ContextNode(
                node_id=function_node_id,
                node_type="function",
                content=context_type,  # conversation/user/assistant/system
                parent_id=global_root_id
            )
            self.nodes[function_node_id] = function_node
            global_root.children.append(function_node_id)
            self._queue_node_for_write(function_node, user_id)

        function_node = self.nodes[function_node_id]

        # 第3层：文本层节点
        text_node_id = f"text_{user_id}_{len(self.nodes)}"
        text_node = ContextNode(
            node_id=text_node_id,
            node_type="text",
            content=content[:100] + "..." if len(content) > 100 else content,
            parent_id=function_node_id
        )
        text_node.summary = content[:50] + "..." if len(content) > 50 else content
        self.nodes[text_node_id] = text_node
        function_node.children.append(text_node_id)

        # 第4层：段落层节点
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

        # 将文本节点加入队列（用于滑动窗口管理）
        queue_order = len(self.queue)
        self.queue.append(text_node_id)

        # 批量写入数据库
        self._queue_node_for_write(global_root, user_id)
        self._queue_node_for_write(function_node, user_id)
        self._queue_node_for_write(text_node, user_id, queue_order=queue_order)

        # 段落节点也加入写入队列
        for para_node_id in text_node.children:
            if para_node_id in self.nodes:
                self._queue_node_for_write(self.nodes[para_node_id], user_id)

        # 维护队列大小
        if len(self.queue) > self.window_size:
            removed_node_id = self.queue.popleft()
            # 移除相关节点
            self._remove_node(removed_node_id, user_id)

        logger.info("添加新上下文，用户: %s，类型: %s，内容长度: %d，总节点: %d",
                   user_id, context_type, len(content), len(self.nodes))
        return text_node_id

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
                "content": f"[ROOT] {global_root.content}"
            })

        # BFS遍历队列中的文本节点
        for node_id in list(self.queue):
            if node_id not in self.nodes:
                continue

            text_node = self.nodes[node_id]

            # 更新访问时间
            text_node.last_accessed = datetime.now()
            text_node.access_count += 1

            # 向上查找功能层节点
            function_node = self._find_parent(text_node, "function")
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

    def clear_context(self, user_id: str):
        """清除指定用户的上下文"""
        # 先刷新写入缓冲区
        self._flush_write_buffer(user_id)

        # 找出该用户的所有节点
        user_nodes = [node_id for node_id in self.nodes if user_id in node_id]

        # 从队列中移除
        for node_id in user_nodes:
            if node_id in self.queue:
                self.queue.remove(node_id)

        # 批量删除节点
        self._batch_delete_nodes_from_db(user_nodes)

        # 移除节点
        for node_id in user_nodes:
            if node_id in self.nodes:
                del self.nodes[node_id]

        logger.info("已清除用户 %s 的上下文，共 %d 个节点", user_id, len(user_nodes))

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_nodes": len(self.nodes),
            "queue_size": len(self.queue),
            "window_size": self.window_size,
            "root_nodes": len(self.root_nodes),
            "orphan_nodes": self._count_orphan_nodes(),
            "write_buffer_size": len(self._write_buffer),
            "memory_pressure": len(self.nodes) / self._max_memory_nodes
        }

    async def start_gc_loop(self, user_id: str):
        """启动垃圾回收循环"""
        if self._gc_running:
            return

        self._gc_running = True
        logger.info("启动垃圾回收循环")

        while self._gc_running:
            try:
                await asyncio.sleep(self.gc_interval)
                await self._garbage_collect(user_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("垃圾回收循环异常: %s", e)

    def stop_gc_loop(self):
        """停止垃圾回收循环"""
        self._gc_running = False
        logger.info("停止垃圾回收循环")

    def shutdown(self, user_id: str):
        """关闭管理器，清理资源"""
        # 停止垃圾回收
        self.stop_gc_loop()

        # 刷新写入缓冲区
        self._flush_write_buffer(user_id)

        # 关闭数据库会话
        if self.db_session:
            try:
                self.db_session.close()
                logger.info("数据库会话已关闭")
            except Exception as e:
                logger.error("关闭数据库会话失败: %s", e)

        logger.info("ShortTermMemoryManager 已关闭")


# 全局短时记忆管理器（支持分层树状索引 + BFS队列）
short_term_memory = ShortTermMemoryManager(window_size=20, batch_size=50, gc_interval=300)
