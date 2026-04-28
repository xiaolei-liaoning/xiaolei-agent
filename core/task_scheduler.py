"""任务调度器模块

实现任务优先级调度、限流和熔断功能
支持动态权重调整和系统负载监控
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
import uuid
from dataclasses import dataclass, field
from collections import deque

from .monitoring import monitoring_manager

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """任务"""
    id: str
    type: str
    params: Dict[str, Any]
    priority: int = 0  # 0-10，值越大优先级越高
    created_at: float = field(default_factory=time.time)
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务ID列表
    dependents: List[str] = field(default_factory=list)  # 依赖此任务的任务ID列表


@dataclass
class TaskDependency:
    """任务依赖关系"""
    task_id: str
    depends_on: List[str]
    completed: bool = False
    results: Dict[str, Any] = field(default_factory=dict)  # 依赖任务的结果


class RateLimiter:
    """速率限制器"""
    
    def __init__(self, max_calls: int, time_window: int):
        """
        Args:
            max_calls: 时间窗口内最大调用次数
            time_window: 时间窗口（秒）
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def allow(self) -> bool:
        """检查是否允许调用
        
        Returns:
            是否允许调用
        """
        current_time = time.time()
        # 清理过期的调用记录
        self.calls = [call for call in self.calls if current_time - call < self.time_window]
        # 检查是否超过限制
        if len(self.calls) < self.max_calls:
            self.calls.append(current_time)
            return True
        return False


class CircuitBreaker:
    """熔断器"""
    
    def __init__(self, failure_threshold: int, recovery_timeout: int):
        """
        Args:
            failure_threshold: 失败阈值
            recovery_timeout: 恢复超时时间（秒）
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
    
    def record_success(self):
        """记录成功"""
        if self.state == "half-open":
            self.state = "closed"
            self.failures = 0
            logger.info("熔断器状态: closed")
    
    def record_failure(self):
        """记录失败"""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.state == "closed" and self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning("熔断器状态: open")
    
    def is_allowed(self) -> bool:
        """检查是否允许请求
        
        Returns:
            是否允许请求
        """
        if self.state == "closed":
            return True
        elif self.state == "open":
            # 检查是否可以尝试恢复
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
                logger.info("熔断器状态: half-open")
                return True
            return False
        elif self.state == "half-open":
            return True
        return False


class TaskScheduler:
    """任务调度器"""
    
    def __init__(self, enable_dynamic_weights: bool = True):
        self.priority_queues = {}
        self.rate_limiters = {}
        self.circuit_breakers = {}
        self.tasks = {}
        self._running = False
        self._worker_task = None
        # 服务性能统计
        self.service_stats = {}
        
        # 动态权重配置
        self.enable_dynamic_weights = enable_dynamic_weights
        self.route_weights = {
            "priority": 0.4,       # 优先级权重
            "service_health": 0.3, # 服务健康度权重
            "execution_time": 0.2, # 执行时间权重
            "success_rate": 0.1    # 成功率权重
        }
        
        # 系统负载监控
        self.system_load_history = deque(maxlen=100)  # 保留最近100次负载记录
        self.task_execution_history = deque(maxlen=100)  # 保留最近100次任务执行记录
        self.current_load = 0.0  # 当前系统负载 (0.0-1.0)
        self.load_update_interval = 5.0  # 负载更新间隔（秒）
        self._last_load_update = 0.0
        
        # 动态权重调整配置
        self.high_load_threshold = 0.7  # 高负载阈值
        self.low_load_threshold = 0.3   # 低负载阈值
        self.weight_adjustment_factor = 0.1  # 权重调整因子
        
        # 任务依赖关系管理
        self.task_dependencies = {}  # task_id -> TaskDependency
        self.dependency_graph = {}  # task_id -> List[task_id] (依赖关系图)
        self.reverse_dependency_graph = {}  # task_id -> List[task_id] (反向依赖关系图)
        
        logger.info("任务调度器初始化完成（动态权重调整: %s）", enable_dynamic_weights)
    
    async def start(self):
        """启动任务调度器"""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._process_tasks())
            logger.info("任务调度器已启动")
    
    async def stop(self):
        """停止任务调度器"""
        if self._running:
            self._running = False
            if self._worker_task:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
            logger.info("任务调度器已停止")
    
    async def submit_task(self, task_type: str, params: Dict[str, Any], priority: int = 0, 
                         dependencies: Optional[List[str]] = None) -> str:
        """提交任务
        
        Args:
            task_type: 任务类型
            params: 任务参数
            priority: 优先级
            dependencies: 依赖的任务ID列表
            
        Returns:
            任务ID
        """
        # 检查熔断器
        if not self._check_circuit_breaker(task_type):
            raise Exception(f"服务 {task_type} 已熔断，请稍后再试")
        
        # 检查速率限制
        if not self._check_rate_limit(task_type):
            raise Exception(f"服务 {task_type} 调用过于频繁，请稍后再试")
        
        # 创建任务
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            type=task_type,
            params=params,
            priority=priority,
            dependencies=dependencies or []
        )
        
        # 处理依赖关系
        if dependencies:
            self._setup_task_dependencies(task_id, dependencies)
        
        # 更新系统负载
        self._update_system_load()
        
        # 动态调整权重
        if self.enable_dynamic_weights:
            self._adjust_weights_based_on_load()
        
        # 计算任务综合评分
        score = self._calculate_task_score(task_type, priority)
        
        # 检查依赖是否都已完成
        if dependencies and not self._check_dependencies_completed(task_id):
            # 如果依赖未完成，任务状态设为blocked
            task.status = "blocked"
            logger.info(f"任务 {task_id} 等待依赖完成: {dependencies}")
        else:
            # 添加到队列
            if priority not in self.priority_queues:
                self.priority_queues[priority] = asyncio.PriorityQueue()
            
            # 优先级队列使用负优先级，因为asyncio.PriorityQueue是最小堆
            # 添加时间戳作为第三个元素，确保相同优先级的任务能够正确比较
            await self.priority_queues[priority].put((-priority, task.created_at, task))
        
        self.tasks[task_id] = task
        
        logger.info(f"任务已提交: {task_id} (type={task_type}, priority={priority}, score={score:.2f}, dependencies={len(dependencies or [])})")
        return task_id
    
    async def get_task_status(self, task_id: str) -> Optional[Task]:
        """获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务对象
        """
        return self.tasks.get(task_id)
    
    def _calculate_task_score(self, task_type: str, priority: int) -> float:
        """计算任务综合评分
        
        Args:
            task_type: 任务类型
            priority: 优先级
            
        Returns:
            综合评分 (0-10)
        """
        # 1. 优先级分数 (0-10)
        priority_score = min(priority, 10)
        
        # 2. 服务健康度分数 (0-10)
        health_score = self._get_service_health_score(task_type)
        
        # 3. 执行时间分数 (0-10) - 基于历史数据
        time_score = self._get_execution_time_score(task_type)
        
        # 4. 成功率分数 (0-10) - 基于历史数据
        success_score = self._get_success_rate_score(task_type)
        
        # 计算加权总和
        score = (
            priority_score * self.route_weights["priority"] +
            health_score * self.route_weights["service_health"] +
            time_score * self.route_weights["execution_time"] +
            success_score * self.route_weights["success_rate"]
        )
        
        return score
    
    def _get_service_health_score(self, task_type: str) -> float:
        """获取服务健康度分数"""
        if task_type not in self.circuit_breakers:
            return 10.0
        
        breaker = self.circuit_breakers[task_type]
        if breaker.state == "closed":
            return 10.0
        elif breaker.state == "half-open":
            return 5.0
        else:  # open
            return 1.0
    
    def _get_execution_time_score(self, task_type: str) -> float:
        """获取执行时间分数"""
        stats = self.service_stats.get(task_type, {})
        avg_time = stats.get("avg_execution_time", 1.0)
        # 执行时间越短分数越高，上限10
        score = max(1.0, min(10.0, 10.0 / (1.0 + avg_time)))
        return score
    
    def _get_success_rate_score(self, task_type: str) -> float:
        """获取成功率分数"""
        stats = self.service_stats.get(task_type, {})
        success_rate = stats.get("success_rate", 1.0)
        return success_rate * 10.0
    
    async def _process_tasks(self):
        """处理任务队列"""
        while self._running:
            try:
                # 按优先级处理任务
                task = await self._get_next_task()
                if task:
                    await self._execute_task(task)
                else:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"任务处理异常: {e}")
                await asyncio.sleep(0.1)
    
    async def _get_next_task(self) -> Optional[Task]:
        """获取下一个任务
        
        Returns:
            任务对象
        """
        # 按优先级从高到低检查队列
        sorted_priorities = sorted(self.priority_queues.keys(), reverse=True)
        
        for priority in sorted_priorities:
            queue = self.priority_queues[priority]
            if not queue.empty():
                try:
                    # 非阻塞获取
                    _, _, task = queue.get_nowait()
                    return task
                except asyncio.QueueEmpty:
                    continue
        
        return None
    
    async def _execute_task(self, task: Task):
        """执行任务
        
        Args:
            task: 任务对象
        """
        task.status = "running"
        start_time = time.time()
        logger.info(f"开始执行任务: {task.id} (type={task.type})")
        
        try:
            # 检查任务参数中是否有失败标记
            if task.params.get("should_fail"):
                raise Exception("任务被标记为失败")
            
            # 这里应该调用相应的处理函数
            # 暂时模拟执行
            await asyncio.sleep(1)
            task.result = {"status": "success", "message": "任务执行成功"}
            task.status = "completed"
            
            # 记录成功
            self._record_success(task.type)
            duration = time.time() - start_time
            logger.info(f"任务执行成功: {task.id} - 耗时: {duration:.2f}s")
            
            # 记录任务执行情况到监控系统
            monitoring_manager.record_task(task.type, "completed", duration)
            
            # 更新服务性能统计
            self._update_service_stats(task.type, True, duration)
            
            # 记录执行时间到历史记录
            self.task_execution_history.append(duration)
            
            # 检查并激活依赖此任务的其他任务
            await self._on_task_completed(task.id, task.result)
        except Exception as e:
            task.error = str(e)
            task.status = "failed"
            duration = time.time() - start_time
            
            # 记录失败
            self._record_failure(task.type)
            logger.error(f"任务执行失败: {task.id} - {e} - 耗时: {duration:.2f}s")
            
            # 记录任务执行情况到监控系统
            monitoring_manager.record_task(task.type, "failed", duration)
            # 记录错误到监控系统
            monitoring_manager.record_error("task_execution", str(e))
            
            # 更新服务性能统计
            self._update_service_stats(task.type, False, duration)
    
    def _update_service_stats(self, service: str, success: bool, duration: float):
        """更新服务性能统计"""
        if service not in self.service_stats:
            self.service_stats[service] = {
                "total_executions": 0,
                "success_count": 0,
                "total_duration": 0.0,
                "avg_execution_time": 0.0,
                "success_rate": 0.0
            }
        
        stats = self.service_stats[service]
        stats["total_executions"] += 1
        stats["total_duration"] += duration
        
        if success:
            stats["success_count"] += 1
        
        # 更新统计数据
        stats["avg_execution_time"] = stats["total_duration"] / stats["total_executions"]
        stats["success_rate"] = stats["success_count"] / stats["total_executions"]
        
        # 限制历史数据大小，只保留最近100次执行的数据
        if stats["total_executions"] > 100:
            # 简单的滑动窗口实现
            stats["total_executions"] = 100
            stats["success_count"] = int(stats["success_rate"] * 100)
            stats["total_duration"] = stats["avg_execution_time"] * 100
    
    def _check_circuit_breaker(self, service: str) -> bool:
        """检查服务熔断器状态
        
        Args:
            service: 服务名称
            
        Returns:
            是否允许请求
        """
        if service not in self.circuit_breakers:
            self.circuit_breakers[service] = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        
        return self.circuit_breakers[service].is_allowed()
    
    def _check_rate_limit(self, service: str) -> bool:
        """检查服务速率限制
        
        Args:
            service: 服务名称
            
        Returns:
            是否允许请求
        """
        if service not in self.rate_limiters:
            self.rate_limiters[service] = RateLimiter(max_calls=60, time_window=60)  # 每分钟60次
        
        return self.rate_limiters[service].allow()
    
    def _record_success(self, service: str):
        """记录服务成功
        
        Args:
            service: 服务名称
        """
        if service in self.circuit_breakers:
            self.circuit_breakers[service].record_success()
    
    def _record_failure(self, service: str):
        """记录服务失败
        
        Args:
            service: 服务名称
        """
        if service in self.circuit_breakers:
            self.circuit_breakers[service].record_failure()
    
    def get_queue_status(self) -> Dict[str, int]:
        """获取队列状态
        
        Returns:
            队列状态
        """
        status = {}
        for priority, queue in self.priority_queues.items():
            status[f"priority_{priority}"] = queue.qsize()
        return status
    
    def get_service_status(self) -> Dict[str, Dict[str, Any]]:
        """获取服务状态
        
        Returns:
            服务状态
        """
        status = {}
        for service, breaker in self.circuit_breakers.items():
            status[service] = {
                "state": breaker.state,
                "failures": breaker.failures
            }
        return status
    
    def _update_system_load(self):
        """更新系统负载
        
        计算当前系统负载，基于：
        1. 队列中的任务数量
        2. 最近任务执行时间
        3. 服务健康状态
        """
        current_time = time.time()
        
        # 检查是否需要更新
        if current_time - self._last_load_update < self.load_update_interval:
            return
        
        # 计算队列负载
        queue_load = 0.0
        total_queue_size = sum(queue.qsize() for queue in self.priority_queues.values())
        if total_queue_size > 0:
            queue_load = min(1.0, total_queue_size / 50.0)  # 假设50个任务为满载
        
        # 计算执行时间负载
        execution_load = 0.0
        if self.task_execution_history:
            avg_execution_time = sum(self.task_execution_history) / len(self.task_execution_history)
            execution_load = min(1.0, avg_execution_time / 5.0)  # 假设5秒为慢速阈值
        
        # 计算服务健康负载
        health_load = 0.0
        total_services = len(self.circuit_breakers)
        if total_services > 0:
            open_services = sum(1 for breaker in self.circuit_breakers.values() 
                               if breaker.state == "open")
            health_load = open_services / total_services
        
        # 综合负载（加权平均）
        self.current_load = (
            queue_load * 0.5 + 
            execution_load * 0.3 + 
            health_load * 0.2
        )
        
        # 记录负载历史
        self.system_load_history.append(self.current_load)
        self._last_load_update = current_time
        
        logger.info(f"系统负载更新: {self.current_load:.2f} (队列: {queue_load:.2f}, 执行: {execution_load:.2f}, 健康: {health_load:.2f})")
    
    def _adjust_weights_based_on_load(self):
        """根据系统负载动态调整权重
        
        高负载时：增加执行时间权重，减少优先级权重
        低负载时：增加优先级权重，减少执行时间权重
        """
        if not self.enable_dynamic_weights:
            return
        
        if self.current_load > self.high_load_threshold:
            # 高负载：增加执行时间权重，减少优先级权重
            adjustment = self.weight_adjustment_factor
            self.route_weights["execution_time"] = min(0.4, self.route_weights["execution_time"] + adjustment)
            self.route_weights["priority"] = max(0.2, self.route_weights["priority"] - adjustment)
            logger.info(f"高负载模式 - 调整权重: {self.route_weights}")
            
        elif self.current_load < self.low_load_threshold:
            # 低负载：增加优先级权重，减少执行时间权重
            adjustment = self.weight_adjustment_factor
            self.route_weights["priority"] = min(0.6, self.route_weights["priority"] + adjustment)
            self.route_weights["execution_time"] = max(0.1, self.route_weights["execution_time"] - adjustment)
            logger.info(f"低负载模式 - 调整权重: {self.route_weights}")
        
        # 归一化权重，确保总和为1.0
        total_weight = sum(self.route_weights.values())
        if total_weight != 1.0:
            for key in self.route_weights:
                self.route_weights[key] /= total_weight
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态
        
        Returns:
            系统状态信息
        """
        return {
            "current_load": self.current_load,
            "load_history": list(self.system_load_history),
            "route_weights": self.route_weights.copy(),
            "dynamic_weights_enabled": self.enable_dynamic_weights,
            "total_tasks": len(self.tasks),
            "queue_status": self.get_queue_status(),
            "service_status": self.get_service_status()
        }
    
    def reset_weights(self):
        """重置权重为默认值"""
        self.route_weights = {
            "priority": 0.4,
            "service_health": 0.3,
            "execution_time": 0.2,
            "success_rate": 0.1
        }
        logger.info("权重已重置为默认值")
    
    def _setup_task_dependencies(self, task_id: str, dependencies: List[str]):
        """设置任务依赖关系
        
        Args:
            task_id: 任务ID
            dependencies: 依赖的任务ID列表
        """
        # 创建依赖关系对象
        self.task_dependencies[task_id] = TaskDependency(
            task_id=task_id,
            depends_on=dependencies.copy()
        )
        
        # 更新依赖关系图
        self.dependency_graph[task_id] = dependencies.copy()
        
        # 更新反向依赖关系图
        for dep_id in dependencies:
            if dep_id not in self.reverse_dependency_graph:
                self.reverse_dependency_graph[dep_id] = []
            if task_id not in self.reverse_dependency_graph[dep_id]:
                self.reverse_dependency_graph[dep_id].append(task_id)
        
        logger.info(f"设置任务依赖: {task_id} -> {dependencies}")
    
    def _check_dependencies_completed(self, task_id: str) -> bool:
        """检查任务的所有依赖是否都已完成
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否所有依赖都已完成
        """
        if task_id not in self.task_dependencies:
            return True
        
        dependency = self.task_dependencies[task_id]
        
        for dep_id in dependency.depends_on:
            dep_task = self.tasks.get(dep_id)
            # 只有成功完成的任务才算完成
            if not dep_task or dep_task.status != "completed":
                return False
            
            # 收集依赖任务的结果
            if dep_id not in dependency.results:
                dependency.results[dep_id] = dep_task.result
        
        return True
    
    def _resolve_dependencies(self, task_id: str) -> Dict[str, Any]:
        """解析任务依赖，返回依赖任务的结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            依赖任务的结果字典
        """
        if task_id not in self.task_dependencies:
            return {}
        
        return self.task_dependencies[task_id].results
    
    async def _on_task_completed(self, task_id: str, result: Any):
        """任务完成时的回调，检查并激活依赖此任务的其他任务
        
        Args:
            task_id: 已完成的任务ID
            result: 任务结果
        """
        # 检查是否有任务依赖此任务
        if task_id not in self.reverse_dependency_graph:
            return
        
        dependent_tasks = self.reverse_dependency_graph[task_id].copy()
        
        for dependent_id in dependent_tasks:
            dependent_task = self.tasks.get(dependent_id)
            if not dependent_task or dependent_task.status != "blocked":
                continue
            
            # 检查所有依赖是否都已完成
            if self._check_dependencies_completed(dependent_id):
                # 激活任务
                dependent_task.status = "pending"
                
                # 解析依赖结果到任务参数中
                dependency_results = self._resolve_dependencies(dependent_id)
                self._apply_dependency_results(dependent_task, dependency_results)
                
                # 添加到队列
                if dependent_task.priority not in self.priority_queues:
                    self.priority_queues[dependent_task.priority] = asyncio.PriorityQueue()
                
                await self.priority_queues[dependent_task.priority].put(
                    (-dependent_task.priority, dependent_task.created_at, dependent_task)
                )
                
                logger.info(f"任务 {dependent_id} 已激活，依赖任务 {task_id} 已完成")
    
    def _apply_dependency_results(self, task: Task, dependency_results: Dict[str, Any]):
        """将依赖结果应用到任务参数中
        
        Args:
            task: 任务对象
            dependency_results: 依赖结果字典
        """
        # 将依赖结果存储在任务参数中
        if "_dependency_results" not in task.params:
            task.params["_dependency_results"] = {}
        
        task.params["_dependency_results"].update(dependency_results)
        
        # 替换参数中的占位符
        for key, value in task.params.items():
            if isinstance(value, str) and value.startswith("$"):
                # 尝试从依赖结果中获取值
                dep_key = value[1:]
                for dep_result in dependency_results.values():
                    if isinstance(dep_result, dict) and dep_key in dep_result:
                        task.params[key] = dep_result[dep_key]
                        break
    
    def get_dependency_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务的依赖状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            依赖状态信息
        """
        if task_id not in self.task_dependencies:
            return {"has_dependencies": False}
        
        dependency = self.task_dependencies[task_id]
        
        return {
            "has_dependencies": True,
            "dependencies": dependency.depends_on,
            "completed": self._check_dependencies_completed(task_id),
            "results": dependency.results,
            "pending_dependencies": [
                dep_id for dep_id in dependency.depends_on
                if dep_id not in dependency.results
            ]
        }
    
    def get_dependency_graph(self) -> Dict[str, Any]:
        """获取依赖关系图
        
        Returns:
            依赖关系图
        """
        return {
            "dependency_graph": self.dependency_graph.copy(),
            "reverse_dependency_graph": self.reverse_dependency_graph.copy(),
            "total_dependencies": len(self.task_dependencies)
        }


# 全局任务调度器实例
task_scheduler = TaskScheduler()