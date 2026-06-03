"""
统一工具注册表 — 含 standalone handler 模式

整合六路工具来源：
1. awesome_mcp_manager   — 外部的 114+ 个 MCP 工具（名称安全化）
2. mcp_client            — 本地 MCP 服务器（自动发现 mcp/ 目录 + .mcp.json）
3. SkillDispatcher       — plugin/skills/ 和 config 注册的本地技能
4. plugin/api/           — 功能级 API 路由
5. SkillRegistry         — GuidanceSkill 指导型技能（SKILL.md）
6. builtin               — 8 个合并沙箱工具（降低 LLM 选择噪音）

handler 模式：ToolDefinition 绑定 handler 函数，消除 if-elif 路由链。
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """标准化的工具定义"""
    name: str                              # 完整名称（含前缀）
    description: str                       # 功能描述
    parameters: Dict[str, Any]            # JSON Schema 参数定义
    server: str = ""                       # 来源服务器标识
    tool_name: str = ""                    # 去除前缀后的工具名
    tags: List[str] = field(default_factory=list)  # 功能标签
    handler: Optional[Callable] = None     # 执行函数，绑定后无需 if-elif 路由


# ── 特殊 server 标识常量 ────────────────────────────────────────────────
SERVER_SKILL = "__skill__"
SERVER_API = "__api__"
SERVER_GUIDANCE = "__guidance__"
SERVER_MCP = "__mcp__"
SERVER_BUILTIN = "__builtin__"


# ═══════════════════════════════════════════════════════════════════
# Standalone handlers — 不与任何 Agent 类绑定
# ═══════════════════════════════════════════════════════════════════

async def _handle_fetch_url(args: Dict) -> Dict:
    url = args.get("url", ""); ml = args.get("max_length", 80000)
    if not url: return {"result": {"content": [{"text": "参数缺失: 需要 url"}]}}
    import ssl, urllib.request
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, context=ctx, timeout=15)
    data = resp.read().decode("utf-8", errors="replace"); text = data[:ml]
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
    msg = "状态码:%s 原始:%d字符\n📁%s\n%s" % (resp.status, len(text), fp, clean[:2000])
    return {"result": {"content": [{"text": msg}]}}


async def _handle_file(args: Dict) -> Dict:
    action=args.get("action",""); path=args.get("path","")
    if action=="read":
        if not path or not os.path.isfile(path): return {"result":{"content":[{"text":"文件不存在"}]}}
        return {"result":{"content":[{"text":open(path,encoding="utf-8").read()}]}}
    if action=="write":
        c=args.get("content","")
        if not path or not c: return {"result":{"content":[{"text":"参数缺失"}]}}
        path=os.path.expanduser(path); Path(path).parent.mkdir(parents=True,exist_ok=True)
        Path(path).write_text(c,encoding="utf-8")
        return {"result":{"content":[{"text":f"已写入 {path} ({len(c)} bytes)"}]}}
    return {"result":{"content":[{"text":"file 需要 action=read|write"}]}}


async def _handle_execute_code(args: Dict) -> Dict:
    from core.tools.sandbox_executor import SandboxExecutor
    ex=SandboxExecutor(); action=args.get("action",""); ws=args.get("workspace_id","")
    if action=="run_python":
        code=args.get("code","")
        if not code: return {"result":{"content":[{"text":"缺少 code"}]}}
        if ws:
            from core.sandbox.enhanced_executor import get_enhanced_executor
            r=await get_enhanced_executor().execute_python(ws,code,timeout=args.get("timeout",30))
            t=r.get("stdout","") or r.get("stderr","") or r.get("error","无输出")
            return {"result":{"content":[{"text":f"[workspace] {'成功' if r.get('success') else '失败'}\n{t[:3000]}"}]}}
        sr=await ex.execute_python(code,skip_module_check=True)
        o=sr.stdout or sr.stderr or sr.error_message or ""
        return {"result":{"content":[{"text":f"[沙盒] {sr.status.value}\n{o[:3000]}"}]}}
    if action=="run_shell":
        cmd=args.get("command","")
        if ws:
            from core.sandbox.enhanced_executor import get_enhanced_executor
            r=await get_enhanced_executor().execute_shell(ws,cmd,timeout=args.get("timeout",30))
            t=r.get("stdout","") or r.get("stderr","") or r.get("error","")
            return {"result":{"content":[{"text":f"[workspace] {'成功' if r.get('success') else '失败'}\n{t[:3000]}"}]}}
        sr=await ex.execute_shell(cmd)
        o=sr.stdout or sr.stderr or sr.error_message or ""
        return {"result":{"content":[{"text":f"[沙盒] {sr.status.value}\n{o[:3000]}"}]}}
    return {"result":{"content":[{"text":"execute_code 需要 action=run_python|run_shell"}]}}


async def _handle_workspace(args: Dict) -> Dict:
    from core.sandbox.workspace_manager import get_workspace_manager
    from core.sandbox.enhanced_executor import get_enhanced_executor
    wsm=get_workspace_manager(); ee=get_enhanced_executor(); action=args.get("action","")
    if action=="create":
        ws=wsm.create_workspace(name=args.get("name",""),metadata=args.get("metadata"))
        return {"result":{"content":[{"text":f"工作区已创建: {ws.id}"}]}}
    if action=="list":
        ws=wsm.list_workspaces()
        if not ws: return {"result":{"content":[{"text":"暂无活跃工作区"}]}}
        return {"result":{"content":[{"text":"\n".join(f"{w.id}  {w.name}  {w.state.value}" for w in ws)}]}}
    wid=args.get("workspace_id","")
    if action=="info":
        ws=wsm.get_workspace(wid)
        return {"result":{"content":[{"text":json.dumps(ws.to_dict(),ensure_ascii=False,indent=2) if ws else "不存在"}]}}
    if action=="tree":
        r=await ee.get_file_tree(wid)
        if r.get("success"):
            t=r.get("tree",[]); lines=[f"/ {r['root']}"]
            def _fmt(i,p=""):
                for idx,it in enumerate(i):
                    c="--- " if idx==len(i)-1 else "|-- "; nm=f"[{it['name']}]" if it["type"]=="dir" else it["name"]
                    lines.append(f"{p}{c}{nm}")
                    if it.get("children"): _fmt(it["children"],p+("    " if idx==len(i)-1 else "|   "))
            _fmt(t)
            return {"result":{"content":[{"text":"\n".join(lines)}]}}
    return {"result":{"content":[{"text":"workspace 需要 action=create|list|info|tree"}]}}


async def _handle_workspace_file(args: Dict) -> Dict:
    from core.sandbox.enhanced_executor import get_enhanced_executor
    ee=get_enhanced_executor(); action=args.get("action",""); wid=args.get("workspace_id",""); path=args.get("path","")
    if action=="read":
        r=await ee.read_file(wid,path)
        if r.get("success"): return {"result":{"content":[{"text":f"\n{r['content']}"}]}}
        if os.path.isfile(path): return {"result":{"content":[{"text":open(path,encoding="utf-8").read()}]}}
        return {"result":{"content":[{"text":"读取失败"}]}}
    if action=="write":
        c=args.get("content",""); r=await ee.write_file(wid,path,c)
        if r.get("success"): return {"result":{"content":[{"text":f"已写入 {path} ({r['size']} bytes)"}]}}
        if path and c: Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text(c,encoding="utf-8")
        return {"result":{"content":[{"text":f"已写入 {path}"}]}}
    if action=="export":
        r=await ee.export_file(wid,path,args.get("dest_path",""))
        return {"result":{"content":[{"text":f"已导出到 {r['dest']}" if r.get("success") else "导出失败"}]}}
    return {"result":{"content":[{"text":"workspace_file 需要 action=read|write|export"}]}}


async def _handle_manage_packages(args: Dict) -> Dict:
    from core.sandbox.dependency_manager import get_dependency_manager
    dm=get_dependency_manager(); action=args.get("action",""); wid=args.get("workspace_id","")
    if action=="install":
        pkg=args.get("packages"); mgr=args.get("manager","pip")
        if mgr=="npm": r=await dm.install_node(wid,pkg)
        elif pkg: r=await dm.install_python(wid,pkg)
        else: r=await dm.install_from_requirements(wid)
        msg="安装完成" if r.get("success") else "失败: %s" % r.get("error","")
        return {"result":{"content":[{"text":msg}]}}
    if action=="detect":
        r=dm.detect_dependencies(wid)
        msg="Python: %s\nNode: %s" % (r.get("python",[]), r.get("node",[]))
        return {"result":{"content":[{"text":msg}]}}
    if action=="list":
        r=await dm.list_installed(wid,manager=args.get("manager","pip"))
        if r.get("success"):
            p=r.get("packages",[])
            msg="已安装 (%s):\n" % r["manager"] + chr(10).join("%s==%s" % (x.get("name","?"),x.get("version","?")) for x in p[:30])
            return {"result":{"content":[{"text":msg}]}}
        return {"result":{"content":[{"text":"查询失败: %s" % r.get("error","")}]}}
    return {"result":{"content":[{"text":"manage_packages 需要 action=install|detect|list"}]}}


async def _handle_scaffold(args: Dict) -> Dict:
    from core.sandbox.project_scaffolder import get_project_scaffolder
    sc=get_project_scaffolder(); action=args.get("action",""); wid=args.get("workspace_id","")
    if action=="create":
        r=sc.scaffold(wid,args["template"],{"name":args.get("name",""),"description":args.get("description","")})
        t=r.get("message","") if r.get("success") else r.get("error","创建失败")
        if r.get("files"): t+="\n"+"\n".join(f"  - {f}" for f in r["files"])
        return {"result":{"content":[{"text":t}]}}
    if action=="list_templates":
        ts=sc.list_templates()
        return {"result":{"content":[{"text":"模板:\n"+"\n".join(f"  - {t['name']}: {t['description']}" for t in ts)}]}}
    return {"result":{"content":[{"text":"scaffold 需要 action=create|list_templates"}]}}


async def _handle_run_tests(args: Dict) -> Dict:
    from core.sandbox.enhanced_executor import get_enhanced_executor
    r=await get_enhanced_executor().run_tests(args.get("workspace_id",""),test_path=args.get("test_path"),timeout=args.get("timeout",120))
    t=f"通过:{r.get('tests_passed','?')} 失败:{r.get('tests_failed','?')} 错误:{r.get('tests_errors','?')}"
    if r.get("stdout"): t+="\n"+r["stdout"][:2000]
    return {"result":{"content":[{"text":t}]}}


_HANDLER_MAP: Dict[str, Callable] = {
    "execute_code": _handle_execute_code, "workspace": _handle_workspace,
    "workspace_file": _handle_workspace_file, "manage_packages": _handle_manage_packages,
    "scaffold": _handle_scaffold, "file": _handle_file,
    "run_tests": _handle_run_tests, "fetch_url": _handle_fetch_url,
}


# ═══════════════════════════════════════════════════════════════════
# 8 个合并沙箱工具定义（第 6 源）
# ═══════════════════════════════════════════════════════════════════

_SANDBOX_TOOL_DEFS = [
    ToolDefinition(name="execute_code", server=SERVER_BUILTIN, tags=["code","sandbox"],
        description="在沙盒中执行代码。action='run_python' 执行 Python；action='run_shell' 执行 Shell；传 workspace_id 可在工作区执行",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["run_python","run_shell"]},"code":{"type":"string"},"command":{"type":"string"},"workspace_id":{"type":"string"},"timeout":{"type":"integer","description":"默认30"}},"required":["action"]},
        handler=_handle_execute_code),
    ToolDefinition(name="workspace", server=SERVER_BUILTIN, tags=["workspace","sandbox"],
        description="管理工作区生命周期。action='create'/'list'/'info'/'tree'",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["create","list","info","tree"]},"name":{"type":"string"},"workspace_id":{"type":"string"}},"required":["action"]},
        handler=_handle_workspace),
    ToolDefinition(name="workspace_file", server=SERVER_BUILTIN, tags=["workspace","file"],
        description="工作区文件操作。action='read'/'write'/'export'",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["read","write","export"]},"workspace_id":{"type":"string"},"path":{"type":"string"},"content":{"type":"string"},"dest_path":{"type":"string"}},"required":["action","path"]},
        handler=_handle_workspace_file),
    ToolDefinition(name="file", server=SERVER_BUILTIN, tags=["file","direct"],
        description="直接读写文件（不依赖 workspace）。action='read'/'write'，支持绝对路径",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["read","write"]},"path":{"type":"string"},"content":{"type":"string"}},"required":["action","path"]},
        handler=_handle_file),
    ToolDefinition(name="manage_packages", server=SERVER_BUILTIN, tags=["package","pip","npm"],
        description="依赖管理。action='install'/'detect'/'list'，支持 pip/npm",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["install","detect","list"]},"workspace_id":{"type":"string"},"packages":{"type":"array","items":{"type":"string"}},"manager":{"type":"string","enum":["pip","npm"]}},"required":["action"]},
        handler=_handle_manage_packages),
    ToolDefinition(name="scaffold", server=SERVER_BUILTIN, tags=["scaffold","project"],
        description="项目脚手架。action='create'/'list_templates'",
        parameters={"type":"object","properties":{"action":{"type":"string","enum":["create","list_templates"]},"workspace_id":{"type":"string"},"template":{"type":"string"},"name":{"type":"string"}},"required":["action"]},
        handler=_handle_scaffold),
    ToolDefinition(name="run_tests", server=SERVER_BUILTIN, tags=["test","sandbox"],
        description="在工作区内运行测试",
        parameters={"type":"object","properties":{"workspace_id":{"type":"string"},"test_path":{"type":"string"},"timeout":{"type":"integer","description":"默认120"}}},
        handler=_handle_run_tests),
    ToolDefinition(name="fetch_url", server=SERVER_BUILTIN, tags=["web","http","fetch"],
        description="获取网页/API数据（HTTP GET），自动提取页面 JSON（支持 <!--s-data-->、__NEXT_DATA__、__INITIAL_STATE__），数据保存到 /tmp/ 供 execute_code 读取",
        parameters={"type":"object","properties":{"url":{"type":"string"},"max_length":{"type":"integer","description":"默认80000"}},"required":["url"]},
        handler=_handle_fetch_url),
]


def _safe(raw: str) -> str:
    """工具名称安全化"""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)


class ToolRegistry:
    """统一工具注册表 — 六路来源 + handler 绑定"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False

    async def discover_all(self) -> List[ToolDefinition]:
        """发现并注册所有可用工具（六路来源）"""
        all_tools = []
        all_tools += await self._discover_awesome_mcp()
        all_tools += await self._discover_mcp_client()
        all_tools += await self._discover_skills()
        all_tools += await self._discover_api_routes()
        all_tools += await self._discover_guidance_skills()
        all_tools += await self._discover_builtin()
        self._initialized = True
        bc = self._count_by_server(SERVER_BUILTIN)
        logger.info(f"工具注册表初始化完成: {len(all_tools)} 个工具 "
                     f"(MCP+builtin={self._count_by_server('')+self._count_by_server(SERVER_MCP)+bc}, "
                     f"Skills={self._count_by_server(SERVER_SKILL)}, "
                     f"API={self._count_by_server(SERVER_API)}, "
                     f"Guidance={self._count_by_server(SERVER_GUIDANCE)})")
        return all_tools

    async def _discover_awesome_mcp(self) -> List[ToolDefinition]:
        tools = []
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            for td in await awesome_mcp_manager.get_all_tool_definitions():
                fn = td.get("function", {}); raw = fn.get("name", ""); name = _safe(raw)
                if name:
                    t = ToolDefinition(name=name, description=fn.get("description",""),
                        parameters=fn.get("parameters",{}), server=SERVER_MCP,
                        tool_name=td.get("_tool_name", raw), tags=["mcp"])
                    tools.append(t); self._tools[name] = t
        except Exception as e: logger.debug(f"awesome_mcp 发现失败: {e}")
        return tools

    async def _discover_mcp_client(self) -> List[ToolDefinition]:
        tools = []
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
                        await asyncio.wait_for(mcp_client.connect_server(name=srv,command="python3",
                            args=[os.path.join(mcp_dir,fn)],cwd=proot,env={"PYTHONPATH":proot}), timeout=5)
                        existing.add(srv)
                    except: pass
            # auto-discover .mcp.json
            mcj = os.path.join(proot, ".mcp.json")
            if os.path.exists(mcj):
                try:
                    with open(mcj) as f: cfg = json.load(f)
                    for srv,sc in cfg.get("mcpServers",{}).items():
                        if srv in existing: continue
                        try:
                            await asyncio.wait_for(mcp_client.connect_server(name=srv,command=sc["command"],
                                args=sc.get("args",[]),cwd=proot,env={"PYTHONPATH":proot}), timeout=5)
                            existing.add(srv)
                        except: pass
                except: pass
            # discover tools from all servers
            for srv in existing:
                try:
                    for tool in await asyncio.wait_for(mcp_client.list_tools(srv), timeout=3):
                        raw = tool.get("name",""); fn = _safe(f"{srv}_{raw}")
                        if not raw or fn in self._tools: continue
                        t = ToolDefinition(name=fn, description=tool.get("description",""),
                            parameters=tool.get("inputSchema",{}) or {}, server=srv, tool_name=raw, tags=["mcp"])
                        tools.append(t); self._tools[fn] = t
                except: pass
        except Exception as e: logger.debug(f"mcp_client 发现失败: {e}")
        return tools

    async def _discover_skills(self) -> List[ToolDefinition]:
        tools = []
        try:
            from core.engine.skill_dispatcher import get_skill_dispatcher
            sd = get_skill_dispatcher(); seen = set()
            for name, keywords, priority in sd.skill_configs:
                if name and name not in seen:
                    seen.add(name); kw = ", ".join(keywords[:5])
                    t = ToolDefinition(name=f"skill_{name}", description=f"本地技能: {name} (关键词: {kw})",
                        parameters={}, server=SERVER_SKILL, tool_name=name, tags=["skill"])
                    tools.append(t); self._tools[t.name] = t
            for name, cfg in sd._dynamic_registry.items():
                if name and name not in seen:
                    seen.add(name); desc = cfg.get("description","") or f"本地技能: {name}"
                    kw = cfg.get("keywords",[])
                    t = ToolDefinition(name=f"skill_{name}", description=desc+(f" (关键词: {', '.join(kw[:5])})" if kw else ""),
                        parameters={}, server=SERVER_SKILL, tool_name=name, tags=["skill"])
                    tools.append(t); self._tools[t.name] = t
        except Exception as e: logger.debug(f"技能发现失败: {e}")
        return tools

    async def _discover_api_routes(self) -> List[ToolDefinition]:
        tools = []
        try:
            from pathlib import Path as _P
            api_dir = _P(__file__).parent.parent.parent.parent / "plugin" / "api"
            if not api_dir.exists(): return tools
            for f in sorted(api_dir.glob("*.py")):
                if f.name.startswith("_"): continue
                mn = f.stem; desc = f"API 路由: {mn}"
                try:
                    import importlib; mod = importlib.import_module(f"plugin.api.{mn}")
                    if hasattr(mod, "__doc__") and mod.__doc__: desc = mod.__doc__.strip().split("\n")[0][:100]
                except: pass
                t = ToolDefinition(name=f"api_{mn}", description=desc,
                    parameters={"type":"object","properties":{"endpoint":{"type":"string","description":f"端点路径 (/{mn}/action)"},"method":{"type":"string","enum":["GET","POST"]},"params":{"type":"object"}}},
                    server=SERVER_API, tool_name=mn, tags=["api"])
                tools.append(t); self._tools[t.name] = t
        except Exception as e: logger.debug(f"API 路由发现失败: {e}")
        return tools

    async def _discover_guidance_skills(self) -> List[ToolDefinition]:
        tools = []
        try:
            from core.skill_base import get_skill_registry, GuidanceSkill
            for skill in get_skill_registry().all():
                if not isinstance(skill, GuidanceSkill): continue
                t = ToolDefinition(name=f"guidance_{skill.name}", description=skill.description or f"指导型技能: {skill.name}",
                    parameters={"type":"object","properties":{"task":{"type":"string","description":"任务描述"}}},
                    server=SERVER_GUIDANCE, tool_name=skill.name, tags=["guidance"])
                tools.append(t); self._tools[t.name] = t
        except Exception as e: logger.debug(f"Guidance 发现失败: {e}")
        return tools

    async def _discover_builtin(self) -> List[ToolDefinition]:
        """Source 6: 8 个合并沙箱工具"""
        for sd in _SANDBOX_TOOL_DEFS:
            if sd.name not in self._tools:
                self._tools[sd.name] = sd
        return [sd for sd in _SANDBOX_TOOL_DEFS]

    # ── 查询 ───────────────────────────────────────────────────────────

    def get_handler_map(self) -> Dict[str, Callable]:
        """获取 {tool_name: handler} 映射 — 替代 if-elif 路由链"""
        result = dict(_HANDLER_MAP)
        for name, td in self._tools.items():
            if td.handler is not None and name not in result:
                result[name] = td.handler
        return result

    def get_handler(self, tool_name: str) -> Optional[Callable]:
        """获取工具的执行 handler"""
        h = _HANDLER_MAP.get(tool_name)
        if h: return h
        td = self._tools.get(tool_name)
        return td.handler if td else None

    def get_tools_for_task(self, task_description: str, max_tools: int = 25) -> List[ToolDefinition]:
        if not self._initialized:
            return list(self._tools.values())[:max_tools]
        desc = task_description.lower()
        scored = []
        keywords = []
        try:
            import jieba; keywords = list(jieba.cut(desc))
        except ImportError:
            keywords = [desc[i:i+2] for i in range(0, len(desc)-1, 2)]
            if not keywords: keywords = desc.split()
        for t in self._tools.values():
            score = 0.0; dl = t.description.lower(); nl = t.name.lower()
            for kw in keywords:
                kw = kw.strip().lower()
                if len(kw) > 1:
                    if kw in dl: score += 2.0
                    if kw in nl: score += 3.0
            for tag in t.tags:
                if tag.lower() in desc: score += 2.0
            # 内置工具提权
            if t.server == SERVER_BUILTIN: score += 1.0
            if t.server == SERVER_SKILL: score += 0.5
            if t.server == SERVER_MCP: score += 0.3
            scored.append((score, t))
        scored.sort(key=lambda x: -x[0])
        result = [t for s, t in scored if s > 0]
        core_names = {"file", "fetch_url", "execute_code", "workspace_file"}
        core_missing = [t for t in self._tools.values() if t.name in core_names and t not in result]
        if len(result) < 5:
            seen = {t.name for t in result}
            for t in self._tools.values():
                if t.name not in seen:
                    result.append(t)
                    if len(result) >= max_tools: break
        result.extend(core_missing)
        return result[:max_tools]

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def validate_arguments(self, tool_name: str, arguments: Dict) -> tuple:
        tool = self._tools.get(tool_name)
        if not tool: return False, f"工具 {tool_name} 未注册"
        params = tool.parameters
        if not params: return True, ""
        props = params.get("properties", {}); req = params.get("required", [])
        for f in req:
            if f not in arguments: return False, f"缺少必需参数 '{f}'"
        for k, v in list(arguments.items()):
            if k in props:
                pt = props[k].get("type", "")
                if pt == "string" and not isinstance(v, str): arguments[k] = str(v)
                elif pt in ("integer","number") and isinstance(v, str):
                    try: arguments[k] = int(v) if pt=="integer" else float(v)
                    except ValueError: return False, f"参数 '{k}' 不能从 '{v}' 转换"
        return True, ""

    def list_by_server(self, server: str) -> List[ToolDefinition]:
        return [t for t in self._tools.values() if t.server == server]

    def _count_by_server(self, server: str) -> int:
        return sum(1 for t in self._tools.values() if t.server == server)

    @property
    def count(self) -> int:
        return len(self._tools)


# 全局单例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
