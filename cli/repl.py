"""REPL 主循环 — 统一的输入/输出事件循环

将 EnhancedCLI.run() 中的输入循环抽取为独立模块，
集成 Rich 样式化提示符、Tab 补全、模糊建议、状态栏。
"""

import asyncio
from typing import TYPE_CHECKING, Optional

from cli.colors import _console, print_color, CliColors
from cli.prompt import get_styled_input
from cli.autocomplete import Completer
from cli.suggestions import suggest_and_render

if TYPE_CHECKING:
    from cli.enhanced_cli import EnhancedCLI


class REPL:
    """主事件循环 — 处理输入、补全、提示符渲染"""

    def __init__(self, cli_instance: "EnhancedCLI"):
        self.cli = cli_instance
        self.completer: Optional[Completer] = None
        self._setup_completer()

    # ── 公开 API ──────────────────────────────────────────────────────────

    async def run(self):
        """运行主输入循环（替代 EnhancedCLI.run() 中的裸循环）"""
        self.cli.print_welcome()

        # 启动状态栏
        if self.cli._status_bar:
            await self.cli._status_bar.start()

        while self.cli.running:
            try:
                # 定期刷新状态栏统计
                if self.cli._status_bar:
                    await self.cli._status_bar.update()

                user_input = get_styled_input(self.cli)

                if not user_input:
                    continue

                # 快捷命令（不要求 / 前缀）
                if user_input.lower() in ("exit", "quit", "q", "退出"):
                    self.cli.handle_quit()
                    break
                if user_input.lower() in ("help", "h", "帮助"):
                    self.cli.handle_help()
                    continue

                # 自然语言：不作为命令处理
                if not user_input.startswith("/"):
                    await self.cli.handle_smart_request(user_input)
                    _console.print(f"[{CliColors.GRAY}]{'─' * 60}[/{CliColors.GRAY}]")
                    continue

                # 命令模式
                parsed_cmd = self.cli.command_parser.parse(user_input)
                await self.cli.handle_command(parsed_cmd)

            except KeyboardInterrupt:
                print_color("\n👋 再见！", CliColors.BLUE)
                self.cli.running = False
            except EOFError:
                self.cli.running = False
            except Exception as e:
                from cli.logging_system import log_error
                log_error(f"处理异常: {e}")
                # 对不识别的命令做建议
                if user_input and user_input.startswith("/"):
                    suggest_and_render(user_input, self.completer)

        # 清理
        self.completer.save_history()
        if self.cli._status_bar:
            await self.cli._status_bar.stop()

    # ── 内部方法 ───────────────────────────────────────────────────────────

    def _setup_completer(self):
        """初始化 Tab 补全器"""
        parser = self.cli.command_parser
        self.completer = Completer(
            get_commands_fn=lambda: list(parser.COMMAND_MAP.keys()),
            get_help_fn=lambda: parser.COMMAND_HELP,
        )
        self.completer.install()
