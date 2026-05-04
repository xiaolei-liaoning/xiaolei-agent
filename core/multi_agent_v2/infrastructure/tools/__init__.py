"""
ToolGateway - 工具网关

统一工具接入，负责：
1. 工具注册与管理
2. 权限控制
3. 调用限流
4. 日志记录
5. 熔断保护
6. 结果校验
"""

from core.multi_agent_v2.infrastructure.tools.tool_gateway import (
    ToolGateway,
    ToolRegistry,
    PermissionManager,
    Permission,
)

__all__ = [
    "ToolGateway",
    "ToolRegistry",
    "PermissionManager",
    "Permission",
]
