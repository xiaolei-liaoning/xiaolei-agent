"""
LLM反思机制 - 模型自我评估与迭代优化

在Pipeline关键节点嵌入LLM反思，实现：
1. 执行结果评估
2. 计划调整决策
3. 动态优化执行流程
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)


class ReflectionDecision(Enum):
    """反思决策类型"""
    CONTINUE = "continue"              # 继续原计划
    SKIP_NEXT = "skip_next"           # 跳过下一步
    ADD_STEPS = "add_steps"           # 添加新步骤
    REORDER = "reorder"               # 调整顺序
    RETRY = "retry"                   # 重试上一步
    FAIL = "fail"                     # 宣告失败


@dataclass
class StepResult:
    """步骤执行结果"""
    step_id: str
    step_name: str
    step_type: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReflectionPrompt:
    """反思Prompt模板"""
    completed_steps: List[StepResult]
    remaining_steps: List[Dict[str, Any]]
    original_goal: str
    task_context: Dict[str, Any]


@dataclass
class ReflectionResult:
    """反思结果"""
    decision: ReflectionDecision
    confidence: float
    reasoning: str
    adjustments: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    new_plan: Optional[List[Dict[str, Any]]] = None


@dataclass
class ReflectionTriggerConfig:
    """反思触发配置"""
    check_on_failure: bool = True
    check_on_timeout: bool = True
    check_interval: int = 3
    confidence_threshold: float = 0.6
    step_timeout_multiplier: float = 2.0
    max_retries: int = 3
    max_reflections: int = 5
    max_plan_adjustments: int = 3


class ReflectionTrigger:
    """反思触发器 - 决定何时进行反思"""

    def __init__(self, config: Optional[ReflectionTriggerConfig] = None):
        self.config = config or ReflectionTriggerConfig()
        self.step_count = 0

    def should_reflect(self, result: StepResult, expected_time: float) -> bool:
        """判断是否应该进行反思"""
        if self.config.check_on_failure and not result.success:
            logger.info(f"反思触发: 步骤 {result.step_id} 执行失败")
            return True

        if self.config.check_on_timeout:
            if result.execution_time > expected_time * self.config.step_timeout_multiplier:
                logger.info(f"反思触发: 步骤 {result.step_id} 执行超时")
                return True

        if result.confidence < self.config.confidence_threshold:
            logger.info(f"反思触发: 步骤 {result.step_id} 置信度过低 ({result.confidence})")
            return True

        self.step_count += 1
        if self.step_count % self.config.check_interval == 0:
            logger.info(f"反思触发: 周期性检查 (第{self.step_count}步)")
            return True

        return False

    def reset(self) -> None:
        """重置触发器"""
        self.step_count = 0


class LLMReflection:
    """LLM反思引擎 - 使用LLM进行反思"""

    def __init__(self, llm_facade: Optional[Any] = None):
        self.llm_facade = llm_facade
        self.reflection_count = 0

    async def reflect(
        self,
        prompt: ReflectionPrompt,
        previous_decision: Optional[ReflectionDecision] = None
    ) -> ReflectionResult:
        """执行反思"""
        self.reflection_count += 1

        logger.info(f"开始第{self.reflection_count}次反思")

        if self.llm_facade:
            return await self._llm_reflect(prompt, previous_decision)
        else:
            return self._heuristic_reflect(prompt, previous_decision)

    async def _llm_reflect(
        self,
        prompt: ReflectionPrompt,
        previous_decision: Optional[ReflectionDecision]
    ) -> ReflectionResult:
        """使用LLM进行反思"""
        reflection_prompt = self._build_reflection_prompt(prompt, previous_decision)

        try:
            response = await self.llm_facade.generate(reflection_prompt)
            return self._parse_llm_response(response, prompt)

        except Exception as e:
            logger.error(f"LLM反思失败: {e}，回退到启发式反思")
            return self._heuristic_reflect(prompt, previous_decision)

    def _build_reflection_prompt(
        self,
        prompt: ReflectionPrompt,
        previous_decision: Optional[ReflectionDecision]
    ) -> Dict[str, Any]:
        """构建反思Prompt"""
        completed_str = "\n".join([
            f"- 步骤{i+1} [{s.step_name}]: {'成功' if s.success else '失败'} "
            f"(置信度: {s.confidence}, 耗时: {s.execution_time:.2f}s)"
            f"{f', 输出: {s.output}' if s.output else ''}"
            f"{f', 错误: {s.error}' if s.error else ''}"
            for i, s in enumerate(prompt.completed_steps)
        ])

        remaining_str = "\n".join([
            f"- 步骤{i+1} [{s['name']}]: {s['description']}"
            for i, s in enumerate(prompt.remaining_steps)
        ])

        system_prompt = """你是一个专业的任务评审专家。你的职责是评估当前任务的执行情况，并决定是否需要调整后续计划。

评估标准：
1. 执行效率：是否在合理时间内完成
2. 输出质量：结果是否符合预期
3. 目标对齐：是否符合原始目标
4. 风险识别：是否存在潜在问题

决策选项：
- CONTINUE: 当前进展良好，继续执行原计划
- SKIP_NEXT: 跳过某些不必要的步骤
- ADD_STEPS: 需要添加额外的步骤
- RETRY: 需要重试上一步骤
- FAIL: 任务无法完成，宣告失败

请给出详细的推理过程和具体的调整建议。"""

        user_prompt = f"""## 原始目标
{prompt.original_goal}

## 已完成步骤
{completed_str or '（暂无）'}

## 剩余计划
{remaining_str or '（无剩余步骤）'}

## 任务上下文
{self._format_context(prompt.task_context)}

{f'## 上次决策: {previous_decision.value}' if previous_decision else ''}

请评估当前执行情况，并给出你的决策和建议。"""

        return {
            "prompt": system_prompt + "\n\n" + user_prompt,
            "metadata": {
                "task_type": "reflection",
                "requirements": ["reflection", "decision"]
            }
        }

    def _parse_llm_response(self, response: str, prompt: ReflectionPrompt) -> ReflectionResult:
        """解析LLM响应"""
        response_lower = response.lower()

        if "fail" in response_lower and ("无法" in response or "不可能" in response):
            decision = ReflectionDecision.FAIL
            confidence = 0.9
        elif "retry" in response_lower or "重试" in response:
            decision = ReflectionDecision.RETRY
            confidence = 0.7
        elif "skip" in response_lower or "跳过" in response:
            decision = ReflectionDecision.SKIP_NEXT
            confidence = 0.6
        elif "add" in response_lower or "添加" in response:
            decision = ReflectionDecision.ADD_STEPS
            confidence = 0.6
        else:
            decision = ReflectionDecision.CONTINUE
            confidence = 0.8

        return ReflectionResult(
            decision=decision,
            confidence=confidence,
            reasoning=response[:500],
            suggestions=[response]
        )

    def _heuristic_reflect(
        self,
        prompt: ReflectionPrompt,
        previous_decision: Optional[ReflectionDecision]
    ) -> ReflectionResult:
        """启发式反思（无LLM时使用）"""
        if not prompt.completed_steps:
            return ReflectionResult(
                decision=ReflectionDecision.CONTINUE,
                confidence=1.0,
                reasoning="暂无执行结果，继续执行"
            )

        failures = [s for s in prompt.completed_steps if not s.success]

        if len(failures) >= 3:
            return ReflectionResult(
                decision=ReflectionDecision.FAIL,
                confidence=0.9,
                reasoning=f"已连续失败{len(failures)}次，继续下去可能无法完成任务"
            )

        avg_confidence = sum(s.confidence for s in prompt.completed_steps) / len(prompt.completed_steps)

        if avg_confidence < 0.5:
            return ReflectionResult(
                decision=ReflectionDecision.RETRY,
                confidence=0.8,
                reasoning=f"平均置信度过低 ({avg_confidence:.2f})，建议重试"
            )

        timeouts = [
            s for s in prompt.completed_steps
            if s.execution_time > 30.0
        ]

        if len(timeouts) >= 2:
            return ReflectionResult(
                decision=ReflectionDecision.CONTINUE,
                confidence=0.7,
                reasoning=f"存在{len(timeouts)}次超时，但仍有进展，继续执行"
            )

        return ReflectionResult(
            decision=ReflectionDecision.CONTINUE,
            confidence=0.8,
            reasoning="执行情况正常，继续原计划"
        )

    def _format_context(self, context: Dict[str, Any]) -> str:
        """格式化上下文"""
        if not context:
            return "无额外上下文"

        return "\n".join([f"- {k}: {v}" for k, v in context.items()])


class AdaptivePipelineWithReflection:
    """带反思机制的自适应Pipeline"""

    def __init__(
        self,
        llm_facade: Optional[Any] = None,
        trigger_config: Optional[ReflectionTriggerConfig] = None
    ):
        self.trigger = ReflectionTrigger(trigger_config)
        self.reflection_engine = LLMReflection(llm_facade)
        self.config = trigger_config or ReflectionTriggerConfig()

        self.total_steps = 0
        self.total_reflections = 0
        self.plan_adjustments = 0

    async def execute_with_reflection(
        self,
        task: Any,
        execution_plan: List[Dict[str, Any]],
        executor: Callable,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """带反思的执行"""
        self.trigger.reset()
        completed_steps: List[StepResult] = []
        current_plan = execution_plan.copy()
        final_result = None

        logger.info(f"开始带反思的Pipeline执行，初始计划: {len(current_plan)} 步")

        while current_plan and self.total_steps < 50:
            if self.total_reflections >= self.config.max_reflections:
                logger.warning(f"已达到最大反思次数 ({self.config.max_reflections})，强制结束")
                break

            current_step = current_plan.pop(0)
            self.total_steps += 1

            expected_time = current_step.get("estimated_time", 10.0)
            result = await executor(current_step, task)

            step_result = StepResult(
                step_id=current_step.get("id", f"step_{self.total_steps}"),
                step_name=current_step.get("name", current_step.get("description", "unknown")),
                step_type=current_step.get("type", "general"),
                success=result.get("success", True),
                output=result.get("output"),
                error=result.get("error"),
                execution_time=result.get("execution_time", 0.0),
                confidence=result.get("confidence", 1.0)
            )

            completed_steps.append(step_result)

            logger.info(
                f"步骤 {self.total_steps} 完成: {step_result.step_name} - "
                f"{'成功' if step_result.success else '失败'} "
                f"(置信度: {step_result.confidence:.2f}, 耗时: {step_result.execution_time:.2f}s)"
            )

            if result.get("done"):
                final_result = result
                logger.info("任务完成")
                break

            if self.trigger.should_reflect(step_result, expected_time):
                self.total_reflections += 1

                prompt = ReflectionPrompt(
                    completed_steps=completed_steps,
                    remaining_steps=current_plan,
                    original_goal=task.get("goal", task.get("description", "")),
                    task_context=context or {}
                )

                reflection_result = await self.reflection_engine.reflect(prompt, None)

                logger.info(
                    f"反思结果: {reflection_result.decision.value} "
                    f"(置信度: {reflection_result.confidence:.2f})"
                )

                current_plan = self._apply_reflection(reflection_result, current_plan, completed_steps)

                if reflection_result.decision == ReflectionDecision.FAIL:
                    logger.error("反思决定：任务失败")
                    return {
                        "success": False,
                        "completed_steps": completed_steps,
                        "reason": reflection_result.reasoning,
                        "total_steps": self.total_steps,
                        "total_reflections": self.total_reflections
                    }

        return {
            "success": final_result is not None,
            "completed_steps": completed_steps,
            "total_steps": self.total_steps,
            "total_reflections": self.total_reflections,
            "final_result": final_result
        }

    def _apply_reflection(
        self,
        reflection: ReflectionResult,
        current_plan: List[Dict[str, Any]],
        completed_steps: List[StepResult]
    ) -> List[Dict[str, Any]]:
        """应用反思决策"""
        new_plan = current_plan.copy()

        if reflection.decision == ReflectionDecision.SKIP_NEXT and new_plan:
            skipped = new_plan.pop(0)
            self.plan_adjustments += 1
            logger.info(f"跳过步骤: {skipped.get('name', skipped.get('description', 'unknown'))}")

        elif reflection.decision == ReflectionDecision.RETRY:
            if completed_steps:
                last_step = completed_steps[-1]
                retry_step = {
                    "id": f"{last_step.step_id}_retry",
                    "name": f"重试: {last_step.step_name}",
                    "type": last_step.step_type,
                    "retry": True
                }
                new_plan.insert(0, retry_step)
                self.plan_adjustments += 1
                logger.info(f"添加重试步骤: {last_step.step_name}")

        elif reflection.decision == ReflectionDecision.ADD_STEPS and reflection.suggestions:
            for suggestion in reflection.suggestions[:2]:
                new_step = {
                    "id": f"added_{uuid.uuid4().hex[:8]}",
                    "name": suggestion,
                    "type": "added",
                    "description": suggestion
                }
                new_plan.append(new_step)
                self.plan_adjustments += 1
                logger.info(f"添加新步骤: {suggestion}")

        elif reflection.decision == ReflectionDecision.REORDER and reflection.new_plan:
            new_plan = reflection.new_plan
            self.plan_adjustments += 1
            logger.info("应用新的执行计划")

        return new_plan

    def get_statistics(self) -> Dict[str, Any]:
        """获取执行统计"""
        return {
            "total_steps": self.total_steps,
            "total_reflections": self.total_reflections,
            "plan_adjustments": self.plan_adjustments,
            "reflection_rate": self.total_reflections / max(self.total_steps, 1)
        }
