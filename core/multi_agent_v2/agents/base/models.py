"""
BaseAgent 数据模型 — 精简版

只保留运行时实际使用的数据类。
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentType(Enum):
    """Agent类型 — 只有 WORKER，不预设角色"""
    GENERIC = "generic"
    WORKER = "worker"


@dataclass
class Task:
    """任务定义"""
    task_id: str
    type: str
    description: str
    keywords: List[str] = field(default_factory=list)
    complexity: float = 0.5
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

