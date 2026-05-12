#!/usr/bin/env python3
"""RAG增强模块 - 更好的知识管理"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RAGEnhancer:
    """RAG增强引擎"""

    def __init__(self):
        self.vector_store = None
        self.search_engine = None
        self._init_components()

    def _init_components(self):
        """初始化RAG组件"""
        try:
            from core.rag_search_engine import RAGSearchEngine
            self.search_engine = RAGSearchEngine()
            logger.info("RAG搜索引擎初始化成功")
        except Exception as e:
            logger.warning(f"RAG搜索引擎初始化失败: {e}")

    async def retrieve_knowledge(self, query: str, top_k: int = 5) -> List[Dict]:
        """检索相关知识"""
        if not self.search_engine:
            return []

        try:
            results = await self.search_engine.search(query, top_k=top_k)
            logger.info(f"RAG检索到 {len(results)} 条相关知识")
            return results
        except Exception as e:
            logger.error(f"RAG检索失败: {e}")
            return []

    async def augment_prompt(self, query: str, context: Dict = None) -> str:
        """增强提示词，添加相关知识"""
        knowledge = await self.retrieve_knowledge(query)
        
        if not knowledge:
            return query

        context_str = "\n".join([f"【知识{i+1}】{k.get('content', '')[:200]}..." for i, k in enumerate(knowledge)])
        
        augmented_prompt = f"""以下是相关知识，请参考回答问题：

{context_str}

问题：{query}

请结合以上知识回答问题，如果知识中有冲突以最新的为准。"""

        return augmented_prompt

    async def add_document(self, content: str, metadata: Dict = None) -> bool:
        """添加文档到知识库"""
        try:
            # 简化实现：保存到向量存储
            if hasattr(self.search_engine, 'add_document'):
                await self.search_engine.add_document(content, metadata)
                logger.info("文档添加成功")
                return True
            return False
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            return False

    async def batch_add_documents(self, documents: List[Dict]) -> int:
        """批量添加文档"""
        count = 0
        for doc in documents:
            if await self.add_document(doc.get('content', ''), doc.get('metadata')):
                count += 1
        return count


class KnowledgeManager:
    """知识管理器"""

    def __init__(self):
        self.rag_enhancer = RAGEnhancer()
        self.knowledge_base = {}

    async def query_knowledge(self, query: str) -> str:
        """查询知识库"""
        # 1. 首先尝试RAG检索
        rag_results = await self.rag_enhancer.retrieve_knowledge(query)
        
        if rag_results:
            # 2. 如果有结果，构建增强提示
            return await self.rag_enhancer.augment_prompt(query)
        
        # 3. 回退到本地知识库
        for key in self.knowledge_base:
            if key.lower() in query.lower():
                return f"参考知识：{self.knowledge_base[key]}\n\n问题：{query}"
        
        return query

    def add_knowledge(self, key: str, content: str):
        """添加知识到本地知识库"""
        self.knowledge_base[key] = content
        logger.info(f"添加知识: {key}")

    def load_knowledge_from_file(self, file_path: str):
        """从文件加载知识"""
        try:
            import json
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for key, value in data.items():
                    self.add_knowledge(key, value)
            logger.info(f"从文件加载知识: {file_path}")
        except Exception as e:
            logger.error(f"加载知识文件失败: {e}")