"""Skill loader — discover and load SKILL.md files

ponytail: replicates OpenCode's skill system — scan known dirs, parse frontmatter,
return content on demand. Used by the `skill` tool and system prompt injection.
"""

import os
import re
import xml.sax.saxutils as xml_escape
from dataclasses import dataclass, field
from typing import Dict, List, Optional


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


def discover_skills(force_reload: bool = False) -> Dict[str, SkillInfo]:
    """Scan skill dirs for SKILL.md files. Results cached after first call."""
    global _singleton
    if _singleton is not None and not force_reload:
        return _singleton

    skills: Dict[str, SkillInfo] = {}
    for base_dir in SKILL_DIRS:
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