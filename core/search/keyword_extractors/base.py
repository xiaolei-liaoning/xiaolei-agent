"""关键词提取器 - 共享数据结构和工具函数"""

import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set


@dataclass
class KeywordInfo:
    """关键词信息"""
    word: str              # 关键词
    score: float           # 重要性分数
    category: str          # 类别（动作/对象/地点/时间/人物/其他）
    position: int          # 在原文中的位置


@dataclass
class ExtractedEntities:
    """提取的实体"""
    persons: List[str] = field(default_factory=list)     # 人名
    locations: List[str] = field(default_factory=list)   # 地点
    times: List[str] = field(default_factory=list)       # 时间
    numbers: List[str] = field(default_factory=list)     # 数字
    organizations: List[str] = field(default_factory=list)  # 组织
    urls: List[str] = field(default_factory=list)        # URL链接
    emails: List[str] = field(default_factory=list)      # 邮箱


@dataclass
class ExtractionResult:
    """提取结果"""
    keywords: List[KeywordInfo]        # 关键词列表
    entities: ExtractedEntities        # 实体信息
    main_intent: str                   # 主要意图
    action_words: List[str]            # 动作词
    target_words: List[str]            # 目标词
    summary: str                       # 文本摘要
    confidence: float                  # 置信度


# ---------------------------------------------------------------------------
# 共享工具函数
# ---------------------------------------------------------------------------

def normalize_keyword(keyword: str) -> str:
    """规范化关键词

    Args:
        keyword: 原始关键词

    Returns:
        规范化后的关键词
    """
    if not keyword:
        return ""

    # 去除首尾空白
    keyword = keyword.strip()

    # 转换为小写（英文）
    keyword = keyword.lower()

    # 去除常见标点
    keyword = re.sub(r'[^\w一-鿿]', '', keyword)

    return keyword


def categorize_word(word: str,
                     action_words: Set[str],
                     target_words: Set[str]) -> str:
    """判断词语类别

    Args:
        word: 词语
        action_words: 动作词集合
        target_words: 目标词集合

    Returns:
        类别
    """
    if word in action_words:
        return "动作"
    elif word in target_words:
        return "对象"
    elif any(time_word in word for time_word in ['年', '月', '日', '点', '周']):
        return "时间"
    elif any(loc in word for loc in ['北京', '上海', '广州', '深圳']):
        return "地点"
    else:
        return "其他"


def diversify_keywords(keywords: List[KeywordInfo],
                       max_per_category: int = 3) -> List[KeywordInfo]:
    """多样化关键词选择，避免单一类别过多

    Args:
        keywords: 已排序的关键词列表
        max_per_category: 每个类别最多选择的数量

    Returns:
        多样化的关键词列表
    """
    category_count = {}
    result = []

    for kw in keywords:
        category = kw.category
        count = category_count.get(category, 0)

        if count < max_per_category:
            result.append(kw)
            category_count[category] = count + 1

            # 如果已经收集了足够的关键词，提前退出
            if len(result) >= 15:
                break

    return result


def post_process_keywords(keywords: List[KeywordInfo],
                           text: str,
                           stopwords: Set[str]) -> List[KeywordInfo]:
    """后处理关键词列表

    Args:
        keywords: 关键词列表
        text: 原文
        stopwords: 停用词集合

    Returns:
        处理后的关键词列表
    """
    if not keywords:
        return []

    # 1. 去除重复（基于规范化后的关键词）
    seen = set()
    unique_keywords = []
    for kw in keywords:
        normalized = normalize_keyword(kw.word)
        if normalized and normalized not in seen and len(normalized) >= 2:
            seen.add(normalized)
            unique_keywords.append(kw)

    # 2. 过滤低质量关键词
    filtered = []
    for kw in unique_keywords:
        # 长度检查
        if len(kw.word) < 2 or len(kw.word) > 20:
            continue

        # 分数检查（过滤极低分）
        if kw.score < 0.01:
            continue

        # 停用词二次检查
        if kw.word in stopwords:
            continue

        filtered.append(kw)

    # 3. 按分数重新排序
    filtered.sort(key=lambda x: x.score, reverse=True)

    # 4. 多样性检查（确保不同类别的关键词）
    diversified = diversify_keywords(filtered)

    return diversified


def detect_domain(text: str,
                   domain_dictionary: Dict[str, List[str]]) -> str:
    """检测文本所属领域

    Args:
        text: 文本
        domain_dictionary: 领域词典

    Returns:
        领域名称
    """
    domain_scores = {}

    # 计算每个领域的匹配度
    for domain, keywords in domain_dictionary.items():
        score = 0
        for keyword in keywords:
            if keyword in text:
                score += 1
        domain_scores[domain] = score

    # 找出得分最高的领域
    if domain_scores:
        best_domain = max(domain_scores, key=domain_scores.get)
        if domain_scores[best_domain] > 0:
            return best_domain

    return "general"


def adjust_extraction_strategy(domain: str) -> dict:
    """根据领域调整提取策略

    Args:
        domain: 领域名称

    Returns:
        调整后的参数
    """
    strategies = {
        "tech": {
            "min_word_length": 2,
            "top_k": 15,
            "weight_adjustment": 1.2  # 技术领域关键词权重调整
        },
        "finance": {
            "min_word_length": 2,
            "top_k": 12,
            "weight_adjustment": 1.1
        },
        "medical": {
            "min_word_length": 2,
            "top_k": 12,
            "weight_adjustment": 1.1
        },
        "entertainment": {
            "min_word_length": 2,
            "top_k": 15,
            "weight_adjustment": 1.0
        },
        "education": {
            "min_word_length": 2,
            "top_k": 12,
            "weight_adjustment": 1.0
        },
        "travel": {
            "min_word_length": 2,
            "top_k": 12,
            "weight_adjustment": 1.0
        },
        "shopping": {
            "min_word_length": 2,
            "top_k": 12,
            "weight_adjustment": 1.0
        },
        "weather": {
            "min_word_length": 2,
            "top_k": 10,
            "weight_adjustment": 1.1
        },
        "general": {
            "min_word_length": 2,
            "top_k": 12,
            "weight_adjustment": 1.0
        }
    }

    return strategies.get(domain, strategies["general"])
