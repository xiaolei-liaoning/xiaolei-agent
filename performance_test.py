#!/usr/bin/env python3
"""性能测试脚本"""

import asyncio
import time
import sys
import os
import gc
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def timing_decorator(func):
    """计时装饰器"""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed_time = time.perf_counter() - start_time
        return result, elapsed_time
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_time = time.perf_counter() - start_time
        return result, elapsed_time
    
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper

def memory_usage():
    """获取当前内存使用情况"""
    try:
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)  # MB
    except ImportError:
        return 0.0

class PerformanceTest:
    """性能测试类"""
    
    def __init__(self):
        self.results = []
    
    def add_result(self, test_name, duration_ms, operations=1, memory_mb=0.0):
        """添加测试结果"""
        throughput = operations / (duration_ms / 1000) if duration_ms > 0 else 0
        self.results.append({
            "test_name": test_name,
            "duration_ms": duration_ms,
            "operations": operations,
            "throughput": throughput,
            "memory_mb": memory_mb
        })
    
    def print_summary(self):
        """打印性能测试总结"""
        print("\n" + "=" * 80)
        print("性能测试报告")
        print("=" * 80)
        print(f"{'测试项':<30} {'耗时(ms)':<10} {'操作数':<8} {'吞吐(ops/s)':<12} {'内存(MB)':<10}")
        print("-" * 80)
        
        for result in self.results:
            print(f"{result['test_name']:<30} {result['duration_ms']:<10.2f} {result['operations']:<8} {result['throughput']:<12.2f} {result['memory_mb']:<10.2f}")
        
        print("=" * 80)
        
        # 计算平均值
        if self.results:
            avg_duration = sum(r["duration_ms"] for r in self.results) / len(self.results)
            avg_throughput = sum(r["throughput"] for r in self.results) / len(self.results)
            print(f"\n平均耗时: {avg_duration:.2f} ms")
            print(f"平均吞吐: {avg_throughput:.2f} ops/s")

async def test_skill_dispatcher_performance(pt: PerformanceTest):
    """测试技能分发器性能 - 模拟测试（旧组件已重构）"""
    print("\n测试: 技能分发器性能（模拟测试）")
    
    # 模拟技能匹配器
    class MockSkillDispatcher:
        @staticmethod
        def match_skill(msg):
            """模拟技能匹配 - 简单关键词匹配"""
            skill_mapping = {
                "天气": "weather",
                "翻译": "translate",
                "分析": "analysis",
                "浏览器": "browser",
                "MCP": "mcp",
                "总结": "summary",
                "搜索": "search",
                "计算": "calculator",
                "爬取": "scrape",
                "自动化": "automation",
                "深度思考": "deep_thinking"
            }
            for keyword, skill in skill_mapping.items():
                if keyword in msg:
                    return skill
            return "default"
        
        @staticmethod
        def has_negation(msg):
            """模拟否定检测"""
            negations = ["不", "不要", "别", "非"]
            return any(neg in msg for neg in negations)
    
    dispatcher = MockSkillDispatcher()
    
    # 测试 match_skill 性能
    @timing_decorator
    def test_match_skill():
        test_messages = [
            "查天气", "翻译中文", "分析数据", "打开浏览器",
            "检查MCP", "总结文档", "搜索知识", "计算总和",
            "爬取网页", "自动化任务", "深度思考", "多步骤任务"
        ]
        for msg in test_messages:
            dispatcher.match_skill(msg)
    
    result, elapsed = test_match_skill()
    pt.add_result("match_skill(12次)", elapsed * 1000, 12, memory_usage())
    print(f"  match_skill: {elapsed*1000:.2f} ms")
    
    # 测试否定处理性能
    @timing_decorator
    def test_negation_processing():
        test_cases = [
            "不要聊天，帮我查天气",
            "不要用计算器，手动计算",
            "不要搜索，直接回答"
        ]
        for test in test_cases:
            dispatcher.has_negation(test)
    
    result, elapsed = test_negation_processing()
    pt.add_result("否定处理(3次)", elapsed * 1000, 3, memory_usage())
    print(f"  否定处理: {elapsed*1000:.2f} ms")
    
    # 测试反问检测性能
    @timing_decorator
    def test_clarification_detection():
        # 简单的模拟反问检测
        test_messages = [
            "查天气",
            "帮我分析一下",
            "打开文件",
            "搜索信息"
        ]
        for msg in test_messages:
            # 模拟生成问题
            questions = [f"你需要关于'{msg}'的什么信息？"]

    result, elapsed = test_clarification_detection()
    pt.add_result("反问检测(4次)", elapsed * 1000, 4, memory_usage())
    print(f"  反问检测: {elapsed*1000:.2f} ms")

async def test_multi_agent_performance(pt: PerformanceTest):
    """测试多Agent协同性能 - 模拟测试（旧组件已重构）"""
    print("\n测试: 多Agent协同性能（模拟测试）")
    
    # 模拟任务和Agent类
    class MockTask:
        def __init__(self, task_id, description, keywords):
            self.task_id = task_id
            self.description = description
            self.keywords = keywords
    
    class MockAgent:
        def __init__(self, capabilities):
            self.capabilities = capabilities
    
    class MockCapability:
        def __init__(self, name, description, keywords, confidence):
            self.name = name
            self.description = description
            self.keywords = keywords
            self.confidence = confidence
    
    # 创建模拟数据
    mock_agent = MockAgent([
        MockCapability("data_analysis", "数据分析", ["分析", "数据"], 0.85),
        MockCapability("web_scraping", "网页爬取", ["爬取", "网页"], 0.75),
        MockCapability("text_analysis", "文本分析", ["文本", "分析"], 0.80)
    ])
    
    # 模拟能力匹配计算性能
    @timing_decorator
    def test_capability_match():
        # 简单的关键词匹配模拟
        def _calculate_match(task, agent):
            score = 0.0
            for capability in agent.capabilities:
                for keyword in task.keywords:
                    if keyword in capability.keywords:
                        score += capability.confidence
            return min(score, 1.0)
        
        for i in range(100):
            task = MockTask(
                task_id=f"task_{i}",
                description=f"分析数据第{i}批",
                keywords=["分析", "数据"]
            )
            _calculate_match(task, mock_agent)
    
    result, elapsed = test_capability_match()
    pt.add_result("能力匹配计算(100次)", elapsed * 1000, 100, memory_usage())
    print(f"  能力匹配计算: {elapsed*1000:.2f} ms")
    
    # 模拟结果聚合性能
    @timing_decorator
    def test_result_aggregation():
        # 简单的结果聚合模拟
        for _ in range(10):
            subtasks = ["t1", "t2", "t3"]
            results = {
                "t1": {"success": True, "data": "r1", "time": 1.0},
                "t2": {"success": True, "data": "r2", "time": 2.0},
                "t3": {"success": True, "data": "r3", "time": 1.5},
            }
            # 简单聚合逻辑
            aggregated = {"total_tasks": len(subtasks), "success_tasks": sum(1 for r in results.values() if r["success"])}
    
    result, elapsed = test_result_aggregation()
    pt.add_result("结果聚合(10次)", elapsed * 1000, 10, memory_usage())
    print(f"  结果聚合: {elapsed*1000:.2f} ms")

async def test_fallback_performance(pt: PerformanceTest):
    """测试Fallback机制性能 - 模拟测试（旧组件已重构）"""
    print("\n测试: Fallback机制性能（模拟测试）")
    
    # 模拟需求分析
    @timing_decorator
    def test_requirement_analysis():
        test_cases = [
            "计算1到100的和",
            "今天星期几",
            "替换字符串中的空格",
            "筛选列表中的偶数",
            "下载网页内容",
            "读取文件内容",
            "判断条件是否满足",
            "排序数据列表"
        ]
        # 简单类型判断模拟
        for test in test_cases:
            req_type = "calculation" if "计算" in test else "string"
            if "筛选" in test:
                req_type = "list_operation"
            if "下载" in test:
                req_type = "network"
    
    result, elapsed = test_requirement_analysis()
    pt.add_result("需求类型分析(8次)", elapsed * 1000, 8, memory_usage())
    print(f"  需求类型分析: {elapsed*1000:.2f} ms")
    
    # 测试沙盒执行性能
    @timing_decorator
    async def test_sandbox_execution():
        # 模拟沙盒执行（不实际执行）
        test_code = """
def solve_problem(message: str) -> dict:
    try:
        import math
        result = sum(range(1, 1001))
        return {"success": True, "result": result, "message": "计算完成"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}
"""
        # 模拟编译检查
        compile(test_code, '<string>', 'exec')
    
    result, elapsed = await test_sandbox_execution()
    pt.add_result("沙盒执行(1次)", elapsed * 1000, 1, memory_usage())
    print(f"  沙盒执行: {elapsed*1000:.2f} ms")

async def test_mcp_check_performance(pt: PerformanceTest):
    """测试MCP检查技能性能 - 模拟测试（旧组件已重构）"""
    print("\n测试: MCP检查技能性能（模拟测试）")
    
    @timing_decorator
    async def test_mcp_check():
        # 模拟MCP检查 - 简单休眠模拟网络请求
        await asyncio.sleep(0.01)
        return {"servers": ["mcp1", "mcp2"], "status": "ok"}
    
    result, elapsed = await test_mcp_check()
    pt.add_result("MCP可用性检查", elapsed * 1000, 1, memory_usage())
    print(f"  MCP检查: {elapsed*1000:.2f} ms")

async def test_context_enhancement_performance(pt: PerformanceTest):
    """测试上下文增强性能"""
    print("\n测试: 上下文增强性能 - 跳过（待重构）")

async def test_concurrent_performance(pt: PerformanceTest):
    """测试并发性能 - 模拟测试"""
    print("\n测试: 并发性能（模拟测试）")
    
    # 使用前面的MockSkillDispatcher
    class MockSkillDispatcher:
        @staticmethod
        def match_skill(msg):
            return "default"
    
    dispatcher = MockSkillDispatcher()
    
    # 测试并发技能匹配
    @timing_decorator
    async def test_concurrent_match():
        async def match_task(msg):
            return dispatcher.match_skill(msg)
        
        tasks = [match_task(f"任务{i}") for i in range(100)]
        await asyncio.gather(*tasks)
    
    result, elapsed = await test_concurrent_match()
    pt.add_result("并发技能匹配(100次)", elapsed * 1000, 100, memory_usage())
    print(f"  并发技能匹配: {elapsed*1000:.2f} ms")

async def main():
    """运行所有性能测试"""
    print("=" * 80)
    print("性能测试套件")
    print("=" * 80)
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 清理内存
    gc.collect()
    
    pt = PerformanceTest()
    
    await test_skill_dispatcher_performance(pt)
    await test_multi_agent_performance(pt)
    await test_fallback_performance(pt)
    await test_mcp_check_performance(pt)
    await test_context_enhancement_performance(pt)
    await test_concurrent_performance(pt)
    
    pt.print_summary()
    
    print(f"\n结束时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("测试完成!")

if __name__ == "__main__":
    asyncio.run(main())