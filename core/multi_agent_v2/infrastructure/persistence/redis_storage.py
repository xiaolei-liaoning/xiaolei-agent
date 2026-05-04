"""
Redis持久化存储方案

功能：
1. 任务状态持久化
2. Agent状态持久化
3. 上下文数据缓存
4. 分布式锁
5. 消息队列（发布/订阅）
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

try:
    import redis
    from redis.exceptions import RedisError
except ImportError:
    redis = None
    RedisError = Exception

logger = logging.getLogger(__name__)


@dataclass
class RedisConfig:
    """Redis配置"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    socket_timeout: int = 30
    retry_on_timeout: bool = True


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RedisStorage:
    """Redis存储适配器"""

    def __init__(self, config: Optional[RedisConfig] = None):
        self.config = config or RedisConfig()
        self.client = None
        self.connected = False

    async def connect(self) -> bool:
        """连接到Redis"""
        if redis is None:
            logger.error("Redis库未安装，请安装redis-py")
            return False

        try:
            self.client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                socket_timeout=self.config.socket_timeout,
                retry_on_timeout=self.config.retry_on_timeout
            )

            # 测试连接
            self.client.ping()
            self.connected = True
            logger.info(f"成功连接到Redis: {self.config.host}:{self.config.port}")
            return True

        except RedisError as e:
            logger.error(f"Redis连接失败: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self.client:
            try:
                self.client.close()
                self.connected = False
                logger.info("已断开Redis连接")
            except Exception as e:
                logger.error(f"断开连接失败: {e}")

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置键值对"""
        if not self.connected:
            return False

        try:
            serialized = self._serialize(value)
            if ttl:
                self.client.setex(key, ttl, serialized)
            else:
                self.client.set(key, serialized)
            return True
        except RedisError as e:
            logger.error(f"Redis set失败: {e}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        """获取值"""
        if not self.connected:
            return None

        try:
            result = self.client.get(key)
            if result:
                return self._deserialize(result)
            return None
        except RedisError as e:
            logger.error(f"Redis get失败: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """删除键"""
        if not self.connected:
            return False

        try:
            self.client.delete(key)
            return True
        except RedisError as e:
            logger.error(f"Redis delete失败: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if not self.connected:
            return False

        try:
            return self.client.exists(key) > 0
        except RedisError as e:
            logger.error(f"Redis exists失败: {e}")
            return False

    async def keys(self, pattern: str) -> List[str]:
        """获取匹配模式的键"""
        if not self.connected:
            return []

        try:
            return [k.decode('utf-8') for k in self.client.keys(pattern)]
        except RedisError as e:
            logger.error(f"Redis keys失败: {e}")
            return []

    async def hset(self, key: str, field: str, value: Any) -> bool:
        """设置哈希字段"""
        if not self.connected:
            return False

        try:
            serialized = self._serialize(value)
            self.client.hset(key, field, serialized)
            return True
        except RedisError as e:
            logger.error(f"Redis hset失败: {e}")
            return False

    async def hget(self, key: str, field: str) -> Optional[Any]:
        """获取哈希字段"""
        if not self.connected:
            return None

        try:
            result = self.client.hget(key, field)
            if result:
                return self._deserialize(result)
            return None
        except RedisError as e:
            logger.error(f"Redis hget失败: {e}")
            return None

    async def hgetall(self, key: str) -> Dict[str, Any]:
        """获取所有哈希字段"""
        if not self.connected:
            return {}

        try:
            result = self.client.hgetall(key)
            return {k.decode('utf-8'): self._deserialize(v) for k, v in result.items()}
        except RedisError as e:
            logger.error(f"Redis hgetall失败: {e}")
            return {}

    async def lpush(self, key: str, value: Any) -> bool:
        """列表左侧插入"""
        if not self.connected:
            return False

        try:
            serialized = self._serialize(value)
            self.client.lpush(key, serialized)
            return True
        except RedisError as e:
            logger.error(f"Redis lpush失败: {e}")
            return False

    async def rpop(self, key: str) -> Optional[Any]:
        """列表右侧弹出"""
        if not self.connected:
            return None

        try:
            result = self.client.rpop(key)
            if result:
                return self._deserialize(result)
            return None
        except RedisError as e:
            logger.error(f"Redis rpop失败: {e}")
            return None

    async def publish(self, channel: str, message: Any) -> bool:
        """发布消息到频道"""
        if not self.connected:
            return False

        try:
            serialized = self._serialize(message)
            self.client.publish(channel, serialized)
            return True
        except RedisError as e:
            logger.error(f"Redis publish失败: {e}")
            return False

    async def subscribe(self, channel: str) -> Any:
        """订阅频道"""
        if not self.connected:
            return None

        try:
            pubsub = self.client.pubsub()
            pubsub.subscribe(channel)
            return pubsub
        except RedisError as e:
            logger.error(f"Redis subscribe失败: {e}")
            return None

    async def acquire_lock(self, lock_key: str, timeout: int = 60) -> Optional[str]:
        """获取分布式锁"""
        if not self.connected:
            return None

        lock_value = str(uuid.uuid4())
        lock_key = f"lock:{lock_key}"

        try:
            result = self.client.set(lock_key, lock_value, ex=timeout, nx=True)
            if result:
                return lock_value
            return None
        except RedisError as e:
            logger.error(f"获取锁失败: {e}")
            return None

    async def release_lock(self, lock_key: str, lock_value: str) -> bool:
        """释放分布式锁"""
        if not self.connected:
            return False

        lock_key = f"lock:{lock_key}"

        try:
            # 使用Lua脚本保证原子性
            script = """
                if redis.call('get', KEYS[1]) == ARGV[1] then
                    return redis.call('del', KEYS[1])
                else
                    return 0
                end
            """
            result = self.client.eval(script, 1, lock_key, lock_value)
            return result == 1
        except RedisError as e:
            logger.error(f"释放锁失败: {e}")
            return False

    def _serialize(self, value: Any) -> bytes:
        """序列化值"""
        return json.dumps(value, default=self._json_default).encode('utf-8')

    def _deserialize(self, value: bytes) -> Any:
        """反序列化值"""
        return json.loads(value.decode('utf-8'))

    def _json_default(self, obj: Any) -> Any:
        """JSON序列化默认处理"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)


class TaskPersistence:
    """任务持久化管理器"""

    def __init__(self, storage: RedisStorage):
        self.storage = storage

    async def save_task(self, task_id: str, task_data: Dict[str, Any]) -> bool:
        """保存任务"""
        key = f"task:{task_id}"
        return await self.storage.hset(key, "data", task_data)

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务"""
        key = f"task:{task_id}"
        return await self.storage.hget(key, "data")

    async def update_task_status(self, task_id: str, status: str) -> bool:
        """更新任务状态"""
        key = f"task:{task_id}"
        return await self.storage.hset(key, "status", status)

    async def list_tasks(self, status: Optional[str] = None) -> List[str]:
        """列出任务"""
        keys = await self.storage.keys("task:*")

        if status is None:
            return [k.replace("task:", "") for k in keys]

        result = []
        for key in keys:
            task_status = await self.storage.hget(key, "status")
            if task_status == status:
                result.append(key.replace("task:", ""))

        return result

    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        key = f"task:{task_id}"
        return await self.storage.delete(key)


class AgentPersistence:
    """Agent持久化管理器"""

    def __init__(self, storage: RedisStorage):
        self.storage = storage

    async def save_agent(self, agent_id: str, agent_data: Dict[str, Any]) -> bool:
        """保存Agent"""
        key = f"agent:{agent_id}"
        return await self.storage.hset(key, "data", agent_data)

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取Agent"""
        key = f"agent:{agent_id}"
        return await self.storage.hget(key, "data")

    async def update_agent_state(self, agent_id: str, state: str) -> bool:
        """更新Agent状态"""
        key = f"agent:{agent_id}"
        return await self.storage.hset(key, "state", state)

    async def list_agents(self, state: Optional[str] = None) -> List[str]:
        """列出Agent"""
        keys = await self.storage.keys("agent:*")

        if state is None:
            return [k.replace("agent:", "") for k in keys]

        result = []
        for key in keys:
            agent_state = await self.storage.hget(key, "state")
            if agent_state == state:
                result.append(key.replace("agent:", ""))

        return result


class ContextCache:
    """上下文缓存管理器"""

    def __init__(self, storage: RedisStorage):
        self.storage = storage

    async def set_context(self, task_id: str, context_data: Dict[str, Any], ttl: int = 3600) -> bool:
        """设置上下文"""
        key = f"context:{task_id}"
        return await self.storage.set(key, context_data, ttl)

    async def get_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取上下文"""
        key = f"context:{task_id}"
        return await self.storage.get(key)

    async def update_context(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """更新上下文"""
        key = f"context:{task_id}"
        current = await self.storage.get(key)

        if current:
            current.update(updates)
            return await self.storage.set(key, current)

        return False

    async def delete_context(self, task_id: str) -> bool:
        """删除上下文"""
        key = f"context:{task_id}"
        return await self.storage.delete(key)


class PersistenceManager:
    """持久化管理器 - 统一入口"""

    def __init__(self, config: Optional[RedisConfig] = None):
        self.storage = RedisStorage(config)
        self.task_persistence = TaskPersistence(self.storage)
        self.agent_persistence = AgentPersistence(self.storage)
        self.context_cache = ContextCache(self.storage)

    async def start(self) -> bool:
        """启动持久化服务"""
        return await self.storage.connect()

    async def stop(self) -> None:
        """停止持久化服务"""
        await self.storage.disconnect()

    async def save_task(self, task_id: str, task_data: Dict[str, Any]) -> bool:
        """保存任务"""
        return await self.task_persistence.save_task(task_id, task_data)

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务"""
        return await self.task_persistence.get_task(task_id)

    async def save_agent(self, agent_id: str, agent_data: Dict[str, Any]) -> bool:
        """保存Agent"""
        return await self.agent_persistence.save_agent(agent_id, agent_data)

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取Agent"""
        return await self.agent_persistence.get_agent(agent_id)

    async def set_context(self, task_id: str, context: Dict[str, Any], ttl: int = 3600) -> bool:
        """设置上下文"""
        return await self.context_cache.set_context(task_id, context, ttl)

    async def get_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取上下文"""
        return await self.context_cache.get_context(task_id)

    async def publish_message(self, channel: str, message: Any) -> bool:
        """发布消息"""
        return await self.storage.publish(channel, message)

    async def acquire_lock(self, lock_key: str, timeout: int = 60) -> Optional[str]:
        """获取分布式锁"""
        return await self.storage.acquire_lock(lock_key, timeout)

    async def release_lock(self, lock_key: str, lock_value: str) -> bool:
        """释放分布式锁"""
        return await self.storage.release_lock(lock_key, lock_value)

    @property
    def connected(self) -> bool:
        """检查连接状态"""
        return self.storage.connected
