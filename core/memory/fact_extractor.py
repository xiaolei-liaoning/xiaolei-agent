# core/memory/fact_extractor.py
"""事实提取器 — 从对话中自动提取用户事实/偏好"""

import asyncio
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """分析以下对话，提取关于用户的事实和偏好。

规则：
1. 只提取关于用户本人的信息（姓名、职业、地点、偏好、习惯等）
2. 跳过任务进度、一次性指令请求
3. 「我喜欢/我不喜欢/我偏好/我习惯」等表达喜好的语句必须提取，即使包含"现在""今天"等时间词
4. 中文"和""、""与"分隔的并列列表项，每项提取为独立的偏好/事实

输出 JSON 数组，每项格式：
{{"type": "fact|preference|name", "content": "简洁的陈述句", "confidence": 0.0-1.0}}

示例：
用户: 我叫小雷，是个程序员
[{{"type": "name", "content": "用户姓名是小雷", "confidence": 0.95}}, {{"type": "fact", "content": "用户是程序员", "confidence": 0.9}}]

用户: 今天天气怎么样
[]

用户: 我喜欢用 VS Code
[{{"type": "preference", "content": "用户偏好使用 VS Code 编辑器", "confidence": 0.9}}]

用户: 我现在喜欢吃苹果、香蕉和梨
[{{"type": "preference", "content": "用户喜欢吃苹果", "confidence": 0.9}}, {{"type": "preference", "content": "用户喜欢吃香蕉", "confidence": 0.9}}, {{"type": "preference", "content": "用户喜欢吃梨", "confidence": 0.9}}]

用户: 帮我查一下北京到上海的高铁
[]

---

对话历史:
{conversation}

最新消息:
{message}

只输出 JSON 数组，不要其他内容。"""


class FactExtractor:
    """从对话中提取用户事实"""

    def __init__(self):
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            try:
                from core.engine.llm_backend import get_llm_router
                self._llm = get_llm_router()
            except Exception:
                return None
        return self._llm

    async def extract(
        self,
        message: str,
        conversation_history: str = "",
    ) -> List[Dict]:
        if not self.llm:
            return []

        prompt = EXTRACTION_PROMPT.format(
            conversation=conversation_history or "(无历史对话)",
            message=message,
        )

        try:
            resp = await asyncio.wait_for(
                self.llm.simple_chat(
                    user_message=prompt,
                    system_prompt="你是一个精准的信息提取器。只输出 JSON。",
                    temperature=0.1,
                ),
                timeout=10,
            )
            if not resp:
                return []

            text = resp.strip() if isinstance(resp, str) else str(resp).strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [item for item in parsed if item.get("confidence", 0) >= 0.6]
            return []
        except asyncio.TimeoutError:
            logger.debug("事实提取: LLM 超时")
        except json.JSONDecodeError:
            logger.debug("事实提取: LLM 返回非 JSON")
        except Exception as e:
            logger.debug("事实提取失败: %s", e)
        return []


_extractor: Optional[FactExtractor] = None


def get_fact_extractor() -> FactExtractor:
    global _extractor
    if _extractor is None:
        _extractor = FactExtractor()
    return _extractor
