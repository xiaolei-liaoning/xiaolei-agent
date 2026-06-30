#!/usr/bin/env python3
"""
DEPRECATED: 此模块已弃用，请使用 awesome_mcp_manager 替代 (2026-06-17)
"""

import warnings
warnings.warn("mcp_client.py 已弃用，请使用 core.mcp.awesome_mcp_manager", DeprecationWarning, stacklevel=2)

import asyncio
import json
import os
import glob
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
import httpx

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 0.5  # 秒


@dataclass
class _Connection:
    """持久的 MCP 连接"""
    process: Optional[asyncio.subprocess.Process] = None
    server_name: str = ""
    initialized: bool = False
    last_used: float = 0.0
    connection_type: str = "stdio"


class _HttpConnection:
    """HTTP 类型的 MCP 连接"""
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.headers = headers or {}
        self.client: Optional[httpx.AsyncClient] = None
        self.initialized = False
        self.last_used: float = 0.0
    
    async def initialize(self) -> bool:
        """初始化 HTTP 连接"""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.url,
                headers=self.headers,
                timeout=30.0
            )
            self.initialized = True
            logger.info(f"HTTP MCP 连接已建立: {self.url}")
            return True
        except Exception as e:
            logger.error(f"HTTP MCP 连接初始化失败: {e}")
            return False
    
    async def send_request(self, method: str, params: Optional[dict] = None) -> Optional[dict]:
        """发送 JSON-RPC 请求到 HTTP 端点"""
        if not self.client:
            return None
        
        request_id = id(self) % 10000
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            request["params"] = params
        
        try:
            response = await self.client.post(
                "/mcp",
                json=request,
                timeout=30.0
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"HTTP 请求失败: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"HTTP 请求异常: {e}")
            return None
    
    async def close(self):
        """关闭 HTTP 连接"""
        if self.client:
            await self.client.aclose()
            self.client = None
            self.initialized = False


class MCPClientManager:
    """MCP 客户端管理器（连接池版）"""

    def __init__(self):
        self._server_configs: Dict[str, Dict[str, Any]] = {}
        self._connections: Dict[str, _Connection] = {}
        self._http_connections: Dict[str, _HttpConnection] = {}
        self._server_locks: Dict[str, asyncio.Lock] = {}
        self._request_counter: Dict[str, int] = {}

    def _get_request_id(self, server_name: str) -> int:
        counter = self._request_counter.get(server_name, 0) + 1
        self._request_counter[server_name] = counter
        return counter

    def _get_server_lock(self, name: str) -> asyncio.Lock:
        """获取/创建每台服务器的独立锁，避免不同 MCP 服务器串行排队"""
        if name not in self._server_locks:
            self._server_locks[name] = asyncio.Lock()
        return self._server_locks[name]

    async def initialize(self):
        """初始化管理器"""
        logger.info("✅ MCP 客户端管理器 v2 初始化成功")
        return True

    async def auto_connect_local_servers(self):
        """动态扫描 mcp/ 目录，自动连接所有 *_mcp_server.py 文件"""
        mcp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "mcp")
        if not os.path.exists(mcp_dir):
            logger.warning(f"MCP 服务器目录不存在: {mcp_dir}")
            return

        for fn in sorted(os.listdir(mcp_dir)):
            if not fn.endswith("_mcp_server.py"):
                continue
            server_name = fn.replace("_mcp_server.py", "").replace("_", "-")
            script_path = os.path.join(mcp_dir, fn)
            if not os.path.exists(script_path):
                continue

            try:
                await self.connect_server(
                    name=server_name,
                    command="python3",
                    args=[script_path],
                    env={"PYTHONPATH": os.path.dirname(mcp_dir)},
                )
                logger.info(f"  ✅ {server_name} 服务器就绪")
            except Exception as e:
                logger.warning(f"  ⚠️ {server_name} 服务器启动失败: {e}")

    # ── 连接管理 ──────────────────────────────────────────────────────────────

    async def connect_server(
        self,
        name: str,
        command: str,
        args: List[str],
        cwd: Optional[str] = None,
        http_url: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> bool:
        """配置 MCP 服务器（进程按需启动）"""
        self._server_configs[name] = {
            "command": command,
            "args": args,
            "cwd": cwd,
            "http_url": http_url,
            "env": env or None,
            "type": "http" if http_url else "stdio",
        }

        logger.info(f"✅ 服务器 '{name}' 配置已保存（进程按需启动）")
        return True

    async def disconnect_server(self, name: str):
        """断开服务器连接（清理进程 + 移除配置）"""
        await self._cleanup_connection(name)
        self._server_configs.pop(name, None)
        logger.info(f"✅ 服务器 '{name}' 已断开")

    async def list_servers(self) -> List[str]:
        """列出所有已配置的服务器"""
        return list(self._server_configs.keys())

    # ── 工具操作（复用连接池） ────────────────────────────────────────────────

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """列出服务器提供的工具"""
        config = self._server_configs.get(server_name)
        if not config:
            logger.warning(f"服务器 '{server_name}' 未配置")
            return []
        
        if config.get("type") == "http":
            http_conn = await self._get_or_connect_http(server_name)
            if not http_conn:
                return []
            resp = await self._send_http_request_with_retry(
                http_conn, "tools/list", None
            )
            if resp and "result" in resp:
                return resp["result"].get("tools", [])
            return []
        else:
            process = await self._get_or_reconnect_stdio(server_name)
            resp = await self._send_request_with_retry(
                process, "tools/list", None,
                request_id=self._get_request_id(server_name),
                server_name=server_name
            )
            if resp and "result" in resp:
                return resp["result"].get("tools", [])
            return []

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> str:
        """调用工具"""
        config = self._server_configs.get(server_name)
        if not config:
            return f"❌ 服务器 '{server_name}' 未配置"
        
        if config.get("type") == "http":
            http_conn = await self._get_or_connect_http(server_name)
            if not http_conn:
                return f"❌ 无法连接到 HTTP 服务器 '{server_name}'"
            resp = await self._send_http_request_with_retry(
                http_conn, "tools/call",
                {"name": tool_name, "arguments": arguments or {}}
            )
            if resp and "result" in resp:
                content = resp["result"].get("content", [])
                if content:
                    texts = [
                        item.get("text", "") for item in content
                        if isinstance(item, dict)
                    ]
                    return "\n".join(texts)
                return str(resp["result"])
            return f"❌ HTTP 调用失败: {resp}"
        else:
            process = await self._get_or_reconnect_stdio(server_name)
            resp = await self._send_request_with_retry(
                process, "tools/call",
                {"name": tool_name, "arguments": arguments or {}},
                request_id=self._get_request_id(server_name),
                server_name=server_name,
            )
            if resp and "result" in resp:
                content = resp["result"].get("content", [])
                if content:
                    texts = [
                        item.get("text", "") for item in content
                        if isinstance(item, dict)
                    ]
                    return "\n".join(texts)
                return str(resp["result"])
            return f"❌ 调用失败: {resp}"

    # ── HTTP 连接管理 ─────────────────────────────────────────────────────────

    async def _get_or_connect_http(self, name: str) -> Optional[_HttpConnection]:
        """获取或创建 HTTP 连接"""
        if name in self._http_connections:
            conn = self._http_connections[name]
            if conn.initialized and conn.client:
                conn.last_used = asyncio.get_event_loop().time()
                return conn
        
        config = self._server_configs.get(name)
        if not config or not config.get("http_url"):
            return None
        
        http_url = config["http_url"]
        headers = config.get("headers", {})
        
        conn = _HttpConnection(url=http_url, headers=headers)
        if await conn.initialize():
            self._http_connections[name] = conn
            logger.info(f"HTTP 服务器 '{name}' 已连接: {http_url}")
            return conn
        
        return None

    async def _send_http_request_with_retry(
        self,
        http_conn: _HttpConnection,
        method: str,
        params: Optional[dict] = None,
    ) -> Optional[dict]:
        """HTTP 请求带重试"""
        last_error = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await http_conn.send_request(method, params)
            except Exception as e:
                last_error = e
                if attempt < _MAX_RETRIES - 1:
                    delay = _BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"HTTP 请求重试 {attempt + 1}/{_MAX_RETRIES}: {method} "
                        f"(等待 {delay:.1f}s, 错误: {e})"
                    )
                    await asyncio.sleep(delay)
        logger.error(f"HTTP 请求失败（已达最大重试次数）: {method}: {last_error}")
        return None

    # ── 连接池内部 ────────────────────────────────────────────────────────────

    async def _get_or_reconnect_stdio(self, name: str) -> asyncio.subprocess.Process:
        """获取活跃的 stdio 连接，失效则自动重连"""
        if name in self._connections:
            conn = self._connections[name]
            if conn.process and conn.process.returncode is None:  # 进程仍在运行
                if conn.initialized:
                    return conn.process
                # 未初始化 → 重新初始化
                resp = await self._send_request(
                    conn.process, "initialize", {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "xiaolei", "version": "3.4.0"},
                    }, request_id=1, server_name=name
                )
                if resp and "result" in resp:
                    await self._send_notification(conn.process, "notifications/initialized", server_name=name)
                    conn.initialized = True
                    return conn.process
                else:
                    await self._cleanup_connection(name)
        else:
            await self._cleanup_connection(name)

        # 自动重连
        config = self._server_configs.get(name)
        if not config:
            raise ValueError(f"服务器 '{name}' 未配置")

        logger.info(f"🔄 自动重连 stdio 服务器: {name}")
        process = await self._create_process(name)
        conn = _Connection(process=process, server_name=name, connection_type="stdio")
        self._connections[name] = conn
        resp = await self._send_request(
            process, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "xiaolei", "version": "3.4.0"},
            }, request_id=1, server_name=name
        )
        if resp and "result" in resp:
            await self._send_notification(process, "notifications/initialized", server_name=name)
            conn.initialized = True
            return process
        raise RuntimeError(f"重连 stdio 服务器 '{name}' 失败")

    async def _send_request_with_retry(
        self,
        process: asyncio.subprocess.Process,
        method: str,
        params: Optional[dict] = None,
        request_id: int = 1,
        server_name: str = "",
    ) -> Optional[dict]:
        """带指数退避重试的 JSON-RPC 请求"""
        last_error = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await self._send_request(process, method, params, request_id, server_name=server_name)
            except (ConnectionError, asyncio.TimeoutError, json.JSONDecodeError) as e:
                last_error = e
                if attempt < _MAX_RETRIES - 1:
                    delay = _BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"请求重试 {attempt + 1}/{_MAX_RETRIES}: {method} "
                        f"(等待 {delay:.1f}s, 错误: {e})"
                    )
                    await asyncio.sleep(delay)
        # ponytail: 最后重试失败后清理连接，避免死进程永久占用
        logger.error(f"请求失败（已达最大重试次数）: {method}: {last_error}")
        await self._cleanup_connection(server_name)
        return None

    async def _send_request(
        self,
        process: asyncio.subprocess.Process,
        method: str,
        params: Optional[dict] = None,
        request_id: int = 1,
        server_name: str = "",
    ) -> Optional[dict]:
        """发送 JSON-RPC 请求（带锁保护，避免并发读写破坏协议）"""
        lock = self._get_server_lock(server_name)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=35.0)
        except asyncio.TimeoutError:
            logger.error(f"[mcp:{server_name}] 锁获取超时, method={method}")
            return None
        try:
            request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
            }
            if params:
                request["params"] = params

            request_str = json.dumps(request) + "\n"
            process.stdin.write(request_str.encode())
            await process.stdin.drain()

            response_line = await asyncio.wait_for(
                process.stdout.readline(), timeout=30.0
            )
            return json.loads(response_line.decode()) if response_line else None
        finally:
            lock.release()

    async def _send_notification(
        self,
        process: asyncio.subprocess.Process,
        method: str,
        params: Optional[dict] = None,
        server_name: str = "",
    ) -> None:
        """发送 JSON-RPC 通知（无 id，不期望响应）"""
        lock = self._get_server_lock(server_name)
        async with lock:
            notification = {"jsonrpc": "2.0", "method": method}
            if params:
                notification["params"] = params
            process.stdin.write((json.dumps(notification) + "\n").encode())
            await process.stdin.drain()

    # ── 进程管理 ──────────────────────────────────────────────────────────────

    async def _create_process(self, name: str) -> asyncio.subprocess.Process:
        """创建服务器进程"""
        config = self._server_configs.get(name)
        if not config:
            raise ValueError(f"服务器 '{name}' 未配置")

        proc_env = None
        if config.get("env"):
            proc_env = os.environ.copy()
            proc_env.update(config["env"])

        process_timeout = config.get("process_timeout", 60.0)  # ponytail: npx 首次下载常超 10s
        process = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                config["command"],
                *config["args"],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=config["cwd"],
                env=proc_env,
            ),
            timeout=process_timeout,
        )
        # ponytail: 异步消费 stderr，防止管道缓冲区满导致进程阻塞
        asyncio.create_task(self._consume_stderr(name, process))
        return process

    async def _consume_stderr(self, name: str, process: asyncio.subprocess.Process):
        """异步读取并记录 stderr，防止管道缓冲区满"""
        try:
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                logger.debug(f"[mcp:{name}] {line.decode().rstrip()}")
        except Exception as e:
            logger.debug(f"[mcp:{name}] stderr consumer 结束: {e}")

    async def _cleanup_connection(self, name: str):
        """清理连接进程和 HTTP 连接"""
        # 清理 stdio 连接
        conn = self._connections.pop(name, None)
        if conn and conn.process and conn.process.returncode is None:
            try:
                conn.process.terminate()
                await asyncio.wait_for(conn.process.wait(), timeout=5.0)
            except Exception:
                try:
                    conn.process.kill()
                except Exception:
                    pass
        
        # 清理 HTTP 连接
        http_conn = self._http_connections.pop(name, None)
        if http_conn:
            await http_conn.close()
            logger.info(f"HTTP 连接已清理: {name}")

    # ── 便捷连接方法 ──────────────────────────────────────────────────────────

    async def connect_agency_server(
        self,
        agency_path: Optional[str] = None,
        use_http: bool = False
    ) -> bool:
        """连接到 the-agency 服务器"""
        try:
            from ..engine.config_manager import ConfigManager
            config = ConfigManager.load()
            default_agency_path = config.paths.the_agency_path
            mcp_servers_dir = config.paths.mcp_servers_dir
        except Exception as e:
            logger.warning(f"无法加载配置，使用默认路径: {e}")
            default_agency_path = os.path.expanduser("~/the-agency")
            mcp_servers_dir = os.path.join(os.path.dirname(__file__), "..", "mcp")

        if agency_path is None:
            possible_paths = [
                default_agency_path,
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
            mcp_servers = glob.glob(os.path.join(mcp_servers_dir, "*.py"))
            fun_mcp = os.path.join(mcp_servers_dir, "fun_mcp_server.py")
            weather_mcp = os.path.join(mcp_servers_dir, "weather_mcp_server.py")

            print("\n📡 可用的本地MCP服务器:")
            if os.path.exists(fun_mcp):
                print(f"  ✅ 趣味MCP服务器: {fun_mcp}")
            if os.path.exists(weather_mcp):
                print(f"  ✅ 天气MCP服务器: {weather_mcp}")
            if mcp_servers:
                print("\n  📂 发现的MCP相关文件:")
                for f in mcp_servers[:5]:
                    print(f"     - {f}")
            return False

        package_json = os.path.join(agency_path, "package.json")
        if not os.path.exists(package_json):
            logger.warning(f"package.json 不存在: {package_json}")
            return False

        agency_port = os.getenv("AGENCY_SERVER_PORT", "8080")
        return await self.connect_server(
            name="the-agency",
            command="npx",
            args=["tsx", "src/integrations/claude-desktop/agency-server/index.ts"],
            cwd=agency_path,
            http_url=f"http://localhost:{agency_port}" if use_http else None,
        )

    async def connect_fun_server(self) -> bool:
        return await self._connect_mcp_server("fun", "fun_mcp_server.py", "趣味MCP")

    async def connect_weather_server(self) -> bool:
        return await self._connect_mcp_server("weather-mcp", "weather_mcp_server.py", "天气MCP")

    async def connect_calculator_server(self) -> bool:
        return await self._connect_mcp_server("calculator", "calculator_mcp_server.py", "计算器MCP")

    async def connect_file_ops_server(self) -> bool:
        return await self._connect_mcp_server("file-ops-mcp", "file_operations_mcp_server.py", "文件操作MCP")

    async def connect_text_processing_server(self) -> bool:
        return await self._connect_mcp_server("text-processing-mcp", "text_processing_mcp_server.py", "文本处理MCP")

    async def connect_sandbox_executor_server(self) -> bool:
        """连接代码沙盒执行器服务器"""
        return await self._connect_mcp_server("sandbox-executor", "sandbox_executor_mcp_server.py", "代码沙盒执行器")

    async def connect_web_search_server(self) -> bool:
        """连接联网搜索服务器"""
        return await self._connect_mcp_server("web-search", "web_search_mcp_server.py", "联网搜索")

    async def _connect_mcp_server(self, server_name: str, script_name: str, label: str) -> bool:
        """通用 MCP 服务器连接"""
        try:
            from ..engine.config_manager import ConfigManager
            config = ConfigManager.load()
            mcp_servers_dir = config.paths.mcp_servers_dir
        except Exception:
            mcp_servers_dir = os.path.join(os.path.dirname(__file__), "..", "mcp")

        script_path = os.path.join(mcp_servers_dir, script_name)
        if not os.path.exists(script_path):
            print(f"\n❌ {label}服务器不存在: {script_path}")
            return False

        success = await self.connect_server(
            name=server_name,
            command="python",
            args=[script_path],
            cwd=os.path.dirname(script_path),
        )
        print(f"\n{'✅' if success else '❌'} 成功连接到 {label}服务器" if success else f"\n❌ 连接 {label}服务器 失败")
        return success


mcp_client = MCPClientManager()
