"""
CognitivePipeline — 认知闭环编排中枢

统一编排 反问 + 反思 + 上下文记忆 + Agent集群 四个模块为一条完整的认知链：

    Context ──→ Clarify ──→ Execute ──→ Reflect ──→ [Agent Cluster] ──→ Context
       ↑                           │                    │                  │
       └───────────────────────────┘──── 反思失败重试 ──┘──────────────────┘

核心设计原则：任何步骤异常都不向上抛出，而是转换成反问问题让用户决策。
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List

from ..services.clarification_service import (
    get_clarification_service, ClarificationService,
    ClarificationQuestion, ClarificationResult,
)
from ..memory.short_term_memory import ShortTermMemoryManager
from ..context import ExecutionContext
from ..workflow.bfs_processor import get_bfs_processor
from ..multi_agent_v2.orchestration.collaboration.strategies import ReflectionTriggerConfig
class ReflectionDecision:
    CONTINUE = "continue"
    FAIL = "fail"
    RETRY = "retry"
    ADD_STEPS = "add_steps"
    REORDER = "reorder"

class ReflectionPrompt:
    pass

class StepResult:
    pass

class AdaptivePipelineWithReflection:
    def __init__(self, executor, trigger_config=None):
        self.executor = executor
    async def execute(self, plan):
        return []

class LLMReflection:
    def reflect(self, context):
        return ReflectionDecision.CONTINUE

logger = logging.getLogger(__name__)


class _LLMReflectionAdapter:
    """桥接 llm_backend.get_llm_router() 到 LLMReflection 期望的接口

    LLMReflection.reflect() 内部调用 llm_facade.generate(dict) → str
    此适配器将实际 LLM Router 的 simple_chat() 包装为该接口。
    """

    def __init__(self, context: Optional['ExecutionContext'] = None):
        self._router = None
        self._ctx = context

    async def _ensure_router(self):
        if self._router is not None:
            return self._router
        # 优先用上下文中的 llm_router
        if self._ctx and self._ctx.llm_router:
            self._router = self._ctx.llm_router
            return self._router
        try:
            from ..engine.llm_backend import get_llm_router
            self._router = get_llm_router()
        except Exception:
            self._router = False  # 标记不可用
        return self._router

    async def generate(self, prompt_dict: dict) -> str:
        router = await self._ensure_router()
        if not router or not hasattr(router, 'simple_chat'):
            raise RuntimeError("LLM不可用")

        prompt_text = prompt_dict.get("prompt", "")
        if not prompt_text:
            raise ValueError("prompt_dict 缺少 'prompt' 字段")

        # 从 prompt_dict 拆出 system 和 user 消息
        parts = prompt_text.split("\n\n", 1)
        system_prompt = parts[0] if len(parts) > 1 else ""
        user_prompt = parts[1] if len(parts) > 1 else prompt_text

        response = await router.simple_chat(
            user_message=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
        )
        return response or ""


class CognitivePipeline:
    """认知闭环编排器

    用法：
        pipe = CognitivePipeline(user_id="default")
        result = await pipe.run("查一下北京天气，再分析一下最近的热搜")

    任何步骤出错都不会抛异常，而是返回 requires_clarification=True 的反问响应。
    """

    def __init__(self, user_id: str = "default", max_rounds: int = 3,
                 context: Optional[ExecutionContext] = None):
        self.user_id = user_id
        self.ctx = context or ExecutionContext.create_default()
        self.clarification: ClarificationService = self.ctx.clarification
        self.short_term_memory = self.ctx.short_term_memory
        self.bfs = self.ctx.bfs_processor

        # 初始化 LLM 反思引擎（尝试接入真实 LLM，失败也保底走启发式）
        try:
            llm_adapter = _LLMReflectionAdapter(context=self.ctx)
            self.reflection_trigger = AdaptivePipelineWithReflection(
                llm_facade=llm_adapter,
                trigger_config=ReflectionTriggerConfig(max_reflections=3),
            )
        except Exception:
            self.reflection_trigger = AdaptivePipelineWithReflection(
                trigger_config=ReflectionTriggerConfig(max_reflections=3),
            )

        # 跨模块共享状态
        self._current_message: str = ""
        self._current_skill: str = ""
        self._round = 0
        self._max_rounds = max_rounds
        self._reflection_history: List[Dict[str, Any]] = []
        self._last_error: Optional[str] = None

    # ═══════════════════════════════════════════════════════════════════
    #  公开 API
    # ═══════════════════════════════════════════════════════════════════

    async def run(
        self,
        message: str,
        skill_name: str = "chat",
        dispatcher=None,
        db_initialized: bool = False,
    ) -> Dict[str, Any]:
        """运行一次认知闭环

        整个 run 方法被 try/except 包裹，任何异常 → 反问用户。
        """
        self._current_message = message
        self._current_skill = skill_name
        self._round = 0
        self._last_error = None

        try:
            return await self._run_pipeline(message, skill_name, dispatcher, db_initialized)
        except Exception as e:
            logger.error(f"认知闭环异常: {e}", exc_info=True)
            return self._error_to_clarification(
                error=str(e),
                context=f"处理 '{message[:50]}...' 时遇到错误",
                skill_name=skill_name,
                original_message=message,
            )

    async def _run_pipeline(
        self,
        message: str,
        skill_name: str,
        dispatcher,
        db_initialized: bool,
    ) -> Dict[str, Any]:
        """闭环主逻辑（被 run 的 try/except 保护）"""
        # ── 第1步：上下文增强 ──
        context = await self._enrich_context(message)

        # ── 第2步：反问检测 ──
        questions = await self._check_clarification(message, context)
        if questions:
            return self._clarification_response(questions, skill_name, message)

        # ── 第3步：执行 + 反思循环 ──
        while self._round < self._max_rounds:
            self._round += 1

            result = await self._safe_execute(message, skill_name, dispatcher, db_initialized)

            # 执行返回反问 → 直接透传
            if result.get("requires_clarification"):
                return result

            # 执行彻底失败 → 反问用户怎么处理
            if not result.get("success"):
                error_msg = result.get("error", result.get("reply", "执行失败"))
                on_fail = await self._on_execution_failure(error_msg, skill_name)
                if on_fail.get("requires_clarification"):
                    return on_fail
                continue  # 用户可能选择了重试

            # ── 第4步：反思评估 ──
            reflection = await self._safe_reflect(result, context)
            if reflection.get("_reflection_failed"):
                # 反思本身失败 → 直接返回执行结果，不中断
                return result

            self._reflection_history.append(reflection)

            # ── 第5步：决策路由 ──
            action = self._decide_action(reflection, result)

            if action == "done":
                await self._store_result(result, context)
                return result
            elif action == "retry":
                logger.info(f"反思决定重试 (第{self._round}轮)")
                continue
            elif action == "clarify":
                return self._build_reflection_clarification(reflection, message, skill_name)
            elif action == "escalate":
                return await self._safe_escalate(message, skill_name)

        # 超过最大轮数 → 反问用户
        return self._error_to_clarification(
            error=f"已尝试 {self._max_rounds} 次仍未完成",
            context=f"处理 '{message[:50]}...'",
            skill_name=skill_name,
            original_message=message,
        )

    # ═══════════════════════════════════════════════════════════════════
    #  步骤 1：上下文增强
    # ═══════════════════════════════════════════════════════════════════

    async def _enrich_context(self, message: str) -> Dict[str, Any]:
        """从短期记忆 + BFS 构建当前上下文（全部 try/except 保护）"""
        context: Dict[str, Any] = {
            "entities": {"cities": [], "files": [], "apps": []},
            "recent_messages": [],
            "reflection_history": self._reflection_history[-5:],
            "bfs_tree": None,
        }

        for attempt in [
            ("短期记忆", lambda: self._load_recent_messages(context)),
            ("实体提取", lambda: self._extract_entities(context, message)),
            ("BFS建树", lambda: self._build_bfs(context, message)),
        ]:
            try:
                attempt[1]()
            except Exception as e:
                logger.debug(f"上下文增强({attempt[0]})跳过: {e}")

        return context

    def _load_recent_messages(self, context: Dict[str, Any]):
        msgs = self.short_term_memory.get_context(self.user_id, depth=2)
        if msgs:
            context["recent_messages"] = [m.get("content", "") for m in msgs[-5:]]

    def _extract_entities(self, context: Dict[str, Any], message: str):
        recent = context["recent_messages"] + [message]
        entities = self.clarification._extract_entities_from_messages(recent)
        context["entities"] = entities

    def _build_bfs(self, context: Dict[str, Any], message: str):
        if _needs_bfs(message):
            bfs_result = self.bfs.process_text(message)
            context["bfs_tree"] = bfs_result

    # ═══════════════════════════════════════════════════════════════════
    #  步骤 2：反问检测
    # ═══════════════════════════════════════════════════════════════════

    async def _check_clarification(
        self, message: str, context: Dict[str, Any],
    ) -> List[ClarificationQuestion]:
        """执行反问检测（带LLM后备）"""
        if self._current_skill == "chat":
            return []

        try:
            # 先用关键词匹配
            questions = self.clarification.generate_questions(message)
            if questions:
                for q in questions:
                    self.clarification._enhance_question_with_context(q, context)
                return questions

            # 关键词没匹配到 → 用LLM判断
            questions = await self.clarification.async_detect_clarification(message)
            if questions and context.get("entities"):
                for q in questions:
                    self.clarification._enhance_question_with_context(q, context)
            return questions
        except Exception as e:
            logger.debug(f"反问检测跳过: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════════
    #  步骤 3：安全执行
    # ═══════════════════════════════════════════════════════════════════

    async def _safe_execute(
        self, message: str, skill_name: str, dispatcher, db_initialized: bool,
    ) -> Dict[str, Any]:
        """执行技能，异常不抛 → 返回 error 信息给反思引擎处理"""
        try:
            return await self._execute(message, skill_name, dispatcher, db_initialized)
        except Exception as e:
            logger.error(f"执行异常: {skill_name}: {e}")
            self._last_error = str(e)
            return {
                "success": False,
                "error": str(e),
                "reply": f"执行 {skill_name} 时遇到错误: {str(e)[:200]}",
            }

    async def _execute(
        self, message: str, skill_name: str, dispatcher, db_initialized: bool,
    ) -> Dict[str, Any]:
        """实际执行逻辑"""
        from .single_step_handler_utils import execute_tool
        from .multi_step_handler import handle_multi_step

        if skill_name == "multi_step":
            planner = self._get_planner()
            processor = self._get_processor()
            return await handle_multi_step(
                message, int(self.user_id),
                planner, processor, dispatcher, db_initialized,
            )

        result = await execute_tool(
            message, skill_name, int(self.user_id),
            dispatcher, db_initialized,
        )

        # ── 工具执行失败 → 代码沙盒降级 ──
        if not result.get("success") and skill_name not in ("chat", "mcp_suggestion"):
            try:
                from .code_fallback import try_code_generation
                code_result = await try_code_generation(
                    message=message,
                    skill_name=skill_name,
                    params=result.get("tool_call", {}).get("params", {}),
                    context=self.ctx,
                )
                if code_result.get("success"):
                    logger.info(f"✅ 代码降级成功: {skill_name}")
                    return code_result
            except Exception as e:
                logger.debug(f"代码降级跳过: {e}")

        # 自检优化：对非错误的结果做迭代评分优化
        if result.get("success") and result.get("reply"):
            try:
                from core.results.self_check_middleware import create_self_check_middleware
                checker = create_self_check_middleware()
                checked = await checker.check(
                    query=message,
                    response=result["reply"],
                )
                if checked and checked.get("optimized_response"):
                    result["reply"] = checked["optimized_response"]
                    result["self_checked"] = True
            except Exception:
                pass  # 自检失败不影响主流程

        return result

    def _get_planner(self):
        try:
            from ..tasks.task_planner import TaskPlanner
            return TaskPlanner()
        except Exception:
            return None

    def _get_processor(self):
        try:
            from ..tasks.task_processor import TaskProcessor
            return TaskProcessor()
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════════════
    #  步骤 4：安全反思
    # ═══════════════════════════════════════════════════════════════════

    async def _safe_reflect(
        self, result: Dict[str, Any], context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """反思评估，异常不抛 → 返回 fallback 反思结果"""
        try:
            return await self._reflect(result, context)
        except Exception as e:
            logger.warning(f"反思引擎异常，使用默认通过: {e}")
            return {
                "decision": "continue",
                "confidence": 0.5,
                "reasoning": f"反思失败: {e}，默认继续",
                "success": result.get("success", False),
                "_reflection_failed": True,
            }

    async def _reflect(
        self, result: Dict[str, Any], context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """反思评估核心"""
        success = result.get("success", False)
        error = result.get("error", "")
        execution_time = result.get("execution_time", 0.0)

        step = RStep(
            step_id=f"step_{self._round}",
            step_name=self._current_skill,
            step_type="execution",
            success=success,
            output=result.get("reply", result.get("result")),
            error=error,
            execution_time=execution_time if isinstance(execution_time, (int, float)) else 0.0,
        )

        prompt = ReflectionPrompt(
            completed_steps=[step],
            remaining_steps=[],
            original_goal=self._current_message,
            task_context=context,
        )

        ref = self.reflection_trigger.reflection_engine
        ref_result = await ref.reflect(prompt)

        return {
            "decision": ref_result.decision.value,
            "confidence": ref_result.confidence,
            "reasoning": ref_result.reasoning,
            "success": success,
            "error": error,
        }

    # ═══════════════════════════════════════════════════════════════════
    #  步骤 5：决策路由
    # ═══════════════════════════════════════════════════════════════════

    def _decide_action(self, reflection: Dict[str, Any], result: Dict[str, Any]) -> str:
        """根据反思结果决定下一步动作"""
        if reflection.get("success") and reflection.get("decision") in (
            ReflectionDecision.CONTINUE.value, "continue"
        ):
            return "done"

        decision = reflection.get("decision", "")

        if decision == ReflectionDecision.FAIL.value:
            return "clarify"
        elif decision == ReflectionDecision.RETRY.value:
            return "retry" if self._round < 2 else "clarify"
        elif decision in (ReflectionDecision.ADD_STEPS.value, ReflectionDecision.REORDER.value):
            return "escalate"

        return "done"

    # ═══════════════════════════════════════════════════════════════════
    #  执行失败 → 反问
    # ═══════════════════════════════════════════════════════════════════

    async def _on_execution_failure(
        self, error_msg: str, skill_name: str,
    ) -> Dict[str, Any]:
        """工具执行失败时，生成反问让用户决定怎么处理"""
        logger.info(f"执行失败，生成反问: {error_msg[:100]}")

        # 使用 ClarificationService 的错误反问
        try:
            context_info = {"entities": {}, "recent_messages": []}
            question = await self.clarification.handle_execution_failure(
                error_context=error_msg,
                original_message=self._current_message,
            )
            if question:
                return self._clarification_response(
                    [question], skill_name, self._current_message,
                )
        except Exception:
            pass

        # 兜底：硬编码反问
        q = ClarificationQuestion(
            question=f"执行 {skill_name} 时遇到问题：{error_msg[:100]}，请问您希望如何处理？",
            header="执行错误",
            options=[
                self._opt("重试", "再试一次"),
                self._opt("跳过", "跳过此步骤继续"),
                self._opt("换方法", "尝试另一种方式"),
                self._opt("放弃", "取消当前操作"),
            ],
        )
        return self._clarification_response([q], skill_name, self._current_message)

    # ═══════════════════════════════════════════════════════════════════
    #  升级 Agent 集群（带异常保护）
    # ═══════════════════════════════════════════════════════════════════

    async def _safe_escalate(self, message: str, skill_name: str) -> Dict[str, Any]:
        """升级到多Agent集群，异常不抛 → 反问"""
        try:
            return await self._escalate_to_agent_cluster(message, skill_name)
        except Exception as e:
            logger.error(f"Agent集群升级失败: {e}")
            return self._error_to_clarification(
                error=f"多Agent调度失败: {e}",
                context=f"尝试用多Agent处理 '{message[:50]}...'",
                skill_name=skill_name,
                original_message=message,
            )

    async def _escalate_to_agent_cluster(self, message: str, skill_name: str) -> Dict[str, Any]:
        """将复杂/反思需要的任务升级到多Agent集群"""
        from .single_step_handler_utils import _route_to_multi_agent

        logger.info(f"升级到 Agent 集群: skill={skill_name}")
        context = await self._enrich_context(message)
        result = await _route_to_multi_agent(message, int(self.user_id), skill_name)

        if result.get("success"):
            await self._store_result(result, context)

        return result

    # ═══════════════════════════════════════════════════════════════════
    #  通用异常 → 反问
    # ═══════════════════════════════════════════════════════════════════

    def _error_to_clarification(
        self,
        error: str,
        context: str,
        skill_name: str,
        original_message: str,
    ) -> Dict[str, Any]:
        """任何未预料的异常都转换为反问，绝不抛出"""
        logger.warning(f"异常降级反问: {error[:100]}")

        q = ClarificationQuestion(
            question=f"{context}，遇到问题：{error[:150]}，请问您希望怎么处理？",
            header="系统提示",
            options=[
                self._opt("重试", "再试一次"),
                self._opt("简化", "换个更简单的方式"),
                self._opt("放弃", "取消当前操作"),
            ],
        )
        return {
            "success": True,
            "requires_clarification": True,
            "clarification_questions": [q.to_dict()],
            "original_skill": skill_name,
            "message": original_message,
            "reply": q.question,
            "_error": error,
        }

    def _build_reflection_clarification(
        self, reflection: Dict[str, Any], message: str, skill_name: str,
    ) -> Dict[str, Any]:
        """从反思结果构建反问响应"""
        reasoning = reflection.get("reasoning", "遇到问题")
        q = ClarificationQuestion(
            question=f"{reasoning[:200]}，请问您希望如何处理？",
            header="反思建议",
            options=[
                self._opt("重试", "让系统重试"),
                self._opt("跳过", "跳过此步骤继续"),
                self._opt("修改方案", "尝试其他策略"),
                self._opt("放弃", "取消当前操作"),
            ],
        )
        return {
            "success": True,
            "requires_clarification": True,
            "clarification_questions": [q.to_dict()],
            "original_skill": skill_name,
            "message": message,
            "reply": q.question,
        }

    # ═══════════════════════════════════════════════════════════════════
    #  工具方法
    # ═══════════════════════════════════════════════════════════════════

    async def _store_result(self, result: Dict[str, Any], context: Dict[str, Any]):
        """将本轮结果存回短期记忆 + 持续学习（异常不抛）"""
        try:
            self.short_term_memory.add_context(
                user_id=self.user_id,
                content=str(result.get("reply", result.get("result", ""))),
                context_type=f"assistant_{self._current_skill}",
            )
        except Exception as e:
            logger.debug(f"存储结果到上下文失败: {e}")

        # 持续学习：记录每次执行经验
        try:
            from core.learning.continuous_learning import ContinuousLearner
            continuous_learner = ContinuousLearner()
            await continuous_learner.learn_from_execution(
                task=context.get("message", ""),
                action=self._current_skill or "unknown",
                result=str(result.get("reply", result.get("result", ""))),
                success=result.get("success", False),
            )
        except Exception:
            pass  # 学习失败不影响主流程

    def _clarification_response(
        self, questions: List[ClarificationQuestion], skill_name: str, message: str,
    ) -> Dict[str, Any]:
        """构建反问响应"""
        return {
            "success": True,
            "requires_clarification": True,
            "clarification_questions": [q.to_dict() for q in questions],
            "original_skill": skill_name,
            "message": message,
            "reply": questions[0].question if questions else "",
        }

    def _opt(self, label: str, desc: str):
        from ..services.clarification_service import QuestionOption
        return QuestionOption(label, desc)


def _needs_bfs(message: str) -> bool:
    """判断是否需要对消息做BFS结构化建树"""
    msg = message.lower()
    chat_patterns = ["你好", "hi", "hello", "谢谢", "再见", "拜拜", "?"]
    if any(p in msg for p in chat_patterns) and len(msg) < 20:
        return False
    return (
        len(msg) > 50
        or any(kw in msg for kw in ["分析", "总结", "比较", "报告", "详细"])
    )