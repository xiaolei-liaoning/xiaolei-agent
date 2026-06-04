"""ToolRegistry — 工具注册表（含 handler 模式）

3 个可用工具：
- fetch_url: HTTP GET 获取网页/API数据
- file: 直接读写文件
- execute_code: 沙盒执行 Python/Shell 代码

自动发现：MCP 服务器（mcp/ 目录 + .mcp.json）
"""

import asyncio, json, logging, os, re, time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SERVER_BUILTIN = "__builtin__"

@dataclass
class ToolDefinition:
    name: str; description: str; parameters: Dict[str, Any]
    server: str = ""; tool_name: str = ""; tags: List[str] = field(default_factory=list)
    handler: Optional[Callable] = None

# ═══════════════════════════════════════════════════════════════════
# Handlers
# ═══════════════════════════════════════════════════════════════════

async def _handle_fetch_url(args: Dict) -> Dict:
    url = args.get("url", ""); ml = args.get("max_length", 80000)
    if not url: return {"result": {"content": [{"text": "需要 url 参数"}]}}
    import asyncio, ssl, urllib.request
    from urllib.parse import urlparse, urlunparse, quote
    # URL 中文编码
    try:
        url.encode("ascii")
    except (UnicodeEncodeError, UnicodeDecodeError):
        parsed = urlparse(url)
        path = quote(parsed.path, safe="/%@") if parsed.path else ""
        q = parsed.query
        if q:
            try: q.encode("ascii")
            except (UnicodeEncodeError, UnicodeDecodeError):
                parts = []
                for part in q.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        try: v.encode("ascii")
                        except: v = quote(v, safe="")
                        parts.append(f"{k}={v}")
                    else: parts.append(part)
                q = "&".join(parts)
        url = urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, q, parsed.fragment))
    loop = asyncio.get_running_loop()
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, context=ctx, timeout=15))
        data = resp.read().decode("utf-8", errors="replace"); text = data[:ml]
    except Exception as e:
        return {"result": {"content": [{"text": f"请求失败: {e}"}]}}
    # 提取 JSON
    je = None
    for p in [r'<!--s-data:(.*?)-->', r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
              r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>']:
        m = re.search(p, text, re.DOTALL)
        if m: je = m.group(1).strip(); break
    if not je:
        m = re.search(r'[\{\[]', text)
        if m: je = text[m.start():]
    clean = je or text

    # 检测 CSS/HTML 无意义内容（百度热搜等动态页面）
    stripped = clean.strip()
    if not je and (stripped.startswith("<") or "margin-top" in stripped[:500]):
        return {"result": {"content": [{"text": "网页是动态HTML，无法直接提取数据。请用 execute_code 执行 Python 通过 requests + BeautifulSoup/正则解析来抓取数据。"}]}}

    fp = f"/tmp/agent_fetch_{int(time.time())}.json"
    Path(fp).write_text(clean, encoding="utf-8")
    msg = "状态码:%s 原始:%d字符\n📁%s\n%s" % (resp.status, len(text), fp, clean[:300])
    return {"result": {"content": [{"text": msg}]}}

async def _handle_file(args: Dict) -> Dict:
    action=args.get("action",""); path=args.get("path","")
    if not path: return {"result":{"content":[{"text":"需要 path 参数"}]}}
    # 处理 Windows 路径（%USERPROFILE% 等）— macOS 上替换为 $HOME
    import re
    path = re.sub(r'%([^%]+)%', lambda m: os.environ.get(m.group(1), os.environ.get('HOME', '~')), path)
    path = os.path.expanduser(path)
    if action=="read":
        if not os.path.isfile(path): return {"result":{"content":[{"text":f"文件不存在: {path}"}]}}
        return {"result":{"content":[{"text":open(path,encoding="utf-8").read()}]}}
    if action=="write":
        c=args.get("content","")
        if not c: return {"result":{"content":[{"text":"需要 content 参数"}]}}
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        Path(path).write_text(c,encoding="utf-8")
        return {"result":{"content":[{"text":f"已写入 {path} ({len(c)} bytes)"}]}}
    return {"result":{"content":[{"text":"file 需要 action=read|write"}]}}

async def _handle_search(args: Dict) -> Dict:
    """搜索 — 并发尝试多个搜索引擎，谁先返回有效结果用谁"""
    query = args.get("query", "")
    if not query: return {"result": {"content": [{"text": "需要 query 参数"}]}}
    from urllib.parse import quote
    encoded = quote(query)

    async def _try_one(url: str) -> str:
        try:
            result = await _handle_fetch_url({"url": url, "max_length": 10000})
            text = result.get("result", {}).get("content", [{}])[0].get("text", "")
            if text and "请求失败" not in text and "动态HTML" not in text and len(text) > 80:
                return f"搜索结果({url}):\n{text[:2000]}"
        except BaseException:
            pass  # 捕获 CancelledError 等（Python 3.13 中 CancelledError 继承 BaseException）
        return ""

    urls = [
        f"https://cn.bing.com/search?q={encoded}&count=10",
        f"https://www.google.com/search?q={encoded}&hl=zh-CN&num=10",
        f"https://www.baidu.com/s?wd={encoded}&rn=10",
    ]
    # 并发搜，谁先回用谁（超时10秒）
    tasks = [asyncio.create_task(_try_one(u)) for u in urls]
    done, pending = await asyncio.wait(tasks, timeout=10.0, return_when=asyncio.FIRST_COMPLETED)
    # 取消还没完成的
    for p in pending: p.cancel()
    for task in done:
        text = task.result()
        if text:
            return {"result": {"content": [{"text": text}]}}
    # 全部失败，等剩余的完成
    for task in tasks:
        if task not in done:
            try:
                text = await asyncio.wait_for(task, timeout=5.0)
                if text:
                    return {"result": {"content": [{"text": text}]}}
            except BaseException:
                pass
    return {"result": {"content": [{"text": "搜索暂时无法获取结果，请用 fetch_url 直接访问目标网址"}]}}

async def _handle_execute_code(args: Dict) -> Dict:
    action=args.get("action","")
    if action=="run_python":
        code=args.get("code","")
        if not code: return {"result":{"content":[{"text":"缺少 code 参数"}]}}
        # 第1层：沙盒执行
        try:
            from core.tools.sandbox_executor import SandboxExecutor
            ex=SandboxExecutor()
            sr=await ex.execute_python(code,skip_module_check=True)
            o=sr.stdout or sr.stderr or sr.error_message or ""
            if sr.status.value == "success":
                return {"result":{"content":[{"text":f"[沙盒] success\n{o[:5000]}"}]}}
        except Exception:
            pass
        # 第2层：本地 exec() 兜底 — 使用 textwrap.dedent 处理缩进
        exec_error = None
        try:
            import io, contextlib, textwrap
            dedented = textwrap.dedent(code)
            f=io.StringIO(); err=io.StringIO()
            with contextlib.redirect_stdout(f), contextlib.redirect_stderr(err):
                try:
                    exec(dedented)
                except SyntaxError as se:
                    exec_error = f"[本地] 语法错误: 行 {se.lineno}: {se.msg}\n{se.text}"
                except Exception as ie:
                    exec_error = f"[本地] 执行异常: {type(ie).__name__}: {ie}"
                else:
                    o=f.getvalue() or err.getvalue() or "(无输出)"
                    return {"result":{"content":[{"text":f"[本地] success\n{o[:5000]}"}]}}
        except Exception as e:
            if exec_error is None:
                exec_error = f"[本地] 异常: {e}"
        # 第3层：subprocess 兜底 — 写入临时文件执行
        tmp_path = f"/tmp/agent_script_{os.urandom(4).hex()}.py"
        subprocess_error = None
        try:
            Path(tmp_path).write_text(code, encoding="utf-8")
            proc = await asyncio.create_subprocess_exec(
                "python3", tmp_path,
                stdout=-1,
                stderr=-1
            )
            stdout, stderr = await proc.communicate()
            out_text = stdout.decode("utf-8", errors="replace")
            err_text = stderr.decode("utf-8", errors="replace")
            if proc.returncode == 0:
                return {"result":{"content":[{"text":f"[subprocess] success\n{out_text[:5000]}"}]}}
            subprocess_error = f"[subprocess] exit code {proc.returncode}"
            if out_text: subprocess_error += f"\nstdout: {out_text[:2000]}"
            if err_text: subprocess_error += f"\nstderr: {err_text[:2000]}"
        except Exception as sub_e:
            subprocess_error = f"[subprocess] 执行失败: {sub_e}"
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
        # 所有方式均失败
        msg = exec_error or subprocess_error or "[本地] 未知错误"
        return {"result":{"content":[{"text":msg[:5000]}]}}
    if action=="run_shell":
        cmd=args.get("command","")
        if not cmd: return {"result":{"content":[{"text":"缺少 command"}]}}
        try:
            import asyncio
            proc=await asyncio.create_subprocess_shell(cmd,stdout=-1,stderr=-1)
            o,_=await proc.communicate()
            return {"result":{"content":[{"text":f"[本地] {proc.returncode}\n{o.decode()[:3000]}"}]}}
        except Exception as e:
            return {"result":{"content":[{"text":f"[本地] failed\n{str(e)[:2000]}"}]}}
    return {"result":{"content":[{"text":"execute_code 需要 action=run_python|run_shell"}]}}

_HANDLER_MAP: Dict[str, Callable] = {
    "fetch_url": _handle_fetch_url,
    "file": _handle_file,
    "search": _handle_search,
    "execute_code": _handle_execute_code,
}

_SANDBOX_TOOL_DEFS = [
    ToolDefinition(name="execute_code", server=SERVER_BUILTIN, tags=["code","sandbox"],
        description="沙盒执行代码。action=run_python 执行 Python(网络/文件/数据分析)；action=run_shell 执行 Shell",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["run_python","run_shell"]},"code":{"type":"string"},"command":{"type":"string"},"timeout":{"type":"integer"}},"required":["action"]},
        handler=_handle_execute_code),
    ToolDefinition(name="search", server=SERVER_BUILTIN, tags=["web","search"],
        description="联网搜索查询信息。当用户要求搜索、查找、查询时使用",
        parameters={"type":"object","properties":{"query":{"type":"string","description":"搜索关键词"}},"required":["query"]},
        handler=_handle_search),
    ToolDefinition(name="fetch_url", server=SERVER_BUILTIN, tags=["web","fetch"],
        description="HTTP GET 获取网页/API数据。用于抓取网页内容、调用API接口",
        parameters={"type":"object","properties":{"url":{"type":"string","description":"目标URL"},"max_length":{"type":"integer","description":"最大返回字符数"}},"required":["url"]},
        handler=_handle_fetch_url),
    ToolDefinition(name="file", server=SERVER_BUILTIN, tags=["file","storage"],
        description="直接读写文件。action=read 读取文件内容；action=write 写入文件内容",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["read","write"]},"path":{"type":"string","description":"文件路径"},"content":{"type":"string","description":"写入内容（write时必填）"}},"required":["action","path"]},
        handler=_handle_file),
]

def _safe(raw: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)

class ToolRegistry:
    """工具注册表 — 懒加载 MCP + 智能工具筛选"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False
        self._mcp_servers_discovered: Set[str] = set()  # 已配置但未连的 MCP 服务器

    async def ensure_mcp_tools_loaded(self) -> None:
        """懒加载：连接 MCP 服务器并获取工具定义（首次需要工具时调用）"""
        if not self._mcp_servers_discovered:
            return
        from core.mcp.mcp_client import mcp_client
        servers = list(self._mcp_servers_discovered)
        self._mcp_servers_discovered.clear()
        for srv in servers:
            try:
                for tool in await asyncio.wait_for(mcp_client.list_tools(srv), timeout=3):
                    raw = tool.get("name",""); fn = _safe(f"{srv}_{raw}")
                    if not raw or fn in self._tools: continue
                    t = ToolDefinition(name=fn, description=tool.get("description",""),
                        parameters=tool.get("inputSchema",{}) or {}, server=srv,
                        tool_name=raw, tags=["mcp"])
                    self._tools[fn] = t
            except Exception:
                pass  # 连接失败就跳过，不影响其他工具

    async def discover_all(self) -> List[ToolDefinition]:
        """发现所有工具来源，MCP 只注册配置不启动进程"""
        all_tools = []
        # Source 1: awesome_mcp
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            for td in await awesome_mcp_manager.get_all_tool_definitions():
                fn = td.get("function", {}); raw = fn.get("name", ""); name = _safe(raw)
                if name:
                    t = ToolDefinition(name=name, description=fn.get("description",""),
                        parameters=fn.get("parameters",{}), server="__mcp__",
                        tool_name=td.get("_tool_name", raw), tags=["mcp"])
                    all_tools.append(t); self._tools[name] = t
        except: pass
        # Source 2: builtin tools — 先加载，不阻塞
        for sd in _SANDBOX_TOOL_DEFS:
            if sd.name not in self._tools:
                self._tools[sd.name] = sd
                all_tools.append(sd)
        self._initialized = True

        # Source 3: mcp_client — 后台任务，不阻塞返回
        asyncio.ensure_future(self._connect_mcp_servers())

        return all_tools

    async def _connect_mcp_servers(self) -> None:
        """后台连接 MCP 服务器（不阻塞 discover_all 返回）"""
        try:
            from core.mcp.mcp_client import mcp_client
            proot = os.path.normpath(os.path.join(os.path.dirname(__file__),"..","..",".."))
            existing = set(await mcp_client.list_servers())
            bg_tasks = []
            srv_names = []

            mcp_dir = os.path.join(proot, "mcp")
            if os.path.isdir(mcp_dir):
                for fn in sorted(os.listdir(mcp_dir)):
                    if not fn.endswith("_mcp_server.py"): continue
                    srv = fn.replace("_mcp_server.py","").replace("_","-")
                    if srv in existing: continue
                    srv_names.append(srv)
                    bg_tasks.append(asyncio.wait_for(
                        mcp_client.connect_server(name=srv, command="python3",
                            args=[os.path.join(mcp_dir,fn)], cwd=proot,
                            env={"PYTHONPATH": proot}), timeout=5))

            mcj = os.path.join(proot, ".mcp.json")
            if os.path.exists(mcj):
                try:
                    with open(mcj) as f: cfg = json.load(f)
                    for srv,sc in cfg.get("mcpServers",{}).items():
                        if srv in existing: continue
                        srv_names.append(srv)
                        bg_tasks.append(asyncio.wait_for(
                            mcp_client.connect_server(name=srv, command=sc["command"],
                                args=sc.get("args",[]), cwd=proot,
                                env={"PYTHONPATH": proot}), timeout=5))
                except: pass

            if bg_tasks:
                results = await asyncio.gather(*bg_tasks, return_exceptions=True)
                for i, r in enumerate(results):
                    if i < len(srv_names) and not isinstance(r, Exception):
                        existing.add(srv_names[i])
            known = {t.server for t in self._tools.values()
                     if t.server not in ("__builtin__","__mcp__","")}
            self._mcp_servers_discovered.update(existing - known)
        except Exception:
            pass

    def get_handler_map(self) -> Dict[str, Callable]:
        result = dict(_HANDLER_MAP)
        for n, td in self._tools.items():
            if td.handler and n not in result: result[n] = td.handler
        return result

    def get_handler(self, name: str) -> Optional[Callable]:
        h = _HANDLER_MAP.get(name)
        if h: return h
        td = self._tools.get(name)
        return td.handler if td else None

    async def get_tools_for_task(self, task: str, max_tools=25) -> List[ToolDefinition]:
        """按任务相关性排序的工具列表（含中文关键词）"""
        if self._mcp_servers_discovered:
            await self.ensure_mcp_tools_loaded()
        if not self._initialized:
            return list(self._tools.values())[:max_tools]
        desc = task.lower()
        scored = []
        for t in self._tools.values():
            s = 0.0
            dl = t.description.lower()
            nl = t.name.lower()
            for kw in desc.split():
                kw = kw.strip().lower()
                if len(kw) > 1:
                    if kw in dl: s += 2.0
                    if kw in nl: s += 3.0
            if len(desc) > 1:
                if any(c in dl for c in desc if len(c.strip()) > 0):
                    s += 0.5
            if t.server == SERVER_BUILTIN:
                s += 1.0
            scored.append((s, t))
        scored.sort(key=lambda x: -x[0])
        result = [t for s,t in scored if s > 0]
        core = [t for t in self._tools.values() if t.name in ("file","fetch_url","execute_code")]
        for t in core:
            if t not in result: result.append(t)
        if len(result) < 5:
            seen = {t.name for t in result}
            for t in self._tools.values():
                if t.name not in seen:
                    result.append(t)
                    if len(result) >= max_tools: break
        return result[:max_tools]

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def validate_arguments(self, name: str, args: Dict) -> tuple:
        t = self._tools.get(name)
        if not t: return False, "未知工具"
        p = t.parameters
        if not p: return True, ""
        props = p.get("properties",{}); req = p.get("required",[])
        for f in req:
            if f not in args: return False, f"缺少 {f}"
        for k,v in list(args.items()):
            if k in props:
                pt = props[k].get("type","")
                if pt == "string" and not isinstance(v, str): args[k] = str(v)
                elif pt in ("integer","number") and isinstance(v, str):
                    try: args[k] = int(v) if pt=="integer" else float(v)
                    except: return False, f"{k} 不能从 {v} 转换"
        return True, ""

    @property
    def count(self) -> int: return len(self._tools)

_registry = None
def get_tool_registry() -> 'ToolRegistry':
    global _registry
    if _registry is None: _registry = ToolRegistry()
    return _registry
