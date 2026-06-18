"""Agency Agents 角色匹配 Skill

将 agency-agents-zh 的 144+ 个专家 Agent 角色注册为 Skill，
Worker Agent 可根据任务场景自主匹配最合适的专家角色。
"""

import logging
from typing import Any, Dict, List, Optional

from .skill_base import SkillHandler, ToolCallResult
from .skills.agency_agents.handler import get_agency_agent_matcher

logger = logging.getLogger(__name__)


class AgencyAgentMatcherSkill(SkillHandler):
    """Agency Agent 角色匹配技能

    根据用户输入的任务描述，自动匹配最合适的专家 Agent 角色。
    """

    name = "agency_agent_matcher"
    description = "根据任务场景自动匹配最合适的专家 Agent 角色（从 144+ 个专家中选择）"
    keywords = [
        "角色匹配",
        "专家匹配",
        "agent匹配",
        "任务分配",
        "role matching",
        "agent matching",
        "expert selection",
        "选择角色",
        "选择专家",
        "分配任务",
    ]
    priority = 8

    async def execute(
        self, params: Dict[str, Any], context: Any = None
    ) -> Dict[str, Any]:
        """执行角色匹配

        Args:
            params: 包含 task 参数的字典
            context: 执行上下文

        Returns:
            匹配结果
        """
        task = params.get("task", "")
        top_k = params.get("top_k", 3)

        if not task:
            return {
                "success": False,
                "error": "缺少 task 参数",
                "reply": "请提供任务描述以便匹配专家角色。",
            }

        try:
            matcher = get_agency_agent_matcher()
            matched_agents = matcher.match(task, top_k=top_k)

            if not matched_agents:
                return {
                    "success": True,
                    "reply": f"未找到匹配的专家角色。任务：{task}",
                    "matched_agents": [],
                    "suggestion": "请尝试更具体地描述任务，或联系通用助手。",
                }

            # 构建回复
            reply_parts = [f"✅ 已为任务匹配到 {len(matched_agents)} 个专家角色：\n"]

            for i, agent in enumerate(matched_agents, 1):
                emoji = agent.get("emoji", "👤")
                name = agent.get("name", "未知")
                category = agent.get("category", "unknown")
                description = agent.get("description", "")
                score = agent.get("match_score", 0)

                reply_parts.append(
                    f"{i}. {emoji} **{name}** ({category})\n"
                    f"   匹配度: {score:.1f}\n"
                    f"   专长: {description}\n"
                )

            # 推荐最佳匹配
            best = matched_agents[0]
            reply_parts.append(
                f"\n💡 推荐使用：**{best.get('emoji', '👤')} {best.get('name', '未知')}**\n"
                f"   ID: {best.get('id', '')}\n"
                f"   可通过此 ID 调用该专家角色。"
            )

            return {
                "success": True,
                "reply": "\n".join(reply_parts),
                "matched_agents": [
                    {
                        "id": a.get("id"),
                        "name": a.get("name"),
                        "category": a.get("category"),
                        "emoji": a.get("emoji"),
                        "match_score": a.get("match_score"),
                        "description": a.get("description"),
                    }
                    for a in matched_agents
                ],
                "best_match": matched_agents[0] if matched_agents else None,
            }

        except Exception as e:
            logger.error(f"Agency Agent 匹配失败: {e}")
            return {"success": False, "error": str(e), "reply": f"角色匹配失败: {e}"}


class AgencyAgentListSkill(SkillHandler):
    """列出所有可用的 Agency Agent 角色"""

    name = "agency_agent_list"
    description = "列出所有可用的专家 Agent 角色（144+ 个）"
    keywords = ["角色列表", "专家列表", "agent列表", "available agents", "list agents"]
    priority = 5

    async def execute(
        self, params: Dict[str, Any], context: Any = None
    ) -> Dict[str, Any]:
        """列出所有 Agent 角色"""
        try:
            matcher = get_agency_agent_matcher()
            agents = matcher.list_agents()
            categories = matcher.get_all_categories()

            # 按分类组织
            reply_parts = [f"📋 可用专家角色列表（共 {len(agents)} 个）：\n"]

            for category in categories:
                cat_agents = [a for a in agents if a.get("category") == category]
                if cat_agents:
                    reply_parts.append(f"\n**{category}** ({len(cat_agents)} 个):")
                    for agent in cat_agents:
                        emoji = agent.get("emoji", "👤")
                        name = agent.get("name", "未知")
                        reply_parts.append(f"  {emoji} {name}")

            return {
                "success": True,
                "reply": "\n".join(reply_parts),
                "agents": agents,
                "categories": categories,
                "total_count": len(agents),
            }

        except Exception as e:
            logger.error(f"获取 Agent 列表失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "reply": f"获取角色列表失败: {e}",
            }


class AgencyAgentExecuteSkill(SkillHandler):
    """执行指定的 Agency Agent 角色"""

    name = "agency_agent_execute"
    description = "执行指定的专家 Agent 角色任务"
    keywords = ["执行角色", "调用专家", "execute agent", "run expert"]
    priority = 7

    async def execute(
        self, params: Dict[str, Any], context: Any = None
    ) -> Dict[str, Any]:
        """执行指定的 Agent 角色"""
        agent_id = params.get("agent_id", "")
        task = params.get("task", "")

        if not agent_id:
            return {
                "success": False,
                "error": "缺少 agent_id 参数",
                "reply": "请指定要执行的专家角色 ID。",
            }

        if not task:
            return {
                "success": False,
                "error": "缺少 task 参数",
                "reply": "请提供任务描述。",
            }

        try:
            matcher = get_agency_agent_matcher()
            agent = matcher.get_agent_by_id(agent_id)

            if not agent:
                return {
                    "success": False,
                    "error": f"未找到 Agent: {agent_id}",
                    "reply": f"未找到专家角色 '{agent_id}'。请使用 agency_agent_list 查看可用角色。",
                }

            # 获取角色定义文件路径
            agent_file = self._find_agent_file(agent_id)

            if agent_file:
                with open(agent_file, "r", encoding="utf-8") as f:
                    agent_prompt = f.read()

                return {
                    "success": True,
                    "reply": f"✅ 已加载专家角色：**{agent.get('emoji', '👤')} {agent.get('name', '未知')}**\n\n"
                    f"任务：{task}\n\n"
                    f"角色定义已加载，可开始执行任务。",
                    "agent": agent,
                    "agent_prompt": agent_prompt,
                    "task": task,
                }
            else:
                return {
                    "success": True,
                    "reply": f"✅ 已选择专家角色：**{agent.get('emoji', '👤')} {agent.get('name', '未知')}**\n\n"
                    f"任务：{task}\n\n"
                    f"角色描述：{agent.get('description', '')}",
                    "agent": agent,
                    "task": task,
                }

        except Exception as e:
            logger.error(f"执行 Agent 角色失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "reply": f"执行专家角色失败: {e}",
            }

    def _find_agent_file(self, agent_id: str) -> Optional[str]:
        """查找 Agent 角色定义文件"""
        import os

        # agency-agents-zh 项目路径
        base_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",  # 回到项目根目录
            "agency-agents-zh",
        )
        base_path = os.path.normpath(base_path)

        if not os.path.exists(base_path):
            return None

        # 遍历查找
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.endswith(".md") and agent_id in file:
                    return os.path.join(root, file)

        return None
