"""智能任务规划器 - 实现真正的任务拆解和执行图生成

提供：
1. LLM驱动的任务拆解
2. 执行图生成
3. 动态任务优先级调整
4. 依赖关系管理
5. 执行结果反思
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import uuid

from .llm_backend import get_llm_router

logger = logging.getLogger(__name__)


@dataclass
class PlanNode:
    """任务节点"""
    id: str
    agent_type: str
    task_type: str
    params: Dict[str, Any]
    dependencies: List[str] = None
    priority: int = 5
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None
    error: Optional[str] = None
    
    def to_dict(self):
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "task_type": self.task_type,
            "params": self.params,
            "dependencies": self.dependencies or [],
            "priority": self.priority,
            "status": self.status,
            "result": self.result,
            "error": self.error
        }


@dataclass
class ExecutionPlan:
    """执行计划"""
    id: str
    user_query: str
    nodes: List[PlanNode]
    created_at: float
    status: str = "draft"  # draft, executing, completed, failed
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_query": self.user_query,
            "nodes": [node.to_dict() for node in self.nodes],
            "created_at": self.created_at,
            "status": self.status
        }


class IntelligentPlanner:
    """智能任务规划器"""
    
    def __init__(self):
        self.llm_router = get_llm_router()
        self.plans = {}  # plan_id -> ExecutionPlan
        logger.info("智能任务规划器初始化完成")
    
    async def create_plan(self, user_query: str) -> ExecutionPlan:
        """创建执行计划"""
        plan_id = str(uuid.uuid4())
        logger.info(f"开始创建执行计划: {user_query[:50]}...")
        
        # 1. 使用LLM生成执行图
        plan_nodes = await self._generate_execution_graph(user_query)
        
        # 2. 创建执行计划
        plan = ExecutionPlan(
            id=plan_id,
            user_query=user_query,
            nodes=plan_nodes,
            created_at=asyncio.get_event_loop().time(),
            status="draft"
        )
        
        self.plans[plan_id] = plan
        logger.info(f"执行计划创建完成: {plan_id}, 共 {len(plan_nodes)} 个节点")
        
        return plan
    
    async def execute_plan(self, plan_id: str) -> Dict[str, Any]:
        """执行计划"""
        if plan_id not in self.plans:
            raise ValueError(f"计划不存在: {plan_id}")
        
        plan = self.plans[plan_id]
        plan.status = "executing"
        
        results = []
        completed_nodes = set()
        failed_nodes = set()
        
        while completed_nodes.union(failed_nodes) != {node.id for node in plan.nodes}:
            # 找到可以执行的节点（所有依赖已完成）
            ready_nodes = [
                node for node in plan.nodes 
                if node.status == "pending" 
                and set(node.dependencies or []).issubset(completed_nodes)
            ]
            
            if not ready_nodes:
                # 检查是否有无法执行的节点（依赖失败）
                pending_nodes = [node for node in plan.nodes if node.status == "pending"]
                if pending_nodes:
                    logger.warning(f"存在无法执行的节点: {[n.id for n in pending_nodes]}")
                    plan.status = "failed"
                    break
                break
            
            # 按优先级排序
            ready_nodes.sort(key=lambda n: -n.priority)
            
            # 并行执行所有准备好的节点
            tasks = []
            for node in ready_nodes:
                node.status = "running"
                task = asyncio.create_task(self._execute_node(node, plan))
                tasks.append((node.id, task))
            
            for node_id, task in tasks:
                try:
                    result = await task
                    node = next(n for n in plan.nodes if n.id == node_id)
                    node.status = "completed"
                    node.result = result
                    completed_nodes.add(node_id)
                    results.append(result)
                    
                    # 记录执行结果到监控
                    logger.info(f"节点执行成功: {node_id}")
                    
                except Exception as e:
                    node = next(n for n in plan.nodes if n.id == node_id)
                    node.status = "failed"
                    node.error = str(e)
                    failed_nodes.add(node_id)
                    logger.error(f"节点执行失败: {node_id} - {e}")
        
        # 执行反思阶段
        if failed_nodes:
            await self._reflect_and_retry(plan, failed_nodes)
        
        plan.status = "completed" if not failed_nodes else "failed"
        return {"plan_id": plan_id, "status": plan.status, "results": results}
    
    async def _generate_execution_graph(self, user_query: str) -> List[PlanNode]:
        """使用LLM生成执行图"""
        try:
            prompt = self._build_prompt(user_query)
            response = await self.llm_router.simple_chat(
                user_message=prompt,
                system_prompt="你是一个专业的任务规划助手，请按照要求的JSON格式输出执行计划。",
                temperature=0.3
            )
            
            return self._parse_plan(response, user_query)
        except Exception as e:
            logger.error(f"LLM生成计划失败，使用默认计划: {e}")
            return self._create_default_plan(user_query)
    
    def _build_prompt(self, user_query: str) -> str:
        """构建规划提示词"""
        return f"""你是一个专业的任务规划助手。请将用户的任务拆解为多个可执行的子任务，生成详细的执行计划。

用户任务：{user_query}

可用Agent类型：
- checker: 网站检查、系统检查
- scraper: 网页爬取、搜索
- vulnerability: 漏洞扫描、分析
- summarizer: 文本总结、报告生成
- data_analysis: 数据分析、可视化
- nlp: 情感分析、翻译、NER
- text_analyzer: 文本拆解、提取
- planning: 任务规划

请按照以下JSON格式输出：
{{
    "nodes": [
        {{
            "id": "node_1",
            "agent_type": "scraper",
            "task_type": "search",
            "params": {{"query": "搜索关键词"}},
            "dependencies": [],
            "priority": 5
        }}
    ],
    "reasoning": "分解理由"
}}

注意：
1. 子任务之间要有逻辑顺序和依赖关系
2. dependencies是依赖的前置节点ID列表
3. priority范围1-10，数字越大优先级越高
4. 复杂任务需要多个步骤
5. 输出必须是有效的JSON格式
"""
    
    def _parse_plan(self, response: str, user_query: str) -> List[PlanNode]:
        """解析LLM响应"""
        try:
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            data = json.loads(response)
            nodes = []
            
            for node_data in data.get("nodes", []):
                node = PlanNode(
                    id=node_data.get("id", str(uuid.uuid4())),
                    agent_type=node_data.get("agent_type", "summarizer"),
                    task_type=node_data.get("task_type", "chat"),
                    params=node_data.get("params", {}),
                    dependencies=node_data.get("dependencies", []),
                    priority=node_data.get("priority", 5)
                )
                nodes.append(node)
            
            return nodes
        except Exception as e:
            logger.error(f"解析计划失败: {e}")
            return self._create_default_plan(user_query)
    
    def _create_default_plan(self, user_query: str) -> List[PlanNode]:
        """创建默认计划（降级方案）"""
        return [
            PlanNode(
                id="node_1",
                agent_type="summarizer",
                task_type="chat",
                params={"message": user_query},
                dependencies=[],
                priority=5
            )
        ]
    
    async def _execute_node(self, node: PlanNode, plan: ExecutionPlan) -> Any:
        """执行单个节点"""
        # 获取Agent调度器
        from .multi_agent_system import agent_scheduler
        
        params = node.params.copy()
        
        # 注入依赖结果
        for dep_id in node.dependencies or []:
            dep_node = next((n for n in plan.nodes if n.id == dep_id), None)
            if dep_node and dep_node.result:
                params[f"_{dep_id}_result"] = dep_node.result
        
        # 提交任务
        result = await agent_scheduler.submit_task(
            task_type=node.task_type,
            params=params
        )
        
        return result
    
    async def _reflect_and_retry(self, plan: ExecutionPlan, failed_nodes: set):
        """反思失败并尝试重试"""
        logger.info(f"反思失败节点: {failed_nodes}")
        
        for node_id in failed_nodes:
            node = next(n for n in plan.nodes if n.id == node_id)
            
            # 简单重试逻辑
            if node.params.get("_retry_count", 0) < 2:
                node.params["_retry_count"] = node.params.get("_retry_count", 0) + 1
                node.status = "pending"
                logger.info(f"重新执行节点: {node_id}")
    
    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """获取计划"""
        return self.plans.get(plan_id)
    
    def cancel_plan(self, plan_id: str):
        """取消计划"""
        if plan_id in self.plans:
            del self.plans[plan_id]
            logger.info(f"计划已取消: {plan_id}")


# 全局规划器实例
intelligent_planner = IntelligentPlanner()
