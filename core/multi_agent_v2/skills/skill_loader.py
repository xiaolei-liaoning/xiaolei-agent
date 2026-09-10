"""Skill loader — discover and load SKILL.md files

ponytail: replicates OpenCode's skill system — scan known dirs, parse frontmatter,
return content on demand. Used by the `skill` tool and system prompt injection.
"""

import os
import re
import logging
import xml.sax.saxutils as xml_escape
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    name: str
    description: str
    location: str
    content: str


SKILL_DIRS = [
    os.path.expanduser("~/.opencode/skills"),
    os.path.expanduser("~/.agents/skills"),
    # ponytail: 部分 skill 目录是 symlink，同时搜索真实路径
    os.path.expanduser("~/.config/opencode/.opencode/skills"),
    os.path.expanduser("~/.config/opencode/.agents/skills"),
]

_singleton: Optional[Dict[str, SkillInfo]] = None


def discover_skills(force_reload: bool = False, pm_provided: Any = None) -> Dict[str, SkillInfo]:
    """Scan skill dirs for SKILL.md files. Results cached after first call.

    ponytail (用户定调): skill 可从三处挂载:
    1. 默认 SKILL_DIRS (内置 OpenCode path, 向后兼容)
    2. PluginManager.register_skill_provider 的注册目录 (user / builtin trust)
    合并去 dup。pm_provided 传值时用它, 否则用全局 singleton。
    """
    global _singleton
    if _singleton is not None and not force_reload:
        return _singleton

    skills: Dict[str, SkillInfo] = {}
    all_dirs = list(SKILL_DIRS)

    # PluginManager 侧 skill provider 目录 (user / builtin trust)
    # 传参注入 > 单例兜底 — 允许测试 / 明确调用方不走全局 singleton
    pms: List[Any] = []
    if pm_provided is not None:
        pms = [pm_provided]
    else:
        try:
            from core.plugin_registry import get_plugin_manager
            pms = [get_plugin_manager()]
        except Exception as e:
            logger.debug(f"PluginManager skill providers scan fail (skip): {e}")

    for pm in pms:
        try:
            pm.discover(force=True) if hasattr(pm, "_manifests") and not pm._manifests else None
            for sp in pm.get_skill_providers():
                path = str(sp.dir_path)
                if path not in all_dirs:
                    all_dirs.append(path)
        except Exception as e:
            logger.debug(f"PluginManager skill provider scan fail (skip): {e}")

    for base_dir in all_dirs:
        if not os.path.isdir(base_dir):
            continue
        for root, dirs, files in os.walk(base_dir, followlinks=True):
            for f in files:
                if f == "SKILL.md":
                    path = os.path.join(root, f)
                    skill = _parse_skill(path)
                    if skill:
                        skills[skill.name] = skill
    _singleton = skills
    return skills


def _parse_skill(path: str) -> Optional[SkillInfo]:
    try:
        with open(path) as fh:
            content = fh.read()
    except Exception:
        return None

    m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not m:
        return None

    frontmatter: Dict[str, str] = {}
    for line in m.group(1).strip().split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            frontmatter[k.strip()] = v.strip()

    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    if not name:
        return None

    body = content[m.end():].strip()
    return SkillInfo(name=name, description=description, location=path, content=body)


def format_skills_xml(skills: Dict[str, SkillInfo]) -> str:
    """OpenCode-style XML listing for system prompt."""
    if not skills:
        return ""
    lines = [
        "Skills provide specialized instructions and workflows for specific tasks.",
        "Use the skill tool to load a skill when a task matches its description.",
        "<available_skills>",
    ]
    for s in sorted(skills.values(), key=lambda x: x.name):
        lines.append(f"  <skill>")
        lines.append(f"    <name>{s.name}</name>")
        # 修复提示注入风险：将 description 中的 XML 特殊字符转义
        safe_desc = xml_escape.escape(str(s.description))
        lines.append(f"    <description>{safe_desc}</description>")
        lines.append(f"    <location>file://{s.location}</location>")
        lines.append(f"  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)