"""统一任务处理器（简化版）

合并功能：
- 规则匹配（快速）
- 复杂度判断（可选）
- AI 分解（兜底）

使用方式：
    from core.task_processor import task_processor
    result = await task_processor.process("爬取微博热搜并分析")
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from .llm_backend import get_llm_router

logger = logging.getLogger(__name__)


class TaskPath(Enum):
    """任务处理路径"""
    RULE = "rule"
    AI = "ai"


@dataclass
class SubTask:
    """子任务"""
    id: str
    action: str
    params: Dict[str, Any]
    dependencies: List[str]
    priority: int = 5  # 优先级（1-10，数字越大优先级越高）


@dataclass
class TaskResult:
    """处理结果"""
    path: TaskPath
    subtasks: List[SubTask]
    success: bool


class TaskProcessor:
    """统一任务处理器
    
    特性：
    - 规则匹配（快速）
    - AI 分解（兜底）
    """
    
    def __init__(self):
        self.router = get_llm_router()
        logger.info("TaskProcessor 初始化完成")
    
    async def process(self, task: str) -> TaskResult:
        """处理任务
        
        策略：
        1. 先规则匹配（快速）
        2. 失败则 AI 分解（兜底）
        
        Args:
            task: 用户任务
            
        Returns:
            处理结果
        """
        logger.info("处理任务: %s", task[:50])
        
        try:
            async with asyncio.timeout(10):
                # 1. 规则匹配
                rule_result = self._try_rule(task)
                if rule_result:
                    logger.info("规则匹配成功")
                    return rule_result
                
                # 2. AI 分解
                logger.info("规则失败，使用 AI")
                return await self._try_ai(task)
        except asyncio.TimeoutError:
            logger.warning("处理超时")
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "chat", {"message": task}, [])],
                success=False,
            )
    
    def _try_rule(self, task: str) -> Optional[TaskResult]:
        """规则匹配
        
        只处理简单任务，复杂任务返回 None 让 AI 处理
        """
        # 检测复杂任务（包含多个动作或逻辑连接词）
        complex_indicators = ["并", "然后", "接着", "再", "最后", "之后", "同时", "并且", "还有", "以及", "分析", "生成报告"]
        if any(ind in task for ind in complex_indicators):
            return None
        
        # 简单关键词匹配
        keywords = {
            "天气": ("weather", {"city": "北京"}),
            "微博": ("web_scraper", {"site_name": "微博", "action": "热搜"}),
            "百度": ("web_scraper", {"site_name": "百度", "action": "热搜"}),
            "翻译": ("translator", {"text": task, "target_lang": "en"}),
        }
        
        for kw, (action, params) in keywords.items():
            if kw in task:
                return TaskResult(
                    path=TaskPath.RULE,
                    subtasks=[SubTask("task_1", action, params, [])],
                    success=True,
                )
        
        return None
    
    async def _try_ai(self, task: str) -> TaskResult:
        """AI 分解"""
        try:
            prompt = f"""请将以下任务拆解为多个可执行的子任务。

任务：{task}

可用技能：
- web_scraper: 网站爬取
- data_analysis: 数据分析
- data_processing: 数据处理
- data_visualization: 数据可视化
- translator: 翻译
- weather: 天气查询

返回 JSON 格式（不要用markdown代码块）：
{{
  "subtasks": [
    {{
      "id": "task_1",
      "action": "web_scraper",
      "params": {{"site_name": "微博", "action": "热搜"}},
      "dependencies": []
    }},
    {{
      "id": "task_2",
      "action": "data_analysis",
      "params": {{"action": "分析"}},
      "dependencies": ["task_1"]
    }}
  ]
}}

注意：
1. 每个子任务都要有 id、action、params、dependencies
2. dependencies 表示依赖的前置任务ID列表
3. 只返回JSON，不要其他内容"""
            
            logger.info("调用 AI 分解: %s", task[:50])
            response = await self.router.simple_chat(
                user_message=prompt,
                system_prompt="你是任务分解助手，只返回JSON格式，不要用markdown代码块",
                temperature=0.7,
            )
            
            logger.info("AI 响应: %s", response[:200] if response else "空")
            
            if not response or not response.strip():
                raise ValueError("AI 返回空响应")
            
            # 处理可能的 markdown 代码块
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            data = json.loads(response)
            subtasks = []
            
            for st in data.get("subtasks", []):
                subtask = SubTask(
                    id=st["id"],
                    action=st["action"],
                    params=st.get("params", {}),
                    dependencies=st.get("dependencies", []),
                )
                subtasks.append(subtask)
            
            logger.info("AI 分解成功: %d 个子任务", len(subtasks))
            return TaskResult(
                path=TaskPath.AI,
                subtasks=subtasks,
                success=True,
            )
        except Exception as e:
            logger.error("AI 分解失败: %s", e)
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "chat", {"message": task}, [])],
                success=False,
            )


# 全局实例
task_processor = TaskProcessor()