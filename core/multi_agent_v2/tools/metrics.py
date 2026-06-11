"""
执行日志和性能指标 — 工具调用追踪 + 统计分析

提供：
- 工具调用日志
- 性能指标（延迟、成功率、吞吐量）
- 统计分析
- 可视化报告
"""

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """工具调用记录"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool
    start_time: float
    end_time: float
    duration: float
    error: Optional[str] = None
    quality: str = "success"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """性能指标"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration: float = 0.0
    avg_duration: float = 0.0
    min_duration: float = float("inf")
    max_duration: float = 0.0
    calls_per_second: float = 0.0


class ExecutionLogger:
    """执行日志记录器"""

    def __init__(self, max_records: int = 10000):
        self._records: List[ToolCallRecord] = []
        self._max_records = max_records
        self._start_time = time.time()

    def log(
        self,
        tool_name: str,
        arguments: Dict,
        result: Any,
        success: bool,
        start_time: float,
        end_time: float,
        error: Optional[str] = None,
        quality: str = "success",
        metadata: Optional[Dict] = None,
    ) -> None:
        """记录工具调用"""
        record = ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            start_time=start_time,
            end_time=end_time,
            duration=end_time - start_time,
            error=error,
            quality=quality,
            metadata=metadata or {},
        )

        self._records.append(record)

        # 检查是否需要清理
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

    def get_records(
        self,
        tool_name: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
    ) -> List[ToolCallRecord]:
        """获取记录"""
        records = self._records

        if tool_name:
            records = [r for r in records if r.tool_name == tool_name]

        if start_time:
            records = [r for r in records if r.start_time >= start_time]

        if end_time:
            records = [r for r in records if r.end_time <= end_time]

        return records[-limit:]

    def clear(self) -> None:
        """清空记录"""
        self._records.clear()


class MetricsCollector:
    """性能指标收集器"""

    def __init__(self):
        self._tool_metrics: Dict[str, PerformanceMetrics] = {}
        self._global_metrics = PerformanceMetrics()
        self._call_counts: Dict[str, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._start_time = time.time()

    def record_call(
        self,
        tool_name: str,
        success: bool,
        duration: float,
        error: Optional[str] = None,
    ) -> None:
        """记录工具调用"""
        # 更新全局指标
        self._global_metrics.total_calls += 1
        self._global_metrics.total_duration += duration

        if success:
            self._global_metrics.successful_calls += 1
        else:
            self._global_metrics.failed_calls += 1

        self._global_metrics.min_duration = min(
            self._global_metrics.min_duration, duration
        )
        self._global_metrics.max_duration = max(
            self._global_metrics.max_duration, duration
        )

        if self._global_metrics.total_calls > 0:
            self._global_metrics.avg_duration = (
                self._global_metrics.total_duration / self._global_metrics.total_calls
            )

        elapsed = time.time() - self._start_time
        if elapsed > 0:
            self._global_metrics.calls_per_second = (
                self._global_metrics.total_calls / elapsed
            )

        # 更新工具级指标
        if tool_name not in self._tool_metrics:
            self._tool_metrics[tool_name] = PerformanceMetrics()

        metrics = self._tool_metrics[tool_name]
        metrics.total_calls += 1
        metrics.total_duration += duration

        if success:
            metrics.successful_calls += 1
        else:
            metrics.failed_calls += 1

        metrics.min_duration = min(metrics.min_duration, duration)
        metrics.max_duration = max(metrics.max_duration, duration)

        if metrics.total_calls > 0:
            metrics.avg_duration = metrics.total_duration / metrics.total_calls

        # 更新计数
        self._call_counts[tool_name] += 1
        if not success:
            self._error_counts[tool_name] += 1

    def get_global_metrics(self) -> Dict:
        """获取全局指标"""
        m = self._global_metrics
        return {
            "total_calls": m.total_calls,
            "successful_calls": m.successful_calls,
            "failed_calls": m.failed_calls,
            "success_rate": f"{m.successful_calls / max(m.total_calls, 1):.2%}",
            "total_duration": f"{m.total_duration:.2f}s",
            "avg_duration": f"{m.avg_duration:.3f}s",
            "min_duration": f"{m.min_duration:.3f}s" if m.min_duration != float("inf") else "N/A",
            "max_duration": f"{m.max_duration:.3f}s",
            "calls_per_second": f"{m.calls_per_second:.2f}",
        }

    def get_tool_metrics(self, tool_name: Optional[str] = None) -> Dict:
        """获取工具级指标"""
        if tool_name:
            metrics = self._tool_metrics.get(tool_name)
            if not metrics:
                return {}
            return {
                "tool": tool_name,
                "total_calls": metrics.total_calls,
                "successful_calls": metrics.successful_calls,
                "failed_calls": metrics.failed_calls,
                "success_rate": f"{metrics.successful_calls / max(metrics.total_calls, 1):.2%}",
                "avg_duration": f"{metrics.avg_duration:.3f}s",
                "error_rate": f"{self._error_counts.get(tool_name, 0) / max(metrics.total_calls, 1):.2%}",
            }

        # 返回所有工具的指标
        result = {}
        for name, metrics in self._tool_metrics.items():
            result[name] = {
                "total_calls": metrics.total_calls,
                "successful_calls": metrics.successful_calls,
                "failed_calls": metrics.failed_calls,
                "avg_duration": f"{metrics.avg_duration:.3f}s",
            }
        return result

    def get_top_tools(self, limit: int = 10) -> List[Dict]:
        """获取调用量最多的工具"""
        sorted_tools = sorted(
            self._call_counts.items(), key=lambda x: -x[1]
        )[:limit]

        return [
            {
                "tool": name,
                "calls": count,
                "errors": self._error_counts.get(name, 0),
            }
            for name, count in sorted_tools
        ]

    def clear(self) -> None:
        """清空指标"""
        self._tool_metrics.clear()
        self._global_metrics = PerformanceMetrics()
        self._call_counts.clear()
        self._error_counts.clear()
        self._start_time = time.time()


class ExecutionReporter:
    """执行报告生成器"""

    def __init__(
        self,
        logger: ExecutionLogger,
        metrics: MetricsCollector,
    ):
        self._logger = logger
        self._metrics = metrics

    def generate_summary(self) -> str:
        """生成执行摘要"""
        global_metrics = self._metrics.get_global_metrics()
        top_tools = self._metrics.get_top_tools(5)

        lines = [
            "=" * 60,
            "执行摘要",
            "=" * 60,
            "",
            "全局指标:",
            f"  总调用次数: {global_metrics['total_calls']}",
            f"  成功次数: {global_metrics['successful_calls']}",
            f"  失败次数: {global_metrics['failed_calls']}",
            f"  成功率: {global_metrics['success_rate']}",
            f"  平均耗时: {global_metrics['avg_duration']}",
            f"  调用频率: {global_metrics['calls_per_second']} 次/秒",
            "",
            "Top 5 工具:",
        ]

        for i, tool in enumerate(top_tools, 1):
            lines.append(
                f"  {i}. {tool['tool']}: {tool['calls']} 次调用, {tool['errors']} 次错误"
            )

        return "\n".join(lines)

    def generate_tool_report(self, tool_name: str) -> str:
        """生成工具报告"""
        metrics = self._metrics.get_tool_metrics(tool_name)
        if not metrics:
            return f"工具 {tool_name} 无调用记录"

        lines = [
            f"工具报告: {tool_name}",
            "-" * 40,
            f"  总调用次数: {metrics['total_calls']}",
            f"  成功次数: {metrics['successful_calls']}",
            f"  失败次数: {metrics['failed_calls']}",
            f"  成功率: {metrics['success_rate']}",
            f"  平均耗时: {metrics['avg_duration']}",
            f"  错误率: {metrics['error_rate']}",
        ]

        return "\n".join(lines)

    def export_json(self) -> str:
        """导出 JSON 格式报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "global_metrics": self._metrics.get_global_metrics(),
            "tool_metrics": self._metrics.get_tool_metrics(),
            "top_tools": self._metrics.get_top_tools(),
        }
        return json.dumps(report, indent=2, ensure_ascii=False)


# 全局实例
_execution_logger: Optional[ExecutionLogger] = None
_metrics_collector: Optional[MetricsCollector] = None
_execution_reporter: Optional[ExecutionReporter] = None


def get_execution_logger() -> ExecutionLogger:
    """获取执行日志记录器"""
    global _execution_logger
    if _execution_logger is None:
        _execution_logger = ExecutionLogger()
    return _execution_logger


def get_metrics_collector() -> MetricsCollector:
    """获取性能指标收集器"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def get_execution_reporter() -> ExecutionReporter:
    """获取执行报告生成器"""
    global _execution_reporter
    if _execution_reporter is None:
        _execution_reporter = ExecutionReporter(
            get_execution_logger(),
            get_metrics_collector(),
        )
    return _execution_reporter
