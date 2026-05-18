"""指导型 Skill 加载器 — 将 everything-claude-code 的 SKILL.md 嵌入 agent

读取 ~/Desktop/claude/everything-claude-code-main/.agents/skills/
下的所有 SKILL.md，自动生成 GuidanceSkill 并注册到全局 SkillRegistry。
"""

import os
import re
import logging
from typing import Dict, Optional

from .skill_base import GuidanceSkill, get_skill_registry

logger = logging.getLogger(__name__)

# everything-claude-code 技能仓库路径
SKILLS_BASE = os.path.expanduser(
    "~/Desktop/claude/everything-claude-code-main/.agents/skills"
)

# Skill 分类映射（用于生成关键词）
SKILL_CATEGORIES = {
    "product": {"product-capability", "market-research", "strategic-compact"},
    "frontend": {"frontend-patterns", "frontend-slides", "nextjs-turbopack"},
    "backend": {"backend-patterns", "api-design", "mcp-server-patterns", "bun-runtime"},
    "content": {"article-writing", "content-engine", "crosspost", "brand-voice"},
    "media": {"video-editing", "fal-ai-media"},
    "ai": {"deep-research", "exa-search", "documentation-lookup", "e2e-testing",
           "eval-harness", "everything-claude-code"},
    "devops": {"tdd-workflow", "verification-loop", "coding-standards", "agent-sort"},
    "investor": {"investor-materials", "investor-outreach"},
    "security": {"security-review"},
    "api-platform": {"x-api", "agent-introspection-debugging", "dmux-workflows"},
}

# 系统级 Skill（保留在 Claude Code 原生中，不嵌入 agent）
SYSTEM_SKILLS = {
    "update-config", "keybindings-help", "simplify",
    "fewer-permission-prompts", "loop", "init", "review",
    "security-review", "GenericAgent",
}

# 手动维护的中文关键词（自动生成不够好时补充）
MANUAL_KEYWORDS: Dict[str, list] = {
    "product-capability": ["产品能力", "产品分析", "PRD", "产品需求", "capability"],
    "market-research": ["市场研究", "竞品分析", "行业分析", "market research"],
    "strategic-compact": ["战略文档", "上下文压缩", "strategic compact"],
    "frontend-patterns": ["前端", "React", "组件", "UI", "frontend"],
    "api-design": ["API设计", "REST", "接口规范", "api design"],
    "article-writing": ["文章", "写作", "博客", "内容创作", "article"],
    "deep-research": ["深度研究", "调研", "研究报告", "deep research"],
    "e2e-testing": ["端到端测试", "E2E", "Playwright", "自动化测试"],
    "tdd-workflow": ["TDD", "测试驱动", "单元测试", "test driven"],
    "security-review": ["安全审查", "安全审计", "security review"],
    "video-editing": ["视频编辑", "视频剪辑", "video editing"],
    "content-engine": ["内容引擎", "内容系统", "content engine"],
    "brand-voice": ["品牌语调", "写作风格", "brand voice"],
    "coding-standards": ["编码规范", "代码规范", "coding standards"],
}


def scan_skills() -> Dict[str, dict]:
    """扫描 everything-claude-code 目录，返回 {name: metadata}"""
    if not os.path.isdir(SKILLS_BASE):
        logger.warning(f"everything-claude-code 目录不存在: {SKILLS_BASE}")
        return {}

    skills = {}
    for name in sorted(os.listdir(SKILLS_BASE)):
        if name.startswith("."):
            continue
        if name in SYSTEM_SKILLS:
            continue

        skill_dir = os.path.join(SKILLS_BASE, name)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue

        # 从 frontmatter 提取元数据
        description = ""
        try:
            with open(skill_md, 'r', encoding='utf-8') as f:
                content = f.read()
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    for line in parts[1].strip().split("\n"):
                        if ":" in line:
                            key, _, val = line.partition(":")
                            if key.strip() == "description":
                                description = val.strip().strip('"')
        except Exception:
            pass

        # 确定分类
        category = "uncategorized"
        for cat, skill_names in SKILL_CATEGORIES.items():
            if name in skill_names:
                category = cat
                break

        skills[name] = {
            "name": name,
            "description": description or name,
            "category": category,
            "path": skill_md,
        }

    return skills


def build_keywords(name: str, description: str) -> list:
    """为技能生成关键词列表"""
    # 优先使用手动维护的关键词
    if name in MANUAL_KEYWORDS:
        return MANUAL_KEYWORDS[name]

    # 自动从 description 提取
    words = set()

    # 英文关键词：从 name 提取
    words.add(name.lower())
    words.add(name.replace("-", " "))
    parts = name.split("-")
    if len(parts) > 1:
        words.add(parts[0])
        words.add(" ".join(parts))

    # 英文关键词：从 description 提取常见单词
    desc_en = re.findall(r'[a-zA-Z]{3,}', description)
    for w in desc_en[:5]:
        words.add(w.lower())

    # 中文关键词：从 description 提取
    desc_cn = re.findall(r'[一-鿿]{2,10}', description)
    for w in desc_cn[:3]:
        words.add(w)

    # 标准 mapping
    category_keywords = {
        "product": ["产品"],
        "frontend": ["前端", "UI"],
        "backend": ["后端", "API"],
        "content": ["内容", "写作"],
        "media": ["媒体", "视频"],
        "ai": ["AI", "搜索", "研究"],
        "devops": ["开发", "测试"],
        "investor": ["投资", "融资"],
        "api-platform": ["API", "平台"],
        "security": ["安全"],
    }

    # 找分类关键词
    for cat, cat_names in SKILL_CATEGORIES.items():
        if name in cat_names:
            words.update(category_keywords.get(cat, []))
            break

    return list(words)


def load_guidance_skills() -> int:
    """加载所有指导型技能到全局 SkillRegistry

    Returns:
        加载的技能数量
    """
    skills = scan_skills()
    if not skills:
        logger.warning("没有发现指导型技能（检查 everything-claude-code 路径）")
        return 0

    registry = get_skill_registry()
    count = 0

    for name, meta in skills.items():
        try:
            keywords = build_keywords(name, meta["description"])
            skill = GuidanceSkill(
                name=name,
                description=meta["description"],
                skill_md_path=meta["path"],
                keywords=keywords,
                priority=3,
            )
            # 预加载内容
            skill.load_content()
            registry.register(skill)
            count += 1
        except Exception as e:
            logger.error(f"加载指导技能 {name} 失败: {e}")

    logger.info(f"✅ 已嵌入 {count}/{len(skills)} 个指导型技能到 agent")
    return count


# 便捷方法：按分类查询
def get_skills_by_category(category: str) -> list:
    """获取指定分类的所有指导技能

    Args:
        category: 分类名（product/frontend/backend/content/media/ai/devops/investor/api-platform）

    Returns:
        GuidanceSkill 实例列表
    """
    registry = get_skill_registry()
    cat_skills = SKILL_CATEGORIES.get(category, set())
    return [s for s in registry.all() if hasattr(s, 'name') and s.name in cat_skills]


def list_guidance_skills() -> str:
    """格式化输出所有指导型技能"""
    registry = get_skill_registry()
    guidance_skills = [s for s in registry.all()
                       if hasattr(s, 'skill_md_path')]

    if not guidance_skills:
        return "（未加载指导型技能）"

    lines = [f"📖 已嵌入的指导型技能 ({len(guidance_skills)} 个)\n"]

    # 按分类分组
    by_cat: Dict[str, list] = {}
    for s in guidance_skills:
        cat = "uncategorized"
        for c, names in SKILL_CATEGORIES.items():
            if s.name in names:
                cat = c
                break
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(s)

    for cat, skills in sorted(by_cat.items()):
        lines.append(f"\n## {cat}")
        for s in skills:
            lines.append(f"  • {s.name} — {s.description[:60]}")

    return "\n".join(lines)
