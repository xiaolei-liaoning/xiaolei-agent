"""
重复操作检测器 — 防止Agent兜圈子

检测相同 (目标 → 操作 → 结果) 模式反复出现，
提供 LLM 可见的"已尝试过"信息，引导换方案。
"""

import hashlib
import json
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RepetitionTracker:
    """跟踪执行模式，检测重复

    用法：
        tracker = RepetitionTracker(threshold=3)
        tracker.record("爬取数据", "fetch(url='...')", "超时")
        if tracker.is_repeating(...):
            print(tracker.advice())  # → "相同操作已执行3次，建议换方案"
    """

    def __init__(self, threshold: int = 3):
        self._records: Dict[str, int] = {}
        self._history: List[Dict[str, Any]] = []
        self.threshold = threshold

    # ── 记录 ────────────────────────────────────────────────────────────

    def _signature(self, goal: str, action: str, result: Any) -> str:
        raw = f"{goal}|{action}|{str(result)[:200]}"
        return hashlib.md5(raw.encode()).hexdigest()

    def record(self, goal: str, action: str, result: Any) -> int:
        """记录一次执行，返回该模式累计次数"""
        sig = self._signature(goal, action, result)
        count = self._records.get(sig, 0) + 1
        self._records[sig] = count
        self._history.append({
            "goal": goal[:80],
            "action": action[:120],
            "result": str(result)[:200],
            "time": time.time(),
            "count": count,
        })
        return count

    def is_repeating(self, goal: str, action: str, result: Any) -> bool:
        """检测是否达到重复阈值"""
        return self.record(goal, action, result) >= self.threshold

    # ── 同类任务归组 ────────────────────────────────────────────────────

    def group_similar(self, goal: str) -> List[Dict[str, Any]]:
        """找出同一目标下的所有尝试历史"""
        return [h for h in self._history if goal[:60] in h["goal"] or h["goal"][:60] in goal]

    def similar_count(self, goal: str) -> int:
        """同一目标已尝试次数"""
        return len(self.group_similar(goal))

    # ── LLM 可见提示 ───────────────────────────────────────────────────

    def advice(self, goal: str = "") -> str:
        """生成智能提醒文本，注入 LLM 提示词"""
        repeats = [(k, v) for k, v in self._records.items() if v >= 2]
        if not repeats and not goal:
            return ""
        lines: List[str] = []

        if goal:
            same_goal = self.group_similar(goal)
            if same_goal:
                lines.append(f"## ⚠️ 任务「{goal[:50]}」已尝试 {len(same_goal)} 次")
                for h in same_goal[-3:]:
                    lines.append(f"- 尝试: {h['action']} → {h['result'][:60]}")

        if repeats:
            lines.append("## ⚠️ 检测到重复模式")
            for sig, count in sorted(repeats, key=lambda x: -x[1]):
                if count >= self.threshold:
                    lines.append(f"- 相同模式重复 {count} 次，建议换方案")
                else:
                    lines.append(f"- 相同模式出现 {count} 次")

        return "\n".join(lines)

    def clear(self) -> None:
        self._records.clear()
        self._history.clear()
