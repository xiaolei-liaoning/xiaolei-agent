"""Worker Agent 角色自动匹配器

在 V1 队长-队员系统中，Worker Agent 可根据任务场景自主匹配专家角色。
"""

import logging
from typing import Any, Dict, Optional

from core.skills.agency_agents.handler import get_agency_agent_matcher

logger = logging.getLogger(__name__)


class WorkerAgentRoleMatcher:
    """Worker Agent 角色匹配器

    为 V1 队长-队员系统提供角色匹配功能，
    Worker Agent 可根据分配的任务自动选择合适的专家角色。
    """

    def __init__(self):
        self.matcher = get_agency_agent_matcher()

    def match_role_for_task(
        self, task: str, worker_name: str = None
    ) -> Optional[Dict[str, Any]]:
        """为任务匹配最适合的 Worker Agent 角色

        Args:
            task: 任务描述
            worker_name: Worker 名称（可选）

        Returns:
            匹配的 Agent 角色信息
        """
        matched = self.matcher.match(task, top_k=1)

        if not matched:
            return None

        best_match = matched[0]

        logger.info(
            f"🎯 Worker '{worker_name or 'unknown'}' 自动匹配角色: "
            f"{best_match.get('emoji', '👤')} {best_match.get('name', '未知')} "
            f"(匹配度: {best_match.get('match_score', 0):.1f})"
        )

        return best_match

    def assign_roles_to_workers(self, task: str, worker_count: int = 3) -> list:
        """为多个 Worker 分配不同的专家角色

        Args:
            task: 任务描述
            worker_count: Worker 数量

        Returns:
            Worker 角色分配列表
        """
        matched = self.matcher.match(task, top_k=worker_count)

        if not matched:
            return []

        assignments = []
        for i, agent in enumerate(matched):
            assignments.append(
                {
                    "worker_index": i,
                    "worker_name": f"worker_{i}",
                    "role": agent.get("name"),
                    "role_id": agent.get("id"),
                    "emoji": agent.get("emoji", "👤"),
                    "category": agent.get("category"),
                    "match_score": agent.get("match_score", 0),
                    "description": agent.get("description", ""),
                }
            )

            logger.info(
                f"👷 Worker {i} 分配角色: {agent.get('emoji', '👤')} {agent.get('name', '未知')} "
                f"({agent.get('category', 'unknown')})"
            )

        return assignments

    def get_role_prompt(self, agent_id: str) -> Optional[str]:
        """获取专家角色的系统提示词

        Args:
            agent_id: Agent ID

        Returns:
            角色提示词
        """
        import os

        agent = self.matcher.get_agent_by_id(agent_id)
        if not agent:
            return None

        # 查找角色定义文件
        base_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "agency-agents-zh"
        )
        base_path = os.path.normpath(base_path)

        if not os.path.exists(base_path):
            return agent.get("description", "")

        # 遍历查找
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.endswith(".md") and agent_id in file:
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        return f.read()

        return agent.get("description", "")


# 全局单例
_role_matcher: Optional[WorkerAgentRoleMatcher] = None


def get_worker_role_matcher() -> WorkerAgentRoleMatcher:
    """获取全局 Worker Agent 角色匹配器"""
    global _role_matcher
    if _role_matcher is None:
        _role_matcher = WorkerAgentRoleMatcher()
    return _role_matcher


def reset_worker_role_matcher():
    """重置全局匹配器（用于测试）"""
    global _role_matcher
    _role_matcher = None
