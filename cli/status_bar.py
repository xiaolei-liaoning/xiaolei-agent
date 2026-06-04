"""底部状态栏 — 实时显示系统状态信息

在终端底部常驻显示 MCP 连接数、工具数、会话 ID 等。
基于 Rich Live 实现，不干扰正常输出。
"""

import asyncio
import time
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.layout import Layout

from cli.colors import _console, CLAUDE, SUCCESS, ERROR, SUBTLE, INACTIVE, BOLD


class StatusBar:
    """底部状态栏 — 2Hz 刷新，实时显示系统状态

    用法:
        bar = StatusBar(session_id="abc123")
        await bar.start()
        # ... run CLI loop ...
        await bar.stop()
    """

    def __init__(self, session_id: str = "", console: Optional[Console] = None,
                 debug_mode: bool = False):
        self.session_id = session_id
        self._console = console or _console
        self._live: Optional[Live] = None
        self._running = False
        self._debug = debug_mode
        self._last_refresh = 0.0

        # 缓存的状态数据
        self._tool_total = 0
        self._builtin_count = 0
        self._mcp_connected = 0
        self._mcp_awesome = 0
        self._last_command = ""
        self._mode_text = "Normal"

    def set_debug(self, enabled: bool):
        self._debug = enabled

    def set_mode(self, mode: str):
        self._mode_text = mode

    def set_last_command(self, cmd: str):
        self._last_command = cmd[:40]

    async def refresh_stats(self):
        """异步刷新工具统计数据"""
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
            reg = get_tool_registry()
            summary = reg.get_available_tools_summary()
            self._tool_total = summary.get("total", 0)
            self._builtin_count = summary.get("builtin", 0)
            self._mcp_connected = summary.get("mcp_connected", 0)
            self._mcp_awesome = summary.get("mcp_awesome", 0)
        except Exception:
            pass

    async def start(self):
        """启动状态栏"""
        self._running = True
        await self.refresh_stats()
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=2,
            transient=True,
            vertical_overflow="visible",
        )
        self._live.start()

    async def stop(self):
        """停止并清除状态栏"""
        self._running = False
        if self._live:
            self._live.stop()
            self._live = None

    async def update(self):
        """刷新状态栏显示"""
        if not self._running or not self._live:
            return
        # 限频刷新（最多 2Hz）
        now = time.time()
        if now - self._last_refresh < 0.5:
            return
        self._last_refresh = now
        if self._live:
            self._live.update(self._render())

    def _render(self) -> Panel:
        """渲染状态栏"""
        # 左侧：系统信息
        left_parts = []
        left_parts.append(f"[{CLAUDE}]🦞[/] [{BOLD}]xiaolei[/]")
        left_parts.append(f"[{SUBTLE}]session:[/] [{BOLD}]{self.session_id}[/]")
        left_parts.append(f"[{SUBTLE}]tools:[/] [{BOLD}]{self._tool_total}[/](+{self._mcp_awesome}MCP)")
        left_parts.append(f"[{SUBTLE}]mode:[/] [{BOLD}]{self._mode_text}[/]")

        left = Text.from_markup("  ".join(left_parts))

        # 右侧：MCP 和 debug 状态
        right_parts = []
        if self._mcp_connected > 0:
            right_parts.append(f"[{SUCCESS}]●[/] {self._mcp_connected} MCP")
        if self._debug:
            right_parts.append(f"[{ERROR}][bold]DEBUG[/][/]")

        right = Text.from_markup("  ".join(right_parts))

        # 组合
        content = Text()
        content.append(left)
        content.append(" " * max(2, 60 - len(left.plain)))
        content.append(right)

        return Panel(
            content,
            style=Style(bgcolor="grey11"),
            border_style=SUBTLE,
            height=1,
            padding=(0, 1),
        )
