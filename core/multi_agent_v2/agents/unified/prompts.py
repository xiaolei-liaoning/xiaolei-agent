"""V1 提示词模板 + LLM 工具函数"""

import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_llm_semaphore = asyncio.Semaphore(3)


def get_llm_router_safe():
    """懒加载 LLM router，避免模块级导入触发 LLM 后端初始化"""
    from core.engine.llm_backend import get_llm_router
    return get_llm_router()


async def llm_json(system_prompt: str, user_message: str, max_tokens: int = 800) -> dict:
    """调用 LLM 并返回解析后的 JSON（含 1 次重试 + 提取兜底）"""
    last_error = None
    for attempt in range(2):
        try:
            router = get_llm_router_safe()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            async with _llm_semaphore:
                response = await router.chat(messages, temperature=0.7, max_tokens=max_tokens)
            cleaned = (response or "").strip().strip("```json").strip("```").strip()
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_error = str(e)
            if attempt == 0:
                logger.warning(f"LLM JSON 解析失败，重试中: {e}")
                user_message += f"\n\n（注意：上次返回的 JSON 格式无效，错误: {e}。请确保只输出有效 JSON。）"
            else:
                logger.warning(f"LLM JSON 解析重试仍失败: {e}")
        except Exception as e:
            logger.warning(f"LLM 调用/解析失败: {e}/{e.__class__.__name__}")
            last_error = str(e)
            if attempt == 0:
                user_message += f"\n\n（注意：上次 LLM 调用失败: {e}。请重试。）"
                continue
    try:
        router = get_llm_router_safe()
        extract_prompt = f"从以下文本中提取 JSON 对象并返回（仅返回 JSON）：\n\n{user_message}"
        messages = [
            {"role": "system", "content": "你是一个 JSON 提取器，只输出 JSON 格式。"},
            {"role": "user", "content": extract_prompt},
        ]
        async with _llm_semaphore:
            response = await router.chat(messages, temperature=0.3, max_tokens=max_tokens)
        cleaned = (response or "").strip().strip("```json").strip("```").strip()
        return json.loads(cleaned)
    except Exception:
        pass
    logger.warning(f"LLM JSON 解析最终失败: {last_error}")
    return {}


SYSTEM_PROMPT_TEMPLATE = """你是一个{role}Agent。你的职责是{description}。

先思考再行动：
1. 任务目标是什么？当前进度在哪里？
2. 需要工具就调用，有数据就回答，信息不够继续追问
3. 不要输出思考过程描述，直接行动

关键规则：
- 如果任务明确且有数据，直接执行，不要描述"我将..."
- 创建文件/报告 → 用 write_file 工具写入（如 ~/Desktop/文件名）
- 分析任务 → 先读取文件/搜索获取数据，再返回完整分析结果
- 修改代码 → 用 edit_file（精确字符串替换）
- 禁止输出被截断/不完整的内容

{extra_context}

{file_tip}

输出格式：
返回 JSON 格式结果（可直接用工具完成的任务在 result 字段返回实际内容）
{output_format}"""

OUTPUT_FORMATS = {
    "decompose": """{"task": "原始任务","subtasks": [...],"estimated_steps": 数字,"strategy": "策略"}""",
    "execute": """{"status": "success/failed","result": "执行结果","details": {...}}""",
    "research": """{"topic": "主题","findings": [...],"summary": "总结"}""",
    "analyze": """{"analysis_type": "类型","key_insights": [...],"recommendations": [...],"confidence": 0-1}""",
    "review": """{"review_score": 0-100,"passed": true/false,"comments": "意见","suggestions": [...]}""",
    "reflect": """{"analysis": "原因","suggestion": "改进","should_retry": true/false}""",
    "kepa_decision": """{"decision": "continue/retry/fail","confidence": 0-1,"reason": "原因"}""",
    "leader_analyze": """{"decision": "complete/retry/reassign","confidence": 0-1,"reason": "原因","retry_tasks": [...],"needed_count": 数字}""",
}
