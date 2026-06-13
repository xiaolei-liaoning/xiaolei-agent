"""
SubagentRegistry — 子 Agent 类型注册表

全局单例，内置 5 个预置 Agent 类型（含工具权限约束），
同时支持运行时从 .md 文件动态注册更多类型。
"""

import logging
from typing import Dict, List, Optional

from .models import SubagentProfile

logger = logging.getLogger(__name__)

# ── 内置 Agent 类型定义（含工具权限约束） ────────────────────────────────
# 每个类型限制可见工具集，防止子 Agent 调用不该用的工具。
# 选型原则参考 OpenCode：Explore=只读，Plan=只读，Coder=Coder 全开。
_BUILTIN_PROFILES: Dict[str, SubagentProfile] = {
    # 通用型 — 无限制
    "general-purpose": SubagentProfile(
        name="general-purpose",
        description="通用 Agent，可执行所有类型的任务。无工具限制。",
    ),
    # 搜索/浏览型 — 只读工具
    "Explore": SubagentProfile(
        name="Explore",
        description="搜索和浏览 Agent，用于信息收集和资料查找。只有读取类工具。",
        tools=["read_file", "search_files", "web_search", "fetch_url"],
    ),
    # 规划型 — 只读 + 搜索，不能写文件或执行代码
    "Plan": SubagentProfile(
        name="Plan",
        description="规划 Agent，用于任务分解和方案设计。只有读取和搜索工具。",
        tools=["read_file", "search_files", "web_search", "fetch_url"],
    ),
    # 编码型 — 全工具可用，但排除 git（交由 orchestrator 决定）
    "Coder": SubagentProfile(
        name="Coder",
        description="代码 Agent，用于编写和调试代码。可使用所有开发和搜索工具。",
        disallowed_tools=["git"],
    ),
    # 分析型 — 读取 + 搜索 + 执行 Python（数据分析用）
    "Analyst": SubagentProfile(
        name="Analyst",
        description="数据分析 Agent，用于数据分析、统计和图表生成。有 Python 执行能力。",
        tools=[
            "read_file", "search_files", "web_search", "fetch_url",
            "execute_python", "write_file",
        ],
    ),
    # 运维型 — shell + git + 文件读写
    "Operator": SubagentProfile(
        name="Operator",
        description="运维 Agent，用于执行 Shell 命令和 Git 操作。",
        tools=[
            "execute_shell", "execute_python", "git",
            "read_file", "write_file", "search_files",
        ],
    ),
}


class SubagentRegistry:
    """子 Agent 类型注册表 — 全局单例

    内置 6 个预置类型（Explore/Plan/Coder/Analyst/Operator/general-purpose），
    运行时也可通过 discover_agents() 从 .claude/agents 目录加载更多。

    用法：
        registry = get_subagent_registry()
        profile = registry.dispatch("Explore")   # 返回内置类型
        registry.register(SubagentProfile(name="my-custom", ...))  # 运行时注册
    """

    _instance: Optional["SubagentRegistry"] = None

    def __new__(cls) -> "SubagentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._profiles: Dict[str, SubagentProfile] = {}
            # 注册内置 Profile
            for name, profile in _BUILTIN_PROFILES.items():
                cls._instance._profiles[name] = profile
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
        """清空动态创建的 profile，保留内置"""
        builtin_names = set(_BUILTIN_PROFILES.keys())
        self._profiles = {k: v for k, v in self._profiles.items() if k in builtin_names}

    def __contains__(self, name: str) -> bool:
        return name in self._profiles


# 全局单例
_registry = SubagentRegistry()


def get_subagent_registry() -> SubagentRegistry:
    """获取 SubagentRegistry 全局单例"""
    return _registry
