"""单步任务处理器 — 认知闭环入口

由 CognitivePipeline 编排 反问/反思/上下文/Agent集群 的全链路。
对外暴露 handle_single_step 接口不变，内部逻辑委托给管道。
"""

import re
import logging
from typing import Dict, Any

from .cognitive_pipeline import CognitivePipeline

logger = logging.getLogger(__name__)

# 需要多Agent协同的复杂技能
_COMPLEX_SKILLS = {"deep_thinking", "multi_step", "text_analyzer", "batch_operations"}


async def handle_single_step(
    message: str,
    user_id: int,
    skill_name: str,
    agent_id: str,
    dispatcher,
    db_initialized: bool = False
) -> Dict[str, Any]:
    """处理单步任务（工具调用或闲聊）。

    通过 CognitivePipeline 走完整的认知闭环：
        上下文增强 → 反问检测 → 执行 → 反思 → (重试/升级Agent集群/反问)

    Args:
        message: 用户消息
        user_id: 用户ID
        skill_name: 匹配的技能名
        agent_id: Agent ID
        dispatcher: SkillDispatcher 实例
        db_initialized: 数据库是否已初始化

    Returns:
        包含 reply / tool_call / success / clarification 的字典
    """
    try:
        return await _handle_single_step_inner(message, user_id, skill_name, agent_id, dispatcher, db_initialized)
    except Exception as exc:
        try:
            from core.security.error_handler import AppException, ErrorResponse
            if isinstance(exc, AppException):
                logger.warning("AppException: [%s] %s", exc.code, exc.message)
                return ErrorResponse.from_exception(exc).to_dict()
        except ImportError:
            pass
        raise


async def _handle_single_step_inner(
    message: str,
    user_id: int,
    skill_name: str,
    agent_id: str,
    dispatcher,
    db_initialized: bool = False
) -> Dict[str, Any]:
    """单步任务处理内部逻辑"""
    # MCP 建议 / 纯闲聊 不走闭环
    if skill_name == "mcp_suggestion":
        from .single_step_handler_utils import _handle_mcp_suggestion
        return await _handle_mcp_suggestion(message)

    if skill_name == "chat":
        from .chat_handler import handle_chat
        return await handle_chat(message, user_id, agent_id, db_initialized)

    # ── 认知闭环（反问 + 执行 + 反思 + 升级） ──
    from ..context import ExecutionContext
    ctx = ExecutionContext.create_default()
    pipe = CognitivePipeline(user_id=str(user_id), context=ctx)
    result = await pipe.run(
        message=message,
        skill_name=skill_name,
        dispatcher=dispatcher,
        db_initialized=db_initialized,
    )

    # 如果管道返回了反问或结果，直接返回
    if result.get("requires_clarification") or result.get("success"):
        return result

    # ── 多Agent桥接（复杂任务直接调度） ──
    if skill_name in _COMPLEX_SKILLS or _is_complex_request(message):
        try:
            from .single_step_handler_utils import _route_to_multi_agent
            return await _route_to_multi_agent(message, user_id, skill_name)
        except Exception as e:
            logger.warning(f"多Agent调度失败，降级到单步: {e}")

    return result


def _is_complex_request(message: str) -> bool:
    """判断是否为需要多Agent协同的复杂请求"""
    msg = message.lower()
    patterns = [
        r"先.*然后.*再", r"第一步.*第二步",
        r"同时.*并且", r"分析.*并.*生成",
        r"爬取.*分析.*报告", r"搜集.*汇总", r"对比.*总结",
    ]
    if any(re.search(p, msg) for p in patterns):
        return True
    skill_count = sum(
        1 for kw in ["搜索", "爬取", "翻译", "分析", "天气", "打开"]
        if kw in msg
    )
    return skill_count >= 2
