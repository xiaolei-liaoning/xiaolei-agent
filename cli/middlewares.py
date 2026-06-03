"""轻量 ReAct 执行器 — 真正的 Reasoning + Acting 循环

流程（每次只调一次 LLM）：
  1. 把请求 + 可用工具发给 LLM
  2. LLM 决定：
     - 调工具 → 执行工具，结果喂回去 → 回到 1（最多 3 轮）
     - 输出文本 → 这就是最终回复
"""

import json
import logging
from cli.middleware import Context, AgentMiddleware, MiddlewarePipeline
from cli.colors import print_chat_bubble
from cli.logging_system import log_info, log_error

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 3


# ── 可用工具定义 ─────────────────────────────────────────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网获取最新信息。当用户要求搜索、查找、查询信息时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "执行 Shell 命令。当用户要求运行代码、执行命令、操作文件时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 Shell 命令"}
                },
                "required": ["command"]
            }
        }
    },
]


class ReActMiddleware(AgentMiddleware):
    """真正的 ReAct 循环：LLM 自己决定何时调工具、何时给答案"""
    name = "react"

    async def awrap_execution(self, ctx: Context, handler) -> None:
        await self._react(ctx)
        await handler()

    async def _react(self, ctx: Context) -> None:
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if not router.is_available():
            ctx.response = {"success": False, "error": "LLM 不可用"}
            return

        messages = [
            {"role": "system", "content": "你是小雷版小龙虾AI助手。你需要使用工具来回答用户的问题。每次思考后，要么调用一个工具，要么给出最终答案。"},
            {"role": "user", "content": ctx.request},
        ]

        for rnd in range(1, _MAX_ROUNDS + 1):
            reply = await router.chat(messages, temperature=0.3, max_tokens=2000, tools=_TOOLS)

            # 解析 LLM 回复
            tool_calls = self._parse_tool_calls(reply)

            if not tool_calls:
                # 纯文本 = 最终答案
                text = reply.strip()
                if text:
                    print_chat_bubble(text, is_user=False)
                    ctx.chat_history.append({"role": "assistant", "content": text})
                    ctx.response = {"success": True, "summary": text, "rounds": rnd}
                return

            # 有工具调用 → 执行
            for tc in tool_calls:
                name = tc.get("function", {}).get("name", "")
                try:
                    args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}

                log_info(f"🔧 第{rnd}轮 调用: {name}({args})")
                result = await self._call_tool(name, args)

                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.get("id", f"call_{rnd}"),
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                    }]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{rnd}"),
                    "content": json.dumps(result, ensure_ascii=False)[:3000],
                })

        # 超出最大轮次还没出答案 → 强制 LLM 给结论
        reply = await router.chat(
            messages + [{"role": "user", "content": "请基于已有的信息给出最终回答。"}],
            temperature=0.3, max_tokens=1000,
        )
        text = reply.strip()
        if text:
            print_chat_bubble(text, is_user=False)
            ctx.chat_history.append({"role": "assistant", "content": text})
            ctx.response = {"success": True, "summary": text, "rounds": _MAX_ROUNDS}

    def _parse_tool_calls(self, reply: str) -> list:
        """解析 LLM 返回中的 tool_calls"""
        try:
            data = json.loads(reply)
            if isinstance(data, dict):
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                    return msg.get("tool_calls", [])
                return data.get("tool_calls", [])
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return []

    async def _call_tool(self, name: str, args: dict) -> dict:
        """执行工具"""
        if name == "web_search":
            return await self._web_search(args.get("query", ""))
        if name == "run_bash":
            return await self._run_bash(args.get("command", ""))
        return {"error": f"未知工具: {name}"}

    async def _web_search(self, query: str) -> dict:
        """搜索 — 用 Python urllib 抓取，不依赖 curl/grep"""
        import urllib.request
        import urllib.parse
        import re

        url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            return {"error": str(e)}

        # 提取搜索结果标题
        items = re.findall(r'<a[^>]*>(.*?)</a>', html)
        titles = []
        for item in items:
            clean = re.sub(r'<[^>]+>', '', item).strip()
            if clean and len(clean) > 4:
                titles.append(clean)
        titles = titles[:20]

        if not titles:
            # fallback: 提取所有可见文本片段
            texts = re.findall(r'[^<>]{10,100}', html)
            titles = [t.strip() for t in texts if t.strip()][:20]

        return {"query": query, "results": titles, "count": len(titles)}

    async def _run_bash(self, command: str) -> dict:
        """执行 shell 命令"""
        import asyncio
        try:
            proc = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            return {
                "stdout": stdout.decode("utf-8", errors="replace")[:2000],
                "stderr": stderr.decode("utf-8", errors="replace")[:500],
                "returncode": proc.returncode,
            }
        except asyncio.TimeoutError:
            return {"error": "命令执行超时"}
        except Exception as e:
            return {"error": str(e)}


def build_default_pipeline():
    pipeline = MiddlewarePipeline()
    pipeline.use(ReActMiddleware())
    return pipeline

def get_default_middlewares():
    return [ReActMiddleware()]
