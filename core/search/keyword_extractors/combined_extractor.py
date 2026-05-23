"""组合关键词提取器 - 结合TF-IDF和TextRank算法"""

import logging
from typing import List, Optional, Set

from .base import KeywordInfo, normalize_keyword, categorize_word
from .tfidf_extractor import TfidfExtractor
from .textrank_extractor import TextrankExtractor

logger = logging.getLogger(__name__)


class CombinedExtractor:
    """结合TF-IDF和TextRank算法的关键词提取器

    综合两种算法的优势，提高关键词提取的准确性
    """

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
        """结合TF-IDF和TextRank算法提取关键词

        Args:
            text: 文本

        Returns:
            关键词列表
        """
        # 创建独立的提取器实例
        tfidf_extractor = TfidfExtractor(
            stopwords=self.stopwords,
            action_words=self.action_words,
            target_words=self.target_words
        )
        textrank_extractor = TextrankExtractor(
            stopwords=self.stopwords,
            action_words=self.action_words,
            target_words=self.target_words
        )

        # 获取TF-IDF关键词
        tfidf_keywords = tfidf_extractor.extract(text)

        # 获取TextRank关键词
        textrank_keywords = textrank_extractor.extract(text)

        # 合并结果
        combined_keywords = {}

        # 权重分配
        for kw in tfidf_keywords:
            key = normalize_keyword(kw.word)
            if key:
                combined_keywords[key] = kw.score * 0.4

        for kw in textrank_keywords:
            key = normalize_keyword(kw.word)
            if key:
                if key in combined_keywords:
                    combined_keywords[key] += kw.score * 0.6
                else:
                    combined_keywords[key] = kw.score * 0.6

        # 转换为KeywordInfo
        result = []
        for word, score in combined_keywords.items():
            category = categorize_word(word, self.action_words, self.target_words)
            position = text.find(word)
            result.append(KeywordInfo(
                word=word,
                score=score,
                category=category,
                position=position
            ))

        # 排序
        result.sort(key=lambda x: x.score, reverse=True)
        return result[:15]
