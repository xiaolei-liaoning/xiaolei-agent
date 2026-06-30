"""V1ToolRegistry — V1 独立工具注册表（11 内置工具 + MCP 代理）

与 V2 ToolRegistry 的区别：
- 无 scoped registry
- 无 _written_file_registry / _file_read_cache
- MCP 工具名统一 mcp_ 前缀
"""
import asyncio
import glob as globmod
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)
SERVER_BUILTIN = "__builtin__"


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    server: str = ""
    tool_name: str = ""
    tags: List[str] = field(default_factory=list)
    handler: Optional[Callable] = None


_SANDBOX_TOOL_DEFS = [
    ToolDefinition(
        name="write_todos",
        server=SERVER_BUILTIN,
        tags=["task", "tracking"],
        description="【自动跟踪】任务进度由系统自动管理，无需手动调用此工具。",
        parameters={
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "任务描述"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"], "description": "任务状态"}
                        },
                        "required": ["content", "status"]
                    },
                    "description": "任务列表"
                }
            },
            "required": ["todos"]
        },
        handler=None,
    ),
    ToolDefinition(
        name="write_file",
        server=SERVER_BUILTIN,
        tags=["file", "write"],
        description="新建文件并写入完整内容。\n- 适用于创建脚本、HTML 游戏、报告等新文件\n- content 是文件的**完整**内容，不可截断或留占位符\n- ⚠️ 只需修改文件某几行 → 用 edit_file，不要全文重写",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径，如 ~/Desktop/game.html"},
                "content": {"type": "string", "description": "文件的完整内容（必填，不能为空，不能截断）"},
            },
            "required": ["path", "content"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="execute_python",
        server=SERVER_BUILTIN,
        tags=["code", "sandbox"],
        description="安全执行 Python 代码。\n- 适用于运行脚本、测试算法、pip 安装包、操作桌面文件\n- mode=sandbox（默认）：沙盒隔离，无法访问桌面/网络\n- mode=local：真实环境，可写 ~/Desktop，可访问网络\n- ⚠️ 需运行系统命令(ls/pwd/git) → 用 execute_shell\n- ⚠️ 抓取网页/API 数据 → 用 fetch_url（execute_python 不是爬虫工具）",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码字符串"},
                "mode": {
                    "type": "string",
                    "enum": ["sandbox", "local"],
                    "description": "sandbox=沙盒隔离(默认,安全) | local=本地(可写桌面文件,无安全隔离)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（默认30，最大60）",
                },
                "skip_module_check": {
                    "type": "boolean",
                    "description": "仅 sandbox 模式有效：是否跳过模块安全检查",
                },
            },
            "required": ["code"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="execute_shell",
        server=SERVER_BUILTIN,
        tags=["code", "shell"],
        description="执行 Shell 系统命令。\n- 适用于文件操作(ls/mkdir/cp)、包管理(pip/npm)、Git、curl 等\n- mode=sandbox（默认）：沙盒隔离\n- mode=local：用户真实终端执行\n- ⚠️ 需运行 Python 代码 → 用 execute_python",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell 命令字符串"},
                "mode": {
                    "type": "string",
                    "enum": ["sandbox", "local"],
                    "description": "sandbox=沙盒隔离(默认,安全) | local=本地(无安全隔离)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（默认30，最大60）",
                },
            },
            "required": ["command"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="git",
        server=SERVER_BUILTIN,
        tags=["git", "code"],
        description="Git 版本控制操作。\n- 支持：status / add / commit / log / diff / branch / pull\n- 在当前项目目录执行\n- 典型工作流：status → diff → add → commit",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "status",
                        "add",
                        "commit",
                        "log",
                        "diff",
                        "branch",
                        "pull",
                    ],
                    "description": "Git 操作类型",
                },
                "message": {"type": "string", "description": "commit 时的提交信息（仅 action=commit 时必填）"},
                "files": {
                    "type": "string",
                    "description": "add 时的文件路径，默认全部（.）",
                },
                "count": {
                    "type": "integer",
                    "description": "log 显示的提交数，默认5",
                },
            },
            "required": ["action"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="fetch_url",
        server=SERVER_BUILTIN,
        tags=["web", "fetch"],
        description="HTTP GET 获取网页或 API 数据。\n- 适用于抓取网页 HTML 内容、调用 REST API\n- URL 会自动升级 HTTP → HTTPS\n- 结果可能被截断（可设 max_length 控制）\n- ⚠️ 需要搜索信息 → 用 web_search",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL（自动升级 HTTP → HTTPS）"},
                "max_length": {"type": "integer", "description": "最大返回字符数，不设则返回全部"},
            },
            "required": ["url"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="web_search",
        server=SERVER_BUILTIN,
        tags=["web", "search"],
        description="联网搜索获取实时信息。\n- 适用于查资料、新闻、数据收集\n- 三种搜索类型：auto(默认,均衡)、fast(快速)、deep(深度搜索)\n- ⚠️ 需要抓取特定 URL 内容 → 用 fetch_url",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询（越具体结果越精准）"},
                "num_results": {"type": "integer", "description": "返回结果数量，默认8"},
                "type": {"type": "string", "enum": ["auto", "fast", "deep"], "description": "搜索类型：auto(默认,均衡) | fast(快速) | deep(深度搜索)"},
            },
            "required": ["query"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="read_file",
        server=SERVER_BUILTIN,
        tags=["file", "read"],
        description="读取文件内容或浏览目录结构。\n- 是了解文件内容和项目结构的起点\n- 支持分页读取：offset(起始行号,从1开始) / limit(行数限制)\n- 目录会列出所有条目（目录带 / 后缀）\n- 长行超过2000字符会被截断\n- 支持读取图片和 PDF（返回附件）",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录的绝对路径"},
                "offset": {"type": "integer", "description": "起始行号（从1开始，不设则从头读）"},
                "limit": {"type": "integer", "description": "读取行数上限（默认2000）"},
            },
            "required": ["path"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="edit_file",
        server=SERVER_BUILTIN,
        tags=["file", "edit", "write"],
        description="精确字符串替换，修改文件中特定内容。\n- 正确流程：先 read_file 确认 → old_string 提供足够上下文确保唯一匹配 → 替换为新内容\n- 适用于修复 bug、增删函数、修改样式等局部改动\n- 支持 replace_all 替换所有匹配项\n- ⚠️ 编辑前必须先 read_file 读取文件\n- ⚠️ 大范围改动 → 用 write_file 重写",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径"},
                "old_string": {"type": "string", "description": "要替换的原始文本（需提供足够上下文确保唯一匹配）"},
                "new_string": {"type": "string", "description": "替换后的新文本"},
                "replace_all": {"type": "boolean", "description": "是否替换所有匹配项（默认 false）"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="search_files",
        server=SERVER_BUILTIN,
        tags=["search", "file"],
        description="搜索文件。两种模式**二选一，不可同时使用**：\n- 模式① pattern：按文件名 glob 搜索（如 **/*.py、src/**）\n- 模式② content_pattern：按文件内容正则搜索（如 def foo）\n- ⚠️ open-ended 搜索需要多轮 glob + grep → 用 Task agent",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "【与 content_pattern 二选一】Glob 文件名模式，如 *.py、**/*.ts"},
                "content_pattern": {"type": "string", "description": "【与 pattern 二选一】文件内容正则搜索，如 def foo"},
                "path": {"type": "string", "description": "搜索目录，默认当前项目目录"},
                "include": {"type": "string", "description": "内容搜索时的文件过滤，如 *.py（仅 content_pattern 模式有效）"},
                "limit": {"type": "integer", "description": "结果数量上限，默认200"},
            },
        },
        handler=None,
    ),
    ToolDefinition(
        name="text_analyzer",
        server=SERVER_BUILTIN,
        tags=["text", "analysis"],
        description="深度文本分析（基于 LLM）。\n- 分析文本主题、关键信息、情感倾向\n- 生成摘要和要点提取\n- 适用于文章分析、报告解读、内容理解\n- ⚠️ 只需统计字数/关键词 → 用 MCP text-analyzer",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待分析的文本内容"},
            },
            "required": ["text"],
        },
        handler=None,
    ),
]

async def _handle_write_file(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    path = os.path.expanduser(args.get("path", ""))
    content = args.get("content", "")
    if not path and "content" not in args:
        return err("缺少 path 或 content 参数")
    try:
        dirpath = os.path.dirname(path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return ok(f"已写入 {len(content)} 字符到 {path}", path=path, from_handler=f"文件已保存到 {path}")
    except Exception as e:
        return err(f"写入失败: {e}")


async def _handle_read_file(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    path = os.path.expanduser(args.get("path", ""))
    if not path:
        return err("缺少 path 参数")
    try:
        if os.path.isdir(path):
            entries = sorted(os.listdir(path))
            return ok("\n".join(e + "/" if os.path.isdir(os.path.join(path, e)) else e for e in entries))
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        offset = args.get("offset", 1)
        limit = args.get("limit", 2000)
        page = lines[offset - 1 : offset - 1 + limit]
        result = "".join(page)
        if offset > 1 or len(page) < len(lines):
            result = f"(lines {offset}-{offset + len(page) - 1}/{len(lines)})\n{result}"
        return ok(result, path=path)
    except Exception as e:
        return err(f"读取失败: {e}")


async def _handle_edit_file(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    path = os.path.expanduser(args.get("path", ""))
    old = args.get("old_string", "")
    new = args.get("new_string", "")
    replace_all = args.get("replace_all", False)
    if not path or not old:
        return err("缺少 path 或 old_string 参数")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if replace_all:
            count = content.count(old)
            if count == 0:
                return err(f"未找到匹配: {old[:50]}")
            content = content.replace(old, new)
        else:
            idx = content.find(old)
            if idx == -1:
                return err(f"未找到匹配: {old[:50]}")
            content = content[:idx] + new + content[idx + len(old):]
            count = 1
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return ok(f"替换了 {count} 处", path=path, count=count)
    except Exception as e:
        return err(f"编辑失败: {e}")


async def _handle_search_files(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    pattern = args.get("pattern", "")
    content_pattern = args.get("content_pattern", "")
    search_path = args.get("path", ".")
    limit = args.get("limit", 200)
    include = args.get("include", "")
    if pattern:
        results = []
        for p in globmod.glob(os.path.expanduser(os.path.join(search_path, pattern)), recursive=True):
            if len(results) >= limit:
                break
            results.append(p)
        return ok("\n".join(results))
    elif content_pattern:
        try:
            grep_args = ["grep", "-rn", "-l"]
            if include:
                grep_args.extend(["--include", include])
            else:
                for ext in ("*.py", "*.js", "*.ts", "*.md", "*.json", "*.yaml", "*.yml"):
                    grep_args.extend(["--include", ext])
            grep_args.extend(["--", content_pattern, os.path.expanduser(search_path)])
            out = subprocess.check_output(
                grep_args, stderr=subprocess.DEVNULL, timeout=10, text=True
            )
            lines = out.strip().split("\n") if out.strip() else []
            return ok("\n".join(lines[:limit]))
        except subprocess.CalledProcessError:
            return ok("无匹配结果")
        except Exception as e:
            return err(f"搜索失败: {e}")
    return err("需要 pattern 或 content_pattern 参数")


async def _handle_execute_python(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    code = args.get("code", "")
    if not code:
        return err("缺少 code 参数")
    timeout = min(int(args.get("timeout", 30)), 60)
    mode = args.get("mode", "sandbox")  # V1-C2 fix: 真实读取 mode 参数

    if mode == "sandbox":
        # V1-C2 fix: sandbox 模式走真实 SandboxExecutor，做模块黑名单/写入拦截/资源限制
        try:
            from core.tools.sandbox_executor import SandboxExecutor, ResourceLimits
            limits = ResourceLimits(timeout=timeout)
            ex = SandboxExecutor()
            r = await ex.execute_python(
                code, limits=limits, skip_module_check=args.get("skip_module_check", False)
            )
            if r.status.value == "completed":
                out = r.stdout or ""
                if r.stderr:
                    out += f"\n--- stderr ---\n{r.stderr[-2000:]}"
                return ok(out[:5000] if out else "（无输出）")
            else:
                return err(f"沙盒执行失败: {r.error_message or r.stderr or '未知错误'}"[:3000])
        except Exception as e:
            return err(f"沙盒启动失败: {e}")

    # mode=local：真实 subprocess.run，无安全隔离
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(["python3", f.name], capture_output=True, text=True, timeout=timeout)
            output = result.stdout
            if result.stderr:
                output += f"\n--- stderr ---\n{result.stderr[-2000:]}"
            return ok(output[:5000] if output else "（无输出）")
        except subprocess.TimeoutExpired:
            return err(f"执行超时({timeout}s)")
        except Exception as e:
            return err(f"执行失败: {e}")
        finally:
            os.unlink(f.name)


async def _handle_execute_shell(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    command = args.get("command", "")
    if not command:
        return err("缺少 command 参数")
    timeout = min(int(args.get("timeout", 20)), 60)
    mode = args.get("mode", "sandbox")
    if mode == "sandbox":
        # V1-C3 fix: 用真实 ShellGuard 替代脆弱的前缀检查
        try:
            from core.multi_agent_v2.tools.shell_guard import get_shell_guard
            guard = get_shell_guard(sandbox_mode=True)
            scan_result = guard.scan(command)
            if not scan_result.safe:
                risk_desc = "; ".join(r.description for r in scan_result.risks) if scan_result.risks else "危险命令"
                return err(f"安全策略阻止: {risk_desc}\n命令: {command}")
        except ImportError:
            # ShellGuard 不可用时回退到前缀检查（兼容性）
            safe_prefixes = ("ls", "pwd", "echo", "cat ", "head ", "tail ", "wc ", "date", "whoami", "uname", "which ", "mkdir ", "cp ", "mv ", "rm ", "grep ", "find ", "chmod ", "sort ", "uniq ", "cut ")
            if not any(command.startswith(p) for p in safe_prefixes):
                return err(f"sandbox 模式仅允许安全命令: {command[:50]}")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        output = result.stdout
        if result.stderr:
            output += f"\n--- stderr ---\n{result.stderr[:500]}"
        return ok(output[:5000] or "（执行完成，无输出）", returncode=result.returncode)
    except subprocess.TimeoutExpired:
        return err(f"执行超时({timeout}s)")
    except Exception as e:
        return err(f"执行失败: {e}")


async def _handle_git(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    action = args.get("action", "")
    if not action:
        return err("缺少 action 参数")
    msg = args.get("message", "")
    repo = os.getcwd()
    cmds = {
        "status": ["git", "status"],
        "add": ["git", "add", args.get("files", ".")],
        "commit": ["git", "commit", "-m", msg] if msg else None,
        "log": ["git", "log", "--oneline", f"-{args.get('count', 5)}"],
        "diff": ["git", "diff", "--stat"],
        "branch": ["git", "branch", "-a"],
        "pull": ["git", "pull"],
    }
    if action not in cmds or cmds[action] is None:
        return err(f"未知操作或缺少参数: {action}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmds[action], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        o, e = await asyncio.wait_for(proc.communicate(), timeout=15)
        text = (o.decode() if o else "") or (e.decode() if e else "(无输出)")
        return ok(text[:2000], returncode=proc.returncode)
    except asyncio.TimeoutError:
        return err("执行超时(15s)")
    except Exception as e:
        return err(f"git 失败: {e}")


async def _handle_fetch_url(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    import aiohttp, ssl
    url = args.get("url", "")
    timeout = int(args.get("timeout", 10))
    max_length = int(args.get("max_length", 8000))
    if not url:
        return err("缺少 url 参数")
    if url.startswith("http://"):
        url = "https://" + url[7:]
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                body = await resp.text(encoding="utf-8", errors="replace")
    except (aiohttp.ClientConnectorError, ssl.SSLError):
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout), ssl=False) as resp:
                body = await resp.text(encoding="utf-8", errors="replace")
    from .v1_html_parser import html_to_text
    text = html_to_text(body, max_length=max_length)
    return ok(text, url=url, raw_length=len(body))


async def _handle_search(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    from .v1_html_parser import html_to_text, extract_search_results
    import aiohttp
    query = args.get("query", "")
    if not query:
        return err("缺少 query 参数")
    num_results = min(int(args.get("num_results", 8)), 20)
    from urllib.parse import quote
    url = f"https://www.baidu.com/s?wd={quote(query)}&rn={num_results}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                html = await resp.text(encoding="utf-8", errors="replace")
        results = extract_search_results(html, engine="baidu")
        if results:
            lines = [f"{i+1}. {r['title']}\n   {r['link']}\n   {r['snippet']}" for i, r in enumerate(results)]
            return ok("\n\n".join(lines), count=len(results))
        text = html_to_text(html)
        return ok(text)
    except Exception as e:
        return err(f"搜索失败: {e}")


async def _handle_text_analyzer(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    text = args.get("text", "")
    if not text:
        return err("缺少 text 参数")
    from core.engine.llm_backend import get_llm_router
    router = get_llm_router()
    if not router or not router.is_available():
        return ok(f"文本长度: {len(text)} 字符\n前200字: {text[:200]}")
    prompt = f"分析以下文本，输出 JSON：\n{{\"summary\":\"摘要\",\"key_points\":[\"要点1\",...],\"tone\":\"情感倾向\"}}\n\n文本：{text[:3000]}"
    try:
        resp = await router.simple_chat(prompt, temperature=0.3, max_tokens=800)
        return ok(resp or "分析完成")
    except Exception as e:
        return ok(f"分析异常，返回原文前500字:\n{text[:500]}")


async def _handle_write_todos(args: Dict) -> Dict:
    from .v1_tool_result import ok, err
    todos = args.get("todos", [])
    if not todos:
        return err("缺少 todos 参数")
    lines = []
    for t in todos:
        if isinstance(t, dict):
            content = t.get("content", str(t))
            status = t.get("status", "pending")
            prefix = "- [x]" if status == "completed" else "- [ ]"
            lines.append(f"{prefix} {content}")
        else:
            lines.append(f"- [ ] {t}")
    return ok("\n".join(lines), count=len(todos))


_HANDLER_MAP: Dict[str, Callable] = {
    "write_file": _handle_write_file,
    "read_file": _handle_read_file,
    "edit_file": _handle_edit_file,
    "search_files": _handle_search_files,
    "execute_python": _handle_execute_python,
    "execute_shell": _handle_execute_shell,
    "git": _handle_git,
    "fetch_url": _handle_fetch_url,
    "web_search": _handle_search,
    "text_analyzer": _handle_text_analyzer,
    "write_todos": _handle_write_todos,
}

for sd in _SANDBOX_TOOL_DEFS:
    if sd.name in _HANDLER_MAP:
        sd.handler = _HANDLER_MAP[sd.name]


class V1ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False
        self._mcp_explored = False
        self._mcp_adapter = None

    async def discover_all(self) -> List[ToolDefinition]:
        """发现内置工具 + MCP 工具"""
        if not self._initialized:
            for sd in _SANDBOX_TOOL_DEFS:
                if sd.name not in self._tools:
                    self._tools[sd.name] = sd
            self._initialized = True
        if not self._mcp_explored:
            try:
                from .v1_mcp_adapter import V1MCPAdapter
                self._mcp_adapter = V1MCPAdapter()
                mcp_defs = await self._mcp_adapter.get_all_tool_defs()
                for td_dict in mcp_defs:
                    td = ToolDefinition(**td_dict)
                    if td.name not in self._tools:
                        self._tools[td.name] = td
                self._mcp_explored = True
            except Exception as e:
                logger.warning(f"MCP 发现失败: {e}")
        return list(self._tools.values())

    def get_handler(self, name: str) -> Optional[Callable]:
        h = _HANDLER_MAP.get(name)
        if h:
            return h
        td = self._tools.get(name)
        if td and td.handler:
            return td.handler
        # MCP 工具
        if td and td.server and td.tool_name and td.server not in ("", SERVER_BUILTIN):
            if self._mcp_adapter is None:
                return None
            srv, tname = td.server, td.tool_name
            async def _mcp_handler(args: dict) -> str:
                result = await self._mcp_adapter.call_tool(srv, tname, args)
                return result
            return _mcp_handler
        return None

    def validate_arguments(self, name: str, args: Dict) -> tuple:
        t = self._tools.get(name)
        if not t:
            return False, f"未知工具 '{name}'"
        p = t.parameters
        if not p:
            return True, ""
        props = p.get("properties", {})
        req = p.get("required", [])
        errors = []
        for f in req:
            if f not in args or args[f] is None or args[f] == "":
                field_schema = props.get(f, {})
                desc = field_schema.get("description", "")
                detail = f"缺少必需参数 '{f}' (类型: {field_schema.get('type', 'any')})"
                if desc:
                    detail += f" — {desc[:100]}"
                errors.append(detail)
        for k, v in list(args.items()):
            if k in props:
                pt = props[k].get("type", "")
                if pt == "string" and not isinstance(v, str):
                    args[k] = str(v)
                elif pt in ("integer", "number") and isinstance(v, str):
                    try:
                        args[k] = int(v) if pt == "integer" else float(v)
                    except ValueError:
                        errors.append(f"参数 '{k}' 无法从 '{v}' 转换为 {pt}")
        if errors:
            detail_lines = [f"参数校验失败 - 工具 '{name}':"]
            detail_lines += [f"  {e}" for e in errors]
            detail_lines += ["", "可用参数:"]
            for pn, ps in props.items():
                preq = "必填" if pn in req else "可选"
                pdesc = ps.get("description", "")
                detail_lines.append(f"  • {pn} ({ps.get('type','any')}, {preq}){' — ' + pdesc[:120] if pdesc else ''}")
            return False, "\n".join(detail_lines)
        return True, ""

    async def get_tools_for_task(self, task: str = "", max_tools=20, allowed=None, disallowed=None, tool_preference=None) -> List[ToolDefinition]:
        if not self._initialized:
            return list(self._tools.values())[:max_tools]
        all_tools = list(self._tools.values())
        if allowed is not None:
            allowed_set = set(allowed)
            all_tools = [t for t in all_tools if t.name in allowed_set or t.server not in (SERVER_BUILTIN, "")]
        if disallowed is not None:
            disallowed_set = set(disallowed)
            all_tools = [t for t in all_tools if t.name not in disallowed_set]
        if tool_preference:
            preferred = [t for t in all_tools if t.server in tool_preference]
            others = [t for t in all_tools if t.server not in tool_preference]
            all_tools = preferred + others
        return all_tools[:max_tools]
