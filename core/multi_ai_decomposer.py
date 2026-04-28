"""多 AI 并发任务分解器

通过并发调用多个 AI 来：
1. 解决卡顿问题（并行处理）
2. 提高任务拆解准确性（多模型投票）
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .llm_backend import get_llm_router

logger = logging.getLogger(__name__)


class DecompositionPath(Enum):
    """分解路径类型"""
    RULE = "rule"
    AI = "ai"
    MULTI_AI = "multi_ai"  # 多 AI 并发


@dataclass
class SubTask:
    """子任务定义"""
    id: str
    action: str
    params: Dict[str, Any]
    dependencies: List[str]
    priority: int = 5
    retry_count: int = 3
    timeout: int = 30


@dataclass
class DecompositionResult:
    """分解结果"""
    path: DecompositionPath
    subtasks: List[SubTask]
    confidence: float
    reasoning: str
    original_task: str


class MultiAIDecomposer:
    """多 AI 并发任务分解器"""
    
    def __init__(self):
        self.router = get_llm_router()
        self.models = ["glm-4-flash", "glm-4-air"]
        logger.info("MultiAIDecomposer 初始化完成")
    
    async def decompose(self, task: str) -> DecompositionResult:
        """使用多个 AI 并发分解任务
        
        策略：
        1. 先尝试规则匹配（快速）
        2. 规则失败，并发调用多个 AI
        3. 投票选择最佳结果
        
        Args:
            task: 用户任务
            
        Returns:
            分解结果
        """
        logger.info("开始多 AI 分解: %s", task[:50])
        
        # 1. 先尝试规则匹配
        rule_result = self._try_rule_match(task)
        if rule_result:
            logger.info("规则匹配成功")
            return rule_result
        
        # 2. 并发调用多个 AI
        logger.info("规则匹配失败，并发调用 %d 个 AI", len(self.models))
        results = await self._call_multiple_ais(task)
        
        # 3. 投票选择最佳结果
        best_result = self._vote_best_result(results, task)
        
        return best_result
    
    def _try_rule_match(self, task: str) -> Optional[DecompositionResult]:
        """尝试规则匹配"""
        # 这里可以集成规则引擎
        return None
    
    async def _call_multiple_ais(self, task: str) -> List[Dict[str, Any]]:
        """并发调用多个 AI
        
        Returns:
            多个 AI 的返回结果
        """
        tasks = []
        for model in self.models:
            ai_task = self._call_single_ai(task, model)
            tasks.append(ai_task)
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤异常
        valid_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning("AI %s 调用失败: %s", self.models[i], r)
            else:
                valid_results.append(r)
        
        logger.info("成功获取 %d/%d 个 AI 结果", len(valid_results), len(self.models))
        return valid_results
    
    async def _call_single_ai(self, task: str, model: str) -> Dict[str, Any]:
        """调用单个 AI
        
        Args:
            task: 任务描述
            model: 模型名称
            
        Returns:
            AI 返回结果
        """
        prompt = self._build_prompt(task)
        
        try:
            # 使用 asyncio.to_thread 避免阻塞
            response = await asyncio.to_thread(
                self._sync_call_api,
                prompt,
                model
            )
            
            return {
                "model": model,
                "response": response,
                "success": True
            }
        except Exception as e:
            logger.error("AI %s 调用异常: %s", model, e)
            return {
                "model": model,
                "response": None,
                "success": False,
                "error": str(e)
            }
    
    def _sync_call_api(self, prompt: str, model: str) -> str:
        """同步调用 API（在线程池中执行）"""
        # 这里调用实际的 API
        # 暂时返回模拟数据
        return '{"subtasks": [{"id": "task_1", "action": "web_scraper", "params": {}, "dependencies": []}], "reasoning": "模拟响应"}'
    
    def _build_prompt(self, task: str) -> str:
        """构建提示词"""
        return f"""请将以下任务拆解为子任务：{task}

返回 JSON 格式：{{"subtasks": [...], "reasoning": "..."}}"""
    
    def _vote_best_result(self, results: List[Dict[str, Any]], task: str) -> DecompositionResult:
        """投票选择最佳结果
        
        策略：
        1. 选择子任务数最多的结果
        2. 选择置信度最高的结果
        3. 默认选择第一个成功的结果
        """
        if not results:
            # 所有 AI 都失败，返回默认分解
            return self._default_result(task)
        
        # 解析所有结果
        parsed_results = []
        for result in results:
            try:
                import json
                data = json.loads(result["response"])
                subtask_count = len(data.get("subtasks", []))
                parsed_results.append({
                    "model": result["model"],
                    "response": result["response"],
                    "subtask_count": subtask_count,
                    "data": data
                })
            except Exception as e:
                logger.warning("解析结果失败: %s", e)
                continue
        
        if not parsed_results:
            return self._default_result(task)
        
        # 选择子任务数最多的结果
        best_result = max(parsed_results, key=lambda x: x["subtask_count"])
        logger.info("选择 %s 的结果，子任务数: %d", best_result["model"], best_result["subtask_count"])
        
        # 解析并返回
        return self._parse_result(best_result["response"], task)
    
    def _parse_result(self, response: str, task: str) -> DecompositionResult:
        """解析 AI 返回结果"""
        import json
        
        try:
            data = json.loads(response)
            subtasks = []
            
            for st in data.get("subtasks", []):
                subtask = SubTask(
                    id=st["id"],
                    action=st["action"],
                    params=st.get("params", {}),
                    dependencies=st.get("dependencies", []),
                    priority=st.get("priority", 5),
                )
                subtasks.append(subtask)
            
            return DecompositionResult(
                path=DecompositionPath.MULTI_AI,
                subtasks=subtasks,
                confidence=0.9,
                reasoning=data.get("reasoning", "多 AI 分解"),
                original_task=task,
            )
        except Exception as e:
            logger.error("解析失败: %s", e)
            return self._default_result(task)
    
    def _default_result(self, task: str) -> DecompositionResult:
        """默认结果"""
        return DecompositionResult(
            path=DecompositionPath.RULE,
            subtasks=[SubTask(
                id="task_1",
                action="chat",
                params={"message": task},
                dependencies=[],
            )],
            confidence=0.3,
            reasoning="默认分解",
            original_task=task,
        )


# 全局实例
multi_ai_decomposer = MultiAIDecomposer()