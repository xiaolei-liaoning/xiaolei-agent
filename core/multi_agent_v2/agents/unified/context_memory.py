"""任务级上下文记忆"""

from typing import List


class ContextMemory:
    """简单的上下文记忆（任务级）"""

    def __init__(self):
        self.entries: List[str] = []

    def add(self, entry: str) -> None:
        self.entries.append(entry)
        if len(self.entries) > 20:
            self.entries = self.entries[-20:]

    def get_recent(self, n: int = 5) -> str:
        return "\n".join(self.entries[-n:]) if self.entries else "（无上下文）"

    def clear(self) -> None:
        self.entries = []
