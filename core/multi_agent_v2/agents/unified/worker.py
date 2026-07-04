"""V1 LLMAgent — 队员 Agent（KEPA + RAG + 工具调用）"""

import asyncio
import json
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from .context_memory import ContextMemory
from .prompts import (
    SYSTEM_PROMPT_TEMPLATE, OUTPUT_FORMATS,
    llm_json, get_llm_router_safe,
)

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    LEADER = "队长"
    WORKER = "队员"


class AgentMessage:
    """跨 Agent 消息"""

    def __init__(self, from_agent: str, content: str,
                 timestamp: float = None, message_type: str = "task"):
        self.from_agent = from_agent
        self.content = content
        self.timestamp = timestamp or time.time()
        self.message_type = message_type


class LLMAgent:
    """统一 LLM Agent — KEPA + RAG + 反问 + 上下文 + 工具调用"""

    def __init__(self, name: str, role: AgentRole, tool_registry=None,
                 role_prompt: str = "", tool_restrictions: Optional[List[str]] = None):
        self.name = name
        self.role = role
        self.status = "idle"
        self.context = ContextMemory()
        self.tool_registry = tool_registry
        self.role_prompt = role_prompt
        self.tool_restrictions = tool_restrictions
        self._tool_cache = None
        self._tool_cache_time = 0
        self._task_id = None

        self.state = "idle"
        self.current_task = None
        self.last_result = None
        self.leader_name = None

        self.user_id: str = ""
        self._stm = None
        self._vm = None

    @property
    def vm(self):
        if self._vm is None:
            try:
                from core.memory.vector_memory import VectorMemoryStore
                self._vm = VectorMemoryStore()
            except Exception as e:
                logger.debug(f"VectorMemory init failed: {e}")
                self._vm = False
        return self._vm if self._vm else None

    @property
    def stm(self):
        if self._stm is None and self.user_id:
            from core.memory.short_term_memory import get_memory_manager
            self._stm = get_memory_manager()
        return self._stm

    def _get_role_config(self) -> tuple:
        configs = {
            AgentRole.LEADER: ("队长", "负责任务拆解、分配、监管 Worker 执行、分析结果并动态规划", "decompose"),
            AgentRole.WORKER: ("队员", "负责执行队长分配的具体任务", "execute"),
        }
        return configs.get(self.role, ("通用", "处理各类任务", "execute"))

    @staticmethod
    async def _do_rag_query(query: str) -> str:
        try:
            from core.search.rag_search_engine import RAGSearchEngine
            engine = RAGSearchEngine()
            result = await asyncio.wait_for(
                engine.search_and_learn(query, max_results=3, learn=False, use_query_cache=True),
                timeout=5,
            )
            items = result.get("results", result.get("items", []))
            if items:
                return "\n".join(
                    f"- {r.get('content', r.get('text', ''))[:200]}"
                    for r in items if r
                )
        except asyncio.TimeoutError:
            logger.debug(f"RAG 检索超时: {query[:30]}")
        except Exception as e:
            logger.debug(f"RAG 检索失败: {e}")
        return ""

    def _update_state(self, new_state: str, reason: str = "") -> None:
        old_state = self.state
        self.state = new_state
        self.status = new_state
        logger.debug(f"{self.name} 状态变更: {old_state} → {new_state} ({reason})")

    async def _execute_tool(self, tool_name: str, arguments: Dict) -> Dict:
        if not self.tool_registry:
            return {"success": False, "error": "工具注册表未初始化"}

        if self.tool_restrictions is not None and tool_name not in self.tool_restrictions:
            return {"success": False, "error": f"工具 {tool_name} 不在角色白名单中（可用: {self.tool_restrictions}）"}

        handler = self.tool_registry.get_handler(tool_name)
        if not handler:
            return {"success": False, "error": f"未找到工具: {tool_name}"}

        try:
            timeout = 30
            if tool_name in ("fetch_url", "rag_search"):
                timeout = 45
            elif tool_name in ("execute_python", "execute_shell"):
                timeout = 25

            result = await asyncio.wait_for(handler(arguments), timeout=timeout)
            return {"success": True, "result": result}
        except asyncio.TimeoutError:
            return {"success": False, "error": f"工具 {tool_name} 执行超时"}
        except Exception as e:
            return {"success": False, "error": f"工具 {tool_name} 执行失败: {str(e)}"}

    async def _get_tools_for_task(self, task: str) -> List[Dict]:
        if not self.tool_registry:
            return []

        now = time.time()
        cache_ttl = 300
        if self._tool_cache is not None and (now - self._tool_cache_time) < cache_ttl:
            return self._tool_cache

        try:
            tools = await self.tool_registry.get_tools_for_task(task, max_tools=15)
            self._tool_cache = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                }
                for t in tools
            ]
            self._tool_cache_time = time.time()
        except Exception as e:
            logger.debug(f"获取工具列表失败: {e}")
            if self._tool_cache is None:
                self._tool_cache = []

        return self._tool_cache

    async def _kepa_reflect(self, result: dict, max_retries: int = 3) -> dict:
        for attempt in range(max_retries):
            KEPA_SYSTEM_PROMPT = (
                "你是{role}Agent。\n\n"
                "评估以下执行结果的置信度（0-1），决定继续执行/重试/标记失败。\n\n"
                "输出JSON:\n{format}"
            )
            reflect_system = KEPA_SYSTEM_PROMPT.format(
                role=self.role.value,
                format=OUTPUT_FORMATS['kepa_decision'],
            )
            reflect_prompt = f"评估以下执行结果的置信度（0-1），决定继续/重试/失败：\n{json.dumps(result, ensure_ascii=False)}"
            reflection = await llm_json(reflect_system, reflect_prompt, max_tokens=300)

            decision = reflection.get("decision", "continue")
            confidence = reflection.get("confidence", 0.0)

            if decision == "fail":
                result["success"] = False
                result["error"] = reflection.get("reason", "KEPA 判断失败")
                result["kepa_iterations"] = attempt + 1
                return result

            if confidence >= 0.85:
                result["confidence"] = confidence
                result["kepa_iterations"] = attempt + 1
                return result

            if decision != "retry":
                result["confidence"] = confidence
                result["kepa_iterations"] = attempt + 1
                return result

            logger.info(f"{self.name} KEPA 重试 #{attempt + 1}: {reflection.get('reason', '')[:60]}")
            result["retry_reason"] = reflection.get("reason", "")

        result["success"] = False
        result["error"] = f"KEPA 超过最大重试 {max_retries} 次"
        result["kepa_iterations"] = max_retries
        return result

    async def process_message(self, message: AgentMessage) -> str:
        self.context.add(f"收到: {message.content[:100]}")
        logger.info(f"{self.name} 收到消息 from {message.from_agent}")

        if self.stm and self.user_id:
            try:
                self.stm.add(self.user_id, "user", message.content)
            except Exception as e:
                logger.debug(f"STM add user failed: {e}")

        self._task_id = f"{message.from_agent}_{int(time.time())}"
        self.current_task = message.content[:200]
        self._update_state("executing", f"收到任务: {message.content[:50]}")

        max_retries = 2
        for attempt in range(max_retries + 1):
            result = await self._handle_message(message)

            try:
                result_data = json.loads(result) if isinstance(result, str) else result
            except json.JSONDecodeError:
                result_data = {"status": "completed", "message": result}

            if result_data.get("success", True) and result_data.get("status") != "failed":
                self._update_state("completed", "任务完成")
                self.last_result = result_data
                break

            if attempt < max_retries:
                error = result_data.get("error", "未知错误")
                self._update_state("failed", f"失败: {error[:50]}")

            self._update_state("retrying", f"尝试 {attempt + 1}/{max_retries + 1}")

        self.context.add(f"回复: {str(result)[:100]}")

        if self.stm and self.user_id:
            try:
                self.stm.add(self.user_id, "assistant", str(result)[:2000])
            except Exception as e:
                logger.debug(f"STM add assistant failed: {e}")

        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    async def _handle_message(self, message: AgentMessage) -> str:
        role, default_desc, fmt_type = self._get_role_config()
        desc = self.role_prompt or default_desc
        output_format = OUTPUT_FORMATS.get(fmt_type, OUTPUT_FORMATS["execute"])

        rag_context = await self._do_rag_query(message.content)
        _rag_hit = bool(rag_context)

        extra_context = ""
        if rag_context:
            extra_context += f"\n【知识库参考】\n{rag_context}\n"

        stm_context = ""
        if self.stm and self.user_id:
            try:
                ctx_msgs = self.stm.get_context(self.user_id)
                if ctx_msgs:
                    stm_context = "\n".join(
                        f"[{m['role']}] {m['content'][:300]}"
                        for m in ctx_msgs[-5:]
                    )
                    extra_context += f"\n【历史对话】\n{stm_context}\n"
            except Exception as e:
                logger.debug(f"STM get_context failed: {e}")
        if not stm_context:
            recent_ctx = self.context.get_recent()
            if recent_ctx != "（无上下文）":
                extra_context += f"\n【上下文】\n{recent_ctx}\n"

        tools = await self._get_tools_for_task(message.content)

        if _rag_hit and tools:
            _search_tools = {"rag_search", "web_search", "fetch_url"}
            before = len(tools)
            tools = [t for t in tools if t.get("function", {}).get("name") not in _search_tools]
            if len(tools) < before:
                extra_context += "\n【注意】知识库已包含相关信息，请直接用知识回答，无需搜索。\n"

        has_write = any("write_file" in str(t) for t in tools) if tools else False
        file_tip = ""
        if has_write:
            file_tip = "🔧 你有 write_file 工具可以创建/写入文件。如果任务要求「保存到桌面」或「生成报告」，请用 write_file 把结果写入 ~/Desktop/。\n"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            role=role, description=desc, extra_context=extra_context,
            file_tip=file_tip, output_format=output_format
        )

        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"任务内容:\n{message.content}"},
        ]

        try:
            from core.memory.context_compactor import get_compactor
            compactor = get_compactor()
            compactor.update_assistant_timestamp()
            conversation = compactor.compact(conversation)
        except Exception:
            pass

        _WORKER_MAX_ROUNDS = 8
        max_react_rounds = _WORKER_MAX_ROUNDS
        result = {}
        all_tool_results = []

        for round_num in range(max_react_rounds):
            result = await self._llm_with_tools_from_conversation(conversation, tools)

            if not result:
                return json.dumps({"status": "failed", "error": "LLM 调用失败"}, ensure_ascii=False)

            tool_calls = result.get("tool_calls", [])
            if not tool_calls:
                break

            tool_results = await self._execute_tool_calls(tool_calls)
            self._append_tool_round(conversation, tool_calls, tool_results)

            all_tool_results.extend(tool_results)
            logger.info(f"{self.name} 第 {round_num + 1} 轮: {len(tool_calls)} 个工具执行完成")

        if all_tool_results and not result.get("content", ""):
            _summarize_prompt = (
                "任务: " + message.content[:200] +
                "\n\n你已通过工具获取了数据，请基于已有数据生成最终回答，不要再调用工具。"
            )
            conversation.append({"role": "user", "content": _summarize_prompt})
            result = await self._llm_with_tools_from_conversation(conversation, tools=None)

        if all_tool_results:
            result = await self._process_tool_results(result, all_tool_results, message.content)

        kepa_result = await self._kepa_reflect(result)

        if not kepa_result.get("success", True):
            logger.warning(f"{self.name} KEPA 判定失败: {kepa_result.get('error', '')}")
            return json.dumps({
                "status": "failed", "success": False,
                "error": kepa_result.get("error", "KEPA 判定失败"),
            }, ensure_ascii=False)

        if self.role == AgentRole.WORKER and self.vm and self.user_id:
            asyncio.ensure_future(self._store_knowledge(message.content, kepa_result))

        return json.dumps(kepa_result, ensure_ascii=False)

    def _append_tool_round(self, conversation: List[Dict], tool_calls: List[Dict],
                           tool_results: List[Dict]) -> None:
        assistant_msg = {"role": "assistant", "content": None, "tool_calls": [
            {"id": tc.get("id", f"call_{i}"), "type": "function",
             "function": {"name": tc.get("name", ""),
                          "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False)}}
            for i, tc in enumerate(tool_calls)
        ]}
        conversation.append(assistant_msg)

        for tc, tr in zip(tool_calls, tool_results):
            res = tr.get("result", {})
            if isinstance(res, dict):
                if "ok" in res:
                    content = str(res.get("data", str(res)))
                else:
                    content = str(res.get("content", res.get("text", res.get("result", str(res)))))
            else:
                content = str(res) if res else tr.get("error", "工具执行失败")
            conversation.append({
                "role": "tool",
                "tool_call_id": tc.get("id", "call_0"),
                "content": str(content)[:1000],
            })

    async def _llm_with_tools_from_conversation(self, conversation: List[Dict],
                                                  tools: List[Dict]) -> dict:
        try:
            router = get_llm_router_safe()
            async with asyncio.Semaphore(3):
                response = await router.chat(
                    conversation,
                    temperature=0.7,
                    max_tokens=8000,
                    tools=tools if tools else None,
                )

            if isinstance(response, str):
                try:
                    parsed = json.loads(response)
                    if isinstance(parsed, dict):
                        response = parsed
                except (json.JSONDecodeError, TypeError):
                    return {"content": response, "tool_calls": []}
            if isinstance(response, dict):
                if "choices" in response and response["choices"]:
                    msg = response["choices"][0].get("message", {})
                    return {
                        "content": msg.get("content", ""),
                        "tool_calls": msg.get("tool_calls", []),
                    }
                return response
            if response is None:
                return {}
            return {"content": str(response), "tool_calls": []}
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            return {}

    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        def _normalize(tc: Dict) -> Dict:
            if "function" in tc and isinstance(tc["function"], dict):
                func = tc["function"]
                args = func.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                return {"name": func.get("name", ""), "arguments": args}
            return {"name": tc.get("name", ""), "arguments": tc.get("arguments", {})}

        async def _run_one(tc: Dict) -> Dict:
            flat = _normalize(tc)
            name = flat["name"]
            args = flat["arguments"]
            result = await self._execute_tool(name, args)
            result["tool_call"] = tc
            return result

        tasks = [_run_one(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final_results = []
        for i, item in enumerate(results):
            if isinstance(item, Exception):
                final_results.append({
                    "success": False, "error": str(item),
                    "tool_call": tool_calls[i]
                })
            else:
                final_results.append(item)

        return final_results

    async def _process_tool_results(self, result: dict, tool_results: List[Dict],
                                      task: str) -> dict:
        successful_results = [r for r in tool_results if r.get("success")]

        if not successful_results:
            result["status"] = "failed"
            result["error"] = "所有工具调用失败"
            return result

        result_summary = []
        seen = set()
        for r in successful_results:
            tc = r.get("tool_call", {})
            res = r.get("result", {})
            if isinstance(res, dict):
                if "ok" in res:
                    content = str(res.get("data", str(res)))
                else:
                    content = str(res.get("content", res.get("text", res.get("result", str(res)))))
            else:
                content = str(res)
            tc_name = tc.get("name", "")
            if not tc_name and isinstance(tc.get("function"), dict):
                tc_name = tc["function"].get("name", "?")
            dedup_key = f"{tc_name}:{str(content)[:30]}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            result_summary.append(f"[{tc_name}] {content[:500]}")

        result["tool_result_summary"] = "\n".join(result_summary)
        result["status"] = "success"
        return result

    async def execute_with_context(self, task_content: str, from_agent: str = "系统") -> str:
        msg = AgentMessage(from_agent=from_agent, content=task_content)
        return await self.process_message(msg)

    async def _store_knowledge(self, task: str, result: dict) -> None:
        if not result.get("success", True):
            return
        kw = ["搜索", "查找", "调研", "分析", "摘要", "总结", "翻译", "热搜", "查询", "对比"]
        if not any(k in task for k in kw):
            return
        if not self.vm or not self.user_id:
            return
        result_text = result.get("result", "")
        if isinstance(result_text, dict):
            result_text = result_text.get("result", result_text.get("content", str(result_text)[:500]))
        content = f"【任务】{task[:100]}\n【结果】{str(result_text)[:500]}"
        try:
            self.vm.add_memory(
                user_id=self.user_id, content=content, category="fact",
                metadata={"source": task[:60], "agent": self.name},
            )
        except Exception as e:
            logger.debug(f"写入知识失败: {e}")
