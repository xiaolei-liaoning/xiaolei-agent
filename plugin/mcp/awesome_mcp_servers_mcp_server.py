#!/usr/bin/env python3
"""Awesome MCP Servers 管理 - JSON-RPC stdio 协议"""

import sys
import json
import asyncio
from pathlib import Path

TOOLS = [
    {
        "name": "search_servers",
        "description": "按关键词搜索 MCP 服务器",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "list_popular",
        "description": "列出最受欢迎的 MCP 服务器",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_categories",
        "description": "获取所有服务器分类及统计",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_by_category",
        "description": "按分类获取服务器列表",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "分类名称，如 Databases, Browser Automation, Code Execution 等"}
            },
            "required": ["category"]
        }
    },
    {
        "name": "quick_connect",
        "description": "快速连接预配置的 MCP 服务器",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "服务器名称（支持: calculator, weather, fun, chroma, playwright, sqlite, github, slack 等）"}
            },
            "required": ["server_name"]
        }
    },
    {
        "name": "list_connected",
        "description": "列出当前已连接的 MCP 服务器",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_server_info",
        "description": "获取指定 MCP 服务器的详细信息",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "服务器名称"}
            },
            "required": ["server_name"]
        }
    },
]

_manager = None


def get_manager():
    global _manager
    if _manager is None:
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
        _manager = awesome_mcp_manager
    return _manager


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "awesome-mcp-servers", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        try:
            mgr = get_manager()

            if tool == "search_servers":
                keyword = args.get("keyword", "")
                if not keyword:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供搜索关键词"}]}}
                servers = mgr.search_servers(keyword)
                result = mgr.format_server_list(servers)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": result}]}}

            if tool == "list_popular":
                servers = mgr.get_popular_servers()
                result = mgr.format_server_list(servers)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": result}]}}

            if tool == "get_categories":
                servers = mgr.parse_readme()
                cats = {}
                for s in servers:
                    cat = s["category"]
                    if cat not in cats:
                        cats[cat] = []
                    cats[cat].append(s["name"])
                lines = [f"📂 MCP 服务器分类 ({len(cats)} 个分类)\n"]
                for cat, names in sorted(cats.items()):
                    lines.append(f"### {cat} — {len(names)} 个服务器")
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": '\n'.join(lines)}]}}

            if tool == "get_by_category":
                category = args.get("category", "")
                if not category:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供分类名称"}]}}
                servers = mgr.get_by_category(category)
                result = mgr.format_server_list(servers)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": result}]}}

            if tool == "quick_connect":
                server_name = args.get("server_name", "")
                if not server_name:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供服务器名称"}]}}
                result = await mgr.quick_connect(server_name)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": result["message"]}]}}

            if tool == "list_connected":
                servers = mgr.get_connected_servers()
                if not servers:
                    avail = mgr.get_available_quick_connect()
                    text = "📭 暂无已连接的 MCP 服务器\n\n可用快速连接: " + ", ".join(avail[:15])
                else:
                    text = f"🔗 已连接 ({len(servers)} 个):\n" + "\n".join(f"  ✅ {s}" for s in servers)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "get_server_info":
                server_name = args.get("server_name", "")
                if not server_name:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供服务器名称"}]}}
                info = mgr.get_server_info(server_name)
                if not info:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"未找到服务器: {server_name}"}]}}
                text = (
                    f"📦 {info['name']}\n"
                    f"  分类: {info['category']}\n"
                    f"  描述: {info['description']}\n"
                    f"  URL: {info['url']}\n"
                    f"  标签: {' '.join(info['badges']) if info['badges'] else '无'}"
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"错误: {str(e)}"}]}}

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
