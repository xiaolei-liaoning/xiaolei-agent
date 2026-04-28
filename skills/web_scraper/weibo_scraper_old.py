"""
微博热搜爬虫 - 三级降级策略

方式1（首选）: API调用 https://weibo.com/ajax/side/hotSearch (httpx, 无需Playwright)
方式2（备用）: Playwright爬取 https://s.weibo.com/top/summary
方式3（最终）: RSSHub https://rsshub.app/weibo/hot
"""
import asyncio
import logging
import random
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

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
