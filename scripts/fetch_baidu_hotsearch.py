#!/usr/bin/env python3
"""百度热搜爬取工具 — 供Agent调用"""
import json, re, urllib.request, urllib.error, ssl
from html.parser import HTMLParser

class HotSearchParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.titles = []
        self._tag_stack = []
    def handle_starttag(self, tag, attrs):
        self._tag_stack.append(tag)
        attrs_d = dict(attrs)
        if tag in ('a', 'span', 'div') and 'title' in attrs_d:
            if len(attrs_d['title']) > 4 and len(attrs_d['title']) < 100:
                self.titles.append(attrs_d['title'])
        if tag == 'div' and 'class' in attrs_d and 'c-single-text-ellipsis' in attrs_d.get('class', ''):
            self.in_title = True

def fetch_baidu_hotsearch():
    """获取百度实时热搜榜"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = "https://top.baidu.com/board?tab=realtime"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    })

    try:
        resp = urllib.request.urlopen(req, timeout=10, context=ctx)
        html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return {"error": str(e), "html_preview": ""}

    # 提取热点标题
    parser = HotSearchParser()
    parser.feed(html)

    # 也尝试正则提取
    patterns = [
        r'<div[^>]*class="[^"]*c-single-text-ellipsis[^"]*"[^>]*>([^<]+)',
        r'<a[^>]*title="([^"]{4,80})"',
        r'>(第\d名|TOP\d|)\s*[:：]\s*([^<]{4,60})<',
    ]
    titles = []
    for p in patterns:
        matches = re.findall(p, html)
        for m in matches:
            t = m if isinstance(m, str) else m[-1]
            t = t.strip()
            if len(t) > 4 and len(t) < 80 and t not in titles:
                titles.append(t)

    # 合并去重
    all_titles = []
    seen = set()
    for t in parser.titles + titles:
        if t not in seen:
            seen.add(t)
            all_titles.append(t)

    return {
        "top5": all_titles[:5],
        "all": all_titles[:20],
        "total": len(all_titles),
        "note": "来自百度实时热搜榜",
    }

if __name__ == "__main__":
    result = fetch_baidu_hotsearch()
    print(json.dumps(result, ensure_ascii=False, indent=2))
