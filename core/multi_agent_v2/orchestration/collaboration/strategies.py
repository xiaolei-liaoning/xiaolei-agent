"""
协作策略 - 实现不同的多Agent协作模式

包含：
1. 流水线模式 - 顺序执行，每个阶段专注特定任务
2. 主从模式 - 主Agent分解+聚合，从Agent执行
3. 评审模式 - 多Agent并行，结果通过评审达成共识
4. 拍卖模式 - 任务发布后，最适合的Agent"竞标"执行
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.multi_agent_v2.agents.base.base_agent import (
    BaseAgent, Task, ActionResult
)
from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter, TaskState
)

logger = logging.getLogger(__name__)


@dataclass
class CollaborationResult:
    """协作结果"""
    task_id: str
    success: bool
    final_result: Any
    partial_results: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    agent_results: Dict[str, ActionResult] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class BaseCollaborationStrategy(ABC):
    """协作策略基类"""

    def __init__(self, context_center: GlobalContextCenter):
        self.context_center = context_center

    @abstractmethod
    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """执行协作"""
        pass

    async def _execute_agent_task(
        self,
        agent: BaseAgent,
        subtask_id: str,
        task_data: Dict[str, Any]
    ) -> Tuple[str, ActionResult]:
        """执行单个Agent任务"""
        start_time = time.time()

        try:
            # 创建子任务
            subtask = Task(
                task_id=subtask_id,
                type=task_data.get("type", "subtask"),
                description=task_data.get("description", ""),
                keywords=task_data.get("keywords", []),
                complexity=task_data.get("complexity", 0.5)
            )

            # Agent思考
            thought = await agent.think(subtask)

            # Agent执行
            result = await agent.act(thought.plan)

            # Agent反思
            await agent.reflect(result)

            # 记录成功
            execution_time = time.time() - start_time
            await self.context_center.context_center.update_agent_state(
                agent.agent_id, "idle"
            )

            return subtask_id, result

        except Exception as e:
            logger.error(f"Agent {agent.agent_id} 执行任务 {subtask_id} 失败: {e}")

            return subtask_id, ActionResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )


class PipelineStrategy(BaseCollaborationStrategy):
    """流水线协作策略 - 顺序执行，每个阶段专注特定任务"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """流水线执行

        流程：
        1. 将任务分解为多个阶段
        2. 每个阶段分配给专门的Agent
        3. 每个Agent只完成特定阶段的工作
        4. 阶段之间通过上下文传递结果
        """
        start_time = time.time()
        partial_results = {}
        agent_results = {}

        logger.info(f"开始流水线执行: {task.task_id}, 计划: {len(execution_plan)} 个步骤")

        # 更新任务状态
        await self.context_center.update_task_state(task.task_id, TaskState.RUNNING)

        # 按步骤顺序执行
        for i, step in enumerate(execution_plan):
            step_name = step.get("subtask_id")
            agent_id = step.get("agent_id")

            # 获取Agent
            agent = next((a for a in agents if a.agent_id == agent_id), None)
            if not agent:
                logger.error(f"未找到Agent: {agent_id}")
                continue

            logger.info(f"流水线步骤 {i+1}/{len(execution_plan)}: {step_name} -> Agent {agent_id}")

            # 更新上下文，传递之前的结果
            context_data = {
                "step": i,
                "previous_results": partial_results,
                "total_steps": len(execution_plan)
            }

            # 执行步骤
            subtask_id, result = await self._execute_agent_task(
                agent,
                step_name,
                {
                    "type": f"pipeline_step_{i}",
                    "description": f"执行流水线第 {i+1} 步",
                    "keywords": task.keywords,
                    "complexity": task.complexity / len(execution_plan),
                    "context": context_data
                }
            )

            # 记录结果
            agent_results[agent_id] = result

            if result.success:
                partial_results[step_name] = result.output
                # 更新全局上下文，传递结果给下一个阶段
                await self.context_center.update_context(
                    task.task_id, agent_id, f"step_{i}_result", result.output
                )
            else:
                logger.error(f"步骤 {step_name} 执行失败: {result.error}")
                partial_results[step_name] = None

                # 流水线模式中，步骤失败会导致整个流程失败
                break

        # 计算最终结果
        final_result = self._aggregate_pipeline_results(partial_results)

        # 更新任务状态
        if all(r is not None for r in partial_results.values()):
            await self.context_center.update_task_state(task.task_id, TaskState.COMPLETED)
        else:
            await self.context_center.update_task_state(task.task_id, TaskState.FAILED)

        execution_time = time.time() - start_time

        return CollaborationResult(
            task_id=task.task_id,
            success=all(r is not None for r in partial_results.values()),
            final_result=final_result,
            partial_results=partial_results,
            execution_time=execution_time,
            agent_results=agent_results
        )

    def _aggregate_pipeline_results(self, partial_results: Dict[str, Any]) -> Any:
        """聚合流水线结果"""
        # 简单实现：返回最后一个成功的结果
        successful_results = [r for r in partial_results.values() if r is not None]
        return successful_results[-1] if successful_results else None


class MasterSlaveStrategy(BaseCollaborationStrategy):
    """主从协作策略 - 主Agent分解+聚合，从Agent执行"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """主从执行

        流程：
        1. 主Agent理解任务，分解为子任务
        2. 主Agent将子任务分配给从Agent
        3. 从Agent并行执行子任务
        4. 主Agent收集结果，进行聚合和校验
        """
        start_time = time.time()
        partial_results = {}
        agent_results = {}

        # 分离Master和Slave
        master_agent = None
        slave_agents = []

        for plan in execution_plan:
            agent_id = plan.get("agent_id")
            role = plan.get("role", "worker")
            agent = next((a for a in agents if a.agent_id == agent_id), None)

            if not agent:
                continue

            if role == "master" or plan.get("agent_type") == "master":
                master_agent = agent
            else:
                slave_agents.append(agent)

        if not master_agent:
            logger.error("未找到Master Agent")
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=["未找到Master Agent"]
            )

        logger.info(f"开始主从执行: {task.task_id}, Master: {master_agent.agent_id}, Slaves: {len(slave_agents)}")

        # 更新任务状态
        await self.context_center.update_task_state(task.task_id, TaskState.RUNNING)

        # Master分析任务并分解
        master_task = Task(
            task_id=f"{task.task_id}_decompose",
            type="task_decomposition",
            description=f"分解任务: {task.description}",
            keywords=task.keywords,
            complexity=task.complexity * 0.3
        )

        master_thought = await master_agent.think(master_task)

        # Master创建执行计划
        decomposition_plan = await self._create_decomposition_plan(task, len(slave_agents))

        logger.info(f"Master分解任务为 {len(decomposition_plan)} 个子任务")

        # 并行执行子任务
        subtasks = []
        for i, (subtask_data, slave) in enumerate(zip(decomposition_plan, slave_agents)):
            subtask_id = f"{task.task_id}_subtask_{i}"

            subtasks.append(
                self._execute_agent_task(
                    slave,
                    subtask_id,
                    {
                        "type": "worker",
                        "description": subtask_data["description"],
                        "keywords": task.keywords,
                        "complexity": subtask_data["complexity"],
                        "context": {"master_plan": decomposition_plan}
                    }
                )
            )

        # 等待所有子任务完成
        results = await asyncio.gather(*subtasks, return_exceptions=True)

        # 收集结果
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"子任务执行异常: {result}")
                continue

            subtask_id, action_result = result
            agent_results[subtask_id] = action_result

            if action_result.success:
                partial_results[subtask_id] = action_result.output

        # Master聚合结果
        aggregated_result = await self._aggregate_slave_results(master_agent, partial_results)

        # Master进行校验
        validation_result = await self._validate_results(master_agent, aggregated_result)

        # 更新任务状态
        if validation_result["valid"]:
            await self.context_center.update_task_state(task.task_id, TaskState.COMPLETED)
        else:
            # 尝试修复
            await self._attempt_recovery(master_agent, partial_results, validation_result)

        execution_time = time.time() - start_time

        return CollaborationResult(
            task_id=task.task_id,
            success=validation_result["valid"],
            final_result=aggregated_result,
            partial_results=partial_results,
            execution_time=execution_time,
            agent_results=agent_results,
            errors=validation_result.get("errors", [])
        )

    async def _create_decomposition_plan(self, task: Task, num_slaves: int) -> List[Dict[str, Any]]:
        """创建分解计划"""
        # 简化实现：平均分解
        step_complexity = task.complexity / num_slaves

        return [
            {
                "description": f"执行任务部分 {i+1}/{num_slaves}",
                "complexity": step_complexity,
                "keywords": task.keywords
            }
            for i in range(num_slaves)
        ]

    async def _aggregate_slave_results(self, master: BaseAgent, partial_results: Dict[str, Any]) -> Any:
        """聚合从Agent结果"""
        # 简单实现：合并所有结果
        successful_results = [r for r in partial_results.values() if r is not None]

        if not successful_results:
            return None

        # 如果是字典，合并
        if isinstance(successful_results[0], dict):
            return {"aggregated": successful_results}

        # 否则返回列表
        return successful_results

    async def _validate_results(self, master: BaseAgent, result: Any) -> Dict[str, Any]:
        """验证结果"""
        # 简单实现：检查结果是否存在
        if result is None:
            return {"valid": False, "errors": ["结果为空"]}

        return {"valid": True, "errors": []}

    async def _attempt_recovery(self, master: BaseAgent, partial_results: Dict, validation: Dict) -> None:
        """尝试恢复"""
        logger.warning("结果验证失败，尝试恢复")


class ReviewStrategy(BaseCollaborationStrategy):
    """评审协作策略 - 多Agent并行，结果通过评审达成共识"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """评审执行

        流程：
        1. 多个Worker Agent并行执行任务
        2. 各Worker提交结果
        3. 评审Agent对结果进行评审
        4. 如有分歧，进行多轮评审和讨论
        5. 达成共识后输出最终结果
        """
        start_time = time.time()
        worker_results = {}
        agent_results = {}

        # 分离Worker和Reviewer
        workers = []
        reviewers = []

        for plan in execution_plan:
            agent_id = plan.get("agent_id")
            role = plan.get("role", "worker")
            agent = next((a for a in agents if a.agent_id == agent_id), None)

            if not agent:
                continue

            if role == "reviewer" or plan.get("agent_type") == "reviewer":
                reviewers.append(agent)
            else:
                workers.append(agent)

        if not reviewers:
            logger.warning("未找到Reviewer，使用默认评审")
            reviewers = workers[:1] if workers else []
            workers = workers[1:] if len(workers) > 1 else workers

        logger.info(f"开始评审执行: {task.task_id}, Workers: {len(workers)}, Reviewers: {len(reviewers)}")

        # 更新任务状态
        await self.context_center.update_task_state(task.task_id, TaskState.RUNNING)

        # 第一轮：Worker并行执行
        subtasks = []
        for i, worker in enumerate(workers):
            subtask_id = f"{task.task_id}_work_{i}"

            subtasks.append(
                self._execute_agent_task(
                    worker,
                    subtask_id,
                    {
                        "type": "worker",
                        "description": f"执行评审任务 {i+1}",
                        "keywords": task.keywords,
                        "complexity": task.complexity
                    }
                )
            )

        # 等待Worker完成
        worker_task_results = await asyncio.gather(*subtasks, return_exceptions=True)

        # 收集Worker结果
        for result in worker_task_results:
            if isinstance(result, Exception):
                logger.error(f"Worker执行异常: {result}")
                continue

            subtask_id, action_result = result
            agent_results[subtask_id] = action_result

            if action_result.success:
                worker_results[subtask_id] = action_result.output

        logger.info(f"Worker执行完成，{len(worker_results)} 个成功")

        # 第二轮：评审
        review_results = await self._perform_review(reviewers, worker_results)

        # 第三轮：共识达成
        final_result = await self._reach_consensus(reviewers, worker_results, review_results)

        # 更新任务状态
        if final_result:
            await self.context_center.update_task_state(task.task_id, TaskState.COMPLETED)
        else:
            await self.context_center.update_task_state(task.task_id, TaskState.FAILED)

        execution_time = time.time() - start_time

        return CollaborationResult(
            task_id=task.task_id,
            success=final_result is not None,
            final_result=final_result,
            partial_results=worker_results,
            execution_time=execution_time,
            agent_results=agent_results
        )

    async def _perform_review(self, reviewers: List[BaseAgent], worker_results: Dict[str, Any]) -> Dict[str, Any]:
        """执行评审"""
        review_results = {}

        for i, reviewer in enumerate(reviewers):
            review_task = Task(
                task_id=f"review_{i}",
                type="review",
                description="评审执行结果",
                keywords=task.keywords if 'task' in locals() else [],
                complexity=0.5
            )

            thought = await reviewer.think(review_task)

            # 评审逻辑（简化）
            review_result = {
                "approved": len(worker_results) > 0,
                "comments": f"评审 {i+1} 完成",
                "suggestions": []
            }

            review_results[f"reviewer_{i}"] = review_result

        return review_results

    async def _reach_consensus(
        self,
        reviewers: List[BaseAgent],
        worker_results: Dict[str, Any],
        review_results: Dict[str, Any]
    ) -> Any:
        """达成共识"""
        # 简单实现：多数评审通过即成功
        approved_count = sum(1 for r in review_results.values() if r.get("approved"))

        if approved_count >= len(reviewers) / 2:
            # 返回所有worker结果的综合
            successful = [r for r in worker_results.values() if r is not None]
            return {"consensus": True, "results": successful}

        return None


class AuctionStrategy(BaseCollaborationStrategy):
    """拍卖协作策略 - 任务发布后，最适合的Agent竞标执行"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """拍卖执行

        流程：
        1. 任务发布到Agent池
        2. 各Agent根据自身能力评估任务
        3. 符合条件的Agent提交投标（Bid）
        4. 调度器选择最优的Agent执行
        5. 执行过程中其他Agent待命
        """
        start_time = time.time()
        agent_results = {}

        logger.info(f"开始拍卖执行: {task.task_id}")

        # 更新任务状态
        await self.context_center.update_task_state(task.task_id, TaskState.RUNNING)

        # 获取中标Agent
        if not execution_plan:
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=["没有Agent参与拍卖"]
            )

        winner_plan = execution_plan[0]  # 简化：直接取第一个
        winner_id = winner_plan.get("agent_id")

        winner = next((a for a in agents if a.agent_id == winner_id), None)

        if not winner:
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=[f"中标Agent {winner_id} 不存在"]
            )

        logger.info(f"拍卖结果: Agent {winner_id} 中标")

        # 执行任务
        subtask_id, result = await self._execute_agent_task(
            winner,
            task.task_id,
            {
                "type": "auction",
                "description": task.description,
                "keywords": task.keywords,
                "complexity": task.complexity
            }
        )

        agent_results[winner_id] = result

        # 更新任务状态
        if result.success:
            await self.context_center.update_task_state(task.task_id, TaskState.COMPLETED)
        else:
            await self.context_center.update_task_state(task.task_id, TaskState.FAILED)

        execution_time = time.time() - start_time

        return CollaborationResult(
            task_id=task.task_id,
            success=result.success,
            final_result=result.output,
            execution_time=execution_time,
            agent_results=agent_results,
            errors=[result.error] if result.error else []
        )


class HybridStrategy(BaseCollaborationStrategy):
    """混合协作策略 - 根据任务特征动态组合多种模式"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """混合执行 - 根据任务特征选择最合适的策略"""

        # 根据任务复杂度选择策略
        if task.complexity < 0.3:
            # 简单任务：直接执行
            return await self._execute_simple_task(task, agents)
        elif task.complexity < 0.6:
            # 中等复杂度：主从模式
            strategy = MasterSlaveStrategy(self.context_center)
            return await strategy.execute(task, agents, execution_plan)
        else:
            # 复杂任务：评审模式
            strategy = ReviewStrategy(self.context_center)
            return await strategy.execute(task, agents, execution_plan)

    async def _execute_simple_task(self, task: Task, agents: List[BaseAgent]) -> CollaborationResult:
        """执行简单任务"""
        start_time = time.time()

        # 直接选择第一个可用Agent
        agent = agents[0] if agents else None

        if not agent:
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=["没有可用Agent"]
            )

        subtask_id, result = await self._execute_agent_task(
            agent,
            task.task_id,
            {
                "type": "simple",
                "description": task.description,
                "keywords": task.keywords,
                "complexity": task.complexity
            }
        )

        await self.context_center.update_task_state(
            task.task_id,
            TaskState.COMPLETED if result.success else TaskState.FAILED
        )

        return CollaborationResult(
            task_id=task.task_id,
            success=result.success,
            final_result=result.output,
            execution_time=time.time() - start_time,
            agent_results={agent.agent_id: result}
        )

# ══════════════════════════════════════════════════════════════════════════════
# 以下内容来自 complex_collaboration.py（复杂协作：拍卖/投票/动态组队）
# ══════════════════════════════════════════════════════════════════════════════

"""
复杂Agent协作模式 - 提升系统处理复杂任务的能力

包含：
1. 递归任务分解
2. 动态团队组建
3. 协商机制
4. 任务拍卖机制
5. 知识共享机制
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


class CollaborationMode(Enum):
    """协作模式"""
    PIPELINE = "pipeline"           # 流水线
    MASTER_SLAVE = "master_slave"   # 主从
    REVIEW = "review"               # 评审
    AUCTION = "auction"             # 拍卖
    CONSENSUS = "consensus"         # 共识
    MARKET = "market"               # 市场
    RECURSIVE = "recursive"         # 递归


@dataclass
class TeamMember:
    """团队成员"""
    agent_id: str
    agent_type: str
    role: str
    capabilities: List[str]
    availability: float
    load: float


@dataclass
class Team:
    """团队"""
    team_id: str
    members: List[TeamMember]
    task_goal: str
    formation_time: float
    status: str = "forming"


@dataclass
class Bid:
    """投标"""
    agent_id: str
    task_id: str
    bid_amount: float
    estimated_time: float
    confidence: float
    timestamp: float


@dataclass
class AuctionResult:
    """拍卖结果"""
    task_id: str
    winner: Optional[str]
    winning_bid: Optional[Bid]
    all_bids: List[Bid]
    status: str


class RecursiveTaskDecomposer:
    """递归任务分解器"""

    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth

    async def decompose_recursive(
        self,
        task: Dict[str, Any],
        depth: int = 0
    ) -> List[Dict[str, Any]]:
        """递归分解任务"""
        if depth >= self.max_depth:
            return [task]

        subtasks = await self._decompose(task)

        if not subtasks or len(subtasks) <= 1:
            return [task]

        result = []
        for subtask in subtasks:
            result.extend(await self.decompose_recursive(subtask, depth + 1))

        return result

    async def _decompose(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """分解单个任务"""
        description = task.get("description", "")
        keywords = task.get("keywords", [])

        subtasks = []

        # 根据任务类型分解
        if "爬取" in description or "抓取" in description:
            subtasks = [
                {
                    "task_id": f"{task['task_id']}_analyze",
                    "type": "analysis",
                    "description": "分析目标网站结构",
                    "keywords": ["分析", "结构"],
                    "parent_id": task["task_id"]
                },
                {
                    "task_id": f"{task['task_id']}_scrape",
                    "type": "scraping",
                    "description": "执行数据抓取",
                    "keywords": ["抓取", "数据"],
                    "parent_id": task["task_id"]
                },
                {
                    "task_id": f"{task['task_id']}_process",
                    "type": "processing",
                    "description": "数据清洗处理",
                    "keywords": ["清洗", "处理"],
                    "parent_id": task["task_id"]
                }
            ]
        elif "分析" in description or "统计" in description:
            subtasks = [
                {
                    "task_id": f"{task['task_id']}_collect",
                    "type": "collection",
                    "description": "收集数据",
                    "keywords": ["收集", "数据"],
                    "parent_id": task["task_id"]
                },
                {
                    "task_id": f"{task['task_id']}_analyze",
                    "type": "analysis",
                    "description": "执行分析",
                    "keywords": ["分析", "统计"],
                    "parent_id": task["task_id"]
                },
                {
                    "task_id": f"{task['task_id']}_report",
                    "type": "reporting",
                    "description": "生成报告",
                    "keywords": ["报告", "总结"],
                    "parent_id": task["task_id"]
                }
            ]

        return subtasks


class DynamicTeamForming:
    """动态团队组建"""

    def __init__(self, communication_center: Any = None):
        self.communication_center = communication_center

    async def form_team(self, task: Dict[str, Any]) -> Team:
        """组建团队"""
        team_id = f"team_{int(time.time())}"
        required_capabilities = self._identify_requirements(task)

        # 查找符合条件的Agent
        candidates = []
        try:
            online = self.communication_center.get_online_agents()
            candidates = [{"agent_id": a} for a in online] if online else []
        except Exception:
            pass

        # 选择最佳组合
        members = []
        for capability in required_capabilities:
            for agent in candidates:
                if capability in agent.get("capabilities", []):
                    members.append(TeamMember(
                        agent_id=agent["agent_id"],
                        agent_type=agent["agent_type"],
                        role=self._determine_role(capability),
                        capabilities=agent.get("capabilities", []),
                        availability=agent.get("availability", 1.0),
                        load=agent.get("load", 0.0)
                    ))
                    break

        return Team(
            team_id=team_id,
            members=members,
            task_goal=task.get("goal", ""),
            formation_time=time.time(),
            status="formed"
        )

    def _identify_requirements(self, task: Dict[str, Any]) -> List[str]:
        """识别任务需求"""
        keywords = task.get("keywords", [])
        requirements = []

        if any(k in ["爬取", "抓取", "网页"] for k in keywords):
            requirements.append("web_scraping")

        if any(k in ["分析", "统计", "数据"] for k in keywords):
            requirements.append("data_analysis")

        if any(k in ["报告", "总结", "可视化"] for k in keywords):
            requirements.append("reporting")

        if any(k in ["安全", "漏洞", "风险"] for k in keywords):
            requirements.append("security_analysis")

        if not requirements:
            requirements.append("general_execution")

        return requirements

    def _determine_role(self, capability: str) -> str:
        """确定角色"""
        role_mapping = {
            "web_scraping": "scraper",
            "data_analysis": "analyst",
            "reporting": "reporter",
            "security_analysis": "security_expert",
            "general_execution": "worker"
        }
        return role_mapping.get(capability, "worker")


class TaskAuction:
    """任务拍卖机制"""

    def __init__(self, communication_center: Any = None):
        self.communication_center = communication_center
        self.active_auctions: Dict[str, List[Bid]] = {}

    async def start_auction(self, task: Dict[str, Any], duration: int = 10) -> AuctionResult:
        """开始拍卖"""
        task_id = task["task_id"]
        self.active_auctions[task_id] = []

        # 通知所有可用Agent
        available_agents = []
        try:
            online = self.communication_center.get_online_agents()
            available_agents = [{"agent_id": a} for a in online] if online else []
        except Exception:
            pass

        # 收集投标
        bids = await self._collect_bids(task, available_agents, duration)

        # 确定赢家
        winner = self._determine_winner(bids)

        result = AuctionResult(
            task_id=task_id,
            winner=winner.agent_id if winner else None,
            winning_bid=winner,
            all_bids=bids,
            status="completed" if winner else "failed"
        )

        del self.active_auctions[task_id]
        return result

    async def _collect_bids(self, task: Dict[str, Any], agents: List[Dict], duration: int) -> List[Bid]:
        """收集投标"""
        bids = []

        async def collect_from_agent(agent):
            try:
                bid = await self._request_bid(agent, task)
                if bid:
                    bids.append(bid)
            except Exception as e:
                logger.error(f"从Agent {agent['agent_id']} 获取投标失败: {e}")

        # 并行收集投标
        tasks = [collect_from_agent(agent) for agent in agents]
        await asyncio.gather(*tasks)

        # 等待剩余时间
        await asyncio.sleep(duration)

        return bids

    async def _request_bid(self, agent: Dict, task: Dict) -> Optional[Bid]:
        """向单个Agent请求投标"""
        # 模拟投标逻辑
        await asyncio.sleep(0.5)

        # 基于Agent能力和负载计算投标
        confidence = min(1.0, agent.get("availability", 1.0) * (1 - agent.get("load", 0.0)))
        estimated_time = 5.0 / confidence
        bid_amount = estimated_time * (1 - agent.get("load", 0.0))

        return Bid(
            agent_id=agent["agent_id"],
            task_id=task["task_id"],
            bid_amount=bid_amount,
            estimated_time=estimated_time,
            confidence=confidence,
            timestamp=time.time()
        )

    def _determine_winner(self, bids: List[Bid]) -> Optional[Bid]:
        """确定赢家"""
        if not bids:
            return None

        # 选择综合评分最高的投标
        # 评分 = 置信度 * (1 - 投标金额/10) * (1 - 预估时间/30)
        best_bid = None
        best_score = -1

        for bid in bids:
            score = bid.confidence * (1 - bid.bid_amount / 10) * (1 - bid.estimated_time / 30)
            if score > best_score:
                best_score = score
                best_bid = bid

        return best_bid


class ConsensusMechanism:
    """共识机制"""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    async def reach_consensus(
        self,
        agents: List[str],
        question: str,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """达成共识"""
        results = await self._collect_votes(agents, question, timeout)

        if not results:
            return {"success": False, "reason": "无响应"}

        # 统计投票
        vote_counts = {}
        for result in results:
            answer = result.get("answer")
            vote_counts[answer] = vote_counts.get(answer, 0) + 1

        # 检查是否达成共识
        total_votes = len(results)
        max_votes = max(vote_counts.values())
        consensus_ratio = max_votes / total_votes

        if consensus_ratio >= self.threshold:
            consensus_answer = max(vote_counts, key=vote_counts.get)
            return {
                "success": True,
                "consensus": consensus_answer,
                "confidence": consensus_ratio,
                "votes": vote_counts,
                "total_voters": total_votes
            }
        else:
            return {
                "success": False,
                "reason": "未达成共识",
                "votes": vote_counts,
                "consensus_ratio": consensus_ratio,
                "total_voters": total_votes
            }

    async def _collect_votes(self, agents: List[str], question: str, timeout: int) -> List[Dict]:
        """收集投票"""
        results = []

        async def vote(agent_id):
            try:
                await asyncio.sleep(1)  # 模拟投票延迟
                results.append({
                    "agent_id": agent_id,
                    "answer": self._simulate_answer(question)
                })
            except Exception as e:
                logger.error(f"Agent {agent_id} 投票失败: {e}")

        tasks = [vote(agent) for agent in agents]
        await asyncio.gather(*tasks)

        return results

    def _simulate_answer(self, question: str) -> str:
        """模拟回答"""
        if "是" in question or "否" in question:
            return "是" if hash(question) % 2 == 0 else "否"
        return "同意" if hash(question) % 3 == 0 else "反对"


class KnowledgeSharing:
    """知识共享机制"""

    def __init__(self):
        self.knowledge_base: Dict[str, Dict[str, Any]] = {}

    async def share_knowledge(self, agent_id: str, knowledge: Dict[str, Any]):
        """共享知识"""
        knowledge_id = f"knowledge_{int(time.time())}"
        self.knowledge_base[knowledge_id] = {
            "agent_id": agent_id,
            "knowledge": knowledge,
            "timestamp": time.time(),
            "access_count": 0
        }
        logger.info(f"Agent {agent_id} 共享了知识: {knowledge_id}")

    async def query_knowledge(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """查询知识"""
        results = []

        for knowledge_id, data in self.knowledge_base.items():
            if self._match(query, data["knowledge"]):
                data["access_count"] += 1
                results.append({
                    "knowledge_id": knowledge_id,
                    "agent_id": data["agent_id"],
                    "knowledge": data["knowledge"],
                    "timestamp": data["timestamp"]
                })

        return sorted(results, key=lambda x: x["timestamp"], reverse=True)[:max_results]

    def _match(self, query: str, knowledge: Dict[str, Any]) -> bool:
        """检查匹配"""
        query_lower = query.lower()
        knowledge_str = str(knowledge).lower()
        return query_lower in knowledge_str

    def get_popular_knowledge(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取热门知识"""
        sorted_items = sorted(
            self.knowledge_base.items(),
            key=lambda x: x[1]["access_count"],
            reverse=True
        )

        return [
            {
                "knowledge_id": k,
                "access_count": v["access_count"],
                "agent_id": v["agent_id"]
            }
            for k, v in sorted_items[:limit]
        ]


class ComplexCollaborationEngine:
    """复杂协作引擎"""

    def __init__(self, communication_center: Any = None):
        self.communication_center = communication_center
        self.decomposer = RecursiveTaskDecomposer()
        self.team_former = DynamicTeamForming(agent_pool)
        self.auction = TaskAuction(agent_pool)
        self.consensus = ConsensusMechanism()
        self.knowledge_sharing = KnowledgeSharing()

    async def execute_complex_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行复杂任务"""
        start_time = time.time()

        # 1. 递归分解任务
        subtasks = await self.decomposer.decompose_recursive(task)
        logger.info(f"任务分解完成，共 {len(subtasks)} 个子任务")

        # 2. 组建团队
        team = await self.team_former.form_team(task)
        logger.info(f"团队组建完成，成员数: {len(team.members)}")

        # 3. 执行子任务（使用拍卖机制）
        results = []
        for subtask in subtasks:
            auction_result = await self.auction.start_auction(subtask, duration=5)

            if auction_result.winner:
                # 分配任务给中标Agent
                result = await self._execute_task(auction_result.winner, subtask)
                results.append(result)
            else:
                results.append({"success": False, "task_id": subtask["task_id"]})

        # 4. 知识共享
        for result in results:
            if result.get("success"):
                await self.knowledge_sharing.share_knowledge(
                    result.get("agent_id", ""),
                    {"task_id": result.get("task_id"), "result": result.get("output")}
                )

        return {
            "success": all(r.get("success") for r in results),
            "task_id": task["task_id"],
            "subtasks_count": len(subtasks),
            "team_size": len(team.members),
            "results": results,
            "execution_time": time.time() - start_time
        }

    async def _execute_task(self, agent_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个任务 — 子类必须覆写，默认抛出"""
        raise NotImplementedError(
            f"_execute_task 需要在子类中实现 (agent={agent_id}, task={task.get('task_id', '?')})"
        )

# ══════════════════════════════════════════════════════════════════════════════
# 以下内容来自 llm_reflection.py（LLM反思：结果评估/计划调整）
# ══════════════════════════════════════════════════════════════════════════════

"""
LLM反思机制 - 模型自我评估与迭代优化

在Pipeline关键节点嵌入LLM反思，实现：
1. 执行结果评估
2. 计划调整决策
3. 动态优化执行流程
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)


class ReflectionDecision(Enum):
    """反思决策类型"""
    CONTINUE = "continue"              # 继续原计划
    SKIP_NEXT = "skip_next"           # 跳过下一步
    ADD_STEPS = "add_steps"           # 添加新步骤
    REORDER = "reorder"               # 调整顺序
    RETRY = "retry"                   # 重试上一步
    FAIL = "fail"                     # 宣告失败


@dataclass
class StepResult:
    """步骤执行结果"""
    step_id: str
    step_name: str
    step_type: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReflectionPrompt:
    """反思Prompt模板"""
    completed_steps: List[StepResult]
    remaining_steps: List[Dict[str, Any]]
    original_goal: str
    task_context: Dict[str, Any]


@dataclass
class ReflectionResult:
    """反思结果"""
    decision: ReflectionDecision
    confidence: float
    reasoning: str
    adjustments: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    new_plan: Optional[List[Dict[str, Any]]] = None


@dataclass
class ReflectionTriggerConfig:
    """反思触发配置"""
    check_on_failure: bool = True
    check_on_timeout: bool = True
    check_interval: int = 3
    confidence_threshold: float = 0.6
    step_timeout_multiplier: float = 2.0
    max_retries: int = 3
    max_reflections: int = 5
    max_plan_adjustments: int = 3


class ReflectionTrigger:
    """反思触发器 - 决定何时进行反思"""

    def __init__(self, config: Optional[ReflectionTriggerConfig] = None):
        self.config = config or ReflectionTriggerConfig()
        self.step_count = 0

    def should_reflect(self, result: StepResult, expected_time: float) -> bool:
        """判断是否应该进行反思"""
        if self.config.check_on_failure and not result.success:
            logger.info(f"反思触发: 步骤 {result.step_id} 执行失败")
            return True

        if self.config.check_on_timeout:
            if result.execution_time > expected_time * self.config.step_timeout_multiplier:
                logger.info(f"反思触发: 步骤 {result.step_id} 执行超时")
                return True

        if result.confidence < self.config.confidence_threshold:
            logger.info(f"反思触发: 步骤 {result.step_id} 置信度过低 ({result.confidence})")
            return True

        self.step_count += 1
        if self.step_count % self.config.check_interval == 0:
            logger.info(f"反思触发: 周期性检查 (第{self.step_count}步)")
            return True

        return False

    def reset(self) -> None:
        """重置触发器"""
        self.step_count = 0


class LLMReflection:
    """LLM反思引擎 - 使用LLM进行反思"""

    def __init__(self, llm_facade: Optional[Any] = None):
        self.llm_facade = llm_facade
        self.reflection_count = 0

    async def reflect(
        self,
        prompt: ReflectionPrompt,
        previous_decision: Optional[ReflectionDecision] = None
    ) -> ReflectionResult:
        """执行反思"""
        self.reflection_count += 1

        logger.info(f"开始第{self.reflection_count}次反思")

        if self.llm_facade:
            return await self._llm_reflect(prompt, previous_decision)
        else:
            return self._heuristic_reflect(prompt, previous_decision)

    async def _llm_reflect(
        self,
        prompt: ReflectionPrompt,
        previous_decision: Optional[ReflectionDecision]
    ) -> ReflectionResult:
        """使用LLM进行反思"""
        reflection_prompt = self._build_reflection_prompt(prompt, previous_decision)

        try:
            response = await self.llm_facade.generate(reflection_prompt)
            return self._parse_llm_response(response, prompt)

        except Exception as e:
            logger.error(f"LLM反思失败: {e}，回退到启发式反思")
            return self._heuristic_reflect(prompt, previous_decision)

    def _build_reflection_prompt(
        self,
        prompt: ReflectionPrompt,
        previous_decision: Optional[ReflectionDecision]
    ) -> Dict[str, Any]:
        """构建反思Prompt"""
        completed_str = "\n".join([
            f"- 步骤{i+1} [{s.step_name}]: {'成功' if s.success else '失败'} "
            f"(置信度: {s.confidence}, 耗时: {s.execution_time:.2f}s)"
            f"{f', 输出: {s.output}' if s.output else ''}"
            f"{f', 错误: {s.error}' if s.error else ''}"
            for i, s in enumerate(prompt.completed_steps)
        ])

        remaining_str = "\n".join([
            f"- 步骤{i+1} [{s['name']}]: {s['description']}"
            for i, s in enumerate(prompt.remaining_steps)
        ])

        system_prompt = """你是一个专业的任务评审专家。你的职责是评估当前任务的执行情况，并决定是否需要调整后续计划。

评估标准：
1. 执行效率：是否在合理时间内完成
2. 输出质量：结果是否符合预期
3. 目标对齐：是否符合原始目标
4. 风险识别：是否存在潜在问题

决策选项：
- CONTINUE: 当前进展良好，继续执行原计划
- SKIP_NEXT: 跳过某些不必要的步骤
- ADD_STEPS: 需要添加额外的步骤
- RETRY: 需要重试上一步骤
- FAIL: 任务无法完成，宣告失败

请给出详细的推理过程和具体的调整建议。"""

        user_prompt = f"""## 原始目标
{prompt.original_goal}

## 已完成步骤
{completed_str or '（暂无）'}

## 剩余计划
{remaining_str or '（无剩余步骤）'}

## 任务上下文
{self._format_context(prompt.task_context)}

{f'## 上次决策: {previous_decision.value}' if previous_decision else ''}

请评估当前执行情况，并给出你的决策和建议。"""

        return {
            "prompt": system_prompt + "\n\n" + user_prompt,
            "metadata": {
                "task_type": "reflection",
                "requirements": ["reflection", "decision"]
            }
        }

    def _parse_llm_response(self, response: str, prompt: ReflectionPrompt) -> ReflectionResult:
        """解析LLM响应"""
        response_lower = response.lower()

        if "fail" in response_lower and ("无法" in response or "不可能" in response):
            decision = ReflectionDecision.FAIL
            confidence = 0.9
        elif "retry" in response_lower or "重试" in response:
            decision = ReflectionDecision.RETRY
            confidence = 0.7
        elif "skip" in response_lower or "跳过" in response:
            decision = ReflectionDecision.SKIP_NEXT
            confidence = 0.6
        elif "add" in response_lower or "添加" in response:
            decision = ReflectionDecision.ADD_STEPS
            confidence = 0.6
        else:
            decision = ReflectionDecision.CONTINUE
            confidence = 0.8

        return ReflectionResult(
            decision=decision,
            confidence=confidence,
            reasoning=response[:500],
            suggestions=[response]
        )

    def _heuristic_reflect(
        self,
        prompt: ReflectionPrompt,
        previous_decision: Optional[ReflectionDecision]
    ) -> ReflectionResult:
        """启发式反思（无LLM时使用）"""
        if not prompt.completed_steps:
            return ReflectionResult(
                decision=ReflectionDecision.CONTINUE,
                confidence=1.0,
                reasoning="暂无执行结果，继续执行"
            )

        failures = [s for s in prompt.completed_steps if not s.success]

        if len(failures) >= 3:
            return ReflectionResult(
                decision=ReflectionDecision.FAIL,
                confidence=0.9,
                reasoning=f"已连续失败{len(failures)}次，继续下去可能无法完成任务"
            )

        avg_confidence = sum(s.confidence for s in prompt.completed_steps) / len(prompt.completed_steps)

        if avg_confidence < 0.5:
            return ReflectionResult(
                decision=ReflectionDecision.RETRY,
                confidence=0.8,
                reasoning=f"平均置信度过低 ({avg_confidence:.2f})，建议重试"
            )

        timeouts = [
            s for s in prompt.completed_steps
            if s.execution_time > 30.0
        ]

        if len(timeouts) >= 2:
            return ReflectionResult(
                decision=ReflectionDecision.CONTINUE,
                confidence=0.7,
                reasoning=f"存在{len(timeouts)}次超时，但仍有进展，继续执行"
            )

        return ReflectionResult(
            decision=ReflectionDecision.CONTINUE,
            confidence=0.8,
            reasoning="执行情况正常，继续原计划"
        )

    def _format_context(self, context: Dict[str, Any]) -> str:
        """格式化上下文"""
        if not context:
            return "无额外上下文"

        return "\n".join([f"- {k}: {v}" for k, v in context.items()])


class AdaptivePipelineWithReflection:
    """带反思机制的自适应Pipeline"""

    def __init__(
        self,
        llm_facade: Optional[Any] = None,
        trigger_config: Optional[ReflectionTriggerConfig] = None
    ):
        self.trigger = ReflectionTrigger(trigger_config)
        self.reflection_engine = LLMReflection(llm_facade)
        self.config = trigger_config or ReflectionTriggerConfig()

        self.total_steps = 0
        self.total_reflections = 0
        self.plan_adjustments = 0

    async def execute_with_reflection(
        self,
        task: Any,
        execution_plan: List[Dict[str, Any]],
        executor: Callable,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """带反思的执行"""
        self.trigger.reset()
        completed_steps: List[StepResult] = []
        current_plan = execution_plan.copy()
        final_result = None

        logger.info(f"开始带反思的Pipeline执行，初始计划: {len(current_plan)} 步")

        while current_plan and self.total_steps < 50:
            if self.total_reflections >= self.config.max_reflections:
                logger.warning(f"已达到最大反思次数 ({self.config.max_reflections})，强制结束")
                break

            current_step = current_plan.pop(0)
            self.total_steps += 1

            expected_time = current_step.get("estimated_time", 10.0)
            result = await executor(current_step, task)

            step_result = StepResult(
                step_id=current_step.get("id", f"step_{self.total_steps}"),
                step_name=current_step.get("name", current_step.get("description", "unknown")),
                step_type=current_step.get("type", "general"),
                success=result.get("success", True),
                output=result.get("output"),
                error=result.get("error"),
                execution_time=result.get("execution_time", 0.0),
                confidence=result.get("confidence", 1.0)
            )

            completed_steps.append(step_result)

            logger.info(
                f"步骤 {self.total_steps} 完成: {step_result.step_name} - "
                f"{'成功' if step_result.success else '失败'} "
                f"(置信度: {step_result.confidence:.2f}, 耗时: {step_result.execution_time:.2f}s)"
            )

            if result.get("done"):
                final_result = result
                logger.info("任务完成")
                break

            if self.trigger.should_reflect(step_result, expected_time):
                self.total_reflections += 1

                prompt = ReflectionPrompt(
                    completed_steps=completed_steps,
                    remaining_steps=current_plan,
                    original_goal=task.get("goal", task.get("description", "")),
                    task_context=context or {}
                )

                reflection_result = await self.reflection_engine.reflect(prompt, None)

                logger.info(
                    f"反思结果: {reflection_result.decision.value} "
                    f"(置信度: {reflection_result.confidence:.2f})"
                )

                current_plan = self._apply_reflection(reflection_result, current_plan, completed_steps)

                if reflection_result.decision == ReflectionDecision.FAIL:
                    logger.error("反思决定：任务失败")
                    return {
                        "success": False,
                        "completed_steps": completed_steps,
                        "reason": reflection_result.reasoning,
                        "total_steps": self.total_steps,
                        "total_reflections": self.total_reflections
                    }

        return {
            "success": final_result is not None,
            "completed_steps": completed_steps,
            "total_steps": self.total_steps,
            "total_reflections": self.total_reflections,
            "final_result": final_result
        }

    def _apply_reflection(
        self,
        reflection: ReflectionResult,
        current_plan: List[Dict[str, Any]],
        completed_steps: List[StepResult]
    ) -> List[Dict[str, Any]]:
        """应用反思决策"""
        new_plan = current_plan.copy()

        if reflection.decision == ReflectionDecision.SKIP_NEXT and new_plan:
            skipped = new_plan.pop(0)
            self.plan_adjustments += 1
            logger.info(f"跳过步骤: {skipped.get('name', skipped.get('description', 'unknown'))}")

        elif reflection.decision == ReflectionDecision.RETRY:
            if completed_steps:
                last_step = completed_steps[-1]
                retry_step = {
                    "id": f"{last_step.step_id}_retry",
                    "name": f"重试: {last_step.step_name}",
                    "type": last_step.step_type,
                    "retry": True
                }
                new_plan.insert(0, retry_step)
                self.plan_adjustments += 1
                logger.info(f"添加重试步骤: {last_step.step_name}")

        elif reflection.decision == ReflectionDecision.ADD_STEPS and reflection.suggestions:
            for suggestion in reflection.suggestions[:2]:
                new_step = {
                    "id": f"added_{uuid.uuid4().hex[:8]}",
                    "name": suggestion,
                    "type": "added",
                    "description": suggestion
                }
                new_plan.append(new_step)
                self.plan_adjustments += 1
                logger.info(f"添加新步骤: {suggestion}")

        elif reflection.decision == ReflectionDecision.REORDER and reflection.new_plan:
            new_plan = reflection.new_plan
            self.plan_adjustments += 1
            logger.info("应用新的执行计划")

        return new_plan

    def get_statistics(self) -> Dict[str, Any]:
        """获取执行统计"""
        return {
            "total_steps": self.total_steps,
            "total_reflections": self.total_reflections,
            "plan_adjustments": self.plan_adjustments,
            "reflection_rate": self.total_reflections / max(self.total_steps, 1)
        }

# ══════════════════════════════════════════════════════════════════════════════
# 以下内容来自 result_aggregator.py（结果聚合：LLM整合/多源归纳）
# ══════════════════════════════════════════════════════════════════════════════

"""
LLM辅助结果聚合模块 - 多源信息的智能整合与归纳

功能：
1. 收集多个Agent的执行结果
2. 使用LLM进行智能整合
3. 生成结构化的最终报告
4. 支持多种聚合策略
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time

logger = logging.getLogger(__name__)


class AggregationStrategy(Enum):
    """聚合策略"""
    SIMPLE_MERGE = "simple_merge"           # 简单合并
    WEIGHTED_VOTE = "weighted_vote"       # 加权投票
    HIERARCHICAL = "hierarchical"           # 层次聚合
    LLM_SUMMARIZE = "llm_summarize"        # LLM总结


@dataclass
class PartialResult:
    """部分结果"""
    source: str                           # 结果来源（Agent ID）
    result_type: str                       # 结果类型
    content: Any                          # 结果内容
    confidence: float = 1.0              # 置信度
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregationConfig:
    """聚合配置"""
    strategy: AggregationStrategy = AggregationStrategy.LLM_SUMMARIZE
    max_results: int = 10                 # 最大结果数
    confidence_threshold: float = 0.5    # 置信度阈值
    use_llm_fallback: bool = True         # LLM失败时回退
    llm_model: str = "gpt-3.5-turbo"     # 使用的LLM模型


@dataclass
class AggregationResult:
    """聚合结果"""
    success: bool
    final_output: Any
    summary: str                          # LLM生成的总结
    metadata: Dict[str, Any] = field(default_factory=dict)
    aggregation_time: float = 0.0
    strategy_used: str = ""


class SimpleAggregator:
    """简单聚合器 - 合并多个结果"""

    def aggregate(self, results: List[PartialResult]) -> AggregationResult:
        """简单合并所有结果"""
        start_time = time.time()

        if not results:
            return AggregationResult(
                success=True,
                final_output=[],
                summary="无结果可聚合"
            )

        successful_results = [r for r in results if r.confidence >= 0.5]

        if not successful_results:
            return AggregationResult(
                success=True,
                final_output=results,
                summary=f"所有{len(results)}个结果置信度都低于阈值"
            )

        return AggregationResult(
            success=True,
            final_output=successful_results,
            summary=f"成功聚合{len(successful_results)}个结果",
            aggregation_time=time.time() - start_time
        )


class WeightedVoteAggregator:
    """加权投票聚合器"""

    def aggregate(self, results: List[PartialResult]) -> AggregationResult:
        """加权投票聚合"""
        start_time = time.time()

        if not results:
            return AggregationResult(
                success=True,
                final_output=[],
                summary="无结果可聚合"
            )

        # 按结果类型分组
        grouped = {}
        for result in results:
            result_type = result.result_type
            if result_type not in grouped:
                grouped[result_type] = []
            grouped[result_type].append(result)

        # 计算每组的加权分数
        aggregated = {}
        for result_type, type_results in grouped.items():
            total_weight = sum(r.confidence for r in type_results)
            weighted_output = {
                "type": result_type,
                "count": len(type_results),
                "total_confidence": total_weight,
                "results": [r.content for r in type_results],
                "avg_confidence": total_weight / len(type_results)
            }
            aggregated[result_type] = weighted_output

        return AggregationResult(
            success=True,
            final_output=aggregated,
            summary=f"加权聚合了{len(grouped)}种类型的结果",
            aggregation_time=time.time() - start_time
        )


class HierarchicalAggregator:
    """层次聚合器 - 先子任务聚合，再总体聚合"""

    def aggregate(self, results: List[PartialResult]) -> AggregationResult:
        """层次聚合"""
        start_time = time.time()

        if not results:
            return AggregationResult(
                success=True,
                final_output={},
                summary="无结果可聚合"
            )

        # 按来源分组
        by_source = {}
        for result in results:
            source = result.source
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(result)

        # 第一层：每个来源内部聚合
        source_aggregates = {}
        for source, source_results in by_source.items():
            source_aggregates[source] = {
                "count": len(source_results),
                "avg_confidence": sum(r.confidence for r in source_results) / len(source_results),
                "results": [r.content for r in source_results],
                "success_rate": len([r for r in source_results if r.confidence >= 0.5]) / len(source_results)
            }

        # 第二层：总体聚合
        total_confidence = sum(v["avg_confidence"] for v in source_aggregates.values())
        overall_quality = total_confidence / len(source_aggregates) if source_aggregates else 0

        final_output = {
            "sources": source_aggregates,
            "overall": {
                "source_count": len(source_aggregates),
                "total_results": len(results),
                "overall_confidence": overall_quality,
                "success_rate": len([r for r in results if r.confidence >= 0.5]) / len(results)
            }
        }

        return AggregationResult(
            success=True,
            final_output=final_output,
            summary=f"层次聚合了{len(source_aggregates)}个来源的{len(results)}个结果",
            aggregation_time=time.time() - start_time
        )


class LLMAggregator:
    """LLM辅助聚合器 - 使用LLM生成总结"""

    def __init__(self, llm_facade: Optional[Any] = None):
        self.llm_facade = llm_facade

    async def aggregate(
        self,
        results: List[PartialResult],
        task_description: str = ""
    ) -> AggregationResult:
        """使用LLM聚合结果"""
        start_time = time.time()

        if not results:
            return AggregationResult(
                success=True,
                final_output=[],
                summary="无结果可聚合"
            )

        # 构建LLM prompt
        prompt = self._build_aggregation_prompt(results, task_description)

        try:
            # 调用LLM
            if self.llm_facade:
                response = await self.llm_facade.generate(prompt)
                summary = response if isinstance(response, str) else response.get("content", "")
            else:
                # 无LLM时使用简单总结
                summary = self._simple_summary(results)

            successful_results = [r for r in results if r.confidence >= 0.5]

            return AggregationResult(
                success=True,
                final_output=successful_results,
                summary=summary,
                metadata={
                    "total_results": len(results),
                    "successful_results": len(successful_results),
                    "llm_used": self.llm_facade is not None
                },
                aggregation_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"LLM聚合失败: {e}")
            # 回退到简单聚合
            simple = SimpleAggregator()
            result = simple.aggregate(results)
            result.strategy_used = "llm_fallback"
            return result

    def _build_aggregation_prompt(
        self,
        results: List[PartialResult],
        task_description: str
    ) -> Dict[str, Any]:
        """构建聚合Prompt"""
        # 构建结果列表
        results_text = []
        for i, r in enumerate(results, 1):
            results_text.append(f"""
结果{i} [来源: {r.source}, 类型: {r.result_type}, 置信度: {r.confidence:.2f}]:
{r.content}
""")

        system_prompt = """你是一个专业的报告生成专家。你的任务是将多个Agent的执行结果整合成一个清晰、简洁的最终报告。

要求：
1. 总结各结果的核心内容
2. 识别结果之间的一致性和差异
3. 提供整体结论和建议
4. 使用清晰的结构化格式
5. 突出关键信息和重要发现

输出格式：
- 执行摘要（一段话概括整体情况）
- 详细结果（按类型分组）
- 关键发现（3-5个要点）
- 建议和结论"""

        user_prompt = f"""## 任务描述
{task_description or '无特定任务描述'}

## 待聚合结果
{"".join(results_text)}

请生成最终报告。"""

        return {
            "prompt": system_prompt + "\n\n" + user_prompt,
            "metadata": {
                "task_type": "aggregation",
                "requirements": ["summary", "structured_output"]
            }
        }

    def _simple_summary(self, results: List[PartialResult]) -> str:
        """简单总结（无LLM时使用）"""
        if not results:
            return "无结果"

        total = len(results)
        successful = len([r for r in results if r.confidence >= 0.5])
        types = set(r.result_type for r in results)

        return f"聚合了{total}个结果，其中{successful}个置信度较高，涉及{len(types)}种类型：{', '.join(types)}"


class ResultAggregator:
    """结果聚合器 - 统一接口"""

    def __init__(self, config: Optional[AggregationConfig] = None, llm_facade: Optional[Any] = None):
        self.config = config or AggregationConfig()
        self.llm_facade = llm_facade

        # 初始化各种聚合器
        self.simple_aggregator = SimpleAggregator()
        self.weighted_aggregator = WeightedVoteAggregator()
        self.hierarchical_aggregator = HierarchicalAggregator()
        self.llm_aggregator = LLMAggregator(llm_facade)

    async def aggregate(
        self,
        results: List[PartialResult],
        task_description: str = ""
    ) -> AggregationResult:
        """聚合多个结果"""
        strategy = self.config.strategy

        logger.info(f"开始聚合，使用策略: {strategy.value}")

        if strategy == AggregationStrategy.SIMPLE_MERGE:
            result = self.simple_aggregator.aggregate(results)
            result.strategy_used = strategy.value
            return result

        elif strategy == AggregationStrategy.WEIGHTED_VOTE:
            result = self.weighted_aggregator.aggregate(results)
            result.strategy_used = strategy.value
            return result

        elif strategy == AggregationStrategy.HIERARCHICAL:
            result = self.hierarchical_aggregator.aggregate(results)
            result.strategy_used = strategy.value
            return result

        elif strategy == AggregationStrategy.LLM_SUMMARIZE:
            return await self.llm_aggregator.aggregate(results, task_description)

        else:
            # 默认使用简单聚合
            result = self.simple_aggregator.aggregate(results)
            result.strategy_used = "default"
            return result

    def aggregate_sync(
        self,
        results: List[PartialResult],
        task_description: str = ""
    ) -> AggregationResult:
        """同步聚合（不使用LLM）"""
        if self.config.strategy == AggregationStrategy.LLM_SUMMARIZE:
            # 回退到层次聚合
            result = self.hierarchical_aggregator.aggregate(results)
            result.strategy_used = "hierarchical_fallback"
            return result

        return asyncio.run(self.aggregate(results, task_description))

    def set_strategy(self, strategy: AggregationStrategy) -> None:
        """设置聚合策略"""
        self.config.strategy = strategy
        logger.info(f"聚合策略已更新: {strategy.value}")


class MasterAgentAggregator:
    """MasterAgent专用的结果聚合器"""

    def __init__(self, llm_facade: Optional[Any] = None):
        self.aggregator = ResultAggregator(
            config=AggregationConfig(
                strategy=AggregationStrategy.LLM_SUMMARIZE
            ),
            llm_facade=llm_facade
        )

    async def aggregate_master_results(
        self,
        subtask_results: Dict[str, Any],
        task_goal: str
    ) -> AggregationResult:
        """聚合MasterAgent的子任务结果

        Args:
            subtask_results: 子任务ID -> 结果 的字典
            task_goal: 原始任务目标

        Returns:
            聚合结果
        """
        # 转换为PartialResult列表
        partial_results = []
        for subtask_id, result in subtask_results.items():
            partial_results.append(PartialResult(
                source=result.get("agent_id", subtask_id),
                result_type=result.get("type", "unknown"),
                content=result.get("output"),
                confidence=result.get("confidence", 0.8),
                metadata=result
            ))

        # 聚合
        return await self.aggregator.aggregate(partial_results, task_goal)


# ══════════════════════════════════════════════════════════════════════
# LLM 动态策略选择 — 替换硬编码的规则
# ══════════════════════════════════════════════════════════════════════

async def select_strategy_with_llm(
    task_description: str,
    task_keywords: list,
    estimated_steps: int,
    complexity: float,
    available_agents: list,
    llm_router=None,
) -> tuple:
    """调用 LLM 选择协作策略，返回 (mode, params)

    Args:
        task_description: 任务描述
        task_keywords: 任务关键词
        estimated_steps: 预估步骤数
        complexity: 复杂度 (0-1)
        available_agents: 可用Agent列表
        llm_router: LLM路由实例

    Returns:
        (mode_str: str, params: dict) — 例如 ("pipeline", {"parallelism": 3})
        失败时返回硬编码规则的兜底结果
    """
    # 兜底：硬编码规则
    def fallback() -> tuple:
        if complexity > 0.8:
            return "review", {"reviewers": max(1, len(available_agents)//2)}
        if estimated_steps > 2 and estimated_steps <= len(available_agents):
            return "pipeline", {"parallelism": min(estimated_steps, len(available_agents))}
        if complexity > 0.5:
            return "master_slave", {"slaves": max(1, len(available_agents)-1)}
        if len(task_keywords) > 3:
            return "auction", {}  # 多技能需求 -> 拍卖
        return "hybrid", {}

    # 没有 LLM 时直接走兜底
    if not llm_router:
        return fallback()

    from core.engine.llm_backend import GLMBackend

    # 构建 prompt
    agents_summary = "\n".join([
        f"- {getattr(a, 'agent_name', 'unknown')} "
        f"(type: {getattr(a, 'agent_type', '?')}, "
        f"capabilities: {[c.name for c in getattr(a, 'capabilities', [])][:3]})"
        for a in available_agents[:10]
    ]) if available_agents else "无可用Agent信息"

    prompt = f"""根据以下任务信息，选择最合适的多Agent协作策略。

任务描述: {task_description}
关键词: {task_keywords}
预估步骤数: {estimated_steps}
复杂度: {complexity}

可用Agent:\n{agents_summary}

可选策略:\n- pipeline: 流水线顺序执行，每阶段专注特定任务\n- master_slave: 主从模式，主Agent分解，从Agent并行执行\n- review: 评审模式，多Agent并行 + 评审达成共识\n- auction: 拍卖模式，任务发布后最合适的Agent竞标执行\n- hybrid: 混合模式，动态组合多种策略\n\n请只输出JSON格式，不要其他内容:\n{{"mode": "策略名", "params": {{"并行度": 数字, "重试次数": 数字, "评审阈值": 0-1}}}}\n"""

    try:
        messages = [
            {"role": "system", "content": "你是一个多Agent协作策略专家，根据任务特征选择最优策略。"},
            {"role": "user", "content": prompt}
        ]
        if hasattr(llm_router, "chat"):
            response = await llm_router.chat(messages, temperature=0.3, max_tokens=300)
        else:
            return fallback()

        import json
        # 尝试解析JSON
        result = json.loads(response.strip().strip("```json").strip("```").strip())
        mode = result.get("mode", "hybrid")
        params = result.get("params", {})
        if mode not in ("pipeline", "master_slave", "review", "auction", "hybrid"):
            return fallback()
        return mode, params

    except Exception as e:
        logger.warning(f"LLM策略选择失败，使用兜底规则: {e}")
        return fallback()
