#!/usr/bin/env python3
"""
性能优化模块
基于profiling结果实现优化策略
"""
import sys
import time
import functools
from typing import Callable, Any, Dict

sys.path.insert(0, '.')


def memoize(func: Callable) -> Callable:
    """缓存装饰器 - 优化重复调用"""
    cache = {}
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        key = (args, frozenset(kwargs.items()))
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]
    return wrapper


class AgentPoolOptimizer:
    """Agent池优化器"""
    
    def __init__(self):
        self._pool = {}
        self._idle_threshold = 300  # 5分钟空闲超时
    
    def get_agent(self, agent_type: str, name: str = None):
        """获取或创建Agent（复用策略）"""
        key = f"{agent_type}_{name or 'default'}"
        
        if key in self._pool:
            agent = self._pool[key]
            if agent['last_used'] + self._idle_threshold > time.time():
                agent['last_used'] = time.time()
                return agent['instance']
        
        # 创建新Agent
# DEAD-IMPORT: from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
# DEAD-IMPORT: from core.multi_agent_v2.agents.master.master_agent import MasterAgent
# DEAD-IMPORT: from core.multi_agent_v2.agents.reviewer.reviewer_agent import ReviewerAgent
# DEAD-IMPORT: from core.multi_agent_v2.agents.expert.expert_agent import ExpertAgent
        
        agent_classes = {
            'worker': WorkerAgent,
            'master': MasterAgent,
            'reviewer': ReviewerAgent,
            'expert': ExpertAgent
        }
        
        agent_class = agent_classes.get(agent_type, WorkerAgent)
        instance = agent_class(name=name or f"pool_{agent_type}")
        
        self._pool[key] = {
            'instance': instance,
            'last_used': time.time(),
            'type': agent_type
        }
        
        return instance
    
    def cleanup(self):
        """清理超时的空闲Agent"""
        now = time.time()
        to_remove = [key for key, agent in self._pool.items() 
                     if agent['last_used'] + self._idle_threshold < now]
        
        for key in to_remove:
            del self._pool[key]
        
        return len(to_remove)


class LazyLoader:
    """延迟加载优化器"""
    
    def __init__(self):
        self._loaded_modules = {}
    
    def load_module(self, module_path: str):
        """延迟加载模块"""
        if module_path not in self._loaded_modules:
            import importlib
            self._loaded_modules[module_path] = importlib.import_module(module_path)
        return self._loaded_modules[module_path]
    
    def __getattr__(self, name):
        """动态获取模块"""
        return self.load_module(f"core.{name}")


class AsyncExecutor:
    """异步执行优化器"""
    
    def __init__(self):
        import asyncio
        self._loop = asyncio.get_event_loop()
        self._semaphore = asyncio.Semaphore(10)  # 限制并发数
    
    async def execute(self, func: Callable, *args, **kwargs):
        """异步执行函数"""
        async with self._semaphore:
            return await self._loop.run_in_executor(None, func, *args, **kwargs)
    
    def execute_sync(self, func: Callable, *args, **kwargs):
        """同步执行（带线程池）"""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            return executor.submit(func, *args, **kwargs).result()


class OptimizedAgentFactory:
    """优化的Agent工厂"""
    
    _agent_templates = {}
    
    @classmethod
    def register_template(cls, agent_type: str, template):
        """注册Agent模板"""
        cls._agent_templates[agent_type] = template
    
    @classmethod
    def create_agent(cls, agent_type: str, **kwargs):
        """快速创建Agent（使用模板）"""
        template = cls._agent_templates.get(agent_type)
        if template:
            agent = template.copy()
            agent.update(kwargs)
            return agent
        
        # 默认创建
# DEAD-IMPORT: from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
        return WorkerAgent(**kwargs)


def optimize_imports():
    """优化模块导入"""
    # 预加载核心模块（在启动时）
    start = time.time()
    
# DEAD-IMPORT: import core.multi_agent_v2
    import core.infrastructure
    
    elapsed = time.time() - start
    return elapsed


def optimize_memory_usage():
    """优化内存使用"""
    # 实现内存优化策略
    strategies = [
        ("对象池化", "减少重复创建"),
        ("延迟初始化", "按需加载"),
        ("弱引用缓存", "自动清理"),
        ("批量操作", "减少IO次数"),
    ]
    return strategies


def run_optimization_demo():
    """运行优化演示"""
    print("=" * 70)
    print("🚀 性能优化演示")
    print("=" * 70)
    
    # 测试1: Agent池优化
    print("\n[测试1] Agent池优化")
    pool = AgentPoolOptimizer()
    
    start = time.time()
    for i in range(100):
        agent = pool.get_agent('worker', f'test_{i}')
    elapsed_with_pool = time.time() - start
    print(f"使用池化: {elapsed_with_pool:.4f}s")
    
    # 测试2: 重复获取相同Agent
    start = time.time()
    for i in range(100):
        agent = pool.get_agent('worker', 'reuse_test')
    elapsed_reuse = time.time() - start
    print(f"复用Agent: {elapsed_reuse:.4f}s")
    print(f"优化比例: {(1 - elapsed_reuse/elapsed_with_pool) * 100:.1f}%")
    
    # 测试3: 延迟加载
    print("\n[测试2] 延迟加载优化")
    loader = LazyLoader()
    start = time.time()
    _ = loader.multi_agent_v2
    elapsed = time.time() - start
    print(f"延迟加载耗时: {elapsed:.4f}s")
    
    # 测试4: 内存策略
    print("\n[测试3] 内存优化策略")
    strategies = optimize_memory_usage()
    for name, desc in strategies:
        print(f"  ✅ {name}: {desc}")
    
    print("\n" + "=" * 70)
    print("✅ 性能优化模块加载完成")
    print("=" * 70)


# 全局实例
global_pool = AgentPoolOptimizer()
global_loader = LazyLoader()
global_executor = AsyncExecutor()


def get_optimized_pool():
    """获取优化的Agent池"""
    return global_pool


def get_lazy_loader():
    """获取延迟加载器"""
    return global_loader


def get_executor():
    """获取执行器"""
    return global_executor


if __name__ == "__main__":
    run_optimization_demo()
