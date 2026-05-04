"""
Prometheus监控集成 - 实现关键指标的实时采集与可视化监控

功能：
1. Agent性能指标收集
2. 任务执行指标收集
3. 系统资源指标收集
4. Prometheus端点暴露
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from prometheus_client import (
        Counter, Gauge, Histogram, Summary,
        start_http_server, CollectorRegistry
    )
except ImportError:
    prometheus_client = None
    Counter = Gauge = Histogram = Summary = start_http_server = CollectorRegistry = None

logger = logging.getLogger(__name__)


@dataclass
class MetricsConfig:
    """监控配置"""
    port: int = 9090
    namespace: str = "multi_agent"
    subsystem: str = "core"


class AgentMetrics:
    """Agent相关指标"""

    def __init__(self, registry: CollectorRegistry, namespace: str, subsystem: str):
        if not Counter or not Gauge:
            logger.warning("Prometheus client not installed")
            return

        # Agent计数
        self.agent_count = Gauge(
            "agent_count",
            "Number of agents",
            ["agent_type", "state"],
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # Agent负载
        self.agent_load = Gauge(
            "agent_load",
            "Agent load percentage",
            ["agent_id", "agent_type"],
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # Agent执行时间
        self.agent_execution_time = Histogram(
            "agent_execution_time_seconds",
            "Agent execution time",
            ["agent_id", "agent_type"],
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # Agent成功/失败计数
        self.agent_success_count = Counter(
            "agent_success_count",
            "Agent success count",
            ["agent_id", "agent_type"],
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        self.agent_failure_count = Counter(
            "agent_failure_count",
            "Agent failure count",
            ["agent_id", "agent_type"],
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )


class TaskMetrics:
    """任务相关指标"""

    def __init__(self, registry: CollectorRegistry, namespace: str, subsystem: str):
        if not Counter or not Gauge:
            logger.warning("Prometheus client not installed")
            return

        # 任务计数
        self.task_count = Gauge(
            "task_count",
            "Number of tasks",
            ["status"],
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # 任务执行时间
        self.task_execution_time = Histogram(
            "task_execution_time_seconds",
            "Task execution time",
            ["task_type"],
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # 任务成功率
        self.task_success_rate = Summary(
            "task_success_rate",
            "Task success rate",
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # 任务队列长度
        self.task_queue_length = Gauge(
            "task_queue_length",
            "Task queue length",
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )


class SystemMetrics:
    """系统资源指标"""

    def __init__(self, registry: CollectorRegistry, namespace: str, subsystem: str):
        if not Gauge:
            logger.warning("Prometheus client not installed")
            return

        # CPU使用率
        self.cpu_usage = Gauge(
            "cpu_usage_percent",
            "CPU usage percentage",
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # 内存使用率
        self.memory_usage = Gauge(
            "memory_usage_percent",
            "Memory usage percentage",
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # 内存使用量
        self.memory_used = Gauge(
            "memory_used_bytes",
            "Memory used in bytes",
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # 线程数
        self.thread_count = Gauge(
            "thread_count",
            "Number of threads",
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )


class ReflectionMetrics:
    """反思机制指标"""

    def __init__(self, registry: CollectorRegistry, namespace: str, subsystem: str):
        if not Counter or not Histogram:
            logger.warning("Prometheus client not installed")
            return

        # 反思次数
        self.reflection_count = Counter(
            "reflection_count",
            "Number of reflections",
            ["decision"],
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )

        # 反思时间
        self.reflection_time = Histogram(
            "reflection_time_seconds",
            "Reflection time",
            namespace=namespace,
            subsystem=subsystem,
            registry=registry
        )


class MetricsCollector:
    """指标收集器"""

    def __init__(self, config: Optional[MetricsConfig] = None):
        self.config = config or MetricsConfig()
        self.registry = CollectorRegistry()

        # 初始化指标
        self.agent_metrics = AgentMetrics(
            self.registry,
            self.config.namespace,
            self.config.subsystem
        )
        self.task_metrics = TaskMetrics(
            self.registry,
            self.config.namespace,
            self.config.subsystem
        )
        self.system_metrics = SystemMetrics(
            self.registry,
            self.config.namespace,
            self.config.subsystem
        )
        self.reflection_metrics = ReflectionMetrics(
            self.registry,
            self.config.namespace,
            self.config.subsystem
        )

        self._collecting = False
        self._collect_task = None

    async def start(self) -> bool:
        """启动监控"""
        if not start_http_server:
            logger.error("Prometheus client not installed")
            return False

        try:
            # 启动HTTP服务器
            start_http_server(
                self.config.port,
                registry=self.registry
            )
            logger.info(f"Prometheus监控已启动: http://localhost:{self.config.port}/metrics")

            # 启动系统指标收集任务
            self._collecting = True
            self._collect_task = asyncio.create_task(self._collect_system_metrics())

            return True

        except Exception as e:
            logger.error(f"启动监控失败: {e}")
            return False

    async def stop(self) -> None:
        """停止监控"""
        self._collecting = False

        if self._collect_task:
            self._collect_task.cancel()

        logger.info("Prometheus监控已停止")

    async def _collect_system_metrics(self):
        """定期收集系统指标"""
        while self._collecting:
            try:
                # 获取系统指标
                import psutil

                # CPU使用率
                cpu_percent = psutil.cpu_percent()
                self.system_metrics.cpu_usage.set(cpu_percent)

                # 内存信息
                mem = psutil.virtual_memory()
                self.system_metrics.memory_usage.set(mem.percent)
                self.system_metrics.memory_used.set(mem.used)

                # 线程数
                self.system_metrics.thread_count.set(psutil.Process().num_threads())

            except ImportError:
                logger.warning("psutil not installed, skipping system metrics")

            except Exception as e:
                logger.error(f"收集系统指标失败: {e}")

            await asyncio.sleep(5)  # 每5秒收集一次

    def record_agent_start(self, agent_id: str, agent_type: str):
        """记录Agent启动"""
        if self.agent_metrics.agent_count:
            self.agent_metrics.agent_count.labels(
                agent_type=agent_type,
                state="running"
            ).inc()

    def record_agent_stop(self, agent_id: str, agent_type: str):
        """记录Agent停止"""
        if self.agent_metrics.agent_count:
            self.agent_metrics.agent_count.labels(
                agent_type=agent_type,
                state="running"
            ).dec()

    def record_agent_execution(
        self,
        agent_id: str,
        agent_type: str,
        duration: float,
        success: bool
    ):
        """记录Agent执行"""
        if self.agent_metrics.agent_execution_time:
            self.agent_metrics.agent_execution_time.labels(
                agent_id=agent_id,
                agent_type=agent_type
            ).observe(duration)

        if success:
            if self.agent_metrics.agent_success_count:
                self.agent_metrics.agent_success_count.labels(
                    agent_id=agent_id,
                    agent_type=agent_type
                ).inc()
        else:
            if self.agent_metrics.agent_failure_count:
                self.agent_metrics.agent_failure_count.labels(
                    agent_id=agent_id,
                    agent_type=agent_type
                ).inc()

    def record_agent_load(self, agent_id: str, agent_type: str, load: float):
        """记录Agent负载"""
        if self.agent_metrics.agent_load:
            self.agent_metrics.agent_load.labels(
                agent_id=agent_id,
                agent_type=agent_type
            ).set(load)

    def record_task_start(self, task_type: str):
        """记录任务开始"""
        if self.task_metrics.task_count:
            self.task_metrics.task_count.labels(status="running").inc()
            self.task_metrics.task_count.labels(status="pending").dec()

    def record_task_complete(
        self,
        task_type: str,
        duration: float,
        success: bool
    ):
        """记录任务完成"""
        if self.task_metrics.task_count:
            self.task_metrics.task_count.labels(status="running").dec()

            if success:
                self.task_metrics.task_count.labels(status="completed").inc()
            else:
                self.task_metrics.task_count.labels(status="failed").inc()

        if self.task_metrics.task_execution_time:
            self.task_metrics.task_execution_time.labels(
                task_type=task_type
            ).observe(duration)

        if self.task_metrics.task_success_rate:
            self.task_metrics.task_success_rate.observe(1.0 if success else 0.0)

    def record_task_queue_length(self, length: int):
        """记录任务队列长度"""
        if self.task_metrics.task_queue_length:
            self.task_metrics.task_queue_length.set(length)

    def record_reflection(self, decision: str, duration: float):
        """记录反思"""
        if self.reflection_metrics.reflection_count:
            self.reflection_metrics.reflection_count.labels(
                decision=decision
            ).inc()

        if self.reflection_metrics.reflection_time:
            self.reflection_metrics.reflection_time.observe(duration)

    def get_metrics(self) -> Dict[str, Any]:
        """获取当前指标"""
        return {
            "agent_metrics": {
                "type": "prometheus",
                "endpoint": f"http://localhost:{self.config.port}/metrics"
            },
            "system_metrics": {
                "type": "prometheus",
                "endpoint": f"http://localhost:{self.config.port}/metrics"
            }
        }
