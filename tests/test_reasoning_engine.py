#!/usr/bin/env python3
"""
深度思考引擎测试
"""

import unittest
import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.reasoning_engine import get_reasoning_engine
from core.search_engine import get_self_search_engine

class TestReasoningEngine(unittest.TestCase):
    """深度思考引擎测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.reasoning_engine = get_reasoning_engine()
        self.search_engine = get_self_search_engine()
    
    async def test_simple_question(self):
        """测试简单问题处理"""
        simple_questions = [
            "你好",
            "hi",
            "在吗",
            "你是谁",
            "谢谢",
            "再见"
        ]
        
        for question in simple_questions:
            result = await self.reasoning_engine.process(question)
            self.assertIn("final_answer", result)
            self.assertEqual(result["thinking_process"]["type"], "quick")
    
    async def test_complex_question(self):
        """测试复杂问题处理"""
        complex_questions = [
            "人工智能的发展趋势是什么？",
            "如何提高Python代码的性能？",
            "介绍一下深度学习的基本原理。"
        ]
        
        for question in complex_questions:
            result = await self.reasoning_engine.process(question)
            self.assertIn("final_answer", result)
            self.assertIn("thinking_process", result)
            self.assertIn("understanding", result["thinking_process"])
            self.assertIn("plan", result["thinking_process"])
    
    async def test_realtime_question(self):
        """测试需要实时信息的问题"""
        realtime_questions = [
            "2026年最新的科技新闻是什么？",
            "最近的人工智能发展趋势如何？",
            "今天的天气怎么样？"
        ]
        
        for question in realtime_questions:
            result = await self.reasoning_engine.process(question)
            self.assertIn("final_answer", result)
            understanding = result["thinking_process"].get("understanding", {})
            self.assertTrue(understanding.get("needs_realtime_info", False))
    
    async def test_search_execution(self):
        """测试搜索执行"""
        search_questions = [
            "2026年的世界杯冠军是谁？",
            "最新的iPhone型号是什么？"
        ]
        
        for question in search_questions:
            result = await self.reasoning_engine.process(question)
            self.assertIn("final_answer", result)
            thinking_process = result.get("thinking_process", {})
            info_needed = thinking_process.get("info_needed", {})
            self.assertTrue(info_needed.get("needs_search", False))
    
    async def test_validation_and_reflection(self):
        """测试验证和自我反思"""
        question = "人工智能的未来发展趋势"
        result = await self.reasoning_engine.process(question)
        self.assertIn("final_answer", result)
        thinking_process = result.get("thinking_process", {})
        validation = thinking_process.get("validation", {})
        self.assertIn("validation_passed", validation)
        self.assertIn("confidence", validation)
    
    async def test_information_fusion(self):
        """测试信息融合"""
        question = "人工智能的应用场景"
        result = await self.reasoning_engine.process(question)
        self.assertIn("final_answer", result)
        thinking_process = result.get("thinking_process", {})
        fused_info = thinking_process.get("fused_info", {})
        self.assertIn("fused_content", fused_info)
        self.assertIn("sources", fused_info)
    
    async def test_error_handling(self):
        """测试错误处理"""
        # 测试空消息
        empty_result = await self.reasoning_engine.process("")
        self.assertIn("final_answer", empty_result)
        
        # 测试非常长的消息
        long_message = "a" * 1000
        long_result = await self.reasoning_engine.process(long_message)
        self.assertIn("final_answer", long_result)
    
    async def test_search_engine(self):
        """测试搜索引擎"""
        query = "人工智能"
        results = await self.search_engine.search(query)
        self.assertIsInstance(results, list)
        for result in results:
            self.assertIn("title", result)
            self.assertIn("snippet", result)
            self.assertIn("url", result)
    
    async def test_search_result_processing(self):
        """测试搜索结果处理"""
        query = "Python programming"
        results = await self.search_engine.search(query)
        self.assertIsInstance(results, list)
        # 确保结果已去重
        urls = [result.get("url") for result in results]
        self.assertEqual(len(urls), len(set(urls)))
    
    def test_run_async_tests(self):
        """运行异步测试"""
        asyncio.run(self.test_simple_question())
        asyncio.run(self.test_complex_question())
        asyncio.run(self.test_realtime_question())
        asyncio.run(self.test_search_execution())
        asyncio.run(self.test_validation_and_reflection())
        asyncio.run(self.test_information_fusion())
        asyncio.run(self.test_error_handling())
        asyncio.run(self.test_search_engine())
        asyncio.run(self.test_search_result_processing())

if __name__ == "__main__":
    unittest.main()