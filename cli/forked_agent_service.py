"""Forked Agent服务模块

实现Forked Agent模式，支持：
1. 侧问题（Side Question）处理 - 不中断主流程
2. 并发任务执行
3. 共享prompt缓存
4. 异步并行处理
5. 结果聚合与协调

参考Claude Code的sideQuestion.ts实现
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Callable, Coroutine
from enum import Enum
from datetime import datetime
import logging
import uuid

logger = logging.getLogger(__name__)


class ForkedAgentStatus(Enum):
    """Forked Agent状态枚举"""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ForkedAgentType(Enum):
    """Forked Agent类型枚举"""
    SIDE_QUESTION = "side_question"      # 侧问题 - 不中断主流程
    PARALLEL_TASK = "parallel_task"      # 并行任务
    BACKGROUND_TASK = "background_task"  # 后台任务
    CACHE_WARMUP = "cache_warmup"        # 缓存预热


@dataclass
class ForkedTask:
    """Forked任务"""
    task_id: str
    agent_type: ForkedAgentType
    prompt: str
    max_turns: int = 1
    can_use_tools: bool = False
    skip_cache_write: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_type": self.agent_type.value,
            "prompt": self.prompt,
            "max_turns": self.max_turns,
            "can_use_tools": self.can_use_tools,
            "skip_cache_write": self.skip_cache_write
        }


@dataclass
class ForkedResult:
    """Forked任务结果"""
    task_id: str
    status: ForkedAgentStatus
    response: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "response": self.response,
            "error": self.error,
            "usage": self.usage,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


@dataclass
class ForkedAgent:
    """Forked Agent实例"""
    agent_id: str
    task: ForkedTask
    status: ForkedAgentStatus = ForkedAgentStatus.CREATED
    result: Optional[ForkedResult] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    _task: Optional[asyncio.Task] = None
    
    async def run(self, executor: Callable[[str], Coroutine[Any, Any, str]]):
        """执行Forked任务"""
        self.status = ForkedAgentStatus.RUNNING
        self.started_at = datetime.now()
        
        try:
            # 执行任务
            response = await executor(self.task.prompt)
            
            self.result = ForkedResult(
                task_id=self.task.task_id,
                status=ForkedAgentStatus.COMPLETED,
                response=response,
                completed_at=datetime.now()
            )
        except Exception as e:
            self.result = ForkedResult(
                task_id=self.task.task_id,
                status=ForkedAgentStatus.FAILED,
                error=str(e),
                completed_at=datetime.now()
            )
        
        self.status = self.result.status
    
    def cancel(self):
        """取消任务"""
        if self._task and not self._task.done():
            self._task.cancel()
        self.status = ForkedAgentStatus.CANCELLED


class ForkedAgentService:
    """Forked Agent服务
    
    核心功能：
    1. 创建和管理Forked Agent实例
    2. 执行侧问题（不中断主流程）
    3. 并发任务调度
    4. 结果聚合
    """
    
    def __init__(self, max_concurrent_agents: int = 5):
        self.max_concurrent_agents = max_concurrent_agents
        self._agents: Dict[str, ForkedAgent] = {}
        self._running_tasks: set = set()
        self._lock = asyncio.Lock()
        
        # 缓存管理器（模拟共享缓存）
        self._prompt_cache: Dict[str, Any] = {}
        
        logger.info("✅ Forked Agent服务初始化成功")
    
    async def _execute_agent(self, prompt: str) -> str:
        """执行Agent推理（模拟实现）
        
        实际实现应调用LLM服务，但保持与主流程独立
        """
        # 模拟处理时间
        await asyncio.sleep(0.5)
        
        # 简单的响应生成
        responses = [
            "好的，我来回答这个问题。",
            "根据我的知识，答案是...",
            "让我分析一下这个问题...",
            "这是一个很好的问题！",
            "我来帮您解答。"
        ]
        
        # 根据prompt内容生成响应
        if "天气" in prompt:
            return "今天天气晴朗，气温适中。"
        elif "计算" in prompt:
            return "计算结果是：42"
        elif "分析" in prompt:
            return "分析完成，主要发现包括：1. 数据趋势明显；2. 存在潜在问题。"
        else:
            return responses[hash(prompt) % len(responses)] + "\n\n" + prompt[:50] + "..."
    
    async def create_side_question(self, question: str, 
                                  context: Optional[Dict[str, Any]] = None) -> ForkedResult:
        """创建并执行侧问题
        
        侧问题使用独立的Forked Agent，不中断主流程
        共享父Agent的prompt缓存，但不写入缓存
        
        Args:
            question: 用户侧问题
            context: 上下文信息
            
        Returns:
            任务结果
        """
        # 包装问题
        wrapped_prompt = self._wrap_side_question(question)
        
        # 创建任务
        task = ForkedTask(
            task_id=str(uuid.uuid4()),
            agent_type=ForkedAgentType.SIDE_QUESTION,
            prompt=wrapped_prompt,
            max_turns=1,
            can_use_tools=False,
            skip_cache_write=True
        )
        
        # 执行任务
        return await self._execute_task(task)
    
    def _wrap_side_question(self, question: str) -> str:
        """包装侧问题"""
        return f"""<system-reminder>This is a side question from the user. You must answer this question directly in a single response.

IMPORTANT CONTEXT:
- You are a separate, lightweight agent spawned to answer this one question
- The main agent is NOT interrupted - it continues working independently in the background
- You share the conversation context but are a completely separate instance
- Do NOT reference being interrupted or what you were "previously doing" - that framing is incorrect

CRITICAL CONSTRAINTS:
- You have NO tools available - you cannot read files, run commands, search, or take any actions
- This is a one-off response - there will be no follow-up turns
- You can ONLY provide information based on what you already know from the conversation context
- NEVER say things like "Let me try...", "I'll now...", "Let me check...", or promise to take any action
- If you don't know the answer, say so - do not offer to look it up or investigate

Simply answer the question with the information you have.</system-reminder>

{question}"""
    
    async def create_parallel_task(self, prompt: str, 
                                  can_use_tools: bool = True) -> ForkedResult:
        """创建并行任务
        
        Args:
            prompt: 任务prompt
            can_use_tools: 是否允许使用工具
            
        Returns:
            任务结果
        """
        task = ForkedTask(
            task_id=str(uuid.uuid4()),
            agent_type=ForkedAgentType.PARALLEL_TASK,
            prompt=prompt,
            max_turns=3,
            can_use_tools=can_use_tools,
            skip_cache_write=False
        )
        
        return await self._execute_task(task)
    
    async def _execute_task(self, task: ForkedTask) -> ForkedResult:
        """执行任务"""
        # 检查并发限制
        if len(self._running_tasks) >= self.max_concurrent_agents:
            return ForkedResult(
                task_id=task.task_id,
                status=ForkedAgentStatus.FAILED,
                error="达到最大并发数限制"
            )
        
        async with self._lock:
            # 创建Agent实例
            agent = ForkedAgent(
                agent_id=str(uuid.uuid4()),
                task=task
            )
            self._agents[agent.agent_id] = agent
        
        # 创建并执行任务
        async def _run():
            self._running_tasks.add(task.task_id)
            try:
                await agent.run(self._execute_agent)
            finally:
                self._running_tasks.discard(task.task_id)
        
        agent._task = asyncio.create_task(_run())
        await agent._task
        
        return agent.result if agent.result else ForkedResult(
            task_id=task.task_id,
            status=ForkedAgentStatus.FAILED,
            error="任务未返回结果"
        )
    
    async def run_parallel_tasks(self, tasks: List[Dict[str, Any]]) -> List[ForkedResult]:
        """并行执行多个任务
        
        Args:
            tasks: 任务列表，每个任务包含prompt和可选的can_use_tools
            
        Returns:
            任务结果列表
        """
        # 创建任务列表
        coroutines = []
        for task_data in tasks:
            prompt = task_data.get("prompt", "")
            can_use_tools = task_data.get("can_use_tools", False)
            
            coro = self.create_parallel_task(prompt, can_use_tools)
            coroutines.append(coro)
        
        # 并行执行
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        # 处理异常
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(ForkedResult(
                    task_id=f"task_{i}",
                    status=ForkedAgentStatus.FAILED,
                    error=str(result)
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    def get_agent_status(self, agent_id: str) -> Optional[ForkedAgentStatus]:
        """获取Agent状态"""
        agent = self._agents.get(agent_id)
        return agent.status if agent else None
    
    def get_task_result(self, task_id: str) -> Optional[ForkedResult]:
        """获取任务结果"""
        for agent in self._agents.values():
            if agent.task.task_id == task_id:
                return agent.result
        return None
    
    def get_running_tasks(self) -> List[Dict[str, Any]]:
        """获取运行中的任务"""
        return [
            {
                "agent_id": agent.agent_id,
                "task_id": agent.task.task_id,
                "type": agent.task.agent_type.value,
                "status": agent.status.value
            }
            for agent in self._agents.values()
            if agent.status == ForkedAgentStatus.RUNNING
        ]
    
    def cleanup_completed(self):
        """清理已完成的任务（保留最近10条）"""
        completed = [
            agent for agent in self._agents.values()
            if agent.status in [ForkedAgentStatus.COMPLETED, 
                               ForkedAgentStatus.FAILED, 
                               ForkedAgentStatus.CANCELLED]
        ]
        
        # 按完成时间排序，保留最近10条
        completed.sort(key=lambda x: x.result.completed_at if x.result else x.created_at, reverse=True)
        
        # 删除超出限制的
        for agent in completed[10:]:
            del self._agents[agent.agent_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        stats = {
            "total_agents": len(self._agents),
            "running": sum(1 for a in self._agents.values() if a.status == ForkedAgentStatus.RUNNING),
            "completed": sum(1 for a in self._agents.values() if a.status == ForkedAgentStatus.COMPLETED),
            "failed": sum(1 for a in self._agents.values() if a.status == ForkedAgentStatus.FAILED),
            "max_concurrent": self.max_concurrent_agents,
            "cache_size": len(self._prompt_cache)
        }
        return stats


# 全局单例
_forked_agent_service = None

def get_forked_agent_service() -> ForkedAgentService:
    """获取Forked Agent服务实例"""
    global _forked_agent_service
    if _forked_agent_service is None:
        _forked_agent_service = ForkedAgentService()
    return _forked_agent_service