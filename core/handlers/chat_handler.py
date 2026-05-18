"""闲聊处理器"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def handle_chat(
    message: str, 
    user_id: int, 
    agent_id: str,
    db_initialized: bool = False
) -> Dict[str, Any]:
    """处理闲聊对话（GLM 后端 + 角色扮演 + BFS上下文记忆 + 深度思考）。

    Args:
        message: 用户消息
        user_id: 用户ID
        agent_id: Agent ID
        db_initialized: 数据库是否已初始化

    Returns:
        包含 reply、success 和 thinking_process 的字典
    """
    from .context_memory import add_to_context_memory, get_context_for_llm
    from .persistence import get_system_prompt
    
    add_to_context_memory(user_id, message, role="user", skill_name="chat")
    
    context_str = get_context_for_llm(user_id, depth=2)
    
    system_prompt: str = get_system_prompt(agent_id, db_initialized)
    
    if context_str:
        system_prompt += f"\n\n历史对话上下文（用于理解当前问题）：\n{context_str}"

    thinking_process = None
    
    from ..engine.llm_backend import get_llm_router
    
    try:
        from ..engine.reasoning_engine import get_reasoning_engine
        
        reasoning_engine = get_reasoning_engine()
        reasoning_result = await reasoning_engine.process(message, user_id)
        
        thinking_process = reasoning_result.get("thinking_process")
        final_answer = reasoning_result.get("final_answer")
        
        if final_answer and final_answer != message:
            reply = final_answer
        else:
            router = get_llm_router()
            reply: str = await router.simple_chat(message, system_prompt=system_prompt)
            
    except Exception as e:
        logger.debug("深度思考引擎未启用或失败: %s", e)
        try:
            router = get_llm_router()
            reply: str = await router.simple_chat(message, system_prompt=system_prompt)
        except Exception as llm_e:
            logger.warning("LLM 对话失败: %s", llm_e)
            reply = f"你好！有什么可以帮你的吗？（LLM 未配置: {llm_e}）"
    
    add_to_context_memory(user_id, reply, role="assistant", skill_name="chat")
    
    return {
        "reply": reply,
        "success": True,
        "tool_call": {"name": "chat", "params": {}},
        "thinking_process": thinking_process,
    }
