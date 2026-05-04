"""多角色独立智能体系统

架构：【多角色独立智能体 + 内部并发分身】

特点：
- 每个Agent都是独立个体，有独立的配置和任务队列
- 每个Agent内部支持并发，可以开多个分身同时处理同类任务
- 上层有调度中心，负责分配任务到对应Agent
- 单机多实例异步架构，不跨设备
- 支持并行处理大量不同类型任务
"""

import asyncio
import logging
import os
import importlib
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid

from .message_bus import message_bus
from .task_scheduler import task_scheduler
from .boundary_manager import boundary_manager
from .exception_handler import exception_handler
from .response_manager import response_manager
from .monitoring import monitoring_manager
from .intent_recognizer import IntentRecognizer
from .task_splitter import TaskSplitter
from .bfs_processor import get_bfs_processor, TextNode

logger = logging.getLogger(__name__)

# 全局人物Skill缓存
_global_character_skills = {}

# 初始化全局人物Skill
def _initialize_character_skills():
    """初始化全局人物Skill"""
    global _global_character_skills
    if not _global_character_skills:
        character_skills = {}
        # 正确计算路径，包含'小雷版小龙虾agent'目录
        current_dir = os.path.dirname(__file__)
        parent_dir = os.path.dirname(current_dir)
        skills_dir = os.path.join(parent_dir, "skills", "人物")
        
        logger.info(f"开始加载人物Skill，目录: {skills_dir}")
        logger.info(f"目录是否存在: {os.path.exists(skills_dir)}")
        
        if os.path.exists(skills_dir):
            logger.info(f"人物Skill目录存在: {skills_dir}")
            try:
                # 过滤掉隐藏文件，如.DS_Store
                skill_dirs = [d for d in os.listdir(skills_dir) if not d.startswith(".")]
                logger.info(f"目录内容: {skill_dirs}")
            except Exception as e:
                logger.error(f"读取目录内容失败: {e}")
                return
            
            # 添加当前工作目录到Python路径，以便能够正确导入skills模块
            import sys
            sys.path.insert(0, parent_dir)
            logger.info(f"Python路径: {sys.path[:5]}")
            
            for character in skill_dirs:
                character_path = os.path.join(skills_dir, character)
                if os.path.isdir(character_path):
                    try:
                        # 动态导入人物Skill
                        module_path = f"skills.人物.{character}.handler"
                        logger.info(f"尝试导入人物Skill: {module_path}")
                        module = importlib.import_module(module_path)
                        if hasattr(module, "handler"):
                            character_skills[character] = module.handler
                            logger.info(f"加载人物Skill成功: {character}")
                        else:
                            logger.warning(f"人物Skill {character} 缺少handler属性")
                    except Exception as e:
                        logger.warning(f"加载人物Skill失败: {character} - {e}")
        else:
            logger.warning(f"人物Skill目录不存在: {skills_dir}")
        
        _global_character_skills = character_skills
        logger.info(f"人物Skill加载完成，共加载 {len(character_skills)} 个技能: {list(character_skills.keys())}")

# 初始化全局人物Skill
_initialize_character_skills()


class AgentType(Enum):
    """智能体类型"""
    CHECKER = "checker"      # 检查Agent
    SCRAPER = "scraper"      # 爬虫Agent
    VULNERABILITY = "vulnerability"  # 漏洞Agent
    SUMMARIZER = "summarizer"  # 总结Agent
    DATA_ANALYSIS = "data_analysis"  # 数据分析Agent
    NLP = "nlp"  # 自然语言处理Agent
    TEXT_ANALYZER = "text_analyzer"  # 文本拆解提取总结Agent
    PLANNING = "planning"  # 规划Agent（新增）


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentTask:
    """Agent任务"""
    id: str
    type: str
    params: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=lambda: time.time())
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class BaseAgent:
    """智能体基类"""
    
    def __init__(self, agent_type: AgentType, max_workers: int = 5):
        self.agent_type = agent_type
        self.max_workers = max_workers
        self._queue: asyncio.Queue = asyncio.Queue()
        self._tasks: Dict[str, AgentTask] = {}
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._shutdown_flag = False
        self._character_skills = {}
        
        # 延迟启动，不在构造函数中启动worker
        self._running = False
        self._shutdown_flag = False
        
        logger.info(f"{agent_type.value} Agent 初始化完成 (max_workers={max_workers})")
    
    def _start_workers(self):
        """启动worker线程"""
        # 检查是否已经有worker在运行
        if self._workers:
            logger.info(f"{self.agent_type.value} Agent 已有 {len(self._workers)} 个worker在运行")
            return
        
        # 检查是否有运行的事件循环
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行的事件循环，无法启动worker
            logger.warning(f"{self.agent_type.value} Agent 无法启动worker: 没有运行的事件循环")
            return
        
        logger.info(f"{self.agent_type.value} Agent 启动 {self.max_workers} 个worker线程")
        
        for i in range(self.max_workers):
            worker = loop.create_task(
                self._run_worker(f"{self.agent_type.value}_worker_{i}")
            )
            self._workers.append(worker)
            logger.info(f"{self.agent_type.value} Agent worker_{i} 已创建")
    
    async def start(self):
        """启动智能体"""
        if self._running:
            return
        
        logger.info(f"启动 {self.agent_type.value} Agent...")
        self._shutdown_flag = False
        
        # 加载人物Skill
        logger.info(f"开始加载人物Skill")
        self._character_skills = self._load_character_skills()
        logger.info(f"人物Skill加载结果: {len(self._character_skills)} 个技能")
        
        self._running = True
        
        # 启动worker线程
        self._start_workers()
        
        logger.info(f"{self.agent_type.value} Agent 已启动，{self.max_workers} 个工作线程")
    
    async def stop(self, wait: bool = True):
        """停止智能体"""
        if not self._running:
            return
        
        logger.info(f"停止 {self.agent_type.value} Agent...")
        self._shutdown_flag = True
        
        if wait:
            for worker in self._workers:
                worker.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        self._running = False
        logger.info(f"{self.agent_type.value} Agent 已停止")
    
    async def submit_task(self, task_type: str, params: Dict[str, Any]) -> str:
        """提交任务"""
        # 确保worker已启动
        if not self._running:
            self._start_workers()
        
        task_id = str(uuid.uuid4())
        task = AgentTask(
            id=task_id,
            type=task_type,
            params=params
        )
        
        self._tasks[task_id] = task
        await self._queue.put(task_id)
        
        logger.info(f"{self.agent_type.value} Agent 任务已提交: {task_id}")
        return task_id
    
    async def get_task_status(self, task_id: str) -> Optional[AgentTask]:
        """获取任务状态"""
        return self._tasks.get(task_id)
    
    async def _run_worker(self, name: str):
        """工作线程"""
        logger.info(f"{name} 启动")
        
        while not self._shutdown_flag:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                task = self._tasks.get(task_id)
                
                if not task:
                    logger.warning(f"任务不存在: {task_id}")
                    continue
                
                await self._execute_task(task)
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info(f"{name} 被取消")
                break
            except Exception as e:
                logger.error(f"{name} 异常: {e}")
        
        logger.info(f"{name} 退出")
    
    async def _execute_task(self, task: AgentTask):
        """执行任务"""
        task.status = TaskStatus.RUNNING
        task.started_at = asyncio.get_event_loop().time()
        
        logger.info(f"执行任务: {task.id} (type={task.type})")
        
        try:
            result = await self._run_task(task)
            task.status = TaskStatus.COMPLETED
            task.completed_at = asyncio.get_event_loop().time()
            task.result = result
            
            duration = task.completed_at - task.started_at
            logger.info(f"任务执行成功: {task.id} - 耗时: {duration:.2f}s")
            
            # 记录任务执行情况到监控系统
            monitoring_manager.record_task(f"{self.agent_type.value}_{task.type}", "completed", duration)
            # 记录Agent状态到监控系统
            active_tasks = sum(1 for t in self._tasks.values() if t.status in [TaskStatus.PENDING, TaskStatus.RUNNING])
            monitoring_manager.record_agent_status(self.agent_type.value, "active", active_tasks)
            
            # 发布任务完成消息
            await message_bus.publish("task_completed", {
                "task_id": task.id,
                "task_type": task.type,
                "agent_type": self.agent_type.value,
                "status": "completed",
                "result": result,
                "duration": duration,
                "completed_at": task.completed_at
            })
            
            # 自动发送任务结果给相关Agent
            await self._send_task_result(task, result)
            # 自动触发下一个任务
            await self._trigger_next_task(task, result)
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.completed_at = asyncio.get_event_loop().time()
            task.error = str(e)
            duration = task.completed_at - task.started_at
            
            logger.error(f"任务执行失败: {task.id} - {e} - 耗时: {duration:.2f}s")
            
            # 记录任务执行情况到监控系统
            monitoring_manager.record_task(f"{self.agent_type.value}_{task.type}", "failed", duration)
            # 记录错误到监控系统
            monitoring_manager.record_error(f"{self.agent_type.value}_task", str(e))
            # 记录Agent状态到监控系统
            active_tasks = sum(1 for t in self._tasks.values() if t.status in [TaskStatus.PENDING, TaskStatus.RUNNING])
            monitoring_manager.record_agent_status(self.agent_type.value, "error", active_tasks)
            
            # 发布任务完成消息（失败）
            await message_bus.publish("task_completed", {
                "task_id": task.id,
                "task_type": task.type,
                "agent_type": self.agent_type.value,
                "status": "failed",
                "error": str(e),
                "duration": duration,
                "completed_at": task.completed_at
            })
    
    def _load_character_skills(self) -> Dict[str, Any]:
        """加载人物Skill"""
        # 直接使用全局缓存的人物Skill
        logger.info(f"使用全局人物Skill缓存，共 {len(_global_character_skills)} 个技能")
        return _global_character_skills
    
    async def _handle_character_task(self, task: AgentTask) -> Any:
        """处理人物Skill任务"""
        character_id = task.type
        if character_id in self._character_skills:
            handler = self._character_skills[character_id]
            try:
                result = await handler.execute(**task.params)
                logger.info(f"人物Skill执行成功: {character_id}")
                return result
            except Exception as e:
                logger.error(f"人物Skill执行失败: {character_id} - {e}")
                raise
        else:
            raise ValueError(f"未知的人物Skill: {character_id}")
    
    async def _run_task(self, task: AgentTask) -> Any:
        """运行具体任务（子类实现）"""
        # 先检查是否是人物SKILL任务
        if task.type in self._character_skills:
            return await self._handle_character_task(task)
        # 否则由子类实现
        raise NotImplementedError("子类必须实现 _run_task 方法")
    
    async def _send_task_result(self, task: AgentTask, result: Any):
        """发送任务结果给相关Agent"""
        # 根据任务类型确定目标Agent
        target_agent = self._get_target_agent(task.type)
        if target_agent:
            # 发送任务结果消息
            await message_bus.publish("agent_message", {
                "sender": self.agent_type.value,
                "receiver": target_agent,
                "content": f"任务 {task.type} 执行完成",
                "task_id": task.id,
                "result": result
            })
            logger.info(f"已发送任务结果给 {target_agent}")
    
    async def _trigger_next_task(self, task: AgentTask, result: Any):
        """触发下一个任务"""
        # 根据当前任务类型确定下一个任务类型
        next_task = self._get_next_task(task.type)
        if next_task:
            # 提交下一个任务
            next_task_result = await agent_scheduler.submit_task(
                task_type=next_task,
                params={"previous_result": result, "previous_task_id": task.id}
            )
            if next_task_result.get("success"):
                next_task_id = next_task_result["data"]["task_id"]
                logger.info(f"已触发下一个任务: {next_task} - ID: {next_task_id}")
    
    def _get_target_agent(self, task_type: str) -> Optional[str]:
        """根据任务类型获取目标Agent"""
        target_map = {
            "scrape": "data_analysis",
            "analyze": "summarizer",
            "visualize": "summarizer",
            "sentiment": "summarizer",
            "ner": "summarizer",
            "translation": "summarizer"
        }
        return target_map.get(task_type)
    
    def _get_next_task(self, task_type: str) -> Optional[str]:
        """根据当前任务类型获取下一个任务类型"""
        next_task_map = {
            "scrape": "analyze",
            "analyze": "visualize",
            "visualize": "sentiment",
            "sentiment": "summary",
            "ner": "summary",
            "translation": "summary"
        }
        return next_task_map.get(task_type)


class CheckerAgent(BaseAgent):
    """检查Agent"""
    
    def __init__(self, max_workers: int = 5):
        super().__init__(AgentType.CHECKER, max_workers)
    
    async def _run_task(self, task: AgentTask) -> Any:
        """执行检查任务"""
        # 先检查是否是人物SKILL任务
        if task.type in self._character_skills:
            return await self._handle_character_task(task)
        
        task_type = task.type
        params = task.params
        
        if task_type == "website":
            # 检查网站
            url = params.get("url")
            logger.info(f"检查网站: {url}")
            # 模拟检查
            await asyncio.sleep(1)
            return {"status": "success", "url": url, "checked": True}
        
        elif task_type == "system":
            # 检查系统
            logger.info("检查系统状态")
            # 模拟检查
            await asyncio.sleep(0.5)
            return {"status": "success", "system": "healthy"}
        
        else:
            raise ValueError(f"未知的检查类型: {task_type}")


class ScraperAgent(BaseAgent):
    """爬虫Agent"""
    
    def __init__(self, max_workers: int = 10):
        super().__init__(AgentType.SCRAPER, max_workers)
    
    async def _run_task(self, task: AgentTask) -> Any:
        """执行爬虫任务"""
        # 先检查是否是人物SKILL任务
        if task.type in self._character_skills:
            return await self._handle_character_task(task)
        
        task_type = task.type
        params = task.params
        
        if task_type == "website":
            # 爬取网站
            url = params.get("url")
            logger.info(f"爬取网站: {url}")
            # 模拟爬取
            await asyncio.sleep(2)
            return {"status": "success", "url": url, "content": "爬取的内容"}
        
        elif task_type == "search":
            # 使用真实的搜索引擎工具
            from tools.tool_manager import ToolManager, register_all_skills
            
            # 确保技能已注册
            tm = ToolManager.get_instance()
            if not tm.has_tool("search_engine"):
                logger.info("搜索引擎工具未注册，正在注册所有技能...")
                register_all_skills()
            
            query = params.get("query", "")
            logger.info(f"搜索: {query}")
            
            # 执行搜索引擎工具 - 使用关键字参数
            result = await tm.execute(tool_name="search_engine", query=query, mode="search")
            
            if result.get("success", False):
                return {
                    "status": "success", 
                    "query": query, 
                    "results": result.get("results", []),
                    "report_path": result.get("report_path")
                }
            else:
                # 如果搜索引擎失败，回退到模拟搜索
                logger.warning(f"搜索引擎失败，回退到模拟搜索: {result.get('error', 'Unknown error')}")
                await asyncio.sleep(1)
                return {"status": "success", "query": query, "results": ["结果1", "结果2"]}
        
        elif task_type == "scrape":
            # 通用爬取
            url = params.get("url")
            query = params.get("query")
            logger.info(f"爬取: {url} (查询: {query})")
            # 模拟爬取
            await asyncio.sleep(2)
            return {"status": "success", "url": url, "query": query, "content": "爬取的内容"}
        
        else:
            raise ValueError(f"未知的爬虫类型: {task_type}")


class VulnerabilityAgent(BaseAgent):
    """漏洞Agent"""
    
    def __init__(self, max_workers: int = 5):
        super().__init__(AgentType.VULNERABILITY, max_workers)
    
    async def _run_task(self, task: AgentTask) -> Any:
        """执行漏洞扫描任务"""
        # 先检查是否是人物SKILL任务
        if task.type in self._character_skills:
            return await self._handle_character_task(task)
        
        task_type = task.type
        params = task.params
        
        if task_type == "scan":
            # 漏洞扫描
            target = params.get("target")
            logger.info(f"漏洞扫描: {target}")
            # 模拟扫描
            await asyncio.sleep(3)
            return {"status": "success", "target": target, "vulnerabilities": []}
        
        elif task_type == "analysis":
            # 漏洞分析
            vulnerability = params.get("vulnerability")
            logger.info(f"漏洞分析: {vulnerability}")
            # 模拟分析
            await asyncio.sleep(1.5)
            return {"status": "success", "vulnerability": vulnerability, "severity": "low"}
        
        else:
            raise ValueError(f"未知的漏洞类型: {task_type}")


class SummarizerAgent(BaseAgent):
    """总结Agent"""
    
    def __init__(self, max_workers: int = 3):
        super().__init__(AgentType.SUMMARIZER, max_workers)
    
    async def _run_task(self, task: AgentTask) -> Any:
        """执行总结任务"""
        # 先检查是否是人物SKILL任务
        if task.type in self._character_skills:
            return await self._handle_character_task(task)
        
        task_type = task.type
        params = task.params
        
        if task_type == "text":
            # 文本总结
            text = params.get("text")
            logger.info(f"总结文本: {text[:50]}...")
            # 模拟总结
            await asyncio.sleep(1)
            return {"status": "success", "summary": "这是一个文本总结"}
        
        elif task_type == "report":
            # 报告总结
            data = params.get("data")
            logger.info("总结报告")
            # 模拟总结
            await asyncio.sleep(2)
            return {"status": "success", "report": "这是一个报告总结"}
        
        elif task_type == "summary":
            # 通用总结
            previous_result = params.get("previous_result")
            # 添加空值判断
            data = previous_result.get("data", {}) if isinstance(previous_result, dict) else {}
            logger.info("通用总结")
            # 模拟总结
            await asyncio.sleep(1)
            return {"status": "success", "summary": "这是一个通用总结"}
        
        elif task_type == "summarize":
            # 汇总总结（工作流使用）
            previous_result = params.get("previous_result")
            data = previous_result.get("data", {}) if isinstance(previous_result, dict) else {}
            logger.info("汇总总结")
            # 模拟总结
            await asyncio.sleep(1)
            return {"status": "success", "summary": "任务执行完成，这是汇总结果"}
        
        elif task_type == "chat":
            # 聊天消息处理
            message = params.get("message")
            user_id = params.get("user_id")
            agent_id = params.get("agent_id")
            logger.info(f"处理聊天消息: {message[:50]}... (用户: {user_id}, Agent: {agent_id})")
            
            # 智能分析用户意图并生成回复
            reply = self._generate_smart_reply(message, user_id, agent_id)
            
            # 模拟处理时间
            await asyncio.sleep(1)
            return {"status": "success", "reply": reply}
        
        else:
            raise ValueError(f"未知的总结类型: {task_type}")
    
    def _generate_smart_reply(self, message: str, user_id: str, agent_id: str) -> str:
        """生成智能回复"""
        # 常见问题和回答
        common_responses = {
            "你好": "你好！我是你的智能助手，有什么可以帮助你的吗？",
            "再见": "再见！有需要随时找我。",
            "谢谢": "不客气！很高兴能帮到你。",
            "你是谁": "我是你的智能助手，能够帮你执行各种操作，如打开应用、访问网页等。",
            "你能做什么": "我可以帮你打开应用程序、访问网页、关闭应用程序等操作。例如，你可以说'打开微信'、'访问百度'等。",
            "帮助": "你可以让我帮你做以下事情：\n1. 打开应用程序（如：打开微信）\n2. 关闭应用程序（如：关闭微信）\n3. 访问网页（如：访问百度）\n4. 回答你的问题"
        }
        
        # 检查是否是常见问题
        for key, value in common_responses.items():
            if key in message:
                return value
        
        # 检查是否是操作指令
        if message.startswith(('打开', '关闭', '退出', '访问', '打开网页')):
            return f"我理解你的指令：{message}。正在执行操作..."
        
        # 检查是否是问候语
        greetings = ['你好', '嗨', '哈喽', '嗨喽', 'hi', 'hello', 'hey']
        for greeting in greetings:
            if greeting in message.lower():
                return "你好！我是你的智能助手，有什么可以帮助你的吗？"
        
        # 检查是否是感谢语
        thanks = ['谢谢', '多谢', 'thank', 'thanks']
        for thank in thanks:
            if thank in message.lower():
                return "不客气！很高兴能帮到你。"
        
        # 默认回复
        return f"我收到了你的消息：{message}。如果你需要帮助，可以告诉我你想做什么，比如'打开微信'、'访问百度'等。"


class DataAnalysisAgent(BaseAgent):
    """数据分析Agent"""
    
    def __init__(self, max_workers: int = 5):
        super().__init__(AgentType.DATA_ANALYSIS, max_workers)
    
    async def _run_task(self, task: AgentTask) -> Any:
        """执行数据分析任务"""
        # 先检查是否是人物SKILL任务
        if task.type in self._character_skills:
            return await self._handle_character_task(task)
        
        task_type = task.type
        params = task.params
        
        if task_type == "analyze":
            # 数据分析
            data = params.get("data")
            logger.info(f"分析数据: {len(data) if data else 0} 条记录")
            # 模拟分析
            await asyncio.sleep(2)
            return {"status": "success", "analysis": "数据分析结果", "insights": ["洞察1", "洞察2"]}
        
        elif task_type == "visualize":
            # 数据可视化
            data = params.get("data")
            logger.info("数据可视化")
            # 模拟可视化
            await asyncio.sleep(1.5)
            return {"status": "success", "visualization": "数据可视化结果"}
        
        else:
            raise ValueError(f"未知的数据分析类型: {task_type}")


class NlpAgent(BaseAgent):
    """自然语言处理Agent"""
    
    def __init__(self, max_workers: int = 8):
        super().__init__(AgentType.NLP, max_workers)
    
    async def _run_task(self, task: AgentTask) -> Any:
        """执行自然语言处理任务"""
        # 先检查是否是人物SKILL任务
        if task.type in self._character_skills:
            return await self._handle_character_task(task)
        
        task_type = task.type
        params = task.params
        
        if task_type == "sentiment":
            # 情感分析
            text = params.get("text")
            # 安全处理空值
            text_content = text[:50] if text else ""
            logger.info(f"情感分析: {text_content}...")
            # 模拟分析
            await asyncio.sleep(1)
            return {"status": "success", "sentiment": "positive", "score": 0.85}
        
        elif task_type == "ner":
            # 命名实体识别
            text = params.get("text")
            # 安全处理空值
            text_content = text[:50] if text else ""
            logger.info(f"命名实体识别: {text_content}...")
            # 模拟识别
            await asyncio.sleep(1)
            return {"status": "success", "entities": [{"type": "PERSON", "text": "张三"}, {"type": "LOCATION", "text": "北京"}]}
        
        elif task_type == "translation" or task_type == "translate":
            # 翻译
            text = params.get("text")
            target_language = params.get("target_language", "en")
            # 安全处理空值
            text_content = text[:50] if text else ""
            logger.info(f"翻译: {text_content}... 到 {target_language}")
            # 模拟翻译
            await asyncio.sleep(1.5)
            return {"status": "success", "translated_text": "Translated text"}
        
        else:
            raise ValueError(f"未知的自然语言处理类型: {task_type}")


class PlanningAgent(BaseAgent):
    """规划Agent - 负责任务规划和分解"""
    
    def __init__(self, max_workers: int = 5):
        super().__init__(AgentType.PLANNING, max_workers)
    
    async def _run_task(self, task: AgentTask) -> Any:
        """执行规划任务"""
        task_type = task.type
        params = task.params
        
        if task_type == "create_plan":
            # 创建任务计划
            goal = params.get("goal", "")
            constraints = params.get("constraints", [])
            
            logger.info(f"创建任务计划: {goal[:50]}...")
            await asyncio.sleep(1)
            
            # 生成计划步骤
            plan_steps = self._generate_plan(goal, constraints)
            
            return {
                "status": "success",
                "goal": goal,
                "steps": plan_steps,
                "total_steps": len(plan_steps),
                "estimated_time": len(plan_steps) * 2  # 每步预估2秒
            }
        
        elif task_type == "optimize_plan":
            # 优化现有计划
            current_plan = params.get("plan", [])
            feedback = params.get("feedback", "")
            
            logger.info(f"优化任务计划，当前{len(current_plan)}步")
            await asyncio.sleep(0.8)
            
            # 基于反馈优化计划
            optimized_plan = self._optimize_plan(current_plan, feedback)
            
            return {
                "status": "success",
                "original_steps": len(current_plan),
                "optimized_steps": len(optimized_plan),
                "improvements": ["减少冗余步骤", "合并相似任务", "优化执行顺序"]
            }
        
        elif task_type == "validate_plan":
            # 验证计划可行性
            plan = params.get("plan", [])
            resources = params.get("resources", {})
            
            logger.info(f"验证计划可行性，共{len(plan)}步")
            await asyncio.sleep(0.5)
            
            # 检查计划可行性
            validation_result = self._validate_plan(plan, resources)
            
            return {
                "status": "success",
                "is_feasible": validation_result["feasible"],
                "issues": validation_result.get("issues", []),
                "suggestions": validation_result.get("suggestions", [])
            }
        
        else:
            raise ValueError(f"未知的规划类型: {task_type}")
    
    def _generate_plan(self, goal: str, constraints: List[str]) -> List[Dict[str, Any]]:
        """生成任务计划步骤（增强版 - 支持更多场景）"""
        steps = []
        
        # 分析目标关键词，使用更智能的匹配
        goal_lower = goal.lower()
        
        # 场景1: 爬虫/数据抓取类任务
        if any(keyword in goal for keyword in ["爬取", "爬虫", "抓取", "采集", "下载"]):
            steps.extend([
                {
                    "step_id": 1,
                    "action": "analyze_target",
                    "description": "分析目标网站结构和反爬策略",
                    "estimated_time": 2,
                    "details": "检查robots.txt、API接口、页面结构"
                },
                {
                    "step_id": 2,
                    "action": "design_scraper",
                    "description": "设计爬虫策略",
                    "estimated_time": 2,
                    "details": "确定请求频率、代理设置、数据解析规则"
                },
                {
                    "step_id": 3,
                    "action": "fetch_data",
                    "description": "执行数据抓取",
                    "estimated_time": 5,
                    "details": "批量获取数据，处理分页和异常"
                },
                {
                    "step_id": 4,
                    "action": "process_data",
                    "description": "数据清洗和处理",
                    "estimated_time": 3,
                    "details": "去重、格式化、验证数据完整性"
                },
                {
                    "step_id": 5,
                    "action": "store_results",
                    "description": "存储结果",
                    "estimated_time": 1,
                    "details": "保存到文件或数据库"
                }
            ])
        
        # 场景2: 数据分析类任务
        elif any(keyword in goal for keyword in ["分析", "统计", "趋势", "对比", "评估"]):
            steps.extend([
                {
                    "step_id": 1,
                    "action": "collect_data",
                    "description": "收集相关数据源",
                    "estimated_time": 3,
                    "details": "从数据库、API或文件获取原始数据"
                },
                {
                    "step_id": 2,
                    "action": "data_preprocessing",
                    "description": "数据预处理",
                    "estimated_time": 2,
                    "details": "清洗、转换、处理缺失值"
                },
                {
                    "step_id": 3,
                    "action": "analyze_trends",
                    "description": "执行分析算法",
                    "estimated_time": 4,
                    "details": "统计分析、趋势识别、模式发现"
                },
                {
                    "step_id": 4,
                    "action": "visualize_results",
                    "description": "可视化结果",
                    "estimated_time": 2,
                    "details": "生成图表、热力图、时间序列图"
                },
                {
                    "step_id": 5,
                    "action": "generate_report",
                    "description": "生成分析报告",
                    "estimated_time": 2,
                    "details": "总结关键发现和建议"
                }
            ])
        
        # 场景3: 天气查询类任务
        elif any(keyword in goal for keyword in ["天气", "气温", "预报"]):
            steps.extend([
                {
                    "step_id": 1,
                    "action": "parse_location",
                    "description": "解析地理位置",
                    "estimated_time": 1,
                    "details": "提取城市名称，转换为标准格式"
                },
                {
                    "step_id": 2,
                    "action": "query_weather_api",
                    "description": "查询天气API",
                    "estimated_time": 1,
                    "details": "调用第三方天气服务获取数据"
                },
                {
                    "step_id": 3,
                    "action": "format_response",
                    "description": "格式化响应",
                    "estimated_time": 1,
                    "details": "整理温度、湿度、风力等信息"
                }
            ])
        
        # 场景4: 搜索/检索类任务
        elif any(keyword in goal for keyword in ["搜索", "查找", "检索", "查询"]):
            steps.extend([
                {
                    "step_id": 1,
                    "action": "extract_keywords",
                    "description": "提取搜索关键词",
                    "estimated_time": 1,
                    "details": "从用户输入中提取核心词汇"
                },
                {
                    "step_id": 2,
                    "action": "search_sources",
                    "description": "多源搜索",
                    "estimated_time": 3,
                    "details": "搜索引擎、知识库、向量数据库并行搜索"
                },
                {
                    "step_id": 3,
                    "action": "rank_results",
                    "description": "结果排序和过滤",
                    "estimated_time": 2,
                    "details": "根据相关性评分排序，去除低质量结果"
                },
                {
                    "step_id": 4,
                    "action": "summarize_findings",
                    "description": "总结搜索结果",
                    "estimated_time": 2,
                    "details": "提取关键信息，生成简洁摘要"
                }
            ])
        
        # 场景5: 文件操作类任务
        elif any(keyword in goal for keyword in ["文件", "文档", "保存", "读取", "写入"]):
            steps.extend([
                {
                    "step_id": 1,
                    "action": "validate_path",
                    "description": "验证文件路径",
                    "estimated_time": 1,
                    "details": "检查路径合法性，创建必要目录"
                },
                {
                    "step_id": 2,
                    "action": "execute_file_operation",
                    "description": "执行文件操作",
                    "estimated_time": 2,
                    "details": "读取、写入、复制或移动文件"
                },
                {
                    "step_id": 3,
                    "action": "verify_result",
                    "description": "验证操作结果",
                    "estimated_time": 1,
                    "details": "确认文件存在性和内容正确性"
                }
            ])
        
        # 场景6: 邮件/消息发送类任务
        elif any(keyword in goal for keyword in ["邮件", "发送", "通知", "消息"]):
            steps.extend([
                {
                    "step_id": 1,
                    "action": "prepare_content",
                    "description": "准备发送内容",
                    "estimated_time": 2,
                    "details": "格式化邮件正文、附件、收件人列表"
                },
                {
                    "step_id": 2,
                    "action": "validate_recipients",
                    "description": "验证收件人地址",
                    "estimated_time": 1,
                    "details": "检查邮箱格式，过滤无效地址"
                },
                {
                    "step_id": 3,
                    "action": "send_message",
                    "description": "执行发送操作",
                    "estimated_time": 3,
                    "details": "调用邮件服务器或消息API"
                },
                {
                    "step_id": 4,
                    "action": "confirm_delivery",
                    "description": "确认送达状态",
                    "estimated_time": 2,
                    "details": "检查发送日志，处理失败情况"
                }
            ])
        
        # 默认通用计划模板
        else:
            steps.extend([
                {
                    "step_id": 1,
                    "action": "understand_requirement",
                    "description": "理解用户需求",
                    "estimated_time": 1,
                    "details": "分析任务目标和约束条件"
                },
                {
                    "step_id": 2,
                    "action": "identify_resources",
                    "description": "识别所需资源",
                    "estimated_time": 1,
                    "details": "确定需要的工具、API、数据源"
                },
                {
                    "step_id": 3,
                    "action": "execute_task",
                    "description": "执行核心任务",
                    "estimated_time": 5,
                    "details": "调用相应的Agent或工具完成任务"
                },
                {
                    "step_id": 4,
                    "action": "verify_result",
                    "description": "验证结果质量",
                    "estimated_time": 2,
                    "details": "检查结果是否符合预期"
                },
                {
                    "step_id": 5,
                    "action": "format_output",
                    "description": "格式化输出",
                    "estimated_time": 1,
                    "details": "将结果转换为用户友好的格式"
                }
            ])
        
        return steps
    
    def _optimize_plan(self, current_plan: List[Dict], feedback: str) -> List[Dict]:
        """优化现有计划"""
        # 简单优化：移除重复步骤，合并相似步骤
        optimized = []
        seen_actions = set()
        
        for step in current_plan:
            action = step.get("action", "")
            if action not in seen_actions:
                optimized.append(step)
                seen_actions.add(action)
        
        return optimized
    
    def _validate_plan(self, plan: List[Dict], resources: Dict) -> Dict[str, Any]:
        """验证计划可行性"""
        issues = []
        suggestions = []
        
        # 检查步骤数量
        if len(plan) > 10:
            issues.append("计划步骤过多，建议简化")
            suggestions.append("考虑合并相关步骤")
        
        # 检查总时间
        total_time = sum(step.get("estimated_time", 0) for step in plan)
        if total_time > 60:
            issues.append(f"预计执行时间过长（{total_time}秒）")
            suggestions.append("考虑并行执行独立步骤")
        
        return {
            "feasible": len(issues) == 0,
            "issues": issues,
            "suggestions": suggestions
        }


class TextAnalyzerAgent(BaseAgent):
    """文本拆解提取总结Agent"""
    
    def __init__(self, max_workers: int = 5):
        super().__init__(AgentType.TEXT_ANALYZER, max_workers)
        # 初始化上下文记忆队列
        self.context_memory_queue = []
        # 使用全局BFS处理器（复用公共能力）
        self.bfs_processor = get_bfs_processor(max_depth=5, max_nodes=100)
    
    async def _run_task(self, task: AgentTask) -> Any:
        """执行文本拆解提取总结任务"""
        # 先检查是否是人物SKILL任务
        if task.type in self._character_skills:
            return await self._handle_character_task(task)
        
        task_type = task.type
        params = task.params
        
        if task_type == "analyze_text":
            # 文本拆解分析
            text = params.get("text")
            logger.info(f"文本拆解分析: {text[:50]}...")
            # 模拟分析
            await asyncio.sleep(2)
            
            # 拆解文本为段落
            paragraphs = self._split_into_paragraphs(text)
            
            # 提取每段的概要
            summaries = []
            for i, paragraph in enumerate(paragraphs):
                summary = self._generate_summary(paragraph)
                summaries.append({
                    "paragraph_index": i,
                    "content": paragraph,
                    "summary": summary
                })
            
            # 生成整体标题
            title = self._generate_title(text)
            
            # 构建树结构
            tree = self._build_content_tree(title, paragraphs, summaries)
            
            # 更新上下文记忆队列（BFS遍历）
            self._update_context_memory(tree)
            
            return {
                "status": "success",
                "title": title,
                "paragraphs": len(paragraphs),
                "analysis": summaries,
                "tree_structure": tree,
                "context_memory": self.context_memory_queue
            }
        
        elif task_type == "extract_summary":
            # 提取概要
            text = params.get("text")
            logger.info(f"提取概要: {text[:50]}...")
            # 模拟提取
            await asyncio.sleep(1)
            return {
                "status": "success",
                "summary": self._generate_summary(text)
            }
        
        elif task_type == "generate_title":
            # 生成标题
            text = params.get("text")
            logger.info(f"生成标题: {text[:50]}...")
            # 模拟生成
            await asyncio.sleep(0.5)
            return {
                "status": "success",
                "title": self._generate_title(text)
            }
        
        else:
            raise ValueError(f"未知的文本分析类型: {task_type}")
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """将文本分割为段落"""
        if not text:
            return []
        # 按换行符分割
        paragraphs = text.split('\n')
        # 过滤空段落
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        return paragraphs
    
    def _generate_summary(self, text: str) -> str:
        """生成文本概要"""
        if not text:
            return ""
        # 简单的概要生成逻辑
        words = text.split()
        if len(words) <= 10:
            return text
        # 提取前10个词作为概要
        summary = ' '.join(words[:10]) + '...'
        return summary
    
    def _generate_title(self, text: str) -> str:
        """生成文本标题"""
        if not text:
            return "无标题"
        # 简单的标题生成逻辑
        words = text.split()
        if len(words) <= 5:
            return text
        # 提取前5个词作为标题
        title = ' '.join(words[:5])
        return title
    
    def _build_content_tree(self, title: str, paragraphs: List[str], summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """构建内容树结构"""
        # 根节点（第一层）
        root = {
            "type": "root",
            "title": title,
            "children": []
        }
        
        # 功能节点（第二层）
        function_node = {
            "type": "function",
            "name": "text_analyzer",
            "children": []
        }
        root["children"].append(function_node)
        
        # 标题节点（第三层）
        title_node = {
            "type": "title",
            "content": title,
            "children": []
        }
        function_node["children"].append(title_node)
        
        if paragraphs:
            # 第四层：左节点放一整篇文本，右节点放第一段概要
            fourth_level_node = {
                "type": "content_level",
                "children": [
                    # 左节点：一整篇文本
                    {
                        "type": "full_content",
                        "content": '\n'.join(paragraphs),
                        "children": []
                    },
                    # 右节点：第一段概要
                    {
                        "type": "summary",
                        "content": summaries[0]["summary"] if summaries else ""
                    }
                ]
            }
            title_node["children"].append(fourth_level_node)
            
            # 第五层及以下：左边节点放前一层的段落全部内容，右边放下一段的概要，依次类推
            current_parent = fourth_level_node["children"][0]  # 从第四层的左节点开始
            for i in range(len(paragraphs)):
                if i > 0:  # 从第二段开始
                    level_node = {
                        "type": f"level_{5 + i - 1}",
                        "children": [
                            # 左节点：前一层的段落全部内容
                            {
                                "type": "content",
                                "content": paragraphs[i-1],
                                "children": []
                            },
                            # 右节点：当前段的概要
                            {
                                "type": "summary",
                                "content": summaries[i]["summary"] if i < len(summaries) else ""
                            }
                        ]
                    }
                    current_parent["children"].append(level_node)
                    current_parent = level_node["children"][0]  # 下一层的父节点是当前层的左节点
        
        return root
    
    def _update_context_memory(self, tree: Dict[str, Any]):
        """使用全局BFS处理器更新上下文记忆队列"""
        # 清空队列
        self.context_memory_queue = []
        
        # 将字典树转换为BFSTextProcessor可处理的格式
        # 直接使用BFS遍历字典树（复用公共算法逻辑）
        bfs_queue = self.bfs_processor.bfs_traverse_dict(tree)
        
        # 将遍历结果转换为上下文记忆格式
        for node in bfs_queue:
            node_info = {
                "type": node.get("type"),
                "content": node.get("content", node.get("title", "")),
                "level": node.get("level", 0)
            }
            self.context_memory_queue.append(node_info)
        
        logger.info(f"使用全局BFS处理器更新上下文记忆，共{len(self.context_memory_queue)}个节点")
    
    def _get_node_level(self, node: Dict[str, Any], root: Dict[str, Any]) -> int:
        """获取节点在树中的层级"""
        if node == root:
            return 1
        
        # BFS查找父节点
        queue = [(root, 1)]
        while queue:
            current, level = queue.pop(0)
            if "children" in current and current["children"]:
                for child in current["children"]:
                    if child == node:
                        return level + 1
                    queue.append((child, level + 1))
        return 0


class AgentScheduler:
    """智能体调度中心"""
    
    def __init__(self):
        # 初始化各个Agent
        self.agents = {
            AgentType.CHECKER: CheckerAgent(),
            AgentType.SCRAPER: ScraperAgent(),
            AgentType.VULNERABILITY: VulnerabilityAgent(),
            AgentType.SUMMARIZER: SummarizerAgent(),
            AgentType.DATA_ANALYSIS: DataAnalysisAgent(),
            AgentType.NLP: NlpAgent(),
            AgentType.TEXT_ANALYZER: TextAnalyzerAgent(),
            AgentType.PLANNING: PlanningAgent()  # ✅ 新增PlanningAgent
        }
        
        # 任务分配映射
        self.task_mapping = {
            "check": AgentType.CHECKER,
            "scrape": AgentType.SCRAPER,
            "crawl": AgentType.SCRAPER,
            "vulnerability": AgentType.VULNERABILITY,
            "scan": AgentType.VULNERABILITY,
            "summarize": AgentType.SUMMARIZER,
            "summary": AgentType.SUMMARIZER,
            "website": AgentType.SCRAPER,
            "search": AgentType.SCRAPER,
            "system": AgentType.CHECKER,
            "analyze": AgentType.DATA_ANALYSIS,
            "visualize": AgentType.DATA_ANALYSIS,
            "data": AgentType.DATA_ANALYSIS,
            "sentiment": AgentType.NLP,
            "ner": AgentType.NLP,
            "translation": AgentType.NLP,
            "translate": AgentType.NLP,
            "nlp": AgentType.NLP,
            "report": AgentType.SUMMARIZER,
            "chat": AgentType.SUMMARIZER,  # 添加chat任务类型映射
            "analyze_text": AgentType.TEXT_ANALYZER,  # 文本拆解分析
            "extract_summary": AgentType.TEXT_ANALYZER,  # 提取概要
            "generate_title": AgentType.TEXT_ANALYZER,  # 生成标题
            "text_analyzer": AgentType.TEXT_ANALYZER,  # 文本分析
            # 规划相关任务
            "create_plan": AgentType.PLANNING,
            "optimize_plan": AgentType.PLANNING,
            "validate_plan": AgentType.PLANNING,
            "planning": AgentType.PLANNING,
            # 人物SKILL
            "bestfriend": AgentType.SUMMARIZER,
            "first_love": AgentType.SUMMARIZER,
            "goddess": AgentType.SUMMARIZER,
            "john_carmack": AgentType.SUMMARIZER,
            "libai": AgentType.SUMMARIZER
        }
        
        # 初始化意图识别器和任务拆解器
        self.intent_recognizer = IntentRecognizer()
        self.task_splitter = TaskSplitter()
        
        logger.info("Agent调度中心初始化完成")
    
    async def start(self):
        """启动所有Agent"""
        logger.info("启动所有Agent...")
        for agent in self.agents.values():
            await agent.start()
        logger.info("所有Agent已启动")
    
    async def stop(self, wait: bool = True):
        """停止所有Agent"""
        logger.info("停止所有Agent...")
        for agent in self.agents.values():
            await agent.stop(wait)
        logger.info("所有Agent已停止")
    
    async def submit_task(self, task_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """提交任务到合适的Agent"""
        try:
            # 检查边界限制
            if not boundary_manager.check_rate_limit(task_type):
                return response_manager.error(
                    code=429,
                    message="调用过于频繁，请稍后再试"
                )
            
            # 意图识别
            message = params.get("message", "")
            intent = self.intent_recognizer.recognize(message)
            
            # 任务拆解（添加await）
            sub_tasks = await self.task_splitter.split(task_type, params)
            
            # 检查是否需要串行执行（存在真正的数据依赖）
            needs_serial_execution = self._has_real_dependencies(sub_tasks)
            
            if needs_serial_execution:
                # 简单串行执行：按顺序等待每个任务完成
                results = []
                task_results = {}  # 存储各任务的实际结果
                
                for i, sub_task in enumerate(sub_tasks):
                    # 替换依赖占位符（使用前序任务的结果）
                    resolved_params = self._resolve_task_dependencies(sub_task["params"], task_results)
                    
                    # 确定任务类型对应的Agent
                    agent_type = self._get_agent_type(sub_task["type"])
                    if not agent_type:
                        return response_manager.error(
                            code=400,
                            message=f"未知的任务类型: {sub_task['type']}"
                        )
                    
                    # 提交任务并等待完成
                    agent = self.agents[agent_type]
                    priority = self._calculate_task_priority(sub_task["type"], intent)
                    task_id = await agent.submit_task(sub_task["type"], resolved_params)
                    
                    # 等待任务完成
                    task_result = await self._wait_for_task_completion(agent, task_id)
                    if not task_result or task_result.status.value != "completed":
                        return response_manager.error(
                            code=500,
                            message=f"任务执行失败: {sub_task['type']}"
                        )
                    
                    # 存储结果供后续任务使用
                    task_results[sub_task["type"]] = task_result.result
                    
                    # 记录调用和发布消息
                    boundary_manager.add_call(sub_task["type"])
                    await message_bus.publish("task_allocation", {
                        "task_type": sub_task["type"],
                        "params": resolved_params,
                        "agent_type": agent_type.value,
                        "task_id": task_id,
                        "priority": priority
                    })
                    
                    results.append({
                        "task_id": task_id,
                        "agent_type": agent_type.value,
                        "task_type": sub_task["type"],
                        "status": "completed",
                        "priority": priority
                    })
                
                return response_manager.success({
                    "tasks": results,
                    "status": "completed",
                    "intent": intent
                })
            else:
                # 无真实依赖，保持并行提交
                if len(sub_tasks) == 1:
                    sub_task = sub_tasks[0]
                    # 确定任务类型对应的Agent
                    agent_type = self._get_agent_type(sub_task["type"])
                    if not agent_type:
                        return response_manager.error(
                            code=400,
                            message=f"未知的任务类型: {sub_task['type']}"
                        )
                    
                    # 智能任务分配：根据负载选择最优Agent
                    agent_type = self._select_optimal_agent(agent_type, sub_task["type"])
                    
                    # 直接提交任务到对应的Agent
                    agent = self.agents[agent_type]
                    # 设置任务优先级
                    priority = self._calculate_task_priority(sub_task["type"], intent)
                    task_id = await agent.submit_task(sub_task["type"], sub_task["params"])
                    
                    # 记录调用
                    boundary_manager.add_call(sub_task["type"])
                    
                    # 发布任务分配消息
                    await message_bus.publish("task_allocation", {
                        "task_type": sub_task["type"],
                        "params": sub_task["params"],
                        "agent_type": agent_type.value,
                        "task_id": task_id,
                        "priority": priority
                    })
                    
                    logger.info(f"任务已分配: {sub_task['type']} -> {agent_type.value} Agent (优先级: {priority})")
                    return response_manager.success({
                        "task_id": task_id,
                        "agent_type": agent_type.value,
                        "status": "submitted",
                        "intent": intent,
                        "priority": priority
                    })
                else:
                    # 处理多个子任务
                    results = []
                    for sub_task in sub_tasks:
                        # 确定任务类型对应的Agent
                        agent_type = self._get_agent_type(sub_task["type"])
                        if not agent_type:
                            return response_manager.error(
                                code=400,
                                message=f"未知的任务类型: {sub_task['type']}"
                            )
                        
                        # 智能任务分配：根据负载选择最优Agent
                        agent_type = self._select_optimal_agent(agent_type, sub_task["type"])
                        
                        # 直接提交任务到对应的Agent
                        agent = self.agents[agent_type]
                        # 设置任务优先级
                        priority = self._calculate_task_priority(sub_task["type"], intent)
                        task_id = await agent.submit_task(sub_task["type"], sub_task["params"])
                        
                        # 记录调用
                        boundary_manager.add_call(sub_task["type"])
                        
                        # 发布任务分配消息
                        await message_bus.publish("task_allocation", {
                            "task_type": sub_task["type"],
                            "params": sub_task["params"],
                            "agent_type": agent_type.value,
                            "task_id": task_id,
                            "priority": priority
                        })
                        
                        logger.info(f"任务已分配: {sub_task['type']} -> {agent_type.value} Agent (优先级: {priority})")
                        results.append({
                            "task_id": task_id,
                            "agent_type": agent_type.value,
                            "task_type": sub_task["type"],
                            "status": "submitted",
                            "priority": priority
                        })
                    
                    return response_manager.success({
                        "tasks": results,
                        "status": "submitted",
                        "intent": intent
                    })
        except Exception as e:
            error_response = await exception_handler.handle_exception(e)
            return error_response
    
    def _has_real_dependencies(self, sub_tasks: List[Dict[str, Any]]) -> bool:
        """检查是否存在真正的数据依赖（需要前序任务结果）"""
        for sub_task in sub_tasks:
            params_str = str(sub_task["params"])
            # 检查是否包含非原始输入的占位符（如$search_result, $scraped_content等）
            if "$" in params_str and "$query" not in params_str:
                return True
        return False
    
    def _resolve_task_dependencies(self, params: Dict[str, Any], task_results: Dict[str, Any]) -> Dict[str, Any]:
        """解析任务依赖，将占位符替换为实际结果"""
        import re
        
        result = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                placeholder_name = value[1:]  # 去掉$前缀
                if placeholder_name in task_results:
                    result[key] = task_results[placeholder_name]
                else:
                    result[key] = value  # 保持原样
            else:
                result[key] = value
        return result
    
    async def _wait_for_task_completion(self, agent, task_id: str, timeout: float = 60.0):
        """等待任务完成"""
        try:
            start_time = asyncio.get_event_loop().time()
            while True:
                task_result = await agent.get_task_status(task_id)
                if not task_result:
                    return None
                
                if task_result.status.value in ["completed", "failed"]:
                    return task_result
                
                # 检查超时
                current_time = asyncio.get_event_loop().time()
                if current_time - start_time > timeout:
                    logger.warning(f"任务 {task_id} 超时")
                    return None
                
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"等待任务完成时出错: {e}")
            return None
    
    def _select_optimal_agent(self, agent_type: AgentType, task_type: str) -> AgentType:
        """选择最优Agent
        
        Args:
            agent_type: 推荐的Agent类型
            task_type: 任务类型
            
        Returns:
            最优的Agent类型
        """
        # 获取Agent信息
        agent_info = self.get_agent_info()
        
        # 计算每个Agent的负载
        agent_loads = {}
        for at, info in agent_info.items():
            if info["running"]:
                # 负载计算：队列长度 + 任务数
                load = info["queue_length"] + info["task_count"]
                agent_loads[at] = load
        
        # 选择能够处理该任务类型的Agent
        candidate_agents = []
        for at, load in agent_loads.items():
            # 检查Agent是否能够处理该任务类型
            if self._can_agent_handle_task(AgentType(at), task_type):
                candidate_agents.append((at, load))
        
        # 如果没有候选Agent，返回推荐的Agent类型
        if not candidate_agents:
            return agent_type
        
        # 选择负载最低的Agent
        min_load = float('inf')
        optimal_agent = agent_type
        
        for at, load in candidate_agents:
            if load < min_load:
                min_load = load
                optimal_agent = AgentType(at)
        
        return optimal_agent
    
    def _can_agent_handle_task(self, agent_type: AgentType, task_type: str) -> bool:
        """检查Agent是否能够处理该任务类型
        
        Args:
            agent_type: Agent类型
            task_type: 任务类型
            
        Returns:
            是否能够处理
        """
        # 任务类型到Agent类型的映射
        task_to_agent = {
            "check": AgentType.CHECKER,
            "website": AgentType.CHECKER,
            "system": AgentType.CHECKER,
            "scrape": AgentType.SCRAPER,
            "crawl": AgentType.SCRAPER,
            "search": AgentType.SCRAPER,
            "vulnerability": AgentType.VULNERABILITY,
            "scan": AgentType.VULNERABILITY,
            "summarize": AgentType.SUMMARIZER,
            "summary": AgentType.SUMMARIZER,
            "report": AgentType.SUMMARIZER,
            "chat": AgentType.SUMMARIZER,
            "analyze": AgentType.DATA_ANALYSIS,
            "visualize": AgentType.DATA_ANALYSIS,
            "data": AgentType.DATA_ANALYSIS,
            "sentiment": AgentType.NLP,
            "ner": AgentType.NLP,
            "translation": AgentType.NLP,
            "translate": AgentType.NLP,
            "nlp": AgentType.NLP,
            "analyze_text": AgentType.TEXT_ANALYZER,
            "extract_summary": AgentType.TEXT_ANALYZER,
            "generate_title": AgentType.TEXT_ANALYZER,
            "text_analyzer": AgentType.TEXT_ANALYZER
        }
        
        # 检查任务类型是否映射到当前Agent类型
        expected_agent = task_to_agent.get(task_type)
        if expected_agent:
            return agent_type == expected_agent
        
        # 检查是否是人物SKILL任务
        if task_type in _global_character_skills:
            # 人物SKILL任务可以由任何Agent处理
            return True
        
        # 默认返回False
        return False
    
    def _calculate_task_priority(self, task_type: str, intent: Dict[str, Any]) -> int:
        """计算任务优先级
        
        Args:
            task_type: 任务类型
            intent: 意图信息
            
        Returns:
            优先级 (1-10，10最高)
        """
        # 任务类型优先级映射
        priority_map = {
            "open_app": 8,
            "close_app": 7,
            "open_url": 7,
            "search": 6,
            "analyze": 5,
            "analyze_text": 5,
            "extract_summary": 4,
            "generate_title": 3,
            "summarize": 4,
            "chat": 3,
            "research": 6,
            "compare": 5
        }
        
        # 获取基础优先级
        base_priority = priority_map.get(task_type, 3)
        
        # 根据意图置信度调整优先级
        confidence = intent.get("confidence", 0.5)
        priority_adjustment = int((confidence - 0.5) * 2)
        
        # 计算最终优先级
        final_priority = base_priority + priority_adjustment
        
        # 确保优先级在1-10之间
        return max(1, min(10, final_priority))
    
    async def get_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务列表"""
        all_tasks = []
        for agent_type, agent in self.agents.items():
            for task_id, task in agent._tasks.items():
                all_tasks.append({
                    "task_id": task.id,
                    "type": task.type,
                    "status": task.status.value,
                    "created_at": task.created_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                    "params": task.params,
                    "agent_type": agent_type.value
                })
        return all_tasks
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        for agent_type, agent in self.agents.items():
            task = await agent.get_task_status(task_id)
            if task:
                return {
                    "task_id": task.id,
                    "type": task.type,
                    "status": task.status.value,
                    "created_at": task.created_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                    "params": task.params,
                    "result": task.result,
                    "error": task.error,
                    "agent_type": agent_type.value
                }
        return None
    
    def _get_agent_type(self, task_type: str) -> Optional[AgentType]:
        """根据任务类型获取Agent类型"""
        # 直接映射
        if task_type in self.task_mapping:
            return self.task_mapping[task_type]
        
        # 关键词匹配
        for keyword, at in self.task_mapping.items():
            if keyword in task_type.lower():
                return at
        
        # 默认返回
        return None
    
    def get_agent_info(self) -> Dict[str, Any]:
        """获取所有Agent信息"""
        info = {}
        for agent_type, agent in self.agents.items():
            info[agent_type.value] = {
                "type": agent_type.value,
                "max_workers": agent.max_workers,
                "running": agent._running,
                "queue_length": agent._queue.qsize(),
                "task_count": len(agent._tasks)
            }
        return info
    
    def get_agent_tasks(self, agent_type: str) -> List[Dict[str, Any]]:
        """获取指定Agent的任务列表"""
        tasks = []
        for at, agent in self.agents.items():
            if at.value == agent_type:
                for task_id, task in agent._tasks.items():
                    tasks.append({
                        "task_id": task.id,
                        "type": task.type,
                        "status": task.status.value,
                        "created_at": task.created_at,
                        "started_at": task.started_at,
                        "completed_at": task.completed_at,
                        "params": task.params
                    })
                break
        return tasks
    
    def get_all_tasks(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有Agent的任务列表"""
        all_tasks = {}
        for agent_type, agent in self.agents.items():
            agent_tasks = []
            for task_id, task in agent._tasks.items():
                agent_tasks.append({
                    "task_id": task.id,
                    "type": task.type,
                    "status": task.status.value,
                    "created_at": task.created_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                    "params": task.params
                })
            all_tasks[agent_type.value] = agent_tasks
        return all_tasks


# 全局实例
agent_scheduler = AgentScheduler()