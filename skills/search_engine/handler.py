"""
Search Engine Handler - 联网搜索引擎处理器

支持两种模式：
- search: RAG引擎搜索（默认）
- scrape: Playwright深度爬取
"""
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional


class SearchEngineHandler:
    """搜索引擎处理器，与爬虫隔离的智能搜索工具"""
    
    def __init__(self):
        self.rag_engine = None
        self.scraper_dispatcher = None
        self._init_engines()
    
    def _init_engines(self):
        """懒加载初始化引擎"""
        try:
            from core.rag_search_engine import RAGSearchEngine
            self.rag_engine = RAGSearchEngine()
        except Exception as e:
            print(f"[SearchEngine] RAG引擎初始化失败: {e}")
        
        try:
            from skills.web_scraper.handler import ScraperDispatcher
            self.scraper_dispatcher = ScraperDispatcher()
        except Exception as e:
            print(f"[SearchEngine] 爬虫调度器初始化失败: {e}")
    
    async def execute(self, query: str, mode: str = "search", **kwargs) -> dict:
        """
        执行搜索任务
        
        Args:
            query: 搜索关键词或URL
            mode: 工作模式 "search" 或 "scrape"
            **kwargs: 额外参数
            
        Returns:
            dict: 搜索结果和报告路径
        """
        # 自动检测模式：如果用户消息包含"爬取"等词，切换到scrape模式
        if self._should_use_scrape_mode(query, mode):
            mode = "scrape"
        
        print(f"[SearchEngine] 执行{mode}模式搜索: {query}")
        
        try:
            if mode == "scrape":
                result = await self._execute_scrape(query, **kwargs)
            else:
                result = await self._execute_search(query, **kwargs)
            
            # 生成MD报告到桌面
            report_path = self._generate_markdown_report(query, result, mode)
            result['report_path'] = str(report_path)
            
            return result
            
        except Exception as e:
            error_msg = f"搜索失败: {str(e)}"
            print(f"[SearchEngine] {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'mode': mode
            }
    
    def _should_use_scrape_mode(self, query: str, mode: str) -> bool:
        """判断是否应该使用scrape模式"""
        if mode == "scrape":
            return True
        
        # 检测爬取相关关键词
        scrape_keywords = ['爬取', '抓取', '下载页面', '获取完整内容', '深度抓取']
        for keyword in scrape_keywords:
            if keyword in query:
                print(f"[SearchEngine] 检测到关键词'{keyword}'，切换到scrape模式")
                return True
        
        return False
    
    async def _execute_search(self, query: str, **kwargs) -> dict:
        """执行RAG搜索模式"""
        if not self.rag_engine:
            raise Exception("RAG引擎未初始化")
        
        print("[SearchEngine] 调用RAG引擎搜索...")
        
        # 调用RAG搜索引擎
        results = await self.rag_engine.search_and_learn(query)
        
        return {
            'success': True,
            'mode': 'search',
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
    
    async def _execute_scrape(self, query: str, depth: int = 1, **kwargs) -> dict:
        """执行爬虫抓取模式"""
        if not self.scraper_dispatcher:
            raise Exception("爬虫调度器未初始化")
        
        print(f"[SearchEngine] 调用爬虫调度器抓取 (depth={depth})...")
        
        # 调用爬虫调度器
        result = await self.scraper_dispatcher.execute(
            site_name="搜索引擎",
            url=query if query.startswith('http') else None,
            keywords=query if not query.startswith('http') else None,
            depth=depth
        )
        
        return {
            'success': True,
            'mode': 'scrape',
            'results': result,
            'timestamp': datetime.now().isoformat()
        }
    
    def _generate_markdown_report(self, query: str, result: dict, mode: str) -> Path:
        """生成Markdown报告到桌面"""
        desktop_path = Path.home() / "Desktop"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_report_{timestamp}.md"
        report_path = desktop_path / filename
        
        # 构建报告内容
        md_content = f"""# 搜索报告: {query}

**搜索时间**: {result.get('timestamp', 'N/A')}  
**模式**: {mode}  
**状态**: {'✅ 成功' if result.get('success') else '❌ 失败'}

---

## 搜索结果

"""
        
        if mode == "search":
            md_content += self._format_search_results(result.get('results', {}))
        else:
            md_content += self._format_scrape_results(result.get('results', {}))
        
        md_content += """
---

## 关键发现

根据搜索结果，已提取核心信息并保存到向量记忆库。

---

*报告由小雷版小龙虾AI Agent自动生成*
"""
        
        # 写入文件
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        print(f"[SearchEngine] 报告已保存: {report_path}")
        
        # 自动打开报告（macOS）
        try:
            import subprocess
            subprocess.run(['open', str(report_path)], check=False)
        except Exception as e:
            print(f"[SearchEngine] 无法自动打开报告: {e}")
        
        return report_path
    
    def _format_search_results(self, results: dict) -> str:
        """格式化RAG搜索结果"""
        if not results:
            return "暂无搜索结果\n"
        
        content = ""
        
        # 处理搜索结果列表
        if isinstance(results, list):
            for i, item in enumerate(results, 1):
                if isinstance(item, dict):
                    title = item.get('title', '无标题')
                    snippet = item.get('snippet', '无摘要')
                    source = item.get('source', '未知来源')
                    content += f"### {i}. {title}\n\n"
                    content += f"**来源**: {source}\n\n"
                    content += f"{snippet}\n\n"
                    content += "---\n\n"
        elif isinstance(results, dict):
            # 处理字典格式的搜索结果
            for key, value in results.items():
                content += f"### {key}\n\n"
                content += f"{value}\n\n"
                content += "---\n\n"
        
        return content
    
    def _format_scrape_results(self, results: dict) -> str:
        """格式化爬虫抓取结果"""
        if not results:
            return "暂无抓取结果\n"
        
        content = ""
        
        if isinstance(results, dict):
            title = results.get('title', '无标题')
            url = results.get('url', 'N/A')
            extracted_text = results.get('content', results.get('text', '无内容'))
            
            content += f"**URL**: {url}\n\n"
            content += f"**标题**: {title}\n\n"
            content += "---\n\n"
            content += f"## 页面内容\n\n"
            content += f"{extracted_text[:2000]}...\n\n"  # 限制长度
        
        return content


# 导出处理器实例
handler = SearchEngineHandler()
