"""多Agent协同优化模块

参考 Claude Code 的 skill 协同机制，优化多Agent协同效果：

1. 协作模式自动检测：根据任务类型自动选择最佳协作模式
2. 任务分解优化：智能识别可并行执行的任务
3. 通信协议标准化：统一Agent间的通信格式
4. 结果聚合策略：根据任务类型选择最优结果聚合方式

使用场景：
- 复杂任务需要多Agent协作
- 并行执行可提升效率的场景
- 需要不同专业领域Agent配合的场景
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class CollaborationPattern(Enum):
    """协作模式枚举"""
    PIPELINE = "pipeline"           # 流水线：上一个Agent的输出是下一个的输入
    PARALLEL = "parallel"          # 并行：多个Agent同时执行独立任务
    MASTER_SLAVE = "master_slave"  # 主从：主Agent协调，多个从Agent执行
    REVIEW = "review"              # 评审：一个Agent执行，一个Agent评审
    AUCTION = "auction"            # 拍卖：多个Agent竞争，最优者执行


class TaskDependency(Enum):
    """任务依赖类型"""
    INDEPENDENT = "independent"     # 完全独立，可并行
    SEQUENTIAL = "sequential"      # 顺序依赖，必须串行
    CONDITIONAL = "conditional"    # 条件依赖，根据结果决定
    RESULT_DEPENDENT = "result_dependent"  # 结果依赖，依赖前置结果


@dataclass
class CollaborationStep:
    """协作步骤"""
    step_id: str
    agent_type: str
    task_description: str
    input_from: List[str] = field(default_factory=list)  # 依赖的前置步骤ID
    expected_output: str = ""
    timeout: float = 30.0  # 超时时间（秒）
    retry_on_failure: bool = True
    max_retries: int = 2


@dataclass
class CollaborationPlan:
    """协作计划"""
    plan_id: str
    pattern: CollaborationPattern
    steps: List[CollaborationStep]
    estimated_duration: float = 0.0
    parallel_groups: List[List[str]] = field(default_factory=list)  # 可并行的步骤分组


class CollaborationOptimizer:
    """协作优化器
    
    核心功能：
    1. 分析任务，确定最佳协作模式
    2. 分解任务为可执行的步骤
    3. 识别可并行执行的任务
    4. 生成详细的协作计划
    """
    
    # 协作模式选择规则
    COLLABORATION_RULES = {
        "parallel_threshold": 3,  # 超过3个独立任务，选择并行模式
        "sequential_keywords": ["然后", "接着", "之后", "再", "最后", "首先", "第一步"],
        "parallel_keywords": ["同时", "并行", "分别", "各自"],
        "review_keywords": ["检查", "验证", "审核", "评审", "确认"],
        "master_slave_keywords": ["协调", "管理", "分配", "调度"]
    }
    
    def __init__(self):
        self.collaboration_history: List[Dict[str, Any]] = []
    
    def analyze_task(self, task_description: str) -> Dict[str, Any]:
        """分析任务，返回协作建议
        
        Args:
            task_description: 任务描述
            
        Returns:
            协作分析结果
        """
        task_lower = task_description.lower()
        
        # 1. 检测是否需要多Agent协作
        needs_collaboration = self._detect_collaboration_need(task_description)
        
        # 2. 确定协作模式
        pattern = self._determine_pattern(task_description)
        
        # 3. 分解任务步骤
        steps = self._decompose_task(task_description)
        
        # 4. 确定依赖关系
        dependencies = self._analyze_dependencies(steps, pattern)
        
        # 5. 识别可并行的步骤
        parallel_groups = self._identify_parallel_groups(steps, dependencies)
        
        return {
            "needs_collaboration": needs_collaboration,
            "pattern": pattern,
            "steps": steps,
            "dependencies": dependencies,
            "parallel_groups": parallel_groups,
            "estimated_duration": self._estimate_duration(steps, parallel_groups)
        }
    
    def _detect_collaboration_need(self, task_description: str) -> bool:
        """检测是否需要多Agent协作"""
        # 多步骤指示词
        multi_step_indicators = [
            "先", "然后", "接着", "再", "之后", "最后",
            "第一步", "第二步", "第三步",
            "首先", "其次", "最后"
        ]
        
        # 检测步骤词数量
        step_count = sum(1 for indicator in multi_step_indicators if indicator in task_description)
        
        # 多个动词可能表示需要协作
        action_verbs = ["分析", "处理", "生成", "获取", "爬取", "翻译", "统计", "可视化"]
        verb_count = sum(1 for verb in action_verbs if verb in task_description)
        
        # 触发协作的条件
        return step_count >= 2 or verb_count >= 3
    
    def _determine_pattern(self, task_description: str) -> CollaborationPattern:
        """确定协作模式"""
        task_lower = task_description.lower()
        
        # 并行模式检测
        if any(kw in task_lower for kw in self.COLLABORATION_RULES["parallel_keywords"]):
            return CollaborationPattern.PARALLEL
        
        # 评审模式检测
        if any(kw in task_lower for kw in self.COLLABORATION_RULES["review_keywords"]):
            return CollaborationPattern.REVIEW
        
        # 主从模式检测
        if any(kw in task_lower for kw in self.COLLABORATION_RULES["master_slave_keywords"]):
            return CollaborationPattern.MASTER_SLAVE
        
        # 流水线模式（默认）- 多步骤顺序执行
        multi_step_indicators = self.COLLABORATION_RULES["sequential_keywords"]
        if any(kw in task_description for kw in multi_step_indicators):
            return CollaborationPattern.PIPELINE
        
        # 检查是否有多个明确的阶段
        if self._count_phases(task_description) >= 3:
            return CollaborationPattern.PIPELINE
        
        # 默认返回流水线模式
        return CollaborationPattern.PIPELINE
    
    def _count_phases(self, task_description: str) -> int:
        """计算任务中的阶段数量"""
        phases = [
            "准备", "分析", "处理", "执行", "完成",
            "收集", "整理", "生成", "输出",
            "查询", "获取", "处理", "展示"
        ]
        return sum(1 for phase in phases if phase in task_description)
    
    def _decompose_task(self, task_description: str) -> List[CollaborationStep]:
        """分解任务为步骤"""
        steps = []
        step_id_counter = 0
        
        # 根据关键词分解任务
        task_segments = self._split_by_keywords(task_description)
        
        for i, segment in enumerate(task_segments):
            if not segment.strip():
                continue
            
            step_id = f"step_{step_id_counter}"
            step_id_counter += 1
            
            # 确定Agent类型
            agent_type = self._infer_agent_type(segment)
            
            step = CollaborationStep(
                step_id=step_id,
                agent_type=agent_type,
                task_description=segment.strip(),
                expected_output=self._infer_expected_output(segment)
            )
            steps.append(step)
        
        return steps
    
    def _split_by_keywords(self, text: str) -> List[str]:
        """使用关键词分割任务"""
        import re
        
        # 分隔符模式
        separators = [
            r'[，,]\s*',  # 逗号分隔
            r'[。]\s*',    # 句号分隔
            r'\s*[然后接着再之后最后]\s*',  # 步骤词分隔
            r'\s*[并并且同时]\s*',  # 并列词分隔
        ]
        
        segments = [text]
        for sep in separators:
            new_segments = []
            for segment in segments:
                parts = re.split(sep, segment)
                new_segments.extend(parts)
            segments = new_segments
        
        # 清理和过滤
        cleaned_segments = []
        for seg in segments:
            seg = seg.strip()
            if seg and len(seg) > 3:  # 过滤太短的片段
                cleaned_segments.append(seg)
        
        return cleaned_segments if cleaned_segments else [text]
    
    def _infer_agent_type(self, segment: str) -> str:
        """推断需要的Agent类型"""
        segment_lower = segment.lower()
        
        # Agent类型映射
        agent_mappings = {
            "web_scraper": ["爬", "抓", "获取", "采集", "热搜", "热榜"],
            "translator": ["翻译", "英文", "中文", "日语", "韩语"],
            "data_analysis": ["分析", "统计", "图表", "可视化", "计算"],
            "text_analyzer": ["总结", "摘要", "提取", "情感"],
            "gui_automation": ["打开", "点击", "截图", "控制"],
            "weather": ["天气", "气温", "温度"]
        }
        
        for agent_type, keywords in agent_mappings.items():
            if any(kw in segment_lower for kw in keywords):
                return agent_type
        
        # 默认使用通用Agent
        return "chat"
    
    def _infer_expected_output(self, segment: str) -> str:
        """推断预期输出"""
        if "获取" in segment or "爬" in segment:
            return "data_list"
        if "翻译" in segment:
            return "translated_text"
        if "分析" in segment or "统计" in segment:
            return "analysis_result"
        if "打开" in segment or "点击" in segment:
            return "action_confirmation"
        return "general_response"
    
    def _analyze_dependencies(self, steps: List[CollaborationStep], 
                              pattern: CollaborationPattern) -> Dict[str, TaskDependency]:
        """分析任务依赖关系"""
        dependencies = {}
        
        if pattern == CollaborationPattern.PARALLEL:
            # 并行模式下，所有步骤独立
            for step in steps:
                dependencies[step.step_id] = TaskDependency.INDEPENDENT
        else:
            # 流水线模式，第一个步骤独立，其余依赖前一个
            for i, step in enumerate(steps):
                if i == 0:
                    dependencies[step.step_id] = TaskDependency.INDEPENDENT
                else:
                    dependencies[step.step_id] = TaskDependency.RESULT_DEPENDENT
                    step.input_from = [steps[i-1].step_id]
        
        return dependencies
    
    def _identify_parallel_groups(self, steps: List[CollaborationStep],
                                 dependencies: Dict[str, TaskDependency]) -> List[List[str]]:
        """识别可并行的步骤分组"""
        parallel_groups = []
        
        # 找出所有独立的步骤
        independent_steps = [
            step.step_id for step in steps 
            if dependencies.get(step.step_id) == TaskDependency.INDEPENDENT
        ]
        
        if independent_steps:
            parallel_groups.append(independent_steps)
        
        # 找出所有结果依赖的步骤（作为单独的组）
        dependent_steps = [
            step.step_id for step in steps 
            if dependencies.get(step.step_id) == TaskDependency.RESULT_DEPENDENT
        ]
        
        if dependent_steps:
            # 如果依赖链简单，可以并行执行
            if len(dependent_steps) > 1:
                # 检查是否可以合并
                parallel_groups.append(dependent_steps)
            else:
                for step_id in dependent_steps:
                    parallel_groups.append([step_id])
        
        return parallel_groups
    
    def _estimate_duration(self, steps: List[CollaborationStep],
                         parallel_groups: List[List[str]]) -> float:
        """估算执行时长"""
        # 每个步骤的基础时长（秒）
        base_durations = {
            "web_scraper": 5.0,
            "translator": 2.0,
            "data_analysis": 3.0,
            "text_analyzer": 2.0,
            "gui_automation": 1.0,
            "weather": 1.0,
            "chat": 0.5
        }
        
        # 计算每个并行组的总时长
        group_durations = []
        for group in parallel_groups:
            group_duration = 0
            for step_id in group:
                for step in steps:
                    if step.step_id == step_id:
                        duration = base_durations.get(step.agent_type, 2.0)
                        group_duration = max(group_duration, duration)  # 并行取最大
                        break
            group_durations.append(group_duration)
        
        return sum(group_durations)
    
    def create_plan(self, task_description: str) -> CollaborationPlan:
        """创建协作计划
        
        Args:
            task_description: 任务描述
            
        Returns:
            协作计划
        """
        import uuid
        
        analysis = self.analyze_task(task_description)
        
        plan = CollaborationPlan(
            plan_id=str(uuid.uuid4())[:8],
            pattern=analysis["pattern"],
            steps=analysis["steps"],
            parallel_groups=analysis["parallel_groups"],
            estimated_duration=analysis["estimated_duration"]
        )
        
        # 记录历史
        self.collaboration_history.append({
            "plan_id": plan.plan_id,
            "pattern": plan.pattern.value,
            "step_count": len(plan.steps),
            "parallel_groups": len(plan.parallel_groups)
        })
        
        return plan
    
    def get_collaboration_hint(self, task_description: str) -> str:
        """生成协作提示（用于优化LLM理解）
        
        Args:
            task_description: 任务描述
            
        Returns:
            协作提示文本
        """
        analysis = self.analyze_task(task_description)
        
        hints = []
        
        # 协作需求提示
        if analysis["needs_collaboration"]:
            hints.append(f"需要多Agent协作（{len(analysis['steps'])}个步骤）")
        
        # 协作模式提示
        pattern_hints = {
            CollaborationPattern.PIPELINE: "建议使用流水线模式，按顺序执行各步骤",
            CollaborationPattern.PARALLEL: "建议使用并行模式，同时执行独立任务",
            CollaborationPattern.MASTER_SLAVE: "建议使用主从模式，一个Agent协调多个Agent执行",
            CollaborationPattern.REVIEW: "建议使用评审模式，一个Agent执行一个Agent评审",
            CollaborationPattern.AUCTION: "建议使用拍卖模式，多个Agent竞争最优方案"
        }
        hints.append(pattern_hints.get(analysis["pattern"], ""))
        
        # 并行机会提示
        if analysis["parallel_groups"] and len(analysis["parallel_groups"]) > 1:
            total_parallel = sum(len(g) for g in analysis["parallel_groups"])
            hints.append(f"可并行执行{total_parallel}个步骤，预计节省{(len(analysis['steps']) - len(analysis['parallel_groups'])) * 2}秒")
        
        return " | ".join(hints)


# 全局单例
_optimizer_instance: Optional[CollaborationOptimizer] = None


def get_collaboration_optimizer() -> CollaborationOptimizer:
    """获取协作优化器实例"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = CollaborationOptimizer()
    return _optimizer_instance
