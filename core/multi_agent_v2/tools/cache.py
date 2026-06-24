"""
工具调用缓存 — 避免重复执行相同工具调用

支持：
- 基于工具名 + 参数的缓存键
- 可配置的 TTL（生存时间）
- LRU（最近最少使用）淘汰策略
- 缓存命中率统计

项目分析文件缓存：
- 跟踪哪些文件已注入上下文，防止 read_file 重复读取
"""

import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# ToolCache — 工具调用缓存（原有）
# ═══════════════════════════════════════════════════════════════════

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
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._stats = CacheStats()

    def _generate_key(self, tool_name: str, arguments: Dict) -> str:
        sorted_args = json.dumps(arguments, sort_keys=True, default=str)
        key_data = f"{tool_name}:{sorted_args}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, tool_name: str, arguments: Dict) -> Optional[Any]:
        self._stats.total_requests += 1
        key = self._generate_key(tool_name, arguments)
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry.created_at > entry.ttl:
                self._remove(key)
                self._stats.misses += 1
                return None
            entry.last_accessed = time.time()
            entry.access_count += 1
            self._cache.move_to_end(key)
            self._stats.hits += 1
            logger.debug(f"缓存命中: {tool_name}")
            return entry.value
        self._stats.misses += 1
        return None

    def set(self, tool_name: str, arguments: Dict, value: Any, ttl: float = None) -> None:
        key = self._generate_key(tool_name, arguments)
        if key in self._cache:
            del self._cache[key]
        while len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            self._remove(oldest_key)
            self._stats.evictions += 1
        now = time.time()
        entry = CacheEntry(
            key=key, value=value, created_at=now,
            last_accessed=now, access_count=0,
            ttl=ttl or self._default_ttl,
        )
        self._cache[key] = entry

    def _remove(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        self._cache.clear()
        logger.info("缓存已清空")

    def get_stats(self) -> Dict:
        return {
            "size": len(self._cache), "max_size": self._max_size,
            "hits": self._stats.hits, "misses": self._stats.misses,
            "evictions": self._stats.evictions,
            "hit_rate": f"{self._stats.hit_rate:.2%}",
        }

    def cleanup_expired(self) -> int:
        now = time.time()
        expired_keys = [key for key, entry in self._cache.items()
                        if now - entry.created_at > entry.ttl]
        for key in expired_keys:
            self._remove(key)
        if expired_keys:
            logger.info(f"清理了 {len(expired_keys)} 个过期缓存条目")
        return len(expired_keys)


# 全局工具缓存实例
_tool_cache: Optional[ToolCache] = None


def get_tool_cache(max_size: int = 1000, default_ttl: float = 3600) -> ToolCache:
    global _tool_cache
    if _tool_cache is None:
        _tool_cache = ToolCache(max_size, default_ttl)
    return _tool_cache


# 可缓存的工具列表
CACHEABLE_TOOLS = {"web_search", "fetch_url", "fetch_json", "rag_search"}


def is_cacheable(tool_name: str, arguments: Dict) -> bool:
    return tool_name in CACHEABLE_TOOLS


# ═══════════════════════════════════════════════════════════════════
# 项目分析文件缓存（新增）
# ═══════════════════════════════════════════════════════════════════

_cached_project_files: set = set()
"""已通过 Phase 2 注入上下文的文件路径集合"""


def cache_files(paths: set, base_dir: str = "") -> None:
    """注册一批已注入的文件路径（自动转为绝对路径）"""
    abs_paths = set()
    for p in paths:
        if base_dir and not os.path.isabs(p):
            p = os.path.join(base_dir, p)
        abs_paths.add(os.path.abspath(os.path.expanduser(p)))
    _cached_project_files.update(abs_paths)


def is_file_cached(filepath: str) -> bool:
    """检查文件是否已通过项目分析注入上下文"""
    full = os.path.abspath(os.path.expanduser(filepath)) if "~" not in filepath else os.path.expanduser(filepath)
    if full in _cached_project_files:
        return True
    base = os.path.basename(full).lower()
    return base in {os.path.basename(p).lower() for p in _cached_project_files}


def clear_project_file_cache() -> None:
    """清理项目分析文件缓存"""
    _cached_project_files.clear()
