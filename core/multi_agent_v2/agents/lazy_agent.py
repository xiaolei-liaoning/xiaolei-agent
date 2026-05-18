#!/usr/bin/env python3
"""
LazyAgent - 轻量级Agent包装类

用于在调度时延迟初始化真正的Agent实例,主要用于测试和快速原型开发。
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from core.multi_agent_v2.agents.base.base_agent import BaseAgent, AgentType, Task, ActionResult

logger = logging.getLogger(__name__)


class LazyAgent(BaseAgent):
    """轻量级Agent包装类 - 延迟初始化"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_type: AgentType = AgentType.WORKER,
        name: Optional[str] = None,
        description: str = ""
    ):
        # 兼容字符串传参
        if isinstance(agent_type, str):
            try:
                agent_type = AgentType(agent_type)
            except ValueError:
                logger.warning(f"未知的AgentType: {agent_type}, 使用默认值 WORKER")
                agent_type = AgentType.WORKER
        
        super().__init__(
            agent_id=agent_id,
            agent_type=agent_type,
            name=name,
            description=description
        )
        self._initialized = False

    async def ensure_initialized(self) -> None:
        """确保Agent已初始化"""
        if not self._initialized:
            logger.info(f"LazyAgent {self.agent_id} 正在初始化...")
            # 这里可以添加实际的初始化逻辑
            # 例如: 加载模型、连接数据库等
            await asyncio.sleep(0.01)  # 模拟初始化时间
            self._initialized = True
            logger.info(f"LazyAgent {self.agent_id} 初始化完成")

    async def execute(self, task: Task) -> ActionResult:
        """执行任务"""
        logger.info(f"LazyAgent {self.agent_id} 执行任务: {task.task_id}")
        await self.ensure_initialized()
        
        try:
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()
            prompt = f"请完成以下任务：{task.description}"
            result = await router.chat([{"role": "user", "content": prompt}],
                                     temperature=0.5, max_tokens=1000)
            
            return ActionResult(
                success=True,
                output={"result": result, "task_id": task.task_id},
                execution_time=0.0
            )
        except Exception as e:
            logger.error(f"LazyAgent {self.agent_id} 执行任务失败: {e}")
            return ActionResult(
                success=False,
                error=str(e),
                execution_time=0.0
            )

    async def start(self) -> None:
        """启动Agent"""
        await self.ensure_initialized()
        await super().start()

    def __repr__(self) -> str:
        return f"LazyAgent(id={self.agent_id}, type={self.agent_type.value}, initialized={self._initialized})"