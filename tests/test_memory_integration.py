"""记忆系统集成测试"""
import pytest
from unittest.mock import Mock, patch, MagicMock


def test_chat_handler_injects_vector_memory():
    """测试 chat_handler 是否注入向量记忆（验证函数签名和导入）"""
    from core.handlers.chat_handler import handle_chat
    import inspect
    
    # 验证函数签名接受 user_id 参数
    sig = inspect.signature(handle_chat)
    params = list(sig.parameters.keys())
    assert "message" in params
    assert "user_id" in params
    assert "agent_id" in params


def test_vector_memory_search_with_str_user_id():
    """测试向量记忆支持 str 类型的 user_id"""
    from core.memory.vector_memory import VectorMemoryStore
    import inspect
    
    # 验证 search_memories 签名接受 user_id
    sig = inspect.signature(VectorMemoryStore.search_memories)
    params = list(sig.parameters.keys())
    assert "query" in params
    assert "user_id" in params


def test_memory_nudge_triggers_after_interval():
    """测试 nudge 机制在间隔后触发"""
    from core.memory.memory_nudge import MemoryNudge
    
    nudge = MemoryNudge(nudge_interval=3)
    
    # 前两次不触发
    assert nudge.increment("user1") == False
    assert nudge.increment("user1") == False
    
    # 第三次触发
    assert nudge.increment("user1") == True


def test_stm_singleton_consistency():
    """测试 STM 单例一致性"""
    from core.memory.short_term_memory import get_memory_manager
    from core.handlers.context_memory import short_term_memory
    
    manager = get_memory_manager()
    # context_memory 中的 short_term_memory 应该是同一个实例
    assert short_term_memory is manager
