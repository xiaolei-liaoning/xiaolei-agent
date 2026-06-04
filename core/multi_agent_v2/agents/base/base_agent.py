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
            def _ok(t):
                if t.server == "__builtin__": return True  # builtin handler 全部可用
                return t.name in _HANDLER_MAP or t.handler is not None
            core_n = ["search","fetch_url","file","execute_code"]
            items = [{"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.parameters},
                      "_server":t.server,"_tool_name":t.tool_name} for t in raw if _ok(t)]
            core = [i for i in items if i["function"]["name"] in core_n]
            other = [i for i in items if i["function"]["name"] not in core_n]
            tool_defs = core + other[:20]
        except Exception:
            pass

        # 判断是否简单对话（无需工具），直接回复
        simple = len(task_description) < 30 and not any(kw in task_description for kw in
            ["搜索","查找","写","创建","生成","分析","报告","爬","保存","桌面","文件","数据","代码","游戏","脚本"])
        if simple:
            resp = await self._llm_call(task_description, None)
            step = self._parse_response(resp)
            answer = step.get("text","") or step.get("reasoning","")
            if trace: trace.done(True, detail="直接回答")
            return {"success":True,"result":{"tool_results":[],"final_answer":answer},"iterations":1}

        # 固定 3 步模板，每步标注工具
        steps = await self._decompose_task(task_description)
        if trace:
            trace.set_plan(steps)

        # 逐步骤执行（每步最多尝试 3 个工具）
        results = []
        prev_context = ""
        for step_idx, step_name in enumerate(steps or []):
            if trace:
                trace.on_tool_call("步骤%d" % (step_idx+1), step_name[:60])

            result_text = ""
            used_tool = ""
            attempt_tools = list(tool_defs)  # 每步从完整工具列表开始

            for attempt in range(3):
                prompt = "## 步骤 %d/%d\n%s\n\n完整任务：%s\n\n" % (step_idx+1, len(steps), step_name, task_description)
                if prev_context:
                    prompt += "已完成：%s\n\n" % prev_context[:800]
                if attempt == 0:
                    prompt += "选择最合适的工具执行此步骤。\n"
                elif attempt == 1:
                    prompt += "上一步工具失败。请换其他工具或方法。\n提示：如果网页获取失败，可以用 execute_code 写 Python 代码通过 requests 库抓取。\n"
                else:
                    prompt += "仍然失败。请换第三种方法或直接给出答案。\n提示：用 execute_code 执行 Python 代码可以完成绝大多数任务。\n"
                for td in attempt_tools:
                    prompt += "- %s: %s\n" % (td["function"]["name"], td["function"]["description"])

                response = await self._llm_call(prompt, attempt_tools)
                step = self._parse_response(response)
                action = step.get("action", {})
                text = step.get("text", "") or step.get("reasoning", "")

                if action and action.get("name"):
                    tn = action["name"]
                    used_tool = tn
                    tc = {"name": tn, "arguments": action.get("arguments", {}), "_tool_name": tn, "_server": ""}
                    r = await self._execute_single_tool_call(tc)
                    ok = r.get("success", False)
                    obs = self._extract_observation(r)
                    if trace:
                        (trace.on_tool_result if ok else trace.on_tool_error)(obs[:200] or "无结果")
                    if ok:
                        result_text = obs
                        break  # 成功后进入下一步
                    # 失败，排除这个工具再试
                    attempt_tools = [td for td in attempt_tools if td["function"]["name"] != tn]
                else:
                    result_text = text
                    if trace:
                        trace.on_tool_result(text[:200])
                    break  # LLM 直接回答了，接受

            if not result_text:
                result_text = "(步骤执行失败)"

            results.append({"step": step_name, "result": result_text, "tool_call": used_tool})
            prev_context += "\n步骤%d (%s): %s\n" % (step_idx+1, step_name, result_text[:200].replace("\n"," "))

        answer = "\n\n".join("步骤%d: %s" % (i+1, r["result"][:300]) for i, r in enumerate(results) if r.get("result"))
        if trace:
            trace.done(True, detail="%d 步完成" % len(results))
        return {"success": True, "result": {"tool_results": results, "final_answer": answer}, "iterations": len(results)}

    # ── 任务拆解 ───────────────────────────────────────────────────────

    async def _decompose_task(self, task: str) -> list:
        """固定 3 步拆解，标注工具"""
        prompt = "拆解任务为3个步骤。\n\n任务：%s\n\n可用工具：fetch_url(获取网页), execute_code(执行代码), file(文件)\n格式每行：工具:步骤\n示例：\nfetch_url:获取热搜数据\nexecute_code:分析数据\nfile:保存到桌面" % task
        try:
            response = await self._llm_call(prompt, tools=None)
            text = response if isinstance(response, str) else str(response)
            steps = []
            for line in text.strip().split("\n"):
                cl = re.sub(r'^[\d]+[.、\)\s]+', '', line.strip())
                cl = re.sub(r'^[-*\s]+', '', cl)
                if cl and len(cl) > 4 and not cl.startswith("```"):
                    steps.append(cl)
            return steps[:3]
        except:
            return ["获取数据", "分析处理", "输出结果"]

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
