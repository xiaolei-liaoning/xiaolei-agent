#!/usr/bin/env python3
"""智能多Agent系统 - V1 架构（队长-队员模式）

V1 角色分工型多 Agent：
- 1 个 LeaderAgent（队长）+ N 个 WorkerAgent（队员）
- 队长分解任务、分配子任务、分析 Worker 结果、动态规划
- 队员只负责执行具体子任务
- 分批模式：队长分配一批 → 并行执行 → 队长分析 → 循环
"""

import asyncio
import json
import time
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from core.engine.llm_backend import get_llm_router

logger = logging.getLogger(__name__)


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
    """调用 LLM 并返回解析后的 JSON"""
    try:
        router = get_llm_router()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        async with _llm_semaphore:
            response = await router.chat(messages, temperature=0.7, max_tokens=max_tokens)
        cleaned = (response or "").strip().strip("```json").strip("```").strip()
        return json.loads(cleaned)
    except Exception as e:
        logger.warning(f"LLM 调用/解析失败: {e}")
        return {}


# =============================================================================
# 提示词模板
# =============================================================================

SYSTEM_PROMPT_TEMPLATE = """你是一个{role}Agent。你的职责是{description}。

对于给定的任务，你需要：
1. 分析任务的目标和要求
2. 制定执行计划
3. 执行任务并生成结果
4. 提供详细的过程描述

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
    """统一 LLM Agent — KEPA + RAG + 反问 + 上下文"""

    def __init__(self, name: str, role: AgentRole):
        self.name = name
        self.role = role
        self.status = "idle"
        self.context = ContextMemory()

    def _get_role_config(self) -> tuple:
        configs = {
            AgentRole.LEADER: ("队长", "负责任务拆解、分配、监管 Worker 执行、分析结果并动态规划", "decompose"),
            AgentRole.WORKER: ("队员", "负责执行队长分配的具体任务", "execute"),
        }
        return configs.get(self.role, ("通用", "处理各类任务", "execute"))

    async def _rag_query(self, query: str) -> str:
        """RAG 检索增强 — 从知识库获取相关信息"""
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

            if decision == "continue" or confidence >= 0.85:
                result["confidence"] = confidence
                result["kepa_iterations"] = attempt + 1
                return result

            if decision == "fail":
                result["success"] = False
                result["error"] = reflection.get("reason", "KEPA 判断失败")
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
        result = await self._handle_message(message)
        self.context.add(f"回复: {result[:100]}")
        return result

    async def _handle_message(self, message: AgentMessage) -> str:
        """处理消息 — KEPA + RAG + 反问"""
        role, desc, fmt_type = self._get_role_config()
        output_format = OUTPUT_FORMATS.get(fmt_type, OUTPUT_FORMATS["execute"])

        # RAG 检索
        rag_context = await self._rag_query(message.content)

        extra_context = ""
        if rag_context:
            extra_context += f"\n【知识库参考】\n{rag_context}\n"
        recent_ctx = self.context.get_recent()
        if recent_ctx != "（无上下文）":
            extra_context += f"\n【上下文】\n{recent_ctx}\n"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            role=role, description=desc, extra_context=extra_context, output_format=output_format
        )

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

    async def execute_with_context(self, task_content: str, from_agent: str = "系统") -> str:
        """对外执行接口 — 自动管理 context"""
        msg = AgentMessage(from_agent=from_agent, to_agent=self.name, content=task_content)
        return await self.process_message(msg)


# =============================================================================
# LeaderAgent — 队长 Agent（监管 Worker、分析结果、动态规划）
# =============================================================================

class LeaderAgent(LLMAgent):
    """队长 Agent — 在 LLMAgent 基础上增加监管 Worker、分析结果、动态规划"""

    def __init__(self, name: str, max_workers: int = 5):
        super().__init__(name=name, role=AgentRole.LEADER)
        self.workers: Dict[str, LLMAgent] = {}
        self.max_workers = max_workers
        self.active_worker_count = 3

    async def supervise_task(self, task_description: str, workers: List[LLMAgent],
                             active_count: int = 3, max_rounds: int = 3) -> Dict:
        """队长主循环：分解→分配→执行→分析→循环/完成

        Args:
            task_description: 任务描述
            workers: Worker Agent 列表（全部槽位）
            active_count: 本轮活跃 Worker 数
            max_rounds: 最大循环轮次

        Returns:
            执行结果字典
        """
        self.active_worker_count = min(active_count, len(workers))
        self.workers = {w.name: w for w in workers}

        logger.info(f"🚀 队长 {self.name} 开始执行任务: {task_description}")

        # 1. 分解任务
        subtasks = await self._decompose_task(task_description)
        if not subtasks:
            return {"success": False, "error": "任务分解失败"}

        all_results = []
        remaining = list(subtasks)
        round_num = 0

        while remaining and round_num < max_rounds:
            round_num += 1
            active = workers[:self.active_worker_count]
            logger.info(f"📋 第 {round_num} 轮: 分配 {len(remaining)} 个子任务给 {len(active)} 个 Worker")

            # 2. 分配子任务
            assignments = self._assign(remaining, active)
            remaining = []

            # 3. Workers 并行执行
            batch_results = await self._execute_batch(assignments, workers)
            all_results.extend(batch_results)

            # 4. 队长分析结果
            analysis = await self._analyze_results(batch_results, task_description, round_num)

            decision = analysis.get("decision", "complete")

            if decision == "complete":
                logger.info(f"✅ 第 {round_num} 轮: 队长判定完成")
                break

            elif decision == "retry":
                retry_tasks = analysis.get("retry_tasks", [])
                logger.info(f"🔄 第 {round_num} 轮: 需要重试 {len(retry_tasks)} 个子任务")
                remaining = retry_tasks

            elif decision == "reassign":
                retry_tasks = analysis.get("retry_tasks", [])
                needed = analysis.get("needed_count", 0)
                if needed > 0 and (self.active_worker_count + needed) <= self.max_workers:
                    self.active_worker_count = min(self.active_worker_count + needed, self.max_workers)
                    logger.info(f"📈 唤醒更多 Worker: 当前 {self.active_worker_count} 个")
                remaining = retry_tasks

        success = len(remaining) == 0
        logger.info(f"{'✅' if success else '❌'} 队长任务完成: 共 {round_num} 轮, {len(all_results)} 个子任务")

        return {
            "success": success,
            "results": all_results,
            "rounds": round_num,
            "total_subtasks": len(subtasks),
        }

    async def _decompose_task(self, task_description: str) -> List[str]:
        """用 LLM 将任务分解为子任务列表"""
        system = (
            "你是队长Agent。负责将复杂任务分解为多个独立的子任务，每个子任务可以并行执行。\n\n"
            "输出JSON格式:\n"
            f"{OUTPUT_FORMATS['decompose']}"
        )
        user = f"请将以下任务分解为{self.active_worker_count}个左右的子任务：\n{task_description}\n\n注意：不要输出JSON外的其他内容。"

        rag_context = await self._rag_query(task_description)
        if rag_context:
            user = f"参考知识库信息后分解任务：\n{rag_context}\n\n任务:\n{task_description}"

        result = await _llm_json(system, user, max_tokens=800)
        subtasks = result.get("subtasks", [])
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
                to_agent=worker.name,
                content=task_content,
                message_type="task",
            )
            result_str = await worker.process_message(msg)
            try:
                data = json.loads(result_str)
                is_ok = data.get("success", True) and data.get("status") != "failed"
            except Exception:
                data = {"raw": result_str[:200]}
                is_ok = True
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
                results.append({"success": False, "error": str(item)})
            else:
                results.append(item)
        return results

    async def _analyze_results(self, batch_results: List[Dict], original_task: str, round_num: int) -> Dict:
        """用 LLM 分析 Worker 执行结果，决定下一步"""
        summary_lines = []
        for r in batch_results:
            status = "✅" if r.get("success", False) else "❌"
            summary_lines.append(f"{status} Worker {r.get('worker', '?')}: {json.dumps(r.get('result', {}), ensure_ascii=False)[:200]}")

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
    """队长模式 Agent 池 — 1 个队长 + 最多 max_workers 个 Worker"""

    def __init__(self):
        self._all_agents: Dict[str, LLMAgent] = {}

    def create_team(self, worker_count: int = 3, max_workers: int = 5) -> tuple:
        """创建 1 队长 + 最多 max_workers 个 Worker（默认激活 worker_count 个）

        Returns:
            (LeaderAgent, List[LLMAgent]) — 队长 + 全部 Worker 列表
        """
        team_id = uuid4().hex[:8]
        leader = LeaderAgent(name=f"队长_{team_id}", max_workers=max_workers)
        self._all_agents[leader.name] = leader

        workers = []
        for i in range(max_workers):
            w = LLMAgent(name=f"队员{i+1}_{team_id}", role=AgentRole.WORKER)
            self._all_agents[w.name] = w
            workers.append(w)

        leader.workers = {w.name: w for w in workers}
        leader.active_worker_count = min(worker_count, max_workers)

        logger.info(f"👥 创建队伍: 1 队长 + {worker_count}/{max_workers} Worker (队长={leader.name})")
        return leader, workers

    async def share_memory(self, agents: List[LLMAgent]) -> None:
        """执行后广播每个 Agent 的执行摘要"""
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, Message, MessageType
            bus = get_shared_bus()
            for agent in agents:
                summary = {
                    "agent_id": agent.name,
                    "role": agent.role.value,
                    "context": agent.context.get_recent(),
                    "status": agent.status,
                }
                msg = Message(
                    type=MessageType.AGENT_BROADCAST,
                    sender=agent.name,
                    topic=f"memory:share:v1:{agent.name}",
                    payload=summary,
                )
                await bus.publish(f"memory:share:v1:{agent.name}", msg)
        except Exception as e:
            logger.debug(f"V1 share_memory 失败: {e}")

    async def discard(self, agents: List[LLMAgent]) -> None:
        """清理 Agent"""
        for agent in agents:
            self._all_agents.pop(agent.name, None)
        logger.debug(f"V1LeaderPool: 清理了 {len(agents)} 个 Agent")

    def get_agent(self, name: str) -> Optional[LLMAgent]:
        return self._all_agents.get(name)

    def get_all_agents(self) -> List[LLMAgent]:
        return list(self._all_agents.values())
