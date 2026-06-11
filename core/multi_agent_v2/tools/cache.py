"""
工具调用缓存 — 避免重复执行相同工具调用

支持：
- 基于工具名 + 参数的缓存键
- 可配置的 TTL（生存时间）
- LRU（最近最少使用）淘汰策略
- 缓存命中率统计
"""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: float
    last_accessed: float
    access_count: int = 0
    ttl: float = 3600  # 默认 1 小时


@dataclass
class CacheStats:
    """缓存统计"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_requests: int = 0

    @property
    def hit_rate(self) -> float:
        """命中率"""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests


class ToolCache:
    """工具调用缓存"""

    def __init__(self, max_size: int = 1000, default_ttl: float = 3600):
        """
        初始化缓存

        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认 TTL（秒）
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._stats = CacheStats()

    def _generate_key(self, tool_name: str, arguments: Dict) -> str:
        """生成缓存键"""
        # 排序参数以确保相同的参数生成相同的键
        sorted_args = json.dumps(arguments, sort_keys=True, default=str)
        key_data = f"{tool_name}:{sorted_args}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, tool_name: str, arguments: Dict) -> Optional[Any]:
        """
        获取缓存结果

        Args:
            tool_name: 工具名
            arguments: 工具参数

        Returns:
            缓存的结果，如果未命中则返回 None
        """
        self._stats.total_requests += 1
        key = self._generate_key(tool_name, arguments)

        if key in self._cache:
            entry = self._cache[key]

            # 检查是否过期
            if time.time() - entry.created_at > entry.ttl:
                self._remove(key)
                self._stats.misses += 1
                return None

            # 更新访问信息
            entry.last_accessed = time.time()
            entry.access_count += 1

            # 移到末尾（最近使用）
            self._cache.move_to_end(key)

            self._stats.hits += 1
            logger.debug(f"缓存命中: {tool_name}")
            return entry.value

        self._stats.misses += 1
        return None

    def set(self, tool_name: str, arguments: Dict, value: Any, ttl: float = None) -> None:
        """
        设置缓存

        Args:
            tool_name: 工具名
            arguments: 工具参数
            value: 缓存的值
            ttl: 生存时间（秒）
        """
        key = self._generate_key(tool_name, arguments)

        # 如果已存在，先删除
        if key in self._cache:
            del self._cache[key]

        # 检查是否需要淘汰
        while len(self._cache) >= self._max_size:
            # 淘汰最旧的条目
            oldest_key = next(iter(self._cache))
            self._remove(oldest_key)
            self._stats.evictions += 1

        # 添加新条目
        now = time.time()
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            last_accessed=now,
            access_count=0,
            ttl=ttl or self._default_ttl,
        )
        self._cache[key] = entry
        logger.debug(f"缓存设置: {tool_name}")

    def _remove(self, key: str) -> None:
        """删除缓存条目"""
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        logger.info("缓存已清空")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "evictions": self._stats.evictions,
            "hit_rate": f"{self._stats.hit_rate:.2%}",
        }

    def cleanup_expired(self) -> int:
        """清理过期条目"""
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now - entry.created_at > entry.ttl
        ]

        for key in expired_keys:
            self._remove(key)

        if expired_keys:
            logger.info(f"清理了 {len(expired_keys)} 个过期缓存条目")

        return len(expired_keys)


# 全局缓存实例
_tool_cache: Optional[ToolCache] = None


def get_tool_cache(max_size: int = 1000, default_ttl: float = 3600) -> ToolCache:
    """获取全局工具缓存实例"""
    global _tool_cache
    if _tool_cache is None:
        _tool_cache = ToolCache(max_size, default_ttl)
    return _tool_cache


# 可缓存的工具列表（只有这些工具的结果会被缓存）
CACHEABLE_TOOLS = {
    "web_search",
    "fetch_url",
    "fetch_json",
    "rag_search",
}


def is_cacheable(tool_name: str, arguments: Dict) -> bool:
    """检查工具调用是否可缓存"""
    # 只缓存指定的工具
    if tool_name not in CACHEABLE_TOOLS:
        return False

    return True
