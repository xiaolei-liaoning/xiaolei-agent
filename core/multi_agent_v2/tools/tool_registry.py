"""
统一工具注册表

整合两路工具来源，提供按任务过滤、schema 校验能力：
1. awesome_mcp_manager — 外部的 114+ 个 MCP 工具
2. mcp_client — 本地启动的 MCP 服务器
"""

import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """标准化的工具定义"""
    name: str                              # 完整名称（含 server 前缀）
    description: str                       # 功能描述
    parameters: Dict[str, Any]            # JSON Schema 参数定义
    server: str = ""                       # 来源服务器
    tool_name: str = ""                    # 去除前缀后的工具名
    tags: List[str] = field(default_factory=list)  # 功能标签


class ToolRegistry:
    """统一工具注册表

    用法:
        registry = ToolRegistry()
        await registry.discover_all()
        tools = registry.get_tools_for_task("帮我搜索一下最近的新闻")
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False

    async def discover_all(self) -> List[ToolDefinition]:
        """发现并注册所有可用工具"""
        tools = []

        # Source 1: awesome_mcp_manager
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            aw_defs = await awesome_mcp_manager.get_all_tool_definitions()
            for td in aw_defs:
                fn = td.get("function", {})
                name = fn.get("name", "")
                if name:
                    t = ToolDefinition(
                        name=name,
                        description=fn.get("description", ""),
                        parameters=fn.get("parameters", {}),
                        server=td.get("_server", ""),
                        tool_name=td.get("_tool_name", name),
                        tags=[],
                    )
                    tools.append(t)
                    self._tools[name] = t
        except Exception as e:
            logger.debug(f"awesome_mcp_manager 工具发现失败: {e}")

        # Source 2: mcp_client
        try:
            from core.mcp.mcp_client import mcp_client
            servers = await mcp_client.list_servers()
            for server in servers:
                server_tools = await mcp_client.list_tools(server)
                for tool in server_tools:
                    name = tool.get("name", "")
                    if not name:
                        continue
                    full_name = f"{server}.{name}"
                    t = ToolDefinition(
                        name=full_name,
                        description=tool.get("description", ""),
                        parameters=tool.get("inputSchema", {}) or {},
                        server=server,
                        tool_name=name,
                        tags=[],
                    )
                    tools.append(t)
                    self._tools[full_name] = t
        except Exception as e:
            logger.debug(f"mcp_client 工具发现失败: {e}")

        self._initialized = True
        logger.info(f"工具注册表初始化完成: {len(tools)} 个工具")
        return tools

    def get_tools_for_task(self, task_description: str, max_tools: int = 20) -> List[ToolDefinition]:
        """根据任务描述筛选最相关的工具

        用关键词命中 + 语义相关性排序，减少注入 LLM 的工具数量。
        至少返回 5 个工具（补齐常用工具）。
        """
        if not self._initialized:
            return list(self._tools.values())[:max_tools]

        desc = task_description.lower()
        scored: List[tuple[float, ToolDefinition]] = []

        for t in self._tools.values():
            score = 0.0
            desc_lower = t.description.lower()
            name_lower = t.name.lower()

            # 描述/名称命中（中英文关键词）
            for keyword in desc.split():
                kw = keyword.strip().lower()
                if len(kw) > 1:
                    if kw in desc_lower:
                        score += 2.0
                    if kw in name_lower:
                        score += 3.0

            # 标签匹配
            for tag in t.tags:
                if tag.lower() in desc:
                    score += 2.0

            scored.append((score, t))

        scored.sort(key=lambda x: -x[0])
        result = [t for s, t in scored if s > 0]

        # 补齐至少 5 个通用工具
        if len(result) < 5:
            existing = {t.name for t in result}
            for t in self._tools.values():
                if t.name not in existing:
                    result.append(t)
                    if len(result) >= max_tools:
                        break

        return result[:max_tools]

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """按名称获取工具定义"""
        return self._tools.get(name)

    def validate_arguments(self, tool_name: str, arguments: Dict) -> tuple[bool, str]:
        """校验工具参数是否符合 JSON Schema

        Returns:
            (True, "") 或 (False, "错误描述")
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False, f"工具 {tool_name} 未注册"

        params = tool.parameters
        if not params:
            return True, ""

        properties = params.get("properties", {})
        required = params.get("required", [])

        # 检查必需参数
        for field_name in required:
            if field_name not in arguments:
                return False, f"缺少必需参数 '{field_name}'"

        # 类型校验和自动转换
        for key, value in list(arguments.items()):
            if key in properties:
                prop_type = properties[key].get("type", "")
                if prop_type == "string" and not isinstance(value, str):
                    arguments[key] = str(value)
                elif prop_type in ("integer", "number") and isinstance(value, str):
                    try:
                        arguments[key] = int(value) if prop_type == "integer" else float(value)
                    except ValueError:
                        return False, f"参数 '{key}' 期望 {prop_type}，无法从 '{value}' 转换"

        return True, ""

    @property
    def count(self) -> int:
        return len(self._tools)


# 全局单例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表单例"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
