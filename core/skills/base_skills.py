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
        # LLM 不可用或匹配失败时，兜底返回 general
        return self.skills.get("general") or BaseSkill(
            id="general", name="通用助手", role_prompt="你是一个通用助手", tools=["chat"]
        )

    async def _llm_match(self, task: str) -> Optional[BaseSkill]:
        from core.engine.llm_backend import get_llm_router

        router = get_llm_router()
        if not router or not router.is_available():
            return None
        lines = []
        for s in self.skills.values():
            tools_str = f"  [{', '.join(s.tools[:5])}]" if s.tools else ""
            lines.append(f"  {s.id}: {s.role_prompt}{tools_str}")
        prompt = (
            f"任务：{task}\n\n"
            f"从以下角色中选出最匹配该任务的 1 个。\n"
            f"考虑角色的描述和可用工具是否适合该任务。\n\n"
            + "\n".join(lines)
            + "\n\n只输出角色 ID，不要其他文字："
        )
        resp = (
            await router.simple_chat(prompt, temperature=0.2, max_tokens=30) or ""
        ).strip().lower()
        for sid in self.skills:
            if sid in resp:
                return self.skills[sid]
        return None


_matcher = None


def get_base_skill_matcher():
    global _matcher
    if _matcher is None:
        _matcher = BaseSkillMatcher()
    return _matcher
