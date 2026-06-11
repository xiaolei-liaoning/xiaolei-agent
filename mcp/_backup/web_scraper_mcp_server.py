#!/usr/bin/env python3
"""网页爬虫 MCP 服务器"""

import json
import sys
import logging
from typing import List, Dict, Any


class WebScraperMCPServer:
    """网页爬虫 MCP 服务器"""

    def __init__(self):
        self.name = "web-scraper"
        self.description = "网页数据爬取服务"

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "scrape_weibo",
                "description": "爬取微博热搜",
                "parameters": {
                    "top_n": {"type": "integer", "description": "返回条数", "required": False}
                }
            },
            {
                "name": "scrape_baidu",
                "description": "爬取百度热搜",
                "parameters": {
                    "top_n": {"type": "integer", "description": "返回条数", "required": False}
                }
            },
            {
                "name": "scrape_zhihu",
                "description": "爬取知乎热榜",
                "parameters": {
                    "top_n": {"type": "integer", "description": "返回条数", "required": False}
                }
            },
            {
                "name": "scrape_bilibili",
                "description": "爬取B站热门视频",
                "parameters": {
                    "top_n": {"type": "integer", "description": "返回条数", "required": False}
                }
            },
            {
                "name": "scrape_douyin",
                "description": "爬取抖音热搜",
                "parameters": {
                    "top_n": {"type": "integer", "description": "返回条数", "required": False}
                }
            },
            {
                "name": "scrape_github_trending",
                "description": "爬取GitHub趋势项目",
                "parameters": {
                    "top_n": {"type": "integer", "description": "返回条数", "required": False}
                }
            },
            {
                "name": "search_web",
                "description": "通用网页搜索",
                "parameters": {
                    "keyword": {"type": "string", "description": "搜索关键词", "required": True},
                    "top_n": {"type": "integer", "description": "返回条数", "required": False}
                }
            },
        ]

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            top_n = args.get("top_n", 10)
            site_action = {
                "scrape_weibo": ("微博", "热搜top10"),
                "scrape_baidu": ("百度", "热搜top10"),
                "scrape_zhihu": ("知乎", "热榜"),
                "scrape_bilibili": ("B站", "热门视频"),
                "scrape_douyin": ("抖音", "热搜"),
                "scrape_github_trending": ("GitHub", "trending"),
            }
            if name in site_action:
                site, action = site_action[name]
                result = self._dispatch(site, action, top_n)
                return {"success": True, "result": result}
            elif name == "search_web":
                keyword = args.get("keyword", "")
                result = self._dispatch("通用搜索", "搜索", top_n, keyword=keyword)
                return {"success": True, "result": result}
            return {"success": False, "error": f"未知工具: {name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _dispatch(self, site: str, action: str, top_n: int = 10, **kwargs):
        """委托给 ScraperDispatcher"""
        try:
            from mcp._impl.web_scraper.handler import dispatcher
            params = {"site_name": site, "action": action, "top_n": top_n}
            params.update(kwargs)
            result = dispatcher.execute(site, action=action, params=params)
            return result.get("reply", str(result))
        except Exception as e:
            return f"[爬虫错误] {e}"


server = WebScraperMCPServer()


def handle_request(request: dict) -> dict:
    method = request.get("method", "")

    if method == "list_tools" or method == "tools":
        return {
            "jsonrpc": "2.0",
            "result": server.get_tools(),
            "id": request.get("id")
        }

    elif method == "call" or method == "callTool":
        tool_name = request.get("params", {}).get("name")
        args = request.get("params", {}).get("arguments", {})
        result = server.call_tool(tool_name, args)
        return {
            "jsonrpc": "2.0",
            "result": {
                "success": result["success"],
                "content": [{"text": str(result.get("result", ""))}]
            },
            "id": request.get("id")
        }

    return {
        "jsonrpc": "2.0",
        "error": {"code": -32601, "message": "Method not found"},
        "id": request.get("id")
    }


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
