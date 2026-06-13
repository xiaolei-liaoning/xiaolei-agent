"""ToolRegistry — 工具注册表（含 10 个内置 handler）

内置工具：
- fetch_url:      HTTP GET 获取网页/API数据
- write_file:     写入文件
- read_file:      读取文件/目录
- edit_file:      精确文本替换
- search_files:   文件搜索（glob 模式或正则内容）
- execute_python: 沙盒执行 Python 代码
- execute_shell:  沙盒执行 Shell 命令
- web_search:     联网搜索（多引擎并发）
- git:            Git 操作

自动发现：MCP 服务器（mcp/ 目录 + .mcp.json）
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
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


# ═══════════════════════════════════════════════════════════════════
# 内置 Handlers
# ═══════════════════════════════════════════════════════════════════



# ── 纯 asyncio HTTP GET（不创建线程，可安全取消） ───────────────────


async def _http_get(url: str, timeout: int = 10) -> str:
    """HTTP GET — 使用 aiohttp，自动跟随重定向，SSL 验证优先开启"""
    import aiohttp
    import ssl as _ssl

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/json,*/*",
    }
    
    # 先尝试 SSL 验证
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                max_redirects=10,
            ) as resp:
                body = await resp.text(encoding="utf-8", errors="replace")
                return body
    except (aiohttp.ClientConnectorError, aiohttp.ClientOSError, _ssl.SSLError):
        pass
    
    # SSL 验证失败时，禁用验证重试
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=False,
                max_redirects=10,
            ) as resp:
                body = await resp.text(encoding="utf-8", errors="replace")
                return body
    except Exception:
        # aiohttp 失败时 fallback 到 urllib
        import urllib.request
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="replace")


async def _handle_fetch_url(args: Dict) -> Dict:
    """HTTP GET 获取网页/API数据 — 直接返回可读文本"""
    from core.multi_agent_v2.tools.html_parser import html_to_text
    from core.multi_agent_v2.tools.tool_result import ok, err

    url = args.get("url", "")
    ml = args.get("max_length", 80000)
    if not url:
        return err("需要 url 参数")
    import ssl
    from urllib.parse import quote, urlparse, urlunparse

    try:
        url.encode("ascii")
    except (UnicodeEncodeError, UnicodeDecodeError):
        parsed = urlparse(url)
        path = quote(parsed.path, safe="/%@") if parsed.path else ""
        q = parsed.query
        if q:
            try:
                q.encode("ascii")
            except (UnicodeEncodeError, UnicodeDecodeError):
                parts = []
                for part in q.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        try:
                            v.encode("ascii")
                        except:
                            v = quote(v, safe="")
                        parts.append(f"{k}={v}")
                    else:
                        parts.append(part)
                q = "&".join(parts)
        url = urlunparse(
            (parsed.scheme, parsed.netloc, path, parsed.params, q, parsed.fragment)
        )

    try:
        text = await _http_get(url, timeout=10)
    except asyncio.TimeoutError:
        return err("请求超时(10s)")
    except Exception as e:
        return err(f"请求失败: {e}")

    # 1. 尝试提取嵌入 JSON（__NEXT_DATA__/__INITIAL_STATE__）
    je = None
    for p in [
        r"<!--s-data:(.*?)-->",
        r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});",
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    ]:
        m = re.search(p, text, re.DOTALL)
        if m:
            je = m.group(1).strip()
            break
    if not je:
        m = re.search(r"[\{\[]", text)
        if m:
            maybe_json = text[m.start():].strip()
            is_real_json = False
            if maybe_json.startswith("{") and maybe_json.lstrip("{").strip().startswith('"'):
                is_real_json = True
            elif maybe_json.startswith("[") and maybe_json.lstrip("[").strip()[:1] in (
                '"', "{", "[", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "t", "f", "n",
            ):
                is_real_json = True
            if is_real_json:
                je = maybe_json

    if je:
        # 有嵌入 JSON → 解析并格式化
        try:
            parsed = json.loads(je)
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
                    preview += f"\n  ...共{len(hot_items)}条"
                return ok(preview)
            # 通用 JSON
            text_repr = json.dumps(parsed, ensure_ascii=False, indent=2)
            if len(text_repr) > ml:
                text_repr = text_repr[:int(ml * 0.7)] + f"\n...截断 ({len(text_repr)} 字符)"
            return ok(text_repr)
        except (json.JSONDecodeError, AttributeError):
            pass
        return ok(je[:ml])

    # 2. 纯 HTML → 直接转换为可读文本
    readable = html_to_text(text, max_length=ml)
    if not readable or len(readable) < 20:
        return err("无法解析页面内容")
    return ok(readable)





async def _handle_hot_search(query: str) -> Optional[Dict]:
    """处理热榜/热搜查询 — 调用多个公开数据源

    不依赖搜索引擎结果页（SPA问题），直接调用公开API。
    根据查询关键词智能排序数据源优先级。
    """
    from urllib.parse import quote

    async def _try_json(url: str, parser=None) -> Optional[str]:
        """获取JSON数据并用parser提取文本"""
        try:
            text = await _http_get(url, timeout=8)
            if not text:
                return None
            if parser:
                return parser(text)
            # 默认：返回JSON的格式化文本
            try:
                data = json.loads(text)
                formatted = json.dumps(data, ensure_ascii=False, indent=2)
                if len(formatted) > 300:
                    return formatted[:5000]
                return formatted
            except json.JSONDecodeError:
                return text[:3000]
        except Exception:
            return None

    sources = []
    query_lower = query.lower()

    # 0. GitHub Trending 检测 — 当查询包含 github 时优先使用
    is_github = "github" in query_lower or "git" in query_lower
    if is_github:

        async def _github_trending():
            """抓取 GitHub Trending 页面"""
            # 先尝试 GitHub API (gh CLI)
            try:
                from core.mcp.mcp_client import mcp_client

                gh_tools = await mcp_client.list_tools("github-mcp")
                # f"[{srv}] " 前缀的工具名 → 提取原始名称
                actual_tools = [t.get("name", "") for t in gh_tools]
            except Exception:
                gh_tools = []
            from datetime import datetime, timedelta

            since_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            # 方式 A: 用 GitHub API 直接获取 trending
            gh_data = await _try_json(
                f"https://api.github.com/search/repositories?q=created:>{since_date}&sort=stars&order=desc&per_page=15",
                parser=lambda t: _format_github_trending(t, "GitHub 趋势仓库"),
            )
            if gh_data:
                sources.append(gh_data)

            # 方式 B: 爬取 GitHub Trending 页面做补充
            gh_trending = await _try_json(
                "https://github.com/trending?since=weekly",
                parser=lambda t: _format_github_trending_html(t, "GitHub Trending"),
            )
            if gh_trending:
                # 如果 API 已经拿到数据，把页面解析结果做补充
                if gh_data:
                    sources.append(gh_trending)
                else:
                    sources.append(gh_trending)

        asyncio.create_task(_github_trending())
        # GitHub 查询只等 GitHub 源，不等中文平台
        await asyncio.sleep(2.5)
        if sources:
            combined = "\n\n".join(sources[:3])
            return {
                "result": {
                    "content": [
                        {"text": f"获取到 GitHub Trending 数据：\n\n{combined}"}
                    ]
                }
            }
        # GitHub 源都失败时降级到普通搜索
        return None

    # 根据查询关键词确定数据源优先级
    want_baidu = "百度" in query or "baidu" in query_lower
    want_zhihu = "知乎" in query or "zhihu" in query_lower
    want_weibo = "微博" in query or "weibo" in query_lower
    want_douyin = "抖音" in query or "douyin" in query_lower

    # 定义所有可用数据源
    all_sources = [
        ("baidu", "百度热搜", "https://top.baidu.com/api/board?tab=realtime"),
        ("zhihu", "知乎热搜", "https://www.zhihu.com/api/v3/feed/topstory/hot-lists?limit=10"),
        ("weibo", "微博热搜", "https://tenapi.cn/v2/weibohot"),
        ("douyin", "抖音热榜", "https://tenapi.cn/v2/douyinhot"),
    ]

    # 按优先级排序：明确指定的排前面，其他的排后面
    if want_baidu:
        # 百度优先：baidu第一，其他按默认顺序
        sources_order = ["baidu", "zhihu", "weibo", "douyin"]
    elif want_zhihu:
        sources_order = ["zhihu", "baidu", "weibo", "douyin"]
    elif want_weibo:
        sources_order = ["weibo", "baidu", "zhihu", "douyin"]
    elif want_douyin:
        sources_order = ["douyin", "baidu", "zhihu", "weibo"]
    else:
        # 默认顺序：百度、知乎、微博、抖音
        sources_order = ["baidu", "zhihu", "weibo", "douyin"]

    # 构建有序数据源列表
    ordered_sources = []
    source_map = {s[0]: s for s in all_sources}
    for key in sources_order:
        if key in source_map:
            ordered_sources.append(source_map[key])

    # 并发请求所有数据源
    async def _fetch_source(name: str, url: str):
        data = await _try_json(
            url,
            parser=lambda t, n=name: _format_hot_list(t, n),
        )
        if data:
            sources.append(data)

    tasks = [_fetch_source(name, url) for name, _, url in ordered_sources]
    await asyncio.gather(*tasks)

    # 等待所有任务完成（最多2秒）
    await asyncio.sleep(0.5)

    if sources:
        # 如果用户指定了平台，只返回该平台数据
        if want_baidu:
            baidu_data = [s for s in sources if "百度热搜" in s]
            if baidu_data:
                return {"result": {"content": [{"text": baidu_data[0]}]}}
        elif want_zhihu:
            zhihu_data = [s for s in sources if "知乎热搜" in s]
            if zhihu_data:
                return {"result": {"content": [{"text": zhihu_data[0]}]}}
        elif want_weibo:
            weibo_data = [s for s in sources if "微博热搜" in s]
            if weibo_data:
                return {"result": {"content": [{"text": weibo_data[0]}]}}
        elif want_douyin:
            douyin_data = [s for s in sources if "抖音热榜" in s]
            if douyin_data:
                return {"result": {"content": [{"text": douyin_data[0]}]}}

        # 否则返回所有可用数据（最多3个源）
        combined = "\n\n".join(sources[:3])
        return {"result": {"content": [{"text": f"获取到热门数据：\n\n{combined}"}]}}
    return None


def _format_hot_list(json_text: str, source_name: str) -> Optional[str]:
    """从可能的JSON格式中提取热榜列表"""
    try:
        data = json.loads(json_text)
        items = []

        # 百度热搜API特殊处理：{data: {cards: [{content: [...]}]}}
        if isinstance(data, dict) and "data" in data:
            cards = data.get("data", {}).get("cards", [])
            if cards and isinstance(cards, list):
                content = cards[0].get("content", [])
                if content and isinstance(content, list):
                    for e in content[:15]:
                        if isinstance(e, dict):
                            word = e.get("word", e.get("query", ""))
                            hot_score = e.get("hotScore", e.get("hot", ""))
                            desc = e.get("desc", e.get("description", ""))
                            if word:
                                line = word[:60]
                                if hot_score:
                                    line += f" (热度:{hot_score})"
                                if desc and isinstance(desc, str):
                                    line += f" — {desc[:50]}"
                                items.append(line)
                    if items:
                        return f"【{source_name}】\n" + "\n".join(items[:10])

        # 通用格式处理
        # 尝试多种JSON结构
        # 格式1: {data: {list: [{title:..., ...}]}}
        for d in [data]:
            entries = []

            # 递归搜索list/items/data数组
            def _find_list(obj, depth=0):
                if depth > 3:
                    return []
                if isinstance(obj, dict):
                    if "list" in obj and isinstance(obj["list"], list):
                        return obj["list"]
                    for v in obj.values():
                        r = _find_list(v, depth + 1)
                        if r:
                            return r
                if isinstance(obj, list):
                    return obj
                return []

            entries = _find_list(data)

            if not entries and isinstance(data, list):
                entries = data

            for e in entries[:15]:
                if isinstance(e, dict):
                    title = e.get(
                        "title", e.get("name", e.get("word", e.get("content", "")))
                    )
                    hot = e.get(
                        "hot", e.get("hotScore", e.get("heat", e.get("count", "")))
                    )
                    desc = e.get("desc", e.get("description", ""))
                    if isinstance(title, str) and title:
                        line = title[:60]
                        if hot:
                            line += f" (热度:{hot})"
                        if desc and isinstance(desc, str):
                            line += f" — {desc[:50]}"
                        items.append(line)

        if items:
            return f"【{source_name}】\n" + "\n".join(items[:10])
        return None
    except Exception:
        return None


def _format_github_trending(json_text: str, source_name: str) -> Optional[str]:
    """从 GitHub Search API JSON 中提取趋势仓库列表"""
    try:
        data = json.loads(json_text)
        items_raw = data.get("items", [])
        if not items_raw:
            return None
        lines = []
        for repo in items_raw[:15]:
            name = repo.get("full_name", repo.get("name", ""))
            desc = repo.get("description", "") or ""
            stars = repo.get("stargazers_count", 0)
            forks = repo.get("forks_count", 0)
            lang = repo.get("language") or ""
            if name:
                line = f"  ⭐ {stars}  🍴 {forks}"
                if lang:
                    line += f"  🔤 {lang}"
                line += f"\n      {name}"
                if desc:
                    line += f" — {desc[:80]}"
                lines.append(line)
        if lines:
            return f"【{source_name}】\n" + "\n".join(lines[:15])
        return None
    except Exception:
        return None


def _format_github_trending_html(html_text: str, source_name: str) -> Optional[str]:
    """从 GitHub Trending 页面 HTML 中提取趋势仓库列表"""
    try:
        import re

        # 提取 article 标签内的 repo 信息
        # GitHub trending 页面结构: <article> 内包含 h1/h2/repo 名和描述
        articles = re.findall(r"<article[^>]*>.*?</article>", html_text, re.DOTALL)
        if not articles:
            return None
        lines = []
        for art in articles[:15]:
            # 提取仓库名
            name_match = re.search(
                r'<h[12][^>]*>.*?<a[^>]*href="/([^"]+)"[^>]*>([^<]+)</a>', art
            )
            if name_match:
                full_name = name_match.group(1).strip()
                display = name_match.group(2).strip()
            else:
                # 备选: 直接找 h1/h2 中的文本
                h_match = re.search(r"<h[12][^>]*>\s*(.+?)\s*</h[12]>", art)
                if h_match:
                    display = h_match.group(1).strip()
                    full_name = display
                else:
                    continue

            # 提取描述
            desc_match = re.search(
                r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', art, re.DOTALL
            )
            desc = desc_match.group(1).strip() if desc_match else ""
            desc = re.sub(r"<[^>]+>", "", desc).strip()

            # 提取语言
            lang_match = re.search(
                r'<span[^>]*itemprop="programmingLanguage"[^>]*>(.*?)</span>', art
            )
            lang = lang_match.group(1).strip() if lang_match else ""

            # 提取星数
            stars_match = re.search(
                r'<a[^>]*href="/[^"]+/stargazers"[^>]*>\s*([\d,]+)\s*</a>', art
            )
            stars = stars_match.group(1).strip() if stars_match else ""

            line = f"  ⭐ {stars}"
            if lang:
                line += f"  🔤 {lang}"
            line += f"\n      {full_name}"
            if desc:
                line += f" — {desc[:80]}"
            lines.append(line)

        if lines:
            return f"【{source_name}】\n" + "\n".join(lines[:15])
        return None
    except Exception:
        return None


async def _handle_search(args: Dict) -> Dict:
    """联网搜索 — Bing + Baidu + DDG 三引擎并发，结果合并去重"""
    from urllib.parse import quote
    from core.multi_agent_v2.tools.html_parser import (
        extract_search_results_bing,
        extract_search_results_baidu,
        extract_search_results_ddg,
        merge_search_results,
    )
    from core.multi_agent_v2.tools.tool_result import ok, err

    query = args.get("query", "")
    if not query:
        return err("需要 query 参数")

    encoded = quote(query)

    # ── 热榜/热搜检测：直接调用公开数据源 ──
    is_hot = "热搜" in query or "热榜" in query or "trending" in query.lower()
    if is_hot:
        hot_results = await _handle_hot_search(query)
        if hot_results:
            # 兼容旧格式返回
            text = hot_results.get("result", {}).get("content", [{}])[0].get("text", "")
            if text:
                return ok(text)

    # 三引擎并发
    engines = [
        ("Bing", f"https://cn.bing.com/search?q={encoded}&count=10", extract_search_results_bing),
        ("百度", f"https://www.baidu.com/s?wd={encoded}&rn=10", extract_search_results_baidu),
        ("DuckDuckGo", f"https://html.duckduckgo.com/html/?q={encoded}", extract_search_results_ddg),
    ]

    sources = []

    async def _search_one(name: str, url: str, parser):
        try:
            html = await _http_get(url, timeout=8)
            results = parser(html)
            if results:
                sources.append((name, results))
        except Exception:
            pass

    await asyncio.gather(*[_search_one(n, u, p) for n, u, p in engines])

    if not sources:
        # 兜底：重试百度
        try:
            html = await _http_get(f"https://www.baidu.com/s?wd={encoded}&rn=10", timeout=8)
            results = extract_search_results_baidu(html)
            if results:
                sources.append(("百度(重试)", results))
        except Exception:
            pass

    if not sources:
        return err("搜索暂不可用，请用 fetch_url 直接访问目标网址")

    merged = merge_search_results(sources)
    return ok(merged)


def _detect_code_language(code: str) -> tuple:
    """检测代码语言 — 委托给 gemini_enhanced_tools 共享实现"""
    from core.tools.gemini_enhanced_tools import detect_code_language
    return detect_code_language(code)


async def _handle_execute_python(args: Dict) -> Dict:
    """执行 Python 代码 — 默认沙盒隔离，mode=local 需显式指定
    
    sandbox 模式：执行后检测文件写入操作，如有则提示用户确认保存路径
    local 模式：需要用户确认后执行（无安全隔离）
    非 Python 代码（JS/HTML/CSS等）：自动 redirect 到 write_file
    """
    code = args.get("code", "")
    if not code:
        return {"result": {"content": [{"text": "缺少 code 参数"}]}}

    # ── 非 Python 语言检测 → 自动 redirect 到 write_file ──
    lang, ext, default_name = _detect_code_language(code)
    if lang != "python":
        logger.info(f"检测到 {lang} 代码，自动 redirect 到 write_file")
        # 推荐保存路径
        import os
        desktop = os.path.expanduser("~/Desktop")
        save_path = os.path.join(desktop, f"{default_name}{ext}")

        # 调用 write_file handler
        write_result = await _handle_write_file({"path": save_path, "content": code})
        # 附加 redirect 提示
        result_text = ""
        if write_result and isinstance(write_result.get("result"), dict):
            contents = write_result["result"].get("content", [])
            if contents:
                result_text = contents[0].get("text", "")
        redirect_msg = (
            f"\n\n🔄 已自动将 {lang} 代码保存到文件（execute_python 只能执行 Python）。\n"
            f"保存路径: {save_path}\n"
            f"如需修改路径，请直接调用 write_file(path='新路径', content=代码)"
        )
        return ok(result_text + redirect_msg)
    mode = args.get("mode", "sandbox")  # sandbox(默认,隔离) | local(显式指定,可写桌面文件)
    timeout = int(args.get("timeout", 30))
    
    # local 模式：需要用户确认（无安全隔离）
    if mode == "local":
        confirmed = args.get("confirmed", False)
        if not confirmed:
            return {
                "result": {
                    "content": [{"text": "⚠️ local 模式无安全隔离，代码将直接在本地执行。\n\n是否确认执行？请回复 '确认' 或调用 execute_python 并设置 confirmed=true"}],
                    "requires_confirmation": True,
                    "mode": "local"
                }
            }
        # 用户已确认，执行代码
        try:
            import contextlib
            import io
            import textwrap

            dedented = textwrap.dedent(code)
            f = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(f), contextlib.redirect_stderr(err):
                exec(dedented)
            out = f.getvalue() or err.getvalue() or "(无输出)"
            return {"result": {"content": [{"text": f"[本地] ✅ 执行成功\n{out[:5000]}\n\n⚠️ 警告：当前为本地模式，无安全隔离"}]}}
        except Exception as e:
            return {
                "result": {
                    "content": [{"text": f"[本地] ❌ {type(e).__name__}: {e}\n\n⚠️ 警告：当前为本地模式，无安全隔离"[:3000]}]
                }
            }

    # sandbox 模式（失败直接报错，不降级到裸 exec）
    skip_check = args.get("skip_module_check", False)
    try:
        from core.tools.sandbox_executor import (
            ResourceLimits, SandboxExecutor,
            detect_file_writes, extract_file_paths, get_recommended_path,
            format_file_writes_detected
        )

        limits = ResourceLimits(timeout=min(timeout, 60), max_output_size_kb=10000)
        ex = SandboxExecutor()
        sr = await ex.execute_python(
            code, limits=limits, skip_module_check=skip_check
        )
        if sr.status.value == "completed":
            out = sr.stdout if sr.stdout else ("(无输出)" if sr.stderr else "")
            err = sr.stderr if sr.stderr else ""
            full = out[:8000] + ("\n" + err[:2000] if err else "")
            
            # 检测文件写入操作
            file_writes = detect_file_writes(code)
            if file_writes:
                # 提取路径并获取推荐路径
                detected_paths = extract_file_paths(code)
                task_desc = args.get("_task_description", "")  # 从上下文获取任务描述
                recommended_path = get_recommended_path(detected_paths, task_desc)
                
                # 格式化检测结果
                file_write_msg = format_file_writes_detected(file_writes, recommended_path)
                
                return {
                    "result": {
                        "content": [{"text": f"[沙盒] ✅ 执行成功\n{full}\n\n{file_write_msg}"}],
                        "needs_file_save": True,
                        "file_writes": file_writes,
                        "detected_paths": detected_paths,
                        "recommended_path": recommended_path
                    }
                }
            
            return {
                "result": {"content": [{"text": f"[沙盒] ✅ 执行成功\n{full}"}]}
            }
        # 沙盒执行失败，返回错误信息（不降级）
        sandbox_err = sr.error_message or sr.stderr or "执行失败"
        return {
            "result": {
                "content": [
                    {"text": f"[沙盒] ❌ 执行失败: {sandbox_err[:3000]}"}
                ]
            }
        }
    except Exception as e:
        return {
            "result": {
                "content": [
                    {"text": f"[沙盒] ❌ {type(e).__name__}: {e}"[:3000]}
                ]
            }
        }


async def _handle_execute_shell(args: Dict) -> Dict:
    """执行 Shell 命令 — 默认沙盒隔离，mode=local 需显式指定"""
    command = args.get("command", "")
    if not command:
        return {"result": {"content": [{"text": "缺少 command 参数"}]}}
    
    # 安全检查：使用 ShellGuard 扫描命令
    try:
        from core.multi_agent_v2.tools.shell_guard import ShellGuard
        guard = ShellGuard()
        issues = guard.scan(command)
        if issues.get("blocked"):
            return {"result": {"content": [{"text": f"命令被安全策略阻止: {issues.get('reason', '未知原因')}"}]}}
    except Exception:
        pass  # ShellGuard 不可用时跳过检查
    
    mode = args.get("mode", "sandbox")  # sandbox(默认,隔离) | local(显式指定)
    timeout = int(args.get("timeout", 30))

    if mode == "sandbox":
        try:
            from core.tools.sandbox_executor import ResourceLimits, SandboxExecutor

            limits = ResourceLimits(timeout=min(timeout, 60), max_output_size_kb=10000)
            ex = SandboxExecutor()
            sr = await ex.execute_shell(command, limits=limits)
            if sr.status.value == "completed":
                out = sr.stdout if sr.stdout else ("(无输出)" if sr.stderr else "")
                err = sr.stderr if sr.stderr else ""
                full = out[:8000] + ("\n" + err[:2000] if err else "")
                return {
                    "result": {"content": [{"text": f"[沙盒] ✅ 执行成功\n{full}"}]}
                }
            # 沙盒执行失败，返回错误信息（不降级）
            return {
                "result": {
                    "content": [
                        {
                            "text": f"[沙盒] ❌ 执行失败: {sr.error_message or sr.stderr or '未知错误'}"[
                                :5000
                            ]
                        }
                    ]
                }
            }
        except Exception as e:
            return {
                "result": {
                    "content": [{"text": f"[沙盒] ❌ {type(e).__name__}: {e}"[:3000]}]
                }
            }

    # local 模式：无安全隔离，直接执行
    import asyncio

    try:
        proc = await asyncio.create_subprocess_shell(command, stdout=-1, stderr=-1)
        o, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "result": {
                "content": [
                    {"text": f"[本地] 返回码 {proc.returncode}\n{o.decode()[:3000]}\n\n⚠️ 警告：当前为本地模式，无安全隔离"}
                ]
            }
        }
    except asyncio.TimeoutError:
        # 超时后杀死子进程，防止孤儿进程
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        return {"result": {"content": [{"text": "[本地] ❌ 执行超时（进程已被杀死）\n\n⚠️ 警告：当前为本地模式，无安全隔离"}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"[本地] ❌ {e}\n\n⚠️ 警告：当前为本地模式，无安全隔离"[:2000]}]}}












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
            return {"result": {"content": [{"text": f"未知操作或缺少参数: {action}"}]}}
        proc = await asyncio.create_subprocess_exec(
            *cmds[action], cwd=repo, stdout=-1, stderr=-1
        )
        o, e = await asyncio.wait_for(proc.communicate(), timeout=15)
        text = (o.decode() if o else "") or (e.decode() if e else "(无输出)")
        return {"result": {"content": [{"text": f"git {action}\n{text[:3000]}"}]}}
    except Exception as ex:
        return {"result": {"content": [{"text": f"git {action} 失败: {ex}"[:500]}]}}




def _find_similar_files(path: str, desktop: str) -> List[str]:
    """查找桌面上类似的文件
    
    Args:
        path: 目标文件路径
        desktop: 桌面路径
        
    Returns:
        类似文件列表
    """
    import glob
    
    filename = os.path.basename(path)
    name_without_ext = os.path.splitext(filename)[0]
    
    # 游戏/应用类关键词
    game_keywords = ['game', 'puzzle', '游戏', '应用', 'app', 'digit', '数码', '八数码', '8数码']
    
    similar_files = []
    seen = set()
    
    # 只匹配相同扩展名的文件（.py 不会被 .html 阻挡）
    target_ext = os.path.splitext(path)[1].lower()
    # 获取桌面上所有同类文件
    all_html_files = glob.glob(os.path.join(desktop, f"*{target_ext}"))
    
    for filepath in all_html_files:
        if filepath in seen or filepath == path:
            continue
        
        basename = os.path.basename(filepath).lower()
        basename_no_ext = os.path.splitext(basename)[0]
        
        # 检查是否是游戏/应用类文件
        is_game_file = any(keyword in basename for keyword in game_keywords)
        
        if is_game_file:
            # 检查文件名相似性
            # 1. 完全相同的名字
            if basename_no_ext == name_without_ext.lower():
                seen.add(filepath)
                similar_files.append(filepath)
                continue
            
            # 2. 包含相同的关键词
            for keyword in game_keywords:
                if keyword in basename and keyword in name_without_ext.lower():
                    seen.add(filepath)
                    similar_files.append(filepath)
                    break
    
    return similar_files[:10]  # 最多返回10个


async def _handle_write_file(args: Dict) -> Dict:
    """写文件到指定路径 — 兼容多种参数名"""
    from core.multi_agent_v2.tools.tool_result import ok, err
    from core.multi_agent_v2.tools.omission_detector import detect_omission_placeholders
    from core.multi_agent_v2.tools.content_corrector import ensure_correct_content, detect_encoding_issues

    try:
        path = args.get("path", "")
        content = args.get("content", "")
        # 兼容多种参数名
        if not content:
            content = args.get("code", "") or args.get("text", "") or args.get("html", "") or args.get("data", "") or args.get("file_content", "")
        if not content:
            logger.warning(f"write_file: 参数中没有 content/code/text/html，args keys={list(args.keys())}")
            return err("需要 content 参数")
        
        # 省略占位符检测（移植自 gemini-cli）
        omissions = detect_omission_placeholders(content)
        if omissions:
            logger.warning(f"write_file: 检测到省略占位符 {omissions} (path={path})")
            return err(f"❌ 内容包含省略占位符 {omissions}，请提供完整内容，不要使用 'rest of methods ...' 等占位符！")
        
        # 内容修正（移植自 gemini-cli）
        content = ensure_correct_content(content, aggressive_unescape=True)
        
        # 检测编码问题
        encoding_issues = detect_encoding_issues(content)
        if encoding_issues:
            logger.warning(f"write_file: 检测到编码问题 {encoding_issues} (path={path})")
        
        # 中文路径映射
        desktop = os.path.expanduser("~/Desktop")
        if path.startswith("桌面上/"):
            path = desktop + path[3:]
        elif path.startswith("桌面/"):
            path = desktop + path[2:]
        path = os.path.expanduser(path)
        
        # ── 重复文件检测：检查桌面上是否已存在类似的文件 ──
        force = args.get("force", False)
        if not force and path.startswith(desktop):
            existing_similar = _find_similar_files(path, desktop)
            if existing_similar:
                filename = os.path.basename(path)
                name_without_ext = os.path.splitext(filename)[0]
                # 检查是否是游戏/应用类文件
                is_game_or_app = any(keyword in content.lower() for keyword in 
                    ['game', 'puzzle', '游戏', '应用', 'app'])
                
                if is_game_or_app and len(existing_similar) > 0:
                    return err(
                        f"桌面上已存在类似的文件: " +
                        ", ".join([f for f in existing_similar[:5]]) +
                        f"。建议复用已有文件，或使用 force=true 参数覆盖，或选择其他文件名。"
                    )
        
        # ── 自动合并：如果写入 .js/.css 但存在同名 .html，自动合并到 HTML 中 ──
        if path.endswith(('.js', '.ts')) or path.endswith(('.css', '.scss', '.less')):
            html_path = path.rsplit('.', 1)[0] + '.html'
            if not os.path.exists(html_path):
                html_path = path.rsplit('.', 1)[0] + '.htm'
            if os.path.exists(html_path):
                try:
                    html_content = open(html_path, 'r', encoding='utf-8').read()
                    code = content
                    if code.strip().startswith('<script') and code.strip().endswith('</script>'):
                        code = code.strip()[8:-9].strip()
                    elif code.strip().startswith('<style') and code.strip().endswith('</style>'):
                        code = code.strip()[7:-8].strip()
                    
                    if path.endswith(('.js', '.ts')):
                        if '</script>' in html_content:
                            import re
                            html_content = re.sub(
                                r'<script>\s*(?://.*?\n\s*)?</script>',
                                f'<script>\n{code}\n</script>',
                                html_content,
                                count=1
                            )
                        else:
                            html_content = html_content.replace('</body>', f'<script>\n{code}\n</script>\n</body>')
                    elif path.endswith(('.css', '.scss', '.less')):
                        if '</style>' in html_content:
                            import re
                            html_content = re.sub(
                                r'<style>\s*</style>',
                                f'<style>\n{code}\n</style>',
                                html_content,
                                count=1
                            )
                        else:
                            html_content = html_content.replace('</head>', f'<style>\n{code}\n</style>\n</head>')
                    
                    Path(html_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(html_path).write_text(html_content, encoding='utf-8')
                    logger.info(f"write_file: 自动合并 {os.path.basename(path)} → {html_path}")
                    return ok(f"✅ 已合并到 {html_path} ({len(html_content)} 字符)")
                except Exception as e:
                    logger.warning(f"自动合并失败: {e}，回退到单独写入")
        
        # 内容长度提示（仅警告，不阻断）
        if len(content) < 100:
            logger.info(f"write_file: 内容较短 ({len(content)}字符, path={path})")
        
        # HTML文件结构提示（仅警告，不阻断）
        if path.endswith(('.html', '.htm')):
            content_lower = content.lower()
            missing = []
            if '<!doctype' not in content_lower and '<html' not in content_lower:
                missing.append("<!DOCTYPE html>/<html>")
            if '<body' not in content_lower:
                missing.append("<body>")
            if '</html>' not in content_lower:
                missing.append("</html>")
            if missing:
                logger.info(f"write_file: HTML文件缺标签: {', '.join(missing)} (path={path})")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        # 检测是否为续写（文件已存在且内容较短 → 追加模式）
        is_append = False
        is_overwrite = False
        force = args.get("force", False)  # 支持 force 参数强制覆盖
        
        if Path(path).exists():
            existing = Path(path).read_text(encoding="utf-8")
            
            # 内容完全相同，无需写入
            if existing == content:
                return ok(f"✅ 文件内容相同，无需写入: {path}")
            
            # 文件已存在且内容不同
            if not force and existing and len(existing) > 100:
                # 对于游戏/应用类文件，返回提示让 Agent 确认
                is_game_or_app = any(keyword in content.lower() for keyword in 
                    ['<!doctype', '<html', 'game', 'puzzle', '游戏', '应用'])
                if is_game_or_app:
                    return err(
                        f"文件已存在且内容不同: {path} "
                        f"(现有{len(existing)}字符, 新内容{len(content)}字符)。"
                        f"请使用 force=true 参数强制覆盖，或选择其他文件名。"
                    )
            
            # HTML/游戏/报告文件始终覆盖，避免多个 <!DOCTYPE 混在一起
            is_html_file = path.endswith(('.html', '.htm'))
            if not is_html_file and existing and len(existing) > 50 and not content.startswith(existing[:50]):
                # 检查是否为明显的代码延续（新内容较短且不含 DOCTYPE/html 标签）
                if len(content) < 500 and '<!doctype' not in content.lower() and '<html' not in content.lower():
                    is_append = True
            else:
                is_overwrite = True
        
        if is_append:
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            Path(path).write_text(content, encoding="utf-8")

        # 写后自验证：确认文件已落盘且内容一致
        if not Path(path).exists():
            return err(f"❌ 文件写入后无法验证（路径不存在）: {path}")
        written = Path(path).read_text(encoding="utf-8")
        if len(written) < len(content) * 0.5:
            return err(f"❌ 文件写入不完整: 传入{len(content)}字符, 实际{len(written)}字符")
        
        # 截断检测：HTML 文件是否缺少闭合标签
        truncation_msg = ""
        if path.endswith(('.html', '.htm')):
            content_lower = content.lower()
            missing = []
            if '<script' in content_lower and '</script>' not in content_lower:
                missing.append("</script>")
            if '<style' in content_lower and '</style>' not in content_lower:
                missing.append("</style>")
            if '<body' in content_lower and '</body>' not in content_lower:
                missing.append("</body>")
            if '</html>' not in content_lower:
                missing.append("</html>")
            if missing:
                truncation_msg = f"\n⚠️ 代码被截断！缺少: {', '.join(missing)}\n请继续生成剩余代码，使用 write_file 追加到同一文件。"
        
        result_msg = f"✅ 已写入文件: {path} ({len(content)} 字符)"
        if is_append:
            result_msg = f"✅ 已追加到文件: {path} (+{len(content)} 字符, 总计{len(existing) + len(content)} 字符)"
        if truncation_msg:
            result_msg += truncation_msg
        
        return ok(result_msg)
    except Exception as e:
        return err(f"❌ 写入失败: {type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════════
# 迁移工具：原 register_new_tools.py 中的工具（原生 async 实现）
# ═══════════════════════════════════════════════════════════════════

async def _handle_read_file(args: Dict) -> Dict:
    """读取文件或目录 — 支持分页"""
    from core.multi_agent_v2.tools.tool_result import ok, err

    path = args.get("path", "")
    if not path:
        return err("需要 path 参数")
    path = os.path.expanduser(path)
    p = Path(path)
    if not p.exists():
        return err(f"路径不存在: {path}")
    if p.is_dir():
        entries = sorted(p.iterdir())[:args.get("limit", 200)]
        lines = [f"{'📁' if e.is_dir() else '📄'} {e.name}" for e in entries]
        return ok(f"目录 {path} ({len(entries)} 项):\n" + "\n".join(lines))
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return err(f"无法解码文件: {path}")
    lines = text.split("\n")
    offset = max(0, args.get("offset", 1) - 1)
    limit = args.get("limit", 2000)
    page = lines[offset:offset + limit]
    result = "\n".join(page)
    if offset > 0 or offset + limit < len(lines):
        result = f"(行 {offset+1}-{min(offset+limit, len(lines))}/{len(lines)})\n{result}"
    return ok(result)


async def _handle_edit_file(args: Dict) -> Dict:
    """精确文本替换 + diff 预览"""
    import difflib
    from core.multi_agent_v2.tools.tool_result import err

    path = args.get("path", "")
    old = args.get("old_string", "")
    new = args.get("new_string", "")
    replace_all = args.get("replace_all", False)
    if not path or not old:
        return err("需要 path 和 old_string 参数")
    path = os.path.expanduser(path)
    p = Path(path)
    if not p.exists():
        return err(f"文件不存在: {path}")
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return err(f"无法解码文件: {path}")
    count = text.count(old)
    if count == 0:
        return err("old_string 未在文件中找到")
    if not replace_all and count > 1:
        return err(f"找到 {count} 处匹配，请设置 replace_all=true 或提供更多上下文")
    new_text = text.replace(old, new, -1 if replace_all else 1)
    p.write_text(new_text, encoding="utf-8")
    actual = text.count(old) - new_text.count(old) if replace_all else 1

    # 生成 diff
    rel_path = p.relative_to(Path.cwd()) if p.is_relative_to(Path.cwd()) else p
    old_lines = text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile=str(rel_path), tofile=str(rel_path), n=3))
    diff_text = "".join(diff_lines) if diff_lines else ""

    return {"ok": True, "data": f"编辑成功: {path} (替换 {actual} 处)", "diff": diff_text}


async def _handle_glob_search(args: Dict) -> Dict:
    """文件模式匹配搜索"""
    import glob as _glob
    from core.multi_agent_v2.tools.tool_result import ok, err

    pattern = args.get("pattern", "")
    if not pattern:
        return err("需要 pattern 参数")
    search_path = args.get("path", ".")
    limit = args.get("limit", 200)
    full_pattern = os.path.join(search_path, pattern)
    matches = sorted(_glob.glob(full_pattern, recursive=True))[:limit]
    if not matches:
        return ok("未找到匹配文件")
    return ok(f"找到 {len(matches)} 个文件:\n" + "\n".join(matches[:50]))


async def _handle_grep_search(args: Dict) -> Dict:
    """正则表达式内容搜索"""
    from core.multi_agent_v2.tools.tool_result import ok, err

    pattern = args.get("pattern", "")
    if not pattern:
        return err("需要 pattern 参数")
    search_path = args.get("path", ".")
    include = args.get("include", "")
    limit = args.get("limit", 200)
    import re as _re
    try:
        regex = _re.compile(pattern)
    except _re.error as e:
        return err(f"正则表达式错误: {e}")
    results = []
    p = Path(search_path)
    files = [p] if p.is_file() else list(p.rglob(include if include else "*"))
    for fp in files:
        if not fp.is_file() or len(results) >= limit:
            break
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.split("\n"), 1):
                if regex.search(line):
                    results.append(f"{fp}:{i}: {line.strip()[:100]}")
                    if len(results) >= limit:
                        break
        except Exception:
            continue
    if not results:
        return ok("未找到匹配内容")
    return ok(f"找到 {len(results)} 个匹配:\n" + "\n".join(results[:30]))



async def _handle_search_files(args: Dict) -> Dict:
    """搜索文件 — 按文件名 glob 模式或按正则内容搜索"""
    from core.multi_agent_v2.tools.tool_result import ok, err
    pattern = args.get("pattern", "")
    content_pattern = args.get("content_pattern", "")
    search_path = args.get("path", ".")
    include = args.get("include", "")
    limit = args.get("limit", 200)
    if content_pattern:
        return await _handle_grep_search({
            "pattern": content_pattern, "path": search_path,
            "include": include, "limit": limit,
        })
    elif pattern:
        return await _handle_glob_search({
            "pattern": pattern, "path": search_path, "limit": limit,
        })
    else:
        return err("需要 pattern（文件名搜索）或 content_pattern（内容搜索）参数")


# ═══════════════════════════════════════════════════════════════════
# Handler 映射 & 工具定义
# ═══════════════════════════════════════════════════════════════════

_HANDLER_MAP: Dict[str, Callable] = {
    "fetch_url": _handle_fetch_url,
    "write_file": _handle_write_file,
    "read_file": _handle_read_file,
    "edit_file": _handle_edit_file,
    "search_files": _handle_search_files,
    "execute_python": _handle_execute_python,
    "execute_shell": _handle_execute_shell,
    "web_search": _handle_search,
    "git": _handle_git,
}

_SANDBOX_TOOL_DEFS = [
    ToolDefinition(
        name="write_file",
        server=SERVER_BUILTIN,
        tags=["file", "write"],
        description="写入文件到指定路径。用于创建游戏、脚本、HTML报告、数据页面等文件。必填：path=文件路径(如~/Desktop/game.html)，content=完整文件内容(必须！文件的全部代码)。注意：content 参数是文件的完整内容，必须为非空字符串。HTML游戏必须是单个自包含文件，所有JS和CSS内联，禁止拆分成多个文件。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径，如 ~/Desktop/game.html 或 ~/Desktop/game.py"},
                "content": {"type": "string", "description": "要写入的完整文件内容（必填，不能为空）"},
            },
            "required": ["path", "content"],
        },
        handler=_handle_write_file,
    ),
    ToolDefinition(
        name="execute_python",
        server=SERVER_BUILTIN,
        tags=["code", "sandbox"],
        description="执行 Python 代码。默认沙盒隔离执行（安全）；mode=local 本地执行（可写桌面文件，无安全隔离）。",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码"},
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
                    "description": "仅 sandbox 模式：是否跳过模块安全检查",
                },
            },
            "required": ["code"],
        },
        handler=_handle_execute_python,
    ),
    ToolDefinition(
        name="execute_shell",
        server=SERVER_BUILTIN,
        tags=["code", "shell"],
        description="Shell 命令执行。默认沙盒隔离执行（安全）；mode=local 本地执行（无安全隔离）。",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell 命令"},
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
        handler=_handle_execute_shell,
    ),
    ToolDefinition(
        name="git",
        server=SERVER_BUILTIN,
        tags=["git", "code"],
        description="Git 操作 — status/add/commit/log/diff/branch/pull。在当前项目目录执行。",
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
                    "description": "git 操作",
                },
                "message": {"type": "string", "description": "commit 时的提交信息"},
                "files": {
                    "type": "string",
                    "description": "add 时的文件路径（默认全部 .）",
                },
                "count": {
                    "type": "integer",
                    "description": "log 显示的提交数（默认5）",
                },
            },
            "required": ["action"],
        },
        handler=_handle_git,
    ),
    ToolDefinition(
        name="fetch_url",
        server=SERVER_BUILTIN,
        tags=["web", "fetch"],
        description="HTTP GET 获取网页/API数据。用于抓取网页内容、调用简单 API 接口。",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标URL"},
                "max_length": {"type": "integer", "description": "最大返回字符数"},
            },
            "required": ["url"],
        },
        handler=_handle_fetch_url,
    ),
    ToolDefinition(
        name="web_search",
        server=SERVER_BUILTIN,
        tags=["web", "search"],
        description="网页搜索。支持多种搜索类型。用于获取实时信息、查找资料、收集报告数据。报告/分析类任务应优先使用此工具获取真实数据。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"},
                "num_results": {"type": "integer", "description": "结果数量（默认8）"},
                "type": {"type": "string", "enum": ["auto", "fast", "deep"], "description": "搜索类型"},
            },
            "required": ["query"],
        },
        handler=_handle_search,
    ),
    ToolDefinition(
        name="read_file",
        server=SERVER_BUILTIN,
        tags=["file", "read"],
        description="读取文件或目录。支持分页读取。用于查看文件内容、浏览目录结构。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录路径"},
                "offset": {"type": "integer", "description": "起始行号（从1开始）"},
                "limit": {"type": "integer", "description": "读取行数限制"},
            },
            "required": ["path"],
        },
        handler=_handle_read_file,
    ),
    ToolDefinition(
        name="edit_file",
        server=SERVER_BUILTIN,
        tags=["file", "edit", "write"],
        description="精确字符串替换——修改文件中特定内容。先 read_file 确认当前内容，再用 edit_file 精确定位替换（需提供足够上下文确保唯一匹配）。适合修复 bug、增删函数、修改样式，避免 write_file 重写整个文件。支持 replace_all 替换所有匹配项。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_string": {"type": "string", "description": "要替换的原始文本"},
                "new_string": {"type": "string", "description": "替换后的新文本"},
                "replace_all": {"type": "boolean", "description": "是否替换所有匹配项"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        handler=_handle_edit_file,
    ),
    ToolDefinition(
        name="search_files",
        server=SERVER_BUILTIN,
        tags=["search", "file"],
        description="搜索文件。按文件名 glob 模式搜索（pattern=*.py）或按正则表达式搜索文件内容（content_pattern=def foo）。二选一。",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob 文件名模式（如 *.py, **/*.ts）。与 content_pattern 二选一。"},
                "content_pattern": {"type": "string", "description": "文件内容正则搜索。与 pattern 二选一。"},
                "path": {"type": "string", "description": "搜索目录（默认当前目录）"},
                "include": {"type": "string", "description": "内容搜索时的文件过滤模式（如 *.py）"},
                "limit": {"type": "integer", "description": "结果数量限制（默认200）"},
            },
        },
        handler=_handle_search_files,
    ),
]


def _safe(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", raw)


class ToolRegistry:
    """工具注册表 — 10 个内置工具 + 懒加载 MCP + Agent 权限过滤"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False
        self._mcp_explored = False  # MCP 已探索过一次

    async def discover_all(self) -> List[ToolDefinition]:
        """发现所有工具来源：内置工具 + MCP 服务器（连接并注册工具）

        核心优化：
        1. 内置工具先到位（0ms），立即标记 _initialized = True
        2. MCP 21个服务器并行连接（总耗时≈最慢那个，不是累加）
        3. MCP 只探索一次，后续 discover_all 直接返回缓存
        4. 子进程超时/取消时立即清理
        """
        all_tools = list(self._tools.values())

        # Source 1: builtin tools（已有就跳过）
        if not self._initialized:
            for sd in _SANDBOX_TOOL_DEFS:
                if sd.name not in self._tools:
                    self._tools[sd.name] = sd
                    all_tools.append(sd)
            self._initialized = True
            logger.info(
                f"内置工具: {sum(1 for t in self._tools.values() if t.server=='__builtin__')} 个"
            )

        # Source 2: MCP 工具（已探索过就跳过）
        if not self._mcp_explored:
            try:
                mcp_tools = await asyncio.wait_for(
                    self._connect_mcp_servers_parallel(), timeout=12
                )
                for t in mcp_tools:
                    if t.name not in self._tools:
                        self._tools[t.name] = t
                        all_tools.append(t)
                self._mcp_explored = True
                n_mcp = sum(
                    1 for t in self._tools.values() if t.server not in ("__builtin__", "")
                )
                if n_mcp:
                    logger.info(f"MCP 工具: {n_mcp} 个")
            except asyncio.TimeoutError:
                n_partial = sum(
                    1 for t in self._tools.values() if t.server not in ("__builtin__", "")
                )
                if n_partial:
                    self._mcp_explored = True
                    logger.info(f"MCP 部分超时: {n_partial} 个工具已注册")
                else:
                    logger.warning("MCP 连接超时，无工具注册")
            except Exception as e:
                logger.debug(f"MCP 连接异常: {e}")
        else:
            # MCP 工具已有缓存，直接收集
            for t in self._tools.values():
                if t.server not in ("__builtin__", "") and t not in all_tools:
                    all_tools.append(t)

        return all_tools

    async def _discover_mcp_configs(self) -> set:
        """发现所有 MCP 服务器配置并注册到 mcp_client，返回服务器名集合"""
        from core.mcp.mcp_client import mcp_client

        proot = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        servers = set(await mcp_client.list_servers())

        # 1. 从 mcp/ 目录发现
        mcp_dir = os.path.join(proot, "mcp")
        if os.path.isdir(mcp_dir):
            for fn in sorted(os.listdir(mcp_dir)):
                if not fn.endswith("_mcp_server.py"):
                    continue
                srv = fn.replace("_mcp_server.py", "").replace("_", "-")
                if srv in servers:
                    continue
                await mcp_client.connect_server(
                    name=srv,
                    command="python3",
                    args=[os.path.join(mcp_dir, fn)],
                    cwd=proot,
                    env={"PYTHONPATH": proot},
                )
                servers.add(srv)

        # 2. 从 .mcp.json 发现
        mcj = os.path.join(proot, ".mcp.json")
        if os.path.exists(mcj):
            try:
                with open(mcj) as f:
                    for srv, sc in json.load(f).get("mcpServers", {}).items():
                        if srv in servers:
                            continue
                        await mcp_client.connect_server(
                            name=srv,
                            command=sc["command"],
                            args=sc.get("args", []),
                            cwd=proot,
                            env={"PYTHONPATH": proot},
                        )
                        servers.add(srv)
            except Exception:
                pass

        return servers

    async def _list_mcp_tools(self, srv: str) -> tuple:
        """从单个 MCP 服务器拉取工具列表（5s 超时）"""
        from core.mcp.mcp_client import mcp_client

        try:
            tools = await asyncio.wait_for(mcp_client.list_tools(srv), timeout=5.0)
            return (srv, tools)
        except asyncio.TimeoutError:
            logger.debug(f"MCP {srv}: 超时")
            return (srv, [])
        except Exception:
            logger.debug(f"MCP {srv}: 不可用")
            return (srv, [])

    async def _connect_mcp_servers_parallel(self) -> List[ToolDefinition]:
        """并行发现所有 MCP 服务器 — 21个同时连，不串行

        原来：21个 server 逐个连 → 最坏 105s
        现在：21个 server 同时连 → 最坏 ~5s
        """
        mcp_tools = []
        try:
            # 第一步：发现并注册所有 server 配置（纯内存操作，快）
            servers = await self._discover_mcp_configs()
            if not servers:
                return mcp_tools

            # 第二步：并行拉取所有 server 的工具列表
            tasks = [self._list_mcp_tools(srv) for srv in sorted(servers)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 第三步：处理结果
            seen_names = set()
            for result in results:
                if isinstance(result, Exception):
                    continue
                srv, tools = result
                if not tools:
                    continue
                for tool in tools:
                    raw = tool.get("name", "")
                    if not raw:
                        continue
                    fn = _safe(raw)
                    if fn in seen_names:
                        fn = _safe(f"{srv}_{raw}")
                    seen_names.add(fn)
                    desc = tool.get("description", "")
                    if not desc:
                        desc = f"通过 {srv} 服务器提供的工具"
                    mcp_tools.append(
                        ToolDefinition(
                            name=fn,
                            description=f"[{srv}] {desc}",
                            parameters=tool.get("inputSchema", {}) or {},
                            server=srv,
                            tool_name=raw,
                            tags=["mcp"],
                        )
                    )
        except Exception:
            pass

        if mcp_tools:
            logger.info(
                f"MCP: {len(mcp_tools)} 个工具来自 {len({t.server for t in mcp_tools})} 台服务器"
            )
        return mcp_tools

    def get_handler_map(self) -> Dict[str, Callable]:
        result = dict(_HANDLER_MAP)
        for n, td in self._tools.items():
            if td.handler and n not in result:
                result[n] = td.handler
        return result

    def get_handler(self, name: str) -> Optional[Callable]:
        h = _HANDLER_MAP.get(name)
        if h:
            return h
        td = self._tools.get(name)
        if td and td.handler:
            return td.handler
        # MCP 工具：通过 MCP client 代理执行
        if td and td.server and td.tool_name and td.server not in ("", SERVER_BUILTIN):
            srv = td.server
            tname = td.tool_name

            async def _mcp_handler(args: dict) -> str:
                from core.mcp.mcp_client import mcp_client

                result = await mcp_client.call_tool(srv, tname, args)
                if isinstance(result, str) and result.startswith("❌"):
                    raise RuntimeError(result)
                return result

            return _mcp_handler
        return None

    async def get_tools_for_task(
        self,
        task: str,
        max_tools=20,
        allowed: Optional[List[str]] = None,
        disallowed: Optional[List[str]] = None,
    ) -> List[ToolDefinition]:
        """获取工具列表，应用 Agent 类型的 allowed/disallowed 约束

        不再做领域分类/评分排序/条件保留——让 LLM 靠工具 description 自主选工具。
        只做：
        1. 所有工具返回
        2. Agent 类型硬约束：allowed 白名单 + disallowed 黑名单
        """
        if not self._initialized:
            return list(self._tools.values())[:max_tools]

        all_tools = list(self._tools.values())

        # Agent 类型硬约束过滤
        if allowed is not None:
            allowed_set = set(allowed)
            all_tools = [t for t in all_tools if t.name in allowed_set]
        if disallowed is not None:
            disallowed_set = set(disallowed)
            all_tools = [t for t in all_tools if t.name not in disallowed_set]

        return all_tools[:max_tools]

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
        mcp_count = sum(1 for s in by_server if s not in ("__builtin__", "__mcp__", ""))
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
        return bool(t and t.server not in ("__builtin__", "__mcp__", ""))

    def validate_arguments(self, name: str, args: Dict) -> tuple:
        t = self._tools.get(name)
        if not t:
            return False, "未知工具"
        p = t.parameters
        if not p:
            return True, ""
        props = p.get("properties", {})
        req = p.get("required", [])
        for f in req:
            if f not in args:
                return False, f"缺少 {f}"
        for k, v in list(args.items()):
            if k in props:
                pt = props[k].get("type", "")
                if pt == "string" and not isinstance(v, str):
                    args[k] = str(v)
                elif pt in ("integer", "number") and isinstance(v, str):
                    try:
                        args[k] = int(v) if pt == "integer" else float(v)
                    except:
                        return False, f"{k} 不能从 {v} 转换"
        return True, ""

    @property
    def count(self) -> int:
        return len(self._tools)


_registry = None


def get_tool_registry() -> "ToolRegistry":
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
