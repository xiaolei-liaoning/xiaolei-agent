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
import time
import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
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


class TaskStatus(Enum):
    PENDING = "待执行"
    IN_PROGRESS = "执行中"
    COMPLETED = "已完成"
    FAILED = "失败"
    REFLECTING = "反思中"


class WorkerState(Enum):
    """Worker 状态机"""
    IDLE = "idle"              # 空闲，等待任务
    EXECUTING = "executing"    # 正在执行任务
    COMPLETED = "completed"    # 任务完成，等待主Agent确认
    FAILED = "failed"          # 执行失败，等待主Agent指示
    ASKING = "asking"          # 正在询问主Agent
    RETRYING = "retrying"      # 重试中


# 消息类型常量
class MessageType:
    TASK_ASSIGN = "task_assign"          # 主Agent分配任务给Worker
    TASK_RESULT = "task_result"          # Worker返回任务结果
    ASK_LEADER = "ask_leader"            # Worker询问主Agent
    LEADER_RESPONSE = "leader_response"  # 主Agent回复Worker
    CONTROL = "control"                  # 主Agent发送控制指令（停止/重试/调整）
    STATUS_UPDATE = "status_update"      # Worker状态更新
    PROGRESS = "progress"                # 进度汇报


@dataclass
class Task:
    id: str
    name: str
    description: str
    status: TaskStatus
    priority: int
    assignee: Optional[str] = None
    subtasks: List['Task'] = None
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if self.subtasks is None:
            self.subtasks = []


@dataclass
class AgentMessage:
    from_agent: str
    to_agent: str
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

    def clear(self) -> None:
        self.entries.clear()


# =============================================================================
# LLMAgent — 统一 Agent 基类（含 KEPA + RAG + 反问 + 上下文）
# =============================================================================

class LLMAgent:
    """统一 LLM Agent — KEPA + RAG + 反问 + 上下文 + 工具调用 + 消息总线"""

    def __init__(self, name: str, role: AgentRole, tool_registry=None, comm_center=None):
        self.name = name
        self.role = role
        self.status = "idle"
        self.context = ContextMemory()
        self.tool_registry = tool_registry  # V2 ToolRegistry 引用
        self.comm_center = comm_center  # 通信中心引用
        self._tool_cache = None  # 缓存的工具列表
        self._tool_cache_time = 0  # 缓存时间戳（用于TTL）
        self._task_id = None  # 当前任务 ID
        
        # Worker 状态机
        self.state = WorkerState.IDLE
        self.state_history = []  # 状态变更历史
        self.current_task = None  # 当前执行的任务
        self.last_result = None  # 上一次执行结果
        self.leader_name = None  # 所属主Agent名称（用于询问）
        self._ask_future = None  # 用于等待主Agent回复的Future

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
            result = await engine.search_and_learn(query, max_results=3, learn=False, use_query_cache=True)
            items = result.get("results", result.get("items", []))
            if items:
                return "\n".join(
                    f"- {r.get('content', r.get('text', ''))[:200]}"
                    for r in items if r
                )
        except Exception as e:
            logger.debug(f"RAG 检索失败: {e}")
        return ""

    async def _ask_user(self, question: str, timeout: int = 30) -> Optional[str]:
        """反问用户 — 降级前征求意见"""
        try:
            from core.agents.agent_communication import get_question_registry
            future = get_question_registry().ask(
                agent_id=self.name,
                agent_name=self.name,
                question=question,
                timeout=timeout,
            )
            return await asyncio.wait_for(future, timeout=timeout + 5)
        except ImportError:
            return None
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.debug(f"反问失败: {e}")
            return None

    # ─── Worker 状态机方法 ───────────────────────────────────────────

    def _update_state(self, new_state: WorkerState, reason: str = "") -> None:
        """更新 Worker 状态"""
        old_state = self.state
        self.state = new_state
        self.status = new_state.value
        self.state_history.append({
            "from": old_state.value,
            "to": new_state.value,
            "reason": reason,
            "timestamp": time.time(),
        })
        logger.debug(f"🔄 {self.name} 状态变更: {old_state.value} → {new_state.value} ({reason})")

    async def _report_status(self) -> None:
        """向主Agent报告状态更新"""
        if not self.leader_name:
            return
        status_msg = {
            "type": MessageType.STATUS_UPDATE,
            "worker": self.name,
            "state": self.state.value,
            "current_task": self.current_task,
            "last_result": self.last_result,
        }
        await self.send_message(self.leader_name, status_msg, MessageType.STATUS_UPDATE)

    # ─── Worker 询问主Agent 机制 ──────────────────────────────────────

    async def ask_leader(self, question: str, context: Dict = None, timeout: int = 30) -> Optional[Dict]:
        """询问主Agent，等待回复
        
        Args:
            question: 问题描述
            context: 附加上下文（如失败原因、当前状态等）
            timeout: 超时时间（秒）
        
        Returns:
            主Agent的回复字典，或 None（超时）
        """
        if not self.leader_name:
            logger.warning(f"{self.name}: 未设置主Agent名称，无法询问")
            return None
        
        self._update_state(WorkerState.ASKING, f"询问主Agent: {question[:50]}")
        
        # 构建询问消息
        ask_msg = {
            "type": MessageType.ASK_LEADER,
            "worker": self.name,
            "question": question,
            "context": context or {},
            "current_task": self.current_task,
            "timestamp": time.time(),
        }
        
        # 发送询问
        self._ask_future = asyncio.get_event_loop().create_future()
        await self.send_message(self.leader_name, ask_msg, MessageType.ASK_LEADER)
        
        try:
            # 等待主Agent回复
            response = await asyncio.wait_for(self._ask_future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning(f"{self.name}: 等待主Agent回复超时")
            self._ask_future = None
            return None
        finally:
            self._ask_future = None

    def handle_leader_response(self, response: Dict) -> None:
        """处理主Agent的回复"""
        if self._ask_future and not self._ask_future.done():
            self._ask_future.set_result(response)
            logger.debug(f"{self.name}: 收到主Agent回复")

    async def on_task_failed(self, error: str, can_retry: bool = True) -> Optional[Dict]:
        """任务执行失败时，询问主Agent是否重试/放弃/更换策略
        
        Args:
            error: 错误信息
            can_retry: 是否可以重试
        
        Returns:
            主Agent的指示
        """
        self._update_state(WorkerState.FAILED, f"失败: {error[:50]}")
        
        question = f"任务执行失败: {error}"
        if can_retry:
            question += "\n是否重试？"
        
        context = {
            "error": error,
            "can_retry": can_retry,
            "task": self.current_task,
        }
        
        response = await self.ask_leader(question, context)
        
        if response:
            action = response.get("action", "retry")
            if action == "retry":
                self._update_state(WorkerState.RETRYING, "主Agent指示重试")
            elif action == "skip":
                self._update_state(WorkerState.COMPLETED, "主Agent指示跳过")
            elif action == "abort":
                self._update_state(WorkerState.IDLE, "主Agent指示中止")
            return response
        
        # 超时默认重试
        self._update_state(WorkerState.RETRYING, "超时默认重试")
        return {"action": "retry", "reason": "超时默认重试"}

    # ─── 消息总线方法 ───────────────────────────────────────────

    async def send_message(self, receiver: str, content: Any, msg_type: str = "task") -> str:
        """发送直接消息到指定 Agent"""
        if not self.comm_center:
            logger.debug(f"{self.name}: 通信中心未初始化，无法发送消息")
            return ""
        return await self.comm_center.send_direct(
            sender=self.name,
            receiver=receiver,
            content=content,
            message_type=msg_type,
        )

    async def publish(self, topic: str, content: Any) -> None:
        """发布消息到主题"""
        if not self.comm_center:
            return
        await self.comm_center.publish(topic, {"content": content, "sender": self.name}, sender=self.name)

    async def publish_progress(self, progress: str, task_id: str = "") -> None:
        """发布进度更新"""
        tid = task_id or self._task_id or "unknown"
        await self.publish(f"task:progress:{tid}", {
            "agent": self.name,
            "progress": progress,
            "task_id": tid,
        })

    async def store_knowledge(self, key: str, data: Any, tags: Optional[set] = None) -> None:
        """存储知识到共享知识库"""
        if not self.comm_center:
            return
        await self.comm_center.store_knowledge(
            key=key,
            data=data,
            tags=tags or set(),
            source=self.name,
            summary=str(data)[:200],
        )

    async def search_knowledge(self, tag: str) -> Dict[str, Any]:
        """按标签搜索共享知识"""
        if not self.comm_center:
            return {}
        return await self.comm_center.search_knowledge(tag)

    async def receive_messages(self, timeout: float = 0.1) -> List[dict]:
        """接收待处理消息"""
        if not self.comm_center:
            return []
        return await self.comm_center.receive_all_messages(self.name)

    def on_message_received(self, message: dict) -> None:
        """消息接收回调（可被子类覆盖）"""
        msg_type = message.get("message_type", "?")
        sender = message.get("sender", "?")
        logger.debug(f"{self.name} 收到消息: {msg_type} from {sender}")
        
        # 处理主Agent的回复
        if msg_type == MessageType.LEADER_RESPONSE:
            content = message.get("content", {})
            if isinstance(content, dict) and content.get("type") == MessageType.LEADER_RESPONSE:
                self.handle_leader_response(content)
                return
        
        # 处理控制指令
        if msg_type == MessageType.CONTROL:
            content = message.get("content", {})
            if isinstance(content, dict):
                self._handle_control_message(content)

    def _handle_control_message(self, content: Dict) -> None:
        """处理来自主Agent的控制指令"""
        action = content.get("action", "")
        logger.info(f"🎛️ {self.name} 收到控制指令: {action}")
        
        if action == "stop":
            # 停止当前任务
            self._update_state(WorkerState.IDLE, "主Agent指示停止")
        elif action == "retry":
            # 重试当前任务
            self._update_state(WorkerState.RETRYING, "主Agent指示重试")
        elif action == "adjust":
            # 调整任务参数
            new_params = content.get("params", {})
            if new_params:
                self.current_task = new_params.get("task", self.current_task)
                self._update_state(WorkerState.EXECUTING, "主Agent指示调整并继续")
        elif action == "abort":
            # 中止任务
            self._update_state(WorkerState.IDLE, "主Agent指示中止")
        else:
            logger.warning(f"{self.name}: 未知控制指令 {action}")

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
        self._task_id = f"{message.from_agent}_{message.to_agent}_{int(time.time())}"
        
        # 更新状态为执行中
        self.current_task = message.content[:200]
        self._update_state(WorkerState.EXECUTING, f"收到任务: {message.content[:50]}")
        await self._report_status()
        
        # 发布开始执行消息
        await self.publish_progress("开始执行")
        
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
                self._update_state(WorkerState.COMPLETED, "任务完成")
                self.last_result = result_data
                await self._report_status()
                break
            
            # 失败，询问主Agent是否重试
            if attempt < max_retries:
                error = result_data.get("error", "未知错误")
                self._update_state(WorkerState.FAILED, f"失败: {error[:50]}")
                
                # 询问主Agent
                response = await self.on_task_failed(error, can_retry=True)
                
                if response:
                    action = response.get("action", "retry")
                    if action == "skip":
                        # 跳过，返回失败结果但标记为已处理
                        result_data["skipped"] = True
                        result = json.dumps(result_data, ensure_ascii=False)
                        break
                    elif action == "abort":
                        # 中止，返回错误
                        self._update_state(WorkerState.IDLE, "主Agent中止")
                        result = json.dumps({
                            "status": "failed",
                            "error": f"任务中止: {error}",
                            "aborted_by_leader": True,
                        }, ensure_ascii=False)
                        break
                    # action == "retry" 继续循环
            
            # 发布进度
            await self.publish_progress(f"尝试 {attempt + 1}/{max_retries + 1}")
        
        # 发布执行完成消息
        await self.publish_progress("执行完成")
        
        self.context.add(f"回复: {result[:100]}")
        return result

    async def _handle_message(self, message: AgentMessage) -> str:
        """处理消息 — KEPA + RAG + 反问 + 工具调用"""
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

        # 获取任务相关的工具
        tools = await self._get_tools_for_task(message.content)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            role=role, description=desc, extra_context=extra_context,
            output_format=output_format
        )

        # 如果有工具，使用支持函数调用的 LLM
        if tools:
            result = await self._llm_with_tools(system_prompt, message.content, tools)
        else:
            result = await _llm_json(
                system_prompt,
                f"任务内容:\n{message.content}",
                max_tokens=1000,
            )

        if not result:
            question = f"{self.name} 处理任务时 LLM 调用失败，是否降级使用基础响应？(proceed/cancel)"
            user_response = await self._ask_user(question)
            if user_response == "proceed":
                fallback = {"status": "completed", "message": f"{self.name} 已处理: {message.content[:50]}"}
                return json.dumps(fallback, ensure_ascii=False)
            return json.dumps({"status": "failed", "error": "LLM 调用失败，用户取消降级"}, ensure_ascii=False)

        # 处理工具调用
        tool_calls = result.get("tool_calls", [])
        if tool_calls:
            tool_results = await self._execute_tool_calls(tool_calls)
            # 将工具结果注入到结果中
            result["tool_results"] = tool_results
            
            # 将工具结果存入共享知识库
            for tr in tool_results:
                if tr.get("success"):
                    tc = tr.get("tool_call", {})
                    tool_name = tc.get("name", "unknown")
                    tool_result = tr.get("result", {})
                    tags = {"kepa", "tool"}
                    if "search" in tool_name or "fetch" in tool_name:
                        tags.add("search")
                    elif "python" in tool_name or "shell" in tool_name:
                        tags.add("code")
                    elif "file" in tool_name or "write" in tool_name:
                        tags.add("file")
                    await self.store_knowledge(
                        f"tool:{self.name}:{tool_name}",
                        {"result": str(tool_result)[:500], "tool": tool_name},
                        tags=tags,
                    )
            
            # 如果有工具结果，基于结果生成最终答案
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

    async def _llm_with_tools(self, system_prompt: str, user_message: str, tools: List[Dict]) -> dict:
        """使用支持函数调用的 LLM"""
        try:
            router = _get_llm_router()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"任务内容:\n{user_message}"},
            ]
            
            # 尝试使用函数调用
            async with _llm_semaphore:
                response = await router.chat(
                    messages, 
                    temperature=0.7, 
                    max_tokens=1000,
                    tools=tools if tools else None
                )
            
            # 解析响应
            if isinstance(response, dict):
                return response
            
            # 尝试从文本中提取 JSON
            cleaned = (response or "").strip().strip("```json").strip("```").strip()
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"LLM JSON 解析失败: {e}")
            # 尝试从文本中提取工具调用
            return self._extract_tool_calls_from_text(response or "")
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            return {}

    def _extract_tool_calls_from_text(self, text: str) -> dict:
        """从文本中提取工具调用（备用方案）"""
        import re
        result = {"tool_calls": []}
        
        # 匹配 write_file(path=xxx, content=xxx) 格式
        write_match = re.search(r'write_file\s*\(\s*path\s*=\s*["\']([^"\']+)["\']\s*,\s*content\s*=\s*["\'](.+?)["\']\s*\)', text, re.DOTALL)
        if write_match:
            result["tool_calls"].append({
                "name": "write_file",
                "arguments": {"path": write_match.group(1), "content": write_match.group(2)}
            })
        
        # 匹配 execute_python(code=xxx) 格式
        python_match = re.search(r'execute_python\s*\(\s*code\s*=\s*["\'](.+?)["\']\s*\)', text, re.DOTALL)
        if python_match:
            result["tool_calls"].append({
                "name": "execute_python",
                "arguments": {"code": python_match.group(1)}
            })
        
        return result

    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """执行多个工具调用（并行）"""
        results = []
        
        async def _run_one(tc: Dict) -> Dict:
            name = tc.get("name", "")
            args = tc.get("arguments", {})
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
        msg = AgentMessage(from_agent=from_agent, to_agent=self.name, content=task_content)
        return await self.process_message(msg)


# =============================================================================
# LeaderAgent — 队长 Agent（监管 Worker、分析结果、动态规划）
# =============================================================================

class LeaderAgent(LLMAgent):
    """队长 Agent — 在 LLMAgent 基础上增加监管 Worker、分析结果、动态规划"""

    def __init__(self, name: str, max_workers: int = 5, tool_registry=None, comm_center=None):
        super().__init__(name=name, role=AgentRole.LEADER, tool_registry=tool_registry, comm_center=comm_center)
        self.workers: Dict[str, LLMAgent] = {}
        self.max_workers = max_workers
        self.active_worker_count = 3
        self.worker_states: Dict[str, WorkerState] = {}  # 跟踪Worker状态
        self._pending_questions: Dict[str, asyncio.Future] = {}  # 等待回复的询问

    def on_message_received(self, message: dict) -> None:
        """处理来自Worker的消息（覆盖父类方法）"""
        msg_type = message.get("message_type", "?")
        sender = message.get("sender", "?")
        content = message.get("content", {})
        
        logger.debug(f"👑 {self.name} 收到消息: {msg_type} from {sender}")
        
        # 处理Worker的询问
        if msg_type == MessageType.ASK_LEADER:
            if isinstance(content, dict) and content.get("type") == MessageType.ASK_LEADER:
                # 记录Worker状态
                worker_name = content.get("worker", sender)
                if worker_name in self.workers:
                    self.worker_states[worker_name] = WorkerState.ASKING
                
                # 将询问放入队列，由主循环处理
                question_id = f"{worker_name}_{int(time.time() * 1000)}"
                self._pending_questions[question_id] = {
                    "worker": worker_name,
                    "question": content.get("question", ""),
                    "context": content.get("context", {}),
                }
                logger.info(f"❓ Worker {worker_name} 询问: {content.get('question', '')[:80]}")
        
        # 处理Worker状态更新
        elif msg_type == MessageType.STATUS_UPDATE:
            if isinstance(content, dict):
                worker_name = content.get("worker", sender)
                state_str = content.get("state", "idle")
                try:
                    self.worker_states[worker_name] = WorkerState(state_str)
                except ValueError:
                    pass
                logger.debug(f"📊 Worker {worker_name} 状态: {state_str}")

    async def respond_to_worker(self, worker_name: str, action: str, reason: str = "") -> None:
        """回复Worker的询问
        
        Args:
            worker_name: Worker名称
            action: 动作（retry/skip/abort/adjust）
            reason: 原因说明
        """
        if worker_name not in self.workers:
            logger.warning(f"Worker {worker_name} 不在队伍中")
            return
        
        response = {
            "type": MessageType.LEADER_RESPONSE,
            "worker": worker_name,
            "action": action,
            "reason": reason,
            "timestamp": time.time(),
        }
        
        # 发送回复给Worker
        await self.send_message(worker_name, response, MessageType.LEADER_RESPONSE)
        
        # 更新Worker状态
        if action == "retry":
            self.worker_states[worker_name] = WorkerState.RETRYING
        elif action in ("skip", "abort"):
            self.worker_states[worker_name] = WorkerState.IDLE
        
        logger.info(f"👑 主Agent回复 {worker_name}: {action} ({reason})")

    async def send_control(self, worker_name: str, action: str, params: Dict = None) -> None:
        """发送控制指令给Worker
        
        Args:
            worker_name: Worker名称
            action: 控制动作（stop/retry/adjust/abort）
            params: 附加参数
        """
        if worker_name not in self.workers:
            logger.warning(f"Worker {worker_name} 不在队伍中")
            return
        
        control_msg = {
            "type": MessageType.CONTROL,
            "action": action,
            "params": params or {},
            "timestamp": time.time(),
        }
        
        await self.send_message(worker_name, control_msg, MessageType.CONTROL)
        logger.info(f"🎛️ 主Agent发送控制指令给 {worker_name}: {action}")

    def get_worker_states(self) -> Dict[str, str]:
        """获取所有Worker的状态"""
        return {name: state.value for name, state in self.worker_states.items()}

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
        
        # 发布任务开始消息
        await self.publish_progress("任务开始")

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

            # ========== 处理 Worker 询问 ==========
            await self._process_worker_questions()

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

    async def _process_worker_questions(self) -> None:
        """处理Worker的询问请求"""
        if not self._pending_questions:
            return
        
        # 复制并清空队列
        questions = dict(self._pending_questions)
        self._pending_questions.clear()
        
        for q_id, q_info in questions.items():
            worker_name = q_info["worker"]
            question = q_info["question"]
            context = q_info["context"]
            
            logger.info(f"❓ 处理 {worker_name} 的询问: {question[:60]}")
            
            # 使用LLM决定如何回复
            system = (
                "你是队长Agent，需要处理Worker的询问。\n\n"
                "Worker可能遇到的情况：\n"
                "1. 任务执行失败，询问是否重试\n"
                "2. 不确定如何执行，请求澄清\n"
                "3. 需要更多资源或权限\n\n"
                "请决定如何回复，输出JSON：\n"
                '{"action": "retry/skip/abort", "reason": "原因说明"}\n\n'
                "- retry: 让Worker重试\n"
                "- skip: 跳过这个子任务\n"
                "- abort: 中止整个任务"
            )
            
            user = (
                f"Worker {worker_name} 询问:\n{question}\n\n"
                f"上下文: {json.dumps(context, ensure_ascii=False)[:200]}"
            )
            
            response = await _llm_json(system, user, max_tokens=200)
            
            if response and isinstance(response, dict):
                action = response.get("action", "retry")
                reason = response.get("reason", "队长决定")
            else:
                # 默认重试
                action = "retry"
                reason = "超时默认重试"
            
            # 回复Worker
            await self.respond_to_worker(worker_name, action, reason)

    async def _react_think(self, task_description: str, history: List[Dict], 
                           results: List[Dict], round_num: int) -> Dict:
        """ReAct Thought 阶段：分析状态，决定下一步"""
        
        # 构建上下文
        history_text = ""
        if history:
            history_lines = []
            for h in history[-3:]:  # 只保留最近3轮
                history_lines.append(
                    f"轮次{h['round']}: 思考={h['thought'][:100]}, "
                    f"行动={h['action_type']}, 结果={'成功' if h['result'].get('success') else '失败'}"
                )
            history_text = "\n".join(history_lines)

        results_text = ""
        if results:
            results_text = f"\n已完成 {len(results)} 个子任务"

        # 根据任务类型提供更具体的工具调用指导
        tool_hints = ""
        task_lower = task_description.lower()
        
        if any(kw in task_lower for kw in ["天气", "气温", "温度"]):
            tool_hints = (
                "\n【重要】这是一个天气查询任务！请直接调用工具：\n"
                '{"done": false, "thinking": "用户需要查询天气", "action": {"type": "tool", "tool_name": "skill_execute", "args": {"skill_name": "weather", "params": {"city": "城市名"}}}}\n'
            )
        elif any(kw in task_lower for kw in ["搜索", "爬取", "热搜", "百度", "微博", "知乎"]):
            tool_hints = (
                "\n【重要】这是一个网页搜索/爬取任务！请直接调用工具：\n"
                '{"done": false, "thinking": "用户需要搜索网页", "action": {"type": "tool", "tool_name": "web_search", "args": {"query": "搜索关键词"}}}\n'
            )
        elif any(kw in task_lower for kw in ["翻译", "translate"]):
            tool_hints = (
                "\n【重要】这是一个翻译任务！请直接调用工具：\n"
                '{"done": false, "thinking": "用户需要翻译", "action": {"type": "tool", "tool_name": "skill_execute", "args": {"skill_name": "translator", "params": {"text": "要翻译的文本", "target_lang": "en"}}}}\n'
            )
        elif any(kw in task_lower for kw in ["写", "创建", "保存", "文件"]):
            tool_hints = (
                "\n【重要】这是一个文件操作任务！请直接调用工具：\n"
                '{"done": false, "thinking": "用户需要创建文件", "action": {"type": "tool", "tool_name": "write_file", "args": {"path": "~/Desktop/output.txt", "content": "文件内容"}}}\n'
            )
        elif any(kw in task_lower for kw in ["执行", "运行", "代码", "python"]):
            tool_hints = (
                "\n【重要】这是一个代码执行任务！请直接调用工具：\n"
                '{"done": false, "thinking": "用户需要执行代码", "action": {"type": "tool", "tool_name": "execute_python", "args": {"code": "print(1)"}}}\n'
            )

        system = (
            "你是队长Agent，使用 ReAct 模式执行任务。\n\n"
            "当前状态分析后，输出下一步行动的 JSON：\n\n"
            "选项1 - 调用工具（适合单步操作）:\n"
            '{"done": false, "thinking": "分析...", "action": {"type": "tool", "tool_name": "工具名", "args": {...}}}\n\n'
            "选项2 - 分配单个子任务给Worker（适合简单子任务）:\n"
            '{"done": false, "thinking": "分析...", "action": {"type": "delegate", "task": "子任务描述"}}\n\n'
            "选项3 - 批量分配子任务给多个Worker并行执行（适合复杂任务分解）:\n"
            '{"done": false, "thinking": "分析...", "action": {"type": "batch_delegate", "tasks": ["子任务1", "子任务2", "子任务3"]}}\n\n'
            "选项4 - 处理前一轮的batch_delegate结果（并发→串行的关键环节）:\n"
            '{"done": false, "thinking": "基于上一轮并发结果...", "action": {"type": "process_results", "task": "综合分析并生成报告"}}\n\n'
            "选项5 - 任务完成:\n"
            '{"done": true, "thinking": "任务已完成..."}\n\n'
            "可调用的工具: write_file, read_file, edit_file, execute_python, execute_shell, "
            "web_search, fetch_url, search_files, git\n\n"
            "决策指南:\n"
            "- 简单任务（如写文件、搜索）→ 使用 tool\n"
            "- 需要多个独立步骤的任务 → 使用 batch_delegate，将任务分解为可并行的子任务\n"
            "- 单个复杂子任务 → 使用 delegate\n"
            "- 处理前一轮并发结果 → 使用 process_results\n\n"
            "混合调度策略（重要！）:\n"
            "- 并发→串行：先用 batch_delegate 并发收集数据，下一轮用 process_results 串行处理结果\n"
            "- 串行→并发：先用 delegate 串行准备，下一轮用 batch_delegate 并发拆解执行\n"
            "- 引用前一轮结果：在 thinking 中说明「基于上一轮结果...」\n"
            "- 阶段性规划：在 thinking 中说明当前阶段（如「数据收集阶段」「处理阶段」「输出阶段」）\n\n"
            f"{tool_hints}\n"
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
                to_agent=worker.name,
                content=task,
                message_type="task",
            )
            result_str = await worker.process_message(msg)
            
            try:
                data = json.loads(result_str)
                is_ok = data.get("success") is True and data.get("status") != "failed"
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
            
            # 分析执行结果
            analysis = await self._analyze_results(batch_results, original_task, 1)
            
            # 统计成功数量
            success_count = sum(1 for r in batch_results if r.get("success"))
            
            return {
                "success": success_count > 0,
                "result": {
                    "batch_results": batch_results,
                    "analysis": analysis,
                    "success_count": success_count,
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
                to_agent=worker.name,
                content=enhanced_task,
                message_type="task",
            )
            result_str = await worker.process_message(msg)
            
            try:
                data = json.loads(result_str)
                is_ok = data.get("success") is True and data.get("status") != "failed"
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
        """并行执行一批子任务（使用消息总线通信）"""
        
        # 发布任务分配消息
        await self.publish_progress(f"分配 {len(assignments)} 个子任务")
        
        async def _run_one(assignment: Dict) -> Dict:
            worker = assignment["worker"]
            task_content = assignment["task"]
            
            # 通过消息总线发送任务给 worker
            await self.send_message(worker.name, {
                "type": "task_assignment",
                "task": task_content,
                "from": self.name,
            }, msg_type="task")
            
            msg = AgentMessage(
                from_agent=self.name,
                to_agent=worker.name,
                content=task_content,
                message_type="task",
            )
            result_str = await worker.process_message(msg)
            try:
                data = json.loads(result_str)
                is_ok = data.get("success") is True and data.get("status") != "failed"
            except Exception as e:
                data = {"raw": result_str[:200], "error": str(e)}
                is_ok = False
            
            # 发布 worker 完成消息
            status = "完成" if is_ok else "失败"
            await self.publish_progress(f"Worker {worker.name} {status}")
            
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
        
        # 发布批次完成消息
        success_count = sum(1 for r in results if r.get("success"))
        await self.publish_progress(f"批次完成: {success_count}/{len(results)} 成功")
        
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

    async def _activate_worker(self, count: int):
        """激活更多 Worker"""
        self.active_worker_count = min(self.active_worker_count + count, self.max_workers)


# =============================================================================
# V1LeaderPool — 队长模式 Agent 池
# =============================================================================

class V1LeaderPool:
    """队长模式 Agent 池 — 1 个队长 + 最多 max_workers 个 Worker（支持池化复用）"""

    def __init__(self):
        self._all_agents: Dict[str, LLMAgent] = {}
        self._tool_registry = None
        self._comm_center = None
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
            except Exception as e:
                logger.warning(f"初始化工具注册表失败: {e}")
                self._tool_registry = None

    async def _ensure_comm_center(self):
        """确保通信中心已初始化"""
        if self._comm_center is None:
            try:
                from core.agents.agent_communication import get_communication_center
                self._comm_center = get_communication_center()
            except Exception as e:
                logger.warning(f"初始化通信中心失败: {e}")
                self._comm_center = None

    async def create_team(self, worker_count: int = 3, max_workers: int = 5) -> tuple:
        """创建 1 队长 + 最多 max_workers 个 Worker（默认激活 worker_count 个）

        Returns:
            (LeaderAgent, List[LLMAgent]) — 队长 + 全部 Worker 列表
        """
        # 确保通信中心已初始化
        await self._ensure_comm_center()
        
        team_id = uuid4().hex[:8]
        leader = LeaderAgent(
            name=f"队长_{team_id}",
            max_workers=max_workers,
            tool_registry=self._tool_registry,
            comm_center=self._comm_center,
        )
        self._all_agents[leader.name] = leader

        workers = []
        for i in range(max_workers):
            w = LLMAgent(
                name=f"队员{i+1}_{team_id}",
                role=AgentRole.WORKER,
                tool_registry=self._tool_registry,
                comm_center=self._comm_center,
            )
            self._all_agents[w.name] = w
            workers.append(w)

        leader.workers = {w.name: w for w in workers}
        leader.active_worker_count = min(worker_count, max_workers)

        # 注册所有 agents 到通信中心
        if self._comm_center:
            try:
                await self._comm_center.register_agent(
                    leader.name, leader.name, "leader",
                    callbacks={"message_received": leader.on_message_received}
                )
                for w in workers:
                    await self._comm_center.register_agent(
                        w.name, w.name, "worker",
                        callbacks={"message_received": w.on_message_received}
                    )
                logger.info(f"📡 已注册 {len(workers) + 1} 个 Agent 到通信中心")
            except Exception as e:
                logger.warning(f"注册 Agent 到通信中心失败: {e}")

        logger.info(f"👥 创建队伍: 1 队长 + {worker_count}/{max_workers} Worker (队长={leader.name})")
        return leader, workers

    async def share_memory(self, agents: List[LLMAgent]) -> None:
        """执行后广播每个 Agent 的执行摘要到共享知识库"""
        for agent in agents:
            logger.info(f"V1 share_memory: agent={agent.name} role={agent.role.value} status={agent.status}")
            # 将 agent 的执行摘要存入共享知识库
            if self._comm_center:
                try:
                    await self._comm_center.store_knowledge(
                        key=f"agent:{agent.name}:summary",
                        data={"name": agent.name, "role": agent.role.value, "status": agent.status},
                        tags={"agent", "summary"},
                        source=agent.name,
                        summary=f"{agent.name} ({agent.role.value}): {agent.status}",
                    )
                except Exception as e:
                    logger.debug(f"存储 agent 摘要失败: {e}")

    # ─── Worker 池化管理 ──────────────────────────────────────────────

    async def get_worker(self, leader_name: str = None) -> Optional[LLMAgent]:
        """从池中获取一个空闲Worker
        
        Args:
            leader_name: 主Agent名称（用于设置Worker的leader_name）
        
        Returns:
            空闲Worker，或 None（池空且无法创建新Worker）
        """
        async with self._pool_lock:
            # 优先从池中获取
            if self._worker_pool:
                worker = self._worker_pool.pop()
                worker._update_state(WorkerState.IDLE, "从池中取出")
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
                    comm_center=self._comm_center,
                )
                if leader_name:
                    worker.leader_name = leader_name
                
                # 注册到通信中心
                if self._comm_center:
                    try:
                        await self._comm_center.register_agent(
                            worker.name, worker.name, "worker",
                            callbacks={"message_received": worker.on_message_received}
                        )
                    except Exception as e:
                        logger.warning(f"注册Worker失败: {e}")
                
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
            worker._update_state(WorkerState.IDLE, "任务完成归还池")
            worker.current_task = None
            worker.last_result = None
            
            # 放回池中
            if worker not in self._worker_pool:
                self._worker_pool.append(worker)
                logger.debug(f"📦 Worker 归还池: {worker.name}")

    def get_pool_status(self) -> Dict[str, Any]:
        """获取Worker池状态"""
        return {
            "pool_size": len(self._worker_pool),
            "busy_count": len(self._busy_workers),
            "total_agents": len(self._all_agents),
            "idle_workers": [w.name for w in self._worker_pool],
            "busy_workers": list(self._busy_workers.keys()),
        }

    async def discard(self, agents: List[LLMAgent]) -> None:
        """清理 Agent — Worker放回池中，Leader注销
        
        注意：Worker不会被删除，而是放回池中以供复用。
        只有Leader会被完全清理。
        """
        for agent in agents:
            if agent.role == AgentRole.LEADER:
                # Leader 直接清理
                self._all_agents.pop(agent.name, None)
                if self._comm_center:
                    try:
                        await self._comm_center.unregister_agent(agent.name)
                    except Exception as e:
                        logger.debug(f"注销 Leader 失败: {e}")
                logger.debug(f"V1LeaderPool: 清理 Leader {agent.name}")
            else:
                # Worker 放回池中
                await self.return_worker(agent)
                logger.debug(f"V1LeaderPool: Worker {agent.name} 归还池")

    def get_agent(self, name: str) -> Optional[LLMAgent]:
        return self._all_agents.get(name)

    def get_all_agents(self) -> List[LLMAgent]:
        return list(self._all_agents.values())
