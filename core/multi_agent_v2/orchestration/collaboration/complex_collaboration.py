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

    def __init__(self, agent_pool: Any):
        self.agent_pool = agent_pool

    async def form_team(self, task: Dict[str, Any]) -> Team:
        """组建团队"""
        team_id = f"team_{int(time.time())}"
        required_capabilities = self._identify_requirements(task)

        # 查找符合条件的Agent
        candidates = await self.agent_pool.find_agents_by_capabilities(required_capabilities)

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

    def __init__(self, agent_pool: Any):
        self.agent_pool = agent_pool
        self.active_auctions: Dict[str, List[Bid]] = {}

    async def start_auction(self, task: Dict[str, Any], duration: int = 10) -> AuctionResult:
        """开始拍卖"""
        task_id = task["task_id"]
        self.active_auctions[task_id] = []

        # 通知所有可用Agent
        available_agents = await self.agent_pool.get_available_agents()

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

    def __init__(self, agent_pool: Any):
        self.agent_pool = agent_pool
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
        """执行单个任务"""
        await asyncio.sleep(1)  # 模拟执行时间
        return {
            "success": True,
            "agent_id": agent_id,
            "task_id": task["task_id"],
            "output": f"任务 {task['task_id']} 已完成",
            "execution_time": 1.0
        }
