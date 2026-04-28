"""混合检索引擎 - 向量检索 + 关键词检索

核心功能：
- 混合检索策略（向量 + 关键词）
- 分数融合算法
- 倒排融合算法
- 结果去重和重排序
- 可配置权重

优势：
- 结合语义理解和精确匹配
- 提升检索精度和召回率
- 适应不同类型的查询
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FusionStrategy(Enum):
    """融合策略"""
    SCORE_FUSION = "score_fusion"  # 分数融合
    RRF = "rrf"  # 倒排融合
    WEIGHTED_AVERAGE = "weighted_average"  # 加权平均


@dataclass
class SearchResult:
    """搜索结果"""
    content: str
    metadata: Dict[str, Any]
    vector_score: float = 0.0
    keyword_score: float = 0.0
    combined_score: float = 0.0
    vector_rank: int = 999
    keyword_rank: int = 999
    source: str = "hybrid"  # vector, keyword, hybrid


class HybridSearchEngine:
    """混合检索引擎"""
    
    def __init__(
        self,
        vector_weight: float = 0.6,
        keyword_weight: float = 0.4,
        fusion_strategy: FusionStrategy = FusionStrategy.SCORE_FUSION,
        rrf_k: int = 60
    ):
        """初始化混合检索引擎
        
        Args:
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
            fusion_strategy: 融合策略
            rrf_k: 倒排融合的k参数
        """
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.fusion_strategy = fusion_strategy
        self.rrf_k = rrf_k
        
        # 初始化向量检索引擎
        self._init_vector_search()
        
        # 初始化关键词检索引擎
        self._init_keyword_search()
        
        logger.info(f"混合检索引擎初始化完成 (向量权重={vector_weight}, 关键词权重={keyword_weight}, 融合策略={fusion_strategy.value})")
    
    def _init_vector_search(self):
        """初始化向量检索"""
        try:
            from core.vector_memory import VectorMemoryStore
            self.vector_store = VectorMemoryStore()
            logger.info("向量检索引擎初始化成功")
        except Exception as e:
            logger.error(f"向量检索引擎初始化失败: {e}")
            self.vector_store = None
    
    def _init_keyword_search(self):
        """初始化关键词检索"""
        try:
            from core.search_engine import SelfSearchEngine
            self.keyword_engine = SelfSearchEngine()
            logger.info("关键词检索引擎初始化成功")
        except Exception as e:
            logger.error(f"关键词检索引擎初始化失败: {e}")
            self.keyword_engine = None
    
    async def search(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        top_k: int = 10,
        user_id: Optional[int] = None,
        category: Optional[str] = None,
        use_vector: bool = True,
        use_keyword: bool = True
    ) -> List[SearchResult]:
        """混合检索
        
        Args:
            query: 查询文本
            keywords: 关键词列表（可选，如果不提供则自动提取）
            top_k: 返回结果数量
            user_id: 用户ID（用于向量检索过滤）
            category: 记忆类别（用于向量检索过滤）
            use_vector: 是否使用向量检索
            use_keyword: 是否使用关键词检索
            
        Returns:
            混合检索结果列表
        """
        logger.info(f"开始混合检索: query='{query}', keywords={keywords}, top_k={top_k}")
        
        # 如果没有提供关键词，从查询中提取
        if keywords is None and use_keyword:
            keywords = await self._extract_keywords(query)
        
        # 并行执行向量检索和关键词检索
        tasks = []
        if use_vector and self.vector_store:
            tasks.append(self._vector_search(query, top_k * 2, user_id, category))
        if use_keyword and self.keyword_engine and keywords:
            tasks.append(self._keyword_search(query, keywords, top_k * 2))
        
        if not tasks:
            logger.warning("无可用的检索引擎")
            return []
        
        # 执行检索
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        vector_results = []
        keyword_results = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"检索失败: {result}")
                continue
            
            if use_vector and self.vector_store and i == 0:
                vector_results = result
            elif use_keyword and self.keyword_engine:
                keyword_results = result
        
        logger.info(f"向量检索结果: {len(vector_results)}条, 关键词检索结果: {len(keyword_results)}条")
        
        # 融合结果
        hybrid_results = await self._fuse_results(
            vector_results,
            keyword_results,
            query,
            top_k
        )
        
        logger.info(f"混合检索完成，返回{len(hybrid_results)}条结果")
        return hybrid_results
    
    async def _vector_search(
        self,
        query: str,
        top_k: int,
        user_id: Optional[int] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """向量检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            user_id: 用户ID
            category: 记忆类别
            
        Returns:
            向量检索结果
        """
        if not self.vector_store:
            return []
        
        try:
            results = self.vector_store.search_memories(
                query=query,
                user_id=user_id,
                top_k=top_k
            )
            
            # 转换为统一格式
            formatted_results = []
            for i, result in enumerate(results):
                formatted_results.append({
                    "content": result.get("content", ""),
                    "metadata": result.get("metadata", {}),
                    "distance": result.get("distance", 1.0),
                    "score": 1.0 - result.get("distance", 1.0),  # 转换为相似度分数
                    "rank": i + 1
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []
    
    async def _keyword_search(
        self,
        query: str,
        keywords: List[str],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """关键词检索
        
        Args:
            query: 查询文本
            keywords: 关键词列表
            top_k: 返回结果数量
            
        Returns:
            关键词检索结果
        """
        if not self.keyword_engine or not keywords:
            return []
        
        try:
            # 构造文档列表（从向量存储中获取）
            documents = await self._get_documents_for_keyword_search()
            
            if not documents:
                logger.warning("没有可用于关键词检索的文档")
                return []
            
            # 执行关键词检索
            results = await self.keyword_engine.search_by_keywords(
                keywords=keywords,
                documents=documents,
                top_k=top_k,
                use_tfidf=True,
                use_hierarchy=False
            )
            
            # 转换为统一格式
            formatted_results = []
            for i, result in enumerate(results):
                doc = result.get("document", {})
                formatted_results.append({
                    "content": doc.get("content", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": result.get("score", 0.0),
                    "rank": i + 1
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"关键词检索失败: {e}")
            return []
    
    async def _fuse_results(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        query: str,
        top_k: int
    ) -> List[SearchResult]:
        """融合检索结果
        
        Args:
            vector_results: 向量检索结果
            keyword_results: 关键词检索结果
            query: 原始查询
            top_k: 返回结果数量
            
        Returns:
            融合后的结果
        """
        # 创建结果映射（基于内容去重）
        results_map = {}
        
        # 处理向量检索结果
        for i, result in enumerate(vector_results):
            content = result["content"]
            if content not in results_map:
                results_map[content] = SearchResult(
                    content=content,
                    metadata=result["metadata"],
                    vector_score=result["score"],
                    vector_rank=i + 1
                )
            else:
                # 更新向量分数和排名
                results_map[content].vector_score = max(
                    results_map[content].vector_score,
                    result["score"]
                )
                results_map[content].vector_rank = min(
                    results_map[content].vector_rank,
                    i + 1
                )
        
        # 处理关键词检索结果
        for i, result in enumerate(keyword_results):
            content = result["content"]
            if content not in results_map:
                results_map[content] = SearchResult(
                    content=content,
                    metadata=result["metadata"],
                    keyword_score=result["score"],
                    keyword_rank=i + 1
                )
            else:
                # 更新关键词分数和排名
                results_map[content].keyword_score = max(
                    results_map[content].keyword_score,
                    result["score"]
                )
                results_map[content].keyword_rank = min(
                    results_map[content].keyword_rank,
                    i + 1
                )
        
        # 转换为列表
        all_results = list(results_map.values())
        
        # 根据融合策略计算综合分数
        if self.fusion_strategy == FusionStrategy.SCORE_FUSION:
            all_results = self._score_fusion(all_results)
        elif self.fusion_strategy == FusionStrategy.RRF:
            all_results = self._rrf_fusion(all_results)
        elif self.fusion_strategy == FusionStrategy.WEIGHTED_AVERAGE:
            all_results = self._weighted_average_fusion(all_results)
        
        # 排序并返回top_k结果
        all_results.sort(key=lambda x: x.combined_score, reverse=True)
        return all_results[:top_k]
    
    def _score_fusion(self, results: List[SearchResult]) -> List[SearchResult]:
        """分数融合
        
        Args:
            results: 搜索结果列表
            
        Returns:
            融合后的结果
        """
        for result in results:
            # 归一化分数
            normalized_vector = result.vector_score if result.vector_score > 0 else 0
            normalized_keyword = result.keyword_score if result.keyword_score > 0 else 0
            
            # 加权融合
            result.combined_score = (
                normalized_vector * self.vector_weight +
                normalized_keyword * self.keyword_weight
            )
            
            # 标记来源
            if result.vector_score > 0 and result.keyword_score > 0:
                result.source = "hybrid"
            elif result.vector_score > 0:
                result.source = "vector"
            else:
                result.source = "keyword"
        
        return results
    
    def _rrf_fusion(self, results: List[SearchResult]) -> List[SearchResult]:
        """倒排融合
        
        Args:
            results: 搜索结果列表
            
        Returns:
            融合后的结果
        """
        for result in results:
            # 计算RRF分数
            rrf_score = 0.0
            
            if result.vector_rank < 999:
                rrf_score += 1.0 / (self.rrf_k + result.vector_rank)
            
            if result.keyword_rank < 999:
                rrf_score += 1.0 / (self.rrf_k + result.keyword_rank)
            
            result.combined_score = rrf_score
            
            # 标记来源
            if result.vector_rank < 999 and result.keyword_rank < 999:
                result.source = "hybrid"
            elif result.vector_rank < 999:
                result.source = "vector"
            else:
                result.source = "keyword"
        
        return results
    
    def _weighted_average_fusion(self, results: List[SearchResult]) -> List[SearchResult]:
        """加权平均融合
        
        Args:
            results: 搜索结果列表
            
        Returns:
            融合后的结果
        """
        for result in results:
            # 计算加权平均
            scores = []
            if result.vector_score > 0:
                scores.append(result.vector_score)
            if result.keyword_score > 0:
                scores.append(result.keyword_score)
            
            if scores:
                result.combined_score = sum(scores) / len(scores)
            else:
                result.combined_score = 0.0
            
            # 标记来源
            if result.vector_score > 0 and result.keyword_score > 0:
                result.source = "hybrid"
            elif result.vector_score > 0:
                result.source = "vector"
            else:
                result.source = "keyword"
        
        return results
    
    async def _extract_keywords(self, query: str) -> List[str]:
        """从查询中提取关键词
        
        Args:
            query: 查询文本
            
        Returns:
            关键词列表
        """
        try:
            from core.search_engine import SelfSearchEngine
            engine = SelfSearchEngine()
            
            # 使用jieba分词
            import jieba
            keywords = list(jieba.cut(query))
            
            # 过滤停用词和短词
            stopwords = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"}
            keywords = [kw for kw in keywords if len(kw) > 1 and kw not in stopwords]
            
            return keywords[:10]  # 返回前10个关键词
        except Exception as e:
            logger.error(f"关键词提取失败: {e}")
            return []
    
    async def _get_documents_for_keyword_search(self) -> List[Dict[str, Any]]:
        """获取用于关键词检索的文档
        
        Returns:
            文档列表
        """
        if not self.vector_store:
            return []
        
        try:
            # 从向量存储中获取所有记忆
            results = self.vector_store._collection.get()
            
            documents = []
            for i, (content, metadata) in enumerate(zip(results.get("documents", []), results.get("metadatas", []))):
                documents.append({
                    "content": content,
                    "metadata": metadata,
                    "id": results.get("ids", [])[i] if i < len(results.get("ids", [])) else str(i)
                })
            
            return documents
        except Exception as e:
            logger.error(f"获取文档失败: {e}")
            return []
    
    def update_weights(self, vector_weight: float, keyword_weight: float):
        """更新权重
        
        Args:
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
        """
        # 归一化权重
        total = vector_weight + keyword_weight
        self.vector_weight = vector_weight / total
        self.keyword_weight = keyword_weight / total
        
        logger.info(f"权重已更新: 向量={self.vector_weight:.2f}, 关键词={self.keyword_weight:.2f}")
    
    def set_fusion_strategy(self, strategy: FusionStrategy):
        """设置融合策略
        
        Args:
            strategy: 融合策略
        """
        self.fusion_strategy = strategy
        logger.info(f"融合策略已更新为: {strategy.value}")


# 全局混合检索引擎实例
_hybrid_search_engine = None
_hybrid_lock = asyncio.Lock()


async def get_hybrid_search_engine() -> HybridSearchEngine:
    """获取混合检索引擎单例
    
    Returns:
        混合检索引擎实例
    """
    global _hybrid_search_engine
    
    if _hybrid_search_engine is None:
        async with _hybrid_lock:
            if _hybrid_search_engine is None:
                _hybrid_search_engine = HybridSearchEngine()
    
    return _hybrid_search_engine