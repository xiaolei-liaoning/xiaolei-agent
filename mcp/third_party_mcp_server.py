#!/usr/bin/env python3
"""第三方应用集成 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import asyncio

TOOLS = [
    {
        "name": "list_apps",
        "description": "列出所有已配置的第三方应用",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "execute_app",
        "description": "执行第三方应用的操作",
        "inputSchema": {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "应用名称: twitter/discord/jira/wechat/dingtalk/feishu/github"},
                "action": {"type": "string", "description": "操作名称"},
                "params": {"type": "object", "description": "操作参数字典"}
            },
            "required": ["app"]
        }
    },
    {
        "name": "app_info",
        "description": "获取指定应用的配置和功能信息",
        "inputSchema": {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "应用名称"}
            },
            "required": ["app"]
        }
    },
]

_app_manager = None


def get_manager():
    global _app_manager
    if _app_manager is None:
        from mcp._impl.third_party.handler import app_manager
        _app_manager = app_manager
    return _app_manager


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "third-party-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        try:
            mgr = get_manager()

            if tool == "list_apps":
                apps = list(mgr.apps.keys())
                if not apps:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "暂未配置第三方应用"}]}}
                lines = [f"📱 已配置的第三方应用 ({len(apps)} 个):"]
                for app in apps:
                    app_obj = mgr.get_app(app)
                    desc = getattr(app_obj, "config", {}).get("description", "")
                    lines.append(f"  • {app}" + (f" — {desc}" if desc else ""))
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": '\n'.join(lines)}]}}

            if tool == "app_info":
                app_name = args.get("app", "")
                app_obj = mgr.get_app(app_name)
                if not app_obj:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"应用不存在: {app_name}"}]}}
                cfg = app_obj.config
                info = (
                    f"📱 {app_name}\n"
                    f"  名称: {cfg.get('name', app_name)}\n"
                    f"  认证方式: {cfg.get('auth_method', 'api_key')}\n"
                    f"  API地址: {cfg.get('api_url', '未配置')}\n"
                    f"  描述: {cfg.get('description', '无')}"
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": info}]}}

            if tool == "execute_app":
                app_name = args.get("app", "")
                action = args.get("action", "get_info")
                execute_params = args.get("params", {})

                app_obj = mgr.get_app(app_name)
                if not app_obj:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"应用不存在或未配置: {app_name}"}]}}

                result = await mgr.execute(app_name, action, execute_params)
                if result.get("success"):
                    data = result.get("data", {})
                    if isinstance(data, dict):
                        text = f"✅ {app_name} {action} 成功\n" + '\n'.join(f"{k}: {v}" for k, v in data.items() if not isinstance(v, dict))
                    else:
                        text = f"✅ {app_name} {action} 成功: {data}"
                else:
                    error = result.get("error", result.get("data", {}).get("error", "未知错误"))
                    if "密钥未配置" in str(error) or "API key" in str(error).lower():
                        text = f"⚠️ {app_name} 需要在 mcp/_impl/third_party/config.yml 中配置API密钥"
                    else:
                        text = f"❌ {app_name} 执行失败: {error}"
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
