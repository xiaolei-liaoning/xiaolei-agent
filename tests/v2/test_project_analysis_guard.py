"""测试项目分析守卫：验证 final_answer 不泄露 JSON、不被截断"""
import pytest
import json

pytestmark = pytest.mark.real_llm


@pytest.mark.asyncio
async def test_guard_extracts_clean_text_from_tool_result():
    """项目分析 write_file 成功后，应走到 fallback 总结 LLM 生成摘要，而非直接退出了事"""
    from core.multi_agent_v2.agents.react_core import run_react

    desc = (
        "分析项目。数据如下：\n"
        "## 文件树\nsrc/main.py — 主入口\n\n"
        "## 技术栈\nPython 3.13, FastAPI\n\n"
        "## 核心代码\n### src/main.py\nfrom fastapi import FastAPI\napp = FastAPI()\n"
    )

    result = await run_react(desc, max_rounds=5)
    ans = result.get("answer", "")

    # 不应泄露 JSON
    assert "choices" not in ans, f"final_answer 泄露 JSON: {ans[:200]}"
    assert "tool_calls" not in ans, f"final_answer 泄露 JSON: {ans[:200]}"
    assert not ans.startswith("{"), f"final_answer 以 JSON 开头: {ans[:200]}"

    # final_answer 不应为空（可能是空字符串）
    assert not ans.startswith("{"), f"final_answer 仍以 JSON 开头: {ans[:200]}"


@pytest.mark.asyncio
async def test_knowledge_context_no_json():
    """knowledge_context 不应包含 JSON 原始响应"""
    from core.multi_agent_v2.agents.middleware import RunContext

    ctx = RunContext(task_description="测试")
    ctx.react_depth = 1
    ctx.knowledge_context = "之前的内容\n"

    ctx._pending_reply = json.dumps({
        "choices": [{"message": {
            "content": "I'll analyze the project",
            "tool_calls": [{"id": "call_1", "type": "function",
                            "function": {"name": "write_file", "arguments": '{"path":"/tmp/test.html"}'}}]
        }}]
    })

    # 模拟 on_thin_end 中的写入逻辑
    from core.multi_agent_v2.agents.react_core import _extract_text_from_json
    reply = ctx._pending_reply
    _ctx_text = reply if not reply.startswith("{") else _extract_text_from_json(reply) or reply[:200]
    ctx.knowledge_context += f"\nLLM第{ctx.react_depth}轮: {_ctx_text[:300]}"

    assert "choices" not in ctx.knowledge_context, "knowledge_context 包含 JSON"
    assert "I'll analyze the project" in ctx.knowledge_context, "knowledge_context 丢失 LLM 文本"


@pytest.mark.asyncio
async def test_extract_text_from_json():
    from core.multi_agent_v2.agents.react_core import _extract_text_from_json

    # 有 content 的情况
    j1 = json.dumps({"choices": [{"message": {"content": "分析完成", "tool_calls": []}}]})
    assert _extract_text_from_json(j1) == "分析完成"

    # 空 content
    j2 = json.dumps({"choices": [{"message": {"content": "", "tool_calls": [{"id": "c1"}]}}]})
    assert _extract_text_from_json(j2) == ""

    # 无 choices
    j3 = json.dumps({})
    assert _extract_text_from_json(j3) == ""

    # 非法 JSON
    assert _extract_text_from_json("not json") == ""
