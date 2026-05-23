"""
BaseAgent 数据模型

所有数据类、枚举、Pydantic 模型集中定义在此处，供 base_agent / mind / memory 共享使用。
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class CommunicationTopic(Enum):
    """通信主题"""
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    VULNERABILITY_FOUND = "vuln_found"
    DATA_ANALYZED = "data_analyzed"
    BROADCAST = "broadcast"
    AGENT_MESSAGE = "agent_message"


class AgentState(Enum):
    """Agent状态"""
    CREATED = "created"           # 创建
    REGISTERED = "registered"     # 已注册
    IDLE = "idle"                 # 空闲
    READY = "ready"               # 准备就绪
    RUNNING = "running"           # 执行中
    WAITING = "waiting"           # 等待中
    COMPLETED = "completed"       # 完成任务
    FAILED = "failed"             # 执行失败
    STOPPED = "stopped"           # 已停止


class AgentType(Enum):
    """Agent类型 — 只有 WORKER，不预设角色"""
    GENERIC = "generic"
    WORKER = "worker"


@dataclass
class Capability:
    """Agent能力定义"""
    name: str                                     # 能力名称
    description: str                              # 能力描述
    keywords: List[str] = field(default_factory=list)  # 匹配关键词
    expertise_level: float = 0.5                  # 专业等级 (0-1)
    max_concurrent_tasks: int = 1                 # 最大并发任务数
    avg_execution_time: float = 10.0              # 平均执行时间（秒）
    success_rate: float = 0.9                     # 历史成功率
    preferred_tools: List[str] = field(default_factory=list)  # 偏好工具

    def match_score(self, task_keywords: List[str]) -> float:
        """计算与任务的匹配分数"""
        keyword_matches = sum(1 for kw in task_keywords if kw in self.keywords)
        return (keyword_matches / max(len(task_keywords), 1)) * self.expertise_level


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable
    permissions: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    is_concurrency_safe: bool = False


@dataclass
class Thought:
    """思考过程"""
    reasoning: str                       # 推理过程
    plan: List[str]                     # 执行计划
    confidence: float                   # 置信度
    alternatives: List[str] = field(default_factory=list)  # 备选方案
    tool_calls: List[Dict] = field(default_factory=list)   # LLM 选择的工具调用


@dataclass
class Reflection:
    """反思结果"""
    success: bool                       # 是否成功
    lessons_learned: List[str]          # 经验教训
    improvements: List[str]             # 改进建议
    performance_metrics: Dict[str, float]  # 性能指标


@dataclass
class AgentMetrics:
    """Agent性能指标"""
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_execution_time: float = 0.0
    total_execution_time: float = 0.0
    last_task_time: Optional[float] = None
    current_load: float = 0.0
    priority: float = 1.0

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return self.tasks_completed / total if total > 0 else 0.0


@dataclass
class Task:
    """任务定义"""
    task_id: str
    type: str
    description: str
    keywords: List[str] = field(default_factory=list)
    complexity: float = 0.5  # 任务复杂度 (0-1)
    estimated_steps: int = 3
    dependencies: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1
    deadline: Optional[float] = None


@dataclass
class ActionResult:
    """执行结果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    partial_results: List[Any] = field(default_factory=list)
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """Agent间消息"""
    message_id: str
    from_agent: str
    to_agent: Optional[str]  # None表示广播
    content: Any
    message_type: str
    timestamp: float = field(default_factory=time.time)
