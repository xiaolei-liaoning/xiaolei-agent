"""
MemorySystem - Agent记忆系统

每个 Agent 拥有独立的记忆系统，支持：
- 短期记忆（工作记忆）
- 长期记忆（重要信息的持久化存储）
- 情景记忆（事件序列的存储与回顾）
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemorySystem:
    """Agent记忆系统 - 短期、长期、情景记忆"""

    def __init__(self, agent: 'BaseAgent'):
        self.agent = agent
        self.short_term: Dict[str, Any] = {}    # 短期记忆
        self.long_term: List[Dict[str, Any]] = []  # 长期记忆
        self.episodic: List[Dict[str, Any]] = []   # 情景记忆

    async def remember(self, key: str, value: Any) -> None:
        """记忆：存储信息"""
        self.short_term[key] = {
            "value": value,
            "timestamp": time.time()
        }

    async def recall(self, key: str) -> Optional[Any]:
        """回忆：检索信息"""
        if key in self.short_term:
            return self.short_term[key]["value"]
        return None

    async def forget(self, key: str) -> None:
        """遗忘：删除信息"""
        self.short_term.pop(key, None)

    async def store_episode(self, episode: Dict[str, Any]) -> None:
        """存储情景记忆"""
        self.episodic.append({
            **episode,
            "timestamp": time.time()
        })

    async def get_recent_episodes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的情景记忆"""
        return self.episodic[-limit:]

    async def consolidate_to_long_term(self) -> None:
        """将短期记忆整合到长期记忆"""
        # 根据重要性和访问频率决定是否保留
        important_memories = [
            (k, v) for k, v in self.short_term.items()
            if v.get("access_count", 0) > 3
        ]

        for key, value in important_memories:
            self.long_term.append({
                "key": key,
                "value": value["value"],
                "timestamp": time.time()
            })

        # 限制长期记忆大小
        if len(self.long_term) > 1000:
            self.long_term = self.long_term[-1000:]
