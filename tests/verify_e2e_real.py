#!/usr/bin/env python3
"""
真实 LLM 端到端验证

测试从 CLI → WorkAgent.run() → Mind._think_with_llm()
→ tool_calls 返回 → act(tool_calls) → _execute_tool_calls()
→ ToolRegistry → reflect() 的完整路径。

需要 ZHIPU_API_KEY 环境变量（已在 .env 中配置）。
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 颜色 ──────────────────────────────────────────────
G = "\033[92m"  # green
Y = "\033[93m"  # yellow
C = "\033[96m"  # cyan
R = "\033[91m"  # red
B = "\033[1m"
N = "\033[0m"   # reset


def ok(msg): print(f"  {G}✓{N} {msg}")
def info(msg): print(f"  {C}→{N} {msg}")
def warn(msg): print(f"  {Y}!{N} {msg}")
def fail(msg): print(f"  {R}✗{N} {msg}")


async def step1_check_llm_available():
    """检查 LLM 后端是否可用"""
    print(f"\n{B}步骤1: LLM 后端可用性检查{N}")

    from core.engine.llm_backend import get_llm_router
    router = get_llm_router()

    if router.backend and router.backend.client:
        ok(f"GLM 客户端已初始化 (model={os.getenv('MODEL', 'glm-4-flash')})")
    else:
        warn("GLM 客户端未初始化，将尝试免费 API")
        if not router.api_key:
            warn("未找到 API Key")

    # 尝试一次简单调用
    try:
        reply = await router.chat(
            [{"role": "user", "content": "用一句话回答：1+1等于几？"}],
            temperature=0.1, max_tokens=50,
        )
        info(f"LLM 回复: {reply[:80]}...")
        ok("LLM 基础调用正常")
        return True
    except Exception as e:
        fail(f"LLM 调用失败: {e}")
        return False


async def step2_verify_tool_registry():
    """ToolRegistry 能发现工具"""
    print(f"\n{B}步骤2: ToolRegistry 工具发现{N}")

    from core.multi_agent_v2.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    tools = await registry.discover_all()
    info(f"发现 {len(tools)} 个工具")
    if tools:
        for t in tools[:5]:
            info(f"  {t.name}: {t.description[:60]}")
        ok(f"ToolRegistry 初始化完成 ({len(tools)} 工具)")
    else:
        warn("未发现任何工具（无 MCP 服务器连接）")
    return registry._initialized


async def step3_worker_agent_run():
    """
    用真实 LLM 跑 WorkAgent.run()

    用一个简单的搜索/分析类任务，期望 LLM 返回 tool_calls。
    如果 LLM 没有返回 tool_calls（纯文字回答），也验证 plan 执行路径正常。
    """
    print(f"\n{B}步骤3: WorkAgent.run() 真实 LLM 执行{N}")

    from core.multi_agent_v2.agents import WorkAgent
    from cli.thinking_trace import get_trace

    agent = WorkAgent(agent_id="e2e-test")
    trace = get_trace()
    agent.set_trace(trace)
    trace.start("端到端验证任务")

    # 先测试 _think_with_llm 是否正常（诊断用）
    from core.multi_agent_v2.agents.base.base_agent import Task as InnerTask
    from core.engine.llm_backend import get_llm_router
    router = get_llm_router()
    try:
        sample_task = InnerTask(
            task_id="diag", type="general",
            description="请用中文回复：当前系统的组件有哪些？列出3个即可。",
            keywords=[], complexity=0.5, estimated_steps=3,
        )
        diag_thought = await agent.mind._think_with_llm(sample_task)
        info(f"_think_with_llm 返回 plan={len(diag_thought.plan)}步, tool_calls={len(diag_thought.tool_calls) if hasattr(diag_thought, 'tool_calls') else 0}")
    except Exception as e:
        import traceback
        warn(f"_think_with_llm 异常: {e}")
        traceback.print_exc()

    start = time.time()
    result = await agent.run(
        "请用中文回复：当前系统的组件有哪些？列出3个即可。",
        max_iterations=1,
    )
    elapsed = time.time() - start

    print()
    info(f"耗时: {elapsed:.1f}s")
    info(f"迭代: {result.get('iterations')} 轮")
    info(f"置信度: {result.get('confidence', 0):.2f}")
    info(f"成功: {result.get('success')}")
    result_preview = str(result.get("result", ""))[:200]
    if result_preview:
        info(f"结果预览: {result_preview}")

    if result.get("success"):
        ok("WorkAgent.run() 执行成功")
    else:
        error = result.get("error", "")
        if "API" in error or "timeout" in error.lower():
            warn(f"LLM API 问题，非代码错误: {error[:100]}")
        else:
            fail(f"执行失败: {error[:100]}")

    return result.get("success", False)


async def step4_verify_tool_calls_parsing():
    """
    验证 tool_calls 解析路径：模拟 LLM 返回 OpenAI 格式 tool_calls，
    验证 _extract_tool_calls → act(tool_calls) 路径。
    """
    print(f"\n{B}步骤4: tool_calls 解析与 act() 路径{N}")

    from core.multi_agent_v2.agents.base.base_agent import Mind, Task
    from unittest.mock import MagicMock
    from enum import Enum

    class MockType(Enum):
        worker = "worker"

    agent = MagicMock()
    agent.agent_id = "test"
    agent.agent_type = MockType.worker
    agent.capabilities = []
    agent.ask_user = MagicMock()
    mind = Mind(agent)
    mind.llm_router = None
    mind.prompt_manager = None

    # OpenAI 格式 tool_calls
    response = json.dumps({
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "我将搜索网络信息",
                "tool_calls": [
                    {
                        "id": "call_test_1",
                        "type": "function",
                        "function": {
                            "name": "search.web",
                            "arguments": '{"query": "test"}',
                        }
                    }
                ]
            }
        }]
    })

    # 验证 _extract_tool_calls
    tc = mind._extract_tool_calls(response)
    assert tc is not None, "OpenAI 格式 tool_calls 解析失败"
    assert len(tc) == 1
    assert tc[0]["name"] == "search.web"
    assert tc[0]["arguments"]["query"] == "test"
    ok("_extract_tool_calls() 正确解析 OpenAI 格式")

    # 验证 _extract_openai_content
    content = mind._extract_openai_content(response)
    assert content == "我将搜索网络信息"
    ok("_extract_openai_content() 正确提取 content")

    # 验证 _parse_llm_response: 使用 content（模拟 _think_with_llm 的真实路径）
    task = Task(
        task_id="v1", type="general", description="验证",
        keywords=[], complexity=0.5, estimated_steps=3,
    )
    # 真实路径是先取 content 再传给 _parse_llm_response
    content = mind._extract_openai_content(response) or response
    thought = mind._parse_llm_response(content, task)
    assert thought.reasoning == "我将搜索网络信息"
    ok(f"_parse_llm_response(content) 解析正确 (reasoning='{thought.reasoning[:30]}')")

    # act(tool_calls) 路径验证
    from core.multi_agent_v2.agents import WorkAgent
    agent2 = WorkAgent(agent_id="act-test")
    agent2.register = MagicMock()
    agent2.start = MagicMock()
    agent2.receive_task = MagicMock()

    # Mock _execute_tool_calls 来验证 tool_calls 被传递
    captured = []

    async def mock_execute(tc_list):
        captured.extend(tc_list)
        return [{"tool_call": tc_list[0], "success": True, "result": "mock"}]

    agent2._execute_tool_calls = mock_execute

    tool_calls = [{"name": "search.web", "arguments": {"query": "test"}}]
    ar = await agent2.act(["步骤1"], tool_calls=tool_calls)
    assert ar.success is True
    assert len(captured) == 1
    assert captured[0]["name"] == "search.web"
    ok("act(tool_calls) 正确传递到 _execute_tool_calls()")


async def main():
    print(f"{B}{'='*55}{N}")
    print(f"{B}  真实 LLM 端到端验证{N}")
    print(f"{B}{'='*55}{N}")

    steps = [
        ("LLM 可用性", step1_check_llm_available),
        ("ToolRegistry", step2_verify_tool_registry),
        ("WorkAgent.run()", step3_worker_agent_run),
        ("tool_calls 解析路径", step4_verify_tool_calls_parsing),
    ]

    passed = 0
    results = []
    for name, fn in steps:
        try:
            r = await fn()
            if r:
                passed += 1
            results.append((name, r))
        except Exception as e:
            import traceback
            fail(f"{name}: {e}")
            traceback.print_exc()
            results.append((name, False))

    print(f"\n{B}{'='*55}{N}")
    print(f"{B}  汇总: {passed}/{len(steps)} 通过{N}")
    for name, r in results:
        mark = f"{G}✓{N}" if r else (f"{Y}~{N}" if r is None else f"{R}✗{N}")
        print(f"  {mark} {name}")
    print(f"{B}{'='*55}{N}")

    return 0 if passed == len(steps) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
