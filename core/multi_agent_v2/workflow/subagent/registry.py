"""
SubagentRegistry — 子 Agent 类型注册表

全局单例，支持运行时动态注册 SubagentProfile。
不预设任何硬编码类型，所有类型在运行时按需创建。
"""

import logging
from typing import Dict, List, Optional

from .models import SubagentProfile

logger = logging.getLogger(__name__)


class SubagentRegistry:
    """子 Agent 类型注册表 — 全局单例

    用法：
        registry = get_subagent_registry()

        # 动态注册
        registry.register(SubagentProfile(name="my-custom", ...))

        # 查找（不存在时降级为通用类型）
        profile = registry.dispatch("my-custom")
    """

    _instance: Optional["SubagentRegistry"] = None

    def __new__(cls) -> "SubagentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._profiles: Dict[str, SubagentProfile] = {}
        return cls._instance

    def register(self, profile: SubagentProfile) -> None:
        """注册或覆盖一个子 Agent 类型"""
        self._profiles[profile.name] = profile
        logger.debug(f"SubagentRegistry: 注册类型 '{profile.name}'")

    def get(self, name: str) -> Optional[SubagentProfile]:
        """按名称查找，未找到返回 None"""
        return self._profiles.get(name)

    def dispatch(self, name: str) -> SubagentProfile:
        """按名称查找，未找到返回通用类型

        Args:
            name: agentType 字符串

        Returns:
            SubagentProfile，未注册时返回通用 profile
        """
        profile = self._profiles.get(name)
        if profile is not None:
            return profile

        # 忽略大小写匹配
        name_lower = name.lower()
        for key in self._profiles:
            if key.lower() == name_lower:
                return self._profiles[key]

        # 未找到，返回通用 profile（不施加任何工具约束）
        return SubagentProfile(
            name=name,
            description=f"动态创建的 Agent: {name}",
        )

    def search(self, query: str) -> List[SubagentProfile]:
        """搜索匹配的 Agent（按名称或描述）"""
        query_lower = query.lower()
        return [
            p for p in self._profiles.values()
            if query_lower in p.name.lower() or query_lower in p.description.lower()
        ]

    def list_types(self) -> Dict[str, str]:
        """列出所有已注册类型名+描述"""
        return {k: v.description for k, v in self._profiles.items()}

    def clear(self) -> None:
        """清空所有注册类型"""
        self._profiles.clear()

    def __contains__(self, name: str) -> bool:
        return name in self._profiles


# 全局单例
_registry = SubagentRegistry()


def get_subagent_registry() -> SubagentRegistry:
    """获取 SubagentRegistry 全局单例"""
    return _registry
