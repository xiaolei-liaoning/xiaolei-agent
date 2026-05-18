#!/usr/bin/env python3
"""翻译助手 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import re
import asyncio

LANG_NAMES = {
    'zh': '中文', 'en': '英文', 'ja': '日文', 'ko': '韩文',
    'fr': '法文', 'de': '德文', 'ru': '俄文', 'es': '西班牙文',
    'it': '意大利文', 'pt': '葡萄牙文', 'ar': '阿拉伯文',
}
SUPPORTED_TARGETS = set(LANG_NAMES.keys())

TOOLS = [
    {
        "name": "translate",
        "description": "翻译文本到指定语言",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待翻译文本"},
                "target_lang": {"type": "string", "description": "目标语言代码 zh/en/ja/ko/fr/de/ru/es/it/pt/ar，默认en"},
                "source_lang": {"type": "string", "description": "源语言代码，留空自动检测"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "detect_language",
        "description": "检测文本的语言",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要检测语言的文本"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "batch_translate",
        "description": "批量翻译多段文本",
        "inputSchema": {
            "type": "object",
            "properties": {
                "texts": {"type": "array", "items": {"type": "string"}, "description": "待翻译文本列表"},
                "target_lang": {"type": "string", "description": "目标语言代码，默认en"}
            },
            "required": ["texts"]
        }
    },
    {
        "name": "get_supported_languages",
        "description": "获取支持的语言列表",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
]


def detect_language(text: str) -> str:
    """基于Unicode范围自动检测语言"""
    if not text:
        return 'en'
    zh_count = ja_hira = ja_kata = ko_count = latin_count = cyrillic_count = 0
    sample = text[:500]
    for char in sample:
        cp = ord(char)
        if '一' <= char <= '鿿':
            zh_count += 1
        elif '぀' <= char <= 'ゟ':
            ja_hira += 1
        elif '゠' <= char <= 'ヿ':
            ja_kata += 1
        elif 0xac00 <= cp <= 0xd7af or 0x1100 <= cp <= 0x11ff:
            ko_count += 1
        elif 0x0400 <= cp <= 0x04ff:
            cyrillic_count += 1
        elif char.isascii() and char.isalpha():
            latin_count += 1
    scores = {'zh': zh_count, 'ja': (ja_hira + ja_kata) * 2, 'ko': ko_count * 2, 'ru': cyrillic_count * 2, 'en': latin_count}
    detected = max(scores, key=scores.get)
    return detected if scores[detected] > 0 else 'en'


def call_translate_api(text: str, langpair: str) -> dict:
    """调用MyMemory API执行翻译"""
    import httpx
    response = httpx.get(
        "https://api.mymemory.translated.net/get",
        params={'q': text, 'langpair': langpair},
        timeout=10,
        headers={'User-Agent': 'Mozilla/5.0'},
    )
    response.raise_for_status()
    data = response.json()
    status = data.get('responseStatus')
    if int(status) if status else 0 == 200:
        translated = data['responseData']['translatedText']
        match_val = data.get('responseData', {}).get('match', 0)
        confidence = round(float(match_val), 2) if match_val else None
        return {"success": True, "original": text, "translated": translated, "confidence": confidence}
    return {"success": False, "error": data.get('responseDetails', '未知错误')}


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "translator-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "callTool" or method == "call":
        tool = params.get("name")
        args = params.get("arguments", {})

        if tool == "get_supported_languages":
            langs = "\n".join([f"{k}: {v}" for k, v in sorted(LANG_NAMES.items())])
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"支持的语言:\n{langs}"}]}}

        if tool == "translate":
            text = args.get("text", "")
            target_lang = args.get("target_lang", "en")
            source_lang = args.get("source_lang", "autodetect")
            if not text:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "错误: 未指定翻译文本"}]}}
            target_lang = target_lang.lower().strip()
            if target_lang not in SUPPORTED_TARGETS:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"不支持的语言: {target_lang}"}]}}
            langpair = f"{source_lang}|{target_lang}"
            result = call_translate_api(text, langpair)
            if result.get("success"):
                detected = detect_language(text)
                source_name = LANG_NAMES.get(detected, detected)
                target_name = LANG_NAMES.get(target_lang, target_lang)
                reply = f"[{source_name}→{target_name}] {text}\n译文: {result['translated']}"
                if result.get("confidence"):
                    reply += f"\n置信度: {result['confidence']}"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": reply}]}}
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"翻译失败: {result.get('error', '未知错误')}"}]}}

        if tool == "detect_language":
            text = args.get("text", "")
            if not text:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供文本"}]}}
            detected = detect_language(text)
            lang_name = LANG_NAMES.get(detected, detected)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"检测到语言: {lang_name} ({detected})"}]}}

        if tool == "batch_translate":
            texts = args.get("texts", [])
            target_lang = args.get("target_lang", "en")
            if not texts:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供待翻译文本列表"}]}}
            target_lang = target_lang.lower().strip()
            results = []
            for i, text in enumerate(texts):
                result = call_translate_api(text, f"autodetect|{target_lang}")
                if result.get("success"):
                    results.append(f"{i+1}. {text[:40]}... → {result['translated'][:40]}...")
                else:
                    results.append(f"{i+1}. {text[:40]}... → [失败]")
            reply = f"批量翻译完成 ({len(results)}条):\n" + "\n".join(results)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": reply}]}}

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
