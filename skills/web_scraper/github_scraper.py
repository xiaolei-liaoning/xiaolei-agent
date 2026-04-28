"""GitHub Trending 爬虫 - Playwright有头浏览器"""

import logging
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


class GitHubTrendingScraper(BaseScraper):
    """GitHub Trending 爬虫 - 支持翻页"""
    
    def __init__(self):
        super().__init__("github_trending")
        self.base_url = "https://github.com/trending"
    
    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """爬取 GitHub Trending（有头浏览器+翻页）
        
        Args:
            language: 编程语言过滤
            since: 时间范围 (daily/weekly/monthly)
            pages: 爬取页数
            generate_report: 是否生成MD报告
            download_images: 是否下载图片
            download_videos: 是否下载视频
            download_audio: 是否下载音频
            extract_tables: 是否提取表格
            
        Returns:
            包含 trending 仓库列表的字典
        """
        language = kwargs.get("language", "")
        since = kwargs.get("since", "daily")
        pages = int(kwargs.get("pages", 1))
        generate_report = kwargs.get("generate_report", True)
        download_images = kwargs.get("download_images", False)
        download_videos = kwargs.get("download_videos", False)
        download_audio = kwargs.get("download_audio", False)
        extract_tables = kwargs.get("extract_tables", False)
        
        try:
            # 使用BaseScraper的浏览器池
            browser, context, page = await self.get_browser("github")
            
            url = self.base_url
            if language:
                url += f"/{language}"
            url += f"?since={since}"
            
            all_repos = []
            downloaded_images = []
            downloaded_videos = []
            downloaded_audio = []
            extracted_tables = []
            
            # 重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    for page_num in range(1, pages + 1):
                        if page_num > 1:
                            url = f"{self.base_url}/{language}?since={since}&page={page_num}" if language else f"{self.base_url}?since={since}&page={page_num}"
                        
                        logger.info(f"正在爬取 GitHub Trending 第 {page_num} 页... (尝试 {attempt+1}/{max_retries})")
                        
                        # 尝试访问页面
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        
                        # 等待页面加载
                        await page.wait_for_timeout(3000)
                        
                        # 获取页面标题用于调试
                        page_title = await page.title()
                        logger.info(f"页面标题: {page_title}")
                        
                        # 检查页面内容
                        page_content = await page.content()
                        logger.info(f"页面内容长度: {len(page_content)} 字符")
                        
                        # 滚动页面到底部，加载更多内容
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(2000)  # 等待加载
                        
                        # 检查是否有trending内容
                        has_trending = await page.query_selector('article.Box-row')
                        logger.info(f"找到Box-row元素: {has_trending is not None}")
                        
                        # 下载图片
                        if download_images:
                            save_dir = OUTPUT_DIR / f"github_images_{since}_{language}"
                            images = await self.download_images(page, 'img', str(save_dir), max_images=5)
                            downloaded_images.extend(images)
                        
                        # 下载视频
                        if download_videos:
                            save_dir = OUTPUT_DIR / f"github_videos_{since}_{language}"
                            videos = await self.download_videos(page, 'video', str(save_dir), max_videos=3)
                            downloaded_videos.extend(videos)
                        
                        # 下载音频
                        if download_audio:
                            save_dir = OUTPUT_DIR / f"github_audio_{since}_{language}"
                            audio = await self.download_audio(page, 'audio', str(save_dir), max_audio=3)
                            downloaded_audio.extend(audio)
                        
                        # 提取表格
                        if extract_tables:
                            tables = await self.extract_tables(page)
                            extracted_tables.extend(tables)
                        
                        # 解析当前页 - 使用更稳定的选择器
                        repos = await page.evaluate("""
                            () => {
                                const results = [];
                                
                                // GitHub Trending页面的主要容器
                                const articles = document.querySelectorAll('article.Box-row');
                                
                                console.log('找到文章数量:', articles.length);
                                
                                articles.forEach((article, index) => {
                                    try {
                                        // 获取仓库名称和链接
                                        let name = '';
                                        let url = '';
                                        
                                        // 方式1: h2.h3 > a (GitHub Trending标准结构)
                                        const titleLink = article.querySelector('h2.h3 a');
                                        if (titleLink) {
                                            name = titleLink.textContent.trim();
                                            url = titleLink.getAttribute('href');
                                            if (url && !url.startsWith('http')) {
                                                url = 'https://github.com' + url;
                                            }
                                        }
                                        
                                        // 如果方式1失败，尝试其他方式
                                        if (!name) {
                                            const altTitle = article.querySelector('h2 a, .repo-listing-h1 a');
                                            if (altTitle) {
                                                name = altTitle.textContent.trim();
                                                url = altTitle.getAttribute('href');
                                                if (url && !url.startsWith('http')) {
                                                    url = 'https://github.com' + url;
                                                }
                                            }
                                        }
                                        
                                        // 获取描述
                                        let description = '';
                                        const descElem = article.querySelector('p.col-9, p.text-gray');
                                        if (descElem) {
                                            description = descElem.textContent.trim();
                                        }
                                        
                                        // 获取语言
                                        let language = 'Unknown';
                                        const langElem = article.querySelector('span[itemprop="programmingLanguage"], [itemprop="programmingLanguage"]');
                                        if (langElem) {
                                            language = langElem.textContent.trim();
                                        }
                                        
                                        // 获取stars
                                        let stars = '0';
                                        const starsLink = article.querySelector('a[href*="/stargazers"]');
                                        if (starsLink) {
                                            stars = starsLink.textContent.trim().replace(/\\s+/g, ' ').trim();
                                        }
                                        
                                        // 获取forks
                                        let forks = '0';
                                        const forksLink = article.querySelector('a[href*="/forks"]');
                                        if (forksLink) {
                                            forks = forksLink.textContent.trim().replace(/\\s+/g, ' ').trim();
                                        }
                                        
                                        // 只添加有名称的仓库
                                        if (name && name.length > 0) {
                                            // 清理名称中的换行符和多余空格
                                            name = name.replace(/\\s+/g, ' ').trim();
                                            
                                            results.push({
                                                name,
                                                url,
                                                description,
                                                language,
                                                stars,
                                                forks
                                            });
                                            
                                            console.log(`仓库 ${index + 1}:`, name);
                                        }
                                    } catch (e) {
                                        console.error('解析仓库失败:', e);
                                    }
                                });
                                
                                console.log('成功解析的仓库数量:', results.length);
                                return results;
                            }
                        """)
                        
                        all_repos.extend(repos)
                        logger.info(f"第 {page_num} 页爬取完成: {len(repos)} 个仓库")
                        
                        # 检查是否有下一页
                        has_next = await page.query_selector("a.next_page")
                        if not has_next or page_num >= pages:
                            break
                        
                        await page.wait_for_timeout(3000)  # 防封
                    
                    # 成功爬取，退出重试循环
                    break
                    
                except Exception as e:
                    logger.warning(f"爬取失败（尝试 {attempt+1}/{max_retries}）: {e}")
                    if attempt < max_retries - 1:
                        # 重试前等待
                        await page.wait_for_timeout(5000)
                        # 重新创建页面
                        await page.close()
                        page = await context.new_page()
                    else:
                        # 达到最大重试次数
                        raise
            
            # 不要关闭浏览器，留给池管理
            
            # 保存CSV
            csv_path = None
            if all_repos:
                csv_path = self._save_to_csv(all_repos, since, language)
            
            # 生成MD报告
            md_path = None
            if generate_report and all_repos:
                md_path = self._generate_md_report(all_repos, since, language)
            
            result = {
                "success": True,
                "count": len(all_repos),
                "data": all_repos,
                "site": "GitHub",
                "action": f"trending_{since}",
                "csv_path": str(csv_path) if csv_path else None,
                "md_path": str(md_path) if md_path else None,
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
            
            logger.info(f"GitHub Trending 爬取完成: {len(all_repos)} 个仓库")
            return result
                
        except Exception as e:
            logger.error(f"GitHub Trending 爬取失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "site": "GitHub",
            }
    
    def _save_to_csv(self, repos: List[Dict], since: str, language: str) -> Path:
        """保存为CSV"""
        import csv
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        lang_suffix = f"_{language}" if language else ""
        filename = f"github_trending_{since}{lang_suffix}_{timestamp}.csv"
        filepath = OUTPUT_DIR / filename
        
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["排名", "仓库名", "描述", "语言", "Stars", "Forks", "链接"])
            writer.writeheader()
            
            for idx, repo in enumerate(repos, 1):
                writer.writerow({
                    "排名": idx,
                    "仓库名": repo["name"],
                    "描述": repo["description"],
                    "语言": repo["language"],
                    "Stars": repo["stars"],
                    "Forks": repo["forks"],
                    "链接": repo["url"],
                })
        
        logger.info(f"CSV已保存: {filepath}")
        return filepath
    
    def _generate_md_report(self, repos: List[Dict], since: str, language: str) -> Path:
        """生成MD报告并保存到桌面"""
        from pathlib import Path
        import platform
        
        desktop = Path.home() / "Desktop"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        lang_suffix = f"_{language}" if language else ""
        filename = f"GitHub_Trending_{since}{lang_suffix}_{timestamp}.md"
        filepath = desktop / filename
        
        lines = [
            f"# GitHub Trending - {since.title()}\n",
            f"**爬取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**语言过滤**: {language if language else '全部'}\n",
            f"**总数**: {len(repos)} 个仓库\n",
        ]
        
        lines.append("\n---\n")
        
        for idx, repo in enumerate(repos, 1):
            repo_name = repo['name'].strip().replace('\n', ' ').replace('  ', ' ')
            lines.append(f"## {idx}. [{repo_name}]({repo['url']})\n")
            lines.append(f"- **描述**: {repo['description']}\n")
            lines.append(f"- **语言**: {repo['language']}\n")
            lines.append(f"- **Stars**: {repo['stars']}\n")
            lines.append(f"- **Forks**: {repo['forks']}\n")
            lines.append("")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        # macOS自动打开
        if platform.system() == "Darwin":
            import subprocess
            subprocess.run(["open", str(filepath)])
        
        logger.info(f"MD报告已保存到桌面: {filepath}")
        return filepath
    
    def get_hot_list(self, top_n: int = 10) -> List[Dict]:
        """
        兼容旧接口：获取GitHub Trending列表
        
        Args:
            top_n: 返回条数
            
        Returns:
            [{"title": str, "heat": str, "url": str}, ...]
        """
        import asyncio
        import concurrent.futures
        
        try:
            # 检查是否已有运行的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 如果有运行的事件循环，在新线程中执行
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.scrape(language="", since="daily", pages=1, generate_report=False))
                    result = future.result(timeout=30)
            except RuntimeError:
                # 如果没有运行的事件循环，直接运行
                result = asyncio.run(self.scrape(language="", since="daily", pages=1, generate_report=False))
            
            if result.get('success'):
                data = result.get('data', [])
                # 转换为旧接口格式
                return [
                    {
                        'title': repo.get('name', 'Unknown').replace('\n', ' ').strip(),
                        'heat': f"{repo.get('stars', '0')} stars",
                        'url': repo.get('url', ''),
                    }
                    for repo in data[:top_n]
                ]
            return []
        except Exception as e:
            logger.error(f"GitHub Trending获取失败: {e}")
            return []
    
    def search(self, keyword: str, top_n: int = 10) -> List[Dict]:
        """
        兼容旧接口：搜索GitHub仓库
        
        Args:
            keyword: 搜索关键词
            top_n: 返回条数
            
        Returns:
            [{"title": str, "heat": str, "url": str}, ...]
        """
        # GitHub Trending不支持搜索，返回空列表
        logger.warning("GitHub Trending不支持搜索功能")
        return []