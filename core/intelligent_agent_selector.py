"""智能Agent自动选择器

根据任务复杂度自动决定：
1. 使用多少个Agent
2. 并发还是协作模式
3. 具体使用哪些Agent
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """任务复杂度"""
    TRIVIAL = "trivial"      # 琐碎任务：单agent，单步
    SIMPLE = "simple"        # 简单任务：单agent，少量步骤
    MODERATE = "moderate"    # 中等任务：2-3个agent，轻度协作
    COMPLEX = "complex"      # 复杂任务：3-5个agent，协作模式
    VERY_COMPLEX = "very_complex"  # 极复杂任务：5+个agent，强协作


class ExecutionMode(Enum):
    """执行模式"""
    SINGLE = "single"        # 单agent执行
    PARALLEL = "parallel"    # 并发执行
    COLLABORATIVE = "collaborative"  # 协作执行
    HYBRID = "hybrid"       # 混合模式（先并发后协作）


@dataclass
class AgentRequirement:
    """Agent需求"""
    agent_type: str          # Agent类型
    count: int              # 数量
    capabilities: List[str] # 需要的能力
    can_parallel: bool      # 是否可以并行


@dataclass
class ExecutionPlan:
    """执行计划"""
    complexity: TaskComplexity
    execution_mode: ExecutionMode
    agents: List[str]
    agent_count: int
    estimated_time: float
    strategy: str           # 执行策略描述
    auto_selected: bool = True  # 标记为自动选择


class IntelligentAgentSelector:
    """智能Agent选择器

    根据任务特征自动分析并选择最优的Agent组合和执行模式
    """

    def __init__(self):
        self.agent_registry = self._init_agent_registry()
        self.complexity_keywords = self._init_complexity_keywords()

    def _init_agent_registry(self) -> Dict[str, Dict[str, Any]]:
        """初始化Agent注册表"""
        return {
            "scraper": {
                "capabilities": ["web_scraping", "data_collection", "search"],
                "best_for": ["信息检索", "数据收集", "搜索任务"],
                "weight": 1.0,
                "max_count": 3
            },
            "analyzer": {
                "capabilities": ["data_analysis", "pattern_recognition", "insight"],
                "best_for": ["分析", "洞察", "模式识别"],
                "weight": 1.2,
                "max_count": 2
            },
            "summarizer": {
                "capabilities": ["summarization", "text_generation", "report"],
                "best_for": ["总结", "报告", "文本生成"],
                "weight": 0.8,
                "max_count": 2
            },
            "checker": {
                "capabilities": ["verification", "validation", "quality"],
                "best_for": ["验证", "检查", "质量控制"],
                "weight": 1.0,
                "max_count": 2
            },
            "nlp": {
                "capabilities": ["nlp", "understanding", "language"],
                "best_for": ["语义理解", "自然语言处理"],
                "weight": 1.5,
                "max_count": 1
            },
            "planner": {
                "capabilities": ["planning", "reasoning", "strategy"],
                "best_for": ["规划", "推理", "策略制定"],
                "weight": 1.3,
                "max_count": 1
            },
            "chat": {
                "capabilities": ["conversation", "response", "interaction"],
                "best_for": ["对话", "问答", "交互"],
                "weight": 0.5,
                "max_count": 1
            }
        }

    def _init_complexity_keywords(self) -> Dict[str, List[str]]:
        """初始化复杂度关键词"""
        return {
            TaskComplexity.TRIVIAL: [
                "你好", "嗨", "hello", "谢谢", "再见", "你是谁", "聊天"
            ],
            TaskComplexity.SIMPLE: [
                "查询", "搜索", "告诉我", "介绍", "解释"
            ],
            TaskComplexity.MODERATE: [
                "分析", "比较", "评估", "研究", "探讨"
            ],
            TaskComplexity.COMPLEX: [
                "深度分析", "详细研究", "全面评估", "深入探讨",
                "复杂问题", "多维度"
            ],
            TaskComplexity.VERY_COMPLEX: [
                "深度思考", "综合研究", "系统分析", "全面诊断",
                "复杂任务", "多任务", "协同工作"
            ]
        }

    def analyze_task(self, task: str) -> Tuple[TaskComplexity, List[str]]:
        """分析任务复杂度

        Returns:
            (复杂度等级, 匹配的特征词列表)
        """
        task_lower = task.lower()

        # 检查每个复杂度级别的关键词
        matched_features = []
        complexity_scores = {c: 0 for c in TaskComplexity}

        for complexity, keywords in self.complexity_keywords.items():
            for kw in keywords:
                if kw.lower() in task_lower:
                    matched_features.append(kw)
                    # 越复杂的任务权重越高
                    complexity_scores[complexity] += {
                        TaskComplexity.TRIVIAL: 1,
                        TaskComplexity.SIMPLE: 2,
                        TaskComplexity.MODERATE: 3,
                        TaskComplexity.COMPLEX: 4,
                        TaskComplexity.VERY_COMPLEX: 5
                    }[complexity]

        # 额外分析任务结构
        structure_score = 0
        if any(w in task for w in ["第一", "第二", "第三", "首先", "其次", "然后", "最后"]):
            structure_score += 2  # 有步骤结构
        if any(w in task for w in ["并且", "同时", "而且", "此外"]):
            structure_score += 1  # 有并行结构
        if any(w in task for w in ["因为", "所以", "如果", "那么"]):
            structure_score += 1  # 有逻辑结构
        if len(task) > 50:
            structure_score += 1  # 任务描述较长
        if any(c in task for c in ["？", "?", "。"]):
            structure_score += 1  # 多个句子

        # 综合评分
        total_score = sum(complexity_scores.values()) + structure_score

        # 确定复杂度
        if total_score <= 2:
            return TaskComplexity.TRIVIAL, matched_features
        elif total_score <= 5:
            return TaskComplexity.SIMPLE, matched_features
        elif total_score <= 10:
            return TaskComplexity.MODERATE, matched_features
        elif total_score <= 15:
            return TaskComplexity.COMPLEX, matched_features
        else:
            return TaskComplexity.VERY_COMPLEX, matched_features

    def determine_execution_mode(
        self,
        complexity: TaskComplexity,
        matched_agents: List[str]
    ) -> ExecutionMode:
        """根据任务结构确定执行模式

        并发 vs 协作的判断依据：
        1. 并发（PARALLEL）：子任务相互独立，可同时执行
        2. 协作（COLLABORATIVE）：子任务有依赖，需按顺序执行

        判断信号：
        - 并发：任务描述中有"和"、"并且"、"同时"、"AND"
        - 协作：任务描述中有"然后"、"接着"、"先...再..."、"第一步...第二步..."
        """
        agent_count = len(matched_agents)

        # 单Agent只能是SINGLE
        if agent_count == 1:
            return ExecutionMode.SINGLE

        # 分析任务结构来判断是并发还是协作
        # 注意：这个方法应该在select_agents之后调用，
        # 但我们需要在select_agents中记录任务结构特征

        # 临时检查：如果之前分析发现是协作结构，使用COLLABORATIVE
        # 否则根据agent数量和复杂度判断
        if agent_count >= 3 and complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]:
            return ExecutionMode.COLLABORATIVE
        elif agent_count >= 2:
            return ExecutionMode.HYBRID
        else:
            return ExecutionMode.SINGLE

    def analyze_task_structure(self, task: str) -> Tuple[str, List[str]]:
        """分析任务结构，判断是并发还是协作

        Returns:
            (structure_type, structure_indicators)
            - "parallel": 并行结构（子任务独立）
            - "collaborative": 协作结构（子任务有依赖）
            - "mixed": 混合结构
        """
        task_lower = task.lower()

        # 并行结构的关键词（子任务独立）
        parallel_keywords = [
            "和", "并且", "同时", "而且", "此外",
            "以及", "加", "plus", "and", "also",
            "都", "都需", "都需要"
        ]

        # 协作结构的关键词（子任务有依赖）
        collaborative_keywords = [
            "然后", "接着", "再", "之后", "之后在",
            "先", "首先", "第一", "第二", "第三",
            "接下来", "之后在", "最后",
            "再然后", "之后才", "才能", "才进行",
            "的前提", "基于", "根据",
            "第一步", "第二步", "第三步",
            "先...再...", "先...然后..."
        ]

        parallel_score = 0
        collaborative_score = 0

        # 检查并行关键词
        for kw in parallel_keywords:
            if kw in task_lower:
                parallel_score += 2

        # 检查协作关键词
        for kw in collaborative_keywords:
            if kw in task_lower:
                collaborative_score += 3  # 协作关键词权重更高

        # 检查任务是否明确包含多个可独立执行的部分
        if any(w in task for w in ["、", ",", "，"]):
            # 使用顿号或逗号分隔的列表通常是并行的
            if "然后" not in task and "接着" not in task:
                parallel_score += 2

        # 判断结构类型
        if parallel_score > collaborative_score and parallel_score >= 2:
            return "parallel", ["parallel_keywords", f"parallel_score={parallel_score}"]
        elif collaborative_score > 0:
            return "collaborative", ["collaborative_keywords", f"collaborative_score={collaborative_score}"]
        else:
            return "unknown", ["no_clear_structure"]

    def select_agents(self, task: str, complexity: TaskComplexity) -> List[str]:
        """根据任务和复杂度选择Agent"""
        task_lower = task.lower()
        selected = []

        # 基础选择逻辑
        if any(w in task_lower for w in ["搜索", "爬取", "抓取", "热搜", "数据"]):
            selected.append("scraper")
        if any(w in task_lower for w in ["分析", "研究", "评估", "比较"]):
            selected.append("analyzer")
        if any(w in task_lower for w in ["总结", "汇总", "概括", "报告"]):
            selected.append("summarizer")
        if any(w in task_lower for w in ["检查", "验证", "确认", "核对"]):
            selected.append("checker")
        if any(w in task_lower for w in ["理解", "语义", "自然语言"]):
            selected.append("nlp")
        if any(w in task_lower for w in ["规划", "计划", "策略", "方案"]):
            selected.append("planner")
        if any(w in task_lower for w in ["对话", "聊天", "问答", "回复"]):
            selected.append("chat")

        # 如果没有匹配到任何agent，默认使用chat
        if not selected:
            selected.append("chat")

        # 根据复杂度调整agent数量
        max_agents = {
            TaskComplexity.TRIVIAL: 1,
            TaskComplexity.SIMPLE: 1,
            TaskComplexity.MODERATE: 2,
            TaskComplexity.COMPLEX: 3,
            TaskComplexity.VERY_COMPLEX: 5
        }[complexity]

        # 去重并限制数量
        selected = list(dict.fromkeys(selected))[:max_agents]

        # 如果是极复杂任务，确保有planner和analyzer
        if complexity == TaskComplexity.VERY_COMPLEX:
            if "planner" not in selected:
                selected.insert(0, "planner")
            if "analyzer" not in selected:
                selected.insert(1, "analyzer")
            selected = selected[:3]  # 最多3个核心agent

        return selected

    def create_execution_plan(self, task: str) -> ExecutionPlan:
        """创建完整的执行计划

        这是主入口方法，输入任务描述，输出完整的执行计划

        执行模式判断逻辑：
        1. 先分析任务结构（并发 vs 协作）
        2. 再结合复杂度确定最终模式
        """
        start_time = time.time()

        # 1. 分析任务复杂度
        complexity, matched_features = self.analyze_task(task)
        logger.info(f"任务复杂度分析: {complexity.value}, 特征: {matched_features}")

        # 2. 分析任务结构（并发 vs 协作）
        structure_type, structure_indicators = self.analyze_task_structure(task)
        logger.info(f"任务结构分析: {structure_type}, 指标: {structure_indicators}")

        # 3. 选择Agent
        agents = self.select_agents(task, complexity)
        agent_count = len(agents)

        # 4. 确定执行模式（综合考虑结构、复杂度、Agent数量）
        execution_mode = self._determine_execution_mode_with_structure(
            structure_type, complexity, agents
        )

        # 5. 估算时间
        base_times = {
            TaskComplexity.TRIVIAL: 0.5,
            TaskComplexity.SIMPLE: 1.0,
            TaskComplexity.MODERATE: 3.0,
            TaskComplexity.COMPLEX: 8.0,
            TaskComplexity.VERY_COMPLEX: 15.0
        }
        base_time = base_times[complexity]

        # 并发可以加速，协作会延长
        if execution_mode == ExecutionMode.PARALLEL:
            estimated_time = base_time * 0.6
        elif execution_mode == ExecutionMode.COLLABORATIVE:
            estimated_time = base_time * 1.3
        elif execution_mode == ExecutionMode.HYBRID:
            estimated_time = base_time * 0.9
        else:
            estimated_time = base_time

        # 6. 生成策略描述
        strategy_map = {
            ExecutionMode.SINGLE: f"单Agent直接执行 ({agents[0]})",
            ExecutionMode.PARALLEL: f"并发执行 {', '.join(agents)}，子任务相互独立",
            ExecutionMode.COLLABORATIVE: f"协作执行 {', '.join(agents)}，按依赖顺序执行",
            ExecutionMode.HYBRID: f"混合模式：先并发后协作 {', '.join(agents)}"
        }
        strategy = strategy_map[execution_mode]

        logger.info(
            f"执行计划生成: 复杂度={complexity.value}, "
            f"结构={structure_type}, Agent={agents}, 模式={execution_mode.value}, "
            f"预计时间={estimated_time:.1f}秒"
        )

        return ExecutionPlan(
            complexity=complexity,
            execution_mode=execution_mode,
            agents=agents,
            agent_count=agent_count,
            estimated_time=estimated_time,
            strategy=strategy,
            auto_selected=True
        )

    def _determine_execution_mode_with_structure(
        self,
        structure_type: str,
        complexity: TaskComplexity,
        agents: List[str]
    ) -> ExecutionMode:
        """综合任务结构和复杂度来确定执行模式

        判断规则：
        1. 单Agent → SINGLE
        2. 任务结构明确为parallel → PARALLEL（即使多Agent）
        3. 任务结构明确为collaborative → COLLABORATIVE
        4. 多Agent + 复杂任务 → COLLABORATIVE
        5. 多Agent + 简单任务 → HYBRID
        """
        agent_count = len(agents)

        if agent_count == 1:
            return ExecutionMode.SINGLE

        # 根据任务结构优先判断
        if structure_type == "parallel":
            return ExecutionMode.PARALLEL
        elif structure_type == "collaborative":
            return ExecutionMode.COLLABORATIVE

        # 结构不明确时，根据复杂度和Agent数量判断
        if agent_count >= 3 and complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]:
            return ExecutionMode.COLLABORATIVE
        elif agent_count >= 2:
            return ExecutionMode.HYBRID
        else:
            return ExecutionMode.SINGLE

    def explain_plan(self, plan: ExecutionPlan) -> str:
        """生成执行计划的解释"""
        return f"""
🤖 智能Agent执行计划
━━━━━━━━━━━━━━━━━━━━

📊 任务复杂度: {plan.complexity.value.upper()}
🎯 执行模式: {plan.execution_mode.value}
👥 Agent数量: {plan.agent_count}
🤖 使用Agent: {', '.join(plan.agents)}
⏱️ 预计时间: {plan.estimated_time:.1f}秒
📝 执行策略: {plan.strategy}

💡 决策说明:
   - 系统根据任务特征自动判断复杂度为 "{plan.complexity.value}"
   - {"单Agent足以处理" if plan.agent_count == 1 else f"需要{plan.agent_count}个Agent协作"}
   - {"采用直接执行" if plan.execution_mode == ExecutionMode.SINGLE else "采用并发加速" if plan.execution_mode == ExecutionMode.PARALLEL else "采用协作模式保证质量" if plan.execution_mode == ExecutionMode.COLLABORATIVE else "先并发后协作优化效率"}
"""


# 全局单例
_intelligent_selector: Optional[IntelligentAgentSelector] = None


def get_intelligent_selector() -> IntelligentAgentSelector:
    """获取智能选择器单例"""
    global _intelligent_selector
    if _intelligent_selector is None:
        _intelligent_selector = IntelligentAgentSelector()
    return _intelligent_selector
