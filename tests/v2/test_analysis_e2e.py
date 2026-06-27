"""端到端测试：项目分析拦截扫描工具 + 生成完整总结"""
import pytest


@pytest.mark.asyncio
async def test_analysis_filters_scan_tools():
    """验证 _has_structure_data 时扫描工具被过滤"""
    from core.multi_agent_v2.agents.middleware import RunContext

    ctx = RunContext(task_description="test")
    ctx._has_structure_data = True
    ctx.tool_defs = [
        {"function": {"name": "execute_shell", "description": "run cmd"}},
        {"function": {"name": "read_file", "description": "read file"}},
        {"function": {"name": "write_file", "description": "write file"}},
        {"function": {"name": "web_search", "description": "search web"}},
    ]

    # 模拟 on_think_start 中的过滤逻辑
    from core.multi_agent_v2.agents.react_core import _filter_scan_tools
    ctx.tool_defs = _filter_scan_tools(ctx.tool_defs)

    names = {t["function"]["name"] for t in ctx.tool_defs}
    assert "execute_shell" not in names, "execute_shell 未被过滤"
    assert "read_file" not in names, "read_file 未被过滤"
    assert "write_file" in names, "write_file 被误过滤"


@pytest.mark.asyncio
async def test_analysis_non_truncated_summary():
    """验证带有 Phase 1 数据的总结不被截断"""
    from core.multi_agent_v2.agents.react_core import run_react

    phase_data = (
        "## 文件树\n"
        "src/main.py — 主入口\n"
        "src/utils.py — 工具函数\n"
        "tests/test_main.py — 测试\n\n"
        "## 技术栈\n"
        "- Python 3.13\n"
        "- FastAPI\n"
        "- Pydantic v2\n"
        "- SQLAlchemy\n"
        "- pytest\n\n"
        "## 核心代码\n"
        "### src/main.py\n"
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/')\n"
        "async def root():\n"
        "    return {'message': 'Hello'}\n\n"
        "### src/utils.py\n"
        "def process(data: dict) -> dict:\n"
        "    return {'processed': True}\n"
    )
    desc = f"分析这个项目\n\n===== 项目结构概览（Phase 1 扫描）=====\n{phase_data}"

    result = await run_react(desc, max_rounds=5)
    ans = result.get("answer", "")

    # 不应泄露 JSON
    assert "choices" not in ans, f"final_answer 泄露 JSON: {ans[:200]}"
    assert "tool_calls" not in ans, f"final_answer 泄露 tool_calls: {ans[:200]}"
    assert not ans.startswith("{"), f"final_answer 以 JSON 开头: {ans[:200]}"

    # 应有足够的总结内容
    assert len(ans) > 100, f"final_answer 太短 ({len(ans)} 字符): {ans[:200]}"

    # 应提到项目关键信息
    assert "Python" in ans or "FastAPI" in ans or "Pydantic" in ans, \
        f"final_answer 缺少项目技术栈信息: {ans[:200]}"
    assert "main.py" in ans or "src" in ans, \
        f"final_answer 缺少目录结构信息: {ans[:200]}"

    # 不应以截断符号结尾
    import re
    truncated_endings = [
        r"\|\|\|\|", r"\.\.\.\.\.", r"\-\-\-\-", r"\*\*\*\*",
        r"[\|\.\-]{4,}$",
        r"（待补充|待完善|待继续|未完待续",
    ]
    for pat in truncated_endings:
        if re.search(pat, ans.strip()[-30:]):
            pytest.fail(f"final_answer 似乎被截断: ...{ans.strip()[-40:]}")

    # 不应有 "docs/-----" 这类奇怪结尾
    assert not re.search(r'`[^`]+`\-{3,}', ans[-100:]), \
        f"summar 末尾出现疑似截断的 markdown 列表项: {ans[-100:]}"

    assert result.get("success", False), f"任务失败: {result.get('error', '')}"
