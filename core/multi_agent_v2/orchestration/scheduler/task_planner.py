"""
任务规划器 - 智能任务分解与规划

功能：
1. 任务理解 - 解析任务类型、复杂度
2. 任务分解 - 将复杂任务拆解为子任务
3. 依赖分析 - 分析子任务之间的依赖关系
4. 执行计划 - 生成执行顺序和时间安排
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import uuid
import time

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """任务类型"""
    SIMPLE = "simple"           # 简单任务
    SEQUENTIAL = "sequential"   # 顺序任务
    PARALLEL = "parallel"     # 并行任务
    HIERARCHICAL = "hierarchical"  # 层次任务
    MIXED = "mixed"           # 混合任务


class TaskPriority(Enum):
    """任务优先级"""
    CRITICAL = 0    # 关键
    HIGH = 1        # 高
    MEDIUM = 2      # 中
    LOW = 3         # 低


@dataclass
class SubTask:
    """子任务"""
    subtask_id: str
    parent_task_id: str
    description: str
    task_type: str
    keywords: List[str] = field(default_factory=list)
    complexity: float = 0.5
    estimated_time: float = 10.0
    dependencies: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.MEDIUM
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """执行计划"""
    plan_id: str
    original_task: str
    subtasks: List[SubTask]
    execution_order: List[str]  # 按执行顺序排列的subtask_id
    total_estimated_time: float
    collaboration_mode: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskPlanner:
    """任务规划器"""

    def __init__(self):
        self.plan_history: List[ExecutionPlan] = []
        self._task_patterns = self._initialize_patterns()
        logger.info("任务规划器初始化完成")

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

    async def plan(self, task_description: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """规划任务

        Args:
            task_description: 任务描述
            context: 上下文信息

        Returns:
            执行计划
        """
        logger.info(f"开始规划任务: {task_description}")

        # 1. 理解任务
        task_type = await self._understand_task(task_description)

        # 2. 分解任务
        subtasks = await self._decompose_task(task_description, task_type)

        # 3. 分析依赖
        await self._analyze_dependencies(subtasks)

        # 4. 确定执行顺序
        execution_order = await self._determine_execution_order(subtasks)

        # 5. 计算总时间
        total_time = sum(st.estimated_time for st in subtasks)

        # 6. 确定协作模式
        collaboration_mode = await self._determine_collaboration_mode(task_type, subtasks)

        # 7. 创建执行计划
        plan = ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            original_task=task_description,
            subtasks=subtasks,
            execution_order=execution_order,
            total_estimated_time=total_time,
            collaboration_mode=collaboration_mode,
            metadata={
                "task_type": task_type.value,
                "context": context or {}
            }
        )

        # 记录历史
        self.plan_history.append(plan)

        logger.info(f"任务规划完成，生成{len(subtasks)}个子任务")
        return plan

    async def _understand_task(self, task_description: str) -> TaskType:
        """理解任务类型"""
        # 简单的关键词匹配
        for pattern_name, pattern in self._task_patterns.items():
            for keyword in pattern["keywords"]:
                if keyword in task_description:
                    # 根据模式确定任务类型
                    if pattern["collaboration_mode"] == "pipeline":
                        return TaskType.SEQUENTIAL
                    elif pattern["collaboration_mode"] == "parallel_review":
                        return TaskType.PARALLEL
                    elif pattern["collaboration_mode"] == "master_slave":
                        return TaskType.HIERARCHICAL

        # 默认返回简单任务
        return TaskType.SIMPLE

    async def _decompose_task(
        self,
        task_description: str,
        task_type: TaskType
    ) -> List[SubTask]:
        """分解任务"""
        subtasks = []

        # 查找匹配的模式
        matched_pattern = None
        for pattern_name, pattern in self._task_patterns.items():
            for keyword in pattern["keywords"]:
                if keyword in task_description:
                    matched_pattern = pattern
                    break
            if matched_pattern:
                break

        if matched_pattern:
            # 使用预定义的子任务
            for i, subtask_def in enumerate(matched_pattern["subtasks"]):
                subtask = SubTask(
                    subtask_id=f"subtask_{i}",
                    parent_task_id=str(uuid.uuid4()),
                    description=subtask_def["description"],
                    task_type=subtask_def["type"],
                    complexity=subtask_def["complexity"],
                    estimated_time=subtask_def["complexity"] * 20.0
                )
                subtasks.append(subtask)
        else:
            # 通用分解
            subtask = SubTask(
                subtask_id="subtask_0",
                parent_task_id=str(uuid.uuid4()),
                description=task_description,
                task_type="general",
                complexity=0.5,
                estimated_time=10.0
            )
            subtasks.append(subtask)

        return subtasks

    async def _analyze_dependencies(self, subtasks: List[SubTask]) -> None:
        """分析子任务依赖关系"""
        # 简单的顺序依赖
        for i in range(1, len(subtasks)):
            subtasks[i].dependencies.append(subtasks[i-1].subtask_id)

    async def _determine_execution_order(self, subtasks: List[SubTask]) -> List[str]:
        """确定执行顺序"""
        # 拓扑排序
        order = []
        visited = set()

        def visit(subtask: SubTask):
            if subtask.subtask_id in visited:
                return
            visited.add(subtask.subtask_id)

            # 先访问依赖的任务
            for dep_id in subtask.dependencies:
                dep = next((st for st in subtasks if st.subtask_id == dep_id), None)
                if dep:
                    visit(dep)

            order.append(subtask.subtask_id)

        for subtask in subtasks:
            visit(subtask)

        return order

    async def _determine_collaboration_mode(
        self,
        task_type: TaskType,
        subtasks: List[SubTask]
    ) -> str:
        """确定协作模式"""
        if task_type == TaskType.SEQUENTIAL:
            return "pipeline"
        elif task_type == TaskType.PARALLEL:
            return "parallel_review"
        elif task_type == TaskType.HIERARCHICAL:
            return "master_slave"
        else:
            return "single"

    def get_plan_history(self, limit: int = 100) -> List[ExecutionPlan]:
        """获取规划历史"""
        return self.plan_history[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.plan_history:
            return {
                "total_plans": 0,
                "avg_subtasks": 0,
                "avg_estimated_time": 0
            }

        total_plans = len(self.plan_history)
        avg_subtasks = sum(len(p.subtasks) for p in self.plan_history) / total_plans
        avg_estimated_time = sum(p.total_estimated_time for p in self.plan_history) / total_plans

        return {
            "total_plans": total_plans,
            "avg_subtasks": avg_subtasks,
            "avg_estimated_time": avg_estimated_time
        }


# 全局任务规划器实例
_task_planner: Optional[TaskPlanner] = None


def get_task_planner() -> TaskPlanner:
    """获取任务规划器实例"""
    global _task_planner
    if _task_planner is None:
        _task_planner = TaskPlanner()
    return _task_planner
