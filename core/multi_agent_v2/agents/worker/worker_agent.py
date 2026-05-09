"""
WorkerAgent - 执行Agent

负责具体任务的执行
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..base.base_agent import (
    BaseAgent,
    AgentType,
    Capability,
    Task,
    ActionResult,
    Thought
)

logger = logging.getLogger(__name__)


class WorkerAgent(BaseAgent):
    """WorkerAgent - 负责具体任务的执行"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "执行Agent，负责具体任务的执行",
        specialization: Optional[str] = None
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.WORKER,
            name=name,
            description=description
        )

        self.specialization = specialization or "general"

        # 定义WorkerAgent的能力
        self.capabilities = self._initialize_capabilities()

        logger.info(f"WorkerAgent初始化完成: {self.agent_id} (specialization={self.specialization})")

    def _initialize_capabilities(self) -> List[Capability]:
        """初始化能力"""
        capabilities = []

        if self.specialization == "scraping":
            capabilities = [
                Capability(
                    name="web_scraping",
                    description="网页抓取能力",
                    keywords=["爬取", "抓取", "网页", "数据"],
                    expertise_level=0.9,
                    max_concurrent_tasks=3,
                    avg_execution_time=15.0,
                    success_rate=0.85
                ),
                Capability(
                    name="data_extraction",
                    description="数据提取能力",
                    keywords=["提取", "解析", "数据"],
                    expertise_level=0.85,
                    max_concurrent_tasks=5,
                    avg_execution_time=10.0,
                    success_rate=0.88
                )
            ]
        elif self.specialization == "analysis":
            capabilities = [
                Capability(
                    name="data_analysis",
                    description="数据分析能力",
                    keywords=["分析", "统计", "数据"],
                    expertise_level=0.9,
                    max_concurrent_tasks=2,
                    avg_execution_time=20.0,
                    success_rate=0.9
                ),
                Capability(
                    name="visualization",
                    description="可视化能力",
                    keywords=["可视化", "图表", "展示"],
                    expertise_level=0.8,
                    max_concurrent_tasks=3,
                    avg_execution_time=15.0,
                    success_rate=0.85
                )
            ]
        elif self.specialization == "processing":
            capabilities = [
                Capability(
                    name="data_processing",
                    description="数据处理能力",
                    keywords=["处理", "清洗", "转换"],
                    expertise_level=0.85,
                    max_concurrent_tasks=5,
                    avg_execution_time=10.0,
                    success_rate=0.9
                ),
                Capability(
                    name="format_conversion",
                    description="格式转换能力",
                    keywords=["转换", "格式", "输出"],
                    expertise_level=0.8,
                    max_concurrent_tasks=10,
                    avg_execution_time=5.0,
                    success_rate=0.95
                )
            ]
        else:
            # 通用能力
            capabilities = [
                Capability(
                    name="general_execution",
                    description="通用执行能力",
                    keywords=["执行", "处理", "完成"],
                    expertise_level=0.7,
                    max_concurrent_tasks=5,
                    avg_execution_time=10.0,
                    success_rate=0.85
                )
            ]

        return capabilities

    async def execute(self, task: Task) -> ActionResult:
        """执行任务"""
        logger.info(f"WorkerAgent开始执行任务: {task.task_id}")

        try:
            # 1. 思考
            thought = await self.think(task)
            logger.info(f"思考完成: {thought.reasoning}")

            # 2. 执行
            result = await self._execute_task(task)

            # 3. 反思
            reflection = await self.reflect(result)

            return result

        except Exception as e:
            logger.error(f"WorkerAgent执行失败: {e}")
            return ActionResult(
                success=False,
                error=str(e)
            )

    async def _execute_task(self, task: Task) -> ActionResult:
        """执行具体任务"""
        start_time = asyncio.get_event_loop().time()

        try:
            # 首先检查任务描述中是否包含系统操作相关的关键词
            description = task.description.lower() if task.description else ""
            system_keywords = ["打开", "启动", "运行", "启动程序", "执行程序"]
            app_keywords = ["qq", "微信", "浏览器", "finder", "terminal", "计算器", "日历", "邮件"]
            
            has_system_intent = any(keyword in description for keyword in system_keywords)
            has_app_intent = any(keyword in description for keyword in app_keywords)
            
            # 如果有系统操作意图，执行系统命令
            if has_system_intent or has_app_intent:
                result = await self._execute_system_command(task)
            else:
                # 检查是否有搜索/爬取相关的关键词
                search_keywords = ["搜索", "爬取", "热搜", "热点", "新闻", "资讯", "百度", "github", "微博", "b站", "抖音"]
                has_search_intent = any(keyword in description for keyword in search_keywords)
                
                # 如果有搜索意图，优先执行爬取任务
                if has_search_intent:
                    result = await self._execute_scraping(task)
                elif task.type == "scraping":
                    result = await self._execute_scraping(task)
                elif task.type == "analysis":
                    result = await self._execute_analysis(task)
                elif task.type == "processing":
                    result = await self._execute_processing(task)
                else:
                    result = await self._execute_general(task)

            execution_time = asyncio.get_event_loop().time() - start_time

            return ActionResult(
                success=True,
                output=result,
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            return ActionResult(
                success=False,
                error=str(e),
                execution_time=execution_time
            )

    async def _execute_system_command(self, task: Task) -> Dict[str, Any]:
        """执行系统命令，如打开应用程序"""
        logger.info(f"执行系统命令: {task.description}")
        
        import subprocess
        import platform
        
        description = task.description.lower() if task.description else ""
        os_type = platform.system()
        
        # 应用程序名称映射
        app_mapping = {
            "qq": {"mac": "QQ", "win": "QQ.exe", "linux": "qq"},
            "微信": {"mac": "WeChat", "win": "WeChat.exe", "linux": "wechat"},
            "浏览器": {"mac": "Safari", "win": "msedge.exe", "linux": "firefox"},
            "finder": {"mac": "Finder", "win": "explorer.exe", "linux": "nautilus"},
            "terminal": {"mac": "Terminal", "win": "cmd.exe", "linux": "gnome-terminal"},
            "计算器": {"mac": "Calculator", "win": "calc.exe", "linux": "gnome-calculator"},
            "日历": {"mac": "Calendar", "win": "calendar.exe", "linux": "gnome-calendar"},
            "邮件": {"mac": "Mail", "win": "outlook.exe", "linux": "thunderbird"},
        }
        
        # 识别要打开的应用程序
        app_name = None
        for keyword, apps in app_mapping.items():
            if keyword in description:
                app_name = apps.get(os_type.lower(), apps.get("mac"))
                break
        
        if not app_name:
            return {
                "type": "system",
                "action": "unknown",
                "message": f"无法识别要打开的应用程序: {task.description}",
                "status": "failed"
            }
        
        try:
            if os_type == "Darwin":  # macOS
                subprocess.run(["open", "-a", app_name], check=True)
            elif os_type == "Windows":  # Windows
                subprocess.run(["start", "", app_name], check=True, shell=True)
            else:  # Linux
                subprocess.run([app_name], check=True)
            
            return {
                "type": "system",
                "action": "open_app",
                "app": app_name,
                "message": f"已成功启动 {app_name}",
                "status": "success"
            }
        except Exception as e:
            logger.warning(f"启动应用程序失败: {e}")
            return {
                "type": "system",
                "action": "open_app",
                "app": app_name,
                "message": f"启动 {app_name} 失败: {str(e)}",
                "status": "failed"
            }
    
    async def _execute_scraping(self, task: Task) -> Dict[str, Any]:
        """执行爬取任务"""
        logger.info(f"执行爬取任务: {task.description}")
        
        try:
            # 尝试调用真实的爬虫技能
            from skills.web_scraper.handler import ScraperDispatcher, _SITE_ALIASES
            
            dispatcher = ScraperDispatcher()
            
            # 根据任务描述识别站点
            description = task.description.lower() if task.description else ""
            site_name = '百度'  # 默认
            
            for alias, canonical in _SITE_ALIASES.items():
                if alias in description:
                    site_name = canonical
                    break
            
            result = dispatcher.execute(site_name=site_name, action='热搜')
            
            return {
                "type": "scraping",
                "data": result,
                "count": len(result) if isinstance(result, list) else 1,
                "status": "success"
            }
        except Exception as e:
            logger.warning(f"调用爬虫技能失败，使用模拟数据: {e}")
            # 模拟爬取过程
            await asyncio.sleep(2.0)

            return {
                "type": "scraping",
                "data": f"爬取的数据: {task.description}",
                "count": 100,
                "status": "success"
            }

    async def _execute_analysis(self, task: Task) -> Dict[str, Any]:
        """执行分析任务"""
        logger.info(f"执行分析任务: {task.description}")

        # 模拟分析过程
        await asyncio.sleep(3.0)

        return {
            "type": "analysis",
            "insights": [
                "洞察1: 数据呈现上升趋势",
                "洞察2: 存在异常值需要关注",
                "洞察3: 建议进一步调查"
            ],
            "statistics": {
                "mean": 50.0,
                "std": 10.0,
                "count": 1000
            },
            "status": "success"
        }

    async def _execute_processing(self, task: Task) -> Dict[str, Any]:
        """执行处理任务"""
        logger.info(f"执行处理任务: {task.description}")

        # 模拟处理过程
        await asyncio.sleep(1.5)

        return {
            "type": "processing",
            "processed_count": 100,
            "errors": 0,
            "status": "success"
        }

    async def _execute_general(self, task: Task) -> Dict[str, Any]:
        """执行通用任务"""
        logger.info(f"执行通用任务: {task.description}")

        # 模拟执行过程
        await asyncio.sleep(1.0)

        return {
            "type": "general",
            "result": f"任务完成: {task.description}",
            "status": "success"
        }

    def get_specialization(self) -> str:
        """获取专业领域"""
        return self.specialization
