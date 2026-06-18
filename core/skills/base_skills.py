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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)
BASE_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "agents.yml")
EXPERT_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "core", "skills", "agency_agents", "agents_config.yaml")


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
    "web_scraper":    ["engineering", "specialized"],
    "data_analyst":   ["engineering", "finance", "specialized"],
    "deep_thinker":   ["specialized", "product", "engineering"],
    "translator":     ["specialized"],
    "weather_expert": ["specialized"],
    "system_toolbox": ["engineering", "support"],
    "creative":       ["design", "game_development", "marketing"],
    "general":        [],
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
            result.expert_personality = f"你的专业方向是：{expert.get('description', '')[:300]}"

        # Layer 3: Guidance
        guide = self._match_guidance(base.id if base else "general")
        if guide:
            result.guidance = guide

        return result

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
        """只在 BaseSkill 相关的类别中匹配 Expert"""
        cats = BASE_TO_EXPERT_CATEGORIES.get(base_id, [])
        candidates = []
        for cat in cats:
            candidates.extend(self.experts.get(cat, []))
        if not candidates:
            return None

        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if not router or not router.is_available():
            return None

        # 候选太多时只取前 20 个
        if len(candidates) > 20:
            candidates = candidates[:20]

        lines = [f"  {a.get('id','?')}: {a.get('emoji','')} {a.get('name','')} — {a.get('description','')[:60]}" for a in candidates]
        prompt = f"任务：{task}\n\n从以下专家中选最匹配的 1 个：\n" + "\n".join(lines) + "\n\n只输出专家 ID："
        resp = (await router.simple_chat(prompt, temperature=0.2, max_tokens=30) or "").strip().lower()
        for a in candidates:
            if a.get("id", "") in resp:
                return a
        return None

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
