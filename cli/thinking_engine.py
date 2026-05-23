"""思考引擎 — Claude Code 风格执行显示

显示格式：
  ● ToolName (args)     ← 正在执行，闪烁状态点
  ● ToolName (args)     ← 已完成，黑色实心点
  ⎿  结果文本            ← 缩进表示结果归属
"""

import time
from typing import List, Dict, Any, Optional
from enum import Enum
from rich.console import Console
from rich.text import Text
from rich.panel import Panel

_console = Console()

# ── 颜色常量（Claude Code 品牌色） ──────────────────────────────────────────
CLAUDE = "rgb(215,119,87)"
SUCCESS = "rgb(78,186,101)"
ERROR = "rgb(255,107,128)"
INACTIVE = "rgb(153,153,153)"
SUBTLE = "rgb(80,80,80)"
BOLD = "bold"
DIM = "dim"

# ── 符号 ────────────────────────────────────────────────────────────────────
DOT_DONE = "●"          # 已完成
DOT_QUEUED = "○"        # 排队中
DOT_RUNNING = "◐"       # 执行中
DOT_FAILED = "●"        # 失败（红色）
INDENT = "  ⎿  "        # 结果缩进前缀


class ThinkingEngine:
    """Claude Code 风格的步骤执行显示器"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._start_time: float = 0
        self._step_count: int = 0

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def is_enabled(self) -> bool:
        return self.enabled

    # ── 工具调用行 ────────────────────────────────────────────────────────

    def tool_start(self, name: str, args: str = ""):
        """显示一行工具调用开始

        ● ToolName (args)
        """
        if not self.enabled:
            return
        arg_part = f" ({args})" if args else ""
        _console.print(f"  {DOT_RUNNING} [bold]{name}[/bold]{arg_part}")

    def tool_output(self, text: str, max_lines: int = 3):
        """显示工具输出（缩进）

        ⎿  output line 1
        ⎿  output line 2
        """
        if not self.enabled or not text:
            return
        lines = text.strip().split("\n")
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... +{len(lines) - max_lines} lines"]
        for line in lines:
            _console.print(f"  {INDENT}[dim]{line[:200]}[/dim]")

    def tool_done(self):
        """标记工具调用完成"""
        # 重新打印上一行为●（已完成）
        # 由于 terminal 不可回溯，下次 tool_start 会覆盖
        pass

    def tool_error(self, error: str, max_lines: int = 5):
        """显示工具错误"""
        if not self.enabled:
            return
        lines = error.strip().split("\n")
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... +{len(lines) - max_lines} lines"]
        for line in lines:
            _console.print(f"  {INDENT}[red]{line[:200]}[/red]")

    # ── 进度消息 ──────────────────────────────────────────────────────────

    def status(self, text: str, dim: bool = False):
        """状态消息"""
        if not self.enabled:
            return
        if dim:
            _console.print(f"  [{DIM}]{text}[/{DIM}]")
        else:
            _console.print(f"  {text}")

    def thinking(self, text: str = "Thinking..."):
        """思考中状态（短暂显示）"""
        if not self.enabled:
            return
        _console.print(f"  [dim]{text}[/dim]")

    # ── 分隔 ──────────────────────────────────────────────────────────────

    def divider(self):
        if self.enabled:
            _console.rule(style=SUBTLE)

    # ── 结果展示 ──────────────────────────────────────────────────────────

    def result_text(self, text: str):
        """展示文本结果（Markdown 渲染）"""
        if not self.enabled or not text:
            return
        from rich.markdown import Markdown
        _console.print(Markdown(text[:2000]))

    def result_table(self, headers: list, rows: list):
        """展示表格结果"""
        if not self.enabled:
            return
        from rich.table import Table
        t = Table(header_style="bold", border_style=SUBTLE)
        for h in headers:
            t.add_column(h)
        for row in rows:
            t.add_row(*[str(c) for c in row])
        _console.print(t)

    def result_file(self, path: str, content: str = ""):
        """展示文件结果"""
        if not self.enabled:
            return
        _console.print(Panel(
            content[:500] if content else f"[dim]{path}[/dim]",
            title=f"[bold]{path}[/bold]",
            border_style=CLAUDE, padding=(0, 2),
        ))

    # ── 总结 ──────────────────────────────────────────────────────────────

    def summary(self, success: bool, duration: float = 0,
                detail: str = ""):
        """任务总结"""
        if not self.enabled:
            return
        if success:
            _console.print(f"\n  [bold {SUCCESS}]● 完成[/bold {SUCCESS}]"
                           f"[dim]  ({duration:.1f}s)[/dim]")
        else:
            _console.print(f"\n  [bold {ERROR}]● 失败[/bold {ERROR}]"
                           f"[dim]  ({duration:.1f}s)[/dim]")
        if detail:
            _console.print(f"  [dim]{detail}[/dim]")

    # ── 旧接口兼容 ───────────────────────────────────────────────────────

    def start_task(self, user_request: str):
        self._start_time = time.time()
        if not self.enabled:
            return
        _console.rule(style=SUBTLE)
        _console.print(f"  [bold]Request:[/bold] {user_request}")

    def analyze_intent(self, intent: str, confidence: float = 1.0):
        pass  # Claude Code 不显示意图分析

    def plan_steps(self, steps: List[Dict[str, str]]):
        self._step_count = len(steps)
        if not self.enabled or not steps:
            return
        for i, s in enumerate(steps, 1):
            title = s.get("title", f"Step {i}")
            desc = s.get("description", "")
            d = f" — {desc}" if desc else ""
            _console.print(f"  [dim]{i}.[/dim] {title}{d}")

    def start_step(self, step_num: int):
        pass  # 用 tool_start 替代

    def log_step_message(self, message: str, indent: int = 1):
        self.tool_output(message)

    def complete_step(self, step_num: int, success: bool = True,
                      error_message: str = ""):
        if success:
            _console.print(f"  {DOT_DONE} [dim]Step {step_num} done[/dim]")
        else:
            _console.print(f"  {DOT_DONE} [red]Step {step_num} failed: {error_message}[/red]")

    def summarize(self, success: bool, result: Dict[str, Any] = None):
        duration = time.time() - self._start_time
        self.summary(success, duration)

    def add_step_data(self, step_num: int, data_type: str, data: str):
        self.tool_output(f"{data_type}: {data}")


# ── 全局实例 ────────────────────────────────────────────────────────────────
_global = ThinkingEngine()


def get_thinking_engine() -> ThinkingEngine:
    return _global


def think_start(user_request: str):
    _global.start_task(user_request)


def think_analyze(intent: str, confidence: float = 1.0):
    _global.analyze_intent(intent, confidence)


def think_plan(steps: List[Dict[str, str]]):
    _global.plan_steps(steps)


def think_step(step_num: int):
    _global.start_step(step_num)


def think_log(message: str, indent: int = 1):
    _global.log_step_message(message, indent)


def think_complete(step_num: int, success: bool = True, error: str = ""):
    _global.complete_step(step_num, success, error)


def think_data(data_type: str, data: str):
    _global.add_step_data(0, data_type, data)


def think_summarize(success: bool, result: Dict[str, Any] = None):
    _global.summarize(success, result)


def set_thinking_enabled(enabled: bool):
    _global.set_enabled(enabled)
