"""Redis 连接池管理器（单例模式）

DB 分配:
- db0: 爬虫状态
- db1: 工具缓存
- db2: 任务队列
- db3: 角色记忆

特性:
- 连接池参数: max_connections=10, socket_timeout=5, socket_connect_timeout=3
- 健康检查: 定期 ping 检测连接
- 工具缓存: cache_get / cache_set / cache_delete
- 发布订阅: publish / subscribe
- 全局便捷函数 get_redis(db)
"""

import redis
import os
import logging
import threading
import json
from typing import Optional, List, Callable, Any

logger = logging.getLogger(__name__)

# DB 常量
DB_SCRAPER = 0  # 爬虫状态
DB_CACHE = 1    # 工具缓存
DB_TASK = 2     # 任务队列
DB_MEMORY = 3   # 角色记忆

# 连接池默认参数
_POOL_KWARGS = {
    "max_connections": 10,
    "socket_timeout": 5,
    "socket_connect_timeout": 3,
    "retry_on_timeout": True,
    "decode_responses": True,
}


class RedisPoolManager:
    """Redis 单例连接池管理器。

    支持 4 个逻辑 DB，每个 DB 独立连接池。
    提供缓存快捷方法和发布订阅支持。
    """

    _instance: Optional["RedisPoolManager"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        if RedisPoolManager._instance is not None:
            raise RuntimeError("请使用 RedisPoolManager.get_instance() 获取实例")
        self._pools: dict[int, redis.ConnectionPool] = {}
        self._clients: dict[int, redis.Redis] = {}
        self._client_lock: threading.Lock = threading.Lock()
        self._pubsub: dict[int, redis.client.PubSub] = {}
        self._host: str = os.getenv("REDIS_HOST", "localhost")
        self._port: int = int(os.getenv("REDIS_PORT", "6379"))
        self._password: Optional[str] = os.getenv("REDIS_PASSWORD", None)
        self._health_check_running: bool = False

    # ================================================================
    # 单例
    # ================================================================

    @classmethod
    def get_instance(cls) -> "RedisPoolManager":
        """获取 RedisPoolManager 单例。"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls.__new__(cls)
                    cls._instance.__init__()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅供测试使用）。"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close_all()
            cls._instance = None

    # ================================================================
    # 连接池 / 客户端
    # ================================================================

    def get_pool(self, db: int = 0) -> redis.ConnectionPool:
        """获取指定 DB 的连接池，不存在则自动创建。

        Args:
            db: Redis 数据库编号 (0-15)

        Returns:
            redis.ConnectionPool 实例
        """
        if db not in self._pools:
            self._pools[db] = redis.ConnectionPool(
                host=self._host,
                port=self._port,
                password=self._password,
                db=db,
                **_POOL_KWARGS,
            )
            logger.debug("创建 Redis 连接池: db=%d", db)
        return self._pools[db]

    def get_client(self, db: int = 0) -> redis.Redis:
        """获取指定 DB 的 Redis 客户端。

        Args:
            db: Redis 数据库编号

        Returns:
            redis.Redis 客户端实例
        """
        with self._client_lock:
            if db not in self._clients:
                self._clients[db] = redis.Redis(connection_pool=self.get_pool(db))
            return self._clients[db]

    # ================================================================
    # 健康检查
    # ================================================================

    def ping(self, db: int = 0) -> bool:
        """检测指定 DB 的连接是否可用。

        Args:
            db: Redis 数据库编号

        Returns:
            True 表示连接正常
        """
        try:
            client = self.get_client(db)
            return client.ping()
        except Exception as e:
            logger.error("Redis ping 失败 (db=%d): %s", db, e)
            return False

    def health_check_all(self) -> dict[str, bool]:
        """对所有已创建的连接池执行健康检查。

        Returns:
            {db编号: 是否健康}
        """
        results: dict[str, bool] = {}
        for db in list(self._pools.keys()):
            results[str(db)] = self.ping(db)
        return results

    # ================================================================
    # 工具缓存 (db1)
    # ================================================================

    def cache_get(self, key: str) -> Optional[Any]:
        """获取缓存值（自动 JSON 反序列化）。

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在返回 None
        """
        try:
            client = self.get_client(DB_CACHE)
            raw: Optional[str] = client.get(key)
            if raw is None:
                return None
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
        except Exception as e:
            logger.error("cache_get 失败 (key=%s): %s", key, e)
            return None

    def cache_set(
        self, key: str, value: Any, ttl: Optional[int] = None
    ) -> bool:
        """设置缓存值（自动 JSON 序列化）。

        Args:
            key:   缓存键
            value: 缓存值
            ttl:   过期时间（秒），None 表示永不过期

        Returns:
            True 表示设置成功
        """
        try:
            client = self.get_client(DB_CACHE)
            serialized: str = (
                json.dumps(value, ensure_ascii=False)
                if not isinstance(value, str)
                else value
            )
            if ttl is not None:
                client.setex(key, ttl, serialized)
            else:
                client.set(key, serialized)
            return True
        except Exception as e:
            logger.error("cache_set 失败 (key=%s): %s", key, e)
            return False

    def cache_delete(self, pattern: str) -> int:
        """删除匹配模式的缓存键。

        Args:
            pattern: glob 模式，如 "tool:*"

        Returns:
            删除的键数量
        """
        try:
            client = self.get_client(DB_CACHE)
            keys: List[str] = []
            cursor = 0
            while True:
                cursor, batch = client.scan(cursor, match=pattern, count=100)
                keys.extend(batch)
                if cursor == 0:
                    break
            if not keys:
                return 0
            return client.delete(*keys)
        except Exception as e:
            logger.error("cache_delete 失败 (pattern=%s): %s", pattern, e)
            return 0

    # ================================================================
    # 发布订阅
    # ================================================================

    def publish(self, channel: str, message: str) -> bool:
        """发布消息到频道。

        Args:
            channel: 频道名
            message: 消息内容

        Returns:
            True 表示发布成功
        """
        try:
            client = self.get_client(DB_TASK)
            client.publish(channel, message)
            logger.debug("发布消息到 %s: %s", channel, message[:50])
            return True
        except Exception as e:
            logger.error("publish 失败 (channel=%s): %s", channel, e)
            return False

    def subscribe(
        self, channel: str, callback: Callable[[str, str], None]
    ) -> bool:
        """订阅频道并在新消息到达时调用回调。

        注意：订阅是阻塞的，应在独立线程中调用。

        Args:
            channel:  频道名
            callback: 回调函数 (channel, message) -> None

        Returns:
            True 表示订阅成功启动
        """
        try:
            pubsub = self.get_client(DB_TASK).pubsub()
            pubsub.subscribe(channel)

            def _listener() -> None:
                try:
                    for item in pubsub.listen():
                        if item["type"] == "message":
                            callback(item["channel"], item["data"])
                except Exception as e:
                    logger.error("subscribe 监听异常 (channel=%s): %s", channel, e)
                finally:
                    try:
                        pubsub.unsubscribe(channel)
                        pubsub.close()
                    except Exception:
                        pass

            t = threading.Thread(target=_listener, daemon=True, name=f"redis_sub_{channel}")
            t.start()
            logger.info("已订阅频道: %s", channel)
            return True
        except Exception as e:
            logger.error("subscribe 失败 (channel=%s): %s", channel, e)
            return False

    # ================================================================
    # 资源管理
    # ================================================================

    def close_all(self) -> None:
        """关闭所有连接池和客户端，释放资源。"""
        # 关闭 pubsub
        for ps in self._pubsub.values():
            try:
                ps.close()
            except Exception:
                pass
        self._pubsub.clear()

        # 关闭客户端
        for client in self._clients.values():
            try:
                client.close()
            except Exception:
                pass
        self._clients.clear()

        # 断开连接池
        for pool in self._pools.values():
            try:
                pool.disconnect()
            except Exception:
                pass
        self._pools.clear()

        logger.info("RedisPoolManager 所有连接已关闭")


# ================================================================
# 全局便捷函数
# ================================================================

def get_redis(db: int = 0) -> redis.Redis:
    """获取指定 DB 的 Redis 客户端（全局便捷函数）。

    Args:
        db: Redis 数据库编号

    Returns:
        redis.Redis 客户端实例
    """
    return RedisPoolManager.get_instance().get_client(db)
