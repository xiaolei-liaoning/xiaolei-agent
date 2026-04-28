#!/usr/bin/env python3
"""
缓存管理器：管理系统缓存，减少频繁访问数据的内存开销
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from functools import lru_cache

logger = logging.getLogger(__name__)

class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        """初始化缓存管理器"""
        self.caches = {
            "memory": {},  # 内存缓存
            "disk": {}     # 磁盘缓存（模拟）
        }
        self.cache_config = {
            "memory": {
                "max_size": 500,  # 最大缓存数量（减少内存使用）
                "expiry": 1800,     # 缓存过期时间（秒，缩短为30分钟）
                "cleanup_interval": 30  # 清理间隔（秒，增加清理频率）
            },
            "disk": {
                "max_size": 5000,  # 减少磁盘缓存大小
                "expiry": 43200,  # 缓存过期时间（秒，缩短为12小时）
                "cleanup_interval": 1800  # 清理间隔（秒，增加清理频率）
            }
        }
        self.last_cleanup = {
            "memory": datetime.now(),
            "disk": datetime.now()
        }
        logger.info("缓存管理器初始化完成")
    
    def get(self, cache_type: str, key: str) -> Optional[Any]:
        """获取缓存
        
        Args:
            cache_type: 缓存类型 (memory/disk)
            key: 缓存键
            
        Returns:
            缓存值，如果不存在或已过期则返回None
        """
        if cache_type not in self.caches:
            logger.error(f"缓存类型不存在: {cache_type}")
            return None
        
        # 检查是否需要清理过期缓存
        self._cleanup_expired(cache_type)
        
        # 获取缓存
        if key in self.caches[cache_type]:
            cache_item = self.caches[cache_type][key]
            # 检查是否过期
            if not self._is_expired(cache_item):
                # 更新访问时间
                cache_item["last_access"] = datetime.now().isoformat()
                cache_item["access_count"] = cache_item.get("access_count", 0) + 1
                return cache_item["value"]
            else:
                # 缓存已过期，删除
                del self.caches[cache_type][key]
                logger.debug(f"缓存已过期: {key}")
        
        return None
    
    def set(self, cache_type: str, key: str, value: Any, expiry: Optional[int] = None) -> bool:
        """设置缓存
        
        Args:
            cache_type: 缓存类型 (memory/disk)
            key: 缓存键
            value: 缓存值
            expiry: 过期时间（秒），如果为None则使用默认值
            
        Returns:
            是否设置成功
        """
        if cache_type not in self.caches:
            logger.error(f"缓存类型不存在: {cache_type}")
            return False
        
        # 检查是否需要清理过期缓存
        self._cleanup_expired(cache_type)
        
        # 检查缓存大小
        if len(self.caches[cache_type]) >= self.cache_config[cache_type]["max_size"]:
            # 清理最久未使用的缓存
            self._cleanup_lru(cache_type)
        
        # 设置缓存
        expiry = expiry or self.cache_config[cache_type]["expiry"]
        self.caches[cache_type][key] = {
            "value": value,
            "created": datetime.now().isoformat(),
            "last_access": datetime.now().isoformat(),
            "expiry": expiry,
            "access_count": 1
        }
        
        logger.debug(f"设置缓存: {key}")
        return True
    
    def delete(self, cache_type: str, key: str) -> bool:
        """删除缓存
        
        Args:
            cache_type: 缓存类型 (memory/disk)
            key: 缓存键
            
        Returns:
            是否删除成功
        """
        if cache_type not in self.caches:
            logger.error(f"缓存类型不存在: {cache_type}")
            return False
        
        if key in self.caches[cache_type]:
            del self.caches[cache_type][key]
            logger.debug(f"删除缓存: {key}")
            return True
        
        return False
    
    def clear(self, cache_type: str) -> bool:
        """清空缓存
        
        Args:
            cache_type: 缓存类型 (memory/disk)
            
        Returns:
            是否清空成功
        """
        if cache_type not in self.caches:
            logger.error(f"缓存类型不存在: {cache_type}")
            return False
        
        self.caches[cache_type].clear()
        logger.info(f"清空{cache_type}缓存")
        return True
    
    def _is_expired(self, cache_item: Dict) -> bool:
        """检查缓存是否过期
        
        Args:
            cache_item: 缓存项
            
        Returns:
            是否过期
        """
        created = datetime.fromisoformat(cache_item["created"])
        expiry = cache_item["expiry"]
        return (datetime.now() - created).total_seconds() > expiry
    
    def _cleanup_expired(self, cache_type: str):
        """清理过期缓存
        
        Args:
            cache_type: 缓存类型 (memory/disk)
        """
        now = datetime.now()
        if (now - self.last_cleanup[cache_type]).total_seconds() < self.cache_config[cache_type]["cleanup_interval"]:
            return
        
        expired_keys = []
        for key, item in self.caches[cache_type].items():
            if self._is_expired(item):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.caches[cache_type][key]
        
        if expired_keys:
            logger.debug(f"清理过期缓存: {len(expired_keys)}个")
        
        self.last_cleanup[cache_type] = now
    
    def _cleanup_lru(self, cache_type: str):
        """清理最久未使用的缓存
        
        Args:
            cache_type: 缓存类型 (memory/disk)
        """
        # 按最后访问时间排序
        items = sorted(
            self.caches[cache_type].items(),
            key=lambda x: x[1]["last_access"]
        )
        
        # 删除最久未使用的10%缓存
        to_delete = len(items) // 10
        if to_delete < 1:
            to_delete = 1
        
        for key, _ in items[:to_delete]:
            del self.caches[cache_type][key]
        
        logger.debug(f"清理最久未使用的缓存: {to_delete}个")
    
    def get_stats(self, cache_type: str) -> Dict[str, Any]:
        """获取缓存统计信息
        
        Args:
            cache_type: 缓存类型 (memory/disk)
            
        Returns:
            缓存统计信息
        """
        if cache_type not in self.caches:
            logger.error(f"缓存类型不存在: {cache_type}")
            return {}
        
        # 检查是否需要清理过期缓存
        self._cleanup_expired(cache_type)
        
        total = len(self.caches[cache_type])
        max_size = self.cache_config[cache_type]["max_size"]
        
        # 计算缓存使用情况
        usage = (total / max_size) * 100 if max_size > 0 else 0
        
        # 计算平均访问次数
        access_counts = [item.get("access_count", 0) for item in self.caches[cache_type].values()]
        avg_access = sum(access_counts) / len(access_counts) if access_counts else 0
        
        return {
            "total": total,
            "max_size": max_size,
            "usage": usage,
            "avg_access": avg_access,
            "last_cleanup": self.last_cleanup[cache_type].isoformat()
        }
    
    def get_cache_keys(self, cache_type: str) -> List[str]:
        """获取缓存键列表
        
        Args:
            cache_type: 缓存类型 (memory/disk)
            
        Returns:
            缓存键列表
        """
        if cache_type not in self.caches:
            logger.error(f"缓存类型不存在: {cache_type}")
            return []
        
        # 检查是否需要清理过期缓存
        self._cleanup_expired(cache_type)
        
        return list(self.caches[cache_type].keys())

# 全局缓存管理器实例
cache_manager = CacheManager()

def get_cache_manager() -> CacheManager:
    """获取缓存管理器实例
    
    Returns:
        CacheManager实例
    """
    return cache_manager

# 缓存装饰器
def cacheable(cache_type: str = "memory", expiry: int = 3600):
    """缓存装饰器
    
    Args:
        cache_type: 缓存类型 (memory/disk)
        expiry: 过期时间（秒）
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key = f"{func.__name__}:{args}:{kwargs}"
            
            # 尝试从缓存获取
            cached_value = cache_manager.get(cache_type, key)
            if cached_value is not None:
                logger.debug(f"从缓存获取: {key}")
                return cached_value
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 缓存结果
            cache_manager.set(cache_type, key, result, expiry)
            logger.debug(f"缓存结果: {key}")
            
            return result
        return wrapper
    return decorator