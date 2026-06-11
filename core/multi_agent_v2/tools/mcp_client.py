"""
MCP 客户端 — Model Context Protocol 协议实现

支持连接 MCP 服务器，发现和调用工具
对标 opencode 的 MCP 集成
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MCPConfig:
    """MCP 服务器配置"""
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    server: str = ""


@dataclass
class MCPToolResult:
    """MCP 工具调用结果"""
    content: List[Dict[str, Any]] = field(default_factory=list)
    isError: bool = False


class MCPClient:
    """MCP 客户端"""

    def __init__(self, server_configs: Optional[List[MCPConfig]] = None):
        self.server_configs = server_configs or []
        self.servers: Dict[str, subprocess.Popen] = {}
        self.tools: Dict[str, MCPTool] = {}
        self._connected = False

    async def connect(self) -> bool:
        """连接所有 MCP 服务器"""
        if self._connected:
            return True

        for config in self.server_configs:
            try:
                await self._connect_server(config)
                logger.info(f"连接 MCP 服务器成功: {config.name}")
            except Exception as e:
                logger.error(f"连接 MCP 服务器失败: {config.name} - {e}")

        self._connected = len(self.servers) > 0
        return self._connected

    async def _connect_server(self, config: MCPConfig) -> None:
        """连接单个 MCP 服务器"""
        cmd = [config.command] + config.args
        env = {**os.environ, **config.env}

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self.servers[config.name] = process
            logger.debug(f"MCP 服务器进程启动: {config.name} (PID: {process.pid})")
        except Exception as e:
            logger.error(f"启动 MCP 服务器失败: {config.name} - {e}")
            raise

    async def initialize(self) -> bool:
        """初始化 MCP 连接（发送 initialize 请求）"""
        if not self._connected:
            await self.connect()

        for name, process in self.servers.items():
            try:
                # 发送 initialize 请求
                request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "v2-agent",
                            "version": "1.0.0"
                        }
                    }
                }
                response = await self._send_request(name, request)
                if response and "result" in response:
                    logger.info(f"MCP 服务器初始化成功: {name}")
                else:
                    logger.warning(f"MCP 服务器初始化失败: {name}")
            except Exception as e:
                logger.error(f"初始化 MCP 服务器失败: {name} - {e}")

        return True

    async def discover_tools(self) -> List[MCPTool]:
        """发现所有 MCP 服务器提供的工具"""
        tools = []

        for name, process in self.servers.items():
            try:
                request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }
                response = await self._send_request(name, request)
                if response and "result" in response:
                    result = response["result"]
                    for tool_data in result.get("tools", []):
                        tool = MCPTool(
                            name=tool_data.get("name", ""),
                            description=tool_data.get("description", ""),
                            input_schema=tool_data.get("inputSchema", {}),
                            server=name,
                        )
                        tools.append(tool)
                        # 使用 server:name 作为唯一标识
                        self.tools[f"{name}:{tool.name}"] = tool
                logger.info(f"从 {name} 发现 {len(tools)} 个工具")
            except Exception as e:
                logger.error(f"发现 {name} 工具失败: {e}")

        return tools

    async def call_tool(self, server: str, tool: str, arguments: dict) -> Any:
        """
        调用 MCP 工具

        Args:
            server: 服务器名
            tool: 工具名
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if server not in self.servers:
            raise ValueError(f"MCP 服务器未连接: {server}")

        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": arguments
            }
        }

        try:
            response = await self._send_request(server, request)
            if response and "result" in response:
                result = response["result"]
                return result
            elif response and "error" in response:
                error = response["error"]
                raise RuntimeError(f"MCP 工具调用失败: {error.get('message', 'Unknown error')}")
            else:
                raise RuntimeError("MCP 工具调用无响应")
        except Exception as e:
            logger.error(f"调用 MCP 工具失败: {server}:{tool} - {e}")
            raise

    async def _send_request(self, server: str, request: dict) -> Optional[dict]:
        """发送 JSON-RPC 请求到 MCP 服务器"""
        if server not in self.servers:
            return None

        process = self.servers[server]
        try:
            # 发送请求
            request_bytes = json.dumps(request).encode() + b"\n"
            process.stdin.write(request_bytes)
            await process.stdin.drain()

            # 读取响应（简单实现，实际应该处理超时和多行响应）
            response_line = await asyncio.wait_for(
                process.stdout.readline(),
                timeout=30
            )
            if response_line:
                return json.loads(response_line.decode())
            return None
        except asyncio.TimeoutError:
            logger.warning(f"MCP 服务器 {server} 响应超时")
            return None
        except Exception as e:
            logger.error(f"与 MCP 服务器 {server} 通信失败: {e}")
            return None

    async def disconnect(self) -> None:
        """断开所有 MCP 服务器连接"""
        for name, process in self.servers.items():
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)
                logger.info(f"MCP 服务器 {name} 已断开")
            except Exception as e:
                logger.warning(f"断开 MCP 服务器 {name} 失败: {e}")
                process.kill()

        self.servers.clear()
        self.tools.clear()
        self._connected = False

    def get_tool_defs(self) -> List[Dict]:
        """获取所有 MCP 工具的定义（标准格式）"""
        defs = []
        for key, tool in self.tools.items():
            defs.append({
                "type": "function",
                "function": {
                    "name": f"mcp_{key.replace(':', '_')}",
                    "description": f"[MCP:{tool.server}] {tool.description}",
                    "parameters": tool.input_schema,
                },
                "_server": f"mcp:{tool.server}",
                "_tool_name": tool.name,
            })
        return defs

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected


# 默认配置文件路径
DEFAULT_CONFIG_PATH = ".mcp.json"


def load_mcp_config(config_path: str = DEFAULT_CONFIG_PATH) -> List[MCPConfig]:
    """
    从 JSON 文件加载 MCP 配置

    配置格式:
    {
        "mcpServers": {
            "server-name": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-xxx"],
                "env": {}
            }
        }
    }
    """
    import os

    configs = []

    # 尝试从当前目录加载
    if not os.path.isabs(config_path):
        config_path = os.path.join(os.getcwd(), config_path)

    if not os.path.exists(config_path):
        logger.debug(f"MCP 配置文件不存在: {config_path}")
        return configs

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        servers = data.get("mcpServers", {})
        for name, server_data in servers.items():
            config = MCPConfig(
                name=name,
                command=server_data.get("command", ""),
                args=server_data.get("args", []),
                env=server_data.get("env", {}),
                timeout=server_data.get("timeout", 30),
            )
            configs.append(config)
        logger.info(f"从 {config_path} 加载了 {len(configs)} 个 MCP 服务器配置")
    except Exception as e:
        logger.error(f"加载 MCP 配置失败: {e}")

    return configs


# 全局 MCP 客户端实例
_mcp_client: Optional[MCPClient] = None


def get_mcp_client(config_path: Optional[str] = None) -> MCPClient:
    """获取全局 MCP 客户端实例"""
    global _mcp_client
    if _mcp_client is None:
        configs = load_mcp_config(config_path or DEFAULT_CONFIG_PATH)
        _mcp_client = MCPClient(configs)
    return _mcp_client
