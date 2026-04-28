"""
B站热门爬虫

数据源:
    - 热门排行榜: https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all
    - 搜索: https://api.bilibili.com/x/web-interface/search/type?keyword=
解析方式: httpx (JSON API)，Playwright降级
"""
import asyncio
import logging
import random
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_HEADERS_POOL = [
    {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Origin': 'https://www.bilibili.com',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Referer': 'https://search.bilibili.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Origin': 'https://search.bilibili.com',
    },
]

_TIMEOUT = 10.0
_RANKING_URL = 'https://api.bilibili.com/x/web-interface/ranking/v2'
_SEARCH_URL = 'https://api.bilibili.com/x/web-interface/search/type'


def _get_headers(**extra: str) -> dict:
    """获取随机请求头"""
    headers = random.choice(_HEADERS_POOL).copy()
    headers.update(extra)
    return headers


def _format_number(num: Optional[int]) -> str:
    """格式化数字为可读字符串（如 1.2万）"""
    if num is None:
        return ''
    if num >= 100_000_000:
        return f'{num / 100_000_000:.1f}亿'
    if num >= 10_000:
        return f'{num / 10_000:.1f}万'
    return str(num)


class BilibiliScraper:
    """
    B站热门爬虫

    支持功能:
        - get_hot_list: 获取全站热门排行榜
        - search: 搜索视频内容
    """

    def get_hot_list(self, top_n: int = 10) -> List[Dict[str, str]]:
        """
        获取B站热门排行榜

        优先使用API，失败后降级到Playwright。

        Args:
            top_n: 返回条数，默认10

        Returns:
            [{"title": str, "bvid": str, "author": str, "play": str,
              "view": str, "like": str, "url": str, "label": str}, ...]
        """
        try:
            result = self._fetch_via_api(top_n)
            if result:
                return result
        except Exception as e:
            logger.warning(f"B站热门API获取失败: {e}")

        try:
            result = self._fetch_via_playwright(top_n)
            if result:
                return result
        except Exception as e:
            logger.error(f"B站热门Playwright获取也失败: {e}")

        return []

    def search(self, keyword: str, top_n: int = 10) -> List[Dict[str, str]]:
        """
        搜索B站视频

        Args:
            keyword: 搜索关键词
            top_n: 返回条数

        Returns:
            [{"title": str, "heat": str, "url": str, "label": str}, ...]
        """
        try:
            return self._search_via_api(keyword, top_n)
        except Exception as e:
            logger.error(f"B站搜索API失败: {e}")
            try:
                return self._search_via_playwright(keyword, top_n)
            except Exception as e2:
                logger.error(f"B站搜索Playwright也失败: {e2}")
                return []

    def _fetch_via_api(self, top_n: int) -> Optional[List[Dict[str, str]]]:
        """
        通过B站API获取热门排行榜

        Args:
            top_n: 返回条数

        Returns:
            解析结果列表，失败返回None
        """
        params = {'rid': 0, 'type': 'all'}
        headers = _get_headers(Referer='https://www.bilibili.com/v/popular/rank/all')

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(_RANKING_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        if data.get('code') != 0:
            logger.warning(f"B站API返回错误码: {data.get('code')}, {data.get('message')}")
            return None

        list_data = data.get('data', {}).get('list', [])
        if not list_data:
            return None

        results: List[Dict[str, str]] = []
        for item in list_data[:top_n]:
            try:
                owner = item.get('owner', {}) or {}
                stat = item.get('stat', {}) or {}

                results.append({
                    'title': item.get('title', '') or '',
                    'bvid': item.get('bvid', '') or '',
                    'author': owner.get('name', '') or '',
                    'play': _format_number(stat.get('view')),
                    'view': _format_number(stat.get('view')),
                    'like': _format_number(stat.get('like')),
                    'heat': _format_number(stat.get('view')),
                    'url': f"https://www.bilibili.com/video/{item.get('bvid', '')}",
                    'label': owner.get('name', '') or '',
                })
            except Exception as e:
                logger.debug(f"B站热门条目解析异常: {e}")
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
        """Playwright异步获取B站热门"""
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
                'https://www.bilibili.com/v/popular/rank/all',
                timeout=_TIMEOUT * 1000,
                wait_until='domcontentloaded',
            )
            await page.wait_for_selector('.rank-item', timeout=5000)

            items = await page.query_selector_all('.rank-item')
            results: List[Dict[str, str]] = []

            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('.title')
                    author_el = await item.query_selector('.up-name')
                    play_el = await item.query_selector('.detail-state .play')
                    like_el = await item.query_selector('.detail-state .like')
                    link_el = await item.query_selector('a.title')

                    title = (await title_el.inner_text()).strip() if title_el else ''
                    author = (await author_el.inner_text()).strip() if author_el else ''
                    play = (await play_el.inner_text()).strip() if play_el else ''
                    like = (await like_el.inner_text()).strip() if like_el else ''
                    link = (await link_el.get_attribute('href')) if link_el else ''

                    if title:
                        results.append({
                            'title': title,
                            'bvid': '',
                            'author': author,
                            'play': play,
                            'view': play,
                            'like': like,
                            'heat': play,
                            'url': f"https:{link}" if link.startswith('//') else link,
                            'label': author,
                        })
                except Exception:
                    continue

            await browser.close()
            return results if results else None

    def _search_via_api(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        """
        通过B站搜索API搜索视频

        Args:
            keyword: 搜索关键词
            top_n: 返回条数

        Returns:
            搜索结果列表
        """
        params = {
            'keyword': keyword,
            'search_type': 'video',
            'page': 1,
            'page_size': top_n,
        }
        headers = _get_headers(Referer=f'https://search.bilibili.com/all?keyword={quote(keyword)}')

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(_SEARCH_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        if data.get('code') != 0:
            logger.warning(f"B站搜索API返回错误: {data.get('code')}, {data.get('message')}")
            return []

        result_items = data.get('data', {}).get('result', [])
        if not result_items:
            return []

        results: List[Dict[str, str]] = []
        for item in result_items[:top_n]:
            try:
                # B站搜索返回的title含HTML标签，需清理
                title = item.get('title', '') or ''
                title = title.replace('<em class="keyword">', '').replace('</em>', '')

                author = item.get('author', '') or ''
                play = _format_number(item.get('play'))
                like = _format_number(item.get('like'))
                bvid = item.get('bvid', '') or item.get('arcurl', '')

                results.append({
                    'title': title,
                    'bvid': bvid,
                    'author': author,
                    'play': play,
                    'view': play,
                    'like': like,
                    'heat': play,
                    'url': f"https://www.bilibili.com/video/{bvid}" if bvid else item.get('arcurl', ''),
                    'label': author,
                })
            except Exception as e:
                logger.debug(f"B站搜索条目解析异常: {e}")
                continue

        return results

    def _search_via_playwright(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        """Playwright搜索降级"""
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
        """Playwright异步搜索B站"""
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(
                user_agent=_get_headers()['User-Agent'],
                locale='zh-CN',
            )
            page = await context.new_page()

            await page.goto(
                f'https://search.bilibili.com/all?keyword={quote(keyword)}',
                timeout=_TIMEOUT * 1000,
                wait_until='domcontentloaded',
            )
            await page.wait_for_selector('.video-item', timeout=5000)

            items = await page.query_selector_all('.video-item')
            results: List[Dict[str, str]] = []

            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('.title')
                    author_el = await item.query_selector('.up-name')
                    link_el = await item.query_selector('a.title')

                    title = (await title_el.inner_text()).strip() if title_el else ''
                    author = (await author_el.inner_text()).strip() if author_el else ''
                    link = (await link_el.get_attribute('href')) if link_el else ''

                    if title:
                        results.append({
                            'title': title,
                            'bvid': '',
                            'author': author,
                            'play': '',
                            'view': '',
                            'like': '',
                            'heat': '',
                            'url': link or '',
                            'label': author,
                        })
                except Exception:
                    continue

            await browser.close()
            return results
