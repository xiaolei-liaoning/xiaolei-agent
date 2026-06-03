"""
StepExecutor - 分步执行引擎

将 StepPlanner 输出的结构化步骤列表按依赖顺序逐步执行。
每个步骤执行时触发事件，供 CLI 展示或日志记录。

核心流程：
  1. 拓扑排序确保依赖顺序
  2. 按顺序逐个执行步骤（或并行执行无依赖的步骤）
  3. 每个步骤：状态变更 → 执行依赖解析 → 执行步骤 → 状态变更 → 事件触发
  4. 收集所有步骤结果，汇总为 ExecutionResult
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set

from core.multi_agent_v2.agents.base.models import (
    Step, StepStatus, StepType, StepEvent, ExecutionResult, Task,
)

logger = logging.getLogger(__name__)


class StepExecutor:
    """分步执行器 — 按依赖顺序逐步执行步骤"""

    def __init__(self, llm_router=None, agent_pool=None):
        self.llm_router = llm_router
        self.agent_pool = agent_pool
        self._event_listeners: List[Callable[[StepEvent], None]] = []

    def on_step_event(self, callback: Callable[[StepEvent], None]) -> None:
        """注册步骤事件监听器"""
        self._event_listeners.append(callback)

    def _emit_event(self, event_type: str, step: Step, context: Optional[Dict] = None) -> None:
        """触发步骤事件，通知所有监听器"""
        event = StepEvent(
            type=event_type,
            step=step,
            timestamp=time.time(),
            context=context,
        )
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.debug(f"步骤事件监听器异常: {e}")

    async def execute(
        self,
        steps: List[Step],
        task: Optional[Task] = None,
        context: Optional[Dict] = None,
        on_step_start: Optional[Callable[[Step], None]] = None,
        on_step_complete: Optional[Callable[[Step], None]] = None,
        on_step_failed: Optional[Callable[[Step, str], None]] = None,
    ) -> ExecutionResult:
        """按依赖顺序执行所有步骤

        Args:
            steps: 结构化步骤列表
            task: 原始任务（可选）
            context: 执行上下文
            on_step_start: 步骤开始时的回调
            on_step_complete: 步骤成功时的回调
            on_step_failed: 步骤失败时的回调

        Returns:
            执行结果
        """
        total_start = time.time()

        if not steps:
            logger.warning("没有步骤需要执行")
            return ExecutionResult(
                success=True,
                steps=[],
                total_steps=0,
                total_execution_time=0.0,
            )

        # 创建步骤副本（避免修改原始步骤）
        step_map: Dict[str, Step] = {}
        for s in steps:
            step_id = s.step_id or f"step_{uuid.uuid4().hex[:6]}"
            cloned = Step(
                step_id=step_id,
                name=s.name or step_id,
                description=s.description,
                type=s.type,
                status=StepStatus.PENDING,
                dependencies=list(s.dependencies),
                tool_name=s.tool_name,
                tool_args=dict(s.tool_args),
                expected_output=s.expected_output,
                agent_id=s.agent_id,
                metadata=dict(s.metadata),
            )
            step_map[step_id] = cloned

        # 拓扑排序
        sorted_steps = self._topological_sort(list(step_map.values()))
        total = len(sorted_steps)

        logger.info(f"开始分步执行: {total} 个步骤")

        # 执行上下文（用于步骤间传递数据）
        exec_ctx: Dict[str, Any] = {
            "task": task,
            "user_context": context or {},
            "completed": {},  # step_id -> Step
        }

        completed_count = 0
        failed_count = 0
        skipped_count = 0

        for step in sorted_steps:
            # 检查依赖是否全部满足
            deps_met, blocking = self._check_dependencies(step, exec_ctx["completed"])
            if not deps_met:
                logger.warning(f"步骤 {step.step_id} 依赖未就绪: {blocking}")
                step.status = StepStatus.BLOCKED
                step.error = f"依赖未就绪: {blocking}"
                self._emit_event("step_blocked", step, {"blocking": blocking})
                # 检查是否是关键依赖
                if blocking:
                    failed_count += 1
                else:
                    skipped_count += 1
                continue

            # ── 步骤开始 ──
            step.status = StepStatus.RUNNING
            self._emit_event("step_start", step)
            if on_step_start:
                try:
                    on_step_start(step)
                except Exception:
                    pass

            step_start_time = time.time()

            try:
                if step.type == StepType.SEARCH:
                    result = await self._execute_search_step(step, exec_ctx)
                elif step.type == StepType.ANALYSIS:
                    result = await self._execute_analysis_step(step, exec_ctx)
                elif step.type == StepType.TOOL_CALL:
                    result = await self._execute_tool_call_step(step, exec_ctx)
                elif step.type == StepType.LLM_TASK:
                    result = await self._execute_llm_step(step, exec_ctx)
                elif step.type == StepType.HUMAN_INPUT:
                    result = await self._execute_human_input_step(step, exec_ctx)
                else:
                    result = await self._execute_llm_step(step, exec_ctx)

                # ── 步骤成功 ──
                step.execution_time = time.time() - step_start_time
                step.status = StepStatus.SUCCESS
                step.result = result
                exec_ctx["completed"][step.step_id] = step
                completed_count += 1

                self._emit_event("step_complete", step)
                if on_step_complete:
                    try:
                        on_step_complete(step)
                    except Exception:
                        pass

                logger.info(f"步骤 {step.step_id} [{step.name}] 完成 ({step.execution_time:.1f}s)")

            except Exception as e:
                # ── 步骤失败 ──
                step.execution_time = time.time() - step_start_time
                step.status = StepStatus.FAILED
                step.error = str(e)
                exec_ctx["completed"][step.step_id] = step
                failed_count += 1

                self._emit_event("step_failed", step)
                if on_step_failed:
                    try:
                        on_step_failed(step, str(e))
                    except Exception:
                        pass

                logger.error(f"步骤 {step.step_id} [{step.name}] 失败: {e}")

        total_time = time.time() - total_start

        result = ExecutionResult(
            success=failed_count == 0,
            steps=list(step_map.values()),
            total_steps=total,
            completed_steps=completed_count,
            failed_steps=failed_count,
            skipped_steps=skipped_count,
            total_execution_time=total_time,
        )

        self._emit_event("execution_complete", None, {
            "success": result.success,
            "total": total,
            "completed": completed_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "time": total_time,
        })

        logger.info(
            f"分步执行完成: {completed_count}/{total} 成功, "
            f"{failed_count} 失败, {skipped_count} 跳过, "
            f"耗时 {total_time:.1f}s"
        )

        return result

    def _topological_sort(self, steps: List[Step]) -> List[Step]:
        """拓扑排序步骤"""
        step_map = {s.step_id: s for s in steps}
        visited: Set[str] = set()
        result: List[Step] = []

        def dfs(sid: str, path: Set[str]) -> None:
            if sid in visited:
                return
            if sid in path:
                logger.warning(f"检测到循环依赖: {sid}")
                return
            if sid not in step_map:
                return
            path.add(sid)
            for dep_id in step_map[sid].dependencies:
                dfs(dep_id, path)
            path.discard(sid)
            visited.add(sid)
            if step_map[sid] not in result:
                result.append(step_map[sid])

        for step in steps:
            dfs(step.step_id, set())

        return result

    def _check_dependencies(
        self, step: Step, completed: Dict[str, Step]
    ) -> tuple:
        """检查步骤的依赖是否全部满足

        Returns:
            (是否满足, 阻塞的依赖列表)
        """
        if not step.dependencies:
            return True, []

        blocking = []
        for dep_id in step.dependencies:
            dep_step = completed.get(dep_id)
            if dep_step is None:
                blocking.append(f"{dep_id}(未执行)")
            elif dep_step.status != StepStatus.SUCCESS:
                blocking.append(f"{dep_id}({dep_step.status.value})")

        return len(blocking) == 0, blocking

    # ── 各类型步骤执行器 ──────────────────────────────────────

    async def _execute_search_step(self, step: Step, ctx: Dict) -> Any:
        """执行搜索/查询类步骤"""
        query = step.description
        # 优先用上一步上下文中的信息丰富查询
        if ctx.get("completed"):
            last_result = list(ctx["completed"].values())[-1].result
            if last_result:
                if isinstance(last_result, str) and len(last_result) > 20:
                    query = f"{step.description}\n上下文: {last_result[:200]}"

        # 尝试 RAG 搜索
        try:
            from core.search.rag_search_engine import RAGSearchEngine
            engine = RAGSearchEngine()
            result = await engine.search_and_learn(
                query=query, user_id=1, max_results=5, learn=True
            )
            if result:
                return result
        except Exception as e:
            logger.debug(f"RAG 搜索失败: {e}")

        # 兜底：调用 LLM
        return await self._call_llm(f"请搜索并整理以下信息：\n{query}")

    async def _execute_analysis_step(self, step: Step, ctx: Dict) -> Any:
        """执行分析处理类步骤"""
        # 收集上一步的结果作为分析素材
        previous_results = {}
        for dep_id in step.dependencies:
            dep_step = ctx["completed"].get(dep_id)
            if dep_step and dep_step.result:
                previous_results[dep_id] = dep_step.result

        context_str = ""
        if previous_results:
            context_str = "前序步骤结果：\n"
            for dep_id, res in previous_results.items():
                res_str = str(res)[:500] if res else "(无结果)"
                context_str += f"[{dep_id}]: {res_str}\n\n"

        prompt = f"{context_str}请完成以下分析任务：\n{step.description}"
        if step.expected_output:
            prompt += f"\n\n预期产出：{step.expected_output}"

        return await self._call_llm(prompt)

    async def _execute_tool_call_step(self, step: Step, ctx: Dict) -> Any:
        """执行工具调用类步骤"""
        tool_name = step.tool_name
        tool_args = dict(step.tool_args) if step.tool_args else {}

        # 尝试调用 MCP 工具
        try:
            from core.mcp.mcp_client import mcp_client as mcp
            if not mcp._initialized:
                await mcp.initialize()

            servers = await mcp.list_servers()
            for server in servers:
                tools = await mcp.list_tools(server)
                for tool in tools:
                    tname = tool.get("name", "")
                    desc = tool.get("description", "")
                    if tool_name and (tname == tool_name or tname.lower() in tool_name.lower()):
                        result = await mcp.call_tool(server, tname, tool_args)
                        return {"tool": tname, "server": server, "result": result}
                    if not tool_name and (step.description.lower() in desc.lower()):
                        result = await mcp.call_tool(server, tname, tool_args)
                        return {"tool": tname, "server": server, "result": result}

        except Exception as e:
            logger.debug(f"MCP 工具调用失败: {e}")

        # 兜底：用 LLM 处理
        prompt = f"请完成以下工具操作：\n{step.description}"
        if step.tool_args:
            prompt += f"\n参数：{json.dumps(step.tool_args, ensure_ascii=False)}"
        return await self._call_llm(prompt)

    async def _execute_llm_step(self, step: Step, ctx: Dict) -> Any:
        """执行 LLM 生成类步骤"""
        # 收集上下文
        context_parts = []
        for dep_id in step.dependencies:
            dep_step = ctx["completed"].get(dep_id)
            if dep_step and dep_step.result:
                res = dep_step.result
                res_str = str(res)[:800] if res else "(无结果)"
                context_parts.append(f"[{dep_step.name}]: {res_str}")

        prompt = ""
        if context_parts:
            prompt += "已有信息：\n" + "\n\n".join(context_parts) + "\n\n"
        prompt += f"任务：{step.description}"
        if step.expected_output:
            prompt += f"\n\n预期产出：{step.expected_output}"

        return await self._call_llm(prompt)

    async def _execute_human_input_step(self, step: Step, ctx: Dict) -> Any:
        """执行需要用户输入的步骤

        通过 SharedBus 或 QuestionRegistry 向用户请求输入。
        """
        from core.agents.agent_communication import get_question_registry
        import asyncio

        future = get_question_registry().ask(
            agent_id="step_executor",
            agent_name="分步执行器",
            question=step.description,
            context=f"step:{step.step_id}",
            timeout=120,
        )
        try:
            result = await asyncio.wait_for(future, timeout=125)
            return {"user_input": result}
        except asyncio.TimeoutError:
            raise TimeoutError(f"用户输入超时: {step.name}")

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        if self.llm_router:
            try:
                response = await asyncio.wait_for(
                    self.llm_router.chat(
                        [{"role": "user", "content": prompt}],
                        temperature=0.7,
                        max_tokens=1000,
                    ),
                    timeout=20,
                )
                if isinstance(response, dict):
                    content = (response.get("choices", [{}])[0]
                               .get("message", {})
                               .get("content", ""))
                    return content or json.dumps(response, ensure_ascii=False)
                return str(response)
            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")
                raise

        # 没有 LLM 时的兜底
        return f"[模拟执行] {prompt[:100]}..."

    async def execute_step(self, step: Step, context: Dict) -> Step:
        """执行单个独立步骤（外部调用入口）"""
        if step.type == StepType.SEARCH:
            step.result = await self._execute_search_step(step, context)
        elif step.type == StepType.ANALYSIS:
            step.result = await self._execute_analysis_step(step, context)
        elif step.type == StepType.TOOL_CALL:
            step.result = await self._execute_tool_call_step(step, context)
        elif step.type == StepType.LLM_TASK:
            step.result = await self._execute_llm_step(step, context)
        elif step.type == StepType.HUMAN_INPUT:
            step.result = await self._execute_human_input_step(step, context)
        else:
            step.result = await self._execute_llm_step(step, context)

        step.status = StepStatus.SUCCESS if step.error is None else StepStatus.FAILED
        return step
