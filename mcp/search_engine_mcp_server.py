#!/usr/bin/env python3
"""搜索引擎 MCP 服务器"""

import sys
import json
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Dict, Any


class SearchEngineMCPServer:
    def __init__(self):
        self.name = "search-engine"
        self.description = "联网搜索服务"

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "search",
                "description": "联网搜索信息",
                "parameters": {
                    "query": {"type": "string", "description": "搜索关键词", "required": True},
                    "top_n": {"type": "integer", "description": "返回条数", "required": False}
                }
            },
            {
                "name": "scrape",
                "description": "深度爬取网页内容",
                "parameters": {
                    "url": {"type": "string", "description": "目标URL", "required": True},
                    "depth": {"type": "integer", "description": "爬取深度", "required": False}
                }
            },
        ]

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from mcp._impl.search_engine.handler import handler as search_handler
            if name == "search":
                query = args.get("query", "")
                top_n = args.get("top_n", 10)
                import asyncio
                result = asyncio.run(search_handler.execute(query=query, mode="search"))
                return {"success": True, "result": str(result.get("results", result))}
            elif name == "scrape":
                url = args.get("url", "")
                depth = args.get("depth", 1)
                import asyncio
                result = asyncio.run(search_handler.execute(query=url, mode="scrape", depth=depth))
                return {"success": True, "result": str(result.get("results", result))}
            return {"success": False, "error": f"未知工具: {name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


server = SearchEngineMCPServer()


def handle_request(request: dict) -> dict:
    method = request.get("method", "")
    if method == "list_tools" or method == "tools":
        return {"jsonrpc": "2.0", "result": server.get_tools(), "id": request.get("id")}
    elif method == "call" or method == "callTool":
        tool_name = request.get("params", {}).get("name")
        args = request.get("params", {}).get("arguments", {})
        result = server.call_tool(tool_name, args)
        return {
            "jsonrpc": "2.0",
            "result": {"success": result["success"], "content": [{"text": str(result.get("result", ""))}]},
            "id": request.get("id")
        }
    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": request.get("id")}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
