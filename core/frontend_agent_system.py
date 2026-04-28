"""前端Agent系统

架构：【前端Agent + 任务处理中心 + 独立线程池 + 状态监管】

特点：
- 保留前端Agent概念，如"小龙虾助手"、"女神"等
- 移除后端Agent，统一由任务处理中心处理
- 为每个前端Agent分配独立线程池
- 实现状态监管系统，监控Agent和任务状态
"""

import asyncio
import logging
import os
import importlib
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional
import uuid

logger = logging.getLogger(__name__)


class FrontendAgent:
    """前端Agent类"""
    
    def __init__(self, agent_id: str, name: str, avatar: str, max_workers: int = 5):
        self.agent_id = agent_id
        self.name = name
        self.avatar = avatar
        self.messages = []
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks = {}
        self.status = "idle"  # idle, busy, error
        
        logger.info(f"前端Agent初始化完成: {name} (ID: {agent_id}, max_workers: {max_workers})")
    
    def add_message(self, message: dict):
        """添加消息"""
        self.messages.append(message)
    
    def submit_task(self, task_type: str, params: dict) -> str:
        """提交任务"""
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "id": task_id,
            "type": task_type,
            "params": params,
            "status": "pending",
            "result": None
        }
        self.status = "busy"
        logger.info(f"前端Agent {self.name} 任务已提交: {task_id} (type: {task_type})")
        return task_id
    
    def get_task_status(self, task_id: str) -> dict:
        """获取任务状态"""
        return self.tasks.get(task_id)
    
    def get_status(self) -> str:
        """获取Agent状态"""
        return self.status
    
    def update_status(self, status: str):
        """更新Agent状态"""
        self.status = status
    
    def get_info(self) -> dict:
        """获取Agent信息"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "avatar": self.avatar,
            "status": self.status,
            "message_count": len(self.messages),
            "task_count": len(self.tasks),
            "active_tasks": sum(1 for task in self.tasks.values() if task["status"] in ["pending", "running"])
        }


class TaskProcessingCenter:
    """任务处理中心"""
    
    def __init__(self):
        self.agents = {}
        self._character_skills = {}
        self._load_character_skills()
        
        logger.info("任务处理中心初始化完成")
    
    def register_agent(self, agent: FrontendAgent):
        """注册前端Agent"""
        self.agents[agent.agent_id] = agent
        logger.info(f"前端Agent已注册: {agent.name} (ID: {agent.agent_id})")
    
    def unregister_agent(self, agent_id: str):
        """注销前端Agent"""
        if agent_id in self.agents:
            agent = self.agents.pop(agent_id)
            logger.info(f"前端Agent已注销: {agent.name} (ID: {agent_id})")
    
    def submit_task(self, agent_id: str, task_type: str, params: dict) -> str:
        """提交任务"""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        agent = self.agents[agent_id]
        return agent.submit_task(task_type, params)
    
    async def process_task(self, agent_id: str, task_id: str):
        """处理任务"""
        agent = self.agents.get(agent_id)
        if not agent:
            logger.error(f"Agent {agent_id} not found")
            return
        
        task = agent.get_task_status(task_id)
        if not task:
            logger.error(f"Task {task_id} not found for Agent {agent_id}")
            return
        
        # 更新任务状态为运行中
        task["status"] = "running"
        
        try:
            # 根据任务类型处理
            if task["type"] in self._character_skills:
                # 处理人物Skill任务
                result = await self._process_character_task(task["type"], task["params"])
            elif task["type"] == "website":
                # 爬取网站
                result = await self._process_website_task(task["params"])
            elif task["type"] == "summarize":
                # 总结文本
                result = await self._process_summarize_task(task["params"])
            elif task["type"] == "check":
                # 检查任务
                result = await self._process_check_task(task["params"])
            elif task["type"] == "search":
                # 搜索任务
                result = await self._process_search_task(task["params"])
            elif task["type"] == "system":
                # 系统任务
                result = await self._process_system_task(task["params"])
            elif task["type"] == "chat":
                # 聊天任务
                result = await self._process_chat_task(task["params"])
            else:
                # 默认处理
                result = {"error": f"Unknown task type: {task['type']}"}
            
            # 更新任务状态
            task["status"] = "completed"
            task["result"] = result
            agent.update_status("idle")
            
            logger.info(f"任务处理完成: {task_id} (type: {task['type']})")
            
        except Exception as e:
            # 更新任务状态为失败
            task["status"] = "failed"
            task["result"] = {"error": str(e)}
            agent.update_status("idle")
            
            logger.error(f"任务处理失败: {task_id} - {e}")
    
    def _load_character_skills(self):
        """加载人物Skill"""
        character_skills = {}
        # 正确计算路径，包含'小雷版小龙虾agent'目录
        current_dir = os.path.dirname(__file__)
        parent_dir = os.path.dirname(current_dir)
        skills_dir = os.path.join(parent_dir, "skills", "人物")
        
        logger.info(f"当前目录: {current_dir}")
        logger.info(f"父目录: {parent_dir}")
        logger.info(f"开始加载人物Skill，目录: {skills_dir}")
        logger.info(f"目录是否存在: {os.path.exists(skills_dir)}")
        
        if os.path.exists(skills_dir):
            logger.info(f"人物Skill目录存在: {skills_dir}")
            try:
                logger.info(f"目录内容: {os.listdir(skills_dir)}")
            except Exception as e:
                logger.error(f"读取目录内容失败: {e}")
            
            # 添加当前工作目录到Python路径，以便能够正确导入skills模块
            import sys
            sys.path.insert(0, parent_dir)
            logger.info(f"Python路径: {sys.path[:5]}")
            
            for character in os.listdir(skills_dir):
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
        
        self._character_skills = character_skills
        logger.info(f"人物Skill加载完成，共加载 {len(character_skills)} 个技能: {list(character_skills.keys())}")
    
    async def _process_character_task(self, character_id: str, params: dict) -> dict:
        """处理人物Skill任务"""
        if character_id in self._character_skills:
            handler = self._character_skills[character_id]
            try:
                result = await handler.execute(**params)
                logger.info(f"人物Skill执行成功: {character_id}")
                return {"status": "success", "result": result}
            except Exception as e:
                logger.error(f"人物Skill执行失败: {character_id} - {e}")
                raise
        else:
            raise ValueError(f"未知的人物Skill: {character_id}")
    
    async def _process_website_task(self, params: dict) -> dict:
        """处理网站爬取任务"""
        url = params.get("url")
        logger.info(f"爬取网站: {url}")
        # 模拟爬取
        await asyncio.sleep(2)
        return {"status": "success", "url": url, "content": "爬取的内容"}
    
    async def _process_summarize_task(self, params: dict) -> dict:
        """处理文本总结任务"""
        text = params.get("text")
        logger.info(f"总结文本: {text[:50]}...")
        # 模拟总结
        await asyncio.sleep(1)
        return {"status": "success", "summary": "这是一个文本总结"}
    
    async def _process_check_task(self, params: dict) -> dict:
        """处理检查任务"""
        url = params.get("url")
        if url:
            logger.info(f"检查网站: {url}")
            # 模拟检查
            await asyncio.sleep(1)
            return {"status": "success", "url": url, "checked": True}
        else:
            logger.info("检查系统状态")
            # 模拟检查
            await asyncio.sleep(0.5)
            return {"status": "success", "system": "healthy"}
    
    async def _process_search_task(self, params: dict) -> dict:
        """处理搜索任务"""
        query = params.get("query")
        logger.info(f"搜索: {query}")
        # 模拟搜索
        await asyncio.sleep(1)
        return {"status": "success", "query": query, "results": ["结果1", "结果2"]}
    
    async def _process_system_task(self, params: dict) -> dict:
        """处理系统任务"""
        logger.info("处理系统任务")
        # 模拟处理
        await asyncio.sleep(0.5)
        return {"status": "success", "system": "healthy"}
    
    async def _process_chat_task(self, params: dict) -> dict:
        """处理聊天任务"""
        message = params.get("message")
        logger.info(f"处理聊天任务: {message[:50]}...")
        # 模拟聊天处理
        await asyncio.sleep(1)
        return {"status": "success", "reply": f"你好！我是前端Agent，收到了你的消息：{message}"}
    
    def get_agent_info(self, agent_id: str) -> dict:
        """获取Agent信息"""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": "Agent not found"}
        return agent.get_info()
    
    def get_all_agents_info(self) -> dict:
        """获取所有Agent信息"""
        info = {}
        for agent_id, agent in self.agents.items():
            info[agent_id] = agent.get_info()
        return info
    
    def get_agent_tasks(self, agent_id: str) -> list:
        """获取Agent的任务列表"""
        agent = self.agents.get(agent_id)
        if not agent:
            return []
        return list(agent.tasks.values())
    
    def get_all_tasks(self) -> dict:
        """获取所有任务"""
        all_tasks = {}
        for agent_id, agent in self.agents.items():
            all_tasks[agent_id] = list(agent.tasks.values())
        return all_tasks


class AgentMonitor:
    """Agent监管系统"""
    
    def __init__(self, processing_center: TaskProcessingCenter):
        self.processing_center = processing_center
        self._monitoring = False
        
        logger.info("Agent监管系统初始化完成")
    
    def start_monitoring(self):
        """开始监控"""
        self._monitoring = True
        logger.info("Agent监管系统开始监控")
    
    def stop_monitoring(self):
        """停止监控"""
        self._monitoring = False
        logger.info("Agent监管系统停止监控")
    
    def get_agent_status(self, agent_id: str) -> dict:
        """获取Agent状态"""
        return self.processing_center.get_agent_info(agent_id)
    
    def get_all_agents_status(self) -> dict:
        """获取所有Agent状态"""
        return self.processing_center.get_all_agents_info()
    
    def get_agent_tasks(self, agent_id: str) -> list:
        """获取Agent的任务列表"""
        return self.processing_center.get_agent_tasks(agent_id)
    
    def get_all_tasks(self) -> dict:
        """获取所有任务"""
        return self.processing_center.get_all_tasks()
    
    def monitor_system(self):
        """监控系统状态"""
        if not self._monitoring:
            return
        
        # 实现系统监控逻辑
        all_agents = self.get_all_agents_status()
        all_tasks = self.get_all_tasks()
        
        # 统计信息
        total_agents = len(all_agents)
        active_agents = sum(1 for agent in all_agents.values() if agent.get("status") == "busy")
        total_tasks = sum(len(tasks) for tasks in all_tasks.values())
        active_tasks = sum(1 for tasks in all_tasks.values() for task in tasks if task["status"] in ["pending", "running"])
        
        logger.info(f"系统监控: 总Agent数: {total_agents}, 活跃Agent数: {active_agents}, 总任务数: {total_tasks}, 活跃任务数: {active_tasks}")


# 全局实例
frontend_agent_system = TaskProcessingCenter()
agent_monitor = AgentMonitor(frontend_agent_system)