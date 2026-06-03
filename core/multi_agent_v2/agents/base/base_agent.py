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

    # ── Subagent 分步执行 ─────────────────────────────────────────

    async def run(self, task_description: str, max_iterations: int = 10) -> Dict:
        """Subagent 分步执行：拆解 + 并行执行 + 汇总"""
        trace = self._trace
        from core.multi_agent_v2.agents.middleware import RunContext
        ctx = RunContext(task_description)
        ctx.trace = trace

        # 获取工具定义
        tool_defs = []
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry, _HANDLER_MAP
            reg = get_tool_registry()
            if not reg._initialized:
                await reg.discover_all()
            raw = reg.get_tools_for_task(task_description, max_tools=25)
            def _ok(t): return t.name in _HANDLER_MAP or t.handler or (t.server and t.server not in ("__skill__","__api__","__guidance__",""))
            core_n = ["fetch_url","file","execute_code","workspace_file"]
            items = [{"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.parameters},
                      "_server":t.server,"_tool_name":t.tool_name} for t in raw if _ok(t)]
            core = [i for i in items if i["function"]["name"] in core_n]
            other = [i for i in items if i["function"]["name"] not in core_n]
            tool_defs = core + other[:20]
        except Exception:
            pass

        # 任务拆解
        steps = await self._decompose_task(task_description, tool_defs)
        if trace:
            trace.set_plan(steps)

        if not steps:
            r = await self._execute_subagent(task_description, tool_defs, trace)
            return {"success":True,"result":{"tool_results":[],"final_answer":r},"iterations":1}

        # 分步执行（最多 3 并发）
        sem = asyncio.Semaphore(3)
        results = [None]*len(steps)

        async def run_step(i, step):
            async with sem:
                prompt = f"## 步骤 ({i+1}/{len(steps)})\n{step}\n\n完整任务：{task_description}\n\n请完成此步骤。可调用工具。完成后给出结果。"
                if trace: trace.on_tool_call(f"步骤{i+1}", step[:60])
                r = await self._execute_subagent(prompt, tool_defs, None)
                results[i] = {"step":step,"result":r}
                if trace: trace.on_tool_result(f"完成" if r else "无结果")

        await asyncio.gather(*[run_step(i,s) for i,s in enumerate(steps)])

        answer = "\n\n".join(f"步骤{i+1}: {r['result'][:300]}" for i,r in enumerate(results) if r)
        if trace: trace.done(True, detail=f"{len(steps)} 步完成")
        return {"success":True,"result":{"tool_results":results,"final_answer":answer},"iterations":len(steps)}

    async def _execute_subagent(self, prompt: str, tool_defs: list, trace) -> str:
        """单步 subagent：LLM 调用 + 可选工具调用 + 失败重试一次"""
        # 自动获取工具定义
        if not tool_defs:
            try:
                from core.multi_agent_v2.tools.tool_registry import get_tool_registry, _HANDLER_MAP
                reg = get_tool_registry()
                if not reg._initialized:
                    await reg.discover_all()
                raw = reg.get_tools_for_task(prompt, max_tools=25)
                tool_defs = [{"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.parameters},
                              "_server":t.server,"_tool_name":t.tool_name} for t in raw if t.name in _HANDLER_MAP or t.handler]
            except Exception:
                tool_defs = []

        try:
            resp = await self._llm_call(prompt, tool_defs)
        except Exception:
            return ""
        step = self._parse_response(resp)
        action = step.get("action", {})
        if action and action.get("name"):
            tn = action["name"]
            tc = {"name":tn,"arguments":action.get("arguments",{}),"_tool_name":tn,"_server":""}
            if trace: trace.on_tool_call(tn, tc["arguments"])
            r = await self._execute_single_tool_call(tc)
            if r.get("success"):
                obs = self._extract_observation(r)
                if trace: trace.on_tool_result(obs[:200])
                return obs
            # 失败重试一次
            retry = await self._llm_call(f"工具 {tn} 失败: {(r.get('result') or r.get('error',''))[:200]}\n\n原任务：{prompt}\n请换方法或直接给结果", tool_defs)
            step2 = self._parse_response(retry)
            a2 = step2.get("action",{})
            if a2 and a2.get("name"):
                tc2 = {"name":a2["name"],"arguments":a2.get("arguments",{}),"_tool_name":a2["name"],"_server":""}
                r2 = await self._execute_single_tool_call(tc2)
                if r2.get("success"): return self._extract_observation(r2)
            return step2.get("text","") or step2.get("reasoning","")[:500]
        return step.get("text","") or step.get("reasoning","")[:500]

    # ── 任务拆解 + ReAct 辅助 ─────────────────────────────────────────

    async def _decompose_task(self, task: str, tool_defs: list = None) -> list:
        """先让 LLM 把任务拆成 3-5 个步骤"""
        prompt = f"""拆分任务为3-5个步骤，每行一个步骤名（不要序号）：

{task}

示例：
获取数据
分析数据
生成报告"""
        try:
            response = await self._llm_call(prompt, tools=None)
            text = response
            if isinstance(response, dict):
                text = str(response)
            lines = text.strip().split("\n")
            steps = []
            for line in lines:
                line = line.strip()
                cleaned = re.sub(r'^[\d]+[.、\)\s]+', '', line)
                cleaned = re.sub(r'^[-*\s]+', '', cleaned)
                if cleaned and len(cleaned) > 2 and not cleaned.startswith("```"):
                    steps.append(cleaned)
            return steps[:8]
        except Exception as e:
            logger.debug(f"任务拆解失败: {e}")
        return []

    async def _llm_call(self, prompt, tools=None):
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
                         "完成后输出：{\"reasoning\":\"...\",\"summary\":\"回复\",\"done\":true}\n"
                         "如需调整计划：{\"plan_update\":[\"新步骤1\",\"新步骤2\",...]}\n")
        else:
            if results:
                for r in results[-4:]:
                    tc = r.get("tool_call", {}).get("name", "?")
                    lines.append(f"[{tc}]: {r.get('error','') or str(r.get('result',''))[:300]}\n")
            lines.append("继续推理。可按需用 plan_update 调整后续步骤。完成后输出 done=true。\n")
        if last_error:
            lines.append(f"错误：{last_error}\n")
        return "\n".join(lines)

    async def _llm_call(self, prompt, tools=None):
        from core.engine.llm_backend import get_llm_router
        try:
            llm = get_llm_router()
            resp = await asyncio.wait_for(
                llm.chat([
                    {"role": "system", "content": "ReAct 智能体。调用工具完成任务。可按需调整计划。输出格式：完成时 {\"reasoning\":\"...\",\"summary\":\"回复\",\"done\":true}；调整计划时 {\"plan_update\":[\"新步骤1\",\"新步骤2\",...]}"},
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
