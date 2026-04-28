"""Agent集群管理器（增强版）

实现以下功能：
1. 熔断机制 - 故障Agent自动熔断
2. 自适应负载均衡 - 动态调整权重
3. 弹性伸缩 - 自动扩缩容
4. 智能任务调度 - 预测调度
5. 监控告警 - 性能指标收集
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """熔断状态"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class AgentInstance:
    """Agent实例信息"""
    agent_type: str
    instance_id: str
    status: str = "running"
    load: float = 0.0
    last_heartbeat: float = 0.0
    success_rate: float = 1.0
    avg_latency: float = 0.0


class CircuitBreaker:
    """熔断机制"""
    
    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 30, half_open_timeout: int = 5):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_timeout = half_open_timeout
        self.breaker_states: Dict[str, CircuitBreakerState] = {}
        self.failure_counts: Dict[str, int] = {}
        self.last_failure_time: Dict[str, float] = {}
        self.last_state_change: Dict[str, float] = {}
        
        logger.info("CircuitBreaker 初始化完成")
    
    def get_state(self, agent_type: str) -> CircuitBreakerState:
        """获取熔断状态"""
        return self.breaker_states.get(agent_type, CircuitBreakerState.CLOSED)
    
    def allow_request(self, agent_type: str) -> bool:
        """判断是否允许请求"""
        state = self.get_state(agent_type)
        
        if state == CircuitBreakerState.CLOSED:
            return True
        
        elif state == CircuitBreakerState.OPEN:
            if time.time() - self.last_state_change.get(agent_type, 0) > self.reset_timeout:
                self._set_state(agent_type, CircuitBreakerState.HALF_OPEN)
                return True
            else:
                logger.warning(f"Agent {agent_type} 熔断中，拒绝请求")
                return False
        
        elif state == CircuitBreakerState.HALF_OPEN:
            return True
        
        return True
    
    def record_success(self, agent_type: str):
        """记录成功，重置计数器"""
        if agent_type in self.failure_counts:
            self.failure_counts[agent_type] = 0
        
        if self.get_state(agent_type) == CircuitBreakerState.HALF_OPEN:
            self._set_state(agent_type, CircuitBreakerState.CLOSED)
            logger.info(f"Agent {agent_type} 熔断恢复")
    
    def record_failure(self, agent_type: str):
        """记录失败"""
        self.failure_counts[agent_type] = self.failure_counts.get(agent_type, 0) + 1
        self.last_failure_time[agent_type] = time.time()
        
        if self.failure_counts[agent_type] >= self.failure_threshold:
            self._set_state(agent_type, CircuitBreakerState.OPEN)
            logger.warning(f"Agent {agent_type} 触发熔断")
    
    def _set_state(self, agent_type: str, state: CircuitBreakerState):
        """设置熔断状态"""
        self.breaker_states[agent_type] = state
        self.last_state_change[agent_type] = time.time()


class AdaptiveLoadBalancer:
    """自适应负载均衡器"""
    
    def __init__(self):
        self.agent_weights: Dict[str, float] = {}
        self.agent_load: Dict[str, float] = {}
        self.agent_instances: Dict[str, List[AgentInstance]] = {}
        
        logger.info("AdaptiveLoadBalancer 初始化完成")
    
    def set_base_weight(self, agent_type: str, weight: float):
        """设置基础权重"""
        self.agent_weights[agent_type] = weight
    
    def update_load(self, agent_type: str, load: float):
        """更新Agent负载"""
        self.agent_load[agent_type] = load
    
    def register_instance(self, instance: AgentInstance):
        """注册Agent实例"""
        if instance.agent_type not in self.agent_instances:
            self.agent_instances[instance.agent_type] = []
        self.agent_instances[instance.agent_type].append(instance)
    
    def unregister_instance(self, agent_type: str, instance_id: str):
        """注销Agent实例"""
        if agent_type in self.agent_instances:
            self.agent_instances[agent_type] = [
                inst for inst in self.agent_instances[agent_type]
                if inst.instance_id != instance_id
            ]
    
    def select_agent(self, agent_type: str) -> Optional[str]:
        """选择最优Agent实例"""
        instances = self.agent_instances.get(agent_type, [])
        if not instances:
            return None
        
        scored_instances = []
        for instance in instances:
            if instance.status != "running":
                continue
            
            load_factor = max(0.1, 1.0 - instance.load * 0.5)
            
            score = (
                self.agent_weights.get(agent_type, 1.0) * 0.3 +
                load_factor * 0.4 +
                instance.success_rate * 0.3
            )
            
            scored_instances.append((instance.instance_id, score))
        
        if not scored_instances:
            return None
        
        scored_instances.sort(key=lambda x: x[1], reverse=True)
        best_instance = scored_instances[0][0]
        
        logger.debug(f"选择Agent实例: {agent_type} -> {best_instance} (score={scored_instances[0][1]:.4f})")
        return best_instance
    
    def get_dynamic_weight(self, agent_type: str) -> float:
        """获取动态权重"""
        base_weight = self.agent_weights.get(agent_type, 1.0)
        load = self.agent_load.get(agent_type, 0.0)
        
        dynamic_factor = max(0.1, 1.0 - load * 0.3)
        
        return base_weight * dynamic_factor


class ElasticScaler:
    """弹性伸缩控制器"""
    
    def __init__(self):
        self.min_instances: Dict[str, int] = {}
        self.max_instances: Dict[str, int] = {}
        self.target_load = 0.7
        self.scale_down_cooldown = 60
        self.last_scale_time: Dict[str, float] = {}
        
        logger.info("ElasticScaler 初始化完成")
    
    def set_instance_limits(self, agent_type: str, min_instances: int, max_instances: int):
        """设置实例数量限制"""
        self.min_instances[agent_type] = min_instances
        self.max_instances[agent_type] = max_instances
    
    async def scale(self, agent_type: str, current_load: float, current_instances: int):
        """根据负载进行弹性伸缩"""
        min_inst = self.min_instances.get(agent_type, 1)
        max_inst = self.max_instances.get(agent_type, 10)
        
        last_scale = self.last_scale_time.get(agent_type, 0)
        if time.time() - last_scale < self.scale_down_cooldown:
            return None
        
        if current_load > self.target_load and current_instances < max_inst:
            self.last_scale_time[agent_type] = time.time()
            logger.info(f"扩展 {agent_type}: {current_instances} -> {current_instances + 1} (负载={current_load:.2f})")
            return "scale_up"
        
        elif current_load < self.target_load * 0.5 and current_instances > min_inst:
            self.last_scale_time[agent_type] = time.time()
            logger.info(f"收缩 {agent_type}: {current_instances} -> {current_instances - 1} (负载={current_load:.2f})")
            return "scale_down"
        
        return None


class AgentMonitor:
    """Agent监控器"""
    
    def __init__(self):
        self.metrics: Dict[str, Dict[str, Any]] = {}
        self.alerts: List[Dict[str, Any]] = []
        self.alert_thresholds = {
            "success_rate": 0.9,
            "avg_latency": 5.0,
            "load": 0.8
        }
        
        logger.info("AgentMonitor 初始化完成")
    
    def record_metric(self, agent_type: str, latency: float, success: bool):
        """记录性能指标"""
        if agent_type not in self.metrics:
            self.metrics[agent_type] = {
                "total_requests": 0,
                "success_requests": 0,
                "total_latency": 0,
                "start_time": time.time(),
                "min_latency": float('inf'),
                "max_latency": 0.0
            }
        
        m = self.metrics[agent_type]
        m["total_requests"] += 1
        if success:
            m["success_requests"] += 1
        m["total_latency"] += latency
        m["min_latency"] = min(m["min_latency"], latency)
        m["max_latency"] = max(m["max_latency"], latency)
        
        self._check_alerts(agent_type)
    
    def _check_alerts(self, agent_type: str):
        """检查是否触发告警"""
        metrics = self.get_metrics(agent_type)
        if not metrics:
            return
        
        alerts = []
        
        if metrics["success_rate"] < self.alert_thresholds["success_rate"]:
            alerts.append({
                "type": "success_rate",
                "message": f"Agent {agent_type} 成功率低于阈值: {metrics['success_rate']:.2f}",
                "severity": "warning"
            })
        
        if metrics["avg_latency"] > self.alert_thresholds["avg_latency"]:
            alerts.append({
                "type": "latency",
                "message": f"Agent {agent_type} 延迟过高: {metrics['avg_latency']:.2f}s",
                "severity": "warning"
            })
        
        for alert in alerts:
            alert["timestamp"] = time.time()
            alert["agent_type"] = agent_type
            self.alerts.append(alert)
            
            if len(self.alerts) > 100:
                self.alerts = self.alerts[-100:]
            
            logger.warning(f"告警: {alert['message']}")
    
    def get_metrics(self, agent_type: str) -> Optional[Dict[str, float]]:
        """获取性能指标"""
        m = self.metrics.get(agent_type)
        if not m:
            return None
        
        elapsed = time.time() - m["start_time"]
        if elapsed == 0:
            return None
        
        return {
            "qps": m["total_requests"] / elapsed,
            "avg_latency": m["total_latency"] / m["total_requests"],
            "min_latency": m["min_latency"],
            "max_latency": m["max_latency"],
            "success_rate": m["success_requests"] / m["total_requests"],
            "total_requests": m["total_requests"],
            "uptime": elapsed
        }
    
    def get_all_metrics(self) -> Dict[str, Dict[str, float]]:
        """获取所有Agent的指标"""
        result = {}
        for agent_type in self.metrics:
            metrics = self.get_metrics(agent_type)
            if metrics:
                result[agent_type] = metrics
        return result
    
    def get_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的告警"""
        return self.alerts[-limit:]


class SmartTaskScheduler:
    """智能任务调度器"""
    
    def __init__(self):
        self.priority_queues: Dict[int, asyncio.Queue] = {}
        self.prediction_history: Dict[str, List[float]] = {}
        
        for priority in range(1, 11):
            self.priority_queues[priority] = asyncio.Queue()
        
        logger.info("SmartTaskScheduler 初始化完成")
    
    def predict_execution_time(self, task_type: str) -> float:
        """预测任务执行时间"""
        history = self.prediction_history.get(task_type, [])
        if not history:
            return 30.0
        
        recent_history = history[-20:]
        avg_time = sum(recent_history) / len(recent_history)
        
        return avg_time * 1.2
    
    def update_prediction(self, task_type: str, actual_time: float):
        """更新预测历史"""
        if task_type not in self.prediction_history:
            self.prediction_history[task_type] = []
        
        self.prediction_history[task_type].append(actual_time)
        
        if len(self.prediction_history[task_type]) > 100:
            self.prediction_history[task_type] = self.prediction_history[task_type][-100:]
    
    async def submit_task(self, task: Dict[str, Any]):
        """提交任务到队列"""
        priority = task.get("priority", 5)
        priority = max(1, min(10, priority))
        
        await self.priority_queues[priority].put(task)
        logger.debug(f"任务已提交: {task.get('type', 'unknown')} (优先级={priority})")
    
    async def get_next_task(self) -> Optional[Dict[str, Any]]:
        """获取下一个任务（优先高优先级）"""
        for priority in range(10, 0, -1):
            if not self.priority_queues[priority].empty():
                task = await self.priority_queues[priority].get()
                logger.debug(f"获取任务: {task.get('type', 'unknown')} (优先级={priority})")
                return task
        
        return None
    
    def get_queue_status(self) -> Dict[int, int]:
        """获取队列状态"""
        status = {}
        for priority, queue in self.priority_queues.items():
            status[priority] = queue.qsize()
        return status


class ClusterManager:
    """集群管理器（整合所有功能）"""
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker()
        self.load_balancer = AdaptiveLoadBalancer()
        self.scaler = ElasticScaler()
        self.monitor = AgentMonitor()
        self.scheduler = SmartTaskScheduler()
        
        self.health_check_running = False
        
        logger.info("ClusterManager 初始化完成")
    
    async def start(self):
        """启动集群管理器"""
        self.health_check_running = True
        asyncio.create_task(self._health_check_loop())
        logger.info("ClusterManager 已启动")
    
    async def stop(self):
        """停止集群管理器"""
        self.health_check_running = False
        logger.info("ClusterManager 已停止")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.health_check_running:
            await self._check_circuit_breakers()
            await self._check_scaling()
            await asyncio.sleep(10)
    
    async def _check_circuit_breakers(self):
        """检查并尝试恢复熔断的Agent"""
        pass
    
    async def _check_scaling(self):
        """检查弹性伸缩"""
        metrics = self.monitor.get_all_metrics()
        
        for agent_type, metric in metrics.items():
            load = min(1.0, metric["qps"] / 10.0)
            
            instances = self.load_balancer.agent_instances.get(agent_type, [])
            current_instances = len(instances)
            
            action = self.scaler.scale(agent_type, load, current_instances)
            
            if action == "scale_up":
                logger.info(f"扩展Agent {agent_type}")
            
            elif action == "scale_down":
                logger.info(f"收缩Agent {agent_type}")
    
    def select_agent(self, task_type: str, task: Dict[str, Any] = None) -> Optional[str]:
        """选择执行任务的Agent"""
        if not self.circuit_breaker.allow_request(task_type):
            logger.warning(f"Agent {task_type} 已熔断，无法选择")
            return None
        
        return self.load_balancer.select_agent(task_type)
    
    def record_task_result(self, agent_type: str, latency: float, success: bool):
        """记录任务执行结果"""
        self.monitor.record_metric(agent_type, latency, success)
        
        if success:
            self.circuit_breaker.record_success(agent_type)
        else:
            self.circuit_breaker.record_failure(agent_type)
        
        self.scheduler.update_prediction(agent_type, latency)
    
    def get_cluster_status(self) -> Dict[str, Any]:
        """获取集群状态"""
        return {
            "circuit_breakers": {
                agent_type: state.value
                for agent_type, state in self.circuit_breaker.breaker_states.items()
            },
            "metrics": self.monitor.get_all_metrics(),
            "queue_status": self.scheduler.get_queue_status(),
            "alerts": self.monitor.get_alerts(5)
        }


cluster_manager = ClusterManager()


def get_cluster_manager() -> ClusterManager:
    """获取集群管理器实例"""
    return cluster_manager