"""Agency Agents 角色匹配器 — 让 Worker Agent 自主匹配专家角色

从 agency-agents-zh 项目导入 144+ 个专家 Agent 角色，
Worker Agent 根据任务场景自动匹配最合适的专家角色。

用法：
    from core.skills.agency_agents.handler import AgencyAgentMatcher

    matcher = AgencyAgentMatcher()
    matched = matcher.match("帮我设计一个高并发的后端系统")
    # 返回: {"name": "后端架构师", "id": "engineering-backend-architect", ...}
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "agents_config.yaml")


class AgencyAgentMatcher:
    """Agency Agent 角色匹配器

    根据用户输入的任务描述，自动匹配最合适的专家 Agent 角色。
    """

    def __init__(self, config_path: str = None):
        self.config_path = config_path or CONFIG_PATH
        self.agents: List[Dict[str, Any]] = []
        self._load_config()

    def _load_config(self):
        """加载 YAML 配置文件"""
        if not os.path.exists(self.config_path):
            logger.warning(f"Agency Agents 配置文件不存在: {self.config_path}")
            self.agents = []
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self.agents = []
            for category, agents in config.items():
                if isinstance(agents, list):
                    for agent in agents:
                        agent["category"] = category
                        self.agents.append(agent)

            logger.info(f"✅ 已加载 {len(self.agents)} 个 Agency Agent 角色")
        except Exception as e:
            logger.error(f"加载 Agency Agents 配置失败: {e}")
            self.agents = []

    def match(self, task: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """匹配最合适的 Agent 角色

        Args:
            task: 任务描述
            top_k: 返回前 K 个匹配结果

        Returns:
            匹配的 Agent 列表，按匹配度排序
        """
        if not self.agents:
            return []

        task_lower = task.lower()
        scores = []

        for agent in self.agents:
            score = self._calculate_score(agent, task_lower)
            if score > 0:
                scores.append((score, agent))

        # 按分数降序排序
        scores.sort(key=lambda x: x[0], reverse=True)

        # 返回 top_k
        result = []
        for score, agent in scores[:top_k]:
            matched_agent = agent.copy()
            matched_agent["match_score"] = score
            result.append(matched_agent)

        return result

    def _calculate_score(self, agent: Dict[str, Any], task_lower: str) -> float:
        """计算 Agent 与任务的匹配分数"""
        score = 0.0

        # 1. 关键词匹配 (权重: 1.0)
        keywords = agent.get("keywords", [])
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in task_lower:
                score += 1.0
            # 模糊匹配：对于短关键词，计算字符重叠度
            elif len(kw) <= 4:
                chars = sum(1 for c in kw_lower if c in task_lower)
                if chars >= len(kw_lower) * 0.7:
                    score += 0.5

        # 2. 匹配模式匹配 (权重: 2.0)
        match_patterns = agent.get("match_patterns", [])
        for pattern in match_patterns:
            try:
                if re.search(pattern, task_lower):
                    score += 2.0
            except re.error:
                # 正则表达式错误，跳过
                pass

        # 3. 名称匹配 (权重: 3.0)
        name = agent.get("name", "").lower()
        if name in task_lower:
            score += 3.0

        # 4. 描述匹配 (权重: 0.5)
        description = agent.get("description", "").lower()
        desc_words = re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z]{3,}", description)
        for word in desc_words[:10]:  # 只检查前10个词
            if word.lower() in task_lower:
                score += 0.5

        return score

    def get_agent_by_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取 Agent"""
        for agent in self.agents:
            if agent.get("id") == agent_id:
                return agent
        return None

    def get_agents_by_category(self, category: str) -> List[Dict[str, Any]]:
        """获取指定分类的所有 Agent"""
        return [a for a in self.agents if a.get("category") == category]

    def get_all_categories(self) -> List[str]:
        """获取所有分类"""
        categories = set()
        for agent in self.agents:
            categories.add(agent.get("category", "unknown"))
        return sorted(categories)

    def list_agents(self) -> List[Dict[str, str]]:
        """列出所有 Agent 的简要信息"""
        return [
            {
                "id": a["id"],
                "name": a["name"],
                "category": a["category"],
                "emoji": a.get("emoji", ""),
                "description": a.get("description", ""),
            }
            for a in self.agents
        ]


# 全局单例
_matcher: Optional[AgencyAgentMatcher] = None


def get_agency_agent_matcher() -> AgencyAgentMatcher:
    """获取全局 Agency Agent 匹配器实例"""
    global _matcher
    if _matcher is None:
        _matcher = AgencyAgentMatcher()
    return _matcher


def reset_agency_agent_matcher():
    """重置全局匹配器（用于测试）"""
    global _matcher
    _matcher = None
