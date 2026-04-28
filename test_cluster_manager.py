"""测试集群管理器功能"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.cluster_manager import (
    get_cluster_manager,
    AgentInstance,
    CircuitBreakerState
)


async def test_circuit_breaker():
    """测试熔断机制"""
    print("=" * 70)
    print("测试1: 熔断机制")
    print("=" * 70)
    
    cluster = get_cluster_manager()
    
    # 模拟连续失败
    print("\n模拟连续失败...")
    for i in range(6):
        cluster.circuit_breaker.record_failure("test_agent")
        state = cluster.circuit_breaker.get_state("test_agent")
        print(f"  失败{i+1}: 状态={state.value}")
    
    # 测试是否允许请求
    print("\n测试熔断状态...")
    allowed = cluster.circuit_breaker.allow_request("test_agent")
    print(f"  是否允许请求: {allowed}")
    
    # 模拟成功恢复
    print("\n模拟成功恢复...")
    cluster.circuit_breaker.record_success("test_agent")
    state = cluster.circuit_breaker.get_state("test_agent")
    print(f"  恢复后状态: {state.value}")


async def test_load_balancer():
    """测试负载均衡"""
    print("\n" + "=" * 70)
    print("测试2: 自适应负载均衡")
    print("=" * 70)
    
    cluster = get_cluster_manager()
    
    # 设置权重
    cluster.load_balancer.set_base_weight("search_engine", 2.0)
    cluster.load_balancer.set_base_weight("web_scraper", 1.5)
    
    # 注册实例
    print("\n注册Agent实例...")
    instances = [
        AgentInstance("search_engine", "search_001", load=0.3, success_rate=0.95),
        AgentInstance("search_engine", "search_002", load=0.7, success_rate=0.88),
        AgentInstance("search_engine", "search_003", load=0.2, success_rate=0.92),
    ]
    
    for inst in instances:
        cluster.load_balancer.register_instance(inst)
        print(f"  已注册: {inst.agent_type} - {inst.instance_id} (负载={inst.load})")
    
    # 选择Agent
    print("\n选择最优Agent实例...")
    selected = cluster.load_balancer.select_agent("search_engine")
    print(f"  选择的实例: {selected}")
    
    # 获取动态权重
    print("\n获取动态权重...")
    cluster.load_balancer.update_load("search_engine", 0.6)
    dynamic_weight = cluster.load_balancer.get_dynamic_weight("search_engine")
    print(f"  动态权重: {dynamic_weight:.4f}")


async def test_monitoring():
    """测试监控告警"""
    print("\n" + "=" * 70)
    print("测试3: 监控告警")
    print("=" * 70)
    
    cluster = get_cluster_manager()
    
    # 记录一些指标
    print("\n记录性能指标...")
    for i in range(10):
        success = i < 8  # 前8次成功，后2次失败
        latency = 2.0 + i * 0.3
        cluster.monitor.record_metric("test_agent", latency, success)
    
    # 获取指标
    print("\n获取性能指标...")
    metrics = cluster.monitor.get_metrics("test_agent")
    if metrics:
        print(f"  QPS: {metrics['qps']:.2f}")
        print(f"  平均延迟: {metrics['avg_latency']:.2f}s")
        print(f"  成功率: {metrics['success_rate']:.2f}")
        print(f"  最小延迟: {metrics['min_latency']:.2f}s")
        print(f"  最大延迟: {metrics['max_latency']:.2f}s")
    
    # 获取告警
    print("\n获取告警...")
    alerts = cluster.monitor.get_alerts(5)
    print(f"  告警数量: {len(alerts)}")
    for alert in alerts:
        print(f"    - {alert['type']}: {alert['message']}")


async def test_task_scheduler():
    """测试智能任务调度"""
    print("\n" + "=" * 70)
    print("测试4: 智能任务调度")
    print("=" * 70)
    
    cluster = get_cluster_manager()
    
    # 提交任务
    print("\n提交任务...")
    tasks = [
        {"type": "search", "priority": 8},
        {"type": "scrape", "priority": 5},
        {"type": "analyze", "priority": 10},
        {"type": "summarize", "priority": 3},
    ]
    
    for task in tasks:
        await cluster.scheduler.submit_task(task)
        print(f"  已提交: {task['type']} (优先级={task['priority']})")
    
    # 获取队列状态
    print("\n队列状态...")
    queue_status = cluster.scheduler.get_queue_status()
    for priority, count in sorted(queue_status.items(), reverse=True):
        if count > 0:
            print(f"  优先级{priority}: {count}个任务")
    
    # 预测执行时间
    print("\n预测执行时间...")
    predicted = cluster.scheduler.predict_execution_time("search")
    print(f"  search任务预测时间: {predicted:.2f}s")


async def test_cluster_integration():
    """测试集群集成"""
    print("\n" + "=" * 70)
    print("测试5: 集群集成")
    print("=" * 70)
    
    cluster = get_cluster_manager()
    
    # 启动集群
    print("\n启动集群管理器...")
    await cluster.start()
    
    # 注册实例
    cluster.load_balancer.register_instance(
        AgentInstance("search_engine", "search_001", load=0.4)
    )
    
    # 选择Agent
    print("\n选择Agent...")
    selected = cluster.select_agent("search_engine")
    print(f"  选择的Agent: {selected}")
    
    # 记录任务结果
    print("\n记录任务结果...")
    cluster.record_task_result("search_engine", 2.5, True)
    cluster.record_task_result("search_engine", 3.2, True)
    cluster.record_task_result("search_engine", 1.8, False)
    
    # 获取集群状态
    print("\n获取集群状态...")
    status = cluster.get_cluster_status()
    print(f"  熔断状态: {status['circuit_breakers']}")
    print(f"  性能指标: {status['metrics']}")
    print(f"  队列状态: {status['queue_status']}")
    print(f"  告警数量: {len(status['alerts'])}")
    
    # 停止集群
    print("\n停止集群管理器...")
    await cluster.stop()


async def main():
    """主测试函数"""
    print("\n" + "*" * 70)
    print("Agent集群管理器功能测试")
    print("*" * 70)
    
    await test_circuit_breaker()
    await test_load_balancer()
    await test_monitoring()
    await test_task_scheduler()
    await test_cluster_integration()
    
    print("\n" + "*" * 70)
    print("所有测试完成！")
    print("*" * 70)


if __name__ == "__main__":
    asyncio.run(main())