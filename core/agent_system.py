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
import os
import re
import time
import logging
from typing import Any, Dict, List, Optional
from core.memory.context_compactor import get_compactor
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

logger = logging.getLogger(__name__)


class V1SkillRouter:
    """V1 版 skill 路由 — 输入 task，输出 skill_id

    增强功能：
    - 第1层: @skill 确定性路由
    - 第2层: SkillSystem 三层匹配
    - 第3层: LLM 意图分类兜底
    - 第4层: 回退到 general
    """

    def __init__(self):
        self._skill_system = None
        self._llm_router = None

    async def match(self, task: str) -> str:
        # 第1层: @skill 确定性路由
        at_match = re.match(r"@(\w+)\s", task)
        if at_match:
            skill_name = at_match.group(1)
            try:
                if self._skill_system is None:
                    from core.skills.base_skills import SkillSystem
                    self._skill_system = SkillSystem()
                await self._skill_system.match(task)
                known_skills = [s.id for s in self._skill_system.base_skills.values()] if hasattr(self._skill_system, 'base_skills') else []
                if skill_name in known_skills:
                    return skill_name
            except Exception:
                pass

        # 第2层: SkillSystem 三层匹配（原有逻辑）
        try:
            if self._skill_system is None:
                from core.skills.base_skills import SkillSystem
                self._skill_system = SkillSystem()
            result = await self._skill_system.match(task)
            if result.skill_id and result.skill_id != "general":
                return result.skill_id
        except Exception as e:
            logger.debug("V1SkillRouter.match 第2层失败: %s", e)

        # 第3层: LLM 意图分类兜底
        llm_skill = await self._llm_classify(task)
        if llm_skill:
            return llm_skill

        # 第4层: 回退到 general
        return "general"

    async def _llm_classify(self, task: str) -> Optional[str]:
        try:
            if self._llm_router is None:
                from core.engine.llm_backend import get_llm_router
                self._llm_router = get_llm_router()
            if not self._llm_router or not self._llm_router.is_available():
                return None
            system = ("你是一个技能路由器。从以下技能中选择最匹配的一个，只返回 JSON：\n"
                      "可用技能: project_analyzer, web_scraper, data_analyst, deep_thinker, translator, weather_expert, system_toolbox, creative, general\n"
                      '输出: {"skill": "技能名", "confidence": 0.0~1.0, "reason": "简短理由"}')
            resp = await self._llm_router.simple_chat(
                user_message=task, system_prompt=system,
                temperature=0.1, max_tokens=100,
            )
            if resp:
                text = resp.strip().strip("```json").strip("```").strip()
                parsed = json.loads(text)
                skill = parsed.get("skill", "")
                conf = float(parsed.get("confidence", 0.0))
                if skill and conf >= 0.6 and skill != "general":
                    return skill
        except Exception as e:
            logger.debug("V1SkillRouter LLM 分类失败: %s", e)
        return None


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
    """调用 LLM 并返回解析后的 JSON（含 1 次重试 + 提取兜底）"""
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
    # ponytail: 兜底 - 用 LLM 提取 JSON
    try:
        router = _get_llm_router()
        extract_prompt = f"从以下文本中提取 JSON 对象并返回（仅返回 JSON）：\n\n{user_message}"
        messages = [
            {"role": "system", "content": "你是一个 JSON 提取器，只输出 JSON 格式。"},
            {"role": "user", "content": extract_prompt},
        ]
        async with _llm_semaphore:
            response = await router.chat(messages, temperature=0.3, max_tokens=max_tokens)
        cleaned = (response or "").strip().strip("```json").strip("```").strip()
        return json.loads(cleaned)
    except Exception:
        pass
    logger.warning(f"LLM JSON 解析最终失败: {last_error}")
    return {}


# =============================================================================
# 提示词模板
# =============================================================================

SYSTEM_PROMPT_TEMPLATE = """你是一个{role}Agent。你的职责是{description}。

先思考再行动：
1. 任务目标是什么？当前进度在哪里？
2. 需要工具就调用，有数据就回答，信息不够继续追问
3. 不要输出思考过程描述，直接行动

关键规则：
- 如果任务明确且有数据，直接执行，不要描述"我将..."
- 创建文件/报告 → 用 write_file 工具写入（如 ~/Desktop/文件名）
- 分析任务 → 先读取文件/搜索获取数据，再返回完整分析结果
- 修改代码 → 用 edit_file（精确字符串替换）
- 禁止输出被截断/不完整的内容

{extra_context}

{file_tip}

输出格式：
返回 JSON 格式结果（可直接用工具完成的任务在 result 字段返回实际内容）
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
        """清空上下文记忆"""
        self.entries = []


# =============================================================================
# LLMAgent — 统一 Agent 基类（含 KEPA + RAG + 反问 + 上下文）
# =============================================================================

class LLMAgent:
    """统一 LLM Agent — KEPA + RAG + 反问 + 上下文 + 工具调用 + 消息总线"""

    def __init__(self, name: str, role: AgentRole, tool_registry=None, role_prompt: str = "", tool_restrictions: Optional[List[str]] = None):
        self.name = name
        self.role = role
        self.status = "idle"
        self.context = ContextMemory()
        self.tool_registry = tool_registry  # V2 ToolRegistry 引用
        self.role_prompt = role_prompt
        self.tool_restrictions = tool_restrictions  # None=不限制, []=禁全部
        self._tool_cache = None  # 缓存的工具列表
        self._tool_cache_time = 0  # 缓存时间戳（用于TTL）
        self._task_id = None  # 当前任务 ID

        # Worker 状态
        self.state = "idle"
        self.current_task = None  # 当前执行的任务
        self.last_result = None  # 上一次执行结果
        self.leader_name = None  # 所属主Agent名称（用于询问）

        # A: 对话记忆 (ShortTermMemory)
        self.user_id: str = ""
        self._stm = None
        # B/C: 向量记忆 (VectorMemoryStore)
        self._vm = None

    @property
    def vm(self):
        """Lazy init VectorMemoryStore"""
        if self._vm is None:
            try:
                from core.memory.vector_memory import VectorMemoryStore
                self._vm = VectorMemoryStore()
            except Exception as e:
                logger.debug(f"VectorMemory init failed: {e}")
                self._vm = False  # 标记失败不再重试
        return self._vm if self._vm else None

    @property
    def stm(self):
        """Lazy init ShortTermMemoryManager"""
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

        if self.tool_restrictions is not None and tool_name not in self.tool_restrictions:
            return {"success": False, "error": f"工具 {tool_name} 不在该角色的白名单中（可用: {self.tool_restrictions}）"}

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

            if confidence >= 0.85:
                result["confidence"] = confidence
                result["kepa_iterations"] = attempt + 1
                return result

            if decision != "retry":
                result["confidence"] = confidence
                result["kepa_iterations"] = attempt + 1
                return result

            logger.info(f"🔄 {self.name} KEPA 重试 #{attempt + 1}: {reflection.get('reason', '')[:60]}")
            result["retry_reason"] = reflection.get("reason", "")

        result["success"] = False
        result["error"] = f"KEPA 超过最大重试 {max_retries} 次"
        result["kepa_iterations"] = max_retries
        return result

    async def process_message(self, message: AgentMessage) -> str:
        self.context.add(f"收到: {message.content[:100]}")
        logger.info(f"📬 {self.name} 收到消息 from {message.from_agent}")

        # A: 对话记忆 — 存用户消息
        if self.stm and self.user_id:
            try:
                self.stm.add(self.user_id, "user", message.content)
            except Exception as e:
                logger.debug(f"STM add user failed: {e}")

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

        # A: 对话记忆 — 存 Agent 回复
        if self.stm and self.user_id:
            try:
                self.stm.add(self.user_id, "assistant", str(result)[:2000])
            except Exception as e:
                logger.debug(f"STM add assistant failed: {e}")

        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    async def _handle_message(self, message: AgentMessage) -> str:
        """处理消息 — ReAct 循环（Think→Act→Observe→循环）"""
        role, default_desc, fmt_type = self._get_role_config()
        desc = self.role_prompt or default_desc
        output_format = OUTPUT_FORMATS.get(fmt_type, OUTPUT_FORMATS["execute"])

        # RAG 检索
        rag_context = await self._do_rag_query(message.content)
        _rag_hit = bool(rag_context)

        extra_context = ""
        if rag_context:
            extra_context += f"\n【知识库参考】\n{rag_context}\n"
        # A: 从 STM 获取对话历史上下文
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

        # 获取工具列表（先获取，后面 system_prompt 和 ReAct 都要用）
        tools = await self._get_tools_for_task(message.content)

        # ponytail: RAG 命中时隐藏搜索工具，避免 agent 重复联网
        if _rag_hit and tools:
            _search_tools = {"rag_search", "web_search", "fetch_url"}
            before = len(tools)
            tools = [t for t in tools if t.get("function", {}).get("name") not in _search_tools]
            if len(tools) < before:
                extra_context += "\n【注意】知识库已包含相关信息，请直接用知识回答，无需搜索。\n"

        # 判断是否有写文件能力
        has_write = any("write_file" in str(t) for t in tools) if tools else False
        file_tip = ""
        if has_write:
            file_tip = "🔧 你有 write_file 工具可以创建/写入文件。如果任务要求「保存到桌面」或「生成报告」，请用 write_file 把结果写入 ~/Desktop/。\n"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            role=role, description=desc, extra_context=extra_context,
            file_tip=file_tip, output_format=output_format
        )

        # 构建对话历史（ReAct 循环用）
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"任务内容:\n{message.content}"},
        ]

        # ===== 上下文压缩：5层压缩架构 =====
        try:
            compactor = get_compactor()
            # Update assistant timestamp for time-based MC
            compactor.update_assistant_timestamp()
            # Run 5-layer compaction
            conversation = compactor.compact(conversation)
        except Exception:
            pass

        _WORKER_MAX_ROUNDS = 8
        max_react_rounds = _WORKER_MAX_ROUNDS
        result = {}
        all_tool_results = []  # 累积所有轮的 tool_results

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

            all_tool_results.extend(tool_results)
            logger.info(f"🔧 {self.name} 第 {round_num + 1} 轮: {len(tool_calls)} 个工具执行完成")

        # ponytail: 如果最后没有文本回答（全是工具调用），强制补一轮无工具 LLM 调用生成摘要
        if all_tool_results and not result.get("content", ""):
            _summarize_prompt = (
                "任务: " + message.content[:200] +
                "\n\n你已通过工具获取了数据，请基于已有数据生成最终回答，不要再调用工具。"
            )
            conversation.append({"role": "user", "content": _summarize_prompt})
            result = await self._llm_with_tools_from_conversation(conversation, tools=None)

        # 基于所有轮累积的工具结果生成答案
        if all_tool_results:
            result = await self._process_tool_results(result, all_tool_results, message.content)

        # KEPA 反思闭环
        kepa_result = await self._kepa_reflect(result)

        if not kepa_result.get("success", True):
            logger.warning(f"⚠️ {self.name} KEPA 判定失败: {kepa_result.get('error', '')}")
            return json.dumps({
                "status": "failed",
                "success": False,
                "error": kepa_result.get("error", "KEPA 判定失败"),
            }, ensure_ascii=False)

        # C: 知识积累 — Worker 执行完知识型任务后自动写入
        if self.role == AgentRole.WORKER and self.vm and self.user_id:
            asyncio.ensure_future(self._store_knowledge(message.content, kepa_result))

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
                if "ok" in res:
                    content = str(res.get("data", str(res)))
                else:
                    content = str(res.get("content", res.get("text", res.get("result", str(res)))))
            else:
                content = str(res) if res else tr.get("error", "工具执行失败")
            conversation.append({
                "role": "tool",
                "tool_call_id": tc.get("id", "call_0"),
                "content": str(content)[:1000],  # ponytail: 截断到1000字符，过长会撑爆上下文
            })

    async def _llm_with_tools_from_conversation(self, conversation: List[Dict], tools: List[Dict]) -> dict:
        """使用完整对话历史调用 LLM（支持工具调用）"""
        try:
            router = _get_llm_router()
            async with _llm_semaphore:
                response = await router.chat(
                    conversation,
                    temperature=0.7,
                    max_tokens=8000,  # ponytail: 8000 tokens 给 write_file 等大数据写入留空间
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
        
        # 基于工具结果生成最终答案（去重：按工具名+结果摘要前20字去重）
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
            # 从 OpenAI 格式 tool_call 中提取工具名
            tc_name = tc.get("name", "")
            if not tc_name and isinstance(tc.get("function"), dict):
                tc_name = tc["function"].get("name", "?")
            # 去重键：工具名 + 结果前30字
            dedup_key = f"{tc_name}:{str(content)[:30]}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            result_summary.append(f"[{tc_name}] {content[:500]}")
        
        result["tool_result_summary"] = "\n".join(result_summary)
        result["status"] = "success"
        return result

    async def execute_with_context(self, task_content: str, from_agent: str = "系统") -> str:
        """对外执行接口 — 自动管理 context"""
        msg = AgentMessage(from_agent=from_agent, content=task_content)
        return await self.process_message(msg)

    # ── C: 知识积累 ────────────────────────────────────────────────────

    async def _store_knowledge(self, task: str, result: dict) -> None:
        """Worker 执行完知识型任务后写入向量库"""
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
        self._current_skill_id = "general"
        self.worker_states: Dict[str, str] = {}  # 跟踪Worker状态

    async def supervise_task(self, task_description: str, workers: List[LLMAgent],
                             active_count: int = 3, max_rounds: Optional[int] = None,
                             skill_id: str = "general") -> Dict:
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
            max_rounds: 最大循环轮次（ReAct 默认5轮，Web传3轮）

        Returns:
            执行结果字典
        """
        if max_rounds is None:
            max_rounds = int(os.getenv("AGENT_MAX_ROUNDS", "10"))
        self.active_worker_count = min(active_count, len(workers))
        self._current_skill_id = skill_id
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
            
            # ponytail: 程序化强制 — 已有成功结果且 round>=4 时，直接 done（比之前 >=2 多给 2 轮，让深度分析有机会继续）
            successful = [r for r in all_results if r.get("success")]
            if successful and round_num >= 4 and not thought.get("done"):
                logger.info(f"🔒 已有 {len(successful)} 个成功结果，强制 done（跳过 LLM 决策）")
                # 用 LLM 的 thinking 作为 final_result（如果有的话），否则用 raw 结果
                final = thought.get("thinking", "")
                if not final or len(final) < 20:
                    for r in reversed(successful):
                        data = r.get("result", {})
                        if isinstance(data, dict):
                            c = data.get("tool_result_summary", data.get("content", ""))
                            if c:
                                final = c[:5000]
                                break
                thought = {"done": True, "thinking": final or "任务已完成", "final_result": final or "任务已完成"}
            
            # ponytail: 程序化强制 — 已有成功结果且 round>=4 时，直接 done（已由上一块处理，此处不会触发）
            
            # 检查是否任务完成（必须在 force done 之后）
            if thought.get("done"):
                logger.info(f"✅ ReAct 第 {round_num} 轮: 队长判定任务完成")
                final = thought.get("final_result") or thought.get("thinking", "任务完成")
                all_results.append({
                    "success": True,
                    "result": {"tool_result_summary": final, "content": final},
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

            # ponytail: tool 失败强制 fallback，避免 Leader 反复重试失败的 tool
            if action_type == "tool" and not action_result.get("success"):
                # 统计连续 tool 失败次数
                tool_fail_streak = sum(
                    1 for h in context_history
                    if h["action_type"] == "tool" and not h["result"].get("success")
                )
                if tool_fail_streak >= 1:
                    # 注入强制 delegate 提示，让下一轮 LLM 必须选 delegate
                    context_history.append({
                        "round": round_num,
                        "thought": "系统提示：tool 执行失败，下一轮必须使用 delegate 分配给 Worker",
                        "action_type": "system_override",
                        "action": {"type": "delegate"},
                        "result": {"success": False, "error": "tool fallback"},
                    })
            
            # reassign → 增加活跃 Worker 数
            if action_type == "batch_delegate" and not action_result.get("success"):
                analysis = action_result.get("result", {}).get("analysis", {})
                if analysis.get("decision") == "reassign":
                    self.active_worker_count = min(self.active_worker_count + 1, self.max_workers)
                    logger.info(f"reassign: 增加活跃 Worker 到 {self.active_worker_count}")

            # ponytail: 已有成功结果时，检查是否全部子任务完成，是则强制合成，否则允许继续 delegate
            if action_type == "batch_delegate" and action_result.get("success") and all_results:
                result_data = action_result.get("result", {})
                success_count = result_data.get("success_count", 0)
                total_count = result_data.get("total_count", 0)
                if total_count > 0 and success_count >= total_count:
                    logger.info("🔒 全部子任务完成，强制切换为 process_results")
                    context_history.append({
                        "round": round_num,
                        "thought": "系统强制：全部子任务已完成，下一轮必须使用 process_results 综合分析",
                        "action_type": "system_override",
                        "action": {"type": "process_results", "task": f"综合分析以下结果并生成最终答案：{task_description}"},
                        "result": {"success": False, "error": "force process_results"},
                    })

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

        # B: 异步写经验
        result_payload = {
            "success": success, "rounds": round_num,
            "total_subtasks": total_subtasks, "react_history": context_history,
        }
        asyncio.ensure_future(self._store_experience(task_description, result_payload))

        # ★: 自我进化触发检查
        if self.user_id:
            try:
                from core.memory.self_evolution import get_evolution_engine
                asyncio.ensure_future(get_evolution_engine().check_and_evolve(self.user_id))
            except Exception:
                pass

        return {
            "success": success,
            "results": all_results,
            "rounds": round_num,
            "total_subtasks": total_subtasks,
            "react_history": context_history,
        }

    # ── B: 任务经验写入 ────────────────────────────────────────────────

    async def _store_experience(self, task: str, result: dict) -> None:
        """任务完成后异步写入经验到向量库"""
        if not self.vm or not self.user_id:
            return
        success = result.get("success", False)
        rounds = result.get("rounds", 0)
        total_sub = result.get("total_subtasks", 0)
        strategies = set()
        for h in result.get("react_history", []):
            strategies.add(h.get("action_type", ""))
        used = ", ".join(s for s in strategies if s) or "direct"
        task_type = "分析"
        if any(kw in task for kw in ["搜索", "查找", "调研", "热搜"]):
            task_type = "搜索调研"
        elif any(kw in task for kw in ["写", "创建", "保存", "生成"]):
            task_type = "生成创作"
        elif any(kw in task for kw in ["代码", "执行", "运行", "python"]):
            task_type = "代码执行"
        elif any(kw in task for kw in ["分析", "对比", "总结", "翻译"]):
            task_type = "分析处理"
        content = (
            f"[{task_type}] 使用 {used} 策略，{rounds} 轮完成，"
            f"{total_sub}个子任务，{'成功' if success else '失败'}。"
            f"任务: {task[:100]}"
        )
        try:
            self.vm.add_memory(
                user_id=self.user_id, content=content, category="experience",
                metadata={
                    "task_type": task_type, "strategy": used,
                    "rounds": rounds, "success": str(success),
                    "agent": self.name,
                },
            )
        except Exception as e:
            logger.debug(f"写入经验失败: {e}")

    async def _react_think(self, task_description: str, history: List[Dict],
                           results: List[Dict], round_num: int) -> Dict:
        """ReAct Thought 阶段：分析状态，决定下一步"""

        # ===== 上下文压缩：5层压缩架构 =====
        try:
            if history and len(history) > 3:
                compactor = get_compactor()
                # Convert history to message format for compression
                history_msgs = [{"role": "assistant", "content": str(h)} for h in history]
                # Update assistant timestamp for time-based MC
                compactor.update_assistant_timestamp()
                # Run 5-layer compaction
                compressed = compactor.compact(history_msgs)
                # Extract compressed history back
                history = [h for h in history if any(c.get("content", "").startswith(str(h)[:50]) for c in compressed if c.get("role") == "assistant")]
        except Exception:
            pass

        history_text = ""
        if history:
            history_lines = []
            for h in history[-3:]:
                history_lines.append(
                    f"轮次{h['round']}: 思考={h['thought'][:100]}, "
                    f"行动={h['action_type']}, 结果={'成功' if h['result'].get('success') else '失败'}"
                )
            history_text = "\n".join(history_lines)

        if history:
            last_batch = [h for h in history[-2:] if h["action_type"] in ("batch_delegate", "delegate")]
            if last_batch and results:
                history_text += "\n→ 上一轮是 delegate，本轮必须 process_results"

        results_text = ""
        if results:
            # 最近一次 action 类型
            last_action = history[-1]["action_type"] if history else None
            has_delegate_recently = last_action in ("delegate", "batch_delegate")
            # 提取已有结果的关键内容
            result_summaries = []
            for r in results[-3:]:
                data = r.get("result", {})
                if isinstance(data, dict):
                    if "batch_results" in data:
                        for br in data["batch_results"][:3]:
                            br_data = br.get("result", {})
                            if isinstance(br_data, dict):
                                c = br_data.get("tool_result_summary", br_data.get("content", ""))
                                if c:
                                    result_summaries.append(c[:200])
                    else:
                        c = data.get("content", data.get("result", data.get("tool_result_summary", "")))
                        if c:
                            result_summaries.append(str(c)[:200])
            if result_summaries:
                results_text = (
                    f"\n【已有结果】\n" + "\n".join(result_summaries)
                )
            else:
                results_text = f"\n已完成 {len(results)} 个子任务"

        # 动态获取可用工具列表（V2 ToolRegistry + MCP）
        tool_hints = ""
        try:
            tools = await self._get_tools_for_task(task_description)
            if tools:
                tool_names = []
                for t in tools:
                    fn = t.get("function", {})
                    name = fn.get("name", "?")
                    desc = fn.get("description", "")[:60]
                    tool_names.append(f"  - {name}: {desc}")
                tool_hints = "\n【Worker 可用工具】\n" + "\n".join(tool_names[:20])
        except Exception:
            pass

        # A: 获取用户上下文（画像 + 相关记忆）
        user_context_str = ""
        if self.user_id:
            try:
                from core.memory.memory_middleware import get_memory_middleware
                mw = get_memory_middleware()
                # V1-C1 fix: run_until_complete 在运行中的事件循环里会 RuntimeError
                #           被外层 except 吞掉导致 user_context 永远空，改用 await
                user_context_str = await mw.get_user_context(self.user_id, task_description)
            except Exception:
                pass

        # B: 检索知识库 + 历史经验
        experience_hints = ""
        if self.vm:
            try:
                # 搜共享知识库（user_id=None）和个人经验
                shared = self.vm.search_memories(
                    query=task_description, user_id=None, top_k=3
                )
                personal = []
                if self.user_id:
                    personal = self.vm.search_memories(
                        query=task_description, user_id=self.user_id, top_k=3
                    )
                combined = (shared or []) + (personal or [])
                seen = set()
                unique = []
                for m in combined:
                    cid = m.get("id", "")
                    if cid not in seen:
                        seen.add(cid)
                        unique.append(m)
                if unique:
                    lines = []
                    for m in unique[:5]:
                        cat = m.get("metadata", {}).get("category", "")
                        prefix = "💡" if cat == "insight" else "📋"
                        lines.append(f"{prefix} {m['content'][:200]}")
                    if lines:
                        experience_hints = "\n【知识库 + 历史经验参考】\n" + "\n".join(lines)
            except Exception as e:
                logger.debug(f"检索知识/经验失败: {e}")

        # 注入用户上下文到任务描述
        full_task = task_description
        if user_context_str:
            full_task = f"{task_description}\n\n{user_context_str}\n\n请根据以上用户信息回答。"

        # 可用 skill 列表
        skill_hints = ""
        try:
            pool_info = getattr(self, '_pool', None)
            if pool_info is not None:
                skills = list(pool_info._agent_configs.keys()) if hasattr(pool_info, '_agent_configs') else []
            else:
                from core.engine.config_loader import register_agents_from_config
                skills = [c["id"] for c in register_agents_from_config()]
            if skills:
                skill_hints = f"\n可用 skill: {', '.join(skills)}\n当前匹配 skill: {self._current_skill_id or 'general'}\n\n"
        except Exception:
            skill_hints = "\n可用 skill: project_analyzer, web_scraper, data_analyst, general\n\n"

        system = (
            "你是队长Agent。严格按以下三轮流程执行，不得跳过任何一步：\n\n"
            "第1轮 → delegate（或 batch_delegate）给 Worker 执行\n"
            "第2轮 → process_results 综合分析 Worker 返回的结果\n"
            "第3轮 → done 结束\n\n"
            "格式：\n"
            'delegate: {"done":false,"action":{"type":"delegate","task":"子任务","skill":"skill名"}}\n'
            'batch_delegate: {"done":false,"action":{"type":"batch_delegate","tasks":[{"task":"子任务1","skill":"skill名"},...]}}\n'
            'process_results: {"done":false,"action":{"type":"process_results","task":"综合分析"}}\n'
            'done: {"done":true,"thinking":"已完成..."}\n\n'
            "规则：\n"
            "- 除非用户要求保存文件，否则不要自己决定写文件\n"
            "- 用户要求保存到桌面 → delegate 的 task 里写明用 write_file\n"
            "- 不得跳过 process_results 直接 done\n"
            "输出纯JSON，不要其他内容。"
        ) + skill_hints

        user = f"任务: {full_task}\n\n历史:\n{history_text or '无'}\n\n{results_text}\n\n第{round_num}轮，请思考下一步："

        result = await _llm_json(system, user, max_tokens=500)

        if not result or not isinstance(result, dict):
            return {"done": True, "thinking": "LLM 响应异常，结束任务"}

        return result

    async def _react_act(self, action_type: str, action: Dict, 
                         workers: List[LLMAgent], original_task: str,
                         context_history: List[Dict] = None) -> Dict:
        """ReAct Action 阶段：执行具体行动"""
        
        if action_type == "tool":
            # ponytail: Leader 直接调用工具（设计上"只决策不执行"，但简单任务免去 Worker 分配开销）
            # 仅用于"查天气"等单步场景，复杂任务仍走 delegate/batch_delegate
            tool_name = action.get("tool_name", "")
            args = action.get("args", {})
            
            if not tool_name:
                return {"success": False, "error": "未指定工具名称"}
            
            result = await self._execute_tool(tool_name, args)
            return result

        elif action_type == "delegate":
            # 分配子任务给 Worker
            task = action.get("task", original_task)
            skill_id = action.get("skill", self._current_skill_id or "general")
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
                "skill_id": skill_id,
            }

        elif action_type == "batch_delegate":
            # 批量分配子任务给多个 Worker 并行执行
            tasks = action.get("tasks", [])
            if not tasks:
                # 如果没有提供任务列表，则分解原始任务
                tasks = await self._decompose_task(original_task)
            
            if not tasks:
                return {"success": False, "error": "无可用子任务"}
            
            # 规范化任务：提取 (task_str, skill_id) 对
            task_skills = []
            normalized_tasks = []
            for task_item in tasks:
                if isinstance(task_item, dict):
                    t = task_item["task"]
                    s = task_item.get("skill", self._current_skill_id or "general")
                else:
                    t = task_item
                    s = self._current_skill_id or "general"
                normalized_tasks.append(t)
                task_skills.append(s)
            
            # 使用轮询分配子任务给 Worker
            active_workers = workers[:self.active_worker_count]
            assignments = self._assign(normalized_tasks, active_workers)
            
            # 并行执行所有子任务
            batch_results = await self._execute_batch(assignments, workers)
            
            # 统计成功数量
            success_count = sum(1 for r in batch_results if r.get("success"))
            
            # 有成功结果 → 返回结果，由 Leader 在下一轮决定是否需要 process_results 合成
            if success_count > 0:
                return {
                    "success": True,
                    "result": {
                        "batch_results": batch_results,
                        "success_count": success_count,
                        "total_count": len(batch_results),
                    },
                    "workers": [r.get("worker") for r in batch_results],
                    "skill_ids": task_skills,
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
                "skill_ids": task_skills,
            }

        elif action_type == "process_results":
            # 处理前一轮的delegate/batch_delegate结果
            # ponytail: 直接返回结果给 leader，不委派给 worker（避免 worker 重复读文件覆盖合成结果）
            prev_results = []
            for h in reversed(context_history):
                atype = h.get("action_type")
                if atype in ("batch_delegate", "delegate") and h.get("result", {}).get("success"):
                    if atype == "batch_delegate":
                        prev_results = h["result"].get("result", {}).get("batch_results", [])
                    else:
                        prev_results = [h["result"]]
                    break
            
            if not prev_results:
                return {"success": False, "error": "没有找到可处理的前一轮结果"}
            
            # 提取各 worker 的 tool_result_summary
            summaries = []
            for r in prev_results[:5]:
                data = r.get("result", {})
                if isinstance(data, dict):
                    if "batch_results" in data:
                        for br in data["batch_results"][:3]:
                            br_data = br.get("result", {})
                            if isinstance(br_data, dict):
                                c = br_data.get("tool_result_summary", br_data.get("content", ""))
                                if c:
                                    summaries.append(c[:500])
                    else:
                        cc = data.get("content", "") or ""
                        tc = data.get("tool_result_summary", "") or ""
                        c = cc or tc
                        if c:
                            summaries.append(str(c)[:500])
            
            combined = "\n\n".join(summaries) if summaries else "无有效结果"

            # ponytail: 只有任务显式要求保存到桌面时才自动写文件
            _should_write = (
                "保存到桌面" in original_task or "保存到 ~/Desktop" in original_task
                or "保存到 ~/桌面" in original_task
            )
            if self.tool_registry and _should_write:
                import re as _re
                _path = None
                _name_match = _re.search(r'(?:文件名为?|file_name|filename)\s*[:：]?\s*([\w.\-]+)', original_task)
                if _name_match:
                    _path = f"~/Desktop/{_name_match.group(1)}"
                if not _path:
                    _abs_match = _re.search(r'保存到\s*([~/][\w/.\-]+)', original_task)
                    if _abs_match:
                        _path = _abs_match.group(1)
                if _path:
                    try:
                        _handler = self.tool_registry.get_handler("write_file")
                        if _handler:
                            await _handler({"path": _path, "content": combined})
                            logger.info(f"📝 process_results 自动写入文件: {_path}")
                            combined = f"✅ 报告已保存到 {_path}\n\n{combined[:200]}...\n\n（完整内容见文件）"
                    except Exception as _e:
                        logger.warning(f"自动写文件失败: {_e}")

            return {
                "success": True,
                "result": {"tool_result_summary": combined, "content": combined},
                "worker": self.name,
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
        if len(raw_subtasks) != len(subtasks):
            logger.debug(f"_decompose_task: 过滤了 {len(raw_subtasks) - len(subtasks)} 个非字符串子任务")
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
        # Worker 池化管理 — skill_id → [空闲Worker]
        self._worker_pool: Dict[str, List[LLMAgent]] = {}
        self._busy_workers: Dict[str, LLMAgent] = {}  # 忙碌中的Worker
        self._pool_lock = asyncio.Lock()  # 池操作锁
        self._agent_configs: Dict[str, dict] = {}  # agents.yml 配置缓存

    def _load_agent_configs(self):
        """加载 agents.yml 中的 skill 配置缓存"""
        if self._agent_configs:
            return
        try:
            from core.engine.config_loader import register_agents_from_config
            for cfg in register_agents_from_config():
                self._agent_configs[cfg["id"]] = cfg
        except Exception as e:
            logger.error("加载 agents.yml 配置失败，Worker 将使用默认配置: %s", e)

    async def _ensure_tool_registry(self):
        """确保 V1 工具注册表已初始化"""
        if self._tool_registry is None:
            try:
                from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
                self._tool_registry = V1ToolRegistry()
                await self._tool_registry.discover_all()
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
        self._load_agent_configs()
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

    # ─── Worker 池化管理 ──────────────────────────────────────────────

    async def get_worker(self, skill_id: str = "general", leader_name: str = None) -> Optional[LLMAgent]:
        """从池中获取一个空闲Worker（按 skill_id 池化）

        Args:
            skill_id: 技能类型ID，对应 agents.yml 中的 agent id
            leader_name: 主Agent名称（用于设置Worker的leader_name）

        Returns:
            空闲Worker，或 None（池空且达到上限）
        """
        await self._ensure_tool_registry()
        self._load_agent_configs()
        async with self._pool_lock:
            if skill_id not in self._worker_pool:
                self._worker_pool[skill_id] = []

            # 优先从池中获取
            if self._worker_pool[skill_id]:
                worker = self._worker_pool[skill_id].pop()
                worker._update_state("idle", "从池中取出")
                if leader_name:
                    worker.leader_name = leader_name
                self._busy_workers[worker.name] = worker
                logger.debug(f"📦 从池中取出 Worker: {worker.name}")
                return worker

            # 池空且在容量上限内，创建新Worker
            # ponytail: 硬上限 10 个，避免内存泄漏
            total_workers = sum(len(v) for v in self._worker_pool.values()) + len(self._busy_workers)
            if total_workers < 10:
                config = self._agent_configs.get(skill_id, {})
                worker = LLMAgent(
                    name=f"队员_{skill_id}_{uuid4().hex[:6]}",
                    role=AgentRole.WORKER,
                    role_prompt=config.get("role_prompt", ""),
                    tool_restrictions=None,  # ponytail: V1 不限制工具（agents.yml tools 为 V2 MCP 名）
                    tool_registry=self._tool_registry,
                )
                worker.skill_id = skill_id
                if leader_name:
                    worker.leader_name = leader_name

                self._all_agents[worker.name] = worker
                self._busy_workers[worker.name] = worker
                logger.debug(f"✨ 创建新 Worker: {worker.name} (skill={skill_id})")
                return worker

            logger.warning("Worker池已满(%d)，无法获取更多Worker", total_workers)
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

            skill_id = getattr(worker, 'skill_id', "general")
            if skill_id not in self._worker_pool:
                self._worker_pool[skill_id] = []

            # 放回池中
            if worker not in self._worker_pool[skill_id]:
                self._worker_pool[skill_id].append(worker)
                logger.debug(f"📦 Worker 归还池: {worker.name} (skill={skill_id})")


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
                await self.return_worker(agent)  # return_worker 内部已记录日志

    def get_agent(self, name: str) -> Optional[LLMAgent]:
        return self._all_agents.get(name)

    def get_all_agents(self) -> List[LLMAgent]:
        return list(self._all_agents.values())
