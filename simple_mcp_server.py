#!/usr/bin/env python3
"""
超级简单的 MCP 服务器 - 用于测试 MCP 客户端
兼容最新的 MCP Python SDK
"""

import asyncio
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from typing import Any

async def main():
    """运行简单的 MCP 服务器"""
    
    print("🚀 启动简单的 MCP 测试服务器...", file=sys.stderr)
    
    # 创建服务器
    server = Server("xiaolei-test-server", "1.0.0")
    
    # 注册工具
    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        """列出可用工具"""
        return [
            Tool(
                name="get_hello",
                description="返回一个简单的问候消息",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "要问候的名字"
                        }
                    },
                    "required": []
                }
            ),
            Tool(
                name="add_numbers",
                description="将两个数字相加",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "第一个数字"},
                        "b": {"type": "number", "description": "第二个数字"}
                    },
                    "required": ["a", "b"]
                }
            )
        ]
    
    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """调用工具"""
        
        result_text = ""
        
        if name == "get_hello":
            name_arg = arguments.get("name", "World")
            result_text = f"Hello, {name_arg}!"
            
        elif name == "add_numbers":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            result_text = f"{a} + {b} = {a + b}"
            
        else:
            result_text = f"Unknown tool: {name}"
        
        # 返回 TextContent 格式
        return [TextContent(type="text", text=result_text)]
    
    # 使用 stdio 运行服务器
    print("✅ 服务器准备就绪，等待连接...", file=sys.stderr)
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    except Exception as e:
        print(f"❌ 服务器错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
