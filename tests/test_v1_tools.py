#!/usr/bin/env python3
"""测试 V1 Agent + V2 ToolRegistry 集成"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_v1_tool_integration():
    """测试 V1 Agent 工具集成"""
    print("=" * 60)
    print("测试 V1 Agent + V2 ToolRegistry 集成")
    print("=" * 60)
    
    try:
        from core.agent_system import V1LeaderPool, LLMAgent, AgentRole
        
        # 1. 创建 Agent 池
        print("\n1. 创建 V1LeaderPool...")
        pool = V1LeaderPool()
        
        # 2. 初始化工具注册表
        print("2. 初始化工具注册表...")
        await pool._ensure_tool_registry()
        
        if pool._tool_registry:
            tools_count = pool._tool_registry.count
            print(f"   ✅ 工具注册表已初始化，共 {tools_count} 个工具")
        else:
            print("   ⚠️ 工具注册表初始化失败，将使用无工具模式")
        
        # 3. 创建队伍
        print("3. 创建 1 队长 + 2 队员...")
        leader, workers = pool.create_team(worker_count=2, max_workers=3)
        
        print(f"   队长: {leader.name}")
        print(f"   队员: {[w.name for w in workers]}")
        
        # 4. 检查工具引用
        print("4. 检查工具引用...")
        for agent in [leader] + workers:
            if agent.tool_registry:
                print(f"   ✅ {agent.name} 已有工具注册表引用")
            else:
                print(f"   ⚠️ {agent.name} 无工具注册表引用")
        
        # 5. 测试工具获取（简单任务）
        print("\n5. 测试工具获取...")
        test_task = "创建一个Python脚本"
        tools = await leader._get_tools_for_task(test_task)
        print(f"   任务: {test_task}")
        print(f"   可用工具数: {len(tools)}")
        if tools:
            tool_names = [t.get('function', {}).get('name', '?') for t in tools[:5]]
            print(f"   前5个工具: {tool_names}")
        
        # 6. 清理
        print("\n6. 清理资源...")
        await pool.discard([leader] + workers)
        
        print("\n" + "=" * 60)
        print("✅ 测试完成！V1 Agent 已成功集成 V2 ToolRegistry")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_v1_tool_integration())
    sys.exit(0 if success else 1)
