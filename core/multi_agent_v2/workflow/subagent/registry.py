"""
SubagentRegistry — 子 Agent 类型注册表

全局单例，管理 SubagentProfile 的注册、查找、智能分派。
内置 5 种预定义类型。

注册表可在任意时刻扩展：
  registry.register(SubagentProfile(name="my-custom", ...))

未注册的类型会降级为 "general"。
"""

import logging
from typing import Dict, Optional

from .models import SubagentProfile

logger = logging.getLogger(__name__)

# ── 内置子 Agent 类型配置 ─────────────────────────────────────
_BUILTIN_PROFILES: Dict[str, SubagentProfile] = {
    "general": SubagentProfile(
        name="general",
        description="通用子 Agent，默认类型",
    ),
    "explorer": SubagentProfile(
        name="explorer",
        description="快速搜索和探索 —— 联网搜索、信息获取、代码浏览",
        model="",
        personality="你是一个信息搜索专家，擅长从多源获取并验证信息。",
        role="researcher",
        max_rounds=5,
    ),
    "analyst": SubagentProfile(
        name="analyst",
        description="深度分析和推理 —— 数据对比、趋势分析、报告撰写",
        model="",
        personality="你是一个数据分析专家，擅长从数据中提取洞察并撰写分析报告。",
        role="analyst",
        max_rounds=15,
    ),
    "coder": SubagentProfile(
        name="coder",
        description="代码编写和调试 —— 生成代码、调试错误、重构优化",
        model="",
        personality="你是一个资深程序员，擅长编写高质量代码和调试。",
        role="coder",
        max_rounds=20,
    ),
    "critic": SubagentProfile(
        name="critic",
        description="质疑和验证 —— 找漏洞、反例、边界情况",
        model="",
        personality="你是一个严格的审查员，擅长找漏洞和错误。",
        role="analyst",
        max_rounds=3,
    ),
}


class SubagentRegistry:
    """子 Agent 类型注册表 — 全局单例"""

    _instance: Optional["SubagentRegistry"] = None

    def __new__(cls) -> "SubagentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._profiles: Dict[str, SubagentProfile] = {}
            cls._instance._initialized = False
        return cls._instance

    def _ensure(self) -> None:
        """懒加载内置类型"""
        if not self._initialized:
            self._profiles = dict(_BUILTIN_PROFILES)
            self._initialized = True

    def register(self, profile: SubagentProfile) -> None:
        """注册或覆盖一个子 Agent 类型"""
        self._ensure()
        self._profiles[profile.name] = profile
        logger.info(f"SubagentRegistry: 注册类型 '{profile.name}'")

    def get(self, name: str) -> Optional[SubagentProfile]:
        """按名称查找，未找到返回 None"""
        self._ensure()
        return self._profiles.get(name)

    def dispatch(self, name: str) -> SubagentProfile:
        """智能分派：按名查找 → 降级到 general

        Args:
            name: agentType 字符串

        Returns:
            SubagentProfile，未注册时返回 general
        """
        self._ensure()
        profile = self._profiles.get(name)
        if profile is None:
            logger.debug(f"SubagentRegistry: 未找到类型 '{name}'，降级为 general")
            return self._profiles["general"]
        return profile

    def list_types(self) -> Dict[str, str]:
        """列出所有已注册类型名+描述"""
        self._ensure()
        return {k: v.description for k, v in self._profiles.items()}

    def __contains__(self, name: str) -> bool:
        self._ensure()
        return name in self._profiles


# 全局单例
_registry = SubagentRegistry()


def get_subagent_registry() -> SubagentRegistry:
    """获取 SubagentRegistry 全局单例"""
    return _registry
