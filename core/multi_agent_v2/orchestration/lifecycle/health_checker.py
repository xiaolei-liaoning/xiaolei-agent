"""
健康检查器 - Agent健康状态监控

功能：
1. 定期健康检查
2. 健康评分计算
3. 异常检测
4. 健康报告生成
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import time

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"       # 健康
    DEGRADED = "degraded"     # 降级
    UNHEALTHY = "unhealthy"   # 不健康
    CRITICAL = "critical"     # 严重
    UNKNOWN = "unknown"       # 未知


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    agent_id: str
    status: HealthStatus
    score: float
    checks: Dict[str, Any]
    timestamp: float
    message: str = ""


@dataclass
class HealthMetrics:
    """健康指标"""
    agent_id: str
    cpu_usage: float
    memory_usage: float
    response_time: float
    error_rate: float
    success_rate: float
    active_tasks: int
    queue_size: int
    last_check: float


class HealthChecker:
    """健康检查器"""

    def __init__(self, check_interval: float = 30.0):
        self.check_interval = check_interval
        self.health_status: Dict[str, HealthCheckResult] = {}
        self.health_history: List[HealthCheckResult] = []
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        logger.info(f"健康检查器初始化完成 (interval={check_interval}s)")

    async def start(self) -> None:
        """启动健康检查"""
        if self._running:
            return

        self._running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("健康检查器已启动")

    async def stop(self) -> None:
        """停止健康检查"""
        if not self._running:
            return

        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

        logger.info("健康检查器已停止")

    async def _check_loop(self) -> None:
        """健康检查循环"""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                # 这里应该检查所有注册的Agent
                # 暂时跳过，因为没有Agent注册机制
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查异常: {e}")

    async def check_agent(self, agent_id: str, metrics: HealthMetrics) -> HealthCheckResult:
        """检查单个Agent的健康状态

        Args:
            agent_id: Agent ID
            metrics: 健康指标

        Returns:
            健康检查结果
        """
        checks = {}

        # 1. CPU使用率检查
        cpu_status = "ok" if metrics.cpu_usage < 80 else "warning" if metrics.cpu_usage < 95 else "critical"
        checks["cpu"] = {
            "usage": metrics.cpu_usage,
            "status": cpu_status
        }

        # 2. 内存使用率检查
        memory_status = "ok" if metrics.memory_usage < 80 else "warning" if metrics.memory_usage < 95 else "critical"
        checks["memory"] = {
            "usage": metrics.memory_usage,
            "status": memory_status
        }

        # 3. 响应时间检查
        response_status = "ok" if metrics.response_time < 5.0 else "warning" if metrics.response_time < 10.0 else "critical"
        checks["response_time"] = {
            "time": metrics.response_time,
            "status": response_status
        }

        # 4. 错误率检查
        error_status = "ok" if metrics.error_rate < 0.05 else "warning" if metrics.error_rate < 0.1 else "critical"
        checks["error_rate"] = {
            "rate": metrics.error_rate,
            "status": error_status
        }

        # 5. 成功率检查
        success_status = "ok" if metrics.success_rate > 0.9 else "warning" if metrics.success_rate > 0.8 else "critical"
        checks["success_rate"] = {
            "rate": metrics.success_rate,
            "status": success_status
        }

        # 6. 队列积压检查
        queue_status = "ok" if metrics.queue_size < 10 else "warning" if metrics.queue_size < 50 else "critical"
        checks["queue"] = {
            "size": metrics.queue_size,
            "status": queue_status
        }

        # 计算健康分数
        score = self._calculate_health_score(checks)

        # 确定健康状态
        status = self._determine_health_status(score, checks)

        # 生成消息
        message = self._generate_health_message(status, checks)

        result = HealthCheckResult(
            agent_id=agent_id,
            status=status,
            score=score,
            checks=checks,
            timestamp=time.time(),
            message=message
        )

        # 更新状态
        self.health_status[agent_id] = result
        self.health_history.append(result)

        # 限制历史记录大小
        if len(self.health_history) > 1000:
            self.health_history = self.health_history[-1000:]

        return result

    def _calculate_health_score(self, checks: Dict[str, Any]) -> float:
        """计算健康分数"""
        score = 1.0

        for check_name, check_data in checks.items():
            status = check_data.get("status", "ok")
            if status == "warning":
                score -= 0.1
            elif status == "critical":
                score -= 0.3

        return max(0.0, score)

    def _determine_health_status(self, score: float, checks: Dict[str, Any]) -> HealthStatus:
        """确定健康状态"""
        if score >= 0.8:
            return HealthStatus.HEALTHY
        elif score >= 0.6:
            return HealthStatus.DEGRADED
        elif score >= 0.4:
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.CRITICAL

    def _generate_health_message(self, status: HealthStatus, checks: Dict[str, Any]) -> str:
        """生成健康消息"""
        critical_checks = [name for name, data in checks.items() if data.get("status") == "critical"]
        warning_checks = [name for name, data in checks.items() if data.get("status") == "warning"]

        if status == HealthStatus.HEALTHY:
            return "Agent运行正常"
        elif status == HealthStatus.DEGRADED:
            return f"Agent性能下降: {', '.join(warning_checks)}"
        elif status == HealthStatus.UNHEALTHY:
            return f"Agent状态异常: {', '.join(critical_checks)}"
        else:
            return f"Agent严重故障: {', '.join(critical_checks)}"

    def get_agent_health(self, agent_id: str) -> Optional[HealthCheckResult]:
        """获取Agent健康状态"""
        return self.health_status.get(agent_id)

    def get_all_health(self) -> Dict[str, HealthCheckResult]:
        """获取所有Agent健康状态"""
        return self.health_status.copy()

    def get_health_history(self, agent_id: str, limit: int = 100) -> List[HealthCheckResult]:
        """获取Agent健康历史"""
        return [h for h in self.health_history if h.agent_id == agent_id][-limit:]

    def get_unhealthy_agents(self) -> List[str]:
        """获取不健康的Agent列表"""
        return [
            agent_id for agent_id, result in self.health_status.items()
            if result.status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]
        ]


# 全局健康检查器实例
_health_checker: Optional[HealthChecker] = None


def get_health_checker(check_interval: float = 30.0) -> HealthChecker:
    """获取健康检查器实例"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker(check_interval=check_interval)
    return _health_checker
