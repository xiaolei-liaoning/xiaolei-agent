"""
TaskMemory — 轻量任务记忆系统

功能：
- 存储任务描述 + 执行结果
- 新任务时按关键词检索相关历史
- 注入到思考提示作为参考经验

不依赖外部存储，纯内存。重启后清空，每次 Session 重新积累。
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """单条记忆"""
    task_id: str
    description: str
    result: str
    success: bool
    tools_used: List[str]
    timestamp: float = 0.0


class TaskMemory:
    """轻量任务记忆存储与检索"""

    def __init__(self, max_entries: int = 50):
        self._entries: List[MemoryEntry] = []
        self._max_entries = max_entries

    def remember(self, entry: MemoryEntry) -> None:
        """存储一条记忆"""
        entry.timestamp = entry.timestamp or time.time()
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
        logger.debug(f"记忆已存储: {entry.description[:50]}...")

    def recall(self, query: str, max_results: int = 3) -> List[MemoryEntry]:
        """根据查询检索相关记忆（中文/英文关键词匹配）"""
        if not self._entries or not query:
            return []

        # 支持中英文：英文按空格分词，中文按字/双字词匹配
        q = query.lower()
        scored = []
        for entry in self._entries:
            ed = entry.description.lower()
            score = 0.0
            # 中文：检查共有字符
            cn_chars = set(c for c in q if '一' <= c <= '鿿')
            en_chars = set(c for c in q if c.isalpha() and c.isascii())
            # 中文字符重叠
            if cn_chars:
                ed_cn = set(c for c in ed if '一' <= c <= '鿿')
                overlap = len(cn_chars & ed_cn)
                score += overlap / max(len(cn_chars), 1) * 2.0
            # 英文分词匹配
            if en_chars:
                q_words = set(w for w in q.split() if len(w) > 1)
                e_words = set(w for w in ed.split() if len(w) > 1)
                overlap = len(q_words & e_words)
                if q_words:
                    score += overlap / len(q_words) * 3.0
            # 整词匹配（中文双字词）
            for i in range(len(q) - 1):
                bigram = q[i:i+2]
                if '一' <= bigram[0] <= '鿿' and '一' <= bigram[1] <= '鿿':
                    if bigram in ed:
                        score += 1.0
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:max_results]]

    def advice(self, query: str) -> Optional[str]:
        """生成检索到的记忆建议文本（供注入到 prompt）"""
        related = self.recall(query)
        if not related:
            return None

        lines = ["[历史经验]"]
        for i, e in enumerate(related, 1):
            status = "✅" if e.success else "❌"
            tools = ", ".join(e.tools_used) if e.tools_used else "-"
            lines.append(f"  {i}. {status} {e.description[:60]} → {e.result[:100]} (工具: {tools})")
        return "\n".join(lines)

    @property
    def count(self) -> int:
        return len(self._entries)


# 全局单例
_memory: Optional[TaskMemory] = None


def get_task_memory() -> TaskMemory:
    global _memory
    if _memory is None:
        _memory = TaskMemory()
    return _memory
