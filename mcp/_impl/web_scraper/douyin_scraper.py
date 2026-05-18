"""
抖音热搜爬虫

数据源:
    - API尝试: https://www.douyin.com/aweme/v1/web/hot/search/list/
    - 备用: Playwright爬取 https://www.douyin.com/hot
降级策略: API → Playwright
"""
import asyncio
import json
import logging
import random
import re
from typing import Dict, List, Optional, Any
from urllib.parse import quote
from pathlib import Path
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

_HEADERS_POOL = [
    {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cookie': 'ttwid=1',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/explore',
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


def _format_hot_value(val: Optional[int]) -> str:
    """格式化热度数值"""
    if val is None:
        return ''
    if val >= 100_000_000:
        return f'{val / 100_000_000:.1f}亿'
    if val >= 10_000:
        return f'{val / 10_000:.1f}万'
    return str(val)


class DouyinScraper:
    """
    抖音热搜爬虫

    支持功能:
        - get_hot_list: 获取抖音热搜榜
        - search: 搜索抖音内容

    注意: 抖音反爬较严格，API可能需要cookie/msToken，
          失败时自动降级到Playwright渲染。
    """

    def get_hot_list(self, top_n: int = 10) -> List[Dict[str, str]]:
        """
        获取抖音热搜榜

        优先使用API，失败后降级到Playwright。

        Args:
            top_n: 返回条数，默认10

        Returns:
            [{"title": str, "heat": str, "url": str, "label": str}, ...]
        """
        try:
            result = self._fetch_via_api(top_n)
            if result:
                return result
        except Exception as e:
            logger.warning(f"抖音热搜API获取失败: {e}")

        try:
            result = self._fetch_via_playwright(top_n)
            if result:
                return result
        except Exception as e:
            logger.error(f"抖音热搜Playwright获取也失败: {e}")

        return []

    def search(self, keyword: str, top_n: int = 10) -> List[Dict[str, str]]:
        """
        搜索抖音内容

        Args:
            keyword: 搜索关键词
            top_n: 返回条数

        Returns:
            [{"title": str, "heat": str, "url": str, "label": str}, ...]
        """
        try:
            result = self._search_via_playwright(keyword, top_n)
            if result:
                return result
        except Exception as e:
            logger.error(f"抖音搜索失败: {e}")

        return []

    def _fetch_via_api(self, top_n: int) -> Optional[List[Dict[str, str]]]:
        """
        尝试通过抖音Web API获取热搜

        Args:
            top_n: 返回条数

        Returns:
            解析结果列表，失败返回None
        """
        url = 'https://www.douyin.com/aweme/v1/web/hot/search/list/'
        params = {
            'detail_list': '1',
            'count': top_n,
        }
        headers = _get_headers(
            Referer='https://www.douyin.com/hot',
        )

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()

            # 尝试JSON解析
            try:
                data = resp.json()
            except (json.JSONDecodeError, Exception):
                # 非JSON响应，可能被重定向或拦截
                logger.debug("抖音API返回非JSON响应")
                return None

        if data.get('status_code') != 0:
            logger.debug(f"抖音API错误码: {data.get('status_code')}")
            return None

        word_list = data.get('data', {}).get('word_list', [])
        if not word_list:
            return None

        results: List[Dict[str, str]] = []
        for item in word_list[:top_n]:
            try:
                sentence_info = item.get('sentence_info', {}) or {}
                event_time = item.get('event_time', 0) or 0

                results.append({
                    'title': item.get('word', '') or '',
                    'heat': _format_hot_value(item.get('hot_value')),
                    'url': f"https://www.douyin.com/hot/{item.get('sentence_id', '')}",
                    'label': sentence_info.get('label', '') or '',
                })
            except Exception as e:
                logger.debug(f"抖音热搜条目解析异常: {e}")
                continue

        return results if results else None

    def _fetch_via_playwright(self, top_n: int) -> Optional[List[Dict[str, str]]]:
        """Playwright降级方案：渲染抖音热搜页面"""
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
        """Playwright异步获取抖音热搜"""
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-images',
                ],
            )
            context = await browser.new_context(
                user_agent=_get_headers()['User-Agent'],
                locale='zh-CN',
                viewport={'width': 1920, 'height': 1080},
            )
            page = await context.new_page()

            # 注入stealth脚本
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
            """)

            try:
                await page.goto(
                    'https://www.douyin.com/hot',
                    timeout=_TIMEOUT * 1000,
                    wait_until='domcontentloaded',
                )
                # 等待热搜列表渲染（抖音是SPA，需要等待JS加载）
                await page.wait_for_selector(
                    'ul.hot-list li, div[class*="hotList"] div, [data-e2e="hot-list"] li',
                    timeout=8000,
                )
            except Exception as e:
                logger.debug(f"抖音热搜页面等待超时: {e}")

            # 尝试多种选择器匹配抖音的DOM结构
            selectors = [
                'ul.hot-list li',
                'div[class*="hotList"] > div',
                '[data-e2e="hot-list"] li',
                'div[class*="hot-search"] div[class*="item"]',
                'a[href*="/search/"]',
            ]

            items = []
            for selector in selectors:
                items = await page.query_selector_all(selector)
                if items:
                    break

            results: List[Dict[str, str]] = []

            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('a, h3, p, span[class*="title"], [class*="text"]')
                    heat_el = await item.query_selector('[class*="hot"], [class*="count"], [class*="heat"]')
                    link_el = await item.query_selector('a')

                    title = ''
                    if title_el:
                        title = (await title_el.inner_text()).strip()
                    if not title and link_el:
                        title = (await link_el.inner_text()).strip()

                    title = title.strip()
                    if not title or len(title) > 100:
                        continue

                    heat = ''
                    if heat_el:
                        heat = (await heat_el.inner_text()).strip()

                    link = ''
                    if link_el:
                        link = (await link_el.get_attribute('href')) or ''
                        if link.startswith('/'):
                            link = f'https://www.douyin.com{link}'

                    results.append({
                        'title': title,
                        'heat': heat,
                        'url': link,
                        'label': '',
                    })
                except Exception:
                    continue

            await browser.close()

            return results if results else None

    def _search_via_playwright(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        """Playwright搜索抖音"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._async_search_playwright(keyword, top_n))

    async def _async_search_playwright(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        """Playwright异步搜索抖音"""
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled', '--disable-images'],
            )
            context = await browser.new_context(
                user_agent=_get_headers()['User-Agent'],
                locale='zh-CN',
                viewport={'width': 1920, 'height': 1080},
            )
            page = await context.new_page()

            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
            """)

            try:
                await page.goto(
                    f'https://www.douyin.com/search/{quote(keyword)}',
                    timeout=_TIMEOUT * 1000,
                    wait_until='domcontentloaded',
                )
                await page.wait_for_selector(
                    'div[class*="search-result"] div, ul li, div[id^="search"]',
                    timeout=8000,
                )
            except Exception:
                logger.debug("抖音搜索页面等待超时")

            # 多种选择器
            selectors = [
                'div[class*="search-result"] > div',
                'div[class*="video-card"]',
                'div[class*="search-common"] div',
                'ul > li',
            ]

            items = []
            for selector in selectors:
                items = await page.query_selector_all(selector)
                if items:
                    break

            results: List[Dict[str, str]] = []

            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('a, p, span, [class*="title"]')
                    link_el = await item.query_selector('a')

                    title = ''
                    if title_el:
                        title = (await title_el.inner_text()).strip()

                    title = title.strip()
                    if not title or len(title) > 100:
                        continue

                    link = ''
                    if link_el:
                        link = (await link_el.get_attribute('href')) or ''
                        if link.startswith('/'):
                            link = f'https://www.douyin.com{link}'

                    results.append({
                        'title': title,
                        'heat': '',
                        'url': link,
                        'label': '',
                    })
                except Exception:
                    continue

            await browser.close()
            return results
    
    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """爬取抖音数据
        
        Args:
            action: 操作类型 (热门/搜索)
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

        action = kwargs.get("action", "热门")
        top_n = kwargs.get("top_n", 10)
        keyword = kwargs.get("keyword", "")
        generate_report = kwargs.get("generate_report", False)
        
        try:
            if action in ["热门", "热榜", "热搜"]:
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
                "site": "抖音",
                "action": action,
                "csv_path": str(csv_path) if csv_path else None,
                "md_path": str(md_path) if md_path else None,
            }
            
            return result
        except Exception as e:
            logger.error(f"抖音爬虫执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "site": "抖音",
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
        filename = f"抖音{action}_{timestamp}.md"
        filepath = desktop / filename
        
        lines = [
            f"# 抖音{action}榜\n",
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
        filename = f"douyin_{action}_{timestamp}.csv"
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
