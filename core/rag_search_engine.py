"""RAG智能搜索引擎 - DuckDuckGo + ChromaDB + BeautifulSoup

工业级检索增强生成引擎：
- DuckDuckGo搜索（兼容新版ddgs库）
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

_HTTP_TIMEOUT = 15.0  # 秒

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
        self._ddgs = None
        self._vector_store = None
        self._write_buffer: List[Tuple[str, str, Dict[str, Any]]] = []
        self._buffer_lock = threading.Lock()
        self._last_flush_time = time.time()
        self._search_engine_ok = False

        self._init_search_engine()
        self._init_vector_store()

    # ── 初始化 ──────────────────────────────────────────────────────────────
    def _init_search_engine(self) -> None:
        """初始化 DuckDuckGo 搜索客户端（兼容新版 ddgs 库）"""
        for import_path in ("duckduckgo_search.DDGS", "ddgs.DDGS"):
            try:
                module_path, class_name = import_path.rsplit(".", 1)
                module = __import__(module_path, fromlist=[class_name])
                DDGS = getattr(module, class_name)
                self._ddgs = DDGS()
                self._search_engine_ok = True
                logger.info("DuckDuckGo搜索引擎初始化成功 (%s)", module_path)
                return
            except ImportError:
                continue
            except Exception as exc:
                logger.warning("DuckDuckGo初始化异常 (%s): %s", import_path, exc)
                continue
        logger.warning("duckduckgo-search / ddgs 均未安装，联网搜索不可用")

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
        search_results = await self._web_search(query, max_results)
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
            # 1. 从知识索引中查找相关主题
            index = self._load_knowledge_index()
            topics = index.get("topics", {})
            
            # 查找相关主题
            related_topics = []
            for t in topics:
                if topic in t or t in topic:
                    related_topics.append(t)
            
            # 2. 从向量库中搜索
            results = self._check_existing_knowledge(topic, user_id)
            
            # 3. 从知识索引中获取相关知识
            knowledge_points = []
            for t in related_topics:
                points = topics.get(t, [])
                for point in points[:5]:  # 每个主题最多取5条
                    knowledge_points.append({
                        "content": point.get("point", ""),
                        "timestamp": point.get("timestamp", ""),
                        "topic": t
                    })
            
            return {
                "topic": topic,
                "related_topics": related_topics,
                "vector_results": results or [],
                "knowledge_points": knowledge_points,
                "total_results": len(results or []) + len(knowledge_points),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"按主题搜索失败: {e}")
            return {
                "topic": topic,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    def get_knowledge_summary(self, topic: str = None) -> Dict[str, Any]:
        """获取知识摘要（增强版 - 自动生成摘要）
        
        Args:
            topic: 可选的主题过滤
            
        Returns:
            知识摘要（包含自动生成的文本摘要）
        """
        try:
            index = self._load_knowledge_index()
            topics = index.get("topics", {})
            
            summary = {
                "total_topics": len(topics),
                "total_knowledge_points": index.get("total_knowledge_points", 0),
                "last_updated": index.get("last_updated", ""),
                "topics": {},
                "topic_summaries": {}  # 新增：主题摘要
            }
            
            if topic:
                # 只返回相关主题
                for t in topics:
                    if topic in t or t in topic:
                        points = topics[t]
                        summary["topics"][t] = len(points)
                        # 生成主题摘要
                        summary["topic_summaries"][t] = self._generate_topic_summary(t, points)
            else:
                # 返回所有主题（限制数量）
                for t in list(topics.keys())[:20]:  # 最多20个主题
                    points = topics[t]
                    summary["topics"][t] = len(points)
                    # 生成主题摘要
                    summary["topic_summaries"][t] = self._generate_topic_summary(t, points)
            
            return summary
        except Exception as e:
            logger.error(f"获取知识摘要失败: {e}")
            return {
                "error": str(e)
            }
    
    def _generate_topic_summary(self, topic: str, knowledge_points: List[Dict]) -> str:
        """生成主题摘要
        
        Args:
            topic: 主题名称
            knowledge_points: 知识点列表
            
        Returns:
            生成的摘要文本
        """
        if not knowledge_points:
            return f"主题「{topic}」暂无相关知识"
        
        # 提取关键信息
        total_points = len(knowledge_points)
        latest_point = max(knowledge_points, key=lambda x: x.get("timestamp", ""))
        latest_time = latest_point.get("timestamp", "")[:10] if latest_point else "未知"
        
        # 提取前3个知识点的内容
        sample_contents = []
        for point in knowledge_points[:3]:
            content = point.get("point", "")
            if content:
                # 截取前50字符
                sample_contents.append(content[:50])
        
        # 生成摘要
        summary_parts = [
            f"主题「{topic}」共有 {total_points} 条知识点",
            f"最近更新时间: {latest_time}",
        ]
        
        if sample_contents:
            summary_parts.append("主要内容:")
            for i, content in enumerate(sample_contents, 1):
                summary_parts.append(f"  {i}. {content}...")
        
        return " | ".join(summary_parts)

    def cleanup_old_knowledge(self, days: int = 30) -> Dict[str, Any]:
        """清理过期知识（ChromaDB不支持按时间删除，标记清理状态）"""
        logger.info("RAG知识清理请求：保留最近 %d 天的知识", days)
        try:
            index = self._load_knowledge_index()
            cutoff = datetime.now().isoformat()[:10]
            cleaned = 0
            for topic in list(index.get("topics", {})):
                points = index["topics"][topic]
                before = len(points)
                points[:] = [
                    p for p in points
                    if p.get("timestamp", "9999") >= cutoff
                ]
                cleaned += before - len(points)
                if not points:
                    del index["topics"][topic]

            self._save_knowledge_index(index)
            return {"cleaned": cleaned, "remaining_topics": len(index.get("topics", {}))}
        except Exception as exc:
            logger.error("知识清理失败: %s", exc)
            return {"cleaned": 0, "error": str(exc)}

    def get_stats(self) -> Dict[str, Any]:
        """获取RAG引擎统计信息"""
        vs = self.vector_store
        try:
            index = self._load_knowledge_index()
            topic_count = len(index.get("topics", {}))
            total_points = index.get("total_knowledge_points", 0)
        except Exception:
            topic_count = 0
            total_points = 0

        return {
            "total_memories": vs.count() if vs else 0,
            "search_engine": "available" if self._search_engine_ok else "unavailable",
            "vector_store": "available" if vs else "unavailable",
            "buffer_size": len(self._write_buffer),
            "knowledge_topics": topic_count,
            "knowledge_points_indexed": total_points,
        }

    # ══════════════════════════════════════════════════════════════════════
    #  搜索
    # ══════════════════════════════════════════════════════════════════════

    async def _web_search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """DuckDuckGo异步搜索（在线程池中执行同步API调用）"""
        if not self._ddgs:
            return []

        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None, self._sync_ddg_search, query, num_results
            )
            return results
        except Exception as exc:
            logger.error("DuckDuckGo搜索失败: %s", exc)
            return []

    def _sync_ddg_search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """同步DDG搜索（在线程池中运行）"""
        results: List[Dict[str, Any]] = []
        try:
            items = self._ddgs.text(query, max_results=num_results)
            for item in items:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
                    "source": "duckduckgo",
                    "content": "",  # 由 _enrich_with_page_content 填充
                })
        except Exception as exc:
            logger.error("DDG搜索结果解析异常: %s", exc)
        return results

    # ══════════════════════════════════════════════════════════════════════
    #  网页内容提取
    # ══════════════════════════════════════════════════════════════════════

    async def _fetch_page_content(self, url: str) -> str:
        """异步抓取网页正文（httpx + BeautifulSoup）"""
        try:
            import httpx
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _BROWSER_UA},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # 移除无关标签
            for tag_name in _REMOVE_TAGS:
                for tag in soup.find_all(tag_name):
                    tag.decompose()

            # 尝试提取正文（优先 article/main/body）
            article = soup.find("article") or soup.find("main") or soup.find("body")
            if not article:
                article = soup

            text = article.get_text(separator="\n", strip=True)
            # 去除多余空行
            lines = [ln for ln in text.splitlines() if ln.strip()]
            cleaned = "\n".join(lines)

            # 智能截取前3000字符（在句号/换行处截断）
            if len(cleaned) > _MAX_CONTENT_LENGTH:
                cut = cleaned[:_MAX_CONTENT_LENGTH]
                # 找最后一个句号/换行
                last_break = max(cut.rfind("。"), cut.rfind("\n"))
                if last_break > _MAX_CONTENT_LENGTH * 0.5:
                    cut = cut[: last_break + 1]
                cleaned = cut

            return cleaned

        except ImportError:
            logger.warning("httpx 或 beautifulsoup4 未安装，无法抓取网页")
            return ""
        except Exception as exc:
            logger.debug("网页抓取失败 [%s]: %s", url[:80], exc)
            return ""

    async def _enrich_with_page_content(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """为搜索结果批量抓取正文（并行）"""
        tasks = []
        urls_to_fetch: List[str] = []
        for r in results:
            url = r.get("url", "")
            if url:
                tasks.append(self._fetch_page_content(url))
                urls_to_fetch.append(url)
            else:
                tasks.append(asyncio.coroutine(lambda: "")())

        contents = await asyncio.gather(*tasks, return_exceptions=True)

        enriched = []
        for r, url, content in zip(results, urls_to_fetch, contents):
            r_copy = dict(r)
            r_copy["content"] = content if isinstance(content, str) else ""
            enriched.append(r_copy)
        return enriched

    # ══════════════════════════════════════════════════════════════════════
    #  知识提取与索引
    # ══════════════════════════════════════════════════════════════════════

    def _extract_knowledge(
        self, search_results: List[Dict[str, Any]], query: str
    ) -> List[str]:
        """从搜索结果中提取关键知识点

        优先使用正文内容（content），回退到 snippet。
        每个结果最多生成1条知识点，最多返回5条。
        """
        knowledge_points: List[str] = []
        for result in search_results:
            title = result.get("title", "").strip()
            # 优先正文，回退snippet
            body = result.get("content", "") or result.get("snippet", "")
            body = body.strip()

            if not body or len(body) < 15:
                continue

            # 截取正文前500字作为知识摘要
            summary = body[:500]
            if len(body) > 500:
                last_period = summary.rfind("。")
                if last_period > 250:
                    summary = summary[: last_period + 1]

            kp = f"[{title}] {summary}"
            if len(kp) > 10:
                knowledge_points.append(kp)

        return knowledge_points[:5]

    def _update_knowledge_index(self, topic: str, knowledge_points: List[str]) -> None:
        """更新JSON知识索引文件"""
        try:
            index = self._load_knowledge_index()

            if topic not in index["topics"]:
                index["topics"][topic] = []

            ts = datetime.now().isoformat()
            for kp in knowledge_points:
                index["topics"][topic].append({
                    "point": kp,
                    "timestamp": ts,
                })

            # 防止单个主题无限膨胀，保留最近100条
            if len(index["topics"][topic]) > 100:
                index["topics"][topic] = index["topics"][topic][-100:]

            index["total_knowledge_points"] = sum(
                len(v) for v in index["topics"].values()
            )
            index["last_updated"] = ts

            self._save_knowledge_index(index)
        except Exception as exc:
            logger.error("知识索引更新失败: %s", exc)

    # ── 缓存查询 ────────────────────────────────────────────────────────────
    def _check_existing_knowledge(
        self, query: str, user_id: int
    ) -> Optional[List[Dict[str, Any]]]:
        """检查向量库是否已有足够相似的知识（distance < 0.3 视为命中）"""
        vs = self.vector_store
        if not vs:
            return None

        try:
            memories = vs.search_memories(query, user_id, top_k=3)
            if memories and memories[0].get("distance", 1.0) < _COSINE_HIT_THRESHOLD:
                return [
                    {
                        "content": m["content"],
                        "distance": m.get("distance", 0),
                        "source": "vector_cache",
                    }
                    for m in memories
                ]
        except Exception as exc:
            logger.error("向量库查询失败: %s", exc)
        return None

    # ── 批量写入缓冲 ────────────────────────────────────────────────────────
    def _buffered_add_memory(
        self,
        user_id: int,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """缓冲写入向量库，减少I/O开销"""
        vs = self.vector_store
        if not vs:
            return None

        memory_id = f"rag_{user_id}_{int(time.time() * 1000)}"
        meta = metadata or {}
        meta.update({
            "user_id": str(user_id),
            "category": "fact",
            "timestamp": datetime.now().isoformat(),
        })

        with self._buffer_lock:
            self._write_buffer.append((memory_id, content, meta))
            should_flush = (
                len(self._write_buffer) >= _BUFFER_SIZE
                or (time.time() - self._last_flush_time) >= _FLUSH_INTERVAL
            )
            if should_flush:
                self._flush_write_buffer()

        return memory_id

    def _flush_write_buffer(self) -> None:
        """将缓冲区内容批量写入ChromaDB"""
        if not self._write_buffer:
            return

        vs = self.vector_store
        if not vs or not vs._collection:
            return

        items = list(self._write_buffer)
        try:
            ids = [item[0] for item in items]
            docs = [item[1] for item in items]
            metas = [item[2] for item in items]
            vs._collection.add(ids=ids, documents=docs, metadatas=metas)
            logger.info("RAG批量写入 %d 条知识到ChromaDB", len(items))
        except Exception as exc:
            logger.error("批量写入ChromaDB失败: %s", exc)
        finally:
            self._write_buffer.clear()
            self._last_flush_time = time.time()

    # ── 知识索引文件IO ──────────────────────────────────────────────────────
    @staticmethod
    def _load_knowledge_index() -> Dict[str, Any]:
        """加载JSON知识索引"""
        if INDEX_FILE.exists():
            try:
                with open(INDEX_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as exc:
                logger.warning("知识索引加载失败，将重建: %s", exc)
        return {"topics": {}, "total_knowledge_points": 0}

    @staticmethod
    def _save_knowledge_index(index: Dict[str, Any]) -> None:
        """保存JSON知识索引"""
        try:
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except IOError as exc:
            logger.error("知识索引保存失败: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════
#  全局单例
# ═══════════════════════════════════════════════════════════════════════════
_rag_instance: Optional[RAGSearchEngine] = None
_rag_lock = threading.Lock()


def get_rag_engine() -> RAGSearchEngine:
    """获取RAG搜索引擎全局单例"""
    global _rag_instance
    if _rag_instance is None:
        with _rag_lock:
            if _rag_instance is None:
                _rag_instance = RAGSearchEngine()
    return _rag_instance