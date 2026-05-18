"""
微博热搜爬虫 - 三级降级策略

方式1（首选）: API调用 https://weibo.com/ajax/side/hotSearch (httpx, 无需Playwright)
方式2（备用）: Playwright爬取 https://s.weibo.com/top/summary
方式3（最终）: RSSHub https://rsshub.app/weibo/hot
"""
import asyncio
import logging
import random
from typing import Dict, List, Optional, Any
from urllib.parse import quote
from pathlib import Path
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

REPORT_DIR = OUTPUT_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# 请求头池（模拟浏览器访问）
_HEADERS_POOL = [
    {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://weibo.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'X-Requested-With': 'XMLHttpRequest',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Referer': 'https://s.weibo.com/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
    },
]

_TIMEOUT = 10.0


def _get_headers() -> dict:
    return random.choice(_HEADERS_POOL).copy()


class WeiboScraper:
    """微博热搜爬虫"""

    def get_hot_list(self, top_n: int = 10) -> List[Dict]:
        """
        获取微博热搜榜

        三级降级: API → Playwright → RSSHub

        Args:
            top_n: 返回条数

        Returns:
            [{"title": str, "heat": str, "url": str, "label": str}, ...]
        """
        # 方式1: API
        try:
            result = self._fetch_via_api(top_n)
            if result:
                return result
        except Exception as e:
            logger.warning(f"微博API获取失败: {e}")

        # 方式2: Playwright
        try:
            result = self._fetch_via_playwright(top_n)
            if result:
                return result
        except Exception as e:
            logger.warning(f"微博Playwright获取失败: {e}")

        # 方式3: RSSHub
        try:
            result = self._fetch_via_rsshub(top_n)
            if result:
                return result
        except Exception as e:
            logger.warning(f"微博RSSHub获取失败: {e}")

        logger.error("微博热搜全部获取方式均失败")
        return []

    def search(self, keyword: str, top_n: int = 10) -> List[Dict]:
        """
        搜索微博内容

        Args:
            keyword: 搜索关键词
            top_n: 返回条数

        Returns:
            [{"title": str, "heat": str, "url": str, "label": str}, ...]
        """
        try:
            return self._search_via_api(keyword, top_n)
        except Exception as e:
            logger.error(f"微博搜索失败: {e}")
            try:
                return self._search_via_playwright(keyword, top_n)
            except Exception as e2:
                logger.error(f"微博搜索Playwright也失败: {e2}")
                return []

    def _fetch_via_api(self, top_n: int) -> Optional[List[Dict]]:
        """方式1: 微博Ajax API"""
        url = 'https://weibo.com/ajax/side/hotSearch'
        headers = _get_headers()
        headers['Referer'] = 'https://weibo.com/'

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        real_time_list = data.get('data', {}).get('realtime', [])
        if not real_time_list:
            return None

        results = []
        for item in real_time_list[:top_n]:
            word = item.get('word', '') or item.get('note', '')
            label = item.get('label_name', '') or ''
            if isinstance(label, dict):
                label = label.get('text', '')
            raw_hot = item.get('num', 0) or item.get('raw_hot', 0)
            heat_str = str(raw_hot) if raw_hot else ''

            results.append({
                'title': word,
                'heat': heat_str,
                'url': f"https://s.weibo.com/weibo?q=%23{quote(word)}%23",
                'label': label,
            })

        return results

    def _fetch_via_playwright(self, top_n: int) -> Optional[List[Dict]]:
        """方式2: Playwright爬取微博热搜页面"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._async_fetch_playwright(top_n))

    async def _async_fetch_playwright(self, top_n: int) -> Optional[List[Dict]]:
        """Playwright异步爬取"""
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
            await page.set_extra_http_headers({'Referer': 'https://weibo.com/'})

            await page.goto('https://s.weibo.com/top/summary', timeout=_TIMEOUT * 1000, wait_until='domcontentloaded')
            await page.wait_for_selector('.list_a li', timeout=5000)

            items = await page.query_selector_all('.list_a li')
            results = []
            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('a')
                    heat_el = await item.query_selector('.td-02 .star')
                    title = (await title_el.inner_text()).strip() if title_el else ''
                    href = (await title_el.get_attribute('href')) if title_el else ''
                    heat = (await heat_el.inner_text()).strip() if heat_el else ''

                    if title:
                        results.append({
                            'title': title,
                            'heat': heat,
                            'url': f"https://s.weibo.com{href}" if href.startswith('/') else href,
                            'label': '',
                        })
                except Exception:
                    continue

            await browser.close()

        return results if results else None

    def _fetch_via_rsshub(self, top_n: int) -> Optional[List[Dict]]:
        """方式3: RSSHub微博热搜"""
        url = 'https://rsshub.app/weibo/hot'
        headers = _get_headers()

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()

        # RSS XML解析
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.text)
            items = root.findall('.//item')

            results = []
            for item in items[:top_n]:
                title_el = item.find('title')
                link_el = item.find('link')
                if title_el is not None:
                    title = title_el.text or ''
                    link = link_el.text if link_el is not None else ''
                    results.append({
                        'title': title,
                        'heat': '',
                        'url': link,
                        'label': '',
                    })

            return results if results else None
        except Exception as e:
            logger.error(f"RSSHub XML解析失败: {e}")
            return None

    def _search_via_api(self, keyword: str, top_n: int) -> List[Dict]:
        """API搜索微博"""
        url = 'https://m.weibo.cn/api/container/getIndex'
        params = {
            'containerid': f'100103type=1&q={quote(keyword)}',
            'page_type': 'searchall',
        }
        headers = _get_headers()
        headers['Referer'] = 'https://m.weibo.cn/'

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        cards = data.get('data', {}).get('cards', [])
        results = []
        for card in cards:
            mblog = card.get('mblog', {})
            if not mblog:
                continue
            title = mblog.get('text', '').replace('<[^>]+>', '')[:100]
            mid = mblog.get('mid', '') or mblog.get('id', '')
            results.append({
                'title': title,
                'heat': str(mblog.get('attitudes_count', 0)),
                'url': f"https://m.weibo.cn/detail/{mid}" if mid else '',
                'label': mblog.get('source', ''),
            })
            if len(results) >= top_n:
                break

        return results

    def _search_via_playwright(self, keyword: str, top_n: int) -> List[Dict]:
        """Playwright搜索微博"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._async_search_playwright(keyword, top_n))

    async def _async_search_playwright(self, keyword: str, top_n: int) -> List[Dict]:
        """Playwright异步搜索"""
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(user_agent=_get_headers()['User-Agent'])
            page = await context.new_page()

            search_url = f"https://s.weibo.com/weibo?q={quote(keyword)}"
            await page.goto(search_url, timeout=_TIMEOUT * 1000, wait_until='domcontentloaded')
            await page.wait_for_selector('.card-wrap', timeout=5000)

            items = await page.query_selector_all('.card-wrap[action-type="feed_list_item"]')
            results = []
            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('.txt')
                    title = (await title_el.inner_text()).strip()[:100] if title_el else ''
                    link_el = await item.query_selector('a[node-type="feed_list_item_date"]')
                    link = (await link_el.get_attribute('href')) if link_el else ''
                    if title:
                        results.append({
                            'title': title,
                            'heat': '',
                            'url': f"https://s.weibo.com{link}" if link.startswith('/') else link,
                            'label': '',
                        })
                except Exception:
                    continue

            await browser.close()
            return results

    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """爬取微博数据

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
            if action in ["热搜", "热榜", "热搜top10"]:
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
                "site": "微博",
                "action": action,
                "csv_path": str(csv_path) if csv_path else None,
                "md_path": str(md_path) if md_path else None,
            }

            return result
        except Exception as e:
            logger.error(f"微博爬虫执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "site": "微博",
                "count": 0
            }

    def _generate_md_report(self, data: List[Dict], action: str) -> Path:
        """生成MD报告并保存到项目目录"""
        from datetime import datetime
        from pathlib import Path
        import platform
        import subprocess

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"微博{action}_{timestamp}.md"

        # 统一保存到项目目录（macOS API进程无法写入桌面）
        filepath = REPORT_DIR / filename

        lines = [
            f"# 微博{action}榜\n",
            f"**爬取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**总数**: {len(data)} 条\n",
        ]

        lines.append("\n---\n")

        for item in data:
            title = item.get('title', '').strip().replace('\n', ' ').replace('  ', ' ')
            lines.append(f"## {item.get('排名', '')}. #{title}#\n")

            if item.get('heat'):
                lines.append(f"- **热度**: {item['heat']}\n")
            if item.get('url'):
                lines.append(f"- **链接**: [查看详情]({item['url']})\n")
            lines.append("")

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            logger.info(f"MD报告已保存: {filepath}")

            if platform.system() == "Darwin":
                subprocess.run(["open", str(filepath)], check=False)

            return filepath
        except Exception as e:
            logger.error(f"MD报告保存失败: {e}")
            return None

    def _save_to_csv(self, data: List[Dict], action: str) -> Path:
        """保存为CSV"""
        import csv

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"weibo_{action}_{timestamp}.csv"
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
