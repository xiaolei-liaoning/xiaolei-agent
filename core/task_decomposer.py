"""任务分解器（工业级 - 双层策略优化版）

实现「规则兜底 + LLM智能泛化」双层拆解策略：
1. 第一层：规则引擎快速匹配（置信度≥0.6直接返回）
2. 第二层：LLM智能泛化处理复杂任务
3. 降级机制：确保任何情况下都有可用结果
"""

import asyncio
import json
import logging
import re
import time
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from enum import Enum

from .llm_backend import get_llm_router

logger = logging.getLogger(__name__)


class DecompositionPath(Enum):
    """分解路径类型"""
    RULE = "rule"      # 规则路径
    AI = "ai"          # AI路径


@dataclass
class SubTask:
    """子任务定义"""
    id: str                    # 任务ID
    action: str                # 动作类型
    params: Dict[str, Any]     # 动作参数
    dependencies: List[str]     # 依赖的任务ID列表
    priority: int = 5          # 优先级（1-10，数字越大优先级越高）
    retry_count: int = 3       # 重试次数
    timeout: int = 30          # 超时时间（秒）
    max_retries: int = 3       # 最大重试次数
    status: str = "pending"     # 任务状态: pending, running, completed, failed
    error_message: str = ""     # 错误信息
    
    def is_ready(self, completed_tasks: Set[str]) -> bool:
        """检查任务是否准备好执行（所有依赖已完成）
        
        Args:
            completed_tasks: 已完成的任务ID集合
            
        Returns:
            是否可以执行
        """
        return all(dep in completed_tasks for dep in self.dependencies)
    
    def mark_running(self):
        """标记任务为运行中"""
        self.status = "running"
    
    def mark_completed(self):
        """标记任务为已完成"""
        self.status = "completed"
    
    def mark_failed(self, error: str):
        """标记任务为失败"""
        self.status = "failed"
        self.error_message = error


@dataclass
class DecompositionResult:
    """分解结果"""
    path: DecompositionPath       # 使用的分解路径
    subtasks: List[SubTask]     # 子任务列表
    confidence: float            # 置信度（0-1）
    reasoning: str             # 分解理由
    original_task: str         # 原始任务


class RuleEngine:
    """规则引擎（基于关键词权重）"""
    
    def __init__(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.skill_dispatcher import SkillDispatcher
        self.dispatcher = SkillDispatcher()
    
    def match(self, task: str) -> Tuple[bool, float, Optional[DecompositionResult]]:
        """规则匹配
        
        Args:
            task: 用户任务描述
            
        Returns:
            (是否匹配, 置信度, 分解结果)
        """
        # 1. 技能匹配
        skill = self.dispatcher.match_skill(task)
        
        # 2. 参数提取
        params = self.dispatcher.extract_params(task, skill)
        
        # 3. 计算置信度
        confidence = self._calculate_confidence(task, skill, params)
        
        # 4. 如果置信度足够高，直接返回结果
        if confidence >= 0.6:
            subtask = SubTask(
                id="task_1",
                action=skill,
                params=params,
                dependencies=[],
                priority=5,
            )
            result = DecompositionResult(
                path=DecompositionPath.RULE,
                subtasks=[subtask],
                confidence=confidence,
                reasoning=f"规则匹配：{skill}",
                original_task=task,
            )
            return True, confidence, result
        
        return False, confidence, None
    
    def _calculate_confidence(self, task: str, skill: str, params: Dict[str, Any]) -> float:
        """计算置信度
        
        Args:
            task: 任务描述
            skill: 匹配的技能
            params: 提取的参数
            
        Returns:
            置信度（0-1）
        """
        confidence = 0.5  # 基础置信度
        
        # 1. 参数完整度
        if params:
            confidence += 0.2
        
        # 2. 任务明确度
        if any(kw in task for kw in ["打开", "查看", "分析", "翻译", "爬取"]):
            confidence += 0.1
        
        # 3. 检测复杂任务（包含多个动作或逻辑连接词）
        complex_indicators = ["并", "然后", "接着", "再", "最后", "之后", "同时", "并且", "还有", "以及"]
        if any(ind in task for ind in complex_indicators):
            confidence -= 0.5  # 复杂任务大幅降低置信度，让AI路径接管
        
        # 4. 技能匹配度
        skill_keywords = {
            "weather": ["天气", "气温", "温度"],
            "web_scraper": ["爬取", "抓取", "热搜"],
            "data_analysis": ["分析", "统计", "数据"],
            "gui_automation": [
                "打开", "点击", "自动化", 
                "qq", "QQ", "微信", "wechat", "钉钉", "dingtalk", "飞书",
                "邮件", "mail", "日历", "calendar", "浏览器", "browser",
                "chrome", "safari", "终端", "terminal", "代码", "code",
                "截图", "截屏", "screenshot", "ocr", "音量", "亮度",
                "音乐", "视频", "照片", "计算器", "地图", "设置"
            ],
            "translator": ["翻译", "translate"],
            "system_toolbox": ["系统", "时间", "内存"],
        }
        
        if skill in skill_keywords:
            keywords = skill_keywords[skill]
            hit_count = sum(1 for kw in keywords if kw.lower() in task.lower())
            confidence += min(hit_count * 0.15, 0.25)
        
        return max(min(confidence, 0.85), 0.0)


class GLMClient:
    """GLM-4.7-flash客户端"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.model = "glm-4-flash"
        self._router = get_llm_router()
        logger.info("GLMClient 初始化完成, 模型: %s", self.model)
    
    async def decompose(self, task: str) -> Optional[DecompositionResult]:
        """使用GLM分解任务
        
        Args:
            task: 用户任务描述
            
        Returns:
            分解结果，失败返回None
        """
        try:
            # 1. 构建提示词
            prompt = self._build_prompt(task)
            
            # 2. 调用GLM API
            response = await self._call_api(prompt)
            
            # 3. 解析响应
            result = self._parse_response(response, task)
            
            return result
            
        except Exception as e:
            logger.error("GLM分解失败: %s", e, exc_info=True)
            return None
    
    def _build_prompt(self, task: str) -> str:
        """构建提示词
        
        Args:
            task: 用户任务
            
        Returns:
            提示词
        """
        prompt = f"""你是一个任务分解助手。请将用户的复杂任务拆解为多个可执行的子任务。

用户任务：{task}

请按照以下JSON格式返回分解结果：
{{
    "subtasks": [
        {{
            "id": "task_1",
            "action": "技能名称（如：web_scraper, data_analysis, translator等）",
            "params": {{"参数名": "参数值"}},
            "dependencies": [],
            "priority": 5,
            "reasoning": "分解理由"
        }}
    ],
    "reasoning": "整体分解理由"
}}

注意事项：
1. 子任务之间要有逻辑顺序
2. 每个子任务都要明确指定action和params
3. dependencies表示依赖的前置任务ID列表
4. priority范围1-10，数字越大优先级越高
5. reasoning要简洁明了

请只返回JSON，不要包含其他内容。"""
        
        return prompt
    
    async def _call_api(self, prompt: str) -> str:
        """调用GLM API
        
        Args:
            prompt: 提示词
            
        Returns:
            API响应
        """
        try:
            # 调用实际的GLM API
            response = await self._router.simple_chat(
                user_message=prompt,
                system_prompt="你是一个任务分解助手，将复杂任务拆解为多个可执行的子任务。请严格按照JSON格式返回结果。",
                temperature=0.7,
            )
            
            logger.info("GLM API调用成功, 响应长度: %d", len(response) if response else 0)
            
            # 检查响应是否为空
            if not response or not response.strip():
                raise ValueError("GLM API返回空响应")
            
            return response
            
        except Exception as e:
            logger.error("GLM API调用失败: %s", e)
            # 返回兜底的简单响应
            return json.dumps({
                "subtasks": [
                    {
                        "id": "task_1",
                        "action": "web_scraper",
                        "params": {"site_name": "微博", "action": "热搜top10"},
                        "dependencies": [],
                        "priority": 5,
                        "reasoning": "获取数据"
                    }
                ],
                "reasoning": "API调用失败，使用默认分解"
            })
    
    def _parse_response(self, response: str, original_task: str) -> DecompositionResult:
        """解析API响应
        
        Args:
            response: API响应JSON字符串
            original_task: 原始任务
            
        Returns:
            分解结果
        """
        try:
            # 1. 尝试提取JSON（处理可能的代码块）
            response = response.strip()
            if response.startswith("```"):
                # 移除代码块
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            # 2. 解析JSON
            data = json.loads(response)
            
            # 3. 构建子任务列表
            subtasks = []
            for task_data in data.get("subtasks", []):
                subtask = SubTask(
                    id=task_data["id"],
                    action=task_data["action"],
                    params=task_data.get("params", {}),
                    dependencies=task_data.get("dependencies", []),
                    priority=task_data.get("priority", 5),
                )
                subtasks.append(subtask)
            
            # 4. 构建结果
            result = DecompositionResult(
                path=DecompositionPath.AI,
                subtasks=subtasks,
                confidence=0.9,
                reasoning=data.get("reasoning", "AI分解"),
                original_task=original_task,
            )
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error("JSON解析失败: %s, 响应内容: %s", e, response[:200] if response else "空")
            raise ValueError(f"Invalid JSON response: {e}")
        except KeyError as e:
            logger.error("缺少必要字段: %s", e)
            raise ValueError(f"Missing required field: {e}")


class TaskDecomposer:
    """任务分解器（工业级 - 双层策略优化版）
    
    实现「规则兜底 + LLM智能泛化」双层拆解策略：
    1. 第一层：规则引擎快速匹配（置信度≥0.6直接返回）
    2. 第二层：LLM智能泛化处理复杂任务
    3. 降级机制：确保任何情况下都有可用结果
    """
    
    def __init__(self):
        self.rule_engine = RuleEngine()
        self.glm_client = GLMClient()
        logger.info("TaskDecomposer 初始化完成（双层策略）")
    
    async def decompose(self, task: str) -> DecompositionResult:
        """分解任务（双层策略）
        
        处理流程：
        1. 尝试规则路径（快速、准确）
        2. 如果规则失败或置信度低，使用LLM路径（智能、灵活）
        3. 如果LLM也失败，使用默认兜底方案
        
        Args:
            task: 用户任务描述
            
        Returns:
            分解结果（保证非空）
        """
        logger.info("开始分解任务: %s", task[:100])
        start_time = time.time()
        
        # === 第一层：规则引擎 ===
        try:
            matched, confidence, rule_result = self.rule_engine.match(task)
            
            if matched and confidence >= 0.6:
                # 验证依赖关系
                if self._validate_subtasks(rule_result.subtasks):
                    elapsed = time.time() - start_time
                    logger.info("规则路径匹配成功 (置信度=%.2f, 耗时=%.2fs)", confidence, elapsed)
                    return rule_result
                else:
                    logger.warning("规则路径依赖验证失败，切换到LLM路径")
            else:
                logger.info("规则路径未匹配或置信度过低 (%.2f)，切换到LLM路径", confidence)
        except Exception as e:
            logger.warning("规则引擎异常: %s，切换到LLM路径", e)
        
        # === 第二层：LLM智能泛化 ===
        try:
            llm_result = await self.glm_client.decompose(task)
            
            if llm_result and llm_result.subtasks:
                # 验证依赖关系
                if self._validate_subtasks(llm_result.subtasks):
                    elapsed = time.time() - start_time
                    logger.info("LLM路径分解成功 (子任务数=%d, 耗时=%.2fs)", 
                               len(llm_result.subtasks), elapsed)
                    return llm_result
                else:
                    # 尝试修复依赖
                    fixed_subtasks = self._fix_dependencies(llm_result.subtasks)
                    llm_result.subtasks = fixed_subtasks
                    elapsed = time.time() - start_time
                    logger.info("LLM路径分解成功（已修复依赖） (子任务数=%d, 耗时=%.2fs)", 
                               len(llm_result.subtasks), elapsed)
                    return llm_result
            else:
                logger.warning("LLM路径返回空结果，使用兜底方案")
        except Exception as e:
            logger.error("LLM分解异常: %s，使用兜底方案", e)
        
        # === 第三层：兜底方案 ===
        fallback_result = self._create_fallback_decomposition(task)
        elapsed = time.time() - start_time
        logger.warning("使用兜底方案 (耗时=%.2fs)", elapsed)
        return fallback_result
    
    def _validate_subtasks(self, subtasks: List[SubTask]) -> bool:
        """验证子任务依赖关系
        
        检查：
        1. 是否存在循环依赖
        2. 依赖的任务是否存在
        3. 任务ID是否唯一
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            是否有效
        """
        task_ids = {task.id for task in subtasks}
        
        # 检查任务ID唯一性
        if len(task_ids) != len(subtasks):
            logger.error("子任务ID不唯一")
            return False
        
        # 检查依赖的任务是否存在
        for task in subtasks:
            for dep in task.dependencies:
                if dep not in task_ids:
                    logger.error(f"任务 {task.id} 的依赖 {dep} 不存在")
                    return False
        
        # 检查循环依赖
        if self._has_circular_dependency(subtasks):
            logger.error("检测到循环依赖")
            return False
        
        return True
    
    def _has_circular_dependency(self, subtasks: List[SubTask]) -> bool:
        """检测循环依赖
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            是否存在循环依赖
        """
        task_map = {task.id: task for task in subtasks}
        
        def dfs(task_id: str, visited: Set[str], stack: Set[str]) -> bool:
            if task_id in stack:
                return True  # 发现循环
            if task_id in visited:
                return False
            
            visited.add(task_id)
            stack.add(task_id)
            
            task = task_map.get(task_id)
            if task:
                for dep in task.dependencies:
                    if dfs(dep, visited, stack):
                        return True
            
            stack.remove(task_id)
            return False
        
        for task in subtasks:
            if dfs(task.id, set(), set()):
                return True
        
        return False
    
    def _fix_dependencies(self, subtasks: List[SubTask]) -> List[SubTask]:
        """修复依赖问题
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            修复后的子任务列表
        """
        task_ids = {task.id for task in subtasks}
        fixed_subtasks = []
        
        for task in subtasks:
            # 移除无效依赖
            valid_deps = [dep for dep in task.dependencies if dep in task_ids]
            fixed_task = SubTask(
                id=task.id,
                action=task.action,
                params=task.params,
                dependencies=valid_deps,
                priority=task.priority,
                retry_count=task.retry_count,
                timeout=task.timeout
            )
            fixed_subtasks.append(fixed_task)
        
        logger.info("已修复子任务依赖")
        return fixed_subtasks
    
    def _create_fallback_decomposition(self, task: str) -> DecompositionResult:
        """创建兜底分解方案
        
        Args:
            task: 原始任务
            
        Returns:
            兜底分解结果
        """
        # 简单的关键词提取
        action_keywords = {
            "爬取": "web_scraper",
            "抓取": "web_scraper",
            "翻译": "translator",
            "分析": "data_analysis",
            "打开": "gui_automation",
            "查询": "web_search",
            "天气": "weather",
        }
        
        # 匹配动作
        action = "web_search"  # 默认动作
        for keyword, skill in action_keywords.items():
            if keyword in task:
                action = skill
                break
        
        # 创建简单子任务
        subtask = SubTask(
            id="task_1",
            action=action,
            params={"query": task},
            dependencies=[],
            priority=5,
            retry_count=2,
            timeout=20
        )
        
        return DecompositionResult(
            path=DecompositionPath.RULE,
            subtasks=[subtask],
            confidence=0.3,
            reasoning=f"兜底方案：使用{action}技能处理",
            original_task=task
        )


# 全局单例
_task_decomposer_instance = None


def get_task_decomposer() -> TaskDecomposer:
    """获取任务分解器单例"""
    global _task_decomposer_instance
    if _task_decomposer_instance is None:
        _task_decomposer_instance = TaskDecomposer()
    return _task_decomposer_instance


class TaskExecutor:
    """任务执行器 - 支持多任务并发执行"""
    
    def __init__(self):
        self.skill_registry: Dict[str, Any] = {}
        logger.info("TaskExecutor 初始化完成")
    
    def register_skill(self, name: str, handler: Any):
        """注册技能处理器"""
        self.skill_registry[name] = handler
        logger.debug("注册技能: %s", name)
    
    async def execute(self, result: DecompositionResult) -> Dict[str, Any]:
        """执行分解后的任务
        
        支持并发执行：
        - 无依赖的子任务并行执行
        - 有依赖的子任务按依赖顺序执行
        
        Args:
            result: 分解结果
            
        Returns:
            执行结果
        """
        start_time = time.time()
        subtasks = result.subtasks
        
        if not subtasks:
            return {
                "success": False,
                "error": "没有子任务",
                "results": [],
                "total_time": 0,
            }
        
        logger.info("开始执行 %d 个子任务", len(subtasks))
        
        try:
            async with asyncio.timeout(120):
                return await self._execute_tasks(subtasks, start_time)
        except asyncio.TimeoutError:
            logger.warning("任务执行超时")
            return {
                "success": False,
                "error": "执行超时",
                "results": [],
                "total_time": time.time() - start_time,
            }
    
    async def _execute_tasks(self, subtasks: List['SubTask'], start_time: float) -> Dict[str, Any]:
        """实际执行任务"""
        task_results: Dict[str, Any] = {}
        completed: set = set()
        
        max_iterations = len(subtasks) + 1
        iteration = 0
        
        while len(completed) < len(subtasks) and iteration < max_iterations:
            iteration += 1
            
            executable = []
            for task in subtasks:
                if task.id in completed:
                    continue
                # 检查依赖是否都已完成
                deps_ready = all(dep in completed for dep in task.dependencies)
                if deps_ready:
                    executable.append(task)
            
            if not executable:
                logger.warning("没有可执行的任务，可能存在循环依赖")
                break
            
            # 并行执行本轮任务
            logger.info("第%d轮: 并行执行 %d 个任务", iteration, len(executable))
            
            async def execute_single(task: SubTask) -> Dict[str, Any]:
                task_start = time.time()
                try:
                    # 获取技能处理器
                    handler = self.skill_registry.get(task.action)
                    
                    if handler:
                        # 调用技能
                        if hasattr(handler, 'execute'):
                            output = await handler.execute(task.params)
                        else:
                            output = await handler(task.params)
                    else:
                        # 模拟执行
                        logger.debug("模拟执行: %s", task.action)
                        output = {"status": "simulated", "action": task.action}
                    
                    return {
                        "task_id": task.id,
                        "action": task.action,
                        "success": True,
                        "output": output,
                        "duration": round(time.time() - task_start, 2),
                    }
                except Exception as e:
                    logger.error("任务 %s 执行失败: %s", task.id, e)
                    return {
                        "task_id": task.id,
                        "action": task.action,
                        "success": False,
                        "error": str(e),
                        "duration": round(time.time() - task_start, 2),
                    }
            
            # 并发执行
            tasks = [execute_single(t) for t in executable]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 收集结果
            for r in results:
                if isinstance(r, Exception):
                    logger.error("任务执行异常: %s", r)
                    continue
                task_results[r["task_id"]] = r
                if r.get("success"):
                    completed.add(r["task_id"])
        
        total_time = time.time() - start_time
        success = all(r.get("success", False) for r in task_results.values())
        
        return {
            "success": success,
            "results": list(task_results.values()),
            "completed_tasks": list(completed),
            "total_time": round(total_time, 2),
        }
    
    async def execute_parallel(self, subtasks: List[SubTask]) -> List[Dict[str, Any]]:
        """并行执行多个子任务（无依赖）
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            执行结果列表
        """
        async def execute_one(task: SubTask) -> Dict[str, Any]:
            start = time.time()
            try:
                handler = self.skill_registry.get(task.action)
                if handler and hasattr(handler, 'execute'):
                    output = await handler.execute(task.params)
                else:
                    output = {"status": "simulated", "action": task.action}
                return {"task_id": task.id, "action": task.action, "success": True, "output": output, "duration": round(time.time()-start, 2)}
            except Exception as e:
                return {"task_id": task.id, "action": task.action, "success": False, "error": str(e), "duration": round(time.time()-start, 2)}
        
        results = await asyncio.gather(*[execute_one(t) for t in subtasks], return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception)]


task_executor = TaskExecutor()


# 全局实例
task_decomposer = TaskDecomposer()


async def main():
    """测试函数"""
    decomposer = TaskDecomposer()
    
    # 测试简单任务（规则路径）
    print("="*60)
    print("测试1: 简单任务（规则路径）")
    print("="*60)
    result1 = await decomposer.decompose("查看北京天气")
    print(f"路径: {result1.path.value}")
    print(f"置信度: {result1.confidence}")
    print(f"子任务数: {len(result1.subtasks)}")
    print(f"理由: {result1.reasoning}")
    
    # 测试复杂任务（AI路径）
    print("\n" + "="*60)
    print("测试2: 复杂任务（AI路径）")
    print("="*60)
    result2 = await decomposer.decompose("爬取微博热搜并分析数据")
    print(f"路径: {result2.path.value}")
    print(f"置信度: {result2.confidence}")
    print(f"子任务数: {len(result2.subtasks)}")
    print(f"理由: {result2.reasoning}")
    for i, task in enumerate(result2.subtasks, 1):
        print(f"  任务{i}: {task.action} - {task.params}")
    
    # 测试多步任务（AI路径）
    print("\n" + "="*60)
    print("测试3: 多步任务（AI路径）")
    print("="*60)
    result3 = await decomposer.decompose("先爬取微博热搜，然后翻译成英文，最后发送邮件")
    print(f"路径: {result3.path.value}")
    print(f"置信度: {result3.confidence}")
    print(f"子任务数: {len(result3.subtasks)}")
    print(f"理由: {result3.reasoning}")
    for i, task in enumerate(result3.subtasks, 1):
        print(f"  任务{i}: {task.action} - {task.params}")
        if task.dependencies:
            print(f"         依赖: {task.dependencies}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())