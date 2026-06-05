"""命令自动补全 — 基于 readline 的 Tab 补全

包装 readline，从 CommandParser 动态获取命令列表。
在用户按 Tab 时显示匹配候选项及命令描述。
"""

import os
import readline
from pathlib import Path
from typing import List, Dict, Optional, Callable

from cli.colors import _console, CLAUDE, SUBTLE, INACTIVE, SUCCESS


# ── 历史文件路径 ──────────────────────────────────────────────────────────────
HISTORY_FILE = str(Path.home() / ".xiaolei_history")


class Completer:
    """Readline Tab 补全器

    用法:
        completer = Completer(get_commands_fn, get_help_fn)
        completer.install()
        # ... main loop ...
        completer.save_history()

    get_commands_fn 返回命令列表 (如 ["/help", "/run"])
    get_help_fn 返回 {命令: 描述} 字典
    """

    def __init__(
        self,
        get_commands_fn: Callable[[], List[str]],
        get_help_fn: Callable[[], Dict[str, str]],
    ):
        self._get_commands = get_commands_fn
        self._get_help = get_help_fn
        self._matches: List[str] = []

    # ── 公共 API ──────────────────────────────────────────────────────────

    def install(self):
        """安装到 readline（在主循环启动时调用一次）"""
        readline.set_completer(self._complete)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n;")

        # 加载历史文件
        try:
            readline.read_history_file(HISTORY_FILE)
        except (FileNotFoundError, PermissionError):
            pass

        # 绑定补全显示钩子（Tab 时打印候选项）
        try:
            readline.set_completion_display_matches_hook(self._display_matches)
        except AttributeError:
            # macOS libedit 不支持此钩子，忽略
            pass

    def save_history(self):
        """保存命令历史到文件"""
        try:
            readline.write_history_file(HISTORY_FILE)
        except Exception:
            pass

    def get_suggestions(self, text: str, n: int = 3) -> List[str]:
        """模糊匹配：针对不认识的命令返回最接近的建议"""
        if not text.startswith("/"):
            return []
        from difflib import get_close_matches

        return get_close_matches(text, self._get_commands(), n=n, cutoff=0.3)

    # ── readline 回调 ─────────────────────────────────────────────────────

    def _complete(self, text: str, state: int) -> Optional[str]:
        """readline 补全回调 — 每次按键 Tab 触发"""
        if state == 0:
            commands = self._get_commands()
            self._matches = [cmd for cmd in commands if cmd.startswith(text)]
        if state < len(self._matches):
            return self._matches[state]
        return None

    def _display_matches(self, substitution: str, matches: List[str],
                         longest_match_length: int):
        """补全候选项显示钩子 — 在提示符下方打印匹配项"""
        help_map = self._get_help()
        count = len(matches)
        show = matches[:10]

        lines = []
        for cmd in show:
            desc = help_map.get(cmd, "")
            if desc:
                lines.append(f"  [{CLAUDE}]{cmd:<16}[/] [{INACTIVE}]{desc}[/]")
            else:
                lines.append(f"  [{CLAUDE}]{cmd}[/]")

        if count > 10:
            lines.append(f"  [{SUBTLE}]... 以及 {count - 10} 个更多匹配[/]")

        _console.print("\n".join(lines))
