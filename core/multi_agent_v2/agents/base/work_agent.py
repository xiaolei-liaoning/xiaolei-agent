"""
WorkAgent - 统一智能体

单一 Agent 类型，根据任务需求动态调整行为和能力。
取代了原先分散的 WorkerAgent / MasterAgent / ReviewerAgent / ExpertAgent / CoordinatorAgent / MonitorAgent。

核心设计：
- 不预设角色：同一个 WorkAgent 实例可以根据不同任务动态调整
- 能力即配置：capabilities 由任务匹配动态生成，而非硬编码
- LLM 驱动的执行：所有任务通过 think → act → reflect 循环
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent
from .models import AgentType, Capability, Task, ActionResult, Thought, StepStatus

logger = logging.getLogger(__name__)


class WorkAgent(BaseAgent):
    """统一工作 Agent - 根据任务动态调整行为和能力

    替代 WorkerAgent / MasterAgent / ReviewerAgent / ExpertAgent / CoordinatorAgent / MonitorAgent。
    不再预设 specialization，而是根据任务类型动态适配。
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "通用工作 Agent，根据任务动态调整",
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.WORKER,
            name=name,
            description=description,
        )

        # 能力列表 - 非硬编码，根据任务动态生成
        self.capabilities: List[Capability] = self._default_capabilities()

        # 工作记录
        self.work_history: List[Dict[str, Any]] = []

        # 执行进度（供 Mind 注入）
        self._progress = None

        logger.info(f"WorkAgent 初始化完成: {self.agent_id}")

    def _default_capabilities(self) -> List[Capability]:
        """提供一组通用的默认能力，具体匹配由 scheduler 动态完成"""
        return [
            Capability(
                name="general_task",
                description="通用任务执行能力，适配各种类型的任务",
                keywords=["执行", "处理", "完成", "分析", "生成", "搜索"],
                expertise_level=0.7,
            ),
        ]

    def adapt_to_task(self, task: Task) -> None:
        """根据任务动态调整 Agent 的能力配置

        每个 Agent 拥有完整能力（不做裁剪），根据任务类型追加专项能力。
        """
        task_type = task.type or "general"
        task_keywords = task.keywords or []

        # 追加全部能力类型（不做关键词过滤），每个 Agent 天然具备所有能力
        extra_capabilities = [
            Capability(
                name=f"analysis_{task_type}",
                description=f"分析能力: {task.description[:50]}",
                keywords=task_keywords + ["分析", "评估"],
                expertise_level=0.8,
            ),
            Capability(
                name=f"execution_{task_type}",
                description=f"执行能力: {task.description[:50]}",
                keywords=task_keywords + ["执行", "处理"],
                expertise_level=0.8,
            ),
            Capability(
                name=f"review_{task_type}",
                description=f"评审能力: {task.description[:50]}",
                keywords=task_keywords + ["评审", "质量"],
                expertise_level=0.85,
            ),
            Capability(
                name=f"research_{task_type}",
                description=f"研究能力: {task.description[:50]}",
                keywords=task_keywords + ["研究", "检索"],
                expertise_level=0.75,
            ),
            Capability(
                name=f"integration_{task_type}",
                description=f"整合能力: {task.description[:50]}",
                keywords=task_keywords + ["整合", "汇总"],
                expertise_level=0.8,
            ),
        ]

        self.capabilities = self._default_capabilities() + extra_capabilities
        logger.info(
            f"WorkAgent {self.agent_id} 已适配任务: {task_type} "
            f"(完整能力: 基础+分析/执行/评审/研究/整合)"
        )

    async def execute(self, task: Task) -> ActionResult:
        """执行任务 - 统一的执行入口

        workflow:
        1. 适配任务 → 调整能力配置
        2. 拆解 → StepPlanner 生成结构化步骤（注入工具+历史）
        3. 执行 → StepExecutor 逐步执行（含进度追踪+失败计数）
        4. 反思重规划 → 失败2次后触发局部重规划
        """
        logger.info(f"WorkAgent 开始执行任务: {task.task_id} ({task.type})")

        # 1. 动态适配
        self.adapt_to_task(task)

        # 2. 拆解计划
        # 先在 try 外初始化 llm/registry，避免 except 后 llm 未定义
        llm = registry = None
        try:
            from core.engine.llm_backend import get_llm_router
            llm = get_llm_router()
        except Exception:
            pass

        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
            registry = get_tool_registry()
            if not registry._initialized:
                await registry.discover_all()  # 不阻塞，MCP连接在后台
        except Exception:
            pass

        # ── 工具需求判断：先问 LLM 是否需要工具 ──────────────────────────
        # 纯聊天/知识查询则直通回答，避免不必要的 StepPlanner + StepExecutor 开销。
        if llm is not None:
            try:
                _judge_prompt = (
                    f"用户请求: {task.description}\n\n"
                    f'这个请求需要调用工具(搜索/写文件/执行代码)来完成吗？只回答"需要"或"不需要"'
                )
                _judge_resp = await llm.chat(
                    [{"role": "user", "content": _judge_prompt}],
                    max_tokens=10,
                )
                _judge_text = str(_judge_resp).strip() if _judge_resp else ""
                logger.info(f"工具需求判断结果: {_judge_text}")

                if "不需要" in _judge_text:
                    from rich.console import Console
                    _rcon = Console()
                    _rcon.print("  💬 检测为纯聊天/知识请求，直接回答...")
                    _fast_start = time.time()
                    try:
                        _fast_resp = await llm.chat([
                            {"role": "system", "content": "你是一个智能助手，请直接回答用户的问题。"},
                            {"role": "user", "content": task.description},
                        ], temperature=0.7, max_tokens=2000)
                        output_text = str(_fast_resp).strip() if _fast_resp else ""
                        if not output_text or output_text == "系统正在处理您的请求...":
                            output_text = "您好，请问有什么可以帮您的？"
                    except Exception as e:
                        logger.error(f"快速通道 LLM 回答失败: {e}")
                        output_text = f"抱歉，处理您的请求时出现了问题: {e}"
                    _elapsed = time.time() - _fast_start

                    self.work_history.append({
                        "task_id": task.task_id,
                        "task_type": task.type,
                        "success": True,
                        "execution_time": _elapsed,
                        "timestamp": time.time(),
                        "replans": 0,
                    })
                    if len(self.work_history) > 100:
                        self.work_history = self.work_history[-100:]

                    return ActionResult(
                        success=True,
                        output=output_text,
                        execution_time=_elapsed,
                        metadata={"fast_path": True, "needs_tool": False},
                    )
            except Exception as e:
                logger.warning(f"工具需求判断失败，走完整流程: {e}")

        # ── 结束快速通道，以下为完整流程 ──────────────────────────────────

        try:
            from core.multi_agent_v2.orchestration.scheduler.step_planner import StepPlanner
            planner = StepPlanner(llm_router=llm)
            print("  ⏳ 正在分析任务，拆解执行步骤...")
            steps = await planner.plan(task, tool_registry=registry)
        except Exception as e:
            logger.warning(f"任务拆解失败，使用兜底: {e}")
            from .models import Step, StepStatus, StepType
            steps = [
                Step(step_id="step_1", name="执行任务", description=task.description,
                     type=StepType.LLM_TASK, expected_output="执行结果"),
            ]

        if not steps:
            return ActionResult(success=False, error="任务拆解失败，无可执行步骤")

        # 3. 执行（带进度追踪+反思重规划循环）
        from core.multi_agent_v2.infrastructure.step_executor import StepExecutor
        from .models import NeedsReflection, ProgressSnapshot

        # 步骤指示 — ◐ → Rich 旋转 → ✅
        from rich.console import Console
        _rcon = Console()
        total = len(steps)
        _counter = [0]

        async def _spin(step_num: int, name: str, stop_evt: asyncio.Event):
            """1秒后启动 Rich 旋转动画，步骤完成自动消失"""
            await asyncio.sleep(1.0)
            if stop_evt.is_set():
                return
            frames = ["◐", "◓", "◑", "◒"]
            i = 0
            try:
                while not stop_evt.is_set():
                    _rcon.print(f"  {frames[i]} [{step_num}/{total}] {name}", end="\r")
                    i = (i + 1) % len(frames)
                    await asyncio.sleep(0.15)
            except Exception:
                pass

        def _extract_preview(result_obj, max_len=200) -> str:
            if not result_obj:
                return ""
            if isinstance(result_obj, dict):
                texts = []
                for tr in result_obj.get("tool_results", []):
                    t = tr.get("result", {})
                    if isinstance(t, dict):
                        content = t.get("result", {}).get("content", [])
                        for c in content if isinstance(content, list) else [content]:
                            if isinstance(c, dict):
                                texts.append(str(c.get("text", ""))[:200])
                if result_obj.get("text"):
                    texts.append(str(result_obj["text"])[:200])
                return "\n".join(t for t in texts if t)
            return str(result_obj)[:max_len]

        _stop_evt = [None]

        def _on_step_start(step):
            _counter[0] += 1
            name = getattr(step, 'name', getattr(step, 'step_id', '?'))
            _rcon.print(f"  ◐ [{_counter[0]}/{total}] {name}")
            evt = asyncio.Event()
            _stop_evt[0] = evt
            asyncio.ensure_future(_spin(_counter[0], name, evt))

        def _on_step_complete(step):
            if _stop_evt[0]:
                _stop_evt[0].set()
                _stop_evt[0] = None
            name = getattr(step, 'name', getattr(step, 'step_id', '?'))
            t = getattr(step, 'execution_time', 0)
            time_str = f" ({t:.1f}s)" if t else ""
            _rcon.print(f"  ✅ [{_counter[0]}/{total}] {name}{time_str}")
            preview = _extract_preview(getattr(step, 'result', None))
            if preview:
                _rcon.print(f"     {preview[:200]}")

        def _on_step_failed(step, error=""):
            if _stop_evt[0]:
                _stop_evt[0].set()
                _stop_evt[0] = None
            name = getattr(step, 'name', getattr(step, 'step_id', '?'))
            t = getattr(step, 'execution_time', 0)
            time_str = f" ({t:.1f}s)" if t else ""
            _rcon.print(f"  ❌ [{_counter[0]}/{total}] {name}{time_str}")
            if error:
                _rcon.print(f"     {error[:200]}")

        executor = StepExecutor(llm_router=llm)
        max_replans = 2
        replan_count = 0
        original_steps = steps
        start_time = time.time()

        # 设置初始进度（供 Mind 读取）
        self._progress = ProgressSnapshot(
            remaining=[{"step_id": s.step_id, "name": s.name,
                        "type": s.type.value if hasattr(s.type, 'value') else str(s.type)}
                       for s in steps]
        )

        # 先打印计划概览
        _rcon.print(f"  [{total}] steps plan:")
        for i, s in enumerate(steps, 1):
            _rcon.print(f"      {i}. {s.name}")

        while True:
            try:
                result = await executor.execute(
                    steps,
                    on_step_start=_on_step_start,
                    on_step_complete=_on_step_complete,
                    on_step_failed=_on_step_failed,
                )
                break  # 全部成功
            except NeedsReflection as e:
                if replan_count >= max_replans:
                    logger.warning(f"已达到最大重规划次数 ({max_replans})，任务失败")
                    return ActionResult(
                        success=False,
                        error=f"多次重规划仍失败: {e.reason}",
                        execution_time=time.time() - start_time,
                    )

                # 反思：判断是工具问题还是计划问题
                try:
                    await self.reflect(ActionResult(
                        success=False,
                        error=e.reason,
                        output={"failed_step": e.failed_step, "progress": e.progress.to_prompt()},
                    ))
                except Exception:
                    pass

                # 统一尝试局部重规划
                replan_count += 1
                logger.info(f"第 {replan_count} 次重规划，失败步骤: {e.step_id}")

                try:
                    new_steps = await planner.replan(
                        original_steps=original_steps,
                        completed_ids=[s["step_id"] for s in e.progress.completed],
                        failed_step_id=e.step_id,
                        failed_reason=e.reason,
                    )
                    steps = new_steps
                    # 更新进度
                    self._progress = e.progress
                    self._progress.remaining = [
                        {"step_id": s.step_id, "name": s.name,
                         "type": s.type.value if hasattr(s.type, 'value') else str(s.type)}
                        for s in new_steps
                        if s.step_id not in [c["step_id"] for c in e.progress.completed]
                    ]
                    logger.info(f"重规划完成: {len(steps)} 个步骤 (已完成 {len(e.progress.completed)})")
                except Exception as replan_err:
                    logger.error(f"重规划失败: {replan_err}")
                    return ActionResult(
                        success=False,
                        error=f"重规划失败: {replan_err}",
                        execution_time=time.time() - start_time,
                    )

        execution_time = time.time() - start_time
        success = result.success if hasattr(result, 'success') else True
        raw_steps_list = result.steps if hasattr(result, 'steps') and isinstance(result.steps, list) else []
        output = ""  # Will be populated as a string below; raw steps go into metadata.steps

        # 4. 收集步骤摘要，用 LLM 汇总为人类可读的回答
        step_summary_parts = []
        for s in raw_steps_list:
            status_icon = "成功" if s.status == StepStatus.SUCCESS else "失败"
            result_text = ""
            if s.result:
                if isinstance(s.result, dict):
                    texts = []
                    for tr in s.result.get("tool_results", []):
                        t = tr.get("result", {})
                        if isinstance(t, dict):
                            content = t.get("result", {}).get("content", [])
                            for c in content if isinstance(content, list) else [content]:
                                if isinstance(c, dict):
                                    texts.append(str(c.get("text", ""))[:300])
                                elif isinstance(c, str):
                                    texts.append(c[:300])
                    if s.result.get("text"):
                        texts.append(str(s.result["text"])[:300])
                    result_text = "\n".join(t for t in texts if t)
                else:
                    result_text = str(s.result)[:500]
            elif s.error:
                result_text = f"错误: {s.error[:200]}"
            step_summary_parts.append(f"[{status_icon}] {s.name}\n  结果: {result_text[:200] if result_text else '(无)'}")

        step_summary_raw = "\n---\n".join(step_summary_parts)

        llm_summary = None
        if step_summary_raw.strip():
            try:
                from core.engine.llm_backend import get_llm_router
                _llm = get_llm_router()
                _prompt = f"""你是一个智能助手。请根据下列任务执行步骤摘要，生成一段连贯、人类可读的总结回答，说明完成了什么以及各项结果如何。

步骤摘要：
{step_summary_raw}"""
                _resp = await _llm.chat([
                    {"role": "system", "content": "根据任务执行记录生成简短、有条理的总结回答。"},
                    {"role": "user", "content": _prompt},
                ], temperature=0.3, max_tokens=1000)
                _text = str(_resp).strip() if _resp else ""
                if _text and _text != "系统正在处理您的请求...":
                    llm_summary = _text
            except Exception:
                pass

        if llm_summary:
            output = llm_summary
        else:
            # Fallback: simple concatenation of step results
            lines = []
            for s in raw_steps_list:
                status_str = "成功" if s.status == StepStatus.SUCCESS else "失败"
                res_preview = ""
                if s.result:
                    if isinstance(s.result, dict):
                        res_preview = str(s.result)[:200]
                    else:
                        res_preview = str(s.result)[:200]
                elif s.error:
                    res_preview = f"错误: {s.error[:200]}"
                lines.append(f"[{status_str}] {s.name}: {res_preview}")
            output = "\n".join(lines)

        # 5. 记忆存储（供后续任务检索）
        try:
            from core.multi_agent_v2.agents.memory import get_task_memory, MemoryEntry
            tools_used = []
            for s in raw_steps_list:
                if hasattr(s, 'result') and isinstance(s.result, dict):
                    for tr in s.result.get("tool_results", []):
                        t = tr.get("tool_call", {})
                        if isinstance(t, dict):
                            tools_used.append(t.get("name", ""))
            get_task_memory().remember(MemoryEntry(
                task_id=task.task_id,
                description=task.description,
                result=str(output)[:300] if output else str(success),
                success=success,
                tools_used=tools_used,
            ))
        except Exception:
            pass

        # 6. 记录工作历史
        self.work_history.append({
            "task_id": task.task_id,
            "task_type": task.type,
            "success": success,
            "execution_time": execution_time,
            "timestamp": time.time(),
            "replans": replan_count,
        })

        # 保持最近的记录
        if len(self.work_history) > 100:
            self.work_history = self.work_history[-100:]

        success_result = ActionResult(
            success=success,
            output=output,
            execution_time=execution_time,
            metadata={
                "replans": replan_count,
                "total_steps": len(steps) if hasattr(result, 'total_steps') else 0,
                "steps": [
                    {"step_id": s.step_id, "name": s.name, "status": s.status.value if hasattr(s.status, 'value') else str(s.status)}
                    for s in raw_steps_list
                ],
            },
        )
        return success_result

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
