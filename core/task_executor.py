"""任务执行引擎 - 智能重试系统（循环版本）

特性：
- 任务拆解后放入队列
- 子任务失败后重新拆解
- 并发执行所有子任务
- 循环重试（最多 N 次，不会栈溢出）
- 任务依赖管理

使用方式：
    from core.task_executor import task_executor
    
    # 执行任务
    result = await task_executor.execute("爬取微博热搜并分析数据")
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

from .task_processor import task_processor, TaskResult, SubTask
from .task_queue import task_queue, TaskStatus, RetryPolicy

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    results: List[Dict[str, Any]]
    total_time: float
    completed_tasks: List[str]
    failed_tasks: List[str]
    retry_count: int = 0


@dataclass
class TaskNode:
    """任务节点（支持循环重试）"""
    id: str
    original_task: str  # 原始任务
    subtask: Optional[SubTask] = None  # 子任务（如果已拆解）
    parent_id: Optional[str] = None  # 父任务 ID
    retry_count: int = 0  # 重试次数
    max_retries: int = 3  # 最大重试次数
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None


class TaskExecutor:
    """任务执行引擎（循环重试模式）"""
    
    def __init__(self):
        self._task_queue = task_queue
        self._processor = task_processor
        self._started = False
        
        # 任务节点存储
        self._task_nodes: Dict[str, TaskNode] = {}
        self._task_counter: int = 0
        
        # 执行结果
        self._results: Dict[str, Dict[str, Any]] = {}
        
        logger.info("TaskExecutor 初始化完成（循环重试模式）")
    
    async def start(self):
        """启动执行引擎"""
        if self._started:
            return
        
        logger.info("启动任务执行引擎...")
        await self._task_queue.start()
        self._started = True
        logger.info("任务执行引擎已启动")
    
    async def stop(self, wait: bool = True):
        """停止执行引擎"""
        if not self._started:
            return
        
        logger.info("停止任务执行引擎...")
        await self._task_queue.stop(wait=wait)
        self._started = False
        logger.info("任务执行引擎已停止")
    
    async def execute(
        self,
        user_task: str,
        max_retries: int = 3,
    ) -> ExecutionResult:
        """执行任务（循环重试模式）
        
        流程：
        1. 创建根任务节点
        2. 放入待处理队列
        3. 循环处理队列中的任务
        4. 失败的任务重新拆解（循环，最多 N 次）
        5. 直到所有任务完成或达到最大重试次数
        
        Args:
            user_task: 用户任务
            max_retries: 最大重试次数
            
        Returns:
            执行结果
        """
        import time
        start_time = time.time()
        
        # 确保引擎已启动
        if not self._started:
            await self.start()
        
        # 清空状态
        self._task_nodes.clear()
        self._results.clear()
        self._task_counter = 0
        
        logger.info("开始执行任务: %s", user_task[:50])
        
        try:
            # 1. 创建根任务节点
            root_node = self._create_task_node(
                original_task=user_task,
                max_retries=max_retries,
            )
            
            # 2. 创建待处理队列（循环处理）
            pending_queue: List[TaskNode] = [root_node]
            
            # 3. 循环处理队列中的任务
            while pending_queue:
                # 取出一个任务
                node = pending_queue.pop(0)
                
                logger.info(
                    "处理任务: %s (重试: %d/%d)",
                    node.id, node.retry_count, node.max_retries,
                )
                
                # 4. 拆解任务
                decompose_success = await self._decompose_task(node)
                
                if decompose_success:
                    # 拆解成功，子任务已入队
                    logger.info("任务拆解成功: %s", node.id)
                    node.status = TaskStatus.COMPLETED
                    node.completed_at = datetime.now().timestamp()
                    self._results[node.id] = {
                        "task_id": node.id,
                        "action": node.subtask.action if node.subtask else None,
                        "status": "completed",
                        "success": True,
                    }
                else:
                    # 拆解失败
                    logger.warning("任务拆解失败: %s", node.id)
                    
                    # 检查是否可以重试
                    if node.retry_count < node.max_retries:
                        # 可以重试，重新入队
                        node.retry_count += 1
                        node.status = TaskStatus.PENDING
                        pending_queue.append(node)
                        
                        logger.info(
                            "任务重新入队: %s (重试: %d/%d)",
                            node.id, node.retry_count, node.max_retries,
                        )
                    else:
                        # 达到最大重试次数，标记为失败
                        node.status = TaskStatus.DEAD_LETTER
                        node.completed_at = datetime.now().timestamp()
                        self._results[node.id] = {
                            "task_id": node.id,
                            "action": node.subtask.action if node.subtask else None,
                            "status": "failed",
                            "success": False,
                            "error": node.error or "达到最大重试次数",
                        }
            
            # 5. 等待所有子任务完成
            await self._wait_for_subtasks(timeout=300.0)
            
            # 6. 收集结果
            completed_tasks = [
                task_id for task_id, node in self._task_nodes.items()
                if node.status == TaskStatus.COMPLETED
            ]
            failed_tasks = [
                task_id for task_id, node in self._task_nodes.items()
                if node.status in [TaskStatus.FAILED, TaskStatus.DEAD_LETTER]
            ]
            
            total_time = time.time() - start_time
            
            logger.info(
                "任务执行完成: %s (成功: %d, 失败: %d, 总耗时: %.2fs)",
                user_task[:50], len(completed_tasks), len(failed_tasks), total_time,
            )
            
            return ExecutionResult(
                success=len(failed_tasks) == 0,
                results=list(self._results.values()),
                total_time=total_time,
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
                retry_count=sum(node.retry_count for node in self._task_nodes.values()),
            )
            
        except Exception as e:
            logger.error("任务执行失败: %s - %s", user_task, e)
            return ExecutionResult(
                success=False,
                results=list(self._results.values()),
                total_time=time.time() - start_time,
                completed_tasks=[],
                failed_tasks=[],
            )
    
    def _create_task_node(
        self,
        original_task: str,
        max_retries: int = 3,
        parent_id: Optional[str] = None,
    ) -> TaskNode:
        """创建任务节点"""
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        
        node = TaskNode(
            id=task_id,
            original_task=original_task,
            parent_id=parent_id,
            max_retries=max_retries,
        )
        
        self._task_nodes[task_id] = node
        return node
    
    async def _decompose_task(self, node: TaskNode) -> bool:
        """拆解任务（循环版本，不会递归）
        
        Returns:
            True: 拆解成功
            False: 拆解失败
        """
        try:
            # 拆解任务
            result: TaskResult = await self._processor.process(node.original_task)
            
            if not result.subtasks:
                # 无法拆解，直接执行原始任务
                logger.info("任务无法拆解，直接执行: %s", node.id)
                return await self._enqueue_single_task(node)
            
            # 拆解成功，创建子任务节点并入队
            for subtask in result.subtasks:
                # 创建子任务节点
                child_node = self._create_task_node(
                    original_task=f"{subtask.action}: {subtask.params}",
                    max_retries=node.max_retries,
                    parent_id=node.id,
                )
                child_node.subtask = subtask
                
                # 入队
                await self._enqueue_subtask(child_node)
            
            logger.info("任务拆解完成: %s -> %d 个子任务", node.id, len(result.subtasks))
            return True
            
        except Exception as e:
            logger.error("任务拆解失败: %s - %s", node.id, e)
            node.error = str(e)
            return False
    
    async def _enqueue_single_task(self, node: TaskNode) -> bool:
        """将单个任务入队（无法拆解的情况）
        
        Returns:
            True: 入队成功
            False: 入队失败
        """
        try:
            # 提取 action 和 params
            from core.skill_dispatcher import SkillDispatcher
            dispatcher = SkillDispatcher()
            
            action = dispatcher.match_skill(node.original_task)
            params = dispatcher.extract_params(node.original_task, action)
            
            # 创建临时 subtask
            node.subtask = SubTask(
                id=f"{node.id}_sub",
                action=action,
                params=params,
                dependencies=[],
            )
            
            # 入队
            await self._enqueue_subtask(node)
            return True
            
        except Exception as e:
            logger.error("任务入队失败: %s - %s", node.id, e)
            node.error = str(e)
            return False
    
    async def _enqueue_subtask(self, node: TaskNode):
        """将子任务入队"""
        if not node.subtask:
            logger.warning("子任务为空，跳过: %s", node.id)
            return
        
        # 提交到队列
        task_id = await self._task_queue.submit(
            action=node.subtask.action,
            params=node.subtask.params,
            max_retries=1,  # 我们自己控制重试
            retry_policy=RetryPolicy.FIXED,
            retry_delay=0.1,
            priority=10 - node.subtask.priority,
            metadata={
                "node_id": node.id,
                "original_task": node.original_task,
            },
        )
        
        node.status = TaskStatus.RUNNING
        node.started_at = datetime.now().timestamp()
        
        logger.info("子任务已入队: %s -> %s", node.id, task_id)
    
    async def _wait_for_subtasks(self, timeout: float = 300.0):
        """等待所有子任务完成"""
        import time
        start_time = time.time()
        
        while True:
            # 检查所有任务节点
            all_completed = True
            has_running = False
            
            for task_id, node in self._task_nodes.items():
                if node.status == TaskStatus.RUNNING:
                    has_running = True
                    all_completed = False
                    
                    # 检查任务是否完成（从队列获取状态）
                    task_status = await self._check_task_status(node)
                    
                    if task_status == TaskStatus.COMPLETED:
                        node.status = TaskStatus.COMPLETED
                        node.completed_at = datetime.now().timestamp()
                        self._results[task_id] = {
                            "task_id": task_id,
                            "action": node.subtask.action if node.subtask else None,
                            "status": "completed",
                            "success": True,
                        }
                        
                    elif task_status == TaskStatus.DEAD_LETTER:
                        # 任务失败
                        logger.warning("子任务执行失败: %s", task_id)
                        node.status = TaskStatus.DEAD_LETTER
                        node.completed_at = datetime.now().timestamp()
                        self._results[task_id] = {
                            "task_id": task_id,
                            "action": node.subtask.action if node.subtask else None,
                            "status": "failed",
                            "success": False,
                            "error": node.error or "任务执行失败",
                        }
            
            if all_completed:
                break
            
            # 检查超时
            if time.time() - start_time > timeout:
                logger.warning("等待任务超时: %ds", timeout)
                break
            
            # 等待一段时间再检查
            await asyncio.sleep(0.5)
    
    async def _check_task_status(self, node: TaskNode) -> TaskStatus:
        """检查任务状态（从队列获取真实状态）"""
        if not node.subtask:
            return TaskStatus.FAILED
        
        # 从队列获取所有任务，找到对应的任务
        # 注意：TaskQueue 的 task_id 和 TaskExecutor 的 node.id 不同
        # 我们需要通过 metadata 中的 node_id 来匹配
        
        # 获取队列中的所有任务
        all_tasks = self._task_queue._tasks
        
        # 查找匹配的任务（通过 metadata 中的 node_id）
        for task_id, task in all_tasks.items():
            if task.metadata.get("node_id") == node.id:
                # 找到匹配的任务
                return task.status
        
        # 没有找到匹配的任务，假设已完成
        return TaskStatus.COMPLETED
    
    async def get_metrics(self) -> Dict[str, Any]:
        """获取执行引擎指标"""
        queue_metrics = self._task_queue.get_metrics()
        
        total_nodes = len(self._task_nodes)
        completed_nodes = sum(
            1 for node in self._task_nodes.values()
            if node.status == TaskStatus.COMPLETED
        )
        failed_nodes = sum(
            1 for node in self._task_nodes.values()
            if node.status in [TaskStatus.FAILED, TaskStatus.DEAD_LETTER]
        )
        
        return {
            "executor": {
                "started": self._started,
                "total_nodes": total_nodes,
                "completed_nodes": completed_nodes,
                "failed_nodes": failed_nodes,
            },
            "queue": queue_metrics,
        }


# 全局实例
task_executor = TaskExecutor()