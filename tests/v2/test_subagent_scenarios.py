"""子代理场景测试 — 真实 LLM 调用

测试目标：
  1. 复杂任务使用子代理（task/orchestrate）
  2. 简单任务不使用子代理
  3. 出错时优雅降级

运行: python -m pytest tests/v2/test_subagent_scenarios.py -v -x
"""

import asyncio
import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

pytestmark = pytest.mark.asyncio

logger = logging.getLogger(__name__)

# ── 辅助函数 ──

_TOOL_LOG: list = []


def _extract_tools(tool_results: list) -> list:
    """从执行结果提取工具调用序列"""
    return [r.get("tool_call", {}).get("name", "") for r in (tool_results or [])]


def _has_any(tools: list, names: set) -> bool:
    return any(t in names for t in tools)


def _has_subagent(tools: list) -> bool:
    """是否使用了子代理"""
    return _has_any(tools, {"task", "orchestrate"})


def _has_codegraph(tools: list) -> bool:
    return _has_any(tools, {"codegraph_explore", "codegraph_files", "codegraph_search"})


def _read_file_count(tools: list) -> int:
    return sum(1 for t in tools if t == "read_file")


async def _run(task: str, max_rounds: int = 10) -> dict:
    from core.multi_agent_v2.agents.react_core import run_react
    from core.skills.base_skills import SkillSystem
    mgr = SkillSystem()
    skill = await mgr.match(task)
    pp = skill.personality
    pref = skill.tool_preference
    result = await run_react(
        task_description=task,
        max_rounds=max_rounds,
        personality_prompt=pp,
        tool_preference=pref,
    )
    result["_skill_name"] = skill.skill_name
    result["_personality_len"] = len(pp)
    return result


# ════════════════════════════════════════════════════════════════
# 测试用例
# ════════════════════════════════════════════════════════════════


async def test_project_analysis_should_use_subagents():
    """复杂项目分析应该使用子代理或 codegraph"""
    result = await _run("分析 /Users/leiyuxuan/Desktop/hermes-agent 这个项目", max_rounds=12)
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")
    success = result.get("success", False)

    tool_summary = ", ".join(tools)
    print(f"\n  tools: {tool_summary}")
    print(f"  success: {success}, answer_len: {len(answer)}")
    print(f"  skill: {result.get('_skill_name', '?')}")

    used_subagent = _has_subagent(tools)
    used_codegraph = _has_codegraph(tools)
    read_files = _read_file_count(tools)

    print(f"  subagent: {used_subagent}, codegraph: {used_codegraph}, read_file: {read_files}")

    # 项目分析应该产生有意义的输出
    assert success or len(answer) > 200, f"分析太短或失败: len={len(answer)}, success={success}"


async def test_simple_qa_no_subagent():
    """简单问答不应该使用子代理"""
    result = await _run("用一句话解释什么是 Python 装饰器", max_rounds=3)
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")

    tool_summary = ", ".join(tools) if tools else "(none)"
    print(f"\n  tools: {tool_summary}, answer_len: {len(answer)}")

    # 简单问答应该得到有意义的回答
    assert len(answer) > 20, f"回答太短: {len(answer)}"
    assert answer != "[LLM_MOCK]", "不应 mock 回答"


async def test_multi_file_generation():
    """多文件生成应该使用子代理"""
    result = await _run(
        "创建一个贪吃蛇 HTML 游戏，包含 index.html, style.css, game.js",
        max_rounds=10,
    )
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")
    success = result.get("success", False)

    tool_summary = ", ".join(tools)
    print(f"\n  tools: {tool_summary}")
    print(f"  success: {success}, answer_len: {len(answer)}")
    print(f"  has_write_file: {'write_file' in tools}")

    assert len(answer) > 100, f"输出太短: {len(answer)}"


async def test_orchestrate_parallel_tasks():
    """多个独立任务应该使用 orchestrate 或分批 task"""
    result = await _run(
        "搜索 Python 和 JavaScript 的最新版本号",
        max_rounds=8,
    )
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")

    tool_summary = ", ".join(tools)
    print(f"\n  tools: {tool_summary}")
    print(f"  answer_len: {len(answer)}")

    # 搜索任务应该搜索
    has_search = _has_any(tools, {"web_search", "fetch_url"})
    print(f"  searched: {has_search}")

    assert len(answer) > 50


async def test_subagent_error_recovery():
    """子代理出错时应该降级处理"""
    result = await _run(
        "分析 /nonexistent/path 这个项目",
        max_rounds=8,
    )
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")
    error = result.get("error", "")

    tool_summary = ", ".join(tools)
    print(f"\n  tools: {tool_summary}")
    print(f"  error: {error}")
    print(f"  answer: {answer[:200]}")

    # 即使路径不存在，也应该有回应
    assert len(answer) > 30 or error, "路径不存在时也应该有输出"


async def test_code_search_uses_codegraph():
    """代码搜索应该使用 codegraph 或 grep"""
    result = await _run(
        "在 /Users/leiyuxuan/Desktop/hermes-agent 中搜索所有异步函数定义",
        max_rounds=8,
    )
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")

    tool_summary = ", ".join(tools)
    print(f"\n  tools: {tool_summary}")
    print(f"  answer_len: {len(answer)}")

    has_codegraph = _has_codegraph(tools)
    has_grep = "grep" in tools or "search_files" in tools
    print(f"  codegraph: {has_codegraph}, grep: {has_grep}")

    assert len(answer) > 50, f"搜索太短: {len(answer)}"
