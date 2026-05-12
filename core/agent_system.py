#!/usr/bin/env python3
"""智能多Agent系统 - 支持自主沟通、任务拆解、多Agent协作、反思重试"""

import asyncio
import json
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from cli.colors import CliColors, print_color
from cli.logging_system import log_info, log_success, log_error, log_warning, log_debug
from cli.ui_components import Table, Card, ProgressBar

class AgentRole(Enum):
    STRATEGIST = "策略师"
    EXECUTOR = "执行者"
    ANALYZER = "分析师"
    RESEARCHER = "研究员"
    REVIEWER = "评审员"

class TaskStatus(Enum):
    PENDING = "待执行"
    IN_PROGRESS = "执行中"
    COMPLETED = "已完成"
    FAILED = "失败"
    REFLECTING = "反思中"

@dataclass
class Task:
    id: str
    name: str
    description: str
    status: TaskStatus
    priority: int
    assignee: Optional[str] = None
    subtasks: List['Task'] = None
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if self.subtasks is None:
            self.subtasks = []

@dataclass
class AgentMessage:
    from_agent: str
    to_agent: str
    content: str
    timestamp: float = None
    message_type: str = "task"

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

class BaseAgent:
    def __init__(self, name: str, role: AgentRole):
        self.name = name
        self.role = role
        self.status = "idle"
        self.task_history: List[Dict] = []
        self.message_queue: List[AgentMessage] = []
    
    async def process_message(self, message: AgentMessage) -> str:
        """处理收到的消息"""
        self.message_queue.append(message)
        log_info(f"📬 {self.name} 收到消息 from {message.from_agent}")
        return await self._handle_message(message)
    
    async def _handle_message(self, message: AgentMessage) -> str:
        """子类实现具体处理逻辑"""
        return "已收到消息"

class StrategistAgent(BaseAgent):
    """策略师Agent - 负责任务拆解和规划"""
    
    def __init__(self):
        super().__init__("策略师", AgentRole.STRATEGIST)
    
    async def _handle_message(self, message: AgentMessage) -> str:
        if message.message_type == "task":
            return await self.decompose_task(message.content)
        return "消息已处理"
    
    async def decompose_task(self, task_description: str) -> str:
        """智能任务拆解"""
        log_info(f"🧠 策略师正在分析任务: {task_description}")
        
        # 模拟智能任务拆解逻辑
        task_patterns = {
            "爬取.*微博": ["分析需求", "打开浏览器", "访问微博", "提取热搜数据", "保存数据"],
            "打开.*微信": ["分析需求", "查找微信应用", "启动微信"],
            "生成.*报告": ["分析需求", "收集数据", "分析数据", "生成报告", "审查报告"],
            "分析.*数据": ["加载数据", "数据清洗", "数据分析", "生成结论"],
            "搜索.*信息": ["分析搜索需求", "执行搜索", "整理结果", "生成报告"],
        }
        
        subtasks = ["分析需求", "制定计划", "执行任务", "验证结果"]
        
        for pattern, tasks in task_patterns.items():
            if any(keyword in task_description for keyword in pattern.split(".*")):
                subtasks = tasks
                break
        
        result = {
            "task": task_description,
            "subtasks": subtasks,
            "estimated_steps": len(subtasks),
            "strategy": "分步骤执行"
        }
        
        log_success(f"✅ 任务拆解完成，共 {len(subtasks)} 个子任务")
        return json.dumps(result, ensure_ascii=False)

class ExecutorAgent(BaseAgent):
    """执行者Agent - 负责执行具体任务"""
    
    def __init__(self):
        super().__init__("执行者", AgentRole.EXECUTOR)
    
    async def _handle_message(self, message: AgentMessage) -> str:
        if message.message_type == "task":
            return await self.execute_task(message.content)
        return "消息已处理"
    
    async def execute_task(self, task: str) -> str:
        """执行任务"""
        log_info(f"⚡ 执行者开始执行任务: {task}")
        
        # 模拟执行延迟
        await asyncio.sleep(1)
        
        # 模拟执行结果
        success_rate = 0.8
        if "危险" in task.lower() or "rm" in task.lower():
            success_rate = 0.3
        
        if time.time() % 3 < success_rate:
            result = {
                "status": "success",
                "task": task,
                "result": f"任务 '{task}' 执行成功",
                "details": {"steps": 1, "duration": 1.0}
            }
            log_success(f"✅ 任务执行成功: {task}")
        else:
            result = {
                "status": "failed",
                "task": task,
                "error": f"任务执行失败，需要重试",
                "retry_suggestion": "检查参数或重试"
            }
            log_error(f"❌ 任务执行失败: {task}")
        
        return json.dumps(result, ensure_ascii=False)

class ResearcherAgent(BaseAgent):
    """研究员Agent - 负责信息收集和研究"""
    
    def __init__(self):
        super().__init__("研究员", AgentRole.RESEARCHER)
    
    async def _handle_message(self, message: AgentMessage) -> str:
        if message.message_type == "research":
            return await self.conduct_research(message.content)
        return "消息已处理"
    
    async def conduct_research(self, topic: str) -> str:
        """进行研究"""
        log_info(f"🔍 研究员正在研究: {topic}")
        
        # 模拟研究过程
        await asyncio.sleep(1)
        
        research_results = {
            "topic": topic,
            "sources": ["网络搜索", "文档查阅", "数据库查询"],
            "findings": [
                f"关于 '{topic}' 的关键信息 1",
                f"关于 '{topic}' 的关键信息 2",
                f"关于 '{topic}' 的关键信息 3"
            ],
            "summary": f"已完成对 '{topic}' 的研究，获取了相关信息"
        }
        
        log_success(f"✅ 研究完成: {topic}")
        return json.dumps(research_results, ensure_ascii=False)

class AnalyzerAgent(BaseAgent):
    """分析师Agent - 负责数据分析和报告"""
    
    def __init__(self):
        super().__init__("分析师", AgentRole.ANALYZER)
    
    async def _handle_message(self, message: AgentMessage) -> str:
        if message.message_type == "analyze":
            return await self.analyze_data(message.content)
        return "消息已处理"
    
    async def analyze_data(self, data: str) -> str:
        """分析数据"""
        log_info(f"📊 分析师正在分析数据")
        
        # 模拟分析过程
        await asyncio.sleep(0.5)
        
        analysis = {
            "analysis_type": "综合分析",
            "key_insights": ["发现趋势 A", "识别模式 B", "异常检测 C"],
            "recommendations": ["建议行动 1", "建议行动 2"],
            "confidence": 0.85
        }
        
        log_success(f"✅ 分析完成")
        return json.dumps(analysis, ensure_ascii=False)

class ReviewerAgent(BaseAgent):
    """评审员Agent - 负责结果审查和质量保证"""
    
    def __init__(self):
        super().__init__("评审员", AgentRole.REVIEWER)
    
    async def _handle_message(self, message: AgentMessage) -> str:
        if message.message_type == "review":
            return await self.review_result(message.content)
        return "消息已处理"
    
    async def review_result(self, result: str) -> str:
        """评审结果"""
        log_info(f"🔎 评审员正在评审结果")
        
        # 模拟评审过程
        await asyncio.sleep(0.5)
        
        # 模拟评审结果
        score = min(95, int(time.time() % 30) + 70)
        passed = score >= 80
        
        review = {
            "review_score": score,
            "passed": passed,
            "comments": "结果符合预期" if passed else "需要改进",
            "suggestions": [] if passed else ["建议重新执行", "建议增加检查步骤"]
        }
        
        if passed:
            log_success(f"✅ 评审通过，得分: {score}")
        else:
            log_warning(f"⚠️ 评审未通过，得分: {score}")
        
        return json.dumps(review, ensure_ascii=False)

class Reflector:
    """反思器 - 负责反思和重试逻辑"""
    
    def __init__(self):
        self.history: List[Dict] = []
    
    async def reflect(self, task: Task) -> Dict:
        """反思任务执行过程"""
        log_info(f"🤔 反思器开始反思任务: {task.name}")
        
        if task.error:
            analysis = await self._analyze_failure(task)
            suggestion = await self._generate_suggestion(task, analysis)
            should_retry = task.retry_count < task.max_retries
            
            reflection = {
                "task_id": task.id,
                "task_name": task.name,
                "status": "reflection_complete",
                "analysis": analysis,
                "suggestion": suggestion,
                "should_retry": should_retry,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries
            }
            
            self.history.append(reflection)
            return reflection
        
        return {"status": "no_reflection_needed"}
    
    async def _analyze_failure(self, task: Task) -> str:
        """分析失败原因"""
        failure_patterns = {
            "网络": "可能是网络连接问题",
            "权限": "可能是权限不足",
            "超时": "可能是超时问题",
            "格式": "可能是数据格式问题",
        }
        
        for pattern, reason in failure_patterns.items():
            if pattern in task.error:
                return reason
        
        return "未知原因导致失败"
    
    async def _generate_suggestion(self, task: Task, analysis: str) -> str:
        """生成改进建议"""
        suggestions = {
            "网络": "建议检查网络连接，或稍后重试",
            "权限": "建议检查权限设置，或使用管理员权限",
            "超时": "建议增加超时时间，或优化执行逻辑",
            "格式": "建议检查输入数据格式",
        }
        
        for pattern, suggestion in suggestions.items():
            if pattern in analysis:
                return suggestion
        
        return "建议检查相关依赖，或尝试其他方法"

class CollaborationEngine:
    """协作引擎 - 管理多Agent协作"""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.reflector = Reflector()
        self.task_queue: List[Task] = []
        self.completed_tasks: List[Task] = []
        self.failed_tasks: List[Task] = []
    
    def register_agent(self, agent: BaseAgent):
        """注册Agent"""
        self.agents[agent.name] = agent
        log_info(f"👤 注册Agent: {agent.name} ({agent.role.value})")
    
    def get_agent_by_role(self, role: AgentRole) -> Optional[BaseAgent]:
        """按角色获取Agent"""
        for agent in self.agents.values():
            if agent.role == role:
                return agent
        return None
    
    async def send_message(self, from_agent: str, to_agent: str, content: str, message_type: str = "task"):
        """发送消息"""
        if to_agent not in self.agents:
            log_error(f"❌ 目标Agent不存在: {to_agent}")
            return None
        
        message = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            message_type=message_type
        )
        
        return await self.agents[to_agent].process_message(message)
    
    async def execute_task(self, task_description: str) -> Dict:
        """执行任务 - 完整流程"""
        log_info(f"🚀 开始执行任务: {task_description}")
        
        # 1. 策略师拆解任务
        strategist = self.get_agent_by_role(AgentRole.STRATEGIST)
        if not strategist:
            return {"error": "策略师Agent未注册"}
        
        decomposition_result = await self.send_message(
            "系统", strategist.name, task_description, "task"
        )
        
        try:
            decomposition = json.loads(decomposition_result)
            subtasks = decomposition.get("subtasks", [])
        except:
            subtasks = ["执行任务"]
        
        # 2. 创建任务对象
        main_task = Task(
            id=f"task_{int(time.time())}",
            name=task_description,
            description=task_description,
            status=TaskStatus.IN_PROGRESS,
            priority=1,
            subtasks=[Task(id=f"sub_{i}", name=sub, description=sub, status=TaskStatus.PENDING, priority=i+1) 
                     for i, sub in enumerate(subtasks)]
        )
        
        self.task_queue.append(main_task)
        
        # 3. 执行子任务
        results = []
        progress_bar = ProgressBar(total=len(subtasks), width=50)
        
        for i, subtask in enumerate(main_task.subtasks):
            subtask.status = TaskStatus.IN_PROGRESS
            
            # 执行子任务
            executor = self.get_agent_by_role(AgentRole.EXECUTOR)
            if executor:
                result = await self.send_message(
                    strategist.name, executor.name, subtask.name, "task"
                )
                
                try:
                    result_data = json.loads(result)
                    if result_data.get("status") == "success":
                        subtask.status = TaskStatus.COMPLETED
                        subtask.result = result_data
                        results.append(result_data)
                        log_success(f"✅ 子任务完成: {subtask.name}")
                    else:
                        # 反思重试逻辑
                        subtask.status = TaskStatus.FAILED
                        subtask.error = result_data.get("error", "未知错误")
                        subtask.retry_count += 1
                        
                        # 调用反思器
                        reflection = await self.reflector.reflect(subtask)
                        
                        if reflection.get("should_retry", False):
                            log_info(f"🔄 正在重试子任务: {subtask.name} (第 {subtask.retry_count} 次)")
                            # 重试执行
                            result = await self.send_message(
                                strategist.name, executor.name, subtask.name, "task"
                            )
                            result_data = json.loads(result)
                            if result_data.get("status") == "success":
                                subtask.status = TaskStatus.COMPLETED
                                subtask.result = result_data
                                results.append(result_data)
                                log_success(f"✅