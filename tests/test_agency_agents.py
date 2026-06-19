"""测试 Agency Agents 角色匹配系统

验证 Worker Agent 能否根据真实场景自主匹配专家角色。

运行: python tests/test_agency_agents.py
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.skills.agency_agents import (
    get_agency_agent_matcher,
    get_worker_role_matcher,
)


async def test_basic_matching():
    """测试基础角色匹配"""
    print("\n" + "=" * 60)
    print("测试 1: 基础角色匹配")
    print("=" * 60)

    matcher = get_agency_agent_matcher()

    test_cases = [
        ("帮我设计一个高并发的后端系统，需要支持百万级用户", "后端架构"),
        ("写一篇小红书种草笔记，推广我们的新产品", "小红书运营"),
        ("优化我们的 React 前端性能，减少首屏加载时间", "前端开发"),
        ("搭建 CI/CD 流水线，实现自动化部署", "DevOps"),
        ("分析这个财务报表，给出投资建议", "财务分析"),
        ("设计一个游戏关卡，需要有趣的机制", "游戏设计"),
    ]

    for task, expected in test_cases:
        matched = await matcher.match(task, top_k=1)
        if matched:
            agent = matched[0]
            print(f"✅ 任务: {task[:40]}...")
            print(
                f"   匹配: {agent.get('emoji', '👤')} {agent.get('name', '未知')} "
                f"(匹配度: {agent.get('match_score', 0):.1f})"
            )
            print(f"   期望: {expected}")
            print()
        else:
            print(f"❌ 任务: {task[:40]}...")
            print(f"   未匹配到角色")
            print()


async def test_worker_role_assignment():
    """测试 Worker 角色分配"""
    print("\n" + "=" * 60)
    print("测试 2: Worker 角色分配")
    print("=" * 60)

    role_matcher = get_worker_role_matcher()

    task = "开发一个电商平台，需要后端架构、前端开发、数据库设计和安全审计"

    print(f"任务: {task}")
    print()

    assignments = await role_matcher.assign_roles_to_workers(task, worker_count=4)

    print(f"\n分配结果 ({len(assignments)} 个 Worker):")
    for assignment in assignments:
        print(
            f"  👷 Worker {assignment['worker_index']}: "
            f"{assignment['emoji']} {assignment['role']} "
            f"({assignment['category']}) - "
            f"匹配度: {assignment['match_score']:.1f}"
        )


def test_role_prompt_loading():
    """测试角色提示词加载"""
    print("\n" + "=" * 60)
    print("测试 3: 角色提示词加载")
    print("=" * 60)

    role_matcher = get_worker_role_matcher()

    agent_id = "engineering-backend-architect"
    prompt = role_matcher.get_role_prompt(agent_id)

    if prompt:
        print(f"✅ 成功加载角色提示词: {agent_id}")
        print(f"   长度: {len(prompt)} 字符")
        print(f"   前 200 字符: {prompt[:200]}...")
    else:
        print(f"❌ 未找到角色提示词: {agent_id}")


def test_list_all_agents():
    """测试列出所有 Agent"""
    print("\n" + "=" * 60)
    print("测试 4: 列出所有可用角色")
    print("=" * 60)

    matcher = get_agency_agent_matcher()

    categories = matcher.get_all_categories()
    print(f"\n共 {len(categories)} 个分类:")
    for cat in categories:
        agents = matcher.get_agents_by_category(cat)
        print(f"  📁 {cat}: {len(agents)} 个角色")

    print(f"\n总计: {len(matcher.agents)} 个专家角色")


def test_skill_execution():
    """测试 Skill 执行"""
    print("\n" + "=" * 60)
    print("测试 5: Skill 执行")
    print("=" * 60)

    import asyncio

    from core.skills.agency_agents.skill import AgencyAgentMatcherSkill

    async def run_test():
        skill = AgencyAgentMatcherSkill()

        result = await skill.execute(
            {"task": "帮我设计一个微服务架构的电商系统", "top_k": 3}
        )

        if result.get("success"):
            print(f"✅ Skill 执行成功")
            print(f"   回复: {result.get('reply', '')[:200]}...")
            print(f"   匹配数: {len(result.get('matched_agents', []))}")
        else:
            print(f"❌ Skill 执行失败: {result.get('error', '未知错误')}")

    asyncio.run(run_test())


async def main():
    print("\n" + "🚀" * 30)
    print("Agency Agents 角色匹配系统测试")
    print("🚀" * 30)

    await test_basic_matching()
    await test_worker_role_assignment()
    test_role_prompt_loading()
    test_list_all_agents()
    await test_skill_execution()

    print("\n" + "✅" * 30)
    print("所有测试完成！")
    print("✅" * 30 + "\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
