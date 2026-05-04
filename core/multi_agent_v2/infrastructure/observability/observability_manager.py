"""
可观测性层 - 全链路追踪、指标收集、告警集成

包含：
1. 追踪管理器 - 全链路追踪
2. 指标收集器 - 性能指标
3. 告警集成 - 与告警系统集成
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class SpanStatus(Enum):
    """Span状态"""
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Span:
    """Span - 追踪的基本单元"""
    span_id: str
    trace_id: str
    parent_id: Optional[str]
    name: str
    service_name: str
    start_time: float
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.STARTED
    tags: Dict[str, str] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceContext:
    """追踪上下文"""
    trace_id: str
    root_span_id: str
    created_at: float
    finished_at: Optional[float] = None
    spans: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """事件"""
    event_id: str
    name: str
    timestamp: float
    attributes: Dict[str, Any] = field(default_factory=dict)


class TraceManager:
    """追踪管理器 - 全链路追踪"""

    def __init__(self):
        self.traces: Dict[str, TraceContext] = {}
        self.spans: Dict[str, Span] = {}
        self.trace_id_counter = 0

        self._lock = asyncio.Lock()

        logger.info("追踪管理器初始化完成")

    def generate_trace_id(self) -> str:
        """生成追踪ID"""
        self.trace_id_counter += 1
        return f"trace_{self.trace_id_counter}_{int(time.time())}"

    async def start_trace(self, request_id: Optional[str] = None, metadata: Optional[Dict] = None) -> TraceContext:
        """开始追踪"""
        trace_id = request_id or self.generate_trace_id()

        root_span_id = f"span_{uuid.uuid4().hex[:8]}"

        context = TraceContext(
            trace_id=trace_id,
            root_span_id=root_span_id,
            created_at=time.time(),
            metadata=metadata or {}
        )

        async with self._lock:
            self.traces[trace_id] = context

        logger.info(f"开始追踪: {trace_id}")

        return context

    async def create_span(
        self,
        trace_id: str,
        span_name: str,
        service_name: str,
        parent_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> Span:
        """创建Span"""
        span_id = f"span_{uuid.uuid4().hex[:8]}"

        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_id=parent_id,
            name=span_name,
            service_name=service_name,
            start_time=time.time(),
            tags=tags or {}
        )

        async with self._lock:
            self.spans[span_id] = span

            if trace_id in self.traces:
                self.traces[trace_id].spans.append(span_id)

        logger.debug(f"创建Span: {span_id} (trace: {trace_id})")

        return span

    async def record_event(self, span_id: str, event_name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """记录事件"""
        if span_id not in self.spans:
            return

        span = self.spans[span_id]

        event = {
            "name": event_name,
            "timestamp": time.time(),
            "attributes": attributes or {}
        }

        span.logs.append(event)

        logger.debug(f"记录事件: {span_id} - {event_name}")

    async def add_tag(self, span_id: str, key: str, value: str) -> None:
        """添加标签"""
        if span_id in self.spans:
            self.spans[span_id].tags[key] = value

    async def set_attribute(self, span_id: str, key: str, value: Any) -> None:
        """设置属性"""
        if span_id in self.spans:
            self.spans[span_id].attributes[key] = value

    async def finish_span(self, span_id: str, status: SpanStatus = SpanStatus.COMPLETED) -> None:
        """结束Span"""
        if span_id not in self.spans:
            return

        span = self.spans[span_id]
        span.end_time = time.time()
        span.status = status

        logger.debug(f"结束Span: {span_id}, 状态: {status.value}, 耗时: {span.end_time - span.start_time:.3f}s")

    async def finish_trace(self, trace_id: str) -> Optional[TraceContext]:
        """结束追踪"""
        if trace_id not in self.traces:
            return None

        context = self.traces[trace_id]
        context.finished_at = time.time()

        duration = context.finished_at - context.created_at

        logger.info(f"追踪完成: {trace_id}, 耗时: {duration:.3f}s, Spans: {len(context.spans)}")

        return context

    async def get_trace(self, trace_id: str) -> Optional[TraceContext]:
        """获取追踪"""
        return self.traces.get(trace_id)

    async def get_span(self, span_id: str) -> Optional[Span]:
        """获取Span"""
        return self.spans.get(span_id)

    async def get_trace_tree(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """获取追踪树"""
        context = self.traces.get(trace_id)

        if not context:
            return None

        spans = [self.spans[sid] for sid in context.spans if sid in self.spans]

        return {
            "trace_id": trace_id,
            "created_at": context.created_at,
            "finished_at": context.finished_at,
            "duration": context.finished_at - context.created_at if context.finished_at else None,
            "spans": [
                {
                    "span_id": s.span_id,
                    "parent_id": s.parent_id,
                    "name": s.name,
                    "service_name": s.service_name,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "duration": s.end_time - s.start_time if s.end_time else None,
                    "status": s.status.value,
                    "tags": s.tags,
                    "logs": s.logs,
                    "attributes": s.attributes
                }
                for s in spans
            ]
        }

    async def cleanup_old_traces(self, max_age_hours: int = 24) -> int:
        """清理旧的追踪"""
        cutoff_time = time.time() - (max_age_hours * 3600)
        cleaned = 0

        async with self._lock:
            old_traces = [
                tid for tid, ctx in self.traces.items()
                if ctx.finished_at and ctx.finished_at < cutoff_time
            ]

            for trace_id in old_traces:
                ctx = self.traces[trace_id]

                for span_id in ctx.spans:
                    if span_id in self.spans:
                        del self.spans[span_id]

                del self.traces[trace_id]
                cleaned += 1

        if cleaned > 0:
            logger.info(f"清理了 {cleaned} 个旧追踪")

        return cleaned


class MetricsCollector:
    """指标收集器"""

    # Agent指标
    AGENT_METRICS = [
        "tasks_completed",
        "tasks_failed",
        "avg_execution_time",
        "current_load",
        "success_rate"
    ]

    # 系统指标
    SYSTEM_METRICS = [
        "active_agents",
        "pending_tasks",
        "avg_task_duration",
        "throughput"
    ]

    def __init__(self):
        self.agent_metrics: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.system_metrics: Dict[str, float] = defaultdict(float)
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.histograms: Dict[str, List[float]] = defaultdict(list)

        logger.info("指标收集器初始化完成")

    async def record_agent_metric(self, agent_id: str, metric: str, value: float) -> None:
        """记录Agent指标"""
        self.agent_metrics[agent_id][metric] = value

    async def record_system_metric(self, metric: str, value: float) -> None:
        """记录系统指标"""
        self.system_metrics[metric] = value

    async def increment_counter(self, name: str, value: int = 1) -> None:
        """增加计数器"""
        self.counters[name] += value

    async def set_gauge(self, name: str, value: float) -> None:
        """设置仪表值"""
        self.gauges[name] = value

    async def record_histogram(self, name: str, value: float) -> None:
        """记录直方图值"""
        self.histograms[name].append(value)

        if len(self.histograms[name]) > 1000:
            self.histograms[name] = self.histograms[name][-500:]

    async def get_agent_metrics(self, agent_id: str) -> Dict[str, float]:
        """获取Agent指标"""
        return dict(self.agent_metrics.get(agent_id, {}))

    async def get_system_metrics(self) -> Dict[str, float]:
        """获取系统指标"""
        return dict(self.system_metrics)

    async def get_counters(self) -> Dict[str, int]:
        """获取计数器"""
        return dict(self.counters)

    async def get_gauges(self) -> Dict[str, float]:
        """获取仪表"""
        return dict(self.gauges)

    async def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """获取直方图统计"""
        values = self.histograms.get(name, [])

        if not values:
            return {}

        sorted_values = sorted(values)
        count = len(sorted_values)

        return {
            "count": count,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "mean": sum(sorted_values) / count,
            "p50": sorted_values[int(count * 0.5)],
            "p95": sorted_values[int(count * 0.95)],
            "p99": sorted_values[int(count * 0.99)]
        }

    async def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        return {
            "agent_metrics": dict(self.agent_metrics),
            "system_metrics": dict(self.system_metrics),
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {
                name: await self.get_histogram_stats(name)
                for name in self.histograms.keys()
            }
        }

    async def reset_agent_metrics(self, agent_id: str) -> None:
        """重置Agent指标"""
        if agent_id in self.agent_metrics:
            del self.agent_metrics[agent_id]


class AlertIntegration:
    """告警集成 - 与告警系统集成"""

    def __init__(self, alert_manager: Optional[Any] = None):
        self.alert_manager = alert_manager
        self.alert_thresholds: Dict[str, Dict[str, float]] = {
            "agent_load": {"warning": 0.7, "critical": 0.9},
            "task_duration": {"warning": 60.0, "critical": 120.0},
            "error_rate": {"warning": 0.05, "critical": 0.1},
            "agent_health": {"warning": 0.5, "critical": 0.3}
        }

        logger.info("告警集成初始化完成")

    async def check_and_alert(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """检查指标并告警"""
        if metric_name not in self.alert_thresholds:
            return

        thresholds = self.alert_thresholds[metric_name]

        alert_level = None
        alert_message = None

        if value >= thresholds["critical"]:
            alert_level = "critical"
            alert_message = f"{metric_name} 超过critical阈值: {value}"
        elif value >= thresholds["warning"]:
            alert_level = "warning"
            alert_message = f"{metric_name} 超过warning阈值: {value}"

        if alert_level and self.alert_manager:
            logger.warning(alert_message)

    def set_threshold(self, metric_name: str, warning: float, critical: float) -> None:
        """设置阈值"""
        self.alert_thresholds[metric_name] = {
            "warning": warning,
            "critical": critical
        }


class ObservabilityManager:
    """可观测性管理器 - 统一管理追踪、指标、告警"""

    def __init__(self):
        self.trace_manager = TraceManager()
        self.metrics_collector = MetricsCollector()
        self.alert_integration = AlertIntegration()

        logger.info("可观测性管理器初始化完成")

    async def create_trace_context(self, request_id: Optional[str] = None, metadata: Optional[Dict] = None) -> TraceContext:
        """创建追踪上下文"""
        return await self.trace_manager.start_trace(request_id, metadata)

    async def create_span(
        self,
        trace_id: str,
        span_name: str,
        service_name: str,
        parent_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> Span:
        """创建Span"""
        return await self.trace_manager.create_span(trace_id, span_name, service_name, parent_id, tags)

    async def record_metric(
        self,
        metric_type: str,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """记录指标"""
        if metric_type == "agent":
            agent_id = tags.get("agent_id", "unknown") if tags else "unknown"
            await self.metrics_collector.record_agent_metric(agent_id, metric_name, value)
        elif metric_type == "system":
            await self.metrics_collector.record_system_metric(metric_name, value)
        elif metric_type == "counter":
            await self.metrics_collector.increment_counter(metric_name, int(value))
        elif metric_type == "gauge":
            await self.metrics_collector.set_gauge(metric_name, value)
        elif metric_type == "histogram":
            await self.metrics_collector.record_histogram(metric_name, value)

        await self.alert_integration.check_and_alert(metric_name, value, tags)

    async def get_full_observability(self) -> Dict[str, Any]:
        """获取完整的可观测性数据"""
        return {
            "traces": {
                "active_traces": len(self.trace_manager.traces),
                "active_spans": len(self.trace_manager.spans)
            },
            "metrics": await self.metrics_collector.get_all_metrics(),
            "alert_thresholds": self.alert_integration.alert_thresholds
        }

    async def cleanup(self, max_age_hours: int = 24) -> None:
        """清理旧数据"""
        await self.trace_manager.cleanup_old_traces(max_age_hours)
