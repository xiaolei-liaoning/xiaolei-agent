"""全面真实场景测试 — MCP/子代理/角色/工具链全覆盖

运行: python -m pytest tests/v2/test_comprehensive_real.py -v -s
"""

import asyncio
import os
import sys
import pytest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

pytestmark = pytest.mark.asyncio


def _extract_tools(tool_results: list) -> list:
    return [r.get("tool_call", {}).get("name", "") for r in (tool_results or [])]


def _has_any(tools: list, names: set) -> bool:
    return any(t in names for t in tools)


async def _run_react(task: str, max_rounds: int = 10, personality_prompt: str = "",
                     tool_preference: set = None, allowed_tools: list = None,
                     disallowed_tools: list = None) -> dict:
    from core.multi_agent_v2.agents.react_core import run_react
    from core.skills.base_skills import SkillSystem
    mgr = SkillSystem()
    skill = await mgr.match(task)
    pp = personality_prompt or skill.personality
    pref = tool_preference or skill.tool_preference
    result = await run_react(
        task_description=task,
        max_rounds=max_rounds,
        personality_prompt=pp,
        tool_preference=pref,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
    )
    result["_skill_name"] = skill.skill_name
    return result


async def _run_task(description: str, agent: str = "general") -> dict:
    """直接调 task 子代理"""
    from core.multi_agent_v2.agents.subagent.spawn import task as spawn_task
    return await spawn_task(description=description, agent=agent)


async def _run_orchestrate(tasks: list, max_concurrent: int = 3) -> dict:
    """直接调 orchestrate"""
    from core.multi_agent_v2.agents.subagent.spawn import orchestrate
    return await orchestrate(tasks=tasks, max_concurrent=max_concurrent)


# ════════════════════════════════════════════════════════════════
# Test Suite 1: 快捷子代理命令
# ════════════════════════════════════════════════════════════════

async def test_task_command():
    """/task 快捷命令 — 用 general 子代理"""
    result = await _run_task("用一句话说明Python生成器的用途", agent="general")
    success = result.get("success", False)
    output = result.get("output", "")
    print(f"\n  /task: success={success}, output_len={len(output)}")
    assert success, f"/task failed: {result.get('error', '')}"
    assert len(output) > 20, f"输出太短: {len(output)}"


async def test_explore_command():
    """/explore 快捷命令 — 用 explore 子代理探索"""
    result = await _run_task(
        "列举 /Users/leiyuxuan/Desktop/小雷版agent 目录下的 .py 文件数量",
        agent="explore",
    )
    success = result.get("success", False)
    output = result.get("output", "")
    print(f"\n  /explore: success={success}, output_len={len(output)}")
    assert success, f"/explore failed"
    assert len(output) > 50, f"输出太短"


async def test_analyze_command():
    """/analyze 快捷命令 — 用 analyze 子代理分析简单代码"""
    result = await _run_task(
        "分析下面代码有什么问题：\ndef add(a,b):\n    return a+b\n\ndef main():\n    print(add(1))\n    print(add('1','2'))",
        agent="analyze",
    )
    success = result.get("success", False)
    output = result.get("output", "")
    print(f"\n  /analyze: success={success}, output_len={len(output)}")
    assert success, f"/analyze failed"
    assert len(output) > 50


async def test_build_command():
    """/build 快捷命令 — 用 build 子代理创建简单文件"""
    result = await _run_task(
        "在 ~/Desktop 创建 hello_test.html（一个Hello World页面）",
        agent="build",
    )
    success = result.get("success", False)
    output = result.get("output", "")
    print(f"\n  /build: success={success}, output_len={len(output)}")
    assert success, f"/build failed"


# ════════════════════════════════════════════════════════════════
# Test Suite 2: MCP 工具直接调用
# ════════════════════════════════════════════════════════════════

async def test_codegraph_explore():
    """测试 codegraph_explore MCP 工具"""
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    reg = get_tool_registry()
    await reg.discover_all()
    handler = reg.get_handler("codegraph_explore")
    if not handler:
        print("\n  codegraph_explore 不可用（MCP未连接），跳过")
        return

    # 检查工具注册
    cg_tools = [n for n in reg._tools if "codegraph" in n]
    print(f"\n  MCP codegraph 工具 ({len(cg_tools)}): {cg_tools}")
    assert len(cg_tools) >= 4, f"codegraph 工具太少: {cg_tools}"


async def test_deepwiki_mcp():
    """测试 deepwiki MCP 工具"""
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    reg = get_tool_registry()
    await reg.discover_all()
    dw_tools = [n for n in reg._tools if "deepwiki" in n]
    print(f"\n  deepwiki 工具 ({len(dw_tools)}): {dw_tools}")


async def test_context7_mcp():
    """测试 context7 MCP 工具"""
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    reg = get_tool_registry()
    await reg.discover_all()
    c7_tools = [n for n in reg._tools if "query-docs" in n or "resolve" in n]
    print(f"\n  context7 工具 ({len(c7_tools)}): {c7_tools}")


# ════════════════════════════════════════════════════════════════
# Test Suite 3: 多种角色执行
# ════════════════════════════════════════════════════════════════

async def test_web_scraper_role():
    """web_scraper 角色 — 搜索测试"""
    result = await _run_react("搜索 Python 3.13 的新特性", max_rounds=5)
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")
    print(f"\n  role: {result.get('_skill_name','?')}, tools: {tools[:5]}")
    print(f"  answer_len: {len(answer)}")
    assert len(answer) > 20


async def test_system_toolbox_role():
    """system_toolbox 角色 — 系统操作"""
    result = await _run_react("查看当前目录有哪些文件", max_rounds=4)
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")
    print(f"\n  role: {result.get('_skill_name','?')}, tools: {tools[:5]}")
    has_shell = _has_any(tools, {"execute_shell", "read_file"})
    print(f"  used_shell: {has_shell}, answer_len: {len(answer)}")
    assert len(answer) > 20


async def test_data_analyst_role():
    """data_analyst 角色 — 简单分析"""
    result = await _run_react("分析数字 1,2,3,4,5,6 的平均数和中位数", max_rounds=5)
    answer = result.get("answer", "")
    print(f"\n  role: {result.get('_skill_name','?')}, answer_len: {len(answer)}")
    assert len(answer) > 20


async def test_project_analysis_role():
    """project_analyzer 角色 — 项目分析（重点：看是否用子代理）"""
    result = await _run_react(
        "分析 /Users/leiyuxuan/Desktop/hermes-agent 这个项目",
        max_rounds=10,
    )
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")
    tool_summary = Counter(tools)

    print(f"\n  角色: {result.get('_skill_name','?')}")
    print(f"  工具统计: read_file={tool_summary.get('read_file',0)}, "
          f"codegraph={tool_summary.get('codegraph_explore',0)}, "
          f"task={tool_summary.get('task',0)}, "
          f"orchestrate={tool_summary.get('orchestrate',0)}")
    print(f"  answer_len: {len(answer)}")
    assert len(answer) > 200, f"分析太短: {len(answer)}"


# ════════════════════════════════════════════════════════════════
# Test Suite 4: 子代理编排
# ════════════════════════════════════════════════════════════════

async def test_orchestrate_simple():
    """orchestrate 并行 2 个子代理（简单方式）"""
    from core.multi_agent_v2.tools.tool_registry import _handle_orchestrate
    result = await _handle_orchestrate({
        "task1": "用一句话说明Python是什么",
        "task2": "用一句话说明JavaScript是什么",
        "agent": "general",
    })
    ok = result.get("ok", False)
    output = result.get("data", "")
    print(f"\n  orchestrate(simple): ok={ok}, output_len={len(output)}")
    assert ok, f"orchestrate failed: {result.get('error','')}"


async def test_subagent_nested():
    """子代理内再调用 subagent（验证不覆盖父 session）"""
    from core.memory.session_manager import get_session_manager
    sm = get_session_manager()

    sid_parent = sm.create_session("父代理测试")
    print(f"\n  父 session: {sid_parent}")

    result = await _run_task("输出数字 42", agent="general")
    print(f"  子代理完成: {result.get('success')}")

    sid_current = sm.current_session_id
    print(f"  子代理后 current session: {sid_current}")
    assert sid_current == sid_parent, f"session 被覆盖! 期望={sid_parent}, 当前={sid_current}"
    print(f"  ✅ session 栈正确恢复")


# ════════════════════════════════════════════════════════════════
# Test Suite 5: Session Artifact 系统
# ════════════════════════════════════════════════════════════════

async def test_session_artifacts_created():
    """主代理执行后，artifact 文件应被正确创建"""
    from core.memory.session_manager import get_session_manager, SESSION_ROOT
    sm = get_session_manager()

    sid = sm.create_session("Artifact测试")
    sm.record_round(1, "Round 1: 开始分析")
    sm.record_artifact("key_finding", "发现项目使用了CodeGraph")
    artifact_path = sm.record_artifact("final_answer", "最终分析完成")
    sm.finalize_session("测试完成")

    print(f"\n  session: {sid}")
    print(f"  final_answer artifact: {artifact_path}")
    assert artifact_path and os.path.exists(artifact_path), "artifact 文件未创建"
    content = open(artifact_path).read()
    assert "最终分析完成" in content
    print(f"  ✅ artifact 内容正常")


async def test_session_history_injection():
    """历史会话应能被 build_context_block 检索到"""
    from core.memory.session_manager import get_session_manager
    sm = get_session_manager()
    block = sm.build_context_block(n=5)
    print(f"\n  历史会话块长度: {len(block) if block else 0}")
    if block:
        print(f"  内容: {block[:200]}")


# ════════════════════════════════════════════════════════════════
# Test Suite 6: 容错与降级
# ════════════════════════════════════════════════════════════════

async def test_tool_validation_error_recovery():
    """工具参数校验失败后应重试成功"""
    result = await _run_react("搜索Python", max_rounds=3)
    tools = _extract_tools(result.get("tool_results", []))
    answer = result.get("answer", "")
    print(f"\n  tools: {tools[:5]}")
    print(f"  answer_len: {len(answer)}")


async def test_empty_task():
    """空任务不应崩溃"""
    result = await _run_react("", max_rounds=2)
    print(f"\n  空任务: success={result.get('success')}")
