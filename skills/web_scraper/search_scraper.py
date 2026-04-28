"""通用搜索引擎爬虫 - RAG保底"""

import logging
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
import platform

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


class SearchEngineScraper:
    """搜索引擎爬虫 - 使用RAG引擎搜索"""
    
    def __init__(self):
        self.name = "搜索引擎"
    
    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """执行搜索
        
        Args:
            keyword: 搜索关键词
            generate_report: 是否生成MD报告
            
        Returns:
            包含搜索结果的字典
        """
        keyword = kwargs.get("keyword", kwargs.get("query", ""))
        generate_report = kwargs.get("generate_report", True)
        
        if not keyword:
            return {
                "success": False,
                "error": "缺少搜索关键词",
                "site": "搜索引擎",
            }
        
        try:
            from core.rag_search_engine import get_rag_engine
            
            engine = get_rag_engine()
            
            # 执行搜索
            results = await engine.search(keyword, top_k=10)
            
            all_items = []
            for item in results:
                all_items.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                })
            
            # 保存CSV
            csv_path = None
            if all_items:
                csv_path = self._save_to_csv(all_items, keyword)
            
            # 生成MD报告
            md_path = None
            if generate_report and all_items:
                md_path = self._generate_md_report(all_items, keyword)
            
            result = {
                "success": True,
                "count": len(all_items),
                "data": all_items,
                "site": "搜索引擎",
                "action": f"搜索: {keyword}",
                "csv_path": str(csv_path) if csv_path else None,
                "md_path": str(md_path) if md_path else None,
            }
            
            logger.info(f"搜索完成 [{keyword}]: {len(all_items)} 条")
            return result
                
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "site": "搜索引擎",
            }
    
    def _save_to_csv(self, items: List[Dict], keyword: str) -> Path:
        """保存为CSV"""
        import csv
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_{keyword[:20]}_{timestamp}.csv"
        filepath = OUTPUT_DIR / filename
        
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["排名", "标题", "摘要", "来源", "链接"])
            writer.writeheader()
            
            for idx, item in enumerate(items, 1):
                writer.writerow({
                    "排名": idx,
                    "标题": item["title"],
                    "摘要": item["snippet"][:200] if item["snippet"] else "",
                    "来源": item["source"],
                    "链接": item["url"],
                })
        
        logger.info(f"CSV已保存: {filepath}")
        return filepath
    
    def _generate_md_report(self, items: List[Dict], keyword: str) -> Path:
        """生成MD报告并保存到桌面"""
        desktop = Path.home() / "Desktop"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"搜索结果_{keyword[:20]}_{timestamp}.md"
        filepath = desktop / filename
        
        lines = [
            f"# 搜索结果: {keyword}\n",
            f"**搜索时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**总数**: {len(items)} 条\n",
        ]
        
        lines.append("\n---\n")
        
        for idx, item in enumerate(items, 1):
            lines.append(f"## {idx}. [{item['title']}]({item['url']})\n")
            if item['snippet']:
                lines.append(f"{item['snippet']}\n")
            if item['source']:
                lines.append(f"- **来源**: {item['source']}\n")
            lines.append("")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        if platform.system() == "Darwin":
            import subprocess
            subprocess.run(["open", str(filepath)])
        
        logger.info(f"MD报告已保存到桌面: {filepath}")
        return filepath
