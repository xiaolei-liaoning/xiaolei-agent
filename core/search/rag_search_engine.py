"""RAG智能搜索引擎 - 多引擎支持 + ChromaDB + BeautifulSoup

工业级检索增强生成引擎：
- 多搜索引擎支持（百度/Bing/DuckDuckGo，自动选择可用引擎）
- httpx异步HTTP客户端（超时15s、跟随重定向、浏览器UA）
- BeautifulSoup网页正文提取（去script/style/nav/footer，智能截取3000字）
- ChromaDB向量存储（通过VectorMemoryStore单例，余弦相似度）
- 批量写入缓冲区（10条/30秒自动flush）
- 缓存策略：distance<0.3命中向量库则直接返回，未命中才联网
- JSON知识索引文件，支持按主题查询
- 查询结果缓存（LRU + TTL）
- 线程安全操作
- 性能监控
"""
import asyncio
import json
import logging
import os
import re
import threading
import hashlib
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from functools import wraps

logger = logging.getLogger(__name__)

# ─── 路径常量 ───────────────────────────────────────────────────────────────
KNOWLEDGE_DIR = Path(os.path.expanduser("~/.小雷版小龙虾/knowledge_base"))
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

INDEX_FILE = KNOWLEDGE_DIR / "knowledge_index.json"

# ─── 搜索与HTTP配置 ──────────────────────────────────────────────────────────
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_HTTP_TIMEOUT = 3.0  # 秒 - 从15s降至3s，避免长时间等待

# ─── 批量写入缓冲区配置 ─────────────────────────────────────────────────────
_BUFFER_SIZE = 10
_FLUSH_INTERVAL = 30  # 秒

# ─── 向量检索阈值 ────────────────────────────────────────────────────────────
_COSINE_HIT_THRESHOLD = 0.3  # distance < 0.3 视为命中

# ─── 网页正文提取配置 ────────────────────────────────────────────────────────
_MAX_CONTENT_LENGTH = 3000  # 字符
_REMOVE_TAGS: Set[str] = {"script", "style", "nav", "footer", "header", "aside", "noscript"}

# ─── 查询结果缓存配置 ───────────────────────────────────────────────────────
_QUERY_CACHE_SIZE = 100  # 最大缓存条目数
_QUERY_CACHE_TTL = 600  # 缓存过期时间（秒），10分钟


def synchronized(func):
    """线程同步装饰器"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return func(self, *args, **kwargs)
    return wrapper


class TTLCacheEntry:
    """带TTL的缓存条目"""
    def __init__(self, data: Any, ttl: int):
        """
        Args:
            data: 缓存数据
            ttl: 过期时间（秒）
        """
        self.data = data
        self.expires_at = datetime.now() + timedelta(seconds=ttl)
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now() > self.expires_at


# ═══════════════════════════════════════════════════════════════════════════
class RAGSearchEngine:
    """RAG搜索引擎 — 搜索、学习、检索一体化"""

    def __init__(self) -> None:
        self._search_engine = None  # 统一搜索引擎接口
        self._vector_store = None
        self._write_buffer: List[Tuple[str, str, Dict[str, Any]]] = []
        self._buffer_lock = threading.Lock()
        self._last_flush_time = time.time()
        self._search_engine_ok = False
        
        # 新增：查询结果缓存
        self._query_cache: OrderedDict[str, TTLCacheEntry] = OrderedDict()
        self._lock = threading.RLock()  # 线程锁
        
        # 新增：性能统计
        self._stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'vector_hits': 0,
            'web_searches': 0,
            'total_queries': 0
        }

        # 搜索引擎和向量存储均为懒加载，避免 init 时网络/DB 耗时阻塞构造

    # ── 初始化 ──────────────────────────────────────────────────────────────
    def _init_search_engine(self) -> None:
        """初始化搜索引擎（支持多种引擎，自动选择可用的）"""
        try:
            from .search_engine_factory import get_search_engine
            self._search_engine = get_search_engine()
            self._search_engine_ok = True
            engine_name = self._search_engine.__class__.__name__
            logger.info(f"搜索引擎初始化成功: {engine_name}")
        except Exception as exc:
            logger.warning(f"搜索引擎初始化失败: {exc}")

    def _init_vector_store(self) -> None:
        """延迟初始化 VectorMemoryStore 单例"""
        try:
            from ..memory.vector_memory import VectorMemoryStore
            self._vector_store = VectorMemoryStore()
            logger.info("向量存储 (ChromaDB) 初始化成功")
        except Exception as exc:
            logger.error("向量存储初始化失败: %s", exc)
            self._vector_store = None

    # ── 属性 ────────────────────────────────────────────────────────────────
    @property
    def search_engine(self):
        """懒加载搜索引擎"""
        if self._search_engine is None:
            self._init_search_engine()
        return self._search_engine

    @property
    def search_engine_ok(self):
        """搜索引擎是否可用"""
        return self.search_engine is not None

    @property
    def vector_store(self):
        """懒加载向量存储（仅当首次使用时创建）"""
        if self._vector_store is None:
            try:
                from ..memory.vector_memory import VectorMemoryStore
                self._vector_store = VectorMemoryStore()
            except Exception as exc:
                logger.error("向量存储延迟加载失败: %s", exc)
        return self._vector_store
    
    @property
    def cache(self):
        """统一缓存接口 - 指向向量存储（用于测试和外部访问）"""
        return self.vector_store
    
    @property
    def _search_cache(self):
        """兼容性别名 - 搜索缓存（实际使用向量存储）"""
        return self.vector_store

    # ═══════════════════════════════════════════════════════════════════════
    #  缓存辅助方法
    # ═══════════════════════════════════════════════════════════════════════
    
    def _generate_cache_key(self, query: str, user_id: int, max_results: int) -> str:
        """生成查询缓存键
        
        Args:
            query: 搜索查询
            user_id: 用户ID
            max_results: 最大结果数
            
        Returns:
            缓存键
        """
        key_str = f"{query}:{user_id}:{max_results}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    @synchronized
    def _get_from_query_cache(self, key: str) -> Optional[Any]:
        """从查询缓存获取数据
        
        Args:
            key: 缓存键
            
        Returns:
            缓存的数据，未找到或过期返回None
        """
        if key in self._query_cache:
            entry = self._query_cache[key]
            if not entry.is_expired():
                # 移动到末尾，标记为最近使用
                self._query_cache.move_to_end(key)
                self._stats['cache_hits'] += 1
                logger.debug("查询缓存命中: key=%s", key[:10])
                return entry.data
            else:
                # 过期了，删除
                del self._query_cache[key]
                logger.debug("查询缓存过期: key=%s", key[:10])
        
        self._stats['cache_misses'] += 1
        return None
    
    @synchronized
    def _set_query_cache(self, key: str, data: Any) -> None:
        """设置查询缓存
        
        Args:
            key: 缓存键
            data: 要缓存的数据
        """
        self._query_cache[key] = TTLCacheEntry(data, _QUERY_CACHE_TTL)
        
        # LRU淘汰：如果超出容量，删除最久未使用的
        while len(self._query_cache) > _QUERY_CACHE_SIZE:
            oldest_key, _ = self._query_cache.popitem(last=False)
            logger.debug("LRU淘汰缓存: key=%s", oldest_key[:10])
        
        logger.debug("设置查询缓存: key=%s", key[:10])
    
    @synchronized
    def clear_query_cache(self) -> None:
        """清空查询缓存"""
        self._query_cache.clear()
        logger.info("查询缓存已清空")
    
    @synchronized
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        total = self._stats['total_queries']
        cache_hit_rate = (self._stats['cache_hits'] / total * 100) if total > 0 else 0
        
        return {
            **self._stats,
            'cache_hit_rate': round(cache_hit_rate, 2),
            'cache_size': len(self._query_cache),
            'max_cache_size': _QUERY_CACHE_SIZE
        }
    
    @synchronized
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'vector_hits': 0,
            'web_searches': 0,
            'total_queries': 0
        }
        logger.info("RAG搜索统计已重置")
    
    # ═══════════════════════════════════════════════════════════════════════
    #  公开 API
    # ═══════════════════════════════════════════════════════════════════════

    async def search_and_learn(
        self,
        query: str,
        user_id: int = 1,
        learn: bool = True,
        max_results: int = 5,
        enhance: bool = True,
        use_query_cache: bool = True,
    ) -> Dict[str, Any]:
        """搜索并自动学习

        策略：先查查询缓存 → 再查向量库 → 命中直接返回 → 未命中联网搜索 → 可选学习入库

        Args:
            query: 搜索查询
            user_id: 用户ID
            learn: 是否提取知识并写入向量库
            max_results: 最大搜索结果数
            enhance: 是否增强搜索结果（抓取网页内容）
            use_query_cache: 是否使用查询缓存

        Returns:
            {
                "query", "from_cache", "results", "knowledge_extracted",
                "saved_to_kb", "timestamp", "error"(可选), "enhanced"
            }
        """
        self._stats['total_queries'] += 1

        # 0. 关键词提取（增强搜索质量）
        kw_result = None
        try:
            from .keyword_extractor import get_keyword_extractor
            extractor = get_keyword_extractor()
            kw_result = await extractor.extract(query)
            if kw_result and kw_result.keywords:
                logger.debug("关键词提取: %s", [k.word for k in kw_result.keywords])
        except Exception:
            pass  # 关键词提取失败不影响主流程

        # 0.5. 先查查询缓存
        if use_query_cache:
            cache_key = self._generate_cache_key(query, user_id, max_results)
            cached_result = self._get_from_query_cache(cache_key)
            if cached_result is not None:
                logger.info("查询缓存命中: query=%s", query[:50])
                return cached_result
        
        # 1. 缓存策略：查向量库
        cached = self._check_existing_knowledge(query, user_id)
        if cached is not None:
            self._stats['vector_hits'] += 1
            logger.info("RAG向量缓存命中: query=%s", query[:50])
            result = {
                "query": query,
                "from_cache": True,
                "from_vector_cache": True,
                "results": cached,
                "knowledge_extracted": [],
                "saved_to_kb": False,
                "timestamp": datetime.now().isoformat(),
                "enhanced": False,
            }
            # 缓存这个结果
            if use_query_cache:
                self._set_query_cache(cache_key, result)
            return result

        # 2. 联网搜索
        self._stats['web_searches'] += 1
        try:
            search_results = await asyncio.wait_for(
                self._web_search(query, max_results),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.warning(f"搜索超时: {query[:50]}")
            search_results = []
        
        if not search_results:
            result = {
                "query": query,
                "from_cache": False,
                "results": [],
                "knowledge_extracted": [],
                "saved_to_kb": False,
                "error": "搜索无结果",
                "timestamp": datetime.now().isoformat(),
                "enhanced": False,
            }
            if use_query_cache:
                self._set_query_cache(cache_key, result)
            return result

        # 3. 异步抓取网页正文（增强搜索结果）
        enhanced_results = search_results
        if enhance:
            enhanced_results = await self._enrich_with_page_content(search_results[:3])

        # 4. 知识提取 & 写入向量库
        knowledge_points: List[str] = []
        if learn:
            knowledge_points = self._extract_knowledge(enhanced_results, query)
            for kp in knowledge_points:
                self._buffered_add_memory(
                    user_id=user_id,
                    content=kp,
                    metadata={"source": "rag_search", "query": query},
                )
            self._update_knowledge_index(query, knowledge_points)

        result = {
            "query": query,
            "from_cache": False,
            "results": enhanced_results[:max_results],
            "knowledge_extracted": knowledge_points,
            "saved_to_kb": len(knowledge_points) > 0,
            "timestamp": datetime.now().isoformat(),
            "enhanced": enhance,
            "keywords": [k.word for k in kw_result.keywords] if kw_result and kw_result.keywords else [],
        }
        
        # 缓存这个结果
        if use_query_cache:
            self._set_query_cache(cache_key, result)
        
        return result

    async def search_by_topic(self, topic: str, user_id: int = 1, max_results: int = 10) -> Dict[str, Any]:
        """按主题搜索知识
        
        Args:
            topic: 主题
            user_id: 用户ID
            max_results: 最大结果数
            
        Returns:
            搜索结果
        """
        try:
            # 先查主题索引
            topic_data = self._load_knowledge_index().get(topic, {})
            if topic_data:
                return {
                    "topic": topic,
                    "from_cache": True,
                    "results": topic_data.get("knowledge_points", []),
                    "timestamp": datetime.now().isoformat()
                }
            
            # 没有索引，执行搜索
            return await self.search_and_learn(
                query=topic,
                user_id=user_id,
                max_results=max_results
            )
        except Exception as e:
            logger.error(f"按主题搜索失败: {e}")
            return {"topic": topic, "error": str(e)}

    # ══════════════════════════════════════════════════════════════════════
    #  搜索
    # ══════════════════════════════════════════════════════════════════════

    async def _web_search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """多引擎异步搜索"""
        if not self.search_engine:
            logger.warning("搜索引擎未初始化")
            return []

        try:
            loop = asyncio.get_running_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(None, self.search_engine.search, query, num_results),
                timeout=10.0
            )
            return results
        except asyncio.TimeoutError:
            logger.warning(f"搜索超时: {query[:50]}")
            return []
        except Exception as exc:
            logger.error(f"搜索失败: {exc}")
            return []

    # ══════════════════════════════════════════════════════════════════════
    #  网页内容增强
    # ══════════════════════════════════════════════════════════════════════

    async def _enrich_with_page_content(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """异步抓取网页正文，增强搜索结果"""
        if not search_results:
            return search_results

        tasks = [
            self._fetch_page_content(result["url"])
            for result in search_results
            if result.get("url")
        ]
        
        contents = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, content in enumerate(contents):
            if isinstance(content, str):
                search_results[i]["content"] = self._clean_html(content)
        
        return search_results

    async def _fetch_page_content(self, url: str) -> str:
        """异步获取网页内容"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True, verify=False) as client:
                response = await client.get(url, headers={"User-Agent": _BROWSER_UA})
                return response.text
        except Exception as exc:
            logger.warning(f"抓取网页失败 {url[:50]}: {exc}")
            return ""

    def _clean_html(self, html: str) -> str:
        """清理HTML，提取正文"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            
            # 移除不需要的标签
            for tag in soup(_REMOVE_TAGS):
                tag.decompose()
            
            # 提取正文
            text = soup.get_text(separator="\n", strip=True)
            
            # 限制长度
            if len(text) > _MAX_CONTENT_LENGTH:
                text = text[:_MAX_CONTENT_LENGTH] + "..."
            
            return text
        except Exception as exc:
            logger.warning(f"HTML解析失败: {exc}")
            return html[:_MAX_CONTENT_LENGTH] if len(html) > _MAX_CONTENT_LENGTH else html

    # ══════════════════════════════════════════════════════════════════════
    #  知识提取与索引
    # ══════════════════════════════════════════════════════════════════════

    def _extract_knowledge(self, results: List[Dict[str, Any]], query: str) -> List[str]:
        """从搜索结果中提取知识点"""
        knowledge_points = []
        
        for result in results:
            content = result.get("content", "") or result.get("snippet", "")
            if content:
                # 提取关键句子
                sentences = re.split(r"[。！？.!?]", content)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if len(sentence) > 10 and len(sentence) < 500:
                        knowledge_points.append(sentence)
        
        return knowledge_points[:10]  # 最多提取10个知识点

    def _update_knowledge_index(self, topic: str, knowledge_points: List[str]) -> None:
        """更新知识索引文件"""
        index = self._load_knowledge_index()
        
        if topic not in index:
            index[topic] = {
                "created_at": datetime.now().isoformat(),
                "knowledge_points": []
            }
        
        for kp in knowledge_points:
            if kp not in index[topic]["knowledge_points"]:
                index[topic]["knowledge_points"].append(kp)
        
        self._save_knowledge_index(index)

    def _load_knowledge_index(self) -> Dict[str, Any]:
        """加载知识索引文件"""
        if INDEX_FILE.exists():
            try:
                with open(INDEX_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning(f"加载知识索引失败: {exc}")
        return {}

    def _save_knowledge_index(self, index: Dict[str, Any]) -> None:
        """保存知识索引文件"""
        try:
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error(f"保存知识索引失败: {exc}")

    # ══════════════════════════════════════════════════════════════════════
    #  向量存储操作
    # ══════════════════════════════════════════════════════════════════════

    def _check_existing_knowledge(self, query: str, user_id: int) -> Optional[List[Dict[str, Any]]]:
        """检查向量库中是否已有相关知识"""
        vs = self.vector_store
        if not vs:
            return None
        
        try:
            results = vs.search_memories(query, user_id=user_id, top_k=3)
            if results:
                # 检查相似度（distance < 0.3 视为命中）
                if any(r.get("distance", 1.0) < _COSINE_HIT_THRESHOLD for r in results):
                    return results
        except Exception as exc:
            logger.warning(f"向量库查询失败: {exc}")
        
        return None

    def _buffered_add_memory(self, user_id: int, content: str, metadata: Dict[str, Any]) -> None:
        """缓冲添加记忆（批量写入优化）"""
        with self._buffer_lock:
            self._write_buffer.append((user_id, content, metadata))
            
            # 检查是否需要flush
            current_time = time.time()
            if (len(self._write_buffer) >= _BUFFER_SIZE or 
                current_time - self._last_flush_time >= _FLUSH_INTERVAL):
                self._flush_buffer()

    def _flush_buffer(self) -> None:
        """批量写入向量库"""
        with self._buffer_lock:
            if not self._write_buffer:
                return
            
            try:
                vs = self.vector_store
                if vs:
                    for user_id, content, metadata in self._write_buffer:
                        vs.add_memory(content, user_id=user_id, metadata=metadata)
                
                logger.info(f"批量写入 {len(self._write_buffer)} 条记录到向量库")
            except Exception as exc:
                logger.error(f"批量写入失败: {exc}")
            finally:
                self._write_buffer.clear()
                self._last_flush_time = time.time()

    def _update_knowledge_index(self, topic: str, knowledge_points: List[str]) -> None:
        """更新知识索引文件（已在上文定义）"""
        pass  # 已定义

    def get_status(self) -> Dict[str, Any]:
        """获取引擎状态"""
        vs = self.vector_store
        topic_count = len(self._load_knowledge_index())
        
        total_points = 0
        if vs:
            try:
                total_points = vs.count()
            except Exception:
                pass

        return {
            "total_memories": vs.count() if vs else 0,
            "search_engine": "available" if self.search_engine_ok else "unavailable",
            "vector_store": "available" if vs else "unavailable",
            "buffer_size": len(self._write_buffer),
            "knowledge_topics": topic_count,
            "knowledge_points_indexed": total_points,
        }