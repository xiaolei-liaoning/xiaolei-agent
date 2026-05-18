"""智能Agent选择器 - 根据任务复杂度自动选择执行策略"""

import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


class Complexity(Enum):
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


class ExecutionMode(Enum):
    DIRECT = "direct"
    SINGLE_AGENT = "single_agent"
    MULTI_AGENT = "multi_agent"


@dataclass
class ExecutionPlan:
    complexity: Complexity = Complexity.SIMPLE
    execution_mode: ExecutionMode = ExecutionMode.DIRECT
    agent_count: int = 0
    agents: List[str] = field(default_factory=list)
    estimated_time: float = 1.0
    strategy: str = "direct"


class IntelligentAgentSelector:
    """智能Agent选择器 - 基于消息特征分类任务复杂度"""

    # 简单问候/闲聊
    _greeting_patterns = [
        "你好", "hello", "hi", "hey", "早上好", "晚上好", "下午好",
        "谢谢", "thanks", "thank", "再见", "bye", "goodbye",
        "哈哈", "呵呵", "嗯", "好的", "ok", "好的",
    ]

    # 需要单Agent的复杂任务
    _task_keywords = [
        "分析", "总结", "翻译", "计算", "查询", "搜索",
        "天气", "新闻", "股票", "汇率", "翻译",
        "打开", "关闭", "发送", "创建", "删除",
    ]

    # 需要多Agent协作的极复杂任务
    _multi_agent_keywords = [
        "深度思考", "研究一下", "详细分析", "全面分析",
        "对比分析", "趋势分析", "综合评估", "制定方案",
        "出方案", "写报告", "生成报告", "综合分析",
    ]

    def create_execution_plan(self, message: str) -> ExecutionPlan:
        """根据消息内容创建执行计划"""
        message_lower = message.lower().strip()

        # 检测深度思考/多Agent任务
        if any(kw in message_lower for kw in self._multi_agent_keywords):
            return ExecutionPlan(
                complexity=Complexity.COMPLEX,
                execution_mode=ExecutionMode.MULTI_AGENT,
                agent_count=3,
                agents=["master", "worker", "reviewer"],
                estimated_time=30.0,
                strategy="direct",
            )

        # 检测跨步骤复杂任务
        if any(kw in message_lower for kw in ["先", "然后", "再", "最后"]):
            multi_step_kws = ["爬", "分析", "翻译", "生成", "查", "搜索"]
            if any(kw in message_lower for kw in multi_step_kws):
                return ExecutionPlan(
                    complexity=Complexity.MODERATE,
                    execution_mode=ExecutionMode.SINGLE_AGENT,
                    agent_count=1,
                    agents=["worker"],
                    estimated_time=15.0,
                    strategy="single_agent",
                )

        # 检测单Agent任务
        if any(kw in message_lower for kw in self._task_keywords):
            return ExecutionPlan(
                complexity=Complexity.MODERATE,
                execution_mode=ExecutionMode.SINGLE_AGENT,
                agent_count=1,
                agents=["worker"],
                estimated_time=10.0,
                strategy="single_agent",
            )

        # 纯问候
        if any(kw in message_lower for kw in self._greeting_patterns):
            return ExecutionPlan(
                complexity=Complexity.TRIVIAL,
                execution_mode=ExecutionMode.DIRECT,
                agent_count=0,
                agents=[],
                estimated_time=1.0,
                strategy="direct",
            )

        # 默认简单任务
        return ExecutionPlan(
            complexity=Complexity.SIMPLE,
            execution_mode=ExecutionMode.DIRECT,
            agent_count=0,
            agents=[],
            estimated_time=2.0,
            strategy="direct",
        )


# 全局单例
_instance: Optional[IntelligentAgentSelector] = None


def get_intelligent_selector() -> IntelligentAgentSelector:
    global _instance
    if _instance is None:
        _instance = IntelligentAgentSelector()
    return _instance
