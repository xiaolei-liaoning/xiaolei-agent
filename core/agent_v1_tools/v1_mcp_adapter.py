"""V1MCPAdapter — V1 MCP 适配层（封装 core/mcp/mcp_client.py）

设计：
- 不修改 core/mcp/mcp_client.py（V2 共享）
- V1 特有的重试/超时策略在此实现
- 核心 JSON-RPC 通信委托给 MCPClientManager
"""
import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class V1MCPAdapter:
    def __init__(self):
        from core.mcp.mcp_client import mcp_client
        self._client = mcp_client
        self._discovered = False

    async def discover_servers(self) -> List[str]:
        """从 mcp/ 目录 + .mcp.json 发现并注册 MCP 服务器"""
        if self._discovered:
            return await self._client.list_servers()

        proot = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
        servers = set(await self._client.list_servers())

        # 1. mcp/ 目录发现
        mcp_dir = os.path.join(proot, "mcp")
        if os.path.isdir(mcp_dir):
            for fn in sorted(os.listdir(mcp_dir)):
                if not fn.endswith("_mcp_server.py"):
                    continue
                srv = fn.replace("_mcp_server.py", "").replace("_", "-")
                if srv in servers:
                    continue
                await self._client.connect_server(
                    name=srv, command="python3",
                    args=[os.path.join(mcp_dir, fn)],
                    cwd=proot, env={"PYTHONPATH": proot},
                )
                servers.add(srv)

        # 2. .mcp.json 发现
        mcj = os.path.join(proot, ".mcp.json")
        if os.path.exists(mcj):
            try:
                with open(mcj) as f:
                    for srv, sc in json.load(f).get("mcpServers", {}).items():
                        if srv in servers:
                            continue
                        await self._client.connect_server(
                            name=srv, command=sc["command"],
                            args=sc.get("args", []),
                            cwd=proot, env={"PYTHONPATH": proot},
                        )
                        servers.add(srv)
            except Exception:
                pass

        self._discovered = True
        return list(servers)

    async def list_tools(self, server: str) -> List[Dict]:
        """从指定 MCP 服务器拉取工具列表"""
        try:
            return await asyncio.wait_for(
                self._client.list_tools(server), timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning(f"MCP {server}: list_tools 超时")
            return []
        except Exception as e:
            logger.warning(f"MCP {server}: list_tools 失败 - {e}")
            return []

    async def call_tool(self, server: str, tool: str, arguments: dict) -> str:
        """调用 MCP 工具（V1 特有：2 次重试 + 30s 超时）"""
        last_error = None
        for attempt in range(2):
            try:
                result = await asyncio.wait_for(
                    self._client.call_tool(server, tool, arguments),
                    timeout=30.0,
                )
                return result
            except asyncio.TimeoutError:
                last_error = f"超时(30s)"
                logger.warning(f"MCP 调用超时: {server}:{tool} (尝试 {attempt+1}/2)")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"MCP 调用失败: {server}:{tool} (尝试 {attempt+1}/2): {e}")
                if attempt == 0:
                    await asyncio.sleep(1)
        return f"❌ MCP {server}:{tool} 调用失败: {last_error}"

    async def get_all_tool_defs(self) -> List[Dict]:
        """返回所有 MCP 工具定义（供 V1ToolRegistry 注册）"""
        servers = await self.discover_servers()
        if not servers:
            return []
        tasks = [self.list_tools(srv) for srv in servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        tool_defs = []
        seen_names = set()
        for result, srv in zip(results, servers):
            if isinstance(result, BaseException) or not result:
                continue
            for tool in result:
                raw = tool.get("name", "")
                if not raw:
                    continue
                fn = re.sub(r"[^a-zA-Z0-9_-]", "_", raw)
                if fn in seen_names:
                    fn = f"{srv}_{raw}".replace("-", "_")
                seen_names.add(fn)
                tool_defs.append({
                    "name": fn,
                    "description": f"[{srv}] {tool.get('description', '')}",
                    "parameters": tool.get("inputSchema", {}) or {},
                    "server": srv,
                    "tool_name": raw,
                    "tags": ["mcp"],
                    "handler": None,
                })
        return tool_defs
