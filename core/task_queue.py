"""任务队列系统（已废弃 - DEPRECATED）

⚠️ 此模块当前未被主流程使用，保留仅供参考。
如需任务队列功能，请使用 ConcurrentTaskProcessor。

特性：
- 任务状态跟踪（pending/running/completed/failed）
- 自动重试机制（可配置重试次数和退避策略）
- 死信队列（多次失败后的任务）
- 错误分类（可重试错误 vs 不可重试错误）
- 指数退避（重试间隔）
- 任务优先级
- 指标监控

使用方式（示例代码，未实际启用）：
    from core.task_queue import task_queue
    
    # 提交任务
    await task_queue.submit({
        "action": "web_scraper",
        "params": {"site_name": "微博"},
        "max_retries": 3,
    })
    
    # 启动队列处理器
    await task_queue.start()
"""

import asyncio
import time
import logging
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class RetryPolicy(Enum):
    """重试策略"""
    FIXED = "fixed"          # 固定间隔
    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"        # 线性增长


@dataclass
class Task:
    """任务定义"""
    id: str
    action: str
    params: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    max_retries: int = 3
    retry_count: int = 0
    retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL
    retry_delay: float = 1.0  # 初始延迟（秒）
    priority: int = 5  # 1-10，数字越大优先级越高
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0


class TaskQueue:
    """任务队列系统"""
    
    def __init__(
        self,
        max_workers: int = 5,
        max_retries: int = 3,
        retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL,
        retry_delay: float = 1.0,
    ):
        """初始化任务队列
        
        Args:
            max_workers: 最大工作线程数
            max_retries: 默认最大重试次数
            retry_policy: 重试策略
            retry_delay: 初始重试延迟（秒）
        """
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.retry_policy = retry_policy
        self.retry_delay = retry_delay
        
        # 队列
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._dead_letter_queue: asyncio.Queue = asyncio.Queue()
        
        # 任务存储
        self._tasks: Dict[str, Task] = {}
        self._task_counter: int = 0
        
        # 工作线程
        self._workers: List[asyncio.Task] = []
        self._shutdown_flag: bool = False
        
        # 指标
        self._metrics = {
            "total_submitted": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_retries": 0,
        }
        
        logger.info(
            "TaskQueue 初始化完成 (max_workers=%d, max_retries=%d, policy=%s)",
            max_workers, max_retries, retry_policy.value,
        )
    
    async def start(self):
        """启动队列处理器"""
        logger.info("启动任务队列处理器...")
        self._shutdown_flag = False
        
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(worker)
        
        logger.info("已启动 %d 个工作线程", self.max_workers)
    
    async def stop(self, wait: bool = True):
        """停止队列处理器
        
        Args:
            wait: 是否等待当前任务完成
        """
        logger.info("停止任务队列处理器...")
        self._shutdown_flag = True
        
        if wait:
            for worker in self._workers:
                worker.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        logger.info("任务队列处理器已停止")
    
    async def submit(
        self,
        action: str,
        params: Dict[str, Any],
        max_retries: Optional[int] = None,
        retry_policy: Optional[RetryPolicy] = None,
        retry_delay: Optional[float] = None,
        priority: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """提交任务到队列
        
        Args:
            action: 动作类型
            params: 动作参数
            max_retries: 最大重试次数（覆盖默认值）
            retry_policy: 重试策略（覆盖默认值）
            retry_delay: 初始重试延迟（覆盖默认值）
            priority: 优先级（1-10）
            metadata: 元数据
            
        Returns:
            任务 ID
        """
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        
        task = Task(
            id=task_id,
            action=action,
            params=params,
            max_retries=max_retries or self.max_retries,
            retry_policy=retry_policy or self.retry_policy,
            retry_delay=retry_delay or self.retry_delay,
            priority=priority,
            metadata=metadata or {},
        )
        
        self._tasks[task_id] = task
        self._metrics["total_submitted"] += 1
        
        # 使用负优先级，因为 PriorityQueue 是最小堆
        await self._queue.put((-priority, task_id))
        
        logger.info(
            "任务已提交: %s (action=%s, priority=%d, max_retries=%d)",
            task_id, action, priority, task.max_retries,
        )
        
        return task_id
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        return self._tasks.get(task_id)
    
    async def get_dead_letter_tasks(self) -> List[Task]:
        """获取死信队列中的任务"""
        tasks = []
        while not self._dead_letter_queue.empty():
            task_id = await self._dead_letter_queue.get()
            task = self._tasks.get(task_id)
            if task:
                tasks.append(task)
        return tasks
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取队列指标"""
        return {
            **self._metrics,
            "queue_size": self._queue.qsize(),
            "dead_letter_size": self._dead_letter_queue.qsize(),
            "active_workers": len(self._workers),
        }
    
    async def _worker(self, name: str):
        """工作线程"""
        logger.info("工作线程启动: %s", name)
        
        while not self._shutdown_flag:
            try:
                # 从队列获取任务
                priority, task_id = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0,
                )
                
                task = self._tasks.get(task_id)
                if not task:
                    logger.warning("任务不存在: %s", task_id)
                    continue
                
                # 执行任务
                await self._execute_task(task)
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("工作线程被取消: %s", name)
                break
            except Exception as e:
                logger.error("工作线程异常: %s - %s", name, e)
        
        logger.info("工作线程退出: %s", name)
    
    async def _execute_task(self, task: Task):
        """执行任务"""
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        
        logger.info(
            "开始执行任务: %s (action=%s, retry=%d/%d)",
            task.id, task.action, task.retry_count, task.max_retries,
        )
        
        try:
            # 执行任务
            result = await self._run_task(task)
            
            # 成功
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            self._metrics["total_completed"] += 1
            
            logger.info(
                "任务执行成功: %s (耗时: %.2fs)",
                task.id, task.completed_at - task.started_at,
            )
            
        except Exception as e:
            # 失败
            task.error = str(e)
            task.retry_count += 1
            self._metrics["total_retries"] += 1
            
            logger.warning(
                "任务执行失败: %s (错误: %s, 重试: %d/%d)",
                task.id, e, task.retry_count, task.max_retries,
            )
            
            # 判断是否可以重试
            if self._can_retry(task, e):
                await self._retry_task(task)
            else:
                await self._dead_letter(task)
    
    async def _run_task(self, task: Task) -> Any:
        """运行任务（调用实际技能）"""
        try:
            # 导入工具管理器
            from tools.tool_manager import ToolManager
            
            tm = ToolManager.get_instance()
            
            # 调用技能（同步调用，用 to_thread 包装）
            result = await asyncio.to_thread(tm.execute, task.action, **task.params)
            
            if not isinstance(result, dict):
                result = {"success": True, "result": str(result)}
            
            return result
            
        except Exception as e:
            logger.error("技能执行失败: %s - %s", task.action, e)
            raise
    
    def _can_retry(self, task: Task, error: Exception) -> bool:
        """判断任务是否可以重试"""
        # 检查重试次数
        if task.retry_count >= task.max_retries:
            return False
        
        # 检查错误类型（某些错误不应该重试）
        non_retryable_errors = [
            "权限错误",
            "参数错误",
            "配置错误",
        ]
        
        error_msg = str(error)
        for err in non_retryable_errors:
            if err in error_msg:
                return False
        
        return True
    
    async def _retry_task(self, task: Task):
        """重试任务"""
        # 计算重试延迟
        delay = self._calculate_retry_delay(task)
        
        logger.info(
            "任务将在 %.2fs 后重试: %s (策略: %s)",
            delay, task.id, task.retry_policy.value,
        )
        
        # 等待延迟
        await asyncio.sleep(delay)
        
        # 重新入队
        task.status = TaskStatus.PENDING
        await self._queue.put((-task.priority, task.id))
    
    async def _dead_letter(self, task: Task):
        """任务进入死信队列"""
        task.status = TaskStatus.DEAD_LETTER
        task.completed_at = time.time()
        self._metrics["total_failed"] += 1
        
        await self._dead_letter_queue.put(task.id)
        
        logger.error(
            "任务进入死信队列: %s (重试次数: %d, 错误: %s)",
            task.id, task.retry_count, task.error,
        )
    
    def _calculate_retry_delay(self, task: Task) -> float:
        """计算重试延迟"""
        if task.retry_policy == RetryPolicy.FIXED:
            return task.retry_delay
        
        elif task.retry_policy == RetryPolicy.EXPONENTIAL:
            return task.retry_delay * (2 ** (task.retry_count - 1))
        
        elif task.retry_policy == RetryPolicy.LINEAR:
            return task.retry_delay * task.retry_count
        
        return task.retry_delay


# 全局实例
task_queue = TaskQueue(
    max_workers=5,
    max_retries=3,
    retry_policy=RetryPolicy.EXPONENTIAL,
    retry_delay=1.0,
)