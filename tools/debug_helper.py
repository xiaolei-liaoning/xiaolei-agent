"""
交互式调试助手 - 提供便捷的调试功能
"""

import sys
import traceback
import cProfile
import pstats
import io
from typing import Any, Optional, Callable
from contextlib import contextmanager


class DebugHelper:
    """调试助手类"""
    
    @staticmethod
    def inspect_object(obj: Any, max_depth: int = 3):
        """
        深度检查对象
        
        Args:
            obj: 要检查的对象
            max_depth: 最大递归深度
        """
        print("\n" + "="*60)
        print(f"🔍 对象检查: {type(obj).__name__}")
        print("="*60)
        
        # 基本信息
        print(f"类型: {type(obj)}")
        print(f"ID: {id(obj)}")
        print(f"大小: {sys.getsizeof(obj)} bytes")
        
        # 属性列表
        if hasattr(obj, '__dict__'):
            print(f"\n📋 属性 ({len(obj.__dict__)}个):")
            for key, value in list(obj.__dict__.items())[:10]:
                print(f"  - {key}: {type(value).__name__} = {repr(value)[:50]}")
            if len(obj.__dict__) > 10:
                print(f"  ... 还有 {len(obj.__dict__) - 10} 个属性")
        
        # 方法列表
        methods = [m for m in dir(obj) if callable(getattr(obj, m)) and not m.startswith('_')]
        if methods:
            print(f"\n⚙️  方法 ({len(methods)}个):")
            for method in methods[:10]:
                print(f"  - {method}()")
            if len(methods) > 10:
                print(f"  ... 还有 {len(methods) - 10} 个方法")
        
        print("="*60 + "\n")
    
    @staticmethod
    def trace_call(func: Callable, *args, **kwargs):
        """
        追踪函数调用
        
        Args:
            func: 要追踪的函数
            args: 位置参数
            kwargs: 关键字参数
        """
        print(f"\n📞 调用追踪: {func.__qualname__}")
        print(f"   参数: args={args}, kwargs={kwargs}")
        
        try:
            result = func(*args, **kwargs)
            print(f"✅ 返回: {result}")
            return result
        except Exception as e:
            print(f"❌ 异常: {type(e).__name__}: {e}")
            traceback.print_exc()
            raise
    
    @staticmethod
    def profile_function(func: Callable, *args, num=10, **kwargs):
        """
        性能分析函数
        
        Args:
            func: 要分析的函数
            args: 位置参数
            num: 执行次数
            kwargs: 关键字参数
        """
        print(f"\n📊 性能分析: {func.__qualname__} (执行{num}次)")
        
        profiler = cProfile.Profile()
        profiler.enable()
        
        for _ in range(num):
            func(*args, **kwargs)
        
        profiler.disable()
        
        # 输出统计
        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats('cumulative')
        stats.print_stats(20)  # 显示前20行
        
        print(stream.getvalue())


@contextmanager
def debug_context(name: str = "debug"):
    """
    调试上下文管理器
    
    Usage:
        with debug_context("my_operation"):
            # 你的代码
            pass
    """
    import time
    start = time.time()
    print(f"\n🔧 [{name}] 开始执行...")
    
    try:
        yield
        elapsed = time.time() - start
        print(f"✅ [{name}] 完成 (耗时: {elapsed:.3f}s)")
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ [{name}] 失败 (耗时: {elapsed:.3f}s)")
        print(f"   错误: {type(e).__name__}: {e}")
        raise


def breakpoint_if(condition: bool, message: str = "断点触发"):
    """
    条件断点
    
    Args:
        condition: 触发条件
        message: 提示信息
    """
    if condition:
        print(f"\n🛑 {message}")
        import pdb; pdb.set_trace()


# 便捷函数
def quick_inspect(obj: Any):
    """快速检查对象（简写）"""
    DebugHelper.inspect_object(obj)


def quick_profile(func: Callable, *args, **kwargs):
    """快速性能分析（简写）"""
    DebugHelper.profile_function(func, *args, **kwargs)


# 导出
__all__ = ['DebugHelper', 'debug_context', 'breakpoint_if', 'quick_inspect', 'quick_profile']
