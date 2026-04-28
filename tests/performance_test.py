#!/usr/bin/env python3
"""
性能测试脚本：测试高并发场景下内存优化的效果
"""

import asyncio
import aiohttp
import time
import psutil
import json
from datetime import datetime

# 测试配置
BASE_URL = "http://localhost:8001"
CONCURRENT_REQUESTS = 50  # 并发请求数
TOTAL_REQUESTS = 1000  # 总请求数
TEST_DURATION = 60  # 测试持续时间（秒）

class PerformanceTest:
    """性能测试类"""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.requests_sent = 0
        self.requests_failed = 0
        self.response_times = []
        self.memory_usage_history = []
        self.cpu_usage_history = []
    
    async def test_chat_endpoint(self, session, message):
        """测试聊天端点"""
        try:
            start_time = time.time()
            async with session.post(f"{BASE_URL}/api/chat", json={"message": message}) as response:
                end_time = time.time()
                response_time = (end_time - start_time) * 1000  # 转换为毫秒
                self.response_times.append(response_time)
                self.requests_sent += 1
                
                if response.status != 200:
                    self.requests_failed += 1
                    print(f"请求失败: {response.status}")
        except Exception as e:
            self.requests_failed += 1
            print(f"请求异常: {e}")
    
    async def monitor_system(self):
        """监控系统资源使用"""
        while self.start_time and (time.time() - self.start_time) < TEST_DURATION:
            # 记录内存使用
            memory = psutil.virtual_memory()
            self.memory_usage_history.append({
                "timestamp": datetime.now().isoformat(),
                "memory_percent": memory.percent,
                "memory_used": memory.used / (1024 * 1024),  # 转换为MB
                "memory_free": memory.free / (1024 * 1024)
            })
            
            # 记录CPU使用
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_usage_history.append({
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": cpu_percent
            })
            
            await asyncio.sleep(1)
    
    async def run_test(self):
        """运行性能测试"""
        self.start_time = time.time()
        
        # 启动系统监控
        monitor_task = asyncio.create_task(self.monitor_system())
        
        # 准备测试消息
        test_messages = [
            "你好，我想了解一下人工智能的发展趋势",
            "请解释一下什么是机器学习",
            "如何提高Python代码的性能",
            "介绍一下深度学习的基本原理",
            "什么是自然语言处理"
        ]
        
        # 创建会话
        async with aiohttp.ClientSession() as session:
            tasks = []
            request_count = 0
            
            while request_count < TOTAL_REQUESTS and (time.time() - self.start_time) < TEST_DURATION:
                # 限制并发请求数
                if len(tasks) < CONCURRENT_REQUESTS:
                    message = test_messages[request_count % len(test_messages)]
                    task = asyncio.create_task(self.test_chat_endpoint(session, message))
                    tasks.append(task)
                    request_count += 1
                else:
                    # 等待部分任务完成
                    done, pending = await asyncio.wait(
                        tasks, 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    tasks = list(pending)
                
                await asyncio.sleep(0.01)  # 避免过于密集的请求
            
            # 等待所有任务完成
            if tasks:
                await asyncio.gather(*tasks)
        
        # 停止监控
        self.end_time = time.time()
        monitor_task.cancel()
        
        # 输出测试结果
        self.print_results()
        
        # 保存测试结果
        self.save_results()
    
    def print_results(self):
        """打印测试结果"""
        duration = self.end_time - self.start_time if self.end_time else 0
        success_rate = (self.requests_sent - self.requests_failed) / self.requests_sent * 100 if self.requests_sent > 0 else 0
        
        print("\n" + "=" * 80)
        print("性能测试结果")
        print("=" * 80)
        print(f"测试持续时间: {duration:.2f}秒")
        print(f"总请求数: {self.requests_sent}")
        print(f"失败请求数: {self.requests_failed}")
        print(f"成功率: {success_rate:.2f}%")
        
        if self.response_times:
            avg_response_time = sum(self.response_times) / len(self.response_times)
            max_response_time = max(self.response_times)
            min_response_time = min(self.response_times)
            print(f"平均响应时间: {avg_response_time:.2f}ms")
            print(f"最大响应时间: {max_response_time:.2f}ms")
            print(f"最小响应时间: {min_response_time:.2f}ms")
        
        if self.memory_usage_history:
            max_memory = max(item["memory_percent"] for item in self.memory_usage_history)
            avg_memory = sum(item["memory_percent"] for item in self.memory_usage_history) / len(self.memory_usage_history)
            print(f"最大内存使用率: {max_memory:.2f}%")
            print(f"平均内存使用率: {avg_memory:.2f}%")
        
        if self.cpu_usage_history:
            max_cpu = max(item["cpu_percent"] for item in self.cpu_usage_history)
            avg_cpu = sum(item["cpu_percent"] for item in self.cpu_usage_history) / len(self.cpu_usage_history)
            print(f"最大CPU使用率: {max_cpu:.2f}%")
            print(f"平均CPU使用率: {avg_cpu:.2f}%")
        print("=" * 80)
    
    def save_results(self):
        """保存测试结果到文件"""
        results = {
            "test_time": datetime.now().isoformat(),
            "duration": self.end_time - self.start_time if self.end_time else 0,
            "total_requests": self.requests_sent,
            "failed_requests": self.requests_failed,
            "success_rate": (self.requests_sent - self.requests_failed) / self.requests_sent * 100 if self.requests_sent > 0 else 0,
            "response_times": self.response_times,
            "memory_usage": self.memory_usage_history,
            "cpu_usage": self.cpu_usage_history
        }
        
        filename = f"performance_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"测试结果已保存到: {filename}")

if __name__ == "__main__":
    print("开始性能测试...")
    print(f"测试配置: 并发{CONCURRENT_REQUESTS}，总请求{1000}，持续{TEST_DURATION}秒")
    
    test = PerformanceTest()
    asyncio.run(test.run_test())