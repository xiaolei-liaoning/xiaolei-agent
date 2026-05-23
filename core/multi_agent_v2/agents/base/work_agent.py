"""
WorkAgent - 统一智能体

单一 Agent 类型，根据任务需求动态调整行为和能力。
取代了原先分散的 WorkerAgent / MasterAgent / ReviewerAgent / ExpertAgent / CoordinatorAgent / MonitorAgent。

核心设计：
- 不预设角色：同一个 WorkAgent 实例可以根据不同任务动态调整
- 能力即配置：capabilities 由任务匹配动态生成，而非硬编码
- LLM 驱动的执行：所有任务通过 think → act → reflect 循环
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent, AgentType, Capability, Task, ActionResult, Thought

logger = logging.getLogger(__name__)


class WorkAgent(BaseAgent):
    """统一工作 Agent - 根据任务动态调整行为和能力

    替代 WorkerAgent / MasterAgent / ReviewerAgent / ExpertAgent / CoordinatorAgent / MonitorAgent。
    不再预设 specialization，而是根据任务类型动态适配。
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "通用工作 Agent，根据任务动态调整",
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.WORKER,
            name=name,
            description=description,
        )

        # 能力列表 - 非硬编码，根据任务动态生成
        self.capabilities: List[Capability] = self._default_capabilities()

        # 工作记录
        self.work_history: List[Dict[str, Any]] = []

        logger.info(f"WorkAgent 初始化完成: {self.agent_id}")

    def _default_capabilities(self) -> List[Capability]:
        """提供一组通用的默认能力，具体匹配由 scheduler 动态完成"""
        return [
            Capability(
                name="general_task",
                description="通用任务执行能力，适配各种类型的任务",
                keywords=["执行", "处理", "完成", "分析", "生成", "搜索"],
                expertise_level=0.7,
            ),
        ]

    def adapt_to_task(self, task: Task) -> None:
        """根据任务动态调整 Agent 的能力配置

        每个 Agent 拥有完整能力（不做裁剪），根据任务类型追加专项能力。
        """
        task_type = task.type or "general"
        task_keywords = task.keywords or []

        # 追加全部能力类型（不做关键词过滤），每个 Agent 天然具备所有能力
        extra_capabilities = [
            Capability(
                name=f"analysis_{task_type}",
                description=f"分析能力: {task.description[:50]}",
                keywords=task_keywords + ["分析", "评估"],
                expertise_level=0.8,
            ),
            Capability(
                name=f"execution_{task_type}",
                description=f"执行能力: {task.description[:50]}",
                keywords=task_keywords + ["执行", "处理"],
                expertise_level=0.8,
            ),
            Capability(
                name=f"review_{task_type}",
                description=f"评审能力: {task.description[:50]}",
                keywords=task_keywords + ["评审", "质量"],
                expertise_level=0.85,
            ),
            Capability(
                name=f"research_{task_type}",
                description=f"研究能力: {task.description[:50]}",
                keywords=task_keywords + ["研究", "检索"],
                expertise_level=0.75,
            ),
            Capability(
                name=f"integration_{task_type}",
                description=f"整合能力: {task.description[:50]}",
                keywords=task_keywords + ["整合", "汇总"],
                expertise_level=0.8,
            ),
        ]

        self.capabilities = self._default_capabilities() + extra_capabilities
        logger.info(
            f"WorkAgent {self.agent_id} 已适配任务: {task_type} "
            f"(完整能力: 基础+分析/执行/评审/研究/整合)"
        )

    async def execute(self, task: Task) -> ActionResult:
        """执行任务 - 统一的执行入口

        workflow:
        1. 适配任务 → 调整能力配置
        2. 思考 → think() 生成计划和工具调用
        3. 执行 → act() 执行计划
        4. 反思 → reflect() 总结经验
        """
        logger.info(f"WorkAgent 开始执行任务: {task.task_id} ({task.type})")

        # 1. 动态适配
        self.adapt_to_task(task)

        # 2. 思考
        try:
            thought = await self.think(task)
        except Exception as e:
            logger.error(f"思考失败: {e}")
            return ActionResult(success=False, error=f"思考失败: {e}")

        # 3. 执行
        try:
            result = await self.act(thought.plan, thought.tool_calls)
        except Exception as e:
            logger.error(f"执行失败: {e}")
            return ActionResult(success=False, error=f"执行失败: {e}")

        # 4. 反思
        try:
            reflection = await self.reflect(result)
        except Exception as e:
            logger.debug(f"反思异常（非致命）: {e}")
            reflection = None

        # 记录工作历史
        self.work_history.append({
            "task_id": task.task_id,
            "task_type": task.type,
            "success": result.success,
            "execution_time": result.execution_time,
            "timestamp": time.time(),
        })

        # 保持最近的记录
        if len(self.work_history) > 100:
            self.work_history = self.work_history[-100:]

        return result

    def get_work_stats(self) -> Dict[str, Any]:
        """获取工作统计"""
        if not self.work_history:
            return {"total_tasks": 0}

        total = len(self.work_history)
        successful = sum(1 for r in self.work_history if r.get("success"))
        by_type: Dict[str, int] = {}
        for r in self.work_history:
            t = r.get("task_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "total_tasks": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "by_type": by_type,
        }
