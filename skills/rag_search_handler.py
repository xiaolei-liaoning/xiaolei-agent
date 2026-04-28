"""RAG 搜索 Skill 处理器（ToolManager 接口）

RAGSearchHandler:
- execute(query, user_id)  — 调用 RAG 搜索引擎
- 格式化回复：搜索结果摘要 + 学习知识点数量
"""
import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


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
            from core.rag_search_engine import get_rag_engine

            engine = get_rag_engine()

            # 在同步上下文中运行异步方法
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # 已有事件循环 → 用 nest_asyncio 或新建线程
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

            # 格式化回复
            reply_lines = []
            if result.get("from_cache"):
                reply_lines.append("已学过相关知识，直接返回：")
            else:
                reply_lines.append("搜索结果：")

            search_results = result.get("results", [])
            if search_results:
                for i, r in enumerate(search_results[:5], 1):
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    reply_lines.append(f"{i}. {title}")
                    if snippet:
                        reply_lines.append(f"   {snippet}")
            else:
                reply_lines.append("未找到相关结果")

            knowledge = result.get("knowledge_extracted", [])
            if knowledge:
                reply_lines.append(f"\n学习到 {len(knowledge)} 个知识点")

            return {
                "success": True,
                "data": result,
                "reply": "\n".join(reply_lines),
            }

        except Exception as e:
            logger.error("RAG 搜索失败: %s", e)
            return {"success": False, "error": str(e)}


# 模块级实例（供 ToolManager import）
rag_handler = RAGSearchHandler()
