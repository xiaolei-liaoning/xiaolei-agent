"""今日头条爬虫 - 支持热搜、新闻爬取

功能:
    - 热搜榜Top50 (优先API，降级Playwright)
    - 新闻分类
    - 新闻详情
    - CSV导出
"""

import logging
import asyncio
import json
import random
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import platform

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


class ToutiaoScraper(BaseScraper):
    """今日头条爬虫类"""

    def __init__(self):
        super().__init__("toutiao")
        self.base_url = "https://www.toutiao.com"
        self.user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ]

    async def scrape_hot_list(self, top_n: int = 10, page=None) -> List[Dict[str, Any]]:
        """爬取今日头条热搜

        Args:
            top_n: 返回数量
            page: Playwright页面对象

        Returns:
            热搜数据列表
        """
        try:
            # 首先尝试使用API（更快更可靠）
            logger.info("尝试使用头条API获取热榜...")
            api_result = await self._fetch_via_api(top_n)
            if api_result:
                logger.info(f"✅ API成功获取 {len(api_result)} 条热榜")
                return api_result
            
            # API失败，降级到Playwright
            logger.warning("API失败，降级到Playwright...")
            return await self._fetch_via_playwright(top_n, page)
            
        except Exception as e:
            logger.error(f"头条热搜爬取失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def _fetch_via_api(self, top_n: int) -> Optional[List[Dict[str, Any]]]:
        """通过API获取头条热榜"""
        import httpx
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.toutiao.com/',
        }
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    'https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc',
                    headers=headers
                )
                
                if response.status_code != 200:
                    logger.warning(f"头条API返回状态码: {response.status_code}")
                    return None
                
                data = response.json()
                items = data.get('data', [])
                
                if not items:
                    return None
                
                results = []
                for i, item in enumerate(items[:top_n]):
                    try:
                        title = item.get('Title', '未知标题')
                        cluster_id = item.get('ClusterId', '')
                        
                        # 构建链接
                        url = f"https://www.toutiao.com/trending/{cluster_id}/?category_name=topic_innerflow" if cluster_id else ""
                        
                        # 热度信息（如果有）
                        hot_value = item.get('HotValue', '') or f"第{i+1}名"
                        
                        results.append({
                            '排名': i + 1,
                            '标题': title.strip(),
                            '热度': hot_value,
                            '链接': url,
                        })
                    except Exception as e:
                        logger.warning(f"解析头条API项 {i} 失败: {e}")
                        continue
                
                return results if results else None
                
        except Exception as e:
            logger.warning(f"头条API请求失败: {e}")
            return None

    async def _fetch_via_playwright(self, top_n: int, page=None) -> List[Dict[str, Any]]:
        """通过Playwright获取头条热榜（降级方案）"""
        browser = None
        context = None
        try:
            if not page:
                browser, context, page = await self.get_browser("toutiao")
                
            # 随机User-Agent
            user_agent = random.choice(self.user_agents)
            await page.set_extra_http_headers({"User-Agent": user_agent})
            
            # 增加超时时间并添加重试
            max_retries = 3
            for retry in range(max_retries):
                try:
                    logger.info(f"尝试访问头条热搜 (第{retry+1}次)...")
                    await page.goto(f"{self.base_url}/hot/", wait_until='domcontentloaded', timeout=60000)
                    await page.wait_for_timeout(random.randint(2000, 5000))
                    logger.info("页面加载成功")
                    break
                except Exception as e:
                    logger.warning(f"第 {retry+1} 次尝试失败: {e}")
                    if retry == max_retries - 1:
                        raise
                    await page.wait_for_timeout(random.randint(3000, 6000))

            # 尝试多种选择器
            selectors = ['.hot-item', '.hot-list-item', '.trending-item', '[class*="hot"]', '[class*="Hot"]']
            found = False
            selected_selector = None
            for selector in selectors:
                try:
                    logger.info(f"尝试选择器: {selector}")
                    await page.wait_for_selector(selector, timeout=10000)
                    found = True
                    selected_selector = selector
                    logger.info(f"找到元素使用选择器: {selector}")
                    break
                except Exception as e:
                    logger.warning(f"选择器 {selector} 未找到: {e}")
                    continue

            if not found:
                logger.warning("无热搜数据，所有选择器都未找到元素")
                try:
                    await page.screenshot(path=str(OUTPUT_DIR / "toutiao_debug.png"))
                    logger.info("已保存调试截图到 toutiao_debug.png")
                except:
                    pass
                return []

            # 模拟滚动
            await page.evaluate("""
                () => {
                    window.scrollTo(0, document.body.scrollHeight * 0.5);
                }
            """)
            await page.wait_for_timeout(random.randint(1000, 3000))

            items = await page.query_selector_all(selected_selector)
            logger.info(f"找到 {len(items)} 个热搜项")

            results = []
            for i, item in enumerate(items[:top_n]):
                try:
                    title_element = await item.query_selector('.title') or await item.query_selector('.hot-title') or await item.query_selector('[class*="title"]')
                    title = await title_element.inner_text() if title_element else "未知标题"

                    hot_element = await item.query_selector('.hot-value') or await item.query_selector('.value') or await item.query_selector('[class*="hot"]')
                    hot_value = await hot_element.inner_text() if hot_element else "0 热度"

                    link_element = await item.query_selector('a')
                    link = await link_element.get_attribute('href') if link_element else ""
                    if link and not link.startswith('http'):
                        link = f"{self.base_url}{link}"

                    results.append({
                        '排名': i + 1,
                        '标题': title.strip(),
                        '热度': hot_value.strip(),
                        '链接': link,
                    })
                except Exception as e:
                    logger.warning(f"解析热搜项 {i} 失败: {e}")
                    continue

            logger.info(f"成功解析 {len(results)} 条热搜数据")
            return results

        except Exception as e:
            logger.error(f"头条Playwright爬取失败: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass

    async def scrape_news(self, category: str = 'news', limit: int = 20, page=None) -> List[Dict[str, Any]]:
        """爬取新闻列表

        Args:
            category: 新闻分类
            limit: 返回数量
            page: Playwright页面对象

        Returns:
            新闻数据列表
        """
        try:
            if not page:
                browser, context, page = await self.get_browser("toutiao")
                
            await page.goto(f"{self.base_url}/", wait_until='networkidle')

            await asyncio.sleep(2)

            articles = await page.query_selector_all('.article')

            results = []
            for i, article in enumerate(articles[:limit]):
                try:
                    title_element = await article.query_selector('.title')
                    title = await title_element.inner_text() if title_element else "未知标题"

                    summary_element = await article.query_selector('.summary')
                    summary = await summary_element.inner_text() if summary_element else ""

                    link_element = await article.query_selector('a')
                    link = await link_element.get_attribute('href') if link_element else ""

                    results.append({
                        '排名': i + 1,
                        '标题': title.strip(),
                        '摘要': summary.strip(),
                        '链接': link,
                    })
                except Exception as e:
                    logger.warning(f"解析新闻项失败: {e}")
                    continue

            return results

        except Exception as e:
            logger.error(f"今日头条新闻爬取失败: {e}")
            return []

    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """爬取今日头条数据
        
        Args:
            action: 操作类型 (热搜/新闻)
            top_n: 返回数量
            category: 新闻分类
            limit: 新闻返回数量
            generate_report: 是否生成MD报告
            download_images: 是否下载图片
            download_videos: 是否下载视频
            download_audio: 是否下载音频
            extract_tables: 是否提取表格
            
        Returns:
            爬取结果
        """
        action = kwargs.get("action", "热搜")
        generate_report = kwargs.get("generate_report", True)
        download_images = kwargs.get("download_images", False)
        download_videos = kwargs.get("download_videos", False)
        download_audio = kwargs.get("download_audio", False)
        extract_tables = kwargs.get("extract_tables", False)
        
        try:
            # 使用BaseScraper的浏览器池
            browser, context, page = await self.get_browser("toutiao")
            
            downloaded_images = []
            downloaded_videos = []
            downloaded_audio = []
            extracted_tables = []
            
            if action == '热搜' or action == '热榜':
                top_n = kwargs.get('top_n', 10)
                data = await self.scrape_hot_list(top_n=top_n, page=page)
                
                # 下载图片
                if download_images:
                    save_dir = OUTPUT_DIR / f"toutiao_images_hot"
                    images = await self.download_images(page, 'img', str(save_dir), max_images=5)
                    downloaded_images.extend(images)
                
                # 下载视频
                if download_videos:
                    save_dir = OUTPUT_DIR / f"toutiao_videos_hot"
                    videos = await self.download_videos(page, 'video', str(save_dir), max_videos=3)
                    downloaded_videos.extend(videos)
                
                # 下载音频
                if download_audio:
                    save_dir = OUTPUT_DIR / f"toutiao_audio_hot"
                    audio = await self.download_audio(page, 'audio', str(save_dir), max_audio=3)
                    downloaded_audio.extend(audio)
                
                # 提取表格
                if extract_tables:
                    tables = await self.extract_tables(page)
                    extracted_tables.extend(tables)
                
                reply = f"✅ 今日头条热搜Top{len(data)}\n\n"
                for item in data[:5]:
                    reply += f"{item['排名']}. {item['标题']}\n"
                    reply += f"   热度: {item['热度']}\n\n"
                if len(data) > 5:
                    reply += f"...还有{len(data)-5}条"

            elif action == '新闻':
                category = kwargs.get('category', 'news')
                limit = kwargs.get('limit', 20)
                data = await self.scrape_news(category=category, limit=limit, page=page)
                
                # 下载图片
                if download_images:
                    save_dir = OUTPUT_DIR / f"toutiao_images_news"
                    images = await self.download_images(page, 'img', str(save_dir), max_images=5)
                    downloaded_images.extend(images)
                
                # 下载视频
                if download_videos:
                    save_dir = OUTPUT_DIR / f"toutiao_videos_news"
                    videos = await self.download_videos(page, 'video', str(save_dir), max_videos=3)
                    downloaded_videos.extend(videos)
                
                # 下载音频
                if download_audio:
                    save_dir = OUTPUT_DIR / f"toutiao_audio_news"
                    audio = await self.download_audio(page, 'audio', str(save_dir), max_audio=3)
                    downloaded_audio.extend(audio)
                
                # 提取表格
                if extract_tables:
                    tables = await self.extract_tables(page)
                    extracted_tables.extend(tables)
                
                reply = f"✅ 今日头条新闻Top{len(data)}\n\n"
                for item in data[:5]:
                    reply += f"{item['排名']}. {item['标题']}\n"
                    reply += f"   摘要: {item['摘要'][:50]}...\n\n"
                if len(data) > 5:
                    reply += f"...还有{len(data)-5}条"

            else:
                return {
                    'success': False,
                    'error': f'不支持的操作: {action}',
                    'site': '今日头条',
                }
            
            # 保存CSV
            csv_path = None
            if data:
                csv_path = self._save_to_csv(data, action)
            
            # 生成MD报告
            md_path = None
            if generate_report and data:
                md_path = self._generate_md_report(data, action)
            
            result = {
                'success': True,
                'action': action,
                'data': data,
                'reply': reply,
                'site': '今日头条',
                'csv_path': str(csv_path) if csv_path else None,
                'md_path': str(md_path) if md_path else None,
            }
            
            # 添加下载结果
            if downloaded_images:
                result["images"] = downloaded_images
            if downloaded_videos:
                result["videos"] = downloaded_videos
            if downloaded_audio:
                result["audio"] = downloaded_audio
            if extracted_tables:
                result["tables"] = extracted_tables
            
            return result

        except Exception as e:
            logger.error(f"今日头条爬虫执行失败: {e}")
            return {
                'success': False,
                'error': f'爬取失败: {e}',
                'site': '今日头条',
                'count': 0,
            }

    def _save_to_csv(self, data: List[Dict], action: str) -> Path:
        """保存为CSV"""
        import csv
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"toutiao_{action}_{timestamp}.csv"
        filepath = OUTPUT_DIR / filename
        
        if action == '热搜' or action == '热榜':
            fieldnames = ["排名", "标题", "热度", "链接"]
        else:
            fieldnames = ["排名", "标题", "摘要", "链接"]
        
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in data:
                writer.writerow(item)
        
        logger.info(f"CSV已保存: {filepath}")
        return filepath
    
    def _generate_md_report(self, data: List[Dict], action: str) -> Path:
        """生成MD报告并保存到桌面"""
        desktop = Path.home() / "Desktop"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"今日头条{action}_{timestamp}.md"
        filepath = desktop / filename
        
        lines = [
            f"# 今日头条{action}榜\n",
            f"**爬取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**总数**: {len(data)} 条\n",
        ]
        
        lines.append("\n---\n")
        
        for item in data:
            if action == '热搜' or action == '热榜':
                title = item['标题'].strip().replace('\n', ' ').replace('  ', ' ')
                lines.append(f"## {item['排名']}. {title}\n")
                lines.append(f"- **热度**: {item['热度']}\n")
                if item['链接']:
                    lines.append(f"- **链接**: [查看详情]({item['链接']})\n")
            else:
                title = item['标题'].strip().replace('\n', ' ').replace('  ', ' ')
                lines.append(f"## {item['排名']}. {title}\n")
                if item['摘要']:
                    lines.append(f"- **摘要**: {item['摘要'][:100]}...\n")
                if item['链接']:
                    lines.append(f"- **链接**: [查看详情]({item['链接']})\n")
            lines.append("")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        if platform.system() == "Darwin":
            import subprocess
            subprocess.run(["open", str(filepath)])
        
        logger.info(f"MD报告已保存到桌面: {filepath}")
        return filepath

    async def execute(self, action: str = '热搜', **kwargs) -> Dict[str, Any]:
        """执行爬取操作

        Args:
            action: 操作类型 (热搜/新闻)
            **kwargs: 其他参数

        Returns:
            爬取结果
        """
        return await self.scrape(action=action, **kwargs)