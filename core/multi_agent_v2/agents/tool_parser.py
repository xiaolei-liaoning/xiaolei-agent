"""工具调用解析 — 从 LLM 文本回复中提取 JSON 工具调用

react_core.py 通过 router.chat() 获取纯文本回复，再用此模块解析出 tool_calls。
如果 LLM 返回了原生 tool_calls（chat_structured），则不需要此解析。
"""

import json
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def _normalize_tool_calls(calls: list) -> list:
    """统一 arguments 字段为 JSON 字符串"""
    for tc in calls:
        fn = tc.get("function", {})
        args = fn.get("arguments", "{}")
        if isinstance(args, dict):
            fn["arguments"] = json.dumps(args, ensure_ascii=False)
        elif not isinstance(args, str):
            fn["arguments"] = json.dumps(args, ensure_ascii=False) if args else "{}"
    return calls


def parse_tool_calls(text: str) -> List[Dict]:
    """从文本中解析工具调用，返回 tool_calls 列表"""
    if not text:
        return []

    text = text.strip()
    calls = []

    # 尝试1: 整段是 JSON — 处理 chat() 返回的 choices 格式
    if text.startswith("{") or text.startswith("["):
        try:
            obj = json.loads(text)
            # chat() 格式: {"choices": [{"message": {"tool_calls": [...]}}]}
            if isinstance(obj, dict) and "choices" in obj:
                for choice in obj["choices"]:
                    msg = choice.get("message", {})
                    tc = msg.get("tool_calls", [])
                    if tc:
                        calls.extend(tc)
                if calls:
                    return _normalize_tool_calls(calls)
            # 直接包含 tool_calls
            if isinstance(obj, dict) and "tool_calls" in obj:
                return _normalize_tool_calls(obj["tool_calls"])
            # 单个工具调用
            if isinstance(obj, dict) and "function" in obj:
                return _normalize_tool_calls([obj])
            # 列表
            if isinstance(obj, list):
                return _normalize_tool_calls(obj)
        except json.JSONDecodeError:
            pass

    # 尝试2: 从 ```json ... ``` 代码块提取
    code_blocks = re.findall(r'```(?:json)?\s*(\{.*?\}|\[.*?])\s*```', text, re.DOTALL)
    for block in code_blocks:
        try:
            obj = json.loads(block)
            if isinstance(obj, dict) and "choices" in obj:
                for choice in obj["choices"]:
                    msg = choice.get("message", {})
                    calls.extend(msg.get("tool_calls", []))
            elif isinstance(obj, dict) and "tool_calls" in obj:
                calls.extend(obj["tool_calls"])
            elif isinstance(obj, dict) and "function" in obj:
                calls.append(obj)
            elif isinstance(obj, list):
                calls.extend(obj)
        except json.JSONDecodeError:
            continue

    if calls:
        return _normalize_tool_calls(calls)

    # 尝试3: 找所有 {"type": "function", "function": {"name": ..., "arguments": ...}} 模式
    # 用非贪婪匹配支持嵌套 arguments JSON
    pattern = r'\{"type"\s*:\s*"function"\s*,\s*"function"\s*:\s*\{[^{}]*"name"\s*:\s*"[^"]*"[^{}]*\}\s*\}'
    matches = re.finditer(pattern, text, re.DOTALL)
    for m in matches:
        try:
            obj = json.loads(m.group())
            if "function" in obj:
                calls.append(obj)
        except json.JSONDecodeError:
            continue

    # 尝试4: 找 "name": "xxx", "arguments": "xxx" 的简单模式
    if not calls:
        name_match = re.search(r'"name"\s*:\s*"(\w+)"', text)
        args_match = re.search(r'"arguments"\s*:\s*(\{[^}]+\}|"[^"]*")', text)
        if name_match:
            fn_name = name_match.group(1)
            args_str = args_match.group(1) if args_match else "{}"
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = args_str
            calls.append({
                "type": "function",
                "function": {
                    "name": fn_name,
                    "arguments": json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args)
                }
            })

    if calls:
        logger.debug(f"从文本解析出 {len(calls)} 个工具调用")

    return _normalize_tool_calls(calls)
