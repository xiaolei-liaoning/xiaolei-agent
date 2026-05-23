"""
沙盒执行查看器 - 类 Trae 的隔离沙盒可视化面板

功能:
  - 记录并展示沙盒中文件编辑、命令执行的结果
  - 实时渲染 diff/文件变更/命令输出
  - 支持在 CLI 右侧面板或 tmux 右侧窗格显示
  - 支持纯终端内嵌面板模式（无 tmux 时）
"""

import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Deque

from cli.colors import CliColors, print_color

logger = logging.getLogger(__name__)

# ── 日志文件路径 ──────────────────────────────────────────────────────────────
SANDBOX_LOG_FILE = Path(__file__).parent.parent / "logs" / "sandbox_viewer.log"


# ── 事件类型 ──────────────────────────────────────────────────────────────────
class SandboxEvent:
    """沙盒事件"""

    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    FILE_DELETE = "file_delete"
    COMMAND_RUN = "command_run"
    COMMAND_OUTPUT = "command_output"
    SYSTEM_INFO = "system_info"
    ERROR = "error"
    STATUS = "status"
    PROGRESS = "progress"


class SandboxEntry:
    """沙盒日志条目"""

    def __init__(self, event_type: str, title: str,
                 detail: str = "", data: Optional[Dict] = None,
                 status: str = "ok"):
        self.event_type = event_type
        self.title = title
        self.detail = detail
        self.data = data or {}
        self.status = status
        self.timestamp = datetime.now()
        self.id = f"evt_{int(self.timestamp.timestamp() * 1000000)}"

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.event_type,
            "title": self.title,
            "detail": self.detail,
            "data": self.data,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SandboxEntry":
        entry = cls(d["type"], d["title"], d.get("detail", ""),
                    d.get("data", {}), d.get("status", "ok"))
        entry.id = d.get("id", entry.id)
        if "timestamp" in d:
            try:
                entry.timestamp = datetime.fromisoformat(d["timestamp"])
            except Exception:
                pass
        return entry


class SandboxViewer:
    """沙盒查看器 - 记录和渲染沙盒执行过程"""

    def __init__(self, max_entries: int = 200):
        self.entries: Deque[SandboxEntry] = deque(maxlen=max_entries)
        self.max_entries = max_entries
        self._file = None

    # ── 记录事件 ──────────────────────────────────────────────────────────

    def record(self, event_type: str, title: str,
               detail: str = "", data: Optional[Dict] = None,
               status: str = "ok") -> SandboxEntry:
        """记录一个沙盒事件"""
        entry = SandboxEntry(event_type, title, detail, data, status)
        self.entries.append(entry)
        self._log_to_file(entry)
        return entry

    def record_file_read(self, path: str, lines: int) -> SandboxEntry:
        return self.record(
            SandboxEvent.FILE_READ,
            f"📖 读取文件",
            f"{path} ({lines} 行)",
            {"path": path, "lines": lines},
        )

    def record_file_write(self, path: str, bytes_: int) -> SandboxEntry:
        return self.record(
            SandboxEvent.FILE_WRITE,
            f"✏️ 写入文件",
            f"{path} ({bytes_} bytes)",
            {"path": path, "bytes": bytes_},
        )

    def record_file_edit(self, path: str, replacements: int) -> SandboxEntry:
        return self.record(
            SandboxEvent.FILE_EDIT,
            f"🔧 编辑文件",
            f"{path} ({replacements} 处替换)",
            {"path": path, "replacements": replacements},
        )

    def record_command(self, command: str, exit_code: int,
                       stdout: str = "", stderr: str = "",
                       elapsed: float = 0.0) -> SandboxEntry:
        status = "ok" if exit_code == 0 else "fail"
        detail = f"exit={exit_code} time={elapsed:.2f}s"
        if stdout:
            detail += f" output={len(stdout)}b"
        return self.record(
            SandboxEvent.COMMAND_RUN,
            f"💻 {command[:60]}",
            detail,
            {"command": command, "exit_code": exit_code,
             "stdout": stdout[-500:], "stderr": stderr[-500:],
             "elapsed": round(elapsed, 3)},
            status=status,
        )

    def record_macos(self, action: str, result: Dict) -> SandboxEntry:
        status = "ok" if result.get("status") in ("success", "launched", "captured", "copied") else "fail"
        return self.record(
            SandboxEvent.COMMAND_RUN,
            f"🍎 {action}",
            json.dumps(result, ensure_ascii=False)[:120],
            {"action": action, "result": result},
            status=status,
        )

    def record_error(self, message: str) -> SandboxEntry:
        return self.record(
            SandboxEvent.ERROR, "❌ 错误", message, status="fail"
        )

    def record_progress(self, label: str, current: int, total: int) -> SandboxEntry:
        return self.record(
            SandboxEvent.PROGRESS, label, f"{current}/{total}",
            {"current": current, "total": total},
        )

    # ── 持久化 ──────────────────────────────────────────────────────────

    def _get_log_file(self):
        SANDBOX_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        return SANDBOX_LOG_FILE

    def _log_to_file(self, entry: SandboxEntry):
        """追加日志条目到文件（供 tail -f 使用）"""
        try:
            with open(self._get_log_file(), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def clear_log_file(self):
        """清空日志文件"""
        try:
            with open(self._get_log_file(), "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass

    def load_from_file(self) -> List[SandboxEntry]:
        """从文件加载历史记录"""
        entries = []
        try:
            with open(self._get_log_file(), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(SandboxEntry.from_dict(json.loads(line)))
                        except json.JSONDecodeError:
                            pass
        except FileNotFoundError:
            pass
        return entries[-self.max_entries:]

    # ── 渲染 ──────────────────────────────────────────────────────────────

    def render_compact(self, max_items: int = 15) -> str:
        """渲染紧凑摘要（用于右侧面板/状态栏）"""
        lines = []
        entries = list(self.entries)[-max_items:]
        if not entries:
            return "  沙盒空闲"

        for entry in entries:
            icon = self._status_icon(entry)
            lines.append(f"  {icon} {entry.title}")
            if entry.detail and len(entry.detail) < 120:
                lines.append(f"    {CliColors.GRAY}{entry.detail}{CliColors.ENDC}")

        return "\n".join(lines[-max_items * 2:])

    def render_panel(self, width: int = 60, max_items: int = 20) -> str:
        """渲染完整面板（用于终端内嵌显示）"""
        from cli.ui_components import Panel

        panel = Panel("🛡️ 沙盒执行日志", width)
        entries = list(self.entries)[-max_items:]

        if not entries:
            panel.add_line("  (暂无沙盒活动)", CliColors.GRAY)
        else:
            for entry in reversed(entries):
                icon = self._status_icon(entry)
                time_str = entry.timestamp.strftime("%H:%M:%S")
                title = f" [{time_str}] {icon} {entry.title}"
                panel.add_line(title[:width - 4], CliColors.WHITE)

                if entry.status == "fail" and entry.detail:
                    panel.add_line(f"  {entry.detail[:width-6]}", CliColors.RED)

                last_line = entry.data.get('command', '') if isinstance(entry.data, dict) else ''
                if not last_line:
                    last_line = entry.detail
                if last_line:
                    panel.add_line(f"  {CliColors.GRAY}{str(last_line)[:width-8]}{CliColors.ENDC}", CliColors.GRAY)

        return panel

    def render_inline(self, max_items: int = 5) -> None:
        """在终端中内联渲染最近事件"""
        entries = list(self.entries)[-max_items:]
        if not entries:
            return

        print_color("── 沙盒活动 ──────────────────────────────", CliColors.BRIGHT_BLUE)
        for entry in entries:
            icon = self._status_icon(entry)
            print_color(f"  {icon} {entry.title}", CliColors.WHITE)
            if entry.detail:
                print_color(f"    {entry.detail[:80]}", CliColors.GRAY)
            if entry.status == "fail":
                print_color(f"    ⚠️ 失败", CliColors.RED)
        print()

    @staticmethod
    def _status_icon(entry: SandboxEntry) -> str:
        if entry.status == "fail":
            return "❌"
        if entry.event_type == SandboxEvent.FILE_EDIT:
            return "🔧"
        if entry.event_type == SandboxEvent.FILE_WRITE:
            return "✏️"
        if entry.event_type == SandboxEvent.FILE_READ:
            return "📖"
        if entry.event_type == SandboxEvent.COMMAND_RUN:
            return "💻"
        if entry.event_type == SandboxEvent.PROGRESS:
            return "⏳"
        if entry.event_type == SandboxEvent.ERROR:
            return "⚠️"
        if entry.event_type == SandboxEvent.STATUS:
            return "ℹ️"
        return "•"


# ── 全局单例 ──────────────────────────────────────────────────────────────────
_sandbox_viewer: Optional[SandboxViewer] = None


def get_viewer() -> SandboxViewer:
    global _sandbox_viewer
    if _sandbox_viewer is None:
        _sandbox_viewer = SandboxViewer()
    return _sandbox_viewer


def record_event(event_type: str, title: str, **kwargs) -> SandboxEntry:
    return get_viewer().record(event_type, title, **kwargs)
