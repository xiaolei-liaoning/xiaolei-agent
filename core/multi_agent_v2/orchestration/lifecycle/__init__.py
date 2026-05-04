"""
Lifecycle - Agent生命周期管理

包含：
- AgentPool: Agent池管理
- HealthChecker: 健康检查
- CircuitBreaker: 熔断器
"""

from core.multi_agent_v2.orchestration.lifecycle.agent_pool import AgentPool
from core.multi_agent_v2.orchestration.lifecycle.health_checker import HealthChecker

__all__ = [
    "AgentPool",
    "HealthChecker",
]
