"""BaseAgent — Agent 基类（多Agent增强版）

设计：Agent = LLM + Tools + 通信 + 反思
从"小龙虾"版合并回：SharedBus 集成 / Agent间通信 / 增强反思 / 置信度评估
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from .models import AgentType, AgentState, Capability, Task, ActionResult, Reflection, AgentMetrics

logger = logging.getLogger(__name__)


class BaseAgent:
    """Agent 基类 — 极简核心 + 多Agent增强"""

    def __init__(self, agent_id=None, agent_type=AgentType.WORKER, name=None, description=""):
        self.agent_id = agent_id or str(uuid.uuid4().hex[:12])
        self.agent_type = agent_type
        self.agent_name = name or f"agent_{self.agent_id[:8]}"
        self.description = description
        self._trace = None
        self._memory = None  # MemorySystem（惰性初始化）

        # ── 多Agent 增强 ──
        self._bus = None                     # SharedBus（惰性初始化）
        self._communication_center = None    # 通信中心（外部注入）
        self.metrics = AgentMetrics()        # 性能指标
        self.task_history: List[Task] = []   # 任务历史
        self.current_load: float = 0.0       # 当前负载
        self.max_load: float = 1.0           # 最大负载
        self.state: AgentState = AgentState.IDLE  # Agent状态（Scheduler用）
        self.health_score: float = 1.0            # 健康度（Scheduler用）
        self.capabilities: List[Capability] = []  # 能力列表（Scheduler用）

    def get_metrics(self) -> "AgentMetrics":
        """返回性能指标（Scheduler/CapabilityMatcher 依赖）"""
        return self.metrics

        logger.info(f"Agent: {self.agent_id} ({self.agent_type.value})")

    def set_trace(self, trace):
        self._trace = trace

    # ── Think/Act/Reflect/Execute ────────────────────────────────────

    async def think(self, task: Task) -> "Thought":
        """LLM 分析任务，生成计划"""
        from .models import Thought
        prompt = "分析任务并制定执行计划。\n\n任务：%s\n\n输出计划步骤，每行一个。" % task.description
        resp = await self._llm_call(prompt, None)
        step = self._parse_response(resp)
        return Thought(reasoning=step.get("reasoning", "") or task.description,
                       plan=[], confidence=0.5)

    async def act(self, plan: list = None, tool_calls: list = None) -> "ActionResult":
        from .models import ActionResult
        if tool_calls:
            results = await self._execute_tool_calls(tool_calls)
            ok = any(r.get("success") for r in results)
            return ActionResult(success=ok, output=results)
        return ActionResult(success=True, output=[])

    async def reflect(self, result: "ActionResult") -> "Reflection":
        """反思执行结果 — 调 AutoReviewer 复盘 + 存入情景记忆 + 广播"""
        from .models import Reflection
        lessons = []
        improvements = []
        perf = {
            "execution_time": result.execution_time,
            "success_rate": self.metrics.success_rate,
        }

        task_id = self.task_history[-1].task_id if self.task_history else ""
        task_desc = self.task_history[-1].description if self.task_history else ""

        # ── AutoReviewer 复盘 ──
        try:
            from core.auto_reviewer import get_auto_reviewer
            review = await get_auto_reviewer().review(
                task_id=task_id,
                task_description=task_desc,
                execution_logs=str(result.output)[:500],
                task_result=str(result.output)[:500],
            )
            if review:
                if review.what_went_well:
                    lessons = [review.what_went_well[:200]]
                if review.improvement:
                    improvements = [review.improvement[:200]]
                if review.pitfalls:
                    perf["pitfalls"] = review.pitfalls[:200]
                if review.is_worth_saving:
                    perf["is_worth_saving"] = True
        except Exception:
            pass

        # ── 存储到情景记忆 ──
        try:
            await self.memory.store_episode({
                "type": "reflection",
                "agent_id": self.agent_id,
                "success": result.success,
                "lessons": lessons,
            })
        except Exception:
            pass

        # ── 发布到 SharedBus（KEPA闭环）──
        await self._publish_to_bus(result, [])

        return Reflection(
            success=result.success,
            lessons_learned=lessons or (["任务成功完成"] if result.success else []),
            improvements=improvements or ([] if result.success else ["考虑使用不同的策略"]),
            performance_metrics=perf,
        )

    async def execute(self, task: Task) -> "ActionResult":
        """执行任务：think -> act -> reflect"""
        self.task_history.append(task)
        thought = await self.think(task)
        result = await self.act(thought.plan, getattr(thought, 'tool_calls', None))
        try:
            await self.reflect(result)
        except Exception:
            pass
        # 更新指标
        self.metrics.tasks_completed += 1
        self.metrics.total_execution_time += result.execution_time
        self.metrics.avg_execution_time = (
            self.metrics.total_execution_time / self.metrics.tasks_completed
        )
        return result

    # ═══════════════════════════════════════════════════════════════
    # SharedBus 集成
    # ═══════════════════════════════════════════════════════════════

    async def _ensure_bus(self) -> None:
        """惰性初始化 SharedBus"""
        if self._bus is not None:
            return
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import (
                get_shared_bus, Message, MessageType,
            )
            self._bus = get_shared_bus()
            await self._bus.subscribe(f"agent:{self.agent_id}",
                                      self._on_bus_direct_message)
            logger.info(f"{self.agent_id}: SharedBus 已连接")
        except Exception as e:
            logger.debug(f"SharedBus 初始化失败: {e}")

    async def _on_bus_direct_message(self, message) -> None:
        """处理 SharedBus 直接消息"""
        logger.info(f"{self.agent_id} 收到总线消息: {message.type.value}")

    async def _publish_to_bus(self, ar: "ActionResult",
                              step_results: list) -> None:
        """发布执行结果到 SharedBus"""
        try:
            await self._ensure_bus()
            if not self._bus:
                return
            task_id = self.task_history[-1].task_id if self.task_history else "unknown"
            payload = {
                "task_id": task_id,
                "agent_id": self.agent_id,
                "agent_type": self.agent_type.value,
                "success": ar.success,
                "steps": len(step_results),
                "execution_time": ar.execution_time,
                "error": ar.error,
                "output_preview": str(ar.output)[:300] if ar.output else "",
            }
            msg = Message(
                type=MessageType.TASK_PROGRESS if ar.success else MessageType.TASK_FAILED,
                sender=self.agent_id,
                topic=f"task:{task_id}",
                payload=payload,
            )
            await self._bus.publish(msg.topic, msg)
        except Exception as e:
            logger.debug(f"SharedBus publish 失败: {e}")

    # ═══════════════════════════════════════════════════════════════
    # Agent间通信
    # ═══════════════════════════════════════════════════════════════

    async def send_message(self, target_agent_id: str, content: Any,
                           message_type: str = "inform") -> Optional[str]:
        """发送消息给指定 Agent。返回 message_id 或 None。"""
        if not self._communication_center:
            logger.warning(f"{self.agent_id}: 通信中心未初始化")
            return None
        try:
            msg_id = await self._communication_center.send_direct(
                sender=self.agent_id,
                receiver=target_agent_id,
                content=content,
                message_type=message_type,
            )
            return msg_id
        except Exception as e:
            logger.debug(f"send_message 失败: {e}")
            return None

    async def broadcast(self, content: Any) -> None:
        """广播消息给所有 Agent。"""
        if not self._communication_center:
            return
        try:
            await self._communication_center.broadcast(
                sender=self.agent_id, content=content,
            )
        except Exception as e:
            logger.debug(f"broadcast 失败: {e}")

    async def request_help(self, target_agent_id: str, content: Any,
                           timeout: int = 30) -> Optional[Dict[str, Any]]:
        """向其他 Agent 请求帮助（请求-响应模式）。"""
        if not self._communication_center:
            return None
        try:
            result = await self._communication_center.request(
                sender=self.agent_id,
                receiver=target_agent_id,
                content=content,
                timeout=timeout,
            )
            return result
        except Exception as e:
            logger.debug(f"request_help 失败: {e}")
            return None

    async def publish_to_topic(self, topic: str, content: Any) -> None:
        """发布消息到主题。"""
        if not self._communication_center:
            return
        try:
            await self._communication_center.publish(
                topic=topic,
                message={
                    "topic": topic,
                    "content": content,
                    "sender": self.agent_id,
                    "timestamp": time.time(),
                },
                sender=self.agent_id,
            )
        except Exception as e:
            logger.debug(f"publish_to_topic 失败: {e}")

    # ═══════════════════════════════════════════════════════════════
    # 执行结果格式化
    # ═══════════════════════════════════════════════════════════════

    def _format_execution_history(self, result: "ActionResult",
                                  reflection=None) -> str:
        """将执行结果格式化为 LLM 可见的历史上下文。"""
        output = result.output
        if not output:
            return ""
        lines = ["### 上一轮执行结果"]
        if isinstance(output, list):
            success = fail = 0
            for item in output:
                if isinstance(item, dict):
                    tc = item.get("tool_call", {})
                    name = tc.get("name", "?")
                    ok = item.get("success", False)
                    if ok:
                        success += 1
                    else:
                        fail += 1
                    res = str(item.get("result", ""))[:150]
                    err = item.get("error", "")
                    lines.append(f"  {name}: {'✓' if ok else '✗'} {res}"
                                 + (f" 原因: {err[:100]}" if err else ""))
            lines.append(f"  摘要: {success} 成功 / {fail} 失败")
        else:
            lines.append(f"  {str(output)[:200]}")

        # 附加反思改进
        if reflection:
            for attr in ("improvements", "lessons_learned"):
                items = getattr(reflection, attr, [])
                for item in items[:3]:
                    lines.append(f"  - {str(item)[:200]}")

        return "\n".join(lines) + "\n" if len(lines) > 1 else ""

    # ═══════════════════════════════════════════════════════════════
    # 反问用户
    # ═══════════════════════════════════════════════════════════════

    async def _ask_user_inline(self, question: str,
                               timeout: int = 30) -> Optional[str]:
        """终端内联反问 — 直接通过 input() 询问用户。

        返回: "proceed" / "retry" / "cancel" / None(超时)
        """
        print(f"\n{self.agent_name}: {question}")
        print(f"  选项: [proceed/retry/cancel] (默认 proceed, 超时{timeout}s)")

        async def _read():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, lambda: input("> ").strip().lower())

        try:
            answer = await asyncio.wait_for(_read(), timeout=timeout)
            if answer in ("retry", "r"):
                return "retry"
            elif answer in ("cancel", "c", "no", "n"):
                return "cancel"
            return "proceed"
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════════
    # 置信度评估
    # ═══════════════════════════════════════════════════════════════

    def _calculate_task_confidence(
        self, task_description: str, result: "ActionResult",
    ) -> float:
        """评估任务是否真正达成。"""
        if not result or not result.output:
            return 0.3

        if isinstance(result.output, list):
            success = sum(1 for r in result.output
                          if isinstance(r, dict) and r.get("success"))
            total = len(result.output)
            rate = success / total if total > 0 else 0

            # 有写文件动作 → 高置信度
            has_write = any(
                r.get("tool_call", {}).get("name", "")
                in ("workspace_write_file", "write_file", "file")
                and r.get("success")
                for r in result.output if isinstance(r, dict)
            )
            if has_write:
                return 0.9
            if rate > 0.7:
                return 0.8
            if rate > 0.5:
                return 0.6
            return 0.4

        return 0.5

    # ── 原有的 run 和工具执行方法保持不变 ────────────────────────────

    async def run(self, task_description: str,
                  max_iterations: int = 10) -> Dict:
        """分步执行：拆解 → 逐步骤(LLM+工具) → 汇总"""
        return await self._legacy_run(task_description, max_iterations)

    async def _legacy_run(self, task_description: str,
                          max_iterations: int = 10) -> Dict:
        """原有的 run 方法（保留兼容）"""
        trace = self._trace
        from core.multi_agent_v2.agents.middleware import RunContext
        ctx = RunContext(task_description)
        ctx.trace = trace

        tool_defs = []
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
            reg = get_tool_registry()
            if not reg._initialized:
                await reg.discover_all()
            raw = await reg.get_tools_for_task(task_description, max_tools=100)
            items = [
                {"type": "function",
                 "function": {"name": t.name, "description": t.description,
                              "parameters": t.parameters},
                 "_server": t.server, "_tool_name": t.tool_name}
                for t in raw if t.server == "__builtin__"
            ]
            tool_defs = items
        except Exception:
            pass

        simple = len(task_description) < 30 and not any(
            kw in task_description for kw in
            ["搜索", "查找", "写", "创建", "生成", "分析", "报告",
             "爬", "保存", "桌面", "文件", "数据", "代码", "游戏", "脚本"])
        if simple:
            resp = await self._llm_call(task_description, None)
            step = self._parse_response(resp)
            answer = step.get("text", "") or step.get("reasoning", "")
            if trace:
                trace.done(True, detail="直接回答")
            return {"success": True,
                    "result": {"tool_results": [], "final_answer": answer},
                    "iterations": 1}

        from core.multi_agent_v2.orchestration.scheduler.step_planner import \
            StepPlanner
        from core.multi_agent_v2.agents.base.models import Task as TaskModel
        from core.engine.llm_backend import get_llm_router
        llm = get_llm_router()
        t = TaskModel(task_id="decompose", type="general",
                      description=task_description, estimated_steps=3)
        planner = StepPlanner(llm_router=llm)
        try:
            steps = await planner.plan(t, tool_registry=reg)
            steps = [f"{s.tool_name}:{s.name}" if s.tool_name else s.name
                     for s in steps] or ["获取数据", "分析处理", "输出结果"]
        except Exception:
            steps = ["获取数据", "分析处理", "输出结果"]

        if trace:
            trace.set_plan(steps)

        results = []
        prev_context = ""
        for step_idx, step_name in enumerate(steps or []):
            if trace:
                trace.on_tool_call("步骤%d" % (step_idx + 1), step_name[:60])
            result_text = ""
            attempt_tools = list(tool_defs)

            for attempt in range(2):
                prompt = (
                    "## 步骤 %d/%d\n%s\n\n完整任务：%s\n\n"
                    % (step_idx + 1, len(steps), step_name, task_description)
                )
                if prev_context:
                    prompt += "已完成：%s\n\n" % prev_context[:800]
                if attempt > 0:
                    prompt += "上一步工具失败。请换其他工具或方法。\n"
                    prompt += "提示：如果网页获取失败，可以用 execute_python 写 Python 代码通过 requests 库抓取。\n"
                for td in attempt_tools:
                    prompt += "- %s: %s\n" % (
                        td["function"]["name"], td["function"]["description"])

                response = await self._llm_call(prompt, attempt_tools)
                step = self._parse_response(response)
                action = step.get("action", {})
                text = step.get("text", "") or step.get("reasoning", "")

                if action and action.get("name"):
                    tn = action["name"]
                    tc = {
                        "name": tn, "arguments": action.get("arguments", {}),
                        "_tool_name": tn, "_server": "",
                    }
                    r = await self._execute_single_tool_call(tc)
                    ok = r.get("success", False)
                    obs = self._extract_observation(r)
                    if trace:
                        (trace.on_tool_result if ok else trace.on_tool_error)(
                            obs[:200] or "无结果")
                    if ok:
                        result_text = obs
                        break
                    attempt_tools = [
                        td for td in attempt_tools
                        if td["function"]["name"] != tn
                    ]
                else:
                    result_text = text
                    if trace:
                        trace.on_tool_result(text[:200])
                    break

            if not result_text:
                result_text = "(步骤执行失败)"

            results.append({
                "step": step_name, "result": result_text,
                "tool_call": f"tool_{step_idx+1}",
            })
            prev_context += "\n步骤%d (%s): %s\n" % (
                step_idx + 1, step_name,
                result_text[:200].replace("\n", " "))

        answer = "\n\n".join(
            "步骤%d: %s" % (i + 1, r["result"][:300])
            for i, r in enumerate(results) if r.get("result"))
        if trace:
            trace.done(True, detail="%d 步完成" % len(results))
        return {
            "success": True,
            "result": {"tool_results": results, "final_answer": answer},
            "iterations": len(results),
        }

    # ── LLM 调用 ──────────────────────────────────────────────────────

    async def _llm_call(self, prompt, tools=None):
        from core.engine.llm_backend import get_llm_router
        try:
            llm = get_llm_router()
            resp = await asyncio.wait_for(
                llm.chat([
                    {"role": "system",
                     "content": "ReAct 智能体。调用工具完成任务。完成时输出："
                                '{"reasoning":"...","summary":"回复","done":true}'},
                    {"role": "user", "content": prompt},
                ], temperature=0.3, max_tokens=2000, tools=tools),
                timeout=30)
            return resp
        except asyncio.TimeoutError:
            return '{"reasoning":"超时","done":true}'
        except Exception as e:
            return '{"reasoning":"错误","text":"%s","done":true}' % e

    def _parse_response(self, response) -> Dict:
        result = {"reasoning": "", "action": {}, "text": "", "done": False}
        try:
            parsed = json.loads(response) if isinstance(response, str) else response
            if isinstance(parsed, dict):
                for tc in parsed.get("tool_calls", []):
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    result["action"] = {
                        "name": fn.get("name", ""),
                        "arguments": json.loads(args) if isinstance(args, str) else args,
                    }
                    return result
                for ch in parsed.get("choices", []):
                    msg = ch.get("message", {})
                    for tc in msg.get("tool_calls", []):
                        fn = tc.get("function", {})
                        args = fn.get("arguments", "{}")
                        result["action"] = {
                            "name": fn.get("name", ""),
                            "arguments": json.loads(args) if isinstance(args, str) else args,
                        }
                        return result
                    content = msg.get("content", "")
                    if content:
                        inner = self._try_json(content)
                        if inner:
                            for k in ("reasoning", "text", "summary", "done",
                                      "plan_update"):
                                v = inner.get(k)
                                if v is not None:
                                    result[k] = v
                            return result
                        result["text"] = content
                        result["reasoning"] = content[:300]
                        return result
                    return result
        except Exception:
            pass
        if isinstance(response, str):
            j = self._try_json(response)
            if j:
                result["reasoning"] = j.get("reasoning", "")
                act = j.get("action", {})
                if act and isinstance(act, dict) and act.get("name"):
                    result["action"] = act
                result["text"] = j.get("text", j.get("summary", ""))
                result["done"] = j.get("done", False)
                return result
            if response.strip():
                result["reasoning"] = response[:300]
                result["text"] = response
        return result

    def _try_json(self, text):
        try:
            return json.loads(text.strip())
        except Exception:
            pass
        import re
        m = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except Exception:
                pass
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return None

    def _extract_observation(self, result: Dict) -> str:
        try:
            c = result.get("result", {}).get("result", {}).get("content", [])
            if isinstance(c, list):
                return "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
            return str(result.get("result", ""))[:500]
        except Exception:
            return str(result.get("result", ""))[:500]

    # ── 工具执行 ──────────────────────────────────────────────────────

    async def _execute_single_tool_call(self, tc: Dict) -> Dict:
        results = await self._execute_tool_calls([tc])
        return results[0] if results else {"success": False, "error": "无返回"}

    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        results = []
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry
        registry = get_tool_registry()
        if not registry._initialized:
            await registry.discover_all()
        trace = self._trace

        for tc in tool_calls:
            raw_name = tc.get("name", "")
            args = tc.get("arguments", {}).copy()
            tool_name = tc.get("_tool_name", raw_name)
            server = tc.get("_server", "")
            if trace:
                trace.on_tool_call(tool_name, args)

            # 已知 server → 直达 MCP
            if server and server not in ("__builtin__", "__skill__",
                                          "__api__", "__guidance__"):
                try:
                    from core.mcp.mcp_client import mcp_client
                    rt = await mcp_client.call_tool(server, tool_name, args)
                    result = {"result": {"content": [{"text": rt}]}}
                    results.append({
                        "tool_call": tc, "success": True, "result": result,
                    })
                    if trace:
                        trace.on_tool_result(str(result)[:200])
                    continue
                except Exception as e:
                    logger.debug("MCP 直达路由失败 %s/%s: %s" %
                                 (server, tool_name, e))
                    if trace:
                        trace.on_tool_error("MCP 直达失败: %s" % e)
                    results.append({
                        "tool_call": tc, "success": False, "error": str(e),
                    })
                    continue

            # Handler 路由
            handler = registry.get_handler(tool_name)
            if handler:
                try:
                    r = await handler(args)
                    results.append({
                        "tool_call": tc, "success": True, "result": r,
                    })
                    if trace:
                        trace.on_tool_result(str(r)[:200])
                    continue
                except Exception as e:
                    logger.debug("handler %s 失败: %s" % (tool_name, e))
                    if trace:
                        trace.on_tool_error("handler 异常: %s" % e)

            # 兜底 MCP 路由
            result = None
            try:
                from core.mcp.mcp_client import mcp_client
                if server:
                    rt = await mcp_client.call_tool(server, tool_name, args)
                    result = {"result": {"content": [{"text": rt}]}}
                else:
                    for srv in await mcp_client.list_servers():
                        for t in await mcp_client.list_tools(srv):
                            if t.get("name") == tool_name:
                                rt = await mcp_client.call_tool(
                                    srv, tool_name, args)
                                result = {"result": {
                                    "content": [{"text": rt}]}}
                                break
                        if result:
                            break
                if not result:
                    from core.mcp.awesome_mcp_manager import \
                        awesome_mcp_manager
                    for td in await awesome_mcp_manager.get_all_tool_definitions():
                        if td.get("function", {}).get("name") in (
                                raw_name, tool_name):
                            result = await awesome_mcp_manager.call_tool_by_definition(
                                td, args)
                            break
            except Exception:
                pass
            ok = result is not None
            results.append({
                "tool_call": tc, "success": ok, "result": result,
            })
            if trace:
                (trace.on_tool_result if ok else trace.on_tool_error)(
                    str(result)[:200] if result else "调用失败")
        return results

    # ── 记忆（惰性初始化）──

    @property
    def memory(self):
        """惰性初始化 MemorySystem"""
        if self._memory is None:
            from .memory import MemorySystem
            self._memory = MemorySystem(self)
        return self._memory

    def __repr__(self):
        return "BaseAgent(id=%s, type=%s)" % (self.agent_id,
                                               self.agent_type.value)


class AgentFactory:
    """创建 Agent — 支持多Agent编排

    提供静态工厂方法，创建 WorkAgent 实例。
    """

    @staticmethod
    def create_agent(agent_type=AgentType.WORKER, agent_id=None,
                     name=None, description="", **kwargs):
        """创建单个 WorkAgent"""
        from .work_agent import WorkAgent
        return WorkAgent(
            agent_id=agent_id,
            name=name or f"agent_{agent_id[:8] if agent_id else '?'}",
            description=description or "WorkAgent",
        )

    @staticmethod
    def create_agents(count: int = 2, **kwargs) -> list:
        """批量创建多个 WorkAgent"""
        from .work_agent import WorkAgent
        return [
            WorkAgent(
                agent_id=kwargs.get("agent_id_prefix", "") + f"agent-{i}",
                name=kwargs.get("name_prefix", "") + f"worker_{i}",
            )
            for i in range(count)
        ]

    @staticmethod
    def create_agents_for_task(keywords, min_count=2, max_count=5):
        """为任务创建多个 Agent（旧接口，保留兼容）"""
        from .work_agent import WorkAgent
        count = max(min_count, min(max_count, len(keywords) + 1))
        return [WorkAgent(agent_id=f"agent-{i}", name=f"worker_{i}")
                for i in range(count)]

    @staticmethod
    def create_coordinator(name="coordinator"):
        """创建协调 Agent（一个用来分配任务的 Master）"""
        from .work_agent import WorkAgent
        return WorkAgent(agent_id="coordinator", name=name)

    @staticmethod
    def create_reviewer(name="reviewer"):
        """创建审查 Agent（一个用来审查结果的 Reviewer）"""
        from .work_agent import WorkAgent
        return WorkAgent(agent_id="reviewer", name=name)
