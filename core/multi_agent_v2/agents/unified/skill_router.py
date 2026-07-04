"""V1 Skill 路由 — 4层匹配：确定性 → SkillSystem → LLM → 回退"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class V1SkillRouter:
    """V1 版 skill 路由 — 输入 task，输出 skill_id

    增强功能：
    - 第1层: @skill 确定性路由
    - 第2层: SkillSystem 三层匹配
    - 第3层: LLM 意图分类兜底
    - 第4层: 回退到 general
    """

    def __init__(self):
        self._skill_system = None
        self._llm_router = None

    async def match(self, task: str) -> str:
        # 第1层: @skill 确定性路由
        at_match = re.match(r"@(\w+)\s", task)
        if at_match:
            skill_name = at_match.group(1)
            try:
                if self._skill_system is None:
                    from core.skills.base_skills import SkillSystem
                    self._skill_system = SkillSystem()
                await self._skill_system.match(task)
                known_skills = [s.id for s in self._skill_system.base_skills.values()] if hasattr(self._skill_system, 'base_skills') else []
                if skill_name in known_skills:
                    return skill_name
            except Exception:
                pass

        # 第2层: SkillSystem 三层匹配
        try:
            if self._skill_system is None:
                from core.skills.base_skills import SkillSystem
                self._skill_system = SkillSystem()
            result = await self._skill_system.match(task)
            if result.skill_id and result.skill_id != "general":
                return result.skill_id
        except Exception as e:
            logger.debug("V1SkillRouter.match 第2层失败: %s", e)

        # 第3层: LLM 意图分类兜底
        llm_skill = await self._llm_classify(task)
        if llm_skill:
            return llm_skill

        # 第4层: 回退到 general
        return "general"

    async def _llm_classify(self, task: str) -> Optional[str]:
        try:
            if self._llm_router is None:
                from core.engine.llm_backend import get_llm_router
                self._llm_router = get_llm_router()
            if not self._llm_router or not self._llm_router.is_available():
                return None
            system = ("你是一个技能路由器。从以下技能中选择最匹配的一个，只返回 JSON：\n"
                       "可用技能: project_analyzer, web_scraper, data_analyst, deep_thinker, translator, weather_expert, system_toolbox, creative, general\n"
                       '输出: {"skill": "技能名", "confidence": 0.0~1.0, "reason": "简短理由"}')
            resp = await self._llm_router.simple_chat(
                user_message=task, system_prompt=system,
                temperature=0.1, max_tokens=100,
            )
            if resp:
                text = resp.strip().strip("```json").strip("```").strip()
                parsed = json.loads(text)
                skill = parsed.get("skill", "")
                conf = float(parsed.get("confidence", 0.0))
                if skill and conf >= 0.6 and skill != "general":
                    return skill
        except Exception as e:
            logger.debug("V1SkillRouter LLM 分类失败: %s", e)
        return None
