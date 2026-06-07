"""
Command — Claude Code 风格的命令文件支持

官方 Workflow = .claude/commands/ 下的 .md 文件，
主 Claude 读取 body 指令后，用 Agent() 工具调用子 Agent。

本模块提供：
  - Command dataclass：解析 .md 命令文件
  - CommandRegistry：扫描和索引命令，支持嵌套
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Command:
    """命令定义（Claude Code 风格）

    来自 .claude/commands/ 下的 .md 文件，
    包含 YAML 前置元数据（18 个字段）+ body 指令。
    """

    # ── 基础元数据 ──
    name: str  # 命令名（如 "workflows/best-practice/foo"）
    description: str = ""  # 描述
    filepath: Optional[str] = None  # 源文件路径

    # ── 官方元数据字段（约 18 个） ──
    tools: Optional[List[str]] = None
    disallowed_tools: List[str] = field(default_factory=list)
    model: str = ""
    permission_mode: str = "default"
    max_turns: int = 10
    skills: Optional[List[str]] = None
    mcp_servers: Optional[List[str]] = None
    hooks: Optional[List[str]] = None
    memory: Optional[str] = None
    background: bool = False
    effort: str = "default"
    isolation: Optional[str] = None
    initial_prompt: Optional[str] = None
    color: Optional[str] = None
    context: str = "default"  # 上下文模式：default|fork
    agent: Optional[str] = None  # 关联的 Subagent 类型

    # ── 主体内容 ──
    body: Optional[str] = None  # .md 文件主体（指令）

    @classmethod
    def from_markdown(cls, filepath: str, base_dir: Optional[str] = None) -> "Command":
        """从 .md 文件加载 Command

        Args:
            filepath: .md 文件路径
            base_dir: 基础目录，用于计算相对名（如 ".claude/commands"）

        Returns:
            Command
        """
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析 YAML 前置元数据
        metadata = {}
        body = content

        # 匹配 --- 分隔的 YAML 前置元数据
        yaml_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
        if yaml_match:
            yaml_content = yaml_match.group(1)
            body = yaml_match.group(2)
            try:
                metadata = yaml.safe_load(yaml_content) or {}
            except Exception:
                metadata = {}

        # 字段名映射
        field_mapping = {
            "maxTurns": "max_turns",
            "allowedTools": "tools",
            "disallowedTools": "disallowed_tools",
            "permissionMode": "permission_mode",
            "mcpServers": "mcp_servers",
            "initialPrompt": "initial_prompt",
        }

        # 应用映射
        mapped_metadata = {}
        for key, value in metadata.items():
            new_key = field_mapping.get(key, key)
            mapped_metadata[new_key] = value

        # 计算命令名
        if base_dir:
            rel_path = os.path.relpath(filepath, base_dir)
            name = os.path.splitext(rel_path)[0]
            # 转换路径分隔符为 /
            name = name.replace(os.path.sep, "/")
        else:
            filename = os.path.basename(filepath)
            name = os.path.splitext(filename)[0]

        mapped_metadata["name"] = name
        mapped_metadata["filepath"] = filepath
        mapped_metadata["body"] = body.strip() if body else None

        return cls(**mapped_metadata)

    def to_markdown(self) -> str:
        """导出为 .md 文件内容

        Returns:
            str: Markdown 内容
        """
        # 构建元数据
        metadata = {
            "name": self.name,
            "description": self.description,
        }
        if self.tools:
            metadata["tools"] = self.tools
        if self.disallowed_tools:
            metadata["disallowedTools"] = self.disallowed_tools
        if self.model:
            metadata["model"] = self.model
        if self.permission_mode != "default":
            metadata["permissionMode"] = self.permission_mode
        if self.max_turns != 10:
            metadata["maxTurns"] = self.max_turns
        if self.skills:
            metadata["skills"] = self.skills
        if self.mcp_servers:
            metadata["mcpServers"] = self.mcp_servers
        if self.hooks:
            metadata["hooks"] = self.hooks
        if self.memory:
            metadata["memory"] = self.memory
        if self.background:
            metadata["background"] = self.background
        if self.effort != "default":
            metadata["effort"] = self.effort
        if self.isolation:
            metadata["isolation"] = self.isolation
        if self.initial_prompt:
            metadata["initialPrompt"] = self.initial_prompt
        if self.color:
            metadata["color"] = self.color
        if self.context != "default":
            metadata["context"] = self.context
        if self.agent:
            metadata["agent"] = self.agent

        # 生成 YAML
        yaml_str = yaml.dump(metadata, allow_unicode=True, sort_keys=False)

        # 拼接内容
        result = f"---\n{yaml_str}---\n"
        if self.body:
            result += self.body + "\n"

        return result


class CommandRegistry:
    """命令注册表 — 全局单例"""

    _instance: Optional["CommandRegistry"] = None

    def __new__(cls) -> "CommandRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._commands: Dict[str, Command] = {}
            cls._instance._initialized = False
        return cls._instance

    def _ensure(self) -> None:
        if not self._initialized:
            self._initialized = True

    def register(self, command: Command) -> None:
        """注册命令"""
        self._ensure()
        self._commands[command.name] = command
        logger.info(f"CommandRegistry: 注册命令 '{command.name}'")

    def get(self, name: str) -> Optional[Command]:
        """按名称获取命令，支持模糊匹配"""
        self._ensure()
        if name in self._commands:
            return self._commands[name]
        # 尝试前缀匹配
        for cmd_name in self._commands.keys():
            if cmd_name.startswith(name) or name.startswith(cmd_name):
                return self._commands[cmd_name]
        return None

    def scan(self, dir_path: str) -> int:
        """扫描目录下所有 .md 文件作为命令

        Args:
            dir_path: 目录路径（通常是 .claude/commands）

        Returns:
            int: 扫描到的命令数量
        """
        self._ensure()
        count = 0

        if not os.path.isdir(dir_path):
            logger.warning(f"CommandRegistry: 目录不存在: {dir_path}")
            return 0

        for root, _, files in os.walk(dir_path):
            for filename in files:
                if filename.endswith(".md"):
                    filepath = os.path.join(root, filename)
                    try:
                        command = Command.from_markdown(filepath, base_dir=dir_path)
                        self.register(command)
                        count += 1
                    except Exception as e:
                        logger.warning(f"CommandRegistry: 加载失败 {filepath}: {e}")

        logger.info(f"CommandRegistry: 从 {dir_path} 扫描了 {count} 个命令")
        return count

    def list_commands(self) -> Dict[str, str]:
        """列出所有命令"""
        self._ensure()
        return {k: v.description for k, v in self._commands.items()}

    def __contains__(self, name: str) -> bool:
        self._ensure()
        return name in self._commands


# 全局单例
_command_registry = CommandRegistry()


def get_command_registry() -> CommandRegistry:
    """获取 CommandRegistry 全局单例"""
    return _command_registry
