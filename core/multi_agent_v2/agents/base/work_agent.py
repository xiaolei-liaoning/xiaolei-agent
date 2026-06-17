"""
WorkAgent - 统一智能体（精简版）

单一 Agent 类型，统一走 _execute_fast 快路径（ReAct 直通）。

核心保留：
  - personality/role → system_prompt_for_role() → 注入 LLM
  - temp_memory 临时记忆
  - _execute_fast() → run_react() → 4层 MiddlewareChain
  - 任务完成即消失（finally 清理）

已删除：
  - adapt_to_task() / capabilities 系统（不参与实际执行决策）
  - _execute_full 路径（已删除）
  - light_mode 参数
  - SharedBus 总线监听（JS Workflow 独立模式，agent 间不通信）
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent
from .models import ActionResult, AgentType, Task

logger = logging.getLogger(__name__)


class WorkAgent(BaseAgent):
    """统一工作 Agent — 根据任务动态调整行为和能力"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "通用工作 Agent，根据任务动态调整",
        personality: str = "",
        role: str = "",
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.WORKER,
            name=name,
            description=description,
            personality=personality,
            role=role,
        )

        # 模型覆盖（orchestrator 动态设置）
        self._model_override: str = ""

        # 工作记录
        self.work_history: List[Dict[str, Any]] = []

        # Agent标签，用于输出前缀
        self._agent_label: str = name or "Agent"

        logger.info(f"WorkAgent 初始化完成: {self.agent_id}")

    def reset(self) -> None:
        """重置 Agent 状态，为下次复用做准备"""
        self.work_history = []
        self._model_override = ""
        self.reset_temp_memory()
        self.personality = ""
        self.role = ""
        logger.debug(f"WorkAgent {self.agent_id} 状态已重置")

    # ── 执行入口 ───────────────────────────────────────────────────────

    async def execute(self, task: Task) -> ActionResult:
        """执行任务 - 统一执行入口"""
        return await self._execute_fast(task)

    async def _execute_fast(self, task: Task) -> ActionResult:
        """轻量执行 — 直通 ReAct 快路径"""
        logger.info(f"WorkAgent [轻量] 执行任务: {task.task_id} ({task.type})")
        start = time.time()
        desc = task.description

        print(f"\n    \033[1;36m⚡ 开始任务: {desc[:80]}\033[0m")

        try:
            # ── 统一走 ReActCore 中间件链 ──
            _mr = task.context.get("max_rounds", 0)
            max_rounds = max(_mr, 10) if _mr else 10
            logger.info(f"WorkAgent → ReActCore (max_rounds={max_rounds})")
            from core.multi_agent_v2.agents.react_core import run_react

            # ── Layer 1: Base Skill 匹配（新增）──
            try:
                from core.skills.base_skills import get_base_skill_matcher
                skill = await get_base_skill_matcher().match(desc)
                if skill and skill.role_prompt:
                    if self.personality:
                        self.personality = f"{self.personality}\n\n---\n【Skill角色】\n{skill.role_prompt[:500]}"
                    else:
                        self.personality = skill.role_prompt[:2000]
                    logger.info(f"✅ BaseSkill 注入: {skill.name}")
            except Exception as e:
                logger.warning(f"BaseSkill 匹配异常: {e}")

            # ── 双重人设：内置类型（工具权限）+ Skill 角色（领域人格）累加 ──
            try:
                from core.skills.agency_agents.worker_role_matcher import (
                    get_worker_role_matcher,
                )
                matcher = get_worker_role_matcher()
                role = await matcher.match_role_for_task(desc)
                if role:
                    pt = matcher.get_role_prompt(role.get("id", ""))
                    if pt:
                        if self.personality:
                            self.personality = (
                                f"{self.personality}\n\n"
                                f"---\n"
                                f"【当前任务专家身份】\n"
                                f"{pt[:1000]}"
                            )
                        else:
                            self.personality = pt[:2000]
                        logger.info(f"✅ 已注入角色: {role.get('name', '未知')}")
                else:
                    # ponytail: 匹配失败时降级到关键词，不静默跳过
                    logger.warning("角色匹配返回空，尝试关键词降级")
                    fallback = matcher.matcher._keyword_fallback(desc, 1)
                    if fallback:
                        pt = fallback[0].get("description", "")
                        if pt:
                            self.personality = pt[:2000]
                            logger.info(f"✅ 关键词降级匹配: {fallback[0].get('name')}")
            except Exception as e:
                logger.warning(f"角色匹配异常: {e}")

            result = await run_react(
                desc,
                max_rounds=max_rounds,
                model=task.context.get("model", ""),
                personality_prompt=self.system_prompt_for_role(),
                agent=self,
                allowed_tools=task.context.get("allowed_tools"),
                disallowed_tools=task.context.get("disallowed_tools"),
            )

            elapsed = time.time() - start
            success = result.get("success", False)
            output = result.get("answer", "")
            error = result.get("error", "")

            ar = ActionResult(
                success=success,
                output=str(output) if output else None,
                error=error,
                execution_time=elapsed,
                metadata={
                    "light_mode": True,
                    "iterations": result.get("iterations", 0),
                },
            )

            self.work_history.append(
                {
                    "task_id": task.task_id,
                    "task_type": task.type,
                    "success": success,
                    "execution_time": elapsed,
                    "timestamp": time.time(),
                }
            )
            if len(self.work_history) > 100:
                self.work_history = self.work_history[-100:]

            logger.info(f"WorkAgent [轻量] 完成: success={success} {elapsed:.1f}s")
            return ar

        except Exception as e:
            logger.error(f"WorkAgent [轻量] 异常: {e}")
            return ActionResult(
                success=False, error=str(e), execution_time=time.time() - start
            )

    def get_work_stats(self) -> Dict[str, Any]:
        """获取工作统计"""
        if not self.work_history:
            return {"total_tasks": 0}
        total = len(self.work_history)
        successful = sum(1 for r in self.work_history if r.get("success"))
        by_type: Dict[str, int] = {}
        for r in self.work_history:
            t = r.get("task_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total_tasks": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "by_type": by_type,
        }
