"""Agent协调器（已废弃 - DEPRECATED）

⚠️ 此模块当前未被主流程使用，仅初始化但未调用coordinate方法。
如需Agent协调功能，请直接使用 AgentScheduler。

实现Agent之间的协同协作，升级了调度中心路由评分体系：
- 多维加权路由模型
- 考虑优先级、服务健康度、执行时间和成功率
- 动态负载均衡
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import uuid

from .message_bus import message_bus
from .multi_agent_system import agent_scheduler
from .cluster_manager import get_cluster_manager, AgentInstance

logger = logging.getLogger(__name__)


@dataclass
class AgentMetrics:
    """Agent性能指标"""
    agent_type: str
    priority: float = 1.0              # 优先级权重 (0-1)
    health_score: float = 1.0          # 健康度 (0-1)
    avg_execution_time: float = 0.0    # 平均执行时间（秒）
    success_rate: float = 1.0          # 成功率 (0-1)
    total_tasks: int = 0               # 总任务数
    failed_tasks: int = 0              # 失败任务数
    last_active: float = 0.0           # 最后活跃时间戳
    
    # 动态权重配置（基于历史表现自动调整）
    _dynamic_weights: Dict[str, float] = field(default_factory=lambda: {
        "priority": 0.30,
        "health_score": 0.25,
        "execution_time": 0.20,
        "success_rate": 0.25
    })
    _weight_update_count: int = 0      # 权重更新次数
    
    def calculate_routing_score(self) -> float:
        """计算路由评分（多维加权模型）
        
        权重分配：
        - 优先级: 0.30（可动态调整）
        - 健康度: 0.25（可动态调整）
        - 执行时间: 0.20 (越短越好，可动态调整)
        - 成功率: 0.25（可动态调整）
        
        Returns:
            路由评分 (0-1)，越高越优先
        """
        # 执行时间分数（归一化到0-1，假设最大可接受时间为60秒）
        max_acceptable_time = 60.0
        if self.avg_execution_time > 0:
            time_score = max(0, 1.0 - (self.avg_execution_time / max_acceptable_time))
        else:
            time_score = 1.0  # 无历史数据时给满分
        
        # 动态权重调整：当任务数>10时，根据历史表现调整权重
        if self.total_tasks > 10:
            self._adjust_weights_based_on_performance()
        
        # 使用当前权重计算
        w = self._dynamic_weights
        score = (
            self.priority * w["priority"] +
            self.health_score * w["health_score"] +
            time_score * w["execution_time"] +
            self.success_rate * w["success_rate"]
        )
        
        return round(score, 4)
    
    def _adjust_weights_based_on_performance(self):
        """基于历史表现动态调整权重
        
        调整策略：
        - 如果成功率波动大 → 提高success_rate权重
        - 如果执行时间波动大 → 提高execution_time权重
        - 每50次任务重新评估一次
        """
        # 每50次任务才调整一次，避免频繁变化
        if self._weight_update_count % 50 != 0 and self._weight_update_count > 0:
            return
        
        self._weight_update_count += 1
        
        # 计算各指标的稳定性（标准差越小越稳定）
        # 简化版：用成功率作为稳定性指标
        if self.success_rate < 0.8:  # 成功率低于80%
            # 提高成功率权重，降低其他权重
            self._dynamic_weights["success_rate"] = 0.35
            self._dynamic_weights["priority"] = 0.25
            self._dynamic_weights["health_score"] = 0.20
            self._dynamic_weights["execution_time"] = 0.20
        elif self.avg_execution_time > 30:  # 平均执行时间超过30秒
            # 提高执行时间权重
            self._dynamic_weights["execution_time"] = 0.30
            self._dynamic_weights["success_rate"] = 0.25
            self._dynamic_weights["priority"] = 0.25
            self._dynamic_weights["health_score"] = 0.20
        else:
            # 恢复默认权重
            self._dynamic_weights = {
                "priority": 0.30,
                "health_score": 0.25,
                "execution_time": 0.20,
                "success_rate": 0.25
            }
    
    def update_metrics(self, execution_time: float, success: bool):
        """更新性能指标
        
        Args:
            execution_time: 执行时间（秒）
            success: 是否成功
        """
        self.total_tasks += 1
        if not success:
            self.failed_tasks += 1
        
        # 更新成功率
        if self.total_tasks > 0:
            self.success_rate = 1.0 - (self.failed_tasks / self.total_tasks)
        
        # 更新平均执行时间（移动平均）
        alpha = 0.3  # 平滑系数
        if self.avg_execution_time == 0:
            self.avg_execution_time = execution_time
        else:
            self.avg_execution_time = alpha * execution_time + (1 - alpha) * self.avg_execution_time
        
        # 更新最后活跃时间
        self.last_active = time.time()


class CoordinationTask:
    """协调任务状态"""
    
    def __init__(self, coordination_id: str, task: Dict[str, Any], expected_count: int = 0):
        self.coordination_id = coordination_id
        self.task = task
        self.expected_count = expected_count
        self.completed_count = 0
        self.subtask_results = {}  # subtask_id -> {status, result, completed_at}
        self.completed_event = asyncio.Event()
        self.created_at = time.time()


class AgentRouter:
    """Agent路由器（多维加权模型）"""
    
    def __init__(self):
        self.agent_metrics: Dict[str, AgentMetrics] = {}
        logger.info("AgentRouter 初始化完成")
    
    def register_agent(self, agent_type: str, priority: float = 1.0):
        """注册Agent
        
        Args:
            agent_type: Agent类型
            priority: 优先级 (0-1)
        """
        if agent_type not in self.agent_metrics:
            self.agent_metrics[agent_type] = AgentMetrics(
                agent_type=agent_type,
                priority=priority
            )
            logger.info("注册Agent: %s (priority=%.2f)", agent_type, priority)
    
    def update_health(self, agent_type: str, health_score: float):
        """更新Agent健康度
        
        Args:
            agent_type: Agent类型
            health_score: 健康度 (0-1)
        """
        if agent_type in self.agent_metrics:
            self.agent_metrics[agent_type].health_score = health_score
            logger.debug("更新Agent健康度: %s = %.2f", agent_type, health_score)
    
    def record_execution(self, agent_type: str, execution_time: float, success: bool):
        """记录执行结果
        
        Args:
            agent_type: Agent类型
            execution_time: 执行时间
            success: 是否成功
        """
        if agent_type in self.agent_metrics:
            self.agent_metrics[agent_type].update_metrics(execution_time, success)
    
    def select_best_agent(self, task_type: str, 
                         candidate_agents: Optional[List[str]] = None) -> Optional[str]:
        """选择最优Agent
        
        Args:
            task_type: 任务类型
            candidate_agents: 候选Agent列表（None表示所有已注册的Agent）
            
        Returns:
            最优Agent类型
        """
        # 确定候选Agent
        if candidate_agents is None:
            candidates = list(self.agent_metrics.keys())
        else:
            candidates = [a for a in candidate_agents if a in self.agent_metrics]
        
        if not candidates:
            logger.warning("没有可用的候选Agent")
            return None
        
        # 计算每个候选Agent的评分
        scored_agents = []
        for agent_type in candidates:
            metrics = self.agent_metrics[agent_type]
            score = metrics.calculate_routing_score()
            scored_agents.append((agent_type, score))
        
        # 按评分排序
        scored_agents.sort(key=lambda x: x[1], reverse=True)
        
        # 返回最高分的Agent
        best_agent = scored_agents[0][0]
        best_score = scored_agents[0][1]
        
        logger.info("选择Agent: %s (score=%.4f, task=%s)", best_agent, best_score, task_type)
        return best_agent
    
    def get_all_scores(self) -> Dict[str, float]:
        """获取所有Agent的评分
        
        Returns:
            {agent_type: score}
        """
        return {
            agent_type: metrics.calculate_routing_score()
            for agent_type, metrics in self.agent_metrics.items()
        }


class AgentCoordinator:
    """Agent协调器（优化版）"""
    
    def __init__(self):
        self.message_bus = message_bus
        self.agents = {}
        self.running = False
        self.router = AgentRouter()  # 智能路由器
        
        # 集成集群管理器
        self.cluster_manager = get_cluster_manager()
        
        # 任务状态管理
        self.coordination_tasks = {}  # coordination_id -> CoordinationTask
        
        self._register_handlers()
        logger.info("Agent协调器初始化完成（优化版 + 集群管理器集成）")
    
    async def start(self):
        """启动Agent协调器"""
        if not self.running:
            self.running = True
            # 启动集群管理器
            await self.cluster_manager.start()
            # 注册默认Agent
            self._register_default_agents()
            logger.info("Agent协调器已启动")
    
    async def stop(self):
        """停止Agent协调器"""
        if self.running:
            self.running = False
            # 停止集群管理器
            await self.cluster_manager.stop()
            logger.info("Agent协调器已停止")
    
    def _register_default_agents(self):
        """注册默认Agent"""
        default_agents = {
            "scraper": 0.9,      # 爬虫Agent，高优先级
            "checker": 0.8,      # 校验Agent
            "summarizer": 0.7,   # 摘要Agent
            "vulnerability": 0.85,  # 漏洞检测Agent
            "analyzer": 0.75,    # 分析Agent
        }
        
        for agent_type, priority in default_agents.items():
            # 注册到路由器
            self.router.register_agent(agent_type, priority)
            # 注册到集群管理器
            self.cluster_manager.load_balancer.set_base_weight(agent_type, priority)
            # 注册Agent实例
            instance = AgentInstance(
                agent_type=agent_type,
                instance_id=f"{agent_type}_001",
                status="running",
                load=0.0,
                success_rate=1.0
            )
            self.cluster_manager.load_balancer.register_instance(instance)
            # 设置弹性伸缩限制
            self.cluster_manager.scaler.set_instance_limits(agent_type, 1, 3)
    
    def _register_handlers(self):
        """注册消息处理器"""
        # 注册任务分配处理器
        async def task_allocation_handler(message: Dict[str, Any]):
            await self._handle_task_allocation(message)
        
        # 注册任务完成处理器
        async def task_completion_handler(message: Dict[str, Any]):
            await self._handle_task_completion(message)
        
        # 注册Agent状态更新处理器
        async def agent_status_handler(message: Dict[str, Any]):
            await self._handle_agent_status(message)
        
        # 订阅相关主题
        asyncio.create_task(self.message_bus.subscribe("task_allocation", task_allocation_handler))
        asyncio.create_task(self.message_bus.subscribe("task_completion", task_completion_handler))
        asyncio.create_task(self.message_bus.subscribe("agent_status", agent_status_handler))
    
    async def coordinate(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """协调多个Agent完成复杂任务（使用智能路由）
        
        Args:
            task: 任务信息
            
        Returns:
            协调结果
        """
        task_id = str(uuid.uuid4())
        task["coordination_id"] = task_id
        
        logger.info(f"开始协调任务: {task_id} (type={task.get('type')})")
        
        try:
            # 分析任务需求
            required_agents = self._analyze_task_requirements(task)
            logger.info(f"任务需要的Agent: {required_agents}")
            
            # 创建协调任务状态
            coord_task = CoordinationTask(
                coordination_id=task_id,
                task=task,
                expected_count=len(required_agents)
            )
            self.coordination_tasks[task_id] = coord_task
            
            # 使用智能路由选择最优Agent
            selected_agents = []
            for agent_type in required_agents:
                # 优先使用集群管理器选择Agent实例
                selected_instance = self.cluster_manager.select_agent(agent_type, task)
                if selected_instance:
                    selected_agents.append(selected_instance)
                    logger.info(f"集群管理器选择Agent: {agent_type} -> {selected_instance}")
                else:
                    # 降级到路由器选择
                    best_agent = self.router.select_best_agent(
                        task_type=task.get("type"),
                        candidate_agents=[agent_type]
                    )
                    if best_agent:
                        selected_agents.append(best_agent)
                        logger.info(f"路由器选择Agent: {agent_type} -> {best_agent}")
            
            # 分配子任务
            subtasks = []
            for agent_type in selected_agents:
                subtask = {
                    "id": str(uuid.uuid4()),
                    "coordination_id": task_id,
                    "agent_type": agent_type,
                    "task": task,
                    "priority": task.get("priority", 0)
                }
                subtasks.append(subtask)
                
                # 发布任务分配消息
                await self.message_bus.publish("task_allocation", subtask)
            
            # 等待所有子任务完成
            results = await self._wait_for_subtasks(task_id, len(subtasks))
            
            # 整合结果
            final_result = self._integrate_results(results, task)
            
            # 清理协调任务状态
            del self.coordination_tasks[task_id]
            
            logger.info(f"任务协调完成: {task_id}")
            return {
                "success": True,
                "task_id": task_id,
                "result": final_result,
                "subtasks": results
            }
        except Exception as e:
            # 清理协调任务状态
            if task_id in self.coordination_tasks:
                del self.coordination_tasks[task_id]
            
            logger.error(f"任务协调失败: {task_id} - {e}")
            return {
                "success": False,
                "task_id": task_id,
                "error": str(e)
            }
    
    async def _handle_task_allocation(self, message: Dict[str, Any]):
        """处理任务分配消息
        
        Args:
            message: 消息内容
        """
        agent_type = message.get("agent_type")
        subtask = message.get("task")
        
        if not agent_type or not subtask:
            logger.warning("无效的任务分配消息")
            return
        
        logger.info(f"分配任务给 {agent_type}: {message.get('id')}")
        
        start_time = time.time()
        
        # 提交任务到对应的Agent
        try:
            result = await agent_scheduler.submit_task(
                task_type=subtask.get("type"),
                params=subtask.get("params", {})
            )
            
            execution_time = time.time() - start_time
            
            # 记录执行结果（用于路由评分）
            success = result.get("status") == "success"
            self.router.record_execution(agent_type, execution_time, success)
            
            # 记录到集群管理器（熔断、监控）
            self.cluster_manager.record_task_result(agent_type, execution_time, success)
            
            # 发布任务提交结果
            await self.message_bus.publish("task_submitted", {
                "subtask_id": message.get("id"),
                "coordination_id": message.get("coordination_id"),
                "task_id": result.get("task_id"),
                "agent_type": result.get("agent_type"),
                "status": result.get("status")
            })
        except Exception as e:
            execution_time = time.time() - start_time
            self.router.record_execution(agent_type, execution_time, False)
            
            # 记录失败到集群管理器
            self.cluster_manager.record_task_result(agent_type, execution_time, False)
            
            logger.error(f"任务分配失败: {e}")
            await self.message_bus.publish("task_submission_failed", {
                "subtask_id": message.get("id"),
                "coordination_id": message.get("coordination_id"),
                "error": str(e)
            })
    
    async def _handle_task_completion(self, message: Dict[str, Any]):
        """处理任务完成消息
        
        Args:
            message: 消息内容
        """
        coordination_id = message.get("coordination_id")
        subtask_id = message.get("subtask_id")
        result = message.get("result")
        status = message.get("status", "completed")
        
        logger.info(f"子任务完成: {subtask_id} (coordination_id={coordination_id}, status={status})")
        
        # 更新协调任务状态
        if coordination_id in self.coordination_tasks:
            coord_task = self.coordination_tasks[coordination_id]
            
            # 记录子任务结果
            coord_task.subtask_results[subtask_id] = {
                "status": status,
                "result": result,
                "completed_at": message.get("completed_at", time.time())
            }
            
            # 更新完成计数
            if status == "completed":
                coord_task.completed_count += 1
            
            # 检查是否所有子任务都已完成
            if coord_task.completed_count >= coord_task.expected_count:
                coord_task.completed_event.set()
                logger.info(f"协调任务 {coordination_id} 所有子任务完成")
    
    async def _handle_agent_status(self, message: Dict[str, Any]):
        """处理Agent状态更新消息
        
        Args:
            message: 消息内容
        """
        agent_type = message.get("agent_type")
        status = message.get("status")
        health_score = message.get("health_score", 1.0)
        
        if agent_type:
            self.agents[agent_type] = status
            # 更新健康度
            self.router.update_health(agent_type, health_score)
            logger.info(f"Agent状态更新: {agent_type} - {status} (health={health_score:.2f})")
    
    def _analyze_task_requirements(self, task: Dict[str, Any]) -> List[str]:
        """分析任务需求，确定需要哪些Agent
        
        Args:
            task: 任务信息
            
        Returns:
            需要的Agent类型列表
        """
        task_type = task.get("type", "")
        required_agents = []
        
        # 根据任务类型分析需要的Agent
        if "deep_thinking" in task_type:
            required_agents.extend(["scraper", "checker"])
        elif "search" in task_type:
            required_agents.append("scraper")
        elif "website" in task_type:
            required_agents.extend(["scraper", "checker"])
        elif "vulnerability" in task_type:
            required_agents.extend(["vulnerability", "checker"])
        elif "summarize" in task_type:
            required_agents.append("summarizer")
        elif "system" in task_type:
            required_agents.append("checker")
        
        # 去重
        return list(set(required_agents))
    
    async def _wait_for_subtasks(self, coordination_id: str, expected_count: int) -> List[Dict[str, Any]]:
        """等待所有子任务完成（优化版）
        
        Args:
            coordination_id: 协调ID
            expected_count: 预期的子任务数量
            
        Returns:
            子任务结果列表
        """
        # 检查协调任务是否存在
        if coordination_id not in self.coordination_tasks:
            logger.error(f"协调任务不存在: {coordination_id}")
            return []
        
        coord_task = self.coordination_tasks[coordination_id]
        coord_task.expected_count = expected_count
        
        timeout = 120  # 120秒超时
        
        try:
            # 等待完成事件
            await asyncio.wait_for(coord_task.completed_event.wait(), timeout=timeout)
            
            # 返回所有子任务结果
            return list(coord_task.subtask_results.values())
            
        except asyncio.TimeoutError:
            logger.error(f"协调任务超时: {coordination_id}")
            # 返回已完成的结果
            return list(coord_task.subtask_results.values())
    
    def _integrate_results(self, results: List[Dict[str, Any]], task: Dict[str, Any]) -> Dict[str, Any]:
        """整合子任务结果（优化版）
        
        Args:
            results: 子任务结果列表
            task: 原始任务
            
        Returns:
            整合后的结果
        """
        # 检查是否有失败的子任务
        failed_tasks = [r for r in results if r.get("status") != "completed"]
        success_count = len(results) - len(failed_tasks)
        
        # 确定整体状态
        overall_status = "success" if len(failed_tasks) == 0 else "partial" if success_count > 0 else "failed"
        
        integrated_result = {
            "status": overall_status,
            "message": self._generate_integration_message(overall_status, success_count, len(results)),
            "subtask_count": len(results),
            "success_count": success_count,
            "failed_count": len(failed_tasks),
            "original_task": task.get("type"),
            "completed_at": time.time()
        }
        
        # 根据任务类型智能整合结果
        task_type = task.get("type", "")
        
        if "search" in task_type or "research" in task_type:
            # 搜索/研究任务：合并搜索结果
            integrated_result["integrated_content"] = self._merge_search_results(results)
        elif "analyze" in task_type:
            # 分析任务：提取关键洞察
            integrated_result["key_insights"] = self._extract_insights(results)
        elif "summarize" in task_type:
            # 总结任务：生成综合摘要
            integrated_result["summary"] = self._generate_summary(results)
        elif "report" in task_type:
            # 报告任务：生成结构化报告
            integrated_result["report"] = self._generate_report(results)
        else:
            # 通用：提取子任务结果
            subtask_results = []
            for result in results:
                subtask_results.append(result.get("result", {}))
            integrated_result["subtask_results"] = subtask_results
        
        # 如果有失败任务，记录错误信息
        if failed_tasks:
            integrated_result["errors"] = [
                {"subtask_index": i, "error": r.get("result", {}).get("error", "Unknown error")}
                for i, r in enumerate(failed_tasks)
            ]
        
        return integrated_result
    
    def _generate_integration_message(self, status: str, success_count: int, total_count: int) -> str:
        """生成整合结果消息"""
        if status == "success":
            return f"所有 {total_count} 个子任务执行成功"
        elif status == "partial":
            return f"部分子任务完成: {success_count}/{total_count}"
        else:
            return f"所有 {total_count} 个子任务执行失败"
    
    def _merge_search_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并搜索结果"""
        merged = {
            "sources": [],
            "total_results": 0,
            "content": ""
        }
        
        for result in results:
            result_data = result.get("result", {})
            if result_data.get("status") == "success":
                merged["sources"].append(result_data.get("source", "Unknown"))
                merged["total_results"] += result_data.get("count", 0)
                merged["content"] += result_data.get("content", "") + "\n"
        
        return merged
    
    def _extract_insights(self, results: List[Dict[str, Any]]) -> List[str]:
        """提取关键洞察"""
        insights = []
        for result in results:
            result_data = result.get("result", {})
            if result_data.get("status") == "success":
                insights.extend(result_data.get("insights", []))
        
        # 去重并排序
        return sorted(list(set(insights)))
    
    def _generate_summary(self, results: List[Dict[str, Any]]) -> str:
        """生成综合摘要"""
        summaries = []
        for result in results:
            result_data = result.get("result", {})
            if result_data.get("status") == "success":
                summary = result_data.get("summary", result_data.get("content", ""))
                if summary:
                    summaries.append(summary)
        
        return "\n\n".join(summaries)
    
    def _generate_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成结构化报告"""
        report = {
            "sections": [],
            "summary": ""
        }
        
        for i, result in enumerate(results):
            result_data = result.get("result", {})
            if result_data.get("status") == "success":
                report["sections"].append({
                    "section": i + 1,
                    "title": result_data.get("title", f"Section {i + 1}"),
                    "content": result_data.get("content", "")
                })
        
        # 生成报告摘要
        section_titles = [s["title"] for s in report["sections"]]
        report["summary"] = f"报告包含 {len(report['sections'])} 个章节: {', '.join(section_titles)}"
        
        return report
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """获取所有Agent状态（包含路由评分和集群状态）
        
        Returns:
            Agent状态和评分
        """
        base_info = agent_scheduler.get_agent_info()
        
        # 添加路由评分
        routing_scores = self.router.get_all_scores()
        base_info["routing_scores"] = routing_scores
        
        # 添加集群状态
        base_info["cluster_status"] = self.cluster_manager.get_cluster_status()
        
        return base_info
    
    async def get_coordination_status(self, coordination_id: str) -> Dict[str, Any]:
        """获取协调任务状态
        
        Args:
            coordination_id: 协调ID
            
        Returns:
            协调任务状态
        """
        if coordination_id not in self.coordination_tasks:
            return {
                "coordination_id": coordination_id,
                "status": "not_found",
                "error": "协调任务不存在"
            }
        
        coord_task = self.coordination_tasks[coordination_id]
        
        return {
            "coordination_id": coordination_id,
            "status": "completed" if coord_task.completed_event.is_set() else "running",
            "task_type": coord_task.task.get("type"),
            "expected_count": coord_task.expected_count,
            "completed_count": coord_task.completed_count,
            "failed_count": coord_task.failed_count,
            "subtask_count": len(coord_task.subtask_results),
            "created_at": coord_task.created_at,
            "subtasks": list(coord_task.subtask_results.keys())
        }


# 全局Agent协调器实例
agent_coordinator = None

def get_agent_coordinator() -> AgentCoordinator:
    """获取Agent协调器实例
    
    Returns:
        AgentCoordinator实例
    """
    global agent_coordinator
    if agent_coordinator is None:
        agent_coordinator = AgentCoordinator()
    return agent_coordinator