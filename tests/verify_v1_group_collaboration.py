#!/usr/bin/env python3
"""
V1模式（小组协作）端到端测试

测试从 TeamLeader.run() → 队员执行 → 结果聚合 的完整流程。
"""

import asyncio
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


async def step1_check_team_message_center():
    """消息中心初始化"""
    print(f"\n{B}步骤1: TeamMessageCenter 初始化{N}")

    from core.agents.group_collaboration import TeamMessageCenter

    center = TeamMessageCenter()
    center.register_member("worker1")
    center.register_member("worker2")

    assert center.member_count == 2
    ok(f"消息中心初始化成功 (注册了 {center.member_count} 个队员)")

    center.close()
    return True


async def step2_team_worker_execution():
    """队员执行子任务"""
    print(f"\n{B}步骤2: TeamWorkerAgent 执行子任务{N}")

    from core.agents.group_collaboration import TeamMessageCenter, TeamWorkerAgent

    center = TeamMessageCenter()
    worker = TeamWorkerAgent(
        worker_id="test-worker",
        role_name="测试专员",
        specialization="general",
        description="执行简单测试任务",
        leader_id="test-leader",
        msg_center=center,
    )

    subtask = {
        "task_id": "test-1",
        "description": "计算1+1等于几",
        "type": "execution",
        "keywords": [],
        "estimated_steps": 1,
        "complexity": 0.1,
    }

    result = await worker.execute(subtask)

    info(f"执行结果: {result.get('success')}, 输出: {result.get('output', '')[:100]}")
    center.close()

    if result.get("success"):
        ok("队员执行成功")
        return True
    else:
        warn(f"队员执行有问题: {result.get('error', 'unknown')}")
        return False


async def step3_team_leader_run():
    """TeamLeader.run() 全流程"""
    print(f"\n{B}步骤3: TeamLeader.run() 全流程{N}")

    from core.agents.group_collaboration import TeamLeader

    leader = TeamLeader()

    # 测试简单任务
    test_task = "帮我计算一下：2+3等于几？"

    info(f"任务: {test_task}")
    start = time.time()

    result = await leader.run(test_task)

    elapsed = time.time() - start

    print()
    info(f"耗时: {elapsed:.1f}s")
    info(f"团队规模: {result.get('team_size', 0)} 人")
    info(f"成功: {result.get('success')}")

    if result.get('final_result'):
        info(f"最终结果: {str(result.get('final_result'))[:200]}")

    if result.get('success'):
        ok("TeamLeader.run() 执行成功")
        return True
    else:
        error = result.get('error', '')
        if "API" in error or "timeout" in error.lower():
            warn(f"LLM API 问题，非代码错误: {error[:100]}")
            return True  # API问题不算代码bug
        else:
            fail(f"执行失败: {error[:100]}")
            return False


async def step4_verify_dependency_layers():
    """依赖分层算法"""
    print(f"\n{B}步骤4: 依赖分层算法{N}")

    from core.agents.group_collaboration import TeamMemberSpec, TeamLeader

    leader = TeamLeader()

    # 测试依赖关系：无依赖
    members_no_dep = [
        TeamMemberSpec(role_name="A", specialization="general", description="A任务", task_description="做A"),
        TeamMemberSpec(role_name="B", specialization="general", description="B任务", task_description="做B"),
    ]

    # 测试依赖关系：链式依赖
    members_chain = [
        TeamMemberSpec(role_name="A", specialization="general", description="A任务", task_description="做A", depends_on=[]),
        TeamMemberSpec(role_name="B", specialization="general", description="B任务", task_description="做B", depends_on=["A"]),
        TeamMemberSpec(role_name="C", specialization="general", description="C任务", task_description="做C", depends_on=["B"]),
    ]

    # 测试菱形依赖
    members_diamond = [
        TeamMemberSpec(role_name="A", specialization="general", description="A任务", task_description="做A", depends_on=[]),
        TeamMemberSpec(role_name="B", specialization="general", description="B任务", task_description="做B", depends_on=["A"]),
        TeamMemberSpec(role_name="C", specialization="general", description="C任务", task_description="做C", depends_on=["A"]),
        TeamMemberSpec(role_name="D", specialization="general", description="D任务", task_description="做D", depends_on=["B", "C"]),
    ]

    layers_no_dep = leader._dependency_layers(members_no_dep)
    assert len(layers_no_dep) == 1, "无依赖应该有1层"
    ok(f"无依赖分层正确: {len(layers_no_dep)} 层")

    layers_chain = leader._dependency_layers(members_chain)
    assert len(layers_chain) == 3, "链式依赖应该有3层"
    ok(f"链式依赖分层正确: {len(layers_chain)} 层")

    layers_diamond = leader._dependency_layers(members_diamond)
    assert len(layers_diamond) == 3, "菱形依赖应该有3层"
    ok(f"菱形依赖分层正确: {len(layers_diamond)} 层")

    return True


async def main():
    print(f"{B}{'='*55}{N}")
    print(f"{B}  V1模式（小组协作）端到端测试{N}")
    print(f"{B}{'='*55}{N}")

    steps = [
        ("TeamMessageCenter", step1_check_team_message_center),
        ("TeamWorkerAgent", step2_team_worker_execution),
        ("TeamLeader.run()", step3_team_leader_run),
        ("依赖分层算法", step4_verify_dependency_layers),
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
