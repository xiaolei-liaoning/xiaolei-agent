#!/usr/bin/env python3
"""
天气查询 MCP 服务器 - 使用JSON-RPC协议
"""

import asyncio
import sys
import random
import json

# 模拟天气数据
WEATHER_DATA = {
    "beijing": {
        "city": "北京",
        "temperature": "25°C",
        "weather": ["晴天", "多云", "阴天", "小雨"],
        "wind": ["微风", "东风3级", "西北风2级"],
        "humidity": "45%"
    },
    "shanghai": {
        "city": "上海",
        "temperature": "28°C",
        "weather": ["晴天", "多云", "雷阵雨"],
        "wind": ["东南风4级", "微风"],
        "humidity": "65%"
    },
    "guangzhou": {
        "city": "广州",
        "temperature": "32°C",
        "weather": ["晴天", "多云", "暴雨"],
        "wind": ["南风2级", "台风"],
        "humidity": "85%"
    },
    "chengdu": {
        "city": "成都",
        "temperature": "22°C",
        "weather": ["阴天", "小雨", "多云"],
        "wind": ["北风1级", "微风"],
        "humidity": "75%"
    },
    "hangzhou": {
        "city": "杭州",
        "temperature": "26°C",
        "weather": ["晴天", "多云", "小雨"],
        "wind": ["东风2级", "微风"],
        "humidity": "60%"
    },
    "shenzhen": {
        "city": "深圳",
        "temperature": "30°C",
        "weather": ["晴天", "多云", "雷阵雨"],
        "wind": ["西南风3级"],
        "humidity": "78%"
    },
}

# 可用工具列表
TOOLS = [
    {
        "name": "get_weather",
        "description": "查询指定城市的天气",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称: beijing, shanghai, guangzhou, chengdu, hangzhou, shenzhen"
                }
            },
            "required": ["city"]
        }
    },
    {
        "name": "get_weather_forecast",
        "description": "获取未来几天的天气预报",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称"
                },
                "days": {
                    "type": "number",
                    "description": "预报天数"
                }
            },
            "required": ["city"]
        }
    },
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
            "result": {"name": "weather-mcp-server", "version": "1.0.0"}
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
        
        if tool_name == "get_weather":
            city = arguments.get("city", "beijing")
            data = WEATHER_DATA.get(city, WEATHER_DATA["beijing"])
            result_text = f"""
🌤️  {data['city']}天气

温度: {data['temperature']}
天气: {random.choice(data['weather'])}
风向: {random.choice(data['wind'])}
湿度: {data['humidity']}
"""
            
        elif tool_name == "get_weather_forecast":
            city = arguments.get("city", "beijing")
            days = int(arguments.get("days", 3))
            data = WEATHER_DATA.get(city, WEATHER_DATA["beijing"])
            
            forecast = []
            for i in range(1, days + 1):
                temp = int(data['temperature'][:-2]) + random.randint(-3, 3)
                forecast.append(f"📅 第{i}天: {random.choice(data['weather'])} {temp}°C")
            
            result_text = f"""
📊 {data['city']}未来{days}天预报

{'\n'.join(forecast)}
"""
        
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
    """运行天气MCP服务器"""
    print("🚀 启动天气查询 MCP 服务器 (JSON-RPC模式)...", file=sys.stderr)
    
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