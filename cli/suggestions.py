"""命令模糊建议 — 在不认识命令时推荐最接近的匹配

用法:
    from cli.suggestions import suggest_and_render
    suggest_and_render(failed_input, completer)
"""

from typing import List, Dict, Optional, TYPE_CHECKING

from rich.panel import Panel
from difflib import get_close_matches

from cli.colors import _console, CLAUDE, ERROR, SUBTLE, INACTIVE

if TYPE_CHECKING:
    from cli.autocomplete import Completer


def suggest_commands(
    input_text: str,
    available_commands: List[str],
    help_map: Dict[str, str],
    n: int = 3,
) -> List[str]:
    """模糊匹配：对不认识的 /command 返回最接近的建议

    Args:
        input_text: 用户原始输入 (如 "/hepl wat")
        available_commands: 所有合法命令 (如 ["/help", "/run"])
        help_map: 命令 → 描述 字典
        n: 最多返回多少个建议

    Returns:
        按相似度排序的建议命令列表
    """
    if not input_text or not input_text.startswith("/"):
        return []

    # 只匹配命令部分（第一个词）
    cmd_part = input_text.split()[0]

    # 模糊匹配
    matches = get_close_matches(cmd_part, available_commands, n=n, cutoff=0.3)

    # 补充：按描述关键词匹配
    cmd_lower = cmd_part.lstrip("/").lower()
    for cmd, desc in help_map.items():
        if cmd in matches:
            continue
        if cmd_lower and cmd_lower in desc.lower():
            matches.append(cmd)
            if len(matches) >= n:
                break

    return matches[:n]


def render_suggestions(suggestions: List[str], help_map: Dict[str, str]) -> None:
    """以 Rich Panel 打印建议"""
    if not suggestions:
        return

    lines: List[str] = []
    for cmd in suggestions:
        desc = help_map.get(cmd, "")
        if desc:
            lines.append(f"  [{CLAUDE}]{cmd:<16}[/] {desc}")
        else:
            lines.append(f"  [{CLAUDE}]{cmd}[/]")

    _console.print(Panel(
        "\n".join(lines),
        title=f"[{ERROR}]Command not found, did you mean…[/]",
        border_style=SUBTLE,
        padding=(0, 2),
    ))


def suggest_and_render(failed_input: str, completer: Optional["Completer"] = None) -> None:
    """便捷函数：一句调用完成建议 + 渲染"""
    if not completer:
        return

    suggestions = suggest_commands(failed_input, completer.commands, completer.help_map)

    if suggestions:
        render_suggestions(suggestions, completer.help_map)
