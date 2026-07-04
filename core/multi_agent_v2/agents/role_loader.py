"""角色定义加载器 — 从 ~/.xiaolei/roles/*.md 加载角色定义

角色 .md 文件格式：
  # role: <id>
  ## description
  ...
  ## phase_dag
  phase1: <name> — <desc>
  ...
  ## tools_available
  - tool_name: 描述
  ## behavior_rules
  ...
  ## output_spec
  ...
"""
import os
import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
from dataclasses import dataclass

ROLES_DIR = os.path.expanduser("~/.xiaolei/roles")


@dataclass
class RoleDef:
    id: str
    description: str
    phases: List[Dict[str, str]]  # [{"id":"scan","desc":"..."}, ...]
    tools: List[str]  # tool names
    rules: str
    output_spec: str
    raw: str  # full .md text


_cache: Dict[str, RoleDef] = {}
_cache_loaded = False


def _parse_role_md(text: str, role_id: str) -> RoleDef:
    desc = _extract_section(text, "description")
    dag = _extract_section(text, "phase_dag")
    tools = _extract_section(text, "tools_available")
    rules = _extract_section(text, "behavior_rules")
    out = _extract_section(text, "output_spec")

    phases = []
    if dag:
        for line in dag.split("\n"):
            m = re.match(r"phase\d+:\s*(\S+)\s*—\s*(.+)", line.strip())
            if m:
                phases.append({"id": m.group(1), "desc": m.group(2)})

    tool_names = []
    if tools:
        for line in tools.split("\n"):
            m = re.match(r"-\s*(\w+)", line.strip())
            if m:
                tool_names.append(m.group(1))

    return RoleDef(
        id=role_id,
        description=desc.strip() if desc else "",
        phases=phases,
        tools=tool_names,
        rules=rules.strip() if rules else "",
        output_spec=out.strip() if out else "",
        raw=text,
    )


def _extract_section(text: str, heading: str) -> str:
    m = re.search(
        rf"^##\s*{re.escape(heading)}\s*$(.+?)(?=^##\s|\Z)",
        text, re.MULTILINE | re.DOTALL
    )
    if m:
        return m.group(1).strip()
    return ""


def load_all() -> Dict[str, RoleDef]:
    global _cache, _cache_loaded
    if _cache_loaded:
        return _cache
    _cache = {}
    if not os.path.isdir(ROLES_DIR):
        logger.warning(f"roles dir not found: {ROLES_DIR}")
        _cache_loaded = True
        return _cache
    for fname in os.listdir(ROLES_DIR):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(ROLES_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            logger.warning(f"failed to read role {fname}: {e}")
            continue
        role_id = fname[:-3]
        _cache[role_id] = _parse_role_md(text, role_id)
        logger.info(f"loaded role: {role_id} ({len(text)} chars)")
    _cache_loaded = True
    return _cache


def get(role_id: str) -> Optional[RoleDef]:
    roles = load_all()
    return roles.get(role_id)


def build_personality(role_id: str) -> str:
    """从角色定义构建 personality_prompt 字符串"""
    role = get(role_id)
    if not role:
        return ""
    parts = [f"<role:{role_id}>"]
    if role.description:
        parts.append(role.description)
    if role.rules:
        parts.append(f"规则：\n{role.rules}")
    if role.output_spec:
        parts.append(f"输出规范：\n{role.output_spec}")
    parts.append(f"</role:{role_id}>")
    return "\n\n".join(parts)
