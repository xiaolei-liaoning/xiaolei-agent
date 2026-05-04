#!/usr/bin/env python3
"""
消息总线与多Agent协作测试
测试目标：
1. 消息总线的发布-订阅机制
2. 多个Agent的并发任务处理
3. Agent之间的消息传递与协作
"""

import asyncio
import time
import json
from datetime import datetime
from typing import Dict, Any, List
from collections import defaultdict

from core.message_bus import message_bus
from core.multi_agent_system import ChatAgent, AgentTask, AgentType, get_agent_scheduler


class MessageBusTest:
    """消息总线测试"""
    
    def __init__(self):
        self.received_messages = defaultdict(list)
        self.subscriptions = {}
        
    async def subscribe_to_topics(self, topics: List[str]):
        """订阅多个主题"""
        for topic in topics:
            async def callback(msg, topic=topic):
                self.received_messages[topic].append({
                    "timestamp": datetime.now().isoformat(),
                    "message": msg
                })
                print(f"  收到 [{topic}] 消息: {msg.get('type', '')}")
            
            await message_bus.subscribe(topic, callback)
            self.subscriptions[topic] = callback
            print(f"✅ 订阅主题: {topic}")
    
    async def publish_test_messages(self):
        """发布测试消息"""
        print("\n📤 发布测试消息...")
        
        test_messages = [
            ("task_allocation", {
                "type": "task_assigned",
                "task_id": "test_001",
                "agent_type": "checker",
                "params": {"url": "https://example.com"}
            }),
            ("task_allocation", {
                "type": "task_assigned",
                "task_id": "test_002",
                "agent_type": "scraper",
                "params": {"keyword": "AI"}
            }),
            ("task_status", {
                "type": "task_progress",
                "task_id": "test_001",
                "progress": 0.5
            }),
            ("task_allocation", {
                "type": "task_assigned",
                "task_id": "test_003",
                "agent_type": "summarizer",
                "params": {"text": "这是需要总结的文本"}
            })
        ]
        
        for topic, msg in test_messages:
            await message_bus.publish(topic, msg)
            await asyncio.sleep(0.1)
        
        await asyncio.sleep(0.5)
        print(f"\n📊 消息总线测试结果:")
        for topic, msgs in self.received_messages.items():
            print(f"  [{topic}] 收到 {len(msgs)} 条消息")
    
    async def test_agent_concurrency(self):
        """测试多Agent并发"""
        print("\n" + "="*70)
        print("🚀 多Agent并发测试")
        print("="*70)
        
        chat_agent = ChatAgent()
        
        test_tasks = [
            "搜索人工智能最新动态",
            "分析今天天气",
            "计算12345+67890"
        ]
        
        print(f"\n📋 测试用例: {len(test_tasks)} 个任务")
        
        async def run_test_task(message: str, user_id: int):
            task = AgentTask(
                id=f"test_{int(time.time()*1000)}_{user_id}",
                type="chat",
                params={
                    "message": message,
                    "user_id": user_id,
                    "agent_id": "test",
                    "agent_name": "测试Agent"
                }
            )
            start = time.time()
            result = await chat_agent._run_task(task)
            elapsed = time.time() - start
            result.update({"elapsed": elapsed})
            return result
        
        start = time.time()
        tasks = []
        for i, message in enumerate(test_tasks):
            task = asyncio.create_task(run_test_task(message, i+1))
            tasks.append(task)
            await asyncio.sleep(0.1)
        
        print(f"\n⏳ 等待 {len(tasks)} 个并发任务完成...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start
        
        print(f"\n✅ 并发测试完成，总耗时: {total_time:.2f}秒")
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"  [{i+1}] ❌ 失败: {result}")
            else:
                print(f"  [{i+1}] ✅ 成功: {result.get('skill', 'N/A')}, 耗时 {result.get('elapsed', 0):.2f}秒")
        
        print(f"\n📊 性能统计:")
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        print(f"  成功: {success_count}/{len(results)}")
        print(f"  平均耗时: {total_time/max(1, len(results)):.2f}秒/任务")
        print(f"  系统吞吐: {success_count/total_time:.2f} QPS")
    
    async def test_agent_collaboration(self):
        """测试Agent协作"""
        print("\n" + "="*70)
        print("🤝 Agent协作测试")
        print("="*70)
        
        chat_agent = ChatAgent()
        
        complex_query = "搜索最新的AI新闻，然后分析并总结"
        
        print(f"\n💬 复杂查询: {complex_query}")
        print(f"\n📝 预期协作流程:")
        print("  1. 分析查询 → 拆分为搜索 + 总结")
        print("  2. 调用 Search Agent → 获取新闻")
        print("  3. 调用 Summarizer Agent → 总结新闻")
        print("  4. 合并结果 → 返回给用户")
        
        start = time.time()
        task = AgentTask(
            id=f"collab_test_{int(time.time()*1000)}",
            type="chat",
            params={
                "message": complex_query,
                "user_id": 999,
                "agent_id": "test",
                "agent_name": "测试"
            }
        )
        
        result = await chat_agent._run_task(task)
        elapsed = time.time() - start
        
        print(f"\n✅ 协作测试完成，耗时: {elapsed:.2f}秒")
        print(f"\n📄 结果预览:")
        reply = result.get('reply', 'N/A')[:300]
        print(f"  {reply}...")
        print(f"  Skill: {result.get('skill', 'N/A')}")
        thinking = result.get('thinking_process', 'N/A')
        print(f"  思考过程: {thinking[:200] if isinstance(thinking, str) else 'N/A'}...")
    
    async def cleanup(self):
        """清理订阅"""
        for topic, callback in self.subscriptions.items():
            try:
                await message_bus.unsubscribe(topic, callback)
            except:
                pass


async def main():
    """主测试函数"""
    print("="*70)
    print("🔧 消息总线与多Agent协作测试")
    print("="*70)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tester = MessageBusTest()
    
    try:
        # 测试1: 消息总线
        print("\n" + "="*70)
        print("📡 测试1: 消息总线")
        print("="*70)
        await tester.subscribe_to_topics([
            "task_allocation",
            "task_status",
            "agent_status"
        ])
        await tester.publish_test_messages()
        
        # 测试2: 多Agent并发
        await tester.test_agent_concurrency()
        
        # 测试3: Agent协作
        await tester.test_agent_collaboration()
        
        print("\n" + "="*70)
        print("🎉 所有测试完成！")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
