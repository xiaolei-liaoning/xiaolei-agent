"""思考引擎 — Claude Code 风格执行显示（增强版）

现代化显示格式:
  ◐ [1/5] 步骤描述              ← 执行中（带动画）
  ● ✓ [1/5] 步骤描述             ← 成功
  ● ✗ [1/5] 步骤描述             ← 失败
    ⎿ 结果文本                   ← 缩进表示结果归属
  ────────────────────────────
  进度: ▰▰▰▱▱▱ [2/5] 3.2s     ← 总进度概览
"""

import asyncio
import time
from typing import List, Dict, Any, Optional
from enum import Enum
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner as RichSpinner
from rich.rule import Rule

from cli.animated_spinner import (
    AsyncSpinner, StepCounter, print_step, print_divider,
    print_section, print_status_line, CLAUDE, SUCCESS, ERROR,
    SUBTLE, INACTIVE, BOLD, DIM, DOT_FRAMES, SPINNER_FRAMES,
)

_console = Console()

# ── 符号 ──
DOT_DONE = "●"
DOT_QUEUED = "○"
DOT_RUNNING = "◐"
DOT_FAILED = "●"
INDENT = "  ⎿  "


class ThinkingEngine:
    """Claude Code 风格的步骤执行显示器（增强版）"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._start_time: float = 0
        self._step_count: int = 0
        self._current_step: int = 0
        self._total_steps: int = 0
        self._step_states: Dict[int, str] = {}  # step_num -> "running"|"success"|"error"
        self._step_labels: Dict[int, str] = {}
        self._step_times: Dict[int, float] = {}  # step_num -> start_time
        self._spinner: Optional[AsyncSpinner] = None
        self._live: Optional[Live] = None
        self._phase_spinner: Optional[RichSpinner] = None

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def is_enabled(self) -> bool:
        return self.enabled

    # ── 增强步骤进度显示 ──────────────────────────────────────────────

    def plan_steps(self, steps: List[Dict[str, str]]):
        """展示步骤计划并准备进度追踪"""
        self._step_count = len(steps)
        self._total_steps = len(steps)
        self._current_step = 0
        self._step_states = {}
        self._step_labels = {}

        if not self.enabled or not steps:
            return

        # 打印步骤概览
        print_section("执行计划", CLAUDE)
        for i, s in enumerate(steps, 1):
            title = s.get("title", f"Step {i}")
            desc = s.get("description", "")
            tag = s.get("tag", "")
            tag_str = f" [{SUBTLE}]({tag})[/{SUBTLE}]" if tag else ""

            if desc and desc != title:
                self._print(f"  [{SUBTLE}]{i}.[/{SUBTLE}] {title}{tag_str}")
                self._print(f"    [{DIM}]→ {desc[:100]}[/{DIM}]")
            else:
                self._print(f"  [{SUBTLE}]{i}.[/{SUBTLE}] {title}{tag_str}")

        self._print()

    def start_step(self, step_num: int, title: str = ""):
        """开始一个步骤 — 显示 [1/5] 格式，记录开始时间"""
        if not self.enabled:
            return
        if self._total_steps == 0:
            self._total_steps = self._step_count or 5

        self._current_step = step_num
        self._step_states[step_num] = "running"
        self._step_labels[step_num] = title or f"Step {step_num}"
        self._step_times[step_num] = time.time()  # ← 记录开始时间

        # 获取步骤标签
        label = self._step_labels[step_num]

        # 显示进度步数
        print_step(step_num, self._total_steps, label, status="running")

    def complete_step(self, step_num: int, success: bool = True,
                      error_message: str = "", detail: str = ""):
        """完成一个步骤 — 显示 ✓ 或 ✗，附带执行时间"""
        if not self.enabled:
            return

        self._step_states[step_num] = "success" if success else "error"
        label = self._step_labels.get(step_num, f"Step {step_num}")

        # 计算执行耗时
        elapsed = ""
        start = self._step_times.get(step_num)
        if start:
            elapsed = f"{time.time() - start:.1f}s"

        print_step(step_num, self._total_steps, label,
                   status="success" if success else "error",
                   detail=detail if not error_message else error_message,
                   elapsed=elapsed)

    def progress_summary(self):
        """显示总进度摘要"""
        if not self.enabled:
            return
        if not self._step_states:
            return

        done = sum(1 for s in self._step_states.values()
                   if s in ("success", "error"))
        failed = sum(1 for s in self._step_states.values()
                     if s == "error")

        elapsed = time.time() - self._start_time

        # 进度条
        bar_parts = []
        for i in range(1, self._total_steps + 1):
            s = self._step_states.get(i, "pending")
            if s == "running":
                bar_parts.append(f"[{CLAUDE}]◐[/{CLAUDE}]")
            elif s == "success":
                bar_parts.append(f"[{SUCCESS}]▰[/{SUCCESS}]")
            elif s == "error":
                bar_parts.append(f"[{ERROR}]▰[/{ERROR}]")
            else:
                bar_parts.append(f"[{SUBTLE}]▱[/{SUBTLE}]")

        bar = "".join(bar_parts)

        if done == self._total_steps and failed == 0:
            status = f"[{SUCCESS}]全部完成 ✓[/{SUCCESS}]"
        elif failed > 0:
            status = f"[{ERROR}]{done - failed}/{self._total_steps} 成功[/{ERROR}]"
        else:
            status = f"[{CLAUDE}]{done}/{self._total_steps}[/{CLAUDE}]"

        self._print(f"  {bar} {status} [{SUBTLE}]{elapsed:.1f}s[/{SUBTLE}]")

    # ── 工具调用行 ────────────────────────────────────────────────────

    def tool_start(self, name: str, args: str = ""):
        """显示一行工具调用开始（带动画提示）
        ◐ ToolName (args)
        """
        if not self.enabled:
            return
        arg_part = f" ({args})" if args else ""
        self._print(f"  {DOT_RUNNING} [{BOLD}]{name}[/{BOLD}]{arg_part}")

    def tool_output(self, text: str, max_lines: int = 3):
        """显示工具输出（缩进）"""
        if not self.enabled or not text:
            return
        lines = text.strip().split("\n")
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... +{len(lines) - max_lines} lines"]
        for line in lines:
            self._print(f"  {INDENT}[{DIM}]{line[:200]}[/{DIM}]")

    def tool_done(self):
        """标记工具调用完成"""
        pass

    def tool_error(self, error: str, max_lines: int = 5):
        """显示工具错误"""
        if not self.enabled:
            return
        lines = error.strip().split("\n")
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... +{len(lines) - max_lines} lines"]
        for line in lines:
            self._print(f"  {INDENT}[red]{line[:200]}[/red]")

    # ── 进度消息 ──────────────────────────────────────────────────────

    def status(self, text: str, dim: bool = False):
        """状态消息"""
        if not self.enabled:
            return
        if dim:
            self._print(f"  [{DIM}]{text}[/{DIM}]")
        else:
            self._print(f"  {text}")

    def thinking(self, text: str = "Thinking..."):
        """思考中状态"""
        if not self.enabled:
            return
        self._print(f"  [{DIM}]{text}[/{DIM}]")

    # ── 分隔 ──────────────────────────────────────────────────────────

    def divider(self):
        """打印分隔线"""
        if self.enabled:
            print_divider()

    # ── 结果展示 ──────────────────────────────────────────────────────

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
        t = Table(header_style=BOLD, border_style=SUBTLE)
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
            content[:500] if content else f"[{DIM}]{path}[/{DIM}]",
            title=f"[{BOLD}]{path}[/{BOLD}]",
            border_style=CLAUDE, padding=(0, 2),
        ))

    # ── 总结 ──────────────────────────────────────────────────────────

    def summary(self, success: bool, duration: float = 0,
                detail: str = ""):
        """任务总结"""
        if not self.enabled:
            return
        if success:
            _console.print(f"\n  [{BOLD} {SUCCESS}]● 完成[/{BOLD} {SUCCESS}]"
                           f"[{DIM}]  ({duration:.1f}s)[/{DIM}]")
        else:
            _console.print(f"\n  [{BOLD} {ERROR}]● 失败[/{BOLD} {ERROR}]"
                           f"[{DIM}]  ({duration:.1f}s)[/{DIM}]")

        if self._total_steps > 0:
            self.progress_summary()

        if detail:
            _console.print(f"  [{DIM}]{detail}[/{DIM}]")

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _print(self, text: str):
        """Rich 打印"""
        _console.print(text)

    # ── 旧接口兼容（增强版） ───────────────────────────────────────────

    def start_task(self, user_request: str, total_steps: int = 0):
        """开始任务 — 增强版，支持预设步骤总数"""
        self._start_time = time.time()
        self._reset_state()
        self._total_steps = total_steps or self._step_count or 0

        if not self.enabled:
            return
        print_divider()
        _console.print(f"  [{BOLD}]Request:[/{BOLD}] {user_request}")

    def _reset_state(self):
        """重置步骤状态"""
        self._step_count = 0
        self._current_step = 0
        self._total_steps = 0
        self._step_states = {}
        self._step_labels = {}
        self._step_times = {}

    def analyze_intent(self, intent: str, confidence: float = 1.0):
        """分析意图（用步骤格式显示）"""
        if not self.enabled:
            return
        # 使用步骤格式显示意图分析
        pass

    def log_step_message(self, message: str, indent: int = 1):
        """记录日志（通过 tool_output）"""
        self.tool_output(message)

    def summarize(self, success: bool, result: Dict[str, Any] = None):
        """快速总结"""
        duration = time.time() - self._start_time
        self.summary(success, duration)

    def add_step_data(self, step_num: int, data_type: str, data: str):
        """添加步骤数据"""
        self.tool_output(f"{data_type}: {data}")

    # ── 异步动画支持 ──────────────────────────────────────────────────

    async def async_start_task(self, user_request: str, total_steps: int = 0):
        """异步版 start_task"""
        self.start_task(user_request, total_steps)

    async def async_spinner_step(self, message: str) -> AsyncSpinner:
        """创建一个异步动画上下文

        用法:
            spinner = await engine.async_spinner_step("正在搜索...")
            # ... await work ...
            await spinner.stop("搜索完成")
        """
        spinner = AsyncSpinner(message, console=_console)
        await spinner.start()
        return spinner

    def show_step_plan(self, steps: List[Dict[str, str]]):
        """展示步骤计划（别名，兼容旧代码）"""
        self.plan_steps(steps)


# ── 全局实例 ────────────────────────────────────────────────────────────
_global = ThinkingEngine()


def get_thinking_engine() -> ThinkingEngine:
    return _global


def think_start(user_request: str, total_steps: int = 0):
    """增强版 — 支持预设步骤总数"""
    _global.start_task(user_request, total_steps)


def think_analyze(intent: str, confidence: float = 1.0):
    _global.analyze_intent(intent, confidence)


def think_plan(steps: List[Dict[str, str]]):
    _global.plan_steps(steps)


def think_step(step_num: int, title: str = ""):
    """增强版 — 支持步骤标题"""
    _global.start_step(step_num, title)


def think_log(message: str, indent: int = 1):
    _global.log_step_message(message, indent)


def think_complete(step_num: int, success: bool = True, error: str = "",
                   detail: str = ""):
    """增强版 — 支持细节参数"""
    _global.complete_step(step_num, success, error, detail)


def think_data(data_type: str, data: str):
    _global.add_step_data(0, data_type, data)


def think_summarize(success: bool, result: Dict[str, Any] = None):
    _global.summarize(success, result)


def set_thinking_enabled(enabled: bool):
    _global.set_enabled(enabled)
