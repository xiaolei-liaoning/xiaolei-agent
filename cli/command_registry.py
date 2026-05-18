"""命令注册表 — 统一命令发现和查询

所有命令（内置 / 文件系统 / 技能 / 插件 / MCP）统一注册到此。
类比 claude_code_src 的 `commands.ts` + `getCommands()`。
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from .command_model import Command, CommandSource, CommandType

logger = logging.getLogger(__name__)

# 默认命令目录
COMMANDS_DIR = Path(__file__).parent / "commands"


class CommandRegistry:
    """统一命令注册表 — 所有命令的唯一查询点"""

    _commands: Dict[str, Command] = {}
    _loaded: bool = False

    # ── 注册 ────────────────────────────────────────────────────────────

    @classmethod
    def register(cls, cmd: Command):
        """注册一个命令"""
        cls._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            cls._commands[alias] = cmd

    @classmethod
    def register_many(cls, commands: List[Command]):
        for cmd in commands:
            cls.register(cmd)

    # ── Markdown 文件发现 ───────────────────────────────────────────────

    @classmethod
    def register_dir(cls, directory: str) -> int:
        """扫描目录下的 *.md 文件，解析 YAML frontmatter 注册为命令

        格式参考 claude-code-rev:
        ---
        name: run
        description: 执行工作流
        argument-hint: "[prompt]"
        aliases: [execute, workflow]
        ---
        """
        cmd_dir = Path(directory)
        if not cmd_dir.exists():
            return 0

        count = 0
        for f in sorted(cmd_dir.glob("*.md")):
            try:
                content = f.read_text(encoding="utf-8")
                cmd = cls._parse_markdown_command(content, f.stem)
                if cmd:
                    cls.register(cmd)
                    count += 1
            except Exception as e:
                logger.debug(f"命令文件解析失败 {f.name}: {e}")

        if count:
            logger.info(f"命令文件发现: {count} 个来自 {directory}")
        return count

    @classmethod
    def _parse_markdown_command(cls, content: str, default_name: str) -> Optional[Command]:
        """从 Markdown frontmatter 解析命令"""
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter = parts[1].strip()
        body = parts[2].strip()

        # 解析 YAML 风格 frontmatter（简单版，不依赖 PyYAML）
        fields = {}
        for line in frontmatter.split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")

                # 数组解析 [a, b, c]
                if val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1]
                    val = [v.strip().strip('"').strip("'") for v in inner.split(",") if v.strip()]
                fields[key] = val

        name = fields.get("name", default_name)
        description = fields.get("description", "")
        if not name or not description:
            return None

        aliases = fields.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]

        hint = fields.get("argument-hint", "")
        allowed_tools = fields.get("allowed-tools", [])
        if isinstance(allowed_tools, str):
            allowed_tools = [allowed_tools]

        context = fields.get("context", "inline")

        return Command(
            name=name,
            description=description,
            command_type=CommandType.PROMPT,
            source=CommandSource.FILESYSTEM,
            aliases=aliases,
            argument_hint=hint,
            allowed_tools=allowed_tools,
            context=context,
            prompt_template=body,
        )

    # ── 查询 ────────────────────────────────────────────────────────────

    @classmethod
    def get(cls, name: str) -> Optional[Command]:
        """按名称或别名查找命令，支持 / 前缀"""
        clean = name.lstrip("/")
        return cls._commands.get(clean)

    @classmethod
    def search(cls, query: str) -> List[Command]:
        """按关键词搜索命令"""
        q = query.lower()
        results = []
        seen = set()
        for name, cmd in cls._commands.items():
            if cmd.get_slash_name() in seen:
                continue
            if q in name.lower() or q in cmd.description.lower():
                seen.add(cmd.get_slash_name())
                results.append(cmd)
        return results

    @classmethod
    def list(cls, source: Optional[CommandSource] = None) -> List[Command]:
        """列出命令，可选按来源筛选"""
        seen = set()
        results = []
        for cmd in cls._commands.values():
            key = cmd.get_slash_name()
            if key in seen:
                continue
            if source and cmd.source != source:
                continue
            seen.add(key)
            results.append(cmd)
        return results

    @classmethod
    def list_source(cls, source: CommandSource) -> List[Command]:
        return cls.list(source=source)

    @classmethod
    def has(cls, name: str) -> bool:
        return name.lstrip("/") in cls._commands

    @classmethod
    def count(cls) -> int:
        return len(set(c.get_slash_name() for c in cls._commands.values()))

    # ── 初始化 ──────────────────────────────────────────────────────────

    @classmethod
    def init_defaults(cls):
        """默认初始化：加载内置命令目录"""
        if cls._loaded:
            return
        cls.register_dir(str(COMMANDS_DIR))
        cls._loaded = True


# 兼容旧接口
def get_registry() -> CommandRegistry:
    return CommandRegistry


# 解决循环导入：在 cli/__init__.py 中注册所有命令
# 需要在模块顶层执行：
#   CommandRegistry.register_dir(COMMANDS_DIR)
