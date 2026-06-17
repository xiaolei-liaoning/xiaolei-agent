"""Base Skill 系统 — 从 config/agents.yml 加载 8 个内置角色"""
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "agents.yml",
)


@dataclass
class BaseSkill:
    id: str
    name: str
    role_prompt: str
    tools: List[str] = field(default_factory=list)
    priority: int = 1


class BaseSkillMatcher:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or CONFIG_PATH
        self.skills: Dict[str, BaseSkill] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.config_path):
            return
        with open(self.config_path) as f:
            agents = yaml.safe_load(f).get("agents", {})
        for aid, ac in agents.items():
            self.skills[aid] = BaseSkill(
                id=aid,
                name=ac.get("name", aid),
                role_prompt=ac.get("role_prompt", ""),
                tools=ac.get("tools", []),
                priority=ac.get("priority", 1),
            )

    async def match(self, task: str) -> BaseSkill:
        try:
            r = await self._llm_match(task)
            if r:
                return r
        except Exception:
            pass
        try:
            r = self._keyword_fallback(task)
            if r:
                return r
        except Exception:
            pass
        return self.skills.get("general") or BaseSkill(
            id="general", name="通用助手", role_prompt="你是一个通用助手", tools=["chat"]
        )

    async def _llm_match(self, task: str) -> Optional[BaseSkill]:
        from core.engine.llm_backend import get_llm_router

        router = get_llm_router()
        if not router or not router.is_available():
            return None
        lines = [f"  {s.id}: {s.role_prompt}" for s in self.skills.values()]
        prompt = (
            f"任务：{task}\n选最匹配的1个角色:\n"
            + "\n".join(lines)
            + "\n只输出角色ID:"
        )
        resp = (
            await router.simple_chat(prompt, temperature=0.2, max_tokens=30) or ""
        ).strip().lower()
        for sid in self.skills:
            if sid in resp:
                return self.skills[sid]
        return None

    def _keyword_fallback(self, task: str) -> Optional[BaseSkill]:
        maps = {
            "web_scraper": ["搜索", "热搜", "爬取", "抓取", "爬虫", "scraper", "crawl", "search"],
            "data_analyst": ["分析", "数据", "统计", "可视化", "报表", "图表"],
            "deep_thinker": ["为什么", "分析", "深度", "复杂", "思考", "推理"],
            "translator": ["翻译", "英文", "中文", "日语", "韩语", "法语"],
            "weather_expert": ["天气", "温度", "下雨", "台风", "气温"],
            "system_toolbox": ["系统", "命令", "终端", "shell", "进程"],
            "creative": ["创意", "写故事", "写诗", "小说", "创作"],
        }
        for s in sorted(self.skills.values(), key=lambda x: x.priority, reverse=True):
            if any(kw in task for kw in maps.get(s.id, [])):
                return s
        return None


_matcher = None


def get_base_skill_matcher():
    global _matcher
    if _matcher is None:
        _matcher = BaseSkillMatcher()
    return _matcher
