#!/usr/bin/env python3
"""
有趣的 MCP 服务器 - 使用JSON-RPC协议
"""

import asyncio
import sys
import random
import json

# 笑话库
JOKES = [
    "为什么程序员喜欢黑暗？因为他们是guru！",
    "一只蜗牛爬上了苹果树，树上的毛毛虫问它：你是谁？蜗牛说：我是蜗牛。毛毛虫说：那你为什么背着房子？蜗牛说：因为我是蜗牛啊！",
    "程序员的老婆让他去买牛奶，他回来的时候手里拿着10盒牛奶。老婆问他为什么买这么多，他说：因为超市在搞买一送九的活动！",
    "为什么数学书总是很悲伤？因为它有太多的问题。",
    "一只企鹅走进酒吧，问酒保：你们这里有鱼吗？酒保说：没有。第二天企鹅又来了，问：你们这里有鱼吗？酒保说：没有！第三天企鹅又来了，问：你们这里有鱼吗？酒保说：再问我就用锤子砸你！第四天企鹅又来了，问：你们这里有锤子吗？酒保说：没有。企鹅说：那你们这里有鱼吗？",
    "为什么Python程序员不喜欢出门？因为他们喜欢缩进！",
    "什么东西越洗越脏？答案：水！",
]

# 谜语库
RIDDLES = [
    {"question": "什么东西早上四条腿，中午两条腿，晚上三条腿？", "answer": "人（婴儿爬行、成人走路、老人拄拐杖）"},
    {"question": "什么东西打破了才能用？", "answer": "鸡蛋"},
    {"question": "什么东西越洗越脏？", "answer": "水"},
    {"question": "什么东西有头无脚？", "answer": "砖头"},
    {"question": "什么东西天天熬夜？", "answer": "熊猫（有黑眼圈）"},
]

# 冷知识库
FUN_FACTS = [
    "蜜蜂的翅膀每分钟拍打11400次。",
    "章鱼有三个心脏。",
    "香蕉是浆果，但草莓不是。",
    "月球上有一面美国国旗，但由于没有大气，它已经变成白色了。",
    "人类的大脑在夜间会产生比白天更多的褪黑素。",
    "蜗牛可以睡三年。",
]

# ASCII艺术库
ASCII_ARTS = {
    "cat": """
  /\\_/\\  
 ( o.o ) 
  > ^ <
""",
    "dog": """
  / \\__
 (    @\\___
 /         O
/   (_____/
\\_______/
""",
    "rocket": """
   /**\\
  /***\\
 /*****\\
|       |
|       |
|       |
\\       /
 \\_____/
""",
    "heart": """
  ♥♥♥♥♥♥
♥♥♥♥♥♥♥♥♥♥
♥♥♥♥♥♥♥♥♥♥
  ♥♥♥♥♥♥
    ♥♥♥♥
      ♥♥
""",
}

# 星座运势
HOROSCOPES = {
    "aries": "今天是充满活力的一天！适合开始新计划。",
    "taurus": "财运不错，但要注意健康。",
    "gemini": "社交活动丰富，会遇到有趣的人。",
    "cancer": "家庭生活和谐，适合陪伴家人。",
    "leo": "自信心爆棚，适合展示自己。",
    "virgo": "工作效率高，注意细节。",
    "libra": "人际关系良好，适合合作。",
    "scorpio": "直觉敏锐，适合做决策。",
    "sagittarius": "旅行运佳，适合探索新事物。",
    "capricorn": "事业运上升，努力有回报。",
    "aquarius": "创新思维活跃，适合尝试新方法。",
    "pisces": "艺术灵感丰富，适合创作。",
}

# 可用工具列表
TOOLS = [
    {
        "name": "get_joke",
        "description": "获取一个随机笑话",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_riddle",
        "description": "获取一个谜语（包含答案）",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_fun_fact",
        "description": "获取一个有趣的冷知识",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_ascii_art",
        "description": "获取ASCII艺术图案",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "图案类型: cat, dog, rocket, heart"
                }
            },
            "required": ["type"]
        }
    },
    {
        "name": "get_horoscope",
        "description": "获取星座运势",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sign": {
                    "type": "string",
                    "description": "星座名称"
                }
            },
            "required": ["sign"]
        }
    },
    {
        "name": "roll_dice",
        "description": "掷骰子",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sides": {"type": "number", "description": "骰子面数"},
                "count": {"type": "number", "description": "骰子数量"}
            },
            "required": []
        }
    },
    {
        "name": "magic_8ball",
        "description": "魔法8球 - 回答你的问题",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "你的问题"}
            },
            "required": ["question"]
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
            "result": {"name": "fun-mcp-server", "version": "1.0.0"}
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
        
        if tool_name == "get_joke":
            result_text = random.choice(JOKES)
            
        elif tool_name == "get_riddle":
            riddle = random.choice(RIDDLES)
            result_text = f"❓ 谜语: {riddle['question']}\n\n🎯 答案: {riddle['answer']}"
            
        elif tool_name == "get_fun_fact":
            result_text = random.choice(FUN_FACTS)
            
        elif tool_name == "get_ascii_art":
            art_type = arguments.get("type", "cat")
            result_text = ASCII_ARTS.get(art_type, "未知图案类型")
            
        elif tool_name == "get_horoscope":
            sign = arguments.get("sign", "aries")
            result_text = HOROSCOPES.get(sign, "未知星座")
            
        elif tool_name == "roll_dice":
            sides = int(arguments.get("sides", 6))
            count = int(arguments.get("count", 1))
            rolls = [random.randint(1, sides) for _ in range(count)]
            total = sum(rolls)
            result_text = f"🎲 掷骰子结果: {', '.join(map(str, rolls))}\n\n📊 总和: {total}"
            
        elif tool_name == "magic_8ball":
            answers = [
                "✅ 肯定", "❌ 否定", "🤔 不确定", "🌟 可能性很大",
                "🌙 晚上再问", "🔥 时机未到", "💡 好主意", "🌈 会有惊喜",
                "⚡ 小心行事", "💝 顺其自然", "🎯 目标明确", "🎲 试试运气"
            ]
            question = arguments.get("question", "")
            result_text = f"🤔 问题: {question}\n\n🔮 魔法8球回答: {random.choice(answers)}"
            
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
    """运行趣味MCP服务器"""
    print("🚀 启动趣味 MCP 服务器 (JSON-RPC模式)...", file=sys.stderr)
    
    reader = asyncio.StreamReader()
    protocol = asyncio.Protocol()
    
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