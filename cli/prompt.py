"""Rich 样式化提示符 — 替代裸 input()

用法:
    from cli.prompt import get_styled_input, get_chat_input
    user_input = get_styled_input(cli_instance)
"""

from typing import TYPE_CHECKING, Optional

from rich.text import Text
from rich.panel import Panel

from cli.colors import _console, CLAUDE, SUCCESS, ERROR, WARNING, SUBTLE, INACTIVE, BOLD

if TYPE_CHECKING:
    from cli.enhanced_cli import EnhancedCLI


def build_context_tags(cli_instance: "EnhancedCLI") -> str:
    """构建提示符前的上下文标签（session / CHAT / DBG / MCP）"""
    tags = []

    # 会话 ID（前 6 位）
    if cli_instance.session_id:
        tags.append(f"[{INACTIVE}]{cli_instance.session_id[:6]}[/{INACTIVE}]")

    # 聊天模式
    if getattr(cli_instance, "chat_mode", False):
        tags.append(f"[{WARNING}]CHAT[/{WARNING}]")

    # 调试模式
    if getattr(cli_instance, "debug_mode", False):
        tags.append(f"[{ERROR}]DBG[/{ERROR}]")

    # MCP 连接
    if getattr(cli_instance, "current_mcp_server", None):
        tags.append(f"[{SUCCESS}]MCP[/{SUCCESS}]")

    if tags:
        return " ".join(tags) + " "
    return ""


def get_styled_input(cli_instance: "EnhancedCLI", prompt_text: str = "❯ xiaolei") -> str:
    """获取用户输入 — Rich 样式化提示符 + 上下文标签

    使用 _console.input() 渲染 Rich 标记，底层仍是 input()，
    所以 readline 的 Tab 补全依然有效。
    """
    prefix = build_context_tags(cli_instance)
    full_prompt = f"{prefix}[bold {CLAUDE}]{prompt_text}[/bold {CLAUDE}]"

    try:
        return _console.input(full_prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def get_chat_input(cli_instance: "EnhancedCLI") -> str:
    """聊天模式输入 — 绿色 'You:' 提示符"""
    prefix = build_context_tags(cli_instance)
    full_prompt = f"{prefix}[bold {SUCCESS}]You:[/bold {SUCCESS}] "
    try:
        return _console.input(full_prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""
