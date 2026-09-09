#!/usr/bin/env python3
"""SKILL 渐进披露工具 — 对齐 hermes-agent tools/skills_tool.py。

Progressive disclosure（渐进披露）核心：LLM 先看到「摘要」，需要时才加载「全文」。
  - skills_list: 只返回 name/description（摘要层，轻量，不占用大量 context）
  - skill_view:  按名加载全文（含 references/templates/scripts 等支持文件）

这避免 hermes 强调的「一股脑把几千字符 SKILL.md 塞进 system prompt」——
LLM 按需调 skill_view 取全文，其余只占极少 context。

本模块提供两个 handler（execute() 接口），注册到 ToolManager 供 LLM 调用。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_skill_source():
    """返回技能数据源：(SkillExtractor, GuidanceSkillRegistry)。尝试多种，容错降级。"""
    extractor = None
    registry = None
    try:
        from core.skill_extractor import get_skill_extractor
        extractor = get_skill_extractor()
    except Exception as e:
        logger.debug("SkillExtractor 不可用: %s", e)
    try:
        from core.skill_base import get_skill_registry
        registry = get_skill_registry()
    except Exception as e:
        logger.debug("SkillRegistry 不可用: %s", e)
    return extractor, registry


def _describe_skill(name: str) -> str:
    """取单个技能的摘要（name + description）。"""
    extractor, registry = _get_skill_source()

    # 1) GuidanceSkill（插件注册的专家人格，skill_md_path 驱动）
    if registry is not None:
        try:
            reg = registry
            # SkillRegistry 内部结构：_skills dict 或类似
            if hasattr(reg, "_skills"):
                skill = reg._skills.get(name)
                if skill is not None:
                    desc = getattr(skill, "description", "") or name
                    return f"{name}: {desc}"
        except Exception as e:
            logger.debug("registry lookup %s failed: %s", name, e)

    # 2) SkillExtractor（自我进化技能）
    if extractor is not None:
        try:
            all_sk = extractor.get_all_skills()
            for sk in all_sk:
                if getattr(sk, "name", "") == name:
                    try:
                        return extractor.format_skill_summary(sk)
                    except Exception:
                        return f"{name}: {getattr(sk, 'applicable_scenarios', [])}"
        except Exception as e:
            logger.debug("extractor lookup %s failed: %s", name, e)

    return name  # 兜底：只有名字


class SkillsListHandler:
    """skills_list —— 返回全部技能摘要（name/description，不加载全文）。"""

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        extractor, registry = _get_skill_source()
        lines = []

        # 1) GuidanceSkill 注册表
        if registry is not None and hasattr(registry, "_skills"):
            for name, skill in registry._skills.items():
                desc = getattr(skill, "description", "") or ""
                lines.append(f"- {name}: {desc[:120]}")

        # 2) SkillExtractor
        if extractor is not None:
            try:
                for sk in extractor.get_all_skills():
                    name = getattr(sk, "name", "")
                    if any(l.startswith(f"- {name}:") for l in lines):
                        continue  # 去重
                    scenes = getattr(sk, "applicable_scenarios", []) or []
                    lines.append(f"- {name}: {', '.join(scenes[:2]) if scenes else ''}")
            except Exception as e:
                logger.debug("extractor list failed: %s", e)

        if not lines:
            return {"success": True, "result": "（暂无可用技能）"}

        text = "\n".join(lines)
        print(f"    \033[35m◇ Skill: list → {len(lines)} 个摘要 (渐进披露第1层)\033[0m")
        return {"success": True, "result": f"## 可用技能\n{text}"}


class SkillsViewHandler:
    """skill_view —— 按名加载技能全文（渐进披露的第二步）。"""

    def execute(self, skill: str, **kwargs: Any) -> Dict[str, Any]:
        extractor, registry = _get_skill_source()

        # 1) GuidanceSkill（插件专家人格 / SKILL.md）
        if registry is not None and hasattr(registry, "_skills"):
            sk = registry._skills.get(skill)
            if sk is not None:
                content = ""
                if hasattr(sk, "load_content"):
                    try:
                        content = sk.load_content()
                    except Exception as e:
                        logger.debug("load_content failed %s: %s", skill, e)
                if not content:
                    content = getattr(sk, "description", "") or ""
                print(f"    \033[35m◇ Skill: view → '{skill}' 全文 {len(content)} 字 (渐进披露第2层)\033[0m")
                return {"success": True, "result": f"# {skill}\n\n{content[:8000]}"}

        # 2) SkillExtractor
        if extractor is not None:
            try:
                all_sk = extractor.get_all_skills()
                for sk in all_sk:
                    if getattr(sk, "name", "") == skill:
                        return {"success": True, "result": str(sk)}
            except Exception as e:
                logger.debug("extractor view failed %s: %s", skill, e)

        return {"success": False, "error": f"未找到技能: {skill}"}


def register_tools() -> int:
    """把 skills_list / skill_view 注册到 ToolManager（供 LLM 调用）。"""
    count = 0
    try:
        from tools.tool_manager import ToolManager
        tm = ToolManager.get_instance()

        tm.register_tool(
            name="skills_list",
            handler=SkillsListHandler(),
            description="列出所有可用技能的摘要（名称+描述）。用于浏览系统有哪些技能，不加载全文。",
            keywords=["技能", "技能列表", "skill list", "skills"], priority=9,
        )
        count += 1

        tm.register_tool(
            name="skill_view",
            handler=SkillsViewHandler(),
            description="按技能名查看某个技能/专家人格的完整内容。参数 skill=技能名。",
            keywords=["查看技能", "技能内容", "skill view", "专家人格"], priority=9,
        )
        count += 1
    except Exception as e:
        logger.warning("skills_list/skill_view 注册失败: %s", e)
    return count


if __name__ == "__main__":
    n = register_tools()
    print(f"注册了 {n} 个渐进披露工具")
    # 自测
    l = SkillsListHandler().execute()
    print("=== skills_list 输出(截断) ===")
    print(str(l.get("result", ""))[:400])
