"""LLM关键词提取器 - 基于大语言模型的关键词提取"""

import json
import logging
from typing import List, Optional

from .base import KeywordInfo

logger = logging.getLogger(__name__)


class LlmExtractor:
    """基于LLM的关键词提取器"""

    def __init__(self, router=None):
        """
        Args:
            router: LLM路由器实例，如果为None则延迟初始化
        """
        self.router = router

    async def extract(self, text: str) -> List[KeywordInfo]:
        """基于LLM提取关键词

        Args:
            text: 文本

        Returns:
            关键词列表
        """
        # 延迟初始化router
        if self.router is None:
            from ..engine.llm_backend import get_llm_router
            self.router = get_llm_router()

        prompt = f"""请从以下文本中提取关键信息，包括：
1. 主要动作（用户想做什么）
2. 目标对象（针对什么）
3. 关键参数（时间、地点、数量等）
4. 重要实体（人名、地名、组织等）

文本：{text[:500]}

请以JSON格式返回（不要用代码块）：
{{
  "actions": ["动作1", "动作2"],
  "targets": ["目标1", "目标2"],
  "parameters": {{
    "time": ["时间1"],
    "location": ["地点1"],
    "quantity": ["数量1"]
  }},
  "entities": {{
    "persons": ["人名1"],
    "locations": ["地点1"],
    "organizations": ["组织1"]
  }}
}}

注意：
1. 只返回JSON，不要其他内容
2. 如果没有某类信息，返回空数组或空对象
3. 尽量简洁，每类最多3-5个"""

        try:
            response = await self.router.simple_chat(
                user_message=prompt,
                system_prompt="你是关键词提取助手，只返回JSON格式",
                temperature=0.3,
            )

            if not response or not response.strip():
                return []

            # 解析JSON
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

            data = json.loads(response)

            # 转换为KeywordInfo
            keywords = []

            # 处理动作
            for action in data.get("actions", []):
                keywords.append(KeywordInfo(
                    word=action,
                    score=0.9,
                    category="动作",
                    position=text.find(action)
                ))

            # 处理目标
            for target in data.get("targets", []):
                keywords.append(KeywordInfo(
                    word=target,
                    score=0.85,
                    category="对象",
                    position=text.find(target)
                ))

            # 处理参数
            params = data.get("parameters", {})
            for param_type, values in params.items():
                for value in values:
                    keywords.append(KeywordInfo(
                        word=value,
                        score=0.8,
                        category=param_type,
                        position=text.find(value)
                    ))

            # 处理实体
            entities_data = data.get("entities", {})
            for entity_type, values in entities_data.items():
                for value in values:
                    keywords.append(KeywordInfo(
                        word=value,
                        score=0.85,
                        category=entity_type,
                        position=text.find(value)
                    ))

            return keywords

        except Exception as e:
            logger.error("LLM关键词提取失败: %s", e)
            return []
