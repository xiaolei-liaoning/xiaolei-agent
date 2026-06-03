"""CLI 颜色和样式 — Claude Code 风格配色方案

颜色取自 Claude Code 的 theme.ts 暗色主题。
用 Rich Console 实现，保持兼容函数签名。
"""

import time as _time
import shutil
from typing import Optional

from rich.console import Console
from rich.style import Style
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.syntax import Syntax
from rich.tree import Tree
from rich.layout import Layout
from rich.box import MINIMAL, HEAVY_HEAD
from rich.console import Group

_console = Console()

# ── Claude Code 品牌色（暗色主题 RGB 值） ───────────────────────────────────
CLAUDE = "rgb(215,119,87)"       # 品牌橙 — 主强调色
TEXT = "rgb(255,255,255)"        # 正文白
INACTIVE = "rgb(153,153,153)"    # 禁用灰
SUBTLE = "rgb(80,80,80)"         # 极淡灰
SUCCESS = "rgb(78,186,101)"      # 完成绿
ERROR = "rgb(255,107,128)"       # 错误红
WARNING = "rgb(255,193,7)"       # 警告黄
PERMISSION = "rgb(177,185,249)"  # 权限蓝紫
BASH_BORDER = "rgb(253,93,177)"  # Bash 粉色边框
PLAN_MODE = "rgb(72,150,140)"    # 计划模式青绿
DIFF_ADD = "rgb(34,92,43)"       # 新增绿背景
DIFF_DEL = "rgb(122,41,54)"      # 删除红背景
BOLD = "bold"
DIM = "dim"

# ── 兼容旧接口 ──────────────────────────────────────────────────────────────
class CliColors:
    ENDC = ""
    DARK_GREEN = SUCCESS
    DARK_RED = ERROR
    DARK_ORANGE = WARNING
    STEEL_BLUE = PERMISSION
    DARK_BLUE = "blue"
    DARK_CYAN = "cyan"
    DARK_GRAY = INACTIVE
    TEAL = PLAN_MODE
    BOLD = BOLD
    DIM = DIM
    GRAY = INACTIVE
    CYAN = "cyan"
    PURPLE = "purple"
    MAGENTA = "purple"
    BAR = "─"
    DASH = "╌"
    DOT = "·"
    ARROW = "▸"
    DOUBLE_ARROW = "❯"
    SEPARATOR = "┃"
    BLACK = ""
    WHITE = TEXT
    YELLOW = WARNING
    GREEN = SUCCESS
    RED = ERROR
    BLUE = "blue"
    HIGHLIGHT_BLUE = ""
    HIGHLIGHT_GREEN = ""
    HIGHLIGHT_GRAY = ""
    BRIGHT_BLUE = "blue"
    BRIGHT_CYAN = "cyan"
    BRIGHT_MAGENTA = "purple"


# ── 打印函数（兼容旧签名） ──────────────────────────────────────────────────

def print_color(text: str, color: str = "", end: str = '\n', style: str = "") -> None:
    if style:
        _console.print(text, style=style, end=end)
    elif color:
        _console.print(f"[{color}]{text}[/{color}]", end=end)
    else:
        _console.print(text, end=end)


def print_success(message: str) -> None:
    _console.print(f"  [green]{message}[/green]")


def print_error(message: str) -> None:
    _console.print(f"  [red]{message}[/red]")


def print_warning(message: str) -> None:
    _console.print(f"  [orange3]{message}[/orange3]")


def print_info(message: str) -> None:
    _console.print(f"  [steel_blue]{message}[/steel_blue]")


def print_dim(message: str) -> None:
    _console.print(f"  [dim]{message}[/dim]")


def print_header(title: str) -> None:
    _console.print()
    _console.rule(f"[bold {CLAUDE}]{title}[/bold {CLAUDE}]", style=CLAUDE)


def print_section(title: str) -> None:
    _console.print(f"\n  [bold]{title}[/bold]")


def print_divider(char: str = "─", length: int = None, color: str = None) -> None:
    _console.rule(style=color or SUBTLE)


def print_section_end() -> None:
    _console.print()


def print_chat_bubble(text: str, is_user: bool = False, timestamp: str = "") -> None:
    """聊天气泡 — Claude Code 风格"""
    body = text.strip() or "(empty)"
    sub = f" {timestamp}" if timestamp else None
    if is_user:
        _console.print(Panel(
            Markdown(body), title="[bold]You[/bold]",
            subtitle=sub, border_style="grey58", padding=(0, 2),
        ))
    else:
        _console.print(Panel(
            Markdown(body), title=f"[bold {CLAUDE}]Agent[/bold {CLAUDE}]",
            subtitle=sub, border_style=CLAUDE, padding=(0, 2),
        ))


# ── 增强组件 ────────────────────────────────────────────────────────────────

def print_table(headers: list, rows: list, title: str = "") -> None:
    table = Table(title=title, title_style="bold", header_style="bold",
                  border_style=SUBTLE, box=HEAVY_HEAD)
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    _console.print(table)


def print_markdown(content: str) -> None:
    _console.print(Markdown(content))


def print_code(code: str, language: str = "python") -> None:
    _console.print(Syntax(code, language, theme="monokai"))


def spin_animation(text: str, duration: float = 0.8) -> None:
    from rich.progress import Progress, SpinnerColumn, TextColumn
    with Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as p:
        p.add_task(description=text, total=None)
        _time.sleep(duration)


def typing_effect(text: str, delay: float = 0.02, color: str = None) -> None:
    style = f"[{color}]" if color else ""
    end_style = "[/]" if color else ""
    for char in text:
        print(f"{style}{char}{end_style}", end='', flush=True)
        _time.sleep(delay)
    print()


def get_console() -> Console:
    return _console


# ── ANSI 转义码（用于 input() 等直接终端输出的场景） ───────────────────────
ansi = {
    'green': '\033[38;2;78;186;101m',
    'cyan': '\033[38;2;0;255;255m',
    'gray': '\033[38;2;153;153;153m',
    'red': '\033[38;2;255;107;128m',
    'yellow': '\033[38;2;255;193;7m',
    'white': '\033[38;2;255;255;255m',
    'bold': '\033[1m',
    'end': '\033[0m',
}
