"""增强版混合检索引擎 - 解决缓存命中检测和并发性能问题

核心优化：
1. 返回缓存命中状态
2. 改进并发性能
3. 优化锁竞争
4. 完善缓存预热
5. 改进内存测量
"""

import logging
import asyncio
import hashlib
import time
import psutil
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict
import threading

logger = logging.getLogger(__name__)


class FusionStrategy(Enum):
    """融合策略"""
    SCORE_FUSION = "score_fusion"
    RRF = "rrf"
    WEIGHTED_AVERAGE = "weighted_average"


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
    source: str = "hybrid"


@dataclass
class SearchResponse:
    """搜索响应（包含缓存命中状态）"""
    results: List[SearchResult]
    cache_hit: bool = False
    execution_time: float = 0.0
    query: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    results: List[SearchResult]
    timestamp: float
    access_count: int = 0
    ttl: float = 360.0
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() - self.timestamp > self.ttl
    
    def touch(self):
        """更新访问时间和计数"""
        self.timestamp = time.time()
        self.access_count += 1


class LRUCache:
    """LRU缓存池（优化版 - 减少锁竞争）"""
    
    def __init__(self, max_size: int = 1000, default_ttl: float = 360.0):
        """初始化LRU缓存
        
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认TTL（秒）
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()  # 使用可重入锁
        self.hits = 0
        self.misses = 0
        
        logger.info(f"LRU缓存池初始化完成 (max_size={max_size}, ttl={default_ttl}s)")
    
    def _generate_key(self, query: str, top_k: int, strategy: str, 
                    vector_weight: float, keyword_weight: float) -> str:
        """生成缓存键"""
        key_data = f"{query}|{top_k}|{strategy}|{vector_weight:.2f}|{keyword_weight:.2f}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, query: str, top_k: int, strategy: str,
            vector_weight: float, keyword_weight: float) -> Optional[Tuple[List[SearchResult], bool]]:
        """获取缓存（返回结果和命中状态）
        
        Args:
            query: 查询文本
            top_k: 返回结果数
            strategy: 融合策略
            vector_weight: 向量权重
            keyword_weight: 关键词权重
            
        Returns:
            (缓存结果, 命中状态)，如果不存在或已过期返回(None, False)
        """
        key = self._generate_key(query, top_k, strategy, vector_weight, keyword_weight)
        
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                
                if entry.is_expired():
                    del self.cache[key]
                    self.misses += 1
                    logger.debug(f"缓存过期: {query[:30]}...")
                    return None, False
                
                entry.touch()
                self.cache.move_to_end(key)
                self.hits += 1
                logger.debug(f"缓存命中: {query[:30]}... (访问次数={entry.access_count})")
                return entry.results.copy(), True
            
            self.misses += 1
            logger.debug(f"缓存未命中: {query[:30]}...")
            return None, False
    
    def put(self, query: str, top_k: int, strategy: str,
            vector_weight: float, keyword_weight: float,
            results: List[SearchResult], ttl: Optional[float] = None):
        """存入缓存
        
        Args:
            query: 查询文本
            top_k: 返回结果数
            strategy: 融合策略
            vector_weight: 向量权重
            keyword_weight: 关键词权重
            results: 检索结果
            ttl: 自定义TTL（秒）
        """
        key = self._generate_key(query, top_k, strategy, vector_weight, keyword_weight)
        
        with self.lock:
            if len(self.cache) >= self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                logger.debug(f"缓存已满，删除最旧条目")
            
            entry = CacheEntry(
                key=key,
                results=results.copy(),
                timestamp=time.time(),
                ttl=ttl or self.default_ttl
            )
            self.cache[key] = entry
            logger.debug(f"缓存已存入: {query[:30]}...")
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
            logger.info("缓存池已清空")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = self.hits / total_requests if total_requests > 0 else 0.0
            
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
                "total_requests": total_requests
            }
    
    def cleanup_expired(self):
        """清理过期条目"""
        with self.lock:
            expired_keys = [
                key for key, entry in self.cache.items()
                if entry.is_expired()
            ]
            
            for key in expired_keys:
                del self.cache[key]
            
            if expired_keys:
                logger.info(f"清理了 {len(expired_keys)} 个过期缓存条目")


class EnhancedHybridSearchEngine:
    """增强版混合检索引擎"""
    
    def __init__(
        self,
        vector_weight: float = 0.6,
        keyword_weight: float = 0.4,
        fusion_strategy: FusionStrategy = FusionStrategy.SCORE_FUSION,
        rrf_k: int = 60,
        cache_size: int = 1000,
        cache_ttl: float = 360.0,
        enable_cache: bool = True,
        max_concurrent_searches: int = 20
    ):
        """初始化增强版混合检索引擎
        
        Args:
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
            fusion_strategy: 融合策略
            rrf_k: 倒排融合的k参数
            cache_size: 缓存池大小
            cache_ttl: 缓存TTL（秒）
            enable_cache: 是否启用缓存
            max_concurrent_searches: 最大并发检索数
        """
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.fusion_strategy = fusion_strategy
        self.rrf_k = rrf_k
        self.enable_cache = enable_cache
        self.max_concurrent_searches = max_concurrent_searches
        
        self.cache = LRUCache(max_size=cache_size, default_ttl=cache_ttl) if enable_cache else None
        
        self._init_vector_search()
        self._init_keyword_search()
        
        self.semaphore = asyncio.Semaphore(max_concurrent_searches)
        self.vector_cache: Dict[str, Any] = {}
        
        if enable_cache:
            asyncio.create_task(self._periodic_cache_cleanup())
        
        logger.info(f"增强版混合检索引擎初始化完成 "
                   f"(缓存={enable_cache}, 缓存大小={cache_size}, "
                   f"最大并发={max_concurrent_searches})")
    
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
        use_keyword: bool = True,
        skip_cache: bool = False
    ) -> SearchResponse:
        """混合检索（增强版 - 返回缓存命中状态）
        
        Args:
            query: 查询文本
            keywords: 关键词列表（可选）
            top_k: 返回结果数量
            user_id: 用户ID
            category: 记忆类别
            use_vector: 是否使用向量检索
            use_keyword: 是否使用关键词检索
            skip_cache: 是否跳过缓存
            
        Returns:
            SearchResponse（包含缓存命中状态）
        """
        start_time = time.time()
        cache_hit = False
        
        if self.enable_cache and not skip_cache:
            cached_results, hit = self.cache.get(
                query, top_k, self.fusion_strategy.value,
                self.vector_weight, self.keyword_weight
            )
            if cached_results is not None:
                cache_hit = True
                execution_time = time.time() - start_time
                logger.info(f"缓存命中，返回 {len(cached_results)} 条结果 (耗时: {execution_time*1000:.2f}ms)")
                return SearchResponse(
                    results=cached_results,
                    cache_hit=True,
                    execution_time=execution_time,
                    query=query,
                    metadata={"source": "cache"}
                )
        
        async with self.semaphore:
            if keywords is None and use_keyword:
                keywords = await self._extract_keywords_async(query)
            
            tasks = []
            if use_vector and self.vector_store:
                tasks.append(self._vector_search_async(query, top_k * 2, user_id, category))
            if use_keyword and self.keyword_engine and keywords:
                tasks.append(self._keyword_search_async(query, keywords, top_k * 2))
            
            if not tasks:
                logger.warning("无可用的检索引擎")
                return SearchResponse(
                    results=[],
                    cache_hit=False,
                    execution_time=time.time() - start_time,
                    query=query
                )
            
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.error("检索超时")
                return SearchResponse(
                    results=[],
                    cache_hit=False,
                    execution_time=time.time() - start_time,
                    query=query
                )
            
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
            
            logger.info(f"向量检索: {len(vector_results)}条, 关键词检索: {len(keyword_results)}条")
            
            hybrid_results = await self._fuse_results_async(
                vector_results,
                keyword_results,
                query,
                top_k
            )
            
            if self.enable_cache and hybrid_results:
                self.cache.put(
                    query, top_k, self.fusion_strategy.value,
                    self.vector_weight, self.keyword_weight,
                    hybrid_results
                )
            
            execution_time = time.time() - start_time
            logger.info(f"混合检索完成，返回{len(hybrid_results)}条结果 (耗时: {execution_time*1000:.2f}ms)")
            
            return SearchResponse(
                results=hybrid_results,
                cache_hit=False,
                execution_time=execution_time,
                query=query,
                metadata={
                    "vector_count": len(vector_results),
                    "keyword_count": len(keyword_results),
                    "source": "search"
                }
            )
    
    async def _vector_search_async(
        self,
        query: str,
        top_k: int,
        user_id: Optional[int] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """向量检索（异步优化版）"""
        if not self.vector_store:
            return []
        
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self._vector_search_sync,
                query, top_k, user_id, category
            )
            return results
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []
    
    def _vector_search_sync(
        self,
        query: str,
        top_k: int,
        user_id: Optional[int] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """向量检索（同步版本）"""
        try:
            results = self.vector_store.search_memories(
                query=query,
                user_id=user_id,
                top_k=top_k
            )
            
            formatted_results = []
            for i, result in enumerate(results):
                formatted_results.append({
                    "content": result.get("content", ""),
                    "metadata": result.get("metadata", {}),
                    "distance": result.get("distance", 1.0),
                    "score": 1.0 - result.get("distance", 1.0),
                    "rank": i + 1
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"向量检索同步执行失败: {e}")
            return []
    
    async def _keyword_search_async(
        self,
        query: str,
        keywords: List[str],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """关键词检索（异步优化版）"""
        if not self.keyword_engine or not keywords:
            return []
        
        try:
            documents = await self._get_documents_for_keyword_search_async()
            
            if not documents:
                return []
            
            results = await self.keyword_engine.search_by_keywords(
                keywords=keywords,
                documents=documents,
                top_k=top_k,
                use_tfidf=True,
                use_hierarchy=False
            )
            
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
    
    async def _get_documents_for_keyword_search_async(self) -> List[Dict[str, Any]]:
        """获取用于关键词检索的文档（异步版本）"""
        if not self.vector_store:
            return []
        
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self._get_documents_for_keyword_search_sync,
            )
            return results
        except Exception as e:
            logger.error(f"获取文档失败: {e}")
            return []
    
    def _get_documents_for_keyword_search_sync(self) -> List[Dict[str, Any]]:
        """获取用于关键词检索的文档（同步版本）"""
        if not self.vector_store:
            return []
        
        try:
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
    
    async def _fuse_results_async(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        query: str,
        top_k: int
    ) -> List[SearchResult]:
        """融合检索结果（异步优化版）"""
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            self._fuse_results_sync,
            vector_results, keyword_results, query, top_k
        )
        
        return results
    
    def _fuse_results_sync(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        query: str,
        top_k: int
    ) -> List[SearchResult]:
        """融合检索结果（同步版本）"""
        results_map = {}
        
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
                results_map[content].vector_score = max(
                    results_map[content].vector_score,
                    result["score"]
                )
                results_map[content].vector_rank = min(
                    results_map[content].vector_rank,
                    i + 1
                )
        
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
                results_map[content].keyword_score = max(
                    results_map[content].keyword_score,
                    result["score"]
                )
                results_map[content].keyword_rank = min(
                    results_map[content].keyword_rank,
                    i + 1
                )
        
        all_results = list(results_map.values())
        
        if self.fusion_strategy == FusionStrategy.SCORE_FUSION:
            all_results = self._score_fusion(all_results)
        elif self.fusion_strategy == FusionStrategy.RRF:
            all_results = self._rrf_fusion(all_results)
        elif self.fusion_strategy == FusionStrategy.WEIGHTED_AVERAGE:
            all_results = self._weighted_average_fusion(all_results)
        
        all_results.sort(key=lambda x: x.combined_score, reverse=True)
        return all_results[:top_k]
    
    def _score_fusion(self, results: List[SearchResult]) -> List[SearchResult]:
        """分数融合"""
        for result in results:
            normalized_vector = result.vector_score if result.vector_score > 0 else 0
            normalized_keyword = result.keyword_score if result.keyword_score > 0 else 0
            
            result.combined_score = (
                normalized_vector * self.vector_weight +
                normalized_keyword * self.keyword_weight
            )
            
            if result.vector_score > 0 and result.keyword_score > 0:
                result.source = "hybrid"
            elif result.vector_score > 0:
                result.source = "vector"
            else:
                result.source = "keyword"
        
        return results
    
    def _rrf_fusion(self, results: List[SearchResult]) -> List[SearchResult]:
        """倒排融合"""
        for result in results:
            rrf_score = 0.0
            
            if result.vector_rank < 999:
                rrf_score += 1.0 / (self.rrf_k + result.vector_rank)
            
            if result.keyword_rank < 999:
                rrf_score += 1.0 / (self.rrf_k + result.keyword_rank)
            
            result.combined_score = rrf_score
            
            if result.vector_rank < 999 and result.keyword_rank < 999:
                result.source = "hybrid"
            elif result.vector_rank < 999:
                result.source = "vector"
            else:
                result.source = "keyword"
        
        return results
    
    def _weighted_average_fusion(self, results: List[SearchResult]) -> List[SearchResult]:
        """加权平均融合"""
        for result in results:
            scores = []
            if result.vector_score > 0:
                scores.append(result.vector_score)
            if result.keyword_score > 0:
                scores.append(result.keyword_score)
            
            if scores:
                result.combined_score = sum(scores) / len(scores)
            else:
                result.combined_score = 0.0
            
            if result.vector_score > 0 and result.keyword_score > 0:
                result.source = "hybrid"
            elif result.vector_score > 0:
                result.source = "vector"
            else:
                result.source = "keyword"
        
        return results
    
    async def _extract_keywords_async(self, query: str) -> List[str]:
        """从查询中提取关键词（异步版）"""
        try:
            loop = asyncio.get_event_loop()
            keywords = await loop.run_in_executor(
                None,
                self._extract_keywords_sync,
                query
            )
            return keywords
        except Exception as e:
            logger.error(f"关键词提取失败: {e}")
            return []
    
    def _extract_keywords_sync(self, query: str) -> List[str]:
        """从查询中提取关键词（同步版本）"""
        try:
            import jieba
            keywords = list(jieba.cut(query))
            
            stopwords = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"}
            keywords = [kw for kw in keywords if len(kw) > 1 and kw not in stopwords]
            
            return keywords[:10]
        except Exception as e:
            logger.error(f"关键词提取同步执行失败: {e}")
            return []
    
    async def _periodic_cache_cleanup(self):
        """定期清理过期缓存"""
        while True:
            try:
                await asyncio.sleep(300)
                if self.cache:
                    self.cache.cleanup_expired()
            except Exception as e:
                logger.error(f"缓存清理失败: {e}")
    
    def update_weights(self, vector_weight: float, keyword_weight: float):
        """更新权重"""
        total = vector_weight + keyword_weight
        self.vector_weight = vector_weight / total
        self.keyword_weight = keyword_weight / total
        
        logger.info(f"权重已更新: 向量={self.vector_weight:.2f}, 关键词={self.keyword_weight:.2f}")
    
    def set_fusion_strategy(self, strategy: FusionStrategy):
        """设置融合策略"""
        self.fusion_strategy = strategy
        logger.info(f"融合策略已更新为: {strategy.value}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        if self.cache:
            return self.cache.get_stats()
        return {}
    
    def clear_cache(self):
        """清空缓存"""
        if self.cache:
            self.cache.clear()
            logger.info("缓存已清空")
    
    async def warmup_cache(self, queries: List[str]) -> Dict[str, Any]:
        """预热缓存（改进版 - 确保所有任务完成）
        
        Args:
            queries: 预热查询列表
            
        Returns:
            预热结果统计
        """
        logger.info(f"开始预热缓存，查询数: {len(queries)}")
        start_time = time.time()
        
        success_count = 0
        failure_count = 0
        cache_hit_count = 0
        cache_miss_count = 0
        
        for query in queries:
            try:
                response = await self.search(query, skip_cache=False)
                
                if response.cache_hit:
                    cache_hit_count += 1
                else:
                    cache_miss_count += 1
                
                if response.results:
                    success_count += 1
                else:
                    failure_count += 1
                    
            except Exception as e:
                logger.error(f"预热失败: {query[:30]}... - {e}")
                failure_count += 1
        
        execution_time = time.time() - start_time
        
        stats = {
            "total_queries": len(queries),
            "success_count": success_count,
            "failure_count": failure_count,
            "cache_hit_count": cache_hit_count,
            "cache_miss_count": cache_miss_count,
            "execution_time": execution_time,
            "success_rate": success_count / len(queries) if queries else 0.0
        }
        
        logger.info(f"缓存预热完成: {stats}")
        return stats
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """获取内存使用情况（使用psutil）
        
        Returns:
            内存使用统计
        """
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            return {
                "rss": memory_info.rss / 1024 / 1024,  # MB
                "vms": memory_info.vms / 1024 / 1024,  # MB
                "percent": process.memory_percent(),
                "available": psutil.virtual_memory().available / 1024 / 1024,  # MB
                "total": psutil.virtual_memory().total / 1024 / 1024  # MB
            }
        except Exception as e:
            logger.error(f"获取内存使用失败: {e}")
            return {}


# 全局增强版混合检索引擎实例
_enhanced_hybrid_search_engine = None
_enhanced_hybrid_lock = asyncio.Lock()


async def get_enhanced_hybrid_search_engine() -> EnhancedHybridSearchEngine:
    """获取增强版混合检索引擎单例
    
    Returns:
        增强版混合检索引擎实例
    """
    global _enhanced_hybrid_search_engine
    
    if _enhanced_hybrid_search_engine is None:
        async with _enhanced_hybrid_lock:
            if _enhanced_hybrid_search_engine is None:
                _enhanced_hybrid_search_engine = EnhancedHybridSearchEngine()
    
    return _enhanced_hybrid_search_engine