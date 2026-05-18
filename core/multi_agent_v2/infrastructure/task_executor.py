"""
TaskExecutor - 任务执行器

职责：
1. 接收 ScheduleResult，从 AgentPool 获取 Agent 实例
2. 并发调用 agent.act() 执行任务
3. 设置超时保护（默认5分钟）
4. 更新 SharedBus 任务快照状态
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.agents.base.base_agent import BaseAgent, Task, ActionResult
from core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler import ScheduleResult
from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, TaskSnapshot

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器 - 连接 Scheduler 和 Agent 的桥梁"""

    def __init__(self, agent_pool: Optional[Any] = None):
        self.agent_pool = agent_pool
        self._bus = get_shared_bus()

    async def execute(
        self,
        schedule_result: ScheduleResult,
        original_task: Task,
        timeout: float = 300.0
    ) -> Dict[str, Any]:
        """执行调度结果
        
        Args:
            schedule_result: 调度结果
            original_task: 原始任务（用于创建子任务）
            timeout: 超时时间（秒），默认5分钟
            
        Returns:
            执行结果字典，包含 success, results, execution_time 等字段
        """
        start_time = time.time()
        task_id = schedule_result.task_id
        
        logger.info(f"开始执行任务: {task_id}, 模式: {schedule_result.collaboration_mode.value}")
        
        # 更新任务状态为 running
        await self._update_snapshot_status(task_id, "running")
        
        try:
            # 并发执行所有 assigned agents
            tasks = []
            logger.info(f"[DEBUG] assigned_agents: {schedule_result.assigned_agents}")
            for subtask_id, agent_id in schedule_result.assigned_agents.items():
                logger.info(f"[DEBUG] 处理子任务: {subtask_id}, agent_id: {agent_id}")
                # 从 agent_pool 获取 agent（根据类型或直接取第一个可用的）
                agent = await self._get_agent_by_type_or_any(agent_id)
                if not agent:
                    logger.warning(f"无法获取 Agent (原ID: {agent_id})，跳过")
                    continue
                
                logger.info(f"[DEBUG] 成功获取Agent: {agent.agent_id}")
                
                # 创建子任务
                subtask = self._create_subtask(subtask_id, original_task, schedule_result.execution_plan)
                
                # 启动执行协程
                tasks.append(self._execute_with_timeout(agent, subtask, timeout))
            
            logger.info(f"[DEBUG] tasks列表长度: {len(tasks)}")
            if not tasks:
                raise RuntimeError("没有可用的 Agent 执行任务")
            
            # 等待所有任务完成
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            execution_results = []
            all_success = True
            
            for i, (subtask_id, agent_id) in enumerate(schedule_result.assigned_agents.items()):
                result = results[i]
                
                if isinstance(result, Exception):
                    logger.error(f"Agent {agent_id} 执行失败: {result}")
                    execution_results.append({
                        "subtask_id": subtask_id,
                        "agent_id": agent_id,
                        "success": False,
                        "error": str(result)
                    })
                    all_success = False
                else:
                    execution_results.append({
                        "subtask_id": subtask_id,
                        "agent_id": agent_id,
                        "success": result.success,
                        "output": result.output if hasattr(result, 'output') else None,
                        "execution_time": result.execution_time if hasattr(result, 'execution_time') else 0
                    })
                    if not result.success:
                        all_success = False
            
            execution_time = time.time() - start_time
            
            # 更新最终状态
            final_status = "completed" if all_success else "failed"
            await self._update_snapshot_status(task_id, final_status)
            
            logger.info(f"任务执行完成: {task_id}, 耗时: {execution_time:.2f}s, 成功: {all_success}")
            
            return {
                "success": all_success,
                "results": execution_results,
                "execution_time": execution_time,
                "task_id": task_id
            }
            
        except asyncio.TimeoutError:
            logger.error(f"任务执行超时: {task_id}")
            await self._update_snapshot_status(task_id, "timeout")
            return {
                "success": False,
                "error": f"任务执行超时 ({timeout}s)",
                "execution_time": time.time() - start_time,
                "task_id": task_id
            }
        except Exception as e:
            logger.error(f"任务执行异常: {task_id}, 错误: {e}")
            await self._update_snapshot_status(task_id, "failed")
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.time() - start_time,
                "task_id": task_id
            }

    async def _get_agent_by_type_or_any(self, preferred_agent_id: str = None):
        """从 AgentPool 获取可用Agent
        
        策略：
        1. 如果preferred_agent_id在active_agents中，直接返回
        2. 否则从pools中acquire任意一个可用的Agent
        """
        if not self.agent_pool:
            logger.warning("AgentPool 未配置")
            return None
        
        logger.info(f"[DEBUG] Pool状态 - pools keys: {list(self.agent_pool.pools.keys())}")
        for k, v in self.agent_pool.pools.items():
            logger.info(f"[DEBUG]   {k}: {len(v)} agents")
        
        # 尝试从 active_agents 获取
        if preferred_agent_id and hasattr(self.agent_pool, 'active_agents'):
            if preferred_agent_id in self.agent_pool.active_agents:
                return self.agent_pool.active_agents[preferred_agent_id]
        
        # 从 pools 中 acquire 第一个可用的
        if hasattr(self.agent_pool, 'pools'):
            for pool_type in self.agent_pool.pools.keys():
                logger.info(f"[DEBUG] 尝试 acquire: {pool_type}")
                agent = await self.agent_pool.acquire(pool_type)
                if agent:
                    logger.info(f"[DEBUG] 成功 acquire: {agent.agent_id}")
                    return agent
                else:
                    logger.warning(f"[DEBUG] acquire 失败: {pool_type}")
        
        logger.warning("Pool中无可用Agent")
        return None

    async def _get_agent(self, agent_id: str):
        """从 AgentPool 获取 Agent（保留旧接口兼容）"""
        return await self._get_agent_by_type_or_any(agent_id)

    def _create_subtask(
        self,
        subtask_id: str,
        original_task: Task,
        execution_plan: List[Dict[str, Any]]
    ) -> Task:
        """创建子任务"""
        # 从 execution_plan 中找到对应的步骤描述
        description = original_task.description
        for step in execution_plan:
            if step.get("subtask_id") == subtask_id:
                description = step.get("description", original_task.description)
                break
        
        return Task(
            task_id=subtask_id,
            type=original_task.type,
            description=description,
            context=original_task.context,
            priority=original_task.priority,
            keywords=original_task.keywords,
            complexity=original_task.complexity / len(execution_plan) if execution_plan else original_task.complexity
        )

    async def _execute_with_timeout(
        self,
        agent: BaseAgent,
        task: Task,
        timeout: float
    ) -> ActionResult:
        """带超时的 Agent 执行"""
        try:
            # 接收任务
            await agent.receive_task(task)
            
            # 思考
            thought = await agent.think(task)
            
            # 执行
            result = await asyncio.wait_for(
                agent.act(thought.plan),
                timeout=timeout
            )
            
            # 反思
            await agent.reflect(result)
            
            return result
            
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Agent {agent.agent_id} 执行任务 {task.task_id} 失败: {e}")
            raise

    async def _update_snapshot_status(self, task_id: str, status: str) -> None:
        """更新 SharedBus 中的任务快照状态"""
        try:
            snapshot = await self._bus.get_snapshot(task_id)
            if snapshot:
                snapshot.status = status
                await self._bus.save_snapshot(snapshot)
        except Exception as e:
            logger.debug(f"更新任务快照失败: {e}")
