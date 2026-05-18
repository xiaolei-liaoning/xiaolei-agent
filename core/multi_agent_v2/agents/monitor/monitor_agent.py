"""
MonitorAgent - 监控Agent

追踪Agent状态和性能
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from ..base.base_agent import (
    BaseAgent,
    AgentType,
    Capability,
    Task,
    ActionResult,
    Thought
)

logger = logging.getLogger(__name__)


@dataclass
class AgentStateSnapshot:
    """Agent状态快照"""
    agent_id: str
    agent_type: str
    state: str
    timestamp: str
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Alert:
    """告警"""
    alert_id: str
    level: str
    message: str
    source: str
    timestamp: str


class MonitorAgent(BaseAgent):
    """MonitorAgent - 追踪系统状态"""

    # 告警级别
    ALERT_LEVELS = ["info", "warning", "error", "critical"]

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "监控Agent，追踪系统状态"
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.MONITOR,
            name=name,
            description=description
        )

        # 监控的Agent
        self.monitored_agents: Dict[str, AgentStateSnapshot] = {}

        # 历史快照
        self.snapshot_history: List[AgentStateSnapshot] = []

        # 告警
        self.alerts: List[Alert] = []

        # 监控阈值
        self.thresholds = {
            "max_task_time": 60.0,  # 最大任务执行时间（秒）
            "success_rate_warning": 0.7,  # 成功率警告阈值
            "error_rate_critical": 0.3  # 错误率严重阈值
        }

        # 定义MonitorAgent的能力
        self.capabilities = [
            Capability(
                name="state_monitoring",
                description="状态监控能力",
                keywords=["监控", "状态", "追踪", "观察"],
                expertise_level=0.9,
                max_concurrent_tasks=10,
                avg_execution_time=1.0,
                success_rate=0.98
            ),
            Capability(
                name="performance_analysis",
                description="性能分析能力",
                keywords=["性能", "分析", "指标", "统计"],
                expertise_level=0.85,
                max_concurrent_tasks=5,
                avg_execution_time=3.0,
                success_rate=0.95
            ),
            Capability(
                name="alert_generation",
                description="告警生成能力",
                keywords=["告警", "警告", "通知", "异常"],
                expertise_level=0.8,
                max_concurrent_tasks=10,
                avg_execution_time=0.5,
                success_rate=0.92
            )
        ]

        logger.info(f"MonitorAgent初始化完成: {self.agent_id}")

    async def execute(self, task: Task) -> ActionResult:
        """执行监控任务"""
        logger.info(f"MonitorAgent开始执行任务: {task.task_id}")

        try:
            # 1. 思考
            thought = await self.think(task)
            logger.info(f"思考完成: {thought.reasoning}")

            # 2. 执行监控
            result = await self._monitor(task)

            # 3. 反思
            reflection = await self.reflect(
                ActionResult(
                    success=result.get("success", True),
                    output=result
                )
            )

            # ★ 激活：从反思学习优化监控策略
            self._optimize_monitoring_from_reflection(reflection)

            return ActionResult(
                success=result.get("success", True),
                output=result,
                execution_time=result.get("execution_time", 2.0)
            )

        except Exception as e:
            logger.error(f"MonitorAgent执行失败: {e}")
            return ActionResult(
                success=False,
                error=str(e)
            )

    async def _monitor(self, task: Task) -> Dict[str, Any]:
        """执行监控"""
        logger.info(f"开始监控: {task.description}")

        # 收集所有监控的Agent状态
        snapshots = []
        for agent_id in list(self.monitored_agents.keys()):
            snapshot = self._take_agent_snapshot(agent_id)
            if snapshot:
                snapshots.append(snapshot)
                self.snapshot_history.append(snapshot)

        # 检查异常
        alerts = self._check_for_anomalies(snapshots)

        # 生成报告
        report = {
            "type": "monitor",
            "snapshot_count": len(snapshots),
            "alerts_count": len(alerts),
            "alerts": alerts,
            "snapshots": [s.__dict__ for s in snapshots[:10]],
            "status": "success"
        }

        return report

    def start_monitoring_agent(self, agent: BaseAgent) -> None:
        """开始监控Agent"""
        if agent.agent_id not in self.monitored_agents:
            snapshot = AgentStateSnapshot(
                agent_id=agent.agent_id,
                agent_type=agent.agent_type.value,
                state=str(agent.state),
                timestamp=datetime.now().isoformat(),
                metrics=agent.get_metrics().__dict__ if hasattr(agent, 'get_metrics') else {}
            )
            self.monitored_agents[agent.agent_id] = snapshot
            logger.info(f"开始监控: {agent.agent_id}")

    def stop_monitoring_agent(self, agent_id: str) -> None:
        """停止监控Agent"""
        if agent_id in self.monitored_agents:
            del self.monitored_agents[agent_id]
            logger.info(f"停止监控: {agent_id}")

    def _take_agent_snapshot(self, agent_id: str) -> Optional[AgentStateSnapshot]:
        """获取Agent状态快照"""
        if agent_id not in self.monitored_agents:
            return None

        previous_snapshot = self.monitored_agents[agent_id]

        return AgentStateSnapshot(
            agent_id=agent_id,
            agent_type=previous_snapshot.agent_type,
            state="idle",  # 默认状态
            timestamp=datetime.now().isoformat(),
            metrics=previous_snapshot.metrics
        )

    def _check_for_anomalies(self, snapshots: List[AgentStateSnapshot]) -> List[Dict[str, Any]]:
        """检查异常"""
        alerts = []

        for snapshot in snapshots:
            metrics = snapshot.metrics

            # 检查任务执行时间
            if 'avg_execution_time' in metrics:
                avg_time = metrics['avg_execution_time']
                if avg_time > self.thresholds["max_task_time"]:
                    alert = self._create_alert(
                        level="warning",
                        message=f"Agent {snapshot.agent_id} 执行时间过长: {avg_time}s",
                        source=snapshot.agent_id
                    )
                    alerts.append(alert)

            # 检查成功率
            if 'tasks_completed' in metrics and 'tasks_failed' in metrics:
                total = metrics['tasks_completed'] + metrics['tasks_failed']
                if total > 0:
                    success_rate = metrics['tasks_completed'] / total
                    if success_rate < self.thresholds["success_rate_warning"]:
                        alert = self._create_alert(
                            level="warning" if success_rate > self.thresholds["error_rate_critical"] else "error",
                            message=f"Agent {snapshot.agent_id} 成功率过低: {success_rate:.2%}",
                            source=snapshot.agent_id
                        )
                        alerts.append(alert)

        return alerts

    def _create_alert(self, level: str, message: str, source: str) -> Dict[str, Any]:
        """创建告警"""
        import uuid

        alert_id = f"alert-{uuid.uuid4().hex[:8]}"
        alert_data = {
            "alert_id": alert_id,
            "level": level,
            "message": message,
            "source": source,
            "timestamp": datetime.now().isoformat()
        }

        alert = Alert(
            alert_id=alert_id,
            level=level,
            message=message,
            source=source,
            timestamp=datetime.now().isoformat()
        )
        self.alerts.append(alert)

        logger.warning(f"[{level.upper()}] {message}")
        return alert_data

    def _optimize_monitoring_from_reflection(self, reflection) -> None:
        """从反思优化监控策略"""
        if hasattr(reflection, 'lessons_learned') and reflection.lessons_learned:
            logger.info(f"从监控反思中学习: {reflection.lessons_learned}")

    def get_monitoring_report(self) -> Dict[str, Any]:
        """获取监控报告"""
        return {
            "monitored_agents_count": len(self.monitored_agents),
            "total_snapshots": len(self.snapshot_history),
            "total_alerts": len(self.alerts),
            "alerts_by_level": {
                level: sum(1 for a in self.alerts if a.level == level)
                for level in self.ALERT_LEVELS
            },
            "recent_alerts": [a.__dict__ for a in self.alerts[-10:]]
        }

    def get_recent_alerts(self, limit: int = 20, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取最近的告警"""
        filtered = self.alerts
        if level:
            filtered = [a for a in filtered if a.level == level]

        return [a.__dict__ for a in filtered[-limit:]]

    def set_threshold(self, key: str, value: float) -> None:
        """设置监控阈值"""
        if key in self.thresholds:
            self.thresholds[key] = value
            logger.info(f"监控阈值已更新: {key} = {value}")
