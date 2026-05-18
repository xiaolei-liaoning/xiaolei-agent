#!/usr/bin/env python3
"""深度思考 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import asyncio

TOOLS = [
    {
        "name": "think",
        "description": "执行深度思考分析（5阶段框架：理解→收集→设计→验证→反思）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "需要深入分析的问题"},
                "depth": {"type": "string", "description": "思考深度: quick(快速)/standard(标准)/deep(深度)，默认自动"}
            },
            "required": ["query"]
        }
    },
]

_reasoning_engine = None


def get_engine():
    global _reasoning_engine
    if _reasoning_engine is None:
        from core.engine.reasoning_engine import get_reasoning_engine
        _reasoning_engine = get_reasoning_engine()
    return _reasoning_engine


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "deep-thinking-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        if tool == "think":
            query = args.get("query", "")
            if not query:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供要分析的问题"}]}}

            depth = args.get("depth", "").lower()
            try:
                engine = get_engine()
                from core.engine.reasoning_engine import ThinkingDepth
                force_depth = None
                if depth == "quick":
                    force_depth = ThinkingDepth.QUICK
                elif depth == "standard":
                    force_depth = ThinkingDepth.STANDARD
                elif depth == "deep":
                    force_depth = ThinkingDepth.DEEP

                if hasattr(engine, 'process_with_protocol'):
                    result = await engine.process_with_protocol(query, 1, force_depth=force_depth)
                else:
                    result = await engine.process(query, 1)

                final_answer = result.get("final_answer", "")
                thinking_process = result.get("thinking_process", {})
                thinking_depth = result.get("thinking_depth", "standard")
                elapsed = result.get("elapsed_time", 0)

                depth_names = {"quick": "⚡快速", "standard": "🔄标准", "deep": "🧠深度"}
                parts = [f"{depth_names.get(thinking_depth, '标准')}模式 | ⏱️ {elapsed:.1f}s"]
                parts.append("=" * 40)
                parts.append("💡 **答案**")
                parts.append("=" * 40)
                parts.append(final_answer)

                # 搜索参考信息
                search_results = thinking_process.get("search_results", [])
                if search_results:
                    parts.append("\n" + "-" * 40)
                    parts.append("🔍 参考信息")
                    parts.append("-" * 40)
                    for i, sr in enumerate(search_results[:3], 1):
                        title = sr.get("title", "")
                        snippet = sr.get("snippet", "")
                        parts.append(f"[{i}] **{title}**")
                        if snippet:
                            parts.append(f"    {snippet[:120]}")

                text = "\n".join(parts)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            except Exception as e:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"深度思考失败: {str(e)}"}]}}

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
