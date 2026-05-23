"""CLI基础模块 - Agent 执行包装器

改用 BaseAgent.run() 实现 think → act → reflect → 迭代 的真实思考链路。
AutomationWorkflowEngine 仅作为底层工具，不再做顶层执行。
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from cli.colors import (
    print_color, print_success, print_error, print_warning,
    print_info, CliColors
)

from cli.thinking_engine import (
    think_start, think_analyze, think_plan, think_step,
    think_log, think_complete, think_data, think_summarize
)

from cli.logging_system import (
    log_debug, log_info, log_success, log_warning, log_error
)

from cli.ui_components import ProgressBar

logger = logging.getLogger(__name__)


class WorkflowEngineWrapper:
    """Agent 执行包装器 — 使用 BaseAgent.run() 进行迭代思考"""

    def __init__(self):
        self._engine = None

    async def create_and_execute(self, user_request: str, chat_history: List[Dict] = None,
                                  context: Dict = None, mode: str = "single") -> Dict[str, Any]:
        """统一执行入口

        支持三种模式：
        - single（默认）: 单 WorkerAgent 迭代执行
        - collaborate: 多 Agent 协作执行
        - workflow: 文件工作流执行

        BaseAgent.run() 内部流程:
          think() → act() → reflect() → 置信度不够 → 再 think → ... → 完成
        """
        from cli.thinking_trace import get_trace
        trace = get_trace()
        trace.start(user_request)

        think_log("正在分析用户意图...")
        log_info(f"分析用户请求: {user_request[:80]}, mode={mode}")

        if context:
            think_log(f"上下文信息: {context}")

        if mode == "workflow":
            return await self.execute_workflow_file(user_request)

        if mode == "collaborate":
            return await self._execute_collaborate(user_request, trace)

        # ── single 模式（默认）：单 WorkAgent ────────────
        from core.multi_agent_v2.agents import WorkAgent

        agent = WorkAgent(agent_id="cli-agent")
        agent.set_trace(trace)

        try:
            result = await agent.run(user_request, max_iterations=3)
        except Exception as e:
            log_error(f"Agent 执行失败: {e}")
            logger.exception("Agent run failed")
            return {"success": False, "error": str(e)}

        success = result.get("success", False)
        iterations = result.get("iterations", 1)
        confidence = result.get("confidence", 0)

        log_info(f"Agent 执行完成: success={success}, 迭代={iterations}轮, 置信度={confidence:.2f}")

        return {
            "success": success,
            "iterations": iterations,
            "confidence": confidence,
            "total_time": 0,
            "results": [{"step": 1, "type": "agent_run", "success": success,
                         "data_preview": str(result.get("result", ""))[:200]}],
            "agent_result": result,
            "mode": mode,
        }

    async def _execute_collaborate(self, user_request: str, trace) -> Dict[str, Any]:
        """多 Agent 协作执行"""
        think_log("启动多 Agent 协作模式...")

        from core.multi_agent_v2.agents import WorkAgent
        from core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler import IntelligentScheduler
        from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
        from core.multi_agent_v2.agents.base.base_agent import Task

        try:
            master = WorkAgent(agent_id="master")
            worker = WorkAgent(agent_id="worker-1")
            reviewer = WorkAgent(agent_id="reviewer")

            for a in [master, worker, reviewer]:
                a.set_trace(trace)
                await a.register()
                await a.start()

            task = Task(
                task_id=f"collab_{uuid.uuid4().hex[:8]}",
                type="general", description=user_request,
                keywords=user_request.split(),
                complexity=0.6, estimated_steps=5,
            )

            scheduler = IntelligentScheduler(get_shared_bus())
            plan = await scheduler.schedule(task)

            think_log(f"协作计划完成: {len(plan.steps) if plan else 0} 步")
            master_result = await master.execute(task)

            return {
                "success": master_result.success,
                "result": str(master_result.output)[:500] if master_result.output else "",
                "iterations": 1,
                "confidence": 0.8,
                "total_time": master_result.execution_time,
                "results": [],
                "agent_result": {"output": str(master_result.output)[:500]},
                "mode": "collaborate",
            }
        except Exception as e:
            log_error(f"协作执行失败: {e}")
            logger.exception("Collaborate mode failed")
            return {"success": False, "error": str(e), "mode": "collaborate"}

    async def execute_workflow_file(self, file_path: str) -> Dict[str, Any]:
        """从文件执行工作流（仍走 AutomationWorkflowEngine）"""
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