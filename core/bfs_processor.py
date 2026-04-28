"""BFS文本处理器 - 全局公共底层工具

提供文本的广度优先搜索处理能力，支持：
- 文本BFS遍历（按段落、句子层级）
- 内容树构建与处理
- 上下文队列管理
- 可复用的文本分析基础功能
"""

import logging
from collections import deque
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
                          summarizer: Optional[Callable] = None) -> TextNode:
        """构建双节点内容树（左节点=原文，右节点=摘要）
        
        Args:
            paragraphs: 段落列表
            summarizer: 摘要函数，签名为 func(text: str) -> str
            
        Returns:
            根节点
        """
        if not paragraphs:
            raise ValueError("段落列表不能为空")
        
        # 创建根节点
        root = TextNode(
            content="文档根节点",
            level=0,
            node_type="root"
        )
        
        # 为每个段落创建双节点结构
        for idx, paragraph in enumerate(paragraphs):
            # 左节点：原文
            original_node = TextNode(
                content=paragraph,
                level=1,
                node_type="paragraph",
                parent=root,
                metadata={"index": idx, "type": "original"}
            )
            
            # 右节点：摘要（如果提供了摘要函数）
            if summarizer:
                try:
                    summary = summarizer(paragraph)
                    summary_node = TextNode(
                        content=summary,
                        level=1,
                        node_type="summary",
                        parent=root,
                        metadata={"index": idx, "type": "summary"}
                    )
                    original_node.children.append(summary_node)
                except Exception as e:
                    logger.warning("生成摘要失败 (段落%d): %s", idx, e)
            
            root.children.append(original_node)
        
        logger.info("内容树构建完成，共 %d 个段落节点", len(root.children))
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


# 全局单例实例
_bfs_processor_instance = None


def get_bfs_processor(max_depth: int = 5, max_nodes: int = 100) -> BFSTextProcessor:
    """获取BFS文本处理器单例
    
    Args:
        max_depth: 最大遍历深度
        max_nodes: 最大节点数量
        
    Returns:
        BFSTextProcessor实例
    """
    global _bfs_processor_instance
    if _bfs_processor_instance is None:
        _bfs_processor_instance = BFSTextProcessor(max_depth=max_depth, max_nodes=max_nodes)
    return _bfs_processor_instance