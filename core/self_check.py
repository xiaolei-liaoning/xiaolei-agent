"""自我校验 + 循环迭代打分模块

核心功能:
- 对LLM输出进行自动化质量评估
- 低于阈值时自动触发重新生成
- 最多迭代N次,防止死循环
- 适用于所有Agent和Skill的输出校验
- 支持多场景评分标准配置
"""

import asyncio
import logging
import re
from typing import Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass

from .scoring_standards import ScoringScenario, get_scoring_manager

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """评审结果数据类"""
    score: int                  # 得分(0-100)
    issues: list[str]          # 问题列表
    suggestions: list[str]     # 优化建议
    raw_feedback: str          # 原始评审文本
    scenario: str = "general"  # 使用的评分场景
    
    @property
    def is_passed(self, threshold: int = 80) -> bool:
        """判断是否通过阈值"""
        return self.score >= threshold


class SelfCheckEvaluator:
    """自我校验评审器
    
    职责:
    1. 对LLM输出进行多维度评分
    2. 识别具体问题和改进方向
    3. 生成结构化评审报告
    4. 支持多场景评分标准
    """
    
    def __init__(self, 
                 llm_call_fn: Callable[[str], Awaitable[str]],
                 scenario: ScoringScenario = ScoringScenario.GENERAL):
        """初始化评审器
        
        Args:
            llm_call_fn: LLM调用函数,接收prompt返回response字符串
            scenario: 评分场景(默认通用场景)
        """
        self.llm_call_fn = llm_call_fn
        self.scenario = scenario
        self.scoring_manager = get_scoring_manager()
    
    async def evaluate(self, content: str, user_query: str, 
                      threshold: Optional[int] = None) -> EvaluationResult:
        """执行质量评审
        
        Args:
            content: 待评审的内容
            user_query: 用户原始问题
            threshold: 合格分数线(可选,默认使用场景配置)
        
        Returns:
            EvaluationResult: 评审结果
        """
        try:
            # 获取评分标准
            standard = self.scoring_manager.get_standard(self.scenario)
            
            # 使用传入的阈值或场景默认阈值
            effective_threshold = threshold if threshold is not None else standard.pass_threshold
            
            # 构建评审提示词(使用评分标准管理器生成)
            prompt = self.scoring_manager.generate_evaluation_prompt(
                scenario=self.scenario,
                content=content,
                user_query=user_query
            )
            
            # 调用LLM进行评审
            feedback = await self.llm_call_fn(prompt)
            
            # 解析评审结果
            result = self._parse_evaluation(feedback)
            result.scenario = self.scenario.value
            
            logger.info(f"评审完成 [{self.scenario.value}] - 得分: {result.score}, 通过: {result.is_passed}")
            return result
            
        except Exception as e:
            logger.error(f"评审过程异常: {e}", exc_info=True)
            # 降级策略: 返回中等分数,避免阻塞流程
            return EvaluationResult(
                score=70,
                issues=["评审过程出现异常"],
                suggestions=["建议人工复核"],
                raw_feedback=feedback if 'feedback' in locals() else "",
                scenario=self.scenario.value
            )
    
    def _parse_evaluation(self, feedback: str) -> EvaluationResult:
        """解析评审结果
        
        Args:
            feedback: LLM返回的评审文本
        
        Returns:
            EvaluationResult: 结构化的评审结果
        """
        score = 0
        issues = []
        suggestions = []
        
        try:
            lines = feedback.split('\n')
            
            # 提取分数
            for line in lines:
                if '得分' in line or 'score' in line.lower():
                    # 匹配数字(支持"得分：85"或"Score: 85")
                    match = re.search(r'(\d+)', line)
                    if match:
                        score = int(match.group(1))
                        break
            
            # 提取问题列表
            in_issues = False
            in_suggestions = False
            
            for line in lines:
                stripped = line.strip()
                
                # 支持中英文冒号
                if ('问题' in stripped) and (':' in stripped or '：' in stripped):
                    in_issues = True
                    in_suggestions = False
                    continue
                elif ('优化建议' in stripped or '建议' in stripped) and (':' in stripped or '：' in stripped):
                    in_issues = False
                    in_suggestions = True
                    continue
                
                if in_issues and stripped.startswith('-'):
                    issues.append(stripped[1:].strip())
                elif in_suggestions and stripped.startswith('-'):
                    suggestions.append(stripped[1:].strip())
            
            # 容错处理: 如果没解析到任何问题/建议,保留原始反馈
            if not issues and not suggestions:
                issues = ["未检测到具体问题"]
                suggestions = ["建议检查输出质量"]
        
        except Exception as e:
            logger.warning(f"解析评审结果失败: {e}")
            score = 50  # 解析失败给低分
            issues = ["评审结果解析失败"]
            suggestions = ["请重新生成内容"]
        
        return EvaluationResult(
            score=score,
            issues=issues,
            suggestions=suggestions,
            raw_feedback=feedback
        )


class SelfCheckLoop:
    """自我校验循环控制器
    
    核心流程:
    1. 主模型生成初始答案
    2. 评审模型打分并指出问题
    3. 分数达标 → 输出
    4. 分数不达标 → 带着建议重写(最多N次)
    5. 支持多场景评分标准
    """
    
    def __init__(self, 
                 llm_call_fn: Callable[[str], Awaitable[str]],
                 max_retries: int = 3,
                 pass_threshold: Optional[int] = None,
                 scenario: ScoringScenario = ScoringScenario.GENERAL):
        """初始化自检循环
        
        Args:
            llm_call_fn: LLM调用函数
            max_retries: 最大重试次数(防止死循环)
            pass_threshold: 合格分数线(0-100,可选)
            scenario: 评分场景(默认通用场景)
        """
        self.llm_call_fn = llm_call_fn
        self.max_retries = max_retries
        self.pass_threshold = pass_threshold
        self.scenario = scenario
        self.evaluator = SelfCheckEvaluator(llm_call_fn, scenario)
    
    async def generate_with_self_check(self, 
                                      user_query: str,
                                      generation_prompt_template: Optional[str] = None,
                                      threshold: Optional[int] = None) -> Dict[str, Any]:
        """带自检的生成流程
        
        Args:
            user_query: 用户问题
            generation_prompt_template: 可选的生成提示词模板
                                       (默认使用简单模板)
            threshold: 合格分数线(可选,覆盖构造函数设置)
        
        Returns:
            {
                "success": bool,
                "answer": str,           # 最终答案
                "iterations": int,       # 迭代次数
                "final_score": int,      # 最终得分
                "passed": bool,          # 是否通过阈值
                "scenario": str,         # 使用的评分场景
                "history": [...]         # 历史评审记录
            }
        """
        # 默认生成提示词
        if not generation_prompt_template:
            generation_prompt_template = "用户问题：{query}\n\n请认真、准确、完整地回答上述问题。"
        
        # 确定有效阈值
        effective_threshold = threshold if threshold is not None else self.pass_threshold

        current_answer = ""
        iteration_count = 0
        history = []
        
        while iteration_count < self.max_retries:
            iteration_count += 1
            logger.info(f"=== 第 {iteration_count} 轮生成 ===")
            
            try:
                # Step 1: 生成答案
                if iteration_count == 1:
                    # 第一轮: 正常生成
                    prompt = generation_prompt_template.format(query=user_query)
                else:
                    # 后续轮次: 带着评审建议重新生成
                    last_feedback = history[-1]['feedback']
                    prompt = f"""
用户问题：{user_query}

你上一轮回答存在以下问题：
{last_feedback}

请根据上述问题和优化建议，重新修正你的回答，确保：
1. 修正所有指出的错误
2. 补充遗漏的信息
3. 提高逻辑性和准确性
4. 避免重复之前的错误

请给出严谨、准确的回答：
"""
                
                current_answer = await self.llm_call_fn(prompt)
                
                # Step 2: 评审打分
                eval_result = await self.evaluator.evaluate(
                    content=current_answer,
                    user_query=user_query,
                    threshold=effective_threshold
                )
                
                # 记录历史
                history.append({
                    'iteration': iteration_count,
                    'answer_preview': current_answer[:200] + '...',
                    'score': eval_result.score,
                    'issues': eval_result.issues,
                    'suggestions': eval_result.suggestions,
                    'feedback': eval_result.raw_feedback,
                    'scenario': eval_result.scenario
                })
                
                logger.info(f"第{iteration_count}轮得分: {eval_result.score}/100 [{eval_result.scenario}]")
                
                # Step 3: 判断是否达标
                if eval_result.is_passed:
                    logger.info(f"✅ 第{iteration_count}轮通过阈值({effective_threshold})")
                    return {
                        'success': True,
                        'answer': current_answer,
                        'iterations': iteration_count,
                        'final_score': eval_result.score,
                        'passed': True,
                        'scenario': eval_result.scenario,
                        'history': history
                    }
                
                # 未达标,继续下一轮
                logger.warning(f"⚠️ 第{iteration_count}轮未达标({eval_result.score}<{effective_threshold}),准备重试")
                
            except Exception as e:
                logger.error(f"第{iteration_count}轮执行异常: {e}", exc_info=True)
                history.append({
                    'iteration': iteration_count,
                    'error': str(e)
                })
                # 异常时尝试继续,不立即中断
        
        # 达到最大重试次数,返回最后一轮结果
        logger.warning(f"❌ 达到最大重试次数({self.max_retries}),返回最后一轮结果")
        
        return {
            'success': False,
            'answer': current_answer,
            'iterations': iteration_count,
            'final_score': history[-1]['score'] if history else 0,
            'passed': False,
            'scenario': self.scenario.value,
            'history': history,
            'warning': f"已达到最大重试次数({self.max_retries}),结果可能未达质量标准"
        }


# ==================== 便捷函数 ====================

async def self_check_generate(user_query: str,
                              llm_call_fn: Callable[[str], Awaitable[str]],
                              max_retries: int = 3,
                              pass_threshold: Optional[int] = None,
                              generation_prompt: Optional[str] = None,
                              scenario: ScoringScenario = ScoringScenario.GENERAL) -> Dict[str, Any]:
    """便捷的自检生成函数
    
    Args:
        user_query: 用户问题
        llm_call_fn: LLM调用函数
        max_retries: 最大重试次数
        pass_threshold: 合格分数线(可选,默认使用场景配置)
        generation_prompt: 生成提示词模板
        scenario: 评分场景(默认通用场景)
    
    Returns:
        包含答案和评审历史的字典
    """
    loop = SelfCheckLoop(
        llm_call_fn=llm_call_fn,
        max_retries=max_retries,
        pass_threshold=pass_threshold,
        scenario=scenario
    )
    
    return await loop.generate_with_self_check(
        user_query=user_query,
        generation_prompt_template=generation_prompt,
        threshold=pass_threshold
    )
