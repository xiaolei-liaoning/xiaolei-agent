"""ChromaDB向量存储（工业级）

VectorMemoryStore 单例类：
- 线程安全，批量缓冲写入（10条或30秒自动flush）
- PersistentClient + Settings(anonymized_telemetry=False)
- 集合：long_term_memory
- category 支持：general / fact / preference / experience
- 可配置 embedding 模型：在线（sentence-transformers）或离线（TF-IDF）
"""
import os
os.environ["CHROMADB_TELEMETRY_DISABLED"] = "1"

import chromadb
from chromadb.config import Settings
import threading
import time
import logging
import re
import math
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── Embedding 模型配置 ────────────────────────────────────────────────────────
# 设置 EMBEDDING_MODEL="local" 强制使用本地 TF-IDF
_EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "local")
_EMBEDDING_DEVICE = "cpu"
_EMBEDDING_BATCH_SIZE = 32

class LocalEmbeddingFunction:
    """本地 TF-IDF Embedding 函数（离线备选方案）

    当在线模型不可用时使用简单的 TF-IDF 实现
    - 无需网络连接
    - 支持中英文
    - 输出维度不固定（基于词汇表大小）
    """

    def __init__(self):
        self._vectorizer = None
        self._vocab = {}
        self._idf = {}
        self._dimension = 0

    def _tokenize(self, text: str) -> List[str]:
        """简单分词"""
        tokens = re.findall(r'[\w]+', text.lower())
        return tokens

    def _build_vocab(self, texts: List[str]):
        """构建词汇表"""
        vocab = {}
        for text in texts:
            for token in self._tokenize(text):
                if token not in vocab:
                    vocab[token] = len(vocab)
        return vocab

    def _compute_tfidf(self, text: str, vocab: Dict[str, int], idf: Dict[str, float]) -> List[float]:
        """计算 TF-IDF 向量"""
        tokens = self._tokenize(text)
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1

        max_tf = max(tf.values()) if tf else 1
        dimension = len(vocab)
        vector = [0.0] * dimension

        for token, count in tf.items():
            if token in vocab:
                tf_norm = count / max_tf
                idf_val = idf.get(token, 0)
                vector[vocab[token]] = tf_norm * idf_val

        return vector

    def __call__(self, input: List[str]) -> List[List[float]]:
        """ChromaDB API 调用接口"""
        if not input:
            return []

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            vectorizer = TfidfVectorizer()
            vectors = vectorizer.fit_transform(input).toarray()
            return vectors.tolist()
        except ImportError:
            logger.warning("sklearn 不可用，使用简单词向量")
            return self._simple_embedding(input)

    def _simple_embedding(self, texts: List[str]) -> List[List[float]]:
        """简单词向量（无 sklearn 时）"""
        vocab = self._build_vocab(texts)
        self._dimension = len(vocab)

        token_counts = {}
        for text in texts:
            for token in self._tokenize(text):
                token_counts[token] = token_counts.get(token, 0) + 1

        idf = {}
        N = len(texts)
        for token, df in token_counts.items():
            idf[token] = math.log(N / (df + 1)) + 1

        vectors = []
        for text in texts:
            vector = self._compute_tfidf(text, vocab, idf)
            vectors.append(vector)

        return vectors

    def embed_query(self, text: str) -> List[float]:
        """单独查询的 embedding"""
        return self(input=[text])[0]

    def get_dimension(self) -> int:
        """获取向量维度"""
        if self._dimension > 0:
            return self._dimension
        return 768


class BGEEmbeddingFunction:
    """Embedding 函数封装（适配 ChromaDB API）

    使用 shibing624/text2vec-base-chinese 模型，支持中文语义匹配
    - 中文语义embedding效果好
    - 支持最长序列 256 tokens
    - 输出维度 768
    """

    def __init__(
        self,
        model_name: str = _EMBEDDING_MODEL_NAME,
        device: str = _EMBEDDING_DEVICE,
        normalize_embeddings: bool = True,
        batch_size: int = _EMBEDDING_BATCH_SIZE,
    ):
        self.model_name = model_name
        self.device = device
        self.normalize_embeddings = normalize_embeddings
        self.batch_size = batch_size
        self._model = None
        self._max_seq_length = 512

    def _load_model(self):
        """延迟加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"正在加载 BGE 模型: {self.model_name}...")
                self._model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                    cache_folder=os.path.expanduser("~/.cache/bge"),
                )
                self._model.max_seq_length = self._max_seq_length
                logger.info(f"BGE 模型加载成功，设备: {self.device}, 输出维度: {self._model.get_sentence_embedding_dimension()}")
            except Exception as e:
                logger.error(f"BGE 模型加载失败: {e}")
                raise

    def __call__(self, input: List[str]) -> List[List[float]]:
        """ChromaDB API 调用接口

        Args:
            input: 文本列表

        Returns:
            embedding 列表
        """
        if not input:
            return []

        self._load_model()

        try:
            embeddings = self._model.encode(
                input,
                batch_size=self.batch_size,
                normalize_embeddings=self.normalize_embeddings,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Embedding 生成失败: {e}")
            raise

    def embed_query(self, text: str) -> List[float]:
        """单独查询的 embedding

        Args:
            text: 单条查询文本

        Returns:
            embedding 向量
        """
        return self(input=[text])[0]


_bge_embedding_function = None

def get_bge_embedding_function():
    """获取全局 embedding 函数单例（直接使用本地 TF-IDF）"""
    global _bge_embedding_function
    if _bge_embedding_function is None:
        logger.info("使用本地 TF-IDF Embedding")
        _bge_embedding_function = LocalEmbeddingFunction()
    return _bge_embedding_function

# ─── 支持的记忆类别 ──────────────────────────────────────────────────────────
VALID_CATEGORIES = {"general", "fact", "preference", "experience"}


class VectorMemoryStore:
    """ChromaDB 向量记忆存储（线程安全单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, persist_dir: str = None):
        if self._initialized:
            return
        self._initialized = True

        self.persist_dir = persist_dir or os.path.expanduser("~/.小雷版小龙虾/vector_db")
        os.makedirs(self.persist_dir, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = None
        self._ensure_initialized()

        # 批量写入缓冲区
        self._memory_buffer: List[tuple] = []
        self._buffer_lock = threading.Lock()
        self._last_flush_time = time.time()
        self._buffer_size = 10
        self._flush_interval = 30  # 秒
        
        # 定时备份配置
        self._backup_enabled = True
        self._backup_interval = 86400  # 24小时（秒）
        self._last_backup_time = time.time()
        self._backup_thread = None
        
        logger.info("VectorMemoryStore 初始化完成, persist_dir=%s", self.persist_dir)
        
        # 启动定时备份线程
        if self._backup_enabled:
            self._start_backup_scheduler()
    
    def _start_backup_scheduler(self):
        """启动定时备份调度器"""
        self._backup_stop = threading.Event()

        def backup_scheduler():
            while not self._backup_stop.is_set():
                # 使用 Event.wait() 替代 sleep，支持优雅关闭
                if self._backup_stop.wait(timeout=60):
                    break

                # 检查是否需要备份
                if time.time() - self._last_backup_time >= self._backup_interval:
                    try:
                        logger.info("执行定时备份...")
                        self.backup_memory()
                        self._last_backup_time = time.time()
                        logger.info("定时备份完成")
                    except Exception as e:
                        logger.error("定时备份失败: %s", e)

        self._backup_thread = threading.Thread(target=backup_scheduler, daemon=False)
        self._backup_thread.start()
        logger.info("定时备份调度器已启动 (间隔=%d秒)", self._backup_interval)

    def shutdown(self):
        """优雅关闭备份线程"""
        self._backup_enabled = False
        if hasattr(self, '_backup_stop'):
            self._backup_stop.set()
        if hasattr(self, '_backup_thread') and self._backup_thread.is_alive():
            self._backup_thread.join(timeout=10)
            if self._backup_thread.is_alive():
                logger.warning("备份线程未能在10秒内结束")
            else:
                logger.info("备份线程已优雅关闭")

    # ── 集合初始化 ───────────────────────────────────────────────────────────
    def _ensure_initialized(self):
        """确保集合存在（使用 text2vec embedding）"""
        try:
            embed_fn = get_bge_embedding_function()
            try:
                self._collection = self._client.get_collection(name="long_term_memory")
                logger.info("ChromaDB 集合 long_term_memory 已存在")
            except Exception:
                self._collection = self._client.get_or_create_collection(
                    name="long_term_memory",
                    metadata={"description": "用户长期记忆库 (text2vec-base-chinese)"},
                    embedding_function=embed_fn,
                )
                logger.info("ChromaDB 集合 long_term_memory 已创建")
            logger.info("ChromaDB 集合 long_term_memory 就绪")
        except Exception as e:
            logger.error("ChromaDB 初始化失败: %s", e)
            self._collection = None

    # ── 写入 ─────────────────────────────────────────────────────────────────
    def add_memory(self, user_id: int, content: str, category: str = "general",
                   metadata: Dict[str, Any] = None) -> Optional[str]:
        """添加一条记忆（缓冲写入）

        Args:
            user_id:   用户ID
            content:   记忆内容
            category:  general / fact / preference / experience
            metadata:  额外元数据

        Returns:
            memory_id 或 None
        """
        if not self._collection:
            logger.warning("集合未就绪，无法添加记忆")
            return None

        if category not in VALID_CATEGORIES:
            logger.warning("无效 category=%s, 将使用 general", category)
            category = "general"

        memory_id = f"mem_{user_id}_{int(time.time() * 1000)}"
        meta = metadata or {}
        meta.update({
            "user_id": str(user_id),
            "category": category,
            "timestamp": datetime.now().isoformat(),
        })

        with self._buffer_lock:
            self._memory_buffer.append((memory_id, content, meta))
            buffer_count = len(self._memory_buffer)
            time_since_flush = time.time() - self._last_flush_time

            if buffer_count >= self._buffer_size or time_since_flush > self._flush_interval:
                self._flush_buffer()

        logger.debug("记忆入缓冲: %s (缓冲=%d)", memory_id, buffer_count)
        return memory_id

    def _flush_buffer(self):
        """批量写入缓冲区到 ChromaDB"""
        if not self._memory_buffer or not self._collection:
            return

        items = list(self._memory_buffer)
        try:
            ids = [item[0] for item in items]
            docs = [item[1] for item in items]
            metas = [item[2] for item in items]
            self._collection.add(ids=ids, documents=docs, metadatas=metas)
            logger.info("ChromaDB 批量写入 %d 条记忆", len(items))
        except Exception as e:
            logger.error("批量写入 ChromaDB 失败: %s", e)
        finally:
            self._memory_buffer.clear()
            self._last_flush_time = time.time()

    # ── 检索 ─────────────────────────────────────────────────────────────────
    def search_memories(self, query: str, user_id: int = None,
                        top_k: int = 5) -> List[Dict[str, Any]]:
        """向量检索记忆（带 distance）

        Args:
            query:   查询文本
            user_id: 按用户过滤（None=不过滤）
            top_k:   最大返回条数

        Returns:
            [{"id", "content", "metadata", "distance"}, ...]
        """
        if not self._collection or not query or not query.strip():
            return []

        where_filter: Dict[str, Any] = {}
        if user_id is not None:
            where_filter["user_id"] = str(user_id)

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter if where_filter else None,
            )

            memories: List[Dict[str, Any]] = []
            if results and results["ids"] and results["ids"][0]:
                for mem_id, doc, meta, dist in zip(
                    results["ids"][0],
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    memories.append({
                        "id": mem_id,
                        "content": doc,
                        "metadata": meta,
                        "distance": dist,
                    })

            logger.debug("向量检索: query=%s, user_id=%s, 命中=%d",
                         query[:30], user_id, len(memories))
            return memories
        except Exception as e:
            logger.error("向量检索失败: %s", e)
            return []

    # ── 删除 / 统计 / 清空 ────────────────────────────────────────────────────
    def delete_memory(self, memory_id: str):
        """删除单条记忆"""
        if not self._collection:
            return
        try:
            self._collection.delete(ids=[memory_id])
            logger.info("记忆已删除: %s", memory_id)
        except Exception as e:
            logger.error("删除记忆失败: %s", e)

    def count(self) -> int:
        """返回集合中的记忆总数"""
        if not self._collection:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    def clear_all(self):
        """清空所有记忆（重建集合）"""
        old_collection = self._collection
        if not old_collection:
            return
        self._collection = None  # 先置空，避免中间状态不一致
        try:
            self._client.delete_collection("long_term_memory")
            embed_fn = get_bge_embedding_function()
            self._collection = self._client.get_or_create_collection(
                name="long_term_memory",
                metadata={"description": "用户长期记忆库 (text2vec-base-chinese)"},
                embedding_function=embed_fn,
            )
            logger.info("向量库已清空并重建 (text2vec-base-chinese)")
        except Exception as e:
            logger.error("清空向量库失败: %s", e)
            self._collection = old_collection  # 恢复旧引用

    def cleanup_old_memories(self, keep_last: int = 1000):
        """清理旧记忆，保留最近 keep_last 条

        ChromaDB 不支持按时间删除，这里采用 get → delete 策略：
        先获取全部ID，按时间排序后删除多余部分。
        """
        if not self._collection:
            return 0

        try:
            all_data = self._collection.get(include=["metadatas"])
            total = len(all_data["ids"])
            if total <= keep_last:
                logger.info("记忆总数 %d <= keep_last %d, 无需清理", total, keep_last)
                return 0

            # 按 timestamp 排序（取最新 keep_last 条）
            items = list(zip(all_data["ids"], all_data["metadatas"]))
            items.sort(
                key=lambda x: x[1].get("timestamp", "0000") if x[1] else "0000",
                reverse=True,
            )

            to_delete = [item[0] for item in items[keep_last:]]
            if to_delete:
                self._collection.delete(ids=to_delete)
                logger.info("清理旧记忆: 删除 %d 条, 保留 %d 条",
                            len(to_delete), keep_last)

            return len(to_delete)
        except Exception as e:
            logger.error("清理旧记忆失败: %s", e)
            return 0
    
    def backup_memory(self, backup_dir: str = None) -> bool:
        """备份向量存储
        
        Args:
            backup_dir: 备份目录，默认为 persist_dir/backups
            
        Returns:
            是否备份成功
        """
        try:
            import shutil
            import datetime
            
            if backup_dir is None:
                backup_dir = os.path.join(self.persist_dir, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            # 创建带时间戳的备份目录
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"backup_{timestamp}")
            
            # 检查备份目录是否已存在（避免重复备份）
            if os.path.exists(backup_path):
                logger.warning("备份目录已存在，跳过: %s", backup_path)
                return True
            
            # 只复制chromadb数据文件，不复制backups目录
            chroma_files = [f for f in os.listdir(self.persist_dir) 
                          if not f.startswith('.') and f != 'backups']
            
            if chroma_files:
                os.makedirs(backup_path, exist_ok=True)
                for item in chroma_files:
                    src = os.path.join(self.persist_dir, item)
                    dst = os.path.join(backup_path, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                
                logger.info("向量存储备份成功: %s (共%d个文件)", backup_path, len(chroma_files))
                return True
            else:
                logger.warning("没有可备份的文件")
                return False
        except Exception as e:
            logger.error("备份向量存储失败: %s", e)
            return False
    
    def restore_memory(self, backup_path: str) -> bool:
        """从备份恢复向量存储
        
        Args:
            backup_path: 备份路径
            
        Returns:
            是否恢复成功
        """
        try:
            import shutil
            
            if not os.path.exists(backup_path):
                logger.error("备份路径不存在: %s", backup_path)
                return False
            
            # 停止当前连接
            if self._collection:
                # 这里可以添加关闭连接的逻辑
                pass
            
            # 备份当前数据（以防万一）
            self.backup_memory()
            
            # 清空当前目录并复制备份
            shutil.rmtree(self.persist_dir)
            shutil.copytree(backup_path, self.persist_dir)
            
            # 重新初始化
            self._ensure_initialized()
            logger.info("向量存储从备份恢复成功: %s", backup_path)
            return True
        except Exception as e:
            logger.error("恢复向量存储失败: %s", e)
            return False
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取内存统计信息
        
        Returns:
            统计信息
        """
        stats = {
            "total_memories": self.count(),
            "persist_dir": self.persist_dir,
            "buffer_size": len(self._memory_buffer),
            "last_flush_time": self._last_flush_time,
            "buffer_flush_interval": self._flush_interval,
            "buffer_max_size": self._buffer_size
        }
        
        # 分类统计
        try:
            if self._collection:
                all_data = self._collection.get(include=["metadatas"])
                categories = {}
                for meta in all_data.get("metadatas", []):
                    if meta:
                        category = meta.get("category", "general")
                        categories[category] = categories.get(category, 0) + 1
                stats["category_distribution"] = categories
        except Exception as e:
            logger.error("获取分类统计失败: %s", e)
        
        return stats
    
    def optimize_memory(self):
        """优化内存存储

        执行清理和压缩操作
        """
        try:
            # 清理旧记忆
            deleted = self.cleanup_old_memories()

            # 执行备份
            self.backup_memory()

            logger.info("内存优化完成，删除了 %d 条旧记忆", deleted)
            return {
                "deleted_count": deleted,
                "success": True
            }
        except Exception as e:
            logger.error("内存优化失败: %s", e)
            return {
                "success": False,
                "error": str(e)
            }

    def get_embedding_dimension(self) -> int:
        """获取 embedding 向量维度

        Returns:
            embedding 维度
        """
        try:
            embed_fn = get_bge_embedding_function()
            
            if hasattr(embed_fn, 'get_dimension'):
                return embed_fn.get_dimension()
            
            if hasattr(embed_fn, '_load_model'):
                embed_fn._load_model()
                return embed_fn._model.get_sentence_embedding_dimension()
            
            return 768
        except Exception as e:
            logger.error("获取 embedding 维度失败: %s", e)
            return 0

    def test_embedding(self) -> Dict[str, Any]:
        """测试 embedding 是否正常工作

        Returns:
            测试结果字典
        """
        try:
            embed_fn = get_bge_embedding_function()

            test_texts = [
                "深度学习是机器学习的一个分支",
                "人工智能改变了我们的生活方式",
                "Python是一门强大的编程语言"
            ]

            embeddings = embed_fn(test_texts)

            model_name = getattr(embed_fn, 'model_name', 'Local TF-IDF')
            device = getattr(embed_fn, 'device', 'local')

            return {
                "success": True,
                "model": model_name,
                "dimension": len(embeddings[0]) if embeddings else 0,
                "device": device,
                "test_count": len(test_texts),
                "sample_norm": round(sum(sum(e * e for e in emb) ** 0.5 for emb in embeddings) / len(embeddings), 4) if embeddings else 0
            }
        except Exception as e:
            logger.error("Embedding 测试失败: %s", e)
            return {
                "success": False,
                "error": str(e)
            }



