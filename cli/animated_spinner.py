"""动画加载组件 — 现代化终端动画效果

提供:
  - AsyncSpinner: 异步加载动画（支持 Rich Live）
  - StepSpinner: 步骤进度显示 [1/5]
  - PulseLoader: 脉冲加载动画
  - DotsLoader: 点阵加载动画
"""

import asyncio
import time
import functools
from typing import Optional, Callable, Any
from contextlib import asynccontextmanager

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner as RichSpinner
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn,
    TimeElapsedColumn, TimeRemainingColumn, TaskID,
)
from rich.style import Style

from cli.colors import _console

# ── 品牌色 ──
CLAUDE = "rgb(215,119,87)"
SUCCESS = "rgb(78,186,101)"
ERROR = "rgb(255,107,128)"
WARNING = "rgb(255,193,7)"
SUBTLE = "rgb(80,80,80)"
INACTIVE = "rgb(153,153,153)"
BOLD = "bold"
DIM = "dim"

# ── 动画帧 ──
SPINNER_FRAMES = ["◐", "◓", "◑", "◒"]
DOT_FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
PULSE_FRAMES = ["█", "▓", "▒", "░", "▒", "▓"]
ARROW_FRAMES = ["→", "↘", "↓", "↙", "←", "↖", "↑", "↗"]
CLOCK_FRAMES = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]

# ── 单行动画器 ──────────────────────────────────────────────────────────

class AsyncSpinner:
    """异步单行动画加载器

    用法:
        spinner = AsyncSpinner("正在搜索...")
        async with spinner:
            result = await some_async_task()

    或手动:
        spinner = AsyncSpinner("加载中")
        await spinner.start()
        # ... do work ...
        await spinner.stop("完成！", status="success")
    """

    def __init__(self, message: str = "加载中...", frames: list = None,
                 color: str = CLAUDE, console: Console = None):
        self._message = message
        self._frames = frames or SPINNER_FRAMES
        self._color = color
        self._console = console or _console
        self._running = False
        self._task = None

    async def start(self):
        """启动动画"""
        self._running = True
        self._task = asyncio.create_task(self._spin())
        # 给动画一点时间启动
        await asyncio.sleep(0.02)

    async def _spin(self):
        """内部旋转动画"""
        idx = 0
        while self._running:
            frame = self._frames[idx % len(self._frames)]
            text = Text()
            text.append(f"  {frame} ", style=self._color)
            text.append(self._message, style=BOLD)
            self._console.print(text, end="\r")
            idx += 1
            await asyncio.sleep(0.1)
        # 清除此行
        self._console.print(" " * 120, end="\r")

    async def stop(self, final_message: str = None, status: str = "success"):
        """停止动画并显示最终状态"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # 显示最终状态
        if final_message:
            icon = "●" if status == "success" else "●"
            color = SUCCESS if status == "success" else ERROR
            self._console.print(f"  [{color}]{icon}[/{color}] [{BOLD}]{final_message}[/{BOLD}]")
        else:
            self._console.print(" " * 120, end="\r")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()


class RichAsyncSpinner:
    """基于 Rich Live 的异步动画加载器

    支持更复杂的渲染内容。
    用法:
        spinner = RichAsyncSpinner("搜索数据...")
        spinner.start()
        # ... do work ...
        spinner.update("搜索数据中... 找到 5 条")
        spinner.stop("搜索完成！")
    """

    def __init__(self, message: str = "加载中...", spinner_name: str = "dots",
                 color: str = CLAUDE, console: Console = None):
        self._message = message
        self._spinner_name = spinner_name
        self._color = color
        self._console = console or _console
        self._live: Optional[Live] = None
        self._status = "running"

    def start(self):
        """启动动画（同步，阻塞当前线程）"""
        if self._live is not None:
            return
        self._live = Live(
            self._render(self._message),
            console=self._console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()

    def _render(self, message: str, status: str = "running") -> Text:
        """渲染当前动画行"""
        if status == "success":
            icon = "●"
            color = SUCCESS
        elif status == "error":
            icon = "●"
            color = ERROR
        else:
            icon = ""
            color = self._color

        text = Text()
        if status == "running":
            text.append("  ", style=color)
            text.append(RichSpinner(self._spinner_name, style=color).render(0))
            text.append(" ", style=color)
        else:
            text.append(f"  {icon} ", style=color)
        text.append(message, style=BOLD)
        return text

    def update(self, message: str):
        """更新动画文字"""
        self._message = message
        if self._live:
            self._live.update(self._render(message, self._status))

    def stop(self, message: str = None, status: str = "success"):
        """停止动画"""
        self._status = status
        if self._live:
            final_msg = message or self._message
            self._live.update(self._render(final_msg, status))
            self._live.stop()
            self._live = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop(self._message)


# ── 步骤进度显示 ────────────────────────────────────────────────────────

class StepCounter:
    """步骤进度显示器

    显示格式:
      ◐ [1/5] 正在分析用户意图...
      ● [2/5] ✓ 分析完成
      ● [3/5] ✗ 执行失败
    """

    def __init__(self, total_steps: int, title: str = "",
                 console: Console = None, show_spinner: bool = True):
        self.total = total_steps
        self.current = 0
        self.title = title
        self._console = console or _console
        self._show_spinner = show_spinner
        self._live: Optional[Live] = None
        self._tasks: dict = {}  # step_num -> status
        self._task_descriptions: dict = {}  # step_num -> description
        self._elapsed = 0.0
        self._start_time = 0.0

    def start(self):
        """启动进度显示"""
        self._start_time = time.time()
        if self.title:
            self._console.print(f"  [{CLAUDE}]▸[/{CLAUDE}] [{BOLD}]{self.title}[/{BOLD}] [{SUBTLE}]({self.total} 步)[/{SUBTLE}]")
        if self._show_spinner and self.total > 1:
            self._live = Live(
                self._render_overview(),
                console=self._console,
                refresh_per_second=10,
                transient=False,
            )
            self._live.start()

    def _render_overview(self) -> Text:
        """渲染总进度概览"""
        done = sum(1 for s in self._tasks.values() if s in ("success", "error"))
        text = Text()
        text.append(f"  [{CLAUDE}]进度:[/{CLAUDE}] ", style=BOLD)

        # 进度条块
        for i in range(1, self.total + 1):
            status = self._tasks.get(i, "pending")
            if status == "running":
                text.append(RichSpinner("dots", style=CLAUDE).render(0))
            elif status == "success":
                text.append("▰", style=SUCCESS)
            elif status == "error":
                text.append("▰", style=ERROR)
            else:
                text.append("▱", style=SUBTLE)

        elapsed = time.time() - self._start_time
        text.append(f" [{done}/{self.total}] [{SUBTLE}]{elapsed:.1f}s[/{SUBTLE}]")
        return text

    def step_start(self, step_num: int, description: str = ""):
        """标记步骤开始"""
        self.current = step_num
        self._tasks[step_num] = "running"
        self._task_descriptions[step_num] = description

        if self._live:
            self._live.update(self._render_overview())

        # 打印该步骤开始行
        msg = f"  ◐ [{CLAUDE}]{step_num}/{self.total}[/{CLAUDE}] {description}"
        self._console.print(msg)

    def step_done(self, step_num: int, description: str = "",
                  success: bool = True, detail: str = ""):
        """标记步骤完成"""
        self._tasks[step_num] = "success" if success else "error"
        desc = description or self._task_descriptions.get(step_num, "")

        if success:
            icon = f"[{SUCCESS}]● ✓[/{SUCCESS}]"
        else:
            icon = f"[{ERROR}]● ✗[/{ERROR}]"

        msg = f"  {icon} [{SUBTLE}]{step_num}/{self.total}[/{SUBTLE}] {desc}"
        self._console.print(msg)

        if detail:
            self._console.print(f"    [{DIM}]⎿ {detail[:150]}[/{DIM}]")

    def complete(self, success: bool = True, summary: str = ""):
        """完成所有步骤"""
        self._elapsed = time.time() - self._start_time

        if self._live:
            self._live.update(self._render_overview())
            self._live.stop()
            self._live = None

        # 打印完成总结
        total_done = sum(1 for s in self._tasks.values() if s in ("success", "error"))
        color = SUCCESS if (success and total_done == self.total) else ERROR
        icon = "●" if success else "●"
        self._console.print()
        self._console.print(f"  [{color}]{icon} 完成[/{color}] [{SUBTLE}]({total_done}/{self.total} 步, {self._elapsed:.1f}s)[/{SUBTLE}]")
        if summary:
            self._console.print(f"  [{DIM}]{summary}[/{DIM}]")


# ── 工具函数 ────────────────────────────────────────────────────────────

@asynccontextmanager
async def step_spinner(message: str, status: str = "info",
                        color: str = CLAUDE, console: Console = None):
    """步骤动画上下文管理器——用于包裹单个操作

    用法:
        async with step_spinner("正在搜索百度热搜..."):
            result = await search_baidu()
    """
    c = console or _console
    spinner = AsyncSpinner(message, color=color, console=c)
    try:
        await spinner.start()
        yield
        await spinner.stop(f"● {message}", status="success")
    except Exception as e:
        await spinner.stop(f"● {message}", status="error")
        raise


def print_step(step_num: int, total: int, message: str,
               status: str = "running", detail: str = "",
               elapsed: str = "") -> None:
    """打印步骤行（同步版）

    格式: ◐ [1/5] 消息
          ● ✓ [1/5] 消息  (1.2s)
          ● ✗ [1/5] 消息  (0.5s)

    Args:
        step_num: 当前步骤号（从1开始）
        total: 总步骤数
        message: 步骤描述
        status: "running" | "success" | "error"
        detail: 额外详情（缩进显示）
        elapsed: 执行耗时字符串（如 "1.2s"）
    """
    if status == "running":
        icon = f"[{CLAUDE}]◐[/{CLAUDE}]"
        num = f"[{CLAUDE}]{step_num}/{total}[/{CLAUDE}]"
    elif status == "success":
        icon = f"[{SUCCESS}]●[/{SUCCESS}]"
        num = f"[{SUBTLE}]{step_num}/{total}[/{SUBTLE}]"
    else:
        icon = f"[{ERROR}]●[/{ERROR}]"
        num = f"[{SUBTLE}]{step_num}/{total}[/{SUBTLE}]"

    if status == "running":
        msg = f"  {icon} {num} {message}"
    else:
        time_tag = f" [{SUBTLE}]{elapsed}[/{SUBTLE}]" if elapsed else ""
        msg = f"  {icon} {num} {message}{time_tag}"
    _console.print(msg)

    if detail:
        _console.print(f"    [{DIM}]⎿ {detail[:200]}[/{DIM}]")


def print_divider(color: str = SUBTLE):
    """打印分隔线"""
    _console.rule(style=color)


def print_section(title: str, color: str = CLAUDE):
    """打印区域标题"""
    _console.print()
    _console.rule(f"[bold {color}]{title}[/bold {color}]", style=color)


def print_status_line(icon: str, message: str, color: str = CLAUDE,
                      dim_detail: str = ""):
    """打印状态行

    格式: 🦞 消息
    """
    _console.print(f"  [{color}]{icon}[/{color}] {message}")
    if dim_detail:
        _console.print(f"    [{DIM}]{dim_detail}[/{DIM}]")
