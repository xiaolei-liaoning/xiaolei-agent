#!/usr/bin/env python3
"""小雷版小龙虾 AI Agent - CLI入口
重定向到 cli/enhanced_cli.py （增强版CLI）
"""
import asyncio
import os
import shutil
import sys

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli.enhanced_cli import main, parse_args

if __name__ == "__main__":
    args = parse_args()

    enable_dual = args.dual_terminal or (not args.single_terminal and os.environ.get("TMUX") is None)

    if enable_dual and shutil.which("tmux"):
        from cli.enhanced_cli import setup_dual_terminal
        if setup_dual_terminal():
            sys.exit(0)

    asyncio.run(main(
        log_file=args.log_file,
        log_to_console=not args.no_console_log
    ))
