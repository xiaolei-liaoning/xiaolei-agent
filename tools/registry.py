"""
工具注册表 - 升级版

参考Open Code的ToolRegistry设计，提供：
- 工具注册/注销
- 工具执行
- 工具列表
- 工具验证
- 权限控制
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
    SHELL = "shell"        # Shell命令
    SEARCH = "search"      # 搜索工具
    TASK = "task"          # 任务管理
    INTERACTION = "interaction"  # 用户交互
    PATCH = "patch"        # 补丁操作


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    category: ToolCategory
    handler: Callable
    description: str
    input_schema: Dict = field(default_factory=dict)
    parameters: Dict = field(default_factory=dict)
    permission: str = "read"  # read, write, execute, admin
    timeout: int = 30
    max_retries: int = 3


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
        parameters: Dict = None,
        permission: str = "read",
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        注册工具

        Args:
            name: 工具名称
            handler: 处理函数
            category: 工具类别
            description: 工具描述
            parameters: 参数定义
            permission: 权限级别
            timeout: 超时时间
            max_retries: 最大重试次数
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
            parameters=parameters,
            permission=permission,
            timeout=timeout,
            max_retries=max_retries
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
            # 提取工具级参数 - 支持两种格式
            # 格式1: {'tool_name': {'param': value}}
            # 格式2: {'param': value}
            if tool_name in params:
                tool_params = params[tool_name]
            else:
                tool_params = params

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
                "parameters": tool.parameters,
                "permission": tool.permission
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
    parameters: Dict = None,
    permission: str = "read",
    timeout: int = 30,
    max_retries: int = 3
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
            parameters=parameters,
            permission=permission,
            timeout=timeout,
            max_retries=max_retries
        )
        return func
    return decorator


# 导入并注册所有工具
def register_all_tools():
    """注册所有工具"""
    import sys
    import os
    
    # 确保当前目录在路径中
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    import file_ops as file_ops
    import database as database
    import http_client as http_client
    from bash import bash_tool
    from read import read_tool
    from write import write_tool
    from edit import edit_tool
    from glob_tool import glob_tool
    from grep import grep_tool
    from todowrite import todowrite_tool
    from question import question_tool
    from skill import skill_tool
    from apply_patch import apply_patch_tool

    # 注册文件操作工具
    for name in dir(file_ops):
        func = getattr(file_ops, name)
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
    for name in dir(database):
        func = getattr(database, name)
        if name.startswith('execute_') or name.startswith('create_') or name.startswith('insert_') \
           or name.startswith('update_') or name.startswith('delete_') or name.startswith('query_') \
           or name.startswith('backup_') or name.startswith('create_table_from_csv'):
            if callable(func) and not name.startswith('_'):
                try:
                    tool_registry.register(name, func, ToolCategory.DATABASE, func.__doc__)
                except Exception:
                    pass

    # 注册 HTTP 工具
    for name in dir(http_client):
        func = getattr(http_client, name)
        if name.startswith('http_') or name.startswith('download_'):
            if callable(func) and not name.startswith('_'):
                try:
                    tool_registry.register(name, func, ToolCategory.HTTP, func.__doc__)
                except Exception:
                    pass

    # 注册新的工具
    def make_handler(tool):
        def handler(**kwargs):
            return tool.execute(tool.validate_input(kwargs))
        return handler

    tool_registry.register(
        name="bash",
        handler=make_handler(bash_tool),
        category=ToolCategory.SHELL,
        description=bash_tool.description,
        permission="execute",
        timeout=120,
        max_retries=1
    )

    tool_registry.register(
        name="read",
        handler=make_handler(read_tool),
        category=ToolCategory.FILE,
        description=read_tool.description,
        permission="read",
        timeout=30,
        max_retries=1
    )

    tool_registry.register(
        name="write",
        handler=make_handler(write_tool),
        category=ToolCategory.FILE,
        description=write_tool.description,
        permission="write",
        timeout=30,
        max_retries=1
    )

    tool_registry.register(
        name="edit",
        handler=make_handler(edit_tool),
        category=ToolCategory.FILE,
        description=edit_tool.description,
        permission="write",
        timeout=30,
        max_retries=1
    )

    tool_registry.register(
        name="glob",
        handler=make_handler(glob_tool),
        category=ToolCategory.SEARCH,
        description=glob_tool.description,
        permission="read",
        timeout=30,
        max_retries=1
    )

    tool_registry.register(
        name="grep",
        handler=make_handler(grep_tool),
        category=ToolCategory.SEARCH,
        description=grep_tool.description,
        permission="read",
        timeout=30,
        max_retries=1
    )

    tool_registry.register(
        name="todowrite",
        handler=make_handler(todowrite_tool),
        category=ToolCategory.TASK,
        description=todowrite_tool.description,
        permission="write",
        timeout=30,
        max_retries=1
    )

    tool_registry.register(
        name="question",
        handler=make_handler(question_tool),
        category=ToolCategory.INTERACTION,
        description=question_tool.description,
        permission="read",
        timeout=300,
        max_retries=1
    )

    tool_registry.register(
        name="webfetch",
        handler=make_handler(webfetch_tool),
        category=ToolCategory.WEB,
        description=webfetch_tool.description,
        permission="read",
        timeout=30,
        max_retries=1
    )

    tool_registry.register(
        name="websearch",
        handler=make_handler(websearch_tool),
        category=ToolCategory.WEB,
        description=websearch_tool.description,
        permission="read",
        timeout=30,
        max_retries=1
    )

    tool_registry.register(
        name="skill",
        handler=make_handler(skill_tool),
        category=ToolCategory.GENERAL,
        description=skill_tool.description,
        permission="read",
        timeout=30,
        max_retries=1
    )

    tool_registry.register(
        name="apply_patch",
        handler=make_handler(apply_patch_tool),
        category=ToolCategory.PATCH,
        description=apply_patch_tool.description,
        permission="write",
        timeout=60,
        max_retries=1
    )

    logger.info(f"已注册 {len(tool_registry._tools)} 个工具")


# 自动注册所有工具
register_all_tools()


# 导出工具
__all__ = [
    'ToolRegistry',
    'tool_registry',
    'ToolCategory',
    'ToolInfo',
    'register_tool',
    'register_all_tools',
]
