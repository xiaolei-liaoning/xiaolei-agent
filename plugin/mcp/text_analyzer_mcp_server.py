#!/usr/bin/env python3
"""文本分析 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import re
import asyncio
from collections import Counter

TOOLS = [
    {
        "name": "analyze_text",
        "description": "完整分析文本：字符数、词数、句子数、关键词",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待分析的文本"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "count_characters",
        "description": "统计字符数（不含空格）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "输入文本"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "count_words",
        "description": "统计词数（中文按字、英文按单词计算）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "输入文本"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "count_sentences",
        "description": "统计句子数",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "输入文本"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "extract_keywords",
        "description": "提取关键词（基于词频统计）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "输入文本"},
                "top_n": {"type": "integer", "description": "返回关键词数量，默认5"}
            },
            "required": ["text"]
        }
    },
]

STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "这个", "那个",
    "the", "a", "an", "is", "are", "was", "were",
    "of", "in", "on", "at", "to", "for", "and",
}


def count_chars(text):
    return len(text.replace(" ", ""))


def count_words(text):
    chinese_chars = re.findall(r'[一-龥]', text)
    english_words = re.findall(r'[a-zA-Z]+', text)
    return len(chinese_chars) + len(english_words)


def count_sentences(text):
    sentences = re.split(r'[。！？.!?]', text)
    return len([s for s in sentences if s.strip()])


def extract_keywords(text, top_n=5):
    chinese_words = re.findall(r'[一-龥]{2,4}', text)
    english_words = re.findall(r'[a-zA-Z]{3,}', text)
    all_words = chinese_words + english_words
    filtered = [w for w in all_words if w.lower() not in STOP_WORDS]
    return [w for w, _ in Counter(filtered).most_common(top_n)]


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "text-analyzer-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        text = args.get("text", "")
        if not text and tool not in ("analyze_text",):
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供文本"}]}}

        if tool == "count_characters":
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"字符数(不含空格): {count_chars(text)}"}]}}

        if tool == "count_words":
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"词数: {count_words(text)}"}]}}

        if tool == "count_sentences":
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"句子数: {count_sentences(text)}"}]}}

        if tool == "extract_keywords":
            top_n = args.get("top_n", 5)
            kw = extract_keywords(text, int(top_n))
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"关键词(Top{top_n}): {'、'.join(kw) if kw else '无'}"}]}}

        if tool == "analyze_text":
            if not text:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供文本"}]}}
            cc = count_chars(text)
            cw = count_words(text)
            cs = count_sentences(text)
            kw = extract_keywords(text, 5)
            preview = text[:100] + "..." if len(text) > 100 else text
            result = (
                f"📊 文本分析结果\n\n"
                f"字符数(不含空格): {cc}\n"
                f"词数: {cw}\n"
                f"句子数: {cs}\n"
                f"文本长度: {len(text)}\n"
                f"关键词: {'、'.join(kw) if kw else '无'}\n\n"
                f"文本预览: {preview}"
            )
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": result}]}}

        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown tool: {tool}"}}

    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}


async def main():
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


if __name__ == "__main__":
    asyncio.run(main())
