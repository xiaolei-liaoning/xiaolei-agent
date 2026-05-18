"""
小组协作模式（模式二）

队长 + 最多5个队员，队长拆任务、监控、交互，队员只跟队长说话。

与模式一（三省六部制）的区别：
- 模式一：同事关系，Agent之间自由通信（SharedBus）
- 模式二：层级关系，队员只知道队长，队员之间不说话
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 1. 消息系统 - 队长↔队员 双向通信
# ════════════════════════════════════════════════════════════════


@dataclass
class TeamMessage:
    """小组内部消息"""
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    sender: str = ""
    receiver: str = ""
    msg_type: str = ""   # task_assign | task_start | progress | question | answer | result | feedback | error
    content: Any = None
    timestamp: float = field(default_factory=time.time)


class TeamMessageCenter:
    """消息中心 - 队长与队员之间的双向通信管道"""

    def __init__(self):
        self._leader_queue: asyncio.Queue = asyncio.Queue()
        self._member_queues: Dict[str, asyncio.Queue] = {}
        self._closed = False

    def register_member(self, worker_id: str):
        self._member_queues[worker_id] = asyncio.Queue()

    def unregister_member(self, worker_id: str):
        self._member_queues.pop(worker_id, None)

    # ── 发 ──

    async def send_to_leader(self, msg: TeamMessage):
        if not self._closed:
            await self._leader_queue.put(msg)

    async def send_to_member(self, worker_id: str, msg: TeamMessage):
        if self._closed:
            return
        q = self._member_queues.get(worker_id)
        if q:
            await q.put(msg)

    async def broadcast(self, msg: TeamMessage):
        if self._closed:
            return
        for q in self._member_queues.values():
            await q.put(msg)

    # ── 收 ──

    async def recv_for_leader(self) -> TeamMessage:
        while not self._closed:
            try:
                return await asyncio.wait_for(self._leader_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
        raise asyncio.CancelledError("消息中心已关闭")

    async def recv_for_member(self, worker_id: str, timeout: float = 60) -> Optional[TeamMessage]:
        q = self._member_queues.get(worker_id)
        if not q:
            return None
        try:
            return await asyncio.wait_for(q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def close(self):
        self._closed = True

    @property
    def member_count(self) -> int:
        return len(self._member_queues)


# ════════════════════════════════════════════════════════════════
# 2. 队员 - 只跟队长说话
# ════════════════════════════════════════════════════════════════


class TeamWorkerAgent:
    """队员 Agent

    队员不知道其他队员的存在，所有沟通都通过消息中心跟队长进行。
    底层复用模式一的 WorkerAgent（通过 AgentFactory 创建）。
    """

    def __init__(
        self,
        worker_id: str,
        role_name: str,
        specialization: str,
        description: str,
        leader_id: str,
        msg_center: TeamMessageCenter,
    ):
        self.worker_id = worker_id
        self.role_name = role_name
        self.specialization = specialization
        self.description = description
        self.leader_id = leader_id
        self._msg_center = msg_center
        self._msg_center.register_member(worker_id)

        # 延迟创建底层 WorkerAgent（复用模式一）
        self._agent: Optional[Any] = None

    async def _ensure_agent(self):
        if self._agent is not None:
            return self._agent
        from core.multi_agent_v2.agents.base.base_agent import AgentFactory
        self._agent = AgentFactory.create_agent_from_role(
            role_type="tool_executor",
            name=self.role_name,
            description=self.description,
        )
        if hasattr(self._agent, 'specialization'):
            self._agent.specialization = self.specialization
            self._agent.capabilities = self._agent._initialize_capabilities()
        return self._agent

    async def execute(self, subtask: Dict[str, Any]) -> Dict[str, Any]:
        """执行子任务，过程中通过消息中心跟队长交互"""
        agent = await self._ensure_agent()
        result = {"worker_id": self.worker_id, "role": self.role_name, "success": False}

        try:
            from core.multi_agent_v2.agents.base.base_agent import Task

            # 汇报开工
            await self._msg_center.send_to_leader(TeamMessage(
                sender=self.worker_id, receiver=self.leader_id,
                msg_type="task_start", content=subtask,
            ))

            task = Task(
                task_id=subtask.get("id", self.worker_id),
                type=subtask.get("type", self.specialization),
                description=subtask.get("description", ""),
                keywords=subtask.get("keywords", []),
                complexity=subtask.get("complexity", 0.5),
                estimated_steps=subtask.get("estimated_steps", 3),
            )

            # 思考
            thought = await agent.think(task)
            await self._msg_center.send_to_leader(TeamMessage(
                sender=self.worker_id, receiver=self.leader_id,
                msg_type="progress",
                content={"status": "thinking", "reasoning": str(thought.reasoning)[:200]},
            ))

            # 执行
            action_result = await agent.act(thought.plan)

            # 汇报进展
            await self._msg_center.send_to_leader(TeamMessage(
                sender=self.worker_id, receiver=self.leader_id,
                msg_type="progress",
                content={"status": "executed", "steps": len(thought.plan)},
            ))

            # 反思
            reflection = await agent.reflect(action_result) if hasattr(agent, 'reflect') else None

            # 汇报结果
            await self._msg_center.send_to_leader(TeamMessage(
                sender=self.worker_id, receiver=self.leader_id,
                msg_type="result", content={
                    "success": action_result.success,
                    "output": str(action_result.output)[:2000] if action_result.output else None,
                    "execution_time": action_result.execution_time,
                },
            ))

            result["success"] = action_result.success
            result["output"] = action_result.output
            result["execution_time"] = action_result.execution_time

        except Exception as e:
            logger.error(f"队员 {self.role_name}({self.worker_id}) 执行失败: {e}")
            await self._msg_center.send_to_leader(TeamMessage(
                sender=self.worker_id, receiver=self.leader_id,
                msg_type="error", content=str(e),
            ))
            result["error"] = str(e)

        return result

    async def answer_question(self, question: str) -> str:
        """回答队长的问题 / 接收队长的反馈"""
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        messages = [
            {"role": "system", "content": f"你是{self.role_name}，{self.description}"},
            {"role": "user", "content": f"队长问：{question}\n请回答。"},
        ]
        try:
            resp = await router.chat(messages, temperature=0.7, max_tokens=500)
            return resp
        except Exception as e:
            return f"无法回答: {e}"


# ════════════════════════════════════════════════════════════════
# 3. 团队计划 - LLM 分析任务后输出的结构化结果
# ════════════════════════════════════════════════════════════════


@dataclass
class TeamMemberSpec:
    """队员规格 - LLM 决定要什么样的队员"""
    role_name: str                # 角色名，如 "爬虫专员"
    specialization: str           # specialization: scraping / analysis / processing / general
    description: str              # 对队员能力的描述
    task_description: str         # 这个队员要执行的任务
    task_type: str = "execution"  # 任务类型
    keywords: List[str] = field(default_factory=list)
    estimated_steps: int = 3
    complexity: float = 0.5
    depends_on: List[str] = field(default_factory=list)  # 依赖的队员 role_name


@dataclass
class TeamPlan:
    """团队组成计划"""
    task_description: str
    members: List[TeamMemberSpec] = field(default_factory=list)
    reasoning: str = ""


# ════════════════════════════════════════════════════════════════
# 4. 队长 - 拆任务 + 组团队 + 监视 + 交互
# ════════════════════════════════════════════════════════════════


class TeamLeader:
    """队长

    流程：
    1. 用 LLM 分析任务 → 决定团队组成（要几个人、各干什么）
    2. 动态创建 1~5 个队员
    3. 分配任务，并行/串行执行
    4. 监听消息（进展、提问、结果）
    5. 聚合结果返回
    """

    MAX_MEMBERS = 5

    def __init__(self):
        self.msg_center = TeamMessageCenter()
        self.workers: Dict[str, TeamWorkerAgent] = {}
        self.plan: Optional[TeamPlan] = None
        self._results: Dict[str, Any] = {}
        self._active = False

    # ── 入口 ──────────────────────────────────────────

    async def run(self, task: str) -> Dict[str, Any]:
        """全流程入口：分析 → 组队 → 执行 → 返回"""
        start = time.time()
        logger.info(f"队长接收任务: {task[:80]}")

        try:
            # 1. 计划
            self.plan = await self._plan_team(task)
            if not self.plan.members:
                return self._error_result(task, "LLM未给出队员计划")

            team_size = len(self.plan.members)
            logger.info(f"队长计划完成: 需要 {team_size} 个队员")

            # 2. 组队
            self.workers = await self._assemble_team(self.plan)
            logger.info(f"队伍组建完成: {len(self.workers)} 人")

            # 3. 带队执行
            result = await self._lead_team(self.plan)

            result["team_size"] = team_size
            result["duration"] = round(time.time() - start, 2)

            if result["success"]:
                logger.info(f"任务完成 ✓ ({result['duration']}s, {team_size}人)")
            else:
                logger.warning(f"任务部分失败 ({result['duration']}s)")

            return result

        except Exception as e:
            logger.error(f"队长执行失败: {e}")
            return self._error_result(task, str(e))
        finally:
            self._active = False
            self.msg_center.close()

    # ── ① 计划 ────────────────────────────────────────

    async def _plan_team(self, task: str) -> TeamPlan:
        """用 LLM 分析任务，制定团队计划"""
        from core.engine.llm_backend import get_llm_router

        router = get_llm_router()
        prompt = f"""你是一个小组队长，需要分析下面的任务并决定团队组成。

任务：{task}

要求：
1. 分析任务需要几个专业角色（最少1个，最多5个）
2. 为每个角色指定：
   - role_name: 角色名（如"爬虫专员""分析专员""写作专员""搜索专员"等）
   - specialization: 专业领域（scraping/analysis/processing/general）
   - description: 一句话描述这个队员干什么
   - task_description: 分配给他的具体任务

可用专业(6选1)：
- scraping: 网页爬取、数据采集、搜索信息
- analysis: 数据分析、统计、报告
- processing: 数据处理、格式转换、清洗
- general: 通用执行

依赖关系：
- depends_on: 如果这个队员需要等另一个队员的结果再开始，写那个队员的 role_name
- 没有依赖的队员可以并行执行
- 有依赖的队员串行执行

请严格输出 JSON 格式（不要用 markdown 代码块）：
{{"reasoning":"简要分析","members":[
  {{"role_name":"爬虫专员","specialization":"scraping","description":"抓取微博热搜","task_description":"爬取今日微博热搜TOP50","keywords":["热搜","微博"],"estimated_steps":3,"depends_on":[]}},
  ...
]}}"""

        try:
            resp = await router.chat([{"role": "user", "content": prompt}],
                                      temperature=0.7, max_tokens=2000)
            data = json.loads(self._extract_json(resp))
            members = []
            for m in data.get("members", []):
                members.append(TeamMemberSpec(
                    role_name=m.get("role_name", "队员"),
                    specialization=m.get("specialization", "general"),
                    description=m.get("description", ""),
                    task_description=m.get("task_description", ""),
                    task_type=m.get("task_type", "execution"),
                    keywords=m.get("keywords", []),
                    estimated_steps=m.get("estimated_steps", 3),
                    complexity=m.get("complexity", 0.5),
                    depends_on=m.get("depends_on", []),
                ))
            return TeamPlan(task_description=task, members=members,
                            reasoning=data.get("reasoning", ""))
        except Exception as e:
            logger.warning(f"LLM 团队计划失败，回退单兵模式: {e}")
            return TeamPlan(
                task_description=task,
                members=[TeamMemberSpec(
                    role_name="执行专员",
                    specialization="general",
                    description="通用执行",
                    task_description=task,
                    keywords=[],
                    estimated_steps=5,
                    depends_on=[],
                )],
                reasoning="LLM不可用，回退单兵模式",
            )

    @staticmethod
    def _extract_json(text: str) -> str:
        """从 LLM 响应中提取 JSON（支持 markdown 包围、尾部多余数据）"""
        import re
        text = text.strip()
        # 去掉 ```json ... ``` 包围
        if text.startswith("```"):
            lines = text.split("\n")
            cleaned = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    cleaned.append(line)
            if cleaned:
                text = "\n".join(cleaned).strip()
        # 使用 raw_decode 处理尾部多余数据
        try:
            decoder = json.JSONDecoder()
            obj, pos = decoder.raw_decode(text)
            return json.dumps(obj, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
        # 兜底：找最外层 { }
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                decoder = json.JSONDecoder()
                obj, pos = decoder.raw_decode(match.group())
                return json.dumps(obj, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        return text

    # ── ② 组队 ────────────────────────────────────────

    async def _assemble_team(self, plan: TeamPlan) -> Dict[str, TeamWorkerAgent]:
        """动态创建队员（复用模式一的 AgentFactory）"""
        workers = {}
        for spec in plan.members[:self.MAX_MEMBERS]:
            wid = f"member_{uuid.uuid4().hex[:6]}"
            worker = TeamWorkerAgent(
                worker_id=wid,
                role_name=spec.role_name,
                specialization=spec.specialization,
                description=spec.description,
                leader_id="team_leader",
                msg_center=self.msg_center,
            )
            workers[spec.role_name] = worker
            logger.info(f"  队员加入: {spec.role_name} ({spec.specialization})")
        return workers

    # ── ③ 带队执行 ────────────────────────────────────

    async def _lead_team(self, plan: TeamPlan) -> Dict[str, Any]:
        """带队执行：按依赖关系分阶段执行"""
        self._active = True
        results: Dict[str, Any] = {}
        outputs: Dict[str, Any] = {}  # role_name -> output for dependents
        all_worker_tasks = []  # 保存所有创建的队员任务

        # 按依赖分层
        phases = self._dependency_layers(plan.members)

        # 启动监听任务
        listener_task = asyncio.create_task(self._listen_loop())

        try:
            for phase_idx, phase in enumerate(phases):
                if not phase:
                    continue
                logger.info(f"  执行阶段 {phase_idx + 1}: {[m.role_name for m in phase]}")

                # 为有依赖的队员注入上游输出
                for spec in phase:
                    for dep_role in spec.depends_on:
                        if dep_role in outputs:
                            spec.task_description += f"\n\n【上游输出】\n{outputs[dep_role]}"

                # 并行执行本阶段队员
                tasks = {}
                for spec in phase:
                    worker = self.workers.get(spec.role_name)
                    if not worker:
                        continue
                    subtask = {
                        "id": spec.role_name,
                        "type": spec.specialization,
                        "description": spec.task_description,
                        "keywords": spec.keywords,
                        "estimated_steps": spec.estimated_steps,
                        "complexity": spec.complexity,
                    }
                    task = asyncio.create_task(worker.execute(subtask))
                    tasks[spec.role_name] = task
                    all_worker_tasks.append(task)

                # 等待本阶段全部完成
                for role_name, task in tasks.items():
                    try:
                        result = await task
                        results[role_name] = result
                        if result.get("success"):
                            outputs[role_name] = str(result.get("output", ""))[:1000]
                    except Exception as e:
                        results[role_name] = {"success": False, "error": str(e)}

        finally:
            # 取消监听任务
            listener_task.cancel()
            try:
                await listener_task
            except (asyncio.CancelledError, Exception):
                pass
            
            # 取消所有队员任务
            for task in all_worker_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

        return await self._collect_results(plan, results)

    def _dependency_layers(self, members: List[TeamMemberSpec]) -> List[List[TeamMemberSpec]]:
        """按依赖关系分层：无依赖放第一层，随后逐层推进"""
        remaining = {m.role_name: m for m in members}
        layers = []

        while remaining:
            layer = []
            for role_name in list(remaining.keys()):
                spec = remaining[role_name]
                deps = set(spec.depends_on)
                # 如果所有依赖都已经在之前的层里
                if not deps or deps.issubset(set().union(*[
                    {m.role_name for m in l} for l in layers
                ]) if layers else set()):
                    layer.append(spec)
                    del remaining[role_name]
            if not layer:
                # 有循环依赖或异常，强制结束
                layer.extend(remaining.values())
                remaining.clear()
            layers.append(layer)

        return layers

    async def _listen_loop(self):
        """队长监听队员消息"""
        while self._active:
            try:
                msg = await self.msg_center.recv_for_leader()

                if msg.msg_type == "question":
                    logger.info(f"  队员提问 [{msg.sender[:8]}]: {str(msg.content)[:80]}")
                    # 队长可以直接回答
                    worker = self.workers.get(
                        next((r for r, w in self.workers.items()
                              if w.worker_id == msg.sender), None)
                    )
                    if worker:
                        answer = await worker.answer_question(str(msg.content))
                        await self.msg_center.send_to_member(
                            msg.sender, TeamMessage(
                                sender="leader", receiver=msg.sender,
                                msg_type="answer", content=answer,
                            )
                        )

                elif msg.msg_type == "progress":
                    status = msg.content.get("status", "") if isinstance(msg.content, dict) else ""
                    logger.debug(f"  进展 [{msg.sender[:8]}]: {status}")

                elif msg.msg_type == "result":
                    logger.info(f"  结果 [{msg.sender[:8]}]: 完成")

                elif msg.msg_type == "error":
                    logger.warning(f"  错误 [{msg.sender[:8]}]: {str(msg.content)[:100]}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"监听循环异常: {e}")

    # ── ④ 聚合 ────────────────────────────────────────

    async def _collect_results(self, plan: TeamPlan, results: Dict[str, Any]) -> Dict[str, Any]:
        """聚合所有队员结果"""
        successful = []
        failed = []

        for spec in plan.members:
            result = results.get(spec.role_name, {})
            if result.get("success"):
                successful.append({
                    "role": spec.role_name,
                    "output": str(result.get("output", ""))[:2000],
                    "time": result.get("execution_time", 0),
                })
            else:
                failed.append({
                    "role": spec.role_name,
                    "error": result.get("error", "未知错误"),
                })

        # 用 LLM 生成最终总结
        summary = await self._generate_summary(successful, failed)

        return {
            "success": len(failed) == 0,
            "mode": "team",
            "leader_summary": summary,
            "team_size": len(plan.members),
            "results": successful,
            "errors": failed if failed else None,
            "reasoning": plan.reasoning,
        }

    async def _generate_summary(self, successful: List[Dict], failed: List[Dict]) -> str:
        """生成任务总结（LLM不可用时简单拼接）"""
        try:
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()
            prompt = f"汇总以下多Agent执行结果，用2-3句话总结：\n成功：{json.dumps(successful, ensure_ascii=False)[:800]}\n失败：{json.dumps(failed, ensure_ascii=False)[:200]}"
            resp = await router.chat([{"role": "user", "content": prompt}],
                                temperature=0.5, max_tokens=300)
            return resp
        except Exception:
            parts = []
            for s in successful:
                parts.append(f"{s['role']}: 完成")
            for f in failed:
                parts.append(f"{f['role']}: 失败({f['error']})")
            return "; ".join(parts) if parts else "无结果"

    @staticmethod
    def _error_result(task: str, error: str) -> Dict[str, Any]:
        return {"success": False, "mode": "team", "error": error}


# ════════════════════════════════════════════════════════════════
# 5. 面向外部的统一入口
# ════════════════════════════════════════════════════════════════


class DynamicTeamCoordinator:
    """动态团队协调器 - 模式二的统一入口

    用法：
        coordinator = DynamicTeamCoordinator()
        result = await coordinator.execute("分析今日热点并生成报告")
    """

    def __init__(self):
        self._leader: Optional[TeamLeader] = None

    async def execute(self, task: str) -> Dict[str, Any]:
        """执行任务：队长带队"""
        self._leader = TeamLeader()
        return await self._leader.run(task)

    def is_running(self) -> bool:
        return self._leader is not None and self._leader._active


# ════════════════════════════════════════════════════════════════
# 6. 旧接口兼容（GroupCoordinator 保留原有签名，委托给新实现）
# ════════════════════════════════════════════════════════════════


# ── 给外面引用的枚举/类型 ──

class CollaborationStrategy(Enum):
    PIPELINE = "pipeline"
    MASTER_SLAVE = "master_slave"
    REVIEW = "review"
    AUCTION = "auction"
    HYBRID = "hybrid"


class AgentCapability:
    DATA_ANALYSIS = "data_analysis"
    WEB_SEARCH = "web_search"
    REASONING = "reasoning"
    CREATIVE_WRITING = "creative_writing"
    TRANSLATION = "translation"
    TEXT_GENERATION = "text_generation"

    def __init__(self, name: str = "", description: str = ""):
        self.name = name
        self.description = description


class AgentGroupProfile:
    def __init__(self, name: str, agents: List[str] = None, strategy: str = "pipeline",
                 group_id: str = "", capabilities: List[str] = None,
                 description: str = "", success_rate: float = 0.0,
                 total_tasks: int = 0):
        self.name = name
        self.agents = agents or []
        self.strategy = strategy
        self.group_id = group_id
        self.capabilities = capabilities or []
        self.description = description
        self.success_rate = success_rate
        self.total_tasks = total_tasks


@dataclass
class AgentRecommendation:
    requires_new_agent: bool = False
    suggested_agent_name: str = ""
    suggested_agent_description: str = ""
    required_capabilities: List[str] = field(default_factory=list)
    recommended_groups: List[AgentGroupProfile] = field(default_factory=list)


class GroupCoordinator:
    """GroupCoordinator - 小组模式（模式二）统一入口

    新实现：使用 TeamLeader 动态组队执行。
    保留原有方法签名以兼容旧代码。
    """

    def __init__(self, scheduler=None):
        self._scheduler = scheduler
        self._team_coordinator = DynamicTeamCoordinator()

    def register_group_profile(self, profile: AgentGroupProfile) -> None:
        logger.debug("注册Agent小组画像: %s", profile.name)

    async def analyze_and_recommend(self, task: str, available_agents: List[str],
                                   task_type: str = None, keywords: List[str] = None,
                                   estimated_steps: int = None) -> Dict[str, Any]:
        """任务分析 — TeamLeader 的 LLM 计划"""
        leader = TeamLeader()
        plan = await leader._plan_team(task)
        if plan.members:
            return {
                "success": True,
                "recommended_mode": "team",
                "agents": [m.role_name for m in plan.members],
                "analysis": plan.reasoning,
                "team_plan": [
                    {"role": m.role_name, "task": m.task_description}
                    for m in plan.members
                ],
            }
        return {"success": True, "recommended_mode": "pipeline", "agents": available_agents[:2]}

    async def start_session(self, task: str, agents: List[str], strategy: str) -> Dict[str, Any]:
        """启动会话 — 使用新实现"""
        logger.info("协作会话已启动: strategy=%s, agents=%s (小组模式)", strategy, agents)
        from core.multi_agent_v2.infrastructure.shared_bus import (
            get_shared_bus, Message, MessageType, TaskSnapshot
        )
        bus = get_shared_bus()
        await bus.publish("session:start", Message(
            type=MessageType.TASK_STARTED,
            sender="group_coordinator",
            topic="session:start",
            payload={"strategy": strategy, "agents": agents, "task": task},
        ))
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        await bus.save_snapshot(TaskSnapshot(
            task_id=session_id, original_request=task, status="running"
        ))
        return {"success": True, "session_id": session_id, "status": "running"}

    async def get_status(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态"""
        from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
        bus = get_shared_bus()
        snap = await bus.get_snapshot(session_id)
        if snap:
            return {"success": True, "session_id": session_id, "status": snap.status}
        return {"success": True, "session_id": session_id, "status": "unknown"}

    async def execute_with_strategy(self, group_id: str, message: str, strategy: str) -> Dict[str, Any]:
        """执行任务 — 用 TeamLeader 组队执行"""
        logger.info(f"小组模式执行: group={group_id}, strategy={strategy}")

        if strategy == "team":
            # 新：动态组队
            return await self._team_coordinator.execute(message)
        else:
            # 旧兼容：委托给 IntelligentScheduler
            return await self._legacy_execute(message, strategy)

    async def _legacy_execute(self, message: str, strategy: str) -> Dict[str, Any]:
        """旧兼容执行路径"""
        try:
            from core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler import (
                IntelligentScheduler, CollaborationMode
            )
            from core.multi_agent_v2.agents.base.base_agent import Task, AgentFactory
            from core.multi_agent_v2.infrastructure.task_executor import TaskExecutor
            from core.multi_agent_v2.infrastructure.agent_pool import SimpleAgentPool
            from core.multi_agent_v2.orchestration.context.global_context_center import (
                GlobalContextCenter
            )

            pool = SimpleAgentPool()
            agents = AgentFactory.create_agents_for_task(message.split(), 3, 3)
            for a in agents:
                pool.add_agent(a)

            scheduler = IntelligentScheduler(GlobalContextCenter())
            scheduler.agent_pool = pool

            task = Task(task_id=f"group_{uuid.uuid4().hex[:6]}", type=strategy,
                        description=message, keywords=[])
            schedule_result = await scheduler.schedule(task)

            if not schedule_result.success:
                return {"success": False, "error": "调度失败: " + (schedule_result.error or "")}

            executor = TaskExecutor(agent_pool=pool)
            exec_result = await executor.execute(schedule_result, task, timeout=60)

            return {
                "success": exec_result.get("success", False),
                "reply": f"[{strategy}] 执行完成" if exec_result.get("success") else "执行失败",
                "results": exec_result.get("results", []),
            }
        except Exception as e:
            logger.error(f"旧兼容执行失败: {e}")
            return {"success": False, "error": str(e)}

    def recommend_agent_groups(self, task_example: str) -> AgentRecommendation:
        """推荐 Agent 小组 — 用 AgentFactory 按任务特征创建"""
        try:
            from core.multi_agent_v2.agents.base.base_agent import AgentFactory
            templates = AgentFactory.create_agents_for_task(task_example.split(), 3, 3)
            return AgentRecommendation(
                requires_new_agent=True,
                suggested_agent_name=templates[0].agent_name if templates else "auto_agent",
                suggested_agent_description=f"为任务'{task_example[:30]}'自动创建",
                required_capabilities=[c.name for a in templates for c in a.capabilities][:5],
            )
        except Exception:
            return AgentRecommendation(requires_new_agent=False)
    
    # 以下为兼容API路由的方法
    async def start_collaboration_session(self, task: str, strategy=None):
        """启动协作会话（兼容API路由）"""
        logger.info(f"启动协作会话: task={task[:50]}, strategy={strategy}")
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        # 实际执行任务
        result = await self._team_coordinator.execute(task)
        # 构造兼容的响应格式
        return {
            "session_id": session_id,
            "subtasks": [],
            "participant_groups": [],
            "total_subtasks": 0
        }
    
    def get_session_status(self, session_id: str):
        """获取会话状态（兼容API路由）"""
        logger.debug(f"获取会话状态: {session_id}")
        return {
            "session_id": session_id,
            "status": "completed",
            "phase": "done",
            "subtasks": [],
            "total_subtasks": 0,
            "completed_subtasks": 0
        }
    
    async def execute_collaboration(self, session, executor=None):
        """执行协作（兼容API路由）"""
        logger.info(f"执行协作: session={session}")
        # 简单返回成功
        return {
            "success": True,
            "results": []
        }


class TempAgentCreator:
    """临时 Agent 创建器（保留旧接口）"""

    async def create_agent(self, name: str, capability: str) -> Dict[str, Any]:
        try:
            from core.multi_agent_v2.agents.base.base_agent import AgentFactory
            agent = AgentFactory.create_agent_from_role(
                role_type="tool_executor", name=name, description=capability,
            )
            return {"success": True, "agent_name": agent.agent_name,
                    "agent_id": agent.agent_id, "capability": capability}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_pending_requests(self) -> List[Dict[str, Any]]:
        return []

    async def approve_request(self, request_id: str) -> Dict[str, Any]:
        return {"success": True, "request_id": request_id}

    def create_temporary_agent_config(
        self, capabilities: List[str], name: str, description: str
    ) -> Dict[str, Any]:
        return {
            "agent_name": name,
            "description": description,
            "capabilities": capabilities,
            "requires_supervision": True,
        }


# 全局单例
_coordinator: Optional[GroupCoordinator] = None
_temp_creator: Optional[TempAgentCreator] = None


def get_group_coordinator() -> GroupCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = GroupCoordinator()
    return _coordinator


def get_temp_agent_creator() -> TempAgentCreator:
    global _temp_creator
    if _temp_creator is None:
        _temp_creator = TempAgentCreator()
    return _temp_creator
