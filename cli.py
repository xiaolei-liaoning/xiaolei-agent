#!/usr/bin/env python3
"""小雷版小龙虾 AI Agent - 命令行接口

工业级全系统GUI自动化CLI工具：

【自动化功能覆盖】
├── 应用控制 (所有软件)
│   - 打开/关闭/激活任意应用
│   - 列出运行中的应用
├── 文件操作
│   - 打开文件/文件夹
│   - 创建/删除文件
├── 键盘控制
│   - 输入文字、快捷键、单键操作
│   - 按住/释放按键
├── 鼠标控制
│   - 点击、双击、右键
│   - 移动、拖拽、滚动
├── 窗口控制
│   - 最小化/最大化/全屏/关闭
│   - 调整大小、移动位置、切换窗口
├── 系统控制
│   - 音量、亮度、通知
│   - 锁屏、睡眠、重启、关机
├── 文本操作
│   - 复制、粘贴、剪切
│   - 全选、撤销、重做
│   - 查找、替换文字
├── 截图功能
│   - 全屏截图、区域截图

【特色功能】
- 智能意图识别 → 自动创建工作流
- 微信消息自动发送
- 数据爬取与分析
- 工作流执行与监控

示例:
  # 智能工作流
  ./cli.py smart "帮我爬取微博热搜并生成词云分析报告"
  
  # 应用控制
  ./cli.py automate open_app --app "微信"
  ./cli.py automate activate_app --app "Safari"
  ./cli.py automate quit_app --app "Terminal"
  ./cli.py automate list_apps
  
  # 文件操作
  ./cli.py automate open_file --path "/Users/user/Documents/report.pdf"
  ./cli.py automate open_folder --path "/Users/user/Downloads"
  ./cli.py automate create_file --path "/tmp/note.txt" --content "Hello"
  
  # 键盘操作
  ./cli.py automate type --text "Hello World"
  ./cli.py automate hotkey --keys "command c"
  ./cli.py automate key_down --key "shift"
  
  # 鼠标操作
  ./cli.py automate click --x 500 --y 300
  ./cli.py automate double_click --x 100 --y 200
  ./cli.py automate mouse_drag --x 100 --y 100 --to-x 400 --to-y 300
  
  # 窗口操作
  ./cli.py automate window_minimize
  ./cli.py automate window_maximize
  ./cli.py automate window_resize --width 800 --height 600
  ./cli.py automate window_switch --direction next
  
  # 系统控制
  ./cli.py automate volume --level 70
  ./cli.py automate brightness --level 80
  ./cli.py automate notification --title "提醒" --message "任务完成"
  ./cli.py automate lock
  
  # 文本操作
  ./cli.py automate select_all
  ./cli.py automate copy
  ./cli.py automate paste
  ./cli.py automate undo
  
  # 截图
  ./cli.py automate screenshot
  ./cli.py automate capture_region --x 100 --y 100 --width 400 --height 300
  
  # 微信消息
  ./cli.py wechat send --friend "张三" --message "你好！"
  
  # 爬虫与分析
  ./cli.py scrape 微博 --action "热搜top10"
  ./cli.py analyze 可视化 --chart-type wordcloud
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    from core.execution_logger import ExecutionLogger, get_execution_logger, ExecutionStatus
    from core.auto_reviewer import AutoReviewer, get_auto_reviewer
    from core.skill_extractor import SkillExtractor, get_skill_extractor
except ImportError:
    ExecutionLogger = None
    get_execution_logger = None
    ExecutionStatus = None
    AutoReviewer = None
    get_auto_reviewer = None
    SkillExtractor = None
    get_skill_extractor = None

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


class CliColors:
    """终端颜色常量 - Claude Code风格"""
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    GRAY = '\033[90m'
    BRIGHT_BLUE = '\033[38;5;75m'
    BRIGHT_CYAN = '\033[38;5;45m'
    BRIGHT_MAGENTA = '\033[38;5;213m'


def print_color(text: str, color: str = "") -> None:
    """带颜色打印"""
    if color:
        print(f"{color}{text}{CliColors.ENDC}")
    else:
        print(text)


def print_success(message: str) -> None:
    """打印成功消息"""
    print_color(f"  Success: {message}", CliColors.GREEN)


def print_error(message: str) -> None:
    """打印错误消息"""
    print_color(f"  Error: {message}", CliColors.RED)


def print_warning(message: str) -> None:
    """打印警告消息"""
    print_color(f"  Warning: {message}", CliColors.YELLOW)


def print_info(message: str) -> None:
    """打印信息消息"""
    print_color(f"  {message}", CliColors.CYAN)


def print_header(title: str) -> None:
    """打印标题 - Claude Code风格"""
    print()
    print_color(f"  {title}", CliColors.BRIGHT_BLUE + CliColors.BOLD)
    print_color(f"  {'─' * 50}", CliColors.GRAY)
    print()


def print_section(title: str) -> None:
    """打印小节标题"""
    print()
    print_color(f"  {title}", CliColors.CYAN + CliColors.BOLD)


def print_section_end() -> None:
    """打印小节结束"""
    print()


def print_chat_bubble(text: str, is_user: bool = False, timestamp: str = "") -> None:
    """打印聊天气泡 - Claude Code风格"""
    if not text or not text.strip():
        text = "(empty)"

    lines = text.split('\n')

    if is_user:
        print_color(f"\n  [You] {timestamp if timestamp else ''}", CliColors.GREEN + CliColors.BOLD)
        for line in lines:
            print_color(f"  {line}", CliColors.WHITE)
    else:
        print_color(f"\n  [Agent] {timestamp if timestamp else ''}", CliColors.BRIGHT_BLUE + CliColors.BOLD)
        for line in lines:
            print_color(f"  {line}", CliColors.CYAN)


# ============================================================================
# 辅助函数
# ============================================================================

async def _display_workflow_result(result: Dict[str, Any]) -> None:
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
            print_color(f"  [{status}] Step {step_num} [{step_type}] ({duration:.3f}s)", status_color)

            if not success and step_result.get("error"):
                print_color(f"      Error: {step_result['error']}", CliColors.RED)

            if step_result.get("data_preview"):
                preview = step_result["data_preview"]
                if len(preview) > 100:
                    preview = preview[:100] + "..."
                print(f"      Preview: {preview}")

            if step_result.get("csv_path"):
                print(f"      CSV: {step_result['csv_path']}")
            if step_result.get("chart_path"):
                print(f"      Chart: {step_result['chart_path']}")


# ============================================================================
# 工作流引擎包装器
# ============================================================================

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
        
        # 创建智能工作流
        print_info("正在分析用户意图...")
        result = engine.create_smart_workflow(user_request)
        
        if not result.get("success"):
            return {"success": False, "error": result.get("error", "创建工作流失败")}
        
        workflow = result["workflow"]
        
        # 检查是否是问候语响应
        if workflow['steps']:
            first_step = workflow['steps'][0]
            if first_step.get("description") == "问候语响应":
                greeting_message = first_step.get("params", {}).get("message", "")
                if greeting_message:
                    return {"success": True, "greeting_message": greeting_message}
        
        # 显示工作流信息
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
        
        # 执行工作流
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


# ============================================================================
# 命令处理函数
# ============================================================================

async def handle_smart(args):
    """处理智能工作流命令"""
    print_header("智能工作流执行")
    
    if not args.request:
        print_error("请提供用户请求")
        return
    
    wrapper = WorkflowEngineWrapper()
    result = await wrapper.create_and_execute(args.request)
    
    await _display_workflow_result(result)


async def handle_workflow_run(args):
    """处理工作流运行命令"""
    print_header("执行工作流文件")
    
    if not args.file:
        print_error("请提供工作流文件路径")
        return
    
    wrapper = WorkflowEngineWrapper()
    result = await wrapper.execute_workflow_file(args.file)
    
    await _display_workflow_result(result)


async def handle_workflow_list(args):
    """列出可用工作流模板"""
    print_header("工作流模板列表")
    
    workflows_dir = Path("skills") / "workflows"
    if workflows_dir.exists():
        for item in workflows_dir.rglob("*.json"):
            rel_path = item.relative_to(workflows_dir)
            print(f"  • {rel_path}")
    else:
        print_warning("工作流目录不存在")


async def handle_workflow_save(args):
    """保存工作流到文件"""
    print_header("保存工作流")
    
    if not args.request:
        print_error("请提供用户请求")
        return
    
    wrapper = WorkflowEngineWrapper()
    engine = wrapper.get_engine()
    
    result = engine.create_smart_workflow(args.request)
    if not result.get("success"):
        print_error(result.get("error", "创建失败"))
        return
    
    workflow = result["workflow"]
    
    filename = args.output or f"workflow_{workflow['name']}.json"
    filepath = Path(filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)
    
    print_success(f"工作流已保存到: {filepath.absolute()}")


# ============================================================================
# GUI自动化增强命令
# ============================================================================

async def handle_automate(args):
    """处理自动化命令"""
    action = args.action
    
    if action == "script":
        await _handle_automate_script(args)
    elif action == "macro":
        await _handle_automate_macro(args)
    else:
        await _handle_automate_single(args)


async def _handle_automate_single(args):
    """处理单个自动化操作 - 支持全系统软件控制"""
    print_header(f"GUI自动化 - {args.action}")
    
    action = args.action
    
    # ========== 特殊处理: 列出运行中的应用 ==========
    if action == "list_apps":
        await _handle_list_apps()
        return
    
    params = {}
    
    # ========== 应用操作 ==========
    if action == "open_app":
        if not args.app:
            print_error("请指定应用名称 --app")
            return
        params["app"] = args.app
    
    elif action == "quit_app":
        if not args.app:
            print_error("请指定应用名称 --app")
            return
        params["app"] = args.app
    
    elif action == "activate_app":
        if not args.app:
            print_error("请指定应用名称 --app")
            return
        params["app"] = args.app
    
    elif action == "list_apps":
        action = "list_running_apps"
    
    # ========== 文件操作 ==========
    elif action == "open_file":
        if not args.path:
            print_error("请指定文件路径 --path")
            return
        params["path"] = args.path
    
    elif action == "open_folder":
        if not args.path:
            print_error("请指定文件夹路径 --path")
            return
        params["path"] = args.path
    
    elif action == "create_file":
        if not args.path:
            print_error("请指定文件路径 --path")
            return
        params["path"] = args.path
        params["content"] = args.content or ""
    
    elif action == "delete_file":
        if not args.path:
            print_error("请指定文件路径 --path")
            return
        params["path"] = args.path
    
    # ========== 浏览器操作 ==========
    elif action == "open_url":
        if not args.url:
            print_error("请指定URL --url")
            return
        params["url"] = args.url
    
    # ========== 通知 ==========
    elif action == "notification":
        params["title"] = args.title or "小雷版小龙虾"
        params["message"] = args.message or ""
    
    # ========== 截图 ==========
    elif action == "screenshot":
        params["name"] = args.name or f"screenshot_{args.name}"
        if args.delay:
            params["delay"] = args.delay
    
    elif action == "capture_region":
        if args.x is None or args.y is None:
            print_error("请指定区域坐标 --x --y")
            return
        params["x"] = args.x
        params["y"] = args.y
        params["width"] = args.width or 400
        params["height"] = args.height or 300
    
    # ========== 等待 ==========
    elif action == "wait":
        params["seconds"] = args.seconds or 1
    
    # ========== 系统控制 ==========
    elif action == "volume":
        params["level"] = args.level or 50
    
    elif action == "brightness":
        params["level"] = args.level or 70
    
    elif action == "sleep":
        pass
    
    elif action == "restart":
        pass
    
    elif action == "shutdown":
        pass
    
    elif action == "lock":
        pass
    
    # ========== 剪贴板操作 ==========
    elif action == "clipboard":
        if args.set:
            params["text"] = args.set
            action = "set_clipboard"
        else:
            action = "get_clipboard"
    
    # ========== 键盘操作 ==========
    elif action == "type":
        if not args.text:
            print_error("请指定输入文字 --text")
            return
        params["text"] = args.text
        if args.delay:
            params["delay"] = args.delay
        action = "type_text"
    
    elif action == "hotkey":
        if not args.keys:
            print_error("请指定快捷键 --keys（如: 'command c'）")
            return
        params["keys"] = args.keys.split()
        action = "hotkey"
    
    elif action == "key_press":
        if not args.key:
            print_error("请指定按键 --key")
            return
        params["key"] = args.key
    
    elif action == "key_down":
        if not args.key:
            print_error("请指定按键 --key")
            return
        params["key"] = args.key
    
    elif action == "key_up":
        if not args.key:
            print_error("请指定按键 --key")
            return
        params["key"] = args.key
    
    # ========== 鼠标操作 ==========
    elif action == "click":
        if args.x is None or args.y is None:
            print_error("请指定坐标 --x --y")
            return
        params["x"] = args.x
        params["y"] = args.y
        params["button"] = args.button or "left"
    
    elif action == "double_click":
        if args.x is None or args.y is None:
            print_error("请指定坐标 --x --y")
            return
        params["x"] = args.x
        params["y"] = args.y
    
    elif action == "right_click":
        if args.x is None or args.y is None:
            print_error("请指定坐标 --x --y")
            return
        params["x"] = args.x
        params["y"] = args.y
    
    elif action == "scroll":
        params["direction"] = args.direction or "down"
        params["amount"] = args.amount or 100
    
    elif action == "mouse_move":
        if args.x is None or args.y is None:
            print_error("请指定坐标 --x --y")
            return
        params["x"] = args.x
        params["y"] = args.y
    
    elif action == "mouse_drag":
        if args.x is None or args.y is None or args.to_x is None or args.to_y is None:
            print_error("请指定起始坐标 --x --y 和目标坐标 --to-x --to-y")
            return
        params["x"] = args.x
        params["y"] = args.y
        params["to_x"] = args.to_x
        params["to_y"] = args.to_y
    
    # ========== 窗口操作 ==========
    elif action == "window_minimize":
        pass
    
    elif action == "window_maximize":
        pass
    
    elif action == "window_fullscreen":
        pass
    
    elif action == "window_close":
        pass
    
    elif action == "window_switch":
        params["direction"] = args.direction or "next"
    
    elif action == "window_resize":
        if args.width is None or args.height is None:
            print_error("请指定窗口尺寸 --width --height")
            return
        params["width"] = args.width
        params["height"] = args.height
    
    elif action == "window_move":
        if args.x is None or args.y is None:
            print_error("请指定窗口位置 --x --y")
            return
        params["x"] = args.x
        params["y"] = args.y
    
    elif action == "window_focus":
        if args.app:
            params["app"] = args.app
    
    # ========== 文本操作 ==========
    elif action == "find_text":
        if not args.text:
            print_error("请指定查找文字 --text")
            return
        params["text"] = args.text
    
    elif action == "replace_text":
        if not args.find or not args.replace:
            print_error("请指定查找文字 --find 和替换文字 --replace")
            return
        params["find"] = args.find
        params["replace"] = args.replace
    
    elif action == "select_all":
        action = "hotkey"
        params["keys"] = ["command", "a"]
    
    elif action == "copy":
        action = "hotkey"
        params["keys"] = ["command", "c"]
    
    elif action == "paste":
        action = "hotkey"
        params["keys"] = ["command", "v"]
    
    elif action == "cut":
        action = "hotkey"
        params["keys"] = ["command", "x"]
    
    elif action == "undo":
        action = "hotkey"
        params["keys"] = ["command", "z"]
    
    elif action == "redo":
        action = "hotkey"
        params["keys"] = ["command", "shift", "z"]
    
    else:
        print_error(f"未知操作: {action}")
        return
    
    # 创建工作流并执行
    workflow = {
        "name": f"CLI自动化_{action}",
        "description": f"CLI触发的{action}操作",
        "steps": [{
            "type": "automate",
            "action": action,
            "params": params,
            "description": f"执行{action}"
        }],
        "generate_report": False
    }
    
    wrapper = WorkflowEngineWrapper()
    result = await wrapper.get_engine().execute_workflow(workflow)
    
    await _display_workflow_result(result)


async def _handle_automate_script(args):
    """处理自动化脚本（多步骤操作）"""
    print_header("GUI自动化 - 执行脚本")
    
    if not args.file:
        print_error("请提供脚本文件路径 --file")
        return
    
    script_path = Path(args.file)
    if not script_path.exists():
        print_error(f"脚本文件不存在: {args.file}")
        return
    
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            script_data = json.load(f)
    except json.JSONDecodeError as e:
        print_error(f"JSON解析失败: {e}")
        return
    
    # 构建工作流
    workflow = {
        "name": f"脚本_{script_path.stem}",
        "description": f"从脚本执行的自动化操作",
        "steps": [],
        "generate_report": False
    }
    
    for step_data in script_data.get("steps", []):
        step = {
            "type": "automate",
            "action": step_data.get("action", ""),
            "params": step_data.get("params", {}),
            "description": step_data.get("description", "")
        }
        workflow["steps"].append(step)
    
    print_info(f"脚本包含 {len(workflow['steps'])} 个步骤")
    for i, step in enumerate(workflow["steps"], 1):
        print(f"  {i}. [{step['action']}] {step.get('description', '')}")
    
    wrapper = WorkflowEngineWrapper()
    result = await wrapper.get_engine().execute_workflow(workflow)
    
    await _display_workflow_result(result)


async def _handle_automate_macro(args):
    """处理预设宏操作"""
    print_header("GUI自动化 - 预设宏")
    
    macro_name = args.name
    
    macros = {
        "open_browser": [
            {"action": "open_app", "params": {"app": "Safari"}, "description": "打开Safari"},
            {"action": "wait", "params": {"seconds": 2}, "description": "等待启动"},
        ],
        "close_all": [
            {"action": "hotkey", "params": {"keys": ["command", "option", "h"]}, "description": "隐藏所有窗口"},
        ],
        "save_all": [
            {"action": "hotkey", "params": {"keys": ["command", "option", "s"]}, "description": "保存所有"},
        ],
        "screenshot_save": [
            {"action": "screenshot", "params": {"name": "screenshot.png"}, "description": "截图"},
            {"action": "notification", "params": {"title": "截图完成", "message": "截图已保存到桌面"}, "description": "发送通知"},
        ],
        "clean_desktop": [
            {"action": "hotkey", "params": {"keys": ["command", "f3"]}, "description": "显示桌面"},
            {"action": "hotkey", "params": {"keys": ["command", "a"]}, "description": "全选"},
            {"action": "hotkey", "params": {"keys": ["command", "delete"]}, "description": "删除"},
        ],
    }
    
    if macro_name not in macros:
        print_error(f"未知宏: {macro_name}")
        print("可用宏: " + ", ".join(macros.keys()))
        return
    
    # 构建工作流
    workflow = {
        "name": f"宏_{macro_name}",
        "description": f"执行预设宏: {macro_name}",
        "steps": [],
        "generate_report": False
    }
    
    for step_data in macros[macro_name]:
        workflow["steps"].append({
            "type": "automate",
            "action": step_data["action"],
            "params": step_data["params"],
            "description": step_data["description"]
        })
    
    print_info(f"宏 '{macro_name}' 包含 {len(workflow['steps'])} 个步骤")
    for i, step in enumerate(workflow["steps"], 1):
        print(f"  {i}. [{step['action']}] {step['description']}")
    
    wrapper = WorkflowEngineWrapper()
    result = await wrapper.get_engine().execute_workflow(workflow)
    
    await _display_workflow_result(result)


# ============================================================================
# 微信消息发送命令
# ============================================================================

async def handle_wechat(args):
    """处理微信消息发送命令"""
    action = args.action
    
    if action == "send":
        await _handle_wechat_send(args)
    elif action == "list":
        await _handle_wechat_list(args)
    else:
        print_error(f"未知微信操作: {action}")


async def _handle_wechat_send(args):
    """处理微信发送消息"""
    print_header("微信消息发送")
    
    if not args.friend:
        print_error("请指定好友名称 --friend")
        return
    
    if not args.message:
        print_error("请指定消息内容 --message")
        return
    
    friend_name = args.friend
    message = args.message
    delay = args.delay or 1
    
    print_info(f"📤 准备发送消息给: {friend_name}")
    print_info(f"📝 消息内容: {message}")
    print_info(f"⏱️  延迟: {delay}秒")
    
    import subprocess
    import time
    import os
    import tempfile
    import threading
    
    screenshot_path = None
    
    def cleanup_screenshot():
        time.sleep(10)
        if screenshot_path and os.path.exists(screenshot_path):
            os.remove(screenshot_path)
            print_info(f"🗑️  截图已自动删除: {screenshot_path}")
    
    subprocess.run(['open', '-a', 'WeChat'])
    time.sleep(delay)
    
    script1 = 'tell application "System Events" to tell application process "WeChat" to keystroke "f" using command down'
    subprocess.run(['osascript', '-e', script1])
    time.sleep(0.5)
    
    script2 = f'tell application "System Events" to tell application process "WeChat" to keystroke "{friend_name}"'
    subprocess.run(['osascript', '-e', script2])
    time.sleep(0.8)
    
    script3 = 'tell application "System Events" to tell application process "WeChat" to keystroke return'
    subprocess.run(['osascript', '-e', script3])
    time.sleep(1.5)
    
    subprocess.run(['pbcopy'], input=message.encode('utf-8'))
    time.sleep(0.2)
    
    script4 = 'tell application "System Events" to tell application process "WeChat" to keystroke "v" using command down'
    subprocess.run(['osascript', '-e', script4])
    time.sleep(0.3)
    
    script5 = 'tell application "System Events" to tell application process "WeChat" to keystroke return'
    subprocess.run(['osascript', '-e', script5])
    time.sleep(1.0)
    
    screenshot_path = os.path.join(tempfile.gettempdir(), f"wechat_send_{int(time.time())}.png")
    screenshot_cmd = ['screencapture', '-x', screenshot_path]
    subprocess.run(screenshot_cmd, timeout=5)
    
    if os.path.exists(screenshot_path):
        print_info(f"📸 截图已保存: {screenshot_path}")
        
        try:
            from PIL import Image
            import pytesseract
            
            img = Image.open(screenshot_path)
            text = pytesseract.image_to_string(img, lang='chi_sim')
            
            print_info(f"🔍 OCR识别结果: {text[:100]}...")
            
            if message in text:
                print_success("✅ AI验证通过：消息已成功发送！")
            else:
                print_warning("⚠️  AI验证警告：未在截图中检测到消息内容")
                
        except ImportError:
            print_warning("⚠️  PIL或pytesseract未安装，跳过AI验证")
        except Exception as e:
            print_error(f"❌ OCR识别失败: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_screenshot, daemon=True)
        cleanup_thread.start()
    else:
        print_warning("⚠️  截图保存失败")
    
    print_success(f"✅ 消息发送完成！")
    print(f"   📤 收件人: {friend_name}")
    print(f"   📝 消息内容: {message}")
    return


async def _handle_wechat_list(args):
    """列出微信好友（演示功能）"""
    print_header("微信好友列表")
    print_warning("⚠️  此功能需要额外权限，当前仅展示示例")
    print("\n常用操作提示:")
    print("  • 使用 --friend 参数指定好友名称")
    print("  • 支持备注名或昵称匹配")
    print("  • 示例: ./cli.py wechat send --friend \"张三\" --message \"你好\"")


# ============================================================================
# 其他命令处理函数
# ============================================================================

async def handle_scrape(args):
    """处理爬虫命令"""
    print_header(f"数据爬取 - {args.site}")
    
    workflow = {
        "name": f"爬虫_{args.site}",
        "description": f"爬取{args.site}数据",
        "steps": [{
            "type": "scrape",
            "site": args.site,
            "action": args.action or "热搜top10",
            "description": f"爬取{args.site}{args.action}"
        }],
        "generate_report": args.report
    }
    
    wrapper = WorkflowEngineWrapper()
    result = await wrapper.get_engine().execute_workflow(workflow)
    
    await _display_workflow_result(result)


async def handle_analyze(args):
    """处理分析命令"""
    print_header(f"数据分析 - {args.action}")
    
    workflow = {
        "name": f"分析_{args.action}",
        "description": f"{args.action}分析",
        "steps": [{
            "type": "analyze",
            "action": args.action,
            "params": {"chart_type": args.chart_type} if args.chart_type else {},
            "description": f"执行{args.action}分析"
        }],
        "generate_report": args.report
    }
    
    if args.file:
        workflow["steps"][0]["params"]["file_path"] = args.file
    
    wrapper = WorkflowEngineWrapper()
    result = await wrapper.get_engine().execute_workflow(workflow)
    
    await _display_workflow_result(result)


async def handle_report(args):
    """处理报告生成命令"""
    print_header("生成报告")
    
    if not args.input:
        print_error("请提供输入文件路径 --input")
        return
    
    from core.automation_workflow import AutomationWorkflowEngine
    
    engine = AutomationWorkflowEngine()
    
    # 读取工作流结果
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print_error(f"读取文件失败: {e}")
        return
    
    results = data.get("results", [])
    workflow_name = data.get("workflow_name", "未命名工作流")
    total_time = data.get("total_time", 0)
    
    report_path = engine._generate_desktop_report(workflow_name, results, total_time)
    
    if report_path:
        print_success(f"报告已生成: {report_path}")
    else:
        print_error("报告生成失败")


async def handle_status(args):
    """处理状态命令"""
    print_header("系统状态")
    
    # 检查核心组件
    components = [
        ("工作流引擎", "core.automation_workflow", "get_workflow_engine"),
        ("爬虫模块", "skills.web_scraper.handler", "scraper_dispatcher"),
        ("分析模块", "skills.data_analysis.handler", "analysis_handler"),
        ("自动化模块", "skills.advanced_automation.handler", "automation_hub"),
    ]
    
    print_section("核心组件状态")
    for name, module, obj in components:
        try:
            mod = __import__(module, fromlist=[obj])
            getattr(mod, obj)
            print_success(name)
        except Exception as e:
            print_error(f"{name} - {e}")
    print_section_end()
    
    # 检查输出目录
    output_dir = Path("skills") / "output"
    if output_dir.exists():
        csv_count = len(list(output_dir.glob("*.csv")))
        png_count = len(list(output_dir.glob("*.png")))
        print_section("数据统计")
        print_info(f"输出目录: {output_dir}")
        print_info(f"  CSV文件数: {csv_count}")
        print_info(f"  图片文件数: {png_count}")
        print_section_end()
    else:
        print_warning("输出目录不存在")


# ============================================================================
# 交互式聊天命令
# ============================================================================

async def handle_chat(args):
    """处理交互式聊天命令"""
    import time
    
    mode = getattr(args, 'mode', 'simple')
    
    # 清屏并显示欢迎界面
    print("\033c", end="")
    print_color("╔══════════════════════════════════════════════════════════════════╗", CliColors.CYAN + CliColors.BOLD)
    print_color("║                     🦐 小雷版小龙虾 AI 助手                      ║", CliColors.CYAN + CliColors.BOLD)
    print_color("╠══════════════════════════════════════════════════════════════════╣", CliColors.CYAN)
    print_color("║  模式: %-50s ║" % ('简单工作流' if mode == 'simple' else '多Agent深度思考'), CliColors.BLUE)
    print_color("║  提示: 输入 quit/exit/bye 退出，输入 help 查看命令               ║", CliColors.BLUE)
    print_color("╚══════════════════════════════════════════════════════════════════╝", CliColors.CYAN + CliColors.BOLD)
    print()
    
    print_chat_bubble("你好！我是小雷版小龙虾，一个具备自我进化能力的AI助手。\n\n我可以帮你：\n• 爬取网页数据\n• 生成图表分析\n• 发送微信消息\n• 执行自动化任务\n\n有什么我可以帮助你的吗？", is_user=False, timestamp=time.strftime("%H:%M"))
    
    while True:
        try:
            user_input = input(f"\n{CliColors.GREEN}{CliColors.BOLD}你: {CliColors.ENDC}")
            
            if user_input.lower() in ['quit', 'exit', 'bye', '结束']:
                print_color("\n👋 再见！期待下次为你服务！", CliColors.BLUE)
                break
                
            if user_input.lower() == 'help':
                print_chat_bubble("可用命令：\n• quit/exit/bye - 退出聊天\n• help - 显示帮助\n\n聊天模式：\n• simple - 简单工作流模式\n• deep - 多Agent深度思考模式", is_user=False, timestamp=time.strftime("%H:%M"))
                continue
                
            if not user_input.strip():
                continue
                
            # 显示用户消息气泡
            print()
            print_chat_bubble(user_input, is_user=True, timestamp=time.strftime("%H:%M"))
            
            # 创建临时args对象用于调用工作流处理
            class TempArgs:
                request = user_input
                type = mode
            
            if mode == 'simple':
                await _handle_multi_agent_simple_chat(TempArgs())
            else:
                await _handle_multi_agent_deep_chat(TempArgs())
                
        except KeyboardInterrupt:
            print_color("\n\n👋 再见！", CliColors.BLUE)
            break
        except Exception as e:
            error_msg = f"处理失败: {str(e)[:50]}..." if len(str(e)) > 50 else f"处理失败: {e}"
            print_chat_bubble(error_msg, is_user=False, timestamp=time.strftime("%H:%M"))
            logger.error("聊天处理异常", exc_info=True)


# ============================================================================
# 多Agent协作命令
# ============================================================================

async def handle_multi_agent(args):
    """处理多Agent协作（深度思考）命令"""
    mode_type = getattr(args, 'type', 'deep')

    if mode_type == 'simple':
        await _handle_multi_agent_simple(args)
    else:
        await _handle_multi_agent_deep(args)


async def _handle_multi_agent_simple(args):
    """处理简单工作流模式"""
    print_header("多Agent协作 - 简单工作流模式")

    if not args.request:
        print_error("请提供任务描述")
        return

    message = args.request
    print_info(f"任务: {message}")
    print()

    try:
        wrapper = WorkflowEngineWrapper()
        result = await wrapper.create_and_execute(message)
        await _display_workflow_result(result)
    except Exception as e:
        print_error(f"简单工作流执行失败: {e}")
        logger.error("简单工作流异常", exc_info=True)


async def _handle_multi_agent_simple_chat(args):
    """聊天模式专用 - 简单工作流模式"""
    import time
    
    if not args.request:
        print_chat_bubble("请提供任务描述", is_user=False, timestamp=time.strftime("%H:%M"))
        return

    message = args.request

    try:
        wrapper = WorkflowEngineWrapper()
        result = await wrapper.create_and_execute(message)
        
        # 构建结果消息
        result_msg = ""
        if result.get("workflow_name"):
            result_msg += f"✅ 工作流执行完成\n"
            result_msg += f"名称: {result.get('workflow_name')}\n"
            result_msg += f"耗时: {result.get('total_time', 0):.2f}s\n"
            result_msg += f"结果: {result.get('success_count', 0)}/{result.get('failed_count', 0)}\n\n"
        
        results = result.get("results", [])
        if results:
            result_msg += "步骤详情:\n"
            for step_result in results:
                status = "✅" if step_result.get("success") else "❌"
                step_num = step_result.get("step", "?")
                step_type = step_result.get("type", "")
                result_msg += f"{status} 步骤{step_num} [{step_type}]\n"
                
                if step_result.get("data_preview"):
                    preview = step_result["data_preview"]
                    if len(preview) > 50:
                        preview = preview[:50] + "..."
                    result_msg += f"  预览: {preview}\n"
                
                if step_result.get("csv_path"):
                    result_msg += f"  文件: {step_result['csv_path']}\n"
                
                if step_result.get("chart_path"):
                    result_msg += f"  图表: {step_result['chart_path']}\n"
        
        # 如果结果为空，提供友好回复
        if not result_msg.strip():
            result_msg = "已收到您的消息！\n\n如果您需要帮助，可以尝试：\n• 爬取网页数据\n• 生成图表分析\n• 发送微信消息\n• 执行自动化任务\n\n请告诉我您想做什么？"
        
        print_chat_bubble(result_msg, is_user=False, timestamp=time.strftime("%H:%M"))
        
    except Exception as e:
        error_msg = f"处理失败: {str(e)[:50]}..." if len(str(e)) > 50 else f"处理失败: {e}"
        print_chat_bubble(error_msg, is_user=False, timestamp=time.strftime("%H:%M"))
        logger.error("简单工作流异常", exc_info=True)


async def _display_workflow_result(result):
    """显示工作流执行结果"""
    if result.get("workflow_name"):
        print_success(f"✅ 工作流执行完成\n")
        print_info(f"名称: {result.get('workflow_name')}")
        print_info(f"耗时: {result.get('total_time', 0):.2f}s")
        print_info(f"结果: {result.get('success_count', 0)}/{result.get('failed_count', 0)}\n")
    
    results = result.get("results", [])
    if results:
        print_info("步骤详情:")
        for step_result in results:
            status = "✅" if step_result.get("success") else "❌"
            step_num = step_result.get("step", "?")
            step_type = step_result.get("type", "")
            print_info(f"{status} 步骤{step_num} [{step_type}]")
            
            if step_result.get("data_preview"):
                preview = step_result["data_preview"]
                if len(preview) > 50:
                    preview = preview[:50] + "..."
                print_info(f"  预览: {preview}")
            
            if step_result.get("csv_path"):
                print_info(f"  文件: {step_result['csv_path']}")
            
            if step_result.get("chart_path"):
                print_info(f"  图表: {step_result['chart_path']}")

async def _handle_run_workflow(args):
    """处理运行工作流命令"""
    print_header("运行工作流")

    if not args.workflow:
        print_error("请提供工作流名称")
        return

    workflow = args.workflow
    print_info(f"工作流: {workflow}")
    print()

    try:
        wrapper = WorkflowEngineWrapper()
        result = await wrapper.get_engine().execute_workflow(workflow)
    
        await _display_workflow_result(result)
    except Exception as e:
        print_error(f"工作流执行失败: {e}")
        logger.error("工作流执行异常", exc_info=True)


async def _handle_list_apps():
    """处理列出运行中的应用命令"""
    print_header("运行中的应用列表")
    
    try:
        # 使用AppleScript获取前台应用列表
        script = '''
        tell application "System Events"
            set appList to name of every application process whose background only is false
            return appList
        end tell
        '''
        
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            apps = [app.strip() for app in result.stdout.strip().split(', ') if app.strip()]
            
            if apps:
                print_success(f"找到 {len(apps)} 个运行的应用:")
                print()
                for i, app in enumerate(apps, 1):
                    print(f"  {i}. {app}")
                print()
            else:
                print_warning("未找到运行的应用")
        else:
            print_error(f"获取应用列表失败: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        print_error("获取应用列表超时")
    except Exception as e:
        print_error(f"获取应用列表异常: {e}")


async def _handle_automate_macro(args):
    """处理自动化宏命令"""
    print_header("自动化宏")

    if not args.macro:
        print_error("请提供宏名称")
        return

    macro = args.macro
    print_info(f"宏: {macro}")
    print()

    try:
        wrapper = WorkflowEngineWrapper()
        result = await wrapper.get_engine().execute_macro(macro)
        await _display_workflow_result(result)
    except Exception as e:
        print_error(f"宏执行失败: {e}")
        logger.error("宏执行异常", exc_info=True)


async def _handle_automate_macro_chat(args):
    """聊天模式专用 - 自动化宏命令"""
    import time
    
    if not args.macro:
        print_chat_bubble("请提供宏名称", is_user=False, timestamp=time.strftime("%H:%M"))
        return

    macro = args.macro

    try:
        wrapper = WorkflowEngineWrapper()
        result = await wrapper.get_engine().execute_macro(macro)
        
        # 构建结果消息
        result_msg = ""
        if result.get("workflow_name"):
            result_msg += f"✅ 工作流执行完成\n"
            result_msg += f"名称: {result.get('workflow_name')}\n"
            result_msg += f"耗时: {result.get('total_time', 0):.2f}s\n"
            result_msg += f"结果: {result.get('success_count', 0)}/{result.get('failed_count', 0)}\n\n"
        
        results = result.get("results", [])
        if results:
            result_msg += "步骤详情:\n"
            for step_result in results:
                status = "✅" if step_result.get("success") else "❌"
                step_num = step_result.get("step", "?")
                step_type = step_result.get("type", "")
                result_msg += f"{status} 步骤{step_num} [{step_type}]\n"
                
                if step_result.get("data_preview"):
                    preview = step_result["data_preview"]
                    if len(preview) > 50:
                        preview = preview[:50] + "..."
                    result_msg += f"  预览: {preview}\n"
                
                if step_result.get("csv_path"):
                    result_msg += f"  文件: {step_result['csv_path']}\n"
                
                if step_result.get("chart_path"):
                    result_msg += f"  图表: {step_result['chart_path']}\n"
        
        # 如果结果为空，提供友好回复
        if not result_msg.strip():
            result_msg = "已收到您的消息！\n\n如果您需要帮助，可以尝试：\n• 爬取网页数据\n• 生成图表分析\n• 发送微信消息\n• 执行自动化任务\n\n请告诉我您想做什么？"
        
        print_chat_bubble(result_msg, is_user=False, timestamp=time.strftime("%H:%M"))
    except Exception as e:
        error_msg = f"执行失败: {str(e)[:80]}..." if len(str(e)) > 80 else f"执行失败: {e}"
        print_chat_bubble(error_msg, is_user=False, timestamp=time.strftime("%H:%M"))
        logger.error("简单工作流异常", exc_info=True)


async def _handle_multi_agent_deep(args):
    """处理多Agent深度思考模式"""
    print_header("多Agent协作 - 深度思考模式")

    if not args.request:
        print_error("请提供任务描述")
        return

    message = args.request
    collaboration_mode = getattr(args, 'mode', 'master_slave')
    agent_count = getattr(args, 'agents', 3)

    print_info(f"任务: {message}")
    print_info(f"协作模式: {collaboration_mode}")
    print_info(f"Agent数量: {agent_count}")
    print()

    exec_logger = None
    task_id = None
    tool_call_count = 0

    try:
        import time
        from core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler import (
            IntelligentScheduler, CollaborationMode
        )
        from core.multi_agent_v2.agents.base.base_agent import Task
        from core.multi_agent_v2.orchestration.context.global_context_center import (
            GlobalContextCenter
        )
        from core.multi_agent_v2.orchestration.lifecycle.agent_pool import AgentPool
        from core.multi_agent_v2.agents.lazy_agent import LazyAgent
        from core.multi_agent_v2.agents.base.base_agent import AgentType

        if get_execution_logger:
            exec_logger = get_execution_logger()
            task_id = exec_logger.start_task(description=message)

        print_info("初始化多Agent系统...")

        if exec_logger:
            exec_logger.log(
                tool_name="system_init",
                params={"system": "multi_agent_v2", "mode": collaboration_mode},
                status=ExecutionStatus.SUCCESS.value if ExecutionStatus else "success",
                agent_type="system"
            )

        context_center = GlobalContextCenter()
        scheduler = IntelligentScheduler(context_center=context_center)

        agent_pool = AgentPool()
        await agent_pool.start()

        if exec_logger:
            exec_logger.log(
                tool_name="agent_pool_start",
                params={"agent_pool": str(agent_pool)},
                status=ExecutionStatus.SUCCESS.value if ExecutionStatus else "success",
                agent_type="system",
                notes="AgentPool初始化成功"
            )

        agent_types = {
            1: [(AgentType.MASTER, "master-001")],
            2: [(AgentType.MASTER, "master-001"), (AgentType.WORKER, "worker-001")],
            3: [(AgentType.MASTER, "master-001"), (AgentType.WORKER, "worker-001"), (AgentType.REVIEWER, "reviewer-001")],
        }

        selected_agents = agent_types.get(min(agent_count, 3), agent_types[3])

        created_agents = []
        for agent_type, agent_name in selected_agents:
            agent = LazyAgent(agent_type=agent_type.value)
            await agent.ensure_initialized()
            created_agents.append(agent)
            logger.info(f"Agent已初始化: {agent.agent_id} ({agent_type.value})")

            tool_call_count += 1
            if exec_logger:
                exec_logger.log(
                    tool_name="agent_create",
                    params={"agent_type": agent_type.value, "agent_id": agent.agent_id},
                    status=ExecutionStatus.SUCCESS.value if ExecutionStatus else "success",
                    duration_ms=0,
                    agent_type=agent_type.value,
                    notes=f"{agent_name} 创建成功"
                )

        mode_map = {
            "pipeline": CollaborationMode.PIPELINE,
            "master_slave": CollaborationMode.MASTER_SLAVE,
            "review": CollaborationMode.REVIEW,
            "auction": CollaborationMode.AUCTION,
            "hybrid": CollaborationMode.HYBRID,
        }
        selected_mode = mode_map.get(collaboration_mode, CollaborationMode.MASTER_SLAVE)

        print_info(f"创建任务...")
        task_id_str = f"cli_multi_agent_{int(time.time()*1000)}"
        task = Task(
            task_id=task_id_str,
            type="deep_thinking",
            description=message,
            keywords=["深度思考", "分析", "研究"],
            complexity=0.8,
            estimated_steps=5,
            dependencies=[],
            context={"source": "cli", "mode": collaboration_mode},
            priority=1
        )

        if exec_logger:
            exec_logger.log(
                tool_name="task_create",
                params={"task_id": task_id_str, "description": message},
                status=ExecutionStatus.SUCCESS.value if ExecutionStatus else "success",
                agent_type="system",
                notes="任务创建成功"
            )

        print_info("开始多Agent协作调度...")
        start_time = time.time()
        schedule_success = False
        final_result = None

        try:
            schedule_result = await scheduler.schedule(task)
            elapsed = time.time() - start_time

            if schedule_result and schedule_result.success:
                schedule_success = True
                final_result = schedule_result.metadata.get("final_result", "")

                print_success(f"多Agent协作完成! (耗时: {elapsed:.2f}s)")
                print()
                print(f"  协作模式: {schedule_result.collaboration_mode.value}")
                print(f"  分配Agent数: {len(schedule_result.assigned_agents)}")
                print()
                print("  Agent分配:")
                for subtask_id, agent_id in schedule_result.assigned_agents.items():
                    print(f"    • {subtask_id} → {agent_id}")

                if final_result:
                    print()
                    print("  最终结果:")
                    if len(final_result) > 500:
                        final_result_short = final_result[:500] + "..."
                    else:
                        final_result_short = final_result
                    print(f"    {final_result_short}")

                if exec_logger:
                    exec_logger.log(
                        tool_name="multi_agent_schedule",
                        params={"task_id": task_id_str, "agents_assigned": len(schedule_result.assigned_agents)},
                        result=final_result[:200] if final_result else None,
                        status=ExecutionStatus.SUCCESS.value if ExecutionStatus else "success",
                        duration_ms=elapsed * 1000,
                        agent_type="scheduler",
                        notes=f"调度成功，模式={schedule_result.collaboration_mode.value}"
                    )
            else:
                print_warning("多Agent调度失败，可使用 --type simple 模式")
                print_info("示例: python cli.py multi_agent \"任务描述\" --type simple")

                if exec_logger:
                    exec_logger.log(
                        tool_name="multi_agent_schedule",
                        params={"task_id": task_id_str},
                        status=ExecutionStatus.FAILED.value if ExecutionStatus else "failed",
                        duration_ms=elapsed * 1000,
                        agent_type="scheduler",
                        error_message="调度返回失败"
                    )

        except Exception as schedule_error:
            elapsed = time.time() - start_time
            logger.warning(f"multi_agent_v2调度异常: {schedule_error}")

            if exec_logger:
                exec_logger.log(
                    tool_name="multi_agent_schedule",
                    params={"task_id": task_id_str},
                    status=ExecutionStatus.FAILED.value if ExecutionStatus else "failed",
                    duration_ms=elapsed * 1000,
                    agent_type="scheduler",
                    error_message=str(schedule_error)
                )

        if exec_logger and exec_logger.should_trigger_review(task_id):
            print()
            print_info("触发自动复盘...")
            try:
                review_logger = get_auto_reviewer()
                execution_logs = exec_logger.format_logs_for_review(task_id)
                review_result = await review_logger.review(
                    task_id=task_id,
                    task_description=message,
                    execution_logs=execution_logs,
                    task_result=final_result
                )

                print()
                print(review_logger.format_review_report(review_result))

                if review_result.is_worth_saving and review_result.skill_name:
                    print_info("正在萃取技能...")
                    skill_ext = get_skill_extractor()
                    skill = skill_ext.extract_from_review(review_result)
                    if skill:
                        print_success(f"技能萃取成功: {skill.name}")
                        print(skill_ext.format_skill_summary(skill))
            except Exception as review_error:
                logger.warning(f"复盘过程出错: {review_error}")

    except ImportError as e:
        print_error(f"导入模块失败: {e}")
        logger.error("multi_agent导入失败", exc_info=True)
    except Exception as e:
        print_error(f"多Agent协作执行失败: {e}")
        logger.error("多Agent协作异常", exc_info=True)


async def _handle_multi_agent_deep_chat(args):
    """聊天模式专用 - 多Agent深度思考模式"""
    import time
    
    if not args.request:
        print_chat_bubble("请提供任务描述", is_user=False, timestamp=time.strftime("%H:%M"))
        return

    message = args.request
    start_time = time.time()
    
    try:
        from core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler import (
            IntelligentScheduler, CollaborationMode
        )
        from core.multi_agent_v2.agents.base.base_agent import Task
        from core.multi_agent_v2.orchestration.context.global_context_center import (
            GlobalContextCenter
        )
        from core.multi_agent_v2.orchestration.lifecycle.agent_pool import AgentPool
        from core.multi_agent_v2.agents.lazy_agent import LazyAgent
        from core.multi_agent_v2.agents.base.base_agent import AgentType

        context_center = GlobalContextCenter()
        scheduler = IntelligentScheduler(context_center=context_center)

        agent_pool = AgentPool()
        await agent_pool.start()

        scheduler.set_agent_pool(agent_pool)

        task_id_str = f"cli_multi_agent_{int(time.time() * 1000)}"
        
        task = Task(
            task_id=task_id_str,
            type="analysis",
            description=message,
            context={},
            priority=1
        )

        schedule_result = await scheduler.schedule(task)
        elapsed = time.time() - start_time

        if schedule_result and schedule_result.success:
            final_result = schedule_result.metadata.get("final_result", "")
            
            result_msg = f"✅ 多Agent协作完成! (耗时: {elapsed:.2f}s)\n\n"
            result_msg += f"协作模式: {schedule_result.collaboration_mode.value}\n"
            result_msg += f"分配Agent数: {len(schedule_result.assigned_agents)}\n\n"
            
            if schedule_result.assigned_agents:
                result_msg += "Agent分配:\n"
                for subtask, agent in schedule_result.assigned_agents.items():
                    result_msg += f"  • {subtask} → {agent[:8]}...\n"
            
            if schedule_result.metadata:
                result_msg += "\n调度信息:\n"
                if "trace_id" in schedule_result.metadata:
                    result_msg += f"  追踪ID: {schedule_result.metadata['trace_id']}\n"
                if "scheduling_time" in schedule_result.metadata:
                    result_msg += f"  调度耗时: {schedule_result.metadata['scheduling_time']:.2f}s\n"
            
            if final_result:
                if len(final_result) > 200:
                    final_result = final_result[:200] + "..."
                result_msg += f"\n最终结果:\n{final_result}"
            
            print_chat_bubble(result_msg, is_user=False, timestamp=time.strftime("%H:%M"))
        else:
            print_chat_bubble("⚠️ 多Agent调度失败，已切换到简单模式处理", is_user=False, timestamp=time.strftime("%H:%M"))
            await _handle_multi_agent_simple_chat(args)

        await agent_pool.stop()

    except ImportError as e:
        print_chat_bubble(f"模块导入失败: {str(e)[:50]}...", is_user=False, timestamp=time.strftime("%H:%M"))
    except Exception as e:
        print_chat_bubble(f"执行失败: {str(e)[:50]}...", is_user=False, timestamp=time.strftime("%H:%M"))
        logger.error("多Agent协作异常", exc_info=True)


# ============================================================================
# 命令行接口
# ============================================================================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="小雷版小龙虾 AI Agent - 命令行接口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 智能工作流 - 识别用户意图并执行
  python cli.py smart "帮我爬取微博热搜并生成词云分析报告"
  
  # GUI自动化 - 打开应用
  python cli.py automate open_app --app "微信"
  
  # GUI自动化 - 输入文字
  python cli.py automate type --text "Hello World"
  
  # GUI自动化 - 快捷键
  python cli.py automate hotkey --keys "command c"
  
  # GUI自动化 - 执行脚本
  python cli.py automate script --file my_script.json
  
  # GUI自动化 - 执行预设宏
  python cli.py automate macro --name open_browser
  
  # 爬虫 - 爬取微博热搜
  python cli.py scrape 微博 --action "热搜top10"
  
  # 分析 - 生成词云
  python cli.py analyze 可视化 --chart-type wordcloud
  
  # 微信 - 发送消息
  python cli.py wechat send --friend "张三" --message "你好！"
  
  # 微信 - 发送消息（带延迟）
  python cli.py wechat send -f "李四" -m "晚上好" -d 2
  
  # 查看系统状态
  python cli.py status
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # ==================== chat 命令 ====================
    chat_parser = subparsers.add_parser(
        "chat",
        help="交互式聊天",
        description="启动交互式聊天模式，与AI助手对话"
    )
    chat_parser.add_argument(
        "--mode", 
        choices=["simple", "deep"], 
        default="simple",
        help="聊天模式：simple（简单工作流）或 deep（多Agent深度思考）"
    )
    
    # ==================== smart 命令 ====================
    smart_parser = subparsers.add_parser(
        "smart", 
        help="智能意图识别并执行工作流",
        description="根据自然语言描述自动识别意图并执行相应的工作流"
    )
    smart_parser.add_argument("request", help="用户请求描述")
    
    # ==================== workflow 命令 ====================
    workflow_parser = subparsers.add_parser(
        "workflow",
        help="工作流管理",
        description="工作流的执行、列表和保存操作"
    )
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_cmd")
    
    wf_run_parser = workflow_subparsers.add_parser("run", help="执行工作流文件")
    wf_run_parser.add_argument("file", help="工作流JSON文件路径")
    
    wf_list_parser = workflow_subparsers.add_parser("list", help="列出工作流模板")
    
    wf_save_parser = workflow_subparsers.add_parser("save", help="保存工作流到文件")
    wf_save_parser.add_argument("request", help="用户请求描述")
    wf_save_parser.add_argument("--output", "-o", help="输出文件路径")
    
    # ==================== automate 命令 ====================
    automate_parser = subparsers.add_parser(
        "automate",
        help="GUI自动化操作",
        description="执行各种GUI自动化操作"
    )
    automate_subparsers = automate_parser.add_subparsers(dest="action")
    
    # --- 应用操作 ---
    auto_open_app = automate_subparsers.add_parser("open_app", help="打开应用")
    auto_open_app.add_argument("--app", required=True, help="应用名称（如: 微信, Safari, Terminal）")
    
    auto_quit_app = automate_subparsers.add_parser("quit_app", help="退出应用")
    auto_quit_app.add_argument("--app", required=True, help="应用名称")
    
    auto_activate_app = automate_subparsers.add_parser("activate_app", help="激活应用")
    auto_activate_app.add_argument("--app", required=True, help="应用名称")
    
    # --- 浏览器操作 ---
    auto_open_url = automate_subparsers.add_parser("open_url", help="打开URL")
    auto_open_url.add_argument("--url", required=True, help="网址")
    
    # --- 通知 ---
    auto_notify = automate_subparsers.add_parser("notification", help="发送通知")
    auto_notify.add_argument("--title", default="小雷版小龙虾", help="通知标题")
    auto_notify.add_argument("--message", required=True, help="通知内容")
    
    # --- 截图 ---
    auto_screenshot = automate_subparsers.add_parser("screenshot", help="截图")
    auto_screenshot.add_argument("--name", help="截图文件名")
    auto_screenshot.add_argument("--delay", type=int, help="延迟秒数")
    
    # --- 等待 ---
    auto_wait = automate_subparsers.add_parser("wait", help="等待")
    auto_wait.add_argument("--seconds", type=int, default=1, help="等待秒数")
    
    # --- 系统控制 ---
    auto_volume = automate_subparsers.add_parser("volume", help="调节音量")
    auto_volume.add_argument("--level", type=int, default=50, help="音量级别(0-100)")
    
    auto_brightness = automate_subparsers.add_parser("brightness", help="调节亮度")
    auto_brightness.add_argument("--level", type=int, default=70, help="亮度级别(0-100)")
    
    # --- 剪贴板 ---
    auto_clipboard = automate_subparsers.add_parser("clipboard", help="剪贴板操作")
    auto_clipboard.add_argument("--set", help="设置剪贴板内容")
    
    # --- 键盘操作 ---
    auto_type = automate_subparsers.add_parser("type", help="输入文字")
    auto_type.add_argument("--text", required=True, help="要输入的文字")
    auto_type.add_argument("--delay", type=float, help="输入间隔(秒)")
    
    auto_hotkey = automate_subparsers.add_parser("hotkey", help="快捷键操作")
    auto_hotkey.add_argument("--keys", required=True, help="快捷键组合（空格分隔，如: 'command c'）")
    
    auto_key_press = automate_subparsers.add_parser("key_press", help="按键操作")
    auto_key_press.add_argument("--key", required=True, help="按键名称")
    
    # --- 鼠标操作 ---
    auto_click = automate_subparsers.add_parser("click", help="鼠标点击")
    auto_click.add_argument("--x", type=int, help="X坐标")
    auto_click.add_argument("--y", type=int, help="Y坐标")
    auto_click.add_argument("--button", default="left", help="鼠标按钮(left/right)")
    
    auto_double_click = automate_subparsers.add_parser("double_click", help="双击")
    auto_double_click.add_argument("--x", type=int, help="X坐标")
    auto_double_click.add_argument("--y", type=int, help="Y坐标")
    
    auto_right_click = automate_subparsers.add_parser("right_click", help="右键点击")
    auto_right_click.add_argument("--x", type=int, help="X坐标")
    auto_right_click.add_argument("--y", type=int, help="Y坐标")
    
    auto_scroll = automate_subparsers.add_parser("scroll", help="滚动")
    auto_scroll.add_argument("--direction", choices=["up", "down"], default="down", help="滚动方向")
    auto_scroll.add_argument("--amount", type=int, default=100, help="滚动量")
    
    # --- 窗口操作 ---
    auto_win_min = automate_subparsers.add_parser("window_minimize", help="最小化窗口")
    auto_win_max = automate_subparsers.add_parser("window_maximize", help="最大化窗口")
    auto_win_full = automate_subparsers.add_parser("window_fullscreen", help="全屏窗口")
    auto_win_close = automate_subparsers.add_parser("window_close", help="关闭窗口")
    auto_win_switch = automate_subparsers.add_parser("window_switch", help="切换窗口")
    auto_win_switch.add_argument("--direction", choices=["next", "prev"], default="next", help="切换方向")
    
    # --- 文件操作 ---
    auto_open_file = automate_subparsers.add_parser("open_file", help="打开文件")
    auto_open_file.add_argument("--path", required=True, help="文件路径")
    
    auto_open_folder = automate_subparsers.add_parser("open_folder", help="打开文件夹")
    auto_open_folder.add_argument("--path", required=True, help="文件夹路径")
    
    auto_create_file = automate_subparsers.add_parser("create_file", help="创建文件")
    auto_create_file.add_argument("--path", required=True, help="文件路径")
    auto_create_file.add_argument("--content", help="文件内容")
    
    auto_delete_file = automate_subparsers.add_parser("delete_file", help="删除文件")
    auto_delete_file.add_argument("--path", required=True, help="文件路径")
    
    # --- 截图增强 ---
    auto_capture_region = automate_subparsers.add_parser("capture_region", help="截取指定区域")
    auto_capture_region.add_argument("--x", type=int, required=True, help="起始X坐标")
    auto_capture_region.add_argument("--y", type=int, required=True, help="起始Y坐标")
    auto_capture_region.add_argument("--width", type=int, default=400, help="宽度")
    auto_capture_region.add_argument("--height", type=int, default=300, help="高度")
    
    # --- 键盘增强 ---
    auto_key_down = automate_subparsers.add_parser("key_down", help="按住按键")
    auto_key_down.add_argument("--key", required=True, help="按键名称")
    
    auto_key_up = automate_subparsers.add_parser("key_up", help="释放按键")
    auto_key_up.add_argument("--key", required=True, help="按键名称")
    
    # --- 鼠标增强 ---
    auto_mouse_move = automate_subparsers.add_parser("mouse_move", help="移动鼠标")
    auto_mouse_move.add_argument("--x", type=int, required=True, help="目标X坐标")
    auto_mouse_move.add_argument("--y", type=int, required=True, help="目标Y坐标")
    
    auto_mouse_drag = automate_subparsers.add_parser("mouse_drag", help="拖拽操作")
    auto_mouse_drag.add_argument("--x", type=int, required=True, help="起始X坐标")
    auto_mouse_drag.add_argument("--y", type=int, required=True, help="起始Y坐标")
    auto_mouse_drag.add_argument("--to-x", type=int, required=True, help="目标X坐标")
    auto_mouse_drag.add_argument("--to-y", type=int, required=True, help="目标Y坐标")
    
    # --- 窗口增强 ---
    auto_win_resize = automate_subparsers.add_parser("window_resize", help="调整窗口大小")
    auto_win_resize.add_argument("--width", type=int, required=True, help="宽度")
    auto_win_resize.add_argument("--height", type=int, required=True, help="高度")
    
    auto_win_move = automate_subparsers.add_parser("window_move", help="移动窗口位置")
    auto_win_move.add_argument("--x", type=int, required=True, help="X坐标")
    auto_win_move.add_argument("--y", type=int, required=True, help="Y坐标")
    
    auto_win_focus = automate_subparsers.add_parser("window_focus", help="聚焦窗口")
    auto_win_focus.add_argument("--app", help="应用名称")
    
    # --- 文本操作 ---
    auto_select_all = automate_subparsers.add_parser("select_all", help="全选")
    auto_copy = automate_subparsers.add_parser("copy", help="复制")
    auto_paste = automate_subparsers.add_parser("paste", help="粘贴")
    auto_cut = automate_subparsers.add_parser("cut", help="剪切")
    auto_undo = automate_subparsers.add_parser("undo", help="撤销")
    auto_redo = automate_subparsers.add_parser("redo", help="重做")
    
    auto_find_text = automate_subparsers.add_parser("find_text", help="查找文字")
    auto_find_text.add_argument("--text", required=True, help="要查找的文字")
    
    auto_replace_text = automate_subparsers.add_parser("replace_text", help="替换文字")
    auto_replace_text.add_argument("--find", required=True, help="查找内容")
    auto_replace_text.add_argument("--replace", required=True, help="替换内容")
    
    # --- 系统操作 ---
    auto_lock = automate_subparsers.add_parser("lock", help="锁定屏幕")
    auto_sleep = automate_subparsers.add_parser("sleep", help="系统睡眠")
    auto_restart = automate_subparsers.add_parser("restart", help="重启系统")
    auto_shutdown = automate_subparsers.add_parser("shutdown", help="关机")
    
    # --- 应用列表 ---
    auto_list_apps = automate_subparsers.add_parser("list_apps", help="列出运行中的应用")
    
    # --- 脚本和宏 ---
    auto_script = automate_subparsers.add_parser("script", help="执行自动化脚本")
    auto_script.add_argument("--file", required=True, help="脚本JSON文件路径")
    
    auto_macro = automate_subparsers.add_parser("macro", help="执行预设宏")
    auto_macro.add_argument("--name", required=True, choices=[
        "open_browser", "close_all", "save_all", "screenshot_save", "clean_desktop"
    ], help="宏名称")
    
    # ==================== wechat 命令 ====================
    wechat_parser = subparsers.add_parser(
        "wechat",
        help="微信消息发送",
        description="通过GUI自动化发送微信消息"
    )
    wechat_subparsers = wechat_parser.add_subparsers(dest="action")
    
    wechat_send_parser = wechat_subparsers.add_parser("send", help="发送消息")
    wechat_send_parser.add_argument("--friend", "-f", required=True, help="好友名称（备注名或昵称）")
    wechat_send_parser.add_argument("--message", "-m", required=True, help="消息内容")
    wechat_send_parser.add_argument("--delay", "-d", type=float, default=1, help="启动延迟（秒）")
    
    wechat_list_parser = wechat_subparsers.add_parser("list", help="列出好友")
    
    # ==================== scrape 命令 ====================
    scrape_parser = subparsers.add_parser(
        "scrape",
        help="数据爬取",
        description="爬取指定网站的数据"
    )
    scrape_parser.add_argument(
        "site", 
        choices=["微博", "百度", "B站", "抖音", "知乎", "今日头条", "豆瓣"],
        help="目标站点"
    )
    scrape_parser.add_argument("--action", default="热搜top10", help="爬取动作")
    scrape_parser.add_argument("--report", action="store_true", help="生成报告")
    
    # ==================== analyze 命令 ====================
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="数据分析",
        description="对数据进行分析和可视化"
    )
    analyze_parser.add_argument(
        "action", 
        choices=["可视化", "描述性统计"],
        help="分析动作"
    )
    analyze_parser.add_argument("--chart-type", choices=["bar", "pie", "line", "wordcloud"], help="图表类型")
    analyze_parser.add_argument("--file", help="数据文件路径")
    analyze_parser.add_argument("--report", action="store_true", help="生成报告")
    
    # ==================== report 命令 ====================
    report_parser = subparsers.add_parser(
        "report",
        help="报告生成",
        description="从工作流结果生成分析报告"
    )
    report_parser.add_argument("--input", required=True, help="输入JSON文件")
    
    # ==================== status 命令 ====================
    status_parser = subparsers.add_parser(
        "status",
        help="系统状态",
        description="检查系统组件状态"
    )

    # ==================== multi_agent 命令 ====================
    multi_agent_parser = subparsers.add_parser(
        "multi_agent",
        help="多Agent协作（深度思考）",
        description="使用multi_agent_v2多Agent系统进行深度思考和分析任务"
    )
    multi_agent_parser.add_argument(
        "request",
        help="需要深度思考的任务描述"
    )
    multi_agent_parser.add_argument(
        "--type",
        choices=["simple", "deep"],
        default="deep",
        help="模式类型: simple=简单工作流, deep=多Agent深度思考 (默认: deep)"
    )
    multi_agent_parser.add_argument(
        "--mode",
        choices=["pipeline", "master_slave", "review", "auction", "hybrid"],
        default="master_slave",
        help="协作模式 (默认: master_slave)"
    )
    multi_agent_parser.add_argument(
        "--agents",
        type=int,
        default=3,
        help="使用的Agent数量 (默认: 3)"
    )

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 执行命令
    try:
        asyncio.run(_execute_command(args))
    except KeyboardInterrupt:
        print("\n👋 操作已取消")
    except Exception as e:
        print_error(f"执行失败: {e}")
        logger.error("执行失败", exc_info=True)


async def _execute_command(args):
    """执行命令"""
    if args.command == "smart":
        await handle_smart(args)
    
    elif args.command == "workflow":
        if args.workflow_cmd == "run":
            await handle_workflow_run(args)
        elif args.workflow_cmd == "list":
            await handle_workflow_list(args)
        elif args.workflow_cmd == "save":
            await handle_workflow_save(args)
        else:
            print_error("请指定工作流子命令: run, list, save")
    
    elif args.command == "automate":
        if args.action:
            await handle_automate(args)
        else:
            print_error("请指定自动化动作")
    
    elif args.command == "wechat":
        if args.action:
            await handle_wechat(args)
        else:
            print_error("请指定微信操作: send 或 list")
    
    elif args.command == "scrape":
        await handle_scrape(args)
    
    elif args.command == "analyze":
        await handle_analyze(args)
    
    elif args.command == "report":
        await handle_report(args)
    
    elif args.command == "status":
        await handle_status(args)

    elif args.command == "chat":
        await handle_chat(args)

    elif args.command == "multi_agent":
        await handle_multi_agent(args)

    else:
        print_error(f"未知命令: {args.command}")


if __name__ == "__main__":
    main()
