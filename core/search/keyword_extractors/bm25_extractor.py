"""BM25关键词提取器 - 基于BM25算法的关键词提取"""

import logging
import math
from collections import Counter
from typing import List, Optional, Set

from .base import KeywordInfo, categorize_word

logger = logging.getLogger(__name__)


class Bm25Extractor:
    """基于BM25算法的关键词提取器"""

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

    def extract(self, text: str,
                k1: float = 1.5,
                b: float = 0.75) -> List[KeywordInfo]:
        """基于BM25算法提取关键词

        BM25比TF-IDF更适合短文本搜索，考虑了文档长度归一化

        Args:
            text: 文本
            k1: BM25参数，控制词频饱和点（默认1.5）
            b: BM25参数，控制长度归一化（默认0.75）

        Returns:
            关键词列表
        """
        try:
            import jieba
        except ImportError:
            logger.warning("jieba未安装，跳过BM25提取")
            return []

        # 分词
        words = jieba.lcut(text)

        # 过滤停用词和短词
        filtered_words = [w for w in words if w not in self.stopwords and len(w) >= 2]

        if not filtered_words:
            return []

        # 计算词频
        word_freq = Counter(filtered_words)

        # 文档长度（词数）
        doc_length = len(filtered_words)

        # 平均文档长度（这里简化为当前文档长度）
        avg_doc_length = doc_length

        # 计算BM25分数
        keywords = []
        for word, freq in word_freq.items():
            # BM25公式简化版（单文档场景）
            # BM25 = IDF * (TF * (k1 + 1)) / (TF + k1 * (1 - b + b * doc_len/avg_doc_len))

            # 简化IDF：假设所有词都在语料库中出现过
            idf = math.log((1 + len(word_freq)) / (1 + freq)) + 1

            # TF部分
            tf_numerator = freq * (k1 + 1)
            tf_denominator = freq + k1 * (1 - b + b * (doc_length / avg_doc_length))
            tf_score = tf_numerator / tf_denominator

            # BM25分数
            bm25_score = idf * tf_score

            # 位置权重
            position = text.find(word)
            position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5

            # 综合分数
            score = bm25_score * position_weight

            # 判断类别
            category = categorize_word(word, self.action_words, self.target_words)

            keywords.append(KeywordInfo(
                word=word,
                score=score,
                category=category,
                position=position
            ))

        # 按分数排序
        keywords.sort(key=lambda x: x.score, reverse=True)

        return keywords[:20]
