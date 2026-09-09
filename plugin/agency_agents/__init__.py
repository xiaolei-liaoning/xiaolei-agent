"""agency-agents 插件 — 把 agency-agents-zh 的专家人格插件化。

设计目标（参考 hermes-agent 的 SKILL 处理）：
  - hermes 把每个 skill 做成目录 + SKILL.md（frontmatter + body），通过
    `skills_list`/`skill_view` 渐进披露（先摘要后全文）。
  - 副本原逻辑（core/skills/base_skills.py）只靠 AGENCY_AGENTS_DIR 硬编码路径
    + agents_config.yaml，且只加载 16 个目录里能匹配到的专家（110 个），
    其余 18 类（design/marketing/specialized 等，约 100+）因目录不存在/文件缺失
    只能退化成 description[:300] fallback。
  - 本插件的价值：把 agency-agents-zh 全量专家（含缺失那 18 类的 YAML description）
    统一注册为 GuidanceSkill（SKILL.md 驱动的指导型技能），补齐 base_skills 漏掉的，
    并用"渐进披露"（先 name/description、按需 load_content()）减少 prompt 占用。

用法：PluginLoader.discover_sub_plugins() 自动发现本插件，
  __init__.register() 将全部专家注册到 skill registry。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENCY_AGENTS_DIR = PROJECT_ROOT / "agency-agents-zh"
EXPERT_CONFIG = PROJECT_ROOT / "core" / "skills" / "agency_agents" / "agents_config.yaml"

# 磁盘上真实存在的专家目录（agent-dev-prompts 风格，含完整 MD）。
# 其余 18 类（design/marketing/...）文件缺失，用 agents_config.yaml description 兜底。
_AGENT_DEV_DIRS = {
    "agent-workflows", "ai-ml", "backend", "context-engineering", "data-engineering",
    "database", "debugging-quality", "devops-cloud", "evaluation", "frontend",
    "fullstack", "generative-ai", "mobile", "performance", "security", "system-architecture",
}


def _slug_id(fname: str) -> str:
    """'{category}-{name}.md' -> '{category}-{name}'（专家 id = 文件名去 .md）。"""
    return fname[:-3] if fname.endswith(".md") else fname


def _scan_disk_experts() -> List[Dict[str, str]]:
    """扫 agency-agents-zh/{dir}/*.md，返回 {id, path, category, name}。"""
    out = []
    if not AGENCY_AGENTS_DIR.is_dir():
        return out
    for sub in sorted(AGENCY_AGENTS_DIR.iterdir()):
        if not sub.is_dir() or sub.name.startswith("_") or sub.name.startswith("."):
            continue
        cat = sub.name
        for md in sorted(sub.glob("*.md")):
            eid = _slug_id(md.name)
            out.append({
                "id": eid,
                "path": str(md),
                "category": cat,
                "name": eid.split("-", 1)[-1] if "-" in eid else eid,
            })
    return out


def _load_yaml_experts() -> Dict[str, Dict[str, str]]:
    """读 agents_config.yaml，返回 {id: {description, category, name}}（补磁盘缺失的 18 类）。"""
    out: Dict[str, Dict[str, str]] = {}
    if not EXPERT_CONFIG.is_file():
        return out
    try:
        with open(EXPERT_CONFIG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        for cat, agents in cfg.items():
            if not isinstance(agents, list):
                continue
            for a in agents:
                eid = str(a.get("id", ""))
                if eid:
                    out[eid] = {
                        "description": str(a.get("description", ""))[:500],
                        "category": cat,
                        "name": str(a.get("name", eid)),
                    }
    except Exception as e:  # noqa: BLE001
        logger.warning("agents_config.yaml 读取失败: %s", e)
    return out


def register() -> int:
    """把 agency-agents-zh 全量专家注册为 GuidanceSkill，返回注册数。"""
    from core.skill_base import GuidanceSkill, ToolRegistry, get_skill_registry

    disk = _scan_disk_experts()
    yaml_cfg = _load_yaml_experts()
    registered = 0

    # 1) 磁盘上的完整 MD 专家 → 标准 GuidanceSkill（SKILL.md 驱动）
    for e in disk:
        try:
            skill = GuidanceSkill(
                name=e["id"],
                description=f"专家: {e['name']} ({e['category']}) — 领域专家人格",
                skill_md_path=e["path"],
                keywords=[e["name"], e["id"], e["category"]],
                priority=7,
            )
            skill.load_content()
            ToolRegistry.register(skill, keywords=skill.keywords)
            get_skill_registry().register(skill)
            registered += 1
        except Exception as ex:  # noqa: BLE001
            logger.debug("专家 MD 注册失败 %s: %s", e["id"], ex)

    # 2) YAML 有但磁盘缺失的专家 → description 兜底 GuidanceSkill
    disk_ids = {e["id"] for e in disk}
    for eid, info in yaml_cfg.items():
        if eid in disk_ids:
            continue
        try:
            skill = GuidanceSkill(
                name=eid,
                description=f"专家: {info['name']} ({info['category']})",
                skill_md_path="",  # 无 MD，内容用 description
                keywords=[info["name"], eid, info["category"]],
                priority=6,
            )
            skill._content = f"# {info['name']}\n\n你是一名{info['category']}领域专家。\n\n{info['description']}"
            ToolRegistry.register(skill, keywords=skill.keywords)
            get_skill_registry().register(skill)
            registered += 1
        except Exception as ex:  # noqa: BLE001
            logger.debug("YAML 专家注册失败 %s: %s", eid, ex)

    logger.info("✅ agency-agents 插件注册 %d 个专家人格", registered)
    return registered


if __name__ == "__main__":
    n = register()
    print(f"注册了 {n} 个专家人格")
