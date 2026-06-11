#!/usr/bin/env python3
"""
计算器MCP服务器 - 使用JSON-RPC协议
"""

import sys
import json
import random
import asyncio


# 可用工具列表
TOOLS = [
    {
        "name": "add",
        "description": "加法运算",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "第一个数"},
                "b": {"type": "number", "description": "第二个数"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "name": "subtract",
        "description": "减法运算",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "被减数"},
                "b": {"type": "number", "description": "减数"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "name": "multiply",
        "description": "乘法运算",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "第一个数"},
                "b": {"type": "number", "description": "第二个数"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "name": "divide",
        "description": "除法运算",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "被除数"},
                "b": {"type": "number", "description": "除数"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "name": "power",
        "description": "幂运算",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base": {"type": "number", "description": "底数"},
                "exponent": {"type": "number", "description": "指数"}
            },
            "required": ["base", "exponent"]
        }
    },
    {
        "name": "sqrt",
        "description": "平方根运算",
        "inputSchema": {
            "type": "object",
            "properties": {
                "number": {"type": "number", "description": "要计算平方根的数"}
            },
            "required": ["number"]
        }
    },
    {
        "name": "random",
        "description": "生成随机数",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min": {"type": "number", "description": "最小值（默认0）"},
                "max": {"type": "number", "description": "最大值（默认100）"}
            },
            "required": []
        }
    },
    {
        "name": "percentage",
        "description": "百分比计算",
        "inputSchema": {
            "type": "object",
            "properties": {
                "part": {"type": "number", "description": "部分值"},
                "total": {"type": "number", "description": "总值"}
            },
            "required": ["part", "total"]
        }
    },
    {
        "name": "average",
        "description": "计算平均值",
        "inputSchema": {
            "type": "object",
            "properties": {
                "numbers": {"type": "array", "items": {"type": "number"}, "description": "数字数组"}
            },
            "required": ["numbers"]
        }
    },
    {
        "name": "sum",
        "description": "计算总和",
        "inputSchema": {
            "type": "object",
            "properties": {
                "numbers": {"type": "array", "items": {"type": "number"}, "description": "数字数组"}
            },
            "required": ["numbers"]
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
            "result": {"name": "calculator-mcp-server", "version": "1.0.0"}
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
        
        if tool_name == "add":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            result = a + b
            result_text = f"{a} + {b} = {result}"
            
        elif tool_name == "subtract":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            result = a - b
            result_text = f"{a} - {b} = {result}"
            
        elif tool_name == "multiply":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            result = a * b
            result_text = f"{a} × {b} = {result}"
            
        elif tool_name == "divide":
            a = arguments.get("a", 0)
            b = arguments.get("b", 1)
            if b == 0:
                result_text = "错误：除数不能为0"
            else:
                result = a / b
                result_text = f"{a} ÷ {b} = {result}"
            
        elif tool_name == "power":
            base = arguments.get("base", 0)
            exponent = arguments.get("exponent", 1)
            result = base ** exponent
            result_text = f"{base} ^ {exponent} = {result}"
            
        elif tool_name == "sqrt":
            number = arguments.get("number", 0)
            if number < 0:
                result_text = "错误：不能计算负数的平方根"
            else:
                result = number ** 0.5
                result_text = f"√{number} = {result}"
            
        elif tool_name == "random":
            min_val = arguments.get("min", 0)
            max_val = arguments.get("max", 100)
            result = random.uniform(min_val, max_val)
            result_text = f"随机数({min_val}-{max_val}) = {result:.2f}"
            
        elif tool_name == "percentage":
            part = arguments.get("part", 0)
            total = arguments.get("total", 1)
            if total == 0:
                result_text = "错误：总数不能为0"
            else:
                percentage = (part / total) * 100
                result_text = f"{part} / {total} = {percentage:.2f}%"
            
        elif tool_name == "average":
            numbers = arguments.get("numbers", [])
            if not numbers:
                result_text = "错误：没有提供数字"
            else:
                average = sum(numbers) / len(numbers)
                result_text = f"平均值({', '.join(map(str, numbers))}) = {average:.2f}"
            
        elif tool_name == "sum":
            numbers = arguments.get("numbers", [])
            if not numbers:
                result_text = "错误：没有提供数字"
            else:
                total = sum(numbers)
                result_text = f"总和({', '.join(map(str, numbers))}) = {total}"
            
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
    """运行计算器MCP服务器"""
    print("🚀 启动计算器 MCP 服务器 (JSON-RPC模式)...", file=sys.stderr)
    
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
