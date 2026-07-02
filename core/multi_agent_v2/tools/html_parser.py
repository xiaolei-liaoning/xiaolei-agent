"""
HTML 解析工具 — 网页→纯文本 + 搜索结果提取

借鉴 OpenCode 的 extractTextFromHTML，消除 3 处重复 HTML 清洗逻辑。
"""
import re
from typing import Dict, List, Tuple


def html_to_text(html: str, max_length: int = 8000) -> str:
    """HTML → 纯文本，去标签/脚本/样式/噪声"""
    if not html:
        return ""

    # 1. 去 script/style/noscript/iframe 等非内容标签
    text = re.sub(
        r'<(script|style|noscript|iframe|object|embed|svg)[^>]*>.*?</\1>',
        '', html, flags=re.DOTALL | re.IGNORECASE,
    )
    # 2. 去 HTML 注释
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # 3. 去所有标签
    text = re.sub(r'<[^>]+>', ' ', text)
    # 4. HTML 实体解码（常见）
    for entity, char in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
                         ('&quot;', '"'), ('&#39;', "'"), ('&nbsp;', ' ')]:
        text = text.replace(entity, char)
    # 5. 去多余空白
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    # 6. 还原段落换行
    text = text.replace('. ', '.\n')
    text = text.replace('。', '。\n')
    # 7. 去 URL 噪声
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[\w.-]+\.(com|cn|net|org|io|html?|php)\S*', '', text)
    # 8. 最终清理
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    if len(text) > max_length:
        head = text[:int(max_length * 0.7)]
        tail = text[-int(max_length * 0.2):]
        text = f"{head}\n\n... [省略 {len(text) - max_length} 字符] ...\n\n{tail}"

    return text


def extract_search_results_bing(html: str) -> List[Dict[str, str]]:
    """从 Bing 搜索结果页提取标题+摘要+URL"""
    results = []
    for block in re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL):
        title_m = re.search(r'<h2><a[^>]*href="([^"]*)"[^>]*>(.*?)</a></h2>', block, re.DOTALL)
        snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        if title_m:
            url = title_m.group(1)
            title = re.sub(r'<[^>]+>', '', title_m.group(2)).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip() if snippet_m else ""
            results.append({"title": title, "url": url, "snippet": snippet[:200]})
    return results


def extract_search_results_baidu(html: str) -> List[Dict[str, str]]:
    """从百度搜索结果页提取标题+摘要+URL"""
    results = []
    for block in re.findall(r'<div class="result c-container[^"]*"[^>]*>(.*?)</div>\s*(?=<div class="result|</div>)', html, re.DOTALL):
        title_m = re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
        snippet_m = re.search(r'<span class="content-right_[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        if not snippet_m:
            snippet_m = re.search(r'<div class="c-abstract[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
        if title_m:
            url = title_m.group(1)
            title = re.sub(r'<[^>]+>', '', title_m.group(2)).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip() if snippet_m else ""
            results.append({"title": title, "url": url, "snippet": snippet[:200]})
    return results


def extract_search_results_ddg(html: str) -> List[Dict[str, str]]:
    """从 DuckDuckGo HTML 版搜索结果页提取标题+摘要+URL"""
    results = []
    for block in re.findall(r'<div class="result__body">(.*?)</div>\s*</div>', html, re.DOTALL):
        title_m = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
        snippet_m = re.search(r'<a class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
        if title_m:
            url = title_m.group(1)
            title = re.sub(r'<[^>]+>', '', title_m.group(2)).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip() if snippet_m else ""
            results.append({"title": title, "url": url, "snippet": snippet[:200]})
    return results


def merge_search_results(sources: List[Tuple[str, List[Dict[str, str]]]]) -> str:
    """合并多引擎搜索结果，去重，格式化输出"""
    seen_urls: set = set()
    lines: List[str] = []
    total = 0

    for engine_name, results in sources:
        if not results:
            continue
        lines.append(f"\n【{engine_name}】")
        for r in results:
            url = r.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            total += 1
            title = r.get("title", "无标题")
            snippet = r.get("snippet", "")
            lines.append(f"  {total}. {title}")
            if snippet:
                lines.append(f"     {snippet}")
            lines.append(f"     {url}")

    if not lines:
        return "未找到相关结果"

    header = f"搜索结果（共 {total} 条，来自 {len(sources)} 个引擎）"
    return header + "\n" + "\n".join(lines)
