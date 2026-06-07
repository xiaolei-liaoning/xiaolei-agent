"""
Workflow 数据模型

Meta          — Workflow 元数据（名称、描述、阶段定义）
PhaseRecord   — 单阶段执行记录
WorkflowContext — Runtime 注入到脚本的执行上下文
WorkflowResult  — Workflow 执行结果
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.multi_agent_v2.orchestration.orchestrator import AgentResult


@dataclass
class Meta:
    """Workflow 元数据"""
    name: str = ""
    description: str = ""
    phases: List[Dict] = field(default_factory=list)
    # phases: [{"title": "搜索", "detail": "..."}, {"title": "分析", ...}]


@dataclass
class PhaseRecord:
    """单阶段执行记录"""
    title: str = ""
    detail: str = ""
    agent_calls: int = 0
    elapsed: float = 0.0


@dataclass
class WorkflowContext:
    """执行上下文 — Runtime 注入到脚本的接口

    脚本通过 ctx.agent / ctx.parallel / ctx.phase 访问。
    Runtime 在 run() 时创建并注入这些方法。
    """

    meta: Meta

    # ── 执行记录 ──
    _results: List[AgentResult] = field(default_factory=list)
    _current_phase: str = ""
    _phase_start: float = 0.0
    _phase_history: List[PhaseRecord] = field(default_factory=list)

    # ── 由 Runtime 注入的编排原语 ──
    # 签名: agent(prompt, opts?) -> AgentResult
    agent: Optional[Callable] = None
    # 签名: parallel(thunks) -> List[AgentResult|None]
    parallel: Optional[Callable] = None
    # 签名: pipeline(items, *stages) -> List[Any]
    pipeline: Optional[Callable] = None
    # 签名: phase(title) -> None
    phase: Optional[Callable] = None
    # 签名: log(msg) -> None
    log: Optional[Callable] = None


@dataclass
class WorkflowResult:
    """Workflow 执行结果"""
    success: bool = False
    output: Any = None
    error: Optional[str] = None
    phases: List[PhaseRecord] = field(default_factory=list)
    agent_results: List[AgentResult] = field(default_factory=list)
    elapsed: float = 0.0
    label: str = ""
