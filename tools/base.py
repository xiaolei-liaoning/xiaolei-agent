"""
工具基础架构 - 参考Open Code的工具系统设计

提供：
- 工具定义基类
- 输入/输出Schema验证
- 工具权限控制
- 工具注册和执行
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, Optional, TypeVar, get_type_hints
from enum import Enum
import inspect
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

InputT = TypeVar('InputT')
OutputT = TypeVar('OutputT')


class ToolPermission(Enum):
    """工具权限级别"""
    READ = "read"          # 只读操作
    WRITE = "write"        # 写入操作
    EXECUTE = "execute"    # 执行操作
    ADMIN = "admin"        # 管理操作


@dataclass
class ToolInput:
    """工具输入基类"""
    pass


@dataclass
class ToolOutput:
    """工具输出基类"""
    pass


@dataclass
class ToolDefinition(Generic[InputT, OutputT]):
    """工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    permission: ToolPermission = ToolPermission.READ
    timeout: int = 30  # 默认超时30秒
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


class Tool(ABC, Generic[InputT, OutputT]):
    """工具基类 - 参考Open Code的Tool.Definition"""

    def __init__(
        self,
        name: str,
        description: str,
        permission: ToolPermission = ToolPermission.READ,
        timeout: int = 30,
        max_retries: int = 3
    ):
        self.name = name
        self.description = description
        self.permission = permission
        self.timeout = timeout
        self.max_retries = max_retries
        self._definition: Optional[ToolDefinition] = None

    @abstractmethod
    def get_input_schema(self) -> Dict[str, Any]:
        """获取输入Schema"""
        pass

    @abstractmethod
    def get_output_schema(self) -> Dict[str, Any]:
        """获取输出Schema"""
        pass

    @abstractmethod
    def execute(self, input_data: InputT) -> OutputT:
        """执行工具"""
        pass

    def validate_input(self, input_data: Any) -> InputT:
        """验证输入数据"""
        # 基础验证，子类可以重写
        return input_data

    def validate_output(self, output_data: Any) -> OutputT:
        """验证输出数据"""
        # 基础验证，子类可以重写
        return output_data

    def get_definition(self) -> ToolDefinition:
        """获取工具定义"""
        if self._definition is None:
            self._definition = ToolDefinition(
                name=self.name,
                description=self.description,
                input_schema=self.get_input_schema(),
                output_schema=self.get_output_schema(),
                permission=self.permission,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
        return self._definition


class ToolRegistry:
    """工具注册表 - 参考Open Code的ToolRegistry"""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._permissions: Dict[str, ToolPermission] = {}

    def register(self, tool: Tool) -> None:
        """注册工具"""
        if tool.name in self._tools:
            logger.warning(f"工具已存在，将被覆盖: {tool.name}")
        
        self._tools[tool.name] = tool
        self._permissions[tool.name] = tool.permission
        logger.info(f"工具注册成功: {tool.name} [{tool.permission.value}]")

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name not in self._tools:
            return False
        
        del self._tools[name]
        if name in self._permissions:
            del self._permissions[name]
        
        logger.info(f"工具注销成功: {name}")
        return True

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools

    def list_tools(self, permission: ToolPermission = None) -> list:
        """列出工具"""
        tools = list(self._tools.values())
        if permission:
            tools = [t for t in tools if t.permission == permission]
        return tools

    def get_definitions(self, permission: ToolPermission = None) -> list:
        """获取所有工具定义"""
        tools = self.list_tools(permission)
        return [tool.get_definition() for tool in tools]

    def execute(self, name: str, input_data: Any) -> Any:
        """执行工具"""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"工具不存在: {name}")
        
        # 验证输入
        validated_input = tool.validate_input(input_data)
        
        # 执行工具
        try:
            result = tool.execute(validated_input)
            # 验证输出
            validated_output = tool.validate_output(result)
            return {
                "success": True,
                "tool": name,
                "result": validated_output,
                "message": f"工具执行成功: {name}"
            }
        except Exception as e:
            logger.error(f"工具执行失败 {name}: {e}")
            return {
                "success": False,
                "tool": name,
                "error": str(e),
                "message": f"工具执行失败: {name}"
            }

    def clear(self):
        """清空所有工具"""
        self._tools.clear()
        self._permissions.clear()
        logger.info("工具注册表已清空")


# 创建全局工具注册表实例
tool_registry = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    permission: ToolPermission = ToolPermission.READ,
    timeout: int = 30,
    max_retries: int = 3
):
    """
    工具注册装饰器

    用法:
        @register_tool("read_file", "读取文件内容", ToolPermission.READ)
        def read_file(path: str) -> str:
            ...
    """
    def decorator(cls):
        # 创建工具实例
        tool_instance = cls()
        tool_instance.name = name
        tool_instance.description = description
        tool_instance.permission = permission
        tool_instance.timeout = timeout
        tool_instance.max_retries = max_retries
        
        # 注册工具
        tool_registry.register(tool_instance)
        
        return cls
    return decorator


# 导出
__all__ = [
    'ToolPermission',
    'ToolInput',
    'ToolOutput',
    'ToolDefinition',
    'Tool',
    'ToolRegistry',
    'tool_registry',
    'register_tool',
]
