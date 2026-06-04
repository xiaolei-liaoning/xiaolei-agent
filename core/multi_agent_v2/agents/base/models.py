"""
BaseAgent 数据模型

所有数据类、枚举、Pydantic 模型集中定义在此处，供 base_agent / mind / memory 共享使用。
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"          # 待执行
    RUNNING = "running"          # 执行中
    SUCCESS = "success"          # 执行成功
    FAILED = "failed"            # 执行失败
    SKIPPED = "skipped"          # 已跳过
    BLOCKED = "blocked"          # 依赖未就绪


class StepType(Enum):
    """步骤类型"""
    TOOL_CALL = "tool_call"       # 调用工具
    LLM_TASK = "llm_task"         # LLM 直接生成
    HUMAN_INPUT = "human_input"   # 需要用户输入
    SUBTASK = "subtask"           # 子任务（可委派给其他 Agent）
    DECISION = "decision"         # 决策分支点
    SEARCH = "search"             # 搜索/查询
    ANALYSIS = "analysis"         # 分析处理


@dataclass
class Step:
    """结构化步骤定义"""
    step_id: str                                      # 步骤唯一 ID
    name: str                                         # 步骤名称
    description: str                                  # 步骤描述
    type: StepType = StepType.TOOL_CALL               # 步骤类型
    status: StepStatus = StepStatus.PENDING           # 步骤状态
    dependencies: List[str] = field(default_factory=list)  # 依赖的 step_id 列表
    tool_name: str = ""                               # 如果是 TOOL_CALL，指定工具
    tool_args: Dict[str, Any] = field(default_factory=dict)  # 工具参数
    expected_output: str = ""                         # 预期产出描述
    result: Any = None                                # 执行结果
    error: Optional[str] = None                       # 错误信息
    execution_time: float = 0.0                       # 执行耗时（秒）
    metadata: Dict[str, Any] = field(default_factory=dict)
    agent_id: Optional[str] = None                    # 分配给哪个 Agent（None 表示当前）


@dataclass
class StepEvent:
    """步骤事件（用于进度回调）"""
    type: str                                         # step_start, step_complete, step_failed, step_skipped, step_progress
    step: Step                                        # 事件关联的步骤
    timestamp: float = field(default_factory=time.time)
    context: Optional[Dict[str, Any]] = None          # 额外上下文


@dataclass
class ExecutionResult:
    """分步执行结果"""
    success: bool                                     # 是否全部成功
    steps: List[Step]                                 # 所有步骤的最终状态
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    total_execution_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProgressSnapshot:
    """执行进度快照 — Agent 在 think() 时可见

    追踪已完成/进行中/待执行的步骤，以及各步骤的失败次数。
    to_prompt() 格式化为 LLM prompt 可读的文本看板。
    """
    completed: List[Dict] = field(default_factory=list)
    current: Optional[Dict] = None
    remaining: List[Dict] = field(default_factory=list)
    failed_attempts: Dict[str, int] = field(default_factory=dict)

    def to_prompt(self) -> str:
        lines = ["[执行进度]"]
        for c in self.completed:
            status = "✅" if c.get("status") == "success" else "❌"
            result = str(c.get("result", ""))[:120]
            lines.append(f"  {status} {c['step_id']} {c.get('name','')} — {result}")
        if self.current:
            fa = self.failed_attempts.get(self.current["step_id"], 0)
            warn = f" ⚠️ 已失败 {fa} 次" if fa > 0 else ""
            lines.append(f"  🔄 {self.current['step_id']} {self.current.get('name','')} — 执行中{warn}")
        for r in self.remaining:
            fa = self.failed_attempts.get(r["step_id"], 0)
            warn = f" ⚠️ 已失败 {fa} 次" if fa > 0 else ""
            lines.append(f"  ⏳ {r['step_id']} {r.get('name','')} — 待执行{warn}")
        if not lines:
            return "[执行进度] 尚未开始"
        return "\n".join(lines)


class NeedsReflection(Exception):
    """步骤失败 2 次后抛出的反思信号

    WorkAgent 捕获后决定是重试还是重规划。
    """
    def __init__(self, step_id: str, reason: str, progress: ProgressSnapshot,
                 remaining_steps: list, failed_step: dict = None):
        self.step_id = step_id
        self.reason = reason
        self.progress = progress
        self.remaining_steps = remaining_steps
        self.failed_step = failed_step or {}
        super().__init__(f"步骤 {step_id} 需要反思: {reason[:100]}")


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
    plan: List[str]                     # 执行计划（文本形式，兼容旧路径）
    confidence: float                   # 置信度
    alternatives: List[str] = field(default_factory=list)  # 备选方案
    tool_calls: List[Dict] = field(default_factory=list)   # LLM 选择的工具调用
    structured_plan: Optional[List[Step]] = None  # 结构化步骤（新路径）


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
