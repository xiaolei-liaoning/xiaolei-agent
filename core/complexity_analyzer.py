"""任务复杂度分析器

使用AI快速判断任务是简单还是复杂：
- 简单任务：规则路径（快速匹配）
- 复杂任务：AI路径（智能分解）
"""

import asyncio
import json
import logging
from typing import Tuple, Optional

from .llm_backend import get_llm_router

logger = logging.getLogger(__name__)


class ComplexityAnalyzer:
    """任务复杂度分析器
    
    使用GLM快速判断任务复杂度，决定使用哪个分解路径：
    - 简单任务：单动作、无依赖 → 规则路径
    - 复杂任务：多动作、有依赖、需要智能拆解 → AI路径
    """
    
    def __init__(self):
        self._router = get_llm_router()
        self._model = "glm-4-flash"
        logger.info("ComplexityAnalyzer 初始化完成")
    
    async def analyze(self, task: str) -> Tuple[str, float]:
        """分析任务复杂度
        
        Args:
            task: 用户任务描述
            
        Returns:
            (复杂度类型: "simple" | "complex", 置信度)
        """
        try:
            # 构建判断提示词
            user_task = self._build_prompt(task)
            
            # 调用AI判断
            result = await self._call_ai(user_task)
            
            # 解析结果
            complexity, confidence = self._parse_result(result)
            
            logger.info("任务复杂度分析: %s (置信度: %.2f)", complexity, confidence)
            return complexity, confidence
            
        except Exception as e:
            logger.error("复杂度分析失败: %s", e)
            # 默认返回简单任务
            return "simple", 0.5
    
    def _build_prompt(self, task: str) -> str:
        """构建判断提示词"""
        # 直接返回用户任务，不包含复杂的系统提示
        return f"USER_TASK:{task}"
    
    async def _call_ai(self, task: str) -> str:
        """调用AI判断任务复杂度
        
        Args:
            task: 用户任务
            
        Returns:
            "simple" 或 "complex"
        """
        prompt = f"""请判断以下用户任务是简单任务还是复杂任务。

简单任务特征：
- 单个动作，如打开、查看、查询、翻译、计算、发送等
- 无需多个步骤或依赖关系
- 可以一步完成

复杂任务特征：
- 包含多个动作或步骤（如"先...然后..."、"并"、"接着"等）
- 需要多个子任务协同完成
- 有依赖关系，需要先完成某个任务再进行下一个
- 涉及数据收集、处理、分析等多个环节

用户任务：{task}

请直接返回 "simple" 或 "complex"，不要返回其他内容。"""

        try:
            response = await self._router.simple_chat(
                user_message=prompt,
                system_prompt="你是一个任务分类助手，只需要判断任务是简单还是复杂。",
                temperature=0.3,
            )
            
            logger.debug("AI返回: %s", response)
            return response.strip()
            
        except Exception as e:
            logger.warning("GLM API调用失败: %s，使用规则兜底", e)
            return await self._fallback_rule(task)
    
    def _parse_result(self, result: str) -> Tuple[str, float]:
        """解析AI返回的结果
        
        Args:
            result: AI返回的结果
            
        Returns:
            (复杂度类型, 置信度)
        """
        result = result.strip().lower()
        
        if "complex" in result:
            return "complex", 0.9
        elif "simple" in result:
            return "simple", 0.9
        else:
            return "simple", 0.5
    
    async def _fallback_rule(self, task: str) -> str:
        """规则兜底判断
        
        当AI调用失败时使用规则判断
        
        Args:
            task: 用户任务
            
        Returns:
            "simple" 或 "complex"
        """
        complex_keywords = ["并", "然后", "接着", "再", "最后", "之后", "同时", "先", "并且", "以及", "还有"]
        
        simple_keywords = ["打开", "查看", "天气", "翻译", "计算", "查询", "发送", "关闭", "爬取", "抓取", "分析", "搜索", "获取"]
        
        has_complex = any(kw in task for kw in complex_keywords)
        
        if has_complex:
            logger.debug("规则检测到复杂任务关键词 -> complex")
            return "complex"
        
        has_simple = any(kw in task for kw in simple_keywords)
        
        if has_simple:
            logger.debug("规则检测到简单任务关键词 -> simple")
            return "simple"
        
        logger.debug("规则无法判断，默认简单任务")
        return "simple"


# 全局实例
complexity_analyzer = ComplexityAnalyzer()


async def main():
    """测试函数"""
    analyzer = ComplexityAnalyzer()
    
    test_cases = [
        "查看北京天气",
        "打开微信",
        "翻译这句话",
        "爬取微博热搜并分析数据",
        "先翻译成英文，然后发送邮件",
        "查看CPU使用率和内存",
        "爬取B站热门视频然后生成报告",
    ]
    
    print("="*60)
    print("任务复杂度分析测试")
    print("="*60)
    
    for task in test_cases:
        complexity, confidence = await analyzer.analyze(task)
        print(f"\n任务: {task}")
        print(f"复杂度: {complexity} (置信度: {confidence})")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())