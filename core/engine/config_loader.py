"""配置驱动的服务加载器

补上了 system_init.py:_step_config_driven_services 中缺失的引用。

功能委托给已有实现：
  auto_connect_mcp_servers    → ToolRegistry.discover_all()（MCP 并行连接，幂等）
  register_agents_from_config → 从 config/agents.yml 加载代理配置并返回
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def auto_connect_mcp_servers() -> None:
    """自动连接 MCP 服务器

    委托给 V2 ToolRegistry.discover_all()，它内置了并行 MCP 连接。
    如果 ToolRegistry 已经初始化过则跳过。config/mcp_servers.yml 中
    auto_connect: true 的服务器会在此阶段启动。
    """
    try:
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry

        reg = get_tool_registry()
        # 幂等：如果初始化步骤已经 connect 过，跳过
        if reg._initialized:
            logger.info("MCP 服务器已在初始化步骤中连接，跳过")
            return

        await reg.discover_all()
        mcp_count = sum(
            1 for t in reg._tools.values() if t.server not in ("__builtin__", "")
        )
        if mcp_count:
            logger.info("MCP 自动连接完成: %d 个 MCP 工具已注册", mcp_count)
    except Exception as e:
        logger.warning("MCP 自动连接失败（系统仍可运行）: %s", e)


def register_agents_from_config() -> List[Dict[str, Any]]:
    """从 config/agents.yml 读取 Agent 配置并注册

    配置文件定义了 8 个 Agent，包含角色描述和工具列表。
    实际运行时 WorkAgent 通过 core.skills.base_skills.SkillSystem
    在 _execute_fast 中按需加载这些配置注入个性。
    此函数仅确保启动时有日志记录和验证。

    Returns:
        Agent 配置列表，每项含 id/name/role_prompt/tools/priority
    """
    config_path = (
        Path(__file__).resolve().parent.parent.parent / "config" / "agents.yml"
    )
    if not config_path.exists():
        logger.warning("Agent 配置文件不存在: %s", config_path)
        return []

    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        agents_data = data.get("agents", {})

        agents = []
        for agent_id, config in agents_data.items():
            entry = {
                "id": agent_id,
                "name": config.get("name", agent_id),
                "role_prompt": config.get("role_prompt", ""),
                "tools": config.get("tools", []),
                "priority": config.get("priority", 1),
            }
            agents.append(entry)

        logger.info(
            "从 config/agents.yml 加载 %d 个 Agent 配置: %s",
            len(agents),
            ", ".join(a["id"] for a in agents),
        )
        return agents
    except Exception as e:
        logger.warning("加载 Agent 配置失败: %s", e)
        return []
