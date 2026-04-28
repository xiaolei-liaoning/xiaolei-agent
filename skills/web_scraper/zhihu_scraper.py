"""知乎爬虫 - 支持热搜、热榜、话题爬取

功能:
    - 热搜榜Top50
    - 热门话题
    - 问题详情
    - 回答抓取
    - CSV导出
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import platform

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


class ZhihuScraper(BaseScraper):
    """知乎爬虫类"""

    def __init__(self):
        super().__init__("zhihu")
        self.base_url = "https://www.zhihu.com"
        self.user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ]

    async def scrape_hot_list(self, top_n: int = 10, page=None) -> List[Dict[str, Any]]:
        """爬取知乎热榜

        Args:
            top_n: 返回数量
            page: Playwright页面对象

        Returns:
            热榜数据列表
        """
        try:
            # 首先尝试使用API（更快更可靠）
            logger.info("尝试使用知乎API获取热榜...")
            api_result = await self._fetch_via_api(top_n)
            if api_result:
                logger.info(f"✅ API成功获取 {len(api_result)} 条热榜")
                return api_result
            
            # API失败，降级到Playwright
            logger.warning("API失败，降级到Playwright...")
            return await self._fetch_via_playwright(top_n, page)
            
        except Exception as e:
            logger.error(f"知乎热榜爬取失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def _fetch_via_api(self, top_n: int) -> Optional[List[Dict[str, Any]]]:
        """通过API获取知乎热榜"""
        import httpx
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.zhihu.com/',
        }
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    'https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total',
                    params={'limit': top_n, 'desktop': 'true'},
                    headers=headers
                )
                
                if response.status_code != 200:
                    logger.warning(f"知乎API返回状态码: {response.status_code}")
                    return None
                
                data = response.json()
                items = data.get('data', [])
                
                if not items:
                    return None
                
                results = []
                for i, item in enumerate(items[:top_n]):
                    try:
                        target = item.get('target', {})
                        title = target.get('title', '未知标题')
                        
                        # 提取热度信息
                        metrics = item.get('metrics', {})
                        heat = metrics.get('heat_text', f"{item.get('rank', i+1)}")
                        
                        # 构建链接
                        question_id = target.get('id', '')
                        url = f"https://www.zhihu.com/question/{question_id}" if question_id else ""
                        
                        results.append({
                            '排名': i + 1,
                            '标题': title.strip(),
                            '热度': heat,
                            '链接': url,
                        })
                    except Exception as e:
                        logger.warning(f"解析知乎API项 {i} 失败: {e}")
                        continue
                
                return results if results else None
                
        except Exception as e:
            logger.warning(f"知乎API请求失败: {e}")
            return None

    async def _fetch_via_playwright(self, top_n: int, page=None) -> List[Dict[str, Any]]:
        """通过Playwright获取知乎热榜（降级方案）"""
        browser = None
        context = None
        try:
            if not page:
                browser, context, page = await self.get_browser("zhihu")
                
            # 随机User-Agent
            import random
            user_agent = random.choice(self.user_agents)
            await page.set_extra_http_headers({"User-Agent": user_agent})
            
            # 增加超时时间并添加重试
            max_retries = 3
            for retry in range(max_retries):
                try:
                    logger.info(f"尝试访问知乎热榜 (第{retry+1}次)...")
                    await page.goto(f"{self.base_url}/hot", wait_until='domcontentloaded', timeout=60000)
                    await page.wait_for_timeout(random.randint(2000, 5000))
                    logger.info("页面加载成功")
                    break
                except Exception as e:
                    logger.warning(f"第 {retry+1} 次尝试失败: {e}")
                    if retry == max_retries - 1:
                        raise
                    await page.wait_for_timeout(random.randint(3000, 6000))

            # 尝试多种选择器
            selectors = ['.HotItem', '.hot-item', '.trending-item', '[class*="HotItem"]']
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
                logger.warning("无热榜数据，所有选择器都未找到元素")
                try:
                    await page.screenshot(path=str(OUTPUT_DIR / "zhihu_debug.png"))
                    logger.info("已保存调试截图到 zhihu_debug.png")
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
            logger.info(f"找到 {len(items)} 个热榜项")

            results = []
            for i, item in enumerate(items[:top_n]):
                try:
                    title_element = await item.query_selector('.HotItem-title') or await item.query_selector('.title') or await item.query_selector('[class*="title"]')
                    title = await title_element.inner_text() if title_element else "未知标题"

                    metrics_element = await item.query_selector('.HotItem-metrics') or await item.query_selector('.metrics') or await item.query_selector('[class*="metrics"]')
                    metrics = await metrics_element.inner_text() if metrics_element else "0 热度"

                    link_element = await item.query_selector('a')
                    link = await link_element.get_attribute('href') if link_element else ""
                    if link and not link.startswith('http'):
                        link = f"{self.base_url}{link}"

                    results.append({
                        '排名': i + 1,
                        '标题': title.strip(),
                        '热度': metrics.strip(),
                        '链接': link,
                    })
                except Exception as e:
                    logger.warning(f"解析热榜项 {i} 失败: {e}")
                    continue

            logger.info(f"成功解析 {len(results)} 条热榜数据")
            return results

        except Exception as e:
            logger.error(f"知乎Playwright爬取失败: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass

    async def scrape_topic(self, topic_id: str, limit: int = 20, page=None) -> List[Dict[str, Any]]:
        """爬取话题内容

        Args:
            topic_id: 话题ID
            limit: 返回数量
            page: Playwright页面对象

        Returns:
            话题内容列表
        """
        try:
            if not page:
                browser, context, page = await self.get_browser("zhihu")
                
            await page.goto(f"{self.base_url}/topic/{topic_id}", wait_until='networkidle')

            await asyncio.sleep(2)

            questions = await page.query_selector_all('.ContentItem-title')

            results = []
            for i, question in enumerate(questions[:limit]):
                try:
                    title = await question.inner_text()
                    link_element = await question.query_selector('a')
                    link = await link_element.get_attribute('href') if link_element else ""
                    if link and not link.startswith('http'):
                        link = f"{self.base_url}{link}"

                    results.append({
                        '排名': i + 1,
                        '问题': title.strip(),
                        '链接': link,
                    })
                except Exception as e:
                    logger.warning(f"解析话题项失败: {e}")
                    continue

            return results

        except Exception as e:
            logger.error(f"知乎话题爬取失败: {e}")
            return []

    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """爬取知乎数据
        
        Args:
            action: 操作类型 (热搜/话题)
            top_n: 返回数量
            topic_id: 话题ID
            limit: 话题返回数量
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
            browser, context, page = await self.get_browser("zhihu")
            
            downloaded_images = []
            downloaded_videos = []
            downloaded_audio = []
            extracted_tables = []
            
            if action == '热搜' or action == '热榜':
                top_n = kwargs.get('top_n', 10)
                data = await self.scrape_hot_list(top_n=top_n, page=page)
                
                # 下载图片
                if download_images:
                    save_dir = OUTPUT_DIR / f"zhihu_images_hot"
                    images = await self.download_images(page, 'img', str(save_dir), max_images=5)
                    downloaded_images.extend(images)
                
                # 下载视频
                if download_videos:
                    save_dir = OUTPUT_DIR / f"zhihu_videos_hot"
                    videos = await self.download_videos(page, 'video', str(save_dir), max_videos=3)
                    downloaded_videos.extend(videos)
                
                # 下载音频
                if download_audio:
                    save_dir = OUTPUT_DIR / f"zhihu_audio_hot"
                    audio = await self.download_audio(page, 'audio', str(save_dir), max_audio=3)
                    downloaded_audio.extend(audio)
                
                # 提取表格
                if extract_tables:
                    tables = await self.extract_tables(page)
                    extracted_tables.extend(tables)
                
                reply = f"✅ 知乎热榜Top{len(data)}\n\n"
                for item in data[:5]:
                    reply += f"{item['排名']}. {item['标题']}\n"
                    reply += f"   热度: {item['热度']}\n\n"
                if len(data) > 5:
                    reply += f"...还有{len(data)-5}条"

            elif action == '话题':
                topic_id = kwargs.get('topic_id', '19550629')
                limit = kwargs.get('limit', 20)
                data = await self.scrape_topic(topic_id=topic_id, limit=limit, page=page)
                
                # 下载图片
                if download_images:
                    save_dir = OUTPUT_DIR / f"zhihu_images_topic_{topic_id}"
                    images = await self.download_images(page, 'img', str(save_dir), max_images=5)
                    downloaded_images.extend(images)
                
                # 下载视频
                if download_videos:
                    save_dir = OUTPUT_DIR / f"zhihu_videos_topic_{topic_id}"
                    videos = await self.download_videos(page, 'video', str(save_dir), max_videos=3)
                    downloaded_videos.extend(videos)
                
                # 下载音频
                if download_audio:
                    save_dir = OUTPUT_DIR / f"zhihu_audio_topic_{topic_id}"
                    audio = await self.download_audio(page, 'audio', str(save_dir), max_audio=3)
                    downloaded_audio.extend(audio)
                
                # 提取表格
                if extract_tables:
                    tables = await self.extract_tables(page)
                    extracted_tables.extend(tables)
                
                reply = f"✅ 话题内容Top{len(data)}\n\n"
                for item in data[:5]:
                    reply += f"{item['排名']}. {item['问题']}\n\n"
                if len(data) > 5:
                    reply += f"...还有{len(data)-5}条"

            else:
                return {
                    'success': False,
                    'error': f'不支持的操作: {action}',
                    'site': '知乎',
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
                'site': '知乎',
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
            logger.error(f"知乎爬虫执行失败: {e}")
            return {
                'success': False,
                'error': f'爬取失败: {e}',
                'site': '知乎',
                'count': 0,
            }

    def _save_to_csv(self, data: List[Dict], action: str) -> Path:
        """保存为CSV"""
        import csv
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"zhihu_{action}_{timestamp}.csv"
        filepath = OUTPUT_DIR / filename
        
        if action == '热搜' or action == '热榜':
            fieldnames = ["排名", "标题", "热度", "链接"]
        else:
            fieldnames = ["排名", "问题", "链接"]
        
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
        filename = f"知乎{action}_{timestamp}.md"
        filepath = desktop / filename
        
        lines = [
            f"# 知乎{action}榜\n",
            f"**爬取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**总数**: {len(data)} 条\n",
        ]
        
        lines.append("\n---\n")
        
        for item in data:
            if action == '热搜' or action == '热榜':
                title = item['标题'].strip().replace('\n', ' ').replace('  ', ' ')
                lines.append(f"## {item['排名']}. [{title}]({item['链接']})\n")
                lines.append(f"- **热度**: {item['热度']}\n")
            else:
                question = item['问题'].strip().replace('\n', ' ').replace('  ', ' ')
                lines.append(f"## {item['排名']}. [{question}]({item['链接']})\n")
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
            action: 操作类型 (热搜/话题)
            **kwargs: 其他参数

        Returns:
            爬取结果
        """
        return await self.scrape(action=action, **kwargs)