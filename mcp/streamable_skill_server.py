#!/usr/bin/env python3
"""
Streamable HTTP MCP Skill Server
复杂能力型 Skills 的 HTTP/SSE 模式 MCP 服务器

支持的 Skill 分类（能力密集型）：
- product: 产品能力、市场研究、战略压缩
- content: 文章写作、内容引擎、品牌声音
- media: 视频编辑、AI 媒体生成
- ai: 深度研究、文档查询

Usage:
  python mcp/streamable_skill_server.py --port 6283

注册到 .mcp.json:
  {
    "mcpServers": {
      "skill-server-http": {
        "type": "http",
        "url": "http://127.0.0.1:6283/mcp"
      }
    }
  }
"""

import os
import sys
import json
import asyncio
import logging
import argparse
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs

# 复用 stdio 版本的技能加载
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SERVER_DIR)

# 动态导入 stdio 模块（确保 parent dir 在路径中）
sys.path.insert(0, os.path.dirname(SERVER_DIR))
from skill_mcp_server import SkillMCPServer, scan_all_skills, get_skill_content, SKILL_CATEGORIES

logger = logging.getLogger(__name__)


class StreamableSkillHTTPServer:
    """Streamable HTTP MCP Server for Skills"""

    def __init__(self, host: str = "127.0.0.1", port: int = 6283):
        self.host = host
        self.port = port
        self.name = "skill-server-http"
        self.version = "2.0.0"
        self.skill_server = SkillMCPServer()
        self.sse_clients: List[asyncio.Queue] = []
        logger.info(f"🚀 Streamable Skill HTTP Server v{self.version}")
        logger.info(f"📂 已加载 {len(self.skill_server.skills)} 个技能")
        cats = self.skill_server.get_categories()
        for cat, names in sorted(cats.items()):
            logger.info(f"   {cat}: {len(names)} skills")

    async def handle_mcp_request(self, body: dict) -> dict:
        """处理 JSON-RPC MCP 请求"""
        return await self.skill_server.handle_request(body)

    async def handle_http_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """处理 HTTP 连接"""
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                return

            request_str = request_line.decode("utf-8").strip()
            parts = request_str.split(" ")
            if len(parts) < 2:
                writer.close()
                return

            method = parts[0]
            path = parts[1]

            # 读取 headers
            headers = {}
            while True:
                header_line = await reader.readline()
                header_str = header_line.decode("utf-8").strip()
                if not header_str:
                    break
                if ":" in header_str:
                    key, val = header_str.split(":", 1)
                    headers[key.strip().lower()] = val.strip()

            content_length = int(headers.get("content-length", 0))

            if method == "GET":
                if path == "/health":
                    await self._send_json(writer, 200, {
                        "status": "ok",
                        "server": self.name,
                        "skills_count": len(self.skill_server.skills)
                    })
                    return
                elif path == "/sse":
                    await self._handle_sse(writer)
                    return
                else:
                    await self._send_text(writer, 404, "Not Found")
                    return

            elif method == "POST":
                if path == "/mcp":
                    # 读取 body
                    body_bytes = await reader.read(content_length) if content_length > 0 else b"{}"
                    try:
                        request = json.loads(body_bytes)
                    except json.JSONDecodeError:
                        await self._send_json(writer, 400, {
                            "jsonrpc": "2.0", "id": 0,
                            "error": {"code": -32700, "message": "Parse error"}
                        })
                        return

                    # 处理请求
                    response = await self.handle_mcp_request(request)

                    # 检测是否需要流式响应
                    is_streaming = (
                        request.get("method") == "callTool"
                        and request.get("params", {}).get("name") in ("skill_execute", "skill_agent_run")
                        and "stream" in str(json.dumps(request))
                    )

                    if is_streaming:
                        await self._send_sse_event(writer, response)
                    else:
                        await self._send_json(writer, 200, response)
                    return

            await self._send_text(writer, 404, "Not Found")

        except Exception as e:
            logger.error(f"HTTP handler error: {e}")
            try:
                await self._send_json(writer, 500, {"error": str(e)})
            except Exception:
                pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _send_json(self, writer: asyncio.StreamReader, status: int, data: dict):
        """发送 JSON 响应"""
        body = json.dumps(data, ensure_ascii=False)
        response = (
            f"HTTP/1.1 {status} {'OK' if status == 200 else 'Error'}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body.encode('utf-8'))}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Access-Control-Allow-Methods: POST, GET, OPTIONS\r\n"
            f"Access-Control-Allow-Headers: Content-Type\r\n"
            f"\r\n"
            f"{body}"
        )
        writer.write(response.encode("utf-8"))
        await writer.drain()

    async def _send_text(self, writer: asyncio.StreamReader, status: int, text: str):
        """发送纯文本响应"""
        response = (
            f"HTTP/1.1 {status} {'OK' if status == 200 else 'Error'}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(text.encode('utf-8'))}\r\n"
            f"\r\n"
            f"{text}"
        )
        writer.write(response.encode("utf-8"))
        await writer.drain()

    async def _handle_sse(self, writer: asyncio.StreamReader):
        """处理 SSE 连接"""
        response = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: text/event-stream\r\n"
            f"Cache-Control: no-cache\r\n"
            f"Connection: keep-alive\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"\r\n"
        )
        writer.write(response.encode("utf-8"))
        await writer.drain()

        queue: asyncio.Queue = asyncio.Queue()
        self.sse_clients.append(queue)

        try:
            while True:
                event = await queue.get()
                sse_data = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                writer.write(sse_data.encode("utf-8"))
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self.sse_clients.remove(queue)

    async def _send_sse_event(self, writer: asyncio.StreamReader, data: dict):
        """通过 SSE 发送事件"""
        sse_data = f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        response = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: text/event-stream\r\n"
            f"Cache-Control: no-cache\r\n"
            f"\r\n"
            f"{sse_data}"
        )
        writer.write(response.encode("utf-8"))
        await writer.drain()

    async def start(self):
        """启动 HTTP 服务器"""
        server = await asyncio.start_server(
            self.handle_http_request, self.host, self.port
        )
        addr = server.sockets[0].getsockname()
        print(f"🌐 Streamable Skill HTTP Server running on http://{addr[0]}:{addr[1]}/mcp", file=sys.stderr)
        print(f"   SSE endpoint: http://{addr[0]}:{addr[1]}/sse", file=sys.stderr)
        print(f"   Health check: http://{addr[0]}:{addr[1]}/health", file=sys.stderr)

        async with server:
            await server.serve_forever()


async def main():
    parser = argparse.ArgumentParser(description="Streamable HTTP MCP Skill Server")
    parser.add_argument("--port", type=int, default=6283, help="HTTP port (default: 6283)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stderr
    )

    server = StreamableSkillHTTPServer(host=args.host, port=args.port)
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
