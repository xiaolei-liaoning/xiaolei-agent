"""HTML → 纯文本（V1 独立版）"""

import html
import re


def html_to_text(html: str, max_length: int = 8000) -> str:
    if not html:
        return ""
    text = re.sub(r'<(script|style|noscript|iframe|object|embed|svg)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()[:max_length]


def extract_search_results(html: str, engine: str = "baidu") -> list:
    """从搜索引擎结果页提取标题+链接+摘要"""
    from urllib.parse import unquote
    results = []
    if engine == "baidu":
        for item in re.findall(r'<div[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)[:10]:
            title_m = re.search(r'<a[^>]*>(.*?)</a>', item)
            link_m = re.search(r'href="(https?://[^"]+)"', item)
            desc_m = re.search(r'<div[^>]*class="[^"]*c-abstract[^"]*"[^>]*>(.*?)</div>', item, re.DOTALL)
            if title_m:
                results.append({
                    "title": re.sub(r'<[^>]+>', '', title_m.group(1)).strip(),
                    "link": unquote(link_m.group(1)) if link_m else "",
                    "snippet": re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()[:200] if desc_m else "",
                })
    return results
