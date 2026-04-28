"""测试Agent集群协作"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.agent_coordinator import AgentCoordinator
from core.cluster_manager import get_cluster_manager


async def test_agent_collaboration():
    """测试Agent集群协作"""
    print("=" * 70)
    print("测试: Agent集群协作")
    print("=" * 70)
    
    # 创建协调器
    coordinator = AgentCoordinator()
    
    # 启动协调器
    print("\n【步骤1: 启动Agent协调器】")
    await coordinator.start()
    print("✓ Agent协调器已启动")
    
    # 检查集群状态
    print("\n【步骤2: 检查集群状态】")
    agent_status = await coordinator.get_agent_status()
    print(f"✓ 已注册Agent数量: {len(agent_status.get('agents', {}))}")
    print(f"✓ 路由评分: {agent_status.get('routing_scores', {})}")
    
    cluster_status = agent_status.get('cluster_status', {})
    print(f"✓ 熔断状态: {cluster_status.get('circuit_breakers', {})}")
    print(f"✓ 队列状态: {cluster_status.get('queue_status', {})}")
    
    # 测试任务协调
    print("\n【步骤3: 测试任务协调】")
    test_task = {
        "type": "search_website",
        "params": {
            "url": "https://example.com",
            "query": "test"
        },
        "priority": 0.8
    }
    
    print(f"提交任务: {test_task['type']}")
    result = await coordinator.coordinate(test_task)
    
    print(f"✓ 任务状态: {result.get('success')}")
    print(f"✓ 任务ID: {result.get('task_id')}")
    print(f"✓ 子任务数量: {len(result.get('subtasks', []))}")
    
    # 测试多Agent协作
    print("\n【步骤4: 测试多Agent协作】")
    complex_task = {
        "type": "deep_thinking_research",
        "params": {
            "topic": "人工智能"
        },
        "priority": 0.9
    }
    
    print(f"提交复杂任务: {complex_task['type']}")
    result = await coordinator.coordinate(complex_task)
    
    print(f"✓ 任务状态: {result.get('success')}")
    print(f"✓ 任务ID: {result.get('task_id')}")
    print(f"✓ 子任务数量: {len(result.get('subtasks', []))}")
    
    if result.get('success'):
        final_result = result.get('result', {})
        print(f"✓ 整体状态: {final_result.get('status')}")
        print(f"✓ 成功子任务: {final_result.get('success_count')}")
        print(f"✓ 失败子任务: {final_result.get('failed_count')}")
    
    # 测试集群管理器功能
    print("\n【步骤5: 测试集群管理器功能】")
    cluster_manager = get_cluster_manager()
    
    # 测试熔断机制
    print("\n测试熔断机制...")
    for i in range(6):
        cluster_manager.circuit_breaker.record_failure("test_agent")
    print(f"✓ 熔断状态: {cluster_manager.circuit_breaker.get_state('test_agent').value}")
    print(f"✓ 是否允许请求: {cluster_manager.circuit_breaker.allow_request('test_agent')}")
    
    # 测试监控
    print("\n测试监控告警...")
    cluster_manager.monitor.record_metric("test_agent", 2.5, True)
    cluster_manager.monitor.record_metric("test_agent", 3.2, True)
    cluster_manager.monitor.record_metric("test_agent", 1.8, False)
    metrics = cluster_manager.monitor.get_metrics("test_agent")
    print(f"✓ 成功率: {metrics.get('success_rate', 0):.2f}")
    print(f"✓ 平均延迟: {metrics.get('avg_latency', 0):.2f}s")
    
    # 获取集群状态
    print("\n获取集群状态...")
    status = cluster_manager.get_cluster_status()
    print(f"✓ 熔断状态: {status.get('circuit_breakers', {})}")
    print(f"✓ 性能指标: {list(status.get('metrics', {}).keys())}")
    print(f"✓ 告警数量: {len(status.get('alerts', []))}")
    
    # 停止协调器
    print("\n【步骤6: 停止Agent协调器】")
    await coordinator.stop()
    print("✓ Agent协调器已停止")
    
    print("\n" + "=" * 70)
    print("Agent集群协作测试完成！")
    print("=" * 70)


async def test_integration():
    """测试完整集成"""
    print("\n" + "*" * 70)
    print("Agent集群协作完整集成测试")
    print("*" * 70)
    
    await test_agent_collaboration()
    
    print("\n" + "*" * 70)
    print("所有测试完成！")
    print("*" * 70)


if __name__ == "__main__":
    asyncio.run(test_integration())