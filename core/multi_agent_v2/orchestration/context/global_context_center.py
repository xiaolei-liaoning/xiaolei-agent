"""
全局上下文与状态中心 - 多Agent协作的核心

负责：
1. 任务状态追踪
2. 共享上下文管理
3. 状态广播与同步
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)

class TaskState(Enum):
    """任务状态"""
    PENDING = "pending"           # 待处理
    DECOMPOSED = "decomposed"     # 已分解
    SCHEDULED = "scheduled"       # 已调度
    RUNNING = "running"           # 执行中
    WAITING = "waiting"           # 等待中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    CANCELLED = "cancelled"       # 已取消


# EventType/Event/EventSystem 已移除 —— 通知改用 SharedBus


@dataclass
class TaskContext:
    """任务上下文"""
    task_id: str
    original_request: str
    decomposed_subtasks: List[Dict[str, Any]] = field(default_factory=list)
    assigned_agents: Dict[str, str] = field(default_factory=dict)  # subtask_id -> agent_id
    partial_results: Dict[str, Any] = field(default_factory=dict)
    final_result: Optional[Any] = None
    state: TaskState = TaskState.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedContext:
    """共享上下文"""
    task_id: str
    global_data: Dict[str, Any] = field(default_factory=dict)
    agent_views: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    revision: int = 0

    def update(self, agent_id: str, key: str, value: Any) -> None:
        """更新共享数据"""
        self.global_data[key] = value
        self.agent_views[agent_id] = self.agent_views.get(agent_id, {})
        self.agent_views[agent_id][key] = value
        self.revision += 1

    def get_snapshot(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """获取上下文快照"""
        if agent_id:
            view = self.agent_views.get(agent_id, {})
            return {**self.global_data, **view}
        return self.global_data.copy()


# Event/EventSystem 已移除 —— 通知改用 SharedBus


class GlobalContextCenter:
    """全局上下文与状态中心 - 多Agent协作的核心"""

    _instance: Optional["GlobalContextCenter"] = None
    _instance_lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 防止 __init__ 重复执行
        if getattr(self, "_initialized", False):
            return

        # 任务上下文管理
        self.task_contexts: Dict[str, TaskContext] = {}

        # 共享上下文
        self.shared_contexts: Dict[str, SharedContext] = {}

        # 消息总线 — 使用 SharedBus（全局单例）
        # 事件系统已移除 -- 通知改用 SharedBus

        # Agent注册表
        self.agent_registry: Dict[str, Dict[str, Any]] = {}

        # 追踪ID生成器
        self.trace_id_counter = 0

        # 锁
        self._lock = asyncio.Lock()

        # ── Token 预算（Layer 3 会用） ──────────────────
        self._max_context_tokens: int = 32000

        self._initialized = True
        logger.info("全局上下文中心初始化完成")

    def generate_trace_id(self) -> str:
        """生成追踪ID"""
        self.trace_id_counter += 1
        return f"trace_{self.trace_id_counter}_{int(time.time())}"

    async def create_task_context(self, request: str, trace_id: Optional[str] = None, task_id: Optional[str] = None) -> str:
        """创建任务上下文"""
        if task_id is None:
            task_id = f"task_{uuid.uuid4().hex[:12]}"

        context = TaskContext(
            task_id=task_id,
            original_request=request
        )

        async with self._lock:
            self.task_contexts[task_id] = context
            self.shared_contexts[task_id] = SharedContext(task_id=task_id)

        logger.info(f"创建任务上下文: {task_id}")
        return task_id

    async def update_task_state(self, task_id: str, state: TaskState, metadata: Optional[Dict] = None) -> None:
        """更新任务状态"""
        async with self._lock:
            if task_id not in self.task_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            context = self.task_contexts[task_id]
            context.state = state
            context.updated_at = time.time()

            if metadata:
                context.metadata.update(metadata)

        logger.info(f"任务状态更新: {task_id} -> {state.value}")

    async def update_context(self, task_id: str, agent_id: str, key: str, value: Any) -> None:
        """更新共享上下文"""
        async with self._lock:
            if task_id not in self.shared_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            shared_context = self.shared_contexts[task_id]
            shared_context.update(agent_id, key, value)

        # 检查 token 预算，超限则剪枝
        self._check_and_prune(task_id)

    async def get_context(self, task_id: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """获取上下文"""
        if task_id not in self.shared_contexts:
            raise ValueError(f"任务 {task_id} 不存在")

        shared_context = self.shared_contexts[task_id]
        return shared_context.get_snapshot(agent_id)

    async def register_agent(self, agent_id: str, agent_info: Dict[str, Any]) -> None:
        """注册Agent"""
        async with self._lock:
            self.agent_registry[agent_id] = {
                **agent_info,
                "registered_at": time.time(),
                "state": "active"
            }


        logger.info(f"Agent注册: {agent_id}")

    async def update_agent_state(self, agent_id: str, state: str) -> None:
        """更新Agent状态"""
        async with self._lock:
            if agent_id in self.agent_registry:
                self.agent_registry[agent_id]["state"] = state
                self.agent_registry[agent_id]["last_update"] = time.time()

        # 发布状态变更事件

    async def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取Agent信息"""
        return self.agent_registry.get(agent_id)

    async def get_all_agents(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有Agent"""
        if state:
            return [a for a in self.agent_registry.values() if a.get("state") == state]
        return list(self.agent_registry.values())

    async def assign_subtask(self, task_id: str, subtask_id: str, agent_id: str) -> None:
        """分配子任务"""
        async with self._lock:
            if task_id not in self.task_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            context = self.task_contexts[task_id]
            context.assigned_agents[subtask_id] = agent_id

        # 发布任务分配事件

        logger.info(f"子任务分配: {subtask_id} -> Agent {agent_id}")

    async def update_partial_result(self, task_id: str, agent_id: str, subtask_id: str, result: Any) -> None:
        """更新部分结果"""
        async with self._lock:
            if task_id not in self.task_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            context = self.task_contexts[task_id]
            context.partial_results[subtask_id] = {
                "agent_id": agent_id,
                "result": result,
                "timestamp": time.time()
            }
            context.updated_at = time.time()

        logger.info(f"部分结果更新: {task_id}.{subtask_id} by Agent {agent_id}")

    async def get_partial_results(self, task_id: str) -> Dict[str, Any]:
        """获取所有部分结果"""
        if task_id not in self.task_contexts:
            raise ValueError(f"任务 {task_id} 不存在")

        return self.task_contexts[task_id].partial_results.copy()

    async def set_final_result(self, task_id: str, result: Any) -> None:
        """设置最终结果"""
        async with self._lock:
            if task_id not in self.task_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            context = self.task_contexts[task_id]
            context.final_result = result
            context.state = TaskState.COMPLETED
            context.updated_at = time.time()

        logger.info(f"任务完成: {task_id}")

    async def get_task_context(self, task_id: str) -> Optional[TaskContext]:
        """获取任务上下文"""
        return self.task_contexts.get(task_id)

    # ── Token 预算与剪枝 ─────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(text: Any) -> int:
        """估算文本 token 数（对中文友好）。"""
        import re
        text = str(text)
        if not text:
            return 0
        cjk = len(re.findall(r'[一-鿿぀-ヿ]', text))
        ascii_chars = sum(1 for c in text if ord(c) < 128 and c != '\n')
        other = max(0, len(text) - cjk - ascii_chars)
        return int(cjk * 1.5 + ascii_chars / 4 + other / 2) + 1

    def _estimate_task_tokens(self, task_id: str) -> int:
        """估算指定任务的总 token 消耗。"""
        ctx = self.task_contexts.get(task_id)
        if not ctx:
            return 0
        total = self._estimate_tokens(ctx.original_request)
        total += self._estimate_tokens(ctx.partial_results)
        total += self._estimate_tokens(ctx.final_result)
        total += self._estimate_tokens(ctx.metadata)
        for agent_id in ctx.assigned_agents.values():
            total += self._estimate_tokens(agent_id)
        shared = self.shared_contexts.get(task_id)
        if shared:
            total += self._estimate_tokens(shared.global_data)
        return total

    def _check_and_prune(self, task_id: str) -> bool:
        """检查 token 预算并在超限时剪枝。返回 True 表示已剪枝。"""
        total = self._estimate_task_tokens(task_id)
        if total <= self._max_context_tokens:
            return False

        ctx = self.task_contexts.get(task_id)
        if not ctx:
            return False

        logger.info(f"上下文超限: task={task_id} tokens={total} > max={self._max_context_tokens}")

        # 分级剪枝策略
        pruned = False

        # Level 1: 移除最早的 partial_results（保留最近 3 个）
        if len(ctx.partial_results) > 3:
            sorted_keys = sorted(ctx.partial_results.keys(),
                                 key=lambda k: ctx.partial_results[k].get("timestamp", 0))
            for old_key in sorted_keys[:-3]:
                del ctx.partial_results[old_key]
                pruned = True

        # Level 2: 折叠连续的事件记录（仅保留最近 20 条）
            pruned = True

        # Level 3: 如果仍然超限，从 shared_contexts 中移除最旧的 key
        shared = self.shared_contexts.get(task_id)
        if shared and self._estimate_task_tokens(task_id) > self._max_context_tokens:
            if len(shared.global_data) > 10:
                old_keys = list(shared.global_data.keys())[:-10]
                for k in old_keys:
                    del shared.global_data[k]
                    pruned = True

        if pruned:
            logger.info(f"上下文剪枝完成: task={task_id}")

        return pruned

    async def cleanup_completed_tasks(self, older_than_hours: int = 24) -> int:
        """清理已完成的任务"""
        cutoff_time = time.time() - (older_than_hours * 3600)
        cleaned = 0

        async with self._lock:
            completed_tasks = [
                task_id for task_id, ctx in self.task_contexts.items()
                if ctx.state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]
                and ctx.updated_at < cutoff_time
            ]

            for task_id in completed_tasks:
                del self.task_contexts[task_id]
                if task_id in self.shared_contexts:
                    del self.shared_contexts[task_id]
                cleaned += 1

        if cleaned > 0:
            logger.info(f"清理了 {cleaned} 个已完成任务")

        return cleaned
