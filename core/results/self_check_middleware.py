"""自我校验与循环迭代评分系统

特性:
- 自我校验 + 循环迭代打分 + 阈值放行机制
- 多维度评分：事实准确性(40)、逻辑通顺(30)、贴合问题(20)、无幻觉(10)
- 自动重试优化，最多3次迭代
- 异步兼容，适配现有FastAPI架构
- 可作为通用中间件集成到所有Agent/Skill
- 完整的可观测性：记录每轮得分、反馈、迭代历史

使用示例:
    from core.self_check_middleware import SelfCheckMiddleware
    
    # 创建中间件实例
    checker = SelfCheckMiddleware(pass_score=80, max_retry=3)
    
    # 对任意LLM调用进行自检
    result = await checker.check_and_optimize(
        user_query="什么是量子计算？",
        generate_func=lambda query: llm_router.simple_chat(query),
        context={"temperature": 0.7}
    )
    
    print(f"最终得分: {result.score}")
    print(f"迭代次数: {result.retry_count}")
    print(f"优化历史: {result.history}")
    print(f"最终答案: {result.answer}")
"""

import asyncio
import logging
import time
import json
from typing import Callable, Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构定义
# ============================================================

@dataclass
class CheckResult:
    """单次评审结果。"""
    
    score: int = 0  # 得分 (0-100)
    problems: str = ""  # 存在的问题
    suggestions: str = ""  # 优化建议
    timestamp: float = 0.0  # 时间戳
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return asdict(self)


@dataclass
class SelfCheckResponse:
    """自我校验最终响应。"""
    
    answer: str = ""  # 最终答案
    score: int = 0  # 最终得分
    retry_count: int = 0  # 重试次数
    is_passed: bool = False  # 是否通过校验
    history: List[Dict[str, Any]] = field(default_factory=list)  # 优化历史
    total_time: float = 0.0  # 总耗时(秒)
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于API返回）。"""
        return {
            "answer": self.answer,
            "score": self.score,
            "retry_count": self.retry_count,
            "is_passed": self.is_passed,
            "history": self.history,
            "total_time": round(self.total_time, 2),
            "metadata": self.metadata,
        }


# ============================================================
# 提示词模板
# ============================================================

SELF_CHECK_PROMPT_TEMPLATE = """
你现在是内容评审官，请严格按照规则对【待评测内容】进行打分。

满分100分，合格线{pass_score}分。

评分维度及权重：
1. 事实准确无错误（40分）
   - 信息是否真实可靠
   - 有无事实性错误
   - 数据是否准确

2. 逻辑完整通顺（30分）
   - 推理过程是否清晰
   - 结构是否合理
   - 表达是否流畅

3. 贴合用户问题（20分）
   - 是否直接回答问题
   - 有无答非所问
   - 是否覆盖问题要点

4. 无幻觉编造（10分）
   - 有无虚构内容
   - 有无过度推断
   - 是否承认知识边界

输出格式严格如下（必须包含这三行）：
得分：xx
问题：列出当前内容存在的所有错误、遗漏、不合理问题（如无问题写"无明显问题"）
优化建议：给出具体可执行的修改方向（如无需优化写"无需优化"）

---
用户原始问题：
{user_query}

待评测内容：
{content}
---

请开始评审：
"""

OPTIMIZATION_PROMPT_TEMPLATE = """
用户问题：{user_query}

你上一轮回答存在问题，评审反馈如下：
{feedback}

请根据上述问题和优化建议，重新修正你的回答。要求：
1. 严格解决指出的所有问题
2. 遵循优化建议进行改进
3. 保持回答的准确性和完整性
4. 避免重复之前的错误

请重新生成严谨、准确的回答：
"""


# ============================================================
# 核心中间件类
# ============================================================

class SelfCheckMiddleware:
    """自我校验与循环迭代评分中间件。
    
    使用方法：
        1. 创建实例：checker = SelfCheckMiddleware(pass_score=80, max_retry=3)
        2. 调用检查：result = await checker.check_and_optimize(...)
        3. 获取结果：result.answer, result.score, result.history
    """
    
    def __init__(
        self,
        pass_score: int = 80,
        max_retry: int = 3,
        enable_logging: bool = True
    ):
        """初始化自我校验中间件。
        
        Args:
            pass_score: 合格分数线 (0-100)，默认80
            max_retry: 最大重试次数，默认3次
            enable_logging: 是否启用详细日志，默认True
        """
        if not 0 <= pass_score <= 100:
            raise ValueError(f"pass_score 必须在 0-100 之间，当前值: {pass_score}")
        if max_retry < 1:
            raise ValueError(f"max_retry 必须 >= 1，当前值: {max_retry}")
        
        self.pass_score = pass_score
        self.max_retry = max_retry
        self.enable_logging = enable_logging
        
        # 统计信息
        self.total_checks = 0
        self.passed_checks = 0
        self.failed_checks = 0
        self.avg_retry_count = 0.0
        
        if self.enable_logging:
            logger.info(
                "SelfCheckMiddleware 初始化: pass_score=%d, max_retry=%d",
                pass_score, max_retry
            )
    
    async def check_and_optimize(
        self,
        user_query: str,
        generate_func: Callable[[str], Any],
        context: Optional[Dict[str, Any]] = None,
        custom_prompt_template: Optional[str] = None
    ) -> SelfCheckResponse:
        """执行自我校验与循环优化。
        
        Args:
            user_query: 用户原始问题
            generate_func: 生成函数，签名为 async func(query: str) -> str
                          应返回LLM的回答文本
            context: 可选上下文信息，会传递给generate_func
            custom_prompt_template: 自定义评审提示词模板（可选）
            
        Returns:
            SelfCheckResponse: 包含最终答案、得分、历史等信息
        """
        start_time = time.time()
        self.total_checks += 1
        
        current_answer = ""
        retry_count = 0
        history = []
        final_score = 0
        is_passed = False
        
        try:
            while retry_count <= self.max_retry:
                # 第1步：生成回答
                if retry_count == 0:
                    # 首次生成
                    if self.enable_logging:
                        logger.info("[SelfCheck] 第%d轮：生成初始回答", retry_count + 1)
                    
                    if asyncio.iscoroutinefunction(generate_func):
                        current_answer = await generate_func(user_query, context)
                    else:
                        current_answer = generate_func(user_query, context)
                else:
                    # 基于反馈重新生成
                    last_feedback = history[-1] if history else ""
                    optimization_prompt = OPTIMIZATION_PROMPT_TEMPLATE.format(
                        user_query=user_query,
                        feedback=last_feedback
                    )
                    
                    if self.enable_logging:
                        logger.info(
                            "[SelfCheck] 第%d轮：基于反馈重新生成",
                            retry_count + 1
                        )
                    
                    if asyncio.iscoroutinefunction(generate_func):
                        current_answer = await generate_func(optimization_prompt, context)
                    else:
                        current_answer = generate_func(optimization_prompt, context)
                
                # 第2步：评审打分
                check_prompt = (custom_prompt_template or SELF_CHECK_PROMPT_TEMPLATE).format(
                    pass_score=self.pass_score,
                    user_query=user_query,
                    content=current_answer
                )
                
                # 调用LLM进行评审（使用同一模型）
                from ...engine.llm_backend import get_llm_router
                llm_router = get_llm_router()
                
                check_response = await llm_router.simple_chat(
                    check_prompt,
                    temperature=0.3  # 评审时使用较低温度，保证稳定性
                )
                
                # 第3步：解析评审结果
                check_result = self._parse_check_result(check_response)
                final_score = check_result.score
                
                # 记录本轮历史
                round_info = {
                    "round": retry_count + 1,
                    "score": check_result.score,
                    "problems": check_result.problems,
                    "suggestions": check_result.suggestions,
                    "timestamp": datetime.now().isoformat(),
                }
                history.append(round_info)
                
                if self.enable_logging:
                    logger.info(
                        "[SelfCheck] 第%d轮评审完成: 得分=%d, 问题=%s",
                        retry_count + 1,
                        check_result.score,
                        check_result.problems[:50] if check_result.problems else "无"
                    )
                
                # 第4步：判断是否达标
                if check_result.score >= self.pass_score:
                    is_passed = True
                    if self.enable_logging:
                        logger.info(
                            "[SelfCheck] ✓ 校验通过！得分=%d >= 合格线=%d",
                            check_result.score, self.pass_score
                        )
                    break
                
                # 第5步：未达标，准备下一轮
                retry_count += 1
                if retry_count > self.max_retry:
                    if self.enable_logging:
                        logger.warning(
                            "[SelfCheck] ✗ 达到最大重试次数(%d)，最终得分=%d",
                            self.max_retry, check_result.score
                        )
                    break
            
            # 计算总耗时
            total_time = time.time() - start_time
            
            # 更新统计信息
            if is_passed:
                self.passed_checks += 1
            else:
                self.failed_checks += 1
            
            # 计算平均重试次数
            total_attempts = self.passed_checks + self.failed_checks
            if total_attempts > 0:
                self.avg_retry_count = sum(
                    h["round"] - 1 for h in history
                ) / total_attempts
            
            # 构建最终响应
            response = SelfCheckResponse(
                answer=current_answer,
                score=final_score,
                retry_count=retry_count,
                is_passed=is_passed,
                history=history,
                total_time=total_time,
                metadata={
                    "pass_score": self.pass_score,
                    "max_retry": self.max_retry,
                    "query_length": len(user_query),
                    "answer_length": len(current_answer),
                }
            )
            
            if self.enable_logging:
                logger.info(
                    "[SelfCheck] 完成: 得分=%d, 重试=%d次, 耗时=%.2f秒, 通过=%s",
                    final_score, retry_count, total_time, is_passed
                )
            
            return response
            
        except Exception as e:
            logger.error("[SelfCheck] 执行失败: %s", str(e), exc_info=True)
            
            # 异常情况下返回降级结果
            total_time = time.time() - start_time
            return SelfCheckResponse(
                answer=current_answer or f"自我校验过程中发生错误: {str(e)}",
                score=0,
                retry_count=retry_count,
                is_passed=False,
                history=history,
                total_time=total_time,
                metadata={"error": str(e)}
            )
    
    def _parse_check_result(self, check_response: str) -> CheckResult:
        """解析评审模型的响应。
        
        Args:
            check_response: 评审模型的原始响应文本
            
        Returns:
            CheckResult: 解析后的评审结果
        """
        result = CheckResult(timestamp=time.time())
        
        try:
            lines = check_response.strip().split('\n')
            
            # 提取得分
            for line in lines:
                if '得分：' in line or '得分:' in line:
                    score_str = line.replace('得分：', '').replace('得分:', '').strip()
                    # 提取数字
                    import re
                    numbers = re.findall(r'\d+', score_str)
                    if numbers:
                        result.score = int(numbers[0])
                        break
            
            # 提取问题
            problems_start = False
            problems_lines = []
            for line in lines:
                if '问题：' in line or '问题:' in line:
                    problems_start = True
                    content = line.replace('问题：', '').replace('问题:', '').strip()
                    if content:
                        problems_lines.append(content)
                    continue
                if problems_start:
                    if '优化建议：' in line or '优化建议:' in line:
                        break
                    problems_lines.append(line.strip())
            
            result.problems = '\n'.join(problems_lines) if problems_lines else "无明显问题"
            
            # 提取优化建议
            suggestions_start = False
            suggestions_lines = []
            for line in lines:
                if '优化建议：' in line or '优化建议:' in line:
                    suggestions_start = True
                    content = line.replace('优化建议：', '').replace('优化建议:', '').strip()
                    if content:
                        suggestions_lines.append(content)
                    continue
                if suggestions_start:
                    suggestions_lines.append(line.strip())
            
            result.suggestions = '\n'.join(suggestions_lines) if suggestions_lines else "无需优化"
            
        except Exception as e:
            logger.warning("[SelfCheck] 解析评审结果失败: %s，使用默认值", str(e))
            result.score = 0
            result.problems = f"解析失败: {str(e)}"
            result.suggestions = "请重新生成回答"
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。
        
        Returns:
            包含总检查数、通过率、平均重试次数等统计信息
        """
        total = self.passed_checks + self.failed_checks
        pass_rate = (self.passed_checks / total * 100) if total > 0 else 0
        
        return {
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "pass_rate": round(pass_rate, 2),
            "avg_retry_count": round(self.avg_retry_count, 2),
            "current_config": {
                "pass_score": self.pass_score,
                "max_retry": self.max_retry,
            }
        }
    
    def reset_stats(self):
        """重置统计信息。"""
        self.total_checks = 0
        self.passed_checks = 0
        self.failed_checks = 0
        self.avg_retry_count = 0.0


# ============================================================
# 便捷工厂函数
# ============================================================

def create_self_check_middleware(
    pass_score: int = 80,
    max_retry: int = 3,
    enable_logging: bool = True
) -> SelfCheckMiddleware:
    """创建自我校验中间件的工厂函数。
    
    Args:
        pass_score: 合格分数线 (0-100)
        max_retry: 最大重试次数
        enable_logging: 是否启用日志
        
    Returns:
        SelfCheckMiddleware 实例
    """
    return SelfCheckMiddleware(
        pass_score=pass_score,
        max_retry=max_retry,
        enable_logging=enable_logging
    )


# ============================================================
# 全局单例（可选）
# ============================================================

_default_middleware: Optional[SelfCheckMiddleware] = None


def get_self_check_middleware() -> SelfCheckMiddleware:
    """获取默认的自检中间件单例。
    
    Returns:
        SelfCheckMiddleware 单例实例
    """
    global _default_middleware
    if _default_middleware is None:
        _default_middleware = SelfCheckMiddleware()
    return _default_middleware
