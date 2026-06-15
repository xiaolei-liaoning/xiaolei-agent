"""
ToolCache — 工具调用结果缓存（轻量版）

用于 MiddlewareChain 层，缓存读类工具的结果以避免重复执行。
与 tools/cache.py 的全局缓存不同，本模块：
  - 专为 MiddlewareChain 的 on_wrap_tool_call 设计
  - 默认更小的容量和更短的 TTL（100条/60秒）
  - 使用 asyncio.Lock 保证线程安全
  - 写工具（write/edit/apply_patch/bash/shell/task）默认跳过
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 写工具名单（结果不缓存）
WRITE_TOOLS = {
    "write", "write_file",
    "edit", "edit_file",
    "apply_patch",
    "bash", "shell", "execute_shell",
    "task", "create_task",
    "write_todos",
}


class ToolCache:
    """线程安全的 LRU 工具结果缓存"""

    def __init__(self, max_size: int = 100, ttl: float = 60.0):
        self._max_size = max_size
        self._ttl = ttl
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._names: Dict[str, str] = {}  # key -> tool_name
        self._timestamps: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    # ── 键生成 ──

    @staticmethod
    def _make_key(tool_name: str, arguments: Dict) -> str:
        """生成缓存键: md5(tool_name + json.dumps(sorted(arguments)))"""
        sorted_args = json.dumps(arguments, sort_keys=True, default=str)
        raw = f"{tool_name}:{sorted_args}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _is_cacheable(tool_name: str) -> bool:
        """判断工具结果是否可缓存（跳过写工具）"""
        return tool_name not in WRITE_TOOLS

    # ── 核心操作 ──

    async def get(self, tool_name: str, arguments: Dict) -> Optional[Any]:
        """获取缓存结果

        Returns:
            缓存的值，未命中或过期返回 None
        """
        if not self._is_cacheable(tool_name):
            return None

        key = self._make_key(tool_name, arguments)

        async with self._lock:
            if key not in self._cache:
                return None

            # 检查 TTL
            created = self._timestamps.get(key, 0)
            if time.time() - created > self._ttl:
                self._evict(key)
                return None

            # LRU: 移到末尾
            value = self._cache.pop(key)
            self._cache[key] = value
            logger.debug(f"缓存命中: {tool_name}")
            return value

    async def set(self, tool_name: str, arguments: Dict, value: Any) -> None:
        """设置缓存

        Args:
            tool_name: 工具名
            arguments: 工具参数
            value: 要缓存的值
        """
        if not self._is_cacheable(tool_name):
            return

        key = self._make_key(tool_name, arguments)

        async with self._lock:
            if key in self._cache:
                del self._cache[key]

            # LRU 淘汰
            while len(self._cache) >= self._max_size:
                oldest_key = next(iter(self._cache))
                self._evict(oldest_key)

            self._cache[key] = value
            self._names[key] = tool_name
            self._timestamps[key] = time.time()
            logger.debug(f"缓存设置: {tool_name} (size={len(self._cache)})")

    async def invalidate(self, pattern: str) -> int:
        """按模式使缓存失效

        Args:
            pattern: 子串匹配模式（工具名包含该子串的条目将被清除）
        Returns:
            失效条目数
        """
        count = 0
        async with self._lock:
            keys_to_remove = [
                k for k in self._cache.keys()
                if pattern in self._names.get(k, "")
            ]
            for key in keys_to_remove:
                self._evict(key)
                count += 1
        if count:
            logger.info(f"缓存失效: pattern='{pattern}' 清除{count}条")
        return count

    async def clear(self) -> None:
        """清空所有缓存"""
        async with self._lock:
            self._cache.clear()
            self._names.clear()
            self._timestamps.clear()
        logger.info("缓存已清空")

    async def get_stats(self) -> Dict:
        """获取缓存统计"""
        async with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl,
            }

    # ── 内部方法 ──

    def _evict(self, key: str) -> None:
        """从缓存中移除条目（无锁，调用者需持有锁）"""
        self._cache.pop(key, None)
        self._names.pop(key, None)
        self._timestamps.pop(key, None)


# 全局实例
_tool_cache: Optional[ToolCache] = None


def get_tool_cache(max_size: int = 100, ttl: float = 60.0) -> ToolCache:
    """获取全局 ToolCache 实例"""
    global _tool_cache
    if _tool_cache is None:
        _tool_cache = ToolCache(max_size=max_size, ttl=ttl)
    return _tool_cache
