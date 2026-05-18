#!/usr/bin/env python3
"""搜索引擎 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path

TOOLS = [
    {
        "name": "search",
        "description": "执行联网搜索查询（RAG引擎）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "scrape",
        "description": "深度爬取指定URL的内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要爬取的网页URL"},
                "depth": {"type": "integer", "description": "爬取深度，默认1"}
            },
            "required": ["url"]
        }
    },
]


async def do_search(query: str) -> dict:
    """使用 RAG 搜索引擎"""
    try:
        from core.search.rag_search_engine import RAGSearchEngine
        engine = RAGSearchEngine()
        results = await engine.search_and_learn(query)
        return {"success": True, "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def do_scrape(url: str, depth: int = 1) -> dict:
    """使用 web_scraper 爬取"""
    try:
        from mcp._impl.web_scraper.handler import ScraperDispatcher
        dispatcher = ScraperDispatcher()
        result = await dispatcher.execute(
            site_name="web",
            url=url if url.startswith('http') else None,
            keywords=None if url.startswith('http') else url,
            depth=depth
        )
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "search-engine-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        if tool == "search":
            query = args.get("query", "")
            if not query:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供搜索关键词"}]}}
            result = await do_search(query)
            if result.get("success"):
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"✅ 搜索结果: {result['results']}"}]}}
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"搜索失败: {result.get('error')}"}]}}

        if tool == "scrape":
            url = args.get("url", "")
            depth = args.get("depth", 1)
            if not url:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供URL"}]}}
            result = await do_scrape(url, depth)
            if result.get("success"):
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"✅ 爬取完成: {result['result']}"}]}}
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"爬取失败: {result.get('error')}"}]}}

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
