"""工具调用解析

从 react_core.py 提取，负责：
- 解析 LLM 输出中的工具调用
- 支持多种格式（OpenAI/直接/纯文本/Markdown）
- 构建标准工具调用对象
"""

import json
import re
import time
from typing import List, Dict


# 已知工具列表（用于纯文本匹配）
KNOWN_TOOLS = [
    "execute_python", "execute_shell", "write_file", "web_search",
    "fetch_url", "fetch_json", "open_app",
    "browser_navigate", "browser_click", "browser_snapshot",
]


def _fix_json_escapes(s: str) -> str:
    """修复 LLM 生成的 JSON 中的无效转义序列"""
    valid_escapes = set('"\\/bfnrtu')  # 'b' 而非 '\b'(退格符)
    result = []
    i = 0
    in_string = False
    while i < len(s):
        ch = s[i]
        if ch == '"' and (i == 0 or s[i-1] != '\\'):
            in_string = not in_string
            result.append(ch)
        elif ch == '\\' and in_string and i + 1 < len(s):
            next_ch = s[i + 1]
            if next_ch in valid_escapes:
                result.append(ch)
            else:
                # 无效转义 → 双转义 (\\s → \\\\s)
                result.append('\\')
                result.append('\\')
                result.append(next_ch)
                i += 2  # 跳过这两个字符
                continue
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def _make_tool_call(tool_name: str, arguments: dict) -> dict:
    """构建标准工具调用对象"""
    import uuid
    return {
        "id": f"call_{uuid.uuid4().hex[:12]}",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(arguments),
        }
    }


def _build_text_tool_call(tool_name: str, arg_text: str) -> List[dict]:
    """从纯文本参数构建工具调用"""

    # For execute_python: extract the code string
    if tool_name == "execute_python":
        code = arg_text.strip()
        if (code.startswith('"') and code.endswith('"')) or (code.startswith("'") and code.endswith("'")):
            code = code[1:-1]
        code = code.replace("\\n", "\n").replace("\\t", "\t")
        return [_make_tool_call("execute_python", {"code": code})]

    # For execute_shell: extract the command
    if tool_name == "execute_shell":
        cmd = arg_text.strip()
        if (cmd.startswith('"') and cmd.endswith('"')) or (cmd.startswith("'") and cmd.endswith("'")):
            cmd = cmd[1:-1]
        return [_make_tool_call("execute_shell", {"command": cmd})]

    # For write_file tool: try to parse path and content
    if tool_name == "write_file":
        arg_stripped = arg_text.strip()
        
        # 格式0: JSON 格式 {"path": "...", "content": "..."}
        if arg_stripped.startswith("{") and arg_stripped.endswith("}"):
            try:
                data = json.loads(arg_stripped)
                if isinstance(data, dict) and "path" in data and "content" in data:
                    return [_make_tool_call("write_file", {"path": data["path"], "content": data["content"]})]
            except json.JSONDecodeError:
                pass

            # JSON 截断修复: LLM 输出被 max_tokens 截断，JSON 不完整
            if not arg_stripped.endswith("}"):
                path_match = re.search(r'"path"\s*:\s*"([^"]*)"', arg_stripped)
                content_start = re.search(r'"content"\s*:\s*"', arg_stripped)
                if path_match and content_start:
                    path_val = path_match.group(1)
                    content_start_pos = content_start.end()
                    raw_content = arg_stripped[content_start_pos:]
                    raw_content = raw_content.rstrip('\\')
                    raw_content = _fix_json_escapes('"' + raw_content + '"')[1:-1]
                    return [_make_tool_call("write_file", {"path": path_val, "content": raw_content})]

        # 格式1: path: xxx\ncontent: xxx
        # 格式2: "path", "content"
        # 格式3: (path, content)
        # 格式4: 纯文本作为 content，path 需要从上下文推断
        path = ""
        content = arg_text  # 默认整个文本作为 content

        # 尝试提取 path（常见路径模式）
        path_patterns = [
            r'path[=:：]\s*["\']?([^"\'\n]+)["\']?',
            r'["\']([~\/][^"\'\n]+)["\']',
            r'\((["\'][^"\']+["\'])',
        ]
        for pp in path_patterns:
            pm = re.search(pp, arg_text, re.IGNORECASE)
            if pm:
                path = pm.group(1).strip()
                content = arg_text[:pm.start()] + arg_text[pm.end():]
                break

        # 如果没找到 path，尝试从文本开头提取
        if not path:
            path_match = re.match(r'^(~?\/[^\s\n]+)', arg_text.strip())
            if path_match:
                path = path_match.group(1)
                content = arg_text[path_match.end():].strip()

        # 清理 content
        content = content.strip()
        if (content.startswith('"') and content.endswith('"')) or \
           (content.startswith("'") and content.endswith("'")):
            content = content[1:-1]
        content = content.replace("\\n", "\n").replace("\\t", "\t")

        # 如果还是没有有效 content，返回错误提示
        if not content or len(content) < 10:
            return [_make_tool_call("write_file", {"path": path or arg_text, "content": ""})]

        return [_make_tool_call("write_file", {"path": path or "~/Desktop/game.html", "content": content})]

    # Generic: put raw text as first string argument
    return [_make_tool_call(tool_name, {"input": arg_text})]


def _try_parse_tool_calls(text: str) -> List[dict]:
    """尝试从 JSON 文本中提取工具调用"""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(data, dict):
        return []

    # Format 1: OpenAI style
    choices = data.get("choices", [])
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message", {})
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            return tool_calls

    # Format 2: Direct tool_calls
    tool_calls = data.get("tool_calls", [])
    if tool_calls:
        return tool_calls

    # Format 3: Single call (name + arguments at top level)
    if "name" in data and ("arguments" in data or "parameters" in data):
        return [_make_tool_call(
            data["name"],
            data.get("arguments", data.get("parameters", {}))
        )]

    return []


def parse_tool_calls(reply: str) -> List[dict]:
    """容错解析 LLM 工具调用响应

    支持多种格式:
    1. OpenAI 格式: {"choices": [{"message": {"tool_calls": [...]}}]}
    2. 直接格式: {"tool_calls": [...]}
    3. 单个调用: {"name": "...", "arguments": {...}}
    4. Markdown 代码块: ```json\n{"tool_calls": [...]}\n```
    5. 文本中的 JSON: 从文本中提取第一个 JSON 对象
    6. 纯文本工具调用: 工具名 + 参数（适配不支持函数调用的免费模型）
    """
    if not reply or not reply.strip():
        return []

    text = reply.strip()

    # Format 4: Extract from markdown code block
    if "```" in text:
        code_blocks = re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        for block in code_blocks:
            parsed = _try_parse_tool_calls(block.strip())
            if parsed:
                return parsed

    # Format 5: Extract JSON from text (find first { ... } at top level)
    if not text.startswith("{"):
        match = re.search(r'\{[\s\S]*"tool_calls"[\s\S]*\}', text)
        if match:
            text = match.group(0)

    # Formats 1, 2, 3: Direct JSON parsing
    result = _try_parse_tool_calls(text)
    if result:
        return result

    # Format 6: Plain text tool call fallback (for models without function calling)
    for tool_name in KNOWN_TOOLS:
        # Match: tool_name at start followed by newline or space, then content
        pattern = rf'^{re.escape(tool_name)}\s*\n(.+)$'
        match = re.match(pattern, text, re.DOTALL)
        if match:
            arg_text = match.group(1).strip()
            return _build_text_tool_call(tool_name, arg_text)
        # Match: tool_name at start followed by parentheses or quoted string
        pattern2 = rf'^{re.escape(tool_name)}\s*[\("](.+)$'
        match2 = re.match(pattern2, text, re.DOTALL)
        if match2:
            arg_text = match2.group(1).strip().rstrip('")')
            return _build_text_tool_call(tool_name, arg_text)
        # Match: tool_name mentioned anywhere in text
        # Pattern 3a: tool_name ... ```code block```
        pattern3a = rf'{re.escape(tool_name)}[\s\S]*?```[\s\S]*?```'
        match3a = re.search(pattern3a, text, re.DOTALL)
        if match3a:
            code_match = re.search(r'```(?:\w+)?\s*\n([\s\S]*?)```', match3a.group(0))
            if code_match:
                code = code_match.group(1).strip()
                return _build_text_tool_call(tool_name, code)

        # Pattern 3b: tool_name followed by path and/or content (no code block)
        if tool_name == "write_file":
            tool_pos = text.find(tool_name)
            if tool_pos >= 0:
                after = text[tool_pos + len(tool_name):tool_pos + len(tool_name) + 30]
                is_question = any(q in after for q in ["？", "?", "吗", "工具", "建议", "需要"])
                if not is_question:
                    after_tool = text[tool_pos + len(tool_name):].strip()
                    after_tool = after_tool.lstrip('(:：\n ')
                    if after_tool and len(after_tool) > 10:
                        return _build_text_tool_call(tool_name, after_tool)

    return []
