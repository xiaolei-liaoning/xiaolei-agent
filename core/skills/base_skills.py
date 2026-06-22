"""三层 Skill 系统 — Base(8) + Expert(216) + Guidance

匹配流程:
  match("搜索百度热搜")
    → Layer 1: 从 8 个 BaseSkill 中选出 web_scraper
    → Layer 2: 在 web_scraper 相关类别中匹配 Expert Persona
    → Layer 3: 加载 SKILL.md 执行指南
    → 返回: {personality, tool_pref, guidance}
"""
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)
BASE_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "agents.yml")
EXPERT_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "core", "skills", "agency_agents", "agents_config.yaml")
AGENCY_AGENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "agency-agents-zh")


@dataclass
class SkillResult:
    """三层匹配结果"""
    skill_id: str = ""
    skill_name: str = ""
    personality: str = ""
    tool_preference: set = field(default_factory=set)
    expert_name: str = ""
    expert_personality: str = ""
    guidance: str = ""


@dataclass
class BaseSkill:
    id: str; name: str; role_prompt: str
    tools: List[str] = field(default_factory=list); priority: int = 1


# BaseSkill → 相关的 Expert 类别（缩小216个的匹配范围）
BASE_TO_EXPERT_CATEGORIES = {
    "project_analyzer": ["engineering", "specialized"],
    "web_scraper":    ["engineering", "specialized", "marketing"],
    "data_analyst":   ["engineering", "finance", "specialized", "supply_chain"],
    "deep_thinker":   ["specialized", "product_design", "engineering", "strategy"],
    "translator":     ["specialized", "support"],
    "weather_expert": ["specialized"],
    "system_toolbox": ["engineering", "support", "security"],
    "creative":       ["design", "game_development", "marketing", "paid_media"],
    "general":        [],
}

# YAML 分类名 → agency-agents-zh 目录名映射
CATEGORY_TO_DIR = {
    "engineering": "engineering",
    "marketing": "marketing",
    "product_design": "product",
    "design": "design",
    "finance": "finance",
    "sales": "sales",
    "game_development": "game-development",
    "academic": "academic",
    "spatial_computing": "spatial-computing",
    "specialized": "specialized",
    "project_management": "project-management",
    "hr": "hr",
    "legal": "legal",
    "support": "support",
    "supply_chain": "supply-chain",
    "paid_media": "paid-media",
    "testing": "testing",
    "security": "security",
    "strategy": "strategy",
}


class SkillSystem:
    def __init__(self):
        self.base_skills: Dict[str, BaseSkill] = {}
        self.experts: Dict[str, List[dict]] = {}       # category → [experts]
        self.guidance_skills: Dict[str, str] = {}       # skill_name → content
        self._load_base()
        self._load_experts()
        self._load_guidance()

    def _load_base(self):
        if not os.path.exists(BASE_CONFIG): return
        with open(BASE_CONFIG) as f:
            agents = yaml.safe_load(f).get("agents", {})
        for aid, ac in agents.items():
            self.base_skills[aid] = BaseSkill(
                id=aid, name=ac.get("name", aid),
                role_prompt=ac.get("role_prompt", ""),
                tools=ac.get("tools", []),
                priority=ac.get("priority", 1),
            )
        logger.info(f"✅ SkillSystem: {len(self.base_skills)} 个 BaseSkill")

    def _load_experts(self):
        if not os.path.exists(EXPERT_CONFIG): return
        with open(EXPERT_CONFIG) as f:
            cfg = yaml.safe_load(f)
        for cat, agents in cfg.items():
            if isinstance(agents, list):
                for a in agents:
                    a["category"] = cat
                self.experts[cat] = agents
        total = sum(len(v) for v in self.experts.values())
        logger.info(f"✅ SkillSystem: {total} 个 Expert Persona（{len(self.experts)} 类）")

    def _load_guidance(self):
        """读取 SKILL.md 作为执行指南"""
        try:
            from core.guidance_skills import scan_skills, SKILLS_BASE
            meta = scan_skills()
            for name, info in meta.items():
                md_path = info.get("path", "")
                if md_path and os.path.isfile(md_path):
                    with open(md_path, encoding="utf-8") as f:
                        self.guidance_skills[name] = f.read()
            logger.info(f"✅ SkillSystem: {len(self.guidance_skills)} 个 Guidance Skill")
        except Exception as e:
            logger.debug(f"加载 Guidance Skill 失败: {e}")

    async def match(self, task: str) -> SkillResult:
        """三层匹配"""
        result = SkillResult()

        # Layer 1: BaseSkill
        base = await self._match_base(task)
        if base:
            result.skill_id = base.id
            result.skill_name = base.name
            result.personality = base.role_prompt
            result.tool_preference = set(base.tools) if base.tools else set()

        # Layer 2: Expert Persona（缩小到相关类别）
        expert = await self._match_expert(task, base.id if base else "general")
        if expert:
            result.expert_name = expert.get("name", "")
            # 优先加载完整的 MD 角色定义，没有则用 YAML description
            md_content = self._load_expert_md(expert)
            if md_content:
                result.expert_personality = md_content
            else:
                result.expert_personality = f"你的专业方向是：{expert.get('description', '')[:300]}"

        # Layer 3: Guidance
        guide = self._match_guidance(base.id if base else "general")
        if guide:
            result.guidance = guide

        return result

    def _load_expert_md(self, expert: dict) -> Optional[str]:
        """从 agency-agents-zh 加载专家角色的完整 MD 定义

        Args:
            expert: 匹配到的专家角色 dict（含 id、category、name）

        Returns:
            MD 文件内容，如文件不存在则返回 None
        """
        expert_id = expert.get("id", "")
        category = expert.get("category", "")
        if not expert_id or not category or not os.path.isdir(AGENCY_AGENTS_DIR):
            return None

        # category → 目录名映射
        dir_name = CATEGORY_TO_DIR.get(category, category.replace("_", "-"))
        md_path = os.path.join(AGENCY_AGENTS_DIR, dir_name, f"{expert_id}.md")

        if not os.path.isfile(md_path):
            return None

        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                logger.debug(f"📄 加载 Expert MD: {expert_id} ({len(content)} 字符)")
                return content[:4000]  # ponytail: 截断防 prompt 溢出
        except Exception as e:
            logger.warning(f"加载 Expert MD 失败 {expert_id}: {e}")

        return None

    async def _match_base(self, task: str) -> Optional[BaseSkill]:
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if router and router.is_available():
            lines = [f"  {s.id}: {s.role_prompt}" + (f"  [{', '.join(s.tools[:3])}]" if s.tools else "") for s in self.base_skills.values()]
            prompt = f"任务：{task}\n\n选最匹配的 1 个角色：\n" + "\n".join(lines) + "\n\n只输出角色 ID："
            resp = (await router.simple_chat(prompt, temperature=0.2, max_tokens=30) or "").strip().lower()
            for sid in self.base_skills:
                if sid in resp:
                    return self.base_skills[sid]
        return self.base_skills.get("general")

    async def _match_expert(self, task: str, base_id: str) -> Optional[dict]:
        """jieba 分词预筛 + LLM 精排：任务分词后逐词匹配描述，取 Top-4 交 LLM"""
        cats = BASE_TO_EXPERT_CATEGORIES.get(base_id, [])
        # general 没有关联分类时回退到所有分类
        if not cats and base_id == "general":
            cats = list(self.experts.keys())
        candidates = []
        for cat in cats:
            candidates.extend(self.experts.get(cat, []))
        if not candidates:
            return None

        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if not router or not router.is_available():
            return None

        # ── 第 1 步：jieba 分词预筛 ──
        import jieba
        # 只用 jieba 分任务的词（短，0.2s 一次），不分析描述
        raw_tokens = jieba.lcut(task)
        # 过滤：中文词 2+字，英文词 3+字母，去重
        task_words = set()
        for w in raw_tokens:
            w = w.strip()
            if not w: continue
            if re.match(r'^[一-龥]{2,}$', w):
                task_words.add(w)
            elif re.match(r'^[a-zA-Z]{3,}$', w):
                task_words.add(w.lower())
        task_lower = task.lower()

        scored = []
        for a in candidates:
            score = 0.0
            desc = (a.get("description", "") or "")
            desc_lower = desc.lower()
            name = a.get("name", "")

            # a) 分词中文词 → 描述子串匹配（每个词 1 分）
            matched = set()
            for w in task_words:
                if w in desc:
                    matched.add(w)
                    score += 1.0
            # b) 任务词 → YAML keywords 补刀
            for kw in a.get("keywords", []):
                if len(kw) >= 2 and kw.lower() in task_lower and kw not in matched:
                    score += 0.5
            # c) 角色名在任务中出现 → 强信号
            if name and name.lower() in task_lower:
                score += 2.0

            if score > 0:
                # 归一化分数：命中词数 / 任务总词数
                norm = score / max(len(task_words), 1)
                scored.append((norm, score, a))

        if not scored:
            return None

        # 按归一化分降序取 Top-4
        scored.sort(key=lambda x: (-x[0], -x[1]))
        top = [a for _, _, a in scored[:4]]

        # Top-1 领先明显 → 直接采纳
        if len(scored) >= 2 and scored[0][0] - scored[1][0] >= 0.3:
            logger.debug(f"Expert 规则强势命中: {scored[0][2].get('name')} (norm={scored[0][0]:.2f})")
            return scored[0][2]

        # ── 第 2 步：LLM 精排 — 从 Top-4 里选最匹配的 ──
        lines = []
        for a in top:
            lines.append(f"  {a.get('emoji','👤')} {a.get('name','?')} — {(a.get('description','') or '')[:120]}")
        prompt = (
            f"任务：{task}\n\n"
            f"从以下专家中选最匹配的 1 个：\n"
            + "\n".join(lines) +
            "\n\n仔细阅读任务和每个专家的描述，只输出专家 ID："
        )
        resp = (await router.simple_chat(prompt, temperature=0.1, max_tokens=30) or "").strip().lower()
        for a in top:
            if a.get("id", "") in resp:
                logger.debug(f"Expert LLM 精排选中: {a.get('name')}")
                return a
        logger.debug(f"Expert LLM 精排无结果，降级为规则 Top-1: {scored[0][2].get('name')}")
        return scored[0][2] if scored else None

    def _match_guidance(self, base_id: str) -> str:
        """根据 BaseSkill ID 找对应的 Guidance"""
        # BaseSkill → Guidance skill 名称映射
        guide_map = {
            "web_scraper": ["deep-research", "data-scraper-agent"],
            "data_analyst": ["data-throughput-accelerator"],
            "deep_thinker": ["deep-research", "scientific-thinking-literature-review"],
            "translator": ["documentation-lookup"],
            "creative": ["content-engine", "article-writing"],
        }
        targets = guide_map.get(base_id, [])
        snippets = []
        for name in targets:
            content = self.guidance_skills.get(name, "")
            if content:
                snippets.append(content[:500])
        return "\n\n".join(snippets) if snippets else ""


_system = None


def get_skill_system() -> SkillSystem:
    global _system
    if _system is None:
        _system = SkillSystem()
    return _system
