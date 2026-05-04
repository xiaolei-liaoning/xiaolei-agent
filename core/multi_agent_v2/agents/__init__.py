"""
Agents模块 - 多Agent系统中的各种Agent实现

包含：
- BaseAgent: 基础Agent类
- MasterAgent: 主Agent，负责任务分解和结果聚合
- WorkerAgent: 执行Agent，负责具体任务执行
- ReviewerAgent: 评审Agent，负责质量把关
- ExpertAgent: 专家Agent，提供领域知识
- LazyAgent: 懒加载Agent，按需初始化
"""

from core.multi_agent_v2.agents.base.base_agent import BaseAgent, AgentType
from core.multi_agent_v2.agents.master.master_agent import MasterAgent
from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
from core.multi_agent_v2.agents.reviewer.reviewer_agent import ReviewerAgent
from core.multi_agent_v2.agents.expert.expert_agent import ExpertAgent
from core.multi_agent_v2.agents.lazy_agent import LazyAgent, LazyAgentFactory, get_lazy_factory

__all__ = [
    "BaseAgent",
    "AgentType",
    "MasterAgent",
    "WorkerAgent",
    "ReviewerAgent",
    "ExpertAgent",
    "LazyAgent",
    "LazyAgentFactory",
    "get_lazy_factory",
]
