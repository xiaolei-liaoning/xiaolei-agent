"""智能多Agent — 委托给 multi_agent_v2 真实调度"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CoordinatorAgent:
    """协调Agent — 委托给真实调度器"""

    async def execute(self, task: str, mode: str = "auto") -> dict:
        """执行任务 — 走真实调度链路"""
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
            agents = AgentFactory.create_agents_for_task(task.split(), 3, 3)
            for a in agents:
                pool.add_agent(a)

            scheduler = IntelligentScheduler(GlobalContextCenter())
            scheduler.agent_pool = pool

            t = Task(task_id=f"smart_{id(self)}", type=mode, description=task, keywords=[])
            schedule_result = await scheduler.schedule(t)

            if not schedule_result.success:
                return {"success": False, "error": schedule_result.error}

            executor = TaskExecutor(agent_pool=pool)
            exec_result = await executor.execute(schedule_result, t, timeout=60)

            return {
                "success": exec_result.get("success", False),
                "result": str(exec_result.get("results", [])),
                "mode": mode,
            }
        except Exception as e:
            logger.error(f"协调Agent执行失败: {e}")
            return {"success": False, "error": str(e), "mode": mode}


def get_smart_multi_agent_system():
    try:
        from core.multi_agent_v2.agents.base.base_agent import AgentFactory
        return AgentFactory.create_agent_from_role("task_decomposer", name="smart-master")
    except Exception:
        return CoordinatorAgent()
