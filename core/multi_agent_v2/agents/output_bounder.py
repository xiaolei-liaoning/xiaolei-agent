"""
OutputBounder — 工具输出自动截断（委托给 tool_result.bound_result）

所有截断逻辑已合并到 core.multi_agent_v2.tools.tool_result.bound_result，
此模块仅保留 BounderStats 向后兼容和 bound_tool_output 别名。
"""

import logging
from typing import Dict

from core.multi_agent_v2.tools.tool_result import bound_result as _bound_result

logger = logging.getLogger(__name__)


class BounderStats:
    """截断统计（保留向后兼容）"""

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


def bound_tool_output(tool_name: str, text: str) -> str:
    """别名：委托给 tool_result.bound_result

    保留原签名 (tool_name, text: str) -> str 以保持向后兼容。
    """
    if not isinstance(text, str):
        text = str(text)
    return _bound_result(tool_name, text)
