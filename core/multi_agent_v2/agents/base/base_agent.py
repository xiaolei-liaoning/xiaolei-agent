"""BaseAgent — Agent 基类

设计：Agent = LLM + Tools
run() 分步执行：拆解 → 逐步骤串行执行 → 汇总
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
        from .models import Thought
        return Thought(reasoning=f"任务: {task.description}", plan=[], confidence=0.5)

    async def act(self, plan: list = None, tool_calls: list = None) -> "ActionResult":
        from .models import ActionResult
        if tool_calls:
            results = await self._execute_tool_calls(tool_calls)
            ok = any(r.get("success") for r in results)
            return ActionResult(success=ok, output=results)
        return ActionResult(success=True, output=[])

    async def reflect(self, result: "ActionResult") -> "Reflection":
        from .models import Reflection
        return Reflection(success=result.success, lessons_learned=[], improvements=[], performance_metrics={})

    async def execute(self, task: Task) -> "ActionResult":
        return await self.act(plan=[task.description])

    # ── 分步执行 ─────────────────────────────────────────────────────

    async def run(self, task_description: str, max_iterations: int = 10) -> Dict:
        """分步执行：拆解 → 逐步骤(LLM+工具) → 汇总"""
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

        # 逐步骤执行
        results = []
        prev_context = ""
        for step_idx, step_name in enumerate(steps or []):
            if trace:
                trace.on_tool_call("步骤%d" % (step_idx+1), step_name[:60])

            prompt = "## 当前步骤 (%d/%d)\n%s\n\n完整任务：%s\n\n" % (step_idx+1, len(steps), step_name, task_description)
            if prev_context:
                prompt += "### 已完成步骤的结果\n%s\n\n" % prev_context[:1000]
            prompt += "请执行此步骤。完成后输出结果。如需调用工具，直接调用。"

            response = await self._llm_call(prompt, tool_defs)
            step = self._parse_response(response)
            action = step.get("action", {})
            text = step.get("text", "") or step.get("reasoning", "")
            result_text = ""

            if action and action.get("name"):
                tn = action["name"]
                tc = {"name": tn, "arguments": action.get("arguments", {}), "_tool_name": tn, "_server": ""}
                r = await self._execute_single_tool_call(tc)
                ok = r.get("success", False)
                obs = self._extract_observation(r)
                if trace:
                    (trace.on_tool_result if ok else trace.on_tool_error)(obs[:200])
                if ok:
                    result_text = obs
                    # 工具成功后从列表移除，防止后续步骤重复调用
                    tool_defs = [td for td in tool_defs if td.get("function", {}).get("name") != tn]
                else:
                    retry = await self._llm_call("工具失败，请直接给出 %s 的结果" % step_name, tool_defs)
                    s2 = self._parse_response(retry)
                    result_text = s2.get("text", "") or s2.get("reasoning", "")[:500]
                    if trace:
                        trace.on_tool_result(result_text[:200] if result_text else "(无结果)")
            else:
                result_text = text
                if trace:
                    trace.on_tool_result(result_text[:200])

            results.append({"step": step_name, "result": result_text, "tool_call": action.get("name", "")})
            summary = result_text[:200].replace("\n", " ").strip() if result_text else step_name
            prev_context += "\n步骤%d (%s): %s\n" % (step_idx+1, step_name, summary)

        answer = "\n\n".join("步骤%d: %s" % (i+1, r["result"][:300]) for i, r in enumerate(results) if r.get("result"))
        if trace:
            trace.done(True, detail="%d 步完成" % len(results))
        return {"success": True, "result": {"tool_results": results, "final_answer": answer}, "iterations": len(results)}

    # ── 任务拆解 ───────────────────────────────────────────────────────

    async def _decompose_task(self, task: str, tool_defs: list = None) -> list:
        prompt = "请将以下任务拆解为 3-5 个执行步骤，每行一个步骤名（不要序号）：\n\n%s\n\n示例：\n获取数据\n分析数据\n生成报告" % task
        try:
            response = await self._llm_call(prompt, tools=None)
            text = response if isinstance(response, str) else str(response)
            steps = []
            for line in text.strip().split("\n"):
                line = line.strip()
                cl = re.sub(r'^[\d]+[.、\)\s]+', '', line)
                cl = re.sub(r'^[-*\s]+', '', cl)
                if cl and len(cl) > 2 and not cl.startswith("```"):
                    steps.append(cl)
            return steps[:8]
        except Exception as e:
            logger.debug("任务拆解失败: %s" % e)
        return []

    # ── LLM 调用 ───────────────────────────────────────────────────────

    async def _llm_call(self, prompt, tools=None):
        from core.engine.llm_backend import get_llm_router
        try:
            llm = get_llm_router()
            resp = await asyncio.wait_for(
                llm.chat([
                    {"role": "system", "content": "ReAct 智能体。调用工具完成任务。完成时输出：{\"reasoning\":\"...\",\"summary\":\"回复\",\"done\":true}"},
                    {"role": "user", "content": prompt}],
                    temperature=0.3, max_tokens=2000, tools=tools),
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
                            for k in ("reasoning","text","summary","done","plan_update"):
                                v = inner.get(k)
                                if v is not None:
                                    result[k] = v
                            return result
                        else:
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
            handler = registry.get_handler(tool_name)
            if handler:
                try:
                    r = await handler(args)
                    results.append({"tool_call": tc, "success": True, "result": r})
                    if trace:
                        trace.on_tool_result(str(r)[:200])
                    continue
                except Exception as e:
                    logger.debug("handler %s 失败: %s" % (tool_name, e))
                    if trace:
                        trace.on_tool_error("handler 异常: %s" % e)
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
                (trace.on_tool_result if ok else trace.on_tool_error)(str(result)[:200] if result else "调用失败")
        return results

    def __repr__(self):
        return "BaseAgent(id=%s)" % self.agent_id


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
