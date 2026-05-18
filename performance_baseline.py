#!/usr/bin/env python3
"""
性能基线分析器
输出profiling报告，定位Top3瓶颈
"""
import sys
import time
import cProfile
import pstats
from typing import List, Dict, Any

sys.path.insert(0, '.')


def profile_agent_initialization():
    """Profile: Agent初始化"""
# DEAD-IMPORT: from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
    
    print("\n" + "=" * 70)
    print("📊 性能分析1: Agent初始化")
    print("=" * 70)
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    # 测试代码
    agents = []
    for i in range(100):
        agents.append(WorkerAgent(name=f"perf_agent_{i}"))
    
    profiler.disable()
    
    # 分析结果
    stats = pstats.Stats(profiler)
    stats.sort_stats(pstats.SortKey.TIME)
    stats.print_stats(20)
    
    return stats


def profile_module_import():
    """Profile: 模块导入"""
    print("\n" + "=" * 70)
    print("📊 性能分析2: 核心模块导入")
    print("=" * 70)
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    # 测试导入
# DEAD-IMPORT: import core.multi_agent_v2
    import core.infrastructure
    
    profiler.disable()
    
    stats = pstats.Stats(profiler)
    stats.sort_stats(pstats.SortKey.TIME)
    stats.print_stats(20)
    
    return stats


def measure_throughput():
    """测量吞吐量"""
# DEAD-IMPORT: from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
    
    print("\n" + "=" * 70)
    print("⚡ 吞吐量测量")
    print("=" * 70)
    
    # 测量单次操作
    n_trials = 1000
    start = time.time()
    
    for i in range(n_trials):
        _ = WorkerAgent(name=f"throughput_{i}")
    
    elapsed = time.time() - start
    
    print(f"总耗时: {elapsed:.3f}s")
    print(f"操作数: {n_trials}")
    print(f"吞吐量: {n_trials / elapsed:.1f} 操作/秒")
    print(f"平均延迟: {(elapsed / n_trials) * 1000:.3f} 毫秒/操作")
    
    return elapsed


def find_bottlenecks(stats, top_n=3):
    """找出Top N瓶颈"""
    print("\n" + "=" * 70)
    print(f"🔍 Top {top_n} 性能瓶颈")
    print("=" * 70)
    
    bottlenecks = []
    for func, (cc, nc, tt, ct, callers) in stats.stats.items():
        # 只统计累计时间 > 0.01s的函数
        if ct > 0.01:
            bottlenecks.append((ct, func))
    
    bottlenecks.sort(reverse=True, key=lambda x: x[0])
    
    for i, (time_spent, func) in enumerate(bottlenecks[:top_n]):
        filename, line_no, func_name = func
        print(f"\n#{i+1} - 耗时: {time_spent:.4f}s")
        print(f"  文件: {filename}")
        print(f"  行号: {line_no}")
        print(f"  函数: {func_name}")
    
    return bottlenecks[:top_n]


def generate_report():
    """生成完整报告"""
    print("=" * 70)
    print("🚀 性能基线分析报告")
    print("=" * 70)
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python版本: {sys.version}")
    
    # 运行各个profiler
    stats1 = profile_agent_initialization()
    _ = profile_module_import()
    _ = measure_throughput()
    
    # 找出瓶颈
    bottlenecks = find_bottlenecks(stats1)
    
    # 总结
    print("\n" + "=" * 70)
    print("📋 总结")
    print("=" * 70)
    print("✅ 性能基线分析完成")
    print(f"✅ 已识别 {len(bottlenecks)} 个潜在瓶颈")
    
    return bottlenecks


if __name__ == "__main__":
    generate_report()
