"""
RoleTemplate — 角色模板池

替代固定的 Master/Worker/Reviewer 类。
调度器根据任务类型动态选模板、动态实例 Agent。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class RoleType(Enum):
    """角色类型"""
    TASK_DECOMPOSER = "task_decomposer"    # 任务拆解员
    TOOL_EXECUTOR = "tool_executor"        # 工具执行者
    REVIEWER = "reviewer"                  # 评审员
    RESEARCHER = "researcher"              # 研究员
    INTEGRATOR = "integrator"              # 结果整合员


@dataclass
class RoleTemplate:
    """角色模板定义"""
    role_type: RoleType
    name: str
    description: str
    system_prompt_key: str                 # 对应 prompts 中的 key
    default_capabilities: List[str] = field(default_factory=list)
    preferred_strategies: List[str] = field(default_factory=lambda: ["pipeline"])
    max_concurrency: int = 3
    expertise_level: float = 0.5

    def match_score(self, task_keywords: List[str]) -> float:
        """计算与任务关键词的匹配分数"""
        if not task_keywords or not self.default_capabilities:
            return 0.3
        matches = sum(
            1 for kw in task_keywords
            if any(kw in cap for cap in self.default_capabilities)
        )
        return min(matches / len(task_keywords), 1.0) * self.expertise_level


# ─── 预置角色模板 ─────────────────────────────────────────

ROLE_TEMPLATES: Dict[RoleType, RoleTemplate] = {
    RoleType.TASK_DECOMPOSER: RoleTemplate(
        role_type=RoleType.TASK_DECOMPOSER,
        name="任务拆解员",
        description="将复杂任务拆解为可执行的子任务，分析依赖关系",
        system_prompt_key="task_decomposer",
        default_capabilities=["task_decomposition", "dependency_analysis", "planning"],
        preferred_strategies=["master_slave", "pipeline"],
        expertise_level=0.8,
    ),
    RoleType.TOOL_EXECUTOR: RoleTemplate(
        role_type=RoleType.TOOL_EXECUTOR,
        name="工具执行者",
        description="执行具体工具调用：爬虫、搜索、分析等",
        system_prompt_key="worker",
        default_capabilities=["web_scraping", "data_analysis", "api_call", "search"],
        preferred_strategies=["pipeline", "master_slave", "auction"],
        max_concurrency=5,
        expertise_level=0.6,
    ),
    RoleType.REVIEWER: RoleTemplate(
        role_type=RoleType.REVIEWER,
        name="评审员",
        description="审查执行结果，确保质量，提出改进建议",
        system_prompt_key="reviewer",
        default_capabilities=["quality_check", "error_detection", "optimization"],
        preferred_strategies=["review"],
        expertise_level=0.7,
    ),
    RoleType.RESEARCHER: RoleTemplate(
        role_type=RoleType.RESEARCHER,
        name="研究员",
        description="信息检索、资料收集、知识整理",
        system_prompt_key="worker",
        default_capabilities=["research", "information_retrieval", "summarization"],
        preferred_strategies=["pipeline", "auction"],
        expertise_level=0.6,
    ),
    RoleType.INTEGRATOR: RoleTemplate(
        role_type=RoleType.INTEGRATOR,
        name="结果整合员",
        description="汇总各Agent结果，生成最终输出",
        system_prompt_key="master",
        default_capabilities=["result_aggregation", "report_generation"],
        preferred_strategies=["master_slave", "review"],
        expertise_level=0.7,
    ),
}


def get_template(role_type: RoleType) -> Optional[RoleTemplate]:
    """按角色类型获取模板"""
    return ROLE_TEMPLATES.get(role_type)


def select_templates_for_task(
    task_keywords: List[str],
    estimated_steps: int,
    max_agents: int = 5,
) -> List[RoleTemplate]:
    """根据任务特征选择合适的角色模板组合

    Args:
        task_keywords: 任务关键词
        estimated_steps: 预估步骤数
        max_agents: 最大Agent数

    Returns:
        排序后的模板列表
    """
    scored = [
        (template, template.match_score(task_keywords))
        for template in ROLE_TEMPLATES.values()
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    # 至少返回一个 TOOL_EXECUTOR
    templates = [t for t, s in scored if s > 0.2]
    if not any(t.role_type == RoleType.TOOL_EXECUTOR for t in templates):
        templates.append(ROLE_TEMPLATES[RoleType.TOOL_EXECUTOR])

    # 如果步骤多，加一个 TASK_DECOMPOSER
    if estimated_steps > 3 and RoleType.TASK_DECOMPOSER not in [t.role_type for t in templates]:
        templates.insert(0, ROLE_TEMPLATES[RoleType.TASK_DECOMPOSER])

    # 如果步骤多或复杂度高，加 REVIEWER
    if estimated_steps > 5 and RoleType.REVIEWER not in [t.role_type for t in templates]:
        templates.append(ROLE_TEMPLATES[RoleType.REVIEWER])

    return templates[:max_agents]
