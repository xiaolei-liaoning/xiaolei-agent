"""CLI基础模块 - 工作流引擎包装器和辅助函数"""

import json
from pathlib import Path
from typing import Dict, Any

from cli.colors import (
    print_color, print_success, print_error, print_warning,
    print_info, CliColors
)


class WorkflowEngineWrapper:
    """工作流引擎包装器"""

    def __init__(self):
        self._engine = None

    def get_engine(self):
        """懒加载工作流引擎"""
        if self._engine is None:
            from core.automation_workflow import get_workflow_engine
            self._engine = get_workflow_engine()
        return self._engine

    async def create_and_execute(self, user_request: str) -> Dict[str, Any]:
        """智能识别并执行工作流"""
        engine = self.get_engine()

        print_info("正在分析用户意图...")
        result = engine.create_smart_workflow(user_request)

        if not result.get("success"):
            return {"success": False, "error": result.get("error", "创建工作流失败")}

        workflow = result["workflow"]

        if workflow['steps']:
            first_step = workflow['steps'][0]
            if first_step.get("description") == "问候语响应":
                greeting_message = first_step.get("params", {}).get("message", "")
                if greeting_message:
                    return {"success": True, "greeting_message": greeting_message}

        print_info(f"识别到工作流: {workflow['name']}")
        print_info(f"描述: {workflow['description']}")
        print_info(f"步骤数: {len(workflow['steps'])}")

        for i, step in enumerate(workflow['steps'], 1):
            step_type = step.get("type", "unknown")
            action = step.get("action", step.get("site", ""))
            desc = step.get("description", "")
            print(f"  {i}. [{step_type}] {action} - {desc}")

        if workflow.get("generate_report"):
            print_info("将生成分析报告")

        print()
        print_info("开始执行工作流...")

        return await engine.execute_workflow(workflow)

    async def execute_workflow_file(self, file_path: str) -> Dict[str, Any]:
        """从文件执行工作流"""
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

        try:
            with open(str(path), "r", encoding="utf-8") as f:
                workflow = json.load(f)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON解析失败: {e}"}

        engine = self.get_engine()
        return await engine.execute_workflow(workflow)


async def display_workflow_result(result: Dict[str, Any]) -> None:
    """显示工作流执行结果 - Claude Code风格"""
    if not result.get("success"):
        print_error(result.get("error", "Execution failed"))
        return

    greeting_message = result.get("greeting_message")
    if greeting_message:
        print()
        print_color(greeting_message, CliColors.CYAN)
        print()
        return

    print_success("Workflow completed")
    print(f"  Name: {result.get('workflow_name', 'unnamed')}")
    print(f"  Duration: {result.get('total_time', 0):.2f}s")
    print(f"  Status: {result.get('success_count', 0)}/{result.get('failed_count', 0)}")

    if result.get("report_path"):
        print(f"  Report: {result['report_path']}")

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
