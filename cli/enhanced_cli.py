#!/usr/bin/env python3
"""小雷版小龙虾 AI Agent - 命令行接口 (增强版)

EnhancedCLI 被拆分为 4 个 handler 模块，本文件仅保留:
  - _pre_init_logger() / 模块级初始化
  - EnhancedCLI: 命令路由 + 共享辅助方法
  - main() / parse_args() / is_in_tmux() / setup_dual_terminal()

Handler 模块位于 cli/handlers/:
  - chat_handler.py     — /run /analyze /scrape /automate /wechat /chat /orchestrate /smart /workflows
  - mcp_handler.py      — /mcp 所有子命令
  - task_handler.py     — /game /fun /art /agent /review /config /plugin
  - utility_handler.py  — /help /tools /show /quit /clear /history /debug /think /reset /status /test
  - thinking_decorator.py — @with_thinking() 装饰器
"""

import argparse
import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── 预初始化日志系统（必须在导入其他模块之前） ──
def _pre_init_logger():
    """预初始化日志系统 - 在导入其他模块之前"""
    # ── Python 3.13 asyncio subprocess bugfix ──
    import sys as _sys

    if _sys.version_info >= (3, 13):
        try:
            import asyncio.base_subprocess as _asp

            _orig = _asp.BaseSubprocessTransport._try_finish

            def _patched_try_finish(self):
                try:
                    _orig(self)
                except asyncio.InvalidStateError:
                    pass

            _asp.BaseSubprocessTransport._try_finish = _patched_try_finish
        except Exception:
            pass

    # ── 先过滤已知噪音 ──
    import warnings

    warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
    warnings.filterwarnings("ignore", message="Number of requested results")
    os.environ["CHROMADB_TELEMETRY_DISABLED"] = "1"
    logging.getLogger("jieba").setLevel(logging.ERROR)
    logging.getLogger("chromadb").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("core.search.keyword_extractor").setLevel(logging.ERROR)

    # ── 快速解析命令行参数中的日志相关选项 ──
    log_file = None
    no_console_log = False

    in_tmux = os.environ.get("TMUX") is not None

    for i, arg in enumerate(sys.argv):
        if arg in ("--log-file", "-l") and i + 1 < len(sys.argv):
            log_file = sys.argv[i + 1]
        elif arg == "--no-console-log":
            no_console_log = True
        elif arg in ("--dual-terminal", "-d"):
            script_dir = Path(__file__).parent
            log_file = str(script_dir / "logs" / "agent.log")
            no_console_log = True

    if in_tmux and not log_file:
        script_dir = Path(__file__).parent
        log_file = str(script_dir / "logs" / "agent.log")
        no_console_log = True

    if log_file:
        os.environ["AGENT_LOG_FILE"] = log_file
    if no_console_log:
        os.environ["AGENT_ENABLE_CONSOLE_LOG"] = "false"

    from cli.logging_system import init_logger

    init_logger(log_file=log_file or "", log_to_console=not no_console_log)


_pre_init_logger()

# ── CLI 模块导入 (noqa: E402 — 必须在 _pre_init_logger() 之后) ──
from cli.colors import (  # noqa: E402
    CliColors,
    print_chat_bubble,
    print_color,
    print_error,
    print_success,
    print_warning,
)
from cli.command_parser import (  # noqa: E402
    CommandType,
    ParsedCommand,
    get_command_parser,
)
from cli.logging_system import (  # noqa: E402
    log_error,
    log_info,
    log_success,
    log_warning,
)
from cli.prompt import get_chat_input  # noqa: E402
from cli.thinking_engine import (  # noqa: E402
    get_thinking_engine,
    set_thinking_enabled,
    think_analyze,
    think_complete,
    think_log,
    think_plan,
    think_start,
    think_step,
    think_summarize,
)

# ── Handler 模块 ──
from cli.handlers.chat_handler import ChatHandler  # noqa: E402
from cli.handlers.mcp_handler import McpHandler  # noqa: E402
from cli.handlers.task_handler import TaskHandler  # noqa: E402
from cli.handlers.utility_handler import UtilityHandler  # noqa: E402

# 核心服务（延迟导入）
CLARIFICATION_SERVICE = None
PERMISSION_SERVICE = None
FORKED_AGENT_SERVICE = None


def _import_core_services():
    """延迟导入核心服务"""
    global CLARIFICATION_SERVICE, PERMISSION_SERVICE, FORKED_AGENT_SERVICE

    try:
        from cli.clarification_service import get_clarification_service

        CLARIFICATION_SERVICE = get_clarification_service()
        log_success("✅ 反问服务导入成功")
    except Exception as e:
        log_error(f"❌ 反问服务导入失败: {e}")

    try:
        from cli.permission_service import get_permission_service

        PERMISSION_SERVICE = get_permission_service()
        log_success("✅ 权限服务导入成功")
    except Exception as e:
        log_error(f"❌ 权限服务导入失败: {e}")

    try:
        from cli.forked_agent_service import get_forked_agent_service

        FORKED_AGENT_SERVICE = get_forked_agent_service()
        log_success("✅ Forked Agent服务导入成功")
    except Exception as e:
        log_error(f"❌ Forked Agent服务导入失败: {e}")


class EnhancedCLI:
    """增强版CLI — 命令路由主干，实现委托给 handler 模块"""

    def __init__(self):
        self.command_parser = get_command_parser()
        self.thinking_engine = get_thinking_engine()
        self.running = True
        self.debug_mode = False

        # 会话状态管理
        self.chat_mode = False
        self.chat_history = []
        self.session_id = None
        self.current_mcp_server = None
        self.mcp_session = None

        # 状态栏（延迟到 run() 中初始化）
        self._status_bar = None

        # 折叠输出缓存（用于 /show 命令）
        self._collapsed_outputs = {}

        # MCP 调用历史
        self.mcp_history = []

        # 导入核心服务
        _import_core_services()

        # ── 初始化 Handler 委托 ──
        self.chat_handler = ChatHandler(self)
        self.mcp_handler = McpHandler(self)
        self.task_handler = TaskHandler(self)
        self.utility_handler = UtilityHandler(self)

    def _init_session(self):
        """初始化会话状态"""
        import uuid

        self.session_id = str(uuid.uuid4())[:8]
        self.chat_history = []
        log_info(f"会话已初始化: {self.session_id}")

    # ──────────────────────────────────────────────
    # 命令路由
    # ──────────────────────────────────────────────

    async def handle_command(self, parsed_cmd: ParsedCommand):
        """处理解析后的命令 — 委托给各 handler"""
        cmd_type = parsed_cmd.command_type

        # ── 本地处理的命令 ──
        ## smart_request（fallback）
        if cmd_type not in (
            CommandType.HELP, CommandType.QUIT, CommandType.EXIT,
            CommandType.CLEAR, CommandType.STATUS, CommandType.RUN,
            CommandType.ANALYZE, CommandType.SCRAPE, CommandType.AUTOMATE,
            CommandType.WECHAT, CommandType.CHAT, CommandType.HISTORY,
            CommandType.DEBUG, CommandType.THINK, CommandType.MCP,
            CommandType.GAME, CommandType.FUN, CommandType.ART,
            CommandType.AGENT, CommandType.REVIEW, CommandType.CONFIG,
            CommandType.PLUGIN, CommandType.SMART, CommandType.RESET,
            CommandType.TEST, CommandType.TOOLS, CommandType.SHOW,
            CommandType.ORCHESTRATE, CommandType.WORKFLOWS,
        ):
            await self.chat_handler.handle_smart_request(parsed_cmd.remaining)
            return

        # ── 委托到 handler ──
        handler_map = {
            CommandType.HELP:      lambda: self.utility_handler.handle_help(
                parsed_cmd.remaining[6:].strip() if (parsed_cmd.remaining or "").startswith("search") else ""
            ),
            CommandType.QUIT:      lambda: self.utility_handler.handle_quit(),
            CommandType.EXIT:      lambda: self.utility_handler.handle_quit(),
            CommandType.CLEAR:     lambda: self.utility_handler.handle_clear(),
            CommandType.STATUS:    lambda: self.utility_handler.handle_status(),
            CommandType.DEBUG:     lambda: self.utility_handler.handle_debug(),
            CommandType.THINK:     lambda: self.utility_handler.handle_think(),
            CommandType.RESET:     lambda: self.utility_handler.handle_reset(parsed_cmd),
            CommandType.HISTORY:   lambda: self.utility_handler.handle_history(),
            CommandType.TOOLS:     lambda: self.utility_handler.handle_tools(),
            CommandType.SHOW:      lambda: self.utility_handler.handle_show(parsed_cmd),
            CommandType.TEST:      lambda: self.utility_handler.handle_test(parsed_cmd),

            CommandType.RUN:       lambda: self.chat_handler.handle_run(parsed_cmd),
            CommandType.ANALYZE:   lambda: self.chat_handler.handle_analyze(parsed_cmd),
            CommandType.SCRAPE:    lambda: self.chat_handler.handle_scrape(parsed_cmd),
            CommandType.AUTOMATE:  lambda: self.chat_handler.handle_automate(parsed_cmd),
            CommandType.WECHAT:    lambda: self.chat_handler.handle_wechat(parsed_cmd),
            CommandType.CHAT:      lambda: self.chat_handler.handle_chat(parsed_cmd),
            CommandType.SMART:     lambda: self.chat_handler.handle_smart(parsed_cmd),
            CommandType.ORCHESTRATE: lambda: self.chat_handler.handle_orchestrate(parsed_cmd),
            CommandType.WORKFLOWS: lambda: self.chat_handler.handle_workflows(parsed_cmd),

            CommandType.MCP:       lambda: self.mcp_handler.handle_mcp(parsed_cmd),

            CommandType.GAME:      lambda: self.task_handler.handle_game(parsed_cmd),
            CommandType.FUN:       lambda: self.task_handler.handle_fun(parsed_cmd),
            CommandType.ART:       lambda: self.task_handler.handle_art(parsed_cmd),
            CommandType.AGENT:     lambda: self.task_handler.handle_agent(parsed_cmd),
            CommandType.REVIEW:    lambda: self.task_handler.handle_review(parsed_cmd),
            CommandType.CONFIG:    lambda: self.task_handler.handle_config(parsed_cmd),
            CommandType.PLUGIN:    lambda: self.task_handler.handle_plugin(parsed_cmd),
        }

        handler = handler_map.get(cmd_type)
        if handler:
            await handler() if asyncio.iscoroutinefunction(handler) or True else handler()
        else:
            await self.chat_handler.handle_smart_request(parsed_cmd.remaining)

    # ──────────────────────────────────────────────
    # 欢迎界面
    # ──────────────────────────────────────────────

    def print_welcome(self):
        """打印欢迎界面"""
        print("\033c", end="")
        brand = "rgb(215,119,87)"
        dim = "rgb(80,80,80)"

        from rich.console import Console as RichConsole
        from rich.panel import Panel
        from rich.table import Table

        rc = RichConsole()
        rc.print()

        rc.print(
            Panel(
                "[bold rgb(215,119,87)]🦞  xiaolei AI Agent[/bold rgb(215,119,87)]\n"
                f"[{dim}]session: {self.session_id or 'initializing'}  ·  "
                f"version: 3.4.0[/{dim}]",
                border_style=brand,
                padding=(1, 2),
            )
        )

        tool_total = 0
        mcp_count = 0
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry

            reg = get_tool_registry()
            summary = reg.get_available_tools_summary()
            tool_total = summary.get("total", 0)
            mcp_count = summary.get("mcp_connected", 0)
        except Exception:
            pass

        if tool_total > 0:
            rc.print(
                f"  [{dim}]●[/]  [bold]Tools: {tool_total}[/]"
                f"  [{dim}]·[/]  [bold]MCP: {mcp_count}[/] connected"
                f"  [{dim}]·[/]  [{brand}]/tools[/] for details"
            )
        else:
            rc.print(f"  [{dim}]●[/]  tools initializing…")

        rc.print()

        cmd_table = Table(show_header=False, box=None, padding=(0, 3, 0, 0))
        cmd_table.add_column("Command", style=f"bold {brand}", no_wrap=True)
        cmd_table.add_column("What it does", style="white")
        cmd_table.add_row('/run "task"', "Execute a workflow")
        cmd_table.add_row("/chat", "Conversation mode")
        cmd_table.add_row('/smart "task"', "Multi-agent collaboration")
        cmd_table.add_row("/help", "Full command reference")
        rc.print(cmd_table)

        import random

        tips = [
            "Type /help search <term> to search commands",
            "Natural language requests work without / prefix",
            "Use /mcp agency to connect MCP servers",
            "Type /clear to clean up the terminal",
            "Use /orchestrate to manage multi-agent workflows",
        ]
        rc.print(f"\n  [{dim}]💡 {random.choice(tips)}[/{dim}]")
        rc.print()

    # ──────────────────────────────────────────────
    # 共享辅助方法
    # ──────────────────────────────────────────────

    def _display_collapsible_result(
        self, title: str, content: str, collapsed: bool = True, max_chars: int = 500
    ) -> str:
        """显示可折叠的结果"""
        from rich.panel import Panel

        from cli.colors import INACTIVE, SUBTLE, _console

        result_id = hashlib.md5(title.encode()).hexdigest()[:8]

        if len(content) <= max_chars:
            _console.print(
                Panel(content, title=title, border_style=SUBTLE, padding=(0, 2))
            )
        else:
            preview = content[:max_chars]
            remaining_count = len(content) - max_chars
            _console.print(
                Panel(
                    f"{preview}\n\n[{INACTIVE}]...（剩余 {remaining_count} 字符，/show {result_id} 展开全文）[/{INACTIVE}]",
                    title=f"[+] {title}",
                    border_style=SUBTLE,
                    padding=(0, 2),
                )
            )
            if not hasattr(self, "_collapsed_outputs"):
                self._collapsed_outputs = {}
            self._collapsed_outputs[result_id] = content

        return result_id

    def _categorize_error(self, error_class: str, error_msg: str) -> list:
        """根据错误类型自动生成恢复建议"""
        suggestions = []
        msg_lower = error_msg.lower()

        network_kw = [
            "connection", "timeout", "network", "dns", "refused",
            "unreachable", "socket", "reset",
        ]
        if any(kw in msg_lower for kw in network_kw):
            suggestions.append("Check your network connection and try again")
            suggestions.append("Use /mcp status to verify MCP server connectivity")

        if "ModuleNotFoundError" in error_class or "ImportError" in error_class:
            suggestions.append("Run 'pip install -r requirements.txt' to install dependencies")

        if "KeyError" in error_class or "AttributeError" in error_class:
            suggestions.append("This may be a configuration issue. Try /config show")

        json_kw = ["json.decoder.jsondecodeerror", "parse", "unexpected token"]
        if any(kw in msg_lower for kw in json_kw):
            suggestions.append("Check that the input is valid JSON or the expected format")

        if "PermissionError" in error_class:
            suggestions.append("You may need to grant permission via the permission service")

        if "FileNotFoundError" in error_class:
            suggestions.append("Check that the file path exists and is accessible")

        return suggestions

    def _display_error_panel(
        self,
        error: Exception,
        context: str = "",
        suggestions: Optional[List[str]] = None,
    ) -> None:
        """显示带建议操作的错误面板"""
        from rich.panel import Panel
        from rich.syntax import Syntax

        from cli.colors import ERROR, INACTIVE, SUBTLE, WARNING, _console

        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        error_class = type(error).__name__

        auto_suggestions = self._categorize_error(error_class, str(error))
        all_suggestions = (suggestions or []) + auto_suggestions

        _console.print()
        _console.print(
            Panel(
                f"[bold {ERROR}]⚠️  {error_class}[/bold {ERROR}]  {str(error)[:200]}",
                title=f"❌ {context or 'Error'}",
                border_style=ERROR,
                padding=(0, 2),
            )
        )

        if all_suggestions:
            _console.print(f"  [{WARNING}]→ Suggestions:[/{WARNING}]")
            for s in all_suggestions:
                _console.print(f"    [{INACTIVE}]·[/{INACTIVE}] {s}")

        if len(tb) > 200:
            key = hashlib.md5(tb.encode()).hexdigest()[:8]
            _console.print(
                Panel(
                    Syntax(tb, "python", theme="monokai", line_numbers=True),
                    title=f"[+] 堆栈 (/show {key})",
                    border_style=SUBTLE,
                    padding=(0, 1),
                )
            )
            if not hasattr(self, "_collapsed_outputs"):
                self._collapsed_outputs = {}
            self._collapsed_outputs[key] = tb
        else:
            _console.print(
                Panel(Syntax(tb, "python", theme="monokai"), title="堆栈", border_style=SUBTLE, padding=(0, 1))
            )
        _console.print()

    def _display_workflow_result(self, result: Dict[str, Any]):
        """显示工作流结果"""
        from cli.colors import _console

        if not result.get("success"):
            print_error(result.get("error", "执行失败"))
            return

        greeting_message = result.get("greeting_message")
        if greeting_message:
            print()
            print_color(greeting_message, CliColors.CYAN)
            print()
            return

        print()
        print_color("────────────────────────────────────────────────────────", CliColors.PURPLE)
        print_success("✅ 任务完成！")
        print_color("────────────────────────────────────────────────────────", CliColors.PURPLE)
        print()

        if result.get("workflow_name"):
            print(f"  📋 名称: {result.get('workflow_name')}")
        if result.get("total_time"):
            print(f"  ⏱️  耗时: {result.get('total_time', 0):.2f}秒")

        final_result = result.get("result", "")
        if final_result and len(str(final_result)) > 10:
            answer_text = str(final_result)[:500]
            print("\n  📝 最终回答:")
            print(f"    {answer_text}")

        results = result.get("results", [])
        if results:
            print("\n  📊 步骤详情:")
            for step_result in results:
                status = "✅" if step_result.get("success") else "❌"
                step_num = step_result.get("step", "?")
                step_type = step_result.get("type", "")
                action = step_result.get("action", "")
                print(f"\n    {status} 步骤{step_num}")
                print(f"       类型: {step_type}")
                if action:
                    print(f"       操作: {action}")
                if step_result.get("message"):
                    print(f"       消息: {step_result['message']}")
                if step_result.get("data_preview"):
                    print(f"       结果: {step_result['data_preview']}")
                if step_result.get("csv_path"):
                    print(f"       CSV文件: {step_result['csv_path']}")
                if step_result.get("chart_path"):
                    print(f"       图表文件: {step_result['chart_path']}")
                if step_result.get("duration"):
                    print(f"       耗时: {step_result['duration']:.2f}秒")

        if result.get("report_path"):
            print(f"\n  📄 报告文件: {result['report_path']}")

        print()
        print_color("────────────────────────────────────────────────────────", CliColors.PURPLE)
        print()

    # ──────────────────────────────────────────────
    # 主循环
    # ──────────────────────────────────────────────

    async def run(self):
        """运行CLI主循环 — 委托给 REPL 实现"""
        from cli.repl import REPL

        repl = REPL(self)
        await repl.run()


# ──────────────────────────────────────────────
# 模块级函数
# ──────────────────────────────────────────────

async def main(log_file: Optional[str] = None, log_to_console: bool = True):
    """主入口"""
    from cli.logging_system import init_logger

    init_logger(log_file=log_file or "", log_to_console=log_to_console)

    cli = EnhancedCLI()
    cli._init_session()
    await cli.run()


def parse_args():
    """解析命令行参数"""
    import sys

    my_args = [
        "--log-file", "-l", "--no-console-log",
        "--dual-terminal", "-d", "--single-terminal", "-s",
    ]
    has_my_args = any(arg in sys.argv for arg in my_args)

    if not has_my_args:
        return argparse.Namespace(
            log_file=None, no_console_log=False,
            dual_terminal=False, single_terminal=False,
        )

    parser = argparse.ArgumentParser(description="小雷版小龙虾 AI Agent CLI")
    parser.add_argument("--log-file", "-l", type=str, default=None, help="日志文件路径（用于双终端模式）")
    parser.add_argument("--no-console-log", action="store_true", help="不在终端输出日志（用于日志面板）")
    parser.add_argument("--dual-terminal", "-d", action="store_true", default=False, help="启用双终端模式")
    parser.add_argument("--single-terminal", "-s", action="store_true", default=False, help="禁用双终端模式")
    return parser.parse_args()


def is_in_tmux():
    """检查是否在 tmux 环境中"""
    return os.environ.get("TMUX") is not None


def setup_dual_terminal():
    """设置双终端模式"""
    if not shutil.which("tmux"):
        print("⚠️  tmux 未安装，无法启用双终端模式")
        print("   安装方式: macOS: brew install tmux, Ubuntu: sudo apt install tmux")
        return False

    script_dir = Path(__file__).parent
    log_file = str(script_dir / "logs" / "agent.log")
    (script_dir / "logs").mkdir(exist_ok=True)
    Path(log_file).write_text("", encoding="utf-8")

    session_name = "xiaolei_agent"
    result = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True)

    if result.returncode == 0:
        subprocess.run(["tmux", "attach-session", "-t", session_name])
        return True

    try:
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "-n", "Agent"])
        subprocess.run(["tmux", "set-option", "-t", session_name, "history-limit", "10000"])
        subprocess.run(["tmux", "set-option", "-t", session_name, "mouse", "on"])
        subprocess.run(["tmux", "split-window", "-h"])
        subprocess.run(["tmux", "resize-pane", "-L", "70"])
        subprocess.run([
            "tmux", "send-keys", "-t", f"{session_name}:Agent.0",
            f"cd '{script_dir}' && python cli.py --dual-terminal", "C-m",
        ])
        subprocess.run([
            "tmux", "send-keys", "-t", f"{session_name}:Agent.1",
            f"cd '{script_dir}' && tail -f '{log_file}'", "C-m",
        ])
        subprocess.run(["tmux", "select-pane", "-t", "0"])
        subprocess.run(["tmux", "attach-session", "-t", session_name])
        return True
    except Exception as e:
        print(f"❌ 启动双终端模式失败: {e}")
        return False


if __name__ == "__main__":
    args = parse_args()

    enable_dual = args.dual_terminal or (
        not args.single_terminal and os.environ.get("TMUX") is None
    )

    if enable_dual and shutil.which("tmux"):
        if setup_dual_terminal():
            sys.exit(0)

    asyncio.run(main(log_file=args.log_file, log_to_console=not args.no_console_log))
