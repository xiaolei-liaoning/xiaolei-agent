#!/usr/bin/env python3
"""测试 V1 Agent 消息总线集成"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_message_bus():
    """测试消息总线通信"""
    print("=" * 60)
    print("测试 V1 Agent 消息总线集成")
    print("=" * 60)
    
    try:
        from core.agent_system import V1LeaderPool, LLMAgent, AgentRole
        
        # 1. 通信中心（由 V1LeaderPool 内部管理）
        print("\n1. 获取通信中心...")
        # ponytail: CommunicationCenter 已随 core.agents 删除，V1LeaderPool 内部管理通信
        print("   ✅ 由 V1LeaderPool 内部管理")
        
        # 2. 创建 Agent 池
        print("2. 创建 V1LeaderPool...")
        pool = V1LeaderPool()
        
        # 3. 初始化工具注册表
        print("3. 初始化工具注册表...")
        await pool._ensure_tool_registry()
        
        if pool._tool_registry:
            tools_count = pool._tool_registry.count
            print(f"   ✅ 工具注册表已初始化，共 {tools_count} 个工具")
        
        # 4. 创建队伍（会自动注册到通信中心）
        print("4. 创建 1 队长 + 2 队员...")
        leader, workers = await pool.create_team(worker_count=2, max_workers=3)
        
        print(f"   队长: {leader.name}")
        print(f"   队员: {[w.name for w in workers]}")
        
        # 5. 检查通信中心注册
        print("\n5. 检查通信中心注册...")
        online_agents = comm_center.get_online_agents()
        print(f"   在线 Agents: {online_agents}")
        
        # 6. 测试消息发送
        print("\n6. 测试消息发送...")
        msg_id = await leader.send_message(workers[0].name, {"test": "hello"}, msg_type="test")
        print(f"   ✅ 队长 → 队员1 消息已发送: {msg_id}")
        
        # 7. 测试知识存储
        print("\n7. 测试知识存储...")
        await leader.store_knowledge(
            "test:knowledge",
            {"data": "测试知识"},
            tags={"test", "knowledge"},
        )
        print("   ✅ 知识已存储")
        
        # 8. 测试知识搜索
        print("\n8. 测试知识搜索...")
        results = await workers[0].search_knowledge("test")
        print(f"   ✅ 搜索结果: {len(results)} 条")
        for key, entry in results.items():
            print(f"      - {key}: {entry.get('meta', {}).get('summary', '')[:50]}")
        
        # 9. 测试进度发布
        print("\n9. 测试进度发布...")
        await leader.publish_progress("测试进度")
        print("   ✅ 进度已发布")
        
        # 10. 清理
        print("\n10. 清理资源...")
        await pool.discard([leader] + workers)
        
        print("\n" + "=" * 60)
        print("✅ 消息总线集成测试完成！")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_message_bus())
    sys.exit(0 if success else 1)
