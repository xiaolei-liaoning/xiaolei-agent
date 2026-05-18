"""
百度热搜爬虫

数据源: https://top.baidu.com/board?tab=realtime
解析方式: httpx + BeautifulSoup (CSS选择器)
降级策略: API → Playwright
"""
import asyncio
import logging
import random
import re
from typing import Dict, List, Optional, Any
from urllib.parse import quote
from pathlib import Path
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

_HEADERS_POOL = [
    {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.baidu.com/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Referer': 'https://www.baidu.com/s?wd=',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
    },
]

_TIMEOUT = 10.0


def _get_headers(**extra: str) -> dict:
    """获取随机请求头"""
    headers = random.choice(_HEADERS_POOL).copy()
    headers.update(extra)
    return headers


class BaiduScraper:
    """
    百度热搜爬虫

    支持功能:
        - get_hot_list: 获取百度实时热搜榜
        - search: 搜索关键词相关内容
    """

    def get_hot_list(self, top_n: int = 10) -> List[Dict[str, str]]:
        """
        获取百度热搜榜

        优先使用 httpx + BeautifulSoup 解析，失败后降级到 Playwright。

        Args:
            top_n: 返回条数，默认10

        Returns:
            [{"title": str, "heat": str, "url": str, "label": str}, ...]
        """
        try:
            result = self._fetch_via_httpx(top_n)
            if result:
                return result
        except Exception as e:
            logger.warning(f"百度热搜httpx获取失败: {e}")

        try:
            result = self._fetch_via_playwright(top_n)
            if result:
                return result
        except Exception as e:
            logger.error(f"百度热搜Playwright获取也失败: {e}")

        return []

    def search(self, keyword: str, top_n: int = 10) -> List[Dict[str, str]]:
        """
        搜索百度内容

        Args:
            keyword: 搜索关键词
            top_n: 返回条数

        Returns:
            [{"title": str, "heat": str, "url": str, "label": str}, ...]
        """
        try:
            return self._search_via_httpx(keyword, top_n)
        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
            try:
                return self._search_via_playwright(keyword, top_n)
            except Exception as e2:
                logger.error(f"百度搜索Playwright也失败: {e2}")
                return []

    def _fetch_via_httpx(self, top_n: int) -> Optional[List[Dict[str, str]]]:
        """
        httpx + BeautifulSoup 解析百度热搜页面

        Args:
            top_n: 返回条数

        Returns:
            解析结果列表，失败返回None
        """
        url = 'https://top.baidu.com/board?tab=realtime'
        headers = _get_headers(Referer='https://www.baidu.com/')

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, 'html.parser')
        results: List[Dict[str, str]] = []

        # CSS选择器提取热搜条目
        items = soup.select('.category-wrap_iQLoo .c-single-text-ellipsis')
        heat_items = soup.select('.hot-index_1Bl1a')
        link_items = soup.select('.category-wrap_iQLoo a')

        if not items:
            # 尝试备用选择器
            items = soup.select('[class*="content_"] [class*="title"]')
            heat_items = soup.select('[class*="hot-index"]')
            link_items = soup.select('[class*="content_"] a[href]')

        for i, item in enumerate(items[:top_n]):
            try:
                title = item.get_text(strip=True)
                if not title:
                    continue

                heat = ''
                if i < len(heat_items):
                    heat = heat_items[i].get_text(strip=True)

                url_link = ''
                if i < len(link_items):
                    href = link_items[i].get('href', '')
                    if href:
                        url_link = href if href.startswith('http') else f'https://top.baidu.com{href}'

                results.append({
                    'title': title,
                    'heat': heat,
                    'url': url_link,
                    'label': '',
                })
            except Exception as e:
                logger.debug(f"百度热搜条目解析异常: {e}")
                continue

        return results if results else None

    def _fetch_via_playwright(self, top_n: int) -> Optional[List[Dict[str, str]]]:
        """Playwright降级方案"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._async_fetch_playwright(top_n))

    async def _async_fetch_playwright(self, top_n: int) -> Optional[List[Dict[str, str]]]:
        """Playwright异步获取百度热搜"""
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
            )
            context = await browser.new_context(
                user_agent=_get_headers()['User-Agent'],
                locale='zh-CN',
            )
            page = await context.new_page()
            await page.goto(
                'https://top.baidu.com/board?tab=realtime',
                timeout=_TIMEOUT * 1000,
                wait_until='domcontentloaded',
            )
            await page.wait_for_selector('.category-wrap_iQLoo', timeout=5000)

            items = await page.query_selector_all('.category-wrap_iQLoo')
            results: List[Dict[str, str]] = []

            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('.c-single-text-ellipsis')
                    heat_el = await item.query_selector('.hot-index_1Bl1a')
                    link_el = await item.query_selector('a')

                    title = (await title_el.inner_text()).strip() if title_el else ''
                    heat = (await heat_el.inner_text()).strip() if heat_el else ''
                    link = (await link_el.get_attribute('href')) if link_el else ''

                    if title:
                        results.append({
                            'title': title,
                            'heat': heat,
                            'url': link or '',
                            'label': '',
                        })
                except Exception:
                    continue

            await browser.close()
            return results
    
    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """爬取百度数据
        
        Args:
            action: 操作类型 (热搜/搜索)
            top_n: 返回数量
            keyword: 搜索关键词
            generate_report: 是否生成MD报告
            download_images: 是否下载图片
            download_videos: 是否下载视频
            download_audio: 是否下载音频
            extract_tables: 是否提取表格
            
        Returns:
            爬取结果
        """

        action = kwargs.get("action", "热搜")
        top_n = kwargs.get("top_n", 10)
        keyword = kwargs.get("keyword", "")
        generate_report = kwargs.get("generate_report", False)
        
        try:
            if action in ["热搜", "热榜"]:
                data = self.get_hot_list(top_n=top_n)
            elif action in ["搜索", "search"]:
                data = self.search(keyword, top_n=top_n)
            else:
                data = self.get_hot_list(top_n=top_n)
            
            # 保存CSV
            csv_path = None
            if data:
                csv_path = self._save_to_csv(data, action)
            
            # 生成MD报告
            md_path = None
            if generate_report and data:
                md_path = self._generate_md_report(data, action)
            
            result = {
                "success": True,
                "count": len(data),
                "data": data,
                "site": "百度",
                "action": action,
                "csv_path": str(csv_path) if csv_path else None,
                "md_path": str(md_path) if md_path else None,
            }
            
            return result
        except Exception as e:
            logger.error(f"百度爬虫执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "site": "百度",
                "count": 0
            }

    def _generate_md_report(self, data: List[Dict], action: str) -> Path:
        """生成MD报告并保存到桌面"""
        from datetime import datetime
        from pathlib import Path
        import platform
        import subprocess
        
        desktop = Path.home() / "Desktop"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"百度{action}_{timestamp}.md"
        filepath = desktop / filename
        
        lines = [
            f"# 百度{action}榜\n",
            f"**爬取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**总数**: {len(data)} 条\n",
        ]
        
        lines.append("\n---\n")
        
        for item in data:
            title = item.get('title', '').strip().replace('\n', ' ').replace('  ', ' ')
            lines.append(f"## {item.get('排名', '')}. {title}\n")
            
            if item.get('heat'):
                lines.append(f"- **热度**: {item['heat']}\n")
            if item.get('url'):
                lines.append(f"- **链接**: [查看详情]({item['url']})\n")
            lines.append("")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        # macOS自动打开
        if platform.system() == "Darwin":
            subprocess.run(["open", str(filepath)], check=False)
        
        logger.info(f"MD报告已保存到桌面: {filepath}")
        return filepath

    def _save_to_csv(self, data: List[Dict], action: str) -> Path:
        """保存为CSV"""
        import csv
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"baidu_{action}_{timestamp}.csv"
        filepath = OUTPUT_DIR / filename
        
        if data:
            fieldnames = list(data[0].keys())
            
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for item in data:
                    writer.writerow(item)
            
            logger.info(f"CSV已保存: {filepath}")
        
        return filepath

    def _search_via_httpx(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        """httpx搜索百度"""
        url = 'https://www.baidu.com/s'
        params = {'wd': keyword, 'rn': top_n}
        headers = _get_headers(Referer='https://www.baidu.com/')

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, 'html.parser')
        results: List[Dict[str, str]] = []

        items = soup.select('.result.c-container')
        if not items:
            items = soup.select('div[id^="norm"]')

        for item in items[:top_n]:
            try:
                title_el = item.select_one('h3 a')
                snippet_el = item.select_one('.c-abstract')

                title = title_el.get_text(strip=True) if title_el else ''
                link = title_el.get('href', '') if title_el else ''
                snippet = snippet_el.get_text(strip=True)[:100] if snippet_el else ''

                if title:
                    results.append({
                        'title': title,
                        'heat': '',
                        'url': link,
                        'label': snippet,
                    })
            except Exception:
                continue

        return results

    def _search_via_playwright(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        """Playwright搜索百度"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            return loop.run_until_complete(self._async_search_playwright(keyword, top_n))
        except Exception as e:
            logger.error(f"Playwright搜索失败: {e}")
            return []

    async def _async_search_playwright(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        """Playwright异步搜索"""
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(user_agent=_get_headers()['User-Agent'])
            page = await context.new_page()

            await page.goto(
                f'https://www.baidu.com/s?wd={quote(keyword)}',
                timeout=_TIMEOUT * 1000,
                wait_until='domcontentloaded',
            )
            await page.wait_for_selector('.result', timeout=5000)

            items = await page.query_selector_all('.result.c-container')
            results: List[Dict[str, str]] = []

            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('h3 a')
                    title = (await title_el.inner_text()).strip() if title_el else ''
                    link = (await title_el.get_attribute('href')) if title_el else ''

                    if title:
                        results.append({
                            'title': title,
                            'heat': '',
                            'url': link or '',
                            'label': '',
                        })
                except Exception:
                    continue

            await browser.close()
            return results