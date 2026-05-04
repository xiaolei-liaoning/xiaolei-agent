"""任务工作流引擎（增强复杂任务处理能力）

核心功能：
- 支持多步骤任务编排
- 任务依赖管理（串行、并行）
- 任务状态跟踪和重试机制
- 多Agent协作执行
- 结果汇总和反馈

架构：
1. WorkflowManager - 工作流管理器（主入口）
2. TaskNode - 任务节点（支持串行/并行）
3. WorkflowExecutor - 执行引擎
4. ResultAggregator - 结果汇总器
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum

from .message_bus import message_bus
from .multi_agent_system import agent_scheduler

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskType(Enum):
    """任务类型"""
    SEQUENTIAL = "sequential"  # 串行执行
    PARALLEL = "parallel"      # 并行执行


@dataclass
class WorkflowTask:
    """工作流任务节点"""
    id: str
    name: str
    action: str              # Agent/技能名称
    params: Dict[str, Any]   # 任务参数
    task_type: TaskType = TaskType.SEQUENTIAL
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务ID
    priority: int = 5        # 优先级（1-10）
    max_retries: int = 3     # 最大重试次数
    retry_delay: float = 2.0 # 重试延迟（秒）
    timeout: int = 60        # 超时时间（秒）
    
    # 运行时状态
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    result: Optional[Any] = None
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def is_ready(self, completed_tasks: Set[str]) -> bool:
        """检查任务是否准备好执行"""
        return all(dep in completed_tasks for dep in self.dependencies)


@dataclass
class Workflow:
    """工作流定义"""
    id: str
    name: str
    description: str = ""
    tasks: List[WorkflowTask] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: time.time())
    
    def get_task_by_id(self, task_id: str) -> Optional[WorkflowTask]:
        """根据ID获取任务"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None
    
    def get_ready_tasks(self, completed_tasks: Set[str]) -> List[WorkflowTask]:
        """获取所有准备好执行的任务"""
        return [task for task in self.tasks 
                if task.status == TaskStatus.PENDING and task.is_ready(completed_tasks)]


class ResultAggregator:
    """结果汇总器"""
    
    @staticmethod
    def aggregate(results: Dict[str, Any], workflow: Workflow) -> Dict[str, Any]:
        """汇总所有任务结果"""
        aggregated = {
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            "total_tasks": len(workflow.tasks),
            "completed_tasks": sum(1 for t in workflow.tasks if t.status == TaskStatus.COMPLETED),
            "failed_tasks": sum(1 for t in workflow.tasks if t.status == TaskStatus.FAILED),
            "results": {},
            "summary": ""
        }
        
        # 按执行顺序整理结果
        for task in workflow.tasks:
            aggregated["results"][task.id] = {
                "name": task.name,
                "action": task.action,
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
                "duration": round(task.end_time - task.start_time, 2) if task.start_time and task.end_time else 0
            }
        
        # 生成总结
        aggregated["summary"] = ResultAggregator._generate_summary(aggregated, workflow)
        
        return aggregated
    
    @staticmethod
    def _generate_summary(aggregated: Dict[str, Any], workflow: Workflow) -> str:
        """生成工作流执行总结"""
        completed = aggregated["completed_tasks"]
        total = aggregated["total_tasks"]
        
        if completed == total:
            return f"工作流 '{workflow.name}' 全部 {total} 个任务执行成功"
        elif completed > 0:
            return f"工作流 '{workflow.name}' 部分完成: {completed}/{total} 个任务成功"
        else:
            return f"工作流 '{workflow.name}' 全部 {total} 个任务执行失败"


class WorkflowExecutor:
    """工作流执行引擎"""
    
    def __init__(self):
        self._running_workflows: Dict[str, asyncio.Task] = {}
    
    async def execute(self, workflow: Workflow) -> Dict[str, Any]:
        """执行工作流"""
        logger.info(f"开始执行工作流: {workflow.name} (ID: {workflow.id})")
        
        completed_tasks: Set[str] = set()
        failed_tasks: Set[str] = set()
        results: Dict[str, Any] = {}
        
        try:
            # 启动所有Agent
            await self._start_agents()
            
            # 执行工作流直到所有任务完成或失败
            while len(completed_tasks) + len(failed_tasks) < len(workflow.tasks):
                # 获取所有准备好的任务
                ready_tasks = workflow.get_ready_tasks(completed_tasks)
                
                if not ready_tasks:
                    # 检查是否有未完成的任务但没有准备好的任务（可能存在循环依赖）
                    pending_tasks = [t for t in workflow.tasks if t.status == TaskStatus.PENDING]
                    if pending_tasks:
                        logger.warning(f"没有准备好的任务，但还有 {len(pending_tasks)} 个待执行任务，可能存在循环依赖")
                        # 标记这些任务为失败
                        for task in pending_tasks:
                            task.status = TaskStatus.FAILED
                            task.error = "无法解析依赖关系，可能存在循环依赖"
                            failed_tasks.add(task.id)
                    break
                
                # 分离串行和并行任务
                sequential_tasks = [t for t in ready_tasks if t.task_type == TaskType.SEQUENTIAL]
                parallel_tasks = [t for t in ready_tasks if t.task_type == TaskType.PARALLEL]
                
                # 先执行串行任务（按优先级排序）
                if sequential_tasks:
                    sequential_tasks.sort(key=lambda t: -t.priority)
                    for task in sequential_tasks:
                        result = await self._execute_task(task)
                        results[task.id] = result
                        if task.status == TaskStatus.COMPLETED:
                            completed_tasks.add(task.id)
                        else:
                            failed_tasks.add(task.id)
                
                # 并行执行并行任务
                if parallel_tasks:
                    parallel_results = await self._execute_parallel(parallel_tasks)
                    for task_id, result in parallel_results.items():
                        results[task_id] = result
                        task = workflow.get_task_by_id(task_id)
                        if task and task.status == TaskStatus.COMPLETED:
                            completed_tasks.add(task_id)
                        else:
                            failed_tasks.add(task_id)
                
                # 短暂等待，避免空循环
                await asyncio.sleep(0.1)
            
            # 汇总结果
            final_result = ResultAggregator.aggregate(results, workflow)
            
            # 发布工作流完成消息
            await message_bus.publish("workflow_completed", {
                "workflow_id": workflow.id,
                "status": "success" if len(failed_tasks) == 0 else "partial" if len(completed_tasks) > 0 else "failed",
                "result": final_result
            })
            
            logger.info(f"工作流执行完成: {workflow.name} - {final_result['summary']}")
            return final_result
            
        except Exception as e:
            logger.error(f"工作流执行异常: {e}", exc_info=True)
            return {
                "workflow_id": workflow.id,
                "status": "error",
                "error": str(e),
                "results": results
            }
    
    async def _execute_task(self, task: WorkflowTask) -> Dict[str, Any]:
        """执行单个任务（带重试机制和等待完成）"""
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()
        task.attempts += 1
        
        logger.info(f"执行任务: {task.name} (ID: {task.id}, 第{task.attempts}次尝试)")
        
        try:
            async with asyncio.timeout(task.timeout):
                # 调用Agent执行任务
                submit_result = await agent_scheduler.submit_task(
                    task_type=task.action,
                    params=task.params
                )
                
                # 检查任务是否提交成功
                if submit_result.get("success"):
                    # 获取任务ID并等待完成
                    task_id = submit_result.get("data", {}).get("task_id")
                    if task_id:
                        # 等待任务完成
                        final_result = await self._wait_for_agent_task(task.action, task_id)
                        if final_result:
                            task.status = TaskStatus.COMPLETED
                            task.result = final_result
                            task.end_time = time.time()
                            logger.info(f"任务完成: {task.name} - 耗时 {task.end_time - task.start_time:.2f}s")
                            return final_result
                        else:
                            raise Exception("任务执行失败，未获取到结果")
                    else:
                        # 没有任务ID，直接使用提交结果
                        task.status = TaskStatus.COMPLETED
                        task.result = submit_result
                        task.end_time = time.time()
                        logger.info(f"任务完成（无等待）: {task.name} - 耗时 {task.end_time - task.start_time:.2f}s")
                        return submit_result
                else:
                    raise Exception(submit_result.get("message", "任务提交失败"))
                
        except asyncio.TimeoutError:
            task.error = f"任务超时（{task.timeout}秒）"
            logger.warning(f"任务超时: {task.name}")
        except Exception as e:
            task.error = str(e)
            logger.error(f"任务执行失败: {task.name} - {e}")
        
        # 重试逻辑
        if task.attempts < task.max_retries:
            logger.info(f"任务 {task.name} 将在 {task.retry_delay} 秒后重试（剩余 {task.max_retries - task.attempts} 次）")
            await asyncio.sleep(task.retry_delay)
            return await self._execute_task(task)
        
        # 重试次数用尽
        task.status = TaskStatus.FAILED
        task.end_time = time.time()
        return {"status": "failed", "error": task.error}
    
    async def _wait_for_agent_task(self, task_type: str, task_id: str) -> Optional[Dict[str, Any]]:
        """等待Agent任务完成"""
        # 获取对应的Agent类型（通过task_mapping）
        agent_type = agent_scheduler.task_mapping.get(task_type)
        if not agent_type:
            logger.error(f"无法找到任务类型 {task_type} 对应的Agent")
            return None
        
        agent = agent_scheduler.agents.get(agent_type)
        if not agent:
            logger.error(f"Agent {agent_type.value} 不存在")
            return None
        
        # 等待任务完成（轮询）
        max_wait = 60  # 最大等待60秒
        wait_interval = 0.5  # 轮询间隔
        waited = 0
        
        while waited < max_wait:
            task_info = await agent.get_task_status(task_id)
            if task_info:
                if task_info.status.value == "completed":
                    logger.info(f"任务 {task_id} 完成")
                    return task_info.result
                elif task_info.status.value == "failed":
                    logger.error(f"任务 {task_id} 失败: {task_info.error}")
                    return None
            
            await asyncio.sleep(wait_interval)
            waited += wait_interval
        
        logger.warning(f"任务 {task_id} 等待超时")
        return None
    
    async def _execute_parallel(self, tasks: List[WorkflowTask]) -> Dict[str, Any]:
        """并行执行多个任务"""
        logger.info(f"并行执行 {len(tasks)} 个任务")
        
        async def execute_one(task: WorkflowTask) -> tuple:
            result = await self._execute_task(task)
            return (task.id, result)
        
        # 并行执行所有任务
        tasks_future = [execute_one(task) for task in tasks]
        results = await asyncio.gather(*tasks_future)
        
        return dict(results)
    
    async def _start_agents(self):
        """启动所有必要的Agent"""
        try:
            agents = agent_scheduler.agents.values()
            for agent in agents:
                await agent.start()
        except Exception as e:
            logger.warning(f"启动Agent时出现警告: {e}")


class WorkflowManager:
    """工作流管理器（主入口）"""
    
    def __init__(self):
        self.executor = WorkflowExecutor()
        self.workflows: Dict[str, Workflow] = {}
        logger.info("WorkflowManager 初始化完成")
    
    def create_workflow(self, name: str, description: str = "") -> Workflow:
        """创建新工作流"""
        workflow_id = str(uuid.uuid4())
        workflow = Workflow(
            id=workflow_id,
            name=name,
            description=description
        )
        self.workflows[workflow_id] = workflow
        logger.info(f"创建工作流: {name} (ID: {workflow_id})")
        return workflow
    
    def add_task(self, workflow_id: str, task: WorkflowTask) -> bool:
        """向工作流添加任务"""
        if workflow_id not in self.workflows:
            logger.error(f"工作流不存在: {workflow_id}")
            return False
        
        # 检查依赖任务是否存在
        for dep in task.dependencies:
            if not self.workflows[workflow_id].get_task_by_id(dep):
                logger.error(f"依赖任务不存在: {dep}")
                return False
        
        self.workflows[workflow_id].tasks.append(task)
        logger.info(f"添加任务到工作流 {workflow_id}: {task.name}")
        return True
    
    async def execute_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """执行工作流"""
        if workflow_id not in self.workflows:
            logger.error(f"工作流不存在: {workflow_id}")
            return None
        
        workflow = self.workflows[workflow_id]
        return await self.executor.execute(workflow)
    
    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """获取工作流状态"""
        if workflow_id not in self.workflows:
            return None
        
        workflow = self.workflows[workflow_id]
        tasks_info = []
        
        for task in workflow.tasks:
            tasks_info.append({
                "id": task.id,
                "name": task.name,
                "status": task.status.value,
                "attempts": task.attempts,
                "priority": task.priority,
                "dependencies": task.dependencies
            })
        
        return {
            "workflow_id": workflow.id,
            "name": workflow.name,
            "created_at": workflow.created_at,
            "tasks": tasks_info,
            "completed_count": sum(1 for t in workflow.tasks if t.status == TaskStatus.COMPLETED),
            "failed_count": sum(1 for t in workflow.tasks if t.status == TaskStatus.FAILED),
            "pending_count": sum(1 for t in workflow.tasks if t.status == TaskStatus.PENDING)
        }
    
    def delete_workflow(self, workflow_id: str) -> bool:
        """删除工作流"""
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            logger.info(f"删除工作流: {workflow_id}")
            return True
        return False
    
    async def execute_complex_task(self, task_description: str) -> Dict[str, Any]:
        """执行复杂任务（自动解析和编排）
        
        Args:
            task_description: 用户的复杂任务描述
            
        Returns:
            执行结果
        """
        # 1. 解析任务描述，生成工作流
        workflow = await self._parse_complex_task(task_description)
        
        if not workflow:
            return {
                "status": "error",
                "message": "无法解析复杂任务"
            }
        
        # 2. 执行工作流
        result = await self.execute_workflow(workflow.id)
        
        return result
    
    async def _parse_complex_task(self, task_description: str) -> Optional[Workflow]:
        """解析复杂任务描述，生成工作流
        
        支持的模式：
        - "先A，然后B，最后C" - 串行执行
        - "同时执行A和B" - 并行执行
        - "A并B" - 并行执行
        """
        logger.info(f"解析复杂任务: {task_description}")
        
        # 优先使用LLM解析任务（如果可用）
        llm_result = None
        try:
            from core.llm_backend import get_llm_router
            
            router = get_llm_router()
            if router.is_available():
                llm_result = await self._parse_with_llm(task_description)
        except Exception as e:
            logger.warning(f"LLM解析失败，将使用规则解析: {e}")
        
        # 如果LLM解析成功，返回结果；否则使用规则解析
        if llm_result:
            return llm_result
        
        # 规则解析
        return self._parse_with_rules(task_description)
    
    async def _parse_with_llm(self, task_description: str) -> Optional[Workflow]:
        """使用LLM解析复杂任务"""
        from core.llm_backend import get_llm_router
        
        router = get_llm_router()
        
        prompt = f"""请将以下复杂任务拆解为工作流任务列表。

任务描述：{task_description}

输出格式（JSON）：
{{
  "workflow_name": "工作流名称",
  "tasks": [
    {{
      "id": "task_1",
      "name": "任务名称",
      "action": "agent类型（scrape/search/analyze/summarize等）",
      "params": {{"key": "value"}},
      "task_type": "sequential",
      "dependencies": [],
      "priority": 5
    }}
  ]
}}

任务类型：
- sequential: 串行执行（按顺序）
- parallel: 并行执行（同时）

动作类型参考：
- scrape: 爬虫/数据抓取
- search: 搜索
- analyze: 数据分析
- summarize: 总结
- check: 检查
- translate: 翻译
- nlp: 自然语言处理

请只返回JSON，不要包含其他内容。"""
        
        response = await router.simple_chat(
            user_message=prompt,
            system_prompt="你是任务分解专家，将复杂任务拆解为工作流任务列表。",
            temperature=0.3
        )
        
        try:
            import json
            data = json.loads(response)
            
            workflow = self.create_workflow(
                name=data.get("workflow_name", "复杂任务"),
                description=task_description
            )
            
            for task_data in data.get("tasks", []):
                task = WorkflowTask(
                    id=task_data["id"],
                    name=task_data["name"],
                    action=task_data["action"],
                    params=task_data.get("params", {}),
                    task_type=TaskType(task_data.get("task_type", "sequential")),
                    dependencies=task_data.get("dependencies", []),
                    priority=task_data.get("priority", 5)
                )
                self.add_task(workflow.id, task)
            
            return workflow
            
        except Exception as e:
            logger.error(f"LLM解析失败: {e}")
            return None
    
    def _parse_with_rules(self, task_description: str) -> Optional[Workflow]:
        """使用规则解析复杂任务"""
        workflow = self.create_workflow(
            name="规则解析任务",
            description=task_description
        )
        
        # 分隔词列表（按长度降序排列，确保长词优先匹配）
        separators = ["然后", "接着", "之后", "最后", "同时", "先", "再", "并"]
        
        # 使用正则表达式拆分任务
        import re
        
        # 构建正则模式：匹配任意分隔词
        pattern = '|'.join(re.escape(sep) for sep in separators)
        
        # 拆分任务描述
        parts = re.split(f'({pattern})', task_description)
        
        # 过滤空字符串和分隔词
        task_parts = []
        for part in parts:
            part = part.strip()
            if part and part not in separators:
                task_parts.append(part)
        
        # 构建任务列表
        task_id = 1
        prev_task_id = None
        
        for part in task_parts:
            # 判断任务类型
            action = self._infer_action(part)
            params = self._extract_params(part, action)
            
            task = WorkflowTask(
                id=f"task_{task_id}",
                name=part,
                action=action,
                params=params,
                task_type=TaskType.SEQUENTIAL,
                dependencies=[prev_task_id] if prev_task_id else [],
                priority=5
            )
            
            self.add_task(workflow.id, task)
            prev_task_id = task.id
            task_id += 1
        
        return workflow if workflow.tasks else None
    
    def _infer_action(self, task_part: str) -> str:
        """从任务片段推断动作类型"""
        task_lower = task_part.lower()
        
        if any(kw in task_lower for kw in ["爬取", "抓取", "获取"]):
            return "scrape"
        elif any(kw in task_lower for kw in ["搜索", "查询", "查一下"]):
            return "search"
        elif any(kw in task_lower for kw in ["分析", "统计", "计算"]):
            return "analyze"
        elif any(kw in task_lower for kw in ["总结", "概括", "摘要"]):
            return "summarize"
        elif any(kw in task_lower for kw in ["检查", "验证"]):
            return "check"
        elif any(kw in task_lower for kw in ["翻译"]):
            return "translate"
        else:
            return "search"
    
    def _extract_params(self, task_part: str, action: str) -> Dict[str, Any]:
        """从任务片段提取参数"""
        params = {}
        
        if action == "scrape":
            # 提取网站名称
            sites = ["微博", "百度", "知乎", "抖音", "B站", "github"]
            for site in sites:
                if site in task_part:
                    params["site_name"] = site
                    break
            params["action"] = "热搜" if "热搜" in task_part else "crawl"
        
        elif action == "search":
            params["query"] = task_part.replace("搜索", "").replace("查询", "").replace("查一下", "").strip()
        
        elif action == "analyze":
            params["action"] = "analyze"
        
        elif action == "summarize":
            params["action"] = "summarize"
        
        return params


# 全局工作流管理器实例
_workflow_manager = None

def get_workflow_manager() -> WorkflowManager:
    """获取工作流管理器单例"""
    global _workflow_manager
    if _workflow_manager is None:
        _workflow_manager = WorkflowManager()
    return _workflow_manager


# 便捷函数
async def execute_complex_task(task_description: str) -> Dict[str, Any]:
    """执行复杂任务的便捷函数"""
    manager = get_workflow_manager()
    return await manager.execute_complex_task(task_description)