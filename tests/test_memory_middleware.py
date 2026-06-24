import asyncio
import json
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
from core.memory.memory_middleware import MemoryMiddleware, get_memory_middleware


def test_singleton():
    m1 = get_memory_middleware()
    m2 = get_memory_middleware()
    assert m1 is m2


def test_get_user_context_empty():
    mw = MemoryMiddleware()
    with patch("core.memory.user_profile.get_user_profile") as mock_profile, \
         patch("core.memory.vector_memory.VectorMemoryStore") as mock_vm:
        mock_profile.return_value.to_system_prompt_block.return_value = ""
        mock_vm.return_value.wait_for_collection.return_value = False
        result = asyncio.get_event_loop().run_until_complete(
            mw.get_user_context("test", "你好")
        )
        assert result == ""


def test_process_turn_stores_facts():
    mw = MemoryMiddleware()
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_extractor = MagicMock()
        mock_extractor.extract = AsyncMock(return_value=[
            {"type": "name", "content": "用户姓名是小雷", "confidence": 0.95},
            {"type": "fact", "content": "用户是程序员", "confidence": 0.9},
        ])

        mock_profile = MagicMock()
        mock_profile.add_fact.return_value = True

        mock_vm = MagicMock()
        mock_vm.return_value.wait_for_collection.return_value = False

        with patch("core.memory.fact_extractor.get_fact_extractor", return_value=mock_extractor), \
             patch("core.memory.user_profile.get_user_profile", return_value=mock_profile), \
             patch("core.memory.vector_memory.VectorMemoryStore", mock_vm):

            asyncio.get_event_loop().run_until_complete(
                mw.process_turn("test_user", "我叫小雷，是程序员", "你好小雷！")
            )

            # process_turn sets profile.name for name facts
            assert mock_profile.name == "小雷"
            mock_profile.add_fact.assert_called_once_with("用户是程序员")
