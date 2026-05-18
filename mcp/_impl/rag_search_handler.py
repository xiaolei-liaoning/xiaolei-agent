"""RAG 搜索 Skill 处理器（ToolManager 接口）

RAGSearchHandler:
- execute(query, user_id)  — 调用 RAG 搜索引擎
- 格式化回复：搜索结果摘要 + 学习知识点数量
- 生成MD报告到桌面
"""
import asyncio
import logging
from typing import Dict, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

REPORT_DIR = OUTPUT_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


class RAGSearchHandler:
    """RAG 搜索处理器（适配 ToolManager 接口）"""

    def execute(self, query: str = "", user_id: int = 1, **kwargs) -> Dict[str, Any]:
        """执行 RAG 搜索

        Args:
            query:   搜索查询
            user_id: 用户ID

        Returns:
            {"success": True, "data": ..., "reply": "..."}
        """
        if not query:
            return {"success": False, "error": "未指定搜索内容"}

        try:
            from core.search.rag_search_engine import RAGSearchEngine

            engine = RAGSearchEngine()

            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(
                            asyncio.run,
                            engine.search_and_learn(query, user_id=user_id, learn=True)
                        )
                        result = future.result(timeout=30)
                else:
                    result = asyncio.run(
                        engine.search_and_learn(query, user_id=user_id, learn=True)
                    )
            except RuntimeError:
                result = asyncio.run(
                    engine.search_and_learn(query, user_id=user_id, learn=True)
                )

            search_results = result.get("results", [])
            knowledge = result.get("knowledge_extracted", [])

            reply_lines = []
            if result.get("from_cache"):
                reply_lines.append("已学过相关知识，直接返回：")
            else:
                reply_lines.append("搜索结果：")

            if search_results:
                for i, r in enumerate(search_results[:5], 1):
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    reply_lines.append(f"{i}. {title}")
                    if snippet:
                        reply_lines.append(f"   {snippet}")
            else:
                reply_lines.append("未找到相关结果")

            if knowledge:
                reply_lines.append(f"\n学习到 {len(knowledge)} 个知识点")

            md_path = self._generate_md_report(query, search_results, knowledge)

            return {
                "success": True,
                "data": result,
                "reply": "\n".join(reply_lines) + f"\n\n📄 报告已保存: output/reports/{Path(md_path).name}" if md_path else "\n".join(reply_lines),
                "md_path": str(md_path) if md_path else None,
            }

        except Exception as e:
            logger.error("RAG 搜索失败: %s", e)
            return {"success": False, "error": str(e)}

    def _generate_md_report(self, query: str, search_results: list, knowledge: list) -> Path:
        """生成MD报告并保存到项目目录"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"搜索结果_{query[:20]}_{timestamp}.md"

            # 统一保存到项目目录（macOS API进程无法写入桌面）
            filepath = REPORT_DIR / filename

            lines = [
                f"# 搜索结果: {query}\n",
                f"**搜索时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
                f"**搜索结果数**: {len(search_results)} 条\n",
                f"**学习到知识点**: {len(knowledge)} 个\n",
            ]

            lines.append("\n---\n")

            lines.append("## 搜索结果\n")
            for idx, item in enumerate(search_results[:10], 1):
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                url = item.get("url", "")
                lines.append(f"### {idx}. [{title}]({url})\n")
                if snippet:
                    lines.append(f"{snippet}\n")
                lines.append("")

            if knowledge:
                lines.append("\n---\n")
                lines.append("## 学习到的知识点\n")
                for idx, kp in enumerate(knowledge[:10], 1):
                    lines.append(f"{idx}. {kp}\n")

            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            logger.info(f"RAG搜索MD报告已保存: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"生成MD报告失败: {e}")
            return None


rag_handler = RAGSearchHandler()
