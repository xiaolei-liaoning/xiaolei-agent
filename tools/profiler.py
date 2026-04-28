"""
性能分析工具 - 提供多种性能分析功能
"""

import cProfile
import pstats
import time
import functools
from typing import Callable, Optional
from contextlib import contextmanager


class PerformanceProfiler:
    """性能分析器"""
    
    def __init__(self):
        self.profiles = {}
    
    def profile_function(self, func: Callable, num_calls: int = 100):
        """
        分析函数性能
        
        Args:
            func: 要分析的函数
            num_calls: 调用次数
        """
        print(f"\n📊 性能分析: {func.__qualname__} (调用{num_calls}次)")
        
        profiler = cProfile.Profile()
        profiler.enable()
        
        for _ in range(num_calls):
            func()
        
        profiler.disable()
        
        # 输出统计
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        
        print("\n📈 性能统计（前20个最耗时的函数）:")
        print("-" * 80)
        stats.print_stats(20)
        
        # 保存结果
        self.profiles[func.__qualname__] = stats
        
        return stats
    
    def compare_functions(self, funcs: list, num_calls: int = 100):
        """
        比较多个函数的性能
        
        Args:
            funcs: 函数列表
            num_calls: 每个函数的调用次数
        """
        print(f"\n🔍 函数性能对比 (各调用{num_calls}次)")
        print("="*80)
        
        results = []
        for func in funcs:
            start = time.time()
            
            profiler = cProfile.Profile()
            profiler.enable()
            
            for _ in range(num_calls):
                func()
            
            profiler.disable()
            elapsed = time.time() - start
            
            results.append({
                'name': func.__qualname__,
                'time': elapsed,
                'calls': num_calls
            })
            
            print(f"{func.__qualname__:40s} {elapsed:.4f}s")
        
        print("="*80)
        
        # 找出最快的
        fastest = min(results, key=lambda x: x['time'])
        print(f"\n🏆 最快: {fastest['name']} ({fastest['time']:.4f}s)")
        
        return results


@contextmanager
def timer_context(name: str = "operation"):
    """
    计时上下文管理器
    
    Usage:
        with timer_context("my_operation"):
            # 你的代码
            pass
    """
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        print(f"⏱️  [{name}] 耗时: {elapsed:.4f}s")


def profile_decorator(func: Callable):
    """
    性能分析装饰器
    
    Usage:
        @profile_decorator
        def my_function():
            pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()
        
        result = func(*args, **kwargs)
        
        profiler.disable()
        
        print(f"\n📊 {func.__qualname__} 性能分析:")
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        stats.print_stats(10)
        
        return result
    
    return wrapper


def benchmark(func: Callable, iterations: int = 1000):
    """
    基准测试
    
    Args:
        func: 要测试的函数
        iterations: 迭代次数
    
    Returns:
        平均执行时间（秒）
    """
    times = []
    
    for _ in range(iterations):
        start = time.time()
        func()
        end = time.time()
        times.append(end - start)
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    print(f"\n📈 基准测试结果: {func.__qualname__}")
    print(f"   迭代次数: {iterations}")
    print(f"   平均时间: {avg_time*1000:.3f}ms")
    print(f"   最短时间: {min_time*1000:.3f}ms")
    print(f"   最长时间: {max_time*1000:.3f}ms")
    
    return avg_time


# 全局分析器实例
global_profiler = PerformanceProfiler()


# 便捷函数
def quick_profile(func: Callable, num_calls: int = 100):
    """快速性能分析"""
    return global_profiler.profile_function(func, num_calls)


def quick_benchmark(func: Callable, iterations: int = 1000):
    """快速基准测试"""
    return benchmark(func, iterations)


# 导出
__all__ = [
    'PerformanceProfiler',
    'timer_context',
    'profile_decorator',
    'benchmark',
    'global_profiler',
    'quick_profile',
    'quick_benchmark'
]
