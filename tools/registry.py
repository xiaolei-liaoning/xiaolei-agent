"""
工具注册表 - 管理所有可用工具

提供：
- 工具注册/注销
- 工具执行
- 工具列表
- 工具验证
"""

from typing import Dict, Callable, Any, List, Optional
import inspect
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """工具类别"""
    FILE = "file"          # 文件操作
    DATABASE = "database"  # 数据库操作
    HTTP = "http"          # HTTP请求
    WEB = "web"            # 网页操作
    DATA = "data"          # 数据处理
    SYSTEM = "system"      # 系统操作
    GENERAL = "general"    # 通用工具


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    category: ToolCategory
    handler: Callable
    description: str
    input_schema: Dict = field(default_factory=dict)
    parameters: Dict = field(default_factory=dict)


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: Dict[str, ToolInfo] = {}
        self._categories: Dict[ToolCategory, List[str]] = {
            cat: [] for cat in ToolCategory
        }

    def register(
        self,
        name: str,
        handler: Callable,
        category: ToolCategory = ToolCategory.GENERAL,
        description: str = None,
        parameters: Dict = None
    ):
        """
        注册工具

        Args:
            name: 工具名称
            handler: 处理函数
            category: 工具类别
            description: 工具描述
            parameters: 参数定义
        """
        # 获取函数签名
        sig = inspect.signature(handler)
        parameters = parameters or {}

        # 添加 schema
        input_schema = {
            "type": "object",
            "properties": {
                name: {
                    "type": "object",
                    "properties": {
                        p_name: {
                            "type": param.get("type", "string"),
                            "description": param.get("description", "")
                        }
                        for p_name, param in parameters.items()
                    }
                }
            }
        }

        # 获取函数文档作为描述
        doc = handler.__doc__
        if not description:
            if doc:
                description = doc.strip().split('\n')[0]
            else:
                description = f"工具: {name}"

        self._tools[name] = ToolInfo(
            name=name,
            category=category,
            handler=handler,
            description=description,
            input_schema=input_schema,
            parameters=parameters
        )

        self._categories[category].append(name)
        logger.info(f"工具注册成功: {name} [{category.value}]")

    def execute(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        执行工具

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            执行结果
        """
        if tool_name not in self._tools:
            raise ValueError(f"工具不存在: {tool_name}")

        tool = self._tools[tool_name]

        try:
            # 提取工具级参数
            tool_params = params.get(tool_name, {})

            # 调用处理函数
            result = tool.handler(**tool_params)
            return {
                "success": True,
                "tool": tool_name,
                "result": result,
                "message": f"工具执行成功: {tool_name}"
            }

        except Exception as e:
            logger.error(f"工具执行失败 {tool_name}: {e}")
            return {
                "success": False,
                "tool": tool_name,
                "error": str(e),
                "message": f"工具执行失败: {tool_name}"
            }

    def list_tools(self, category: ToolCategory = None) -> List[Dict[str, Any]]:
        """
        列出工具

        Args:
            category: 工具类别（可选）

        Returns:
            工具列表
        """
        tools = list(self._tools.values())

        if category:
            tools = [t for t in tools if t.category == category]

        return [
            {
                "name": tool.name,
                "category": tool.category.value,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for tool in tools
        ]

    def get_tool(self, name: str) -> Optional[ToolInfo]:
        """获取工具信息"""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name not in self._tools:
            return False

        tool = self._tools[name]
        del self._tools[name]
        self._categories[tool.category].remove(name)
        logger.info(f"工具注销成功: {name}")
        return True

    def clear(self):
        """清空所有工具"""
        self._tools.clear()
        for cat in self._categories:
            self._categories[cat].clear()
        logger.info("工具注册表已清空")


# 创建全局工具注册表实例
tool_registry = ToolRegistry()


def register_tool(
    name: str,
    category: ToolCategory = ToolCategory.GENERAL,
    description: str = None,
    parameters: Dict = None
):
    """
    工具注册装饰器

    用法:
        @register_tool("read_file", ToolCategory.FILE, "读取文件")
        def read_file(path: str) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        tool_registry.register(
            name=name,
            handler=func,
            category=category,
            description=description,
            parameters=parameters
        )
        return func
    return decorator


# 自动注册内置工具
from tools.file_ops import *
from tools.database import *
from tools.http_client import *

# 注册文件操作工具
for name, func in list(globals().items()):
    if name.startswith('read_') or name.startswith('write_') or name.startswith('list_') \
       or name.startswith('create_') or name.startswith('delete_') or name.startswith('search_') \
       or name.startswith('get_') or name.startswith('copy_') or name.startswith('move_') \
       or name.startswith('count_') or name.startswith('rename_'):
        if callable(func) and not name.startswith('_'):
            try:
                tool_registry.register(name, func, ToolCategory.FILE, func.__doc__)
            except Exception:
                pass

# 注册数据库操作工具
for name, func in list(globals().items()):
    if name.startswith('execute_') or name.startswith('create_') or name.startswith('insert_') \
       or name.startswith('update_') or name.startswith('delete_') or name.startswith('query_') \
       or name.startswith('backup_') or name.startswith('create_table_from_csv'):
        if callable(func) and not name.startswith('_'):
            try:
                tool_registry.register(name, func, ToolCategory.DATABASE, func.__doc__)
            except Exception:
                pass

# 注册 HTTP 工具
for name, func in list(globals().items()):
    if name.startswith('http_') or name.startswith('download_'):
        if callable(func) and not name.startswith('_'):
            try:
                tool_registry.register(name, func, ToolCategory.HTTP, func.__doc__)
            except Exception:
                pass


# 导出工具
__all__ = [
    'ToolRegistry',
    'tool_registry',
    'ToolCategory',
    'ToolInfo',
    'register_tool',
]
