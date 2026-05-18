"""
GitHub爬虫 - 支持Trending趋势和代码搜索

数据源:
    - Trending: https://github.com/trending
    - Search API: https://api.github.com/search/repositories
    - Search URL: https://github.com/search?q=
解析方式: httpx (HTML解析) + Playwright降级
"""
import asyncio
import logging
import random
from typing import Dict, List, Optional, Any
from urllib.parse import quote
from pathlib import Path
from datetime import datetime

import httpx

from core.security.error_handler import retry_on_error, handle_errors_with_default as handle_errors, ErrorHandlerUtils as ErrorHandler

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

_HEADERS_POOL = [
    {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
    },
]

_TIMEOUT = 30.0


def _get_headers(**extra: str) -> dict:
    """获取随机请求头"""
    headers = random.choice(_HEADERS_POOL).copy()
    headers.update(extra)
    return headers


def _format_stars(stars: int) -> str:
    """格式化star数量"""
    if stars >= 1_000_000:
        return f'{stars / 1_000_000:.1f}M'
    if stars >= 1_000:
        return f'{stars / 1_000:.1f}k'
    return str(stars)


class GitHubTrendingScraper:
    """
    GitHub爬虫

    支持功能:
        - get_hot_list: 获取GitHub Trending趋势
        - search: 搜索GitHub仓库/用户
    """

    def get_hot_list(self, top_n: int = 10) -> List[Dict[str, str]]:
        """
        获取GitHub Trending趋势

        Args:
            top_n: 返回条数

        Returns:
            [{"title": str, "author": str, "stars": str, "url": str, "description": str, "language": str}, ...]
        """
        try:
            return self._fetch_trending_via_httpx(top_n)
        except Exception as e:
            ErrorHandler.log_error(e, module=__name__, function="_fetch_trending_via_httpx", extra_info="httpx方式失败")
            logger.warning("GitHub Trending httpx获取失败，尝试Playwright方式...")
            try:
                return self._fetch_trending_via_playwright(top_n)
            except Exception as e2:
                ErrorHandler.log_error(e2, module=__name__, function="_fetch_trending_via_playwright", extra_info="Playwright方式也失败")
                return []

    def search(self, keyword: str, top_n: int = 10) -> List[Dict[str, str]]:
        """
        搜索GitHub仓库

        支持搜索格式:
            - 普通关键词: "python"
            - 作者+项目: "author:username project"
            - 特定语言: "python language:python"

        Args:
            keyword: 搜索关键词
            top_n: 返回条数

        Returns:
            [{"title": str, "author": str, "stars": str, "url": str, "description": str, "language": str}, ...]
        """
        try:
            return self._search_via_api(keyword, top_n)
        except Exception as e:
            ErrorHandler.log_error(e, module=__name__, function="_search_via_api", extra_info="API方式失败")
            logger.warning("GitHub搜索API失败，尝试Playwright方式...")
            try:
                return self._search_via_playwright(keyword, top_n)
            except Exception as e2:
                ErrorHandler.log_error(e2, module=__name__, function="_search_via_playwright", extra_info="Playwright方式也失败")
                return []

    def _fetch_trending_via_httpx(self, top_n: int) -> List[Dict[str, str]]:
        """通过GitHub Trending页面获取趋势（HTML解析）"""
        from bs4 import BeautifulSoup

        url = 'https://github.com/trending'
        headers = _get_headers(Referer='https://github.com/')

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, 'html.parser')
        articles = soup.find_all('article', class_='Box-row')

        results = []
        for article in articles[:top_n]:
            try:
                h2 = article.find('h2')
                if not h2:
                    continue
                a = h2.find('a')
                if not a:
                    continue

                href = a.get('href', '')
                full_name = a.get_text(strip=True)

                desc_el = article.find('p', class_=lambda x: x and 'col-9' in x)
                description = desc_el.get_text(strip=True) if desc_el else ''

                # 查找语言和stars信息
                language = ''
                stars = ''
                
                # 找到包含meta信息的div
                meta_div = article.find('div', class_=lambda x: x and 'flex-wrap' in x)
                if meta_div:
                    # 获取所有子元素的文本
                    meta_texts = []
                    for child in meta_div.children:
                        if child.name == 'span' or child.name == 'a':
                            text = child.get_text(strip=True)
                            if text:
                                meta_texts.append(text)
                    
                    # 解析语言和stars
                    for text in meta_texts:
                        # 语言通常不包含数字，stars通常包含数字或k/M后缀
                        if any(c.isdigit() for c in text) or text.endswith('k') or text.endswith('M'):
                            if not stars:
                                stars = text
                        else:
                            if not language and text.isalpha():
                                language = text

                # 如果还是没找到stars，尝试查找a标签
                if not stars:
                    for link in article.find_all('a'):
                        link_text = link.get_text(strip=True)
                        if link_text and (any(c.isdigit() for c in link_text) or link_text.endswith('k') or link_text.endswith('M')):
                            stars = link_text
                            break

                parts = href.split('/')
                author = parts[1] if len(parts) > 1 else ''
                repo = parts[2].replace('.git', '') if len(parts) > 2 else ''

                results.append({
                    'title': f'{author}/{repo}',
                    'author': author,
                    'repo': repo,
                    'stars': stars,
                    'url': f'https://github.com{href}',
                    'description': description,
                    'language': language,
                    'heat': stars,
                    'label': language,
                })
            except Exception as e:
                logger.debug(f"GitHub Trending解析异常: {e}")
                continue

        return results

    def _fetch_trending_via_playwright(self, top_n: int) -> List[Dict[str, str]]:
        """Playwright获取GitHub Trending"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._async_fetch_trending_playwright(top_n))

    async def _async_fetch_trending_playwright(self, top_n: int) -> List[Dict[str, str]]:
        """Playwright异步获取GitHub Trending"""
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
            await page.goto('https://github.com/trending', timeout=_TIMEOUT * 1000, wait_until='domcontentloaded')
            await page.wait_for_selector('.Box-row', timeout=5000)

            items = await page.query_selector_all('.Box-row')
            results = []

            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('h2 a')
                    desc_el = await item.query_selector('p.col-9')
                    
                    href = (await title_el.get_attribute('href')) if title_el else ''
                    title = (await title_el.inner_text()).strip() if title_el else ''
                    desc = (await desc_el.inner_text()).strip() if desc_el else ''

                    # 获取meta信息
                    meta_div = await item.query_selector('div.d-flex')
                    language = ''
                    stars = ''
                    
                    if meta_div:
                        # 获取所有span和a标签
                        spans = await meta_div.query_selector_all('span, a')
                        for span in spans:
                            text = (await span.inner_text()).strip()
                            if text:
                                if any(c.isdigit() for c in text) or text.endswith('k') or text.endswith('M'):
                                    if not stars:
                                        stars = text
                                else:
                                    if not language and text.isalpha():
                                        language = text

                    if title and href:
                        parts = href.split('/')
                        author = parts[1] if len(parts) > 1 else ''
                        repo = parts[2].replace('.git', '') if len(parts) > 2 else ''

                        results.append({
                            'title': f'{author}/{repo}',
                            'author': author,
                            'repo': repo,
                            'stars': stars,
                            'url': f'https://github.com{href}',
                            'description': desc,
                            'language': language,
                            'heat': stars,
                            'label': language,
                        })
                except Exception:
                    continue

            await browser.close()
            return results

    def _search_via_api(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        """通过GitHub API搜索仓库"""
        url = 'https://api.github.com/search/repositories'
        
        params = {
            'q': keyword,
            'per_page': top_n,
            'sort': 'stars',
            'order': 'desc',
        }
        headers = _get_headers(Accept='application/vnd.github.v3+json')

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            
            if resp.status_code == 403:
                logger.warning("GitHub API限流，降级到Playwright")
                raise Exception("API rate limited")
                
            resp.raise_for_status()
            data = resp.json()

        items = data.get('items', [])
        results = []

        for item in items[:top_n]:
            try:
                results.append({
                    'title': item.get('full_name', ''),
                    'author': item.get('owner', {}).get('login', ''),
                    'repo': item.get('name', ''),
                    'stars': _format_stars(item.get('stargazers_count', 0)),
                    'url': item.get('html_url', ''),
                    'description': item.get('description', '') or '',
                    'language': item.get('language', '') or '',
                    'heat': str(item.get('stargazers_count', 0)),
                    'label': item.get('language', '') or '',
                    'forks': item.get('forks_count', 0),
                    'updated_at': item.get('updated_at', ''),
                })
            except Exception as e:
                logger.debug(f"GitHub搜索条目解析异常: {e}")
                continue

        return results

    def _search_via_playwright(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        """Playwright搜索GitHub"""
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
        """Playwright异步搜索GitHub"""
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

            search_url = f'https://github.com/search?q={quote(keyword)}&type=repositories'
            await page.goto(search_url, timeout=_TIMEOUT * 1000, wait_until='domcontentloaded')
            await page.wait_for_selector('.repo-list-item', timeout=5000)

            items = await page.query_selector_all('.repo-list-item')
            results = []

            for item in items[:top_n]:
                try:
                    title_el = await item.query_selector('h3 a')
                    desc_el = await item.query_selector('p.col-9')
                    
                    href = (await title_el.get_attribute('href')) if title_el else ''
                    title = (await title_el.inner_text()).strip() if title_el else ''
                    desc = (await desc_el.inner_text()).strip() if desc_el else ''

                    # 获取meta信息
                    language = ''
                    stars = ''
                    meta_div = await item.query_selector('div.d-flex')
                    if meta_div:
                        spans = await meta_div.query_selector_all('span, a')
                        for span in spans:
                            text = (await span.inner_text()).strip()
                            if text:
                                if any(c.isdigit() for c in text) or text.endswith('k') or text.endswith('M'):
                                    if not stars:
                                        stars = text.replace('stars', '').strip()
                                else:
                                    if not language and text.isalpha():
                                        language = text

                    if title and href:
                        parts = href.split('/')
                        author = parts[1] if len(parts) > 1 else ''
                        repo = parts[2].replace('.git', '') if len(parts) > 2 else ''

                        results.append({
                            'title': f'{author}/{repo}',
                            'author': author,
                            'repo': repo,
                            'stars': stars,
                            'url': f'https://github.com{href}',
                            'description': desc,
                            'language': language,
                            'heat': stars,
                            'label': language,
                        })
                except Exception:
                    continue

            await browser.close()
            return results

    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """爬取GitHub数据"""
        action = kwargs.get("action", "trending")
        top_n = kwargs.get("top_n", 10)
        keyword = kwargs.get("keyword", "")

        try:
            if action in ["trending", "hot", "热榜", "趋势"]:
                data = self.get_hot_list(top_n=top_n)
            elif action in ["搜索", "search"]:
                data = self.search(keyword, top_n=top_n)
            else:
                data = self.get_hot_list(top_n=top_n)

            csv_path = None
            if data:
                csv_path = self._save_to_csv(data, action)

            result = {
                "success": True,
                "count": len(data),
                "data": data,
                "site": "GitHub",
                "action": action,
                "csv_path": str(csv_path) if csv_path else None,
            }

            return result
        except Exception as e:
            logger.error(f"GitHub爬虫执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "site": "GitHub",
                "count": 0
            }

    def _save_to_csv(self, data: List[Dict], action: str) -> Path:
        """保存为CSV"""
        import csv
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"github_{action}_{timestamp}.csv"
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