"""
StepPlanner - 结构化任务拆解器

将自然语言任务拆解为带依赖关系的结构化步骤列表（DAG）。
支持两条路径：
1. LLM 路径 — 使用 LLM 智能拆解（主路径）
2. 规则路径 — 基于启发式规则的兜底拆解
"""

import asyncio
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from core.multi_agent_v2.agents.base.models import (
    Step, StepStatus, StepType, Task,
)

logger = logging.getLogger(__name__)

# LLM 拆解提示词模板
SYSTEM_PROMPT = """你是一个专业任务规划师，负责将用户的任务拆解为可执行的步骤。

你需要遵循以下原则：
1. 每个步骤必须有明确的目标和产出
2. 步骤之间通过 dependencies 声明依赖关系（引用其他步骤的 step_id）
3. 无依赖的步骤可以并行执行
4. 每个步骤推荐合适的工具类型（tool_call/llm_task/search/analysis）
5. 步骤数量控制在 3-8 个之间，不要太细也不要太粗
6. 如果有明确的先后顺序，用 dependencies 表达

可用步骤类型：
- tool_call: 调用外部工具
- llm_task: LLM 直接处理
- search: 搜索/查询信息
- analysis: 分析处理数据
- human_input: 需要用户输入
- decision: 决策分支点

请以 JSON 格式输出，格式如下：
{
  "steps": [
    {
      "step_id": "step_1",
      "name": "步骤名称",
      "description": "步骤详细描述",
      "type": "search 或 tool_call 或 llm_task 或 analysis",
      "dependencies": [],  // 依赖的 step_id，无依赖填 []
      "expected_output": "预期产出描述",
      "tool_name": "推荐使用的工具名称（如果有）"
    }
  ]
}

只输出 JSON，不要额外说明。"""


class StepPlanner:
    """结构化任务拆解器"""

    def __init__(self, llm_router=None):
        self.llm_router = llm_router

    async def plan(self, task: Task, context: Optional[Dict] = None) -> List[Step]:
        """将任务拆解为结构化步骤列表

        Args:
            task: 任务定义
            context: 额外上下文（可用工具列表等）

        Returns:
            带依赖关系的结构化步骤列表
        """
        if not task.description:
            logger.warning("空任务描述，返回兜底步骤")
            return self._fallback_steps(task)

        # 主路径：LLM 拆解
        if self.llm_router:
            try:
                steps = await self.plan_with_llm(task, context)
                if steps:
                    logger.info(f"LLM 拆解成功: {len(steps)} 个步骤")
                    return self._post_process_steps(steps)
            except Exception as e:
                logger.warning(f"LLM 拆解失败: {e}")

        # 兜底：规则拆解
        steps = self.plan_with_rules(task)
        logger.info(f"规则拆解兜底: {len(steps)} 个步骤")
        return self._post_process_steps(steps)

    async def plan_with_llm(self, task: Task, context: Optional[Dict] = None) -> List[Step]:
        """使用 LLM 拆解任务"""
        if not self.llm_router:
            raise RuntimeError("LLM 不可用")

        # 构建可用工具列表提示
        tools_hint = ""
        if context and context.get("available_tools"):
            tools = context["available_tools"]
            tool_names = [t.get("name", t.get("function", {}).get("name", "?")) for t in tools[:15]]
            tools_hint = f"\n\n可用工具：\n" + "\n".join(f"- {n}" for n in tool_names)

        user_prompt = f"""任务描述：{task.description}
任务类型：{task.type or 'general'}
{tools_hint}

请将上述任务拆解为3-8个可独立执行的步骤，用 JSON 格式输出。"""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await asyncio.wait_for(
                self.llm_router.chat(messages, temperature=0.3, max_tokens=2000),
                timeout=25,
            )

            steps = self._parse_llm_response(response)
            if steps:
                logger.info(f"LLM 返回 {len(steps)} 个步骤")
                return steps

            raise ValueError("LLM 响应中未解析出有效步骤")

        except (asyncio.TimeoutError, ValueError) as e:
            logger.warning(f"LLM 拆解异常: {e}")
            raise

    def plan_with_rules(self, task: Task) -> List[Step]:
        """基于启发式规则的兜底拆解

        根据关键词将常见任务拆解为结构化步骤。
        """
        desc = task.description.lower()
        rules = [
            # ── 搜索/信息收集类 ──
            (["搜索", "查找", "查一下", "找一下", "search", "find", "lookup"], self._info_gathering_steps),
            (["爬取", "抓取", "爬虫", "scrape", "crawl"], self._web_scraping_steps),
            # ── 分析类 ──
            (["分析", "统计", "总结", "分析一下", "analyze", "analysis"], self._analysis_steps),
            (["比较", "对比", "区别", "compare", "对比分析"], self._comparison_steps),
            # ── 报告类 ──
            (["报告", "汇报", "report", "总结报告"], self._report_steps),
            # ── 代码类 ──
            (["代码", "编码", "写代码", "程序", "编程", "code", "programming"], self._coding_steps),
            (["调试", "debug", "修复", "fix", "bug"], self._debugging_steps),
            # ── 数据类 ──
            (["数据处理", "数据清洗", "转换", "transform", "process"], self._data_processing_steps),
            # ── 翻译类 ──
            (["翻译", "translate", "translation"], self._translation_steps),
        ]

        for keywords, handler in rules:
            if any(kw in desc for kw in keywords):
                base_steps = handler(task)
                if base_steps:
                    return base_steps

        # 通用兜底
        return self._generic_steps(task)

    def _post_process_steps(self, steps: List[Step]) -> List[Step]:
        """步骤后处理：ID 标准化、状态初始化、空依赖处理"""
        for step in steps:
            # 确保 step_id 合法
            if not step.step_id or not re.match(r'^[a-zA-Z0-9_-]+$', step.step_id):
                step.step_id = f"step_{uuid.uuid4().hex[:6]}"

            # 确保状态初始为 PENDING
            step.status = StepStatus.PENDING

            # 确保 dependencies 是列表
            if not isinstance(step.dependencies, list):
                step.dependencies = []

            # 设置步骤名称兜底
            if not step.name:
                step.name = step.description[:40] if step.description else f"步骤 {step.step_id}"

        # 检测循环依赖并修复
        steps = self._resolve_circular_dependencies(steps)

        return steps

    def _resolve_circular_dependencies(self, steps: List[Step]) -> List[Step]:
        """检测并修复循环依赖"""
        deps: Dict[str, Set[str]] = {}
        for s in steps:
            deps[s.step_id] = set(s.dependencies)

        changed = True
        while changed:
            changed = False
            for sid, dep_set in deps.items():
                for dep_id in list(dep_set):
                    if dep_id in deps:
                        # 传递依赖：A 依赖 B，B 依赖 C，则 A 间接依赖 C
                        new_deps = deps[dep_id] - {sid}
                        if new_deps - dep_set:
                            dep_set.update(new_deps)
                            changed = True
                            # 检测循环：如果 A 的依赖中包含 A 自己
                            if sid in dep_set:
                                dep_set.discard(sid)
                                logger.warning(f"修复循环依赖: {sid}")

        # 写回
        for step in steps:
            step.dependencies = list(deps[step.step_id])

        return steps

    def _topological_sort(self, steps: List[Step]) -> List[Step]:
        """拓扑排序步骤"""
        step_map = {s.step_id: s for s in steps}
        visited: Set[str] = set()
        result: List[Step] = []

        def dfs(sid: str, path: Set[str]) -> None:
            if sid in visited:
                return
            if sid in path:
                logger.warning(f"检测到循环依赖: {sid}")
                return
            if sid not in step_map:
                return

            path.add(sid)
            s = step_map[sid]
            for dep_id in s.dependencies:
                dfs(dep_id, path)
            path.discard(sid)

            visited.add(sid)
            if s not in result:
                result.append(s)

        for step in steps:
            dfs(step.step_id, set())

        return result

    def _find_parallel_groups(self, steps: List[Step]) -> List[List[Step]]:
        """找出可并行执行的步骤组

        返回按层级分组的步骤列表，同一层级的可并行执行。
        """
        sorted_steps = self._topological_sort(steps)
        step_map = {s.step_id: s for s in steps}
        depth: Dict[str, int] = {}

        for step in sorted_steps:
            if not step.dependencies:
                depth[step.step_id] = 0
            else:
                max_dep_depth = max(depth.get(dep, 0) for dep in step.dependencies if dep in depth)
                depth[step.step_id] = max_dep_depth + 1

        # 按深度分组
        max_depth = max(depth.values()) if depth else 0
        groups: List[List[Step]] = [[] for _ in range(max_depth + 1)]
        for step in steps:
            d = depth.get(step.step_id, 0)
            groups[d].append(step)

        return [g for g in groups if g]

    # ── 规则拆解处理器 ──────────────────────────────────────────

    def _info_gathering_steps(self, task: Task) -> List[Step]:
        return [
            Step(step_id="step_understand", name="理解需求", description=f"理解任务需求：{task.description[:100]}",
                 type=StepType.LLM_TASK, expected_output="明确搜索关键词和范围"),
            Step(step_id="step_search", name="搜索信息", description="搜索相关信息",
                 type=StepType.SEARCH, dependencies=["step_understand"],
                 expected_output="原始搜索结果"),
            Step(step_id="step_organize", name="整理结果", description="整理搜索结果",
                 type=StepType.ANALYSIS, dependencies=["step_search"],
                 expected_output="结构化整理后的信息"),
            Step(step_id="step_summarize", name="总结输出", description="总结信息并输出",
                 type=StepType.LLM_TASK, dependencies=["step_organize"],
                 expected_output="最终总结报告"),
        ]

    def _web_scraping_steps(self, task: Task) -> List[Step]:
        return [
            Step(step_id="step_analyze", name="分析目标", description="分析目标网站结构",
                 type=StepType.ANALYSIS, expected_output="网站结构分析"),
            Step(step_id="step_scrape", name="抓取数据", description="执行数据抓取",
                 type=StepType.TOOL_CALL, dependencies=["step_analyze"], tool_name="web_scraper",
                 expected_output="原始抓取数据"),
            Step(step_id="step_process", name="清洗处理", description="数据清洗与格式化",
                 type=StepType.ANALYSIS, dependencies=["step_scrape"],
                 expected_output="清洗后的结构化数据"),
        ]

    def _analysis_steps(self, task: Task) -> List[Step]:
        return [
            Step(step_id="step_collect", name="收集数据", description="收集需要分析的数据",
                 type=StepType.SEARCH, expected_output="原始数据"),
            Step(step_id="step_analyze", name="执行分析", description="对数据执行分析",
                 type=StepType.ANALYSIS, dependencies=["step_collect"],
                 expected_output="分析结果"),
            Step(step_id="step_report", name="生成报告", description="生成分析报告",
                 type=StepType.LLM_TASK, dependencies=["step_analyze"],
                 expected_output="最终分析报告"),
        ]

    def _comparison_steps(self, task: Task) -> List[Step]:
        return [
            Step(step_id="step_subject1", name="研究对象一", description="研究第一个对象",
                 type=StepType.SEARCH, expected_output="对象一的详细信息"),
            Step(step_id="step_subject2", name="研究对象二", description="研究第二个对象",
                 type=StepType.SEARCH, expected_output="对象二的详细信息"),
            Step(step_id="step_compare", name="对比分析", description="对比两个对象的异同",
                 type=StepType.ANALYSIS, dependencies=["step_subject1", "step_subject2"],
                 expected_output="对比分析结果"),
            Step(step_id="step_conclusion", name="总结结论", description="总结对比结论",
                 type=StepType.LLM_TASK, dependencies=["step_compare"],
                 expected_output="最终结论"),
        ]

    def _report_steps(self, task: Task) -> List[Step]:
        return [
            Step(step_id="step_research", name="调研资料", description="收集相关资料",
                 type=StepType.SEARCH, expected_output="相关资料"),
            Step(step_id="step_outline", name="制定大纲", description="制定报告大纲",
                 type=StepType.LLM_TASK, dependencies=["step_research"],
                 expected_output="报告大纲"),
            Step(step_id="step_write", name="撰写报告", description="撰写完整报告",
                 type=StepType.LLM_TASK, dependencies=["step_outline"],
                 expected_output="完整报告"),
            Step(step_id="step_review", name="审核修改", description="审核并修改报告",
                 type=StepType.LLM_TASK, dependencies=["step_write"],
                 expected_output="最终报告"),
        ]

    def _coding_steps(self, task: Task) -> List[Step]:
        return [
            Step(step_id="step_analyze", name="需求分析", description="分析编码需求",
                 type=StepType.LLM_TASK, expected_output="需求分析结果"),
            Step(step_id="step_design", name="方案设计", description="设计技术方案",
                 type=StepType.LLM_TASK, dependencies=["step_analyze"],
                 expected_output="技术方案"),
            Step(step_id="step_code", name="编写代码", description="编写实现代码",
                 type=StepType.TOOL_CALL, dependencies=["step_design"],
                 expected_output="代码实现"),
            Step(step_id="step_test", name="测试验证", description="测试代码功能",
                 type=StepType.TOOL_CALL, dependencies=["step_code"],
                 expected_output="测试结果"),
            Step(step_id="step_summarize", name="总结输出", description="总结编码结果",
                 type=StepType.LLM_TASK, dependencies=["step_test"],
                 expected_output="编码总结"),
        ]

    def _debugging_steps(self, task: Task) -> List[Step]:
        return [
            Step(step_id="step_reproduce", name="复现问题", description="了解并复现问题",
                 type=StepType.LLM_TASK, expected_output="问题复现步骤"),
            Step(step_id="step_diagnose", name="诊断原因", description="分析问题根因",
                 type=StepType.ANALYSIS, dependencies=["step_reproduce"],
                 expected_output="根因分析"),
            Step(step_id="step_fix", name="修复问题", description="编写修复代码",
                 type=StepType.TOOL_CALL, dependencies=["step_diagnose"],
                 expected_output="修复方案"),
            Step(step_id="step_verify", name="验证修复", description="验证修复效果",
                 type=StepType.TOOL_CALL, dependencies=["step_fix"],
                 expected_output="验证结果"),
        ]

    def _data_processing_steps(self, task: Task) -> List[Step]:
        return [
            Step(step_id="step_load", name="加载数据", description="加载原始数据",
                 type=StepType.TOOL_CALL, expected_output="加载的数据"),
            Step(step_id="step_clean", name="清洗数据", description="数据清洗与预处理",
                 type=StepType.ANALYSIS, dependencies=["step_load"],
                 expected_output="清洗后的数据"),
            Step(step_id="step_transform", name="数据转换", description="数据格式转换",
                 type=StepType.TOOL_CALL, dependencies=["step_clean"],
                 expected_output="转换后的数据"),
            Step(step_id="step_output", name="输出结果", description="输出处理结果",
                 type=StepType.LLM_TASK, dependencies=["step_transform"],
                 expected_output="最终结果"),
        ]

    def _translation_steps(self, task: Task) -> List[Step]:
        return [
            Step(step_id="step_read", name="理解原文", description="理解原文内容和语境",
                 type=StepType.LLM_TASK, expected_output="原文理解"),
            Step(step_id="step_translate", name="执行翻译", description="执行翻译",
                 type=StepType.TOOL_CALL, dependencies=["step_read"], tool_name="translator",
                 expected_output="翻译结果"),
            Step(step_id="step_polish", name="润色校对", description="润色翻译结果",
                 type=StepType.LLM_TASK, dependencies=["step_translate"],
                 expected_output="最终翻译"),
        ]

    def _generic_steps(self, task: Task) -> List[Step]:
        """通用兜底步骤"""
        return [
            Step(step_id="step_understand", name="理解任务", description=f"理解任务：{task.description[:100]}",
                 type=StepType.LLM_TASK, expected_output="任务理解"),
            Step(step_id="step_execute", name="执行任务", description="执行主要任务操作",
                 type=StepType.TOOL_CALL, dependencies=["step_understand"],
                 expected_output="执行结果"),
            Step(step_id="step_summarize", name="总结结果", description="总结执行结果并输出",
                 type=StepType.LLM_TASK, dependencies=["step_execute"],
                 expected_output="最终结果"),
        ]

    def _fallback_steps(self, task: Task) -> List[Step]:
        """最后兜底 — 当所有方法都失败时"""
        return [
            Step(step_id="step_single", name="执行任务", description=task.description or "执行用户请求",
                 type=StepType.TOOL_CALL, expected_output="执行结果"),
        ]

    # ── LLM 响应解析 ──────────────────────────────────────────

    def _parse_llm_response(self, response: str) -> List[Step]:
        """解析 LLM 响应，提取步骤列表"""
        content = response
        if isinstance(response, dict):
            content = response.get("content", "") or response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                content = json.dumps(response)

        # 尝试直接解析 JSON
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
            if isinstance(parsed, dict):
                steps_data = parsed.get("steps", [])
            elif isinstance(parsed, list):
                steps_data = parsed
            else:
                steps_data = None

            if steps_data:
                return self._steps_from_dicts(steps_data)
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试从 markdown 代码块提取
        if isinstance(content, str):
            block_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
            if block_match:
                try:
                    parsed = json.loads(block_match.group(1))
                    steps_data = parsed if isinstance(parsed, list) else parsed.get("steps", [])
                    if steps_data:
                        return self._steps_from_dicts(steps_data)
                except (json.JSONDecodeError, TypeError):
                    pass

            # 尝试提取 { } 中的 JSON
            brace_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if brace_match:
                try:
                    parsed = json.loads(brace_match.group(0))
                    steps_data = parsed.get("steps", [])
                    if steps_data:
                        return self._steps_from_dicts(steps_data)
                except (json.JSONDecodeError, TypeError):
                    pass

            # 尝试提取 [] 中的 JSON
            bracket_match = re.search(r'\[.*\]', content, re.DOTALL)
            if bracket_match:
                try:
                    parsed = json.loads(bracket_match.group(0))
                    if isinstance(parsed, list):
                        return self._steps_from_dicts(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass

        logger.warning("LLM 响应中未解析出 JSON 步骤，尝试文本行解析")
        return self._parse_text_lines(content) if isinstance(content, str) else []

    def _steps_from_dicts(self, steps_data: List[Dict]) -> List[Step]:
        """将字典列表转换为 Step 对象"""
        steps = []
        for i, sd in enumerate(steps_data):
            if not isinstance(sd, dict):
                continue
            step_id = sd.get("step_id", sd.get("id", f"step_{i+1}"))
            type_str = sd.get("type", "tool_call")
            try:
                step_type = StepType(type_str)
            except ValueError:
                step_type = StepType.TOOL_CALL

            dependencies = sd.get("dependencies", sd.get("depends_on", []))
            if isinstance(dependencies, str):
                dependencies = [dependencies]

            step = Step(
                step_id=step_id,
                name=sd.get("name", sd.get("title", f"步骤 {i+1}")),
                description=sd.get("description", sd.get("desc", "")),
                type=step_type,
                dependencies=dependencies,
                tool_name=sd.get("tool_name", sd.get("tool", "")),
                tool_args=sd.get("tool_args", sd.get("arguments", {})),
                expected_output=sd.get("expected_output", sd.get("output", "")),
                metadata={k: v for k, v in sd.items() if k not in (
                    "step_id", "id", "name", "title", "description", "desc",
                    "type", "dependencies", "depends_on", "tool_name", "tool",
                    "tool_args", "arguments", "expected_output", "output",
                    "status",
                )},
            )
            steps.append(step)

        return steps

    def _parse_text_lines(self, content: str) -> List[Step]:
        """当 JSON 解析失败时，从文本行中提取步骤"""
        lines = content.split("\n")
        steps = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("```"):
                continue
            # 匹配 "序号. 描述" 或 "- 描述" 格式
            cleaned = re.sub(r'^[\d]+[.、\)]\s*', '', line)
            cleaned = re.sub(r'^[-*]\s*', '', cleaned)
            if cleaned and len(cleaned) > 5:
                steps.append(Step(
                    step_id=f"step_{len(steps)+1}",
                    name=cleaned[:40],
                    description=cleaned,
                    type=StepType.TOOL_CALL,
                ))

        return steps
