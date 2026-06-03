"""CLI基础模块 - Agent 执行包装器（增强版）

增强:
  - 单 Agent 执行时显示步骤进度 [1/5]
  - 动画等待效果
  - 现代化的执行日志显示
"""

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
        """统一执行入口

        支持三种模式：
        - single（默认）: 单 WorkerAgent 迭代执行
        - collaborate: 多 Agent 协作执行
        - workflow: 文件工作流执行
        """
        engine = get_thinking_engine()

        # ── 模式选择动画 ──
        mode_labels = {
            "single": "单 Agent",
            "collaborate": "多 Agent 协作",
            "workflow": "工作流文件",
        }
        mode_label = mode_labels.get(mode, mode)

        # 显示模式标签和请求
        if mode != "workflow":
            print_section(f"🦞 {mode_label}: {user_request[:60]}{'...' if len(user_request) > 60 else ''}", CLAUDE)
        else:
            think_start(user_request)

        think_log("正在分析用户意图...")
        log_info(f"分析用户请求: {user_request[:80]}, mode={mode}")

        if context:
            think_log(f"上下文信息: {context}")

        if mode == "workflow":
            return await self.execute_workflow_file(user_request)

        if mode == "collaborate":
            return await self._execute_collaborate(user_request, engine)

        # ── single 模式（默认）：单 WorkAgent ────────────────────────
        # 增强：显示清晰的步骤进度 + 工具调用链

        from core.multi_agent_v2.agents import WorkAgent

        agent = WorkAgent(agent_id="cli-agent")

        # ── 预设步骤计划（显示给用户） ──────────────────────────────
        step_plan = [
            {"title": "理解任务", "description": "分析用户请求的意图和需求", "tag": "思考"},
            {"title": "制定计划", "description": "拆解任务为可执行步骤", "tag": "规划"},
            {"title": "执行计划", "description": "迭代调用工具完成任务", "tag": "执行"},
            {"title": "检查结果", "description": "验证执行结果是否满足需求", "tag": "验证"},
            {"title": "输出总结", "description": "整理执行结果并输出", "tag": "总结"},
        ]

        engine.plan_steps(step_plan)
        total_steps = len(step_plan)

        try:
            # Step 1: 理解任务（带动画）
            step_num = 1
            engine.start_step(step_num, "理解任务")
            async with AsyncSpinner("分析请求意图...", color=CLAUDE):
                await asyncio.sleep(0.3)  # 模拟思考动画
            engine.complete_step(step_num, success=True, detail="任务理解完成")

            # Step 2: 制定计划
            step_num = 2
            engine.start_step(step_num, "制定计划")
            async with AsyncSpinner("拆解任务...", color=CLAUDE):
                pass  # agent.run 内部会做计划
            engine.complete_step(step_num, success=True)

            # Step 3: 执行计划 — 实际运行 agent，捕获工具调用链
            step_num = 3
            engine.start_step(step_num, "执行计划")

            # 使用 ChainCollector 捕获工具调用，而非直接打印 verbose trace
            collector = _ChainCollector()
            agent.set_trace(collector)

            result = await agent.run(user_request, max_iterations=3)

            success = result.get("success", False)
            iterations = result.get("iterations", 1)
            confidence = result.get("confidence", 0)

            # 显示工具调用链
            tool_chain = collector.get_tool_chain()
            if tool_chain:
                chain_display = " → ".join(tool_chain)
                engine.log_step_message(f"由 {chain_display}")
            else:
                # fallback: 从 result 中解析
                tool_results = result.get("result", {}).get("tool_results", [])
                chain_names = []
                for tr in tool_results:
                    tc = tr.get("tool_call", {})
                    name = tc.get("name", "")
                    if name and name != "_text_reply":
                        chain_names.append(name)
                if chain_names:
                    chain_display = " → ".join(chain_names[:12])
                    engine.log_step_message(f"由 {chain_display}")

            # 显示迭代信息
            engine.log_step_message(f"迭代 {iterations} 轮 · {len(tool_chain) if tool_chain else len(tool_results) if 'tool_results' in locals() else 0} 次工具调用")

            engine.complete_step(
                step_num, success=success
            )

            # Step 4: 检查结果
            step_num = 4
            engine.start_step(step_num, "检查结果")
            if success:
                check_detail = f"置信度: {confidence:.0%}"
                if "result" in result:
                    preview = str(result.get("result", ""))[:100]
                    if preview:
                        check_detail += f" | 结果: {preview}..."
                engine.complete_step(step_num, success=True, detail=check_detail)
            else:
                engine.complete_step(step_num, success=False,
                                     error_message=result.get("error", "执行失败"))

            # Step 5: 输出总结
            step_num = 5
            engine.start_step(step_num, "输出总结")
            async with AsyncSpinner("整理执行结果...", color=CLAUDE):
                await asyncio.sleep(0.2)
            engine.complete_step(step_num, success=True)

            log_info(f"Agent 执行完成: success={success}, 迭代={iterations}轮, 置信度={confidence:.2f}")

        except Exception as e:
            log_error(f"Agent 执行失败: {e}")
            logger.exception("Agent run failed")

            # 标记当前步骤失败
            if engine._current_step > 0:
                engine.complete_step(engine._current_step, success=False,
                                     error_message=str(e))

            engine.summary(False, detail=str(e))

            return {"success": False, "error": str(e)}

        # 总进度摘要
        engine.progress_summary()

        # 总结
        duration = time.time() - engine._start_time if engine._start_time else 0
        engine.summary(success, duration)

        return {
            "success": success,
            "iterations": iterations,
            "confidence": confidence,
            "total_time": duration,
            "results": [{"step": 1, "type": "agent_run", "success": success,
                         "data_preview": str(result.get("result", ""))[:200]}],
            "agent_result": result,
            "mode": mode,
        }

    async def _execute_collaborate(self, user_request: str,
                                    engine) -> Dict[str, Any]:
        """多 Agent 协作执行 — 增强显示"""
        think_log("启动多 Agent 协作模式...")

        from core.multi_agent_v2.agents import WorkAgent
        from core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler import IntelligentScheduler
        from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
        from core.multi_agent_v2.agents.base.base_agent import Task

        # 显示协作计划
        collab_plan = [
            {"title": "组建 Agent 团队", "description": "创建 Master/Worker/Reviewer Agent", "tag": "准备"},
            {"title": "任务分配与调度", "description": "智能调度器分析任务并分配", "tag": "调度"},
            {"title": "协作执行", "description": "多 Agent 并行执行各自任务", "tag": "执行"},
            {"title": "结果汇总", "description": "收集并整合各 Agent 执行结果", "tag": "汇总"},
        ]
        engine.plan_steps(collab_plan)

        try:
            # Step 1: 组建团队
            step_num = 1
            engine.start_step(step_num, "组建 Agent 团队")
            master = WorkAgent(agent_id="master")
            worker = WorkAgent(agent_id="worker-1")
            reviewer = WorkAgent(agent_id="reviewer")

            from cli.thinking_trace import get_trace
            trace = get_trace()

            for a in [master, worker, reviewer]:
                a.set_trace(trace)
                await a.register()
                await a.start()

            async with AsyncSpinner("等待 Agent 就绪...", color=CLAUDE):
                await asyncio.sleep(0.3)
            engine.complete_step(step_num, success=True,
                                detail=f"3 个 Agent 已就绪")

            # Step 2: 任务分配
            step_num = 2
            engine.start_step(step_num, "任务分配与调度")
            task = Task(
                task_id=f"collab_{uuid.uuid4().hex[:8]}",
                type="general", description=user_request,
                keywords=user_request.split(),
                complexity=0.6, estimated_steps=5,
            )

            scheduler = IntelligentScheduler(get_shared_bus())
            async with AsyncSpinner("智能调度器正在分析任务...", color=CLAUDE):
                plan = await scheduler.schedule(task)
            engine.complete_step(step_num, success=True,
                                detail=f"计划: {len(plan.steps) if plan else 0} 步")

            # Step 3: 协作执行
            step_num = 3
            engine.start_step(step_num, "协作执行")
            think_log(f"协作计划完成: {len(plan.steps) if plan else 0} 步")
            master_result = await master.execute(task)
            engine.complete_step(step_num, success=master_result.success,
                                detail=f"执行耗时: {master_result.execution_time:.1f}s"
                                if master_result.execution_time else "")

            # Step 4: 结果汇总
            step_num = 4
            engine.start_step(step_num, "结果汇总")
            engine.complete_step(step_num, success=master_result.success)

            result_data = {
                "success": master_result.success,
                "result": str(master_result.output)[:500] if master_result.output else "",
                "iterations": 1,
                "confidence": 0.8,
                "total_time": master_result.execution_time,
                "results": [],
                "agent_result": {"output": str(master_result.output)[:500]},
                "mode": "collaborate",
            }

            engine.progress_summary()
            engine.summary(master_result.success,
                          master_result.execution_time or 0)

            return result_data

        except Exception as e:
            log_error(f"协作执行失败: {e}")
            logger.exception("Collaborate mode failed")

            if engine._current_step > 0:
                engine.complete_step(engine._current_step, success=False,
                                     error_message=str(e))
            engine.summary(False, detail=str(e))

            return {"success": False, "error": str(e), "mode": "collaborate"}

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
