"""TextRank关键词提取器 - 基于图模型的关键词提取算法"""

import logging
from typing import List, Optional, Set

from .base import KeywordInfo, categorize_word

logger = logging.getLogger(__name__)


class TextrankExtractor:
    """基于TextRank算法的关键词提取器"""

    def __init__(self,
                 stopwords: Optional[Set[str]] = None,
                 action_words: Optional[Set[str]] = None,
                 target_words: Optional[Set[str]] = None):
        """
        Args:
            stopwords: 停用词集合
            action_words: 动作词集合
            target_words: 目标词集合
        """
        self.stopwords = stopwords or set()
        self.action_words = action_words or set()
        self.target_words = target_words or set()

    def extract(self, text: str) -> List[KeywordInfo]:
        """基于TextRank算法提取关键词（优化版 - 使用jieba分词）

        Args:
            text: 文本

        Returns:
            关键词列表
        """
        try:
            import networkx as nx
            import jieba
        except ImportError as e:
            logger.warning("依赖未安装，跳过TextRank提取: %s", e)
            return []

        # 使用jieba精准模式分词
        words = jieba.lcut(text)

        # 过滤停用词和短词，只保留有意义的词性
        filtered_words = [
            w for w in words
            if w not in self.stopwords
            and len(w) >= 2
            and not w.isdigit()  # 排除纯数字
        ]

        if not filtered_words:
            return []

        # 构建共现图
        window_size = 5
        graph = nx.Graph()

        for i in range(len(filtered_words)):
            word = filtered_words[i]
            if word not in graph:
                graph.add_node(word, weight=0)

            # 添加共现边
            for j in range(i + 1, min(i + window_size, len(filtered_words))):
                neighbor = filtered_words[j]
                if word != neighbor:  # 避免自环
                    if graph.has_edge(word, neighbor):
                        graph[word][neighbor]['weight'] += 1
                    else:
                        graph.add_edge(word, neighbor, weight=1)

        # 计算TextRank
        try:
            scores = nx.pagerank(graph, weight='weight', alpha=0.85, max_iter=100)
        except Exception as e:
            logger.error("TextRank计算失败: %s", e)
            return []

        # 转换为KeywordInfo
        keywords = []
        for word, score in scores.items():
            category = categorize_word(word, self.action_words, self.target_words)
            position = text.find(word)

            # 位置权重
            position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5

            # 综合分数
            final_score = score * position_weight

            keywords.append(KeywordInfo(
                word=word,
                score=final_score,
                category=category,
                position=position
            ))

        # 按分数排序
        keywords.sort(key=lambda x: x.score, reverse=True)

        return keywords[:20]
