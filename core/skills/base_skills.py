"""三层 Skill 系统 — Base(8) + Expert(216) + Guidance

匹配流程:
  match("搜索百度热搜")
    → Layer 1: 从 8 个 BaseSkill 中选出 web_scraper
    → Layer 2: 在 web_scraper 相关类别中匹配 Expert Persona
    → Layer 3: 加载 SKILL.md 执行指南
    → 返回: {personality, tool_pref, guidance}
"""
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)
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
    "project_analyzer": ["engineering", "specialized", "backend", "fullstack", "system-architecture", "frontend", "database", "ai-ml", "generative-ai", "data-engineering", "devops-cloud", "security", "performance", "debugging-quality", "mobile", "context-engineering", "evaluation", "agent-workflows"],
    "web_scraper":    ["engineering", "specialized", "marketing", "backend"],
    "data_analyst":   ["engineering", "finance", "specialized", "supply_chain", "data-engineering", "evaluation", "database"],
    "deep_thinker":   ["specialized", "product_design", "engineering", "strategy", "system-architecture", "generative-ai", "ai-ml"],
    "translator":     ["specialized", "support"],
    "weather_expert": ["specialized"],
    "system_toolbox": ["engineering", "support", "security", "backend", "devops-cloud", "performance", "debugging-quality"],
    "creative":       ["design", "game_development", "marketing", "paid_media", "frontend", "fullstack"],
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
    # agent-dev-prompts categories
    "frontend": "frontend",
    "backend": "backend",
    "fullstack": "fullstack",
    "database": "database",
    "ai-ml": "ai-ml",
    "generative-ai": "generative-ai",
    "data-engineering": "data-engineering",
    "devops-cloud": "devops-cloud",
    "system-architecture": "system-architecture",
    "performance": "performance",
    "debugging-quality": "debugging-quality",
    "mobile": "mobile",
    "agent-workflows": "agent-workflows",
    "evaluation": "evaluation",
    "context-engineering": "context-engineering",
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
        # Primary: ~/.xiaolei/roles/*.md
        roles_dir = os.path.expanduser("~/.xiaolei/roles")
        loaded = set()
        if os.path.isdir(roles_dir):
            for fname in os.listdir(roles_dir):
                if not fname.endswith(".md"):
                    continue
                rid = fname[:-3]
                path = os.path.join(roles_dir, fname)
                try:
                    with open(path, encoding="utf-8") as f:
                        text = f.read()
                except Exception:
                    continue
                tools = []
                import re
                tm = re.search(r"^## tools_available\s*$(.+?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
                if tm:
                    tools = [m.group(1) for m in re.finditer(r"-\s*(\w+)", tm.group(1))]
                role_m = re.search(r"^#\s*role:\s*(.+)", text, re.MULTILINE)
                name = role_m.group(1).strip()[:80] if role_m else rid
                desc_m = re.search(r"^## description\s*$(.+?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
                self.base_skills[rid] = BaseSkill(
                    id=rid, name=name,
                    role_prompt=text,  # full .md as personality
                    tools=tools,
                    priority=5,        # .md files take priority
                )
                loaded.add(rid)
            logger.info(f"✅ SkillSystem: {len(loaded)} 个 BaseSkill (来自 ~/.xiaolei/roles/)")
        logger.info(f"✅ SkillSystem 总计: {len(self.base_skills)} 个 BaseSkill")

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
                # 可观测性④: 显示命中专家 + 完整 MD 加载成功
                print(f"    \033[36m🧠 Expert: 命中 '{expert.get('name','')}' ({expert.get('id','')}) 完整MD {len(md_content)}字\033[0m")
                result.expert_personality = md_content
            else:
                # 可观测性④: 显示命中专家但走了 description fallback（MD 缺失）
                print(f"    \033[36m🧠 Expert: 命中 '{expert.get('name','')}' ({expert.get('id','')}) 无完整MD→160字描述\033[0m")
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

        if not isinstance(md_path, str) or not os.path.isfile(md_path):
            return None

        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                logger.debug(f"📄 加载 Expert MD: {expert_id} ({len(content)} 字符)")
                return content[:16000]  # ponytail: 截断防 prompt 溢出（dev-prompts 最大 15K）
        except Exception as e:
            logger.warning(f"加载 Expert MD 失败 {expert_id}: {e}")

        return None

    async def _match_base(self, task: str) -> Optional[BaseSkill]:
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if router and router.is_available():
            lines = [f"  {s.id}: {s.name}" + (f"  [{', '.join(s.tools[:3])}]" if s.tools else "") for s in sorted(self.base_skills.values(), key=lambda x: -x.priority)]
            prompt = f"任务：{task}\n\n选最匹配的 1 个角色：\n" + "\n".join(lines) + "\n\n只输出角色 ID。如果不确定，选 general。"
            resp = (await router.simple_chat(prompt, temperature=0.2, max_tokens=64) or "").strip()
            # ponytail: DeepSeek 常把输出放 reasoning_content，提取 content+reasoning
            if resp.startswith("{"):
                try:
                    _parsed = json.loads(resp)
                    _msg = _parsed.get("choices", [{}])[0].get("message", {})
                    _c = (_msg.get("content") or "").strip()
                    _r = (_msg.get("reasoning_content") or "").strip()
                    resp = _c or _r or resp
                except (json.JSONDecodeError, IndexError, KeyError):
                    pass
            resp = resp.lower()
            # ponytail: 按 ID 长度降序匹配（"project_analyzer" 优先于 "analyze"）
            for sid in sorted(self.base_skills, key=lambda x: -len(x)):
                if sid in resp:
                    return self.base_skills[sid]
        return self.base_skills.get("general")

    async def _match_expert(self, task: str, base_id: str) -> Optional[dict]:
        """category 过滤 + LLM 全量选择"""
        cats = BASE_TO_EXPERT_CATEGORIES.get(base_id, [])
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
            return candidates[0]

        lines = []
        for a in candidates:
            desc = (a.get("description", "") or "")[:60]
            lines.append(f"  {a.get('id', '?')}: {a.get('name', '?')} — {desc}")
        prompt = (
            f"任务：{task}\n\n"
            f"从以下专家中选最匹配的 1 个：\n"
            + "\n".join(lines) +
            "\n\n仔细阅读任务和每个专家的描述，只输出专家 ID："
        )
        resp = (await router.simple_chat(prompt, temperature=0.1, max_tokens=30) or "").strip().lower()
        for a in candidates:
            if a.get("id", "") in resp:
                return a
        return candidates[0]

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
