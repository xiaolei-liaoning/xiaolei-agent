"""
P1.1 回归 — tool 消息清理累积式已见集合（跨轮 tool_calls 覆盖不误删）

2026-09-06 修复验证：原逻辑用"最近一次 assistant 的 tool_calls"集合，
跨轮被覆盖导致上一轮 tool 消息被误判孤儿删除（空转根因）。
本测试直接构造 GLMBackend 并 mock 最深层客户端，断言清理后的 messages。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.engine.llm_backend import GLMBackend


def _messages_with_cross_round_tool_calls():
    """构造跨轮消息：轮1 工具A(call_a) → 轮2 assistant 带工具B(call_b) → 轮2结果"""

    return [
        {"role": "user", "content": "任务"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_a", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
        ]},
        {"role": "tool", "tool_call_id": "call_a", "content": "文件A内容"},  # 轮1 结果 — 必须保留
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_b", "type": "function", "function": {"name": "write_file", "arguments": "{}"}}
        ]},
        {"role": "tool", "tool_call_id": "call_b", "content": "写入成功"},  # 轮2 结果 — 必须保留
        {"role": "tool", "tool_call_id": "call_ghost", "content": "幻觉结果"},  # 真孤儿 — 必须删除
    ]


@pytest.mark.asyncio
async def test_tool_cleanup_accumulative_across_rounds():
    """跨轮 tool_calls 覆盖 → 轮1 结果保留；幻觉 id 删除"""
    backend = GLMBackend(api_key="", model="glm-4-flash")
    backend._rate_limiter.acquire = AsyncMock(return_value=True)
    fake_chunk = MagicMock()
    fake_chunk.choices = []
    fake_stream = MagicMock()
    fake_stream.__aiter__ = AsyncMock(return_value=iter([fake_chunk]))
    backend.deepseek_client = MagicMock()
    backend.deepseek_client.chat.completions.create = AsyncMock(return_value=fake_stream)

    captured = {}

    async def fake_create(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return fake_stream

    backend.deepseek_client.chat.completions.create = AsyncMock(side_effect=fake_create)

    await backend.chat_structured_stream(
        list(_messages_with_cross_round_tool_calls()), model="deepseek-chat", tools=None
    )
    ids = [m.get("tool_call_id") for m in captured["messages"] if m.get("role") == "tool"]
    assert "call_a" in ids, f"轮1 结果被误删: {ids}"
    assert "call_b" in ids, f"轮2 结果被误删: {ids}"
    assert "call_ghost" not in ids, f"幻觉孤儿未删除: {ids}"
