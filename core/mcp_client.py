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
        
        try:
            # 添加超时处理
            process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    config["command"],
                    *config["args"],
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=config["cwd"]
                ),
                timeout=10.0  # 10秒超时
            )
            return process
        except asyncio.TimeoutError:
            logger.error(f"创建进程超时: {name}")
            raise RuntimeError(f"创建MCP服务器进程超时")
        except Exception as e:
            logger.error(f"创建进程失败: {name}, 错误: {e}")
            raise

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
        import os
        import glob
        
        if agency_path is None:
            possible_paths = [
                "/Users/leiyuxuan/Desktop/逝去的白月光/the-agency",
                "/Users/leiyuxuan/Desktop/the-agency",
                os.path.expanduser("~/the-agency"),
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    agency_path = path
                    break
            else:
                agency_path = possible_paths[0]
        
        if not os.path.exists(agency_path):
            logger.warning(f"the-agency 目录不存在: {agency_path}")
            
            mcp_servers = glob.glob("/Users/leiyuxuan/Desktop/逝去的白月光/*/mcp/*.py")
            fun_mcp = "/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/mcp/fun_mcp_server.py"
            weather_mcp = "/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/mcp/weather_mcp_server.py"
            
            print("\n📡 可用的本地MCP服务器:")
            if os.path.exists(fun_mcp):
                print(f"  ✅ 趣味MCP服务器: {fun_mcp}")
                print(f"     使用: /mcp fun")
            if os.path.exists(weather_mcp):
                print(f"  ✅ 天气MCP服务器: {weather_mcp}")
                print(f"     使用: /mcp weather")
            if mcp_servers:
                print("\n  📂 发现的MCP相关文件:")
                for f in mcp_servers[:5]:
                    print(f"     - {f}")
            
            return False
        
        package_json = os.path.join(agency_path, "package.json")
        if not os.path.exists(package_json):
            logger.warning(f"package.json 不存在: {package_json}")
            return False

        success = await self.connect_server(
            name="the-agency",
            command="npx",
            args=["tsx", "src/integrations/claude-desktop/agency-server/index.ts"],
            cwd=agency_path,
            http_url="http://localhost:8080" if use_http else None
        )
        
        if success:
            print(f"\n✅ 成功连接到 the-agency MCP服务器")
            print(f"   路径: {agency_path}")
        else:
            print(f"\n❌ 连接 the-agency 失败")
        
        return success

    async def connect_fun_server(self) -> bool:
        """连接趣味MCP服务器"""
        import os
        
        fun_mcp_path = "/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/mcp/fun_mcp_server.py"
        
        if not os.path.exists(fun_mcp_path):
            print(f"\n❌ 趣味MCP服务器不存在: {fun_mcp_path}")
            return False
        
        success = await self.connect_server(
            name="fun-mcp",
            command="python",
            args=[fun_mcp_path],
            cwd=os.path.dirname(fun_mcp_path)
        )
        
        if success:
            print(f"\n✅ 成功连接到 趣味MCP服务器")
        else:
            print(f"\n❌ 连接 趣味MCP服务器 失败")
        
        return success

    async def connect_weather_server(self) -> bool:
        """连接天气MCP服务器"""
        import os
        
        weather_mcp_path = "/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/mcp/weather_mcp_server.py"
        
        if not os.path.exists(weather_mcp_path):
            print(f"\n❌ 天气MCP服务器不存在: {weather_mcp_path}")
            return False
        
        success = await self.connect_server(
            name="weather-mcp",
            command="python",
            args=[weather_mcp_path],
            cwd=os.path.dirname(weather_mcp_path)
        )
        
        if success:
            print(f"\n✅ 成功连接到 天气MCP服务器")
        else:
            print(f"\n❌ 连接 天气MCP服务器 失败")
        
        return success

    async def connect_calculator_server(self) -> bool:
        """连接计算器MCP服务器"""
        import os
        
        calculator_mcp_path = "/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/mcp/calculator_mcp_server.py"
        
        if not os.path.exists(calculator_mcp_path):
            print(f"\n❌ 计算器MCP服务器不存在: {calculator_mcp_path}")
            return False
        
        success = await self.connect_server(
            name="calculator-mcp",
            command="python",
            args=[calculator_mcp_path],
            cwd=os.path.dirname(calculator_mcp_path)
        )
        
        if success:
            print(f"\n✅ 成功连接到 计算器MCP服务器")
        else:
            print(f"\n❌ 连接 计算器MCP服务器 失败")
        
        return success

    async def connect_file_ops_server(self) -> bool:
        """连接文件操作MCP服务器"""
        import os
        
        file_ops_mcp_path = "/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/mcp/file_operations_mcp_server.py"
        
        if not os.path.exists(file_ops_mcp_path):
            print(f"\n❌ 文件操作MCP服务器不存在: {file_ops_mcp_path}")
            return False
        
        success = await self.connect_server(
            name="file-ops-mcp",
            command="python",
            args=[file_ops_mcp_path],
            cwd=os.path.dirname(file_ops_mcp_path)
        )
        
        if success:
            print(f"\n✅ 成功连接到 文件操作MCP服务器")
        else:
            print(f"\n❌ 连接 文件操作MCP服务器 失败")
        
        return success

    async def connect_text_processing_server(self) -> bool:
        """连接文本处理MCP服务器"""
        import os
        
        text_processing_mcp_path = "/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/mcp/text_processing_mcp_server.py"
        
        if not os.path.exists(text_processing_mcp_path):
            print(f"\n❌ 文本处理MCP服务器不存在: {text_processing_mcp_path}")
            return False
        
        success = await self.connect_server(
            name="text-processing-mcp",
            command="python",
            args=[text_processing_mcp_path],
            cwd=os.path.dirname(text_processing_mcp_path)
        )
        
        if success:
            print(f"\n✅ 成功连接到 文本处理MCP服务器")
        else:
            print(f"\n❌ 连接 文本处理MCP服务器 失败")
        
        return success

mcp_client = MCPClientManager()
