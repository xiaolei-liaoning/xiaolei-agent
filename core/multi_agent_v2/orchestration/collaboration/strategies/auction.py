"""
拍卖协作策略 - 任务发布后，最适合的Agent"竞标"执行

包含：
1. AuctionStrategy - 拍卖协作策略
2. 拍卖相关数据类 (TeamMember, Team, Bid, AuctionResult)
3. DynamicTeamForming - 动态团队组建
4. TaskAuction - 任务拍卖机制
5. ComplexCollaborationEngine - 复杂协作引擎
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.agents.base.base_agent import BaseAgent, Task
from core.multi_agent_v2.orchestration.context.global_context_center import TaskState

from .base import BaseCollaborationStrategy, CollaborationResult

logger = logging.getLogger(__name__)


# =============================================================================
# 数据类
# =============================================================================

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


# =============================================================================
# AuctionStrategy
# =============================================================================

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

        if not winner_id:
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=["拍卖执行计划中缺少 agent_id"]
            )

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


# =============================================================================
# 动态团队组建
# =============================================================================

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
            if online:
                # online 可能是 [agent_id, ...] 或 [{"agent_id": id, ...}, ...]
                candidates = [
                    a if isinstance(a, dict) else {"agent_id": a}
                    for a in online
                ]
        except Exception:
            pass

        # 选择最佳组合
        members = []
        for capability in required_capabilities:
            for agent_candidate in candidates:
                caps = agent_candidate.get("capabilities", [])
                if capability in caps or not caps:
                    members.append(TeamMember(
                        agent_id=agent_candidate["agent_id"],
                        agent_type=agent_candidate.get("agent_type", "unknown"),
                        role=self._determine_role(capability),
                        capabilities=caps or [capability],
                        availability=agent_candidate.get("availability", 1.0),
                        load=agent_candidate.get("load", 0.0)
                    ))
                    break

        logger.info(
            f"团队组建完成: team_id={team_id}, "
            f"需求={required_capabilities}, "
            f"匹配={len(members)}/{len(required_capabilities)}"
        )

        return Team(
            team_id=team_id,
            members=members,
            task_goal=task.get("goal", ""),
            formation_time=time.time(),
            status="formed" if members else "failed"
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


# =============================================================================
# 任务拍卖机制
# =============================================================================

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
        """收集投标（用 duration 作为超时，不额外 sleep）"""
        bids = []

        async def collect_from_agent(agent):
            try:
                bid = await self._request_bid(agent, task)
                if bid:
                    bids.append(bid)
            except Exception as e:
                logger.error(f"从Agent {agent['agent_id']} 获取投标失败: {e}")

        # 并行收集投标，使用 duration 作为超时
        tasks = [asyncio.create_task(collect_from_agent(agent)) for agent in agents]
        done, pending = await asyncio.wait(tasks, timeout=duration)
        for task in pending:
            task.cancel()

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


# =============================================================================
# 复杂协作引擎
# =============================================================================

class ComplexCollaborationEngine:
    """复杂协作引擎

    注：此引擎当前为实验性实现。_execute_task 需要构造时提供 agents 映射
    (agent_id -> BaseAgent) 才能实际执行任务。不提供 agents 时任务仅记录为"未执行"。
    """

    def __init__(
        self,
        communication_center: Any = None,
        agents: Optional[Dict[str, Any]] = None,
    ):
        self.communication_center = communication_center
        self._agents = agents or {}

        # 使用延迟导入以避免循环依赖
        from .pipeline import RecursiveTaskDecomposer
        from .review import ConsensusMechanism
        from .base import KnowledgeSharing

        self.decomposer = RecursiveTaskDecomposer()
        self.team_former = DynamicTeamForming(communication_center)
        self.auction = TaskAuction(communication_center)
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
        """执行单个任务"""
        agent = self._agents.get(agent_id)

        if agent is None:
            logger.warning(
                f"ComplexCollaborationEngine: 未找到Agent {agent_id}，"
                f"任务 {task.get('task_id', '?')} 标记为未执行。"
                f"请在构造时传入 agents={{agent_id: agent_obj}}。"
            )
            return {
                "success": False,
                "task_id": task.get("task_id", "?"),
                "agent_id": agent_id,
                "error": f"Agent {agent_id} not available (provide agents dict to constructor)"
            }

        try:
            subtask = Task(
                task_id=task.get("task_id", f"complex_{agent_id}"),
                type=task.get("type", "subtask"),
                description=task.get("description", ""),
                keywords=task.get("keywords", []),
                complexity=task.get("complexity", 0.5)
            )
            thought = await agent.think(subtask)
            result = await agent.act(thought.plan, getattr(thought, 'tool_calls', None))
            await agent.reflect(result)

            return {
                "success": result.success,
                "task_id": subtask.task_id,
                "agent_id": agent_id,
                "output": result.output,
                "error": result.error
            }
        except Exception as e:
            logger.error(f"ComplexCollaborationEngine 执行子任务失败: {e}")
            return {
                "success": False,
                "task_id": task.get("task_id", "?"),
                "agent_id": agent_id,
                "error": str(e)
            }
