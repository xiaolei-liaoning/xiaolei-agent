"""
LLM辅助意图理解系统 - 提升用户输入指令的解析精度

功能：
1. 解析用户原始输入
2. 提取关键实体和意图
3. 识别任务类型和约束
4. 生成结构化的任务定义
5. 为任务分解提供基础
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """意图类型"""
    QUERY = "query"                     # 查询
    ACTION = "action"                   # 执行动作
    CREATION = "creation"               # 创建内容
    ANALYSIS = "analysis"              # 分析
    MODIFICATION = "modification"       # 修改
    DELETION = "deletion"              # 删除
    COMPARISON = "comparison"           # 比较
    SUMMARY = "summary"                # 总结
    UNKNOWN = "unknown"                 # 未知


class TaskComplexity(Enum):
    """任务复杂度"""
    LOW = "low"        # 简单：单一步骤
    MEDIUM = "medium"  # 中等：2-5个步骤
    HIGH = "high"      # 复杂：5个以上步骤
    VERY_HIGH = "very_high"  # 非常复杂：需要多Agent协作


@dataclass
class ExtractedEntity:
    """提取的实体"""
    name: str
    type: str
    value: Any
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IntentConfidence:
    """意图置信度"""
    primary_intent: IntentType
    confidence: float
    alternative_intents: List[tuple] = field(default_factory=list)


@dataclass
class TaskConstraints:
    """任务约束"""
    time_constraint: Optional[str] = None    # 时间约束
    quality_requirements: List[str] = field(default_factory=list)  # 质量要求
    format_requirements: List[str] = field(default_factory=list)   # 格式要求
    budget_constraints: Optional[Dict] = None  # 预算约束
    custom_constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedIntent:
    """解析后的意图"""
    original_input: str
    intent_type: IntentType
    intent_confidence: IntentConfidence
    primary_goal: str
    entities: List[ExtractedEntity] = field(default_factory=list)
    constraints: TaskConstraints = field(default_factory=TaskConstraints)
    task_keywords: List[str] = field(default_factory=list)
    estimated_complexity: TaskComplexity = TaskComplexity.MEDIUM
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IntentUnderstandingConfig:
    """意图理解配置"""
    use_llm: bool = True
    fallback_to_rules: bool = True
    extract_entities: bool = True
    identify_constraints: bool = True
    confidence_threshold: float = 0.7  # 规则置信度阈值,≥0.7走快速路径,<0.7尝试LLM增强
    max_retries: int = 2


class EntityExtractor:
    """实体提取器"""

    def __init__(self):
        # 实体模式定义
        self.entity_patterns = {
            "number": r"\d+(?:\.\d+)?",
            "date": r"\d{4}(?:[-/年](?:\d{1,2}(?:[-/月]\d{1,2}[日]?)?)?)?",  # 支持: 2024, 2024年, 2024-01, 2024年1月, 2024-01-01, 2024年1月1日
            "time": r"\d{1,2}[时:]\d{2}",
            "email": r"[\w\.-]+@[\w\.-]+\.\w+",
            "url": r"https?://[\w\./\-?=&#]+",
            "file_path": r"/[\w/\.-]+",
            "money": r"(?:RMB|¥|\$|USD|EUR)\s*\d+(?:\.\d+)?",
        }

    def extract(self, text: str) -> List[ExtractedEntity]:
        """提取文本中的实体"""
        entities = []

        for entity_type, pattern in self.entity_patterns.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                entities.append(ExtractedEntity(
                    name=match.group(),
                    type=entity_type,
                    value=match.group(),
                    confidence=0.9
                ))

        return entities


class ConstraintIdentifier:
    """约束识别器"""

    def __init__(self):
        self.constraint_patterns = {
            "time": [
                (r"(\d+)(?:分钟|小时|天|周)", "duration"),
                (r"在\d+(?:分钟|小时|天)内", "deadline"),
                (r"尽快|立刻|马上", "urgent"),
            ],
            "quality": [
                (r"高质量|高品质|高标准", "high_quality"),
                (r"精确|准确|无误", "accuracy"),
                (r"详细|完整|全面", "completeness"),
            ],
            "format": [
                (r"用(?:JSON|XML|CSV|Excel)", "structured_format"),
                (r"以.*格式", "specified_format"),
                (r"图表|可视化|图形", "visual"),
            ],
            "budget": [
                (r"预算\s*(?:为)?\d+", "budget_limit"),
                (r"不超过\s*\d+", "cost_ceiling"),
            ]
        }

    def identify(self, text: str) -> TaskConstraints:
        """识别文本中的约束"""
        constraints = TaskConstraints()

        for category, patterns in self.constraint_patterns.items():
            for pattern, constraint_type in patterns:
                if re.search(pattern, text):
                    if category == "time":
                        constraints.time_constraint = constraint_type
                    elif category == "quality":
                        constraints.quality_requirements.append(constraint_type)
                    elif category == "format":
                        constraints.format_requirements.append(constraint_type)
                    elif category == "budget":
                        constraints.budget_constraints = {"type": constraint_type}

        return constraints


class KeywordExtractor:
    """关键词提取器"""

    def __init__(self):
        self.stop_words = {
            "的", "了", "在", "是", "我", "有", "和", "就",
            "不", "人", "都", "一", "一个", "上", "也", "很",
            "到", "说", "要", "去", "你", "会", "着", "没有"
        }

    def extract(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单分词
        words = re.findall(r"[\w]+", text)

        # 过滤停用词和短词
        keywords = [
            w for w in words
            if w not in self.stop_words and len(w) >= 2
        ]

        return list(set(keywords))[:10]  # 最多10个关键词


class RuleBasedIntentClassifier:
    """基于规则的意图分类器"""

    def __init__(self):
        self.intent_keywords = {
            IntentType.QUERY: ["查询", "找", "搜索", "查找", "什么", "如何", "怎么", "多少"],
            IntentType.ACTION: ["执行", "运行", "开始", "启动", "做", "进行"],
            IntentType.CREATION: ["创建", "生成", "制作", "写", "新建"],
            IntentType.ANALYSIS: ["分析", "统计", "计算", "评估"],
            IntentType.MODIFICATION: ["修改", "更新", "调整", "改变", "编辑"],
            IntentType.DELETION: ["删除", "移除", "清除", "去掉"],
            IntentType.COMPARISON: ["比较", "对比", "差异", "哪个好"],
            IntentType.SUMMARY: ["总结", "概括", "汇总", "归纳"],
        }

    def classify(self, text: str) -> IntentConfidence:
        """分类意图"""
        text_lower = text.lower()
        scores = {}

        for intent_type, keywords in self.intent_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[intent_type] = score

        if not scores:
            return IntentConfidence(
                primary_intent=IntentType.UNKNOWN,
                confidence=0.3
            )

        # 找最高分
        primary = max(scores.items(), key=lambda x: x[1])
        confidence = min(primary[1] / 3, 1.0)  # 归一化

        # 记录其他可能意图
        alternatives = [(k, v) for k, v in scores.items() if k != primary[0]]

        return IntentConfidence(
            primary_intent=primary[0],
            confidence=confidence,
            alternative_intents=alternatives[:2]
        )


class LLMIntentClassifier:
    """LLM辅助意图分类器"""

    def __init__(self, llm_facade: Optional[Any] = None):
        self.llm_facade = llm_facade

    async def classify(self, text: str) -> IntentConfidence:
        """使用LLM分类意图"""
        if not self.llm_facade:
            # 回退到规则分类器
            rule_classifier = RuleBasedIntentClassifier()
            return rule_classifier.classify(text)

        prompt = self._build_classification_prompt(text)

        try:
            response = await self.llm_facade.generate(prompt)
            return self._parse_classification_response(response, text)

        except Exception as e:
            logger.error(f"LLM意图分类失败: {e}，回退到规则分类")
            rule_classifier = RuleBasedIntentClassifier()
            return rule_classifier.classify(text)

    def _build_classification_prompt(self, text: str) -> Dict[str, Any]:
        """构建分类Prompt"""
        system_prompt = """你是一个意图分类专家。请分析用户输入，判断其主要意图。

意图类型：
- query: 查询信息
- action: 执行动作
- creation: 创建内容
- analysis: 分析数据
- modification: 修改内容
- deletion: 删除内容
- comparison: 比较
- summary: 总结

请只输出一个词：主要的意图类型。"""

        return {
            "prompt": f"{system_prompt}\n\n用户输入：{text}",
            "metadata": {"task_type": "intent_classification"}
        }

    def _parse_classification_response(self, response: str, original_text: str) -> IntentConfidence:
        """解析LLM响应"""
        response_lower = response.lower().strip()

        # 映射到IntentType
        intent_mapping = {
            "query": IntentType.QUERY,
            "action": IntentType.ACTION,
            "creation": IntentType.CREATION,
            "analysis": IntentType.ANALYSIS,
            "modification": IntentType.MODIFICATION,
            "deletion": IntentType.DELETION,
            "comparison": IntentType.COMPARISON,
            "summary": IntentType.SUMMARY,
        }

        primary = intent_mapping.get(response_lower, IntentType.UNKNOWN)

        # 简单置信度估计
        confidence = 0.8 if primary != IntentType.UNKNOWN else 0.3

        return IntentConfidence(
            primary_intent=primary,
            confidence=confidence
        )


class IntentUnderstandingSystem:
    """意图理解系统 - 统一入口"""

    def __init__(
        self,
        config: Optional[IntentUnderstandingConfig] = None,
        llm_facade: Optional[Any] = None
    ):
        self.config = config or IntentUnderstandingConfig()
        self.llm_facade = llm_facade

        # 初始化各组件
        self.entity_extractor = EntityExtractor()
        self.constraint_identifier = ConstraintIdentifier()
        self.keyword_extractor = KeywordExtractor()
        self.rule_classifier = RuleBasedIntentClassifier()
        self.llm_classifier = LLMIntentClassifier(llm_facade)

    async def understand(self, user_input: str) -> ParsedIntent:
        """理解用户输入

        Args:
            user_input: 用户的原始输入

        Returns:
            ParsedIntent: 结构化的意图表示
        """
        logger.info(f"开始理解用户输入: {user_input[:50]}...")

        # 1. 意图分类
        intent_confidence = await self._classify_intent(user_input)

        # 2. 提取实体
        entities = []
        if self.config.extract_entities:
            entities = self.entity_extractor.extract(user_input)

        # 3. 识别约束
        constraints = TaskConstraints()
        if self.config.identify_constraints:
            constraints = self.constraint_identifier.identify(user_input)

        # 4. 提取关键词
        keywords = self.keyword_extractor.extract(user_input)

        # 5. 估计复杂度
        complexity = self._estimate_complexity(user_input, entities, keywords)

        # 6. 提取主要目标
        primary_goal = self._extract_primary_goal(user_input)

        parsed_intent = ParsedIntent(
            original_input=user_input,
            intent_type=intent_confidence.primary_intent,
            intent_confidence=intent_confidence,
            primary_goal=primary_goal,
            entities=entities,
            constraints=constraints,
            task_keywords=keywords,
            estimated_complexity=complexity,
            metadata={
                "llm_used": self.llm_facade is not None,
                "entity_count": len(entities),
                "constraint_count": len(constraints.quality_requirements) +
                                   len(constraints.format_requirements)
            }
        )

        logger.info(
            f"意图理解完成: {intent_confidence.primary_intent.value} "
            f"(置信度: {intent_confidence.confidence:.2f}), "
            f"复杂度: {complexity.value}, "
            f"关键词: {', '.join(keywords[:5])}"
        )

        return parsed_intent

    async def _classify_intent(self, text: str) -> IntentConfidence:
        """分类意图 - LLM优先,规则兜底
        
        执行顺序:
        1. 优先使用LLM分类(更精准,理解上下文)
        2. LLM失败或禁用时,使用规则分类(快速、稳定)
        """
        # 1. 优先使用LLM分类
        if self.config.use_llm and self.llm_facade:
            try:
                logger.info(f"使用LLM进行意图分类...")
                llm_result = await self.llm_classifier.classify(text)
                
                if llm_result.confidence >= 0.6:
                    logger.info(f"LLM分类成功: {llm_result.primary_intent.value} (置信度: {llm_result.confidence:.2f})")
                    return llm_result
                else:
                    logger.info(f"LLM置信度较低({llm_result.confidence:.2f}),尝试规则分类...")
                    
            except Exception as e:
                logger.warning(f"LLM分类失败: {e},回退到规则结果")
        
        # 2. 回退到规则分类
        rule_result = self.rule_classifier.classify(text)
        logger.debug(f"规则分类结果: {rule_result.primary_intent.value} (置信度: {rule_result.confidence:.2f})")
        return rule_result

    def _extract_primary_goal(self, text: str) -> str:
        """提取主要目标"""
        # 简单实现：去除语气词和辅助词，保留核心描述
        patterns_to_remove = [
            r"帮我|请|能不能|是否可以",
            r"的|一下|一下下",
            r"尽快|马上|立刻"
        ]

        goal = text
        for pattern in patterns_to_remove:
            goal = re.sub(pattern, "", goal)

        return goal.strip()

    def _estimate_complexity(
        self,
        text: str,
        entities: List[ExtractedEntity],
        keywords: List[str]
    ) -> TaskComplexity:
        """估计任务复杂度"""
        complexity_score = 0

        # 基于关键词估计
        complex_keywords = [
            "分析", "统计", "比较", "评估",
            "创建", "生成", "制作",
            "多个", "各种", "一系列"
        ]

        for kw in complex_keywords:
            if kw in text:
                complexity_score += 1

        # 基于实体数量
        if len(entities) >= 5:
            complexity_score += 2
        elif len(entities) >= 3:
            complexity_score += 1

        # 基于关键词数量
        if len(keywords) >= 8:
            complexity_score += 2
        elif len(keywords) >= 5:
            complexity_score += 1

        # 映射到复杂度级别
        if complexity_score >= 5:
            return TaskComplexity.VERY_HIGH
        elif complexity_score >= 3:
            return TaskComplexity.HIGH
        elif complexity_score >= 1:
            return TaskComplexity.MEDIUM
        else:
            return TaskComplexity.LOW

    def understand_sync(self, user_input: str) -> ParsedIntent:
        """同步理解（不调用LLM）"""
        # 使用规则方法
        config_without_llm = IntentUnderstandingConfig(use_llm=False)
        self.config = config_without_llm

        # 同步执行各步骤
        intent_confidence = self.rule_classifier.classify(user_input)
        entities = self.entity_extractor.extract(user_input)
        constraints = self.constraint_identifier.identify(user_input)
        keywords = self.keyword_extractor.extract(user_input)
        complexity = self._estimate_complexity(user_input, entities, keywords)
        primary_goal = self._extract_primary_goal(user_input)

        return ParsedIntent(
            original_input=user_input,
            intent_type=intent_confidence.primary_intent,
            intent_confidence=intent_confidence,
            primary_goal=primary_goal,
            entities=entities,
            constraints=constraints,
            task_keywords=keywords,
            estimated_complexity=complexity,
            metadata={"llm_used": False}
        )


class TaskDefinitionGenerator:
    """任务定义生成器 - 从ParsedIntent生成可执行任务"""

    def __init__(self, intent_system: IntentUnderstandingSystem):
        self.intent_system = intent_system

    async def generate_task_definition(
        self,
        user_input: str,
        session_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """生成任务定义

        Args:
            user_input: 用户输入
            session_context: 会话上下文

        Returns:
            结构化的任务定义
        """
        # 1. 理解意图
        parsed_intent = await self.intent_system.understand(user_input)

        # 2. 生成任务定义
        task_definition = {
            "task_id": f"task_{int(time.time())}",
            "goal": parsed_intent.primary_goal,
            "intent_type": parsed_intent.intent_type.value,
            "complexity": parsed_intent.estimated_complexity.value,
            "keywords": parsed_intent.task_keywords,
            "entities": [
                {
                    "name": e.name,
                    "type": e.type,
                    "value": e.value
                }
                for e in parsed_intent.entities
            ],
            "constraints": {
                "time": parsed_intent.constraints.time_constraint,
                "quality": parsed_intent.constraints.quality_requirements,
                "format": parsed_intent.constraints.format_requirements,
            },
            "estimated_steps": self._estimate_steps(parsed_intent),
            "collaboration_mode": self._select_collaboration_mode(parsed_intent),
            "confidence": parsed_intent.intent_confidence.confidence,
            "metadata": parsed_intent.metadata
        }

        return task_definition

    def _estimate_steps(self, intent: ParsedIntent) -> int:
        """估算所需步骤数"""
        complexity = intent.estimated_complexity

        step_mapping = {
            TaskComplexity.LOW: 1,
            TaskComplexity.MEDIUM: 3,
            TaskComplexity.HIGH: 5,
            TaskComplexity.VERY_HIGH: 8
        }

        base_steps = step_mapping.get(complexity, 3)

        # 根据实体数量调整
        if len(intent.entities) > 5:
            base_steps += 1

        return base_steps

    def _select_collaboration_mode(self, intent: ParsedIntent) -> str:
        """选择协作模式"""
        complexity = intent.estimated_complexity

        if complexity in [TaskComplexity.VERY_HIGH, TaskComplexity.HIGH]:
            return "review"  # 需要评审
        elif complexity == TaskComplexity.MEDIUM:
            return "master_slave"  # 主从模式
        else:
            return "pipeline"  # 简单流水线
