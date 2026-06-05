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
# 内置 Handlers
# ═══════════════════════════════════════════════════════════════════

def _has_readable_content(html_text: str) -> bool:
    """判断 HTML 页面是否有可读的文本内容（不需要 JS 渲染也能用）

    搜索引擎结果页、普通文档页等包含大量可读文本，
    而纯 SPA 页面（如 React 应用）的原始 HTML 只有少量脚本标签和占位 div。
    区分两者，避免误将搜索引擎结果页标记为"动态HTML"。
    """
    # 提取所有标签内的文本
    import re
    text_content = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.DOTALL)
    text_content = re.sub(r'<style[^>]*>.*?</style>', '', text_content, flags=re.DOTALL)
    text_content = re.sub(r'<[^>]+>', ' ', text_content)
    text_content = re.sub(r'\s+', ' ', text_content).strip()

    # 可读文本量评估
    text_len = len(text_content)
    total_len = len(html_text)
    ratio = text_len / max(total_len, 1)

    # 条件：至少有足够可读文本（搜索引擎结果页虽JS多但仍有有用文本）
    # SPA 页面原始 HTML 通常文本极少（< 200 字符）
    # 搜索引擎结果页文本量较大（> 500 字符）但比例低（~2%）
    return text_len > 500 or (text_len > 200 and ratio > 0.05)


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
        # 兜底：找第一个 { 或 [ 尝试作为 JSON
        m = re.search(r'[\{\[]', text)
        if m:
            maybe_json = text[m.start():].strip()
            # 严格验证：必须是真正的 JSON（CSS 会以 { 后跟字母开头）
            is_real_json = False
            if maybe_json.startswith("{") and maybe_json.lstrip("{").strip().startswith('"'):
                # {"key": value} 格式 — 真 JSON
                is_real_json = True
            elif maybe_json.startswith("[") and maybe_json.lstrip("[").strip()[:1] in ('"', '{', '[', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 't', 'f', 'n'):
                # [...] 数组格式
                is_real_json = True
            if is_real_json:
                je = maybe_json
            else:
                je = None
    clean = je or text
    stripped = clean.strip()
    if not je and stripped.startswith("<") and not _has_readable_content(stripped):
        fp = f"/tmp/agent_fetch_{int(time.time())}.html"
        Path(fp).write_text(text, encoding="utf-8")
        return {"result": {"content": [{"text": f"网页是动态HTML (已保存到 {fp})。请用 execute_python 执行 Python 通过 requests + BeautifulSoup/正则解析来提取数据。"}]}}
    fp = f"/tmp/agent_fetch_{int(time.time())}.json"
    Path(fp).write_text(clean, encoding="utf-8")

    # 尝试解析 JSON 数据并生成可读摘要（尤其是热搜/榜单类数据）
    preview = clean[:300]
    try:
        parsed = json.loads(clean) if je else None
        if parsed:
            # 尝试提取热搜列表
            cards = parsed.get("data", {}).get("cards", [])
            hot_items = []
            for card in cards:
                if card.get("component") == "hotList":
                    for item in card.get("content", []):
                        word = item.get("word", item.get("query", ""))
                        hot_score = item.get("hotScore", item.get("heat", ""))
                        if word:
                            hot_items.append(f"  {word}" + (f" (热度:{hot_score})" if hot_score else ""))
            if hot_items:
                preview = f"获取到 {len(hot_items)} 条热搜/榜单数据：\n" + "\n".join(hot_items[:20])
                if len(hot_items) > 20:
                    preview += f"\n  ...共{len(hot_items)}条，完整数据见文件"
            # 通用 JSON 格式友好展示
            if not hot_items:
                text_repr = json.dumps(parsed, ensure_ascii=False, indent=2)[:2000]
                if len(text_repr) < 500:
                    preview = text_repr
                else:
                    preview = text_repr[:500] + f"\n...截断 ({len(text_repr)} 字符)，完整数据见文件"
    except (json.JSONDecodeError, AttributeError):
        pass

    msg = f"状态码:{resp.status} 原始:{len(text)}字符\n{preview}\n📁完整数据: {fp}"
    return {"result": {"content": [{"text": msg}]}}


async def _handle_file(args: Dict) -> Dict:
    """读写文件"""
    action=args.get("action",""); path=args.get("path","")
    if not path: return {"result":{"content":[{"text":"需要 path 参数"}]}}
    path = re.sub(r'%([^%]+)%', lambda m: os.environ.get(m.group(1), os.environ.get('HOME', '~')), path)
    # 中文路径映射：LLM 可能用"桌面上/xxx.txt"代替绝对路径
    desktop = os.path.expanduser("~/Desktop")
    if path.startswith("桌面上/"):
        path = desktop + path[3:]
    elif path.startswith("桌面/"):
        path = desktop + path[2:]
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
            result = await _handle_fetch_url({"url": url, "max_length": 80000})
            text = result.get("result", {}).get("content", [{}])[0].get("text", "")
            if not text or len(text) < 80:
                return ""
            if "请求失败" in text:
                return ""

            # 从 fetch_url 的结果中提取可读文本
            import re as _re
            # 尝试从保存的文件中提取纯文本
            file_path = None
            m = _re.search(r'📁完整数据:\s*(\S+)', text)
            if not m:
                m = _re.search(r'已保存到\s+(\S+)', text)
            if m:
                file_path = m.group(1)

            content_text = ""
            if file_path:
                import os as _os
                if _os.path.exists(file_path):
                    raw = open(file_path, encoding='utf-8').read()
                    # 提取纯文本
                    content_text = _re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=_re.DOTALL)
                    content_text = _re.sub(r'<style[^>]*>.*?</style>', '', content_text, flags=_re.DOTALL)
                    content_text = _re.sub(r'<[^>]+>', ' ', content_text)
                    content_text = _re.sub(r'\s+', ' ', content_text).strip()
                    # 去掉 URL 和纯数字噪声，保留有意义的文本
                    content_text = _re.sub(r'https?://\S+', '', content_text)

            if content_text and len(content_text) > 80:
                return f"搜索结果({url}):\n{content_text[:3000]}"
            elif content_text and len(content_text) > 5:
                return f"搜索结果({url}):\n{content_text[:1000]}"
            return ""
        except BaseException:
            pass
        return ""

    urls = [
        f"https://cn.bing.com/search?q={encoded}&count=10",
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
    # 所有并发搜索都为空时，等待0.5秒后重试Bing一次
    await asyncio.sleep(0.5)
    try:
        text = await asyncio.wait_for(
            _try_one(f"https://cn.bing.com/search?q={encoded}&count=10"),
            timeout=8.0,
        )
        if text:
            return {"result": {"content": [{"text": text}]}}
    except BaseException:
        pass
    return {"result": {"content": [{"text": "搜索暂时无法获取结果，请用 fetch_url 直接访问目标网址"}]}}


async def _handle_execute_python(args: Dict) -> Dict:
    """执行 Python 代码 — 通过 mode 参数指定执行模式"""
    code = args.get("code", "")
    if not code: return {"result": {"content": [{"text": "缺少 code 参数"}]}}
    mode = args.get("mode", "local")  # local(默认,可写桌面文件) | sandbox(隔离)
    timeout = int(args.get("timeout", 30))

    # sandbox 模式（失败时自动降级到 local）
    if mode == "sandbox":
        skip_check = args.get("skip_module_check", False)
        sandbox_err = ""
        try:
            from core.tools.sandbox_executor import SandboxExecutor, ResourceLimits
            limits = ResourceLimits(timeout=min(timeout, 60), max_output_size_kb=10000)
            ex = SandboxExecutor()
            sr = await ex.execute_python(code, limits=limits, skip_module_check=skip_check)
            if sr.status.value in ("completed", "success"):
                out = sr.stdout if sr.stdout else ("(无输出)" if sr.stderr else "")
                err = sr.stderr if sr.stderr else ""
                full = out[:8000] + ("\n" + err[:2000] if err else "")
                return {"result": {"content": [{"text": f"[沙盒] ✅ 执行成功\n{full}"}]}}
            sandbox_err = sr.error_message or sr.stderr or "执行失败"
        except Exception as e:
            sandbox_err = f"{type(e).__name__}: {e}"
        # 沙盒失败 → 降级到 local（保证 LLM 生成的代码能拿到反馈）
        try:
            import io, contextlib, textwrap
            dedented = textwrap.dedent(code)
            f = io.StringIO(); err = io.StringIO()
            with contextlib.redirect_stdout(f), contextlib.redirect_stderr(err):
                exec(dedented)
            out = f.getvalue() or err.getvalue() or "(无输出)"
            return {"result": {"content": [{"text": f"[沙盒❌→本地✅] 沙盒: {sandbox_err[:100]}\n{out[:5000]}"}]}}
        except Exception as e2:
            return {"result": {"content": [{"text": f"[沙盒❌] {sandbox_err[:200]}\n[本地❌] {type(e2).__name__}: {e2}"[:3000]}]}}

    # local 模式：本地 exec（可写桌面文件，速度快）
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


async def _handle_execute_shell(args: Dict) -> Dict:
    """执行 Shell 命令 — 通过 mode 参数指定执行模式"""
    command = args.get("command", "")
    if not command: return {"result": {"content": [{"text": "缺少 command 参数"}]}}
    mode = args.get("mode", "local")
    timeout = int(args.get("timeout", 30))

    if mode == "sandbox":
        try:
            from core.tools.sandbox_executor import SandboxExecutor, ResourceLimits
            limits = ResourceLimits(timeout=min(timeout, 60), max_output_size_kb=10000)
            ex = SandboxExecutor()
            sr = await ex.execute_shell(command, limits=limits)
            if sr.status.value in ("completed", "success"):
                out = sr.stdout if sr.stdout else ("(无输出)" if sr.stderr else "")
                err = sr.stderr if sr.stderr else ""
                full = out[:8000] + ("\n" + err[:2000] if err else "")
                return {"result": {"content": [{"text": f"[沙盒] ✅ 执行成功\n{full}"}]}}
            return {"result": {"content": [{"text": f"[沙盒] ❌ {sr.error_message or sr.stderr or '执行失败'}"[:5000]}]}}
        except Exception as e:
            return {"result": {"content": [{"text": f"[沙盒] ❌ {type(e).__name__}: {e}"[:3000]}]}}

    # local 模式
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


async def _handle_git(args: Dict) -> Dict:
    """Git 操作 — status/add/commit/log/diff/branch/pull"""
    action = args.get("action", "status")
    repo = args.get("repo", os.getcwd())
    msg = args.get("message", "")
    try:
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
            return {"result":{"content":[{"text":f"未知操作或缺少参数: {action}"}]}}
        proc = await asyncio.create_subprocess_exec(*cmds[action], cwd=repo, stdout=-1, stderr=-1)
        o, e = await asyncio.wait_for(proc.communicate(), timeout=15)
        text = (o.decode() if o else "") or (e.decode() if e else "(无输出)")
        return {"result":{"content":[{"text":f"git {action}\n{text[:3000]}"}]}}
    except Exception as ex:
        return {"result":{"content":[{"text":f"git {action} 失败: {ex}"[:500]}]}}


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
    "git": _handle_git,
}

_SANDBOX_TOOL_DEFS = [
    ToolDefinition(name="execute_python", server=SERVER_BUILTIN, tags=["code", "sandbox"],
        description="执行 Python 代码。默认本地执行（可读/写/修改桌面文件）；mode=sandbox 沙盒隔离执行。",
        parameters={"type":"object","properties":{
            "code":{"type":"string","description":"Python 代码"},
            "mode":{"type":"string","enum":["local","sandbox"],"description":"local=本地(默认,可写桌面文件) | sandbox=沙盒隔离"},
            "timeout":{"type":"integer","description":"超时秒数（默认30，最大60）"},
            "skip_module_check":{"type":"boolean","description":"仅 sandbox 模式：是否跳过模块安全检查"},
        },"required":["code"]},
        handler=_handle_execute_python),
    ToolDefinition(name="execute_shell", server=SERVER_BUILTIN, tags=["code", "shell"],
        description="Shell 命令执行。默认本地执行；mode=sandbox 沙盒隔离执行。",
        parameters={"type":"object","properties":{
            "command":{"type":"string","description":"Shell 命令"},
            "mode":{"type":"string","enum":["local","sandbox"],"description":"local=本地(默认) | sandbox=沙盒隔离"},
            "timeout":{"type":"integer","description":"超时秒数（默认30，最大60）"},
        },"required":["command"]},
        handler=_handle_execute_shell),
    ToolDefinition(name="git", server=SERVER_BUILTIN, tags=["git", "code"],
        description="Git 操作 — status/add/commit/log/diff/branch/pull。在当前项目目录执行。",
        parameters={"type":"object","properties":{
            "action":{"type":"string","enum":["status","add","commit","log","diff","branch","pull"],"description":"git 操作"},
            "message":{"type":"string","description":"commit 时的提交信息"},
            "files":{"type":"string","description":"add 时的文件路径（默认全部 .）"},
            "count":{"type":"integer","description":"log 显示的提交数（默认5）"},
        },"required":["action"]},
        handler=_handle_git),
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
        # MCP 服务器已通过 discover_all() 同步加载

    async def discover_all(self) -> List[ToolDefinition]:
        """发现所有工具来源：内置工具 + MCP 服务器（连接并注册工具）"""
        all_tools = []
        # Source 1: builtin tools
        for sd in _SANDBOX_TOOL_DEFS:
            if sd.name not in self._tools:
                self._tools[sd.name] = sd
                all_tools.append(sd)
        self._initialized = True
        # Source 2: MCP 服务器 — 同步连接，注入工具到注册表
        mcp_tools = await self._connect_mcp_servers()
        for t in mcp_tools:
            if t.name not in self._tools:
                self._tools[t.name] = t
                all_tools.append(t)
        all_types = {"builtin": sum(1 for t in all_tools if t.server == "__builtin__"),
                     "mcp": sum(1 for t in all_tools if t.server not in ("__builtin__",""))}
        logger.info(f"工具注册完成: {len(all_tools)} 个 ({all_types})")
        return all_tools

    async def _connect_mcp_servers(self) -> List[ToolDefinition]:
        """发现 MCP 服务器配置，保存到 mcp_client，返回已知工具定义"""
        mcp_tools = []
        try:
            from core.mcp.mcp_client import mcp_client
            proot = os.path.normpath(os.path.join(os.path.dirname(__file__),"..","..",".."))
            servers = set(await mcp_client.list_servers())
            # 从 mcp/ 目录发现
            mcp_dir = os.path.join(proot, "mcp")
            if os.path.isdir(mcp_dir):
                for fn in sorted(os.listdir(mcp_dir)):
                    if not fn.endswith("_mcp_server.py"): continue
                    srv = fn.replace("_mcp_server.py","").replace("_","-")
                    if srv in servers: continue
                    await mcp_client.connect_server(name=srv, command="python3",
                        args=[os.path.join(mcp_dir,fn)], cwd=proot,
                        env={"PYTHONPATH": proot})
                    servers.add(srv)
            # 从 .mcp.json 发现
            mcj = os.path.join(proot, ".mcp.json")
            if os.path.exists(mcj):
                try:
                    with open(mcj) as f:
                        for srv, sc in json.load(f).get("mcpServers",{}).items():
                            if srv in servers: continue
                            await mcp_client.connect_server(name=srv, command=sc["command"],
                                args=sc.get("args",[]), cwd=proot,
                                env={"PYTHONPATH": proot})
                            servers.add(srv)
                except: pass
            # 对已保存配置的服务器，拉取工具列表（超时 5s），使用原始工具名
            seen_names = set()
            for srv in sorted(servers):
                try:
                    tools = await asyncio.wait_for(mcp_client.list_tools(srv), timeout=5.0)
                    for tool in tools:
                        raw = tool.get("name","")
                        if not raw: continue
                        # 工具名 = 原始名（LLM易读），冲突时加服务器前缀
                        fn = _safe(raw)
                        if fn in seen_names:
                            fn = _safe(f"{srv}_{raw}")
                        seen_names.add(fn)
                        desc = tool.get("description","")
                        if not desc:
                            desc = f"通过 {srv} 服务器提供的工具"
                        mcp_tools.append(ToolDefinition(name=fn,
                            description=f"[{srv}] {desc}",
                            parameters=tool.get("inputSchema",{}) or {},
                            server=srv, tool_name=raw, tags=["mcp"]))
                except asyncio.TimeoutError:
                    logger.debug(f"MCP {srv}: 超时（进程启动慢）")
                except Exception:
                    logger.debug(f"MCP {srv}: 不可用")
        except Exception:
            pass
        if mcp_tools:
            logger.info(f"MCP: {len(mcp_tools)} 个工具来自 {len({t.server for t in mcp_tools})} 台服务器")
        return mcp_tools
        return mcp_tools

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

    async def get_tools_for_task(self, task: str, max_tools=30) -> List[ToolDefinition]:
        """按任务相关性排序的工具列表

        排序策略（修正 LLM 倾向选 MCP 工具的问题）：
        1. 内置工具（file/fetch_url/search 等）始终加分，排在前面
        2. MCP 工具按关键词匹配度排序，关键词冲突时内置工具优先
        3. 确保 LLM 先看到最可靠的工具
        """
        if not self._initialized:
            return list(self._tools.values())[:max_tools]
        desc = task.lower()
        scored = []

        # 核心内置工具（始终可用，优先展示）
        CORE_BUILTIN = {"file", "fetch_url", "search", "execute_python", "execute_shell"}

        for t in self._tools.values():
            s = 0.0
            dl = t.description.lower()
            nl = t.name.lower()
            is_builtin = t.server == SERVER_BUILTIN

            # 关键词匹配
            for kw in desc.split():
                kw = kw.strip().lower()
                if len(kw) > 1:
                    if kw in dl: s += 2.0
                    if kw in nl: s += 3.0

            # 中文字符级匹配
            if len(desc) > 1:
                if any(c in dl for c in desc if len(c.strip()) > 0):
                    s += 0.5

            # 内置工具加成：确保核心工具始终排在 MCP 工具前面
            if is_builtin:
                s += 5.0  # 内置工具加分，提高排名

            # 核心工具额外加分
            if t.name in CORE_BUILTIN:
                s += 3.0

            scored.append((s, t))

        # 按分数降序排列（内置工具因为加分自然排在前面）
        scored.sort(key=lambda x: -x[0])

        # 取所有得分 >0 的工具，但 MCP 工具需要更高分才能入选（避免干扰）
        result = []
        for s, t in scored:
            if s > 0:
                if t.server == SERVER_BUILTIN:
                    result.append(t)  # 内置工具只要有分就入选
                elif s >= 3.0:
                    result.append(t)  # MCP 工具需要 ≥3.0 分才入选（强关键词匹配）
            else:
                break  # 分数=0的后面不可能有正分了

        # 确保核心工具一定在列表中（即使得分为 0）
        for t in self._tools.values():
            if t.name in CORE_BUILTIN and t not in result:
                result.append(t)

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
