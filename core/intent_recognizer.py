"""意图识别模块（增强版）

实现语义分析、上下文理解和多意图识别
"""

import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class IntentPattern:
    """意图模式定义"""
    intent: str
    patterns: List[str]
    weight: float = 1.0
    context_required: bool = False
    examples: List[str] = None  # 示例句子


class IntentRecognizer:
    """意图识别器（增强版）
    
    功能特性：
    1. 多意图识别：同时识别多个意图
    2. 语义分析：考虑词频、位置、上下文
    3. 上下文理解：支持对话历史
    4. 意图权重：不同意图有不同优先级
    """
    
    def __init__(self):
        # 意图模式定义（扩展到50+种，带权重和示例）
        self.intent_patterns = {
            # 应用控制类
            "open_app": IntentPattern(
                "open_app", 
                ["打开", "启动", "运行", "开启", "打开应用", "启动应用", "启动程序", "开"],
                weight=2.0,
                examples=["打开微信", "启动浏览器", "运行记事本", "打开APP"]
            ),
            "close_app": IntentPattern(
                "close_app", 
                ["关闭", "退出", "停止", "关掉", "关闭应用", "退出程序", "关掉", "关",
                 "停", "停应用", "退", "退出应用"],  # 新增短句关键词
                weight=1.8,  # 从1.5提升到1.8,与open_app对称
                examples=["关闭浏览器", "退出微信", "停止程序", "关应用"]
            ),
            
            # 网络访问类
            "open_url": IntentPattern(
                "open_url", 
                ["访问", "打开网页", "浏览", "进入", "打开链接", "访问网址", "打开网站", "进"],
                weight=1.8,
                examples=["访问百度", "打开 https://example.com", "打开谷歌"]
            ),
            
            # 搜索查询类
            "search": IntentPattern(
                "search", 
                ["搜索", "查找", "查询", "搜一下", "找一下", "检索", "搜索一下", "找", "搜"],
                weight=2.5,
                examples=["搜索天气", "查找资料", "搜索一下"]
            ),
            "search_web": IntentPattern(
                "search_web", 
                ["上网搜", "网上找", "上网查", "网上搜索", "网上搜索一下", "网络搜索"],
                weight=2.0,
                examples=["上网搜一下", "网上找资料"]
            ),
            
            # 问答类
            "question": IntentPattern(
                "question", 
                ["是什么", "为什么", "怎么样", "如何", "怎么", "怎样", "能否", "什么是", "为什么会", "如何做", "怎么做", "是什么意思", "为什么", "请问"],
                weight=2.0,
                examples=["什么是人工智能", "怎么用电脑"]
            ),
            "explain": IntentPattern(
                "explain", 
                ["解释一下", "说明", "讲解", "详细说明", "解释", "讲一下"],
                weight=1.8,
                examples=["解释一下这个概念", "说明一下"]
            ),
            
            # 交互类
            "greeting": IntentPattern(
                "greeting", 
                ["你好", "嗨", "哈喽", "hi", "hello", "嗨喽", "你好呀", "早上好", "下午好", "晚上好", "哈喽哈喽"],
                weight=1.0,
                examples=["你好", "早上好"]
            ),
            "thanks": IntentPattern(
                "thanks", 
                ["谢谢", "多谢", "thank", "thanks", "感谢", "谢谢啦", "非常感谢", "thank you", "3q", "谢谢谢谢"],
                weight=1.0,
                examples=["谢谢", "非常感谢"]
            ),
            "goodbye": IntentPattern(
                "goodbye", 
                ["再见", "拜拜", "bye", "再见啦", "下次见", "回见", "拜拜了"],
                weight=1.0,
                examples=["再见", "拜拜"]
            ),
            
            # 内容处理类
            "research": IntentPattern(
                "research", 
                ["研究", "了解", "学习", "探索", "调研", "了解一下", "学习一下", "深入研究"],
                weight=1.8,
                examples=["研究人工智能", "了解股票"]
            ),
            "compare": IntentPattern(
                "compare", 
                ["比较", "对比", "vs", "versus", "哪个好", "区别", "差异", "对比一下"],
                weight=1.5,
                examples=["比较A和B", "哪个手机好"]
            ),
            "analyze": IntentPattern(
                "analyze", 
                ["分析", "研究", "评估", "剖析", "分析一下", "分析分析"],
                weight=1.8,
                examples=["分析数据", "评估方案"]
            ),
            "summarize": IntentPattern(
                "summarize", 
                ["总结", "概括", "归纳", "整理", "简要说明", "总结一下", "概括一下"],
                weight=1.5,
                examples=["总结报告", "整理一下"]
            ),
            "extract": IntentPattern(
                "extract", 
                ["提取", "提炼", "摘要", "提取关键词", "摘要一下"],
                weight=1.5,
                examples=["提取关键词", "提炼要点"]
            ),
            
            # 帮助类
            "help": IntentPattern(
                "help", 
                ["帮助", "帮忙", "assistance", "help", "求助", "帮我一下", "有什么用", "功能"],
                weight=1.0,
                examples=["帮我一下", "需要帮助", "你能做什么"]
            ),
            "guide": IntentPattern(
                "guide", 
                ["怎么用", "如何使用", "操作指南", "使用说明", "教程"],
                weight=1.5,
                examples=["怎么使用这个功能", "给我一个教程"]
            ),
            
            # 生活服务类
            "weather": IntentPattern(
                "weather", 
                ["天气", "气温", "温度", "预报", "今天天气", "明天天气", "天气预报", "温度多少", "天气怎么样",
                 "天", "气", "天怎么样", "天气如何", "什么天气", "几度"],  # 新增短句和口语化表达
                weight=2.3,  # 从2.0提升到2.3,提高识别优先级
                examples=["今天天气怎么样", "明天天气", "天怎么样", "气温多少"]
            ),
            "time": IntentPattern(
                "time", 
                ["现在几点", "时间", "几点了", "现在时间", "日期", "今天几号"],
                weight=1.5,
                examples=["现在几点", "今天是几号"]
            ),
            "news": IntentPattern(
                "news", 
                ["新闻", "资讯", "最新消息", "热点新闻", "新闻资讯", "热点"],
                weight=1.8,
                examples=["看看新闻", "最新消息"]
            ),
            
            # 翻译计算类
            "translate": IntentPattern(
                "translate", 
                ["翻译", "translate", "译成", "翻译成", "翻译一下", "翻译翻译",
                 "译", "翻", "翻一下", "帮我翻译", "翻译下"],  # 新增短句和口语化表达
                weight=2.3,  # 从2.0提升到2.3
                examples=["翻译成中文", "翻译这个句子", "翻一下", "译成英文"]
            ),
            "calculate": IntentPattern(
                "calculate", 
                ["计算", "算一下", "求和", "求积", "等于多少", "算一下", "计算一下", "算一算"],
                weight=1.8,
                examples=["计算1+1等于多少", "算一下总价"]
            ),
            "convert": IntentPattern(
                "convert", 
                ["转换", "换算", "单位转换", "换算一下"],
                weight=1.5,
                examples=["转换单位", "换算一下"]
            ),
            
            # 日程提醒类
            "schedule": IntentPattern(
                "schedule", 
                ["日程", "安排", "计划", "提醒", "日程表", "安排一下", "日程安排", "提醒我"],
                weight=1.5,
                examples=["安排日程", "设置提醒"]
            ),
            "remind": IntentPattern(
                "remind", 
                ["提醒我", "别忘了", "记得", "提醒"],
                weight=1.8,
                examples=["提醒我明天开会", "别忘了"]
            ),
            "calendar": IntentPattern(
                "calendar", 
                ["日历", "日程表", "看日历", "日历上"],
                weight=1.2,
                examples=["看看日历", "查一下日历"]
            ),
            
            # 通讯类
            "send": IntentPattern(
                "send", 
                ["发送", "发送邮件", "发消息", "邮寄", "发一下", "发个消息"],
                weight=1.8,
                examples=["发送消息", "发邮件"]
            ),
            "call": IntentPattern(
                "call", 
                ["打电话", "通话", "拨打电话", "呼叫"],
                weight=1.8,
                examples=["给我打电话", "拨打电话"]
            ),
            
            # 数据处理类
            "scrape": IntentPattern(
                "scrape", 
                ["爬取", "抓取", "采集", "获取数据", "爬一下", "抓一下"],
                weight=2.0,
                examples=["爬取数据", "采集信息"]
            ),
            "download": IntentPattern(
                "download", 
                ["下载", "保存", "下载文件", "下载一下"],
                weight=1.5,
                examples=["下载这个文件", "保存一下"]
            ),
            
            # 娱乐类
            "music": IntentPattern(
                "music", 
                ["播放音乐", "听歌", "放歌", "音乐", "播放歌曲", "播放歌", "听音乐", "放首歌"],
                weight=2.0,
                examples=["播放周杰伦的歌", "听歌"]
            ),
            "video": IntentPattern(
                "video", 
                ["看视频", "播放视频", "看电影", "看个视频"],
                weight=1.8,
                examples=["看个视频", "播放电影"]
            ),
            "game": IntentPattern(
                "game", 
                ["玩游戏", "打游戏", "游戏", "玩一把"],
                weight=1.5,
                examples=["玩游戏", "打游戏"]
            ),
            
            # 系统控制类
            "volume": IntentPattern(
                "volume", 
                ["音量", "调整音量", "增大音量", "减小音量", "调高音量", "调低音量", "声音大一点", "声音小一点"],
                weight=2.0,
                examples=["音量提高60%", "调大音量"]
            ),
            "screenshot": IntentPattern(
                "screenshot", 
                ["截图", "截屏", "截个图", "保存屏幕", "截图保存", "截一下"],
                weight=1.8,
                examples=["截图保存", "截个图"]
            ),
            "record": IntentPattern(
                "record", 
                ["录音", "录制", "录屏", "录一下"],
                weight=1.5,
                examples=["录音", "录屏"]
            ),
            
            # 文件操作类
            "file": IntentPattern(
                "file", 
                ["文件", "文档", "打开文件", "保存文件", "创建文档", "编辑文件", "查看文件"],
                weight=1.5,
                examples=["打开这个文件", "保存文档"]
            ),
            "edit": IntentPattern(
                "edit", 
                ["编辑", "修改", "改一下", "编辑一下"],
                weight=1.5,
                examples=["编辑这个文档", "修改一下"]
            ),
            
            # 文本分析类
            "text_analyze": IntentPattern(
                "text_analyze", 
                ["文本分析", "分析文本", "分析一下文本", "文本处理"],
                weight=1.8,
                examples=["文本分析一下", "分析这段文本"]
            ),
            "keyword": IntentPattern(
                "keyword", 
                ["关键词", "提取关键词", "关键词提取"],
                weight=1.5,
                examples=["提取关键词", "找出关键词"]
            ),
            
            # 其他
            "chat": IntentPattern(
                "chat", 
                ["聊天", "说说话", "聊聊", "随便聊", "聊天吧", "闲聊", "说说话"],
                weight=0.8,
                examples=["随便聊聊", "聊天吧"]
            ),
            "unknown": IntentPattern(
                "unknown", 
                ["...", "嗯", "哦", "啊", "呃", "那个"],
                weight=0.5,
                examples=["...", "嗯"]
            ),
            
            # 新增：系统操作
            "system": IntentPattern(
                "system", 
                ["设置", "系统设置", "配置", "调整设置"],
                weight=1.2,
                examples=["打开设置", "系统设置"]
            ),
            "backup": IntentPattern(
                "backup", 
                ["备份", "保存数据", "数据备份"],
                weight=1.5,
                examples=["备份一下", "保存数据"]
            ),
            "restore": IntentPattern(
                "restore", 
                ["恢复", "还原", "恢复数据"],
                weight=1.5,
                examples=["恢复数据", "还原一下"]
            ),
            
            # 新增：学习类
            "learn": IntentPattern(
                "learn", 
                ["学习", "学一下", "学习一下", "学习学习"],
                weight=1.5,
                examples=["学习这个", "学一下"]
            ),
            "teach": IntentPattern(
                "teach", 
                ["教我", "教学", "教教我", "教一下"],
                weight=1.5,
                examples=["教我怎么做", "教我一下"]
            ),
            
            # 新增：推荐类
            "recommend": IntentPattern(
                "recommend", 
                ["推荐", "介绍", "推荐一下", "给我推荐"],
                weight=1.5,
                examples=["推荐一下", "给我推荐"]
            ),
            "suggest": IntentPattern(
                "suggest", 
                ["建议", "提议", "给点建议"],
                weight=1.2,
                examples=["给点建议", "建议一下"]
            ),
            
            # 新增：信息类
            "info": IntentPattern(
                "info", 
                ["信息", "详情", "详细信息", "查一下"],
                weight=1.5,
                examples=["查一下信息", "详细信息"]
            ),
            "check": IntentPattern(
                "check", 
                ["检查", "查看", "检查一下", "查一下"],
                weight=1.5,
                examples=["检查一下", "查看一下"]
            ),
            
            # 新增：确认类
            "confirm": IntentPattern(
                "confirm", 
                ["确认", "确定", "确认一下", "确定一下"],
                weight=1.2,
                examples=["确认一下", "确定吗"]
            ),
            "yes": IntentPattern(
                "yes", 
                ["好的", "可以", "行", "没问题", "好", "对", "嗯"],
                weight=0.8,
                examples=["好的", "可以"]
            ),
            "no": IntentPattern(
                "no", 
                ["不", "不行", "不要", "不好", "不对", "不是"],
                weight=0.8,
                examples=["不行", "不要"]
            ),
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
        
        # 同义词映射（用于模糊匹配）
        self.synonyms = {
            "打开": ["开启", "启动", "运行", "开", "启", "打开应用", "启动应用"],
            "关闭": ["关掉", "停止", "退出", "关", "停", "退", "关闭应用", "退出应用"],
            "搜索": ["查找", "查询", "检索", "找", "搜", "查", "搜索一下", "查一下", "搜一下"],
            "翻译": ["译", "翻", "翻译一下", "帮我翻译", "翻一下"],
            "天气": ["气温", "温度", "天", "气", "预报", "天怎么样"],
            "聊天": ["说说话", "聊聊", "随便聊", "聊聊天", "闲聊"],
            "播放": ["放", "播放", "听", "播放音乐"],
            "查看": ["看一下", "检查", "查看一下", "看看"],
            "帮助": ["帮忙", "协助", "帮一下", "帮个忙", "求助"],
            "了解": ["知道", "明白", "学习"],
            "分析": ["研究", "评估", "剖析"],
            "总结": ["概括", "归纳", "整理"],
            "什么": ["啥", "什么意思"],  # 口语化问答
            "怎么": ["咋", "咋样"],  # 口语化询问
        }
        
        # 否定词（用于排除误匹配）
        self.negations = ["不", "不要", "不用", "别", "不要了", "算了"]
        
        # 常见输入前缀
        self.prefixes = ["帮我", "请帮我", "麻烦帮我", "我想", "我要", "能不能", "能否", "可以"]
    
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
            if confidence >= 0.08:  # 降低最小置信度阈值，提高召回率
                intents.append({
                    "intent": intent_name,
                    "confidence": confidence,
                    "matched_patterns": self._get_matched_patterns(message, pattern_def)
                })
        
        # 按置信度排序
        intents.sort(key=lambda x: x["confidence"], reverse=True)
        
        # 获取主意图
        if intents:
            primary_intent = intents[0]
        else:
            # 没有匹配时，默认返回chat意图，但降低置信度
            primary_intent = {"intent": "chat", "confidence": 0.35}
        
        # 获取高置信度的多意图（置信度>=0.25，降低阈值提高多意图识别）
        multi_intents = [i for i in intents if i["confidence"] >= 0.25]
        
        logger.info(f"识别结果 - 主意图: {primary_intent['intent']} (置信度: {primary_intent['confidence']:.2f}), 多意图数量: {len(multi_intents)}")
        
        return {
            "primary_intent": primary_intent["intent"],
            "confidence": primary_intent["confidence"],
            "multi_intents": multi_intents,
            "context_score": self._calculate_context_score(message),
            "history_count": len(self.conversation_history),
            "needs_clarification": primary_intent["confidence"] < 0.25  # 降低澄清阈值
        }
    
    def _calculate_confidence(self, message: str, pattern_def: IntentPattern) -> float:
        """计算置信度（增强版）
        
        考虑因素：
        1. 模式匹配数量
        2. 模式在消息中的位置
        3. 意图权重
        4. 上下文关键词
        5. 同义词匹配
        6. 否定词排除
        7. 前缀清理
        
        Args:
            message: 用户消息
            pattern_def: 意图模式定义
            
        Returns:
            置信度分数 (0-1)
        """
        if not message:
            return 0.0
        
        # 0. 先检查否定词
        has_negation = any(neg in message for neg in self.negations)
        negation_penalty = 0.5 if has_negation else 1.0
        
        # 0.5 清理常见前缀，提高匹配准确率
        cleaned_message = message
        for prefix in self.prefixes:
            if cleaned_message.startswith(prefix):
                cleaned_message = cleaned_message[len(prefix):].strip()
        
        # 1. 计算精确匹配分数（使用清理后的消息）
        matched_count = 0
        first_position = len(cleaned_message)
        
        for pattern in pattern_def.patterns:
            if pattern in cleaned_message:
                matched_count += 1
                pos = cleaned_message.index(pattern)
                if pos < first_position:
                    first_position = pos
        
        # 2. 计算同义词匹配分数（模糊匹配，支持双向）
        synonym_score = 0.0
        for word, syn_list in self.synonyms.items():
            # 消息中的词匹配模式中的同义词
            if word in cleaned_message:
                for syn in syn_list:
                    if syn in pattern_def.patterns:
                        synonym_score += 0.3
                        break
            # 消息中的同义词匹配模式中的词
            for syn in syn_list:
                if syn in cleaned_message:
                    if word in pattern_def.patterns:
                        synonym_score += 0.2
                        break
        
        # 如果没有匹配，返回0
        if matched_count == 0 and synonym_score < 0.2:
            return 0.0
        
        # 3. 计算位置分数（越靠前置信度越高）
        position_score = 1.0 - (first_position / len(cleaned_message)) if matched_count > 0 else 0.5
        
        # 4. 计算匹配密度分数（匹配模式占总模式的比例）
        total_patterns = len(pattern_def.patterns)
        density_score = min(matched_count / max(total_patterns, 1), 1.0)
        
        # 5. 计算上下文增强分数
        context_score = self._calculate_context_score(message)
        
        # 6. 组合所有分数（优化权重）
        base_score = (
            (0.45 * density_score) +    # 提高匹配密度权重
            (0.25 * position_score) +   # 位置权重
            (0.20 * synonym_score) +    # 同义词权重
            (0.10 * context_score)      # 上下文权重
        )
        
        # 7. 应用意图权重和否定惩罚
        weighted_score = base_score * pattern_def.weight * negation_penalty
        
        # 8. 归一化到0-1范围
        confidence = min(weighted_score, 1.0)
        
        return confidence
    
    def _calculate_context_score(self, message: str) -> float:
        """计算上下文分数
        
        检查消息中是否有上下文关键词
        
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
        """
        if not message or not pattern_def.patterns:
            return []
        
        matched = []
        for pattern in pattern_def.patterns:
            if pattern in message:
                matched.append(pattern)
        
        return matched
