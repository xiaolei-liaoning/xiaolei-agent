"""CLI模块 - 小雷版小龙虾AI Agent命令行接口

入口：cli/enhanced_cli.py（EnhancedCLI）
命令处理：cli/handlers/ 下的四个 Handler。
"""

# ═══════════════════════════════════════════════════════════════
# 全局 Fix: 去掉 Rich Panel 的边框字符（╭╰─ 等）
# 在所有 import 之前 patch，保证所有 Panel 默认 MINIMAL 无字符框
# ═══════════════════════════════════════════════════════════════
import rich.panel as _rp
import rich.box as _rb
_orig_panel_init = _rp.Panel.__init__
def _no_box_panel(self, renderable, **kwargs):
    kwargs.setdefault('box', _rb.MINIMAL)
    _orig_panel_init(self, renderable, **kwargs)
_rp.Panel.__init__ = _no_box_panel

from cli.colors import (
    CliColors,
    print_color,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_header,
    print_section,
    print_section_end,
    print_chat_bubble,
)

from cli.base import (
    WorkflowEngineWrapper,
    display_workflow_result,
)

__all__ = [
    # Colors
    "CliColors",
    "print_color",
    "print_success",
    "print_error",
    "print_warning",
    "print_info",
    "print_header",
    "print_section",
    "print_section_end",
    "print_chat_bubble",
    # Base
    "WorkflowEngineWrapper",
    "display_workflow_result",
]


# ── 自动发现命令目录 ──────────────────────────────────────────────────────
from cli.command_registry import CommandRegistry
from pathlib import Path
CommandRegistry.register_dir(str(Path(__file__).parent / "commands"))
