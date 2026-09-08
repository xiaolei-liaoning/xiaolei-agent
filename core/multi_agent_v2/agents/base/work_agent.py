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

        # 已注入文件路径缓存（项目分析用，拦截重复 read_file）
        self._cached_file_paths: set = set()

        logger.info(f"WorkAgent 初始化完成: {self.agent_id}")

    def reset(self) -> None:
        """重置 Agent 状态，为下次复用做准备"""
        self.work_history = []
        self._model_override = ""
        self._cached_file_paths = set()
        try:
            from core.multi_agent_v2.tools.cache import clear_project_file_cache
            clear_project_file_cache()
        except Exception:
            pass
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

        # 修复(方案A): 用户明确要"子代理"时，把任务描述硬化成强约束指令。
        # 仅靠 role 里的"必须用 task"软指令，LLM 在 ReAct 循环里仍会习惯性 read_file。
        # 把指令直接写进任务描述，LLM 才能把它当硬性要求执行。
        _subagent_signal = ("用子代理", "子代理", "subagent", "spawn子代理", "多agent协作", "多agent编排", "多智能体")
        if any(s in desc for s in _subagent_signal):
            desc += (
                "\n\n【强制要求】本任务必须使用 task 工具派生子代理来执行。"
                "不要用 read_file 直接深入读取每个文件——请先调用 task 工具"
                "（指定 subagent_type，如 explore/analyze）把子任务委托给子代理，"
                "子代理完成后你负责汇总与决策。这是硬性约束，违反会造成任务失败。"
            )

        try:
            # ── SharedBus 工作记忆：搜索其他 Agent 已有成果 ──
            try:
                from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
                _bus = get_shared_bus()
                _found = False
                for _w in re.findall(r'[一-鿟\w]{2,}', desc)[:5]:
                    _results = await _bus.search_knowledge(_w)
                    if _results:
                        _summaries = []
                        for _k, _v in _results.items():
                            _s = _v.get("meta", {}).get("summary", "")
                            if _s and len(_s) > 10:
                                _summaries.append(f"  └─ {_s[:200]}")
                        if _summaries:
                            desc = f"{desc}\n\n📋 其他 Agent 已有成果:\n" + "\n".join(_summaries)
                            task.description = desc
                            _found = True
                            print(f"    \033[1;35m📋 工作记忆: {len(_summaries)} 条已有成果已注入\033[0m")
                            break
                if not _found:
                    print(f"    \033[2;35m📋 工作记忆: 无已有成果\033[0m")
            except Exception:
                pass

            # ── 统一走 ReActCore 中间件链 ──
            _mr = task.context.get("max_rounds", 0)
            max_rounds = max(_mr, 10) if _mr else 10
            logger.info(f"WorkAgent → UnifiedAgent (max_rounds={max_rounds})")
            from core.multi_agent_v2.agents.unified_agent import run_unified

            # ── 三层 Skill 匹配（personality 已由 opts/agentType 指定时跳过） ──
            if not self.personality:
                try:
                    from core.skills.base_skills import get_skill_system
                    skill_result = await get_skill_system().match(desc)
                    if skill_result.personality:
                        overlay = f"【Skill角色】\n{skill_result.personality[:500]}"
                        self.personality = f"{self.personality}\n\n---\n{overlay}" if self.personality else skill_result.personality[:2000]
                        self._skill_tools = list(skill_result.tool_preference)
                        print(f"    \033[1;36m🧠 Skill: {skill_result.skill_name}\033[0m")
                        role_chars = len(skill_result.personality)
                        print(f"    \033[2m📄 角色定义: {role_chars} 字符\033[0m")
                    # ponytail: Expert 人格与工具调用冲突 (Persona 走查专家 → LLM 停止调工具)
                    # skill_agent_map.yaml 中的 Expert 覆盖会跳过
                    if skill_result.guidance:
                        self._skill_guidance = skill_result.guidance
                        print(f"    \033[2m📖 Skill 指导: {len(skill_result.guidance)} 字符\033[0m")

                    # ── skill_agent_map.yaml Expert 覆盖 ──
                    try:
                        import yaml, os
                        _map_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "config", "skill_agent_map.yaml")
                        if os.path.isfile(_map_path):
                            with open(_map_path) as _f:
                                _map_data = yaml.safe_load(_f)
                            _agent_map = _map_data.get("skill_agent_map", {})
                            if skill_result.skill_id in _agent_map:
                                _override_id = _agent_map[skill_result.skill_id]
                                # ponytail: 跳过 Expert 人格（走查专家等角色不适合工具型 agent）
                                if "expert" in _override_id.lower():
                                    logger.info(f"Skill 跳过 Expert 覆盖: {_override_id}")
                                else:
                                    _base = get_skill_system().base_skills.get(_override_id)
                                    if _base and _base.role_prompt:
                                        self.personality = _base.role_prompt
                                        print(f"    \033[1;36m🧠 Skill: {_override_id} (skill_agent_map 覆盖)\033[0m")
                                        print(f"    \033[2m📄 角色定义: {len(_base.role_prompt)} 字符, tools: {len(_base.tools)}\033[0m")
                    except Exception as _e:
                        logger.debug(f"skill_agent_map 覆盖失败: {_e}")
                except Exception as e:
                    logger.warning(f"Skill 匹配异常: {e}")

            # 如果有 Guidance，注入到 personality_prompt
            guidance_text = getattr(self, "_skill_guidance", "")
            pp = self.system_prompt_for_role()
            if guidance_text:
                pp += "\n\n<guidance>\n" + guidance_text[:2000] + "\n</guidance>"

            result = await run_unified(
                desc,
                max_rounds=max_rounds,
                model=task.context.get("model", ""),
                personality_prompt=pp,
                agent=self,
                allowed_tools=task.context.get("allowed_tools"),
                disallowed_tools=task.context.get("disallowed_tools"),
                tool_preference=set(getattr(self, "_skill_tools", [])),
                user_id=str(getattr(self, 'user_id', '')),
                mode="react",
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

            # ── SharedBus 工作记忆：写入分析成果 ──
            _answer = str(output)[:300] if output else ""
            if _answer and len(_answer) > 20 and success:
                try:
                    from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
                    _bus = get_shared_bus()
                    _tags = set(re.findall(r'[一-鿟\w]{2,}', desc)[:5])
                    await _bus.store_knowledge(
                        key=f"analysis:{self.agent_id}",
                        data={"result": output, "task": desc[:200]},
                        tags=_tags,
                        source=self.agent_id,
                        summary=_answer[:200],
                    )
                except Exception:
                    pass

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
