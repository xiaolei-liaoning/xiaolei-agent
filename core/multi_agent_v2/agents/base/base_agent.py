"""BaseAgent — Agent 基类

设计：Agent = LLM + Tools + MiddlewareChain
- LLM：模型推理
- Tools：ToolRegistry 注册的工具
- MiddlewareChain：注入的中间件（可选）

run() 启动 ReAct 循环：Thought → Action → Observation → 直到 done
"""

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from .models import AgentType, Task, ActionResult

logger = logging.getLogger(__name__)


class BaseAgent:
    """Agent 基类 — 极简核心"""

    def __init__(self, agent_id=None, agent_type=AgentType.WORKER, name=None, description=""):
        self.agent_id = agent_id or str(uuid.uuid4().hex[:12])
        self.agent_type = agent_type
        self.agent_name = name or f"agent_{self.agent_id[:8]}"
        self.description = description
        self._trace = None
        logger.info(f"Agent: {self.agent_id}")

    def set_trace(self, trace):
        self._trace = trace

    # ── Think/Act/Reflect（兼容 collaboration 策略） ─────────────────

    async def think(self, task: Task) -> "Thought":
        """思考（兼容旧接口）—— 实际已集成到 run()"""
        from .models import Thought
        return Thought(reasoning=f"任务: {task.description}", plan=[], confidence=0.5)

    async def act(self, plan: list = None, tool_calls: list = None) -> "ActionResult":
        """执行（兼容旧接口）"""
        from .models import ActionResult
        if tool_calls:
            results = await self._execute_tool_calls(tool_calls)
            ok = any(r.get("success") for r in results)
            return ActionResult(success=ok, output=results)
        return ActionResult(success=True, output=[])

    async def reflect(self, result: "ActionResult") -> "Reflection":
        """反思（兼容旧接口）"""
        from .models import Reflection
        return Reflection(success=result.success, lessons_learned=[], improvements=[], performance_metrics={})

    async def execute(self, task: Task) -> "ActionResult":
        """执行任务（兼容旧接口）"""
        return await self.act(plan=[task.description])

    # ── ReAct 循环 ────────────────────────────────────────────────────

    async def run(self, task_description: str, max_iterations: int = 10) -> Dict:
        """ReAct 循环：Thought → Action → Observation → done"""
        trace = self._trace
        from core.multi_agent_v2.agents.middleware import RunContext, MiddlewareChain
        from core.multi_agent_v2.agents.middlewares import (
            ProfileMiddleware, ConfidenceMiddleware, ReActDepthMiddleware,
            DataPipelineMiddleware, KEPAMiddleware, BranchMiddleware,
        )

        ctx = RunContext(task_description)
        ctx.max_iterations = max_iterations
        ctx.trace = trace
        ctx.memory_log = []   # 记忆：每轮关键信息摘要
        ctx.rag_context = ""  # RAG：首轮检索到的相关知识

        # ── RAG 检索（首轮注入相关知识） ──────────────────────
        try:
            from core.search.rag_search_engine import RAGSearchEngine
            rag = RAGSearchEngine()
            rag_result = await rag.search_and_learn(query=task_description, user_id=1, max_results=3, learn=False)
            if rag_result and rag_result.get("results"):
                texts = []
                for r in rag_result["results"][:3]:
                    content = r.get("content", r.get("text", ""))
                    if content:
                        texts.append(str(content)[:300])
                if texts:
                    ctx.rag_context = "\n".join(texts)
        except Exception as e:
            logger.debug(f"RAG 检索失败: {e}")

        # 组装中间件链（按需添加，全可选）
        chain = MiddlewareChain()
        for cls in [ReActDepthMiddleware, ProfileMiddleware, ConfidenceMiddleware,
                    BranchMiddleware, DataPipelineMiddleware, KEPAMiddleware]:
            mw = cls()
            mw._agent = self
            chain.add(mw)
        await chain.on_start(ctx)

        # 获取工具定义（只暴露可执行的工具）
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry, _HANDLER_MAP, SERVER_BUILTIN, SERVER_MCP
            reg = get_tool_registry()
            if not reg._initialized:
                await reg.discover_all()
            raw_tools = reg.get_tools_for_task(task_description, max_tools=25)

            # 只保留有 handler 的 builtin 工具 或 MCP 工具；去掉无执行的 skill/api/guidance
            def _executable(t):
                if t.name in _HANDLER_MAP: return True
                if t.handler is not None: return True
                if t.server and t.server not in ("__skill__", "__api__", "__guidance__", ""): return True
                return False

            ctx.tool_defs = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                 "_server": t.server, "_tool_name": t.tool_name}
                for t in raw_tools if _executable(t)
            ]

            # 确保核心工具始终在最前
            core_names = ["fetch_url", "file", "execute_code", "workspace_file"]
            core = [td for td in ctx.tool_defs if td["function"]["name"] in core_names]
            others = [td for td in ctx.tool_defs if td["function"]["name"] not in core_names]
            ctx.tool_defs = core + others[:20]

            if not ctx.tool_defs:
                ctx.tool_defs = raw_tools[:10]  # 兜底
        except Exception:
            ctx.tool_defs = []

        # ── 任务拆解：先让 LLM 输出执行计划 ──────────────────────
        ctx.plan_steps = await self._decompose_task(task_description, ctx.tool_defs)
        ctx.current_step = 0
        if trace:
            trace.set_plan(ctx.plan_steps)

        # ── ReAct 循环 ──────────────────────────────────────────
        _consecutive_fail = 0  # 连续失败计数，超过 5 次强制退出
        for iteration in range(1, max_iterations + 1):
            ctx.iteration = iteration
            if ctx.interrupted:
                break
            if _consecutive_fail >= 5:
                logger.warning(f"连续 {_consecutive_fail} 次失败，强制退出")
                if not ctx.final_answer:
                    ctx.final_answer = "连续执行失败，请重试或检查环境配置"
                break
                break
            if trace:
                trace.on_thinking(f"第{iteration}步", task_description[:60])

            await chain.on_think_start(ctx)
            response = await self._llm_call(
                self._build_prompt(task_description, iteration, ctx.tool_results, ctx.last_error,
                                   ctx.plan_steps, ctx.current_step, ctx.memory_log, ctx.rag_context),
                ctx.tool_defs,
            )
            step = self._parse_response(response)
            await chain.on_think_end(ctx)

            reasoning = step.get("reasoning", "")
            action = step.get("action", {})
            text = step.get("text", "")
            done = step.get("done", False)
            plan_update = step.get("plan_update", None)

            # 动态调整执行计划
            if plan_update and isinstance(plan_update, list) and len(plan_update) > 0:
                old_steps = list(ctx.plan_steps or [])
                # 保留已完成步骤，替换剩余步骤
                completed = old_steps[:ctx.current_step]
                ctx.plan_steps = completed + plan_update
                logger.info(f"计划动态调整: {old_steps[ctx.current_step:] if ctx.current_step < len(old_steps) else '全部'} → {plan_update}")
                if trace:
                    trace.set_plan(ctx.plan_steps)

            if done:
                ctx.final_answer = text or reasoning
                break

            if not action:
                if text:
                    ctx.tool_results.append({"tool_call": {"name": "_reply"}, "success": True, "result": text})
                elif reasoning and len(reasoning) > 50:
                    ctx.final_answer = reasoning
                    break
                continue

            tn = action.get("name", "")
            if not tn:
                continue
            # 去重
            recent = [r for r in ctx.tool_results[-6:] if r.get("tool_call", {}).get("name", "") == tn]
            if len(recent) >= 3:
                ctx.tool_results.append({"tool_call": action, "success": False, "error": f"跳过 {tn}（连续{len(recent)}次）"})
                await chain.on_tool_end(ctx)
                continue

            try:
                result = await self._execute_single_tool_call(action)
                ok = result.get("success", False)
                obs = self._extract_observation(result)
                ctx.tool_results.append({"tool_call": action, "success": ok, "result": result.get("result", {}), "error": result.get("error", "")})
                await chain.on_tool_end(ctx)
                if trace:
                    trace.on_tool_result(obs[:200], max_lines=3)
                if not ok:
                    ctx.last_error = obs[:200]
                    _consecutive_fail += 1
                    # fetch_url 连续失败 2 次后自动移除
                    if tn == "fetch_url" and _consecutive_fail >= 2:
                        ctx.tool_defs = [td for td in ctx.tool_defs if td.get("function",{}).get("name") != "fetch_url"]
                else:
                    _consecutive_fail = 0
                # 记忆：记录本轮关键信息
                if ok and obs:
                    summary = f"[{tn}] {obs[:100]}"
                    ctx.memory_log.append(summary)
                # 步骤推进：成功调用工具后进入下一步
                if ok and ctx.plan_steps and ctx.current_step < len(ctx.plan_steps) - 1:
                    ctx.current_step += 1
                    logger.info(f"推进到第 {ctx.current_step+1}/{len(ctx.plan_steps)} 步: {ctx.plan_steps[ctx.current_step]}")
            except Exception as e:
                ctx.tool_results.append({"tool_call": action, "success": False, "error": str(e)})
                _consecutive_fail += 1
                await chain.on_tool_end(ctx)
                if trace:
                    trace.on_tool_error(str(e)[:200])

        await chain.on_finish(ctx)
        success = any(r.get("success") for r in ctx.tool_results)
        if trace:
            trace.done(success, detail=f"{ctx.iteration}轮, {len(ctx.tool_results)} 工具调用")
        return {"success": success, "confidence": ctx.confidence_total, "iterations": ctx.iteration,
                "result": {"tool_results": ctx.tool_results, "final_answer": ctx.final_answer},
                "error": ctx.last_error if not success else None}

    # ── 任务拆解 ───────────────────────────────────────────────────────

    async def _decompose_task(self, task: str, tool_defs: list = None) -> list:
        """先让 LLM 把任务拆成 3-5 个步骤"""
        prompt = f"""请将以下任务拆解为 3-5 个执行步骤，只需要输出步骤名称列表，每行一个。

任务：{task}

格式要求（只输出列表，不要其他内容）：
1. 步骤一名称
2. 步骤二名称
3. 步骤三名称"""
        try:
            response = await self._llm_call(prompt, tools=None)
            text = response
            if isinstance(response, dict):
                text = str(response)
            # 解析步骤列表
            lines = text.strip().split("\n")
            steps = []
            for line in lines:
                line = line.strip()
                # 去掉序号前缀 "1. "、"2、" 等
                cleaned = re.sub(r'^[\d]+[.、\)\s]+', '', line)
                # 去掉 markdown 列表标记 "- "、"* "
                cleaned = re.sub(r'^[-*\s]+', '', cleaned)
                if cleaned and len(cleaned) > 2 and not cleaned.startswith("```"):
                    steps.append(cleaned)
            if steps:
                logger.info(f"任务拆解为 {len(steps)} 步: {steps}")
                return steps[:8]
        except Exception as e:
            logger.debug(f"任务拆解失败: {e}")
        return []

    # ── ReAct 辅助 ────────────────────────────────────────────────────

    def _build_prompt(self, task, iteration, results, last_error=None, plan_steps=None, current_step=0, memory_log=None, rag_context=""):
        lines = [f"## 任务\n{task}\n"]

        # ── RAG 相关知识（首轮注入） ──
        if iteration == 1 and rag_context:
            lines.append(f"### 相关知识\n{rag_context}\n")

        # ── 历史记忆 ──
        if memory_log:
            lines.append("### 执行记录\n")
            for m in memory_log[-5:]:
                lines.append(f"- {m}\n")
            lines.append("")

        # 步骤进度
        if plan_steps:
            lines.append("### 执行计划\n")
            for i, s in enumerate(plan_steps):
                prefix = "→" if i == current_step else ("✓" if i < current_step else " ")
                lines.append(f"{prefix} {i+1}. {s}\n")
            lines.append("")

        if iteration == 1:
            lines.append("ReAct 模式：**Thought** → **Action**（调用工具）→ **Observation**\n"
                         "完成后输出：{\"reasoning\":\"...\",\"summary\":\"回复\",\"done\":true}\n")
        else:
            if results:
                for r in results[-4:]:
                    tc = r.get("tool_call", {}).get("name", "?")
                    ok = r.get("success", False)
                    status = "✓" if ok else "✗"
                    lines.append(f"[{status} {tc}]: {r.get('error','') or str(r.get('result',''))[:300]}\n")
            lines.append("继续推理。工具失败请换其他工具。完成后输出 done=true。\n")
        if last_error:
            lines.append(f"错误：{last_error}\n")
        return "\n".join(lines)

    async def _llm_call(self, prompt, tools=None):
        from core.engine.llm_backend import get_llm_router
        try:
            llm = get_llm_router()
            resp = await asyncio.wait_for(
                llm.chat([
                    {"role": "system", "content": "ReAct 智能体。调用工具完成任务。工具失败请换其他工具。完成后输出：{\"reasoning\":\"...\",\"summary\":\"回复\",\"done\":true}"},
                    {"role": "user", "content": prompt}],
                    temperature=0.3, max_tokens=2000, tools=tools),
                timeout=30)
            return resp
        except asyncio.TimeoutError:
            return '{"reasoning":"超时","done":true}'
        except Exception as e:
            return f'{{"reasoning":"错误","text":"{e}","done":true}}'

    def _parse_response(self, response) -> Dict:
        result = {"reasoning": "", "action": {}, "text": "", "done": False}
        try:
            parsed = json.loads(response) if isinstance(response, str) else response
            if isinstance(parsed, dict):
                for tc in parsed.get("tool_calls", []):
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    result["action"] = {"name": fn.get("name", ""), "arguments": json.loads(args) if isinstance(args, str) else args}
                    return result
                for ch in parsed.get("choices", []):
                    msg = ch.get("message", {})
                    for tc in msg.get("tool_calls", []):
                        fn = tc.get("function", {})
                        args = fn.get("arguments", "{}")
                        result["action"] = {"name": fn.get("name", ""), "arguments": json.loads(args) if isinstance(args, str) else args}
                        return result
                    content = msg.get("content", "")
                    if content:
                        inner = self._try_json(content)
                        if inner:
                            result["reasoning"] = inner.get("reasoning", "")
                            result["text"] = inner.get("text", inner.get("summary", ""))
                            result["done"] = inner.get("done", False)
                            result["plan_update"] = inner.get("plan_update", None)
                            return result
                        else:
                            # 纯文本 → 作为 text 返回，让外层处理
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
                result["plan_update"] = j.get("plan_update", None)
        if isinstance(response, str) and len(response) > 10:
            result["reasoning"] = response[:300]
            result["text"] = response
        return result

    def _try_json(self, text):
        try:
            return json.loads(text.strip())
        except Exception:
            pass
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
        """执行工具调用 — handler 优先 → MCP fallback"""
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
            handler = registry.get_handler(tool_name)
            if handler:
                try:
                    r = await handler(args)
                    results.append({"tool_call": tc, "success": True, "result": r})
                    if trace:
                        trace.on_tool_result(str(r)[:200])
                    continue
                except Exception as e:
                    logger.debug(f"handler {tool_name} 失败: {e}")
                    if trace:
                        trace.on_tool_error(f"handler 异常: {e}")
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
                                rt = await mcp_client.call_tool(srv, tool_name, args)
                                result = {"result": {"content": [{"text": rt}]}}
                                break
                        if result:
                            break
                if not result:
                    from core.mcp.awesome_mcp_manager import awesome_mcp_manager
                    for td in await awesome_mcp_manager.get_all_tool_definitions():
                        if td.get("function", {}).get("name") in (raw_name, tool_name):
                            result = await awesome_mcp_manager.call_tool_by_definition(td, args)
                            break
            except Exception:
                pass
            ok = result is not None
            results.append({"tool_call": tc, "success": ok, "result": result})
            if trace:
                (trace.on_tool_result if ok else trace.on_tool_error)(str(result)[:200] if ok else "调用失败")
        return results

    def __repr__(self):
        return f"BaseAgent(id={self.agent_id})"


class AgentFactory:
    """创建 Agent"""

    @staticmethod
    def create_agent(agent_type=AgentType.WORKER, agent_id=None, name=None, description="", **kwargs):
        from .work_agent import WorkAgent
        return WorkAgent(agent_id=agent_id, name=name or f"agent_{agent_id[:8] if agent_id else '?'}")

    @staticmethod
    def create_agent_from_role(role_type, agent_id=None, name=None, description=""):
        from .work_agent import WorkAgent
        return WorkAgent(agent_id=agent_id, name=name or role_type)

    @staticmethod
    def create_agents_for_task(keywords, min_count=2, max_count=5):
        from .work_agent import WorkAgent
        count = max(min_count, min(max_count, len(keywords) + 1))
        return [WorkAgent(agent_id=f"agent-{i}", name=f"worker_{i}") for i in range(count)]
