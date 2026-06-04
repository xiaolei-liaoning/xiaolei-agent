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
SYSTEM_PROMPT = """你是一个专业任务规划师，将用户任务拆解为最少可执行步骤。

原则：
1. 最少步骤原则：用最少的步骤完成任务（通常 2-3 步），不要多余步骤
2. 每个步骤必须有具体产出，步骤名应描述具体任务（如"搜索百度热搜"而非"初始化搜索环境"）
3. 步骤名应描述具体任务（如"搜索百度热搜"），而非工具调用（如"调用 fetch_url 搜索百度热搜"）。tool_name 字段用于指定使用的工具
4. 步骤间用 dependencies 表达先后依赖
5. 只有最后一步需要 LLM 分析结果（type=llm_task），前面的步骤尽量直接调工具
6. 工具选择：优先使用 fetch_url / file / search / execute_python / execute_shell / call_api 等内置工具

JSON 格式：
{
  "steps": [
    {
      "step_id": "step_1",
      "name": "具体步骤名（如：搜索百度热搜）",
      "description": "具体做什么",
      "type": "tool_call 或 llm_task",
      "dependencies": [],
      "expected_output": "预期产出",
      "tool_name": "如果是 tool_call 必须填工具名，如 fetch_url"
    }
  ]
}
只输出 JSON。"""


class StepPlanner:
    """结构化任务拆解器"""

    def __init__(self, llm_router=None):
        self.llm_router = llm_router

    async def plan(self, task: Task, context: Optional[Dict] = None,
                   tool_registry=None, history=None) -> List[Step]:
        """将任务拆解为结构化步骤列表

        Args:
            task: 任务定义
            context: 额外上下文（可用工具列表等）
            tool_registry: 工具注册表，用于获取当前任务可用工具
            history: 历史执行记录字符串

        Returns:
            带依赖关系的结构化步骤列表
        """
        if not task.description:
            logger.warning("空任务描述，返回兜底步骤")
            return self._fallback_steps(task)

        # 处理 tool_registry：获取当前任务可用工具并注入 context
        if tool_registry:
            if context is None:
                context = {}
            try:
                tools = await tool_registry.get_tools_for_task(task.description)
                context["available_tools"] = tools
            except Exception as e:
                logger.warning(f"获取工具列表失败: {e}")

        # 处理 history：通过 context 传递给 plan_with_llm
        if history:
            if context is None:
                context = {}
            context["history"] = history

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
            # 过滤：只给 LLM 展示内置工具，不展示 MCP 工具
            builtin_names = {"fetch_url", "file", "search", "execute_python", "execute_shell", "call_api"}
            builtin_tools = [t for t in tools if hasattr(t, 'name') and t.name in builtin_names]
            # 兼容 ToolDefinition 对象（attribute）和 dict（.get）
            tool_names = []
            for t in builtin_tools[:15]:
                if hasattr(t, 'name'):
                    tool_names.append(t.name)
                elif isinstance(t, dict):
                    tool_names.append(t.get("name", t.get("function", {}).get("name", "?")))
                else:
                    tool_names.append(str(t)[:40])
            tools_hint = f"\n\n可用工具：\n" + "\n".join(f"- {n}" for n in tool_names)

        # 历史执行记录提示
        history_hint = ""
        if context and context.get("history"):
            history_hint = f"\n\n历史执行记录：{context['history']}"

        user_prompt = f"""任务描述：{task.description}
任务类型：{task.type or 'general'}
{tools_hint}
{history_hint}

请将上述任务拆解为最少可独立执行的步骤（最多 2-3 步），用 JSON 格式输出。合并所有搜索/收集为一整步，不要拆分多余步骤。"""

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

    async def replan(self, original_steps: List[Step],
                     completed_ids: List[str],
                     failed_step_id: str,
                     failed_reason: str) -> List[Step]:
        """
        局部重规划：保留已完成步骤，只修改未完成步骤
        """
        completed = [s for s in original_steps if s.step_id in completed_ids]
        remaining = [s for s in original_steps if s.step_id not in completed_ids]

        # Build summary of what's done
        done_summary = "\n".join(
            f"- [{s.step_id}] {s.name}: {str(s.result)[:200] if hasattr(s, 'result') and s.result else '已完成'}"
            for s in completed
        )

        # Build remaining summary
        remain_summary = "\n".join(
            f"- [{s.step_id}] {s.name}: {s.description[:200]}"
            for s in remaining
        )

        prompt = f"""原计划执行到步骤 [{failed_step_id}] 时失败。
失败原因：{failed_reason}

已完成步骤：
{done_summary or '(暂无)'}

剩余未完成步骤：
{remain_summary or '(无)'}

请保留已完成步骤不变，只重新规划剩余步骤。
输出格式（JSON）：
{{"steps": [每个step的 name/description/type/dependencies/expected_output]}}
只输出 JSON，不要多余解释。"""

        if self.llm_router:
            try:
                messages = [
                    {"role": "system", "content": "你是一个任务规划师，负责在任务中途调整计划。请保留已完成步骤，只修改未完成的部分。"},
                    {"role": "user", "content": prompt}
                ]
                response = await asyncio.wait_for(
                    self.llm_router.chat(messages, temperature=0.3, max_tokens=2000),
                    timeout=25,
                )
                new_remaining = self._parse_llm_response(response)
                if new_remaining:
                    # Re-number step_ids to avoid conflicts
                    for i, s in enumerate(new_remaining):
                        s.step_id = f"step_replan_{i+1}"
                        s.status = StepStatus.PENDING
                    result = completed + new_remaining
                    return self._post_process_steps(result)
            except Exception as e:
                logger.warning(f"LLM 重规划失败: {e}")

        # Fallback: keep original remaining, just reset status
        for s in remaining:
            s.status = StepStatus.PENDING
            s.error = None
        return completed + remaining

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
