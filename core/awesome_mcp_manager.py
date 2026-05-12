#!/usr/bin/env python3
"""
Awesome MCP Servers 管理器 - 从 awesome-mcp-servers 列表中管理和连接 MCP 服务器
支持真正启动 MCP 服务器并调用其工具
"""

import asyncio
import json
import re
import subprocess
import os
import tempfile
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
import logging
import threading

logger = logging.getLogger(__name__)

class MCPProcess:
    """MCP 服务器进程封装"""

    def __init__(self, name: str, command: str, args: List[str], env: Dict[str, str] = None):
        self.name = name
        self.command = command
        self.args = args
        self.env = env or os.environ.copy()
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self._lock = threading.Lock()

    def start(self) -> bool:
        """启动 MCP 服务器进程"""
        try:
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.env,
                text=True,
                bufsize=1
            )
            logger.info(f"✅ MCP 服务器已启动: {self.name} (PID: {self.process.pid})")

            # 发送初始化请求
            init_result = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "xiaolei-agent",
                    "version": "1.0.0"
                }
            })
            return init_result is not None
        except Exception as e:
            logger.error(f"❌ 启动 MCP 服务器失败 {self.name}: {e}")
            return False

    def _send_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发送 JSON-RPC 请求"""
        if not self.process or self.process.stdin is None:
            return None

        with self._lock:
            self.request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": method,
                "params": params
            }

            try:
                self.process.stdin.write(json.dumps(request) + "\n")
                self.process.stdin.flush()

                # 读取响应
                response_line = self.process.stdout.readline()
                if response_line:
                    return json.loads(response_line)
            except Exception as e:
                logger.error(f"发送请求失败: {e}")

        return None

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用 MCP 服务器工具"""
        return self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

    def list_tools(self) -> Optional[List[Dict[str, Any]]]:
        """列出可用工具"""
        result = self._send_request("tools/list", {})
        if result and "result" in result:
            return result["result"].get("tools", [])
        return None

    def stop(self):
        """停止 MCP 服务器进程"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            logger.info(f"🛑 MCP 服务器已停止: {self.name}")


class AwesomeMCPManager:
    """Awesome MCP Servers 管理器"""

    def __init__(self):
        self.base_path = Path(__file__).parent / "awesome-mcp-servers"
        self.readme_path = self.base_path / "README.md"
        self._servers_cache: Optional[List[Dict[str, Any]]] = None
        self._connected_servers: Dict[str, MCPProcess] = {}

    def parse_readme(self) -> List[Dict[str, Any]]:
        """解析 README.md 中的 MCP 服务器列表"""
        if self._servers_cache:
            return self._servers_cache

        servers = []
        if not self.readme_path.exists():
            logger.error(f"README.md not found: {self.readme_path}")
            return servers

        with open(self.readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        current_category = "Other"

        for line in lines:
            line = line.strip()

            if line.startswith("### ") and "</a>" in line:
                category_match = re.search(r'### .*</a>\s*([^\n]+)', line)
                if category_match:
                    current_category = category_match.group(1).strip()

            if line.startswith("- ["):
                server_info = self._parse_server_line(line, current_category)
                if server_info:
                    servers.append(server_info)

        self._servers_cache = servers
        logger.info(f"✅ 解析完成，共发现 {len(servers)} 个 MCP 服务器")
        return servers

    def _parse_server_line(self, line: str, category: str) -> Optional[Dict[str, Any]]:
        """解析单行服务器信息"""
        link_match = re.search(r'\[([^\]]+)\]\((https?://[^\)]+)\)', line)
        if not link_match:
            return None

        name = link_match.group(1)
        url = link_match.group(2)

        badges = re.findall(r'([📇🐍🏎️🦀#️⃣☕🌊💎🎖️])', line)
        badges = [b for b in badges if b] if badges else []

        is_cloud = "☁️" in line
        is_local = "🏠" in line
        is_official = "🎖️" in line

        description = line.split(")")[-1].strip() if ")" in line else ""

        return {
            "name": name,
            "url": url,
            "category": category,
            "badges": badges,
            "is_cloud": is_cloud,
            "is_local": is_local,
            "is_official": is_official,
            "description": description,
            "connected": False
        }

    def search_servers(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索 MCP 服务器"""
        servers = self.parse_readme()
        keyword_lower = keyword.lower()

        results = []
        for server in servers:
            if (keyword_lower in server["name"].lower() or
                keyword_lower in server["description"].lower() or
                keyword_lower in server["category"].lower()):
                results.append(server)

        return results

    def get_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按分类获取服务器"""
        servers = self.parse_readme()
        return [s for s in servers if s["category"] == category]

    def get_popular_servers(self) -> List[Dict[str, Any]]:
        """获取最受欢迎的服务器"""
        popular_categories = [
            "Databases",
            "Browser Automation",
            "Code Execution",
            "Coding Agents",
            "Knowledge & Memory"
        ]
        servers = self.parse_readme()
        return [s for s in servers if s["category"] in popular_categories][:20]

    async def quick_connect(self, server_name: str) -> Dict[str, Any]:
        """快速连接并启动 MCP 服务器"""
        quick_connect_map = {
            "chroma": {
                "package": "chroma-mcp",
                "command": "npx",
                "args": ["-y", "chroma-mcp"]
            },
            "playwright": {
                "package": "@anthropic/playwright-mcp",
                "command": "npx",
                "args": ["-y", "@anthropic/playwright-mcp"]
            },
            "e2b": {
                "package": "e2b-sandbox-mcp",
                "command": "npx",
                "args": ["-y", "e2b-sandbox-mcp"]
            },
            "sqlite": {
                "package": "@modelcontextprotocol/server-sqlite",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sqlite"]
            },
            "postgres": {
                "package": "@modelcontextprotocol/server-postgres",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-postgres"]
            },
            "filesystem": {
                "package": "@modelcontextprotocol/server-filesystem",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
            },
            "github": {
                "package": "@modelcontextprotocol/server-github",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"]
            },
            "slack": {
                "package": "@modelcontextprotocol/server-slack",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-slack"]
            },
            "brave-search": {
                "package": "@modelcontextprotocol/server-brave-search",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"]
            },
            "sentry": {
                "package": "@modelcontextprotocol/server-sentry",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sentry"]
            }
        }

        server_key = server_name.lower().strip()
        if server_key not in quick_connect_map:
            return {
                "success": False,
                "message": f"未知的快速连接服务器: {server_name}\n可用服务器: {', '.join(quick_connect_map.keys())}"
            }

        config = quick_connect_map[server_key]

        # 如果已连接，先停止
        if server_key in self._connected_servers:
            self._connected_servers[server_key].stop()
            del self._connected_servers[server_key]

        # 创建并启动进程
        process = MCPProcess(
            name=server_key,
            command=config["command"],
            args=config["args"]
        )

        success = process.start()
        if success:
            self._connected_servers[server_key] = process
            return {
                "success": True,
                "message": f"✅ 成功启动 {server_key}\n命令: {config['command']} {' '.join(config['args'])}",
                "tools": self._get_server_tools(server_key)
            }
        else:
            return {
                "success": False,
                "message": f"❌ 启动 {server_key} 失败"
            }

    def _get_server_tools(self, server_name: str) -> Optional[List[str]]:
        """获取服务器提供的工具列表"""
        if server_name not in self._connected_servers:
            return None
        tools = self._connected_servers[server_name].list_tools()
        if tools:
            return [t.get("name", "unknown") for t in tools]
        return None

    def call_server_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用 MCP 服务器的工具"""
        if server_name not in self._connected_servers:
            logger.error(f"MCP 服务器未连接: {server_name}")
            return None

        return self._connected_servers[server_name].call_tool(tool_name, arguments)

    def get_connected_servers(self) -> List[str]:
        """获取已连接的服务器列表"""
        return list(self._connected_servers.keys())

    def get_server_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取服务器详细信息"""
        servers = self.parse_readme()
        for server in servers:
            if server["name"] == name:
                return server
        return None

    def get_server_tools(self, server_name: str) -> Optional[List[Dict[str, Any]]]:
        """获取服务器的工具列表详情"""
        if server_name not in self._connected_servers:
            return None
        return self._connected_servers[server_name].list_tools()

    def disconnect_server(self, server_name: str) -> bool:
        """断开 MCP 服务器连接"""
        if server_name in self._connected_servers:
            self._connected_servers[server_name].stop()
            del self._connected_servers[server_name]
            return True
        return False

    def format_server_list(self, servers: List[Dict[str, Any]]) -> str:
        """格式化服务器列表为可读字符串"""
        if not servers:
            return "没有找到匹配的服务器"

        result = f"📦 找到 {len(servers)} 个 MCP 服务器:\n\n"

        current_category = ""
        for server in servers:
            if server["category"] != current_category:
                current_category = server["category"]
                result += f"\n### {current_category}\n"

            badges = " ".join(server["badges"]) if server["badges"] else ""
            result += f"- **{server['name']}** {badges}\n"
            result += f"  {server['description']}\n"
            result += f"  🔗 {server['url']}\n\n"

        return result

    def format_connected_servers(self) -> str:
        """格式化已连接服务器信息"""
        if not self._connected_servers:
            return "📭 暂无已连接的 MCP 服务器\n\n可用快速连接: " + ", ".join(self.get_available_quick_connect())

        result = f"🔗 已连接的 MCP 服务器 ({len(self._connected_servers)} 个)\n\n"

        for name, process in self._connected_servers.items():
            tools = self._get_server_tools(name)
            result += f"### {name}\n"
            result += f"  状态: ✅ 运行中 (PID: {process.process.pid})\n"
            if tools:
                result += f"  工具: {', '.join(tools[:5])}"
                if len(tools) > 5:
                    result += f" ... (+{len(tools)-5} 个)"
                result += "\n"
            result += "\n"

        return result

    def get_available_quick_connect(self) -> List[str]:
        """获取可用的快速连接服务器"""
        return [
            "chroma", "playwright", "e2b", "sqlite", "postgres",
            "filesystem", "github", "slack", "brave-search", "sentry"
        ]

awesome_mcp_manager = AwesomeMCPManager()
