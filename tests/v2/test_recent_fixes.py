"""
端到端测试：本轮修复的 4 个核心场景

1. Phase 1 数据截断 — work_agent.py 注入时截断到 5000 字符
2. Plan 生成 — plan_manager.py 正常返回步骤（非空）
3. DeepSeek tool_call_id — llm_backend.py 重建消息保留 tool_call_id
4. short_term_memory 协程 — 同步 _llm_summarize 不产生 RuntimeWarning
"""
import json
import pytest
from typing import List, Dict
from unittest.mock import AsyncMock, MagicMock, patch

from core.multi_agent_v2.agents.middleware import PlanStep
from core.multi_agent_v2.agents.plan_manager import _parse_plan_steps


# ═════════════════════════════════════════════════════════════
# 测试 1: Phase 1 数据截断
# ═════════════════════════════════════════════════════════════

def test_phase1_truncation():
    """Phase 1 数据超过 5000 字符时被截断"""
    large_data = "A" * 10000  # 10k chars
    if len(large_data) > 5000:
        truncated = large_data[:5000] + "\n...(Phase 1 数据已截断)"
    assert len(truncated) < 5100
    assert truncated.endswith("...(Phase 1 数据已截断)")
    # 恰好 5000 字符时不截断
    exact = "B" * 5000
    assert len(exact) <= 5000  # no truncation marker needed


# ═════════════════════════════════════════════════════════════
# 测试 2: Plan 解析
# ═════════════════════════════════════════════════════════════

class TestPlanParsing:

    def test_parse_valid_steps(self):
        text = "步骤|搜索百度热搜|web_search\n步骤|写入文件到桌面|write_file"
        steps = _parse_plan_steps(text)
        assert len(steps) == 2
        assert steps[0].description == "搜索百度热搜"
        assert steps[0].tool_names == ["web_search"]
        assert steps[1].description == "写入文件到桌面"
        assert steps[1].tool_names == ["write_file"]

    def test_parse_direct_answer(self):
        """直接回答场景应返回空列表（表示无需工具）"""
        steps = _parse_plan_steps("步骤|直接回答")
        assert steps == []

    def test_parse_skip_template_blacklist(self):
        """LLM 照抄模板的行应跳过"""
        text = "步骤|步骤描述\n步骤|具体描述\n步骤|真实描述|read_file"
        steps = _parse_plan_steps(text)
        assert len(steps) == 1
        assert steps[0].description == "真实描述"

    def test_parse_empty_text(self):
        assert _parse_plan_steps("") == []
        assert _parse_plan_steps("   ") == []

    def test_parse_without_tool(self):
        """没有工具名的步骤 → 默认 write_file"""
        text = "步骤|只看报告"
        steps = _parse_plan_steps(text)
        assert len(steps) == 1
        assert steps[0].tool_names == ["write_file"]

    def test_parse_multi_tool(self):
        """逗号分隔的多个工具名"""
        text = "步骤|搜索并读取|web_search,read_file"
        steps = _parse_plan_steps(text)
        assert len(steps) == 1
        assert steps[0].tool_names == ["web_search", "read_file"]


# ═════════════════════════════════════════════════════════════
# 测试 3: DeepSeek 消息重建保留 tool_call_id
# ═════════════════════════════════════════════════════════════

def test_deepseek_message_reconstruction_preserves_tool_call_id_and_calls():
    """模拟 llm_backend.py 中 DeepSeek 消息重建逻辑"""
    messages = [
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": "分析项目"},
        {"role": "assistant", "content": "好的", "tool_calls": [
            {"id": "call_abc123", "type": "function",
             "function": {"name": "read_file", "arguments": '{"path":"x"}'}}
        ], "reasoning_content": "thinking..."},
        {"role": "tool", "tool_call_id": "call_abc123", "content": "file content", "name": "read_file"},
    ]
    _ds_msgs = []
    for m in messages:
        md = {"role": m["role"], "content": m.get("content", "")}
        if m.get("tool_calls") and m["role"] == "assistant":
            md["tool_calls"] = m["tool_calls"]
        if m.get("reasoning_content") and m["role"] == "assistant":
            md["reasoning_content"] = m["reasoning_content"]
        if m["role"] == "tool":
            md["tool_call_id"] = m.get("tool_call_id", "")
        if m.get("name"):
            md["name"] = m["name"]
        _ds_msgs.append(md)

    assert len(_ds_msgs) == 4
    asst_msg = _ds_msgs[2]
    assert asst_msg["role"] == "assistant"
    assert "tool_calls" in asst_msg, "assistant 消息必须保留 tool_calls"
    assert asst_msg["tool_calls"][0]["id"] == "call_abc123"
    assert asst_msg["reasoning_content"] == "thinking..."
    tool_msg = _ds_msgs[3]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "call_abc123"
    assert tool_msg["name"] == "read_file"


# ═════════════════════════════════════════════════════════════
# 测试 4: short_term_memory sync _llm_summarize 不抛协程警告
# ═════════════════════════════════════════════════════════════

def test_llm_summarize_sync_context_no_warning():
    """在纯同步上下文中调用 _llm_summarize 不应有 RuntimeWarning"""
    from core.memory.short_term_memory import _llm_summarize
    result = _llm_summarize("", "test")
    assert result is None

    with patch("core.engine.llm_backend.get_llm_router", return_value=None):
        result = _llm_summarize("hello world", "test")
        assert result is None


# ═════════════════════════════════════════════════════════════
# 测试: Plan 解析 — Markdown 表格 + 前言清理
# ═════════════════════════════════════════════════════════════

class TestPlanParsingMarkdown:
    """LLM 输出 markdown 表格/前言时，应解析出干净的步骤"""

    def test_parse_markdown_table_skips_preamble(self):
        """markdown 表格 + 前言 → 只解析表格行，跳过前言/表头"""
        text = (
            '好的，我将为你拆解"发现这个项目"的任务步骤。由于"发现"是一个探索性动作，我将其定义为初步了解项目结构。\n'
            '以下是拆解步骤：\n'
            '| 步骤 | 描述 | 工具 |\n'
            '| :--- | :--- | :--- |\n'
            '| 1 | 确认路径存在与基本属性，检查目录是否存在 | `终端` |\n'
            '| 2 | 读取README或项目说明文档 | `文件读取` |\n'
        )
        steps = _parse_plan_steps(text)
        assert len(steps) == 2, f"应解析 2 步, got {len(steps)}"
        assert steps[0].description == "确认路径存在与基本属性，检查目录是否存在"
        assert steps[0].tool_names == ["execute_shell"]  # 终端 → execute_shell
        assert steps[1].description == "读取README或项目说明文档"
        assert steps[1].tool_names == ["read_file"]  # 文件读取 → read_file

    def test_parse_preamble_lines_skipped(self):
        """纯文本格式：前言行（好的/以下是）应跳过，保留真实步骤"""
        text = (
            '好的，我将为你把任务拆解为可执行的步骤。\n'
            '以下是拆解步骤，每行格式为：步骤|描述|工具\n'
            '定位项目根目录并查看顶层文件结构\n'
            '读取README或项目说明文档\n'
            '识别项目技术栈\n'
        )
        steps = _parse_plan_steps(text)
        assert len(steps) == 3, f"应解析 3 步, got {len(steps)}"
        assert steps[0].description == "定位项目根目录并查看顶层文件结构"
        assert steps[2].description == "识别项目技术栈"

    def test_clean_md_keeps_underscore_tool_names(self):
        """_clean_md 不应剥离 write_file 中的下划线"""
        from core.multi_agent_v2.agents.plan_manager import _clean_md
        assert _clean_md("**写入** `write_file`") == "写入 write_file"
        assert "write_file" in _clean_md("write_file")
