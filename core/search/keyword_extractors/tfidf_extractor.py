"""TF-IDF关键词提取器 - 基于jieba分词和TF-IDF算法"""

import logging
import re
from collections import Counter
from typing import List, Optional, Set

from .base import KeywordInfo, normalize_keyword, categorize_word

logger = logging.getLogger(__name__)


class TfidfExtractor:
    """基于jieba分词和TF-IDF的关键词提取器"""

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
        """基于jieba分词和TF-IDF提取关键词（优化版）

        Args:
            text: 文本

        Returns:
            关键词列表
        """
        try:
            import jieba.analyse

            # 使用jieba的TF-IDF提取
            # allowPOS: 只保留名词、动词、形容词等有意义的词性
            keywords_with_weights = jieba.analyse.extract_tags(
                text,
                topK=30,
                withWeight=True,
                allowPOS=('n', 'nr', 'ns', 'nt', 'nz', 'v', 'a')  # 名词、人名、地名、机构名、动词、形容词
            )

            keywords = []
            for word, weight in keywords_with_weights:
                # 过滤停用词
                if word in self.stopwords or len(word) < 2:
                    continue

                # 计算位置权重
                position = text.find(word)
                position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5

                # 综合分数
                score = weight * position_weight

                # 判断类别
                category = categorize_word(word, self.action_words, self.target_words)

                keywords.append(KeywordInfo(
                    word=word,
                    score=score,
                    category=category,
                    position=position
                ))

            return keywords

        except ImportError:
            logger.warning("jieba.analyse未安装，使用基础方法")
            return self._extract_by_frequency(text)
        except Exception as e:
            logger.error("jieba TF-IDF提取失败: %s", e)
            return self._extract_by_frequency(text)

    def _extract_by_frequency(self, text: str) -> List[KeywordInfo]:
        """基于词频提取关键词（优化版 - 使用jieba分词）

        Args:
            text: 文本

        Returns:
            关键词列表
        """
        try:
            import jieba
        except ImportError:
            logger.warning("jieba未安装，使用简单分词")
            return self._extract_by_frequency_simple(text)

        # 使用jieba精准模式分词
        words = jieba.lcut(text)

        # 过滤停用词和短词
        filtered_words = [w for w in words if w not in self.stopwords and len(w) >= 2]

        if not filtered_words:
            return []

        # 计算词频
        word_freq = Counter(filtered_words)

        # 转换为KeywordInfo
        keywords = []
        for word, freq in word_freq.most_common(30):
            # 计算位置权重（越靠前越重要）
            position = text.find(word)
            position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5

            # 综合分数
            score = freq * position_weight

            # 判断类别
            category = categorize_word(word, self.action_words, self.target_words)

            keywords.append(KeywordInfo(
                word=word,
                score=score,
                category=category,
                position=position
            ))

        return keywords

    def _extract_by_frequency_simple(self, text: str) -> List[KeywordInfo]:
        """基于简单分词的词频提取（降级方案）

        Args:
            text: 文本

        Returns:
            关键词列表
        """
        # 简单分词（按字符和常见分隔符）
        words = re.findall(r'[一-鿿]{2,4}|[a-zA-Z]{3,}', text)

        # 过滤停用词
        filtered_words = [w for w in words if w not in self.stopwords and len(w) >= 2]

        if not filtered_words:
            return []

        # 计算词频
        word_freq = Counter(filtered_words)

        # 转换为KeywordInfo
        keywords = []
        for word, freq in word_freq.most_common(30):
            # 计算位置权重（越靠前越重要）
            position = text.find(word)
            position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5

            # 综合分数
            score = freq * position_weight

            # 判断类别
            category = categorize_word(word, self.action_words, self.target_words)

            keywords.append(KeywordInfo(
                word=word,
                score=score,
                category=category,
                position=position
            ))

        return keywords
