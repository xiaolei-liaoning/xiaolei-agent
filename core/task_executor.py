"""任务执行引擎（已废弃 - DEPRECATED）

⚠️ 此模块当前未被主流程使用，保留仅供参考。
如需简单并发+链式处理，请直接使用 ConcurrentTaskProcessor。

特性：
- 支持并发执行和协作执行
- 基于任务树结构(NaturalLanguageTaskParser)解析用户输入
- 自动识别"与/和/然后/接着"等关键词构建任务依赖关系
- 支持共享数据在协作任务间传递

注意：
- 当前系统采用简化架构，仅使用ConcurrentTaskProcessor进行任务处理
- 如需启用此模块，需修改handlers.py中的handle_multi_step函数
- 未来如需复杂任务编排(嵌套并发/协作)，可重新评估是否启用

原设计目标：
- 处理复杂的自然语言任务描述
- 支持多层级任务依赖关系
- 提供完整的任务执行报告
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from core.task_parser import (
    TaskNode,
    TaskRelation,
    ParseResult,
    get_task_parser
)
from core.intelligent_agent_selector import get_intelligent_selector

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果"""
    task_id: str
    description: str
    success: bool
    result: Any
    error: Optional[str] = None
    duration: float = 0.0
    agent_used: Optional[str] = None
    output_key: Optional[str] = None  # 用于协作传递


@dataclass
class TaskExecutionReport:
    """任务执行报告"""
    total_tasks: int
    success_count: int
    failed_count: int
    total_duration: float
    results: List[ExecutionResult]
    strategy: str
    task_tree_explanation: str


class TaskExecutor:
    """任务执行引擎"""

    def __init__(self):
        self.parser = get_task_parser()
        self.agent_selector = get_intelligent_selector()
        self.execution_results: Dict[str, ExecutionResult] = {}
        self.shared_data: Dict[str, Any] = {}  # 用于协作任务间的数据传递

    async def execute(self, user_input: str, user_id: int = 1) -> TaskExecutionReport:
        """执行用户输入的任务

        Args:
            user_input: 用户输入的自然语言
            user_id: 用户ID

        Returns:
            TaskExecutionReport: 执行报告
        """
        start_time = time.time()

        logger.info(f"开始执行任务: {user_input}")

        # 1. 解析任务
        parse_result = self.parser.parse(user_input)
        task_tree_explanation = self.parser.explain_task_tree(parse_result.root_tasks)
        logger.info(f"任务树:\n{task_tree_explanation}")

        # 2. 执行任务树
        results = []
        self.shared_data.clear()

        for task in parse_result.root_tasks:
            task_results = await self._execute_task_tree(task, user_id)
            results.extend(task_results)

        # 3. 生成报告
        total_duration = time.time() - start_time
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count

        report = TaskExecutionReport(
            total_tasks=len(results),
            success_count=success_count,
            failed_count=failed_count,
            total_duration=total_duration,
            results=results,
            strategy=parse_result.execution_strategy,
            task_tree_explanation=task_tree_explanation
        )

        logger.info(f"执行完成: 成功 {success_count}/{len(results)}, 耗时 {total_duration:.2f}秒")
        return report

    async def _execute_task_tree(self, task: TaskNode, user_id: int) -> List[ExecutionResult]:
        """执行任务树"""
        results = []

        if task.relation == TaskRelation.PARALLEL and task.children:
            # 并发执行
            logger.info(f"并发执行 {len(task.children)} 个子任务")
            task_results = await self._execute_parallel(task.children, user_id)
            results.extend(task_results)

        elif task.relation == TaskRelation.COLLABORATIVE and task.children:
            # 协作执行（按依赖顺序）
            logger.info(f"协作执行 {len(task.children)} 个子任务")
            task_results = await self._execute_collaborative(task.children, user_id)
            results.extend(task_results)

        else:
            # 单个任务
            result = await self._execute_single_task(task.description, user_id)
            results.append(result)

        return results

    async def _execute_parallel(self, tasks: List[TaskNode], user_id: int) -> List[ExecutionResult]:
        """并发执行多个任务"""
        # 创建并发任务
        coroutines = [self._execute_single_task(task.description, user_id) for task in tasks]

        # 使用 gather 并发执行
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # 处理结果
        execution_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                execution_results.append(ExecutionResult(
                    task_id=tasks[i].id,
                    description=tasks[i].description,
                    success=False,
                    result=None,
                    error=str(result)
                ))
            else:
                execution_results.append(result)

        return execution_results

    async def _execute_collaborative(self, tasks: List[TaskNode], user_id: int) -> List[ExecutionResult]:
        """协作执行多个任务（按依赖顺序）"""
        results = []

        for task in tasks:
            # 检查依赖
            if task.depends_on:
                # 等待依赖任务完成
                await self._wait_for_dependencies(task.depends_on)

            # 执行当前任务
            logger.info(f"执行协作任务: {task.description}")
            result = await self._execute_single_task(task.description, user_id, task.depends_on)

            # 保存结果供后续任务使用
            if result.success:
                self.shared_data[task.id] = result.result
                result.output_key = task.id

            results.append(result)

            # 如果失败，根据策略决定是否继续
            if not result.success:
                logger.warning(f"任务 {task.id} 执行失败，继续执行后续任务")

        return results

    async def _wait_for_dependencies(self, depends_on: List[str]) -> None:
        """等待依赖任务完成"""
        # 在协作模式下，依赖任务已经在之前的循环中执行完成
        # 这里可以添加额外的等待逻辑（如检查结果是否可用）
        for dep_id in depends_on:
            if dep_id not in self.shared_data:
                logger.debug(f"等待依赖任务 {dep_id} 完成")

    async def _execute_single_task(self, description: str, user_id: int, depends_on: Optional[List[str]] = None) -> ExecutionResult:
        """执行单个任务

        使用智能选择器选择合适的 Agent/Skill
        """
        start_time = time.time()

        try:
            # 1. 使用智能选择器分析任务
            execution_plan = self.agent_selector.create_execution_plan(description)

            logger.info(
                f"任务执行计划: 复杂度={execution_plan.complexity.value}, "
                f"Agent={execution_plan.agents}, 模式={execution_plan.execution_mode.value}"
            )

            # 2. 获取依赖数据（如果有）
            context_data = None
            if depends_on:
                context_data = self._gather_dependency_data(depends_on)

            # 3. 根据选择的 Agent 执行任务
            # 这里需要根据实际系统集成
            result_text = await self._dispatch_to_agent(
                description=description,
                agents=execution_plan.agents,
                user_id=user_id,
                context_data=context_data
            )

            duration = time.time() - start_time

            return ExecutionResult(
                task_id=f"task_{int(time.time()*1000)}",
                description=description,
                success=True,
                result=result_text,
                duration=duration,
                agent_used=",".join(execution_plan.agents)
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"任务执行失败: {e}", exc_info=True)

            return ExecutionResult(
                task_id=f"task_{int(time.time()*1000)}",
                description=description,
                success=False,
                result=None,
                error=str(e),
                duration=duration
            )

    def _gather_dependency_data(self, depends_on: List[str]) -> Dict[str, Any]:
        """收集依赖任务的数据"""
        data = {}
        for dep_id in depends_on:
            if dep_id in self.shared_data:
                data[dep_id] = self.shared_data[dep_id]
        return data

    async def _dispatch_to_agent(
        self,
        description: str,
        agents: List[str],
        user_id: int,
        context_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """分发任务到 Agent/Skill

        这里需要与现有的 Agent/Skill 系统集成
        """
        # 获取主要 agent
        primary_agent = agents[0] if agents else "chat"

        logger.info(f"分发任务到 {primary_agent}: {description}")

        # 构建带上下文的描述
        task_description = description
        if context_data:
            # 将依赖数据添加到任务描述中
            context_str = "\n".join([f"[参考数据]: {v}" for v in context_data.values() if v])
            task_description = f"{description}\n\n{context_str}"

        # 调用现有的处理逻辑
        try:
            from core.handlers import handle_single_step

            result = await handle_single_step(
                message=task_description,
                user_id=user_id,
                skill_name=None,  # 让系统自动选择
                agent_id="auto_agent"
            )

            reply = result.get("reply", str(result))
            return reply

        except Exception as e:
            logger.error(f"Agent 执行失败: {e}", exc_info=True)
            # 降级到简单回复
            return f"任务执行中: {description}\n\n(详细执行结果待完善)"


class HybridTaskExecutor(TaskExecutor):
    """混合任务执行器

    支持更复杂的嵌套结构和执行策略
    """

    def __init__(self):
        super().__init__()
        self.execution_history: List[Dict[str, Any]] = []

    async def execute_with_nested(
        self,
        user_input: str,
        user_id: int = 1
    ) -> TaskExecutionReport:
        """执行支持嵌套结构的任务"""
        start_time = time.time()

        # 1. 解析任务
        parse_result = self.parser.parse(user_input)
        task_tree_explanation = self.parser.explain_task_tree(parse_result.root_tasks)

        # 2. 递归执行任务树
        results = []
        self.shared_data.clear()
        self.execution_history.clear()

        for task in parse_result.root_tasks:
            task_results = await self._execute_node_recursive(task, user_id, depth=0)
            results.extend(task_results)

        # 3. 生成报告
        total_duration = time.time() - start_time
        success_count = sum(1 for r in results if r.success)

        return TaskExecutionReport(
            total_tasks=len(results),
            success_count=success_count,
            failed_count=len(results) - success_count,
            total_duration=total_duration,
            results=results,
            strategy=parse_result.execution_strategy,
            task_tree_explanation=task_tree_explanation
        )

    async def _execute_node_recursive(
        self,
        node: TaskNode,
        user_id: int,
        depth: int
    ) -> List[ExecutionResult]:
        """递归执行节点"""
        results = []

        # 如果有子节点，按关系执行
        if node.children:
            if node.relation == TaskRelation.PARALLEL:
                # 并发执行所有子节点
                logger.info(f"[深度{depth}] 并发执行 {len(node.children)} 个子任务")
                results = await self._execute_parallel(node.children, user_id)

            elif node.relation == TaskRelation.COLLABORATIVE:
                # 按顺序执行（考虑依赖）
                logger.info(f"[深度{depth}] 协作执行 {len(node.children)} 个子任务")
                results = await self._execute_collaborative(node.children, user_id)

            else:
                # 递归执行每个子节点
                for child in node.children:
                    child_results = await self._execute_node_recursive(child, user_id, depth + 1)
                    results.extend(child_results)
        else:
            # 叶子节点，直接执行
            result = await self._execute_single_task(node.description, user_id)
            results.append(result)

            # 记录执行历史
            self.execution_history.append({
                "depth": depth,
                "node_id": node.id,
                "description": node.description,
                "result": result.result if result.success else None
            })

        return results


# 全局执行器
_executor: Optional[TaskExecutor] = None
_hybrid_executor: Optional[HybridTaskExecutor] = None


def get_task_executor() -> TaskExecutor:
    """获取任务执行器单例"""
    global _executor
    if _executor is None:
        _executor = TaskExecutor()
    return _executor


def get_hybrid_task_executor() -> HybridTaskExecutor:
    """获取混合任务执行器单例"""
    global _hybrid_executor
    if _hybrid_executor is None:
        _hybrid_executor = HybridTaskExecutor()
    return _hybrid_executor
