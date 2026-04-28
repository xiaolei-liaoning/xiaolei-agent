import asyncio
import time
import statistics
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.reasoning_engine import ReasoningEngine
from core.llm_backend import get_llm_router

class StressTest:
    def __init__(self):
        self.engine = ReasoningEngine()
        self.llm_router = get_llm_router()
        # 清空缓存，确保每次测试都能触发实际的API调用
        self.engine._cache = {}
        self.test_questions = [
            "人工智能的未来发展趋势是什么？",
            "如何学习Python编程？",
            "今天的天气怎么样？",
            "什么是机器学习？",
            "如何提高英语口语？",
            "世界上最高的山峰是什么？",
            "如何保持健康的生活方式？",
            "什么是区块链技术？",
            "如何准备高考？",
            "什么是云计算？"
        ]
        # 为每个问题添加随机后缀，避免缓存
        import random
        self.test_questions = [f"{q} {random.randint(1, 1000000)}" for q in self.test_questions]
    
    async def test_single_request(self, question: str, api: str) -> dict:
        """测试单个请求
        
        Args:
            question: 测试问题
            api: 使用的API (glm/deepseek)
            
        Returns:
            测试结果
        """
        start_time = time.time()
        try:
            # 切换到指定的API
            if api == "glm":
                # 使用GLM API
                self.llm_router.switch_model("glm-4-flash")
            elif api == "deepseek":
                # 使用DeepSeek API
                self.llm_router.switch_model("deepseek-v3")
            
            # 直接测试LLM API调用，绕过推理引擎的缓存和其他逻辑
            # 添加超时保护，避免GLM卡死整个测试
            response = await asyncio.wait_for(
                self.llm_router.chat([{"role": "user", "content": question}]),
                timeout=60  # 60秒超时
            )
            end_time = time.time()
            return {
                "question": question,
                "api": api,
                "success": True,
                "response_time": end_time - start_time,
                "response": response[:50] + "..." if len(response) > 50 else response
            }
        except asyncio.TimeoutError:
            end_time = time.time()
            return {
                "question": question,
                "api": api,
                "success": False,
                "response_time": end_time - start_time,
                "error": "请求超时"
            }
        except Exception as e:
            end_time = time.time()
            return {
                "question": question,
                "api": api,
                "success": False,
                "response_time": end_time - start_time,
                "error": str(e)
            }
    
    async def run_stress_test(self, concurrency: int, api: str) -> dict:
        """运行压力测试
        
        Args:
            concurrency: 并发数
            api: 使用的API (glm/deepseek)
            
        Returns:
            测试结果
        """
        start_time = time.time()
        results = []
        total_requests = 10  # 固定总请求数，确保每个并发数测试相同数量的请求
        
        # 使用信号量控制并发数量，避免系统过载
        semaphore = asyncio.Semaphore(concurrency)
        
        async def worker():
            nonlocal results
            while len(results) < total_requests:
                # 随机选择一个问题
                question = self.test_questions[len(results) % len(self.test_questions)]
                # 使用信号量控制并发
                async with semaphore:
                    print(f"  执行请求 {len(results) + 1}/{total_requests}")
                    result = await self.test_single_request(question, api)
                    results.append(result)
                    print(f"  请求 {len(results)}/{total_requests} 完成，响应时间: {result['response_time']:.2f}s")
        
        # 创建并发任务
        tasks = []
        for _ in range(concurrency):
            task = asyncio.create_task(worker())
            tasks.append(task)
        
        # 等待所有任务完成
        await asyncio.gather(*tasks)
        
        # 计算统计数据
        successful_results = [r for r in results if r["success"]]
        response_times = [r["response_time"] for r in successful_results]
        
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]
        else:
            avg_response_time = 0
            min_response_time = 0
            max_response_time = 0
            p95_response_time = 0
        
        success_rate = len(successful_results) / len(results) if results else 0
        
        return {
            "api": api,
            "concurrency": concurrency,
            "total_requests": len(results),
            "successful_requests": len(successful_results),
            "success_rate": success_rate,
            "avg_response_time": avg_response_time,
            "min_response_time": min_response_time,
            "max_response_time": max_response_time,
            "p95_response_time": p95_response_time,
            "results": results
        }
    
    async def run_all_tests(self):
        """运行所有测试
        
        Returns:
            测试结果
        """
        # 测试配置
        concurrency_levels = [5, 10, 20]
        
        all_results = {}
        
        # 测试GLM API
        print("测试GLM API...")
        glm_results = []
        for concurrency in concurrency_levels:
            print(f"  并发数: {concurrency}")
            result = await self.run_stress_test(concurrency, "glm")
            glm_results.append(result)
        all_results["glm"] = glm_results
        
        # 测试DeepSeek API
        print("测试DeepSeek API...")
        deepseek_results = []
        for concurrency in concurrency_levels:
            print(f"  并发数: {concurrency}")
            result = await self.run_stress_test(concurrency, "deepseek")
            deepseek_results.append(result)
        all_results["deepseek"] = deepseek_results
        
        return all_results
    
    def print_report(self, results):
        """打印测试报告
        
        Args:
            results: 测试结果
        """
        print("\n=== 压力测试报告 ===")
        
        for api, api_results in results.items():
            print(f"\n{api.upper()} API 测试结果:")
            print("-" * 60)
            print(f"{'并发数':<10} {'总请求数':<10} {'成功数':<10} {'成功率':<10} {'平均响应时间':<15} {'P95响应时间':<15}")
            print("-" * 60)
            
            for result in api_results:
                print(f"{result['concurrency']:<10} {result['total_requests']:<10} {result['successful_requests']:<10} {result['success_rate']:.2f}       {result['avg_response_time']:.2f}s            {result['p95_response_time']:.2f}s")
            
            # 计算总体统计
            total_requests = sum(r['total_requests'] for r in api_results)
            total_successful = sum(r['successful_requests'] for r in api_results)
            overall_success_rate = total_successful / total_requests if total_requests else 0
            
            all_response_times = []
            for r in api_results:
                all_response_times.extend([res['response_time'] for res in r['results'] if res['success']])
            
            if all_response_times:
                overall_avg = statistics.mean(all_response_times)
                overall_p95 = sorted(all_response_times)[int(len(all_response_times) * 0.95)]
            else:
                overall_avg = 0
                overall_p95 = 0
            
            print("-" * 60)
            print(f"{'总计':<10} {total_requests:<10} {total_successful:<10} {overall_success_rate:.2f}       {overall_avg:.2f}s            {overall_p95:.2f}s")

if __name__ == "__main__":
    test = StressTest()
    results = asyncio.run(test.run_all_tests())
    test.print_report(results)