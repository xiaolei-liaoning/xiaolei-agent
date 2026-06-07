"""
Workflow 数据模型 — Claude Code Dynamic Workflows 风格

Meta          — Workflow 元数据（名称、描述、阶段定义）
PhaseRecord   — 单阶段执行记录
WorkflowResult  — Workflow 执行结果
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
class WorkflowResult:
    """Workflow 执行结果"""
    success: bool = False
    output: Any = None
    error: Optional[str] = None
    phases: List[PhaseRecord] = field(default_factory=list)
    elapsed: float = 0.0
    label: str = ""
