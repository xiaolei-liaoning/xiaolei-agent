#!/usr/bin/env python3
"""智能多Agent系统 - V1 架构（队长-队员模式）+ V2 ToolRegistry 集成

V1 角色分工型多 Agent：
- 1 个 LeaderAgent（队长）+ N 个 WorkerAgent（队员）
- 队长分解任务、分配子任务、分析 Worker 结果、动态规划
- 队员只负责执行具体子任务（含工具调用能力）
- 分批模式：队长分配一批 → 并行执行 → 队长分析 → 循环

V2 ToolRegistry 集成：
- 队员可使用 16+ 内置工具 + MCP 工具
- 工具调用为单步模式（非 ReAct 循环）
- 队员执行时：LLM 决定调用哪个工具 → 执行工具 → 返回结果
"""

import asyncio
import json
import re
import time
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

logger = logging.getLogger(__name__)


def _get_llm_router():
    """懒加载 LLM router，避免模块级导入触发 LLM 后端初始化"""
    from core.engine.llm_backend import get_llm_router
    return get_llm_router()


# =============================================================================
# 数据模型
# =============================================================================

class AgentRole(Enum):
    LEADER = "队长"
    WORKER = "队员"







@dataclass
class AgentMessage:
    from_agent: str
    content: str
    timestamp: float = None
    message_type: str = "task"

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


# =============================================================================
# LLM 工具函数
# =============================================================================

_llm_semaphore = asyncio.Semaphore(3)  # 限制最多 3 个并发 LLM 调用，替代全局串行锁


async def _llm_json(system_prompt: str, user_message: str, max_tokens: int = 800) -> dict:
    """调用 LLM 并返回解析后的 JSON（含 1 次重试）"""
    last_error = None
    for attempt in range(2):  # 原始 + 1 次重试
        try:
            router = _get_llm_router()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            async with _llm_semaphore:
                response = await router.chat(messages, temperature=0.7, max_tokens=max_tokens)
            cleaned = (response or "").strip().strip("```json").strip("```").strip()
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_error = str(e)
            if attempt == 0:
                logger.warning(f"LLM JSON 解析失败，重试中: {e}")
                user_message += f"\n\n（注意：上次返回的 JSON 格式无效，错误: {e}。请确保只输出有效 JSON。）"
            else:
                logger.warning(f"LLM JSON 解析重试仍失败: {e}")
        except Exception as e:
            logger.warning(f"LLM 调用/解析失败: {e}/{e.__class__.__name__}")
            last_error = str(e)
            if attempt == 0:
                user_message += f"\n\n（注意：上次 LLM 调用失败: {e}。请重试。）"
                continue
    logger.warning(f"LLM JSON 解析最终失败: {last_error}")
    return {}


# =============================================================================
# 提示词模板
# =============================================================================

SYSTEM_PROMPT_TEMPLATE = """你是一个{role}Agent。你的职责是{description}。

对于给定的任务，你需要：
1. 分析任务的目标和要求
2. 直接执行任务，生成完整的实际内容（如写故事就写出完整故事，分析数据就给出详细分析）
3. 将执行结果放在 result 字段中（必须是实际交付内容，不是状态描述）

⚠️ 重要：你必须直接完成任务并输出结果，而不是描述你将如何做。例如"写一个故事"→ 直接写出完整故事；"分析数据"→ 直接给出分析结论。

{extra_context}

输出格式（JSON，不要包含其他内容）：
{output_format}"""

OUTPUT_FORMATS = {
    "decompose": """{"task": "原始任务","subtasks": [...],"estimated_steps": 数字,"strategy": "策略"}""",
    "execute": """{"status": "success/failed","result": "执行结果","details": {...}}""",
    "research": """{"topic": "主题","findings": [...],"summary": "总结"}""",
    "analyze": """{"analysis_type": "类型","key_insights": [...],"recommendations": [...],"confidence": 0-1}""",
    "review": """{"review_score": 0-100,"passed": true/false,"comments": "意见","suggestions": [...]}""",
    "reflect": """{"analysis": "原因","suggestion": "改进","should_retry": true/false}""",
    "kepa_decision": """{"decision": "continue/retry/fail","confidence": 0-1,"reason": "原因"}""",
    "leader_analyze": """{"decision": "complete/retry/reassign","confidence": 0-1,"reason": "原因","retry_tasks": [...],"needed_count": 数字}""",
}


# =============================================================================
# ContextMemory — 任务级上下文
# =============================================================================

class ContextMemory:
    """简单的上下文记忆（任务级）"""

    def __init__(self):
        self.entries: List[str] = []

    def add(self, entry: str) -> None:
        self.entries.append(entry)
        if len(self.entries) > 20:
            self.entries = self.entries[-20:]

    def get_recent(self, n: int = 5) -> str:
        return "\n".join(self.entries[-n:]) if self.entries else "（无上下文）"


# =============================================================================
# LLMAgent — 统一 Agent 基类（含 KEPA + RAG + 反问 + 上下文）
# =============================================================================

class LLMAgent:
    """统一 LLM Agent — KEPA + RAG + 反问 + 上下文 + 工具调用 + 消息总线"""

    def __init__(self, name: str, role: AgentRole, tool_registry=None):
        self.name = name
        self.role = role
        self.status = "idle"
        self.context = ContextMemory()
        self.tool_registry = tool_registry  # V2 ToolRegistry 引用
        self._tool_cache = None  # 缓存的工具列表
        self._tool_cache_time = 0  # 缓存时间戳（用于TTL）
        self._task_id = None  # 当前任务 ID
        
        # Worker 状态
        self.state = "idle"
        self.current_task = None  # 当前执行的任务
        self.last_result = None  # 上一次执行结果
        self.leader_name = None  # 所属主Agent名称（用于询问）

    def _get_role_config(self) -> tuple:
        configs = {
            AgentRole.LEADER: ("队长", "负责任务拆解、分配、监管 Worker 执行、分析结果并动态规划", "decompose"),
            AgentRole.WORKER: ("队员", "负责执行队长分配的具体任务", "execute"),
        }
        return configs.get(self.role, ("通用", "处理各类任务", "execute"))

    @staticmethod
    async def _do_rag_query(query: str) -> str:
        """RAG 检索增强 — 共享实现（V1和V2复用）"""
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

    # ─── Worker 状态机方法 ───────────────────────────────────────────

    def _update_state(self, new_state: str, reason: str = "") -> None:
        """更新 Worker 状态"""
        old_state = self.state
        self.state = new_state
        self.status = new_state
        logger.debug(f"🔄 {self.name} 状态变更: {old_state} → {new_state} ({reason})")

    async def _execute_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """执行单个工具调用"""
        if not self.tool_registry:
            return {"success": False, "error": "工具注册表未初始化"}
        
        handler = self.tool_registry.get_handler(tool_name)
        if not handler:
            return {"success": False, "error": f"未找到工具: {tool_name}"}
        
        try:
            # 设置超时
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
        """获取任务相关的工具定义（用于 LLM 函数调用），缓存 TTL 300 秒"""
        if not self.tool_registry:
            return []

        now = time.time()
        cache_ttl = 300
        # 缓存有效则直接返回
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
        """KEPA 反思闭环 — think→act→reflect 循环"""
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
            reflection = await _llm_json(
                reflect_system,
                reflect_prompt,
                max_tokens=300,
            )

            decision = reflection.get("decision", "continue")
            confidence = reflection.get("confidence", 0.0)

            if decision == "fail":
                result["success"] = False
                result["error"] = reflection.get("reason", "KEPA 判断失败")
                result["kepa_iterations"] = attempt + 1
                return result

            if decision != "retry" and confidence >= 0.85:
                result["confidence"] = confidence
                result["kepa_iterations"] = attempt + 1
                return result

            # retry
            logger.info(f"🔄 {self.name} KEPA 重试 #{attempt + 1}: {reflection.get('reason', '')[:60]}")
            result["retry_reason"] = reflection.get("reason", "")

        result["success"] = False
        result["error"] = f"KEPA 超过最大重试 {max_retries} 次"
        result["kepa_iterations"] = max_retries
        return result

    async def process_message(self, message: AgentMessage) -> str:
        self.context.add(f"收到: {message.content[:100]}")
        logger.info(f"📬 {self.name} 收到消息 from {message.from_agent}")
        
        # 设置任务 ID
        self._task_id = f"{message.from_agent}_{int(time.time())}"
        
        # 更新状态为执行中
        self.current_task = message.content[:200]
        self._update_state("executing", f"收到任务: {message.content[:50]}")
        
        # 执行任务（带重试机制）
        max_retries = 2
        for attempt in range(max_retries + 1):
            result = await self._handle_message(message)
            
            # 解析结果
            try:
                result_data = json.loads(result) if isinstance(result, str) else result
            except json.JSONDecodeError:
                result_data = {"status": "completed", "message": result}
            
            # 检查是否成功
            if result_data.get("success", True) and result_data.get("status") != "failed":
                # 成功
                self._update_state("completed", "任务完成")
                self.last_result = result_data
                break
            
            # 失败，记录错误（不再通过消息总线询问）
            if attempt < max_retries:
                error = result_data.get("error", "未知错误")
                self._update_state("failed", f"失败: {error[:50]}")
            
            # 重试
            self._update_state("retrying", f"尝试 {attempt + 1}/{max_retries + 1}")
        
        self.context.add(f"回复: {str(result)[:100]}")
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    async def _handle_message(self, message: AgentMessage) -> str:
        """处理消息 — ReAct 循环（Think→Act→Observe→循环）"""
        role, desc, fmt_type = self._get_role_config()
        output_format = OUTPUT_FORMATS.get(fmt_type, OUTPUT_FORMATS["execute"])

        # RAG 检索
        rag_context = await self._do_rag_query(message.content)

        extra_context = ""
        if rag_context:
            extra_context += f"\n【知识库参考】\n{rag_context}\n"
        recent_ctx = self.context.get_recent()
        if recent_ctx != "（无上下文）":
            extra_context += f"\n【上下文】\n{recent_ctx}\n"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            role=role, description=desc, extra_context=extra_context,
            output_format=output_format
        )

        # 构建对话历史（ReAct 循环用）
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"任务内容:\n{message.content}"},
        ]

        tools = await self._get_tools_for_task(message.content)
        max_react_rounds = 3  # ponytail: 3 rounds 够了，5 轮容易过度执行
        result = {}

        for round_num in range(max_react_rounds):
            # LLM 调用（带完整对话历史）
            result = await self._llm_with_tools_from_conversation(conversation, tools)

            if not result:
                return json.dumps({"status": "failed", "error": "LLM 调用失败"}, ensure_ascii=False)

            # 无工具调用 → LLM 直接回答，循环结束
            tool_calls = result.get("tool_calls", [])
            if not tool_calls:
                break

            # 执行工具
            tool_results = await self._execute_tool_calls(tool_calls)

            # 把工具结果回传到对话历史，让下一轮 LLM 能看到
            self._append_tool_round(conversation, tool_calls, tool_results)

            result["tool_results"] = tool_results
            logger.info(f"🔧 {self.name} 第 {round_num + 1} 轮: {len(tool_calls)} 个工具执行完成")

        # 基于最终工具结果生成答案
        tool_results = result.get("tool_results", [])
        if tool_results:
            result = await self._process_tool_results(result, tool_results, message.content)

        # KEPA 反思闭环
        kepa_result = await self._kepa_reflect(result)

        if not kepa_result.get("success", True):
            logger.warning(f"⚠️ {self.name} KEPA 判定失败: {kepa_result.get('error', '')}")
            return json.dumps({
                "status": "failed",
                "success": False,
                "error": kepa_result.get("error", "KEPA 判定失败"),
            }, ensure_ascii=False)

        return json.dumps(kepa_result, ensure_ascii=False)

    def _append_tool_round(self, conversation: List[Dict], tool_calls: List[Dict], tool_results: List[Dict]) -> None:
        """把工具调用和结果追加到对话历史，供下一轮 LLM 使用"""
        # assistant 的工具调用
        assistant_msg = {"role": "assistant", "content": None, "tool_calls": [
            {"id": tc.get("id", f"call_{i}"), "type": "function",
             "function": {"name": tc.get("name", ""), "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False)}}
            for i, tc in enumerate(tool_calls)
        ]}
        conversation.append(assistant_msg)

        # 每个工具的结果
        for tc, tr in zip(tool_calls, tool_results):
            res = tr.get("result", {})
            if isinstance(res, dict):
                content = res.get("content", res.get("text", res.get("result", str(res))))
            else:
                content = str(res) if res else tr.get("error", "工具执行失败")
            conversation.append({
                "role": "tool",
                "tool_call_id": tc.get("id", "call_0"),
                "content": str(content)[:2000],  # ponytail: 截断防溢出
            })

    async def _llm_with_tools_from_conversation(self, conversation: List[Dict], tools: List[Dict]) -> dict:
        """使用完整对话历史调用 LLM（支持工具调用）"""
        try:
            router = _get_llm_router()
            async with _llm_semaphore:
                response = await router.chat(
                    conversation,
                    temperature=0.7,
                    max_tokens=1000,
                    tools=tools if tools else None,
                )

            # 统一返回 dict，展平 choices 格式
            if isinstance(response, str):
                try:
                    parsed = json.loads(response)
                    if isinstance(parsed, dict):
                        response = parsed
                except (json.JSONDecodeError, TypeError):
                    return {"content": response, "tool_calls": []}
            if isinstance(response, dict):
                # OpenAI choices 格式 → 展平
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

    @staticmethod
    def _extract_tool_calls_from_text(text: str) -> dict:
        """从文本中提取工具调用（备用方案）"""
        import re
        result = {"tool_calls": []}
        write_match = re.search(r'write_file\s*\(\s*path\s*=\s*["\']([^"\']+)["\']\s*,\s*content\s*=\s*["\'](.+?)["\']\s*\)', text, re.DOTALL)
        if write_match:
            result["tool_calls"].append({"name": "write_file", "arguments": {"path": write_match.group(1), "content": write_match.group(2)}})
        python_match = re.search(r'execute_python\s*\(\s*code\s*=\s*["\'](.+?)["\']\s*\)', text, re.DOTALL)
        if python_match:
            result["tool_calls"].append({"name": "execute_python", "arguments": {"code": python_match.group(1)}})
        return result

    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """执行多个工具调用（并行）"""

        def _normalize(tc: Dict) -> Dict:
            """展平 OpenAI 格式 tool_calls → 扁平格式"""
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

        results = []
        
        async def _run_one(tc: Dict) -> Dict:
            flat = _normalize(tc)
            name = flat["name"]
            args = flat["arguments"]
            result = await self._execute_tool(name, args)
            result["tool_call"] = tc
            return result
        
        # 并行执行所有工具调用
        tasks = [_run_one(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        final_results = []
        for i, item in enumerate(results):
            if isinstance(item, Exception):
                final_results.append({
                    "success": False,
                    "error": str(item),
                    "tool_call": tool_calls[i]
                })
            else:
                final_results.append(item)
        
        return final_results

    async def _process_tool_results(self, result: dict, tool_results: List[Dict], task: str) -> dict:
        """处理工具结果，生成最终答案"""
        # 提取成功的工具结果
        successful_results = [r for r in tool_results if r.get("success")]
        
        if not successful_results:
            result["status"] = "failed"
            result["error"] = "所有工具调用失败"
            return result
        
        # 基于工具结果生成最终答案
        result_summary = []
        for r in successful_results:
            tc = r.get("tool_call", {})
            res = r.get("result", {})
            if isinstance(res, dict):
                content = res.get("content", res.get("text", res.get("result", str(res))))
            else:
                content = str(res)
            result_summary.append(f"[{tc.get('name', '?')}] {content[:500]}")
        
        result["tool_result_summary"] = "\n".join(result_summary)
        result["status"] = "success"
        return result

    async def execute_with_context(self, task_content: str, from_agent: str = "系统") -> str:
        """对外执行接口 — 自动管理 context"""
        msg = AgentMessage(from_agent=from_agent, content=task_content)
        return await self.process_message(msg)


# =============================================================================
# LeaderAgent — 队长 Agent（监管 Worker、分析结果、动态规划）
# =============================================================================

class LeaderAgent(LLMAgent):
    """队长 Agent — 在 LLMAgent 基础上增加监管 Worker、分析结果、动态规划"""

    def __init__(self, name: str, max_workers: int = 5, tool_registry=None):
        super().__init__(name=name, role=AgentRole.LEADER, tool_registry=tool_registry)
        self.workers: Dict[str, LLMAgent] = {}
        self.max_workers = max_workers
        self.active_worker_count = 3
        self.worker_states: Dict[str, str] = {}  # 跟踪Worker状态

    async def supervise_task(self, task_description: str, workers: List[LLMAgent],
                             active_count: int = 3, max_rounds: int = 10) -> Dict:
        """队长 ReAct 主循环：Thought → Action → Observation → 循环/完成

        ReAct 模式核心：
        1. Thought: 分析当前状态，决定下一步行动
        2. Action: 执行工具调用或分配子任务给 Worker
        3. Observation: 观察执行结果
        4. 循环直到任务完成或达到最大轮次

        Args:
            task_description: 任务描述
            workers: Worker Agent 列表（全部槽位）
            active_count: 本轮活跃 Worker 数
            max_rounds: 最大循环轮次（ReAct 默认10轮）

        Returns:
            执行结果字典
        """
        self.active_worker_count = min(active_count, len(workers))
        self.workers = {w.name: w for w in workers}

        logger.info(f"🚀 队长 {self.name} 开始 ReAct 执行任务: {task_description}")

        # 初始化 ReAct 状态
        all_results = []
        context_history = []  # 记录每轮的 Thought/Action/Observation
        round_num = 0

        # 为Worker设置主Agent名称
        for w in workers:
            w.leader_name = self.name

        while round_num < max_rounds:
            round_num += 1
            logger.info(f"🔄 ReAct 第 {round_num} 轮")

            # ========== Thought: 队长思考 ==========
            thought = await self._react_think(
                task_description, context_history, all_results, round_num
            )
            
            # 检查是否任务完成
            if thought.get("done"):
                logger.info(f"✅ ReAct 第 {round_num} 轮: 队长判定任务完成")
                # 将最终结果添加到 all_results
                if thought.get("final_result"):
                    all_results.append({
                        "success": True,
                        "result": {"result": thought.get("final_result")},
                        "worker": self.name,
                        "task": "最终结果"
                    })
                elif not all_results:
                    # 如果没有子任务结果，添加一个空结果
                    all_results.append({
                        "success": True,
                        "result": {"result": thought.get("thinking", "任务完成")},
                        "worker": self.name,
                        "task": "最终结果"
                    })
                break

            # ========== Action: 执行行动 ==========
            action = thought.get("action", {})
            action_type = action.get("type", "unknown")
            
            action_result = await self._react_act(
                action_type, action, workers, task_description, context_history
            )
            
            # ========== Observation: 观察结果 ==========
            observation = {
                "round": round_num,
                "thought": thought.get("thinking", ""),
                "action_type": action_type,
                "action": action,
                "result": action_result,
            }
            context_history.append(observation)
            
            if action_result.get("success"):
                all_results.append(action_result)
            
            logger.info(f"👁️ ReAct 第 {round_num} 轮观察: {action_type} - {'成功' if action_result.get('success') else '失败'}")

        success = len(all_results) > 0 and all(r.get("success") for r in all_results)
        
        # 统计子任务总数（支持批量分配的嵌套结构）
        total_subtasks = 0
        for r in all_results:
            result_data = r.get("result", {})
            if isinstance(result_data, dict) and "batch_results" in result_data:
                total_subtasks += len(result_data["batch_results"])
            else:
                total_subtasks += 1
        
        logger.info(f"{'✅' if success else '❌'} ReAct 任务完成: 共 {round_num} 轮, {total_subtasks} 个子任务")

        return {
            "success": success,
            "results": all_results,
            "rounds": round_num,
            "total_subtasks": total_subtasks,
            "react_history": context_history,
        }

    async def _react_think(self, task_description: str, history: List[Dict],
                           results: List[Dict], round_num: int) -> Dict:
        """ReAct Thought 阶段：分析状态，决定下一步"""

        history_text = ""
        if history:
            history_lines = []
            for h in history[-3:]:
                history_lines.append(
                    f"轮次{h['round']}: 思考={h['thought'][:100]}, "
                    f"行动={h['action_type']}, 结果={'成功' if h['result'].get('success') else '失败'}"
                )
            history_text = "\n".join(history_lines)

        results_text = ""
        if results:
            results_text = f"\n已完成 {len(results)} 个子任务"

        # 根据任务类型提供工具提示
        tool_hints = ""
        task_lower = task_description.lower()
        if any(kw in task_lower for kw in ["天气", "气温", "温度"]):
            tool_hints = "\n【提示】天气任务 → 用 tool action 调用 skill_execute(weather)"
        elif any(kw in task_lower for kw in ["搜索", "爬取", "热搜", "百度", "微博", "知乎"]):
            tool_hints = "\n【提示】搜索任务 → 用 tool action 调用 web_search"
        elif any(kw in task_lower for kw in ["翻译", "translate"]):
            tool_hints = "\n【提示】翻译任务 → 用 tool action 调用 skill_execute(translator)"
        elif any(kw in task_lower for kw in ["写", "创建", "保存", "文件"]):
            tool_hints = "\n【提示】文件任务 → 用 tool action 调用 write_file"
        elif any(kw in task_lower for kw in ["执行", "运行", "代码", "python"]):
            tool_hints = "\n【提示】代码任务 → 用 tool action 调用 execute_python"

        system = (
            "你是队长Agent，使用 ReAct 模式执行任务。\n\n"
            "你的职责是分析任务、决策行动、分配子任务给 Worker 执行。\n"
            "Worker 会帮你执行工具调用（搜索、写文件、运行代码等）。\n\n"
            "输出下一步行动的 JSON：\n\n"
            "选项1 - 分配单个子任务给Worker（推荐！大多数任务用这个）:\n"
            '{"done": false, "thinking": "分析...", "action": {"type": "delegate", "task": "子任务描述，要具体可执行"}}\n\n'
            "选项2 - 批量分配子任务给多个Worker并行执行:\n"
            '{"done": false, "thinking": "分析...", "action": {"type": "batch_delegate", "tasks": ["子任务1", "子任务2"]}}\n\n'
            "选项3 - 处理前一轮的batch_delegate结果:\n"
            '{"done": false, "thinking": "基于上一轮结果...", "action": {"type": "process_results", "task": "综合分析并生成报告"}}\n\n'
            "选项4 - 调用工具（仅当任务非常简单、不需要Worker时）:\n"
            '{"done": false, "thinking": "分析...", "action": {"type": "tool", "tool_name": "工具名", "args": {...}}}\n\n'
            "选项5 - 任务完成:\n"
            '{"done": true, "thinking": "任务已完成..."}\n\n'
            "决策指南（重要！）:\n"
            "- 需要搜索+写文件等多步操作 → batch_delegate 或 delegate\n"
            "- 涉及多个独立步骤 → batch_delegate\n"
            "- 单个明确子任务 → delegate\n"
            "- 只需一个简单操作（如查天气）→ tool\n\n"
            "输出纯JSON，不要其他内容。"
        )

        user = f"任务: {task_description}\n\n历史:\n{history_text or '无'}\n\n{results_text}\n\n第{round_num}轮，请思考下一步："

        result = await _llm_json(system, user, max_tokens=500)

        if not result or not isinstance(result, dict):
            return {"done": True, "thinking": "LLM 响应异常，结束任务"}

        return result

    async def _react_act(self, action_type: str, action: Dict, 
                         workers: List[LLMAgent], original_task: str,
                         context_history: List[Dict] = None) -> Dict:
        """ReAct Action 阶段：执行具体行动"""
        
        if action_type == "tool":
            # 直接调用工具
            tool_name = action.get("tool_name", "")
            args = action.get("args", {})
            
            if not tool_name:
                return {"success": False, "error": "未指定工具名称"}
            
            result = await self._execute_tool(tool_name, args)
            return result

        elif action_type == "delegate":
            # 分配子任务给 Worker
            task = action.get("task", original_task)
            if not task:
                return {"success": False, "error": "未指定子任务"}
            
            # 选择第一个空闲 Worker
            worker = workers[0] if workers else None
            if not worker:
                return {"success": False, "error": "无可用 Worker"}
            
            msg = AgentMessage(
                from_agent=self.name,
                content=task,
                message_type="task",
            )
            result_str = await worker.process_message(msg)
            
            try:
                data = json.loads(result_str)
                is_ok = data.get("success", True) is True and data.get("status") != "failed"
            except Exception:
                data = {"raw": result_str[:500]}
                is_ok = False
            
            return {
                "success": is_ok,
                "result": data,
                "worker": worker.name,
            }

        elif action_type == "batch_delegate":
            # 批量分配子任务给多个 Worker 并行执行
            tasks = action.get("tasks", [])
            if not tasks:
                # 如果没有提供任务列表，则分解原始任务
                tasks = await self._decompose_task(original_task)
            
            if not tasks:
                return {"success": False, "error": "无可用子任务"}
            
            # 使用轮询分配子任务给 Worker
            active_workers = workers[:self.active_worker_count]
            assignments = self._assign(tasks, active_workers)
            
            # 并行执行所有子任务
            batch_results = await self._execute_batch(assignments, workers)
            
            # 统计成功数量
            success_count = sum(1 for r in batch_results if r.get("success"))
            
            # 有成功结果 → 直接返回，跳过 LLM 分析（ponytail: 省一轮 LLM 调用）
            if success_count > 0:
                # 提取成功结果的内容
                result_parts = []
                for r in batch_results:
                    if r.get("success"):
                        data = r.get("result", {})
                        content = data.get("content", "")
                        if content:
                            result_parts.append(content)
                
                return {
                    "success": True,
                    "result": {
                        "content": "\n\n".join(result_parts) if result_parts else json.dumps(batch_results, ensure_ascii=False)[:500],
                        "batch_results": batch_results,
                        "success_count": success_count,
                        "total_count": len(batch_results),
                    },
                    "workers": [r.get("worker") for r in batch_results],
                }
            
            # 全部失败 → 分析原因
            analysis = await self._analyze_results(batch_results, original_task, 1)
            
            return {
                "success": False,
                "result": {
                    "batch_results": batch_results,
                    "analysis": analysis,
                    "success_count": 0,
                    "total_count": len(batch_results),
                },
                "workers": [r.get("worker") for r in batch_results],
            }

        elif action_type == "process_results":
            # 处理前一轮的batch_delegate结果（并发→串行的关键环节）
            # 从context_history中获取上一轮的batch_results
            prev_results = []
            for h in reversed(context_history):
                if h.get("action_type") == "batch_delegate" and h.get("result", {}).get("success"):
                    prev_results = h["result"].get("result", {}).get("batch_results", [])
                    break
            
            if not prev_results:
                return {"success": False, "error": "没有找到可处理的前一轮结果"}
            
            # 提取任务描述（从action中获取，或使用原始任务）
            process_task = action.get("task", f"综合分析以下结果并生成报告：{original_task}")
            
            # 将前一轮结果作为上下文传递给Worker
            result_context = "\n".join([
                f"结果{i+1}: {r.get('result', {}).get('raw', str(r.get('result', '')))[:200]}"
                for i, r in enumerate(prev_results[:5])  # 限制数量避免上下文过长
            ])
            
            enhanced_task = f"{process_task}\n\n【需要处理的结果】\n{result_context}"
            
            # 选择第一个空闲 Worker 串行处理
            worker = workers[0] if workers else None
            if not worker:
                return {"success": False, "error": "无可用 Worker"}
            
            msg = AgentMessage(
                from_agent=self.name,
                content=enhanced_task,
                message_type="task",
            )
            result_str = await worker.process_message(msg)
            
            try:
                data = json.loads(result_str)
                is_ok = data.get("success", True) is True and data.get("status") != "failed"
            except Exception:
                data = {"raw": result_str[:500]}
                is_ok = False
            
            return {
                "success": is_ok,
                "result": data,
                "worker": worker.name,
                "processed_count": len(prev_results),
            }

        else:
            return {"success": False, f"error": f"未知的行动类型: {action_type}"}

    async def _decompose_task(self, task_description: str) -> List[str]:
        """用 LLM 将任务分解为子任务列表"""
        system = (
            "你是队长Agent。负责将复杂任务分解为多个独立的子任务，每个子任务可以并行执行。\n\n"
            "输出JSON格式:\n"
            f"{OUTPUT_FORMATS['decompose']}"
        )
        user = f"请将以下任务分解为{self.active_worker_count}个左右的子任务：\n{task_description}\n\n注意：不要输出JSON外的其他内容。"

        rag_context = await self._do_rag_query(task_description)
        if rag_context:
            user = f"请参考知识库信息后，将以下任务分解为{self.active_worker_count}个左右的子任务：\n\n【知识库参考】\n{rag_context}\n\n【原始任务】\n{task_description}\n\n注意：不要输出JSON外的其他内容。"

        result = await _llm_json(system, user, max_tokens=800)
        raw_subtasks = result.get("subtasks", [])
        subtasks = [s for s in raw_subtasks if isinstance(s, str)]
        if not subtasks:
            # 降级：直接返回原任务作为唯一子任务
            return [task_description]

        return subtasks[:self.max_workers]

    def _assign(self, tasks: List[str], active_workers: List[LLMAgent]) -> List[Dict]:
        """分配子任务给空闲 Worker"""
        assignments = []
        for i, task in enumerate(tasks):
            worker = active_workers[i % len(active_workers)]
            assignments.append({
                "worker": worker,
                "task": task,
                "index": i,
            })
        return assignments

    async def _execute_batch(self, assignments: List[Dict], all_workers: List[LLMAgent]) -> List[Dict]:
        """并行执行一批子任务"""
        
        async def _run_one(assignment: Dict) -> Dict:
            worker = assignment["worker"]
            task_content = assignment["task"]
            
            msg = AgentMessage(
                from_agent=self.name,
                content=task_content,
                message_type="task",
            )
            result_str = await worker.process_message(msg)
            try:
                data = json.loads(result_str)
                is_ok = data.get("success", True) is True and data.get("status") != "failed"
            except Exception as e:
                data = {"raw": result_str[:200], "error": str(e)}
                is_ok = False
            
            return {
                "worker": worker.name,
                "task": task_content,
                "success": is_ok,
                "result": data,
            }

        batch = await asyncio.gather(*[_run_one(a) for a in assignments], return_exceptions=True)
        results = []
        for item in batch:
            if isinstance(item, Exception):
                results.append({"success": False, "error": str(item), "worker": "unknown", "task": "", "result": {"error": str(item)}})
            else:
                results.append(item)
        
        return results

    async def _analyze_results(self, batch_results: List[Dict], original_task: str, round_num: int) -> Dict:
        """用 LLM 分析 Worker 执行结果，决定下一步"""
        summary_lines = []
        for r in batch_results:
            status = "✅" if r.get("success", False) else "❌"
            summary_lines.append(f"{status} Worker {r.get('worker', '?')}: {json.dumps(r.get('result', {}), ensure_ascii=False)[:500]}")
        
        system = (
            "你是队长Agent。你的职责是分析队员(Worker)的执行结果。\n\n"
            "输出JSON:\n"
            f"{OUTPUT_FORMATS['leader_analyze']}\n\n"
            "decision 含义：\n"
            "- complete: 所有结果满意，任务完成\n"
            "- retry: 部分结果不满意，需要重试（在 retry_tasks 中列出需要重试的任务）\n"
            "- reassign: 需要更多 Worker 并重试部分任务"
        )
        user = (
            f"原始任务: {original_task}\n"
            f"第 {round_num} 轮执行结果:\n"
            + "\n".join(summary_lines)
        )

        result = await _llm_json(system, user, max_tokens=500)

        if not result:
            # LLM 失败，保守策略：再试一次
            return {"decision": "retry", "confidence": 0.0, "reason": "LLM 分析失败，保守重试"}

        return result


# =============================================================================
# V1LeaderPool — 队长模式 Agent 池
# =============================================================================

class V1LeaderPool:
    """队长模式 Agent 池 — 1 个队长 + 最多 max_workers 个 Worker（支持池化复用）"""

    def __init__(self):
        self._all_agents: Dict[str, LLMAgent] = {}
        self._tool_registry = None
        # Worker 池化管理
        self._worker_pool: List[LLMAgent] = []  # 空闲Worker池
        self._busy_workers: Dict[str, LLMAgent] = {}  # 忙碌中的Worker
        self._pool_lock = asyncio.Lock()  # 池操作锁

    async def _ensure_tool_registry(self):
        """确保工具注册表已初始化（工具发现由 V2 ReActCoreMiddleware.on_start 负责）"""
        if self._tool_registry is None:
            try:
                from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                self._tool_registry = get_tool_registry()
                await self._tool_registry.discover_all()
                # 更新已有 Worker/Leader 的 tool_registry
                for agent in self._all_agents.values():
                    if agent.tool_registry is None:
                        agent.tool_registry = self._tool_registry
            except Exception as e:
                logger.warning(f"初始化工具注册表失败: {e}")
                self._tool_registry = None

    async def create_team(self, worker_count: int = 3, max_workers: int = 5) -> tuple:
        """创建 1 队长 + 最多 max_workers 个 Worker（默认激活 worker_count 个）

        Returns:
            (LeaderAgent, List[LLMAgent]) — 队长 + 全部 Worker 列表
        """
        await self._ensure_tool_registry()
        team_id = uuid4().hex[:8]
        leader = LeaderAgent(
            name=f"队长_{team_id}",
            max_workers=max_workers,
            tool_registry=self._tool_registry,
        )
        self._all_agents[leader.name] = leader

        workers = []
        for i in range(max_workers):
            w = LLMAgent(
                name=f"队员{i+1}_{team_id}",
                role=AgentRole.WORKER,
                tool_registry=self._tool_registry,
            )
            self._all_agents[w.name] = w
            workers.append(w)

        leader.workers = {w.name: w for w in workers}
        leader.active_worker_count = min(worker_count, max_workers)

        logger.info(f"👥 创建队伍: 1 队长 + {worker_count}/{max_workers} Worker (队长={leader.name})")
        return leader, workers

    async def share_memory(self, agents: List[LLMAgent]) -> None:
        """共享记忆 — 已禁用（消息总线已移除）"""
        # ponytail: comm_center removed
        pass

    # ─── Worker 池化管理 ──────────────────────────────────────────────

    async def get_worker(self, leader_name: str = None) -> Optional[LLMAgent]:
        """从池中获取一个空闲Worker
        
        Args:
            leader_name: 主Agent名称（用于设置Worker的leader_name）
        
        Returns:
            空闲Worker，或 None（池空且无法创建新Worker）
        """
        await self._ensure_tool_registry()
        async with self._pool_lock:
            # 优先从池中获取
            if self._worker_pool:
                worker = self._worker_pool.pop()
                worker._update_state("idle", "从池中取出")
                if leader_name:
                    worker.leader_name = leader_name
                self._busy_workers[worker.name] = worker
                logger.debug(f"📦 从池中取出 Worker: {worker.name}")
                return worker
            
            # 池空，尝试创建新Worker
            if len(self._busy_workers) < 10:  # 最多10个Worker
                team_id = uuid4().hex[:8]
                worker = LLMAgent(
                    name=f"队员_{team_id}",
                    role=AgentRole.WORKER,
                    tool_registry=self._tool_registry,
                )
                if leader_name:
                    worker.leader_name = leader_name
                
                self._all_agents[worker.name] = worker
                self._busy_workers[worker.name] = worker
                logger.debug(f"✨ 创建新 Worker: {worker.name}")
                return worker
            
            logger.warning("Worker池已满，无法获取更多Worker")
            return None

    async def return_worker(self, worker: LLMAgent) -> None:
        """将Worker归还到池中（任务完成后）
        
        Args:
            worker: 要归还的Worker
        """
        async with self._pool_lock:
            # 从忙碌列表移除
            self._busy_workers.pop(worker.name, None)
            
            # 重置Worker状态
            worker._update_state("idle", "任务完成归还池")
            worker.current_task = None
            worker.last_result = None
            
            # 放回池中
            if worker not in self._worker_pool:
                self._worker_pool.append(worker)
                logger.debug(f"📦 Worker 归还池: {worker.name}")


    async def discard(self, agents: List[LLMAgent]) -> None:
        """清理 Agent — Worker放回池中，Leader注销
        
        注意：Worker不会被删除，而是放回池中以供复用。
        只有Leader会被完全清理。
        """
        for agent in agents:
            if agent.role == AgentRole.LEADER:
                # Leader 直接清理
                self._all_agents.pop(agent.name, None)
                logger.debug(f"V1LeaderPool: 清理 Leader {agent.name}")
            else:
                # Worker 放回池中
                await self.return_worker(agent)
                logger.debug(f"V1LeaderPool: Worker {agent.name} 归还池")

    def get_agent(self, name: str) -> Optional[LLMAgent]:
        return self._all_agents.get(name)

    def get_all_agents(self) -> List[LLMAgent]:
        return list(self._all_agents.values())
