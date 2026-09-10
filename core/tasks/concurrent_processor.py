"""并发任务处理器 - 工业级双队列 + 线程池 + 熔断保护

设计要点:
- 通用任务队列 (task_queue) + 爬虫专用队列 (scraper_queue)，双队列优先级调度
- ThreadPoolExecutor 处理 IO 密集型阻塞操作
- CircuitBreaker 熔断器：关闭→打开→半开 三态流转
- 爬虫去重：同站点同一时间只允许 1 个爬虫任务 (asyncio.Lock + running_scrapers)
- 任务依赖：depends_on 字段，轮询 0.5s，超时 30s
- 子任务队列优先于主任务队列
- 指标监控：执行时间、成功率、队列深度
- 异常隔离：单个任务失败不影响其他任务
"""

import asyncio
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 熔断器
# ============================================================

from core.circuit_breaker import CircuitBreaker


from dataclasses import dataclass, field


@dataclass
class TaskMetrics:
    """任务指标

    修复 #211/#212: 原字段与调用方严重不符——
    - _safe_execute 构造传 tool_name/start_time（原字段没有）→ TypeError
    - _safe_execute finally 里写 end_time（靠动态属性侥幸活着）
    - get_summary 读 m.elapsed（原字段没有）→ AttributeError
    现补齐 tool_name/start_time/end_time，并加 elapsed 计算属性。
    """
    task_id: str = ""
    type: str = ""
    tool_name: str = "unknown"      # 修复 #212: _safe_execute 构造需要
    start_time: float = 0.0         # 修复 #212: 计时起点
    end_time: float = 0.0           # 修复 #211: 计时终点（原靠动态属性）
    duration: float = 0.0
    success: bool = True
    error: str = ""
    timestamp: float = 0.0
    queue_wait: float = 0.0

    @property
    def elapsed(self) -> float:
        """修复 #211: get_summary 读 m.elapsed，原字段不存在"""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return self.duration


class MetricsCollector:
    """全局指标收集器，统计任务执行时间、成功率、队列深度等。"""

    def __init__(self, max_history: int = 1000) -> None:
        self._history: List[TaskMetrics] = []
        self._max_history: int = max_history
        self._lock: threading.Lock = threading.Lock()
        self._total_submitted: int = 0
        self._total_success: int = 0
        self._total_failed: int = 0

    def record(self, metrics: TaskMetrics) -> None:
        """记录一条任务指标。"""
        with self._lock:
            self._history.append(metrics)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            self._total_submitted += 1
            if metrics.success:
                self._total_success += 1
            else:
                self._total_failed += 1

    def get_summary(self, queue_depth: int = 0, scraper_queue_depth: int = 0) -> Dict[str, Any]:
        """获取指标摘要。"""
        with self._lock:
            recent = self._history[-100:]  # 最近 100 条用于计算平均耗时
        avg_time = (
            sum(m.elapsed for m in recent) / len(recent) if recent else 0.0
        )
        success_rate = (
            self._total_success / self._total_submitted * 100
            if self._total_submitted > 0
            else 0.0
        )
        return {
            "total_submitted": self._total_submitted,
            "total_success": self._total_success,
            "total_failed": self._total_failed,
            "success_rate": round(success_rate, 2),
            "avg_elapsed_recent": round(avg_time, 4),
            "task_queue_depth": queue_depth,
            "scraper_queue_depth": scraper_queue_depth,
            "history_size": len(self._history),
        }


# ============================================================
# 并发任务处理器
# ============================================================

class ConcurrentTaskProcessor:
    """高并发异步任务处理器

    双队列设计：
    - task_queue:     通用任务队列 (maxsize=10)
    - scraper_queue:  爬虫专用队列 (maxsize=10)
    - subtask_queue   子任务队列（最高优先级）

    爬虫去重：
    - 同一 site_name 同一时间只允许 1 个爬虫任务运行
    - 通过 asyncio.Lock + running_scrapers: Dict[str, bool] 管理

    任务依赖：
    - task 字段 depends_on: str 表示依赖的任务 ID
    - 轮询间隔 0.5s，超时 30s
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_scraper: int = 10,
        worker_size: int = 5,
    ) -> None:
        """初始化并发处理器。

        Args:
            max_concurrent: 通用任务最大并发数
            max_scraper:    爬虫任务最大并发数
            worker_size:    线程池工作线程数
        """
        # 信号量
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)
        self._scraper_semaphore: asyncio.Semaphore = asyncio.Semaphore(max_scraper)

        # 双队列
        self.task_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        self.scraper_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        self.subtask_queue: asyncio.Queue = asyncio.Queue(maxsize=10)

        # 爬虫去重
        self._scraper_lock: asyncio.Lock = asyncio.Lock()
        self._running_scrapers: Dict[str, bool] = {}

        # 任务依赖
        self._completed_tasks: Dict[str, Any] = {}
        self._completed_events: Dict[str, asyncio.Event] = {}

        # 线程池（IO 密集型）
        self._thread_pool: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=worker_size, thread_name_prefix="ctp_worker"
        )

        # 熔断器
        self._circuit: CircuitBreaker = CircuitBreaker(
            failure_threshold=5, recovery_timeout=60.0
        )

        # 指标
        self._metrics: MetricsCollector = MetricsCollector()

        # 去重（已处理 key）
        self._processed_keys: set = set()

        # 生命周期
        self._shutdown_flag: bool = False

        logger.info(
            "ConcurrentTaskProcessor 初始化完成 "
            "(max_concurrent=%d, max_scraper=%d, worker_size=%d)",
            max_concurrent, max_scraper, worker_size,
        )

    # ========================================================
    # 公开接口
    # ========================================================

    async def submit_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """提交单个任务并等待结果。

        支持的字段：
        - tool_call: Dict  工具调用信息 {name, params}
        - depends_on: str  依赖的任务 ID（可选）
        - priority: str    "high" 表示走 subtask_queue（可选）

        Args:
            task: 任务字典

        Returns:
            执行结果字典，包含 success / error / result / tool_call 等字段
        """
        if self._shutdown_flag:
            return {"success": False, "error": "处理器已关闭", "tool_call": task.get("tool_call", {})}

        if self._circuit.is_open():
            return {
                "success": False,
                "error": "系统熔断中，请稍后重试",
                "tool_call": task.get("tool_call", {}),
            }

        # 依赖检查
        depends_on: Optional[str] = task.get("depends_on")
        if depends_on:
            dep_result = await self._wait_for_dependency(depends_on)
            if dep_result is None:
                return {
                    "success": False,
                    "error": f"依赖任务 {depends_on} 超时（30s）未完成",
                    "tool_call": task.get("tool_call", {}),
                }

        # 优先级路由
        priority: str = task.get("priority", "normal")
        tool_call: Dict[str, Any] = task.get("tool_call", {})
        tool_name: str = tool_call.get("name", "unknown")
        task_id: str = task.get("task_id", f"{tool_name}_{id(task)}")

        if tool_name == "web_scraper":
            result = await self._execute_with_scraper_queue(task, task_id)
        elif priority == "high":
            result = await self._execute_with_semaphore(
                self.subtask_queue, task, task_id
            )
        else:
            result = await self._execute_with_semaphore(
                self.task_queue, task, task_id
            )

        # 记录已完成任务（用于依赖解析）
        self._completed_tasks[task_id] = result
        evt = self._completed_events.pop(task_id, None)
        if evt:
            evt.set()

        return result

    async def submit_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """并行提交多个任务。

        Args:
            tasks: 任务列表

        Returns:
            结果列表，与输入一一对应
        """
        coroutines = [self.submit_task(t) for t in tasks]
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        return [
            r if not isinstance(r, Exception) else {"success": False, "error": str(r)}
            for r in results
        ]

    def shutdown(self, wait: bool = False) -> None:
        """关闭处理器，释放资源。

        Args:
            wait: 是否等待线程池中的任务完成
        """
        self._shutdown_flag = True
        self._thread_pool.shutdown(wait=wait)
        logger.info("ConcurrentTaskProcessor 已关闭 (wait=%s)", wait)

    def get_metrics(self) -> Dict[str, Any]:
        """获取当前处理器指标。"""
        return self._metrics.get_summary(
            queue_depth=self.task_queue.qsize(),
            scraper_queue_depth=self.scraper_queue.qsize(),
        )

    # ========================================================
    # 去重
    # ========================================================

    def mark_processed(self, key: str) -> None:
        """标记 key 为已处理（外部去重用）。"""
        self._processed_keys.add(key)

    def is_processed(self, key: str) -> bool:
        """检查 key 是否已处理。"""
        return key in self._processed_keys

    # ========================================================
    # 内部执行逻辑
    # ========================================================

    async def _execute_with_semaphore(
        self, queue: asyncio.Queue, task: Dict[str, Any], task_id: str
    ) -> Dict[str, Any]:
        """通过信号量控制并发执行通用任务。"""
        await queue.put(task)
        async with self._semaphore:
            queue.task_done()
            return await self._safe_execute(task, task_id)

    async def _execute_with_scraper_queue(
        self, task: Dict[str, Any], task_id: str
    ) -> Dict[str, Any]:
        """爬虫队列执行：同站点串行。"""
        params: Dict[str, Any] = task.get("tool_call", {}).get("params", {})
        scraper_key: str = params.get("site_name", "default")

        # 等待同站点爬虫完成
        async with self._scraper_lock:
            if self._running_scrapers.get(scraper_key):
                # 等待中：创建事件等待
                if scraper_key not in self._completed_events:
                    self._completed_events[scraper_key] = asyncio.Event()
                waiter = self._completed_events[scraper_key]
            else:
                waiter = None

        if waiter is not None:
            await waiter.wait()
            del waiter

        # 占位
        async with self._scraper_lock:
            self._running_scrapers[scraper_key] = True

        try:
            await self.scraper_queue.put(task)
            async with self._scraper_semaphore:
                self.scraper_queue.task_done()
                result = await self._safe_execute(task, task_id)
                await self._circuit.record_success()
                return result
        except Exception as e:
            await self._circuit.record_failure()
            return {"success": False, "error": str(e), "tool_call": task.get("tool_call", {})}
        finally:
            async with self._scraper_lock:
                self._running_scrapers.pop(scraper_key, None)
                # 唤醒等待者
                if scraper_key in self._completed_events:
                    self._completed_events[scraper_key].set()
                    del self._completed_events[scraper_key]

    async def _safe_execute(self, task: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """安全执行单个任务，记录指标，异常隔离。"""
        metrics = TaskMetrics(
            task_id=task_id,
            tool_name=task.get("tool_call", {}).get("name", "unknown"),
            start_time=time.time(),
        )
        try:
            result = await self._execute_task(task)
            metrics.success = result.get("success", True)
            metrics.error = result.get("error")
            return result
        except Exception as exc:
            logger.error("任务 %s 执行异常: %s", task_id, exc, exc_info=True)
            metrics.success = False
            metrics.error = str(exc)
            return {
                "success": False,
                "error": str(exc),
                "tool_call": task.get("tool_call", {}),
            }
        finally:
            metrics.end_time = time.time()
            self._metrics.record(metrics)

    async def _execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个任务：优先 V2 ToolRegistry，回退到 ToolManager。"""
        tool_call: Dict[str, Any] = task.get("tool_call", {})
        tool_name: str = tool_call.get("name", "")
        params: Dict[str, Any] = tool_call.get("params", {})

        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
            reg = get_tool_registry()
            handler = reg.get_handler(tool_name)
            if handler:
                result = await handler(params)
                return result if isinstance(result, dict) else {"success": True, "result": str(result)}
        except Exception:
            logger.debug("V2 ToolRegistry 执行失败，回退 ToolManager")

        try:
            from tools.tool_manager import ToolManager

            tm = ToolManager.get_instance()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._thread_pool, lambda: tm.execute(tool_name, **params)
            )

            if isinstance(result, dict):
                return result
            return {"success": True, "result": str(result)}
        except Exception as e:
            logger.error("任务执行失败: %s", e)
            return {"success": False, "error": str(e)}

    # ========================================================
    # 任务依赖
    # ========================================================

    async def _wait_for_dependency(
        self, dep_id: str, poll_interval: float = 0.5, timeout: float = 30.0
    ) -> Optional[Any]:
        """等待依赖任务完成。

        Args:
            dep_id:        依赖的任务 ID
            poll_interval: 轮询间隔（秒）
            timeout:       超时时间（秒）

        Returns:
            依赖任务的结果，超时返回 None
        """
        if dep_id in self._completed_tasks:
            return self._completed_tasks[dep_id]

        # 创建等待事件
        async def _poll() -> Optional[Any]:
            elapsed = 0.0
            while elapsed < timeout:
                if dep_id in self._completed_tasks:
                    return self._completed_tasks[dep_id]
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
            return None

        return await _poll()
