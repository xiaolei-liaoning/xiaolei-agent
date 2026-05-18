"""
text_analyzer - 文本分析技能处理器

描述: 分析文本的字符数、词数、句子数，并提取关键词
"""

import logging
import re
from typing import Any, Dict, List
from collections import Counter

logger = logging.getLogger(__name__)


class TextAnalyzerHandler:
    """文本分析技能处理器"""
    
    def __init__(self):
        """初始化技能"""
        self.stop_words = {
            "的", "了", "在", "是", "我", "有", "和", "就",
            "不", "人", "都", "一", "一个", "上", "也", "很",
            "到", "说", "要", "去", "你", "会", "着", "没有",
            "看", "好", "自己", "这", "那", "这个", "那个",
            "the", "a", "an", "is", "are", "was", "were",
            "of", "in", "on", "at", "to", "for", "and"
        }
    
    def count_characters(self, text: str) -> int:
        """统计字符数（不含空格）"""
        return len(text.replace(" ", ""))
    
    def count_words(self, text: str) -> int:
        """统计词数"""
        # 简单分词（中、英文混排处理
        chinese_chars = re.findall(r'[\u4e00-\u9fa5]', text)
        english_words = re.findall(r'[a-zA-Z]+', text)
        return len(chinese_chars) + len(english_words)
    
    def count_sentences(self, text: str) -> int:
        """统计句子数"""
        sentences = re.split(r'[。！？.!?]', text)
        sentences = [s for s in sentences if s.strip()]
        return len(sentences)
    
    def extract_keywords(self, text: str, top_n: int = 5) -> List[str]:
        """提取关键词"""
        # 提取中文词语
        chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        english_words = re.findall(r'[a-zA-Z]{3,}', text)
        
        all_words = chinese_words + english_words
        
        # 过滤停用词
        filtered_words = [word for word in all_words if word.lower() not in self.stop_words]
        
        # 统计词频
        word_counts = Counter(filtered_words)
        
        # 返回Top N关键词
        keywords = [word for word, count in word_counts.most_common(top_n)]
        return keywords
    
    async def execute(self, **params) -> Dict[str, Any]:
        """
        执行技能
        
        Args:
            **params: 技能参数，必须包含 text
        
        Returns:
            dict: 执行结果，包含 success, result/error 等字段
        """
        try:
            text = params.get("text", "")
            
            if not text:
                return {
                    "success": False,
                    "error": "请提供要分析的文本"
                }
            
            logger.info(f"Executing text_analyzer, text length: {len(text)}")
            
            char_count = self.count_characters(text)
            word_count = self.count_words(text)
            sentence_count = self.count_sentences(text)
            keywords = self.extract_keywords(text)
            
            result = {
                "success": True,
                "result": "文本分析完成",
                "data": {
                    "char_count": char_count,
                    "word_count": word_count,
                    "sentence_count": sentence_count,
                    "keywords": keywords,
                    "text_length": len(text),
                    "text_preview": text[:100] + "..." if len(text) > 100 else text
                }
            }
            
            logger.info(f"Text analysis result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Skill execution failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# 导出技能实例
handler = TextAnalyzerHandler()
