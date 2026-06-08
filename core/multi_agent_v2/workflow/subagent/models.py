"""
SubagentProfile — 子 Agent 类型定义

每个 SubagentProfile 定义了一种 agentType 的配置：
  - 模型（model）
  - 角色提示（personality + role）
  - 最大 ReAct 轮数（max_rounds）
  - 工具白名单（allowed_tools）
  - Skills, MCP, Hooks, Memory, Isolation 等（官方 16 字段完整支持）

WorkflowRuntime 的 agent() 根据 agentType 查注册表，
将 profile 属性合并到 opts 后委托给 orchestrator.agent()。
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SubagentProfile:
    """子 Agent 类型定义（完整官方 16 字段支持）

    决定 agent() 用什么模型、什么角色、多少轮次去执行。
    为空则继承调用方默认值。
    """

    # ── 基础字段（官方前 5 个） ──
    name: str  # 唯一标识 —— "explorer", "analyst", "coder", "general-purpose"
    description: str = ""  # 用途说明，填 "PROACTIVELY" 可自动调用

    # ── 工具控制（官方） ──
    tools: Optional[List[str]] = None  # 工具白名单（官方字段名）
    disallowed_tools: List[str] = field(default_factory=list)  # 拒绝的工具

    # ── 模型/权限（官方） ──
    model: str = ""  # 模型覆盖，空 = 继承 workflow 默认
    permission_mode: str = "default"  # 权限模式（官方 permissionMode）
    max_turns: int = 10  # ReAct 最大轮次（官方 maxTurns，兼容旧 max_rounds）

    # ── 新增字段：扩展到官方 16 个 ──
    skills: Optional[List[str]] = None  # 预加载 skills
    mcp_servers: Optional[List[str]] = None  # MCP 服务器列表（官方 mcpServers）
    hooks: Optional[List[str]] = None  # Hooks
    memory: Optional[str] = None  # Memory 范围：user|project|local
    background: bool = False  # 后台运行
    effort: str = "default"  # Effort level
    isolation: Optional[str] = None  # 隔离模式：worktree|none
    initial_prompt: Optional[str] = None  # 初始提示（官方 initialPrompt）
    color: Optional[str] = None  # 颜色

    # ── 角色/个性注入（我们的扩展） ──
    personality: str = ""  # 注入 WorkAgent.personality
    role: str = ""  # 注入 WorkAgent.role → system_prompt_for_role()

    # ── 向后兼容（旧字段名） ──
    allowed_tools: Optional[List[str]] = None  # 旧工具白名单（兼容用）
    max_rounds: int = 10  # 旧字段名（兼容用）

    # ── body（.md 文件主体） ──
    body: Optional[str] = None  # .md 文件的主体内容

    def __post_init__(self):
        """初始化时兼容处理"""
        # max_rounds 兼容 max_turns
        if self.max_rounds != 10 and self.max_turns == 10:
            self.max_turns = self.max_rounds
        elif self.max_turns != 10 and self.max_rounds == 10:
            self.max_rounds = self.max_turns
        # allowed_tools 兼容 tools
        if self.allowed_tools is not None and self.tools is None:
            self.tools = self.allowed_tools
        elif self.tools is not None and self.allowed_tools is None:
            self.allowed_tools = self.tools

    def to_opts(self) -> Dict:
        """转为 orchestrator.agent() 的 opts 字典"""
        opts: Dict = {}
        if self.model:
            opts["model"] = self.model
        if self.personality:
            opts["personality"] = self.personality
        if self.role:
            opts["role"] = self.role
        # 使用 max_turns（官方字段），兼容旧代码
        rounds = self.max_turns if self.max_turns != 10 else self.max_rounds
        if rounds:
            opts["max_rounds"] = rounds
        # 工具约束：白名单 + 黑名单
        if self.tools is not None:
            opts["allowed_tools"] = self.tools
        if self.disallowed_tools:
            opts["disallowed_tools"] = self.disallowed_tools
        return opts

    @classmethod
    def from_markdown(cls, filepath: str) -> "SubagentProfile":
        """从 .md 文件（YAML 前置元数据）加载 SubagentProfile

        Args:
            filepath: .md 文件路径

        Returns:
            SubagentProfile
        """
        import yaml

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

        # 字段名映射（官方名 -> 我们的字段名）
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

        # 从文件名推断 name（如果没提供）
        if "name" not in mapped_metadata:
            import os

            filename = os.path.basename(filepath)
            name = os.path.splitext(filename)[0]
            mapped_metadata["name"] = name

        mapped_metadata["body"] = body.strip() if body else None

        return cls(**mapped_metadata)

    def to_markdown(self) -> str:
        """导出为 .md 文件（YAML 前置元数据 + body）

        Returns:
            str: Markdown 内容
        """
        import yaml

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

        # 生成 YAML
        yaml_str = yaml.dump(metadata, allow_unicode=True, sort_keys=False)

        # 拼接内容
        result = f"---\n{yaml_str}---\n"
        if self.body:
            result += self.body + "\n"
        elif self.personality:
            result += self.personality + "\n"

        return result
