#!/usr/bin/env python3
"""
简单的 MCP 客户端实现 - 使用原始 JSON-RPC 协议
"""

import asyncio
import json
import sys
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class SimpleMCPClient:
    """简单的 MCP 客户端实现"""

    def __init__(self):
        self._server_configs: Dict[str, Dict[str, Any]] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}

    async def connect_server(
        self,
        name: str,
        command: str,
        args: List[str],
        cwd: Optional[str] = None
    ) -> bool:
        """连接到 MCP 服务器"""
        try:
            self._server_configs[name] = {
                "command": command,
                "args": args,
                "cwd": cwd
            }
            logger.info(f"✅ 服务器 '{name}' 配置已保存")
            return True
        except Exception as e:
            logger.error(f"❌ 保存配置失败: {e}")
            return False

    async def _create_process(self, name: str) -> asyncio.subprocess.Process:
        """创建服务器进程"""
        if name not in self._server_configs:
            raise ValueError(f"服务器 '{name}' 未配置")

        config = self._server_configs[name]
        process = await asyncio.create_subprocess_exec(
            config["command"],
            *config["args"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=config["cwd"]
        )
        return process

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """列出工具"""
        process = await self._create_process(server_name)
        try:
            # Initialize
            init_request = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "xiaolei", "version": "1.0"}}
            }) + "\n"
            
            process.stdin.write(init_request.encode())
            await process.stdin.drain()
            
            # 读取响应
            response = await process.stdout.readline()
            logger.debug(f"Initialize 响应: {response}")

            # List tools
            list_request = json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "listTools"
            }) + "\n"
            
            process.stdin.write(list_request.encode())
            await process.stdin.drain()
            
            response = await process.stdout.readline()
            data = json.loads(response.decode())
            
            return data.get("result", {}).get("tools", [])
            
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
        process = await self._create_process(server_name)
        try:
            # Initialize
            init_request = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "xiaolei", "version": "1.0"}}
            }) + "\n"
            
            process.stdin.write(init_request.encode())
            await process.stdin.drain()
            await process.stdout.readline()  # 忽略响应

            # Call tool
            call_request = json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "callTool",
                "params": {"name": tool_name, "arguments": arguments or {}}
            }) + "\n"
            
            process.stdin.write(call_request.encode())
            await process.stdin.drain()
            
            response = await process.stdout.readline()
            data = json.loads(response.decode())
            
            content = data.get("result", {}).get("content", [])
            if content:
                texts = [item.get("text", "") for item in content if isinstance(item, dict)]
                return "\n".join(texts)
            return str(data)
            
        finally:
            process.terminate()
            await process.wait()

mcp_client_simple = SimpleMCPClient()
