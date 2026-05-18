#!/usr/bin/env python3
"""ASCII艺术 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import asyncio

ASCII_ARTS = {
    "cat": r"""
      /\_/\
     ( o.o )
      > ^ <
    """,
    "dog": r"""
       __
      /  \
     |  @  |
     | || ||
     |_^^_|
    /     \
   (___|___)
    """,
    "heart": r"""
     ♥  ♥
    ♥  ♥  ♥
   ♥  ♥  ♥  ♥
  ♥  ♥  ♥  ♥  ♥
   ♥  ♥  ♥  ♥
    ♥  ♥  ♥
     ♥  ♥
      ♥
    """,
    "star": r"""
        *
       /|\
      /*|*\
     /*-*-*-\
    /*-*-*- -*-\
   /*-*-*- -*- -*-\
      -*- -*- -*-
         *
    """,
    "robot": r"""
       /\___/\
      / o   o \
     ( ==  ^  )
      )       (
     /         \
    / (________) \
   |             |
    """,
    "ghost": r"""
         🎃
        /  \
       (    )
       |    |
        \  /
         ⚫
    """,
    "flower": r"""
        💐
       /   \
      /_____\
      | ♥ ♥ |
      | ♥ ♥ |
      |  ♥  |
    """,
    "smile": r"""
       😊
      /   \
     ( o o )
      \ v /
     /     \
    |  o  |
     \___/
    """,
    "rocket": r"""
      🚀
     /  \
    |  🌟 |
     \___/
    """,
    "snowman": r"""
          🎅
          |
         / \
        /   \
       (  o  )
        \___/
    """,
}

TOOLS = [
    {
        "name": "list_arts",
        "description": "列出所有可用的ASCII艺术图案",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_art",
        "description": "获取指定名称的ASCII艺术图案",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "艺术图案名称（如 cat, dog, heart, star, robot, ghost, flower, smile, rocket, snowman）"}
            },
            "required": ["name"]
        }
    },
]


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "art-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        if tool == "list_arts":
            arts = sorted(ASCII_ARTS.keys())
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"🎨 可用ASCII艺术 ({len(arts)}个):\n{'、'.join(arts)}"}]}}

        if tool == "get_art":
            name = args.get("name", "").lower()
            if not name:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请指定艺术图案名称"}]}}

            # 精确匹配
            art = ASCII_ARTS.get(name)
            if art:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"🎨 {name}\n{art}"}]}}

            # 模糊匹配
            matched = [k for k in ASCII_ARTS if name in k]
            if matched:
                art = ASCII_ARTS[matched[0]]
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"🎨 {matched[0]}\n{art}"}]}}

            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"未知图案: {name}\n可用: {'、'.join(sorted(ASCII_ARTS.keys()))}"}]}}

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
