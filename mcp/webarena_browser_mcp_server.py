#!/usr/bin/env python3
"""WebArena 浏览器自动化 MCP 服务器 - 基于 Playwright"""

import sys
import json
import base64
import asyncio
from typing import Dict, Any, Optional
from playwright.sync_api import sync_playwright, Page


class WebArenaBrowserServer:
    """WebArena 浏览器自动化 MCP 服务器"""

    def __init__(self):
        self.name = "webarena-browser"
        self.description = "WebArena 浏览器自动化：导航、点击、填表、截图、内容提取"
        self._playwright = None
        self._browser = None
        self._page = None

    def get_tools(self) -> list:
        return [
            {
                "name": "browser_navigate",
                "description": "导航到指定 URL",
                "parameters": {
                    "url": {"type": "string", "description": "目标 URL"},
                    "wait_until": {"type": "string", "description": "等待条件：load/networkidle/domcontentloaded", "enum": ["load", "networkidle", "domcontentloaded"], "default": "networkidle"}
                }
            },
            {
                "name": "browser_screenshot",
                "description": "截取当前页面截图（返回 base64 编码图片）",
                "parameters": {
                    "full_page": {"type": "boolean", "description": "是否截取全页", "default": False},
                    "path": {"type": "string", "description": "保存路径（可选）"}
                }
            },
            {
                "name": "browser_click",
                "description": "点击页面元素",
                "parameters": {
                    "selector": {"type": "string", "description": "CSS 选择器或文本"},
                    "text": {"type": "string", "description": "按钮/链接文本（模糊匹配）"}
                }
            },
            {
                "name": "browser_fill",
                "description": "填写输入框",
                "parameters": {
                    "selector": {"type": "string", "description": "CSS 选择器"},
                    "value": {"type": "string", "description": "填写内容"}
                }
            },
            {
                "name": "browser_type",
                "description": "在输入框中键入文本（追加模式）",
                "parameters": {
                    "selector": {"type": "string", "description": "CSS 选择器"},
                    "text": {"type": "string", "description": "要输入的文本"}
                }
            },
            {
                "name": "browser_select",
                "description": "从下拉菜单中选择选项",
                "parameters": {
                    "selector": {"type": "string", "description": "select 元素的 CSS 选择器"},
                    "value": {"type": "string", "description": "选项值"}
                }
            },
            {
                "name": "browser_get_text",
                "description": "获取页面文本内容",
                "parameters": {
                    "selector": {"type": "string", "description": "CSS 选择器（可选，不填则获取全部）"},
                    "max_length": {"type": "integer", "description": "最大返回字符数", "default": 5000}
                }
            },
            {
                "name": "browser_get_html",
                "description": "获取页面 HTML 内容",
                "parameters": {
                    "selector": {"type": "string", "description": "CSS 选择器（可选）"},
                    "max_length": {"type": "integer", "description": "最大返回字符数", "default": 10000}
                }
            },
            {
                "name": "browser_get_links",
                "description": "获取页面所有链接",
                "parameters": {}
            },
            {
                "name": "browser_back",
                "description": "后退一步",
                "parameters": {}
            },
            {
                "name": "browser_forward",
                "description": "前进一步",
                "parameters": {}
            },
            {
                "name": "browser_reload",
                "description": "重新加载页面",
                "parameters": {}
            },
            {
                "name": "browser_execute_js",
                "description": "执行 JavaScript 代码",
                "parameters": {
                    "script": {"type": "string", "description": "要执行的 JS 代码"}
                }
            },
            {
                "name": "browser_wait_for",
                "description": "等待元素出现",
                "parameters": {
                    "selector": {"type": "string", "description": "CSS 选择器"},
                    "timeout": {"type": "integer", "description": "超时毫秒数", "default": 10000}
                }
            },
            {
                "name": "browser_scroll",
                "description": "滚动页面",
                "parameters": {
                    "direction": {"type": "string", "description": "方向：up/down", "enum": ["up", "down"]},
                    "amount": {"type": "integer", "description": "滚动像素", "default": 500}
                }
            },
            {
                "name": "browser_close",
                "description": "关闭浏览器",
                "parameters": {}
            }
        ]

    def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._page = self._browser.new_page(viewport={"width": 1280, "height": 800})
        return self._page

    def handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        try:
            page = self._ensure_browser()

            if tool_name == "browser_navigate":
                url = arguments.get("url", "")
                wait_until = arguments.get("wait_until", "networkidle")
                page.goto(url, wait_until=wait_until)
                return {"success": True, "url": page.url, "title": page.title()}

            elif tool_name == "browser_screenshot":
                full_page = arguments.get("full_page", False)
                save_path = arguments.get("path")
                if save_path:
                    page.screenshot(path=save_path, full_page=full_page)
                    return {"success": True, "message": f"截图已保存到 {save_path}"}
                else:
                    screenshot = page.screenshot(full_page=full_page)
                    b64 = base64.b64encode(screenshot).decode()
                    return {"success": True, "screenshot_base64": b64, "mime_type": "image/png"}

            elif tool_name == "browser_click":
                selector = arguments.get("selector")
                text = arguments.get("text")
                if text:
                    page.get_by_text(text).click()
                elif selector:
                    page.locator(selector).click()
                else:
                    return {"success": False, "error": "需要提供 selector 或 text"}
                return {"success": True}

            elif tool_name == "browser_fill":
                selector = arguments.get("selector")
                value = arguments.get("value", "")
                page.locator(selector).fill(value)
                return {"success": True, "filled": value}

            elif tool_name == "browser_type":
                selector = arguments.get("selector")
                text = arguments.get("text", "")
                page.locator(selector).type(text)
                return {"success": True, "typed": text}

            elif tool_name == "browser_select":
                selector = arguments.get("selector")
                value = arguments.get("value", "")
                page.locator(selector).select_option(value)
                return {"success": True}

            elif tool_name == "browser_get_text":
                selector = arguments.get("selector")
                max_length = arguments.get("max_length", 5000)
                if selector:
                    text = page.locator(selector).inner_text()
                else:
                    text = page.inner_text("body")
                text = text.strip()
                return {"success": True, "text": text[:max_length]}

            elif tool_name == "browser_get_html":
                selector = arguments.get("selector")
                max_length = arguments.get("max_length", 10000)
                if selector:
                    html = page.locator(selector).inner_html()
                else:
                    html = page.content()
                html = html.strip()
                return {"success": True, "html": html[:max_length]}

            elif tool_name == "browser_get_links":
                links = page.locator("a[href]").all()
                result = []
                for link in links:
                    href = link.get_attribute("href")
                    text = link.inner_text().strip()[:100]
                    if href and text:
                        result.append({"text": text, "url": href})
                return {"success": True, "links": result[:50]}

            elif tool_name == "browser_back":
                page.goBack()
                return {"success": True, "url": page.url}

            elif tool_name == "browser_forward":
                page.goForward()
                return {"success": True, "url": page.url}

            elif tool_name == "browser_reload":
                page.reload(wait_until="networkidle")
                return {"success": True, "url": page.url, "title": page.title()}

            elif tool_name == "browser_execute_js":
                script = arguments.get("script", "")
                result = page.evaluate(script)
                return {"success": True, "result": result}

            elif tool_name == "browser_wait_for":
                selector = arguments.get("selector")
                timeout = arguments.get("timeout", 10000)
                page.wait_for_selector(selector, timeout=timeout)
                return {"success": True, "message": f"元素已出现: {selector}"}

            elif tool_name == "browser_scroll":
                direction = arguments.get("direction", "down")
                amount = arguments.get("amount", 500)
                if direction == "down":
                    page.evaluate(f"window.scrollBy(0, {amount})")
                else:
                    page.evaluate(f"window.scrollBy(0, -{amount})")
                return {"success": True}

            elif tool_name == "browser_close":
                self._close_browser()
                return {"success": True, "message": "浏览器已关闭"}

            else:
                return {"success": False, "error": f"未知工具: {tool_name}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _close_browser(self):
        """关闭浏览器"""
        if self._page:
            self._page = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None


# ── MCP JSON-RPC 协议处理 ──

def handle_request(request: dict) -> dict:
    """处理 MCP 请求"""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")

    # 初始化
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "webarena-browser", "version": "1.0.0"}
            }
        }

    # 工具列表
    if method == "tools/list":
        server = WebArenaBrowserServer()
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": server.get_tools()}
        }

    # 工具调用
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        server = WebArenaBrowserServer()
        result = server.handle_tool_call(name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result)}]}
        }

    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {method}"}, "id": request_id}


def main():
    """主入口 - stdio 模式"""
    print("WebArena Browser MCP Server started", file=sys.stderr)
    
    while True:
        line = sys.stdin.readline()
        if not line:
            break
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
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": None}))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
