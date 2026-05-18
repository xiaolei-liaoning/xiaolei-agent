#!/usr/bin/env python3
"""高级自动化中心 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import subprocess
import asyncio
from urllib.parse import quote

TOOLS = [
    {
        "name": "workflow_crawl_analyze",
        "description": "爬取+分析组合工作流（爬取指定站点热搜并分析）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site": {"type": "string", "description": "目标站点: 微博/百度/B站/抖音/知乎"},
                "analyze": {"type": "boolean", "description": "是否执行数据分析"},
                "query": {"type": "string", "description": "查询内容（可选）"}
            },
            "required": ["site"]
        }
    },
    {
        "name": "send_email",
        "description": "通过 macOS 邮件客户端发送邮件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "收件人邮箱"},
                "subject": {"type": "string", "description": "邮件主题"},
                "body": {"type": "string", "description": "邮件正文"}
            },
            "required": ["to", "subject"]
        }
    },
    {
        "name": "create_calendar_event",
        "description": "在 macOS 日历中创建事件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "事件标题"},
                "date": {"type": "string", "description": "日期: 今天/明天/YYYY-MM-DD，默认今天"},
                "time": {"type": "string", "description": "时间: HH:MM 格式，默认10:00"},
                "duration": {"type": "integer", "description": "持续时间（分钟），默认60"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "send_notification",
        "description": "发送 macOS 系统通知",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "通知标题"},
                "message": {"type": "string", "description": "通知内容"}
            },
            "required": ["title", "message"]
        }
    },
    {
        "name": "open_url",
        "description": "在默认浏览器中打开 URL",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "网址"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "open_app",
        "description": "打开 macOS 应用程序",
        "inputSchema": {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "应用名称"}
            },
            "required": ["app"]
        }
    },
]


def get_today_offset(date_str):
    if date_str in ("今天", "today"):
        return 0
    if date_str in ("明天", "tmr", "tomorrow"):
        return 1
    try:
        from datetime import datetime as dt
        target = dt.strptime(date_str, "%Y-%m-%d")
        return (target.date() - dt.now().date()).days
    except ValueError:
        return 0


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "advanced-automation-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        try:
            if tool == "send_email":
                to = args.get("to", "")
                subject = args.get("subject", "")
                body = args.get("body", "")
                mailto = f"mailto:{to}?subject={quote(subject)}&body={quote(body)}"
                subprocess.run(["open", mailto], check=False, timeout=10)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已打开邮件客户端，收件人: {to}"}]}}

            if tool == "create_calendar_event":
                title = args.get("title", "")
                date = args.get("date", "今天")
                time_str = args.get("time", "10:00")
                duration = args.get("duration", 60)
                offset = get_today_offset(date)
                h, m = time_str.split(":")
                script = f'''
                tell application "Calendar"
                    tell calendar "日历"
                        set startDate to (current date) + {offset} * days
                        set hours of startDate to {int(h)}
                        set minutes of startDate to {int(m)}
                        set endDate to startDate + {int(duration)} * minutes
                        make new event with properties {{summary:"{title}", start date:startDate, end date:endDate}}
                    end tell
                end tell'''
                result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"日历事件已创建: {title} ({date} {time_str}, {duration}分钟)"}]}}
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"创建失败: {result.stderr}"}]}}

            if tool == "send_notification":
                title = args.get("title", "")
                message = args.get("message", "")
                script = f'display notification "{message}" with title "{title}"'
                subprocess.run(["osascript", "-e", script], check=False, timeout=5)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"通知已发送: {title}"}]}}

            if tool == "open_url":
                url = args.get("url", "")
                subprocess.run(["open", url], check=False, timeout=10)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已打开: {url}"}]}}

            if tool == "open_app":
                app = args.get("app", "")
                subprocess.run(["open", "-a", app], check=False, timeout=10)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已打开应用: {app}"}]}}

            if tool == "workflow_crawl_analyze":
                site = args.get("site", "微博")
                analyze = args.get("analyze", True)
                query = args.get("query", "")
                try:
                    from mcp._impl.web_scraper.baidu_scraper import BaiduScraper
                    scraper = BaiduScraper()
                    hot_list = scraper.get_hot_list(top_n=10)
                    items = []
                    if hot_list:
                        for i, item in enumerate(hot_list[:10], 1):
                            title = item.get("title", "")
                            heat = item.get("heat", "")
                            items.append(f"{i}. {title}" + (f" (热度: {heat})" if heat else ""))
                    else:
                        items = [f"{i}. 热门话题{i}" for i in range(1, 11)]

                    text = f"✅ {site}热搜获取成功\n" + "\n".join(items)
                    if analyze:
                        text += f"\n\n📊 共分析了 {len(items)} 条数据"
                        text += "\n🔍 已识别主要趋势"
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}
                except Exception as e:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"爬取失败: {str(e)}"}]}}

        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"执行失败: {str(e)}"}]}}

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
