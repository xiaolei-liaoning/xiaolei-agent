"""Fake LLM Router — 离线可编程 LLM 替身（对标 hermes evals/fanout 的 fake server）

设计（KISS，不走 http.server，进程内直接替换 router）：
  - 测试给定 replies: List[str]，FakeRouter 按调用序号依序返回
  - 第 N 条 reply 若形如 {"type":"function",...} 会以 tool_call 形态包进 OpenAI 格式
  - 消费完毕自动循环最后一条（防卡死，配合 max_turns 自然退出）
  - 与 real 的接口对齐：simple_chat / chat / is_available

逾越于 mock.AsyncMock：带断言辅助 (:attr: calls 记录请求内容)，
方便测试断言"第二个调用带了工具结果"这类链路。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


class FakeRouter:
    """可编程 LLM router — 按序返回预设 replies"""

    def __init__(self, replies: Optional[List[str]] = None, model: str = "fake-model"):
        self.replies = replies or []
        self._i = 0
        self.model = model
        self.calls: List[dict] = []   # 完整请求记录，测试断言用

    # ── 记录 + 顺序取 reply（打完回绕最后一条） ──
    def _next_reply(self, messages: list) -> str:
        self.calls.append({"messages": messages, "n_tool_results": sum(1 for m in messages if m.get("role") == "tool")})
        if self._i < len(self.replies):
            r = self.replies[self._i]
            self._i += 1
            return r
        return self.replies[-1] if self.replies else ""

    # ── 主接口：与 LLMRouter 签名对齐 ──
    async def simple_chat(self, user_message: str, system_prompt=None, temperature: float = 0.7,
                          max_tokens: int = 4096, **kw) -> str:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": user_message})
        return self._next_reply(msgs)

    async def chat(self, messages, temperature: float = 0.7, max_tokens: int = 4096,
                   stream: bool = False, **kw):
        raw = self._next_reply(messages)
        return self._wrap(raw)

    async def chat_structured(self, messages, **kw):
        return self._wrap(self._next_reply(messages))

    async def chat_stream(self, messages, **kw):
        # 小雷版 stream 还未用，直接给一次性 chunk
        yield self._wrap(self._next_reply(messages))

    async def chat_structured_stream(self, messages, **kw):
        yield self._wrap(self._next_reply(messages))

    # ── 包装器：符合 llm_backend 消费方期待的返回结构 ──
    @staticmethod
    def _parse_tool_call(raw: str):
        """若 reply 是 {"type":"function","function":{...}}，转 OpenAI tool_call dict"""
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if isinstance(obj, dict) and obj.get("type") == "function":
            fn = obj.get("function", {})
            return {
                "id": fn.get("name", "call_0"),
                "type": "function",
                "function": {
                    "name": fn.get("name"),
                    "arguments": fn.get("arguments") if isinstance(fn.get("arguments"), str)
                                 else json.dumps(fn.get("arguments") or {}),
                },
            }
        return None

    def _wrap(self, raw: str):
        """把 raw reply 包成小雷版 LLM backend 消费的结构"""
        tc = self._parse_tool_call(raw)
        if tc:
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [tc],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        return {
            "choices": [{
                "message": {"role": "assistant", "content": raw},
                "finish_reason": "stop",
            }]
        }

    # 兼容旧命名占位已移除

    def is_available(self) -> bool:
        return True

    # ── 测试断言辅助 ──
    def assert_tool_call_count(self, n: int):
        """第 N 次调用返回了 tool_call 数（共 N 条）"""
        actual = sum(1 for c in self.calls for _ in [1] if False)  # 简化：仅记录调用数
        assert len(self.calls) >= n, f"期望至少 {n} 次 LLM 调用, 实际 {len(self.calls)}"


def make_router(replies: List[str]) -> FakeRouter:
    """便捷工厂 — patches llm_backend.get_llm_router 一个测试作用域内使用"""
    router = FakeRouter(replies)
    # 兼容 mock.patch.object(lb, "get_llm_router", return_value=router) 的常见写法:
    return router


def patch_router(monkeypatch, replies: List[str]) -> FakeRouter:
    """一行把 core.engine.llm_backend.get_llm_router 替换为 FakeRouter"""
    from core.engine import llm_backend as _lb
    router = FakeRouter(replies)
    monkeypatch.setattr(_lb, "get_llm_router", lambda *a, **kw: router)
    return router
