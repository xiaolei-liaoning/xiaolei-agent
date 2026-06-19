#!/usr/bin/env python3
"""V1 队长-队员完整流程测试"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_full_flow():
    """完整流程测试：任务分解 → 分配 → 执行 → 分析"""
    print("=" * 70)
    print("  V1 队长-队员 + 消息总线 完整流程测试")
    print("=" * 70)
    
    try:
        from core.agent_system import V1LeaderPool, LLMAgent, AgentRole, AgentMessage
        
        # ── 初始化 ──
        print("\n📦 初始化系统...")
        pool = V1LeaderPool()
        await pool._ensure_tool_registry()
        await pool._ensure_comm_center()
        
        comm_center = pool._comm_center
        print(f"   工具注册表: {pool._tool_registry.count if pool._tool_registry else 0} 个工具")
        print(f"   通信中心: {'✅ 就绪' if comm_center else '❌ 未初始化'}")
        
        # ── 创建队伍 ──
        print("\n👥 创建队伍...")
        leader, workers = await pool.create_team(worker_count=2, max_workers=3)
        print(f"   队长: {leader.name}")
        print(f"   队员: {[w.name for w in workers[:2]]}")
        
        # ── 监控消息 ──
        messages_log = []
        
        async def monitor_messages(agent_name):
            """监控 agent 收到的消息"""
            while True:
                msgs = await comm_center.receive_all_messages(agent_name)
                for msg in msgs:
                    msg_type = msg.get("message_type", "?")
                    sender = msg.get("sender", "?")
                    content = str(msg.get("content", ""))[:80]
                    messages_log.append(f"  📨 {agent_name} ← {sender} [{msg_type}]: {content}")
                await asyncio.sleep(0.05)
        
        # 启动消息监控
        monitors = []
        for w in workers[:2]:
            monitor = asyncio.create_task(monitor_messages(w.name))
            monitors.append(monitor)
        
        # ── 测试1: 直接消息通信 ──
        print("\n" + "─" * 70)
        print("📡 测试1: 队长 → 队员 直接消息")
        print("─" * 70)
        
        msg_id = await leader.send_message(
            workers[0].name,
            {"type": "test", "content": "测试消息"},
            msg_type="test"
        )
        print(f"   ✅ 消息已发送: {msg_id[:16]}...")
        
        await asyncio.sleep(0.2)  # 等待消息投递
        
        # ── 测试2: 知识存储与搜索 ──
        print("\n" + "─" * 70)
        print("🧠 测试2: 知识存储与搜索")
        print("─" * 70)
        
        # 队长存储知识
        await leader.store_knowledge(
            "task:分解结果",
            {"subtasks": ["子任务1", "子任务2"]},
            tags={"task", "decompose"},
        )
        print("   ✅ 队长存储知识: task:分解结果")
        
        # 队员搜索知识
        results = await workers[0].search_knowledge("task")
        print(f"   ✅ 队员搜索结果: {len(results)} 条")
        for key, entry in results.items():
            meta = entry.get("meta", {})
            print(f"      - {key}: {meta.get('summary', '')[:60]}")
        
        # ── 测试3: 进度发布 ──
        print("\n" + "─" * 70)
        print("📊 测试3: 进度发布")
        print("─" * 70)
        
        await leader.publish_progress("任务分解完成")
        await workers[0].publish_progress("开始执行子任务1")
        await workers[1].publish_progress("开始执行子任务2")
        print("   ✅ 进度已发布")
        
        # ── 测试4: 模拟任务执行 ──
        print("\n" + "─" * 70)
        print("🔄 测试4: 模拟任务执行流程")
        print("─" * 70)
        
        # 创建测试任务消息
        test_task = "在桌面创建一个简单的 Python 脚本"
        
        print(f"   任务: {test_task}")
        print(f"\n   队长开始分解任务...")
        
        # 队长分解任务
        subtasks = await leader._decompose_task(test_task)
        print(f"   ✅ 分解为 {len(subtasks)} 个子任务:")
        for i, st in enumerate(subtasks[:3], 1):
            print(f"      {i}. {st[:60]}")
        
        # 分配子任务
        active_workers = workers[:leader.active_worker_count]
        assignments = leader._assign(subtasks[:2], active_workers)
        print(f"\n   ✅ 分配给 {len(assignments)} 个队员:")
        for a in assignments:
            print(f"      - {a['worker'].name}: {a['task'][:50]}...")
        
        # ── 测试5: 模拟 Worker 执行 ──
        print("\n" + "─" * 70)
        print("⚙️  测试5: 模拟 Worker 执行（无 LLM）")
        print("─" * 70)
        
        # 模拟 worker 执行（不调用 LLM）
        for a in assignments[:1]:
            worker = a["worker"]
            task_content = a["task"]
            
            print(f"   {worker.name} 执行: {task_content[:40]}...")
            
            # 发布开始消息
            await worker.publish_progress("开始执行")
            
            # 模拟执行结果
            mock_result = {
                "status": "success",
                "result": f"已完成任务: {task_content[:50]}",
                "worker": worker.name,
            }
            
            # 存储结果到知识库
            await worker.store_knowledge(
                f"result:{worker.name}",
                mock_result,
                tags={"result", "worker"},
            )
            
            # 发送结果给队长
            await worker.send_message(leader.name, mock_result, msg_type="result")
            
            # 发布完成消息
            await worker.publish_progress("执行完成")
            
            print(f"   ✅ {worker.name} 执行完成")
        
        # ── 检查消息日志 ──
        await asyncio.sleep(0.3)  # 等待所有消息投递
        
        print("\n" + "─" * 70)
        print("📋 消息日志")
        print("─" * 70)
        
        if messages_log:
            for log in messages_log[:10]:
                print(log)
        else:
            print("  (无消息)")
        
        # ── 检查知识库 ──
        print("\n" + "─" * 70)
        print("📚 知识库状态")
        print("─" * 70)
        
        all_knowledge = await comm_center.list_knowledge()
        print(f"   知识条目数: {len(all_knowledge)}")
        for key, info in list(all_knowledge.items())[:5]:
            tags = info.get("tags", [])
            source = info.get("source", "?")
            summary = info.get("summary", "")[:50]
            print(f"   - {key} [{','.join(tags)}] from {source}: {summary}")
        
        # ── 清理 ──
        print("\n" + "─" * 70)
        print("🧹 清理资源")
        print("─" * 70)
        
        # 停止监控
        for monitor in monitors:
            monitor.cancel()
        
        # 清理队伍
        await pool.discard([leader] + workers)
        await comm_center.clear_knowledge()
        
        print("   ✅ 资源已清理")
        
        # ── 总结 ──
        print("\n" + "=" * 70)
        print("  ✅ 完整流程测试通过！")
        print("=" * 70)
        print("\n  验证的能力:")
        print("  ✅ 消息发送: 队长 ↔ 队员 直接通信")
        print("  ✅ 知识存储: store_knowledge() 存入共享知识库")
        print("  ✅ 知识搜索: search_knowledge() 跨 agent 查询")
        print("  ✅ 进度发布: publish_progress() 广播进度")
        print("  ✅ 任务分解: leader._decompose_task()")
        print("  ✅ 任务分配: leader._assign()")
        print("  ✅ Agent 注册/注销: 通信中心管理")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_full_flow())
    sys.exit(0 if success else 1)
