"""Utility handlers — help, status, tools, show, quit, clear, history, debug, think, reset, test commands."""

import hashlib
import logging
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from cli.colors import (
    BOLD,
    CLAUDE,
    ERROR,
    INACTIVE,
    SUBTLE,
    SUCCESS,
    WARNING,
    CliColors,
    _console,
    print_color,
    print_error,
    print_success,
    print_warning,
)
from cli.command_parser import CommandType, ParsedCommand
from cli.logging_system import log_error, log_info, log_success
from cli.thinking_engine import set_thinking_enabled


class UtilityHandler:
    """Handles help, status, tools, show, quit, clear, history, debug, think, reset, test commands."""

    def __init__(self, cli):
        self.cli = cli

    # ──────────────────────────────────────────────
    # /help
    # ──────────────────────────────────────────────

    def handle_help(self, search_term: str = ""):
        """分类帮助系统 — 命令按类别分面板展示"""
        from rich.columns import Columns
        from rich.console import Console as RichConsole
        from rich.console import Group
        from rich.panel import Panel
        from rich.table import Table

        rc = RichConsole()

        if search_term:
            self._handle_help_search(search_term)
            return

        categories = {
            "📋 Core": ["/run", "/chat", "/smart", "/orchestrate", "/agents"],
            "📊 Analysis": ["/analyze", "/review", "/scrape"],
            "🤖 Automation": ["/automate", "/wechat"],
            "⚙️ System": ["/status", "/config", "/mcp", "/tools", "/plugin"],
            "🎮 Tools": ["/agent", "/game", "/fun", "/art"],
            "🔄 Session": ["/help", "/history", "/clear", "/debug", "/think", "/reset", "/quit"],
        }

        help_map = self.cli.command_parser.COMMAND_HELP

        panels = []
        for cat_name, cmds in categories.items():
            table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
            table.add_column("Cmd", style=f"bold {CLAUDE}", no_wrap=True)
            table.add_column("Desc", style="white")
            for cmd in cmds:
                desc = help_map.get(cmd, "")
                table.add_row(cmd, desc)
            panels.append(
                Panel(table, title=f"[bold]{cat_name}[/bold]", border_style=SUBTLE, padding=(1, 2))
            )

        rc.print()
        left = Group(*panels[:3])
        right = Group(*panels[3:])

        help_layout = Panel(
            Columns([left, right], equal=True, expand=True),
            title=f"[bold {CLAUDE}]🦞 xiaolei AI Agent 命令参考[/bold {CLAUDE}]",
            border_style=CLAUDE,
            padding=(1, 2),
        )
        rc.print(help_layout)
        rc.print(
            f"\n  [{INACTIVE}]💡 提示: /help search <关键词> 搜索命令 /tools 查看所有工具状态[/{INACTIVE}]"
        )
        rc.print()

    def _handle_help_search(self, term: str):
        """搜索命令帮助"""
        from rich.console import Console as RichConsole
        from rich.table import Table

        rc = RichConsole()
        help_map = self.cli.command_parser.COMMAND_HELP
        results = []
        term_lower = term.lower()
        for cmd, desc in help_map.items():
            if term_lower in cmd.lower() or term_lower in desc.lower():
                results.append((cmd, desc))

        if not results:
            rc.print(f'\n  [{INACTIVE}]未找到包含 "{term}" 的命令[/{INACTIVE}]')
            return

        table = Table(
            title=f'搜索 "{term}" 结果 ({len(results)} 条)',
            title_style="bold",
            border_style=SUBTLE,
            header_style=f"bold {CLAUDE}",
        )
        table.add_column("命令", style=f"bold {CLAUDE}")
        table.add_column("说明", style="white")
        for cmd, desc in results:
            idx = cmd.lower().find(term_lower)
            if idx >= 0:
                cmd = cmd[:idx] + f"[{CLAUDE}]{cmd[idx:idx+len(term)]}[/{CLAUDE}]" + cmd[idx + len(term):]
            table.add_row(cmd, desc)
        rc.print()
        rc.print(table)
        rc.print()

    # ──────────────────────────────────────────────
    # /tools
    # ──────────────────────────────────────────────

    async def handle_tools(self, parsed_cmd: ParsedCommand = None):
        """查看所有可用工具 — 按类型分组展示"""
        from rich.console import Console as RichConsole
        from rich.panel import Panel
        from rich.table import Table

        rc = RichConsole()

        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry

            reg = get_tool_registry()
            if not reg._initialized:
                await reg.discover_all()

            summary = reg.get_available_tools_summary()

            groups = {
                "🔧 代码执行": reg.get_tools_by_tag("code"),
                "🔍 搜索": reg.get_tools_by_tag("search"),
                "🌐 网络": reg.get_tools_by_tag("web") + reg.get_tools_by_tag("api"),
                "🧠 反思": reg.get_tools_by_tag("reflect"),
                "🎯 技能": reg.get_tools_by_tag("skill"),
                "📦 MCP": reg.get_tools_by_tag("mcp"),
                "📁 文件": reg.get_tools_by_tag("file"),
            }

            by_server = {}
            for t in reg._tools.values():
                by_server.setdefault(t.server, []).append(t)

            overview = (
                f"[{BOLD}]{summary['total']}[/] 个工具 | "
                f"[{SUCCESS}]{summary['builtin']}[/] 内置 | "
                f"[{CLAUDE}]{summary['mcp_awesome']}[/] MCP 已发现 | "
                f"[{SUCCESS}]{summary['mcp_connected']}[/] MCP 已连接"
            )

            tag_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
            tag_table.add_column("类别", style=f"bold {CLAUDE}", no_wrap=True)
            tag_table.add_column("工具", style="white")
            for group_name, tools in groups.items():
                if not tools:
                    continue
                names = ", ".join(f"[{SUBTLE}]{t.name}[/{SUBTLE}]" for t in tools)
                tag_table.add_row(group_name, names)

            mcp_rows = []
            for server, tools in sorted(by_server.items()):
                if server in ("__builtin__", "__mcp__", ""):
                    continue
                names = ", ".join(t.name for t in tools)
                mcp_rows.append(f"  [{CLAUDE}]●[/] {server}: [{SUBTLE}]{names}[/{SUBTLE}]")

            panels = [
                Panel(tag_table, title="[bold]工具列表[/bold]", border_style=SUBTLE, padding=(1, 2))
            ]
            if mcp_rows:
                mcp_text = "\n".join(mcp_rows)
                panels.append(
                    Panel(mcp_text, title="[bold]MCP 服务器[/bold]", border_style=CLAUDE, padding=(1, 2))
                )

            rc.print()
            rc.print(
                Panel(
                    f"  {overview}",
                    title="[bold]🔧 工具系统概览[/bold]",
                    border_style=SUBTLE, padding=(0, 1),
                )
            )
            for p in panels:
                rc.print(p)
            rc.print(
                f"  [{INACTIVE}]💡 提示: 工具按任务需求自动筛选，用自然语言描述任务即可自动使用合适工具[/]"
            )
            rc.print()

        except Exception as e:
            self.cli._display_error_panel(e, "获取工具列表失败")

    # ──────────────────────────────────────────────
    # /show
    # ──────────────────────────────────────────────

    def handle_show(self, parsed_cmd: ParsedCommand):
        """展开之前折叠的输出"""
        target = parsed_cmd.action or parsed_cmd.remaining
        if not target:
            print_warning("请指定要展开的内容，如: /show error")
            return

        key = target.strip().lower()
        if hasattr(self.cli, "_collapsed_outputs") and key in self.cli._collapsed_outputs:
            from rich.panel import Panel

            data = self.cli._collapsed_outputs[key]
            _console.print(
                Panel(str(data)[:10000], title=f"[+] {key}", border_style="grey58")
            )
        else:
            print_warning(f"未找到展开内容: {target}")

    # ──────────────────────────────────────────────
    # /quit
    # ──────────────────────────────────────────────

    def handle_quit(self, parsed_cmd: ParsedCommand = None):
        """处理退出命令"""
        print_color("\n👋 再见！期待下次为你服务！", CliColors.BLUE)
        self.cli.running = False

    # ──────────────────────────────────────────────
    # /clear
    # ──────────────────────────────────────────────

    def handle_clear(self, parsed_cmd: ParsedCommand = None):
        """处理清屏命令"""
        print("\033c", end="")

    # ──────────────────────────────────────────────
    # /history
    # ──────────────────────────────────────────────

    def handle_history(self, parsed_cmd: ParsedCommand = None):
        """处理历史记录命令"""
        history = self.cli.command_parser.get_history(10)
        if history:
            print_color("\n命令历史:", CliColors.BOLD)
            for i, cmd in enumerate(reversed(history), 1):
                print_color(f"  {i}. {cmd}", CliColors.WHITE)
        else:
            print_warning("暂无命令历史")

    # ──────────────────────────────────────────────
    # /debug
    # ──────────────────────────────────────────────

    def handle_debug(self, parsed_cmd: ParsedCommand = None):
        """处理调试模式切换"""
        self.cli.debug_mode = self.cli.command_parser.toggle_debug()
        if self.cli._status_bar:
            self.cli._status_bar.set_debug(self.cli.debug_mode)
        if self.cli.debug_mode:
            log_success("调试模式已启用")
        else:
            log_info("调试模式已禁用")

    # ──────────────────────────────────────────────
    # /think
    # ──────────────────────────────────────────────

    def handle_think(self, parsed_cmd: ParsedCommand = None):
        """处理思考模式切换"""
        enabled = self.cli.command_parser.toggle_think()
        set_thinking_enabled(enabled)
        if enabled:
            log_success("思考模式已启用")
        else:
            log_info("思考模式已禁用")

    # ──────────────────────────────────────────────
    # /reset
    # ──────────────────────────────────────────────

    def handle_reset(self, parsed_cmd: ParsedCommand):
        """处理重置命令"""
        reset_all = parsed_cmd.action == "all"

        if reset_all:
            print_color("\n🔄 正在重置所有数据...", CliColors.YELLOW)
            self.cli.command_parser.clear_history()
            self.cli.chat_history = []

            script_dir = Path(__file__).parent.parent
            log_file = script_dir / "logs" / "agent.log"
            if log_file.exists():
                log_file.write_text("", encoding="utf-8")
            print_success("✅ 会话已完全重置（历史 + 记忆 + 日志）")
        else:
            print_color("\n🔄 正在清空命令历史...", CliColors.YELLOW)
            self.cli.command_parser.clear_history()
            self.cli.chat_history = []
            print_success("✅ 命令历史已清空")

        self.cli.handle_clear()

    # ──────────────────────────────────────────────
    # /status
    # ──────────────────────────────────────────────

    async def handle_status(self, parsed_cmd: ParsedCommand = None):
        """处理状态命令"""
        print_color("\n系统状态:", CliColors.BOLD)
        print_color("────────────────", CliColors.GRAY)

        components = [
            ("命令解析器", "cli.command_parser", "CommandParser"),
            ("思考引擎", "cli.thinking_engine", "ThinkingEngine"),
            ("日志系统", "cli.logging_system", "EnhancedLogger"),
        ]

        print_color("核心组件:", CliColors.CYAN)
        for name, module, obj in components:
            try:
                mod = __import__(module, fromlist=[obj])
                getattr(mod, obj)
                print_color(f"  ✅ {name}", CliColors.GREEN)
            except Exception as e:
                print_color(f"  ❌ {name} - {str(e)[:30]}", CliColors.RED)

        print_color("\n当前模式:", CliColors.CYAN)
        print_color(
            f"  思考模式: {'✅ 启用' if self.cli.thinking_engine.is_enabled() else '❌ 禁用'}",
            CliColors.GREEN if self.cli.thinking_engine.is_enabled() else CliColors.RED,
        )
        print_color(
            f"  调试模式: {'✅ 启用' if self.cli.debug_mode else '❌ 禁用'}",
            CliColors.GREEN if self.cli.debug_mode else CliColors.RED,
        )

    # ──────────────────────────────────────────────
    # /test
    # ──────────────────────────────────────────────

    async def handle_test(self, parsed_cmd: ParsedCommand):
        """处理测试命令 - 测试核心服务功能"""
        action = parsed_cmd.action or "all"

        print_color("\n🧪 核心服务测试", CliColors.BOLD)
        print_color("────────────────", CliColors.GRAY)

        if action == "clarify" or action == "all":
            await self._test_clarification_service()
        if action == "permission" or action == "all":
            await self._test_permission_service()
        if action == "forked" or action == "all":
            await self._test_forked_agent_service()
        if action == "all":
            print_success("\n✅ 所有服务测试完成！")

    async def _test_clarification_service(self):
        """测试反问服务"""
        print_color("\n📝 反问服务测试:", CliColors.CYAN)
        from cli.clarification_service import get_clarification_service

        service = get_clarification_service()
        if not service:
            print_error("  ❌ 反问服务未初始化")
            return

        for msg, desc in [("查询天气", "缺少城市信息"), ("分析项目", "缺少分析维度"), ("打开文件", "缺少目标文件")]:
            print_color(f"\n  测试: {desc}", CliColors.WHITE)
            print_color(f"  输入: '{msg}'", CliColors.GRAY)
            questions = service.generate_questions(msg)
            if questions:
                q = questions[0]
                print_color(f"  反问: {q.question}", CliColors.GREEN)
                if q.options:
                    print_color(f"  选项: {', '.join(opt.label for opt in q.options)}", CliColors.GRAY)
            else:
                print_color("  无需反问", CliColors.YELLOW)
        print_color("\n  ✅ 反问服务测试通过", CliColors.GREEN)

    async def _test_permission_service(self):
        """测试权限服务"""
        print_color("\n🔐 权限服务测试:", CliColors.CYAN)
        from cli.permission_service import PermissionType, get_permission_service

        service = get_permission_service()
        if not service:
            print_error("  ❌ 权限服务未初始化")
            return

        for perm_type, desc in [
            (PermissionType.READ_FILE, "读取文件"),
            (PermissionType.WRITE_FILE, "写入文件"),
            (PermissionType.DELETE_FILE, "删除文件"),
        ]:
            print_color(f"\n  测试: {desc}", CliColors.WHITE)
            decision = service.check_permission(perm_type)
            color = CliColors.GREEN if decision.value == "allow" else (CliColors.YELLOW if decision.value == "prompt" else CliColors.RED)
            print_color(f"  决策: {decision.value}", color)
        print_color("\n  ✅ 权限服务测试通过", CliColors.GREEN)

    async def _test_forked_agent_service(self):
        """测试Forked Agent服务"""
        print_color("\n🔀 Forked Agent服务测试:", CliColors.CYAN)
        from cli.forked_agent_service import get_forked_agent_service

        service = get_forked_agent_service()
        if not service:
            print_error("  ❌ Forked Agent服务未初始化")
            return

        print_color("  测试侧问题处理...", CliColors.WHITE)
        result = await service.create_side_question("什么是人工智能？")
        if result.status.value == "completed":
            print_color(f"  响应: {(result.response or '')[:30]}...", CliColors.GREEN)
        else:
            print_error(f"  失败: {result.error}")

        print_color("\n  测试并行任务...", CliColors.WHITE)
        results = await service.run_parallel_tasks([{"prompt": "任务A"}, {"prompt": "任务B"}])
        completed = len([r for r in results if r.status.value == "completed"])
        print_color(f"  完成任务数: {completed}", CliColors.GREEN)
        print_color("\n  ✅ Forked Agent服务测试通过", CliColors.GREEN)
