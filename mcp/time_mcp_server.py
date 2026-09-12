#!/usr/bin/env python3
"""time_mcp_server - 简单时间 MCP 服务器 (stdio 传输)"""

import json
import sys
from datetime import datetime


def handle_request(request):
    """处理 MCP 请求"""
    method = request.get("method", "")
    params = request.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": params.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "time-mcp", "version": "1.0.0"}
            }
        }
    
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": params.get("id"),
            "result": {
                "tools": [{
                    "name": "get_time",
                    "description": "获取当前时间和日期",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                }]
            }
        }
    
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        if tool_name == "get_time":
            now = datetime.now()
            return {
                "jsonrpc": "2.0",
                "id": params.get("id"),
                "result": {
                    "content": [{
                        "type": "text",
                        "text": f"当前时间: {now.strftime('%Y年%m月%d日 %H时%M分%S秒')} (星期{['一','二','三','四','五','六','日'][now.weekday()]})"
                    }]
                }
            }
        
        return {
            "jsonrpc": "2.0",
            "id": params.get("id"),
            "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}
        }
    
    return {
        "jsonrpc": "2.0",
        "id": params.get("id"),
        "error": {"code": -32601, "message": f"Unknown method: {method}"}
    }


def main():
    """主函数 - 处理 stdio 输入"""
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            response = handle_request(request)
            print(json.dumps(response, ensure_ascii=False))
            sys.stdout.flush()
        except json.JSONDecodeError:
            continue
        except Exception as e:
            error_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)}
            }
            print(json.dumps(error_resp, ensure_ascii=False))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
