"""BFS文本处理器 - 全局公共底层工具

提供文本的广度优先搜索处理能力，支持：
- 文本BFS遍历（按段落、句子层级）
- 内容树构建与处理
- 上下文队列管理
- 可复用的文本分析基础功能
"""

import logging
import time
from collections import deque
from functools import lru_cache
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TextNode:
    """文本节点"""
    content: str                    # 节点内容
    level: int = 0                  # 层级深度
    node_type: str = "paragraph"   # 节点类型：paragraph/sentence/summary
    parent: Optional['TextNode'] = None  # 父节点
    children: List['TextNode'] = field(default_factory=list)  # 子节点
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def __str__(self):
        return f"TextNode(level={self.level}, type={self.node_type}, content_len={len(self.content)})"


class BFSTextProcessor:
    """BFS文本处理器 - 全局公共工具
    
    提供文本的广度优先搜索处理能力，可用于：
    - 长文本分层处理
    - 上下文记忆管理
    - 内容树构建与遍历
    """
    
    def __init__(self, max_depth: int = 5, max_nodes: int = 100):
        """初始化BFS处理器
        
        Args:
            max_depth: 最大遍历深度
            max_nodes: 最大节点数量
        """
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        
        # P0修复5：添加上下文缓存（TTL 60秒）
        self._context_cache = {}
        self._cache_ttl = 60  # 秒
        
        logger.info("BFSTextProcessor 初始化完成 (max_depth=%d, max_nodes=%d)", 
                   max_depth, max_nodes)
    
    def split_into_paragraphs(self, text: str) -> List[str]:
        """将文本拆分为段落
        
        Args:
            text: 原始文本
            
        Returns:
            段落列表
        """
        if not text or not text.strip():
            return []
        
        # 按换行符分割，过滤空段落
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        
        logger.debug("文本拆分为 %d 个段落", len(paragraphs))
        return paragraphs
    
    def build_content_tree(self, paragraphs: List[str], 
                          summarizer: Optional[Callable] = None,
                          skills: Optional[List[str]] = None) -> TextNode:
        """构建多层双节点内容树（按用户设计）
        
        树结构设计：
        - 第1层（level=0）：根节点
        - 第2层（level=1）：所有Skill功能节点（如"爬取"、"总结"、"搜索"等）
        - 第3层及以下：双节点结构（以第一个skill为根继续构建）
          - 左节点：概要（summary）
          - 右节点：内容（content）
          - 内容节点的左孩子：下一部分概要
          - 内容节点的右孩子：下一部分内容
        
        Args:
            paragraphs: 段落列表
            summarizer: 摘要函数，签名为 func(text: str) -> str
            skills: 功能节点名称列表
        
        Returns:
            根节点
        """
        if not paragraphs:
            raise ValueError("段落列表不能为空")
        
        # 设置默认skills列表
        if skills is None:
            skills = ["爬取", "总结", "搜索", "分析", "翻译"]
        
        # ===== 第1层：根节点 =====
        root = TextNode(
            content="文档根节点",
            level=0,
            node_type="root"
        )
        
        # ===== 第2层：所有Skill功能节点 =====
        skill_nodes = {}
        for skill_name in skills:
            skill_node = TextNode(
                content=skill_name,
                level=1,
                node_type="function",
                parent=root,
                metadata={"skill": skill_name}
            )
            root.children.append(skill_node)
            skill_nodes[skill_name] = skill_node
        
        # ===== 第3层及以下：递归构建双节点结构 =====
        # 以第一个skill作为内容树的根继续构建
        primary_skill = skills[0] if skills else "unknown"
        current_parent = skill_nodes.get(primary_skill) or root
        
        for idx, paragraph in enumerate(paragraphs):
            # 生成段落摘要
            summary_text = summarizer(paragraph) if summarizer else "..."
            
            # ===== 创建当前段落的双节点 =====
            # 左节点：概要 (level = 2 + idx*2)
            summary_node = TextNode(
                content=summary_text,
                level=current_parent.level + 1,
                node_type="summary",
                parent=current_parent,
                metadata={"index": idx, "type": "summary", "part": idx + 1}
            )
            
            # 右节点：内容 (level = 2 + idx*2)
            content_node = TextNode(
                content=paragraph,
                level=current_parent.level + 1,
                node_type="content",
                parent=current_parent,
                metadata={"index": idx, "type": "content", "part": idx + 1}
            )
            
            # 将双节点添加到当前父节点
            current_parent.children.append(summary_node)
            current_parent.children.append(content_node)
            
            # 更新当前父节点为内容节点（下一段落的双节点作为当前内容节点的子节点）
            current_parent = content_node
        
        logger.info("多层双节点内容树构建完成，共 %d 个Skill，%d 个段落，树深度 %d", 
                   len(skills), len(paragraphs), current_parent.level)
        return root
    
    def bfs_traverse(self, root: TextNode) -> deque:
        """广度优先遍历内容树，生成上下文队列
        
        Args:
            root: 根节点
            
        Returns:
            BFS遍历的节点队列
        """
        if not root:
            return deque()
        
        queue = deque()
        visited = set()
        result_queue = deque()
        
        # 将根节点加入队列
        queue.append(root)
        visited.add(id(root))
        
        while queue and len(result_queue) < self.max_nodes:
            current = queue.popleft()
            
            # 跳过根节点（只处理实际内容）
            if current.node_type != "root":
                result_queue.append(current)
            
            # 将子节点加入队列
            for child in current.children:
                child_id = id(child)
                if child_id not in visited and current.level < self.max_depth:
                    visited.add(child_id)
                    queue.append(child)
        
        logger.info("BFS遍历完成，生成 %d 个上下文节点", len(result_queue))
        return result_queue
    
    def bfs_traverse_dict(self, root: Dict[str, Any]) -> List[Dict[str, Any]]:
        """广度优先遍历字典树（适配TextAnalyzerAgent的树结构）
        
        Args:
            root: 字典格式的根节点
            
        Returns:
            BFS遍历的节点列表
        """
        if not root:
            return []
        
        queue = [root]
        result = []
        level_map = {}  # 记录每个节点的层级
        
        # 计算根节点层级
        level_map[id(root)] = 1
        
        while queue and len(result) < self.max_nodes:
            current = queue.pop(0)  # 队列先进先出（BFS）
            
            # 获取当前节点层级
            current_level = level_map.get(id(current), 1)
            
            # 添加当前节点到结果（跳过根节点）
            if current.get("type") != "root":
                node_info = {
                    "type": current.get("type"),
                    "content": current.get("content", current.get("title", "")),
                    "level": current_level
                }
                result.append(node_info)
            
            # 将子节点加入队列
            if "children" in current and current["children"]:
                for child in current["children"]:
                    level_map[id(child)] = current_level + 1
                    queue.append(child)
        
        logger.info("字典树BFS遍历完成，生成 %d 个节点", len(result))
        return result
    
    def process_text(self, text: str, 
                    summarizer: Optional[Callable] = None) -> Dict[str, Any]:
        """完整的文本BFS处理流程
        
        Args:
            text: 原始文本
            summarizer: 可选的摘要函数
            
        Returns:
            处理结果字典
        """
        try:
            # 步骤1: 段落拆分
            paragraphs = self.split_into_paragraphs(text)
            if not paragraphs:
                return {
                    "success": False,
                    "error": "文本为空或无法拆分段落",
                    "paragraphs_count": 0,
                    "context_queue_size": 0
                }
            
            # 步骤2: 构建内容树
            root = self.build_content_tree(paragraphs, summarizer)
            
            # 步骤3: BFS遍历
            context_queue = self.bfs_traverse(root)
            
            # 步骤4: 转换为列表（便于序列化）
            context_list = []
            for node in context_queue:
                context_list.append({
                    "content": node.content[:200],  # 限制长度
                    "level": node.level,
                    "type": node.node_type,
                    "metadata": node.metadata
                })
            
            result = {
                "success": True,
                "paragraphs_count": len(paragraphs),
                "context_queue_size": len(context_list),
                "context_queue": context_list,
                "tree_root_type": root.node_type,
                "tree_children_count": len(root.children)
            }
            
            logger.info("文本BFS处理完成: %d 段落 → %d 上下文节点", 
                       len(paragraphs), len(context_list))
            return result
            
        except Exception as e:
            logger.error("文本BFS处理失败: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "paragraphs_count": 0,
                "context_queue_size": 0
            }
    
    def extract_context_by_keywords(self, context_queue: deque, 
                                   keywords: List[str],
                                   top_k: int = 5) -> List[Dict[str, Any]]:
        """基于关键词从上下文队列中提取相关内容
        
        Args:
            context_queue: BFS生成的上下文队列
            keywords: 关键词列表
            top_k: 返回最相关的top_k个节点
            
        Returns:
            相关节点列表（带相关性分数）
        """
        if not context_queue or not keywords:
            return []
        
        scored_nodes = []
        
        for node in context_queue:
            score = 0.0
            content_lower = node.content.lower()
            
            # 计算关键词匹配分数
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in content_lower:
                    # 完整匹配得分更高
                    score += 1.0
                    # 考虑出现次数
                    count = content_lower.count(keyword_lower)
                    score += count * 0.5
            
            # 考虑层级权重（浅层节点更重要）
            level_weight = 1.0 / (1 + node.level * 0.2)
            score *= level_weight
            
            if score > 0:
                scored_nodes.append({
                    "node": node,
                    "score": score,
                    "matched_keywords": [
                        kw for kw in keywords 
                        if kw.lower() in node.content.lower()
                    ]
                })
        
        # 按分数排序
        scored_nodes.sort(key=lambda x: x["score"], reverse=True)
        
        # 返回top_k
        result = []
        for item in scored_nodes[:top_k]:
            node = item["node"]
            result.append({
                "content": node.content,
                "level": node.level,
                "type": node.node_type,
                "score": round(item["score"], 3),
                "matched_keywords": item["matched_keywords"],
                "metadata": node.metadata
            })
        
        logger.info("关键词检索完成，返回 %d 个相关节点", len(result))
        return result

    def add_node(self, user_id: int, role: str, content: str,
                 summary: str = "", metadata: Dict[str, Any] = None) -> bool:
        """添加节点到对话历史（兼容旧接口）

        Args:
            user_id: 用户ID
            role: 角色 (user/assistant/system)
            content: 内容
            summary: 摘要
            metadata: 元数据

        Returns:
            是否成功
        """
        try:
            from core.database import get_session, ChatHistory
            from datetime import datetime

            session = get_session()
            if session is None:
                logger.debug("数据库会话未初始化，跳过BFS节点添加")
                return True

            record = ChatHistory(
                user_id=user_id,
                role=role,
                content=content,
                summary=summary,
                metadata=metadata or {},
                created_at=datetime.now()
            )
            session.add(record)
            session.commit()
            session.close()
            logger.debug(f"BFS节点添加成功: user={user_id}, role={role}")
            return True

        except RuntimeError:
            logger.debug("数据库未初始化，跳过BFS节点添加")
            return True
        except Exception as e:
            logger.debug(f"添加BFS节点失败: {e}")
            return True

    def get_context(self, user_id: int, depth: int = 2, limit: int = 10) -> List[Dict[str, Any]]:
        """获取用户对话上下文历史 - P0修复：添加缓存
        
        Args:
            user_id: 用户ID
            depth: 获取的对话深度（往返次数）
            limit: 返回的最大记录数
            
        Returns:
            用户的对话上下文历史列表
        """
        # P0修复：检查缓存
        cache_key = f"{user_id}_{depth}_{limit}"
        now = time.time()
        
        if cache_key in self._context_cache:
            cached_time, cached_data = self._context_cache[cache_key]
            if now - cached_time < self._cache_ttl:
                logger.debug(f"BFS上下文缓存命中: user={user_id}")
                return cached_data
        
        try:
            from core.database import get_session, ChatHistory
            
            session = get_session()
            if session is None:
                logger.warning("数据库会话未初始化，返回空上下文")
                return []
            
            from sqlalchemy import desc
            history_records = session.query(ChatHistory).filter(
                ChatHistory.user_id == user_id
            ).order_by(
                desc(ChatHistory.created_at)
            ).limit(limit).all()
            
            session.close()
            
            context = []
            for record in history_records:
                context.append({
                    "id": record.id,
                    "role": record.role,
                    "content": record.content,
                    "created_at": record.created_at.isoformat() if record.created_at else None
                })

            logger.debug(f"获取用户{user_id}的上下文: {len(context)}条记录")
            
            # P0修复：更新缓存
            self._context_cache[cache_key] = (now, context)
            
            # 清理过期缓存
            self._cleanup_cache(now)
            
            return context

        except RuntimeError:
            logger.debug("数据库未初始化，跳过获取用户上下文")
            return []
        except Exception as e:
            logger.debug(f"获取用户上下文失败: {e}")
            return []
    
    def _cleanup_cache(self, now: float):
        """清理过期缓存"""
        expired_keys = [
            key for key, (cached_time, _) in self._context_cache.items()
            if now - cached_time >= self._cache_ttl
        ]
        for key in expired_keys:
            del self._context_cache[key]


# 全局单例实例
_bfs_processor_instance = None
_bfs_processor_config = {"max_depth": 5, "max_nodes": 100}


def get_bfs_processor(max_depth: int = None, max_nodes: int = None) -> BFSTextProcessor:
    """获取BFS文本处理器单例
    
    注意：单例模式只考虑首次调用时的参数配置，后续调用忽略参数差异
    
    Args:
        max_depth: 最大遍历深度（仅首次调用生效）
        max_nodes: 最大节点数量（仅首次调用生效）
        
    Returns:
        BFSTextProcessor实例
    """
    global _bfs_processor_instance, _bfs_processor_config
    if _bfs_processor_instance is None:
        if max_depth is not None:
            _bfs_processor_config["max_depth"] = max_depth
        if max_nodes is not None:
            _bfs_processor_config["max_nodes"] = max_nodes
        _bfs_processor_instance = BFSTextProcessor(
            max_depth=_bfs_processor_config["max_depth"],
            max_nodes=_bfs_processor_config["max_nodes"]
        )
        logger.info(f"BFS处理器单例已创建: max_depth={_bfs_processor_config['max_depth']}, max_nodes={_bfs_processor_config['max_nodes']}")
    return _bfs_processor_instance


"""BFS任务调度器 - 真正的任务分解与执行引擎

实现基于BFS的任务调度机制：
- 任务树构建：将复杂任务分解为多层级子任务
- BFS队列管理：按层级顺序处理任务节点
- 动态任务分解：功能节点自动展开为子任务
- 叶子节点执行：直接执行可操作的任务

核心流程：
1. 从根节点开始，将任务加入BFS队列
2. 取出队首节点
3. 如果是功能节点（需要分解）：展开子任务并入队
4. 如果是叶子节点（可执行）：直接执行并收集结果
5. 重复直到队列为空
"""

import logging
from collections import deque
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class NodeType(Enum):
    """节点类型枚举"""
    ROOT = "root"              # 根节点：总任务
    FUNCTION = "function"      # 功能层：需要分解的任务（如"爬取"）
    TEXT = "text"             # 文本层：具体任务（如"文章1"）
    PARAGRAPH = "paragraph"   # 段落层：细分任务（如"段落1"）
    LEAF = "leaf"             # 叶子节点：可直接执行的任务


@dataclass
class TaskNode:
    """任务节点
    
    对应你画的图中的所有节点类型
    """
    name: str                   # 节点名称（如"根"、"爬"、"文章1"、"段落1全文"）
    node_type: NodeType         # 节点类型
    children: List['TaskNode'] = field(default_factory=list)  # 子节点列表
    task_data: Optional[Dict[str, Any]] = None  # 任务数据（叶子节点才有）
    parent: Optional['TaskNode'] = None  # 父节点引用
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def is_function_node(self) -> bool:
        """判断是否为功能节点（需要继续分解）
        
        Returns:
            True表示需要分解，False表示是叶子节点可直接执行
        """
        return self.node_type in [NodeType.ROOT, NodeType.FUNCTION, 
                                  NodeType.TEXT, NodeType.PARAGRAPH]
    
    def is_leaf_node(self) -> bool:
        """判断是否为叶子节点（可直接执行）"""
        return self.node_type == NodeType.LEAF
    
    def __str__(self):
        return f"TaskNode(name={self.name}, type={self.node_type.value}, has_task={self.task_data is not None})"


class BFSTaskScheduler:
    """BFS任务调度器（已废弃 - DEPRECATED）
    
    ⚠️ 此模块当前未被主流程使用，仅在测试文件中引用。
    如需任务树功能，请使用 TaskExecutor + NaturalLanguageTaskParser。
    
    实现你画的两张图的核心逻辑：
    - 图1：任务树的层级结构（根→功能→文本→段落→叶子）
    - 图2：BFS队列的工作方式（功能节点出队→子节点入队→叶子节点执行）
    """
    
    def __init__(self, max_concurrent: int = 5):
        """初始化调度器
        
        Args:
            max_concurrent: 最大并发任务数（用于多线程扩展）
        """
        self.max_concurrent = max_concurrent
        self.execution_log: List[Dict[str, Any]] = []  # 执行日志
        self._queue_lock = threading.Lock()  # 队列锁（多线程用）
        logger.info("BFSTaskScheduler 初始化完成 (max_concurrent=%d)", max_concurrent)
    
    def execute_bfs(self, root: TaskNode, 
                   executor: Optional[Callable] = None) -> List[Any]:
        """执行BFS任务调度（核心算法）
        
        对应你图2的队列流程：
        1. 队列初始化：queue = deque([root])
        2. 取出队首：current_node = queue.popleft()
        3. 判断类型：
           - 功能节点：子节点全部入队
           - 叶子节点：执行任务
        4. 循环直到队列为空
        
        Args:
            root: 任务树的根节点
            executor: 任务执行函数，签名为 func(task_data: dict) -> result
                     如果为None，则返回task_data本身
            
        Returns:
            所有叶子节点的执行结果列表
        """
        if executor is None:
            executor = lambda task_data: task_data
        
        # 初始化BFS队列
        queue = deque([root])
        all_results = []
        
        logger.info("🚀 开始BFS任务调度，根节点: %s", root.name)
        
        while queue:
            # 1. 取出队首节点（先进先出，BFS核心）
            current_node = queue.popleft()
            logger.debug("📋 处理节点: %s (类型: %s)", 
                        current_node.name, current_node.node_type.value)
            
            # 记录执行日志
            log_entry = {
                "node_name": current_node.name,
                "node_type": current_node.node_type.value,
                "action": "decomposed" if current_node.is_function_node() else "executed"
            }
            
            # 2. 判断节点类型
            if current_node.is_leaf_node():
                # 叶子节点：直接执行任务
                logger.info("✅ 执行叶子任务: %s", current_node.name)
                
                try:
                    result = executor(current_node.task_data)
                    all_results.append({
                        "node": current_node.name,
                        "result": result
                    })
                    log_entry["result"] = "success"
                except Exception as e:
                    logger.error("❌ 任务执行失败: %s, 错误: %s", 
                               current_node.name, str(e))
                    log_entry["result"] = f"failed: {str(e)}"
            else:
                # 功能节点：把所有子节点入队
                logger.info("🔀 分解功能节点: %s → %d 个子任务", 
                           current_node.name, len(current_node.children))
                
                for child in current_node.children:
                    queue.append(child)
                    logger.debug("  ➕ 子任务入队: %s", child.name)
                
                log_entry["children_count"] = len(current_node.children)
            
            self.execution_log.append(log_entry)
        
        logger.info("🎉 BFS任务调度完成，共执行 %d 个叶子任务", len(all_results))
        return all_results

    def execute_bfs_parallel(self, root: TaskNode,
                            executor: Optional[Callable] = None) -> List[Any]:
        """并行版BFS任务调度（多线程扩展）
        
        使用线程池并行执行叶子节点任务，适合I/O密集型任务（如网络爬取）
        
        Args:
            root: 任务树的根节点
            executor: 任务执行函数
            
        Returns:
            所有叶子节点的执行结果列表
        """
        if executor is None:
            executor = lambda task_data: task_data
        
        # 第一阶段：BFS遍历，收集所有叶子节点
        queue = deque([root])
        leaf_nodes = []
        
        logger.info("🚀 开始并行BFS任务调度")
        
        while queue:
            current_node = queue.popleft()
            
            if current_node.is_leaf_node():
                leaf_nodes.append(current_node)
            else:
                for child in current_node.children:
                    queue.append(child)
        
        logger.info("📊 共发现 %d 个叶子任务，启动 %d 个线程并行执行", 
                   len(leaf_nodes), self.max_concurrent)
        
        # 第二阶段：并行执行叶子节点
        all_results = []
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as pool:
            future_to_node = {}
            
            # 提交所有任务到线程池
            for node in leaf_nodes:
                future = pool.submit(executor, node.task_data)
                future_to_node[future] = node
            
            # 收集结果
            for future in as_completed(future_to_node):
                node = future_to_node[future]
                try:
                    result = future.result()
                    all_results.append({
                        "node": node.name,
                        "result": result
                    })
                    logger.info("✅ 完成: %s", node.name)
                except Exception as e:
                    logger.error("❌ 失败: %s, 错误: %s", node.name, str(e))
                    all_results.append({
                        "node": node.name,
                        "result": {"error": str(e)}
                    })
        
        logger.info("🎉 并行BFS调度完成")
        return all_results
    
    def build_sample_crawl_tree(self) -> TaskNode:
        """构建示例爬取任务树（完全对应你画的图1）
        
        树结构：
        根
        └─ 爬（功能层）
           ├─ 文章1（文本层）
           │  ├─ P1（段落层）
           │  │  └─ 段落1全文（叶子）
           │  ├─ P2（段落层）
           │  │  └─ 段落2全文（叶子）
           │  └─ P3（段落层）
           │     └─ 段落3全文（叶子）
           ├─ 文章2（文本层）
           └─ 文章3（文本层）
        
        Returns:
            根节点
        """
        # ===== 第4层：叶子节点（可直接执行的爬取任务）=====
        p1_full = TaskNode(
            name="段落1全文",
            node_type=NodeType.LEAF,
            task_data={"url": "https://example.com/article1/para1", "type": "crawl"}
        )
        p2_full = TaskNode(
            name="段落2全文",
            node_type=NodeType.LEAF,
            task_data={"url": "https://example.com/article1/para2", "type": "crawl"}
        )
        p3_full = TaskNode(
            name="段落3全文",
            node_type=NodeType.LEAF,
            task_data={"url": "https://example.com/article1/para3", "type": "crawl"}
        )
        
        # ===== 第3层：段落层（需要分解为叶子节点）=====
        p1 = TaskNode(name="P1", node_type=NodeType.PARAGRAPH, children=[p1_full])
        p2 = TaskNode(name="P2", node_type=NodeType.PARAGRAPH, children=[p2_full])
        p3 = TaskNode(name="P3", node_type=NodeType.PARAGRAPH, children=[p3_full])
        
        # ===== 第2层：文本层（文章任务）=====
        article1 = TaskNode(
            name="文章1",
            node_type=NodeType.TEXT,
            children=[p1, p2, p3],
            task_data={"article_id": 1, "title": "第一篇文章"}
        )
        article2 = TaskNode(
            name="文章2",
            node_type=NodeType.TEXT,
            children=[],  # 简化示例，没有段落
            task_data={"article_id": 2, "title": "第二篇文章"}
        )
        article3 = TaskNode(
            name="文章3",
            node_type=NodeType.TEXT,
            children=[],
            task_data={"article_id": 3, "title": "第三篇文章"}
        )
        
        # ===== 第1层：功能层（爬取任务）=====
        crawl = TaskNode(
            name="爬",
            node_type=NodeType.FUNCTION,
            children=[article1, article2, article3],
            task_data={"task_type": "web_crawling"}
        )
        
        # ===== 第0层：根节点 =====
        root = TaskNode(
            name="根",
            node_type=NodeType.ROOT,
            children=[crawl],
            task_data={"project": "文章爬取项目"}
        )
        
        logger.info("✅ 示例任务树构建完成")
        return root


# ==================== 使用示例 ====================
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    print("\n" + "="*80)
    print("演示1: 单线程BFS调度")
    print("="*80)
    
    # 创建调度器
    scheduler = BFSTaskScheduler(max_concurrent=5)
    
    # 构建任务树
    tree = scheduler.build_sample_crawl_tree()
    
    # 定义任务执行函数（模拟爬取）
    def mock_crawler(task_data):
        """模拟爬取任务执行"""
        import time
        if task_data and "url" in task_data:
            time.sleep(0.5)  # 模拟网络延迟
            print(f"  🕷️  正在爬取: {task_data['url']}")
            return {"status": "success", "content_length": 1024}
        return {"status": "skipped"}
    
    # 执行BFS调度
    results = scheduler.execute_bfs(tree, executor=mock_crawler)
    
    # 输出结果
    print(f"\n总计执行了 {len(results)} 个叶子任务\n")
    
    # 演示2: 多线程并行BFS调度
    print("\n" + "="*80)
    print("演示2: 多线程并行BFS调度")
    print("="*80)
    
    tree2 = scheduler.build_sample_crawl_tree()
    results_parallel = scheduler.execute_bfs_parallel(tree2, executor=mock_crawler)
    
    print(f"\n总计执行了 {len(results_parallel)} 个叶子任务")
