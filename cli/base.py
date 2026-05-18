"""CLI基础模块 - 工作流引擎包装器和辅助函数

已整合思考引擎和增强日志系统
"""

import json
from pathlib import Path
from typing import Dict, Any, List

from cli.colors import (
    print_color, print_success, print_error, print_warning,
    print_info, CliColors
)

# 导入思考引擎
from cli.thinking_engine import (
    think_start, think_analyze, think_plan, think_step,
    think_log, think_complete, think_data, think_summarize
)

# 导入日志系统
from cli.logging_system import (
    log_debug, log_info, log_success, log_warning, log_error
)

from cli.ui_components import ProgressBar


class WorkflowEngineWrapper:
    """工作流引擎包装器 - 整合思考引擎和日志"""

    def __init__(self):
        self._engine = None
        self._logger = None

    def get_engine(self):
        """懒加载工作流引擎"""
        if self._engine is None:
            from core.workflow.automation_workflow import AutomationWorkflowEngine
            self._engine = AutomationWorkflowEngine()
        return self._engine

    async def create_and_execute(self, user_request: str, chat_history: List[Dict] = None, context: Dict = None) -> Dict[str, Any]:
        """智能识别并执行工作流"""
        engine = self.get_engine()

        think_log("正在分析用户意图...")
        log_info(f"分析用户请求: {user_request[:50]}..." if len(user_request) > 50 else f"分析用户请求: {user_request}")
        
        # 如果有聊天历史，记录历史长度
        if chat_history and len(chat_history) > 0:
            think_log(f"包含 {len(chat_history)} 条对话历史")
        
        if context:
            think_log(f"上下文信息: {context}")
            log_info(f"上下文信息: {context}")
        
        result = await engine.create_smart_workflow(user_request)

        if not result.get("success"):
            log_error(f"创建工作流失败: {result.get('error', '未知错误')}")
            return {"success": False, "error": result.get("error", "创建工作流失败")}

        workflow = result["workflow"]

        if workflow['steps']:
            first_step = workflow['steps'][0]
            if first_step.get("description") == "问候语响应":
                greeting_message = first_step.get("params", {}).get("message", "")
                if greeting_message:
                    return {"success": True, "greeting_message": greeting_message}

        think_log(f"识别到工作流: {workflow['name']}")
        log_info(f"工作流名称: {workflow['name']}")
        
        think_log(f"描述: {workflow['description']}")
        think_log(f"步骤数: {len(workflow['steps'])}")

        # 规划步骤
        plan_steps = []
        for i, step in enumerate(workflow['steps'], 1):
            step_type = step.get("type", "unknown")
            action = step.get("action", step.get("site", ""))
            desc = step.get("description", "")
            plan_steps.append({
                "title": action if action else step_type,
                "description": desc
            })
            
        think_plan(plan_steps)

        if workflow.get("generate_report"):
            think_log("将生成分析报告")
            log_info("将生成分析报告")

        think_log("开始执行工作流...")
        log_info("开始执行工作流")

        # 执行工作流并跟踪步骤
        return await self._execute_with_thinking(workflow)
    
    async def _execute_with_thinking(self, workflow):
        """执行工作流并跟踪思考过程"""
        engine = self.get_engine()
        total_steps = len(workflow['steps'])
        
        progress_bar = ProgressBar(total=total_steps, width=50)
        
        # 模拟步骤执行的思考跟踪
        for step_num, step in enumerate(workflow['steps'], 1):
            step_type = step.get("type", "unknown")
            action = step.get("action", step.get("site", ""))
            
            think_step(step_num)
            think_log(f"正在执行: {action if action else step_type}")
            log_info(f"执行步骤 {step_num}/{total_steps}: {action}")
            
            progress_bar.update(step_num - 1)
        
        result = await engine.execute_workflow(workflow)
        
        progress_bar.update(total_steps)
        print()
        
        # 检查是否有步骤需要用户输入（如clarification）
        if result.get("results"):
            for step_result in result["results"]:
                if step_result.get("requires_user_input"):
                    # 返回特殊标记，表示需要用户交互
                    return {
                        "success": True,
                        "requires_user_input": True,
                        "type": "clarification",  # 添加type字段供CLI识别
                        "clarification_text": step_result.get("clarification_text", ""),
                        "original_request": step_result.get("original_request", ""),
                        "questions": step_result.get("questions", []),
                        "clarification_questions": step_result.get("questions", []),  # 兼容字段名
                    }
        
        # 完成所有步骤的思考
        for step_num in range(1, total_steps + 1):
            think_complete(step_num, success=True)
        
        # 添加结果数据
        if result.get("results"):
            for step_result in result["results"]:
                if step_result.get("data_preview"):
                    preview = step_result["data_preview"]
                    if len(preview) > 30:
                        preview = preview[:30] + "..."
                    think_data("数据预览", preview)
                if step_result.get("csv_path"):
                    think_data("CSV文件", step_result["csv_path"])
                if step_result.get("chart_path"):
                    think_data("图表文件", step_result["chart_path"])
        
        return result

    async def execute_workflow_file(self, file_path: str) -> Dict[str, Any]:
        """从文件执行工作流"""
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

        engine = self.get_engine()
        
        think_start(f"执行工作流文件: {file_path}")
        think_analyze("工作流执行")
        
        steps = []
        for i, step in enumerate(workflow.get('steps', []), 1):
            step_type = step.get("type", "unknown")
            action = step.get("action", "")
            steps.append({
                "title": action if action else step_type,
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