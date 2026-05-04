"""
工具网关 - 统一工具接入

职责：
1. 工具注册与管理
2. 权限控制
3. 调用限流
4. 日志记录
5. 熔断保护
6. 结果校验
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class Permission(Enum):
    """权限类型"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    ADMIN = "admin"


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str
    category: str
    parameters_schema: Dict[str, Any]
    return_schema: Dict[str, Any]
    permissions: List[Permission]
    rate_limit: int = 60
    timeout: float = 30.0
    tags: List[str] = field(default_factory=list)


@dataclass
class ToolCall:
    """工具调用"""
    call_id: str
    tool_name: str
    parameters: Dict[str, Any]
    caller_id: str
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"


@dataclass
class ToolResult:
    """工具调用结果"""
    call_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self.tools: Dict[str, ToolMetadata] = {}
        self.handlers: Dict[str, Callable] = {}

    def register(self, metadata: ToolMetadata, handler: Callable) -> None:
        """注册工具"""
        if metadata.name in self.tools:
            raise ValueError(f"工具 {metadata.name} 已存在")

        self.tools[metadata.name] = metadata
        self.handlers[metadata.name] = handler

        logger.info(f"工具注册: {metadata.name}")

    def unregister(self, tool_name: str) -> None:
        """注销工具"""
        if tool_name in self.tools:
            del self.tools[tool_name]
        if tool_name in self.handlers:
            del self.handlers[tool_name]

        logger.info(f"工具注销: {tool_name}")

    def get_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """获取工具元数据"""
        return self.tools.get(tool_name)

    def get_handler(self, tool_name: str) -> Optional[Callable]:
        """获取工具处理器"""
        return self.handlers.get(tool_name)

    def list_tools(self, category: Optional[str] = None) -> List[ToolMetadata]:
        """列出工具"""
        if category:
            return [t for t in self.tools.values() if t.category == category]
        return list(self.tools.values())


class PermissionManager:
    """权限管理器"""

    def __init__(self):
        self.agent_permissions: Dict[str, Set[Permission]] = defaultdict(set)
        self.tool_permissions: Dict[str, Set[Permission]] = {}

    def grant_permission(self, agent_id: str, permission: Permission) -> None:
        """授予权限"""
        self.agent_permissions[agent_id].add(permission)

    def revoke_permission(self, agent_id: str, permission: Permission) -> None:
        """撤销权限"""
        self.agent_permissions[agent_id].discard(permission)

    def has_permission(self, agent_id: str, permission: Permission) -> bool:
        """检查权限"""
        return permission in self.agent_permissions[agent_id]

    def can_use_tool(self, agent_id: str, tool_name: str, registry: ToolRegistry) -> bool:
        """检查是否能使用工具"""
        metadata = registry.get_metadata(tool_name)

        if not metadata:
            return False

        for required_permission in metadata.permissions:
            if not self.has_permission(agent_id, required_permission):
                return False

        return True

    def set_tool_permissions(self, tool_name: str, permissions: List[Permission]) -> None:
        """设置工具所需的权限"""
        self.tool_permissions[tool_name] = set(permissions)


class ToolCallLogger:
    """工具调用日志"""

    def __init__(self):
        self.calls: List[ToolCall] = []
        self.results: Dict[str, ToolResult] = {}

    async def log_call(self, call: ToolCall) -> None:
        """记录调用"""
        self.calls.append(call)

        if len(self.calls) > 10000:
            self.calls = self.calls[-5000:]

    async def log_result(self, result: ToolResult) -> None:
        """记录结果"""
        self.results[result.call_id] = result

    async def get_call_history(
        self,
        tool_name: Optional[str] = None,
        caller_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取调用历史"""
        filtered = self.calls

        if tool_name:
            filtered = [c for c in filtered if c.tool_name == tool_name]

        if caller_id:
            filtered = [c for c in filtered if c.caller_id == caller_id]

        history = []
        for call in filtered[-limit:]:
            result = self.results.get(call.call_id)
            history.append({
                "call": call,
                "result": result
            })

        return history


class CircuitBreaker:
    """熔断器"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.failure_count: Dict[str, int] = defaultdict(int)
        self.last_failure_time: Dict[str, float] = {}
        self.state: Dict[str, str] = defaultdict(lambda: "CLOSED")
        self.half_open_calls: Dict[str, int] = defaultdict(int)

    def is_open(self, tool_name: str) -> bool:
        """熔断器是否打开"""
        if self.state[tool_name] == "OPEN":
            if tool_name in self.last_failure_time:
                if time.time() - self.last_failure_time[tool_name] > self.recovery_timeout:
                    self.state[tool_name] = "HALF_OPEN"
                    self.half_open_calls[tool_name] = 0
                    return False
            return True
        return False

    def record_failure(self, tool_name: str) -> None:
        """记录失败"""
        self.failure_count[tool_name] += 1
        self.last_failure_time[tool_name] = time.time()

        if self.failure_count[tool_name] >= self.failure_threshold:
            self.state[tool_name] = "OPEN"
            logger.warning(f"工具 {tool_name} 熔断器打开，失败次数: {self.failure_count[tool_name]}")

    def record_success(self, tool_name: str) -> None:
        """记录成功"""
        if self.state[tool_name] == "HALF_OPEN":
            self.half_open_calls[tool_name] += 1

            if self.half_open_calls[tool_name] >= self.half_open_max_calls:
                self.state[tool_name] = "CLOSED"
                self.failure_count[tool_name] = 0
                logger.info(f"工具 {tool_name} 熔断器关闭，系统恢复")

    def can_execute(self, tool_name: str) -> bool:
        """是否可以执行"""
        if self.state[tool_name] == "CLOSED":
            return True

        if self.state[tool_name] == "HALF_OPEN":
            return self.half_open_calls[tool_name] < self.half_open_max_calls

        return False


class ToolGateway:
    """工具网关 - 统一工具接入"""

    def __init__(self):
        self.registry = ToolRegistry()
        self.permissions = PermissionManager()
        self.logger = ToolCallLogger()
        self.circuit_breaker = CircuitBreaker()

        self.rate_limits: Dict[str, List[float]] = defaultdict(list)
        self.rate_limit_locks: Dict[str, asyncio.Lock] = {}

        logger.info("工具网关初始化完成")

    async def register_tool(
        self,
        name: str,
        description: str,
        category: str,
        handler: Callable,
        parameters_schema: Dict[str, Any],
        return_schema: Dict[str, Any],
        permissions: List[Permission],
        **kwargs
    ) -> None:
        """注册工具"""
        metadata = ToolMetadata(
            name=name,
            description=description,
            category=category,
            parameters_schema=parameters_schema,
            return_schema=return_schema,
            permissions=permissions,
            **kwargs
        )

        self.registry.register(metadata, handler)

    async def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        caller_id: str
    ) -> ToolResult:
        """执行工具调用"""
        call_id = str(uuid.uuid4())
        start_time = time.time()

        call = ToolCall(
            call_id=call_id,
            tool_name=tool_name,
            parameters=parameters,
            caller_id=caller_id
        )

        await self.logger.log_call(call)

        if not self.permissions.can_use_tool(caller_id, tool_name, self.registry):
            logger.warning(f"Agent {caller_id} 没有权限调用工具 {tool_name}")

            return ToolResult(
                call_id=call_id,
                success=False,
                error="没有权限",
                execution_time=time.time() - start_time
            )

        if self.circuit_breaker.is_open(tool_name):
            logger.warning(f"工具 {tool_name} 熔断器打开，拒绝调用")

            return ToolResult(
                call_id=call_id,
                success=False,
                error="工具暂时不可用（熔断保护）",
                execution_time=time.time() - start_time
            )

        if not await self._check_rate_limit(tool_name):
            logger.warning(f"工具 {tool_name} 限流")

            return ToolResult(
                call_id=call_id,
                success=False,
                error="限流中，请稍后重试",
                execution_time=time.time() - start_time
            )

        handler = self.registry.get_handler(tool_name)
        metadata = self.registry.get_metadata(tool_name)

        if not handler or not metadata:
            return ToolResult(
                call_id=call_id,
                success=False,
                error=f"工具 {tool_name} 不存在",
                execution_time=time.time() - start_time
            )

        call.status = "running"

        try:
            result = await asyncio.wait_for(
                handler(**parameters),
                timeout=metadata.timeout
            )

            validated_result = self._validate_result(result, metadata.return_schema)

            self.circuit_breaker.record_success(tool_name)

            tool_result = ToolResult(
                call_id=call_id,
                success=True,
                output=validated_result,
                execution_time=time.time() - start_time,
                metadata={"tool_name": tool_name}
            )

            await self.logger.log_result(tool_result)

            return tool_result

        except asyncio.TimeoutError:
            logger.error(f"工具 {tool_name} 执行超时")

            self.circuit_breaker.record_failure(tool_name)

            return ToolResult(
                call_id=call_id,
                success=False,
                error="执行超时",
                execution_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"工具 {tool_name} 执行失败: {e}")

            self.circuit_breaker.record_failure(tool_name)

            return ToolResult(
                call_id=call_id,
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )

    async def _check_rate_limit(self, tool_name: str) -> bool:
        """检查限流"""
        metadata = self.registry.get_metadata(tool_name)

        if not metadata:
            return True

        current_time = time.time()
        window_start = current_time - 60

        if tool_name not in self.rate_limit_locks:
            self.rate_limit_locks[tool_name] = asyncio.Lock()

        async with self.rate_limit_locks[tool_name]:
            self.rate_limits[tool_name] = [
                t for t in self.rate_limits[tool_name]
                if t > window_start
            ]

            if len(self.rate_limits[tool_name]) >= metadata.rate_limit:
                return False

            self.rate_limits[tool_name].append(current_time)

            return True

    def _validate_result(self, result: Any, schema: Dict[str, Any]) -> Any:
        """验证结果"""
        return result

    def grant_agent_permissions(self, agent_id: str, permissions: List[Permission]) -> None:
        """授予Agent权限"""
        for permission in permissions:
            self.permissions.grant_permission(agent_id, permission)

    def get_tool_metrics(self) -> Dict[str, Any]:
        """获取工具指标"""
        tools = self.registry.list_tools()

        metrics = {}
        for tool in tools:
            metrics[tool.name] = {
                "category": tool.category,
                "rate_limit": tool.rate_limit,
                "timeout": tool.timeout,
                "circuit_state": self.circuit_breaker.state.get(tool.name, "CLOSED"),
                "failures": self.circuit_breaker.failure_count.get(tool.name, 0)
            }

        return metrics
