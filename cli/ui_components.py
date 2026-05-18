"""终端UI组件模块 — 基于 Rich 的现代终端组件

所有组件使用 Rich 的原生实现，支持自动主题、自适应宽度、Unicode。
"""

import time as _time
from typing import List, Dict, Any, Optional, Union, Callable
from enum import Enum

from rich.console import Console, Group as RichGroup
from rich.panel import Panel as RichPanel
from rich.table import Table as RichTable
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn,
    TimeElapsedColumn, TimeRemainingColumn, TaskID,
)
from rich.tree import Tree as RichTree
from rich.text import Text as RichText
from rich.columns import Columns as RichColumns
from rich.layout import Layout as RichLayout
from rich.live import Live as RichLive
from rich.markdown import Markdown as RichMarkdown
from rich.syntax import Syntax as RichSyntax
from rich.box import Box, ROUNDED, MINIMAL, HEAVY_HEAD

from cli.colors import _console


class SpinnerType(Enum):
    LINE = "line"
    DOT = "dot"
    BAR = "bar"
    PULSE = "pulse"


class ProgressBar:
    """进度条组件 — 基于 Rich Progress"""
    def __init__(self, total: int = 100, width: int = 40, show_percent: bool = True):
        self.total = total
        self._progress = Progress(
            BarColumn(bar_width=width),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        )
        self._task: Optional[TaskID] = None
        self._started = False

    def start(self):
        if not self._started:
            self._task = self._progress.add_task("", total=self.total)
            self._progress.start()
            self._started = True

    def update(self, current: int):
        if not self._started:
            self.start()
        self._progress.update(self._task, completed=min(current, self.total))

    def complete(self):
        if self._started:
            self.update(self.total)
            self._progress.stop()
            self._started = False


class Table:
    """表格组件 — Rich Table 包装"""
    def __init__(self, headers: list, title: str = "", box: Box = HEAVY_HEAD):
        self._table = rich.table.Table(
            *[str(h) for h in headers],
            title=title,
            title_style="bold",
            header_style="bold blue",
            box=box,
        )

    def add_row(self, *cells):
        self._table.add_row(*[str(c) for c in cells])

    def render(self):
        _console.print(self._table)


class Card:
    """卡片组件 — Rich Panel 包装"""
    def __init__(self, title: str = "", content: str = "", border: str = "blue"):
        self._panel = RichPanel(
            content.strip(),
            title=title if title else None,
            border_style=border,
            padding=(0, 2),
        )

    def render(self):
        _console.print(self._panel)


class Spinner:
    """加载动画 — Rich SpinnerColumn"""
    def __init__(self, text: str = "加载中..."):
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        )
        self._task = self._progress.add_task(description=text, total=None)

    def start(self):
        self._progress.start()

    def stop(self):
        self._progress.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


class Tree:
    """树形结构 — Rich Tree"""
    def __init__(self, label: str):
        self._tree = rich.tree.Tree(f"[bold]{label}[/bold]")

    def add(self, label: str, children: list = None):
        if children:
            branch = self._tree.add(label)
            for c in children:
                branch.add(c)
        else:
            self._tree.add(label)

    def render(self):
        _console.print(self._tree)


class StatusBar:
    """状态栏 — Layout + Panel"""
    def __init__(self):
        self._layout = Layout()
        self._layout.split_column(
            Layout(name="main"),
            Layout(name="status", size=1),
        )

    def update(self, text: str):
        self._layout["status"].update(
            RichPanel(text, style="dim", border_style="grey58")
        )


class Menu:
    """简单的终端菜单组件"""

    def __init__(self, title: str = "", items: List[str] = None):
        self.title = title
        self.items = items or []

    def show(self) -> None:
        if self.title:
            _console.print(f"\n[bold]{self.title}[/bold]")
        for i, item in enumerate(self.items, 1):
            _console.print(f"  {i}. {item}")

    def get_choice(self) -> Optional[int]:
        try:
            choice = _console.input("\n请选择: ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(self.items):
                    return idx
        except (EOFError, KeyboardInterrupt):
            pass
        return None


class ClaudeCodeDialog:
    """Claude Code 风格对话面板（左右分栏）"""
    def __init__(self, width: int = None):
        pass

    @staticmethod
    def render_user(message: str) -> RichPanel:
        return RichPanel(
            Markdown(message or "(empty)"),
            title="[bold blue]You[/bold blue]",
            border_style="blue",
            padding=(0, 2),
        )

    @staticmethod
    def render_assistant(message: str) -> RichPanel:
        return RichPanel(
            Markdown(message or "(empty)"),
            title="[bold green]Agent[/bold green]",
            border_style="green",
            padding=(0, 2),
        )

    @staticmethod
    def render_system(message: str) -> RichPanel:
        return RichPanel(
            Markdown(message or "(empty)"),
            title="[bold yellow]System[/bold yellow]",
            border_style="yellow",
            padding=(0, 2),
        )


class SandboxPanel:
    """沙盒执行日志面板"""
    @staticmethod
    def render(code: str, output: str, status: str = "success") -> RichPanel:
        border = "green" if status == "success" else "red"
        content = f"[bold]Code:[/bold]\n{code}\n\n[bold]Output:[/bold]\n{output}"
        return RichPanel(
            content,
            title=f"[bold]{'✅' if status == 'success' else '❌'} Sandbox[/bold]",
            border_style=border,
            padding=(0, 2),
        )


class ProgressHeader:
    """进度/状态头部 — Rich 进度实时刷新"""
    def __init__(self, title: str = ""):
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        )
        self._task = self._progress.add_task(title, total=100)

    def update(self, description: str, progress: float = None):
        self._progress.update(self._task, description=description)
        if progress is not None:
            self._progress.update(self._task, completed=progress)

    def __enter__(self):
        self._progress.start()
        return self

    def __exit__(self, *args):
        self._progress.stop()


# 导入 rich 原生模块用于内部引用
import rich.table as _rt
import rich.tree as _rtree
