#!/usr/bin/env python3
"""
文本处理MCP服务器 - 使用JSON-RPC协议
"""

import sys
import json
import re
import asyncio


# 可用工具列表
TOOLS = [
    {
        "name": "to_uppercase",
        "description": "转换为大写",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"]
        }
    },
    {
        "name": "to_lowercase",
        "description": "转换为小写",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"]
        }
    },
    {
        "name": "count_words",
        "description": "统计字数",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"]
        }
    },
    {
        "name": "count_characters",
        "description": "统计字符数",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "输入文本"},
                "include_spaces": {"type": "boolean", "description": "是否包含空格（默认true）"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "reverse_text",
        "description": "反转文本",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"]
        }
    },
    {
        "name": "find_replace",
        "description": "查找替换",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "输入文本"},
                "find": {"type": "string", "description": "要查找的文本"},
                "replace": {"type": "string", "description": "替换为的文本"}
            },
            "required": ["text", "find", "replace"]
        }
    },
    {
        "name": "extract_urls",
        "description": "提取URL",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"]
        }
    },
    {
        "name": "extract_emails",
        "description": "提取邮箱地址",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"]
        }
    },
    {
        "name": "split_sentences",
        "description": "拆分句子",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"]
        }
    },
    {
        "name": "trim_whitespace",
        "description": "去除首尾空白",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"]
        }
    },
    {
        "name": "count_lines",
        "description": "统计行数",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"]
        }
    },
    {
        "name": "word_frequency",
        "description": "词频统计",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "输入文本"},
                "top_n": {"type": "number", "description": "返回前N个词（默认10）"}
            },
            "required": ["text"]
        }
    }
]


async def handle_request(request):
    """处理JSON-RPC请求"""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id", 1)
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"name": "text-processing-mcp-server", "version": "1.0.0"}
        }
    
    elif method == "listTools":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS}
        }
    
    elif method == "callTool":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        result_text = ""
        
        if tool_name == "to_uppercase":
            text = arguments.get("text", "")
            result_text = text.upper()
            
        elif tool_name == "to_lowercase":
            text = arguments.get("text", "")
            result_text = text.lower()
            
        elif tool_name == "count_words":
            text = arguments.get("text", "")
            words = text.split()
            result_text = f"单词数: {len(words)}"
            
        elif tool_name == "count_characters":
            text = arguments.get("text", "")
            include_spaces = arguments.get("include_spaces", True)
            if include_spaces:
                count = len(text)
            else:
                count = len(text.replace(" ", ""))
            result_text = f"字符数: {count} (包含空格: {include_spaces})"
            
        elif tool_name == "reverse_text":
            text = arguments.get("text", "")
            result_text = text[::-1]
            
        elif tool_name == "find_replace":
            text = arguments.get("text", "")
            find = arguments.get("find", "")
            replace = arguments.get("replace", "")
            count = text.count(find)
            result = text.replace(find, replace)
            result_text = f"替换了 {count} 处\n\n{result}"
            
        elif tool_name == "extract_urls":
            text = arguments.get("text", "")
            url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
            urls = re.findall(url_pattern, text)
            if urls:
                result_text = f"找到 {len(urls)} 个URL:\n\n" + "\n".join(f"  {i+1}. {url}" for i, url in enumerate(urls))
            else:
                result_text = "未找到URL"
            
        elif tool_name == "extract_emails":
            text = arguments.get("text", "")
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            emails = re.findall(email_pattern, text)
            if emails:
                result_text = f"找到 {len(emails)} 个邮箱地址:\n\n" + "\n".join(f"  {i+1}. {email}" for i, email in enumerate(emails))
            else:
                result_text = "未找到邮箱地址"
            
        elif tool_name == "split_sentences":
            text = arguments.get("text", "")
            sentences = re.split(r'(?<=[.!?])\s+', text)
            sentences = [s.strip() for s in sentences if s.strip()]
            result_text = f"找到 {len(sentences)} 个句子:\n\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sentences))
            
        elif tool_name == "trim_whitespace":
            text = arguments.get("text", "")
            result_text = text.strip()
            
        elif tool_name == "count_lines":
            text = arguments.get("text", "")
            lines = text.split("\n")
            non_empty_lines = [line for line in lines if line.strip()]
            result_text = f"总行数: {len(lines)}, 非空行数: {len(non_empty_lines)}"
            
        elif tool_name == "word_frequency":
            text = arguments.get("text", "")
            top_n = int(arguments.get("top_n", 10))
            words = re.findall(r'\b\w+\b', text.lower())
            freq = {}
            for word in words:
                freq[word] = freq.get(word, 0) + 1
            sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)
            result_parts = [f"词频统计 (前{top_n}):", ""]
            for i, (word, count) in enumerate(sorted_freq[:top_n]):
                result_parts.append(f"  {i+1}. {word}: {count}")
            result_text = "\n".join(result_parts)
            
        else:
            result_text = f"未知工具: {tool_name}"
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"text": result_text}]}
        }
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"}
        }


async def main():
    """运行文本处理MCP服务器"""
    print("🚀 启动文本处理 MCP 服务器 (JSON-RPC模式)...", file=sys.stderr)
    
    try:
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break
                
            try:
                request = json.loads(line.strip())
                response = await handle_request(request)
                print(json.dumps(response))
                sys.stdout.flush()
            except json.JSONDecodeError:
                print(json.dumps({"jsonrpc": "2.0", "id": 0, "error": {"code": -32700, "message": "Parse error"}}))
                sys.stdout.flush()
            except Exception as e:
                print(json.dumps({"jsonrpc": "2.0", "id": 0, "error": {"code": -32603, "message": str(e)}}))
                sys.stdout.flush()
                
    except KeyboardInterrupt:
        print("✅ 服务器已停止", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
