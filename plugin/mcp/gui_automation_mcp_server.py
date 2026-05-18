#!/usr/bin/env python3
"""GUI 自动化 MCP 服务器（macOS）"""

import json
import sys
from typing import List, Dict, Any


class GUIAutomationMCPServer:
    """GUI 自动化 MCP 服务器"""

    def __init__(self):
        self.name = "gui-automation"
        self.description = "macOS GUI 自动化操作服务"

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "open_app",
                "description": "打开应用程序",
                "parameters": {
                    "app": {"type": "string", "description": "应用名称（如 Safari, 微信）", "required": True}
                }
            },
            {
                "name": "open_url",
                "description": "在浏览器中打开URL",
                "parameters": {
                    "url": {"type": "string", "description": "网址", "required": True},
                    "app": {"type": "string", "description": "浏览器名称", "required": False}
                }
            },
            {
                "name": "quit_app",
                "description": "退出应用程序",
                "parameters": {
                    "app": {"type": "string", "description": "应用名称", "required": True}
                }
            },
            {
                "name": "type_text",
                "description": "模拟键盘输入文本",
                "parameters": {
                    "text": {"type": "string", "description": "要输入的文本", "required": True}
                }
            },
            {
                "name": "screenshot",
                "description": "截取屏幕截图",
                "parameters": {}
            },
            {
                "name": "volume_up",
                "description": "提高系统音量",
                "parameters": {
                    "amount": {"type": "integer", "description": "增量（1-100）", "required": False}
                }
            },
            {
                "name": "volume_down",
                "description": "降低系统音量",
                "parameters": {
                    "amount": {"type": "integer", "description": "减量（1-100）", "required": False}
                }
            },
            {
                "name": "brightness_up",
                "description": "提高屏幕亮度",
                "parameters": {
                    "amount": {"type": "integer", "description": "增量（1-100）", "required": False}
                }
            },
            {
                "name": "brightness_down",
                "description": "降低屏幕亮度",
                "parameters": {
                    "amount": {"type": "integer", "description": "减量（1-100）", "required": False}
                }
            },
        ]

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action_map = {
                "open_app": "open_app",
                "open_url": "open_url",
                "quit_app": "quit_app",
                "type_text": "type_text",
                "screenshot": "screenshot",
                "volume_up": "volume_adjust",
                "volume_down": "volume_adjust",
                "brightness_up": "brightness_adjust",
                "brightness_down": "brightness_adjust",
            }
            action = action_map.get(name)
            if not action:
                return {"success": False, "error": f"未知工具: {name}"}

            kwargs = dict(args)
            if "volume_up" in name:
                kwargs["action_type"] = "increase"
            elif "volume_down" in name:
                kwargs["action_type"] = "decrease"
            elif "brightness_up" in name:
                kwargs["action_type"] = "increase"
            elif "brightness_down" in name:
                kwargs["action_type"] = "decrease"

            handler = self._get_handler()
            result = handler.execute(action=action, **kwargs)
            return {"success": result.get("success", True), "result": result.get("reply", str(result))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_handler(self):
        from mcp._impl.gui_automation.handler import gui_handler
        return gui_handler


server = GUIAutomationMCPServer()


def handle_request(request: dict) -> dict:
    method = request.get("method", "")
    if method == "list_tools" or method == "tools":
        return {"jsonrpc": "2.0", "result": server.get_tools(), "id": request.get("id")}
    elif method == "call" or method == "callTool":
        tool_name = request.get("params", {}).get("name")
        args = request.get("params", {}).get("arguments", {})
        result = server.call_tool(tool_name, args)
        return {
            "jsonrpc": "2.0",
            "result": {"success": result["success"], "content": [{"text": str(result.get("result", ""))}]},
            "id": request.get("id")
        }
    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": request.get("id")}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
