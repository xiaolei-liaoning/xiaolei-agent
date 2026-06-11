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

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SERVER_BUILTIN = "__builtin__"

# ═══════════════════════════════════════════════════════════════════
# 工具领域分类系统
# ═══════════════════════════════════════════════════════════════════


class ToolDomain:
    """工具功能领域 — 用于按域分类、按域筛选"""

    SEARCH = "search"  # 搜索/查询
    FILE = "file"  # 文件读写
    CODE = "code"  # 代码执行/编写
    ANALYSIS = "analysis"  # 数据分析/图表
    SYSTEM = "system"  # 系统信息/监控
    TEXT = "text"  # 文本处理
    TRANSLATE = "translate"  # 翻译
    WEB = "web"  # 网页抓取
    GUI = "gui"  # GUI自动化
    AUTOMATION = "automation"  # 工作流/自动化
    REFLECT = "reflect"  # 反思/复盘
    API = "api"  # HTTP API 调用
    GIT = "git"  # Git 操作
    FUN = "fun"  # 趣味
    GAME = "game"  # 游戏
    WEATHER = "weather"  # 天气
    ART = "art"  # ASCII 艺术
    WORKFLOW = "workflow"  # 工作流引擎
    DATA_SOURCE = "data_source"  # 内置数据源
    SKILL = "skill"  # 技能执行
    MISC = "misc"  # 杂项


# 任务→领域分类关键词表
# 每个领域包含一组触发词，任务描述命中任一触发词即匹配该领域
DOMAIN_CLASSIFIER = {
    ToolDomain.SEARCH: [
        "搜索",
        "查找",
        "查询",
        "搜",
        "寻找",
        "找一下",
        "查一下",
        "搜一下",
        "百度",
        "谷歌",
        "bing",
        "search",
        "find",
        "lookup",
        "query",
        "搜索一下",
        "查查",
        "github",
        "GitHub",
    ],
    ToolDomain.FILE: [
        "文件",
        "保存",
        "写入",
        "读取",
        "打开文件",
        "创建文件",
        "读写",
        "写文件",
        "读文件",
        "path",
        "路径",
        "file",
        "save",
        "write",
        "read",
        "存储",
        "另存为",
        "导出到",
    ],
    ToolDomain.CODE: [
        "代码",
        "编写",
        "编程",
        "写代码",
        "写程序",
        "debug",
        "debugging",
        "code",
        "program",
        "脚本",
        "script",
        "执行",
        "运行代码",
        "编译",
        "实现",
        "编写一个",
        "写一个",
    ],
    ToolDomain.ANALYSIS: [
        "分析",
        "统计",
        "图表",
        "plot",
        "分析数据",
        "analyze",
        "csv",
        "数据",
        "datasets",
        "dataset",
        "绘图",
        "可视化",
        "画图",
        "报告",
        "报表",
        "汇总",
    ],
    ToolDomain.SYSTEM: [
        "系统",
        "cpu",
        "内存",
        "磁盘",
        "进程",
        "system",
        "info",
        "资源",
        "监控",
        "监测",
        "网络",
        "ip",
    ],
    ToolDomain.WEB: [
        "网页",
        "抓取",
        "爬取",
        "scrape",
        "fetch",
        "热搜",
        "trending",
        "爬虫",
        "网站",
        "页面",
        "文章",
        "github",
        "GitHub",
    ],
    ToolDomain.TRANSLATE: [
        "翻译",
        "translate",
        "英文",
        "中文",
        "语言",
        "双语",
        "译成",
        "转换语言",
    ],
    ToolDomain.REFLECT: [
        "反思",
        "复盘",
        "总结",
        "review",
        "reflect",
        "回顾",
        "评估",
        "改进",
        "优化建议",
    ],
    ToolDomain.API: [
        "api",
        "接口",
        "请求",
        "http",
        "调用接口",
        "rest",
        "post请求",
        "get请求",
        "curl",
    ],
    ToolDomain.GIT: [
        "git",
        "提交",
        "commit",
        "push",
        "pull",
        "branch",
        "版本控制",
    ],
    ToolDomain.GUI: [
        "打开应用",
        "打开软件",
        "启动",
        "截图",
        "screenshot",
        "音量",
        "亮度",
        "自动化操作",
    ],
    ToolDomain.AUTOMATION: [
        "工作流",
        "自动化",
        "发送邮件",
        "邮件",
        "通知",
        "日历",
        "workflow",
        "automation",
        "email",
    ],
    ToolDomain.WEATHER: [
        "天气",
        "weather",
        "温度",
        "下雨",
        "下雪",
        "预报",
        "气温",
    ],
    ToolDomain.FUN: [
        "笑话",
        "谜语",
        "星座",
        "运势",
        "趣闻",
        "joke",
        "fun",
        "冷知识",
        "娱乐",
    ],
    ToolDomain.GAME: [
        "游戏",
        "猜数字",
        "猜拳",
        "骰子",
        "game",
        "play",
    ],
    ToolDomain.ART: [
        "ascii",
        "艺术",
        "图案",
        "打印图案",
        "画一个",
        "字符画",
    ],
    ToolDomain.WORKFLOW: [
        "工作流",
        "工作流引擎",
        "创建工作流",
        "执行工作流",
        "流程编排",
    ],
}

# 为每个内置工具预分配领域（一个工具可属多个领域）
_BUILTIN_DOMAINS = {
    "execute_python": {ToolDomain.CODE},
    "execute_shell": {ToolDomain.CODE, ToolDomain.SYSTEM, ToolDomain.FILE},
    "git": {ToolDomain.GIT},
    "web_search": {ToolDomain.SEARCH, ToolDomain.WEB},
    "rag_search": {ToolDomain.SEARCH, ToolDomain.ANALYSIS},
    "skill_execute": {ToolDomain.SKILL},
    "kepa_reflect": {ToolDomain.REFLECT},
    "ask_clarification": {ToolDomain.MISC},
    "self_reflect": {ToolDomain.REFLECT},
    "fetch_url": {ToolDomain.WEB, ToolDomain.SEARCH, ToolDomain.API},
}

# MCP 工具的领域映射（通过服务器名匹配）
# 已清理与内置工具重叠的MCP服务器，保留有独特价值的
_MCP_SERVER_DOMAINS = {
    # 外部MCP（.mcp.json配置）
    "playwright": {ToolDomain.WEB, ToolDomain.SEARCH, ToolDomain.AUTOMATION},
    "codegraph": {ToolDomain.CODE, ToolDomain.ANALYSIS},
    "context7": {ToolDomain.CODE, ToolDomain.ANALYSIS},
    "deepwiki": {ToolDomain.CODE, ToolDomain.ANALYSIS},
    # 自定义MCP（mcp/目录，有独特功能）
    "gui-automation-mcp": {ToolDomain.GUI, ToolDomain.AUTOMATION},
    "deep-thinking-mcp": {ToolDomain.REFLECT, ToolDomain.MISC},
    "translator-mcp": {ToolDomain.TRANSLATE},
    "weather-mcp": {ToolDomain.WEATHER},
    "skill-mcp": {ToolDomain.SKILL},
    "openclaw-mcp": {ToolDomain.WORKFLOW},
    "fun-mcp": {ToolDomain.FUN},
    "game-mcp": {ToolDomain.GAME},
    "art-mcp": {ToolDomain.ART},
    "advanced-automation-mcp": {ToolDomain.AUTOMATION},
    "awesome-mcp-servers-mcp": {ToolDomain.MISC},
    "third-party-mcp": {ToolDomain.API, ToolDomain.AUTOMATION},
}


def classify_domains(task) -> set:
    """将任务描述分类到 1-N 个领域，返回匹配的领域集合"""
    if not isinstance(task, str):
        task = str(task) if task else ""
    desc = task.lower()
    matched = set()
    for domain, keywords in DOMAIN_CLASSIFIER.items():
        for kw in keywords:
            if kw.lower() in desc:
                matched.add(domain)
                break  # 一个领域命中一个关键词即可
    return matched


# ═══════════════════════════════════════════════════════════════════
# LLM 辅助领域分类 — 用 glm-4-flash 快速语义分类，弥补静态关键词的不足
# ═══════════════════════════════════════════════════════════════════

_domain_cache: Dict[str, tuple] = {}  # task_hash -> (domains_set, timestamp)
_DOMAIN_CACHE_TTL = 300  # 5分钟缓存

# 领域→中文名映射（给 LLM prompt 用）
_DOMAIN_ITEMS = [
    (1, ToolDomain.SEARCH, "搜索/查询"),
    (2, ToolDomain.FILE, "文件读写"),
    (3, ToolDomain.CODE, "代码编写/执行"),
    (4, ToolDomain.ANALYSIS, "数据分析/图表"),
    (5, ToolDomain.SYSTEM, "系统信息/监控"),
    (6, ToolDomain.TEXT, "文本处理"),
    (7, ToolDomain.TRANSLATE, "翻译"),
    (8, ToolDomain.WEB, "网页抓取"),
    (9, ToolDomain.GUI, "GUI自动化"),
    (10, ToolDomain.AUTOMATION, "自动化/工作流"),
    (11, ToolDomain.REFLECT, "反思/复盘"),
    (12, ToolDomain.API, "HTTP请求"),
    (13, ToolDomain.GIT, "Git操作"),
    (14, ToolDomain.FUN, "趣味/娱乐"),
    (15, ToolDomain.GAME, "游戏"),
    (16, ToolDomain.WEATHER, "天气"),
    (17, ToolDomain.ART, "ASCII艺术"),
    (18, ToolDomain.WORKFLOW, "工作流引擎"),
]
_DOMAIN_IDX_MAP = {idx: domain for idx, domain, _ in _DOMAIN_ITEMS}


async def llm_classify_domains(task) -> Optional[set]:
    """用 GLM-4-Flash 对任务做快速领域分类

    调用一次 LLM（温度0.05，最多20个token输出），根据语义判断任务领域。
    失败/超时返回 None → 调用方回退到静态关键词分类。
    同类任务缓存5分钟，避免重复调用。
    """
    if not isinstance(task, str):
        task = str(task) if task else ""
    if len(task) < 8:
        return None  # 太短的任务不需要 LLM

    task_hash = str(hash(task))
    now = time.time()
    cached = _domain_cache.get(task_hash)
    if cached and now - cached[1] < _DOMAIN_CACHE_TTL:
        return cached[0]

    domain_lines = "\n".join(f"{idx}={name}" for idx, _, name in _DOMAIN_ITEMS)
    prompt = (
        f"对任务做领域分类。从以下列表中选择1-3个最匹配的编号：\n{domain_lines}"
        f"\n\n任务：{task[:150]}"
        f"\n\n只返回数字，逗号分隔。例如：1,3"
    )

    try:
        from core.engine.llm_backend import get_llm_router

        router = get_llm_router()

        resp = await asyncio.wait_for(
            router.chat(
                [{"role": "user", "content": prompt}], temperature=0.05, max_tokens=20
            ),
            timeout=3.0,
        )
        if not resp or "系统正在处理" in resp:
            return None

        import re as _re

        numbers = _re.findall(r"\d+", resp.strip())
        domains = set()
        for n in numbers:
            n_int = int(n)
            if n_int in _DOMAIN_IDX_MAP:
                domains.add(_DOMAIN_IDX_MAP[n_int])

        if domains:
            _domain_cache[task_hash] = (domains, time.time())
            logger.info(f'LLM分类: "{task[:40]}…" → {domains}')
            return domains
    except asyncio.TimeoutError:
        logger.debug(f"LLM分类超时: {task[:40]}")
    except Exception as e:
        logger.debug(f"LLM分类异常: {e}")

    return None


def estimate_tool_token_count(tool_def: "ToolDefinition") -> int:
    """估算一个工具定义消耗的 token 数（name + description + 参数名）"""
    base = len(tool_def.name) + len(tool_def.description)
    if tool_def.parameters:
        props = tool_def.parameters.get("properties", {})
        base += sum(len(k) for k in props)
    return base // 2 + 80  # 中英文混估 + 固定开销


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    server: str = ""
    tool_name: str = ""
    tags: List[str] = field(default_factory=list)
    handler: Optional[Callable] = None
    domains: set = field(default_factory=set)  # 工具所属领域集合


# ═══════════════════════════════════════════════════════════════════
# 内置 Handlers
# ═══════════════════════════════════════════════════════════════════



# ── 纯 asyncio HTTP GET（不创建线程，可安全取消） ───────────────────


async def _http_get(url: str, timeout: int = 10) -> str:
    """纯 asyncio HTTP GET（使用 asyncio.open_connection, 无 run_in_executor）

    asyncio.wait_for 取消此协程时，socket 立即关闭，不留僵尸线程。
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    reader, writer = None, None
    try:
        if parsed.scheme == "https":
            import ssl

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ctx), timeout=timeout
            )
        else:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Accept: text/html,application/json\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(request.encode())
        await writer.drain()

        # 读取响应（按块读取，不过量）
        chunks = []
        while True:
            chunk = await asyncio.wait_for(reader.read(65536), timeout=timeout)
            if not chunk:
                break
            chunks.append(chunk)

        data = b"".join(chunks)
        # 尝试从响应头分离body
        try:
            header_end = data.index(b"\r\n\r\n") + 4
            body = data[header_end:]
        except ValueError:
            body = data
        return body.decode("utf-8", errors="replace")
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


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


async def _handle_execute_python(args: Dict) -> Dict:
    """执行 Python 代码 — 默认沙盒隔离，mode=local 需显式指定
    
    sandbox 模式：执行后检测文件写入操作，如有则提示用户确认保存路径
    local 模式：需要用户确认后执行（无安全隔离）
    """
    code = args.get("code", "")
    if not code:
        return {"result": {"content": [{"text": "缺少 code 参数"}]}}
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
        return {"result": {"content": [{"text": "[本地] ❌ 执行超时\n\n⚠️ 警告：当前为本地模式，无安全隔离"}]}}
    except Exception as e:
        return {"result": {"content": [{"text": f"[本地] ❌ {e}\n\n⚠️ 警告：当前为本地模式，无安全隔离"[:2000]}]}}


async def _handle_rag_search(args: Dict) -> Dict:
    """RAG 增强搜索 — 向量库 + 知识提取 + 联网搜索"""
    query = args.get("query", "")
    if not query:
        return {"result": {"content": [{"text": "需要 query 参数"}]}}
    max_results = int(args.get("max_results", 5))
    learn = args.get("learn", True)
    try:
        from core.search.rag_search_engine import RAGSearchEngine

        engine = RAGSearchEngine()
        result = await engine.search_and_learn(
            query=query,
            user_id=1,
            learn=learn,
            max_results=max_results,
            enhance=True,
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
            text_parts.append(
                f"\n🧠 知识提取: {str(result['knowledge_extracted'])[:200]}"
            )
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
            import inspect

            from core.skill_base import get_skill_registry

            registry = get_skill_registry()
            skill = registry.get(skill_name)
            if skill:
                ctx = {"user_id": 1}
                if inspect.iscoroutinefunction(skill.execute):
                    result = await skill.execute(params, context=ctx)
                else:
                    result = skill.execute(params, context=ctx)
                return {
                    "result": {
                        "content": [
                            {
                                "text": f"[技能] ✅ {skill_name} 执行成功\n{str(result)[:3000]}"
                            }
                        ]
                    }
                }
        except Exception:
            pass
        # 兜底：通过 dispatcher 匹配
        matched = dispatcher.match_skill(skill_name)
        if matched:
            result = dispatcher.dispatch(skill_name)
            return {
                "result": {
                    "content": [
                        {"text": f"[技能] ✅ 匹配到 {matched}\n{str(result)[:3000]}"}
                    ]
                }
            }
        return {
            "result": {"content": [{"text": f"[技能] ❌ 未找到技能: {skill_name}"}]}
        }
    except Exception as e:
        return {"result": {"content": [{"text": f"技能执行失败: {e}"}]}}


async def _handle_kepa_reflect(args: Dict) -> Dict:
    """KEPA 反思循环 — 知识→执行→感知→调整"""
    action = args.get("action", "full")
    context = args.get("context", "")
    if action not in ("think", "act", "reflect", "full"):
        return {
            "result": {"content": [{"text": "action 必须是 think|act|reflect|full"}]}
        }
    try:
        from core.engine.llm_backend import get_llm_router

        router = get_llm_router()
        results = []

        if action in ("think", "full"):
            prompt = f"请分析以下上下文，给出深入洞察和执行建议：\n\n{context}\n\n输出格式：\n洞察: ...\n建议: ..."
            resp = await router.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=800,
            )
            resp_text = resp if isinstance(resp, str) else str(resp)
            results.append(f"【思考】{resp_text[:500]}")

        if action in ("act", "full") and action != "think":
            results.append(
                "【行动】KEPA 行动阶段：基于洞察生成执行方案。请使用其他工具（execute_python/fetch_url等）执行具体操作。"
            )

        if action in ("reflect", "full"):
            try:
                from core.auto_reviewer import get_auto_reviewer

                reviewer = get_auto_reviewer()
                review = await reviewer.review(
                    task_id="kepa_reflect",
                    task_description=context,
                    execution_logs=context,
                    task_result=context,
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
            lines.append(
                f"\n📌 值得沉淀为技能{' (' + review.skill_name + ')' if review.skill_name else ''}"
            )
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
            return {"result": {"content": [{"text": f"未知操作或缺少参数: {action}"}]}}
        proc = await asyncio.create_subprocess_exec(
            *cmds[action], cwd=repo, stdout=-1, stderr=-1
        )
        o, e = await asyncio.wait_for(proc.communicate(), timeout=15)
        text = (o.decode() if o else "") or (e.decode() if e else "(无输出)")
        return {"result": {"content": [{"text": f"git {action}\n{text[:3000]}"}]}}
    except Exception as ex:
        return {"result": {"content": [{"text": f"git {action} 失败: {ex}"[:500]}]}}





async def _handle_write_file(args: Dict) -> Dict:
    """写文件到指定路径 — 兼容多种参数名"""
    from core.multi_agent_v2.tools.tool_result import ok, err

    path = args.get("path", "")
    content = args.get("content", "")
    # 兼容多种参数名
    if not content:
        content = args.get("code", "") or args.get("text", "") or args.get("html", "") or args.get("data", "") or args.get("file_content", "")
    if not content:
        logger.warning(f"write_file: 参数中没有 content/code/text/html，args keys={list(args.keys())}")
        return err("需要 content 参数")
    # 中文路径映射
    desktop = os.path.expanduser("~/Desktop")
    if path.startswith("桌面上/"):
        path = desktop + path[3:]
    elif path.startswith("桌面/"):
        path = desktop + path[2:]
    path = os.path.expanduser(path)
    # 内容质量校验：代码文件不能太短或只是计划文本
    is_code_file = any(path.endswith(ext) for ext in (".html", ".htm", ".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".java", ".cpp", ".c", ".go", ".rs"))
    if is_code_file and len(content) < 500:
        # 太短的"代码"很可能是计划文本，拒绝写入
        import re
        has_code_indicators = bool(re.search(r'(?:def |class |function|<html|<!DOCTYPE|from |import |print\()', content))
        if not has_code_indicators:
            logger.warning(f"write_file: 内容疑似为计划文本非实际代码 (path={path}, len={len(content)})")
            return err(f"❌ 内容疑似为计划文本而非实际代码！请写入完整的可运行代码（包括所有 HTML 结构、CSS、JavaScript 逻辑），当前内容只有 {len(content)} 字符。建议使用 write_file 一次性写入完整文件。")
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
        return ok(f"✅ 已写入文件: {path} ({len(content)} 字符)")
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
    """精确文本替换"""
    from core.multi_agent_v2.tools.tool_result import ok, err

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
    return ok(f"编辑成功: {path} (替换 {actual} 处)")


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


async def _handle_todo_write_tool(args: Dict) -> Dict:
    """任务列表管理"""
    from core.multi_agent_v2.tools.tool_result import ok, err

    todos = args.get("todos", [])
    if not todos:
        return err("需要 todos 参数")
    lines = []
    for t in todos:
        status = t.get("status", "pending")
        icon = {"completed": "✅", "in_progress": "🔄", "cancelled": "❌"}.get(status, "⬜")
        priority = t.get("priority", "")
        p_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "")
        lines.append(f"{icon} {p_icon} {t.get('content', '')}")
    return ok("任务列表:\n" + "\n".join(lines))


# ═══════════════════════════════════════════════════════════════════
# Handler 映射 & 工具定义
# ═══════════════════════════════════════════════════════════════════

_HANDLER_MAP: Dict[str, Callable] = {
    "fetch_url": _handle_fetch_url,
    "write_file": _handle_write_file,
    "read_file": _handle_read_file,
    "edit_file": _handle_edit_file,
    "glob_search": _handle_glob_search,
    "grep_search": _handle_grep_search,
    "execute_python": _handle_execute_python,
    "execute_shell": _handle_execute_shell,
    "web_search": _handle_search,
    "rag_search": _handle_rag_search,
    "skill_execute": _handle_skill_execute,
    "kepa_reflect": _handle_kepa_reflect,
    "ask_clarification": _handle_ask_clarification,
    "self_reflect": _handle_self_reflect,
    "git": _handle_git,
    "todo_write": _handle_todo_write_tool,
}

_SANDBOX_TOOL_DEFS = [
    ToolDefinition(
        name="write_file",
        server=SERVER_BUILTIN,
        tags=["file", "write"],
        domains={ToolDomain.FILE},
        description="写入文件到指定路径。用于创建游戏、脚本、HTML等文件到桌面。必填：path=文件路径(如~/Desktop/game.html或桌面/game.py)，content=完整文件内容(必须！文件的全部代码)。注意：content 参数是文件的完整内容，必须为非空字符串。创建游戏文件请用此工具，不要用 execute_python。",
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
        domains={ToolDomain.CODE},
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
        domains={ToolDomain.CODE, ToolDomain.SYSTEM, ToolDomain.FILE},
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
        domains={ToolDomain.GIT},
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
        name="rag_search",
        server=SERVER_BUILTIN,
        tags=["rag", "search", "knowledge"],
        domains={ToolDomain.SEARCH, ToolDomain.ANALYSIS},
        description="RAG 增强搜索 — 向量库检索 + 知识提取 + 联网搜索。比 search 更深度，适合研究型问题。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"},
                "max_results": {
                    "type": "integer",
                    "description": "最大结果数（默认5）",
                },
                "learn": {"type": "boolean", "description": "是否提取知识到向量库"},
            },
            "required": ["query"],
        },
        handler=_handle_rag_search,
    ),
    ToolDefinition(
        name="skill_execute",
        server=SERVER_BUILTIN,
        tags=["skill"],
        domains={ToolDomain.SKILL},
        description="执行已注册的技能。技能是预定义的功能模块（天气/翻译/自动化等）。",
        parameters={
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "技能名称"},
                "params": {"type": "object", "description": "技能参数"},
            },
            "required": ["skill_name"],
        },
        handler=_handle_skill_execute,
    ),
    ToolDefinition(
        name="kepa_reflect",
        server=SERVER_BUILTIN,
        tags=["kepa", "reflect"],
        domains={ToolDomain.REFLECT},
        description="KEPA 反思循环：Knowledge→Execution→Perception→Adjustment。对当前状态进行深度思考和自我调整。action=think(仅思考)|act(仅行动)|reflect(仅反思)|full(完整循环)",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["think", "act", "reflect", "full"],
                    "description": "反思阶段",
                },
                "context": {"type": "string", "description": "需要反思的上下文信息"},
            },
            "required": ["action"],
        },
        handler=_handle_kepa_reflect,
    ),
    ToolDefinition(
        name="ask_clarification",
        server=SERVER_BUILTIN,
        tags=["clarification"],
        domains={ToolDomain.MISC},
        description="反问澄清 — 当用户输入模糊或执行失败时，生成追问来明确需求。",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "需要澄清的消息"},
                "error_context": {
                    "type": "string",
                    "description": "错误上下文（可选）",
                },
            },
            "required": ["message"],
        },
        handler=_handle_ask_clarification,
    ),
    ToolDefinition(
        name="self_reflect",
        server=SERVER_BUILTIN,
        tags=["reflect"],
        domains={ToolDomain.REFLECT},
        description="自动复盘反思 — 分析执行过程，生成改进建议和教训总结。适合在任务完成后调用。",
        parameters={
            "type": "object",
            "properties": {
                "task_description": {"type": "string", "description": "任务描述"},
                "execution_logs": {"type": "string", "description": "执行日志"},
                "task_result": {"type": "string", "description": "执行结果（可选）"},
            },
            "required": ["task_description", "execution_logs"],
        },
        handler=_handle_self_reflect,
    ),
    ToolDefinition(
        name="fetch_url",
        server=SERVER_BUILTIN,
        tags=["web", "fetch"],
        domains={ToolDomain.WEB, ToolDomain.SEARCH, ToolDomain.API},
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
        domains={ToolDomain.SEARCH, ToolDomain.WEB},
        description="网页搜索。支持多种搜索类型。用于获取实时信息、查找资料。",
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
        domains={ToolDomain.FILE},
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
        domains={ToolDomain.FILE},
        description="精确文本替换。支持替换所有匹配项。用于修改文件中的特定内容。",
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
        name="glob_search",
        server=SERVER_BUILTIN,
        tags=["search", "file", "glob"],
        domains={ToolDomain.SEARCH, ToolDomain.FILE},
        description="文件模式匹配搜索。支持递归搜索。用于查找符合模式的文件。",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob模式（如 *.py）"},
                "path": {"type": "string", "description": "搜索目录（默认当前目录）"},
                "limit": {"type": "integer", "description": "结果数量限制（默认200）"},
            },
            "required": ["pattern"],
        },
        handler=_handle_glob_search,
    ),
    ToolDefinition(
        name="grep_search",
        server=SERVER_BUILTIN,
        tags=["search", "content", "regex"],
        domains={ToolDomain.SEARCH, ToolDomain.TEXT},
        description="正则表达式内容搜索。支持文件过滤。用于在文件中查找特定内容。",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "正则表达式模式"},
                "path": {"type": "string", "description": "搜索路径（文件或目录）"},
                "include": {"type": "string", "description": "文件过滤模式（如 *.py）"},
                "limit": {"type": "integer", "description": "结果数量限制（默认200）"},
            },
            "required": ["pattern"],
        },
        handler=_handle_grep_search,
    ),
    ToolDefinition(
        name="todo_write",
        server=SERVER_BUILTIN,
        tags=["task", "todo", "management"],
        domains={ToolDomain.AUTOMATION},
        description="任务列表管理。支持创建、更新任务，设置优先级和状态。用于跟踪工作进度。",
        parameters={
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                        },
                        "required": ["content"],
                    },
                    "description": "任务列表",
                },
            },
            "required": ["todos"],
        },
        handler=_handle_todo_write_tool,
    ),
]


def _safe(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", raw)


class ToolRegistry:
    """工具注册表 — 12 个内置工具 + 懒加载 MCP + 智能工具筛选"""

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
                srv_domains = _MCP_SERVER_DOMAINS.get(srv, set())
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
                            domains=srv_domains,
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
        """按任务相关性排序的工具列表

        领域驱动选择：
        1. LLM 语义分类（优先）→ 静态关键词分类（兜底）
        2. 领域内工具优先（内置/MCP 公平竞争），跨领域工具靠关键词补充
        3. 核心工具条件保留（任务描述含关键词才强制入选）
        4. 动态 max_tools：根据工具描述长度估算 token 消耗
        5. Agent 类型硬约束：allowed 白名单 + disallowed 黑名单
        """
        if not self._initialized:
            return list(self._tools.values())[:max_tools]

        desc = task.lower()

        # ═══ 第一步：LLM 语义分类（优先）+ 静态关键词分类（兜底）═══
        task_domains = classify_domains(desc)  # 静态保底
        llm_ok = False
        try:
            llm_domains = await llm_classify_domains(task)
            if llm_domains is not None:
                task_domains = llm_domains
                llm_ok = True
        except Exception:
            pass  # LLM 失败就用静态结果
        if llm_ok:
            logger.info(f"工具筛选: LLM分类+静态→{task_domains}")
        else:
            logger.debug(f"工具筛选: 静态分类→{task_domains}")

        # ═══ 第二步：遍历工具，计算相关性评分 ═══
        scored = []
        for t in self._tools.values():
            dl = t.description.lower()
            nl = t.name.lower()

            # --- 领域匹配（核心信号）---
            domain_score = 0.0
            if t.domains and task_domains:
                overlap = task_domains & t.domains
                if overlap:
                    domain_score = 6.0 + 4.0 * (len(overlap) - 1)

            # --- 关键词匹配（辅助信号）--
            kw_score = 0.0
            for kw in desc.split():
                kw = kw.strip().lower()
                if len(kw) > 1:
                    if kw in nl:
                        kw_score += 3.0
                    elif kw in dl:
                        kw_score += 2.0

            if len(desc) > 1 and any(c in dl for c in desc if len(c.strip()) > 0):
                kw_score += 0.5

            # --- 工具名精确匹配（LLM 在计划阶段已指名时最强信号）--
            exact_match = 8.0 if nl in desc else 0.0

            scored.append(
                (domain_score + kw_score + exact_match, domain_score, kw_score, t)
            )

        # ═══ 第三步：按总分降序 ═══
        scored.sort(key=lambda x: -x[0])

        # ═══ 第四步：分类筛选 ═══
        domain_matched = []
        keyword_fallback = []

        for s, domain_s, kw_s, t in scored:
            if s > 0:
                if domain_s >= 6.0:
                    domain_matched.append((s, t))
                else:
                    keyword_fallback.append((s, t))

        # ═══ 第五步：构建最终列表 ═══
        result = []
        seen = set()

        for s, t in domain_matched:
            if t.name not in seen:
                result.append(t)
                seen.add(t.name)

        for s, t in keyword_fallback:
            if t.name not in seen:
                result.append(t)
                seen.add(t.name)

        # ═══ 第六步：动态估算 max_tools ═══
        if result:
            sample = result[:max_tools]
            avg_tokens = sum(estimate_tool_token_count(t) for t in sample) / len(sample)
            budget = 3000
            dynamic_max = min(max_tools, max(8, int(budget / max(avg_tokens, 80))))
        else:
            dynamic_max = max_tools

        # ═══ 第七步：条件化核心工具保留 ═══
        # 只在任务描述暗示会用到时才强制保留，避免浪费名额
        CONDITIONAL_CORE = {
            "web_search": [
                "搜索",
                "查找",
                "查询",
                "搜",
                "找",
                "查",
                "search",
                "find",
                "query",
                "看看",
                "热搜",
                "热榜",
                "trending",
            ],
            "write_file": [
                "写",
                "创建",
                "生成",
                "保存",
                "桌面",
                "文件",
                "游戏",
                "脚本",
                "HTML",
                "Python",
                "write",
                "create",
                "generate",
                "save",
            ],
            "execute_python": [
                "代码",
                "python",
                "脚本",
                "执行",
                "运行",
                "程序",
                "写一个",
            ],
            "execute_shell": ["命令", "shell", "终端", "执行", "运行"],
            "fetch_url": [
                "网页",
                "url",
                "http",
                "网站",
                "api",
                "接口",
                "请求",
                "fetch",
            ],
        }
        for tool_name, keywords in CONDITIONAL_CORE.items():
            if any(kw.lower() in desc for kw in keywords):
                t = self._tools.get(tool_name)
                if t and t.name not in seen:
                    result.append(t)
                    seen.add(t.name)
                    if len(result) > dynamic_max:
                        # 超出预算，从末尾弹一个非核心 MCP 工具
                        for i in range(len(result) - 1, -1, -1):
                            n = result[i].name
                            if (
                                n
                                not in (
                                    "search",
                                    "write_file",
                                    "execute_python",
                                    "execute_shell",
                                    "fetch_url",
                                )
                                and result[i].server != SERVER_BUILTIN
                            ):
                                result.pop(i)
                                break

        # ═══ 第八步：Agent 类型硬约束过滤 ═══
        if allowed is not None:
            allowed_set = set(allowed)
            result = [t for t in result if t.name in allowed_set]
        if disallowed is not None:
            disallowed_set = set(disallowed)
            result = [t for t in result if t.name not in disallowed_set]

        return result[:dynamic_max]

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
