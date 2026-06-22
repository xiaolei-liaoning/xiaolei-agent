"""记忆推动机制 — 定期触发记忆整理

借鉴 Hermes Agent 的 nudge 系统：
- 每 N 轮对话触发一次后台记忆审查
- 审查内容：向量记忆是否需要整理、STM 是否需要压缩
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_NUDGE_INTERVAL = 10  # 每10轮触发一次
NUDGE_COOLDOWN = 300  # 5分钟冷却时间


class MemoryNudge:
    """记忆推动器 — 追踪对话轮次并触发记忆整理"""

    def __init__(self, nudge_interval: int = DEFAULT_NUDGE_INTERVAL):
        self.nudge_interval = nudge_interval
        self._turn_counts = {}  # user_id → 轮次计数
        self._last_nudge = {}   # user_id → 上次nudge时间戳

    def increment(self, user_id: str) -> bool:
        """增加轮次计数，返回是否应该触发nudge"""
        if user_id not in self._turn_counts:
            self._turn_counts[user_id] = 0

        self._turn_counts[user_id] += 1

        # 检查是否达到nudge间隔
        if self._turn_counts[user_id] >= self.nudge_interval:
            # 检查冷却时间
            last = self._last_nudge.get(user_id, 0)
            if time.time() - last > NUDGE_COOLDOWN:
                self._turn_counts[user_id] = 0
                self._last_nudge[user_id] = time.time()
                return True

        return False

    def should_nudge(self, user_id: str) -> bool:
        """检查是否应该触发nudge（不增加计数）"""
        count = self._turn_counts.get(user_id, 0)
        if count >= self.nudge_interval:
            last = self._last_nudge.get(user_id, 0)
            if time.time() - last > NUDGE_COOLDOWN:
                return True
        return False


# 全局单例
_nudge: Optional[MemoryNudge] = None


def get_memory_nudge() -> MemoryNudge:
    global _nudge
    if _nudge is None:
        _nudge = MemoryNudge()
    return _nudge
