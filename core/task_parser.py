"""自然语言任务解析器（已废弃 - DEPRECATED）

⚠️ 此模块当前未被主流程使用，仅在task_executor.py中引用。
如需简单并发+链式处理，请直接使用 ConcurrentTaskProcessor。

功能说明：
根据用户输入的关键词自动识别：
1. 并发任务（多个任务同时执行）
2. 协作任务（任务之间有依赖，按顺序执行）
3. 嵌套结构（并发嵌套协作，或协作嵌套并发）

关键词定义：
- 并发："与"、"和"、"一起"、"同时"、"并且"
- 协作："然后"、"接着"、"之后"、"再"、"最后"、"并"

注意：
- 当前系统采用简化架构，通过ConcurrentTaskProcessor的depends_on字段实现链式处理
- 此模块提供的任务树解析能力暂未启用
- 未来如需更复杂的自然语言任务编排，可重新评估是否启用

原设计目标：
- 将自然语言任务描述转换为结构化任务树(TaskNode)
- 支持多层级并发/协作关系表达
- 提供任务树可视化解释功能
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskRelation(Enum):
    """任务关系类型"""
    PARALLEL = "parallel"      # 并发（独立执行）
    COLLABORATIVE = "collaborative"  # 协作（有依赖）
    SEQUENTIAL = "sequential"  # 顺序（显式顺序）
    UNKNOWN = "unknown"        # 未知


@dataclass
class TaskNode:
    """任务节点"""
    id: str
    description: str          # 任务描述
    relation: TaskRelation     # 任务关系
    children: List['TaskNode'] = field(default_factory=list)  # 子任务
    parent: Optional['TaskNode'] = None
    depends_on: Optional[List[str]] = None  # 依赖的任务ID
    output_key: Optional[str] = None  # 输出结果的关键字（用于协作传递）

    def is_leaf(self) -> bool:
        """是否为叶子节点（不可再分解）"""
        return len(self.children) == 0

    def get_all_leaf_tasks(self) -> List['TaskNode']:
        """获取所有叶子任务"""
        if self.is_leaf():
            return [self]
        result = []
        for child in self.children:
            result.extend(child.get_all_leaf_tasks())
        return result


@dataclass
class ParseResult:
    """解析结果"""
    root_tasks: List[TaskNode]
    has_parallel: bool = False
    has_collaborative: bool = False
    has_nested: bool = False
    execution_strategy: str = "auto"  # auto, parallel, collaborative, hybrid
    reasoning: str = ""  # 解析说明


class NaturalLanguageTaskParser:
    """自然语言任务解析器"""

    def __init__(self):
        # 并发关键词
        self.parallel_keywords = [
            "和", "与", "一起", "同时", "并且",
            "加", "plus", "and", "also",
            "都", "都需要", "都要"
        ]

        # 协作关键词（顺序依赖）
        self.collaborative_keywords = [
            "然后", "接着", "之后", "再", "最后",
            "之后在", "再然后", "之后才", "才能",
            "先", "首先", "第一", "第二", "第三",
            "的前提", "基于", "根据",
            "先...再...", "先...然后...",
            "并且", "并"  # "搜索并分析" 视为协作
        ]

    def parse(self, text: str) -> ParseResult:
        """解析用户输入，返回任务树

        Args:
            text: 用户输入的自然语言

        Returns:
            ParseResult: 解析结果，包含任务树和执行策略
        """
        if not text or not text.strip():
            return ParseResult(root_tasks=[], reasoning="输入为空")

        logger.info(f"开始解析任务: {text}")

        # 1. 预处理文本
        text = self._preprocess(text)

        # 2. 分析任务关系
        has_parallel = self._contains_parallel(text)
        has_collaborative = self._contains_collaborative(text)

        # 3. 构建任务树
        if has_parallel and has_collaborative:
            # 混合模式：先分解，再分析嵌套
            root_tasks = self._build_mixed_task_tree(text)
            strategy = "hybrid"
            reasoning = "识别为混合模式：包含并发和协作关键词"
        elif has_parallel:
            # 并发模式
            root_tasks = self._build_parallel_task_tree(text)
            strategy = "parallel"
            reasoning = "识别为并发模式：子任务可同时执行"
        elif has_collaborative:
            # 协作模式
            root_tasks = self._build_collaborative_task_tree(text)
            strategy = "collaborative"
            reasoning = "识别为协作模式：子任务有依赖关系"
        else:
            # 简单任务
            root_tasks = [self._create_simple_task(text)]
            strategy = "auto"
            reasoning = "简单任务，无需分解"

        # 4. 检测嵌套结构
        has_nested = self._check_nested_structure(root_tasks)

        result = ParseResult(
            root_tasks=root_tasks,
            has_parallel=has_parallel,
            has_collaborative=has_collaborative,
            has_nested=has_nested,
            execution_strategy=strategy,
            reasoning=reasoning
        )

        logger.info(f"解析完成: {reasoning}, 策略: {strategy}")
        return result

    def _preprocess(self, text: str) -> str:
        """预处理文本"""
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text)
        # 统一标点
        text = text.replace('，', ',').replace('。', '.')
        return text.strip()

    def _contains_parallel(self, text: str) -> bool:
        """检查是否包含并发关键词"""
        for kw in self.parallel_keywords:
            if kw in text:
                return True
        return False

    def _contains_collaborative(self, text: str) -> bool:
        """检查是否包含协作关键词"""
        for kw in self.collaborative_keywords:
            if kw in text:
                return True
        return False

    def _find_keyword_position(self, text: str, keywords: List[str]) -> List[Tuple[str, int, str]]:
        """查找关键词位置，返回 (关键词, 位置, 类型) 列表"""
        positions = []
        for kw in keywords:
            idx = 0
            while True:
                pos = text.find(kw, idx)
                if pos == -1:
                    break
                # 排除括号内的关键词
                if not self._is_in_bracket(text, pos):
                    positions.append((kw, pos, kw))
                idx = pos + len(kw)
        # 按位置排序
        positions.sort(key=lambda x: x[1])
        return positions

    def _is_in_bracket(self, text: str, pos: int) -> bool:
        """检查位置是否在括号内"""
        before = text[:pos]
        open_count = before.count('(') + before.count('[') + before.count('{')
        close_count = before.count(')') + before.count(']') + before.count('}')
        return open_count > close_count

    def _split_by_keyword(self, text: str, keyword: str) -> List[str]:
        """按关键词分割文本"""
        parts = []
        idx = 0
        while True:
            pos = text.find(keyword, idx)
            if pos == -1:
                parts.append(text[idx:].strip())
                break
            # 取关键词前后的内容
            before = text[idx:pos].strip()
            if before:
                parts.append(before)
            idx = pos + len(keyword)
        return [p for p in parts if p.strip()]

    def _build_mixed_task_tree(self, text: str) -> List[TaskNode]:
        """构建混合任务树（并发+协作嵌套）"""
        tasks = []

        # 优先按协作关键词分割
        collaborative_positions = self._find_keyword_position(text, self.collaborative_keywords)

        if collaborative_positions:
            # 找到协作关键词，按协作分割
            main_parts = self._split_by_keyword(text, collaborative_positions[0][0])

            for i, part in enumerate(main_parts):
                if not part.strip():
                    continue

                # 检查每个部分是否包含并发
                if self._contains_parallel(part):
                    # 并发嵌套在协作中
                    parallel_node = self._build_parallel_node(part)
                    parallel_node.id = f"task_{len(tasks)}_parallel"
                    tasks.append(parallel_node)
                else:
                    # 简单任务
                    node = self._create_simple_task(part)
                    node.id = f"task_{len(tasks)}"
                    tasks.append(node)
        else:
            # 没有协作关键词，按并发处理
            tasks = self._build_parallel_task_tree(text)

        return tasks

    def _build_parallel_task_tree(self, text: str) -> List[TaskNode]:
        """构建并发任务树"""
        tasks = []

        # 找到所有并发关键词位置
        parallel_positions = self._find_keyword_position(text, self.parallel_keywords)

        if not parallel_positions:
            # 没有并发关键词，返回简单任务
            return [self._create_simple_task(text)]

        # 按第一个并发关键词分割
        first_kw = parallel_positions[0][0]
        parts = self._split_by_keyword(text, first_kw)

        for i, part in enumerate(parts):
            if not part.strip():
                continue

            # 检查是否还有协作关键词
            if self._contains_collaborative(part):
                # 协作嵌套在并发中
                collaborative_node = self._build_collaborative_node(part)
                collaborative_node.id = f"task_{len(tasks)}_collab"
                tasks.append(collaborative_node)
            else:
                # 叶子任务
                node = self._create_simple_task(part)
                node.id = f"task_{len(tasks)}"
                tasks.append(node)

        # 创建根节点（并发组）
        root = TaskNode(
            id="root_parallel",
            description=text,
            relation=TaskRelation.PARALLEL,
            children=tasks
        )

        # 设置父子关系
        for task in tasks:
            task.parent = root

        return [root]

    def _build_collaborative_task_tree(self, text: str) -> List[TaskNode]:
        """构建协作任务树"""
        tasks = []

        # 找到所有协作关键词
        all_collab_keywords = sorted(
            self.collaborative_keywords,
            key=len,
            reverse=True  # 优先匹配长关键词
        )

        # 使用正则分割
        pattern = '|'.join(re.escape(kw) for kw in all_collab_keywords)
        parts = re.split(pattern, text)
        keywords_found = re.findall(pattern, text)

        # 过滤空部分
        parts = [p.strip() for p in parts if p.strip()]

        # 创建任务节点
        prev_task = None
        for i, part in enumerate(parts):
            # 检查是否包含并发
            if self._contains_parallel(part):
                parallel_node = self._build_parallel_node(part)
                parallel_node.id = f"task_{len(tasks)}_parallel"
                tasks.append(parallel_node)

                # 设置依赖
                if prev_task:
                    if not prev_task.depends_on:
                        prev_task.depends_on = []
                    prev_task.depends_on.append(parallel_node.id)
                    parallel_node.parent = prev_task.parent if prev_task.parent else None
            else:
                node = self._create_simple_task(part)
                node.id = f"task_{len(tasks)}"
                tasks.append(node)

                # 设置依赖关系（协作：当前任务依赖前一个任务）
                if prev_task:
                    if not node.depends_on:
                        node.depends_on = []
                    node.depends_on.append(prev_task.id)
                    node.parent = prev_task.parent

            prev_task = tasks[-1]

        # 创建根节点（协作组）
        if len(tasks) > 1:
            root = TaskNode(
                id="root_collaborative",
                description=text,
                relation=TaskRelation.COLLABORATIVE,
                children=tasks
            )
            for task in tasks:
                task.parent = root
            return [root]
        elif len(tasks) == 1:
            tasks[0].relation = TaskRelation.COLLABORATIVE
            return tasks
        else:
            return [self._create_simple_task(text)]

    def _build_parallel_node(self, text: str) -> TaskNode:
        """构建并发节点"""
        tasks = []
        parallel_positions = self._find_keyword_position(text, self.parallel_keywords)

        if parallel_positions:
            first_kw = parallel_positions[0][0]
            parts = self._split_by_keyword(text, first_kw)

            for part in parts:
                if part.strip():
                    node = self._create_simple_task(part)
                    node.id = f"sub_{len(tasks)}"
                    tasks.append(node)
        else:
            node = self._create_simple_task(text)
            node.id = f"sub_{len(tasks)}"
            tasks.append(node)

        node = TaskNode(
            id="parallel_group",
            description=text,
            relation=TaskRelation.PARALLEL,
            children=tasks
        )

        for task in tasks:
            task.parent = node

        return node

    def _build_collaborative_node(self, text: str) -> TaskNode:
        """构建协作节点"""
        tasks = []

        all_collab_keywords = sorted(
            self.collaborative_keywords,
            key=len,
            reverse=True
        )

        pattern = '|'.join(re.escape(kw) for kw in all_collab_keywords)
        parts = re.split(pattern, text)
        parts = [p.strip() for p in parts if p.strip()]

        prev_task = None
        for i, part in enumerate(parts):
            node = self._create_simple_task(part)
            node.id = f"sub_{len(tasks)}"

            if prev_task:
                node.depends_on = [prev_task.id]

            tasks.append(node)
            prev_task = node

        node = TaskNode(
            id="collaborative_group",
            description=text,
            relation=TaskRelation.COLLABORATIVE,
            children=tasks
        )

        for task in tasks:
            task.parent = node

        return node

    def _create_simple_task(self, description: str) -> TaskNode:
        """创建简单任务节点"""
        return TaskNode(
            id="simple_task",
            description=description.strip(),
            relation=TaskRelation.UNKNOWN,
            children=[]
        )

    def _check_nested_structure(self, tasks: List[TaskNode]) -> bool:
        """检查是否有嵌套结构"""
        for task in tasks:
            if task.children:
                return True
        return False

    def explain_task_tree(self, tasks: List[TaskNode], indent: int = 0) -> str:
        """解释任务树结构"""
        result = []
        prefix = "  " * indent

        for task in tasks:
            relation_symbol = {
                TaskRelation.PARALLEL: "⚡",
                TaskRelation.COLLABORATIVE: "🤝",
                TaskRelation.SEQUENTIAL: "➡️",
                TaskRelation.UNKNOWN: "📋"
            }.get(task.relation, "📋")

            result.append(f"{prefix}{relation_symbol} [{task.relation.value}] {task.description}")

            if task.children:
                result.append(self.explain_task_tree(task.children, indent + 1))

        return "\n".join(result)


# 全局单例
_parser: Optional[NaturalLanguageTaskParser] = None


def get_task_parser() -> NaturalLanguageTaskParser:
    """获取任务解析器单例"""
    global _parser
    if _parser is None:
        _parser = NaturalLanguageTaskParser()
    return _parser
