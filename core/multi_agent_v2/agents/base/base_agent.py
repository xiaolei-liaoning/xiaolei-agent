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
    """Agent类型"""
    MASTER = "master"             # 主Agent：任务分解、结果聚合
    WORKER = "worker"             # 执行Agent：负责具体执行
    REVIEWER = "reviewer"         # 评审Agent：质量把关
    EXPERT = "expert"             # 专家Agent：领域知识
    COORDINATOR = "coordinator"   # 协调Agent：流程控制
    MONITOR = "monitor"           # 监控Agent：状态追踪


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
            from core.llm_backend import get_llm_router
            from core.multi_agent_v2.agents.prompts.agent_prompts import get_prompt_manager
            self.llm_router = get_llm_router()
            self.prompt_manager = get_prompt_manager()
            logger.info(f"Mind组件依赖初始化成功 (Agent: {self.agent.agent_id})")
        except Exception as e:
            logger.warning(f"Mind组件依赖初始化失败: {e}")

    async def think(self, task: 'Task') -> Thought:
        """思考：理解任务、制定计划、做出决策
        
        使用LLM进行真正的智能思考，根据Agent类型使用对应的提示词。
        """
        logger.info(f"Agent {self.agent.agent_id} 正在思考任务: {task.type}")

        # 尝试使用LLM进行真实思考
        try:
            if self.llm_router and self.prompt_manager:
                return await self._think_with_llm(task)
        except Exception as e:
            logger.warning(f"LLM思考失败，使用模拟思考: {e}")

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
            task_type=task.type,
            plan="待制定..."
        )

        # 构建完整的消息列表
        messages = [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": thinking_prompt}
        ]

        # 调用LLM
        response = await self.llm_router.chat(messages, temperature=0.7, max_tokens=1500)
        
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
        """模拟思考过程（降级方案）"""
        reasoning = await self._reason_about_task(task)
        plan = await self._create_plan(task)
        confidence = await self._calculate_confidence(task)

        thought = Thought(
            reasoning=reasoning,
            plan=plan,
            confidence=confidence
        )

        self.thinking_history.append(thought)
        return thought

    async def _reason_about_task(self, task: 'Task') -> str:
        """推理任务（模拟）"""
        return f"分析任务 '{task.type}': 需要调用 {len(self.agent.capabilities)} 个能力"

    async def _create_plan(self, task: 'Task') -> List[str]:
        """创建执行计划（模拟）"""
        return [f"步骤{i+1}: 执行任务相关操作" for i in range(min(task.estimated_steps, 5))]

    async def _calculate_confidence(self, task: 'Task') -> float:
        """计算置信度（模拟）"""
        base_confidence = sum(c.expertise_level for c in self.agent.capabilities) / max(len(self.agent.capabilities), 1)
        return min(base_confidence * 0.9, 0.99)


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

        # 锁
        self._state_lock = asyncio.Lock()

        # 通信系统
        self._communication_center = None
        self._subscribed_topics = set()

        logger.info(f"Agent创建: {self.agent_id} ({self.agent_type.value})")
    
    def _init_communication(self):
        """初始化通信中心（延迟导入避免循环依赖）"""
        try:
            from core.agent_communication import communication_center
            self._communication_center = communication_center
            logger.info(f"Agent {self.agent_id} 通信中心初始化成功")
        except Exception as e:
            logger.warning(f"Agent {self.agent_id} 通信中心初始化失败: {e}")

    async def register(self) -> None:
        """注册到Agent池"""
        async with self._state_lock:
            if self.state != AgentState.CREATED:
                raise ValueError(f"Agent {self.agent_id} 已注册，不能重复注册")

            self.state = AgentState.REGISTERED
            
            # 初始化通信中心并注册Agent
            if self._communication_center is None:
                self._init_communication()
            
            if self._communication_center:
                await self._communication_center.register_agent(
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    agent_type=self.agent_type.value,
                    callbacks={"message_received": self._on_message_received}
                )
                
                # 订阅默认主题
                await self._subscribe_to_topics()
            
            logger.info(f"Agent注册: {self.agent_id}")
    
    async def _subscribe_to_topics(self):
        """订阅默认主题"""
        if not self._communication_center:
            return
        
        # 根据Agent类型订阅相关主题
        topics_to_subscribe = []
        
        if self.agent_type in [AgentType.WORKER, AgentType.EXPERT]:
            topics_to_subscribe.append(CommunicationTopic.TASK_COMPLETED.value)
            topics_to_subscribe.append(CommunicationTopic.BROADCAST.value)
        
        if self.agent_type in [AgentType.REVIEWER, AgentType.MONITOR]:
            topics_to_subscribe.append(CommunicationTopic.TASK_FAILED.value)
            topics_to_subscribe.append(CommunicationTopic.VULNERABILITY_FOUND.value)
        
        if self.agent_type in [AgentType.MASTER, AgentType.COORDINATOR]:
            topics_to_subscribe.append(CommunicationTopic.TASK_COMPLETED.value)
            topics_to_subscribe.append(CommunicationTopic.TASK_FAILED.value)
            topics_to_subscribe.append(CommunicationTopic.DATA_ANALYZED.value)
        
        for topic in topics_to_subscribe:
            await self._communication_center.subscribe(self.agent_id, topic, self._on_topic_message)
            self._subscribed_topics.add(topic)
        
        logger.info(f"Agent {self.agent_id} 订阅主题: {topics_to_subscribe}")

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
        """执行：调用工具、生成结果"""
        logger.info(f"Agent {self.agent_id} 开始执行计划")

        start_time = time.time()
        results = []

        try:
            for step in plan:
                # 调用相关工具
                result = await self._execute_step(step)
                results.append(result)

                # 记录到情景记忆
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

            return ActionResult(
                success=True,
                output=results,
                execution_time=execution_time
            )

        except Exception as e:
            logger.error(f"Agent {self.agent_id} 执行失败: {e}")
            self.metrics.tasks_failed += 1

            return ActionResult(
                success=False,
                error=str(e),
                partial_results=results
            )

        finally:
            # 更新负载
            self.current_load = max(0, self.current_load - task.complexity)

    async def _execute_step(self, step: str) -> Any:
        """执行单个步骤"""
        # 模拟步骤执行
        await asyncio.sleep(0.1)
        return {"step": step, "status": "completed"}

    async def reflect(self, result: 'ActionResult') -> Reflection:
        """反思：评估结果、总结经验"""
        logger.info(f"Agent {self.agent_id} 反思执行结果")

        reflection = Reflection(
            success=result.success,
            lessons_learned=[],
            improvements=[],
            performance_metrics={
                "execution_time": result.execution_time,
                "success_rate": self.metrics.success_rate
            }
        )

        if result.success:
            reflection.lessons_learned.append("任务成功完成")
        else:
            reflection.lessons_learned.append("任务失败，需要改进")
            reflection.improvements.append("考虑使用不同的策略")

        # 存储反思结果
        await self.memory.store_episode({
            "type": "reflection",
            "result": reflection.__dict__,
            "agent_id": self.agent_id
        })

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
