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
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set

from core.multi_agent_v2.agents.base.models import (
    Step, StepStatus, StepType, StepEvent, ExecutionResult, Task,
    ProgressSnapshot, NeedsReflection,
)

logger = logging.getLogger(__name__)


def _extract_text(result_obj: Any, max_len: int = 300) -> str:
    """从 tool_results 的标准嵌套格式提取 text 字符串

    处理 "tool_results" -> "result" -> "content" 链，
    兼容 dict/list 多种格式，返回合并后的字符串。

    Args:
        result_obj: 步骤结果对象（可能是 dict 或其他类型）
        max_len: 每段文本最大长度

    Returns:
        提取出的文本字符串
    """
    if not isinstance(result_obj, dict):
        return str(result_obj)[:max_len]

    texts = []
    for tr in result_obj.get("tool_results", []):
        t = tr.get("result", {})
        if not isinstance(t, dict):
            texts.append(str(t)[:max_len])
            continue
        # 新结构化摘要格式（P0 改造后）
        if t.get("structured") and t.get("summary"):
            texts.append(f"[摘要] {t['summary'][:max_len]}")
            for kp in (t.get("key_points") or [])[:3]:
                texts.append(f"  - {kp[:200]}")
        # 旧原始格式
        else:
            content = t.get("result", {}).get("content", [])
            for c in content if isinstance(content, list) else [content]:
                if isinstance(c, dict):
                    texts.append(str(c.get("text", ""))[:max_len])
                elif isinstance(c, str):
                    texts.append(c[:max_len])

    if result_obj.get("text"):
        texts.append(str(result_obj["text"])[:500])

    return "\n".join(texts) or str(result_obj)[:max_len]


class StepExecutor:
    """分步执行器 — 按依赖顺序逐步执行步骤"""

    def __init__(self, llm_router=None, agent_pool=None):
        self.llm_router = llm_router
        self.agent_pool = agent_pool
        self._event_listeners: List[Callable[[StepEvent], None]] = []
        self.progress = ProgressSnapshot()

    def get_progress(self) -> ProgressSnapshot:
        """返回当前执行进度快照"""
        return self.progress

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

        for exec_step_idx, step in enumerate(sorted_steps):
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

            # Set current step in progress
            self.progress.current = {
                "step_id": step.step_id,
                "name": step.name,
                "type": step.type.value if hasattr(step.type, 'value') else str(step.type),
            }
            # Remove from remaining if present
            self.progress.remaining = [
                r for r in self.progress.remaining
                if r["step_id"] != step.step_id
            ]

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
                if step.type == StepType.HUMAN_INPUT:
                    result = await self._execute_human_input_step(step, exec_ctx)
                else:
                    result = await self._execute_step_via_react(step, exec_ctx)

                # ── 步骤成功 ──
                step.execution_time = time.time() - step_start_time
                step.status = StepStatus.SUCCESS
                step.result = result
                exec_ctx["completed"][step.step_id] = step
                completed_count += 1

                # 记忆存储
                try:
                    from core.multi_agent_v2.agents.memory import get_task_memory, MemoryEntry
                    get_task_memory().remember(MemoryEntry(
                        task_id=f"step_{step.step_id}",
                        description=step.description or step.name,
                        result=str(result)[:200] if result else "success",
                        success=True,
                        tools_used=[step.tool_name] if step.tool_name else [],
                    ))
                except Exception:
                    pass

                # Update progress
                self.progress.completed.append({
                    "step_id": step.step_id,
                    "name": step.name,
                    "result": str(result)[:200] if result else "",
                    "status": "success",
                })
                self.progress.current = None

                self._emit_event("step_complete", step)
                if on_step_complete:
                    try:
                        on_step_complete(step)
                    except Exception:
                        pass

                logger.info(f"步骤 {step.step_id} [{step.name}] 完成 ({step.execution_time:.1f}s)")

            except Exception as e:
                # ── 步骤失败 ──
                # 记忆存储（失败也记录，供后续反思参考）
                try:
                    from core.multi_agent_v2.agents.memory import get_task_memory, MemoryEntry
                    get_task_memory().remember(MemoryEntry(
                        task_id=f"step_{step.step_id}",
                        description=step.description or step.name,
                        result=f"failed: {str(e)[:200]}",
                        success=False,
                        tools_used=[step.tool_name] if step.tool_name else [],
                    ))
                except Exception:
                    pass
                step.execution_time = time.time() - step_start_time
                step.status = StepStatus.FAILED
                step.error = str(e)
                exec_ctx["completed"][step.step_id] = step
                failed_count += 1

                # Count failure
                self.progress.failed_attempts[step.step_id] = \
                    self.progress.failed_attempts.get(step.step_id, 0) + 1
                fa = self.progress.failed_attempts[step.step_id]

                if fa >= 2:
                    # Trigger reflection
                    self.progress.completed.append({
                        "step_id": step.step_id,
                        "name": step.name,
                        "result": str(e)[:200],
                        "status": "failed",
                    })
                    self.progress.current = None
                    remaining_summary = [
                        {"step_id": s.step_id, "name": s.name,
                         "type": s.type.value if hasattr(s.type, 'value') else str(s.type)}
                        for s in sorted_steps[exec_step_idx:]
                        if s.step_id != step.step_id
                    ]
                    raise NeedsReflection(
                        step_id=step.step_id,
                        reason=str(e),
                        progress=self.progress,
                        remaining_steps=remaining_summary,
                        failed_step={"step_id": step.step_id, "name": step.name, "error": str(e)},
                    )
                else:
                    # First failure - add to completed as failed and continue
                    self.progress.completed.append({
                        "step_id": step.step_id,
                        "name": step.name,
                        "result": str(e)[:200],
                        "status": "failed",
                    })
                    self.progress.current = None

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

    # ── 步骤执行（统一走 ReActCore） ─────────────────────────────

    async def _execute_step_via_react(self, step: Step, ctx: Dict) -> Any:
        """执行单个步骤

        如果步骤已指定工具（tool_name）→ 直接调工具，不走 LLM
        否则 → run_react() 经过完整 MiddlewareChain（含 KEPA/反问/反思）
        """
        # 收集前序步骤结果作为上下文
        context_parts = []
        for dep_id in step.dependencies:
            dep_step = ctx["completed"].get(dep_id)
            if dep_step and dep_step.result:
                context_parts.append(
                    f"[{dep_step.name}]: {_extract_text(dep_step.result)}"
                )

        # ── 统一走 run_react() 标准路径（全中间件链） ──
        task_desc = step.description
        # 注入 tool_name 到 prompt，让 LLM 第1轮直接调工具而不是重新选择
        step_tool_name = getattr(step, 'tool_name', '') or ''
        if step_tool_name:
            task_desc += f"\n\n[工具提示] 请使用工具「{step_tool_name}」完成此步骤。不需要选择其他工具。"
        if context_parts:
            task_desc = "### 已有上下文\n" + "\n\n".join(context_parts) + \
                        "\n\n### 当前任务\n" + task_desc
        if step.expected_output:
            task_desc += f"\n\n预期产出：{step.expected_output}"

        # 若步骤涉及代码执行，注入 macOS 系统上下文（通过任务描述提示 LLM）
        if any(t in (step.tool_name or '') for t in ('execute_python','execute_shell','execute_code')) or '代码' in (step.description or ''):
            task_desc += ("\n\n[系统环境] macOS Darwin, home=/Users/leiyuxuan, "
                          "desktop=/Users/leiyuxuan/Desktop。请只使用 Python 标准库，"
                          "不要安装或使用第三方包。")

        # RAG 知识注入（非阻塞——8 秒内拿不到就算了）
        try:
            import asyncio
            async def _rag_inject():
                from core.search.rag_search_engine import RAGSearchEngine
                engine = RAGSearchEngine()
                rag_result = await engine.search_and_learn(
                    query=step.description, user_id=1, max_results=2, learn=False
                )
                if rag_result and rag_result.get("results"):
                    return f"\n\n### 相关知识\n{str(rag_result['results'])[:1000]}"
                return ""
            rag_text = await asyncio.wait_for(_rag_inject(), timeout=8.0)
            task_desc += rag_text
        except asyncio.TimeoutError:
            pass  # RAG 超时不影响执行
        except Exception:
            pass

        from core.multi_agent_v2.agents.react_core import run_react
        result = await run_react(task_desc)
        return result

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

    async def execute_step(self, step: Step, context: Dict) -> Step:
        """执行单个独立步骤（外部调用入口）"""
        if step.type == StepType.HUMAN_INPUT:
            step.result = await self._execute_human_input_step(step, context)
        else:
            step.result = await self._execute_step_via_react(step, context)

        step.status = StepStatus.SUCCESS if step.error is None else StepStatus.FAILED
        return step

    async def _summarize_tool_result(
        self, tool_name: str, tool_args: Dict, raw_result: Any, step_description: str
    ) -> Dict:
        """对工具返回的原始结果进行 LLM 分析，产出结构化摘要

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            raw_result: 工具原始返回结果
            step_description: 步骤描述

        Returns:
            结构化摘要字典，包含 summary/key_points/findings/raw_excerpt/has_errors 等字段
            降级时 is_raw=True 保留原始文本片段
        """
        # ── 提取文本内容 ──
        raw_text = ""
        if isinstance(raw_result, dict):
            content = raw_result.get("content", [])
            if isinstance(content, list):
                texts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        texts.append(c.get("text", ""))
                raw_text = "\n".join(texts)
            elif isinstance(content, str):
                raw_text = content
            else:
                raw_text = str(raw_result.get("result", str(raw_result)))
        elif isinstance(raw_result, str):
            raw_text = raw_result
        else:
            raw_text = str(raw_result)

        # 结果太短不需要分析，直接返回
        if len(raw_text) < 200:
            return {
                "summary": raw_text[:500],
                "key_points": [],
                "findings": {},
                "raw_excerpt": raw_text[:200],
                "has_errors": False,
                "is_raw": True,
                "structured": False,
            }

        # ── 构造 LLM 分析 prompt ──
        try:
            tool_args_str = json.dumps(tool_args, ensure_ascii=False)[:500]
        except Exception:
            tool_args_str = str(tool_args)[:500]

        prompt = f"""你是一个数据分析助手。请分析以下工具执行结果，产出结构化摘要。

### 工具名称
{tool_name}

### 工具参数
{tool_args_str}

### 步骤目标
{step_description[:300]}

### 原始执行结果
```text
{raw_text[:4000]}
```

请分析上述结果，返回 JSON 格式的结构化摘要：

1. "summary" (str): 一段简洁的中文摘要，总结关键发现（200字以内）
2. "key_points" (List[str]): 3-5 个关键数据点或结论，每点不超过 50 字
3. "findings" (dict): 按类别组织的重要发现（至少包含 2 个类别）
4. "raw_excerpt" (str): 原始结果中最重要的段落（200字以内）
5. "has_errors" (bool): 结果中是否包含错误信息

仅返回 JSON，不要包含其他文字。"""

        try:
            import anthropic
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            content_text = response.content[0].text if response.content else ""

            # 从 LLM 响应中提取 JSON
            json_str = None
            # 优先匹配 markdown 代码块
            m = re.search(r'```(?:json)?\s*(.*?)\s*```', content_text, re.DOTALL)
            if m:
                json_str = m.group(1)
            else:
                # 匹配裸 JSON 对象
                m = re.search(r'(\{.*\})', content_text, re.DOTALL)
                if m:
                    json_str = m.group(1)

            if json_str:
                structured = json.loads(json_str)
                structured.setdefault("summary", content_text[:300])
                structured.setdefault("key_points", [])
                structured.setdefault("findings", {})
                structured.setdefault("raw_excerpt", raw_text[:200])
                structured.setdefault("has_errors", False)
                structured["is_raw"] = False
                structured["structured"] = True
                return structured
        except Exception as e:
            logger.debug(f"LLM 分析工具结果失败: {e}")

        # ── 降级：直接返回原始结果摘要 ──
        return {
            "summary": raw_text[:500],
            "key_points": [],
            "findings": {},
            "raw_excerpt": raw_text[:200],
            "has_errors": False,
            "is_raw": True,
            "structured": False,
        }
