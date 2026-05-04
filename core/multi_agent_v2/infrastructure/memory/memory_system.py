"""
记忆系统 - Agent的记忆管理

支持：
1. 短期记忆 - 临时存储，快速访问
2. 长期记忆 - 持久化存储，重要信息
3. 情景记忆 - 事件序列，上下文
4. 语义记忆 - 知识和概念
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import time
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """记忆类型"""
    SHORT_TERM = "short_term"      # 短期记忆
    LONG_TERM = "long_term"        # 长期记忆
    EPISODIC = "episodic"          # 情景记忆
    SEMANTIC = "semantic"          # 语义记忆


@dataclass
class MemoryItem:
    """记忆项"""
    item_id: str
    memory_type: MemoryType
    key: str
    value: Any
    importance: float = 0.5
    access_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemorySystem:
    """记忆系统"""

    def __init__(self, agent_id: str, storage_path: Optional[str] = None):
        self.agent_id = agent_id
        self.storage_path = storage_path or f"/tmp/agent_memory_{agent_id}"

        # 记忆存储
        self.short_term: Dict[str, MemoryItem] = {}
        self.long_term: Dict[str, MemoryItem] = {}
        self.episodic: List[MemoryItem] = []
        self.semantic: Dict[str, MemoryItem] = {}

        # 配置
        self.short_term_capacity = 1000
        self.long_term_capacity = 10000
        self.episodic_capacity = 5000

        # 锁
        self._lock = asyncio.Lock()

        logger.info(f"记忆系统初始化完成: {agent_id}")

    async def remember(
        self,
        key: str,
        value: Any,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        importance: float = 0.5,
        expires_in: Optional[float] = None
    ) -> str:
        """记忆：存储信息

        Args:
            key: 记忆键
            value: 记忆值
            memory_type: 记忆类型
            importance: 重要性 (0-1)
            expires_in: 过期时间（秒）

        Returns:
            记忆项ID
        """
        async with self._lock:
            item_id = f"{self.agent_id}_{key}_{int(time.time())}"

            # 计算过期时间
            expires_at = None
            if expires_in:
                expires_at = time.time() + expires_in

            # 创建记忆项
            item = MemoryItem(
                item_id=item_id,
                memory_type=memory_type,
                key=key,
                value=value,
                importance=importance,
                expires_at=expires_at
            )

            # 存储到对应的记忆类型
            if memory_type == MemoryType.SHORT_TERM:
                await self._store_short_term(item)
            elif memory_type == MemoryType.LONG_TERM:
                await self._store_long_term(item)
            elif memory_type == MemoryType.EPISODIC:
                await self._store_episodic(item)
            elif memory_type == MemoryType.SEMANTIC:
                await self._store_semantic(item)

            logger.debug(f"记忆已存储: {key} ({memory_type.value})")
            return item_id

    async def recall(self, key: str, memory_type: Optional[MemoryType] = None) -> Optional[Any]:
        """回忆：检索信息

        Args:
            key: 记忆键
            memory_type: 记忆类型（None表示搜索所有类型）

        Returns:
            记忆值
        """
        async with self._lock:
            # 搜索指定类型的记忆
            if memory_type:
                item = await self._get_item(key, memory_type)
                if item:
                    await self._update_access(item)
                    return item.value
                return None

            # 搜索所有类型的记忆
            for mem_type in MemoryType:
                item = await self._get_item(key, mem_type)
                if item:
                    await self._update_access(item)
                    return item.value

            return None

    async def forget(self, key: str, memory_type: Optional[MemoryType] = None) -> bool:
        """遗忘：删除记忆

        Args:
            key: 记忆键
            memory_type: 记忆类型（None表示删除所有类型）

        Returns:
            是否成功删除
        """
        async with self._lock:
            if memory_type:
                return await self._remove_item(key, memory_type)

            # 删除所有类型的记忆
            removed = False
            for mem_type in MemoryType:
                if await self._remove_item(key, mem_type):
                    removed = True

            return removed

    async def search(self, query: str, memory_type: Optional[MemoryType] = None) -> List[MemoryItem]:
        """搜索记忆

        Args:
            query: 搜索查询
            memory_type: 记忆类型（None表示搜索所有类型）

        Returns:
            匹配的记忆项列表
        """
        async with self._lock:
            results = []

            if memory_type:
                items = await self._get_all_items(memory_type)
            else:
                items = []
                for mem_type in MemoryType:
                    items.extend(await self._get_all_items(mem_type))

            # 简单的关键词匹配
            for item in items:
                if query.lower() in item.key.lower() or query.lower() in str(item.value).lower():
                    results.append(item)

            # 按重要性排序
            results.sort(key=lambda x: x.importance, reverse=True)

            return results

    async def consolidate(self) -> int:
        """整合：将短期记忆整合到长期记忆

        Returns:
            整合的记忆项数量
        """
        async with self._lock:
            consolidated = 0

            # 找出重要的短期记忆
            important_items = [
                item for item in self.short_term.values()
                if item.importance > 0.7 and item.access_count > 3
            ]

            for item in important_items:
                # 转换为长期记忆
                await self._store_long_term(item)
                # 从短期记忆中删除
                del self.short_term[item.key]
                consolidated += 1

            logger.info(f"整合了{consolidated}个记忆项")
            return consolidated

    async def cleanup(self) -> int:
        """清理：删除过期和低重要性的记忆

        Returns:
            清理的记忆项数量
        """
        async with self._lock:
            cleaned = 0
            now = time.time()

            # 清理短期记忆
            expired_keys = []
            for key, item in self.short_term.items():
                if item.expires_at and item.expires_at < now:
                    expired_keys.append(key)
                elif item.importance < 0.3 and item.access_count < 2:
                    expired_keys.append(key)

            for key in expired_keys:
                del self.short_term[key]
                cleaned += 1

            # 清理情景记忆
            self.episodic = [
                item for item in self.episodic
                if not (item.expires_at and item.expires_at < now)
            ]

            # 限制情景记忆大小
            if len(self.episodic) > self.episodic_capacity:
                removed = len(self.episodic) - self.episodic_capacity
                self.episodic = self.episodic[-self.episodic_capacity:]
                cleaned += removed

            logger.info(f"清理了{cleaned}个记忆项")
            return cleaned

    async def _store_short_term(self, item: MemoryItem) -> None:
        """存储短期记忆"""
        # 检查容量
        if len(self.short_term) >= self.short_term_capacity:
            # 删除最不重要的记忆
            least_important = min(
                self.short_term.values(),
                key=lambda x: (x.importance, x.access_count)
            )
            del self.short_term[least_important.key]

        self.short_term[item.key] = item

    async def _store_long_term(self, item: MemoryItem) -> None:
        """存储长期记忆"""
        # 检查容量
        if len(self.long_term) >= self.long_term_capacity:
            # 删除最不重要的记忆
            least_important = min(
                self.long_term.values(),
                key=lambda x: (x.importance, x.access_count)
            )
            del self.long_term[least_important.key]

        self.long_term[item.key] = item

    async def _store_episodic(self, item: MemoryItem) -> None:
        """存储情景记忆"""
        # 检查容量
        if len(self.episodic) >= self.episodic_capacity:
            # 删除最旧的记忆
            self.episodic.pop(0)

        self.episodic.append(item)

    async def _store_semantic(self, item: MemoryItem) -> None:
        """存储语义记忆"""
        self.semantic[item.key] = item

    async def _get_item(self, key: str, memory_type: MemoryType) -> Optional[MemoryItem]:
        """获取记忆项"""
        if memory_type == MemoryType.SHORT_TERM:
            return self.short_term.get(key)
        elif memory_type == MemoryType.LONG_TERM:
            return self.long_term.get(key)
        elif memory_type == MemoryType.EPISODIC:
            for item in self.episodic:
                if item.key == key:
                    return item
        elif memory_type == MemoryType.SEMANTIC:
            return self.semantic.get(key)

        return None

    async def _get_all_items(self, memory_type: MemoryType) -> List[MemoryItem]:
        """获取所有记忆项"""
        if memory_type == MemoryType.SHORT_TERM:
            return list(self.short_term.values())
        elif memory_type == MemoryType.LONG_TERM:
            return list(self.long_term.values())
        elif memory_type == MemoryType.EPISODIC:
            return self.episodic.copy()
        elif memory_type == MemoryType.SEMANTIC:
            return list(self.semantic.values())

        return []

    async def _remove_item(self, key: str, memory_type: MemoryType) -> bool:
        """删除记忆项"""
        if memory_type == MemoryType.SHORT_TERM:
            if key in self.short_term:
                del self.short_term[key]
                return True
        elif memory_type == MemoryType.LONG_TERM:
            if key in self.long_term:
                del self.long_term[key]
                return True
        elif memory_type == MemoryType.EPISODIC:
            for i, item in enumerate(self.episodic):
                if item.key == key:
                    self.episodic.pop(i)
                    return True
        elif memory_type == MemoryType.SEMANTIC:
            if key in self.semantic:
                del self.semantic[key]
                return True

        return False

    async def _update_access(self, item: MemoryItem) -> None:
        """更新访问信息"""
        item.access_count += 1
        item.last_accessed = time.time()

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "agent_id": self.agent_id,
            "short_term_count": len(self.short_term),
            "long_term_count": len(self.long_term),
            "episodic_count": len(self.episodic),
            "semantic_count": len(self.semantic),
            "total_memory": len(self.short_term) + len(self.long_term) + len(self.episodic) + len(self.semantic)
        }

    async def save_to_disk(self) -> bool:
        """保存到磁盘"""
        try:
            # 创建存储目录
            Path(self.storage_path).mkdir(parents=True, exist_ok=True)

            # 保存长期记忆
            long_term_file = Path(self.storage_path) / "long_term.json"
            with open(long_term_file, 'w', encoding='utf-8') as f:
                data = {
                    key: {
                        "item_id": item.item_id,
                        "key": item.key,
                        "value": item.value,
                        "importance": item.importance,
                        "access_count": item.access_count,
                        "created_at": item.created_at,
                        "last_accessed": item.last_accessed,
                        "metadata": item.metadata
                    }
                    for key, item in self.long_term.items()
                }
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"记忆已保存到磁盘: {long_term_file}")
            return True

        except Exception as e:
            logger.error(f"保存记忆失败: {e}")
            return False

    async def load_from_disk(self) -> bool:
        """从磁盘加载"""
        try:
            long_term_file = Path(self.storage_path) / "long_term.json"

            if not long_term_file.exists():
                logger.info("没有找到持久化的记忆文件")
                return False

            with open(long_term_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 加载长期记忆
            for key, item_data in data.items():
                item = MemoryItem(
                    item_id=item_data["item_id"],
                    memory_type=MemoryType.LONG_TERM,
                    key=item_data["key"],
                    value=item_data["value"],
                    importance=item_data["importance"],
                    access_count=item_data["access_count"],
                    created_at=item_data["created_at"],
                    last_accessed=item_data["last_accessed"],
                    metadata=item_data.get("metadata", {})
                )
                self.long_term[key] = item

            logger.info(f"从磁盘加载了{len(self.long_term)}个长期记忆")
            return True

        except Exception as e:
            logger.error(f"加载记忆失败: {e}")
            return False
