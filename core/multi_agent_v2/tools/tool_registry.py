"""ToolRegistry — 工具注册表（含 12 个内置 handler）

内置工具：
- fetch_url:      HTTP GET 获取网页/API数据
- file:           直接读写文件
- search:         联网搜索（多引擎并发）
- execute_python: 沙盒执行 Python 代码
- execute_shell:  沙盒执行 Shell 命令
- rag_search:     RAG 增强搜索（向量库 + 知识提取）
- skill_execute:  执行注册的技能
- kepa_reflect:   KEPA 反思循环（知识→执行→感知→调整）
- ask_clarification: 反问澄清
- self_reflect:   自动复盘反思
- call_api:       通用 HTTP 客户端（GET/POST/PUT/DELETE）

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
# 内置 Handlers
# ═══════════════════════════════════════════════════════════════════

async def _handle_fetch_url(args: Dict) -> Dict:
    """HTTP GET 获取网页/API数据"""
    url = args.get("url", ""); ml = args.get("max_length", 80000)
    if not url: return {"result": {"content": [{"text": "需要 url 参数"}]}}
    import asyncio, ssl, urllib.request
    from urllib.parse import urlparse, urlunparse, quote
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
    je = None
    for p in [r'<!--s-data:(.*?)-->', r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
              r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>']:
        m = re.search(p, text, re.DOTALL)
        if m: je = m.group(1).strip(); break
    if not je:
        m = re.search(r'[\{\[]', text)
        if m: je = text[m.start():]
    clean = je or text
    stripped = clean.strip()
    if not je and (stripped.startswith("<") or "margin-top" in stripped[:500]):
        return {"result": {"content": [{"text": "网页是动态HTML，无法直接提取数据。请用 execute_python 执行 Python 通过 requests + BeautifulSoup/正则解析来抓取数据。"}]}}
    fp = f"/tmp/agent_fetch_{int(time.time())}.json"
    Path(fp).write_text(clean, encoding="utf-8")
    msg = "状态码:%s 原始:%d字符\n📁%s\n%s" % (resp.status, len(text), fp, clean[:300])
    return {"result": {"content": [{"text": msg}]}}


async def _handle_file(args: Dict) -> Dict:
    """读写文件"""
    action=args.get("action",""); path=args.get("path","")
    if not path: return {"result":{"content":[{"text":"需要 path 参数"}]}}
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
    """联网搜索 — 并发尝试多个搜索引擎"""
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
            pass
        return ""

    urls = [
        f"https://cn.bing.com/search?q={encoded}&count=10",
        f"https://www.google.com/search?q={encoded}&hl=zh-CN&num=10",
        f"https://www.baidu.com/s?wd={encoded}&rn=10",
    ]
    tasks = [asyncio.create_task(_try_one(u)) for u in urls]
    done, pending = await asyncio.wait(tasks, timeout=10.0, return_when=asyncio.FIRST_COMPLETED)
    for p in pending: p.cancel()
    for task in done:
        text = task.result()
        if text:
            return {"result": {"content": [{"text": text}]}}
    for task in tasks:
        if task not in done:
            try:
                text = await asyncio.wait_for(task, timeout=5.0)
                if text:
                    return {"result": {"content": [{"text": text}]}}
            except BaseException:
                pass
    return {"result": {"content": [{"text": "搜索暂时无法获取结果，请用 fetch_url 直接访问目标网址"}]}}


async def _handle_execute_python(args: Dict) -> Dict:
    """沙盒执行 Python 代码 — 安全隔离，支持网络/文件操作"""
    code = args.get("code", "")
    if not code: return {"result": {"content": [{"text": "缺少 code 参数"}]}}
    timeout = args.get("timeout", 30)
    skip_check = args.get("skip_module_check", False)
    try:
        from core.tools.sandbox_executor import SandboxExecutor, ResourceLimits
        limits = ResourceLimits(timeout=min(int(timeout), 60), max_output_size=10000)
        ex = SandboxExecutor()
        sr = await ex.execute_python(code, limits=limits, skip_module_check=skip_check)
        if sr.status.value == "success":
            out = sr.stdout or "(无输出)"
            return {"result": {"content": [{"text": f"[沙盒] ✅ 执行成功\n{out[:8000]}"}]}}
        return {"result": {"content": [{"text": f"[沙盒] ❌ {sr.error_message or sr.stderr or '执行失败'}"[:5000]}]}}
    except ImportError:
        # 降级：本地 exec()
        try:
            import io, contextlib, textwrap
            dedented = textwrap.dedent(code)
            f = io.StringIO(); err = io.StringIO()
            with contextlib.redirect_stdout(f), contextlib.redirect_stderr(err):
                exec(dedented)
            out = f.getvalue() or err.getvalue() or "(无输出)"
            return {"result": {"content": [{"text": f"[本地] ✅ 执行成功\n{out[:5000]}"}]}}
        except Exception as e:
            return {"result": {"content": [{"text": f"[本地] ❌ {type(e).__name__}: {e}"[:3000]}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"[沙盒] ❌ {type(e).__name__}: {e}"[:3000]}]}}


async def _handle_execute_shell(args: Dict) -> Dict:
    """沙盒执行 Shell 命令 — 安全限制，禁止危险命令"""
    command = args.get("command", "")
    if not command: return {"result": {"content": [{"text": "缺少 command 参数"}]}}
    timeout = args.get("timeout", 30)
    try:
        from core.tools.sandbox_executor import SandboxExecutor, ResourceLimits
        limits = ResourceLimits(timeout=min(int(timeout), 60), max_output_size=10000)
        ex = SandboxExecutor()
        sr = await ex.execute_shell(command, limits=limits)
        if sr.status.value == "success":
            out = sr.stdout or "(无输出)"
            return {"result": {"content": [{"text": f"[沙盒] ✅ 执行成功\n{out[:8000]}"}]}}
        return {"result": {"content": [{"text": f"[沙盒] ❌ {sr.error_message or sr.stderr or '执行失败'}"[:5000]}]}}
    except ImportError:
        import asyncio
        try:
            proc = await asyncio.create_subprocess_shell(command, stdout=-1, stderr=-1)
            o, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {"result": {"content": [{"text": f"[本地] 返回码 {proc.returncode}\n{o.decode()[:3000]}"}]}}
        except asyncio.TimeoutError:
            return {"result": {"content": [{"text": "[本地] ❌ 执行超时"}]}}
        except Exception as e:
            return {"result": {"content": [{"text": f"[本地] ❌ {e}"[:2000]}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"[沙盒] ❌ {type(e).__name__}: {e}"[:3000]}]}}


async def _handle_rag_search(args: Dict) -> Dict:
    """RAG 增强搜索 — 向量库 + 知识提取 + 联网搜索"""
    query = args.get("query", "")
    if not query: return {"result": {"content": [{"text": "需要 query 参数"}]}}
    max_results = int(args.get("max_results", 5))
    learn = args.get("learn", True)
    try:
        from core.search.rag_search_engine import RAGSearchEngine
        engine = RAGSearchEngine()
        result = await engine.search_and_learn(
            query=query, user_id=1, learn=learn,
            max_results=max_results, enhance=True,
        )
        text_parts = [f"查询: {result.get('query', query)}"]
        if result.get("from_cache"):
            text_parts.append("📦 来自缓存")
        items = result.get("results", [])
        if items:
            for i, r in enumerate(items):
                content = r.get("content", r.get("text", ""))[:500]
                source = r.get("source", r.get("url", ""))
                text_parts.append(f"\n【{i+1}】{content[:200]}")
                if source:
                    text_parts.append(f"   📎 {source}")
        else:
            text_parts.append("未找到相关结果")
        if result.get("knowledge_extracted"):
            text_parts.append(f"\n🧠 知识提取: {str(result['knowledge_extracted'])[:200]}")
        return {"result": {"content": [{"text": "\n".join(text_parts)[:5000]}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"RAG 搜索失败: {e}"}]}}


async def _handle_skill_execute(args: Dict) -> Dict:
    """执行已注册的技能 — 通过 SkillDispatcher 意图匹配"""
    skill_name = args.get("skill_name", "")
    params = args.get("params", {})
    if not skill_name:
        return {"result": {"content": [{"text": "需要 skill_name 参数"}]}}
    try:
        from core.engine.skill_dispatcher import get_skill_dispatcher
        dispatcher = get_skill_dispatcher()
        # 先试 SkillRegistry 直接执行
        try:
            from core.skill_base import get_skill_registry
            import inspect
            registry = get_skill_registry()
            skill = registry.get(skill_name)
            if skill:
                ctx = {"user_id": 1}
                if inspect.iscoroutinefunction(skill.execute):
                    result = await skill.execute(params, context=ctx)
                else:
                    result = skill.execute(params, context=ctx)
                return {"result": {"content": [{"text": f"[技能] ✅ {skill_name} 执行成功\n{str(result)[:3000]}"}]}}
        except Exception:
            pass
        # 兜底：通过 dispatcher 匹配
        matched = dispatcher.match_skill(skill_name)
        if matched:
            result = dispatcher.dispatch(skill_name)
            return {"result": {"content": [{"text": f"[技能] ✅ 匹配到 {matched}\n{str(result)[:3000]}"}]}}
        return {"result": {"content": [{"text": f"[技能] ❌ 未找到技能: {skill_name}"}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"技能执行失败: {e}"}]}}


async def _handle_kepa_reflect(args: Dict) -> Dict:
    """KEPA 反思循环 — 知识→执行→感知→调整"""
    action = args.get("action", "full")
    context = args.get("context", "")
    if action not in ("think", "act", "reflect", "full"):
        return {"result": {"content": [{"text": "action 必须是 think|act|reflect|full"}]}}
    try:
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        results = []

        if action in ("think", "full"):
            prompt = f"请分析以下上下文，给出深入洞察和执行建议：\n\n{context}\n\n输出格式：\n洞察: ...\n建议: ..."
            resp = await router.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.5, max_tokens=800,
            )
            resp_text = resp if isinstance(resp, str) else str(resp)
            results.append(f"【思考】{resp_text[:500]}")

        if action in ("act", "full") and action != "think":
            results.append("【行动】KEPA 行动阶段：基于洞察生成执行方案。请使用其他工具（execute_python/fetch_url等）执行具体操作。")

        if action in ("reflect", "full"):
            try:
                from core.auto_reviewer import get_auto_reviewer
                reviewer = get_auto_reviewer()
                review = await reviewer.review(
                    task_id="kepa_reflect", task_description=context,
                    execution_logs=context, task_result=context,
                )
                if review:
                    results.append(f"【感知】做得好的: {review.what_went_well[:200]}")
                    if review.pitfalls:
                        results.append(f"【调整】改进: {review.pitfalls[:200]}")
            except Exception:
                results.append("【感知】复盘不可用，跳过此阶段")

        text = "\n\n".join(results) if results else "KEPA 循环完成，无输出"
        return {"result": {"content": [{"text": text[:5000]}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"KEPA 反思失败: {e}"}]}}


async def _handle_ask_clarification(args: Dict) -> Dict:
    """反问澄清 — 当用户输入模糊或执行失败时生成追问"""
    message = args.get("message", "")
    error_context = args.get("error_context", "")
    if not message:
        return {"result": {"content": [{"text": "需要 message 参数"}]}}
    try:
        from core.services.clarification_service import get_clarification_service
        service = get_clarification_service()
        questions = service.generate_questions(
            message=message,
            error_context=error_context or None,
            check_permission=True,
        )
        if questions:
            lines = ["需要进一步确认："]
            for i, q in enumerate(questions):
                lines.append(f"\n{i+1}. {q.question}")
                if q.options:
                    opts = " / ".join(o.label for o in q.options)
                    lines.append(f"   选项: {opts}")
            return {"result": {"content": [{"text": "\n".join(lines)}]}}
        return {"result": {"content": [{"text": "无需反问，信息已足够清晰"}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"反问生成失败: {e}"}]}}


async def _handle_self_reflect(args: Dict) -> Dict:
    """自动复盘反思 — 分析执行过程，生成改进建议"""
    task_desc = args.get("task_description", "")
    exec_logs = args.get("execution_logs", "")
    task_result = args.get("task_result", "")
    if not task_desc:
        return {"result": {"content": [{"text": "需要 task_description 参数"}]}}
    try:
        from core.auto_reviewer import get_auto_reviewer
        reviewer = get_auto_reviewer()
        review = await reviewer.review(
            task_id=f"reflect_{int(time.time())}",
            task_description=task_desc,
            execution_logs=exec_logs or "(无执行日志)",
            task_result=task_result or None,
        )
        lines = [f"📋 复盘报告"]
        if review.what_went_well:
            lines.append(f"\n✅ 做得好的:\n{review.what_went_well[:500]}")
        if review.pitfalls:
            lines.append(f"\n⚠️ 踩坑点:\n{review.pitfalls[:500]}")
        if review.improvement:
            lines.append(f"\n💡 改进建议:\n{review.improvement[:500]}")
        if review.is_worth_saving:
            lines.append(f"\n📌 值得沉淀为技能{' (' + review.skill_name + ')' if review.skill_name else ''}")
        return {"result": {"content": [{"text": "\n".join(lines)[:5000]}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"复盘失败: {e}"}]}}


async def _handle_call_api(args: Dict) -> Dict:
    """通用 HTTP 客户端 — 支持 GET/POST/PUT/DELETE"""
    method = args.get("method", "GET").upper()
    url = args.get("url", "")
    if not url:
        return {"result": {"content": [{"text": "需要 url 参数"}]}}
    if method not in ("GET", "POST", "PUT", "DELETE"):
        return {"result": {"content": [{"text": f"不支持的 HTTP 方法: {method}"}]}}
    headers = args.get("headers", {})
    data = args.get("data", None)
    json_data = args.get("json_data", None)
    timeout = int(args.get("timeout", 15))
    try:
        from tools.http_client import HTTPClient
        client = HTTPClient(timeout=min(timeout, 60), max_retries=2)
        if method == "GET":
            resp = client.get(url, headers=headers)
        elif method == "POST":
            resp = client.post(url, data=data, json=json_data, headers=headers)
        elif method == "PUT":
            resp = client.put(url, data=data or json_data, headers=headers)
        elif method == "DELETE":
            resp = client.delete(url, headers=headers)
        else:
            resp = {"success": False, "error": f"不支持: {method}"}
        success = resp.get("success", False)
        status = resp.get("status", resp.get("status_code", "?"))
        body = resp.get("data", resp.get("content", resp.get("response", "")))
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, indent=2)[:5000]
        else:
            body = str(body)[:5000]
        if success:
            return {"result": {"content": [{"text": f"[API] ✅ {status}\n{body}"}]}}
        error = resp.get("error", resp.get("message", "请求失败"))
        return {"result": {"content": [{"text": f"[API] ❌ {status}: {error}"[:3000]}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"[API] ❌ {type(e).__name__}: {e}"[:3000]}]}}


# ═══════════════════════════════════════════════════════════════════
# Handler 映射 & 工具定义
# ═══════════════════════════════════════════════════════════════════

_HANDLER_MAP: Dict[str, Callable] = {
    "fetch_url": _handle_fetch_url,
    "file": _handle_file,
    "search": _handle_search,
    "execute_python": _handle_execute_python,
    "execute_shell": _handle_execute_shell,
    "rag_search": _handle_rag_search,
    "skill_execute": _handle_skill_execute,
    "kepa_reflect": _handle_kepa_reflect,
    "ask_clarification": _handle_ask_clarification,
    "self_reflect": _handle_self_reflect,
    "call_api": _handle_call_api,
}

_SANDBOX_TOOL_DEFS = [
    ToolDefinition(name="execute_python", server=SERVER_BUILTIN, tags=["code", "sandbox"],
        description="沙盒执行 Python 代码。可运行任何 Python 代码（网络/文件/数据分析/爬虫等）。安全隔离执行环境。",
        parameters={"type":"object","properties":{
            "code":{"type":"string","description":"Python 代码"},
            "timeout":{"type":"integer","description":"超时秒数（默认30，最大60）"},
            "skip_module_check":{"type":"boolean","description":"是否跳过模块安全检查"},
        },"required":["code"]},
        handler=_handle_execute_python),
    ToolDefinition(name="execute_shell", server=SERVER_BUILTIN, tags=["code", "shell"],
        description="沙盒执行 Shell 命令。安全限制环境，禁止危险命令（rm -rf / 等）。",
        parameters={"type":"object","properties":{
            "command":{"type":"string","description":"Shell 命令"},
            "timeout":{"type":"integer","description":"超时秒数（默认30，最大60）"},
        },"required":["command"]},
        handler=_handle_execute_shell),
    ToolDefinition(name="search", server=SERVER_BUILTIN, tags=["web", "search"],
        description="联网搜索查询信息（百度/谷歌/Bing 并发搜索）。当用户要求搜索、查找、查询时使用。",
        parameters={"type":"object","properties":{"query":{"type":"string","description":"搜索关键词"}},"required":["query"]},
        handler=_handle_search),
    ToolDefinition(name="rag_search", server=SERVER_BUILTIN, tags=["rag", "search", "knowledge"],
        description="RAG 增强搜索 — 向量库检索 + 知识提取 + 联网搜索。比 search 更深度，适合研究型问题。",
        parameters={"type":"object","properties":{
            "query":{"type":"string","description":"搜索查询"},
            "max_results":{"type":"integer","description":"最大结果数（默认5）"},
            "learn":{"type":"boolean","description":"是否提取知识到向量库"},
        },"required":["query"]},
        handler=_handle_rag_search),
    ToolDefinition(name="skill_execute", server=SERVER_BUILTIN, tags=["skill"],
        description="执行已注册的技能。技能是预定义的功能模块（天气/翻译/自动化等）。",
        parameters={"type":"object","properties":{
            "skill_name":{"type":"string","description":"技能名称"},
            "params":{"type":"object","description":"技能参数"},
        },"required":["skill_name"]},
        handler=_handle_skill_execute),
    ToolDefinition(name="kepa_reflect", server=SERVER_BUILTIN, tags=["kepa", "reflect"],
        description="KEPA 反思循环：Knowledge→Execution→Perception→Adjustment。对当前状态进行深度思考和自我调整。action=think(仅思考)|act(仅行动)|reflect(仅反思)|full(完整循环)",
        parameters={"type":"object","properties":{
            "action":{"type":"string","enum":["think","act","reflect","full"],"description":"反思阶段"},
            "context":{"type":"string","description":"需要反思的上下文信息"},
        },"required":["action"]},
        handler=_handle_kepa_reflect),
    ToolDefinition(name="ask_clarification", server=SERVER_BUILTIN, tags=["clarification"],
        description="反问澄清 — 当用户输入模糊或执行失败时，生成追问来明确需求。",
        parameters={"type":"object","properties":{
            "message":{"type":"string","description":"需要澄清的消息"},
            "error_context":{"type":"string","description":"错误上下文（可选）"},
        },"required":["message"]},
        handler=_handle_ask_clarification),
    ToolDefinition(name="self_reflect", server=SERVER_BUILTIN, tags=["reflect"],
        description="自动复盘反思 — 分析执行过程，生成改进建议和教训总结。适合在任务完成后调用。",
        parameters={"type":"object","properties":{
            "task_description":{"type":"string","description":"任务描述"},
            "execution_logs":{"type":"string","description":"执行日志"},
            "task_result":{"type":"string","description":"执行结果（可选）"},
        },"required":["task_description","execution_logs"]},
        handler=_handle_self_reflect),
    ToolDefinition(name="call_api", server=SERVER_BUILTIN, tags=["api", "http"],
        description="通用 HTTP 客户端 — 支持 GET/POST/PUT/DELETE 请求。用于调用外部 REST API 接口。",
        parameters={"type":"object","properties":{
            "method":{"type":"string","enum":["GET","POST","PUT","DELETE"],"description":"HTTP 方法"},
            "url":{"type":"string","description":"请求 URL"},
            "headers":{"type":"object","description":"请求头"},
            "data":{"type":"object","description":"表单数据"},
            "json_data":{"type":"object","description":"JSON 数据"},
            "timeout":{"type":"integer","description":"超时秒数（默认15，最大60）"},
        },"required":["url"]},
        handler=_handle_call_api),
    ToolDefinition(name="fetch_url", server=SERVER_BUILTIN, tags=["web", "fetch"],
        description="HTTP GET 获取网页/API数据。用于抓取网页内容、调用简单 API 接口。",
        parameters={"type":"object","properties":{
            "url":{"type":"string","description":"目标URL"},
            "max_length":{"type":"integer","description":"最大返回字符数"},
        },"required":["url"]},
        handler=_handle_fetch_url),
    ToolDefinition(name="file", server=SERVER_BUILTIN, tags=["file", "storage"],
        description="直接读写文件。action=read 读取文件内容；action=write 写入文件内容。",
        parameters={"type":"object","properties":{
            "action":{"type":"string","enum":["read","write"]},
            "path":{"type":"string","description":"文件路径"},
            "content":{"type":"string","description":"写入内容（write时必填）"},
        },"required":["action","path"]},
        handler=_handle_file),
]


def _safe(raw: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', raw)


class ToolRegistry:
    """工具注册表 — 12 个内置工具 + 懒加载 MCP + 智能工具筛选"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False
        self._mcp_servers_discovered: Set[str] = set()

    async def ensure_mcp_tools_loaded(self) -> None:
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
                pass

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
        # Source 2: builtin tools
        for sd in _SANDBOX_TOOL_DEFS:
            if sd.name not in self._tools:
                self._tools[sd.name] = sd
                all_tools.append(sd)
        self._initialized = True
        # Source 3: mcp_client background
        asyncio.ensure_future(self._connect_mcp_servers())
        return all_tools

    async def _connect_mcp_servers(self) -> None:
        """后台连接 MCP 服务器"""
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
        """按任务相关性排序的工具列表"""
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
        core = [t for t in self._tools.values() if t.name in ("file","fetch_url","search","execute_python","execute_shell")]
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

    def get_tools_by_tag(self, tag: str) -> List[ToolDefinition]:
        """按标签筛选工具"""
        return [t for t in self._tools.values() if tag in t.tags]

    def get_available_tools_summary(self) -> Dict[str, Any]:
        """返回工具统计摘要"""
        by_server = {}
        for t in self._tools.values():
            by_server.setdefault(t.server, []).append(t.name)
        mcp_count = sum(1 for s in by_server if s not in ("__builtin__","__mcp__",""))
        return {
            "total": len(self._tools),
            "builtin": len(by_server.get("__builtin__", [])),
            "mcp_awesome": len(by_server.get("__mcp__", [])),
            "mcp_connected": mcp_count,
            "by_tag": {
                "code": len(self.get_tools_by_tag("code")),
                "search": len(self.get_tools_by_tag("search")),
                "skill": len(self.get_tools_by_tag("skill")),
                "reflect": len(self.get_tools_by_tag("reflect")),
                "api": len(self.get_tools_by_tag("api")),
                "mcp": len(self.get_tools_by_tag("mcp")),
            },
        }

    def is_mcp_tool_available(self, name: str) -> bool:
        """检查 MCP 工具是否来自已连接的服务器"""
        t = self._tools.get(name)
        return bool(t and t.server not in ("__builtin__","__mcp__",""))

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
