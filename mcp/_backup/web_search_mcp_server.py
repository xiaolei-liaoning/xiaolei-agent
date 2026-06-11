#!/usr/bin/env python3
"""联网搜索 MCP 服务器 - 参考 opencode 设计

特性：
- 网页搜索：支持多搜索引擎（DuckDuckGo、SearXNG）
- 网页抓取：获取URL内容，支持HTML转Markdown
- 内容处理：自动清洗、截断、格式化
- 超时控制：可配置请求超时
- 重试机制：失败自动重试
- User-Agent：模拟浏览器访问
"""

import sys
import json
import os
import re
import asyncio
import hashlib
import time
from typing import Dict, Any, Optional, List
from urllib.parse import quote_plus, urlparse
from html.parser import HTMLParser

# ────────────────────────────────────────
# 配置
# ────────────────────────────────────────

DEFAULT_TIMEOUT = 15          # 默认超时（秒）
MAX_TIMEOUT = 60              # 最大超时（秒）
MAX_CONTENT_SIZE = 100_000    # 最大内容大小（100KB）
MAX_SEARCH_RESULTS = 20       # 最大搜索结果数

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 搜索引擎配置
SEARCH_ENGINES = {
    "duckduckgo": {
        "url": "https://html.duckduckgo.com/html/",
        "name": "DuckDuckGo",
    },
    "searxng": {
        "url": os.environ.get("SEARXNG_URL", "https://searx.be/search"),
        "name": "SearXNG",
    },
}


# ────────────────────────────────────────
# HTML 清洗器
# ────────────────────────────────────────

class HTMLTextExtractor(HTMLParser):
    """从 HTML 提取纯文本"""
    
    SKIP_TAGS = {'script', 'style', 'noscript', 'iframe', 'object', 'embed', 'head'}
    
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip_depth = 0
        self.current_tag = None
        
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        self.current_tag = tag
        
        # 标题处理
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag[1])
            self.result.append('\n' + '#' * level + ' ')
        
        # 段落和换行
        if tag == 'p':
            self.result.append('\n\n')
        if tag == 'br':
            self.result.append('\n')
        if tag == 'li':
            self.result.append('\n- ')
            
    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.result.append('\n')
            
    def handle_data(self, data):
        if self.skip_depth == 0:
            self.result.append(data)
            
    def get_text(self):
        text = ''.join(self.result)
        # 清理多余空白
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()


def html_to_text(html: str) -> str:
    """HTML 转纯文本"""
    extractor = HTMLTextExtractor()
    try:
        extractor.feed(html)
        return extractor.get_text()
    except Exception:
        # 回退：简单正则清洗
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text


# ────────────────────────────────────────
# 工具定义
# ────────────────────────────────────────

TOOLS = [
    {
        "name": "web_search",
        "description": "联网搜索 - 使用搜索引擎搜索信息，返回标题、链接、摘要。支持 DuckDuckGo（国外）、百度（国内）、SearXNG（自建）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词"
                },
                "num_results": {
                    "type": "integer",
                    "description": f"返回结果数量（默认10，最大 {MAX_SEARCH_RESULTS}）",
                    "minimum": 1,
                    "maximum": MAX_SEARCH_RESULTS
                },
                "engine": {
                    "type": "string",
                    "description": "搜索引擎（duckduckgo/baidu/searxng，默认自动选择）",
                    "enum": ["duckduckgo", "baidu", "searxng"]
                },
                "region": {
                    "type": "string",
                    "description": "搜索区域（如 cn-zh, us-en）"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "web_fetch",
        "description": "抓取网页内容 - 获取URL内容并转为纯文本",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要抓取的URL"
                },
                "format": {
                    "type": "string",
                    "description": "返回格式（text/markdown/html）",
                    "enum": ["text", "markdown", "html"],
                    "default": "text"
                },
                "timeout": {
                    "type": "integer",
                    "description": f"超时秒数（默认 {DEFAULT_TIMEOUT}，最大 {MAX_TIMEOUT}）",
                    "minimum": 1,
                    "maximum": MAX_TIMEOUT
                },
                "max_size": {
                    "type": "integer",
                    "description": f"最大内容大小（默认 {MAX_CONTENT_SIZE}）",
                    "minimum": 1000,
                    "maximum": 1024 * 1024
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "fetch_json",
        "description": "获取JSON数据 - 从URL获取并解析JSON",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "JSON数据URL"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数",
                    "default": DEFAULT_TIMEOUT
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "search_news",
        "description": "搜索新闻 - 搜索最新新闻资讯",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "新闻关键词"
                },
                "num_results": {
                    "type": "integer",
                    "description": "返回数量",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
]


# ────────────────────────────────────────
# HTTP 请求辅助
# ────────────────────────────────────────

async def http_get(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True
) -> bytes:
    """异步 HTTP GET 请求"""
    try:
        import httpx
    except ImportError:
        # 回退到 urllib
        import urllib.request
        
        req_headers = {"User-Agent": USER_AGENT}
        if headers:
            req_headers.update(headers)
        
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
        headers={"User-Agent": USER_AGENT, **(headers or {})}
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


async def http_post(
    url: str,
    data: Optional[Dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
    headers: Optional[Dict[str, str]] = None
) -> bytes:
    """异步 HTTP POST 请求"""
    try:
        import httpx
    except ImportError:
        import urllib.request
        import urllib.parse
        
        req_headers = {"User-Agent": USER_AGENT}
        if headers:
            req_headers.update(headers)
        
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=req_headers, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    
    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, **(headers or {})}
    ) as client:
        response = await client.post(url, json=data)
        response.raise_for_status()
        return response.content


# ────────────────────────────────────────
# 搜索引擎实现
# ────────────────────────────────────────

async def search_duckduckgo(
    query: str,
    num_results: int = 10,
    region: Optional[str] = None
) -> List[Dict[str, str]]:
    """DuckDuckGo 搜索（带超时保护）"""
    results = []
    
    try:
        # DuckDuckGo HTML 版本
        params = {"q": query}
        if region:
            params["kl"] = region
        
        # 使用更短的超时时间（8秒）
        content = await asyncio.wait_for(
            http_post(
                SEARCH_ENGINES["duckduckgo"]["url"],
                data=params,
                timeout=8,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ),
            timeout=10
        )
        
        html = content.decode('utf-8', errors='replace')
        
        # 解析结果
        result_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        
        for match in result_pattern.finditer(html):
            if len(results) >= num_results:
                break
            
            url = match.group(1)
            title = html_to_text(match.group(2))
            snippet = html_to_text(match.group(3))
            
            # 清理 URL（DuckDuckGo 重定向）
            if 'duckduckgo.com' in url:
                url_match = re.search(r'uddg=([^&]+)', url)
                if url_match:
                    from urllib.parse import unquote
                    url = unquote(url_match.group(1))
            
            results.append({
                "title": title,
                "url": url,
                "snippet": snippet
            })
    
    except asyncio.TimeoutError:
        # DuckDuckGo 超时，静默失败
        pass
    except Exception as e:
        # DuckDuckGo 失败，尝试使用 API
        try:
            api_url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1"
            content = await asyncio.wait_for(
                http_get(api_url, timeout=5),
                timeout=7
            )
            data = json.loads(content)
            
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", query),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data.get("Abstract", "")
                })
            
            for topic in data.get("RelatedTopics", [])[:num_results - len(results)]:
                if isinstance(topic, dict) and 'Text' in topic:
                    results.append({
                        "title": topic.get("Text", "")[:100],
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", "")
                    })
        except:
            pass
    
    return results


async def search_baidu(
    query: str,
    num_results: int = 10
) -> List[Dict[str, str]]:
    """百度搜索（国内可用，使用移动版）"""
    results = []
    seen_titles = set()  # 去重
    
    try:
        # 百度移动版搜索 URL
        url = f"https://m.baidu.com/s?word={quote_plus(query)}"
        
        # 使用移动版 User-Agent
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        
        # 使用 httpx 获取
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                html = response.text
        except ImportError:
            # 回退到 curl
            proc = await asyncio.create_subprocess_exec(
                'curl', '-sSL', '--max-time', '10',
                '-H', f'User-Agent: {headers["User-Agent"]}',
                '-H', 'Accept-Language: zh-CN,zh;q=0.9',
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=12)
            html = stdout.decode('utf-8', errors='replace')
        
        # 解析百度移动版搜索结果
        # 尝试多种模式匹配
        patterns = [
            # 模式1: h3 + a 结构（最常见）
            re.compile(
                r'<h3[^>]*>.*?<a[^>]*href="(https?://[^"]*)"[^>]*>(.*?)</a>.*?</h3>',
                re.DOTALL
            ),
            # 模式2: c-result 结构
            re.compile(
                r'<div[^>]*class="[^"]*c-result[^"]*"[^>]*>.*?'
                r'<a[^>]*href="(https?://[^"]*)"[^>]*>(.*?)</a>',
                re.DOTALL
            ),
            # 模式3: 更宽松的链接匹配
            re.compile(
                r'<a[^>]*href="(https?://(?!m\.baidu\.com|haokan\.baidu\.com)[^"]*)"[^>]*>(.*?)</a>',
                re.DOTALL
            ),
        ]
        
        for pattern in patterns:
            if len(results) >= num_results:
                break
            for match in pattern.finditer(html):
                if len(results) >= num_results:
                    break
                
                url = match.group(1)
                title_raw = match.group(2)
                
                # 清理标题
                title = re.sub(r'<[^>]+>', '', title_raw)  # 移除HTML标签
                title = re.sub(r'&[a-zA-Z]+;', '', title)  # 移除HTML实体
                title = re.sub(r'&#\d+;', '', title)  # 移除数字实体
                title = re.sub(r'\s+', ' ', title).strip()  # 合并空白
                
                # 过滤无效结果
                if not title or len(title) < 4:
                    continue
                if 'javascript:' in url or url.startswith('#'):
                    continue
                if 'baidu.com/s' in url or 'baidu.com/link' in url:
                    continue  # 跳过百度搜索结果页
                if 'haokan.baidu.com' in url:
                    continue  # 跳过好看视频
                if title in seen_titles:
                    continue  # 去重
                # 跳过广告和推广
                if '百度推广' in title or '广告' in title:
                    continue
                
                seen_titles.add(title)
                results.append({
                    "title": title[:100],
                    "url": url,
                    "snippet": ""
                })
    
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        pass
    
    return results


async def search_searxng(
    query: str,
    num_results: int = 10,
    engine_url: Optional[str] = None
) -> List[Dict[str, str]]:
    """SearXNG 搜索"""
    results = []
    
    url = engine_url or SEARCH_ENGINES["searxng"]["url"]
    
    try:
        params = {
            "q": query,
            "format": "json",
            "categories": "general"
        }
        
        # 构建查询字符串
        query_string = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        full_url = f"{url}?{query_string}"
        
        content = await http_get(full_url, timeout=DEFAULT_TIMEOUT)
        data = json.loads(content)
        
        for item in data.get("results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", "")[:300]
            })
    
    except Exception as e:
        raise Exception(f"SearXNG 搜索失败: {str(e)}")
    
    return results


# ────────────────────────────────────────
# 工具处理函数
# ────────────────────────────────────────

async def handle_web_search(
    query: str,
    num_results: int = 10,
    engine: str = "duckduckgo",
    region: Optional[str] = None
) -> Dict[str, Any]:
    """执行网页搜索（多引擎自动降级）"""
    num_results = min(max(num_results, 1), MAX_SEARCH_RESULTS)
    
    start_time = time.time()
    results = []
    used_engine = engine
    
    try:
        # 热搜检测：当查询包含热搜关键词时，调用专门的热搜API
        is_hot = "热搜" in query or "热榜" in query or "trending" in query.lower()
        if is_hot:
            try:
                from core.multi_agent_v2.tools.tool_registry import _handle_hot_search
                hot_results = await _handle_hot_search(query)
                if hot_results:
                    content = hot_results.get("result", {}).get("content", [{}])
                    if content:
                        return {"text": content[0].get("text", "")}
            except Exception:
                pass  # 热搜API失败，继续使用普通搜索
        
        # 优先尝试指定引擎
        if engine == "searxng":
            results = await search_searxng(query, num_results)
            used_engine = "searxng"
        elif engine == "baidu":
            results = await search_baidu(query, num_results)
            used_engine = "baidu"
        else:
            # 尝试 DuckDuckGo，失败则自动降级到百度
            results = await search_duckduckgo(query, num_results, region)
            if results:
                used_engine = "duckduckgo"
            else:
                # DuckDuckGo 无结果，降级到百度
                results = await search_baidu(query, num_results)
                used_engine = "baidu"
        
        elapsed = time.time() - start_time
        
        if not results:
            return {
                "text": f"🔍 搜索完成，未找到结果\n"
                        f"查询: {query}\n"
                        f"引擎: {used_engine}\n"
                        f"耗时: {elapsed:.2f}秒\n"
                        f"提示: 所有搜索引擎均无结果，请尝试其他关键词"
            }
        
        # 格式化结果
        lines = [
            f"🔍 搜索结果 ({len(results)} 条)",
            f"查询: {query}",
            f"引擎: {used_engine}",
            f"耗时: {elapsed:.2f}秒",
            ""
        ]
        
        for i, result in enumerate(results, 1):
            lines.append(f"{i}. **{result['title']}**")
            lines.append(f"   🔗 {result['url']}")
            if result.get('snippet'):
                lines.append(f"   📝 {result['snippet'][:200]}")
            lines.append("")
        
        return {"text": "\n".join(lines)}
    
    except Exception as e:
        return {
            "text": f"❌ 搜索失败: {str(e)}\n"
                    f"查询: {query}\n"
                    f"引擎: {engine}"
        }


async def handle_web_fetch(
    url: str,
    format: str = "text",
    timeout: int = DEFAULT_TIMEOUT,
    max_size: int = MAX_CONTENT_SIZE
) -> Dict[str, Any]:
    """抓取网页内容"""
    timeout = min(max(timeout, 1), MAX_TIMEOUT)
    
    # URL 验证
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return {"text": f"❌ 无效的URL: {url}\n仅支持 http:// 和 https://"}
    
    start_time = time.time()
    
    try:
        content = await http_get(url, timeout=timeout)
        
        # 大小检查
        if len(content) > max_size:
            content = content[:max_size]
            truncated = True
        else:
            truncated = False
        
        # 解码
        text = content.decode('utf-8', errors='replace')
        
        # 根据格式处理
        if format == "html":
            output = text
        elif format == "markdown":
            # 简单的 HTML 转 Markdown
            output = html_to_text(text)
        else:
            output = html_to_text(text)
        
        # 截断处理
        if len(output) > max_size:
            output = output[:max_size] + "\n\n[内容已截断]"
            truncated = True
        
        elapsed = time.time() - start_time
        
        lines = [
            f"📄 网页内容",
            f"🔗 URL: {url}",
            f"📏 大小: {len(content)} 字节",
            f"⏱️ 耗时: {elapsed:.2f}秒",
            f"📋 格式: {format}",
            ""
        ]
        
        if truncated:
            lines.append("⚠️ 内容已截断")
            lines.append("")
        
        lines.append(output)
        
        return {"text": "\n".join(lines)}
    
    except Exception as e:
        return {
            "text": f"❌ 抓取失败: {str(e)}\n"
                    f"URL: {url}"
        }


async def handle_fetch_json(
    url: str,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """获取 JSON 数据"""
    timeout = min(max(timeout, 1), MAX_TIMEOUT)
    
    try:
        content = await http_get(url, timeout=timeout)
        data = json.loads(content)
        
        # 格式化输出
        output = json.dumps(data, indent=2, ensure_ascii=False)
        
        # 截断
        if len(output) > MAX_CONTENT_SIZE:
            output = output[:MAX_CONTENT_SIZE] + "\n\n[数据已截断]"
        
        return {
            "text": f"📊 JSON 数据\n"
                    f"URL: {url}\n"
                    f"大小: {len(content)} 字节\n\n"
                    f"```json\n{output}\n```"
        }
    
    except json.JSONDecodeError as e:
        return {"text": f"❌ JSON 解析失败: {str(e)}\nURL: {url}"}
    except Exception as e:
        return {"text": f"❌ 获取失败: {str(e)}\nURL: {url}"}


async def handle_search_news(
    query: str,
    num_results: int = 10
) -> Dict[str, Any]:
    """搜索新闻"""
    # 在搜索词后添加 news 关键词
    news_query = f"{query} news"
    
    return await handle_web_search(
        query=news_query,
        num_results=num_results,
        engine="duckduckgo"
    )


# ────────────────────────────────────────
# 请求处理
# ────────────────────────────────────────

async def handle_request(request: dict) -> dict:
    """处理 JSON-RPC 请求"""
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "name": "web-search",
                "version": "1.0.0",
                "description": "联网搜索服务 - 搜索引擎查询和网页内容抓取"
            }
        }
    
    if method in ("tools/list", "listTools"):
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    
    if method in ("tools/call", "callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})
        
        try:
            if tool == "web_search":
                r = await handle_web_search(
                    query=args["query"],
                    num_results=args.get("num_results", 10),
                    engine=args.get("engine", "duckduckgo"),
                    region=args.get("region"),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}
            
            if tool == "web_fetch":
                r = await handle_web_fetch(
                    url=args["url"],
                    format=args.get("format", "text"),
                    timeout=args.get("timeout", DEFAULT_TIMEOUT),
                    max_size=args.get("max_size", MAX_CONTENT_SIZE),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}
            
            if tool == "fetch_json":
                r = await handle_fetch_json(
                    url=args["url"],
                    timeout=args.get("timeout", DEFAULT_TIMEOUT),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}
            
            if tool == "search_news":
                r = await handle_search_news(
                    query=args["query"],
                    num_results=args.get("num_results", 10),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}
            
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": f"未知工具: {tool}"}
            }
        
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32000, "message": str(e)}
            }
    
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "error": {"code": -32601, "message": f"未知方法: {method}"}
    }


# ────────────────────────────────────────
# 主函数
# ────────────────────────────────────────

def main():
    """stdio 模式主循环"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
            
            # 通知消息没有 id 字段，不需要响应
            if "id" not in request:
                # 处理通知（如 notifications/initialized）
                continue
            
            response = asyncio.run(handle_request(request))
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None
            }
            print(json.dumps(error_response))
            sys.stdout.flush()
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": None
            }
            print(json.dumps(error_response))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
