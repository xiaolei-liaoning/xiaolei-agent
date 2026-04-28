import sys
import os
import unittest
import asyncio

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.reasoning_engine import ReasoningEngine
from core.llm_backend import get_llm_router

class TestBoundaryCases(unittest.TestCase):
    """测试边界情况和异常处理"""
    
    def setUp(self):
        """设置测试环境"""
        self.engine = ReasoningEngine()
        self.llm_router = get_llm_router()
    
    async def test_empty_message(self):
        """测试空消息"""
        result = await self.engine.process("")
        self.assertIn("final_answer", result)
        self.assertIsInstance(result["final_answer"], str)
    
    async def test_very_long_message(self):
        """测试非常长的消息"""
        long_message = "你好" * 1000  # 生成一个非常长的消息
        result = await self.engine.process(long_message)
        self.assertIn("final_answer", result)
        self.assertIsInstance(result["final_answer"], str)
    
    async def test_special_characters(self):
        """测试包含特殊字符的消息"""
        special_message = "Hello! @#$%^&*()_+ 你好，世界！"
        result = await self.engine.process(special_message)
        self.assertIn("final_answer", result)
        self.assertIsInstance(result["final_answer"], str)
    
    async def test_numeric_message(self):
        """测试纯数字消息"""
        numeric_message = "1234567890"
        result = await self.engine.process(numeric_message)
        self.assertIn("final_answer", result)
        self.assertIsInstance(result["final_answer"], str)
    
    async def test_repeated_message(self):
        """测试重复消息（缓存测试）"""
        test_message = "测试缓存机制"
        # 第一次调用
        result1 = await self.engine.process(test_message)
        # 第二次调用（应该使用缓存）
        result2 = await self.engine.process(test_message)
        
        self.assertIn("final_answer", result1)
        self.assertIn("final_answer", result2)
        self.assertEqual(result1["final_answer"], result2["final_answer"])
    
    async def test_llm_unavailable(self):
        """测试LLM不可用时的情况"""
        # 暂时禁用LLM路由器
        original_llm_router = self.engine.llm_router
        self.engine.llm_router = None
        
        try:
            result = await self.engine.process("今天天气怎么样？")
            self.assertIn("final_answer", result)
            self.assertIsInstance(result["final_answer"], str)
        finally:
            # 恢复LLM路由器
            self.engine.llm_router = original_llm_router
    
    async def test_search_engine_unavailable(self):
        """测试搜索引擎不可用时的情况"""
        # 暂时禁用搜索引擎
        original_search_engine = self.engine.search_engine
        self.engine.search_engine = None
        
        try:
            result = await self.engine.process("人工智能的未来发展趋势是什么？")
            self.assertIn("final_answer", result)
            self.assertIsInstance(result["final_answer"], str)
        finally:
            # 恢复搜索引擎
            self.engine.search_engine = original_search_engine
    
    async def test_rate_limit(self):
        """测试速率限制"""
        # 连续发送多个请求，测试速率限制
        test_message = "测试速率限制"
        results = []
        
        for i in range(5):
            result = await self.engine.process(test_message)
            results.append(result)
            # 添加小延迟
            await asyncio.sleep(0.5)
        
        for result in results:
            self.assertIn("final_answer", result)
            self.assertIsInstance(result["final_answer"], str)
    
    def run_async_test(self, coro):
        """运行异步测试"""
        return asyncio.run(coro)
    
    def test_empty_message_sync(self):
        """同步测试空消息"""
        self.run_async_test(self.test_empty_message())
    
    def test_very_long_message_sync(self):
        """同步测试非常长的消息"""
        self.run_async_test(self.test_very_long_message())
    
    def test_special_characters_sync(self):
        """同步测试包含特殊字符的消息"""
        self.run_async_test(self.test_special_characters())
    
    def test_numeric_message_sync(self):
        """同步测试纯数字消息"""
        self.run_async_test(self.test_numeric_message())
    
    def test_repeated_message_sync(self):
        """同步测试重复消息"""
        self.run_async_test(self.test_repeated_message())
    
    def test_llm_unavailable_sync(self):
        """同步测试LLM不可用时的情况"""
        self.run_async_test(self.test_llm_unavailable())
    
    def test_search_engine_unavailable_sync(self):
        """同步测试搜索引擎不可用时的情况"""
        self.run_async_test(self.test_search_engine_unavailable())
    
    def test_rate_limit_sync(self):
        """同步测试速率限制"""
        self.run_async_test(self.test_rate_limit())

if __name__ == "__main__":
    unittest.main()