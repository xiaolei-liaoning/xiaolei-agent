#!/usr/bin/env python3
"""
Awesome MCP Servers 管理器 - 从 awesome-mcp-servers 列表中管理和连接 MCP 服务器
支持真正启动 MCP 服务器并调用其工具
"""

import asyncio
import json
import re
import os
import tempfile
import time
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class MCPProcess:
    """MCP 服务器进程封装（异步版）"""

    def __init__(self, name: str, command: str, args: List[str], env: Dict[str, str] = None):
        self.name = name
        self.command = command
        self.args = args
        self.env = env or os.environ.copy()
        self.process: Optional[asyncio.subprocess.Process] = None
        self.request_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> bool:
        """异步启动 MCP 服务器进程"""
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.command, *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
            logger.info(f"✅ MCP 服务器已启动: {self.name} (PID: {self.process.pid})")

            # 发送初始化请求
            init_result = await self._send_request("initialize", {
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

    async def _send_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """异步发送 JSON-RPC 请求"""
        if not self.process or self.process.stdin is None or self.process.stdout is None:
            return None

        async with self._lock:
            self.request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": method,
                "params": params
            }

            try:
                self.process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
                await self.process.stdin.drain()

                # 读取响应
                response_line = await self.process.stdout.readline()
                if response_line:
                    return json.loads(response_line.decode("utf-8").strip())
            except Exception as e:
                logger.error(f"发送请求失败: {e}")

        return None

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], method: str = "tools/call") -> Optional[Dict[str, Any]]:
        """调用 MCP 服务器工具

        Args:
            tool_name: 工具名
            arguments: 参数
            method: 调用的方法名（MCP 标准用 tools/call，本地服务器用 callTool）
        """
        return await self._send_request(method, {
            "name": tool_name,
            "arguments": arguments
        })

    async def list_tools(self) -> Optional[List[Dict[str, Any]]]:
        """列出可用工具"""
        result = await self._send_request("listTools", {})
        if result and "result" in result:
            return result["result"].get("tools", [])
        return None

    async def stop(self):
        """停止 MCP 服务器进程"""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                self.process.kill()
                await self.process.wait()
            logger.info(f"🛑 MCP 服务器已停止: {self.name}")


class AwesomeMCPManager:
    """Awesome MCP Servers 管理器"""

    def __init__(self):
        # awesome-mcp-servers 仓库在项目根目录（与 agent 目录同级）
        repo_root = Path(__file__).parent.parent.parent.parent
        self.base_path = repo_root / "awesome-mcp-servers"
        self.readme_path = self.base_path / "README.md"
        self._servers_cache: Optional[List[Dict[str, Any]]] = None
        self._connected_servers: Dict[str, MCPProcess] = {}
        self._event_callbacks: Dict[str, List[Callable]] = {
            "connected": [],
            "disconnected": [],
        }

        # 自定义服务器配置文件路径
        self.config_dir = Path(__file__).parent.parent.parent / "config"
        self.custom_servers_file = self.config_dir / "mcp_custom_servers.json"

        # 精选数据库路径
        self.known_servers_file = Path(__file__).parent.parent.parent / "data" / "known_mcp_servers.json"
        self._known_servers_cache: Optional[Dict[str, Any]] = None

        # 发现缓存（Layer 3 结果临时缓存）
        self._discovery_cache: Dict[str, Optional[Dict[str, Any]]] = {}

        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def on(self, event: str, callback: Callable):
        """注册事件回调，支持 connected/disconnected 事件"""
        if event in self._event_callbacks:
            self._event_callbacks[event].append(callback)

    def _emit(self, event: str, server_name: str, **kwargs):
        """触发事件，调用所有已注册的回调"""
        for cb in self._event_callbacks.get(event, []):
            try:
                cb(server_name, **kwargs)
            except Exception as e:
                logger.warning("事件回调异常 [%s] %s: %s", event, server_name, e)

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

    # ── 三层智能匹配：已知数据库 / 启发式提取 / GitHub 发现 ──────────────

    def _load_known_servers(self) -> Dict[str, Dict[str, Any]]:
        """Layer 1: 加载精选数据库 data/known_mcp_servers.json"""
        if self._known_servers_cache is not None:
            return self._known_servers_cache

        if not self.known_servers_file.exists():
            logger.warning(f"精选数据库不存在: {self.known_servers_file}")
            self._known_servers_cache = {}
            return self._known_servers_cache

        try:
            with open(self.known_servers_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._known_servers_cache = data.get("servers", {})
            logger.info(f"✅ 加载精选 MCP 服务器数据库: {len(self._known_servers_cache)} 个")
        except Exception as e:
            logger.error(f"加载精选数据库失败: {e}")
            self._known_servers_cache = {}
        return self._known_servers_cache

    def _extract_install_hints(self, description: str) -> Optional[Dict[str, Any]]:
        """Layer 2: 从描述文本启发式提取安装命令"""
        if not description:
            return None

        # npx -y <package> (最常见)
        m = re.search(r'`?npx\s+-y\s+(@?[\w-]+(?:/[\w-]+)?)`?', description)
        if m:
            return {"command": "npx", "args": ["-y", m.group(1)], "source": "description:npx"}

        # npx <package> (no -y, 需要描述中有 npx 关键词)
        m = re.search(r'`?npx\s+(@?[\w-]+(?:/[\w-]+)?)(?:\s+([\w\-\.\/]+))?`?', description)
        if m and ('npx' in description.lower() or 'install' in description.lower()):
            args = [m.group(1)]
            if m.group(2) and not m.group(2).startswith('--'):
                args.append(m.group(2))
            return {"command": "npx", "args": args, "source": "description:npx"}

        # npm install -g <package> → 转 npx -y
        m = re.search(r'npm\s+install\s+-g\s+(\S+)', description)
        if m:
            return {"command": "npx", "args": ["-y", m.group(1)], "source": "description:npm-g"}

        # pip install <package>
        m = re.search(r'pip\s+install\s+(\S+)', description)
        if m:
            return {"command": "pip", "args": ["install", m.group(1)], "source": "description:pip"}

        # uvx <package>
        m = re.search(r'uvx\s+(\S+)', description)
        if m:
            return {"command": "uvx", "args": [m.group(1)], "source": "description:uvx"}

        # docker run <image>
        m = re.search(r'docker\s+run\s+(\S+)', description)
        if m:
            return {"command": "docker", "args": ["run", m.group(1)], "source": "description:docker"}

        return None

    def _get_known_from_readme(self) -> List[Dict[str, Any]]:
        """Layer 2: 扫描 README 条目，尝试提取安装命令"""
        servers = self.parse_readme()
        results = []
        for srv in servers:
            hint = self._extract_install_hints(srv["description"])
            if hint:
                results.append({
                    "name": srv["name"],
                    "command": hint["command"],
                    "args": hint["args"],
                    "description": srv["description"],
                    "url": srv.get("url", ""),
                    "category": srv.get("category", "未分类"),
                    "confidence": "hint",
                    "source": hint["source"],
                })
        return results

    async def _discover_from_github(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """Layer 3: 按需从 GitHub 仓库发现安装命令"""
        if not repo_url or "github.com" not in repo_url:
            return None

        # 缓存命中
        if repo_url in self._discovery_cache:
            return self._discovery_cache[repo_url]

        try:
            # 解析 owner/repo
            m = re.search(r'github\.com/([^/]+/[^/]+?)(?:/|$|\.)', repo_url)
            if not m:
                return None
            repo_path = m.group(1).rstrip('/')

            async with asyncio.timeout(8):
                # 尝试获取 package.json
                pkg_url = f"https://raw.githubusercontent.com/{repo_path}/main/package.json"
                proc = await asyncio.create_subprocess_exec(
                    "curl", "-sL", pkg_url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                pkg = json.loads(stdout) if stdout else {}

                # 如果有 bin 字段或者 name
                pkg_name = pkg.get("name", "")
                if pkg_name:
                    result = {
                        "command": "npx",
                        "args": ["-y", pkg_name],
                        "package": pkg_name,
                        "source": "github:package.json",
                    }
                    # 如果 package.json 有 "bin" 且没有 "mcp" 前缀，尝试直接运行
                    if "bin" in pkg and not pkg_name.startswith("@modelcontextprotocol"):
                        bin_names = list(pkg["bin"].keys())
                        if bin_names:
                            # 有时 bin 名就是启动命令
                            result["args"] = ["-y", pkg_name]
                    self._discovery_cache[repo_url] = result
                    return result

                # 尝试 pyproject.toml (uvx)
                pyproj_url = f"https://raw.githubusercontent.com/{repo_path}/main/pyproject.toml"
                proc2 = await asyncio.create_subprocess_exec(
                    "curl", "-sL", pyproj_url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout2, _ = await proc2.communicate()
                content = stdout2.decode() if stdout2 else ""
                m2 = re.search(r'name\s*=\s*"([^"]+)"', content)
                if m2:
                    result = {
                        "command": "uvx",
                        "args": [m2.group(1)],
                        "package": m2.group(1),
                        "source": "github:pyproject.toml",
                    }
                    self._discovery_cache[repo_url] = result
                    return result

                # 尝试 setup.py
                setup_url = f"https://raw.githubusercontent.com/{repo_path}/main/setup.py"
                proc3 = await asyncio.create_subprocess_exec(
                    "curl", "-sL", setup_url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout3, _ = await proc3.communicate()
                m3 = re.search(r'name\s*=\s*["\']([^"\']+)["\']', stdout3.decode() if stdout3 else "")
                if m3:
                    result = {
                        "command": "pip",
                        "args": ["install", m3.group(1)],
                        "package": m3.group(1),
                        "source": "github:setup.py",
                    }
                    self._discovery_cache[repo_url] = result
                    return result

        except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
            logger.debug(f"GitHub 发现失败 {repo_url}: {e}")

        self._discovery_cache[repo_url] = None
        return None

    def get_connectable_list(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取三层合并的可连接服务器列表"""
        # Layer 1: 精选数据库
        known = self._load_known_servers()
        layer1 = []
        for name, cfg in known.items():
            layer1.append({
                "name": name,
                "command": cfg["command"],
                "args": cfg["args"],
                "env": cfg.get("env", {}),
                "description": cfg.get("description", ""),
                "category": cfg.get("category", "未分类"),
                "requires_env": [k for k, v in cfg.get("env", {}).items() if v is None],
                "confidence": "known",
                "source": "database",
            })

        # Layer 2: README 启发式提取
        layer2 = self._get_known_from_readme()

        # 去重：layer2 中 layer1 有的去掉
        layer1_names = {s["name"].lower() for s in layer1}
        layer2_filtered = [s for s in layer2 if s["name"].lower() not in layer1_names]

        return {
            "known": sorted(layer1, key=lambda x: x["name"]),
            "hints": sorted(layer2_filtered, key=lambda x: x["name"]),
            "total_known": len(layer1),
            "total_hints": len(layer2_filtered),
        }

    async def smart_connect(self, server_name: str) -> Dict[str, Any]:
        """三层智能连接：已知库 → 启发式 → GitHub 发现"""
        key = server_name.lower().strip()

        # 先查已连接
        if key in self._connected_servers:
            return {
                "success": True,
                "message": f"✅ {server_name} 已经连接",
            }

        # Layer 1: 精选数据库
        known = self._load_known_servers()
        if key in known:
            cfg = known[key]
            return await self._do_connect(key, cfg["command"], cfg["args"], cfg.get("env", {}))

        # Layer 2: README 启发式
        servers = self.parse_readme()
        for srv in servers:
            if srv["name"].lower() == key:
                hint = self._extract_install_hints(srv["description"])
                if hint:
                    return await self._do_connect(key, hint["command"], hint["args"], {})
                # Layer 3: GitHub 发现
                if "github.com" in srv.get("url", ""):
                    discovered = await self._discover_from_github(srv["url"])
                    if discovered:
                        return await self._do_connect(
                            key, discovered["command"], discovered["args"], {}
                        )
                break

        # 全都没找到
        known_names = list(known.keys())
        return {
            "success": False,
            "message": f"❌ 未找到 {server_name} 的连接方式。\n"
                       f"已知服务器 ({len(known_names)} 个): {', '.join(known_names[:10])}...\n"
                       f"💡 提示: 在 config/mcp_servers.yml 中手动配置，或使用 connect_server() 注入"
        }

    async def _do_connect(self, name: str, command: str, args: List[str],
                          env: Dict[str, str]) -> Dict[str, Any]:
        """执行实际的 MCP 连接，自动解析本地 mcp/ 路径"""
        if name in self._connected_servers:
            await self._connected_servers[name].stop()
            del self._connected_servers[name]

        # 解析本地 mcp/ 脚本路径为绝对路径
        project_root = Path(__file__).parent.parent.parent
        resolved_args = []
        for arg in args:
            if arg.startswith("mcp/") or arg.startswith("./mcp/"):
                resolved_args.append(str(project_root / arg))
            else:
                resolved_args.append(arg)

        process = MCPProcess(name=name, command=command, args=resolved_args, env=env or None)
        success = await process.start()
        if success:
            self._connected_servers[name] = process
            self._emit("connected", name)
            tools = await self._get_server_tools(name)
            # 连接后立即预填充工具定义缓存，避免 agent 首次查询时为空
            try:
                self._tool_defs_cache = await self.get_all_tool_definitions(refresh=True)
                self._tool_defs_cache_time = time.time()
            except Exception:
                pass
            return {
                "success": True,
                "message": f"✅ 成功连接 {name}\n命令: {command} {' '.join(args)}",
                "tools": tools,
            }
        else:
            return {
                "success": False,
                "message": f"❌ 连接 {name} 失败\n命令: {command} {' '.join(args)}",
            }

    async def quick_connect(self, server_name: str, timeout: float = 15.0) -> Dict[str, Any]:
        """快速连接并启动 MCP 服务器（带超时保护）"""
        async def _do_connect():
            quick_connect_map = self._get_all_server_configs()

            server_key = server_name.lower().strip()
            if server_key not in quick_connect_map:
                return {
                    "success": False,
                    "message": f"未知的快速连接服务器: {server_name}\n可用服务器: {', '.join(quick_connect_map.keys())}"
                }

            config = quick_connect_map[server_key]

            if server_key in self._connected_servers:
                await self._connected_servers[server_key].stop()
                del self._connected_servers[server_key]

            process = MCPProcess(
                name=server_key,
                command=config["command"],
                args=config["args"],
                env=config.get("env")
            )

            success = await process.start()
            if success:
                self._connected_servers[server_key] = process
                self._emit("connected", server_key)
                tools = await self._get_server_tools(server_key)
                # 预填充工具定义缓存
                try:
                    self._tool_defs_cache = await self.get_all_tool_definitions(refresh=True)
                    self._tool_defs_cache_time = time.time()
                except Exception:
                    pass
                return {
                    "success": True,
                    "message": f"✅ 成功启动 {server_key}\n命令: {config['command']} {' '.join(config['args'])}",
                    "tools": tools
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ 启动 {server_key} 失败"
                }

        try:
            return await asyncio.wait_for(_do_connect(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"MCP 快速连接超时 ({timeout}s): {server_name}")
            return {
                "success": False,
                "message": f"❌ 连接 {server_name} 超时（{timeout}s），可能网络慢或 npx 未安装"
            }

    def _get_all_server_configs(self) -> Dict[str, Dict[str, Any]]:
        """获取所有服务器配置（精选库 + 自定义）"""
        # 从精选数据库加载
        known = self._load_known_servers()
        configs = {}
        for name, cfg in known.items():
            configs[name] = {
                "package": cfg.get("package", ""),
                "command": cfg["command"],
                "args": cfg["args"][:],
                "env": cfg.get("env", {}),
                "description": cfg.get("description", ""),
            }

        # 加载自定义配置（覆盖精选库中同名的）
        custom_configs = self._load_custom_servers()
        configs.update(custom_configs)

        return configs

    def _load_custom_servers(self) -> Dict[str, Dict[str, Any]]:
        """加载自定义服务器配置"""
        if not self.custom_servers_file.exists():
            return {}
        
        try:
            with open(self.custom_servers_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('servers', {})
        except Exception as e:
            logger.error(f"加载自定义服务器配置失败: {e}")
            return {}

    def register_server(self, name: str, command: str, args: List[str], 
                       env: Optional[Dict[str, str]] = None, 
                       description: str = "") -> bool:
        """注册自定义 MCP 服务器"""
        custom_configs = self._load_custom_servers()
        
        # 添加新服务器
        custom_configs[name.lower()] = {
            "command": command,
            "args": args,
            "env": env or {},
            "description": description,
            "custom": True
        }
        
        # 保存到文件
        try:
            with open(self.custom_servers_file, 'w', encoding='utf-8') as f:
                json.dump({"servers": custom_configs}, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ 已注册自定义服务器: {name}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存自定义服务器配置失败: {e}")
            return False

    def unregister_server(self, name: str) -> bool:
        """注销自定义 MCP 服务器"""
        custom_configs = self._load_custom_servers()
        server_key = name.lower()
        
        if server_key not in custom_configs:
            logger.warning(f"⚠️ 服务器 {name} 不存在或不是自定义服务器")
            return False
        
        del custom_configs[server_key]
        
        try:
            with open(self.custom_servers_file, 'w', encoding='utf-8') as f:
                json.dump({"servers": custom_configs}, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ 已注销自定义服务器: {name}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存配置失败: {e}")
            return False

    def get_custom_servers_list(self) -> List[Dict[str, Any]]:
        """获取所有自定义服务器列表"""
        custom_configs = self._load_custom_servers()
        result = []
        for name, config in custom_configs.items():
            result.append({
                "name": name,
                "command": config.get("command"),
                "args": config.get("args"),
                "description": config.get("description", ""),
                "custom": True
            })
        return result

    async def _get_server_tools(self, server_name: str) -> Optional[List[str]]:
        """获取服务器提供的工具名称列表"""
        if server_name not in self._connected_servers:
            return None
        tools = await self._connected_servers[server_name].list_tools()
        if tools:
            return [t.get("name", "unknown") for t in tools]
        return None

    async def get_all_tool_definitions(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """收集所有已连接 MCP 服务器的工具，转换为 LLM function_call 格式
        （带缓存：每 60 秒刷新一次）

        返回格式 (OpenAI function calling):
        [{
            "type": "function",
            "function": {
                "name": "sandbox-tools.read_file",
                "description": "...",
                "parameters": {"type": "object", "properties": {...}, "required": [...]}
            },
            "_server": "sandbox-tools-mcp",   # 内部字段：用于路由回正确的 MCP 服务器
            "_tool_name": "read_file",        # 原始工具名
        }]
        """
        now = time.time()
        # 缓存有效期为 60 秒
        if hasattr(self, '_tool_defs_cache') and self._tool_defs_cache:
            cache_time = getattr(self, '_tool_defs_cache_time', 0)
            if now - cache_time < 60:
                return self._tool_defs_cache

        definitions = []
        tool_servers = {}

        for server_name in self._connected_servers:
            try:
                tools = await self._connected_servers[server_name].list_tools()
                if not tools:
                    continue

                for tool_def in tools:
                    name = tool_def.get("name", "")
                    if not name:
                        continue

                    unique_name = f"{server_name}.{name}"
                    if unique_name in tool_servers:
                        continue

                    tool_servers[unique_name] = server_name
                    input_schema = tool_def.get("inputSchema", {}) or {}

                    definitions.append({
                        "type": "function",
                        "function": {
                            "name": unique_name,
                            "description": tool_def.get("description", ""),
                            "parameters": input_schema,
                        },
                        "_server": server_name,
                        "_tool_name": name,
                    })

            except Exception as e:
                logger.warning(f"获取 {server_name} 工具列表失败: {e}")

        self._tool_defs_cache = definitions
        self._tool_defs_cache_time = now
        return definitions

    async def call_tool_by_definition(self, tool_def: Dict[str, Any], arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """根据工具定义调用 MCP 工具（供 agency_agent 使用）

        Args:
            tool_def: get_all_tool_definitions() 返回的工具定义条目
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        server_name = tool_def.get("_server", "")
        tool_name = tool_def.get("_tool_name", "")
        if not server_name or not tool_name:
            return {"error": "无效的工具定义"}
        # 先试 tools/call（MCP 标准），失败再试 callTool（本地格式）
        result = await self.call_server_tool(server_name, tool_name, arguments)
        if result is None or "error" in result:
            result2 = await self._connected_servers[server_name].call_tool(tool_name, arguments, method="callTool")
            if result2 and "result" in result2:
                return result2
        return result

    async def call_server_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用 MCP 服务器的工具"""
        if server_name not in self._connected_servers:
            logger.error(f"MCP 服务器未连接: {server_name}")
            return None

        return await self._connected_servers[server_name].call_tool(tool_name, arguments)

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

    async def get_server_tools(self, server_name: str) -> Optional[List[Dict[str, Any]]]:
        """获取服务器的工具列表详情"""
        if server_name not in self._connected_servers:
            return None
        return await self._connected_servers[server_name].list_tools()

    async def disconnect_server(self, server_name: str) -> bool:
        """断开 MCP 服务器连接"""
        if server_name in self._connected_servers:
            await self._connected_servers[server_name].stop()
            del self._connected_servers[server_name]
            self._emit("disconnected", server_name)
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

    async def format_connected_servers(self) -> str:
        """格式化已连接服务器信息"""
        if not self._connected_servers:
            return "📭 暂无已连接的 MCP 服务器\n\n可用快速连接: " + ", ".join(self.get_available_quick_connect())

        result = f"🔗 已连接的 MCP 服务器 ({len(self._connected_servers)} 个)\n\n"

        for name, process in self._connected_servers.items():
            tools = await self._get_server_tools(name)
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
        all_configs = self._get_all_server_configs()
        return list(all_configs.keys())

awesome_mcp_manager = AwesomeMCPManager()
