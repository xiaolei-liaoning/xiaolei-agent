#!/usr/bin/env python3
"""
Awesome MCP Servers Skill Handler - 连接和使用 awesome-mcp-servers 列表中的 MCP 服务器
"""

import asyncio
from typing import Dict, List, Any

class AwesomeMCPSkillHandler:
    """Awesome MCP Servers 技能处理器"""

    def __init__(self):
        self.name = "awesome_mcp_servers"
        self.description = "Awesome MCP Servers - 连接并使用 800+ MCP 服务器"
        self._manager = None

    def _get_manager(self):
        """懒加载管理器"""
        if self._manager is None:
            from core.awesome_mcp_manager import awesome_mcp_manager
            self._manager = awesome_mcp_manager
        return self._manager

    async def search_mcp_servers(self, keyword: str) -> str:
        """
        搜索 MCP 服务器
        :param keyword: 搜索关键词
        """
        manager = self._get_manager()
        servers = manager.search_servers(keyword)
        return manager.format_server_list(servers)

    async def list_popular_servers(self) -> str:
        """
        列出最受欢迎的 MCP 服务器
        """
        manager = self._get_manager()
        servers = manager.get_popular_servers()
        return manager.format_server_list(servers)

    async def get_server_categories(self) -> str:
        """
        获取所有服务器分类
        """
        manager = self._get_manager()
        servers = manager.parse_readme()

        categories = {}
        for server in servers:
            cat = server["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(server["name"])

        result = f"📂 MCP 服务器分类 (共 {len(categories)} 个分类)\n\n"
        for cat, names in sorted(categories.items()):
            result += f"### {cat}\n"
            result += f"   共 {len(names)} 个服务器\n\n"

        return result

    async def get_server_by_category(self, category: str) -> str:
        """
        获取指定分类的服务器
        :param category: 分类名称
        """
        manager = self._get_manager()
        servers = manager.get_by_category(category)
        if not servers:
            return f"❌ 未找到分类: {category}"
        return manager.format_server_list(servers)

    async def quick_connect(self, server_name: str) -> str:
        """
        快速连接热门 MCP 服务器
        :param server_name: 服务器名称（支持: chroma, playwright, e2b, sqlite, postgres, filesystem, github, slack）
        """
        manager = self._get_manager()
        result = await manager.quick_connect(server_name)
        return result["message"]

    async def connect_server(self, server_url: str, server_name: str = None) -> str:
        """
        连接指定 URL 的 MCP 服务器
        :param server_url: 服务器 GitHub URL
        :param server_name: 服务器名称（可选）
        """
        manager = self._get_manager()
        name = server_name or server_url.split("/")[-1].replace(".git", "")
        success = await manager.connect_server_by_url(name, server_url)

        if success:
            return f"✅ 成功连接 {name}\n命令: {server_url}"
        else:
            return f"❌ 连接失败: {name}"

    async def list_connected_servers(self) -> str:
        """
        列出已连接的服务器
        """
        manager = self._get_manager()
        servers = manager.get_connected_servers()

        if not servers:
            return "📭 暂无已连接的 MCP 服务器\n\n可用快速连接: chroma, playwright, e2b, sqlite, postgres, filesystem, github, slack"

        result = f"🔗 已连接的 MCP 服务器 ({len(servers)} 个)\n\n"
        for server in servers:
            result += f"  ✅ {server}\n"
        return result

    async def get_server_info(self, server_name: str) -> str:
        """
        获取服务器详细信息
        :param server_name: 服务器名称
        """
        manager = self._get_manager()
        info = manager.get_server_info(server_name)

        if not info:
            return f"❌ 未找到服务器: {server_name}"

        result = f"📦 MCP 服务器详情: {info['name']}\n\n"
        result += f"  分类: {info['category']}\n"
        result += f"  描述: {info['description']}\n"
        result += f"  URL: {info['url']}\n"
        result += f"  标签: {' '.join(info['badges']) if info['badges'] else '无'}\n"
        result += f"  云服务: {'是' if info['is_cloud'] else '否'}\n"
        result += f"  本地服务: {'是' if info['is_local'] else '否'}\n"
        result += f"  官方支持: {'是' if info['is_official'] else '否'}\n"

        return result

    async def execute(self, action: str, params: Dict[str, Any]) -> str:
        """
        执行 MCP 操作
        :param action: 操作类型
        :param params: 操作参数
        """
        actions = {
            'search': self._handle_search,
            'list_popular': self._handle_list_popular,
            'categories': self._handle_categories,
            'by_category': self._handle_by_category,
            'quick_connect': self._handle_quick_connect,
            'connect': self._handle_connect,
            'list_connected': self._handle_list_connected,
            'info': self._handle_info
        }

        handler = actions.get(action)
        if not handler:
            return f"❌ 未知操作: {action}\n可用操作: {', '.join(actions.keys())}"

        return await handler(params)

    async def _handle_search(self, params: Dict[str, Any]) -> str:
        keyword = params.get('keyword', '')
        if not keyword:
            return "❌ 需要提供搜索关键词"
        return await self.search_mcp_servers(keyword)

    async def _handle_list_popular(self, params: Dict[str, Any]) -> str:
        return await self.list_popular_servers()

    async def _handle_categories(self, params: Dict[str, Any]) -> str:
        return await self.get_server_categories()

    async def _handle_by_category(self, params: Dict[str, Any]) -> str:
        category = params.get('category', '')
        if not category:
            return "❌ 需要提供分类名称"
        return await self.get_server_by_category(category)

    async def _handle_quick_connect(self, params: Dict[str, Any]) -> str:
        server_name = params.get('server_name', '')
        if not server_name:
            return "❌ 需要提供服务器名称"
        return await self.quick_connect(server_name)

    async def _handle_connect(self, params: Dict[str, Any]) -> str:
        server_url = params.get('server_url', '')
        if not server_url:
            return "❌ 需要提供服务器 URL"
        server_name = params.get('server_name')
        return await self.connect_server(server_url, server_name)

    async def _handle_list_connected(self, params: Dict[str, Any]) -> str:
        return await self.list_connected_servers()

    async def _handle_info(self, params: Dict[str, Any]) -> str:
        server_name = params.get('server_name', '')
        if not server_name:
            return "❌ 需要提供服务器名称"
        return await self.get_server_info(server_name)

    def get_intents(self) -> List[Dict[str, Any]]:
        """获取技能支持的意图"""
        return [
            {
                'intent': '搜索MCP服务器',
                'patterns': [
                    '搜索MCP服务器',
                    '查找MCP',
                    'search mcp servers',
                    'mcp服务器有哪些',
                    '找一下chroma'
                ],
                'action': 'search'
            },
            {
                'intent': '查看热门服务器',
                'patterns': [
                    '热门MCP服务器',
                    '最常用的MCP',
                    'popular mcp servers',
                    '推荐MCP'
                ],
                'action': 'list_popular'
            },
            {
                'intent': '查看服务器分类',
                'patterns': [
                    'MCP分类',
                    '服务器分类',
                    'mcp categories',
                    '有哪些分类'
                ],
                'action': 'categories'
            },
            {
                'intent': '按分类查看服务器',
                'patterns': [
                    '数据库MCP',
                    '浏览器MCP',
                    '查看数据库类MCP',
                    'Databases MCP'
                ],
                'action': 'by_category'
            },
            {
                'intent': '快速连接服务器',
                'patterns': [
                    '连接chroma',
                    '连接playwright',
                    '快速连接',
                    'quick connect',
                    'connect e2b'
                ],
                'action': 'quick_connect'
            },
            {
                'intent': '查看已连接服务器',
                'patterns': [
                    '已连接服务器',
                    '连接的MCP',
                    'list connected',
                    '查看连接'
                ],
                'action': 'list_connected'
            },
            {
                'intent': '获取服务器信息',
                'patterns': [
                    '服务器详情',
                    'MCP信息',
                    'server info',
                    'chroma是什么'
                ],
                'action': 'info'
            }
        ]
