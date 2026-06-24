import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from core.memory.fact_extractor import FactExtractor, get_fact_extractor


def test_extractor_singleton():
    e1 = get_fact_extractor()
    e2 = get_fact_extractor()
    assert e1 is e2


def test_no_llm_returns_empty():
    extractor = FactExtractor()
    extractor._llm = None
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract("你好")
    )
    assert result == []


def test_extraction_with_mock_llm():
    extractor = FactExtractor()
    mock_llm = AsyncMock()
    mock_llm.simple_chat = AsyncMock(return_value=json.dumps([
        {"type": "name", "content": "用户姓名是小雷", "confidence": 0.95},
        {"type": "fact", "content": "用户是程序员", "confidence": 0.9},
    ]))
    extractor._llm = mock_llm

    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract("我叫小雷，是个程序员")
    )
    assert len(result) == 2
    assert result[0]["type"] == "name"
    assert "小雷" in result[0]["content"]


def test_low_confidence_filtered():
    extractor = FactExtractor()
    mock_llm = AsyncMock()
    mock_llm.simple_chat = AsyncMock(return_value=json.dumps([
        {"type": "fact", "content": "可能的信息", "confidence": 0.3},
        {"type": "fact", "content": "确定的信息", "confidence": 0.9},
    ]))
    extractor._llm = mock_llm

    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract("测试消息")
    )
    assert len(result) == 1
    assert result[0]["confidence"] == 0.9


def test_empty_llm_response():
    extractor = FactExtractor()
    mock_llm = AsyncMock()
    mock_llm.simple_chat = AsyncMock(return_value="[]")
    extractor._llm = mock_llm

    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract("今天天气怎么样")
    )
    assert result == []
