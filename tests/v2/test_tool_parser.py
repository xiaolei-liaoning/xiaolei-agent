"""
tool_parser 单元测试 — 覆盖 4 级 fallback 解析路径
"""
import json
import pytest
from core.multi_agent_v2.agents.tool_parser import parse_tool_calls, _normalize_tool_calls


def test_parse_empty_text_returns_empty():
    assert parse_tool_calls("") == []
    assert parse_tool_calls(None) == []


def test_parse_choices_format():
    """尝试1: chat() 返回 choices 格式"""
    text = json.dumps({
        "choices": [{
            "message": {
                "tool_calls": [{
                    "type": "function",
                    "function": {"name": "write_file", "arguments": {"path": "/tmp/a.txt", "content": "hi"}}
                }]
            }
        }]
    })
    result = parse_tool_calls(text)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "write_file"
    # arguments 应该是 dict（内部格式）
    assert isinstance(result[0]["function"]["arguments"], dict)
    assert result[0]["function"]["arguments"]["path"] == "/tmp/a.txt"


def test_parse_direct_tool_calls_field():
    """尝试1: 直接 tool_calls 字段"""
    text = json.dumps({
        "tool_calls": [{
            "type": "function",
            "function": {"name": "read_file", "arguments": {"path": "/tmp"}}
        }]
    })
    result = parse_tool_calls(text)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "read_file"


def test_parse_single_function_object():
    """尝试1: 单个 {function: ...} 对象"""
    text = json.dumps({
        "type": "function",
        "function": {"name": "git", "arguments": {"action": "status"}}
    })
    result = parse_tool_calls(text)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "git"


def test_parse_json_code_block():
    """尝试2: ```json ... ``` 代码块"""
    text = '''Here's my plan:
```json
{"tool_calls": [{"type": "function", "function": {"name": "web_search", "arguments": {"query": "test"}}}]}
```
'''
    result = parse_tool_calls(text)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "web_search"


def test_parse_regex_function_pattern():
    """尝试3: 正则匹配 {"type":"function","function":{"name":...}}"""
    text = 'Some preamble text {"type": "function", "function": {"name": "echo", "arguments": "{}"}} trailing'
    result = parse_tool_calls(text)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "echo"


def test_parse_name_arguments_fallback():
    """尝试4: 简单 name/arguments 模式"""
    text = 'I will call: {"name": "fetch_url", "arguments": {"url": "https://example.com"}}'
    result = parse_tool_calls(text)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "fetch_url"


def test_normalize_keeps_dict_arguments():
    """_normalize_tool_calls 保持 dict arguments 不变"""
    calls = [{
        "type": "function",
        "function": {"name": "test", "arguments": {"key": "value"}}
    }]
    result = _normalize_tool_calls(calls)
    assert isinstance(result[0]["function"]["arguments"], dict)
    assert result[0]["function"]["arguments"] == {"key": "value"}


def test_normalize_parses_string_arguments():
    """_normalize_tool_calls 把字符串 arguments 解析为 dict"""
    calls = [{
        "type": "function",
        "function": {"name": "test", "arguments": '{"a": 1}'}
    }]
    result = _normalize_tool_calls(calls)
    assert isinstance(result[0]["function"]["arguments"], dict)
    assert result[0]["function"]["arguments"] == {"a": 1}


def test_parse_no_tools_in_plain_text():
    """纯文本无工具调用应返回空"""
    result = parse_tool_calls("I will analyze the project structure now.")
    assert result == []


def test_parse_multiple_tools_in_choices():
    """choices 格式含多个 tool_calls"""
    text = json.dumps({
        "choices": [{
            "message": {
                "tool_calls": [
                    {"type": "function", "function": {"name": "read_file", "arguments": {"path": "/a"}}},
                    {"type": "function", "function": {"name": "read_file", "arguments": {"path": "/b"}}},
                ]
            }
        }]
    })
    result = parse_tool_calls(text)
    assert len(result) == 2
    assert result[0]["function"]["name"] == "read_file"
    assert result[1]["function"]["name"] == "read_file"