"""编排进度可视化 — 实时 TUI 面板

使用 Rich Live 实现实时刷新，展示多阶段多 Agent 的执行状态。

设计目标:
  - 纯终端实时显示（Rich Live）
  - 阶段性标题 + Agent 卡片网格布局
  - 支持 Python 编排（ad-hoc/workflow 脚本）和 JS 编排两种模式
  - 最小化重构 — 将 display 包装在现有 orchestration 调用外围即可

用法:
    from cli.orch_progress import OrchestrationProgressDisplay

    display = OrchestrationProgressDisplay()
    display.set_phases(["研究阶段", "汇总阶段"])
    aid = display.add_agent("研究阶段", "搜索技术方案", timeout=120)

    with display:                           # 启动 Live
        display.start_agent(aid)            # ▶️
        # ... 执行 Agent ...
        display.complete_agent(aid, result) # ✅
        # 或 display.fail_agent(aid, err)   # ❌

    # 上下文退出时自动 finish()，输出最终摘要

    集成到现有编排（enhanced_cli.py handle_orchestrate）:
        display = OrchestrationProgressDisplay()
        display.set_phases([...])
        # add_agent 在 agent() 调用前注册
        with display:
            result = await run_workflow_script(fn, ..., _display=display)

    集成到 JS 编排（js_orchestrator.py）:
        display = OrchestrationProgressDisplay()
        # 在 _run_js_once 主循环中解析 phase/log/agent_call 消息来更新 display
        with display:
            while reading stdout:
                if msg.type == "phase": display.set_phases([title])
                if msg.type == "agent_call": display.add_agent(...)
                ...

依赖:
  - rich (Live, Text, Group)
  - cli.colors (CLAUDE, SUCCESS, ERROR, INACTIVE, SUBTLE, BOLD, ...)
"""

import time
from typing import Dict, List, Optional, Any

from rich.console import Group, Console
from rich.live import Live
from rich.text import Text

from cli.colors import (
    CLAUDE,
    TEXT,
    INACTIVE,
    SUBTLE,
    SUCCESS,
    ERROR,
    WARNING,
    PERMISSION,
    BOLD,
    DIM,
    get_console,
)


class OrchestrationProgressDisplay:
    """编排进度可视化 — 实时 TUI 面板

    用 Rich Live 实现终端实时刷新，展示编排阶段、Agent 状态和耗时.

    核心数据模型:
        _phases: List[str] — 有序的阶段名称列表
        _phase_agents: Dict[阶段名, List[agent_id]] — 各阶段的 Agent 归属
        _agents: Dict[agent_id, Dict] — 每个 Agent 的详细状态

    Agent 状态机: pending → running → done | failed
    """

    # ── 状态图标 ──
    STATUS_ICON = {
        "pending": "⏳",  # ⏳
        "running": "▶️",  # ▶️
        "done": "✅",  # ✅
        "failed": "❌",  # ❌
    }

    # ── 状态色 ──
    STATUS_COLOR = {
        "pending": INACTIVE,
        "running": CLAUDE,
        "done": SUCCESS,
        "failed": ERROR,
    }

    def __init__(self, console: Optional[Console] = None):
        self._console: Console = console or get_console()
        self._phases: List[str] = []
        self._agents: Dict[str, Dict] = {}
        self._phase_agents: Dict[str, List[str]] = {}
        self._live: Optional[Live] = None
        self._start_time: float = 0.0
        self._workflow_name: str = ""

    # ══════════════════════════════════════════════════════════════════
    # 生命周期
    # ══════════════════════════════════════════════════════════════════

    def start(self):
        """启动 Live 实时显示"""
        self._start_time = time.time()
        renderable = self._build()
        self._live = Live(
            renderable,
            console=self._console,
            refresh_per_second=4,
            transient=False,  # 退出后保留最终状态
        )
        self._live.start()

    def stop(self):
        """停止 Live 显示"""
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finish()
        return False  # 不吞异常

    # ══════════════════════════════════════════════════════════════════
    # 数据接口
    # ══════════════════════════════════════════════════════════════════

    def set_workflow_name(self, name: str):
        """设置工作流名称（显示在头部）"""
        self._workflow_name = name
        self._refresh()

    def set_phases(self, names: List[str]):
        """定义编排阶段列表

        Args:
            names: 阶段名称列表（顺序即展示顺序）
        """
        self._phases = list(names)
        for name in names:
            if name not in self._phase_agents:
                self._phase_agents[name] = []
        self._refresh()

    def add_agent(self, phase: str, label: str,
                  timeout: int = 120) -> str:
        """注册一个 Agent 到指定阶段

        如果 phase 尚不在阶段列表中，会自动追加。

        Args:
            phase: 所属阶段名
            label: 显示标签（最长 28 字符）
            timeout: 超时秒数

        Returns:
            agent_id: 用于后续 start_agent / complete_agent / fail_agent
        """
        agent_id = f"ag_{len(self._agents) + 1}_{int(time.time() * 1000) % 10000}"
        self._agents[agent_id] = {
            "label": label[:28],
            "phase": phase,
            "timeout": timeout,
            "status": "pending",
            "start_time": None,
            "end_time": None,
            "result": None,
            "error": None,
        }
        if phase not in self._phase_agents:
            self._phase_agents[phase] = []
            if phase not in self._phases:
                self._phases.append(phase)
        self._phase_agents[phase].append(agent_id)
        self._refresh()
        return agent_id

    def start_agent(self, agent_id: str):
        """标记 Agent 为运行中"""
        info = self._agents.get(agent_id)
        if info is None:
            return
        info["status"] = "running"
        info["start_time"] = time.time()
        self._refresh()

    def complete_agent(self, agent_id: str, result: Any = None):
        """标记 Agent 为已完成"""
        info = self._agents.get(agent_id)
        if info is None:
            return
        now = time.time()
        info["status"] = "done"
        info["end_time"] = now
        info["result"] = result
        self._refresh()

    def fail_agent(self, agent_id: str, error: str = ""):
        """标记 Agent 为失败

        Args:
            agent_id: Agent ID
            error: 错误消息（最长 30 字符）
        """
        info = self._agents.get(agent_id)
        if info is None:
            return
        now = time.time()
        info["status"] = "failed"
        info["end_time"] = now
        info["error"] = error[:30]
        self._refresh()

    def render(self):
        """强制刷新显示

        在 Live 活动期间等价于触发一次重绘。
        在没有 Live 时调用无副作用。
        """
        self._refresh()

    def finish(self):
        """停止 Live 并输出最终摘要

        步骤:
          1. 用最新状态更新一次 Live
          2. 停止 Live 显示
          3. 输出最终摘要文本到终端
        """
        if self._live is not None and self._live.is_started:
            self._live.update(self._build())
        self.stop()
        self._print_summary()

    # ══════════════════════════════════════════════════════════════════
    # 内部 helpers
    # ══════════════════════════════════════════════════════════════════

    def _refresh(self):
        """刷新 Live 显示（仅当 active 时有效）"""
        if self._live is not None and self._live.is_started:
            self._live.update(self._build())

    def _elapsed(self, info: Dict) -> float:
        """计算 Agent 已执行/总用时（秒）"""
        if info["status"] == "pending":
            return 0.0
        end = info.get("end_time")
        start = info.get("start_time")
        if end is not None and start is not None:
            return end - start
        if info["status"] == "running" and start is not None:
            return time.time() - start
        return 0.0

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """格式化秒数为人类可读"""
        if seconds < 1.0:
            return f"{seconds * 1000:.0f}ms"
        if seconds < 60.0:
            return f"{seconds:.1f}s"
        return f"{seconds / 60:.1f}m"

    # ══════════════════════════════════════════════════════════════════
    # Renderable 构建
    # ══════════════════════════════════════════════════════════════════

    def _build(self) -> Group:
        """构建当前状态的 Rich renderable

        布局:
          ━━━ 编排进度 (12s) ━━━
            🔍 研究阶段  [2/3]
              ▶️ 搜索方案A  3.2s    ✅ 搜索方案B  2.1s
              ✅ 搜索方案C  4.5s

            📝 汇总阶段  [0/1]
              ⏳ 生成报告  (120s 超时)

            ⏳ 等待  ▶️ 运行中  ✅ 完成  ❌ 失败
        """
        elements = []

        # ── 头部 ──
        total_elapsed = time.time() - self._start_time if self._start_time else 0.0
        header = Text()
        if self._workflow_name:
            header.append(f"  {self._workflow_name}  ", style=BOLD)
        header.append("编排进度", style=BOLD)
        header.append(f"  ({total_elapsed:.0f}s)", style=f"dim {INACTIVE}")
        elements.append(header)

        # ── 各阶段 ──
        for phase_name in self._phases:
            agent_ids = self._phase_agents.get(phase_name, [])
            if not agent_ids:
                continue

            # 阶段统计
            done_n = sum(
                1 for a in agent_ids
                if self._agents[a]["status"] in ("done", "failed")
            )
            total_n = len(agent_ids)

            # 阶段标题
            phase_text = Text()
            phase_text.append(f"  ")
            phase_text.append(f"{phase_name}", style=BOLD)
            phase_text.append(f"  [{done_n}/{total_n}]", style=f"dim {INACTIVE}")
            elements.append(phase_text)

            # Agent 卡片网格（每行最多 2 个）
            agent_infos = [self._agents[aid] for aid in agent_ids]
            row_size = 2
            for row_start in range(0, len(agent_infos), row_size):
                row_agents = agent_infos[row_start:row_start + row_size]
                row = Text("    ")
                for i, info in enumerate(row_agents):
                    if i > 0:
                        row.append("   ")
                    row.append(self._agent_text(info))
                elements.append(row)

            # 阶段间空行
            elements.append(Text())

        # ── 图例行 ──
        legend = Text("    ")
        legend.append("⏳ 等待", style=INACTIVE)
        legend.append("  ")
        legend.append("▶️ 运行中", style=CLAUDE)
        legend.append("  ")
        legend.append("✅ 完成", style=SUCCESS)
        legend.append("  ")
        legend.append("❌ 失败", style=ERROR)
        elements.append(legend)

        return Group(*elements)

    def _agent_text(self, info: Dict) -> Text:
        """构建单个 Agent 的状态文本行

        根据不同的 status 显示不同样式:
          pending: ⏳ label (timeout s)
          running: ▶️ label  elapsed
          done:    ✅ label  elapsed
          failed:  ❌ label  error
        """
        icon = self.STATUS_ICON.get(info["status"], "?")
        color = self.STATUS_COLOR.get(info["status"], TEXT)
        label = info["label"]
        t = Text()

        if info["status"] == "pending":
            t.append(f"{icon} ", style=color)
            t.append(f"{label}", style=color)
            t.append(f"  ({info['timeout']}s)", style=f"dim {SUBTLE}")

        elif info["status"] == "running":
            t.append(f"{icon} ", style=color)
            t.append(f"{label}", style=color)
            t.append(f"  {self._fmt_time(self._elapsed(info))}",
                     style=f"dim {INACTIVE}")

        elif info["status"] == "done":
            t.append(f"{icon} ", style=SUCCESS)
            t.append(f"{label}", style=SUCCESS)
            t.append(f"  {self._fmt_time(self._elapsed(info))}",
                     style=f"dim {SUCCESS}")

        elif info["status"] == "failed":
            t.append(f"{icon} ", style=ERROR)
            t.append(f"{label}", style=ERROR)
            err = info.get("error") or "?"
            t.append(f"  {err}", style=f"dim {ERROR}")

        return t

    # ══════════════════════════════════════════════════════════════════
    # 摘要输出
    # ══════════════════════════════════════════════════════════════════

    def _print_summary(self):
        """输出编排最终摘要（在 Live 停止之后）"""
        total = len(self._agents)
        done = sum(1 for a in self._agents.values() if a["status"] == "done")
        failed = sum(1 for a in self._agents.values() if a["status"] == "failed")
        total_sec = time.time() - self._start_time if self._start_time else 0.0

        self._console.print()
        summary = Text()
        summary.append("  编排完成", style=BOLD)
        summary.append(f"  ·  {total} Agent", style=f"dim {INACTIVE}")
        if done:
            summary.append(f"  ✅ {done}", style=SUCCESS)
        if failed:
            summary.append(f"  ❌ {failed}", style=ERROR)
        summary.append(f"  ·  {total_sec:.1f}s", style=f"dim {INACTIVE}")

        # 每阶段统计
        if self._phases:
            summary.append("  ·  ", style=f"dim {INACTIVE}")
            parts = []
            for p in self._phases:
                aids = self._phase_agents.get(p, [])
                d = sum(1 for a in aids if self._agents[a]["status"] == "done")
                f = sum(1 for a in aids if self._agents[a]["status"] == "failed")
                if f:
                    parts.append(f"{p}({d}/{len(aids)} ❌{f})")
                else:
                    parts.append(f"{p}({d}/{len(aids)})")
            summary.append(" → ".join(parts), style=f"dim {SUBTLE}")

        self._console.print(summary)
        self._console.print()


def create_display_for_workflow(meta: Any) -> OrchestrationProgressDisplay:
    """便利函数：从 WorkflowMeta 创建预配置的 display

    自动设置工作流名称和阶段列表。

    Args:
        meta: WorkflowMeta 对象，需有 name、phases 属性

    Returns:
        OrchestrationProgressDisplay 实例
    """
    display = OrchestrationProgressDisplay()
    if hasattr(meta, "name") and meta.name:
        display.set_workflow_name(meta.name)
    if hasattr(meta, "phases") and meta.phases:
        phase_titles = [
            p.get("title", str(p)) for p in meta.phases
            if isinstance(p, dict)
        ]
        display.set_phases(phase_titles)
    return display
