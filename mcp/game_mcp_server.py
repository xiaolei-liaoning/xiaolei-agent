#!/usr/bin/env python3
"""游戏 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import random
import asyncio

TOOLS = [
    {
        "name": "guess_number",
        "description": "猜数字游戏（1-100），开始新游戏或猜测数字",
        "inputSchema": {
            "type": "object",
            "properties": {
                "guess": {"type": "integer", "description": "猜测的数字（不提供则开始新游戏）"},
                "reset": {"type": "boolean", "description": "重置游戏"}
            }
        }
    },
    {
        "name": "rps",
        "description": "石头剪刀布游戏",
        "inputSchema": {
            "type": "object",
            "properties": {
                "choice": {"type": "string", "description": "你的选择: rock/stone/r(石头), scissors/s(剪刀), paper/p(布)"},
                "reset": {"type": "boolean", "description": "重置比分"}
            }
        }
    },
    {
        "name": "dice",
        "description": "掷骰子",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rolls": {"type": "string", "description": "骰子表达式，如 1d6（1个6面骰）, 2d6（2个6面骰）, 默认1d6"},
                "reset": {"type": "boolean", "description": "重置游戏"}
            }
        }
    },
]

# 游戏状态
guess_game = None
rps_score = {"win": 0, "lose": 0, "draw": 0}


async def handle_request(request):
    global guess_game, rps_score

    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "game-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        if tool == "guess_number":
            if args.get("reset") or guess_game is None:
                guess_game = {"target": random.randint(1, 100), "attempts": 0, "max": 10}
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "🔢 猜数字游戏开始！\n猜一个1-100之间的数字，你有10次机会。"}]}}

            guess = args.get("guess")
            if guess is None:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请输入一个数字猜测，或设置 reset=True 重置"}]}}

            try:
                g = int(guess)
            except (ValueError, TypeError):
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请输入有效数字"}]}}

            guess_game["attempts"] += 1
            remaining = guess_game["max"] - guess_game["attempts"]

            if g == guess_game["target"]:
                target = guess_game["target"]
                attempts = guess_game["attempts"]
                guess_game = None
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"🎉 恭喜！猜对了！数字就是 {target}，共 {attempts} 次。"}]}}

            hint = "再大一点！" if g < guess_game["target"] else "再小一点！"
            if remaining <= 0:
                target = guess_game["target"]
                guess_game = None
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"😢 游戏结束！正确数字是 {target}"}]}}

            direction = "📈 太小了！" if g < guess_game["target"] else "📉 太大了！"
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"{direction} {hint} 剩余机会: {remaining}"}]}}

        if tool == "rps":
            if args.get("reset"):
                rps_score = {"win": 0, "lose": 0, "draw": 0}
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "✊✋✌️ 比分已重置！"}]}}

            player = args.get("choice")
            if player is None:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请输入 choice: rock/stone/r(石头), scissors/s(剪刀), paper/p(布)"}]}}

            choice_map = {"rock": 0, "stone": 0, "r": 0, "石头": 0,
                          "scissors": 1, "s": 1, "剪刀": 1,
                          "paper": 2, "p": 2, "布": 2}
            pc = choice_map.get(str(player).lower(), -1)
            if pc == -1:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "无效选择！请使用 rock/stone/r, scissors/s, paper/p"}]}}

            ai = random.randint(0, 2)
            names = ["石头", "剪刀", "布"]

            if pc == ai:
                result = "draw"
                rps_score["draw"] += 1
                msg = "🤝 平局！"
            elif (pc + 1) % 3 == ai:
                result = "win"
                rps_score["win"] += 1
                msg = "🎉 你赢了！"
            else:
                result = "lose"
                rps_score["lose"] += 1
                msg = "😢 你输了！"

            text = f"{msg}\n你出: {names[pc]}\nAI出: {names[ai]}\n比分: {rps_score['win']}-{rps_score['lose']}-{rps_score['draw']}"
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

        if tool == "dice":
            if args.get("reset"):
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "🎲 骰子已重置！\n使用 rolls='1d6' 或 '2d6'"}]}}

            rolls = str(args.get("rolls", "1d6"))
            try:
                parts = rolls.split("d")
                count = max(1, min(int(parts[0]) if parts[0] else 1, 100))
                sides = int(parts[1]) if len(parts) == 2 and parts[1] else 6
            except (ValueError, IndexError):
                count, sides = 1, 6

            results = [random.randint(1, sides) for _ in range(count)]
            total = sum(results)
            text = f"🎲 {count}d{sides}: {results}\n总计: {total}"
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

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
