"""微博热搜爬虫 - Playwright有头浏览器+翻页+MD报告"""

import logging
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
import platform

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


class WeiboScraper:
    """微博热搜爬虫 - 支持翻页和报告生成"""
    
    def __init__(self):
        self.base_url = "https://s.weibo.com/top/summary"
    
    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """爬取微博热搜（有头浏览器+翻页）
        
        Args:
            pages: 爬取页数
            generate_report: 是否生成MD报告
            
        Returns:
            包含热搜列表的字典
        """
        pages = int(kwargs.get("pages", 1))
        generate_report = kwargs.get("generate_report", True)
        
        try:
            from playwright.async_api import async_playwright
            
            all_items = []
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                )
                page = await context.new_page()
                
                for page_num in range(1, pages + 1):
                    url = f"{self.base_url}?page={page_num}" if page_num > 1 else self.base_url
                    
                    logger.info(f"正在爬取微博热搜第 {page_num} 页...")
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    
                    try:
                        await page.wait_for_selector(".list_a li", timeout=10000)
                    except:
                        logger.warning(f"第 {page_num} 页无数据，停止")
                        break
                    
                    # 解析当前页
                    items = await page.evaluate("""
                        () => {
                            const lis = document.querySelectorAll('.list_a li');
                            const results = [];
                            
                            lis.forEach(li => {
                                const titleEl = li.querySelector('a');
                                const heatEl = li.querySelector('.td-02 .star');
                                
                                if (!titleEl) return;
                                
                                const title = titleEl.textContent.trim();
                                const href = titleEl.getAttribute('href') || '';
                                const url = href.startsWith('http') ? href : `https://s.weibo.com${href}`;
                                const heat = heatEl ? heatEl.textContent.trim() : '';
                                
                                results.push({
                                    title,
                                    heat,
                                    url
                                });
                            });
                            
                            return results;
                        }
                    """)
                    
                    all_items.extend(items)
                    logger.info(f"第 {page_num} 页爬取完成: {len(items)} 条")
                    
                    # 检查是否有下一页
                    has_next = await page.query_selector("a.next")
                    if not has_next or page_num >= pages:
                        break
                    
                    await page.wait_for_timeout(2000)  # 防封
                
                await browser.close()
            
            # 保存CSV
            csv_path = None
            if all_items:
                csv_path = self._save_to_csv(all_items)
            
            # 生成MD报告
            md_path = None
            if generate_report and all_items:
                md_path = self._generate_md_report(all_items)
            
            result = {
                "success": True,
                "count": len(all_items),
                "data": all_items,
                "site": "微博",
                "action": "热搜",
                "csv_path": str(csv_path) if csv_path else None,
                "md_path": str(md_path) if md_path else None,
            }
            
            logger.info(f"微博热搜爬取完成: {len(all_items)} 条")
            return result
                
        except Exception as e:
            logger.error(f"微博热搜爬取失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "site": "微博",
            }
    
    def _save_to_csv(self, items: List[Dict]) -> Path:
        """保存为CSV"""
        import csv
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"weibo_hot_{timestamp}.csv"
        filepath = OUTPUT_DIR / filename
        
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["排名", "标题", "热度", "链接"])
            writer.writeheader()
            
            for idx, item in enumerate(items, 1):
                writer.writerow({
                    "排名": idx,
                    "标题": item["title"],
                    "热度": item["heat"],
                    "链接": item["url"],
                })
        
        logger.info(f"CSV已保存: {filepath}")
        return filepath
    
    def _generate_md_report(self, items: List[Dict]) -> Path:
        """生成MD报告并保存到桌面"""
        desktop = Path.home() / "Desktop"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"微博热搜_{timestamp}.md"
        filepath = desktop / filename
        
        lines = [
            f"# 微博热搜榜\n",
            f"**爬取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**总数**: {len(items)} 条\n",
        ]
        
        lines.append("\n---\n")
        
        for idx, item in enumerate(items, 1):
            lines.append(f"## {idx}. [{item['title']}]({item['url']})\n")
            if item['heat']:
                lines.append(f"- **热度**: {item['heat']}\n")
            lines.append("")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        # macOS自动打开
        if platform.system() == "Darwin":
            import subprocess
            subprocess.run(["open", str(filepath)])
        
        logger.info(f"MD报告已保存到桌面: {filepath}")
        return filepath
