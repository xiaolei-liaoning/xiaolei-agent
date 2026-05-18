"""
BaseAgent - 真正的智能体基类

每个Agent具备：
- 独立的心智 (Mind) - 思考、决策、反思
- 独立的记忆 (Memory) - 短期、长期、情景记忆
- 独立的能力 (Capabilities) - 技能、工具、知识
- 独立的生命周期 (Lifecycle) - 注册、发现、执行、注销
- 独立的通信能力 - 主动与其他Agent沟通
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
import uuid

logger = logging.getLogger(__name__)

# MCP 工具缓存: {tool_name_lower: (server_name, tool_name)}
_MCP_TOOL_CACHE: Optional[Dict[str, tuple]] = None


async def _build_mcp_tool_cache() -> Dict[str, tuple]:
    """扫描 mcp/*.py 建立 tool→server 映射缓存"""
    import os, importlib.util as iutil
    cache = {}
    mcp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "mcp")
    if not os.path.isdir(mcp_dir):
        return cache
    for fname in sorted(os.listdir(mcp_dir)):
        if not fname.endswith("_mcp_server.py"):
            continue
        modname = fname[:-3]
        spec = iutil.spec_from_file_location(modname, os.path.join(mcp_dir, fname))
        if not spec or not spec.loader:
            continue
        try:
            mod = iutil.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            continue
        server_name = modname.replace("_mcp_server", "").replace("_", "-")
        script_path = fname
        for t in getattr(mod, "TOOLS", []):
            tn = t.get("name", "")
            desc = t.get("description", "")
            if tn:
                cache[tn.lower()] = (server_name, script_path, desc)
    logger.info(f"MCP 缓存构建完成: {len(cache)} 个工具")
    return cache


class CommunicationTopic(Enum):
    """通信主题"""
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    VULNERABILITY_FOUND = "vuln_found"
    DATA_ANALYZED = "data_analyzed"
    BROADCAST = "broadcast"
    AGENT_MESSAGE = "agent_message"


class AgentState(Enum):
    """Agent状态"""
    CREATED = "created"           # 创建
    REGISTERED = "registered"     # 已注册
    IDLE = "idle"                 # 空闲
    READY = "ready"               # 准备就绪
    RUNNING = "running"           # 执行中
    WAITING = "waiting"           # 等待中
    COMPLETED = "completed"       # 完成任务
    FAILED = "failed"             # 执行失败
    STOPPED = "stopped"           # 已停止


class AgentType(Enum):
    """Agent类型
    
    所有类型均已实现对应的 Agent 类：
    - EXPERT → ExpertAgent: 领域知识专家
    - COORDINATOR → CoordinatorAgent: 协作流程控制
    - MONITOR → MonitorAgent: 执行状态追踪
    """
    MASTER = "master"             # 主Agent：任务分解、结果聚合
    WORKER = "worker"           # 执行Agent：负责具体执行
    REVIEWER = "reviewer"       # 评审Agent：质量把关
    EXPERT = "expert"           # 专家Agent：领域知识
    COORDINATOR = "coordinator" # 协调Agent：流程控制
    MONITOR = "monitor"         # 监控Agent：状态追踪


@dataclass
class Capability:
    """Agent能力定义"""
    name: str                                     # 能力名称
    description: str                              # 能力描述
    keywords: List[str] = field(default_factory=list)  # 匹配关键词
    expertise_level: float = 0.5                  # 专业等级 (0-1)
    max_concurrent_tasks: int = 1                 # 最大并发任务数
    avg_execution_time: float = 10.0              # 平均执行时间（秒）
    success_rate: float = 0.9                     # 历史成功率
    preferred_tools: List[str] = field(default_factory=list)  # 偏好工具

    def match_score(self, task_keywords: List[str]) -> float:
        """计算与任务的匹配分数"""
        keyword_matches = sum(1 for kw in task_keywords if kw in self.keywords)
        return (keyword_matches / max(len(task_keywords), 1)) * self.expertise_level


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable
    permissions: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    is_concurrency_safe: bool = False


@dataclass
class Thought:
    """思考过程"""
    reasoning: str                       # 推理过程
    plan: List[str]                     # 执行计划
    confidence: float                   # 置信度
    alternatives: List[str] = field(default_factory=list)  # 备选方案


@dataclass
class Reflection:
    """反思结果"""
    success: bool                       # 是否成功
    lessons_learned: List[str]         # 经验教训
    improvements: List[str]             # 改进建议
    performance_metrics: Dict[str, float]  # 性能指标


@dataclass
class AgentMetrics:
    """Agent性能指标"""
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_execution_time: float = 0.0
    total_execution_time: float = 0.0
    last_task_time: Optional[float] = None
    current_load: float = 0.0
    priority: float = 1.0

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return self.tasks_completed / total if total > 0 else 0.0


class Mind:
    """Agent心智 - 思考引擎"""

    def __init__(self, agent: 'BaseAgent'):
        self.agent = agent
        self.thinking_history: List[Thought] = []
        self.llm_router = None
        self.prompt_manager = None
        self._init_dependencies()

    def _init_dependencies(self):
        """初始化依赖（延迟导入避免循环依赖）"""
        try:
            from core.engine.llm_backend import get_llm_router
            from core.multi_agent_v2.agents.prompts.agent_prompts import get_prompt_manager
            self.llm_router = get_llm_router()
            self.prompt_manager = get_prompt_manager()
            logger.info(f"Mind组件依赖初始化成功 (Agent: {self.agent.agent_id})")
        except Exception as e:
            logger.warning(f"Mind组件依赖初始化失败: {e}")

    async def think(self, task: 'Task') -> Thought:
        """思考：LLM驱动，断线自动重连，失败反问用户"""
        logger.info(f"Agent {self.agent.agent_id} 正在思考任务: {task.type}")

        if not self.llm_router or not self.prompt_manager:
            return await self._think_simulated(task)

        # 自动重连：最多3次
        last_error = None
        for attempt in range(3):
            try:
                return await self._think_with_llm(task)
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM思考失败(第{attempt+1}次): {e}")
                if attempt < 2:
                    await asyncio.sleep(1)  # 等待后重试
                    continue

        # 3次全失败 → 反问用户（短暂等待，无响应直接降级）
        answer = await self.agent.ask_user(
            f"LLM断线重连3次仍失败({last_error[:60]})，是否降级使用模拟思考？",
            context=f"任务类型: {task.type}",
            timeout=3,  # 非交互环境快速降级
        )
        if answer == "retry":
            # 用户要求再试一次
            try:
                return await self._think_with_llm(task)
            except Exception:
                pass
        elif answer == "cancel":
            raise

        # 降级到模拟思考
        return await self._think_simulated(task)

    async def _think_with_llm(self, task: 'Task') -> Thought:
        """使用LLM进行真实思考"""
        # 获取当前Agent类型的提示词
        agent_type = self.agent.agent_type.value
        prompt = self.prompt_manager.get_prompt(agent_type)
        
        if not prompt:
            logger.warning(f"未找到 {agent_type} 类型的提示词，使用通用提示词")
            return await self._think_simulated(task)

        # 构建思考提示词
        thinking_prompt = prompt.thinking_prompt.format(
            task_description=task.description,
            task_id=task.task_id,
            task_type=task.type,
            task_result="待思考",
            plan="待制定...",
            conclusion="待定",
        )

        # 查重提醒注入
        try:
            _advice = self.agent._tracker.advice(task.description)
            if _advice:
                thinking_prompt += f"\n\n{_advice}"
        except Exception:
            pass

        # RAG 知识注入 — 思考前查知识库
        try:
            from core.search.rag_search_engine import RAGSearchEngine
            engine = RAGSearchEngine()
            rag_result = await engine.search_and_learn(
                query=task.description, user_id=1, max_results=3, learn=False
            )
            if rag_result and rag_result.get("results"):
                knowledge = rag_result["results"]
                thinking_prompt += f"\n\n### 相关知识\n{knowledge[:2000]}"
        except Exception as e:
            logger.debug(f"RAG 知识注入失败: {e}")

        # 构建完整的消息列表
        messages = [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": thinking_prompt}
        ]

        # 调用LLM（带超时）
        try:
            response = await asyncio.wait_for(
                self.llm_router.chat(messages, temperature=0.7, max_tokens=1500),
                timeout=25,
            )
        except asyncio.TimeoutError:
            logger.warning("LLM 响应超时")
            raise TimeoutError("LLM 响应超时")
        except Exception as e:
            logger.warning(f"LLM chat 失败: {e}")
            return await self._think_simulated(task)
        
        # 解析LLM响应
        return self._parse_llm_response(response, task)

    def _parse_llm_response(self, response: str, task: 'Task') -> Thought:
        """解析LLM响应为Thought对象"""
        # 尝试提取思考内容
        reasoning = response
        
        # 尝试从响应中提取计划步骤
        plan = []
        lines = response.split('\n')
        for line in lines:
            # 匹配步骤格式："1. xxx" 或 "步骤1: xxx"
            if line.strip():
                plan.append(line.strip())
                if len(plan) >= 10:  # 限制最大步骤数
                    break
        
        # 计算置信度（基于响应长度和质量）
        confidence = min(0.5 + len(response) / 2000, 0.99)
        
        # 如果计划为空，使用默认计划
        if not plan:
            plan = [f"步骤{i+1}: 执行任务" for i in range(min(task.estimated_steps, 5))]

        return Thought(
            reasoning=reasoning,
            plan=plan[:5],  # 最多5个步骤
            confidence=confidence
        )

    async def _think_simulated(self, task: 'Task') -> Thought:
        """模拟思考过程（LLM 不可用时的降级方案）"""
        reasoning = await self._reason_about_task(task)
        plan = await self._create_plan(task)
        confidence = await self._calculate_confidence(task)
        thought = Thought(reasoning=reasoning, plan=plan, confidence=confidence)
        self.thinking_history.append(thought)
        return thought

    async def _reason_about_task(self, task: 'Task') -> str:
        return f"分析任务 '{task.type}': 需要调用 {len(self.agent.capabilities)} 个能力"

    async def _create_plan(self, task: 'Task') -> list:
        return [f"步骤{i+1}: 执行任务相关操作" for i in range(min(task.estimated_steps, 5))]

    async def _calculate_confidence(self, task: 'Task') -> float:
        base = sum(c.expertise_level for c in self.agent.capabilities) / max(len(self.agent.capabilities), 1)
        return min(base * 0.9, 0.99)


class MemorySystem:
    """Agent记忆系统 - 短期、长期、情景记忆"""

    def __init__(self, agent: 'BaseAgent'):
        self.agent = agent
        self.short_term: Dict[str, Any] = {}    # 短期记忆
        self.long_term: List[Dict[str, Any]] = []  # 长期记忆
        self.episodic: List[Dict[str, Any]] = []   # 情景记忆

    async def remember(self, key: str, value: Any) -> None:
        """记忆：存储信息"""
        self.short_term[key] = {
            "value": value,
            "timestamp": time.time()
        }

    async def recall(self, key: str) -> Optional[Any]:
        """回忆：检索信息"""
        if key in self.short_term:
            return self.short_term[key]["value"]
        return None

    async def forget(self, key: str) -> None:
        """遗忘：删除信息"""
        self.short_term.pop(key, None)

    async def store_episode(self, episode: Dict[str, Any]) -> None:
        """存储情景记忆"""
        self.episodic.append({
            **episode,
            "timestamp": time.time()
        })

    async def get_recent_episodes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的情景记忆"""
        return self.episodic[-limit:]

    async def consolidate_to_long_term(self) -> None:
        """将短期记忆整合到长期记忆"""
        # 根据重要性和访问频率决定是否保留
        important_memories = [
            (k, v) for k, v in self.short_term.items()
            if v.get("access_count", 0) > 3
        ]

        for key, value in important_memories:
            self.long_term.append({
                "key": key,
                "value": value["value"],
                "timestamp": time.time()
            })

        # 限制长期记忆大小
        if len(self.long_term) > 1000:
            self.long_term = self.long_term[-1000:]


class BaseAgent(ABC):
    """Agent基类 - 真正的智能体"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_type: AgentType = AgentType.WORKER,
        name: Optional[str] = None,
        description: str = ""
    ):
        # 身份标识
        self.agent_id = agent_id or str(uuid.uuid4())
        self.agent_type = agent_type
        self.agent_name = name or f"{agent_type.value}_{self.agent_id[:8]}"
        self.description = description

        # 能力定义
        self.capabilities: List[Capability] = []
        self.tools: Dict[str, Tool] = {}

        # 自治系统
        self.mind = Mind(self)
        self.memory = MemorySystem(self)

        # 生命周期状态
        self.state = AgentState.CREATED
        self.health_score: float = 1.0
        self.current_load: float = 0.0
        self.max_load: float = 1.0

        # 性能指标
        self.metrics = AgentMetrics()

        # 上下文引用
        self.context_center: Optional[Any] = None
        self.task_history: List['Task'] = []

        # SharedBus 引用（惰性初始化）
        self._bus: Optional[Any] = None

        # 查重跟踪器（防止兜圈子）
        from core.repetition_tracker import RepetitionTracker
        self._tracker = RepetitionTracker(threshold=3)

        # 锁
        self._state_lock = asyncio.Lock()

        logger.info(f"Agent创建: {self.agent_id} ({self.agent_type.value})")

    async def _ensure_bus(self) -> None:
        """惰性初始化 SharedBus 并订阅消息"""
        if self._bus is not None:
            return
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, Message, MessageType
            self._bus = get_shared_bus()
            # 订阅直接消息
            await self._bus.subscribe(f"agent:{self.agent_id}", self._on_bus_direct_message)
            logger.info(f"Agent {self.agent_id} SharedBus 初始化成功")
        except Exception as e:
            logger.warning(f"Agent {self.agent_id} SharedBus 初始化失败: {e}")

    async def _on_bus_direct_message(self, message: 'Message') -> None:
        """处理 SharedBus 直接消息"""
        logger.info(f"Agent {self.agent_id} 收到总线消息: {message.type.value}")
        await self.memory.store_episode({
            "type": "bus_message",
            "message_type": message.type.value,
            "sender": message.sender,
            "payload": message.payload,
        })

    async def register(self) -> None:
        """注册到SharedBus"""
        async with self._state_lock:
            if self.state != AgentState.CREATED:
                raise ValueError(f"Agent {self.agent_id} 已注册，不能重复注册")
            self.state = AgentState.REGISTERED
            await self._ensure_bus()
            logger.info(f"Agent注册: {self.agent_id} (SharedBus)")

    async def start(self) -> None:
        """启动Agent"""
        async with self._state_lock:
            if self.state != AgentState.REGISTERED:
                raise ValueError(f"Agent {self.agent_id} 未注册")

            self.state = AgentState.IDLE
            logger.info(f"Agent启动: {self.agent_id}")

    async def stop(self) -> None:
        """停止Agent"""
        async with self._state_lock:
            self.state = AgentState.STOPPED
            logger.info(f"Agent停止: {self.agent_id}")

    async def set_ready(self) -> None:
        """设置Agent为就绪状态"""
        async with self._state_lock:
            if self.state != AgentState.IDLE:
                raise ValueError(f"Agent {self.agent_id} 不在空闲状态")

            self.state = AgentState.READY

    async def receive_task(self, task: 'Task') -> None:
        """接收任务"""
        async with self._state_lock:
            if self.current_load >= self.max_load:
                raise RuntimeError(f"Agent {self.agent_id} 负载已满")

            self.current_load += task.complexity
            self.state = AgentState.READY
            self.task_history.append(task)

            logger.info(f"Agent {self.agent_id} 接收任务: {task.task_id}")

    async def think(self, task: 'Task') -> Thought:
        """思考：理解任务、制定计划"""
        return await self.mind.think(task)

    @abstractmethod
    async def execute(self, task: 'Task') -> 'ActionResult':
        """执行任务（子类必须实现）"""
        pass

    async def act(self, plan: List[str]) -> 'ActionResult':
        """执行：调用工具（只读并行 + 写串行，参考Claude Code设计）"""
        logger.info(f"Agent {self.agent_id} 开始执行计划 ({len(plan)} 步)")

        start_time = time.time()
        results = []

        try:
            # 分拆：只读(并发安全)步骤并行，写步骤串行
            safe_steps = []
            serial_steps = []
            for step in plan:
                kw = ["读取", "查询", "搜索", "查看", "读", "get", "list", "search",
                       "read", "check", "分析", "统计"]
                if any(k in step for k in kw):
                    safe_steps.append(step)
                else:
                    serial_steps.append(step)

            # 并行执行只读步骤
            if safe_steps:
                safe_results = await asyncio.gather(*[
                    self._execute_step(s) for s in safe_steps
                ], return_exceptions=True)
                for step, res in zip(safe_steps, safe_results):
                    results.append((step, {"success": not isinstance(res, Exception),
                                           "result": res if not isinstance(res, Exception) else str(res)}))
                    if not isinstance(res, Exception):
                        self._tracker.record(
                            self.task_history[-1].description if self.task_history else "unknown",
                            step, res,
                        )

            # 串行执行写步骤
            for step in serial_steps:
                result = await self._execute_step(step)
                results.append((step, result))
                self._tracker.record(
                    self.task_history[-1].description if self.task_history else "unknown",
                    step, result,
                )

            # 记录到情景记忆
            for step, result in results:
                await self.memory.store_episode({
                    "step": step,
                    "result": result,
                    "agent_id": self.agent_id
                })

            # 执行成功
            execution_time = time.time() - start_time
            self.metrics.tasks_completed += 1
            self.metrics.total_execution_time += execution_time
            self.metrics.avg_execution_time = (
                self.metrics.total_execution_time / self.metrics.tasks_completed
            )

            ar = ActionResult(
                success=True,
                output=results,
                execution_time=execution_time
            )

            # 发布执行结果到 SharedBus
            await self._publish_to_bus(ar, results)

            return ar

        except Exception as e:
            logger.error(f"Agent {self.agent_id} 执行失败: {e}")
            self.metrics.tasks_failed += 1

            ar = ActionResult(
                success=False,
                error=str(e),
                partial_results=results
            )

            # 发布失败到 SharedBus
            await self._publish_to_bus(ar, results)

            return ar

        finally:
            self.current_load = max(0, self.current_load - 0.3)

    async def _publish_to_bus(self, ar: 'ActionResult', step_results: list) -> None:
        """发布执行结果到 SharedBus"""
        try:
            await self._ensure_bus()
            if not self._bus:
                return
            from core.multi_agent_v2.infrastructure.shared_bus import Message, MessageType
            task_id = self.task_history[-1].task_id if self.task_history else "unknown"
            msg = Message(
                type=MessageType.TASK_PROGRESS if ar.success else MessageType.TASK_FAILED,
                sender=self.agent_id,
                topic=f"task:{task_id}",
                payload={
                    "task_id": task_id,
                    "agent_id": self.agent_id,
                    "agent_type": self.agent_type.value,
                    "success": ar.success,
                    "steps": len(step_results),
                    "execution_time": ar.execution_time,
                    "error": ar.error,
                }
            )
            await self._bus.publish(msg.topic, msg)
        except Exception as e:
            logger.debug(f"发布到 SharedBus 失败: {e}")

    async def _execute_step(self, step: str) -> Any:
        """执行单个步骤 — 调 MCP 工具 / RAG 搜索 / LLM

        路由逻辑：
        1. 搜索/查询类 → RAGSearchEngine
        2. 工具调用类 → MCPClientManager
        3. 其他 → LLM 直接生成
        4. 全部失败 → sleep(0.1) 兜底
        """
        task_id = self.task_history[-1].task_id if self.task_history else "unknown"
        start = time.time()

        try:
            # ─── 搜索 / 查询类 ─────────────────────────────
            kw_search = ["搜索", "查询", "查找", "搜", "找", "search", "lookup"]
            if any(k in step for k in kw_search):
                try:
                    from core.search.rag_search_engine import RAGSearchEngine
                    engine = RAGSearchEngine()
                    result = await engine.search_and_learn(
                        query=step, user_id=1, max_results=3, learn=True
                    )
                    elapsed = (time.time() - start) * 1000
                    self._log_execution("rag_search", {"query": step}, result, elapsed)
                    return {"step": step, "status": "completed", "result": result}
                except Exception as e:
                    logger.warning(f"RAG 搜索失败: {e}")

            # ★ A级优化：text-analyzer-mcp 内联（字符/词频/句子统计）
            kw_text_analysis = ["统计", "字数", "词数", "字符", "分析", "关键词", 
                              "count", "char", "word", "sentence", "keyword"]
            if any(k in step for k in kw_text_analysis):
                try:
                    import re
                    from collections import Counter
                    
                    text = step
                    analysis_result = {}
                    
                    # 提取引号中的文本
                    quote_match = re.search(r'["""\'""\'](.+?)["""\'""\']', step)
                    if quote_match:
                        text = quote_match.group(1)
                    
                    # 字符统计（去空格）
                    analysis_result["字符数"] = len(text.replace(" ", ""))
                    
                    # 词数统计（中英文）
                    chinese_chars = re.findall(r'[一-龥]', text)
                    english_words = re.findall(r'[a-zA-Z]+', text)
                    analysis_result["词数"] = len(chinese_chars) + len(english_words)
                    
                    # 句子数统计
                    sentences = re.split(r'[。！？.!?]', text)
                    analysis_result["句子数"] = len([s for s in sentences if s.strip()])
                    
                    # 关键词提取
                    chinese_words = re.findall(r'[一-龥]{2,4}', text)
                    english_words = re.findall(r'[a-zA-Z]{3,}', text)
                    all_words = chinese_words + english_words
                    stop_words = {'的', '了', '和', '是', '在', '我', '有', '个', '们', 'the', 'a', 'an', 'is', 'are'}
                    filtered = [w for w in all_words if w.lower() not in stop_words]
                    top_keywords = [w for w, _ in Counter(filtered).most_common(5)]
                    analysis_result["关键词"] = top_keywords
                    
                    result_str = f"文本分析结果：字符数={analysis_result['字符数']}, 词数={analysis_result['词数']}, 句子数={analysis_result['句子数']}, 关键词={analysis_result['关键词']}"
                    
                    elapsed = (time.time() - start) * 1000
                    self._log_execution("text_analyzer_inline", {"text": text[:50]}, analysis_result, elapsed)
                    return {"step": step, "status": "completed", "result": result_str, "tool": "text_analyzer_inline"}
                except Exception as e:
                    logger.debug(f"文本分析内联失败: {e}")

            # ─── 工具调用类（MCP） ─────────────────────────
            try:
                from core.mcp.mcp_client import mcp_client as mcp
                if not mcp._initialized:
                    await mcp.initialize()

                # 1. 先查已连接的服务器
                servers = await mcp.list_servers()
                found = None
                for server in servers:
                    tools = await mcp.list_tools(server)
                    for tool in tools:
                        tname = tool.get("name", "")
                        desc = tool.get("description", "")
                        if tname.lower() in step.lower() or any(
                            kw.lower() in desc.lower() for kw in step.split()
                        ):
                            found = (server, tname, {})
                            break
                    if found:
                        break

                # 2. 没找到 → 使用缓存快速查找本地MCP工具
                if not found:
                    # 构建缓存（首次调用）
                    global _MCP_TOOL_CACHE
                    if _MCP_TOOL_CACHE is None:
                        _MCP_TOOL_CACHE = await _build_mcp_tool_cache()
                    
                    # 在缓存中查找匹配的工具
                    step_lower = step.lower()
                    step_words = step.split()
                    for tool_name, (server_name, script, desc) in _MCP_TOOL_CACHE.items():
                        if tool_name in step_lower or any(
                            kw.lower() in desc.lower() for kw in step_words
                        ):
                            # 自动连接服务器
                            mcp_dir = os.path.join(
                                os.path.dirname(__file__), "..", "..", "..", "..", "mcp"
                            )
                            await mcp.connect_server(
                                server_name, "python", [script],
                                cwd=os.path.join(mcp_dir, script[:-3] + "_mcp_server.py"),
                            )
                            found = (server_name, tool_name, {})
                            break

                # 3. 执行
                if found:
                    server, tname, args = found
                    result_text = await mcp.call_tool(server, tname, args)
                    elapsed = (time.time() - start) * 1000
                    self._log_execution(f"mcp_{tname}",
                        {"server": server, "tool": tname}, result_text, elapsed)
                    return {"step": step, "status": "completed",
                            "result": result_text, "tool": tname}

                # ★ S级优化：本地MCP没找到 → fallback到 awesome-mcp (114个额外工具)
                if not found:
                    try:
                        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
                        
                        step_words = step.split()
                        search_results = []
                        
                        for keyword in step_words[:3]:
                            if len(keyword) >= 2:
                                results = awesome_mcp_manager.search_servers(keyword)
                                search_results.extend(results)
                        
                        seen = set()
                        unique_results = []
                        for r in search_results:
                            if r["name"] not in seen:
                                seen.add(r["name"])
                                unique_results.append(r)
                        
                        if unique_results:
                            server_info = unique_results[0]
                            server_name = server_info["name"]
                            
                            connect_result = await awesome_mcp_manager.quick_connect(server_name)
                            
                            if connect_result.get("success"):
                                tools = await mcp.list_tools(server_name)
                                if tools:
                                    tool = tools[0]
                                    tname = tool.get("name", "")
                                    if tname:
                                        result_text = await mcp.call_tool(server_name, tname, {})
                                        elapsed = (time.time() - start) * 1000
                                        self._log_execution(f"awesome_mcp_{tname}",
                                            {"server": server_name, "tool": tname, 
                                             "via": "awesome-mcp-fallback"}, 
                                            result_text, elapsed)
                                        return {"step": step, "status": "completed",
                                                "result": result_text, "tool": tname,
                                                "source": "awesome-mcp"}
                                        
                    except Exception as awesome_err:
                        logger.debug(f"awesome-mcp fallback 失败: {awesome_err}")

            except Exception as e:
                logger.debug(f"MCP 不可用: {e}")

        except Exception as e:
            logger.warning(f"执行步骤异常: {e}")

        # ─── 兜底 — 直接调用 LLM ─
        # 如果没有可用工具且不是搜索类任务，直接调用LLM生成答案
        try:
            from core.engine.llm_backend import get_llm_router
            llm_router = get_llm_router()
            
            if llm_router.is_available():
                prompt = f"请完成以下任务步骤：{step}"
                response = await llm_router.chat([{"role": "user", "content": prompt}],
                                                temperature=0.7, max_tokens=500)
                
                elapsed = (time.time() - start) * 1000
                self._log_execution("llm_fallback", {"step": step}, response, elapsed)
                return {"step": step, "status": "completed", "result": response, "tool": "llm"}
        except Exception as llm_e:
            logger.warning(f"LLM兜底调用失败: {llm_e}")
        
        # 最后兜底：返回失败
        elapsed = (time.time() - start) * 1000
        self._log_execution("failed", {"step": step}, "无可用工具且LLM不可用", elapsed)
        return {"step": step, "status": "failed", "error": "无可用工具或搜索失败"}

    def _log_execution(self, tool_name: str, params: dict,
                       result: Any, duration_ms: float) -> None:
        """记录执行日志到 ExecutionLogger"""
        try:
            from core.execution_logger import get_execution_logger
            logger_inst = get_execution_logger()
            task_id = self.task_history[-1].task_id if self.task_history else "unknown"
            logger_inst.log(
                tool_name=tool_name,
                params=params,
                result=str(result)[:2000],
                status="success",
                duration_ms=duration_ms,
                agent_type=self.agent_type.value,
            )
        except Exception as e:
            logger.debug(f"ExecutionLogger 记录失败: {e}")

    async def reflect(self, result: 'ActionResult') -> Reflection:
        """反思：调 AutoReviewer 复盘 + SkillExtractor 沉淀 + SharedBus 广播"""
        logger.info(f"Agent {self.agent_id} 反思执行结果")

        task_id = self.task_history[-1].task_id if self.task_history else "unknown"
        task_desc = self.task_history[-1].description if self.task_history else ""
        execution_time = result.execution_time
        success = result.success

        # ─── 收集执行日志 ─────────────────────────────────
        logs_str = ""
        try:
            from core.execution_logger import get_execution_logger
            el = get_execution_logger()
            if hasattr(el, 'format_logs_for_review'):
                logs_str = el.format_logs_for_review(task_id)
        except Exception as e:
            logger.debug(f"ExecutionLogger 获取日志失败: {e}")

        # ─── AutoReviewer 复盘 ────────────────────────────
        review_result = None
        try:
            from core.auto_reviewer import get_auto_reviewer
            reviewer = get_auto_reviewer()
            review_result = await reviewer.review(
                task_id=task_id,
                task_description=task_desc,
                execution_logs=logs_str or f"步骤: {len(result.output if result.output else [])}, 耗时: {execution_time:.2f}s",
                task_result=str(result.output)[:1000] if result.output else None,
            )

            # ─── SkillExtractor 沉淀 ───────────────────────
            if review_result and review_result.is_worth_saving:
                try:
                    from core.skill_extractor import get_skill_extractor
                    extractor = get_skill_extractor()
                    extractor.extract_from_review(review_result, logs_str)
                except Exception as e:
                    logger.debug(f"SkillExtractor 提取失败: {e}")

        except Exception as e:
            logger.debug(f"AutoReviewer 复盘失败: {e}")

        # ─── 构建 Reflection ──────────────────────────────
        reflection = Reflection(
            success=success,
            lessons_learned=[review_result.what_went_well[:200]] if review_result and review_result.what_went_well else (
                ["任务成功完成"] if success else []
            ),
            improvements=[review_result.improvement[:200]] if review_result and review_result.improvement else (
                [] if success else ["考虑使用不同的策略"]
            ),
            performance_metrics={
                "execution_time": execution_time,
                "success_rate": self.metrics.success_rate,
            }
        )
        if review_result:
            reflection.performance_metrics["is_worth_saving"] = review_result.is_worth_saving
            reflection.performance_metrics["pitfalls"] = review_result.pitfalls[:100] if review_result.pitfalls else ""

        # 存储到记忆
        await self.memory.store_episode({
            "type": "reflection",
            "result": reflection.__dict__,
            "agent_id": self.agent_id
        })

        # 发布到 SharedBus（KEPA闭环：将反思结果传递给调度器）
        try:
            await self._ensure_bus()
            if self._bus:
                from core.multi_agent_v2.infrastructure.shared_bus import Message, MessageType
                
                # 获取任务类型（从历史任务中提取）
                task_type = self.task_history[-1].type if self.task_history else "general"
                
                # 获取协作模式（如果有上下文信息）
                collaboration_mode = ""
                if self.context_center:
                    try:
                        context = self.context_center.get_task_context(task_id)
                        if context and hasattr(context, 'collaboration_mode'):
                            collaboration_mode = context.collaboration_mode
                    except Exception:
                        pass
                
                await self._bus.publish(
                    f"agent:{self.agent_id}:reflect",
                    Message(
                        type=MessageType.REFLECTION_RESULT,
                        sender=self.agent_id,
                        topic=f"task:{task_id}:reflect",
                        payload={
                            "task_id": task_id,
                            "agent_id": self.agent_id,
                            "agent_type": self.agent_type.value,
                            "success": success,
                            "lessons_learned": reflection.lessons_learned,
                            "improvements": reflection.improvements,
                            "task_type": task_type,
                            "collaboration_mode": collaboration_mode,
                            "execution_time": execution_time,
                            "performance_metrics": reflection.performance_metrics,
                        }
                    )
                )
                logger.debug(f"✅ 反思结果已发布到KEPA闭环: agent={self.agent_id}, task={task_id}")
        except Exception as e:
            logger.debug(f"发布反思结果失败: {e}")

        return reflection

    async def _on_message_received(self, message: Dict[str, Any]):
        """处理收到的直接消息"""
        logger.info(f"Agent {self.agent_id} 收到消息: {message.get('sender')} -> {message.get('content', '')[:50]}...")
        
        # 存储到情景记忆
        await self.memory.store_episode({
            "type": "message_received",
            "sender": message.get("sender"),
            "content": message.get("content"),
            "message_type": message.get("message_type", "inform")
        })
        
        # 调用子类处理
        await self.handle_message(message)
    
    async def _on_topic_message(self, message: Dict[str, Any]):
        """处理订阅主题的消息"""
        logger.debug(f"Agent {self.agent_id} 收到主题消息: {message.get('topic', 'unknown')}")
        
        # 存储到情景记忆
        await self.memory.store_episode({
            "type": "topic_message",
            "topic": message.get("topic"),
            "content": message.get("content"),
            "sender": message.get("sender")
        })
        
        # 调用子类处理
        await self.handle_topic_message(message)
    
    async def send_message(self, target_agent_id: str, content: Any, message_type: str = "inform"):
        """发送消息给指定Agent"""
        if not self._communication_center:
            logger.warning(f"Agent {self.agent_id} 通信中心未初始化")
            return None
        
        message_id = await self._communication_center.send_direct(
            sender=self.agent_id,
            receiver=target_agent_id,
            content=content,
            message_type=message_type
        )
        
        logger.info(f"Agent {self.agent_id} 发送消息到 {target_agent_id}: {message_id}")
        return message_id
    
    async def publish_to_topic(self, topic: str, content: Any):
        """发布消息到指定主题"""
        if not self._communication_center:
            logger.warning(f"Agent {self.agent_id} 通信中心未初始化")
            return
        
        await self._communication_center.publish(
            topic=topic,
            message={
                "topic": topic,
                "content": content,
                "sender": self.agent_id,
                "timestamp": time.time()
            },
            sender=self.agent_id
        )
        
        logger.info(f"Agent {self.agent_id} 发布到主题 {topic}")
    
    async def broadcast(self, content: Any):
        """广播消息给所有Agent"""
        if not self._communication_center:
            logger.warning(f"Agent {self.agent_id} 通信中心未初始化")
            return
        
        await self._communication_center.broadcast(
            sender=self.agent_id,
            content=content
        )
        
        logger.info(f"Agent {self.agent_id} 广播消息")
    
    async def request_help(self, target_agent_id: str, content: Any, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """向其他Agent请求帮助（请求-响应模式）"""
        if not self._communication_center:
            logger.warning(f"Agent {self.agent_id} 通信中心未初始化")
            return None
        
        result = await self._communication_center.request(
            sender=self.agent_id,
            receiver=target_agent_id,
            content=content,
            timeout=timeout
        )
        
        logger.info(f"Agent {self.agent_id} 从 {target_agent_id} 获取响应")
        return result
    
    async def notify_task_completed(self, task_id: str, result: Any):
        """通知其他Agent任务已完成"""
        await self.publish_to_topic(
            topic=CommunicationTopic.TASK_COMPLETED.value,
            content={
                "task_id": task_id,
                "agent_id": self.agent_id,
                "result": result,
                "timestamp": time.time()
            }
        )
    
    async def notify_task_failed(self, task_id: str, error: str):
        """通知其他Agent任务失败"""
        await self.publish_to_topic(
            topic=CommunicationTopic.TASK_FAILED.value,
            content={
                "task_id": task_id,
                "agent_id": self.agent_id,
                "error": error,
                "timestamp": time.time()
            }
        )
    
    async def handle_message(self, message: Dict[str, Any]):
        """处理收到的消息（子类可重写）"""
        pass
    
    async def handle_topic_message(self, message: Dict[str, Any]):
        """处理主题消息（子类可重写）"""
        pass
    
    def get_online_agents(self) -> List[str]:
        """获取在线Agent列表"""
        if not self._communication_center:
            return []
        return self._communication_center.get_online_agents()

    async def ask_user(
        self,
        question: str,
        context: str = "",
        timeout: int = 60,
    ) -> Optional[str]:
        """反问用户：在降级前询问用户意见

        返回:
          "proceed" - 用户要求继续（降级处理）
          "retry"   - 用户要求重试
          "cancel"  - 用户要求取消
          None      - 超时无响应
        """
        from core.agents.agent_communication import get_question_registry
        future = get_question_registry().ask(
            agent_id=self.agent_id,
            agent_name=self.agent_name or self.agent_id,
            question=question,
            context=context,
            timeout=timeout,
        )
        try:
            result = await asyncio.wait_for(future, timeout=timeout + 5)
            return result
        except asyncio.TimeoutError:
            return None

    async def communicate(self, message: 'Message') -> None:
        """与其他Agent通信（兼容旧接口）"""
        if message.to_agent:
            await self.send_message(
                target_agent_id=message.to_agent,
                content=message.content,
                message_type=message.message_type
            )
        else:
            await self.broadcast(message.content)

    def can_handle(self, task: 'Task') -> bool:
        """判断是否能处理任务"""
        if self.current_load >= self.max_load:
            return False

        if self.state not in [AgentState.IDLE, AgentState.READY]:
            return False

        # 检查能力匹配
        for capability in self.capabilities:
            score = capability.match_score(task.keywords)
            if score > 0.3:
                return True

        return False

    def get_load(self) -> float:
        """获取当前负载"""
        return self.current_load

    def get_metrics(self) -> AgentMetrics:
        """获取性能指标"""
        return self.metrics

    def __repr__(self) -> str:
        return f"BaseAgent(id={self.agent_id}, type={self.agent_type.value}, state={self.state.value})"


@dataclass
class Task:
    """任务定义"""
    task_id: str
    type: str
    description: str
    keywords: List[str] = field(default_factory=list)
    complexity: float = 0.5  # 任务复杂度 (0-1)
    estimated_steps: int = 3
    dependencies: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1
    deadline: Optional[float] = None


@dataclass
class ActionResult:
    """执行结果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    partial_results: List[Any] = field(default_factory=list)
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """Agent间消息"""
    message_id: str
    from_agent: str
    to_agent: Optional[str]  # None表示广播
    content: Any
    message_type: str
    timestamp: float = field(default_factory=time.time)



class AgentFactory:
    """Create disposable agents on demand from role templates"""
    
    @staticmethod
    def create_agent(
        agent_type: AgentType,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "",
        **kwargs
    ) -> 'BaseAgent':
        """直接根据AgentType创建Agent"""
        if agent_type == AgentType.MASTER:
            from core.multi_agent_v2.agents.master.master_agent import MasterAgent
            return MasterAgent(agent_id=agent_id, name=name, description=description)
        elif agent_type == AgentType.WORKER:
            from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
            return WorkerAgent(agent_id=agent_id, name=name, description=description, specialization=kwargs.get("specialization"))
        elif agent_type == AgentType.REVIEWER:
            from core.multi_agent_v2.agents.reviewer.reviewer_agent import ReviewerAgent
            return ReviewerAgent(agent_id=agent_id, name=name, description=description)
        elif agent_type == AgentType.EXPERT:
            from core.multi_agent_v2.agents.expert.expert_agent import ExpertAgent
            return ExpertAgent(domain=kwargs.get("domain", "general"), agent_id=agent_id, name=name, description=description)
        elif agent_type == AgentType.COORDINATOR:
            from core.multi_agent_v2.agents.coordinator.coordinator_agent import CoordinatorAgent
            return CoordinatorAgent(agent_id=agent_id, name=name, description=description)
        elif agent_type == AgentType.MONITOR:
            from core.multi_agent_v2.agents.monitor.monitor_agent import MonitorAgent
            return MonitorAgent(agent_id=agent_id, name=name, description=description)
        else:
            from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
            return WorkerAgent(agent_id=agent_id, name=name, description=description)

    @staticmethod
    def create_agent_from_role(
        role_type: str,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "",
    ) -> 'BaseAgent':
        from core.multi_agent_v2.agents.role_templates import get_template, RoleType
        
        # 首先检查是否是新的Agent类型
        if role_type in ["expert", "coordinator", "monitor"]:
            agent_type_map = {
                "expert": AgentType.EXPERT,
                "coordinator": AgentType.COORDINATOR,
                "monitor": AgentType.MONITOR
            }
            return AgentFactory.create_agent(
                agent_type=agent_type_map[role_type],
                agent_id=agent_id,
                name=name,
                description=description
            )
        
        role_map = {
            "task_decomposer": RoleType.TASK_DECOMPOSER,
            "tool_executor": RoleType.TOOL_EXECUTOR,
            "reviewer": RoleType.REVIEWER,
            "researcher": RoleType.RESEARCHER,
            "integrator": RoleType.INTEGRATOR,
        }
        rt = role_map.get(role_type, RoleType.TOOL_EXECUTOR)
        template = get_template(rt)

        # Create the appropriate concrete subclass
        # Each subclass has a different init signature
        if rt in (RoleType.REVIEWER,):
            from core.multi_agent_v2.agents.reviewer.reviewer_agent import ReviewerAgent
            agent = ReviewerAgent(
                agent_id=agent_id,
                name=name or (template.name if template else role_type),
                description=description or (template.description if template else ""),
            )
        elif rt in (RoleType.TASK_DECOMPOSER, RoleType.INTEGRATOR):
            from core.multi_agent_v2.agents.master.master_agent import MasterAgent
            agent = MasterAgent(
                agent_id=agent_id,
                name=name or (template.name if template else role_type),
                description=description or (template.description if template else ""),
            )
        else:
            # WORKER, RESEARCHER, TOOL_EXECUTOR -> WorkerAgent
            from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
            agent = WorkerAgent(
                agent_id=agent_id,
                name=name or (template.name if template else role_type),
                description=description or (template.description if template else ""),
                specialization=role_type,
            )

        # Add capabilities from template
        if template:
            agent.capabilities = [
                Capability(
                    name=cap_name,
                    description=cap_name,
                    keywords=[cap_name],
                    expertise_level=template.expertise_level,
                    max_concurrent_tasks=template.max_concurrency,
                )
                for cap_name in template.default_capabilities
            ]
        return agent

    @staticmethod
    def create_agents_for_task(
        task_keywords: list, estimated_steps: int = 3, max_agents: int = 5,
    ) -> list:
        from core.multi_agent_v2.agents.role_templates import select_templates_for_task
        templates = select_templates_for_task(task_keywords, estimated_steps, max_agents)
        return [
            AgentFactory.create_agent_from_role(
                role_type=t.role_type.value, name=f"{t.name}_{i}",
                description=t.description,
            ) for i, t in enumerate(templates)
        ]

