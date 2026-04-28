"""意图识别模块（增强版）

实现语义分析、上下文理解和多意图识别
"""

import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class IntentPattern:
    """意图模式定义"""
    
    def __init__(self, intent: str, patterns: List[str], weight: float = 1.0, context_required: bool = False):
        self.intent = intent
        self.patterns = patterns
        self.weight = weight  # 意图权重
        self.context_required = context_required  # 是否需要上下文


class IntentRecognizer:
    """意图识别器（增强版）
    
    功能特性：
    1. 多意图识别：同时识别多个意图
    2. 语义分析：考虑词频、位置、上下文
    3. 上下文理解：支持对话历史
    4. 意图权重：不同意图有不同优先级
    """
    
    def __init__(self):
        # 意图模式定义（带权重）
        self.intent_patterns = {
            "open_app": IntentPattern("open_app", ["打开", "启动", "运行", "开启"], weight=2.0),
            "close_app": IntentPattern("close_app", ["关闭", "退出", "停止", "关掉"], weight=1.5),
            "open_url": IntentPattern("open_url", ["访问", "打开网页", "浏览", "进入"], weight=1.8),
            "search": IntentPattern("search", ["搜索", "查找", "查询", "搜一下"], weight=2.5),
            "question": IntentPattern("question", ["是什么", "为什么", "怎么样", "如何", "怎么", "怎样", "能否"], weight=2.0),
            "greeting": IntentPattern("greeting", ["你好", "嗨", "哈喽", "hi", "hello", "嗨喽", "你好呀"], weight=1.0),
            "thanks": IntentPattern("thanks", ["谢谢", "多谢", "thank", "thanks", "感谢"], weight=1.0),
            "goodbye": IntentPattern("goodbye", ["再见", "拜拜", "bye", "再见啦"], weight=1.0),
            "research": IntentPattern("research", ["研究", "了解", "学习", "探索", "调研"], weight=1.8),
            "compare": IntentPattern("compare", ["比较", "对比", "vs", " versus ", "哪个好"], weight=1.5),
            "analyze": IntentPattern("analyze", ["分析", "研究", "评估", "剖析"], weight=1.8),
            "summarize": IntentPattern("summarize", ["总结", "概括", "归纳", "整理"], weight=1.5),
            "help": IntentPattern("help", ["帮助", "帮忙", " assistance ", "help", "求助"], weight=1.0),
            "weather": IntentPattern("weather", ["天气", "气温", "温度", "预报"], weight=2.0),
            "translate": IntentPattern("translate", ["翻译", "translate", "译成"], weight=2.0),
            "calculate": IntentPattern("calculate", ["计算", "算一下", "求和", "求积"], weight=1.8),
            "schedule": IntentPattern("schedule", ["日程", "安排", "计划", "提醒"], weight=1.5),
            "send": IntentPattern("send", ["发送", "发送邮件", "发消息", "邮寄"], weight=1.8),
            "scrape": IntentPattern("scrape", ["爬取", "抓取", "采集", "获取数据"], weight=2.0),
        }
        
        # 上下文关键词（增强置信度）
        self.context_keywords = {
            "polite": ["请", "帮我", "麻烦", "能否", "可以"],
            "urgent": ["紧急", "快点", "马上", "立即"],
            "confirm": ["确认", "是否", "对吗", "是吗"],
        }
        
        # 对话历史（用于上下文理解）
        self.conversation_history = []
        self.max_history_length = 10
    
    def recognize(self, message: str, context: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """识别意图（支持多意图和上下文）
        
        Args:
            message: 用户消息
            context: 上下文（可选，包含对话历史）
            
        Returns:
            包含主意图、置信度和多意图列表的字典
        """
        # 更新对话历史
        if context:
            self.conversation_history.extend(context)
        self.conversation_history.append({"user": message, "timestamp": __import__("time").time()})
        
        # 保持历史长度
        if len(self.conversation_history) > self.max_history_length:
            self.conversation_history = self.conversation_history[-self.max_history_length:]
        
        intents = []
        
        for intent_name, pattern_def in self.intent_patterns.items():
            confidence = self._calculate_confidence(message, pattern_def)
            if confidence >= 0.1:  # 最小置信度阈值
                intents.append({
                    "intent": intent_name,
                    "confidence": confidence,
                    "matched_patterns": self._get_matched_patterns(message, pattern_def)
                })
        
        # 按置信度排序
        intents.sort(key=lambda x: x["confidence"], reverse=True)
        
        # 获取主意图
        primary_intent = intents[0] if intents else {"intent": "chat", "confidence": 0.5}
        
        # 获取高置信度的多意图（置信度>=0.3）
        multi_intents = [i for i in intents if i["confidence"] >= 0.3]
        
        logger.info(f"识别结果 - 主意图: {primary_intent['intent']} (置信度: {primary_intent['confidence']:.2f}), 多意图数量: {len(multi_intents)}")
        
        return {
            "primary_intent": primary_intent["intent"],
            "confidence": primary_intent["confidence"],
            "multi_intents": multi_intents,
            "context_score": self._calculate_context_score(message),
            "history_count": len(self.conversation_history)
        }
    
    def _calculate_confidence(self, message: str, pattern_def: IntentPattern) -> float:
        """计算置信度（增强版）
        
        考虑因素：
        1. 模式匹配数量
        2. 模式在消息中的位置
        3. 意图权重
        4. 上下文关键词
        
        Args:
            message: 用户消息
            pattern_def: 意图模式定义
            
        Returns:
            置信度分数 (0-1)
        """
        if not message:
            return 0.0
        
        # 1. 计算模式匹配分数
        matched_count = 0
        first_position = len(message)  # 首次匹配位置
        
        for pattern in pattern_def.patterns:
            if pattern in message:
                matched_count += 1
                pos = message.index(pattern)
                if pos < first_position:
                    first_position = pos
        
        if matched_count == 0:
            return 0.0
        
        # 2. 计算位置分数（越靠前置信度越高）
        position_score = 1.0 - (first_position / len(message))
        
        # 3. 计算匹配密度分数
        density_score = min(matched_count / len(pattern_def.patterns), 1.0)
        
        # 4. 计算上下文分数
        context_score = self._calculate_context_score(message)
        
        # 5. 综合计算（考虑意图权重）
        base_score = (position_score * 0.4 + density_score * 0.3 + context_score * 0.3)
        final_score = base_score * pattern_def.weight * 0.5
        
        return min(1.0, max(0.0, final_score))
    
    def _calculate_context_score(self, message: str) -> float:
        """计算上下文分数
        
        礼貌用语、紧急程度等会影响置信度
        
        Args:
            message: 用户消息
            
        Returns:
            上下文分数 (0-1)
        """
        score = 0.5  # 基础分
        
        # 礼貌用语加分
        for kw in self.context_keywords["polite"]:
            if kw in message:
                score += 0.1
                break
        
        # 紧急用语加分（表示用户有明确需求）
        for kw in self.context_keywords["urgent"]:
            if kw in message:
                score += 0.15
                break
        
        # 确认用语（表示用户在验证信息）
        for kw in self.context_keywords["confirm"]:
            if kw in message:
                score += 0.05
                break
        
        return min(1.0, max(0.5, score))
    
    def _get_matched_patterns(self, message: str, pattern_def: IntentPattern) -> List[str]:
        """获取匹配的模式列表
        
        Args:
            message: 用户消息
            pattern_def: 意图模式定义
            
        Returns:
            匹配的模式列表
        """
        return [pattern for pattern in pattern_def.patterns if pattern in message]
    
    def get_intent_info(self, intent: str) -> Optional[IntentPattern]:
        """获取意图信息
        
        Args:
            intent: 意图名称
            
        Returns:
            意图模式定义，如果不存在返回None
        """
        return self.intent_patterns.get(intent)
    
    def clear_history(self):
        """清空对话历史"""
        self.conversation_history = []
        logger.info("对话历史已清空")
    
    def get_history_summary(self) -> Dict[str, Any]:
        """获取对话历史摘要
        
        Returns:
            对话历史摘要
        """
        return {
            "history_length": len(self.conversation_history),
            "recent_messages": [h.get("user", "")[:20] + "..." if len(h.get("user", "")) > 20 else h.get("user", "") 
                               for h in self.conversation_history[-3:]]
        }


# 意图-技能映射表
INTENT_SKILL_MAPPING = {
    "open_app": ["gui_automation"],
    "close_app": ["gui_automation"],
    "open_url": ["gui_automation", "search_engine"],
    "search": ["search_engine", "web_scraper"],
    "question": ["deep_thinking", "search_engine"],
    "greeting": ["doubao_chat"],
    "thanks": ["doubao_chat"],
    "goodbye": ["doubao_chat"],
    "research": ["search_engine", "web_scraper", "summarizer", "data_analysis"],
    "compare": ["search_engine", "data_analysis", "summarizer"],
    "analyze": ["data_analysis", "deep_thinking"],
    "summarize": ["summarizer"],
    "help": ["doubao_chat", "system_toolbox"],
    "weather": ["weather"],
    "translate": ["translator"],
    "calculate": ["system_toolbox"],
    "schedule": ["gui_automation", "system_toolbox"],
    "send": ["gui_automation"],
    "scrape": ["web_scraper"],
    "chat": ["doubao_chat", "libai"]
}


def get_skills_for_intent(intent: str) -> List[str]:
    """根据意图获取推荐的技能列表
    
    Args:
        intent: 意图名称
        
    Returns:
        技能名称列表
    """
    return INTENT_SKILL_MAPPING.get(intent, ["doubao_chat"])


def get_intent_category(intent: str) -> str:
    """获取意图分类
    
    Args:
        intent: 意图名称
        
    Returns:
        分类名称
    """
    intent_categories = {
        "open_app": "应用操作",
        "close_app": "应用操作",
        "open_url": "网页操作",
        "search": "信息获取",
        "question": "信息获取",
        "research": "信息获取",
        "weather": "信息获取",
        "translate": "工具操作",
        "calculate": "工具操作",
        "schedule": "工具操作",
        "send": "工具操作",
        "scrape": "数据操作",
        "analyze": "数据操作",
        "compare": "数据操作",
        "summarize": "内容处理",
        "greeting": "对话交互",
        "thanks": "对话交互",
        "goodbye": "对话交互",
        "help": "对话交互",
        "chat": "对话交互"
    }
    return intent_categories.get(intent, "其他")