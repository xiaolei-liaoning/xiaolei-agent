"""Benchmark Integration Test — AssetOpsBench + WebArena 风格任务

测试小雷版 agent 在工业运维和 Web 操作类任务上的能力。
- AssetOpsBench: 工业4.0振动分析场景（需CouchDB）
- WebArena: Web操作任务（需Docker环境）
- 本地模式: 模拟类似风格的任务，无需外部服务
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

import pytest

REPO = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault('XIAOLEI_REAL_LLM', '1')

from core.engine.llm_backend import GLMBackend
from core.multi_agent_v2.tools.tool_registry import get_tool_registry


@dataclass
class TestResult:
    scenario_id: str
    category: str
    task: str
    tool_calls: List[dict]
    content: str
    profiles_used: List[str]
    success: bool
    error: str = ""
    uses_subagent: bool = False


def load_assetops_scenarios():
    """加载 AssetOpsBench 本地振动分析场景"""
    fpath = Path("/Users/leiyuxuan/Desktop/AssetOpsBench/src/scenarios/local/vibration_utterance.json")
    if not fpath.exists():
        return []
    with open(fpath) as f:
        data = json.load(f)
    return [{"category": s["category"], "task": s["text"], "id": s["id"]} for s in data]


SYSTEM_PROMPT = """你是小雷 Agent orchestrator。
你可以用 task 工具派子代理完成任务。
- task: 派单个子代理处理复杂任务（可选 explore/analyze/read_write/build/general profile）
- 面对多步骤、多文件、多模块任务时，必须派子代理并行工作
- 推荐：分析类→analyze/read_write，搜索类→explore，写代码→build
"""


async def run_single_task(backend, reg, task: str, system: str, timeout: int = 35) -> TestResult:
    task_tool = reg._tools.get('task')
    if not task_tool:
        return TestResult("", "", task, [], "", [], False, "task tool not found")

    tool_def = {'type': 'function', 'function': {
        'name': task_tool.name,
        'description': task_tool.description,
        'parameters': task_tool.parameters,
    }}
    try:
        resp = await asyncio.wait_for(
            backend.chat_structured([
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': task},
            ], tools=[tool_def]),
            timeout=timeout,
        )
        profiles = []
        tool_calls = []
        if resp.tool_calls:
            for tc in resp.tool_calls:
                args = json.loads(tc['function']['arguments']) if isinstance(tc['function']['arguments'], str) else tc['function']['arguments']
                profiles.append(args.get('subagent_type', '?'))
                tool_calls.append({'name': tc['function']['name'], 'profile': args.get('subagent_type')})
        return TestResult(
            scenario_id="", category="", task=task,
            tool_calls=tool_calls, content=resp.content or "",
            profiles_used=profiles,
            success=len(resp.tool_calls) > 0,
        )
    except asyncio.TimeoutError:
        return TestResult("", "", task, [], "", [], False, "timeout")
    except Exception as e:
        return TestResult("", "", task, [], "", [], False, str(e))


async def run_tests():
    backend = GLMBackend(api_key=os.getenv('AGNES_API_KEY', ''))
    reg = get_tool_registry()
    await reg.discover_all()

    # 设计测试用例
    test_cases = [
        # AssetOpsBench 风格（工业运维）
        ("assetops-knowledge", "Knowledge Query",
         "分析以下工业场景：一个 Chiller 6 压缩机的振动数据异常，"
         "FFT频谱显示在轴承故障频率附近有峰值。请分析可能的故障类型和严重程度。"),
        ("assetops-diagnosis", "Diagnosis",
         "给定以下工作订单数据，分析设备故障模式：主要症状是轴承过热、振动升高、"
         "油液分析显示金属颗粒。请诊断根因并提出维护建议。"),
        ("assetops-calculation", "Bearing Analysis",
         "计算 6205 轴承在 1800 RPM 下的特征频率（BPFO, BPFI, BSF, FTF），"
         "轴承参数：9个滚珠，直径7.938mm，节圆直径38.5mm。"),
        # WebArena 风格（Web操作）
        ("web-search", "Web Search",
         "搜索并总结 2024 年最新的大语言模型 Agent 框架有哪些，"
         "比较它们的特点和适用场景，输出结构化对比报告。"),
        ("web-analysis", "Web Analysis",
         "分析 /Users/leiyuxuan/Desktop/hermes-agent 项目的架构，"
         "包括核心技术栈、目录结构、扩展机制，输出架构文档。"),
        # 复杂多步骤任务
        ("complex-multi", "Complex",
         "对 /Users/leiyuxuan/Desktop/webarena 项目进行全面分析：\n"
         "1. 统计代码文件和行数\n"
         "2. 分析核心模块和架构\n"
         "3. 找出潜在的改进点\n"
         "4. 输出结构化评估报告"),
    ]

    print(f"\n{'='*65}")
    print(f"  Benchmark 集成测试 — 小雷版 Agent")
    print(f"  场景数: {len(test_cases)}")
    print(f"  LLM: Agnes-2.5-flash")
    print(f"{'='*65}")

    results = []
    for sid, cat, task in test_cases:
        print(f"\n[{cat}] {task[:60]}...")
        r = await run_single_task(backend, reg, task, SYSTEM_PROMPT)
        r.scenario_id = sid
        r.category = cat
        results.append(r)
        status = "✓" if r.success else "✗"
        print(f"  {status} tools={len(r.tool_calls)}, content_len={len(r.content)}")
        if r.tool_calls:
            print(f"      → profiles: {r.profiles_used}")
        if r.error:
            print(f"      → ERR: {r.error}")

    # 汇总
    passed = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    print(f"\n{'='*65}")
    print(f"  结果: {len(passed)}/{len(results)} 任务触发子代理")
    if failed:
        print(f"  未触发工具的任务:")
        for r in failed:
            print(f"    - [{r.category}] {r.task[:50]}")
    print(f"{'='*65}\n")
    return results


if __name__ == "__main__":
    results = asyncio.run(run_tests())
    # 返回非零如果所有任务都没触发工具
    sys.exit(0 if any(r.success for r in results) else 1)
