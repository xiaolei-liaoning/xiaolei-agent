#!/usr/bin/env python3
"""小雷版小龙虾 AI Agent - CLI入口
重定向到 cli/enhanced_cli.py （增强版CLI）

新增: 支持命令行传参直接执行（非交互模式）
示例:
  python3 cli.py 搜索百度热搜
  python3 cli.py /run 搜索百度热搜
  python3 cli.py /automate open_app --app Safari
  python3 cli.py /feedback 5 完美

注意：所有副作用代码（创建 CLI 实例、运行 asyncio、调用 sys.exit）都
守卫在 if __name__ == "__main__": 之后。任何代码 `import cli` 都不会触发。
（疑点 #001 修复：原版本在 module-level 执行 EnhancedCLI() + asyncio.run()
 + sys.exit(0)，会让 import 立刻崩。）
"""
import asyncio
import os
import shutil
import sys

# 将项目根目录加入 path（path 操作是纯副作用，import 不影响）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _parse_extra_args(argv):
    """从 argv 中提取真实命令参数（排除脚本专属 flags）。

    纯计算函数，无副作用。供 main() 和测试使用。
    """
    _SCRIPT_FLAGS = {"--log-file", "-l", "--no-console-log",
                     "--dual-terminal", "-d", "--single-terminal", "-s"}
    return [a for a in argv if a not in _SCRIPT_FLAGS
            and not any(a.startswith(f) for f in ("--log-file", "-l"))]


def main():
    """CLI 入口（带 if __name__ == "__main__": 守卫）。

    模式选择：
    1. 有 extra args（命令参数）→ 非交互模式：执行 argv 中的命令后退出
    2. 无 extra args → 交互模式：启动 REPL
    """
    extra_args = _parse_extra_args(sys.argv[1:])

    if extra_args:
        # ── 非交互模式 ──
        from cli.enhanced_cli import EnhancedCLI
        from cli.logging_system import init_logger
        init_logger()

        cli = EnhancedCLI()
        cli._init_session()

        cmd_str = " ".join(extra_args)
        asyncio.run(_exec_argv(cli, cmd_str))
        sys.exit(0)

    # ── 交互模式 ──
    from cli.enhanced_cli import main as repl_main, parse_args, setup_dual_terminal
    args = parse_args()

    if args.dual_terminal and shutil.which("tmux"):
        if setup_dual_terminal():
            sys.exit(0)

    asyncio.run(repl_main(
        log_file=args.log_file,
        log_to_console=not args.no_console_log,
    ))


async def _exec_argv(cli, cmd_str: str):
    """执行 argv 中的单条命令（/feedback 特例化处理，其他走统一 command_parser）。"""
    # 方案C: /feedback 命令直接识别（不走 command_parser）
    if cmd_str.strip().lower().startswith("/feedback"):
        await cli.chat_handler.handle_feedback(cmd_str)
        return
    # / 开头走命令解析
    if cmd_str.startswith("/"):
        parsed = cli.command_parser.parse(cmd_str)
        await cli.handle_command(parsed)
    else:
        # 自然语言走智能请求
        await cli.chat_handler.handle_smart_request(cmd_str)


if __name__ == "__main__":
    main()