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
from core.multi_agent_v2.prompts import get_builder
_builder = get_builder()


# ── ToolSets — 工具集分组层（对齐 hermes-agent toolsets.py）──
# 与 SKILL 角色解耦：工具按"编组"而非"角色"启用，按平台/来源 session 动态选择。
# 默认全量暴露（OpenCode 哲学），工具集只做"按平台裁剪"的兜底，不做硬白名单剪枝。
_CORE_TOOLSET = {
    "__builtin__": {
        "web_search", "web_extract", "fetch_url", "read_file", "write_file",
        "patch", "edit_file", "search_files", "execute_python", "execute_shell",
        "git", "task", "orchestrate", "write_todos",
    },
}
# 平台 → 附加/裁剪工具集（对齐 hermes _load_enabled_toolsets(platform)）
_PLATFORM_TOOLSET = {
    "cli": set(),                     # CLI 全量
    "web": set(),                     # Web 端全量
    "desktop": set(),                 # Desktop 全量
    "sandbox": {"execute_shell"},     # 沙盒：默认禁 shell
}


def _resolve_enabled_toolsets(platform: str = "") -> set:
    """返回指定平台启用的工具集（工具名集合）。空 platform = 全量。"""
    if not platform:
        return set()
    # 平台特定裁剪：sandbox 等返回应禁用的工具
    return _PLATFORM_TOOLSET.get(platform, set())


def _apply_toolset_filter(all_tools, platform: str = "") -> list:
    """按平台工具集裁剪工具列表。platform 为空时不裁剪（全量暴露）。"""
    if not platform:
        return all_tools
    disabled = _resolve_enabled_toolsets(platform)
    if not disabled:
        return all_tools
    return [t for t in all_tools if t.name not in disabled]


# ── 沙盒管理器（由 run_react 设置，用于 write_file 路径重定向）──
_active_sandbox_manager = None

def set_active_sandbox_manager(mgr) -> None:
    global _active_sandbox_manager
    _active_sandbox_manager = mgr

def get_active_sandbox_manager():
    return _active_sandbox_manager

def clear_active_sandbox_manager() -> None:
    global _active_sandbox_manager
    _active_sandbox_manager = None

logger = logging.getLogger(__name__)

SERVER_BUILTIN = "__builtin__"

# ── 文件写入去重注册表 ──
# key: 规范化路径, value: {content: str, count: int}
# 用于防止同路径反复写入导致无限循环
_written_file_registry: Dict[str, Dict] = {}
_file_read_cache: Dict[str, str] = {}  # ponytail: path→content, 避免重复读取同一文件


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
    """HTTP GET — 使用 aiohttp，自动跟随重定向

    修复 #057 (原 SSL 静默降级漏洞):
    - SSL 验证失败不再静默 → 记录 warning 并返回明确错误
    - 禁用验证的回退改为 opt-in（XIAOLEI_ALLOW_INSECURE_SSL=1），
      且回退时必须打 warning，让 MITM 风险对运维可见
    """
    import aiohttp
    import ssl as _ssl

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/json,*/*",
    }

    # 第一次尝试：SSL 验证开启（默认，安全）
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
    except (aiohttp.ClientConnectorError, aiohttp.ClientOSError, _ssl.SSLError) as e:
        # 修复 #057: 不再 pass——SSL 失败要让运维看到
        logger.warning(f"fetch_url SSL/连接失败 ({type(e).__name__}): {url}: {e}")

    # 回退路径：仅在显式 opt-in 时禁用 SSL 验证重试（默认关闭）
    # 修复 #057: 原 default 开启 → 任何中间人可伪造证书窃听/篡改 HTTPS 内容
    if os.environ.get("XIAOLEI_ALLOW_INSECURE_SSL", "").lower() in ("1", "true"):
        logger.warning(
            f"⚠️ INSECURE: 已按 XIAOLEI_ALLOW_INSECURE_SSL 禁用 SSL 验证重试: {url} "
            f"(此连接可能被中间人攻击)"
        )
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
        except Exception as e:
            logger.warning(f"fetch_url insecure 回退也失败: {url}: {e}")

    # 默认路径：SSL 失败即失败——不静默降级到禁用验证
    # 调用方（_try_json/_search_one/_handle_fetch_url）均按 str 消费并有空值兜底，
    # 返回空串 + 异常标记注释，让上层走各自的 err() 分支
    logger.error(f"fetch_url 彻底失败 (SSL 验证开启): {url}")
    return ""


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
                # ponytail + deepseek: additionalContext — 告诉 agent 数据全貌（条数、摘要）
                _ex = (
                    f"fetch_url 从 {url} 抓取到 {len(hot_items)} 条热搜/榜单条目。"
                    f"已展示前 20 条，如需全部请参考全部 {len(hot_items)} 条的 prev 文本。"
                )
                return ok(preview, extra_contexts=[_ex])
            # 通用 JSON
            text_repr = json.dumps(parsed, ensure_ascii=False, indent=2)
            if len(text_repr) > ml:
                text_repr = text_repr[:int(ml * 0.7)] + f"\n...截断 ({len(text_repr)} 字符)"
            # ponytail + deepseek: additionalContext — JSON 数据大小 + 截断提示
            _ex = f"fetch_url 从 {url} 返回 JSON 数据 {len(text_repr)} 字符（原始可能更长）。已展示在 data 中。"
            return ok(text_repr, extra_contexts=[_ex])
        except (json.JSONDecodeError, AttributeError):
            pass
        return ok(je[:ml])

    # 2. 纯 HTML → 直接转换为可读文本
    readable = html_to_text(text, max_length=ml)
    if not readable or len(readable) < 20:
        return err("无法解析页面内容")
    # ponytail + deepseek: additionalContext — 告诉 agent 看到的是页面截断版
    _ex = f"fetch_url 从 {url} 抓取页面 {len(readable)} 字符正文，已展示。如需更多细节再追加 fetch。"
    return ok(readable, extra_contexts=[_ex])





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
    async def _fetch_source(name: str, display_name: str, url: str):
        data = await _try_json(
            url,
            parser=lambda t, dn=display_name: _format_hot_list(t, dn),
        )
        if data:
            sources.append(data)

    tasks = [_fetch_source(name, display_name, url) for name, display_name, url in ordered_sources]
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
                                    line += f" — {desc[:150]}"
                                items.append(line)
                    if items:
                        return f"【{source_name}】\n" + "\n".join(items[:15])

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
                            line += f" — {desc[:150]}"
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

    # 三引擎并发（超时从8秒提升到15秒，每引擎重试2次）
    engines = [
        ("Bing", f"https://cn.bing.com/search?q={encoded}&count=10", extract_search_results_bing),
        ("百度", f"https://www.baidu.com/s?wd={encoded}&rn=10", extract_search_results_baidu),
        ("DuckDuckGo", f"https://html.duckduckgo.com/html/?q={encoded}", extract_search_results_ddg),
    ]

    sources = []

    async def _search_one(name: str, url: str, parser):
        for attempt in range(2):
            try:
                # 修复 REAL-BUG: 单个引擎超时/失败不能拖死其它引擎。
                # 原实现 _http_get(timeout=25) 对 DDG(被墙) 每次 25s×2次重试,
                # 且 asyncio.gather 等最慢的 → 其它引擎(Bing成功)的结果被拖到 40s+,
                # 表现为 CLI "Thinking…卡住"。
                # 改为: 每引擎 wait_for 上限(默认 8s), 失败立即放弃该引擎, 不阻塞其余。
                html = await asyncio.wait_for(_http_get(url, timeout=8), timeout=9)
                results = parser(html)
                if results:
                    sources.append((name, results))
                    return
            except (asyncio.TimeoutError, Exception):
                if attempt == 0:
                    await asyncio.sleep(1)
                # 失败/超时直接放弃本引擎, 不继续重试拖时间

    # return_exceptions=True: 任何引擎抛异常/超时都不会中断 gather, 也不等最慢引擎
    await asyncio.gather(
        *[_search_one(n, u, p) for n, u, p in engines],
        return_exceptions=True,
    )

    if not sources:
        # 兜底：重试百度
        try:
            html = await _http_get(f"https://www.baidu.com/s?wd={encoded}&rn=10", timeout=20)
            results = extract_search_results_baidu(html)
            if results:
                sources.append(("百度(重试)", results))
        except Exception:
            pass

    if not sources:
        return err("搜索暂不可用（所有搜索引擎均超时）。请使用 fetch_url 工具手动获取数据：fetch_url(url='https://www.baidu.com/s?wd=查询关键词&rn=10', max_length=80000)")

    merged = merge_search_results(sources)

    # ── 检测安全验证/验证码页面（LLM + 关键词兜底）──
    _is_captcha = False
    try:
        from core.engine.llm_backend import get_llm_router
        _router = get_llm_router()
        if _router and _router.is_available():
            _resp = await _router.simple_chat(
                f"以下网页内容是否包含安全验证/captcha/反爬检测？只回答'是'或'否'\n\n{merged[:2000]}",
                temperature=0, max_tokens=10
            )
            _is_captcha = _resp and '是' in str(_resp)
    except Exception:
        pass
    if not _is_captcha:
        _captcha_keywords = ["百度安全验证", "安全验证", "网络不给力", "请稍后重试", "验证码", "captcha",
                             "Verify you are human", "unusual traffic", "Please confirm"]
        _is_captcha = any(kw in merged for kw in _captcha_keywords)
    if _is_captcha:
        logger.warning(f"搜索结果包含验证码/安全验证，丢弃: {merged[:100]}")
        return err("搜索引擎返回验证码页面，无法获取搜索结果。请使用 fetch_url 直接访问目标网址获取数据。")

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
    from core.multi_agent_v2.tools.tool_result import ok, err
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
        confirmed = args.get("confirmed", True)
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
                    "result": {"content": [{"text": f"[沙盒] ✅ 执行成功(退出码 {sr.exit_code})\n{full}"}]}
                }
            # 沙盒执行失败，提示用 mode=local 重试
            return {
                "result": {
                    "content": [
                        {
                            "text": f"[沙盒] ❌ 执行失败: {sr.error_message or sr.stderr or (f'退出码 {sr.exit_code}（无 stderr；grep类无匹配返回1属正常）' if sr.exit_code == 1 else '未知错误')}"
                            f"\n\n💡 沙盒是隔离环境（cwd=/tmp/agent_sandbox，HOME 重定向）："
                            f"\n• 访问项目文件请用【绝对路径】，或直接设置 mode=local 在项目目录本地执行："
                            f"execute_shell(command=..., mode='local')"
                            f"\n• 包含 pipe(|)、分号(;)、重定向(>) 的命令现在沙盒也支持，失败通常是文件路径问题"[:5000]
                        }
                    ]
                }
            }
        except Exception as e:
            return {
                "result": {
                    "content": [{"text": f"[沙盒] ❌ {type(e).__name__}: {e}"
                                 f"\n\n💡 提示：如果命令需要 pipe/重定向，请设置 mode=local"[:3000]}]
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


async def _handle_write_todos(args: Dict, ctx=None) -> Dict:
    """write_todos — agent 自主声明计划与进度（deepseek-harness update_goal 等价物）。

    接线语义：
    - todos 按 content 模糊匹配 ctx.plan 步骤，同步状态（completed→done, in_progress→running）
    - 全部 completed → 记录 agent 完成声明（产出型任务仍需交付物证据门控）
    - 无 ctx（测试/无计划上下文）时退化为纯确认
    """
    from core.multi_agent_v2.tools.tool_result import ok
    todos = args.get("todos", [])
    if not todos:
        return ok("todos 为空")

    done = sum(1 for t in todos if t.get("status") == "completed")

    # ── 同步到计划步骤（模糊匹配 content）──
    _synced = 0
    if ctx is not None and getattr(ctx, 'plan', None):
        for t in todos:
            content = (t.get("content") or "").strip()
            status = t.get("status") or "pending"
            if len(content) < 4:
                continue
            for step in ctx.plan:
                d = (step.description or "")
                if content[:12] in d or d[:12] in content:
                    if status == "completed" and step.status != "done":
                        step.status = "done"
                        _synced += 1
                    elif status == "in_progress" and step.status == "pending":
                        step.status = "running"
                    break

    # ── agent 完成声明（evidence gate 在主循环：产出型任务仍需交付物验证）──
    all_completed = done == len(todos) and len(todos) > 0
    if ctx is not None and all_completed:
        ctx._agent_claims_complete = True
        logger.info("write_todos: agent claims all todos completed")

    _plan_note = f"，已同步 {_synced} 个计划步骤" if _synced else ""
    return ok(f"✅ 任务清单已更新 ({done}/{len(todos)} 完成){_plan_note}")


async def _handle_update_goal(args: Dict, ctx=None) -> Dict:
    """update_goal — agent 自主声明目标状态（deepseek-harness update_goal 工具对齐）。

    完成判定权在 agent：complete/blocked 由 LLM 主动声明，系统只校验证据。
    - complete → ctx._agent_declared_complete（主循环校验交付物证据后收尾）
    - blocked  → ctx._blocked_streak（同因连续 3 轮 → 系统接受阻塞并收尾）
    - progress → ctx._goal_progress_note（进度备注，注入上下文）
    """
    from core.multi_agent_v2.tools.tool_result import ok, err
    action = (args.get("action") or "").strip().lower()
    reason = (args.get("reason") or "").strip()

    if ctx is None:
        # 无运行上下文（测试/独立调用）→ 纯确认
        return ok(f"goal 状态声明已记录: {action or '(空)'}")

    if action == "complete":
        ctx._agent_declared_complete = True
        ctx._agent_complete_reason = reason[:300]
        logger.info("update_goal: agent declares COMPLETE（等待交付物证据校验）")
        return ok("✅ 完成声明已记录。系统将校验交付物证据；若交付物未写入磁盘将被驳回。")

    if action == "blocked":
        prev = getattr(ctx, "_blocked_reason", "") or ""
        if reason and reason[:80] == prev[:80]:
            ctx._blocked_streak = getattr(ctx, "_blocked_streak", 0) + 1
        else:
            ctx._blocked_streak = 1
        ctx._blocked_reason = (reason or "未说明原因")[:300]
        streak = ctx._blocked_streak
        logger.info(f"update_goal: agent declares BLOCKED x{streak}: {ctx._blocked_reason[:80]}")
        if streak >= 3:
            return ok(f"⚠️ 阻塞声明已接受（连续 {streak} 轮相同阻塞），系统将收尾并保留进度。")
        return ok(f"⚠️ 阻塞声明已记录（{streak}/3）。系统将注入绕行指引；连续 3 轮相同阻塞才会被接受。")

    if action == "progress":
        ctx._goal_progress_note = reason[:200]
        return ok("📝 进度已记录")

    return err(f"未知 action: {action or '(空)'}（可选: complete / blocked / progress）")


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
        # 修复 #069: aggressive_unescape=True 会把合法的 \\n 字面量也"修正"，
        # 可能破坏含正则/转义序列的 Python 代码。改为 False（保守模式）：
        # 只在检测结果"明显是 LLM 双重转义"时才修正，不再激进替换。
        content = ensure_correct_content(content, aggressive_unescape=False)
        
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

        # ── 跨平台路径修复 ──
        _actual_desktop = os.path.expanduser("~/Desktop")
        import re as _re

        # 情况 A: Linux 风格 /home/user/Desktop/ 或 /root/Desktop/ → 修正为实际桌面路径
        _linux_desktop_match = _re.match(r'^/(?:home/[^/]+|root)/Desktop(/.*)?$', path)
        if _linux_desktop_match:
            _rest = _linux_desktop_match.group(1) or ""
            path = _actual_desktop + _rest
            logger.info(f"write_file: 修正跨平台路径 (Linux→macOS): {path}")

        # 情况 B: LLM 用了 `/Users/username/Desktop/` 但 username 不对时
        _user_desktop_match = _re.match(r'^/Users/[^/]+/Desktop(/.*)?$', path)
        if _user_desktop_match and not path.startswith(_actual_desktop):
            _rest = _user_desktop_match.group(1) or ""
            path = _actual_desktop + _rest
            logger.info(f"write_file: 修正路径（用户名不正确→实际桌面）: {path}")

        # ── 沙盒路径重定向（如果当前 task 有活动的 SandboxManager）──
        _sb = get_active_sandbox_manager()
        _original_path = path  # ponytail: 保留原始路径用于写后导出
        if _sb:
            new_path = _sb.redirect_path(path)
            if new_path != path:
                logger.info(f"沙盒重定向: {path} → {new_path}")
                path = new_path

        # ── Worktree 路径重定向（子 Agent 隔离写入）──
        try:
            from core.multi_agent_v2.infrastructure.worktree_isolator import get_active_worktree
            _wt = get_active_worktree()
            if _wt:
                wt_path = _wt.resolve_path(path)
                if wt_path != path:
                    logger.info(f"worktree 重定向: {path} → {wt_path}")
                    path = wt_path
        except ImportError:
            pass

        # ── 同路径写入去重 ──
        registry = _written_file_registry
        prev = registry.get(path)
        if prev:
            if prev.get("content") == content:
                return ok(f"✅ 文件内容相同，无需写入: {path}")
            prev["count"] = prev.get("count", 1) + 1
            # ponytail: 同路径第 10 次写入才拦截，防止 stub 检测+迭代写入循环过早阻断
            if prev["count"] >= 10:
                return err(f"❌ 反复写入被拦截: {path} (已写入 {prev['count']} 次)")
        else:
            registry[path] = {"content": content, "count": 1}

        # ── 重复文件检测：检查桌面上是否已存在类似的文件 ──
        force = args.get("force", True)
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
        force = args.get("force", True)  # ponytail: 默认覆盖，Agent 无需传 force=true
        
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

        # ponytail: 沙盒重定向后，将文件复制到原始路径
        if _sb and _original_path and path != _original_path:
            try:
                _export_dir = os.path.dirname(os.path.expanduser(_original_path))
                os.makedirs(_export_dir, exist_ok=True)
                import shutil as _shutil
                _shutil.copy2(str(path), os.path.expanduser(_original_path))
                logger.info(f"沙盒文件已导出到原始路径: {_original_path}")
                # 更新 path 为原始路径，让后续验证和消息使用正确路径
                path = _original_path
            except Exception as _ex:
                logger.warning(f"沙盒文件导出失败 {_original_path}: {_ex}")
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

        # ponytail + deepseek: 把写入内容摘要作为 additionalContext 注入下一轮 LLM 输入。
        # 真实测试（人机对决）：write_file 后 agent 不知自己写了什么 → 无法修改。摘要让 agent 看见。
        _head = content[:500]
        _tail = content[-300:] if len(content) > 800 else ""
        _extra = (
            f"write_file 已落盘 {path}（{len(content)} 字符）。"
            f"开头摘要：{_head}"
            + (f"\n…\n结尾摘要：{_tail}" if _tail else "")
        )
        return ok(result_msg, extra_contexts=[_extra])
    except Exception as e:
        return err(f"❌ 写入失败: {type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════════
# 迁移工具：原 register_new_tools.py 中的工具（原生 async 实现）
# ═══════════════════════════════════════════════════════════════════

async def _handle_read_file(args: Dict) -> Dict:
    """读取文件或目录 — 支持分页 + 重复读取警告"""
    from core.multi_agent_v2.tools.tool_result import ok, err

    path = args.get("path", "")
    if not path:
        return err("需要 path 参数")
    path = os.path.expanduser(path)
    p = Path(path)
    if not p.exists():
        # ponytail + deepseek: 失败回流附加具体可行的修复指引
        _siblings = ""
        try:
            _parent = p.parent
            if _parent.exists():
                _names = [e.name for e in sorted(_parent.iterdir())[:20] if p.name.lower() in e.name.lower() or len(e.name) <= 4]
                if _names:
                    _siblings = f"\n同目录下相近文件：{', '.join(_names[:8])}"
        except Exception:
            pass
        return err(
            f"路径不存在: {path}\n"
            f"可能：文件名拼写错误 / 工作目录不对（用 execute_shell pwd 检查）/ 文件确实未创建。"
            f"{_siblings}"
        )

    # ── 重复读取检测 ──
    if not hasattr(_handle_read_file, '_read_count'):
        _handle_read_file._read_count = {}
        _handle_read_file._unique_files = set()
    _counts = _handle_read_file._read_count
    _unique = _handle_read_file._unique_files
    _key = str(p.resolve())
    _counts[_key] = _counts.get(_key, 0) + 1
    _unique.add(_key)
    repeat_hint = ""
    if _counts[_key] >= 3:
        repeat_hint = f"\n\n⚠️ 此文件已读取 {_counts[_key]} 次。不要再重读了，数据已足够。"

    if p.is_dir():
        entries = sorted(p.iterdir())[:args.get("limit", 200)]
        lines = [f"{'📁' if e.is_dir() else '📄'} {e.name}" for e in entries]
        return ok(f"目录 {path} ({len(entries)} 项):\n" + "\n".join(lines) + repeat_hint)

    # ponytail: 项目分析缓存拦截
    try:
        from core.multi_agent_v2.tools.cache import is_file_cached
        if is_file_cached(path) and args.get("offset", 1) == 1:
            return ok(f"[CACHED] '{path}' 的内容已在上面提供。继续分析，不要再读这个文件。{repeat_hint}")
    except Exception:
        pass

    try:
        # ponytail: 特殊文件防挂 — FIFO/socket/dev path read() 会永远阻塞
        import stat as _stat
        _mode = p.stat().st_mode
        if _stat.S_ISFIFO(_mode) or _stat.S_ISSOCK(_mode) or not _stat.S_ISREG(_mode):
            return err(f"非常规文件 (fifo/socket/device): {path} — read_file 不支持，请用 execute_shell cat 配合超时，或 os.read")

        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # ponytail: 二进制/非 UTF-8 → 明确拒绝, 不把字节流塞进 LLM
        try:
            size = p.stat().st_size
            head = p.read_bytes()[:8]
            _hex = head.hex()
        except Exception:
            size, _hex = -1, ""
        return err(f"无法按文本解码文件: {path} (可能是二进制, 头部字节 {_hex}, {size}B)。如需 inspect 二进制, 用 execute_shell 配合 xxd/file 命令")
    lines = text.split("\n")
    offset = max(0, args.get("offset", 1) - 1)
    limit = args.get("limit", 2000)
    # ponytail: offset 越界 — 返回明确提示而非空数据 + ok=True (LLM 无法判断是否挂)
    # test_readtool_adversarial::test_read_past_eof_informative 守卫
    if offset >= len(lines):
        return err(
            f"offset={offset+1} 超出文件 EOF（共 {len(lines)} 行）。\n"
            f"提示: 用 offset={max(1, len(lines) - 100)} 读取末尾 100 行, 或不传 offset 从头读。"
        )
    page = lines[offset:offset + limit]
    result = "\n".join(page)
    if offset > 0 or offset + limit < len(lines):
        result = f"(行 {offset+1}-{min(offset+limit, len(lines))}/{len(lines)})\n{result}"

    # ── 进度信息 ──
    progress = f"\n\n📊 已读取 {len(_unique)} 个不同文件（共 {sum(_counts.values())} 次调用）"
    result = result + progress + repeat_hint

    # ponytail + deepseek: 截断时给 agent 后续探索指引（additionalContext）
    _extras = []
    if offset + limit < len(lines):
        _next_offset = offset + limit + 1
        _extras.append(
            f"read_file 显示了第 {offset+1}-{offset+limit} 行 / 共 {len(lines)} 行。"
            f"如需后续内容，用 offset={_next_offset} 继续读，或用更大的 limit 参数。"
        )
    return ok(result, extra_contexts=_extras if _extras else None)


async def _handle_edit_file(args: Dict) -> Dict:
    """智能文本替换 — 9级模糊匹配（edit.py SmartEditor）+ 精确替换安全网

    2026-09-10 修复"功能断裂": edit.py 的 SmartEditor 有完整 9 级匹配引擎
    （fuzzy/indentation/line_number/...）但从未被 _handle_edit_file 调用过，
    导致编辑能力只有 20 行的 text.count() 精确替换 — 缩进/typo/空白差异全被拒。
    现接线: 先 SmartEditor.auto 匹配, 异常/未命中时降级为原精确替换保底。
    """
    import difflib
    from core.multi_agent_v2.tools.tool_result import err

    path = args.get("path", "")
    old = args.get("old_string", "")
    new = args.get("new_string", "")
    replace_all = args.get("replace_all", False)
    if not path or not old:
        return err("需要 path 和 old_string 参数")
    path = os.path.expanduser(path)
    # ── Worktree 路径重定向 ──
    try:
        from core.multi_agent_v2.infrastructure.worktree_isolator import get_active_worktree
        _wt = get_active_worktree()
        if _wt:
            wt_path = _wt.resolve_path(path)
            if wt_path != path:
                logger.info(f"worktree 重定向: {path} → {wt_path}")
                path = wt_path
    except ImportError:
        pass
    p = Path(path)
    if not p.exists():
        return err(f"文件不存在: {path}")
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return err(f"无法解码文件: {path}")

    # ── 主路径: SmartEditor 9 级模糊匹配 ──
    # ponytail: 多处匹配守卫必须在 SmartEditor 之前 — 它只改第一个,
    # 会静默改错位置（test_multiple_matches_no_replace_all 回归守卫）。
    # ponytail2: replace_all 与 SmartEditor 单点匹配语义冲突 → 走精确。
    if not replace_all:
        _n_matches = text.count(old)
        if _n_matches > 1:
            return err(f"找到 {_n_matches} 处匹配，请设置 replace_all=true 或提供更多上下文")
        try:
            from core.multi_agent_v2.tools.edit import SmartEditor
            editor = SmartEditor(file_path=str(p))
            editor.load(str(p))
            er = await editor.edit(old_text=old, new_text=new, strategy="auto")
            if er.success:
                # ponytail: SmartEditor 是内存编辑 — save() 才落盘
                editor.save(str(p))
                # diff: 用 er 自带, 或从内存读取新内容做 unified_diff
                rel_path = p.relative_to(Path.cwd()) if p.is_relative_to(Path.cwd()) else p
                fdata = editor.original_content or ""
                diff = getattr(er, "diff", "") or "\n".join(difflib.unified_diff(
                    text.splitlines(), fdata.splitlines(),
                    fromfile=str(rel_path), tofile=str(rel_path) + " (edited)", lineterm="",
                ))
                return {
                    "ok": True,
                    # ponytail: 文案保留"成功"字眼 — e2e_improvements 契约
                    # assert "成功" in from_handler(edit_result)，data 前缀变化会破坏它
                    "data": f"成功: ✓ 编辑完成 ({er.strategy.value if hasattr(er, 'strategy') else 'match'})",
                    "diff": diff,
                    "strategy": er.strategy.value if hasattr(er, "strategy") else "auto",
                }
            # SmartEditor 明确失败 → 落到下方精确替换保底
            logger.debug(f"SmartEditor 未命中 ({getattr(er, 'error', '')}), 降级精确替换")
        except Exception as _e:
            logger.debug(f"SmartEditor 异常降级: {_e}")

    # ── 保底: 原精确替换语义 ¬ replace_all 或 fuzzy 引擎不可用时 ──
    count = text.count(old)
    if count == 0:
        return err("old_string 未在文件中找到 (SmartEditor 模糊与精确替换均未命中)")
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


async def _handle_arbor_viz(args: Dict) -> Dict:
    """ARBOR 假设树可视化 — 委托给 arbor_viz 模块"""
    from core.multi_agent_v2.tools.arbor_viz import handle_arbor_viz
    return await handle_arbor_viz(args)


async def _handle_text_analyzer(args: Dict) -> Dict:
    """文本分析 — 基于 LLM 的深度文本理解"""
    from core.multi_agent_v2.tools.tool_result import ok, err

    text = args.get("text", "")
    if not text:
        return err("需要 text 参数")

    # ponytail: 最小实现，直接调 LLM 做文本分析
    try:
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()

        system_prompt = (
            "你是文本分析专家。对给定文本进行深入分析，输出：\n"
            "1. 主题/主旨（一句话概括）\n"
            "2. 关键信息点（3-5个要点）\n"
            "3. 文本类型（文章/代码/对话/数据/其他）\n"
            "4. 情感倾向（正面/负面/中性）\n"
            "5. 简短摘要（50字内）\n\n"
            "用中文回答，格式清晰简洁。"
        )
        # ponytail: 截断超长文本，防止 token 爆炸
        truncated = text[:3000] if len(text) > 3000 else text
        response = await router.simple_chat(
            user_message=f"请分析以下文本：\n\n{truncated}",
            system_prompt=system_prompt,
            temperature=0.3,
        )
        if response:
            return ok(response)
        return err("LLM 无响应")
    except Exception as e:
        return err(f"文本分析失败: {e}")


async def _handle_search_history(args: Dict, ctx=None) -> Dict:
    """全量对话账本搜索 — Hermes 式"翻老账本"

    账本 append-only 存所有对话原文（STM 压缩撕掉的页这里都有）。
    被问"上次/之前说了什么"时用这个，不要靠 STM 注入猜。
    """
    from core.multi_agent_v2.tools.tool_result import ok, err
    from core.memory.conversation_ledger import search_or_fallback, recent, stats, format_hits

    action = args.get("action", "search")
    # user_id 与记忆链路同门: 优先运行时 ctx.user_id（run_react #003 透传），
    # 再退环境缺省 default_user（写读同门）
    user_id = str(args.get("user_id", "") or "")
    if not user_id and ctx is not None:
        user_id = str(getattr(ctx, 'user_id', '') or '')
    if not user_id:
        user_id = "default_user"

    try:
        if action == "search":
            query = str(args.get("query", ""))
            if not query.strip():
                return err("需要 query 参数（关键词，多词空格分隔=AND）")
            # 参考 Hermes: AND 无结果时内置 OR 降级（agent 不用学 OR 语法）
            hits = search_or_fallback(query, user_id,
                                      limit=int(args.get("limit", 10)),
                                      role=str(args.get("role", "") or ""))
            return ok(format_hits(hits, query=query))
        elif action == "recent":
            items = recent(user_id, limit=int(args.get("limit", 20)),
                           session_id=str(args.get("session_id", "") or ""))
            return ok(format_hits(items))
        elif action == "stats":
            return ok(f"账本概况: {stats(user_id)}")
        else:
            return err(f"未知 action: {action}（可用: search/recent/stats）")
    except Exception as e:
        return err(f"账本查询失败: {e}")


async def _handle_skill(args: Dict) -> Dict:
    """Load skill content by name — OpenCode-style on-demand skill loading"""
    from core.multi_agent_v2.tools.tool_result import ok, err
    from core.multi_agent_v2.skills.skill_loader import discover_skills

    name = args.get("name", "")
    if not name:
        return err("需要 name 参数")

    skills = discover_skills()
    if name not in skills:
        available = ", ".join(sorted(skills.keys()))
        return err(f"Skill '{name}' 未找到。可用: {available}")

    s = skills[name]
    output = (
        f"<skill_content name=\"{s.name}\">\n"
        f"{s.content}\n"
        f"</skill_content>\n\n"
        f"Base directory for this skill: {os.path.dirname(s.location)}"
    )
    return ok(output)


async def _handle_task(args: Dict) -> Dict:
    """OpenCode-style task tool — spawn single sub-agent"""
    from core.multi_agent_v2.tools.tool_result import ok, err
    from core.multi_agent_v2.agents.subagent.spawn import spawn_subagent
    from core.multi_agent_v2.agents.subagent.types import AgentProfile

    description = args.get("description", "")
    subagent_type = args.get("subagent_type", "general")
    prompt = args.get("prompt", description)

    if not prompt:
        return err("需要 description 或 prompt 参数")

    try:
        profile = AgentProfile(subagent_type)
    except ValueError:
        return err(f"未知代理类型: {subagent_type}。可用: {[p.value for p in AgentProfile]}")

    result = await spawn_subagent(
        task_description=prompt,
        profile=profile,
    )
    if result.get("success"):
        return ok(f"[子代理 {result.get('session_id', '?')}] {result.get('output', '')}")
    return err(f"子代理失败: {result.get('error', '未知错误')}")


async def _handle_orchestrate(args: Dict) -> Dict:
    """OpenCode-style orchestrate tool — DAG parallel sub-agents"""
    from core.multi_agent_v2.tools.tool_result import ok, err
    from core.multi_agent_v2.agents.subagent.spawn import orchestrate_subagents

    tasks = args.get("tasks", [])
    max_concurrent = args.get("max_concurrent", 5)

    if not tasks:
        return err("需要 tasks 参数")

    result = await orchestrate_subagents(
        tasks=tasks,
        max_concurrent=max_concurrent,
    )
    if result.get("success"):
        outputs = []
        for r in result.get("results", []):
            status = "✓" if r.get("success") else "✗"
            _out = r.get("output", "")
            if len(_out) > 500:
                _out = _out[:300] + "\n\n[... 中间部分省略 — 总长 " + str(len(_out)) + " 字符 ...]\n\n" + _out[-200:]
            outputs.append(f"[{r.get('id', '?')}] {status} {_out}")
        return ok("\n".join(outputs))
    return err(f"编排失败: {result.get('error', '未知错误')}")


# ═══════════════════════════════════════════════════════════════════
# 子代理工具 Handlers — 已移至上方 task/orchestrate
# ═══════════════════════════════════════════════════════════════════




_SANDBOX_TOOL_DEFS = [
    ToolDefinition(
        name="write_todos",
        server=SERVER_BUILTIN,
        tags=["task", "tracking"],
        description=_builder.get_tool_desc("write_todos"),
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
        handler=_handle_write_todos,
    ),
    ToolDefinition(
        name="update_goal",
        server=SERVER_BUILTIN,
        tags=["task", "tracking"],
        description=_builder.get_tool_desc("update_goal"),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["complete", "blocked", "progress"],
                    "description": "目标状态声明: complete=已完成, blocked=被阻塞, progress=进度备注"
                },
                "reason": {
                    "type": "string",
                    "description": "complete=1-3句总结; blocked=具体阻塞条件(什么/为什么,而非'难度'或'剩余工作'); progress=简短状态"
                }
            },
            "required": ["action", "reason"]
        },
        handler=_handle_update_goal,
    ),
    ToolDefinition(
        name="write_file",
        server=SERVER_BUILTIN,
        tags=["file", "write"],
        description=_builder.get_tool_desc("write_file"),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径，如 ~/Desktop/game.html"},
                "content": {"type": "string", "description": "文件的完整内容（必填，不能为空，不能截断）"},
            },
            "required": ["path", "content"],
        },
        handler=_handle_write_file,
    ),
    ToolDefinition(
        name="execute_python",
        server=SERVER_BUILTIN,
        tags=["code", "sandbox"],
        description=_builder.get_tool_desc("execute_python"),
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
        handler=_handle_execute_python,
    ),
    ToolDefinition(
        name="execute_shell",
        server=SERVER_BUILTIN,
        tags=["code", "shell"],
        description=_builder.get_tool_desc("execute_shell"),
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
        handler=_handle_execute_shell,
    ),
    ToolDefinition(
        name="git",
        server=SERVER_BUILTIN,
        tags=["git", "code"],
        description=_builder.get_tool_desc("git"),
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
        handler=_handle_git,
    ),
    ToolDefinition(
        name="fetch_url",
        server=SERVER_BUILTIN,
        tags=["web", "fetch"],
        description=_builder.get_tool_desc("fetch_url"),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL（自动升级 HTTP → HTTPS）"},
                "max_length": {"type": "integer", "description": "最大返回字符数，不设则返回全部"},
            },
            "required": ["url"],
        },
        handler=_handle_fetch_url,
    ),
    ToolDefinition(
        name="web_search",
        server=SERVER_BUILTIN,
        tags=["web", "search"],
        description=_builder.get_tool_desc("web_search"),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询（越具体结果越精准）"},
                "num_results": {"type": "integer", "description": "返回结果数量，默认8"},
                "type": {"type": "string", "enum": ["auto", "fast", "deep"], "description": "搜索类型：auto(默认,均衡) | fast(快速) | deep(深度搜索)"},
            },
            "required": ["query"],
        },
        handler=_handle_search,
    ),
    ToolDefinition(
        name="read_file",
        server=SERVER_BUILTIN,
        tags=["file", "read"],
        description=_builder.get_tool_desc("read_file"),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录的绝对路径"},
                "offset": {"type": "integer", "description": "起始行号（从1开始，不设则从头读）"},
                "limit": {"type": "integer", "description": "读取行数上限（默认2000）"},
            },
            "required": ["path"],
        },
        handler=_handle_read_file,
    ),
    ToolDefinition(
        name="edit_file",
        server=SERVER_BUILTIN,
        tags=["file", "edit", "write"],
        description=_builder.get_tool_desc("edit_file"),
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
        handler=_handle_edit_file,
    ),
    ToolDefinition(
        name="search_files",
        server=SERVER_BUILTIN,
        tags=["search", "file"],
        description=_builder.get_tool_desc("search_files"),
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
        handler=_handle_search_files,
    ),
    ToolDefinition(
        name="arbor_viz",
        server=SERVER_BUILTIN,
        tags=["viz", "tree"],
        description=_builder.get_tool_desc("arbor_viz"),
        parameters={
            "type": "object",
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "节点唯一 ID"},
                            "parent_id": {"type": "string", "description": "父节点 ID（根节点填空或 root）"},
                            "status": {"type": "string", "enum": ["predicted", "selected", "implemented", "pruned"], "description": "predicted=预测中(蓝) | selected=已选定(绿) | implemented=已实施(深绿) | pruned=已剪枝(灰)"},
                            "detail": {"type": "string", "description": "节点详情（可选）"},
                        },
                        "required": ["id", "parent_id", "status"],
                    },
                    "description": "节点列表，构成假设树结构",
                },
                "title": {"type": "string", "description": "图表标题（可选）"},
                "output_path": {"type": "string", "description": "输出路径（默认 ~/Desktop/arbor_tree.html）"},
            },
            "required": ["nodes"],
        },
        handler=_handle_arbor_viz,
    ),
    ToolDefinition(
        name="text_analyzer",
        server=SERVER_BUILTIN,
        tags=["text", "analysis"],
        description=_builder.get_tool_desc("text_analyzer"),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待分析的文本内容"},
            },
            "required": ["text"],
        },
        handler=_handle_text_analyzer,
    ),
    ToolDefinition(
        name="skill",
        server=SERVER_BUILTIN,
        tags=["skill", "meta"],
        description="Load a specialized skill when a task matches its description. "
                    "Use this to get detailed instructions for specific workflows.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The name of the skill from available_skills"},
            },
            "required": ["name"],
        },
        handler=_handle_skill,
    ),
    ToolDefinition(
        name="search_history",
        server=SERVER_BUILTIN,
        tags=["memory", "search"],
        description=_builder.get_tool_desc("search_history"),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "recent", "stats"],
                    "description": "search=按关键词搜历史对话; recent=看最近对话; stats=账本概况"
                },
                "query": {
                    "type": "string",
                    "description": "search 必填: 关键词，多词空格分隔（AND 关系），如「项目 优化 建议」"
                },
                "role": {
                    "type": "string",
                    "enum": ["user", "assistant", "tool"],
                    "description": "可选: 只搜某个角色的发言（如 role=user 找用户原话）"
                },
                "limit": {
                    "type": "integer",
                    "description": "可选: 返回条数上限，默认 10"
                },
            },
            "required": [],
        },
        handler=_handle_search_history,
    ),
    ToolDefinition(
        name="task",
        server=SERVER_BUILTIN,
        tags=["subagent", "task"],
        description="Launch a new agent to handle complex, multistep tasks autonomously.\n\n"
                    "WHEN TO USE (强烈推荐): 复杂/多步任务、多文件代码库探索、项目分析、"
                    "需要并行调研多个模块时，优先用 task 派子代理，别自己逐个 read_file 死磕。"
                    "子代理完成后再汇总结果。\n"
                    "Available agent types: explore, build, general, analyze.\n"
                    "Use the explore agent for codebase exploration, build for editing, "
                    "general for complex multi-step research, analyze for deep analysis.",
        parameters={
            "type": "object",
            "properties": {
                "subagent_type": {
                    "type": "string",
                    "description": "Agent type: explore|build|general|analyze",
                    "enum": ["explore", "build", "general", "analyze"],
                },
                "description": {
                    "type": "string",
                    "description": "Short (3-5 word) description of the task",
                },
                "prompt": {
                    "type": "string",
                    "description": "The task for the sub-agent to execute",
                },
            },
            "required": ["subagent_type", "description", "prompt"],
        },
        handler=_handle_task,
    ),
    ToolDefinition(
        name="orchestrate",
        server=SERVER_BUILTIN,
        tags=["subagent", "orchestrate"],
        description="Run multiple tasks in parallel or with dependencies using sub-agents.\n\n"
                    "Use this for complex multi-step workflows. Each task can specify "
                    "agent type, dependencies, and a detailed prompt.",
        parameters={
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "List of tasks to orchestrate",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique task identifier"},
                            "description": {"type": "string", "description": "Short description"},
                            "prompt": {"type": "string", "description": "Full task prompt"},
                            "agent": {"type": "string", "description": "Agent type"},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Task IDs to wait for",
                            },
                        },
                        "required": ["id", "description", "prompt"],
                    },
                },
                "max_concurrent": {
                    "type": "integer",
                    "description": "Max concurrent tasks (default 5)",
                },
            },
            "required": ["tasks"],
        },
        handler=_handle_orchestrate,
    ),
]

# 从 _SANDBOX_TOOL_DEFS 自动生成，增删工具只需维护 _SANDBOX_TOOL_DEFS
_HANDLER_MAP: Dict[str, Callable] = {
    t.name: t.handler for t in _SANDBOX_TOOL_DEFS if t.handler
}


def _safe(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", raw)


class ToolRegistry:
    """工具注册表 — 11 个内置工具 + 懒加载 MCP + Agent 权限过滤"""

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
            except asyncio.CancelledError:
                raise  # 不吞 CancelledError，让上层 wait_for 转为 TimeoutError
            except Exception as e:
                logger.warning(f"MCP 连接异常: {e}")
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

        安全措施：超时/取消时清理孤儿子进程
        """
        from core.mcp.mcp_client import mcp_client

        mcp_tools = []
        servers: list = []
        try:
            # 第一步：发现并注册所有 server 配置（纯内存操作，快）
            servers = sorted(await self._discover_mcp_configs())
            if not servers:
                return mcp_tools

            # 第二步：并行拉取所有 server 的工具列表
            tasks = [self._list_mcp_tools(srv) for srv in servers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 第三步：处理结果
            seen_names = set()
            for result in results:
                if isinstance(result, BaseException):
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
        except asyncio.CancelledError:
            # 取消/超时时清理孤儿子进程（仅清理「脚本已启动但未注册工具」的）
            handled_servers = {t.server for t in mcp_tools if t.server}
            for srv in servers:
                if srv not in handled_servers:
                    try:
                        await mcp_client._cleanup_connection(srv)
                    except Exception:
                        pass
            raise
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
        tool_preference: Optional[set] = None,
        platform: str = "",
    ) -> List[ToolDefinition]:
        """获取工具列表，应用 Agent 类型的 allowed/disallowed 约束

        不再做领域分类/评分排序/条件保留——让 LLM 靠工具 description 自主选工具。
        只做：
        1. 所有工具返回
        2. Agent 类型硬约束：allowed 白名单 + disallowed 黑名单
        3. tool_preference 服务器优先排序（Skill倾向优先）
        4. platform 工具集裁剪（toolset 分组层，对齐 hermes toolsets.py）
        """
        if not self._initialized:
            return list(self._tools.values())[:max_tools]

        all_tools = list(self._tools.values())

        # Agent 类型硬约束过滤
        # 修复 #060 (语义文档化): 白名单约束语义——
        #   - disallowed: 全工具生效（内置 + MCP），黑名单是硬约束
        #   - allowed: 只约束内置工具；MCP 工具放行是有意设计（对标 OpenCode
        #     全量暴露哲学——MCP 工具是外部服务，白名单管不住也不该管）。
        #   ⚠️ 因此：需要"只读"等强约束时必须用 disallowed（EXPLORE/ANALYZE
        #   profile 即如此），不要用 allowed 表达安全边界。
        if allowed is not None:
            allowed_set = set(allowed)
            all_tools = [t for t in all_tools if t.name in allowed_set or t.server not in ("__builtin__",)]
        if disallowed is not None:
            disallowed_set = set(disallowed)
            all_tools = [t for t in all_tools if t.name not in disallowed_set]

        # platform 工具集裁剪（toolset 分组层）
        if platform:
            _before = {t.name for t in all_tools}
            all_tools = _apply_toolset_filter(all_tools, platform)
            _removed = _before - {t.name for t in all_tools}
            if _removed:
                print(f"    \033[33m◇ Toolset: platform={platform} → 禁用 [{', '.join(sorted(_removed))}]\033[0m")

        # tool_preference 服务器优先排序（Skill倾向的服务器排前面）
        if tool_preference:
            preferred = [t for t in all_tools if t.server in tool_preference]
            others = [t for t in all_tools if t.server not in tool_preference]
            all_tools = preferred + others

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
        """校验工具参数，返回 (是否合法, 错误信息)
        
        校验失败时返回详细错误信息（含正确 Schema 和可用参数列表），
        LLM 在下轮看到后可自行修正参数。
        
        参考 Opencode 的 InvalidArgumentsError 回传机制。
        """
        t = self._tools.get(name)
        if not t:
            return False, f"【参数校验失败】未知工具 '{name}'"
        p = t.parameters
        if not p:
            return True, ""
        props = p.get("properties", {})
        req = p.get("required", [])

        errors = []

        # 1. 检查必填字段
        for f in req:
            if f not in args or args[f] is None or args[f] == "":
                field_schema = props.get(f, {})
                field_type = field_schema.get("type", "any")
                enum_vals = field_schema.get("enum")
                desc = field_schema.get("description", "")
                detail = f"缺少必需参数 '{f}' (类型: {field_type})"
                if desc:
                    detail += f" — {desc[:100]}"
                if enum_vals:
                    detail += f"，可选值: {enum_vals}"
                errors.append(detail)

        # 2. 检查字段类型 + 类型自动转换
        for k, v in list(args.items()):
            if k in props:
                pt = props[k].get("type", "")
                enum_vals = props[k].get("enum")
                desc = props[k].get("description", "")

                # 类型自动转换
                if pt == "string" and not isinstance(v, str):
                    args[k] = str(v)
                    continue
                elif pt in ("integer", "number") and isinstance(v, str):
                    try:
                        args[k] = int(v) if pt == "integer" else float(v)
                    except:
                        errors.append(
                            f"参数 '{k}' 类型错误: 期望 {pt}, 无法从 '{v}' 转换"
                        )
                    continue
                elif pt in ("integer", "number") and not isinstance(v, (int, float)):
                    errors.append(
                        f"参数 '{k}' 类型错误: 期望 {pt}, 实际 {type(v).__name__}"
                    )
                    continue
                elif pt == "boolean" and not isinstance(v, bool):
                    errors.append(
                        f"参数 '{k}' 类型错误: 期望 boolean, 实际 {type(v).__name__}"
                    )
                    continue
                elif pt == "array" and not isinstance(v, list):
                    errors.append(
                        f"参数 '{k}' 类型错误: 期望 array(数组), 实际 {type(v).__name__}"
                    )
                    continue

                # Enum 值检查
                if enum_vals and v not in enum_vals:
                    errors.append(
                        f"参数 '{k}' 取值错误: 期望 {enum_vals}, 实际 '{v}'"
                    )

                # 额外检查：string 值是否为空字符串（对非空字段有意义的检测）
                if pt == "string" and isinstance(v, str) and not v.strip():
                    if "description" in props[k]:
                        errors.append(
                            f"参数 '{k}' 为空字符串 ({desc[:80]})"
                        )

        if errors:
            # 构建 LLM 友好的详细错误信息
            detail_lines = [
                f"【参数校验失败】工具 '{name}' 的参数不正确:\n",
                *[f"  {i+1}. {e}" for i, e in enumerate(errors)],
                "",
                f"可用参数:",
            ]
            for prop_name, prop_schema in props.items():
                ptype = prop_schema.get("type", "any")
                preq = "必填" if prop_name in req else "可选"
                pdesc = prop_schema.get("description", "")
                penum = prop_schema.get("enum")
                line = f"  • {prop_name} ({ptype}, {preq})"
                if pdesc:
                    line += f" — {pdesc[:120]}"
                if penum:
                    line += f"\n    可选值: {penum}"
                detail_lines.append(line)

            detail_lines.append(
                "\n请根据正确的参数 Schema 修正后重新调用。"
            )
            return False, "\n".join(detail_lines)

        return True, ""

    @property
    def count(self) -> int:
        return len(self._tools)

    # ── Scoped Registration（对标 opencode Scope-based tool registration）──

    def register(self, tools: Dict[str, ToolDefinition]) -> List[str]:
        """注册工具（覆盖已存在的同名工具），返回被覆盖的旧工具名列表"""
        overwritten = [k for k in tools if k in self._tools]
        for name, td in tools.items():
            self._tools[name] = td
        if overwritten:
            logger.info(f"工具覆盖注册: {', '.join(overwritten)}")
        return overwritten

    def register_scoped(self, tools: Dict[str, ToolDefinition]):
        """上下文管理器：退出时自动注销本 scope 注册的工具"""
        return _ScopedRegistry(self, tools)

    def unregister(self, names: List[str]) -> None:
        """注销工具（仅移除 scope 内注册的，不删内置工具）"""
        for name in names:
            td = self._tools.get(name)
            if td and td.server not in (SERVER_BUILTIN,):
                del self._tools[name]

    def snapshot(self) -> Dict[str, ToolDefinition]:
        """获取当前工具快照（用于 scope 回滚）"""
        return dict(self._tools)


class _ScopedRegistry:
    """Scoped 工具注册上下文管理器"""
    def __init__(self, registry: "ToolRegistry", tools: Dict[str, ToolDefinition]):
        self._registry = registry
        self._tools = tools
        self._previous: Dict[str, Optional[ToolDefinition]] = {}

    def __enter__(self):
        self._previous = {k: self._registry._tools.get(k) for k in self._tools
                          if k in self._registry._tools}
        for name, td in self._tools.items():
            self._registry._tools[name] = td
        logger.info(f"Scoped 注册 {len(self._tools)} 个工具: {', '.join(self._tools.keys())}")
        return self

    async def __aenter__(self):
        return self.__enter__()

    def __exit__(self, *args):
        for name in self._tools:
            if name in self._previous:
                self._registry._tools[name] = self._previous[name]
            else:
                self._registry._tools.pop(name, None)
        logger.info(f"Scoped 注销 {len(self._tools)} 个工具")

    async def __aexit__(self, *args):
        self.__exit__(*args)


_registry = None


def get_tool_registry() -> "ToolRegistry":
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
