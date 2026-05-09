"""CLI颜色和样式模块 - Claude Code风格"""

class CliColors:
    """终端颜色常量"""
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    GRAY = '\033[90m'
    BRIGHT_BLUE = '\033[38;5;75m'
    BRIGHT_CYAN = '\033[38;5;45m'
    BRIGHT_MAGENTA = '\033[38;5;213m'


def print_color(text: str, color: str = "") -> None:
    """带颜色打印"""
    if color:
        print(f"{color}{text}{CliColors.ENDC}")
    else:
        print(text)


def print_success(message: str) -> None:
    """打印成功消息"""
    print_color(f"  Success: {message}", CliColors.GREEN)


def print_error(message: str) -> None:
    """打印错误消息"""
    print_color(f"  Error: {message}", CliColors.RED)


def print_warning(message: str) -> None:
    """打印警告消息"""
    print_color(f"  Warning: {message}", CliColors.YELLOW)


def print_info(message: str) -> None:
    """打印信息消息"""
    print_color(f"  {message}", CliColors.CYAN)


def print_header(title: str) -> None:
    """打印标题 - Claude Code风格"""
    print()
    print_color(f"  {title}", CliColors.BRIGHT_BLUE + CliColors.BOLD)
    print_color(f"  {'─' * 50}", CliColors.GRAY)
    print()


def print_section(title: str) -> None:
    """打印小节标题"""
    print()
    print_color(f"  {title}", CliColors.CYAN + CliColors.BOLD)


def print_section_end() -> None:
    """打印小节结束"""
    print()


def print_chat_bubble(text: str, is_user: bool = False, timestamp: str = "") -> None:
    """打印聊天气泡 - Claude Code风格"""
    if not text or not text.strip():
        text = "(empty)"

    lines = text.split('\n')

    if is_user:
        print_color(f"\n  [You] {timestamp if timestamp else ''}", CliColors.GREEN + CliColors.BOLD)
        for line in lines:
            print_color(f"  {line}", CliColors.WHITE)
    else:
        print_color(f"\n  [Agent] {timestamp if timestamp else ''}", CliColors.BRIGHT_BLUE + CliColors.BOLD)
        for line in lines:
            print_color(f"  {line}", CliColors.CYAN)
