"""动态任务拆解策略 - 自适应任务分解

核心功能：
- 任务复杂度感知拆解
- 历史数据驱动的策略选择
- 自适应拆解深度
- 性能监控和反馈
- 策略学习和优化

优势：
- 更精准的任务拆解
- 动态调整拆解策略
- 提升任务完成率
- 优化资源利用
"""

import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
from collections import defaultdict

logger = logging.getLogger(__name__)


class DecompositionStrategy(Enum):
    """拆解策略类型"""
    RULE_BASED = "rule_based"       # 基于规则的拆解
    LLM_INTELLIGENT = "llm_intelligent"  # LLM智能拆解
    HYBRID = "hybrid"                # 混合策略
    DEEP_ANALYSIS = "deep_analysis"  # 深度分析
    FAST_PATH = "fast_path"          # 快速路径


class TaskCategory(Enum):
    """任务类别"""
    SIMPLE_QUERY = "simple_query"       # 简单查询
    DATA_RETRIEVAL = "data_retrieval"   # 数据检索
    CONTENT_ANALYSIS = "content_analysis"  # 内容分析
    COMPLEX_WORKFLOW = "complex_workflow"  # 复杂工作流
    MULTI_STEP = "multi_step"           # 多步骤任务
    UNKNOWN = "unknown"                 # 未知类别


@dataclass
class TaskCharacteristics:
    """任务特征"""
    task_description: str
    category: TaskCategory
    complexity_score: float  # 复杂度分数 (0-1)
    estimated_steps: int     # 预估步骤数
    estimated_duration: float  # 预估耗时（秒）
    resource_intensity: float  # 资源强度 (0-1)
    confidence: float = 0.0    # 特征识别置信度


@dataclass
class StrategyPerformance:
    """策略性能指标"""
    strategy: DecompositionStrategy
    success_rate: float = 1.0        # 成功率
    avg_execution_time: float = 0.0  # 平均执行时间
    avg_quality_score: float = 0.0   # 平均质量分数
    total_executions: int = 0        # 总执行次数
    last_execution_time: float = 0.0  # 最后执行时间
    
    def update(self, success: bool, execution_time: float, quality_score: float):
        """更新性能指标"""
        self.total_executions += 1
        
        # 更新成功率
        if success:
            success_count = self.success_rate * (self.total_executions - 1)
            self.success_rate = (success_count + 1) / self.total_executions
        else:
            success_count = self.success_rate * (self.total_executions - 1)
            self.success_rate = success_count / self.total_executions
        
        # 更新平均执行时间
        if self.avg_execution_time > 0:
            self.avg_execution_time = (
                self.avg_execution_time * 0.9 + execution_time * 0.1
            )
        else:
            self.avg_execution_time = execution_time
        
        # 更新平均质量分数
        if self.avg_quality_score > 0:
            self.avg_quality_score = (
                self.avg_quality_score * 0.9 + quality_score * 0.1
            )
        else:
            self.avg_quality_score = quality_score
        
        self.last_execution_time = time.time()


@dataclass
class DecompositionResult:
    """拆解结果"""
    strategy: DecompositionStrategy
    subtasks: List[Dict[str, Any]]
    reasoning: str
    confidence: float
    quality_score: float = 0.0
    execution_time: float = 0.0


class DynamicTaskSplitter:
    """动态任务拆解器"""
    
    def __init__(self):
        # 策略性能追踪
        self.strategy_performance: Dict[DecompositionStrategy, StrategyPerformance] = {
            strategy: StrategyPerformance(strategy=strategy)
            for strategy in DecompositionStrategy
        }
        
        # 任务类别到策略的映射
        self.category_strategy_map: Dict[TaskCategory, DecompositionStrategy] = {
            TaskCategory.SIMPLE_QUERY: DecompositionStrategy.FAST_PATH,
            TaskCategory.DATA_RETRIEVAL: DecompositionStrategy.RULE_BASED,
            TaskCategory.CONTENT_ANALYSIS: DecompositionStrategy.LLM_INTELLIGENT,
            TaskCategory.COMPLEX_WORKFLOW: DecompositionStrategy.DEEP_ANALYSIS,
            TaskCategory.MULTI_STEP: DecompositionStrategy.HYBRID,
            TaskCategory.UNKNOWN: DecompositionStrategy.LLM_INTELLIGENT,
        }
        
        # 历史任务缓存
        self.task_history: List[Dict[str, Any]] = []
        self.max_history_size = 1000
        
        # 性能阈值
        self.success_rate_threshold = 0.7
        self.execution_time_threshold = 30.0
        
        logger.info("动态任务拆解器初始化完成")
    
    def analyze_task_characteristics(self, task: str) -> TaskCharacteristics:
        """分析任务特征
        
        Args:
            task: 任务描述
            
        Returns:
            任务特征
        """
        # 任务长度
        task_length = len(task)
        
        # 识别任务类别
        category = self._classify_task_category(task)
        
        # 计算复杂度分数
        complexity_score = self._calculate_complexity_score(task, task_length)
        
        # 预估步骤数
        estimated_steps = self._estimate_steps(task, complexity_score)
        
        # 预估耗时
        estimated_duration = self._estimate_duration(task, complexity_score, estimated_steps)
        
        # 资源强度
        resource_intensity = self._calculate_resource_intensity(task, complexity_score)
        
        return TaskCharacteristics(
            task_description=task,
            category=category,
            complexity_score=complexity_score,
            estimated_steps=estimated_steps,
            estimated_duration=estimated_duration,
            resource_intensity=resource_intensity,
            confidence=0.8
        )
    
    def _classify_task_category(self, task: str) -> TaskCategory:
        """分类任务类别
        
        Args:
            task: 任务描述
            
        Returns:
            任务类别
        """
        task_lower = task.lower()
        
        # 简单查询
        simple_keywords = ["查询", "搜索", "找", "是什么", "怎么", "如何"]
        if any(kw in task_lower for kw in simple_keywords) and len(task) < 50:
            return TaskCategory.SIMPLE_QUERY
        
        # 数据检索
        retrieval_keywords = ["爬取", "抓取", "获取", "下载", "提取"]
        if any(kw in task_lower for kw in retrieval_keywords):
            return TaskCategory.DATA_RETRIEVAL
        
        # 内容分析
        analysis_keywords = ["分析", "总结", "对比", "评估", "统计"]
        if any(kw in task_lower for kw in analysis_keywords):
            return TaskCategory.CONTENT_ANALYSIS
        
        # 复杂工作流
        workflow_keywords = ["流程", "工作流", "自动化", "批量", "循环"]
        if any(kw in task_lower for kw in workflow_keywords):
            return TaskCategory.COMPLEX_WORKFLOW
        
        # 多步骤任务
        step_keywords = ["然后", "接着", "之后", "最后", "第一步", "第二步"]
        if any(kw in task_lower for kw in step_keywords):
            return TaskCategory.MULTI_STEP
        
        return TaskCategory.UNKNOWN
    
    def _calculate_complexity_score(self, task: str, task_length: int) -> float:
        """计算复杂度分数
        
        Args:
            task: 任务描述
            task_length: 任务长度
            
        Returns:
            复杂度分数 (0-1)
        """
        score = 0.0
        
        # 长度因子
        length_score = min(task_length / 200.0, 1.0) * 0.3
        score += length_score
        
        # 关键词复杂度
        complex_keywords = ["分析", "评估", "对比", "统计", "预测", "优化"]
        keyword_count = sum(1 for kw in complex_keywords if kw in task.lower())
        keyword_score = min(keyword_count / 3.0, 1.0) * 0.3
        score += keyword_score
        
        # 结构复杂度（是否包含多个子任务）
        step_separators = ["然后", "接着", "之后", "最后", "；", "。"]
        separator_count = sum(1 for sep in step_separators if sep in task)
        structure_score = min(separator_count / 3.0, 1.0) * 0.4
        score += structure_score
        
        return min(score, 1.0)
    
    def _estimate_steps(self, task: str, complexity_score: float) -> int:
        """预估步骤数
        
        Args:
            task: 任务描述
            complexity_score: 复杂度分数
            
        Returns:
            预估步骤数
        """
        # 基础步骤数
        base_steps = 1
        
        # 根据复杂度调整
        if complexity_score < 0.3:
            return base_steps
        elif complexity_score < 0.6:
            return base_steps + 2
        elif complexity_score < 0.8:
            return base_steps + 4
        else:
            return base_steps + 6
    
    def _estimate_duration(self, task: str, complexity_score: float, 
                          estimated_steps: int) -> float:
        """预估耗时
        
        Args:
            task: 任务描述
            complexity_score: 复杂度分数
            estimated_steps: 预估步骤数
            
        Returns:
            预估耗时（秒）
        """
        # 基础耗时
        base_duration = 2.0
        
        # 根据步骤数调整
        step_duration = estimated_steps * 3.0
        
        # 根据复杂度调整
        complexity_multiplier = 1.0 + complexity_score * 2.0
        
        total_duration = (base_duration + step_duration) * complexity_multiplier
        
        return total_duration
    
    def _calculate_resource_intensity(self, task: str, complexity_score: float) -> float:
        """计算资源强度
        
        Args:
            task: 任务描述
            complexity_score: 复杂度分数
            
        Returns:
            资源强度 (0-1)
        """
        # 基础强度
        intensity = complexity_score * 0.6
        
        # 网络资源需求
        network_keywords = ["爬取", "抓取", "搜索", "下载"]
        if any(kw in task.lower() for kw in network_keywords):
            intensity += 0.2
        
        # 计算资源需求
        compute_keywords = ["分析", "处理", "计算", "统计"]
        if any(kw in task.lower() for kw in compute_keywords):
            intensity += 0.2
        
        return min(intensity, 1.0)
    
    def select_strategy(self, characteristics: TaskCharacteristics) -> DecompositionStrategy:
        """选择拆解策略
        
        Args:
            characteristics: 任务特征
            
        Returns:
            拆解策略
        """
        # 1. 基于任务类别的默认策略
        default_strategy = self.category_strategy_map[characteristics.category]
        
        # 2. 检查历史性能
        strategy_performance = self.strategy_performance[default_strategy]
        
        # 3. 如果默认策略性能不佳，尝试其他策略
        if (strategy_performance.success_rate < self.success_rate_threshold and
            strategy_performance.total_executions > 5):
            
            # 寻找性能更好的策略
            best_strategy = default_strategy
            best_score = strategy_performance.success_rate
            
            for strategy, performance in self.strategy_performance.items():
                if (performance.total_executions > 3 and
                    performance.success_rate > best_score):
                    best_strategy = strategy
                    best_score = performance.success_rate
            
            if best_strategy != default_strategy:
                logger.info(f"策略调整: {default_strategy.value} -> {best_strategy.value} "
                           f"(成功率: {strategy_performance.success_rate:.2%} -> {best_score:.2%})")
                return best_strategy
        
        # 4. 根据复杂度调整策略
        if characteristics.complexity_score > 0.8:
            return DecompositionStrategy.DEEP_ANALYSIS
        elif characteristics.complexity_score < 0.3:
            return DecompositionStrategy.FAST_PATH
        
        return default_strategy
    
    async def decompose_task(self, task: str) -> DecompositionResult:
        """拆解任务（动态策略）
        
        Args:
            task: 任务描述
            
        Returns:
            拆解结果
        """
        start_time = time.time()
        
        # 1. 分析任务特征
        characteristics = self.analyze_task_characteristics(task)
        logger.info(f"任务特征: 类别={characteristics.category.value}, "
                   f"复杂度={characteristics.complexity_score:.2f}, "
                   f"步骤={characteristics.estimated_steps}")
        
        # 2. 选择策略
        strategy = self.select_strategy(characteristics)
        logger.info(f"选择策略: {strategy.value}")
        
        # 3. 执行拆解
        subtasks, reasoning, confidence = await self._execute_decomposition(
            task, strategy, characteristics
        )
        
        # 4. 计算质量分数
        quality_score = self._calculate_quality_score(
            subtasks, characteristics, confidence
        )
        
        execution_time = time.time() - start_time
        
        result = DecompositionResult(
            strategy=strategy,
            subtasks=subtasks,
            reasoning=reasoning,
            confidence=confidence,
            quality_score=quality_score,
            execution_time=execution_time
        )
        
        # 5. 记录历史
        self._record_history(task, result, characteristics)
        
        return result
    
    async def _execute_decomposition(
        self,
        task: str,
        strategy: DecompositionStrategy,
        characteristics: TaskCharacteristics
    ) -> Tuple[List[Dict[str, Any]], str, float]:
        """执行拆解
        
        Args:
            task: 任务描述
            strategy: 拆解策略
            characteristics: 任务特征
            
        Returns:
            (子任务列表, 推理说明, 置信度)
        """
        try:
            if strategy == DecompositionStrategy.FAST_PATH:
                return await self._fast_path_decomposition(task, characteristics)
            elif strategy == DecompositionStrategy.RULE_BASED:
                return await self._rule_based_decomposition(task, characteristics)
            elif strategy == DecompositionStrategy.LLM_INTELLIGENT:
                return await self._llm_intelligent_decomposition(task, characteristics)
            elif strategy == DecompositionStrategy.HYBRID:
                return await self._hybrid_decomposition(task, characteristics)
            elif strategy == DecompositionStrategy.DEEP_ANALYSIS:
                return await self._deep_analysis_decomposition(task, characteristics)
            else:
                return await self._llm_intelligent_decomposition(task, characteristics)
        except Exception as e:
            logger.error(f"拆解失败: {e}")
            # 降级到LLM智能拆解
            return await self._llm_intelligent_decomposition(task, characteristics)
    
    async def _fast_path_decomposition(
        self,
        task: str,
        characteristics: TaskCharacteristics
    ) -> Tuple[List[Dict[str, Any]], str, float]:
        """快速路径拆解"""
        subtask = {
            "type": "search",
            "params": {"query": task},
            "priority": 1.0
        }
        
        reasoning = "简单任务，直接执行搜索"
        confidence = 0.9
        
        return [subtask], reasoning, confidence
    
    async def _rule_based_decomposition(
        self,
        task: str,
        characteristics: TaskCharacteristics
    ) -> Tuple[List[Dict[str, Any]], str, float]:
        """基于规则的拆解"""
        # 简化的规则拆解
        subtasks = []
        
        if "爬取" in task or "抓取" in task:
            subtasks.append({
                "type": "search",
                "params": {"query": task},
                "priority": 1.0
            })
            subtasks.append({
                "type": "scrape",
                "params": {"url": "$search_result"},
                "priority": 0.8
            })
        elif "分析" in task or "总结" in task:
            subtasks.append({
                "type": "search",
                "params": {"query": task},
                "priority": 1.0
            })
            subtasks.append({
                "type": "analyze",
                "params": {"data": "$search_result"},
                "priority": 0.8
            })
            subtasks.append({
                "type": "summarize",
                "params": {"text": "$analysis_result"},
                "priority": 0.6
            })
        else:
            subtasks.append({
                "type": "search",
                "params": {"query": task},
                "priority": 1.0
            })
        
        reasoning = f"基于规则拆解，生成{len(subtasks)}个子任务"
        confidence = 0.8
        
        return subtasks, reasoning, confidence
    
    async def _llm_intelligent_decomposition(
        self,
        task: str,
        characteristics: TaskCharacteristics
    ) -> Tuple[List[Dict[str, Any]], str, float]:
        """LLM智能拆解"""
        try:
            from core.llm_backend import get_llm_router
            
            router = get_llm_router()
            
            if not router.is_available():
                logger.warning("LLM不可用，使用规则拆解")
                return await self._rule_based_decomposition(task, characteristics)
            
            prompt = f"""请将以下任务拆解为具体的子任务步骤。

任务描述：{task}

要求：
1. 分解为{characteristics.estimated_steps}个左右的子任务
2. 每个子任务包含 type 和 params 字段
3. 子任务类型可以是：search, scrape, analyze, summarize, process 等
4. params 中可以使用 $ 开头的占位符表示依赖前序任务的结果
5. 返回JSON格式，不要包含其他内容

示例输出：
[
  {{"type": "search", "params": {{"query": "关键词"}}}},
  {{"type": "scrape", "params": {{"url": "$search_result"}}}},
  {{"type": "analyze", "params": {{"data": "$scraped_content"}}}}
]
"""
            
            response = await router.simple_chat(
                user_message=prompt,
                system_prompt="你是任务拆解专家，只返回JSON格式的子任务列表",
                temperature=0.3
            )
            
            if response:
                subtasks = self._parse_llm_response(response)
                reasoning = f"LLM智能拆解，生成{len(subtasks)}个子任务"
                confidence = 0.85
                return subtasks, reasoning, confidence
            else:
                return await self._rule_based_decomposition(task, characteristics)
                
        except Exception as e:
            logger.error(f"LLM拆解失败: {e}")
            return await self._rule_based_decomposition(task, characteristics)
    
    async def _hybrid_decomposition(
        self,
        task: str,
        characteristics: TaskCharacteristics
    ) -> Tuple[List[Dict[str, Any]], str, float]:
        """混合策略拆解"""
        # 先尝试规则拆解
        rule_subtasks, rule_reasoning, rule_confidence = await self._rule_based_decomposition(
            task, characteristics
        )
        
        # 如果规则拆解置信度足够，直接返回
        if rule_confidence >= 0.7:
            return rule_subtasks, rule_reasoning, rule_confidence
        
        # 否则使用LLM拆解
        llm_subtasks, llm_reasoning, llm_confidence = await self._llm_intelligent_decomposition(
            task, characteristics
        )
        
        # 混合推理
        reasoning = f"混合策略：{rule_reasoning} + {llm_reasoning}"
        confidence = (rule_confidence + llm_confidence) / 2.0
        
        # 返回LLM结果（通常更准确）
        return llm_subtasks, reasoning, confidence
    
    async def _deep_analysis_decomposition(
        self,
        task: str,
        characteristics: TaskCharacteristics
    ) -> Tuple[List[Dict[str, Any]], str, float]:
        """深度分析拆解"""
        # 先进行LLM拆解
        llm_subtasks, llm_reasoning, llm_confidence = await self._llm_intelligent_decomposition(
            task, characteristics
        )
        
        # 增加额外的验证和优化步骤
        optimized_subtasks = self._optimize_subtasks(llm_subtasks, characteristics)
        
        reasoning = f"深度分析拆解：{llm_reasoning} + 优化"
        confidence = min(llm_confidence + 0.05, 1.0)
        
        return optimized_subtasks, reasoning, confidence
    
    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """解析LLM响应
        
        Args:
            response: LLM响应文本
            
        Returns:
            子任务列表
        """
        try:
            # 移除markdown代码块标记
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            # 解析JSON
            subtasks = json.loads(response)
            
            # 验证格式
            if not isinstance(subtasks, list):
                raise ValueError("响应不是列表格式")
            
            for subtask in subtasks:
                if not isinstance(subtask, dict):
                    raise ValueError("子任务不是字典格式")
                if "type" not in subtask:
                    raise ValueError("子任务缺少type字段")
                if "params" not in subtask:
                    subtask["params"] = {}
            
            return subtasks
            
        except Exception as e:
            logger.error(f"解析LLM响应失败: {e}")
            return [{"type": "search", "params": {"query": "default"}}]
    
    def _optimize_subtasks(
        self,
        subtasks: List[Dict[str, Any]],
        characteristics: TaskCharacteristics
    ) -> List[Dict[str, Any]]:
        """优化子任务
        
        Args:
            subtasks: 原始子任务列表
            characteristics: 任务特征
            
        Returns:
            优化后的子任务列表
        """
        optimized = []
        
        for subtask in subtasks:
            # 添加优先级
            if "priority" not in subtask:
                subtask["priority"] = 1.0
            
            # 添加超时时间
            if "timeout" not in subtask:
                subtask["timeout"] = min(
                    characteristics.estimated_duration / len(subtasks),
                    30.0
                )
            
            optimized.append(subtask)
        
        return optimized
    
    def _calculate_quality_score(
        self,
        subtasks: List[Dict[str, Any]],
        characteristics: TaskCharacteristics,
        confidence: float
    ) -> float:
        """计算质量分数
        
        Args:
            subtasks: 子任务列表
            characteristics: 任务特征
            confidence: 置信度
            
        Returns:
            质量分数 (0-1)
        """
        score = 0.0
        
        # 1. 步骤数匹配度
        steps_match = 1.0 - abs(len(subtasks) - characteristics.estimated_steps) / max(characteristics.estimated_steps, 1)
        score += steps_match * 0.3
        
        # 2. 置信度
        score += confidence * 0.4
        
        # 3. 子任务完整性
        completeness = 1.0
        for subtask in subtasks:
            if "type" not in subtask or "params" not in subtask:
                completeness -= 0.1
        score += completeness * 0.3
        
        return max(min(score, 1.0), 0.0)
    
    def _record_history(
        self,
        task: str,
        result: DecompositionResult,
        characteristics: TaskCharacteristics
    ):
        """记录历史
        
        Args:
            task: 任务描述
            result: 拆解结果
            characteristics: 任务特征
        """
        history_entry = {
            "task": task,
            "strategy": result.strategy.value,
            "subtasks_count": len(result.subtasks),
            "confidence": result.confidence,
            "quality_score": result.quality_score,
            "execution_time": result.execution_time,
            "category": characteristics.category.value,
            "complexity_score": characteristics.complexity_score,
            "timestamp": time.time()
        }
        
        self.task_history.append(history_entry)
        
        # 限制历史记录大小
        if len(self.task_history) > self.max_history_size:
            self.task_history = self.task_history[-self.max_history_size:]
    
    def update_strategy_performance(
        self,
        strategy: DecompositionStrategy,
        success: bool,
        execution_time: float,
        quality_score: float
    ):
        """更新策略性能
        
        Args:
            strategy: 策略类型
            success: 是否成功
            execution_time: 执行时间
            quality_score: 质量分数
        """
        if strategy in self.strategy_performance:
            self.strategy_performance[strategy].update(
                success, execution_time, quality_score
            )
            logger.info(f"更新策略性能: {strategy.value} "
                       f"(成功率={self.strategy_performance[strategy].success_rate:.2%})")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息
        
        Returns:
            统计信息
        """
        return {
            "total_tasks": len(self.task_history),
            "strategy_performance": {
                strategy.value: {
                    "success_rate": perf.success_rate,
                    "avg_execution_time": perf.avg_execution_time,
                    "avg_quality_score": perf.avg_quality_score,
                    "total_executions": perf.total_executions
                }
                for strategy, perf in self.strategy_performance.items()
            },
            "category_distribution": self._get_category_distribution(),
            "complexity_distribution": self._get_complexity_distribution()
        }
    
    def _get_category_distribution(self) -> Dict[str, int]:
        """获取类别分布"""
        distribution = defaultdict(int)
        for entry in self.task_history:
            distribution[entry["category"]] += 1
        return dict(distribution)
    
    def _get_complexity_distribution(self) -> Dict[str, int]:
        """获取复杂度分布"""
        distribution = {
            "low": 0,      # 0.0-0.3
            "medium": 0,   # 0.3-0.6
            "high": 0,     # 0.6-0.8
            "very_high": 0 # 0.8-1.0
        }
        
        for entry in self.task_history:
            complexity = entry["complexity_score"]
            if complexity < 0.3:
                distribution["low"] += 1
            elif complexity < 0.6:
                distribution["medium"] += 1
            elif complexity < 0.8:
                distribution["high"] += 1
            else:
                distribution["very_high"] += 1
        
        return distribution


# 全局动态拆解器实例
_dynamic_splitter = None
_splitter_lock = None


def get_dynamic_task_splitter() -> DynamicTaskSplitter:
    """获取动态任务拆解器单例
    
    Returns:
        动态任务拆解器实例
    """
    global _dynamic_splitter, _splitter_lock
    
    if _dynamic_splitter is None:
        import threading
        _splitter_lock = threading.Lock()
        
        with _splitter_lock:
            if _dynamic_splitter is None:
                _dynamic_splitter = DynamicTaskSplitter()
    
    return _dynamic_splitter