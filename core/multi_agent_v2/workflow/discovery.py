"""
Discovery — 自动发现和注册

提供：
  - discover_agents(): 扫描 .claude/agents 目录
  - discover_commands(): 扫描 .claude/commands 目录
"""

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def discover_agents(
    project_dir: Optional[str] = None,
    home_dir: Optional[str] = None,
) -> int:
    """发现并注册所有 Agents

    扫描位置（优先级从高到低）：
      1. {project_dir}/.claude/agents
      2. {home_dir}/.claude/agents

    Args:
        project_dir: 项目根目录（可选，默认当前工作目录）
        home_dir: 用户主目录（可选，默认 ~）

    Returns:
        int: 加载的 Agent 总数
    """
    from core.multi_agent_v2.workflow.subagent.registry import (
        get_subagent_registry,
    )

    registry = get_subagent_registry()
    count = 0

    # 确定目录
    if project_dir is None:
        project_dir = os.getcwd()
    if home_dir is None:
        home_dir = os.path.expanduser("~")

    # 扫描项目目录
    project_agents_dir = os.path.join(project_dir, ".claude", "agents")
    if os.path.isdir(project_agents_dir):
        count += registry.load_from_directory(project_agents_dir)

    # 扫描用户目录
    home_agents_dir = os.path.join(home_dir, ".claude", "agents")
    if os.path.isdir(home_agents_dir) and home_agents_dir != project_agents_dir:
        count += registry.load_from_directory(home_agents_dir)

    logger.info(f"Discovery: 共发现 {count} 个 Agents")
    return count


def discover_commands(
    project_dir: Optional[str] = None,
    home_dir: Optional[str] = None,
) -> int:
    """发现并注册所有 Commands

    扫描位置（优先级从高到低）：
      1. {project_dir}/.claude/commands
      2. {home_dir}/.claude/commands

    Args:
        project_dir: 项目根目录（可选，默认当前工作目录）
        home_dir: 用户主目录（可选，默认 ~）

    Returns:
        int: 加载的 Command 总数
    """
    from core.multi_agent_v2.workflow.command import get_command_registry

    registry = get_command_registry()
    count = 0

    # 确定目录
    if project_dir is None:
        project_dir = os.getcwd()
    if home_dir is None:
        home_dir = os.path.expanduser("~")

    # 扫描项目目录
    project_commands_dir = os.path.join(project_dir, ".claude", "commands")
    if os.path.isdir(project_commands_dir):
        count += registry.scan(project_commands_dir)

    # 扫描用户目录
    home_commands_dir = os.path.join(home_dir, ".claude", "commands")
    if os.path.isdir(home_commands_dir) and home_commands_dir != project_commands_dir:
        count += registry.scan(home_commands_dir)

    logger.info(f"Discovery: 共发现 {count} 个 Commands")
    return count


def discover_all(
    project_dir: Optional[str] = None,
    home_dir: Optional[str] = None,
) -> Tuple[int, int]:
    """发现并注册所有 Agents 和 Commands

    Args:
        project_dir: 项目根目录（可选）
        home_dir: 用户主目录（可选）

    Returns:
        (agents_count, commands_count): 加载的数量
    """
    agents_count = discover_agents(project_dir, home_dir)
    commands_count = discover_commands(project_dir, home_dir)
    return agents_count, commands_count
