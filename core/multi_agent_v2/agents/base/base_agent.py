"""BaseAgent — Agent 基类（精简版）

核心保留：
  - personality/role + temp_memory（临时记忆）
  - system_prompt_for_role() → LLM 个性注入
  - SharedBus 消息监听路由
  - execute()（委托给子类）

已删除：
  - 旧 run() 分步执行路径（被 ReactCore 替代）
  - think/act/reflect 存根
  - _execute_single_tool_call / _execute_tool_calls（由 MiddlewareChain.on_wrap_tool_call 处理）
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

from .models import AgentType, Task, ActionResult

logger = logging.getLogger(__name__)


class BaseAgent:
    """Agent 基类 — 极简核心"""

    def __init__(self, agent_id=None, agent_type=AgentType.WORKER, name=None, description="",
                 personality="", role=""):
        self.agent_id = agent_id or str(uuid.uuid4().hex[:12])
        self.agent_type = agent_type
        self.agent_name = name or f"agent_{self.agent_id[:8]}"
        self.description = description
        # 个性/角色配置
        self.personality = personality
        self.role = role
        # 临时记忆（per-task，任务结束后清空）
        self.temp_memory: Dict[str, Any] = {}
        self._trace = None
        self._bus_listener_task: Optional[asyncio.Task] = None
        logger.info(f"Agent: {self.agent_id}")

    def set_trace(self, trace):
        self._trace = trace

    # ── 个性/记忆 ────────────────────────────────────────────────

    def reset_temp_memory(self) -> None:
        """清空临时记忆（任务结束后调用）"""
        self.temp_memory.clear()

    def system_prompt_for_role(self) -> str:
        """根据角色生成系统提示前缀"""
        prompts = {
            "analyst": "你是一个数据分析专家，擅长从数据中提取洞察和撰写分析报告。",
            "coder": "你是一个资深程序员，擅长编写高质量代码和调试。",
            "researcher": "你是一个研究助手，擅长搜索信息、验证事实和汇总发现。",
            "coordinator": "你是一个协调者，擅长拆分任务、分配和汇总多方结果。",
        }
        if self.personality:
            return self.personality
        return prompts.get(self.role, "")

    # ── SharedBus 消息路由 ───────────────────────────────────────

    async def _start_bus_listener(self, enable: bool = False) -> None:
        """启动 SharedBus 直接消息监听（后台协程）"""
        if not enable:
            return
        if self._bus_listener_task is not None and not self._bus_listener_task.done():
            return
        async def _listen():
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()
            while True:
                try:
                    msg = await bus.receive_direct(self.agent_id, timeout=30.0)
                    if msg is not None:
                        await self._on_bus_direct_message(msg)
                    else:
                        await asyncio.sleep(0.5)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"Agent {self.agent_id} 消息监听异常: {e}")
                    await asyncio.sleep(1)
        self._bus_listener_task = asyncio.create_task(_listen())

    async def _on_bus_direct_message(self, msg: "Message") -> None:
        """处理 SharedBus 直接消息"""
        logger.debug(f"Agent {self.agent_id} 收到 SharedBus 消息: {msg.type} 来自 {msg.sender}")

    async def execute(self, task: Task) -> ActionResult:
        """执行任务 — 由子类实现"""
        raise NotImplementedError

    def __repr__(self):
        return f"BaseAgent(id={self.agent_id})"
