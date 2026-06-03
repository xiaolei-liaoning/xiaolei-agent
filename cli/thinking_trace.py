"""
ThinkingTrace — 实时思考轨迹显示器

将 Agent 执行过程中的思考、工具调用、反思、迭代事件
实时渲染到终端，让用户看到完整的思考链条。

用法:
    trace = ThinkingTrace()
    trace.on_thinking("分析任务", "搜索最新AI论文...")
    trace.on_tool_call("web_search", {"query": "..."})
    trace.on_tool_result("找到 5 篇相关论文")
    trace.on_done(True, 3.2)
"""

import time
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

_console = Console()

# ── 颜色 ──
CLAUDE = "rgb(215,119,87)"
SUCCESS = "rgb(78,186,101)"
ERROR = "rgb(255,107,128)"
WARNING = "rgb(255,193,7)"
SUBTLE = "rgb(80,80,80)"
DIM_STYLE = "dim"
BOLD = "bold"

# ── 符号 ──
TOOL_RUNNING = "◐"
TOOL_DONE = "●"
TOOL_FAILED = "●"
INDENT = "  ⎿  "


class ThinkingTrace:
    """实时思考轨迹显示器"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._start_time: float = 0.0
        self._thinking_depth: int = 0  # 嵌套思考层级
        self._phase_stack: List[str] = []  # 当前阶段栈
        self._iteration: int = 0
        self._plan: List[str] = []  # 当前计划步骤

    # ── 入口/出口 ──────────────────────────────────────────────────

    def start(self, task_desc: str):
        """开始处理一个任务"""
        if not self.enabled:
            return
        self._start_time = time.time()
        self._iteration = 0
        self._plan = []
        _console.rule(style=SUBTLE)
        _console.print(f"  [bold]Request:[/bold] {task_desc}")

    def done(self, success: bool, elapsed: float = 0, detail: str = ""):
        """任务完成总结"""
        if not self.enabled:
            return
        if elapsed == 0:
            elapsed = time.time() - self._start_time
        icon = "✓" if success else "✗"
        color = SUCCESS if success else ERROR
        _console.print()
        _console.print(f"  [bold {color}]{icon} 完成[/bold {color}]"
                       f"[dim]  ({elapsed:.1f}s)[/dim]")
        if detail:
            _console.print(f"  [dim]{detail}[/dim]")

    # ── 思考过程 ────────────────────────────────────────────────────

    def on_thinking(self, phase: str, detail: str = ""):
        """显示 LLM 思考的某个阶段"""
        if not self.enabled:
            return
        self._phase_stack.append(phase)
        indent = "  " * self._thinking_depth
        arrow = f"[{CLAUDE}]┌─[/{CLAUDE}]" if self._thinking_depth == 0 else f"[{CLAUDE}]├─[/{CLAUDE}]"
        prefix = f"  {arrow} [bold {CLAUDE}]{phase}[/bold {CLAUDE}]"
        if detail:
            _console.print(f"{prefix} — {detail}")
        else:
            _console.print(f"{prefix}")

    def on_thinking_result(self, result: str):
        """显示思考得出的结果/计划"""
        if not self.enabled or not result:
            return
        indent = "  " * self._thinking_depth
        # 如果有计划步骤，单独显示
        lines = result.strip().split("\n")
        for line in lines:
            if line.strip():
                _console.print(f"    {INDENT}[dim]{line.strip()[:120]}[/dim]")
        self._thinking_depth += 1

    def on_thinking_end(self):
        """结束一个思考阶段"""
        if not self.enabled:
            return
        self._thinking_depth = max(0, self._thinking_depth - 1)
        if self._phase_stack:
            self._phase_stack.pop()

    # ── 计划 ────────────────────────────────────────────────────────

    def set_plan(self, steps: List[str]):
        """设置/更新执行计划"""
        if not self.enabled or not steps:
            return
        self._plan = steps
        _console.print(f"  [{CLAUDE}]Plan:[/{CLAUDE}]")
        for i, step in enumerate(steps, 1):
            _console.print(f"    [{SUBTLE}]{i}.[/{SUBTLE}] {step}")

    # ── 工具调用 ────────────────────────────────────────────────────

    def on_tool_call(self, tool_name: str, args: Any = None):
        """工具调用开始"""
        if not self.enabled:
            return
        arg_str = self._format_args(args)
        _console.print(f"  {TOOL_RUNNING} [bold]{tool_name}[/bold]{arg_str}")

    def _format_args(self, args: Any) -> str:
        """格式化参数为显示字符串"""
        if args is None:
            return ""
        if isinstance(args, str):
            return f" ({args[:80]})"
        if isinstance(args, dict):
            # 只显示关键字段，截断长值
            parts = []
            for k, v in args.items():
                vs = str(v)
                if len(vs) > 40:
                    vs = vs[:37] + "..."
                parts.append(f"{k}={vs}")
            if parts:
                return f" ({', '.join(parts[:5])})"
            return ""
        return f" ({str(args)[:80]})"

    def on_tool_result(self, text: str, max_lines: int = 3):
        """工具调用结果"""
        if not self.enabled or not text:
            return
        lines = text.strip().split("\n")
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... +{len(lines) - max_lines} lines"]
        for line in lines:
            _console.print(f"  {INDENT}[dim]{line[:200]}[/dim]")

    def on_tool_error(self, error: str, max_lines: int = 3):
        """工具调用错误"""
        if not self.enabled:
            return
        lines = error.strip().split("\n")
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        for line in lines:
            _console.print(f"  {INDENT}[red]{line[:200]}[/red]")

    # ── 反思 ────────────────────────────────────────────────────────

    def on_reflection(self, summary: str, success: bool = True):
        """反思/评估结果"""
        if not self.enabled:
            return
        icon = "✅" if success else "⚠️"
        color = SUCCESS if success else WARNING
        _console.print(f"  [{color}]{icon} 反思:[/{color}] [dim]{summary[:120]}[/dim]")

    # ── 迭代 ────────────────────────────────────────────────────────

    def on_iteration(self, iteration: int, reason: str = ""):
        """开始新一轮迭代"""
        if not self.enabled:
            return
        self._iteration = iteration
        prefix = f"  [{CLAUDE}]── 迭代 #{iteration}[/{CLAUDE}]"
        if reason:
            prefix += f" [{WARNING}]({reason})[/{WARNING}]"
        _console.print(prefix)

    # ── 状态消息 ────────────────────────────────────────────────────

    def status(self, text: str):
        """中间状态消息"""
        if not self.enabled:
            return
        _console.print(f"  [dim]{text}[/dim]")

    def divider(self):
        """分隔线"""
        if self.enabled:
            _console.rule(style=SUBTLE)

    # ── 结构化步骤展示 ────────────────────────────────────────────
    _STEP_ICONS = {
        "pending": "○",
        "running": "◐",
        "success": "✓",
        "failed": "✗",
        "skipped": "→",
        "blocked": "⊘",
    }

    def display_step_plan(self, steps: list):
        """展示完整的步骤计划（含依赖关系）

        Args:
            steps: List[Step] 或 List[Dict] 格式的结构化步骤
        """
        if not self.enabled or not steps:
            return
        _console.print(f"  [{CLAUDE}]Step Plan ({len(steps)} steps):[/{CLAUDE}]")
        for i, step in enumerate(steps, 1):
            # 兼容 Step 对象和 Dict
            if hasattr(step, 'step_id'):
                step_id = step.step_id
                name = getattr(step, 'name', step_id)
                desc = getattr(step, 'description', '')
                s_type = getattr(step, 'type', '')
                deps = getattr(step, 'dependencies', [])
            else:
                step_id = step.get('step_id', f'step_{i}')
                name = step.get('name', step_id)
                desc = step.get('description', '')
                s_type = step.get('type', '')
                deps = step.get('dependencies', [])

            # 类型标签
            type_str = str(s_type).replace("StepType.", "") if not isinstance(s_type, str) else s_type
            type_label = f"[dim]({type_str})[/dim]" if type_str and type_str != "StepType.TOOL_CALL" else ""

            # 依赖标签
            dep_str = f" ← {', '.join(deps)}" if deps else ""

            _console.print(
                f"    {i}. [bold]{name or step_id}[/bold] {type_label}"
                f"[dim]{dep_str}[/dim]"
            )
            if desc and desc != name:
                _console.print(f"       [dim]{desc[:100]}[/dim]")

    @staticmethod
    def _get_field(obj, field: str, default=None):
        """从 Step 对象或 Dict 中安全获取字段"""
        if hasattr(obj, field):
            return getattr(obj, field, default)
        if isinstance(obj, dict):
            return obj.get(field, default)
        return default

    def display_dependency_graph(self, steps: list):
        """以树形展示步骤依赖关系"""
        if not self.enabled or not steps:
            return

        # 找出根步骤（无依赖的）
        roots = []
        for s in steps:
            deps = self._get_field(s, "dependencies", [])
            if not deps:  # 无依赖的步骤是根
                roots.append(s)

        if not roots and steps:
            # 全部有依赖时，第一个作为根
            roots = [steps[0]]

        _console.print(f"  [{CLAUDE}]Dependency Graph:[/{CLAUDE}]")

        def _print_tree(s, depth=0):
            sid = self._get_field(s, "step_id", "")
            name = self._get_field(s, "name", sid)
            indent = "  " * depth
            marker = "└─" if depth > 0 else "●"
            _console.print(f"    {indent} {marker} [bold]{name}[/bold]")
            # 打印子步骤（依赖当前步骤的）
            children = [x for x in steps
                       if sid in self._get_field(x, "dependencies", [])]
            for child in children:
                _print_tree(child, depth + 1)

        for root in roots:
            _print_tree(root)

    def on_step_start(self, step) -> None:
        """步骤开始执行时展示"""
        if not self.enabled:
            return
        step_id = getattr(step, "step_id", "?")
        name = getattr(step, "name", step_id)
        desc = getattr(step, "description", "")
        icon = self._STEP_ICONS.get("running", "◐")
        _console.print(f"  {icon} [{CLAUDE}]Step:[/{CLAUDE}] [bold]{name}[/bold]")
        if desc and desc != name:
            _console.print(f"    [dim]{desc[:100]}[/dim]")

    def on_step_complete(self, step) -> None:
        """步骤完成时展示结果"""
        if not self.enabled:
            return
        name = getattr(step, "name", getattr(step, "step_id", "?"))
        result = getattr(step, "result", None)
        exec_time = getattr(step, "execution_time", 0)
        icon = self._STEP_ICONS.get("success", "✓")

        result_preview = ""
        if result is not None:
            result_str = str(result)
            if len(result_str) > 150:
                result_str = result_str[:147] + "..."
            result_preview = result_str

        time_str = f" ({exec_time:.1f}s)" if exec_time else ""
        _console.print(f"  {icon} [{SUCCESS}]Done:[/{SUCCESS}] {name}[dim]{time_str}[/dim]")
        if result_preview:
            _console.print(f"    {INDENT}[dim]{result_preview}[/dim]")

    def on_step_failed(self, step, error: str = "") -> None:
        """步骤失败时展示错误"""
        if not self.enabled:
            return
        name = getattr(step, "name", getattr(step, "step_id", "?"))
        icon = self._STEP_ICONS.get("failed", "✗")
        _console.print(f"  {icon} [{ERROR}]Failed:[/{ERROR}] {name}")
        if error:
            _console.print(f"    {INDENT}[red]{error[:200]}[/red]")

    # ── 日志兼容 (对接 think_log 等旧接口) ──────────────────────────

    def log(self, text: str, level: str = "info"):
        """兼容旧的 think_log 调用"""
        if not self.enabled:
            return
        if level == "error":
            _console.print(f"  {INDENT}[red]{text[:200]}[/red]")
        elif level == "warning":
            _console.print(f"  {INDENT}[yellow]{text[:200]}[/yellow]")
        else:
            _console.print(f"  {INDENT}[dim]{text[:200]}[/dim]")


# ── 全局单例 ────────────────────────────────────────────────────────────
_global_trace = ThinkingTrace()


def get_trace() -> ThinkingTrace:
    return _global_trace


def set_trace_enabled(enabled: bool):
    _global_trace.enabled = enabled
