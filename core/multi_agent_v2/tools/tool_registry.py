"""ToolRegistry — 工具注册表（含 handler 模式）

3 个可用工具：
- fetch_url: HTTP GET 获取网页/API数据
- file: 直接读写文件
- execute_code: 沙盒执行 Python/Shell 代码

自动发现：MCP 服务器（mcp/ 目录 + .mcp.json）
"""

import json, logging, os, re, time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
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
    fp = f"/tmp/agent_fetch_{int(time.time())}.json"
    Path(fp).write_text(clean, encoding="utf-8")
    msg = "状态码:%s 原始:%d字符\n📁%s\n%s" % (resp.status, len(text), fp, clean[:300])
    return {"result": {"content": [{"text": msg}]}}

async def _handle_file(args: Dict) -> Dict:
    action=args.get("action",""); path=args.get("path","")
    if action=="read":
        if not path or not os.path.isfile(path): return {"result":{"content":[{"text":"文件不存在"}]}}
        return {"result":{"content":[{"text":open(path,encoding="utf-8").read()}]}}
    if action=="write":
        c=args.get("content","")
        if not path or not c: return {"result":{"content":[{"text":"需要 path 和 content"}]}}
        path=os.path.expanduser(path); Path(path).parent.mkdir(parents=True,exist_ok=True)
        Path(path).write_text(c,encoding="utf-8")
        return {"result":{"content":[{"text":f"已写入 {path} ({len(c)} bytes)"}]}}
    return {"result":{"content":[{"text":"file 需要 action=read|write"}]}}

async def _handle_execute_code(args: Dict) -> Dict:
    from core.tools.sandbox_executor import SandboxExecutor
    ex=SandboxExecutor(); action=args.get("action","")
    if action=="run_python":
        code=args.get("code","")
        if not code: return {"result":{"content":[{"text":"缺少 code 参数"}]}}
        sr=await ex.execute_python(code,skip_module_check=True)
        o=sr.stdout or sr.stderr or sr.error_message or "(空输出)"
        return {"result":{"content":[{"text":f"[沙盒] {sr.status.value}\n{o[:5000]}"}]}}
    if action=="run_shell":
        cmd=args.get("command","")
        if not cmd: return {"result":{"content":[{"text":"缺少 command"}]}}
        sr=await ex.execute_shell(cmd)
        o=sr.stdout or sr.stderr or sr.error_message or ""
        return {"result":{"content":[{"text":f"[沙盒] {sr.status.value}\n{o[:3000]}"}]}}
    return {"result":{"content":[{"text":"execute_code 需要 action=run_python|run_shell"}]}}

_HANDLER_MAP: Dict[str, Callable] = {
    "execute_code": _handle_execute_code,
    "file": _handle_file,
    "fetch_url": _handle_fetch_url,
}

_SANDBOX_TOOL_DEFS = [
    ToolDefinition(name="execute_code", server=SERVER_BUILTIN, tags=["code","sandbox"],
        description="沙盒执行代码。action=run_python 执行 Python；action=run_shell 执行 Shell",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["run_python","run_shell"]},"code":{"type":"string"},"command":{"type":"string"},"timeout":{"type":"integer"}},"required":["action"]},
        handler=_handle_execute_code),
    ToolDefinition(name="file", server=SERVER_BUILTIN, tags=["file","direct"],
        description="直接读写文件。action=read/write，支持绝对路径",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["read","write"]},"path":{"type":"string"},"content":{"type":"string"}},"required":["action","path"]},
        handler=_handle_file),
    ToolDefinition(name="fetch_url", server=SERVER_BUILTIN, tags=["web","http","fetch"],
        description="HTTP GET 获取网页数据，自动提取 JSON，保存到 /tmp/",
        parameters={"type":"object","properties":{"url":{"type":"string"},"max_length":{"type":"integer","description":"默认80000"}},"required":["url"]},
        handler=_handle_fetch_url),
]

def _safe(raw: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False

    async def discover_all(self) -> List[ToolDefinition]:
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
        # Source 2: mcp_client
        try:
            from core.mcp.mcp_client import mcp_client
            proot = os.path.normpath(os.path.join(os.path.dirname(__file__),"..",".."))
            existing = set(await mcp_client.list_servers())
            # auto-discover mcp/ directory
            mcp_dir = os.path.join(proot, "mcp")
            if os.path.isdir(mcp_dir):
                for fn in sorted(os.listdir(mcp_dir)):
                    if not fn.endswith("_mcp_server.py"): continue
                    srv = fn.replace("_mcp_server.py","").replace("_","-")
                    if srv in existing: continue
                    try:
                        import asyncio
                        await asyncio.wait_for(mcp_client.connect_server(name=srv,command="python3",
                            args=[os.path.join(mcp_dir,fn)],cwd=proot,env={"PYTHONPATH":proot}), timeout=5)
                        existing.add(srv)
                    except: pass
            # .mcp.json
            mcj = os.path.join(proot, ".mcp.json")
            if os.path.exists(mcj):
                try:
                    with open(mcj) as f: cfg = json.load(f)
                    for srv,sc in cfg.get("mcpServers",{}).items():
                        if srv in existing: continue
                        try:
                            import asyncio
                            await asyncio.wait_for(mcp_client.connect_server(name=srv,command=sc["command"],
                                args=sc.get("args",[]),cwd=proot,env={"PYTHONPATH":proot}), timeout=5)
                            existing.add(srv)
                        except: pass
                except: pass
            for srv in existing:
                try:
                    import asyncio
                    for tool in await asyncio.wait_for(mcp_client.list_tools(srv), timeout=3):
                        raw = tool.get("name",""); fn = _safe(f"{srv}_{raw}")
                        if not raw or fn in self._tools: continue
                        t = ToolDefinition(name=fn, description=tool.get("description",""),
                            parameters=tool.get("inputSchema",{}) or {}, server=srv, tool_name=raw, tags=["mcp"])
                        all_tools.append(t); self._tools[fn] = t
                except: pass
        except: pass
        # Source 3: builtin tools
        for sd in _SANDBOX_TOOL_DEFS:
            if sd.name not in self._tools:
                self._tools[sd.name] = sd
                all_tools.append(sd)
        self._initialized = True
        return all_tools

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

    def get_tools_for_task(self, task: str, max_tools=25) -> List[ToolDefinition]:
        if not self._initialized: return list(self._tools.values())[:max_tools]
        desc = task.lower(); scored = []
        for t in self._tools.values():
            s = 0.0; dl = t.description.lower(); nl = t.name.lower()
            for kw in desc.split():
                kw = kw.strip().lower()
                if len(kw) > 1:
                    if kw in dl: s += 2.0
                    if kw in nl: s += 3.0
            if t.server == SERVER_BUILTIN: s += 1.0
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
