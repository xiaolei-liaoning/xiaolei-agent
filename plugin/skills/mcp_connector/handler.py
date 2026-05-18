import asyncio
import json
from typing import Dict, List, Any

class MCPConnectorHandler:
    def __init__(self):
        self.name = "mcp_connector"
        self.description = "MCP服务连接器 - 连接并调用外部MCP服务器"

    async def connect_server(self, server_name: str, command: str, args: List[str], cwd: str = None) -> str:
        """
        连接MCP服务器
        :param server_name: 服务器名称
        :param command: 启动命令
        :param args: 命令参数
        :param cwd: 工作目录
        :return: 连接结果
        """
        from core.mcp import mcp_client
        
        try:
            await mcp_client.connect_server(server_name, command, args, cwd)
            return f"✅ 成功连接 MCP 服务器: {server_name}"
        except Exception as e:
            return f"❌ 连接失败: {str(e)}"

    async def connect_agency(self) -> str:
        """
        便捷方法：连接 the-agency MCP 服务器
        """
        from core.mcp import mcp_client
        
        result = await mcp_client.connect_agency_server()
        if result:
            tools = await mcp_client.list_tools("the-agency")
            tool_names = [t['name'] for t in tools] if isinstance(tools, list) else []
            return f"✅ 成功连接 the-agency\n可用工具: {', '.join(tool_names)}"
        return "❌ 连接 the-agency 失败"

    async def list_servers(self) -> str:
        """
        列出已连接的MCP服务器
        """
        from core.mcp import mcp_client
        
        servers = await mcp_client.list_servers()
        if servers:
            return f"已连接的 MCP 服务器:\n" + "\n".join(f"  - {s}" for s in servers)
        return "暂无已连接的 MCP 服务器"

    async def list_tools(self, server_name: str) -> str:
        """
        获取服务器提供的工具列表
        :param server_name: 服务器名称
        """
        from core.mcp import mcp_client
        
        try:
            tools = await mcp_client.list_tools(server_name)
            if tools:
                result = f"MCP服务器 '{server_name}' 的可用工具:\n"
                for tool in tools:
                    name = tool.get('name', tool.get('name', '未知'))
                    desc = tool.get('description', '无描述')
                    result += f"  - {name}: {desc}\n"
                return result.strip()
            return f"MCP服务器 '{server_name}' 没有可用工具"
        except Exception as e:
            return f"❌ 获取工具列表失败: {str(e)}"

    async def call_tool(self, server_name: str, tool_name: str, **kwargs) -> str:
        """
        调用MCP工具
        :param server_name: 服务器名称
        :param tool_name: 工具名称
        :param kwargs: 工具参数
        """
        from core.mcp import mcp_client
        
        try:
            result = await mcp_client.call_tool(server_name, tool_name, **kwargs)
            return f"✅ 调用成功:\n{result}"
        except Exception as e:
            return f"❌ 调用失败: {str(e)}"

    async def execute(self, action: str, params: Dict[str, Any]) -> str:
        """
        执行MCP操作
        :param action: 操作类型
        :param params: 操作参数
        """
        actions = {
            'connect': self._handle_connect,
            'connect_agency': self._handle_connect_agency,
            'list_servers': self._handle_list_servers,
            'list_tools': self._handle_list_tools,
            'call': self._handle_call_tool
        }
        
        handler = actions.get(action)
        if handler:
            return await handler(params)
        return f"❌ 未知操作: {action}"

    async def _handle_connect(self, params: Dict[str, Any]) -> str:
        server_name = params.get('server_name', '')
        command = params.get('command', '')
        args = params.get('args', [])
        cwd = params.get('cwd', None)
        
        if not server_name or not command:
            return "❌ 参数不足：需要 server_name 和 command"
        
        return await self.connect_server(server_name, command, args, cwd)

    async def _handle_connect_agency(self, params: Dict[str, Any]) -> str:
        return await self.connect_agency()

    async def _handle_list_servers(self, params: Dict[str, Any]) -> str:
        return await self.list_servers()

    async def _handle_list_tools(self, params: Dict[str, Any]) -> str:
        server_name = params.get('server_name', '')
        if not server_name:
            return "❌ 需要指定 server_name"
        return await self.list_tools(server_name)

    async def _handle_call_tool(self, params: Dict[str, Any]) -> str:
        server_name = params.get('server_name', '')
        tool_name = params.get('tool_name', '')
        
        if not server_name or not tool_name:
            return "❌ 参数不足：需要 server_name 和 tool_name"
        
        tool_params = {k: v for k, v in params.items() if k not in ['server_name', 'tool_name']}
        return await self.call_tool(server_name, tool_name, **tool_params)

    def get_intents(self) -> List[Dict[str, Any]]:
        """获取技能支持的意图"""
        return [
            {
                'intent': '连接MCP服务',
                'patterns': [
                    '连接MCP服务',
                    '连接MCP服务器',
                    '开启MCP连接',
                    'connect mcp',
                    '连接 the-agency'
                ],
                'action': 'connect_agency'
            },
            {
                'intent': '查看MCP服务器列表',
                'patterns': [
                    '查看MCP服务器',
                    '列出MCP服务器',
                    '有哪些MCP服务',
                    'list mcp servers'
                ],
                'action': 'list_servers'
            },
            {
                'intent': '查看MCP工具',
                'patterns': [
                    '查看工具列表',
                    'MCP有什么工具',
                    'list mcp tools'
                ],
                'action': 'list_tools'
            },
            {
                'intent': '调用MCP工具',
                'patterns': [
                    '调用工具',
                    '执行工具',
                    'call mcp tool',
                    '获取项目健康状态',
                    '获取agent状态',
                    '创建协作请求',
                    '列出待处理协作'
                ],
                'action': 'call'
            }
        ]