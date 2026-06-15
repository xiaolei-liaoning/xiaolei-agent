"""
OutputBounder — 工具输出自动截断

拦截工具执行结果，在返回给 LLM 之前按规则截断，
避免超长输出浪费 tokens。

每工具类型有独立的字符上限：
  - read/write/edit/grep/glob: 3000
  - websearch/webfetch:        4000
  - bash/shell:                5000
  - task/todo/plan:            2000
  - 其他:                      3000
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)

# ── 每工具类型的截断上限 ──
TOOL_OUTPUT_LIMITS: Dict[str, int] = {
    "read": 3000,
    "read_file": 3000,
    "write": 3000,
    "write_file": 3000,
    "edit": 3000,
    "edit_file": 3000,
    "grep": 3000,
    "glob": 3000,
    "search_files": 3000,
    "web_search": 4000,
    "websearch": 4000,
    "fetch_url": 4000,
    "webfetch": 4000,
    "bash": 5000,
    "shell": 5000,
    "execute_shell": 5000,
    "execute_python": 5000,
    "task": 2000,
    "todo": 2000,
    "plan": 2000,
    "write_todos": 2000,
}

DEFAULT_LIMIT = 3000


class BounderStats:
    """截断统计"""

    def __init__(self):
        self.total_truncated = 0
        self.total_saved_chars = 0
        self.truncations_by_tool: Dict[str, int] = {}

    def record(self, tool_name: str, original_len: int, truncated_len: int):
        self.total_truncated += 1
        saved = original_len - truncated_len
        self.total_saved_chars += saved
        self.truncations_by_tool[tool_name] = self.truncations_by_tool.get(tool_name, 0) + 1

    def summary(self) -> str:
        if self.total_truncated == 0:
            return "未发生截断"
        tools_detail = ", ".join(
            f"{name}={count}次"
            for name, count in sorted(self.truncations_by_tool.items())
        )
        return (
            f"截断{self.total_truncated}次, "
            f"节省{self.total_saved_chars}字符 [{tools_detail}]"
        )


# 全局单例
_bound_stats = BounderStats()


def get_bound_stats() -> BounderStats:
    """获取全局截断统计"""
    return _bound_stats


def _get_limit(tool_name: str) -> int:
    """根据工具名获取截断上限"""
    # 精确匹配
    if tool_name in TOOL_OUTPUT_LIMITS:
        return TOOL_OUTPUT_LIMITS[tool_name]
    # 模糊匹配：取最接近的工具类型
    for key, limit in TOOL_OUTPUT_LIMITS.items():
        if key in tool_name or tool_name in key:
            return limit
    return DEFAULT_LIMIT


def bound_tool_output(tool_name: str, text: str) -> str:
    """智能截断工具输出

    保留头部和尾部，中间用标识替换。
    Args:
        tool_name: 工具名
        text: 原始输出文本
    Returns:
        截断后的文本（如未超限则原样返回）
    """
    if not isinstance(text, str):
        text = str(text)

    max_chars = _get_limit(tool_name)

    if len(text) <= max_chars:
        return text

    head_len = int(max_chars * 0.6)
    tail_len = max_chars - head_len - 30  # 预留标识符空间

    head = text[:head_len]
    tail = text[-tail_len:] if tail_len > 0 else ""

    truncated_count = len(text) - max_chars
    result = f"{head}\n\n... [截断 {truncated_count} 字符] ...\n\n{tail}"

    _bound_stats.record(tool_name, len(text), len(result))
    logger.info(f"输出截断: {tool_name} {len(text)}→{len(result)}字符 (节省{truncated_count})")

    return result
