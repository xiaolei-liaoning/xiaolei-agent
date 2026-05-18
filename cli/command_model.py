"""命令模型 — 统一命令类型系统

每种命令都是 Command 实例，通过 CommandRegistry 统一查询和执行。
类比 claude_code_src 的 3 种命令类型（prompt / local / local-jsx）。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, List


class CommandType(Enum):
    """命令类型"""
    PROMPT = "prompt"   # 展开为提示文本，给 LLM 消费
    LOCAL = "local"     # 本地函数执行，返回文本
    UI = "ui"           # 终端渲染（类比 claude_code_src 的 local-jsx）


class CommandSource(Enum):
    """命令来源"""
    BUILTIN = "builtin"       # cli/commands/*.py
    FILESYSTEM = "filesystem" # cli/commands/*.md
    SKILL = "skill"           # skills/*/SKILL.md
    PLUGIN = "plugin"         # plugin/*/commands/*.md
    MCP = "mcp"               # MCP 工具自动注册


@dataclass
class Command:
    """统一命令定义

    prompt 类型: 展开为提示文本给 LLM
    local 类型:  执行 handler 函数
    ui 类型:     渲染终端组件
    """
    # ── 核心字段 ──
    name: str
    description: str
    command_type: CommandType = CommandType.PROMPT
    source: CommandSource = CommandSource.BUILTIN

    # ── 可选字段 ──
    aliases: List[str] = field(default_factory=list)
    argument_hint: str = ""
    allowed_tools: List[str] = field(default_factory=list)
    hidden: bool = False
    version: str = ""

    # ── PROMPT 类型字段 ──
    # prompt_template 包含命令展开后的提示文本，支持 $ARGUMENTS 替换
    prompt_template: str = ""

    # ── LOCAL/UI 类型字段 ──
    handler: Optional[Callable] = None
    handler_args: List[str] = field(default_factory=list)

    # ── 执行上下文 ──
    context: str = "inline"  # inline | fork（类比 claude_code_src）

    def get_slash_name(self) -> str:
        return f"/{self.name}"

    def match(self, input_name: str) -> bool:
        """判断输入是否匹配此命令"""
        clean = input_name.lstrip("/")
        return clean == self.name or clean in self.aliases

    def to_help_line(self) -> str:
        hint = f" {self.argument_hint}" if self.argument_hint else ""
        return f"/{self.name}{hint}  — {self.description}"
