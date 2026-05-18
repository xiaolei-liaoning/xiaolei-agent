"""向后兼容层 — 委托给 multi_agent_v2 真实实现"""

import logging

ChatAgent = None
CoordinatorAgent = None
agent_scheduler = None

logger = logging.getLogger(__name__)


class TextAnalyzerAgent:
    """文本分析Agent — 委托给真实调度器"""

    async def execute(self, message: str, user_id: int) -> dict:
        try:
            from core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler import (
                IntelligentScheduler
            )
            from core.multi_agent_v2.agents.base.base_agent import Task, AgentFactory
            from core.multi_agent_v2.infrastructure.task_executor import TaskExecutor
            from core.multi_agent_v2.infrastructure.agent_pool import SimpleAgentPool
            from core.multi_agent_v2.orchestration.context.global_context_center import (
                GlobalContextCenter
            )

            pool = SimpleAgentPool()
            agents = AgentFactory.create_agents_for_task(message.split(), 2, 2)
            for a in agents:
                pool.add_agent(a)

            scheduler = IntelligentScheduler(GlobalContextCenter())
            scheduler.agent_pool = pool

            t = Task(task_id=f"legacy_{id(self)}", type="analysis", description=message, keywords=[])
            schedule_result = await scheduler.schedule(t)

            if not schedule_result.success:
                return {"success": False, "reply": f"处理失败: {schedule_result.error}", "fallback": True}

            executor = TaskExecutor(agent_pool=pool)
            exec_result = await executor.execute(schedule_result, t, timeout=60)

            return {
                "success": exec_result.get("success", False),
                "reply": str(exec_result.get("results", []))[:200],
                "fallback": False,
            }
        except Exception as e:
            logger.error(f"TextAnalyzerAgent 执行失败: {e}")
            return {"success": False, "reply": f"处理失败: {e}", "fallback": True}


def get_smart_multi_agent_system():
    try:
        from core.multi_agent_v2.agents.base.base_agent import AgentFactory
        return AgentFactory.create_agent_from_role("task_decomposer", name="legacy-master")
    except Exception:
        return None


try:
    from core.tasks.task_processor import Task as AgentTask
except ImportError:
    from dataclasses import dataclass
    from typing import Any

    @dataclass
    class AgentTask:
        task_id: str
        task_type: str
        payload: Any = None
        result: Any = None
        success: bool = False

__all__ = [
    'ChatAgent', 'CoordinatorAgent',
    'TextAnalyzerAgent', 'get_smart_multi_agent_system',
    'agent_scheduler', 'AgentTask',
]
