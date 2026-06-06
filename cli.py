#!/usr/bin/env python3
"""小雷版小龙虾 AI Agent - CLI入口
重定向到 cli/enhanced_cli.py （增强版CLI）

新增: 支持命令行传参直接执行（非交互模式）
示例:
  python3 cli.py 搜索百度热搜
  python3 cli.py /run 搜索百度热搜
  python3 cli.py /automate open_app --app Safari
"""
import asyncio
import os
import shutil
import sys

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 检测是否有额外argv命令要执行 ──
_SCRIPT_FLAGS = {"--log-file", "-l", "--no-console-log",
                 "--dual-terminal", "-d", "--single-terminal", "-s"}
_extra_args = [a for a in sys.argv[1:] if a not in _SCRIPT_FLAGS
               and not any(a.startswith(f) for f in ("--log-file", "-l"))]

if _extra_args:
    # ── 非交互模式：执行 argv 中的命令，直接退出 ──
    from cli.enhanced_cli import EnhancedCLI
    from cli.logging_system import init_logger
    init_logger()

    cli = EnhancedCLI()
    cli._init_session()

    cmd_str = " ".join(_extra_args)

    async def _exec_argv():
        # 如果以 / 开头，走命令解析
        if cmd_str.startswith("/"):
            parsed = cli.command_parser.parse(cmd_str)
            await cli.handle_command(parsed)
        else:
            # 自然语言，走智能请求
            await cli.handle_smart_request(cmd_str)

    asyncio.run(_exec_argv())
    sys.exit(0)

# ── 交互模式：启动REPL ──
from cli.enhanced_cli import main, parse_args

if __name__ == "__main__":
    args = parse_args()

    enable_dual = args.dual_terminal

    if enable_dual and shutil.which("tmux"):
        from cli.enhanced_cli import setup_dual_terminal
        if setup_dual_terminal():
            sys.exit(0)

    asyncio.run(main(
        log_file=args.log_file,
        log_to_console=not args.no_console_log
    ))
