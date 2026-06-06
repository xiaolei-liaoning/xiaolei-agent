"""CLI基础模块 - Agent 执行包装器（增强版）

增强:
  - 单 Agent 执行时显示步骤进度 [1/5]
  - 动画等待效果
  - 现代化的执行日志显示
"""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from cli.colors import (
    print_color, print_success, print_error, print_warning,
    print_info, CliColors
)

from cli.thinking_engine import (
    think_start, think_analyze, think_plan, think_step,
    think_log, think_complete, think_data, think_summarize,
    get_thinking_engine,
)

from cli.logging_system import (
    log_debug, log_info, log_success, log_warning, log_error
)

from cli.ui_components import ProgressBar
from cli.animated_spinner import (
    AsyncSpinner, StepCounter, print_step, print_section,
    print_status_line, CLAUDE, SUCCESS, ERROR, SUBTLE, DIM,
)

logger = logging.getLogger(__name__)


class WorkflowEngineWrapper:
    """Agent 执行包装器 — 使用 BaseAgent.run() 进行迭代思考"""

    def __init__(self):
        self._engine = None

    async def create_and_execute(self, user_request: str,
                                  chat_history: List[Dict] = None,
                                  context: Dict = None,
                                  mode: str = "single") -> Dict[str, Any]:
        """统一执行入口"""
        engine = get_thinking_engine()
        start_time = time.time()

        log_info(f"分析用户请求: {user_request[:80]}, mode={mode}")

        if mode == "workflow":
            return await self.execute_workflow_file(user_request)
        if mode == "collaborate":
            return await self._execute_collaborate(user_request, engine)

        # ── single 模式：直接跑 ──────────────────────────────────
        # 显示请求
        print(f"\n    \033[1;36m⚡ {user_request[:80]}\033[0m")

        # ── 直接执行 ──
        from core.multi_agent_v2.agents.react_core import run_react
        result = await run_react(user_request, max_rounds=0)

        elapsed = time.time() - start_time
        success = result.get("success", False)
        iterations = result.get("iterations", 1)
        final_answer = result.get("answer", "")
        tool_results = result.get("tool_results", [])

        # 显示摘要
        if tool_results:
            chain_names = []
            for tr in tool_results:
                tc = tr.get("tool_call", {})
                name = tc.get("name", "")
                ok = tr.get("success", False)
                icon = "✅" if ok else "⚠️"
                if name:
                    chain_names.append(f"{icon}{name}")
            if chain_names:
                print(f"    \033[2m工具链: {' → '.join(chain_names[:10])}\033[0m")

        print(f"    \033[1;32m{'✅' if success else '❌'} {iterations}轮 · {elapsed:.1f}s\033[0m")
        log_info(f"Agent 执行完成: success={success}, 迭代={iterations}轮, 耗时={elapsed:.1f}s")

        return {
            "success": success,
            "iterations": iterations,
            "result": final_answer,
            "error": result.get("error"),
            "total_time": elapsed,
            "agent_result": result,
            "mode": mode,
            "results": [{"step": 1, "type": "agent_run", "success": success,
                         "data_preview": str(final_answer)[:200]}],
        }

    async def _execute_collaborate(self, user_request: str,
                                    engine) -> Dict[str, Any]:
        """多 Agent 协作执行 — 使用编排引擎"""
        think_log("启动多 Agent 协作模式（编排引擎）...")

        from core.multi_agent_v2.orchestration import orchestrator as orch

        # 动态决定 Agent 数量
        agent_count = self._estimate_collab_agents(user_request)

        # 显示协作计划
        collab_plan = [
            {"title": "组建 Agent 团队", "description": f"创建 {agent_count} 个协作 Agent", "tag": "准备"},
            {"title": "并行执行", "description": f"多 Agent 并行执行各自任务", "tag": "执行"},
            {"title": "结果汇总", "description": "收集并整合各 Agent 执行结果", "tag": "汇总"},
        ]
        engine.plan_steps(collab_plan)

        try:
            # Step 1: 组建团队 + 分配子任务
            step_num = 1
            engine.start_step(step_num, f"组建 {agent_count} 个 Agent 团队")

            orch.phase("多Agent协作")

            # 生成不同的子任务维度
            dimensions = self._generate_collab_dimensions(user_request, agent_count)
            engine.complete_step(step_num, success=True,
                                detail=f"{agent_count} 个 Agent 已就绪")

            # Step 2: 并行执行
            step_num = 2
            engine.start_step(step_num, "并行执行")

            async with AsyncSpinner(f"正在并行执行 {agent_count} 个 Agent...", color=CLAUDE):
                thunks = [
                    lambda d=d, i=i: orch.agent(
                        d,
                        {"label": f"Agent_{i+1}", "timeout": 180},
                    )
                    for i, d in enumerate(dimensions)
                ]
                results = await orch.parallel(thunks, max_concurrent=agent_count)

            success_count = sum(1 for r in results if r.success)
            engine.complete_step(
                step_num,
                success=success_count > 0,
                detail=f"{success_count}/{agent_count} 成功",
            )

            # Step 3: 结果汇总
            step_num = 3
            engine.start_step(step_num, "结果汇总")

            # 取最后一个成功的结果作为主结果
            main_result = next((r for r in reversed(results) if r.success), None)
            if main_result:
                success = True
                output = main_result.text()[:500]
            else:
                success = False
                output = ""

            engine.complete_step(step_num, success=success)

            result_data = {
                "success": success,
                "result": output,
                "iterations": len(results),
                "confidence": 0.8,
                "total_time": sum(r.execution_time for r in results if hasattr(r, 'execution_time')),
                "results": [
                    {
                        "agent_id": f"Agent_{i+1}",
                        "success": r.success,
                        "output": r.text()[:300] if r.success else "",
                        "error": r.error if not r.success else None,
                        "execution_time": r.execution_time,
                    }
                    for i, r in enumerate(results)
                ],
                "agent_result": {"output": output} if main_result else {},
                "mode": "collaborate",
            }

            engine.progress_summary()
            engine.summary(success,
                          result_data["total_time"])

            return result_data

        except Exception as e:
            log_error(f"协作执行失败: {e}")
            logger.exception("Collaborate mode failed")

            if engine._current_step > 0:
                engine.complete_step(engine._current_step, success=False,
                                     error_message=str(e))
            engine.summary(False, detail=str(e))

            return {"success": False, "error": str(e), "mode": "collaborate"}

    def _estimate_collab_agents(self, user_request: str) -> int:
        """根据任务描述估算需要的协作 Agent 数量"""
        # 关键词检测
        complex_kw = ["分析", "报告", "深入", "全面", "详细", "复杂",
                      "research", "analyze", "report"]
        medium_kw = ["搜索", "查找", "对比", "评估", "创建",
                     "search", "compare", "evaluate"]

        score = 0
        for kw in complex_kw:
            if kw in user_request.lower():
                score += 2
        for kw in medium_kw:
            if kw in user_request.lower():
                score += 1

        length_bonus = min(len(user_request) // 50, 2)

        total = score + length_bonus
        if total >= 6:
            return 5
        elif total >= 4:
            return 3
        elif total >= 2:
            return 2
        return 1

    def _generate_collab_dimensions(self, user_request: str, count: int) -> list:
        """根据任务生成多个协作维度的子任务"""
        base_prompt = user_request
        if count == 1:
            return [base_prompt]

        dimensions = [
            f"搜索调研：{base_prompt}\n请搜索并收集相关信息。",
            f"分析处理：{base_prompt}\n请分析数据并提取关键信息。",
            f"生成输出：{base_prompt}\n请生成最终结果或报告。",
        ]

        if count >= 4:
            dimensions.append(f"质量审查：{base_prompt}\n请审查并优化输出质量。")
        if count >= 5:
            dimensions.append(f"综合整合：{base_prompt}\n请整合所有输出为一篇完整回答。")

        return dimensions[:count]

    async def execute_workflow_file(self, file_path: str) -> Dict[str, Any]:
        """从文件执行工作流（增强显示）"""
        from core.workflow.automation_workflow import AutomationWorkflowEngine
        engine = AutomationWorkflowEngine()
        path = Path(file_path)
        if not path.exists():
            log_error(f"文件不存在: {file_path}")
            return {"success": False, "error": f"文件不存在: {file_path}"}

        try:
            with open(str(path), "r", encoding="utf-8") as f:
                workflow = json.load(f)
        except json.JSONDecodeError as e:
            log_error(f"JSON解析失败: {e}")
            return {"success": False, "error": f"JSON解析失败: {e}"}

        think_start(f"执行工作流文件: {file_path}")
        think_analyze("工作流执行")

        steps = []
        for i, step in enumerate(workflow.get('steps', []), 1):
            action = step.get("action", step.get("type", "unknown"))
            steps.append({
                "title": action,
                "description": step.get("description", "")
            })
        think_plan(steps)

        result = await engine.execute_workflow(workflow)
        think_summarize(result.get("success", False), result)
        return result


async def display_workflow_result(result: Dict[str, Any]) -> None:
    """显示工作流执行结果 - Claude Code风格"""
    if not result.get("success"):
        print_error(result.get("error", "Execution failed"))
        log_error(result.get("error", "执行失败"))
        return

    greeting_message = result.get("greeting_message")
    if greeting_message:
        print()
        print_color(greeting_message, CliColors.CYAN)
        print()
        return

    print_success("Workflow completed")
    log_success("工作流执行完成")

    print(f"  Name: {result.get('workflow_name', 'unnamed')}")
    print(f"  Duration: {result.get('total_time', 0):.2f}s")
    print(f"  Status: {result.get('success_count', 0)}/{result.get('failed_count', 0)}")

    if result.get("report_path"):
        print(f"  Report: {result['report_path']}")
        log_info(f"报告路径: {result['report_path']}")

    results = result.get("results", [])
    if results:
        print()
        print_color("Steps:", CliColors.BOLD)
        for step_result in results:
            step_num = step_result.get("step", "?")
            step_type = step_result.get("type", "")
            duration = step_result.get("duration", 0)
            success = step_result.get("success", False)

            status = "OK" if success else "FAIL"
            status_color = CliColors.GREEN if success else CliColors.RED

            print_color(f"  [{step_num}] {step_type} - {status}", status_color)

            if duration:
                print(f"      Duration: {duration:.2f}s")

            preview = step_result.get("preview", "")
            if preview:
                for line in preview.split('\n')[:3]:
                    print(f"      {line}")

            if step_result.get("csv_path"):
                print(f"      CSV: {step_result['csv_path']}")
            if step_result.get("chart_path"):
                print(f"      Chart: {step_result['chart_path']}")


class _ChainCollector:
    """静默捕获 Agent 执行过程中的工具调用链

    实现 ThinkingTrace 接口但不输出到终端。
    用于在单 Agent 模式下捕获工具调用，
    执行完成后统一显示为"由 tool1 → tool2 → tool3" 格式。
    """

    def __init__(self):
        self._tool_chain: list = []
        self._start_time: float = 0.0

    # ── ThinkingTrace 接口 ────────────────────────────────────────

    def start(self, task_desc: str):
        self._start_time = time.time()

    def done(self, success: bool, elapsed: float = 0, detail: str = ""):
        pass

    def on_thinking(self, phase: str, detail: str = ""):
        pass

    def on_tool_call(self, tool_name: str, args: Any = None):
        """捕获工具调用名"""
        if tool_name and tool_name != "_text_reply":
            self._tool_chain.append(tool_name)

    def on_tool_result(self, text: str, max_lines: int = 3):
        pass

    def on_tool_error(self, error: str, max_lines: int = 3):
        pass

    def on_reflection(self, summary: str, success: bool = True):
        pass

    def on_iteration(self, iteration: int, reason: str = ""):
        pass

    def set_plan(self, steps: list):
        pass

    def status(self, text: str):
        pass

    def divider(self):
        pass

    def log(self, text: str, level: str = "info"):
        pass

    def on_step_start(self, step) -> None:
        pass

    def on_step_complete(self, step) -> None:
        pass

    def on_step_failed(self, step, error: str = "") -> None:
        pass

    def display_step_plan(self, steps: list):
        pass

    def display_dependency_graph(self, steps: list):
        pass

    def on_thinking_result(self, result: str):
        pass

    def on_thinking_end(self):
        pass

    # ── 提取工具调用链 ─────────────────────────────────────────────

    def get_tool_chain(self) -> list:
        """返回去重后的工具调用链（按调用顺序，但合并连续重复调用）"""
        if not self._tool_chain:
            return []

        # 合并连续重复调用
        deduped = [self._tool_chain[0]]
        for t in self._tool_chain[1:]:
            if t != deduped[-1]:
                deduped.append(t)
        return deduped[:15]  # 最多显示15个
