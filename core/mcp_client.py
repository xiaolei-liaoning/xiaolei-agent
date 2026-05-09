#!/usr/bin/env python3
"""
MCP 客户端管理器 - 使用原始 JSON-RPC 协议实现
"""

import asyncio
import json
import sys
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class MCPClientManager:
    """MCP 客户端管理器"""

    def __init__(self):
        self._server_configs: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        """初始化管理器"""
        logger.info("✅ MCP 客户端管理器初始化成功")
        return True

    async def connect_server(
        self,
        name: str,
        command: str,
        args: List[str],
        cwd: Optional[str] = None,
        http_url: Optional[str] = None
    ) -> bool:
        """保存服务器配置"""
        try:
            self._server_configs[name] = {
                "command": command,
                "args": args,
                "cwd": cwd,
                "http_url": http_url,
                "type": "http" if http_url else "stdio"
            }
            logger.info(f"✅ 服务器 '{name}' 配置已保存")
            return True
        except Exception as e:
            logger.error(f"❌ 保存配置失败: {e}")
            return False

    async def disconnect_server(self, name: str):
        """断开服务器连接"""
        if name in self._server_configs:
            del self._server_configs[name]
            logger.info(f"✅ 服务器 '{name}' 已断开")

    async def list_servers(self) -> List[str]:
        """列出所有已配置的服务器"""
        return list(self._server_configs.keys())

    async def _create_process(self, name: str) -> asyncio.subprocess.Process:
        """创建服务器进程"""
        if name not in self._server_configs:
            raise ValueError(f"服务器 '{name}' 未配置")

        config = self._server_configs[name]
        return await asyncio.create_subprocess_exec(
            config["command"],
            *config["args"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=config["cwd"]
        )

    async def _send_request(self, process: asyncio.subprocess.Process, method: str, params: dict = None, request_id: int = 1):
        """发送 JSON-RPC 请求"""
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method
        }
        if params:
            request["params"] = params

        request_str = json.dumps(request) + "\n"
        process.stdin.write(request_str.encode())
        await process.stdin.drain()

        response_line = await process.stdout.readline()
        if response_line:
            return json.loads(response_line.decode())
        return None

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """列出服务器提供的工具"""
        if server_name not in self._server_configs:
            raise ValueError(f"服务器 '{server_name}' 未配置")

        process = await self._create_process(server_name)
        try:
            await self._send_request(process, "initialize", {"clientInfo": {"name": "xiaolei", "version": "1.0"}}, 1)
            response = await self._send_request(process, "listTools", None, 2)
            return response.get("result", {}).get("tools", [])
        finally:
            process.terminate()
            await process.wait()

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> str:
        """调用工具"""
        if server_name not in self._server_configs:
            raise ValueError(f"服务器 '{server_name}' 未配置")

        process = await self._create_process(server_name)
        try:
            await self._send_request(process, "initialize", {"clientInfo": {"name": "xiaolei", "version": "1.0"}}, 1)
            response = await self._send_request(process, "callTool", {"name": tool_name, "arguments": arguments or {}}, 2)
            
            content = response.get("result", {}).get("content", [])
            if content:
                texts = [item.get("text", "") for item in content if isinstance(item, dict)]
                return "\n".join(texts)
            return str(response)
        finally:
            process.terminate()
            await process.wait()

    async def connect_agency_server(
        self,
        agency_path: Optional[str] = None,
        use_http: bool = False
    ) -> bool:
        """便捷方法：连接到 the-agency 服务器"""
        if agency_path is None:
            agency_path = "/Users/leiyuxuan/Desktop/逝去的白月光/the-agency"

        return await self.connect_server(
            name="the-agency",
            command="npx",
            args=["tsx", "src/integrations/claude-desktop/agency-server/index.ts"],
            cwd=agency_path,
            http_url="http://localhost:8080" if use_http else None
        )

mcp_client = MCPClientManager()
