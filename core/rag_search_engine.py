"""RAG智能搜索引擎 - 多引擎支持 + ChromaDB + BeautifulSoup

工业级检索增强生成引擎：
- 多搜索引擎支持（百度/Bing/DuckDuckGo，自动选择可用引擎）
- httpx异步HTTP客户端（超时15s、跟随重定向、浏览器UA）
- BeautifulSoup网页正文提取（去script/style/nav/footer，智能截取3000字）
- ChromaDB向量存储（通过VectorMemoryStore单例，余弦相似度）
- 批量写入缓冲区（10条/30秒自动flush）
- 缓存策略：distance<0.3命中向量库则直接返回，未命中才联网
- JSON知识索引文件，支持按主题查询
"""
import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

        self._init_search_engine()
        self._init_vector_store()

    # ── 初始化 ──────────────────────────────────────────────────────────────
    def _init_search_engine(self) -> None:
        """初始化搜索引擎（支持多种引擎，自动选择可用的）"""
        try:
            from core.search_engine_factory import get_search_engine
            self._search_engine = get_search_engine()
            self._search_engine_ok = True
            engine_name = self._search_engine.__class__.__name__
            logger.info(f"搜索引擎初始化成功: {engine_name}")
        except Exception as exc:
            logger.warning(f"搜索引擎初始化失败: {exc}")

    def _init_vector_store(self) -> None:
        """延迟初始化 VectorMemoryStore 单例"""
        try:
            from core.vector_memory import VectorMemoryStore
            self._vector_store = VectorMemoryStore()
            logger.info("向量存储 (ChromaDB) 初始化成功")
        except Exception as exc:
            logger.error("向量存储初始化失败: %s", exc)
            self._vector_store = None

    # ── 属性 ────────────────────────────────────────────────────────────────
    @property
    def vector_store(self):
        """懒加载向量存储（仅当首次使用时创建）"""
        if self._vector_store is None:
            try:
                from core.vector_memory import VectorMemoryStore
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

    # ══════════════════════════════════════════════════════════════════════
    #  公开 API
    # ══════════════════════════════════════════════════════════════════════

    async def search_and_learn(
        self,
        query: str,
        user_id: int = 1,
        learn: bool = True,
        max_results: int = 5,
        enhance: bool = True,
    ) -> Dict[str, Any]:
        """搜索并自动学习

        策略：先查向量库 → 命中(distance<0.3)直接返回 → 未命中联网搜索 → 可选学习入库

        Args:
            query: 搜索查询
            user_id: 用户ID
            learn: 是否提取知识并写入向量库
            max_results: 最大搜索结果数
            enhance: 是否增强搜索结果（抓取网页内容）

        Returns:
            {
                "query", "from_cache", "results", "knowledge_extracted",
                "saved_to_kb", "timestamp", "error"(可选), "enhanced"
            }
        """
        # 1. 缓存策略：查向量库
        cached = self._check_existing_knowledge(query, user_id)
        if cached is not None:
            logger.info("RAG缓存命中: query=%s", query[:50])
            return {
                "query": query,
                "from_cache": True,
                "results": cached,
                "knowledge_extracted": [],
                "saved_to_kb": False,
                "timestamp": datetime.now().isoformat(),
                "enhanced": False,
            }

        # 2. 联网搜索
        try:
            search_results = await asyncio.wait_for(
                self._web_search(query, max_results),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.warning(f"搜索超时: {query[:50]}")
            search_results = []
        
        if not search_results:
            return {
                "query": query,
                "from_cache": False,
                "results": [],
                "knowledge_extracted": [],
                "saved_to_kb": False,
                "error": "搜索无结果",
                "timestamp": datetime.now().isoformat(),
                "enhanced": False,
            }

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

        return {
            "query": query,
            "from_cache": False,
            "results": enhanced_results[:max_results],
            "knowledge_extracted": knowledge_points,
            "saved_to_kb": len(knowledge_points) > 0,
            "timestamp": datetime.now().isoformat(),
            "enhanced": enhance,
        }

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
        if not self._search_engine:
            logger.warning("搜索引擎未初始化")
            return []

        try:
            loop = asyncio.get_running_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(None, self._search_engine.search, query, num_results),
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
            "search_engine": "available" if self._search_engine_ok else "unavailable",
            "vector_store": "available" if vs else "unavailable",
            "buffer_size": len(self._write_buffer),
            "knowledge_topics": topic_count,
            "knowledge_points_indexed": total_points,
        }