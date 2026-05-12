"""
MasterAgent - 主Agent

负责任务分解、结果聚合、流程控制
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from ..base.base_agent import (
    BaseAgent,
    AgentType,
    Capability,
    Task,
    ActionResult,
    Thought
)

logger = logging.getLogger(__name__)


class MasterAgent(BaseAgent):
    """主Agent - 负责任务分解和结果聚合"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "主Agent，负责任务分解和结果聚合"
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.MASTER,
            name=name,
            description=description
        )

        # 定义主Agent的能力
        self.capabilities = [
            Capability(
                name="task_decomposition",
                description="任务分解能力",
                keywords=["分解", "拆解", "规划", "计划"],
                expertise_level=0.9,
                max_concurrent_tasks=5,
                avg_execution_time=5.0,
                success_rate=0.95
            ),
            Capability(
                name="result_aggregation",
                description="结果聚合能力",
                keywords=["聚合", "汇总", "整合", "总结"],
                expertise_level=0.85,
                max_concurrent_tasks=3,
                avg_execution_time=3.0,
                success_rate=0.92
            ),
            Capability(
                name="coordination",
                description="协调能力",
                keywords=["协调", "调度", "分配", "管理"],
                expertise_level=0.8,
                max_concurrent_tasks=10,
                avg_execution_time=2.0,
                success_rate=0.9
            )
        ]

        # 子任务管理
        self.subtasks: Dict[str, Task] = {}
        self.subtask_results: Dict[str, ActionResult] = {}

        logger.info(f"MasterAgent初始化完成: {self.agent_id}")

    async def execute(self, task: Task) -> ActionResult:
        """执行任务"""
        logger.info(f"MasterAgent开始执行任务: {task.task_id}")

        try:
            # 1. 思考
            thought = await self.think(task)
            logger.info(f"思考完成: {thought.reasoning}")

            # 2. 分解任务
            subtasks = await self._decompose_task(task)
            logger.info(f"任务分解完成，生成{len(subtasks)}个子任务")

            # 3. 分配子任务
            await self._assign_subtasks(subtasks)

            # 4. 等待子任务完成
            await self._wait_for_subtasks(subtasks)

            # 5. 聚合结果
            final_result = await self._aggregate_results(subtasks)

            # 6. 反思
            reflection = await self.reflect(final_result)

            return final_result

        except Exception as e:
            logger.error(f"MasterAgent执行失败: {e}")
            return ActionResult(
                success=False,
                error=str(e)
            )

    async def _decompose_task(self, task: Task) -> List[Task]:
        """分解任务为子任务（使用LLM进行智能分解）"""
        # 先尝试使用LLM进行智能分解
        try:
            llm_subtasks = await self._decompose_with_llm(task)
            if llm_subtasks:
                for subtask in llm_subtasks:
                    self.subtasks[subtask.task_id] = subtask
                return llm_subtasks
        except Exception as e:
            logger.warning(f"LLM任务分解失败，使用默认规则: {e}")

        # 降级到规则匹配
        return self._decompose_with_rules(task)

    async def _decompose_with_llm(self, task: Task) -> List[Task]:
        """使用LLM进行智能任务分解"""
        from core.llm_backend import get_llm_router
        from core.multi_agent_v2.agents.prompts.agent_prompts import get_prompt_manager
        
        llm_router = get_llm_router()
        prompt_manager = get_prompt_manager()
        
        if not llm_router.is_available():
            return []

        prompt = prompt_manager.get_prompt("master")
        if not prompt:
            return []

        # 构建任务分解提示词
        task_prompt = prompt.task_prompt.format(
            task_description=task.description,
            task_keywords=", ".join(task.keywords),
            task_complexity=task.complexity
        )

        messages = [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": task_prompt}
        ]

        response = await llm_router.chat(messages, temperature=0.6, max_tokens=2000)
        
        # 解析LLM响应
        return self._parse_llm_subtasks(response, task)

    def _parse_llm_subtasks(self, response: str, parent_task: Task) -> List[Task]:
        """解析LLM响应中的子任务"""
        subtasks = []
        lines = response.split('\n')
        
        sub_task_index = 1
        current_subtask = None
        
        for line in lines:
            line = line.strip()
            
            # 匹配子任务标题
            if line.startswith(('1.', '2.', '3.', '4.', '5.', '子任务', '步骤')):
                if current_subtask:
                    subtasks.append(current_subtask)
                
                # 提取子任务描述
                desc = line
                if ':' in line:
                    desc = line.split(':', 1)[1].strip()
                
                current_subtask = Task(
                    task_id=f"{parent_task.task_id}_sub_{sub_task_index}",
                    type="execution",
                    description=desc,
                    keywords=[],
                    complexity=parent_task.complexity / 3,
                    estimated_steps=2
                )
                sub_task_index += 1
            elif current_subtask and line:
                # 添加额外描述
                current_subtask.description += " " + line
        
        if current_subtask:
            subtasks.append(current_subtask)
        
        return subtasks[:5]  # 最多5个子任务

    def _decompose_with_rules(self, task: Task) -> List[Task]:
        """使用规则匹配进行任务分解（降级方案）"""
        subtasks = []

        if "爬取" in task.description or "抓取" in task.description:
            subtasks = [
                Task(
                    task_id=f"{task.task_id}_sub_1",
                    type="analysis",
                    description="分析目标网站结构",
                    keywords=["分析", "结构"],
                    complexity=0.3,
                    estimated_steps=2
                ),
                Task(
                    task_id=f"{task.task_id}_sub_2",
                    type="scraping",
                    description="执行数据抓取",
                    keywords=["抓取", "数据"],
                    complexity=0.7,
                    estimated_steps=3
                ),
                Task(
                    task_id=f"{task.task_id}_sub_3",
                    type="processing",
                    description="数据清洗处理",
                    keywords=["清洗", "处理"],
                    complexity=0.5,
                    estimated_steps=2
                )
            ]
        elif "分析" in task.description or "统计" in task.description:
            subtasks = [
                Task(
                    task_id=f"{task.task_id}_sub_1",
                    type="collection",
                    description="收集数据",
                    keywords=["收集", "数据"],
                    complexity=0.4,
                    estimated_steps=2
                ),
                Task(
                    task_id=f"{task.task_id}_sub_2",
                    type="analysis",
                    description="执行分析",
                    keywords=["分析", "统计"],
                    complexity=0.7,
                    estimated_steps=3
                ),
                Task(
                    task_id=f"{task.task_id}_sub_3",
                    type="reporting",
                    description="生成报告",
                    keywords=["报告", "总结"],
                    complexity=0.5,
                    estimated_steps=2
                )
            ]
        else:
            subtasks = [
                Task(
                    task_id=f"{task.task_id}_sub_1",
                    type="execution",
                    description=task.description,
                    keywords=task.keywords,
                    complexity=task.complexity,
                    estimated_steps=task.estimated_steps
                )
            ]

        return subtasks

    async def _assign_subtasks(self, subtasks: List[Task]) -> None:
        """分配子任务给其他Agent"""
        # 这里应该通过上下文中心分配任务
        # 暂时只是记录
        logger.info(f"分配{len(subtasks)}个子任务")

    async def _wait_for_subtasks(self, subtasks: List[Task]) -> None:
        """等待所有子任务完成"""
        # 这里应该等待子任务完成
        # 暂时只是模拟等待
        await asyncio.sleep(0.5)

    async def _aggregate_results(self, subtasks: List[Task]) -> ActionResult:
        """聚合子任务结果"""
        # 收集所有子任务结果
        results = []
        for subtask in subtasks:
            result = self.subtask_results.get(subtask.task_id)
            if result:
                results.append(result)

        # 生成聚合结果
        if results:
            aggregated = {
                "subtask_count": len(results),
                "success_count": sum(1 for r in results if r.success),
                "results": [r.output for r in results if r.success]
            }

            return ActionResult(
                success=True,
                output=aggregated,
                execution_time=sum(r.execution_time for r in results)
            )
        else:
            return ActionResult(
                success=False,
                error="没有子任务结果"
            )

    async def receive_subtask_result(self, subtask_id: str, result: ActionResult) -> None:
        """接收子任务结果"""
        self.subtask_results[subtask_id] = result
        logger.info(f"收到子任务结果: {subtask_id}")

    def get_subtask_status(self) -> Dict[str, Any]:
        """获取子任务状态"""
        return {
            "total_subtasks": len(self.subtasks),
            "completed_subtasks": len(self.subtask_results),
            "pending_subtasks": len(self.subtasks) - len(self.subtask_results)
        }
