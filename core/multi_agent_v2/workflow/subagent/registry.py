"""
SubagentRegistry — 子 Agent 类型注册表

全局单例，管理 SubagentProfile 的注册、查找、智能分派。
内置 5 种预定义类型 + 5 种官方内置类型。

注册表可在任意时刻扩展：
  registry.register(SubagentProfile(name="my-custom", ...))
  registry.load_from_directory("/path/to/.claude/agents")

未注册的类型会降级为 "general-purpose"。
"""

import logging
import os
from typing import Dict, List, Optional

from .models import SubagentProfile

logger = logging.getLogger(__name__)

# ── 旧内置子 Agent 类型配置（legacy，保留兼容性） ─────────
_LEGACY_BUILTIN_PROFILES: Dict[str, SubagentProfile] = {
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
        # 只读 + 搜索类工具
        tools=["execute_python", "execute_shell", "fetch_url", "search", "rag_search", "file", "git", "call_api"],
    ),
    "analyst": SubagentProfile(
        name="analyst",
        description="深度分析和推理 —— 数据对比、趋势分析、报告撰写",
        model="",
        personality="你是一个数据分析专家，擅长从数据中提取洞察并撰写分析报告。",
        role="analyst",
        max_rounds=15,
        # 读取 + 分析工具，禁止写入和执行
        tools=["execute_python", "fetch_url", "search", "rag_search", "file", "git"],
        disallowed_tools=["execute_shell", "call_api"],
    ),
    "coder": SubagentProfile(
        name="coder",
        description="代码编写和调试 —— 生成代码、调试错误、重构优化",
        model="",
        personality="你是一个资深程序员，擅长编写高质量代码和调试。",
        role="coder",
        max_rounds=20,
        # 代码执行 + 文件操作
        tools=["execute_python", "execute_shell", "file", "git", "search", "rag_search"],
    ),
    "critic": SubagentProfile(
        name="critic",
        description="质疑和验证 —— 找漏洞、反例、边界情况",
        model="",
        personality="你是一个严格的审查员，擅长找漏洞和错误。",
        role="analyst",
        max_rounds=3,
        # 只读工具，禁止执行
        tools=["execute_python", "fetch_url", "search", "rag_search", "file", "git"],
        disallowed_tools=["execute_shell", "call_api", "skill_execute"],
    ),
}

# ── 官方内置子 Agent 类型配置 ─────────────────────────────
_OFFICIAL_BUILTIN_PROFILES: Dict[str, SubagentProfile] = {
    "general-purpose": SubagentProfile(
        name="general-purpose",
        description="通用 Agent，适合各种任务",
        personality="你是一个全能的助手，可以处理各种任务。",
        # 通用：禁用反思类工具（防止自我循环）
        disallowed_tools=["kepa_reflect", "self_reflect"],
    ),
    "Explore": SubagentProfile(
        name="Explore",
        description="探索 Agent，专门用于搜索和探索",
        personality="你是一个探索专家，擅长搜索、浏览和发现信息。",
        # 只读 + 搜索
        tools=["execute_python", "execute_shell", "fetch_url", "search", "rag_search", "file", "git", "call_api"],
    ),
    "Plan": SubagentProfile(
        name="Plan",
        description="计划 Agent，专门用于制定计划",
        personality="你是一个计划专家，擅长制定详细的执行计划。",
        # 计划模式：只读，禁止执行和写入
        tools=["execute_python", "fetch_url", "search", "rag_search", "file", "git"],
        disallowed_tools=["execute_shell", "call_api", "skill_execute"],
    ),
    "statusline-setup": SubagentProfile(
        name="statusline-setup",
        description="状态栏设置 Agent",
        personality="你是一个设置助手，负责配置状态栏。",
    ),
    "claude-code-guide": SubagentProfile(
        name="claude-code-guide",
        description="Claude Code 指南 Agent",
        personality="你是一个 Claude Code 专家，帮助用户了解和使用 Claude Code。",
    ),
}


class SubagentRegistry:
    """子 Agent 类型注册表 — 全局单例（完整官方兼容）"""

    _instance: Optional["SubagentRegistry"] = None

    def __new__(cls) -> "SubagentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._profiles: Dict[str, SubagentProfile] = {}
            cls._instance._initialized = False
        return cls._instance

    def _ensure(self) -> None:
        """懒加载内置类型：先加载官方，再加载 legacy"""
        if not self._initialized:
            self._profiles = dict(_OFFICIAL_BUILTIN_PROFILES)
            # 兼容旧名
            for name, profile in _LEGACY_BUILTIN_PROFILES.items():
                if name not in self._profiles:
                    self._profiles[name] = profile
            self._initialized = True

    def load_builtin_agents(self) -> None:
        """加载官方 5 个内置 Agent（已由 _ensure 加载，显式调用用于刷新）"""
        self._ensure()
        logger.info(f"SubagentRegistry: 内置 Agent 已加载，共 {len(self._profiles)} 个")

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
        """智能分派：先查官方名 → 再查 legacy 名 → 最后默认 general-purpose

        Args:
            name: agentType 字符串

        Returns:
            SubagentProfile，未注册时返回 general-purpose
        """
        self._ensure()
        profile = self._profiles.get(name)
        if profile is None:
            # 尝试忽略大小写匹配
            name_lower = name.lower()
            for key in self._profiles.keys():
                if key.lower() == name_lower:
                    return self._profiles[key]
            logger.debug(
                f"SubagentRegistry: 未找到类型 '{name}'，降级为 general-purpose"
            )
            return self._profiles["general-purpose"]
        return profile

    def load_from_directory(self, dir_path: str) -> int:
        """从目录加载所有 .md 文件作为 SubagentProfile

        Args:
            dir_path: 目录路径

        Returns:
            int: 加载的数量
        """
        self._ensure()
        count = 0
        if not os.path.isdir(dir_path):
            logger.warning(f"SubagentRegistry: 目录不存在: {dir_path}")
            return 0

        for filename in os.listdir(dir_path):
            if filename.endswith(".md"):
                filepath = os.path.join(dir_path, filename)
                try:
                    profile = SubagentProfile.from_markdown(filepath)
                    self.register(profile)
                    count += 1
                except Exception as e:
                    logger.warning(f"SubagentRegistry: 加载失败 {filepath}: {e}")

        logger.info(f"SubagentRegistry: 从 {dir_path} 加载了 {count} 个 Agent")
        return count

    def search(self, query: str) -> List[SubagentProfile]:
        """搜索匹配的 Agent（按名称或描述）

        Args:
            query: 搜索关键词

        Returns:
            List[SubagentProfile]: 匹配的 Profile 列表
        """
        self._ensure()
        query_lower = query.lower()
        results = []
        for profile in self._profiles.values():
            if (
                query_lower in profile.name.lower()
                or query_lower in profile.description.lower()
            ):
                results.append(profile)
        return results

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
