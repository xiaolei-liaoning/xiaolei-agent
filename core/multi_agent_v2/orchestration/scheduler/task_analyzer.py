"""
任务分析器 - 智能任务理解与分析

功能：
1. 任务分析 - 解析任务复杂度、依赖、并行性
2. 任务理解 - 模式匹配识别任务类型
3. 复杂度估算 - 基于内容和特征估算复杂度
"""

import logging
import re
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.agents.base.base_agent import Task
from core.shared.enums import TaskComplexity

logger = logging.getLogger(__name__)


class TaskAnalyzer:
    """任务分析器 - 分析任务的复杂度、类型和结构

    职责：
    - 分析任务基本特征（复杂度、依赖、步骤数）
    - 基于关键词模式理解任务类型
    - 估算任务复杂度分数
    """

    def __init__(self):
        # 任务模式库（源自 TaskPlanner）
        self._task_patterns = self._initialize_patterns()
        logger.info("任务分析器初始化完成")

    def _initialize_patterns(self) -> Dict[str, Dict[str, Any]]:
        """初始化任务模式"""
        return {
            "web_scraping": {
                "keywords": ["爬取", "抓取", "网页", "数据"],
                "subtasks": [
                    {"description": "分析目标网站结构", "type": "analysis", "complexity": 0.3},
                    {"description": "设计爬虫策略", "type": "planning", "complexity": 0.4},
                    {"description": "执行数据抓取", "type": "execution", "complexity": 0.7},
                    {"description": "数据清洗处理", "type": "processing", "complexity": 0.5},
                    {"description": "存储结果", "type": "storage", "complexity": 0.3}
                ],
                "collaboration_mode": "pipeline"
            },
            "data_analysis": {
                "keywords": ["分析", "统计", "数据", "报告"],
                "subtasks": [
                    {"description": "收集数据", "type": "collection", "complexity": 0.4},
                    {"description": "数据预处理", "type": "preprocessing", "complexity": 0.5},
                    {"description": "执行分析", "type": "analysis", "complexity": 0.7},
                    {"description": "生成可视化", "type": "visualization", "complexity": 0.5},
                    {"description": "撰写报告", "type": "reporting", "complexity": 0.6}
                ],
                "collaboration_mode": "pipeline"
            },
            "code_review": {
                "keywords": ["评审", "审查", "代码", "质量"],
                "subtasks": [
                    {"description": "代码静态分析", "type": "static_analysis", "complexity": 0.4},
                    {"description": "安全漏洞检测", "type": "security_check", "complexity": 0.6},
                    {"description": "性能分析", "type": "performance_check", "complexity": 0.5},
                    {"description": "代码规范检查", "type": "style_check", "complexity": 0.3}
                ],
                "collaboration_mode": "parallel_review"
            },
            "research": {
                "keywords": ["研究", "调研", "搜索", "资料"],
                "subtasks": [
                    {"description": "明确研究目标", "type": "definition", "complexity": 0.3},
                    {"description": "信息收集", "type": "collection", "complexity": 0.6},
                    {"description": "信息整理", "type": "organization", "complexity": 0.5},
                    {"description": "分析总结", "type": "analysis", "complexity": 0.7}
                ],
                "collaboration_mode": "master_slave"
            }
        }

    def analyze(self, task: Task) -> Dict[str, Any]:
        """分析任务的基本特征

        提取：
        - complexity: 任务复杂度 (0-1)
        - has_dependencies: 是否有依赖
        - estimated_steps: 预估步骤数
        - requires_review: 是否需要评审
        - is_parallelizable: 是否可并行
        - keywords: 关键词列表

        Args:
            task: 待分析的任务对象

        Returns:
            包含任务分析结果的字典
        """
        analysis = {
            "complexity": task.complexity,
            "has_dependencies": len(task.dependencies) > 0,
            "estimated_steps": task.estimated_steps,
            "requires_review": task.complexity > 0.7,
            "is_parallelizable": len(task.dependencies) == 0 and task.estimated_steps > 1,
            "keywords": task.keywords,
            "task_type": task.type or "general"
        }

        return analysis

    def understand(self, task_description: str) -> Dict[str, Any]:
        """理解任务类型 - 基于关键词模式匹配

        从任务描述中识别任务类型（顺序、并行、层次、混合等）。
        返回包含 task_type（字符串）、matched_pattern（模式名）等信息的字典。

        Args:
            task_description: 任务描述文本

        Returns:
            包含任务类型信息的字典
        """
        result = {
            "task_type": "simple",
            "matched_pattern": None,
            "collaboration_mode": "pipeline",
            "confidence": 0.5
        }

        for pattern_name, pattern in self._task_patterns.items():
            for keyword in pattern["keywords"]:
                if keyword in task_description:
                    result["matched_pattern"] = pattern_name
                    result["collaboration_mode"] = pattern["collaboration_mode"]

                    # 根据模式确定任务类型
                    if pattern["collaboration_mode"] == "pipeline":
                        result["task_type"] = "sequential"
                    elif pattern["collaboration_mode"] == "parallel_review":
                        result["task_type"] = "parallel"
                    elif pattern["collaboration_mode"] == "master_slave":
                        result["task_type"] = "hierarchical"

                    result["confidence"] = 0.8
                    logger.debug(f"任务理解: 匹配模式 '{pattern_name}', 类型={result['task_type']}")
                    return result

        return result

    def estimate_complexity(self, task: Task) -> float:
        """估算任务复杂度分数 (0.0 ~ 1.0)

        综合以下维度估算复杂度：
        - 关键词中包含的复杂度线索
        - 任务预估步骤数
        - 依赖数量

        Args:
            task: 待评估的任务对象

        Returns:
            复杂度分数，范围 0.0 (最简单) ~ 1.0 (最复杂)
        """
        description = task.description or ""
        keywords = task.keywords or []

        complexity_score = 0.0

        # 1. 基于复杂关键词（源自 TaskPlanner 的 _estimate_complexity）
        complex_keywords = [
            "分析", "统计", "比较", "评估",
            "创建", "生成", "制作",
            "多个", "各种", "一系列"
        ]
        for kw in complex_keywords:
            if kw in description:
                complexity_score += 0.15

        # 2. 基于预估步骤数
        estimated_steps = task.estimated_steps or 1
        if estimated_steps >= 8:
            complexity_score += 0.3
        elif estimated_steps >= 5:
            complexity_score += 0.2
        elif estimated_steps >= 3:
            complexity_score += 0.1

        # 3. 基于依赖数量
        dependencies = task.dependencies or []
        if len(dependencies) >= 5:
            complexity_score += 0.2
        elif len(dependencies) >= 3:
            complexity_score += 0.15
        elif len(dependencies) >= 1:
            complexity_score += 0.05

        # 截断到 [0.0, 1.0]
        return min(1.0, max(0.0, complexity_score))
