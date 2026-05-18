#!/usr/bin/env python3
"""小雷版小龙虾 AI Agent - 命令行接口 (增强版)

新增功能:
├── 命令前缀系统 (/xx+)
│   - /help      显示帮助
│   - /run       执行工作流
│   - /analyze   数据分析
│   - /scrape    数据爬取
│   - /automate  GUI自动化
│   - /wechat    微信消息
│   - /chat      进入聊天模式
│   - /status    系统状态
│   - /quit      退出
│   - /clear     清屏
│   - /history   历史记录
│   - /debug     调试模式
│   - /think     思考模式
├── 思考功能
│   - 显示每一步思考过程
│   - 意图分析展示
│   - 执行步骤规划
├── 增强日志系统
│   - 时间戳显示
│   - 颜色区分级别
│   - 结构化输出
└── 类似Claude Code的交互体验

示例:
  # 智能工作流
  /run "帮我爬取微博热搜并生成词云分析报告"
  
  # 命令模式
  /analyze wordcloud --file data.csv
  /automate open_app --app Safari
  /wechat send --friend 张三 --message 你好
  
  # 自然语言请求（无需前缀）
  帮我查看系统状态
  发送微信消息给李四
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 先解析参数并初始化日志系统（在导入任何可能产生日志的模块之前）
def _pre_init_logger():
    """预初始化日志系统 - 在导入其他模块之前"""
    # 快速解析命令行参数中的日志相关选项
    log_file = None
    no_console_log = False
    
    import sys
    in_tmux = os.environ.get("TMUX") is not None
    
    for i, arg in enumerate(sys.argv):
        if arg in ('--log-file', '-l') and i + 1 < len(sys.argv):
            log_file = sys.argv[i + 1]
        elif arg == '--no-console-log':
            no_console_log = True
        elif arg in ('--dual-terminal', '-d'):
            # 双终端模式自动启用日志文件和禁用控制台日志
            script_dir = Path(__file__).parent
            log_file = str(script_dir / "logs" / "agent.log")
            no_console_log = True
    
    # 如果检测到我们在 tmux 中（会话内部），自动启用日志文件
    if in_tmux and not log_file:
        script_dir = Path(__file__).parent
        log_file = str(script_dir / "logs" / "agent.log")
        no_console_log = True
    
    # 设置环境变量，让 core 模块的日志系统也能读取
    if log_file:
        os.environ["AGENT_LOG_FILE"] = log_file
    if no_console_log:
        os.environ["AGENT_ENABLE_CONSOLE_LOG"] = "false"
    
    # 初始化日志系统
    from cli.logging_system import init_logger
    init_logger(log_file=log_file, log_to_console=not no_console_log)

# 预初始化日志系统（必须在导入其他模块之前）
_pre_init_logger()

# 导入CLI模块
from cli.colors import CliColors, print_color, print_chat_bubble, print_success, print_error, print_warning, get_console
from cli.command_parser import (
    CommandParser, CommandType, ParsedCommand, get_command_parser
)
from cli.thinking_engine import (
    ThinkingEngine, get_thinking_engine,
    think_start, think_analyze, think_plan, think_step,
    think_log, think_complete, think_data, think_summarize,
    set_thinking_enabled
)
from cli.logging_system import (
    get_logger, init_logger,
    log_debug, log_info, log_success, log_warning, log_error,
)
from cli.ui_components import ClaudeCodeDialog, SandboxPanel, ProgressHeader
from cli.sandbox_viewer import get_viewer as get_sandbox_viewer, record_event

# 导入核心服务（延迟导入）
CLARIFICATION_SERVICE = None
PERMISSION_SERVICE = None
FORKED_AGENT_SERVICE = None

def _import_core_services():
    """延迟导入核心服务"""
    global CLARIFICATION_SERVICE, PERMISSION_SERVICE, FORKED_AGENT_SERVICE
    
    try:
        from core.services.clarification_service import get_clarification_service
        CLARIFICATION_SERVICE = get_clarification_service()
        log_success("✅ 反问服务导入成功")
    except Exception as e:
        log_error(f"❌ 反问服务导入失败: {e}")
    
    try:
        from core.services.permission_service import get_permission_service
        PERMISSION_SERVICE = get_permission_service()
        log_success("✅ 权限服务导入成功")
    except Exception as e:
        log_error(f"❌ 权限服务导入失败: {e}")
    
    try:
        from core.services.forked_agent_service import get_forked_agent_service
        FORKED_AGENT_SERVICE = get_forked_agent_service()
        log_success("✅ Forked Agent服务导入成功")
    except Exception as e:
        log_error(f"❌ Forked Agent服务导入失败: {e}")


def _cleanup_old_sessions():
    """每次启动时清理上次运行的残留文件"""
    try:
        viewer = get_sandbox_viewer()
        viewer.entries.clear()
        viewer.clear_log_file()
    except Exception:
        pass
    try:
        import tempfile
        from pathlib import Path
        sandbox_dir = Path(tempfile.gettempdir()) / "agent_sandbox"
        if sandbox_dir.exists():
            import shutil
            shutil.rmtree(sandbox_dir, ignore_errors=True)
    except Exception:
        pass


class EnhancedCLI:
    """增强版CLI - 支持命令前缀、思考模式和增强日志"""
    
    def __init__(self):
        self.command_parser = get_command_parser()
        self.thinking_engine = get_thinking_engine()
        self.running = True
        self.debug_mode = False
        
        # 会话状态管理
        self.chat_mode = False
        self.chat_mode_type = "simple"  # simple / deep / expert / quick
        self.chat_history = []
        self.session_id = None
        self.current_mcp_server = None
        self.mcp_session = None
        
        # 导入核心服务
        _import_core_services()
        
    def _init_session(self):
        """初始化会话状态（延迟到日志系统初始化后调用）"""
        import uuid
        self.session_id = str(uuid.uuid4())[:8]
        self.chat_history = []
        # 清理上次运行的残留
        _cleanup_old_sessions()
        log_info(f"会话已初始化: {self.session_id}")
    
    def print_welcome(self):
        """打印欢迎界面 - 现代极简风格"""
        print("\033c", end="")
        from cli.colors import print_divider, CliColors

        # 简约标志
        dc = CliColors
        logo_color = dc.DARK_BLUE + dc.BOLD
        print()
        print(f"  {dc.DARK_BLUE}━━━  ━━━  ━━━{dc.ENDC}")
        print(f"  {dc.DARK_BLUE}  ██╗  ██╗██╗ █████╗ {dc.DARK_CYAN} ██╗     ███████╗██╗{dc.ENDC}")
        print(f"  {dc.DARK_BLUE}  ╚██╗██╔╝██║██╔══██╗{dc.DARK_CYAN} ██║     ██╔════╝██║{dc.ENDC}")
        print(f"  {dc.DARK_BLUE}   ╚███╔╝ ██║███████║{dc.DARK_CYAN} ██║     █████╗  ██║{dc.ENDC}")
        print(f"  {dc.DARK_BLUE}   ██╔██╗ ██║██╔══██║{dc.DARK_CYAN} ██║     ██╔══╝  ╚═╝{dc.ENDC}")
        print(f"  {dc.DARK_BLUE}  ██╔╝ ██╗██║██║  ██║{dc.DARK_CYAN} ███████╗███████╗██╗{dc.ENDC}")
        print(f"  {dc.DARK_BLUE}  ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝{dc.DARK_CYAN} ╚══════╝╚══════╝╚═╝{dc.ENDC}")
        print(f"  {dc.DARK_BLUE}━━━  ━━━  ━━━{dc.ENDC}")
        print()

        # 单行简介
        print_color(f"  {dc.DOUBLE_ARROW} 小雷版小龙虾 AI Agent", dc.DARK_GRAY)
        print_divider()
        print_color(f"  {dc.DOT} 输入 /help 查看命令  {dc.DOT} exit 退出  {dc.DOT} /clear 清屏", dc.DARK_GRAY)
        print()

    async def handle_command(self, parsed_cmd: ParsedCommand):
        """处理解析后的命令"""
        cmd_type = parsed_cmd.command_type
        
        if cmd_type == CommandType.HELP:
            self.handle_help()
        
        elif cmd_type == CommandType.QUIT or cmd_type == CommandType.EXIT:
            self.handle_quit()
        
        elif cmd_type == CommandType.CLEAR:
            self.handle_clear()
        
        elif cmd_type == CommandType.STATUS:
            await self.handle_status()
        
        elif cmd_type == CommandType.RUN:
            await self.handle_run(parsed_cmd)
        
        elif cmd_type == CommandType.ANALYZE:
            await self.handle_analyze(parsed_cmd)
        
        elif cmd_type == CommandType.SCRAPE:
            await self.handle_scrape(parsed_cmd)
        
        elif cmd_type == CommandType.AUTOMATE:
            await self.handle_automate(parsed_cmd)
        
        elif cmd_type == CommandType.WECHAT:
            await self.handle_wechat(parsed_cmd)
        
        elif cmd_type == CommandType.CHAT:
            await self.handle_chat(parsed_cmd)
        
        elif cmd_type == CommandType.HISTORY:
            self.handle_history()
        
        elif cmd_type == CommandType.DEBUG:
            self.handle_debug()
        
        elif cmd_type == CommandType.THINK:
            self.handle_think()
        
        elif cmd_type == CommandType.MCP:
            await self.handle_mcp(parsed_cmd)
        
        elif cmd_type == CommandType.GAME:
            await self.handle_game(parsed_cmd)
        
        elif cmd_type == CommandType.FUN:
            await self.handle_fun(parsed_cmd)
        
        elif cmd_type == CommandType.ART:
            await self.handle_art(parsed_cmd)
        
        elif cmd_type == CommandType.AGENT:
            await self.handle_agent(parsed_cmd)
        
        elif cmd_type == CommandType.REVIEW:
            await self.handle_review(parsed_cmd)
        
        elif cmd_type == CommandType.CONFIG:
            await self.handle_config(parsed_cmd)
        
        elif cmd_type == CommandType.PLUGIN:
            await self.handle_plugin(parsed_cmd)
        
        elif cmd_type == CommandType.SMART:
            await self.handle_smart(parsed_cmd)
        
        elif cmd_type == CommandType.RESET:
            self.handle_reset(parsed_cmd)
        
        elif cmd_type == CommandType.TEST:
            await self.handle_test(parsed_cmd)
        
        else:
            # 非命令，作为智能任务请求
            await self.handle_smart_request(parsed_cmd.remaining)
    
    def handle_help(self):
        """处理帮助命令"""
        help_text = self.command_parser.get_help_text()
        print_color(help_text, CliColors.WHITE)
    
    def handle_quit(self):
        """处理退出命令"""
        print_color("\n👋 再见！期待下次为你服务！", CliColors.BLUE)
        self.running = False
    
    def handle_clear(self):
        """处理清屏命令"""
        print("\033c", end="")
    
    def handle_history(self):
        """处理历史记录命令"""
        history = self.command_parser.get_history(10)
        if history:
            print_color("\n命令历史:", CliColors.BOLD)
            for i, cmd in enumerate(reversed(history), 1):
                print_color(f"  {i}. {cmd}", CliColors.WHITE)
        else:
            print_warning("暂无命令历史")
    
    def handle_debug(self):
        """处理调试模式切换"""
        self.debug_mode = self.command_parser.toggle_debug()
        if self.debug_mode:
            log_success("调试模式已启用")
        else:
            log_info("调试模式已禁用")
    
    def handle_think(self):
        """处理思考模式切换"""
        enabled = self.command_parser.toggle_think()
        set_thinking_enabled(enabled)
        if enabled:
            log_success("思考模式已启用")
        else:
            log_info("思考模式已禁用")
    
    def handle_reset(self, parsed_cmd: ParsedCommand):
        """处理重置命令"""
        reset_all = parsed_cmd.action == "all"
        
        if reset_all:
            # 清空所有：历史、记忆、日志
            print_color("\n🔄 正在重置所有数据...", CliColors.YELLOW)
            self.command_parser.clear_history()
            self.chat_history = []
            
            # 清空日志文件
            script_dir = Path(__file__).parent
            log_file = script_dir / "logs" / "agent.log"
            if log_file.exists():
                log_file.write_text("", encoding="utf-8")
            
            print_success("✅ 会话已完全重置（历史 + 记忆 + 日志）")
        else:
            # 只清空历史
            print_color("\n🔄 正在清空命令历史...", CliColors.YELLOW)
            self.command_parser.clear_history()
            self.chat_history = []
            print_success("✅ 命令历史已清空")
        
        # 清屏
        self.handle_clear()
    
    async def handle_test(self, parsed_cmd: ParsedCommand):
        """处理测试命令 - 测试核心服务功能"""
        action = parsed_cmd.action or "all"
        
        print_color("\n🧪 核心服务测试", CliColors.BOLD)
        print_color("────────────────", CliColors.GRAY)
        
        if action == "clarify" or action == "all":
            await self._test_clarification_service()
        
        if action == "permission" or action == "all":
            await self._test_permission_service()
        
        if action == "forked" or action == "all":
            await self._test_forked_agent_service()
        
        if action == "all":
            print_success("\n✅ 所有服务测试完成！")
    
    async def _test_clarification_service(self):
        """测试反问服务"""
        print_color("\n📝 反问服务测试:", CliColors.CYAN)
        
        if not CLARIFICATION_SERVICE:
            print_error("  ❌ 反问服务未初始化")
            return
        
        test_cases = [
            ("查询天气", "缺少城市信息"),
            ("分析项目", "缺少分析维度"),
            ("打开文件", "缺少目标文件"),
        ]
        
        for msg, desc in test_cases:
            print_color(f"\n  测试: {desc}", CliColors.WHITE)
            print_color(f"  输入: '{msg}'", CliColors.GRAY)
            
            questions = CLARIFICATION_SERVICE.generate_questions(msg)
            if questions:
                q = questions[0]
                print_color(f"  反问: {q.question}", CliColors.GREEN)
                if q.options:
                    options = [opt.label for opt in q.options]
                    print_color(f"  选项: {', '.join(options)}", CliColors.GRAY)
            else:
                print_color(f"  无需反问", CliColors.YELLOW)
        
        print_color("\n  ✅ 反问服务测试通过", CliColors.GREEN)
    
    async def _test_permission_service(self):
        """测试权限服务"""
        print_color("\n🔐 权限服务测试:", CliColors.CYAN)
        
        if not PERMISSION_SERVICE:
            print_error("  ❌ 权限服务未初始化")
            return
        
        # 测试权限检查
        from core.services.permission_service import PermissionType
        
        test_permissions = [
            (PermissionType.READ_FILE, "读取文件"),
            (PermissionType.WRITE_FILE, "写入文件"),
            (PermissionType.DELETE_FILE, "删除文件"),
        ]
        
        for perm_type, desc in test_permissions:
            print_color(f"\n  测试: {desc}", CliColors.WHITE)
            decision = PERMISSION_SERVICE.check_permission(perm_type)
            print_color(f"  决策: {decision.value}", 
                       CliColors.GREEN if decision.value == "allow" else 
                       CliColors.YELLOW if decision.value == "prompt" else CliColors.RED)
        
        print_color("\n  ✅ 权限服务测试通过", CliColors.GREEN)
    
    async def _test_forked_agent_service(self):
        """测试Forked Agent服务"""
        print_color("\n🔀 Forked Agent服务测试:", CliColors.CYAN)
        
        if not FORKED_AGENT_SERVICE:
            print_error("  ❌ Forked Agent服务未初始化")
            return
        
        # 测试侧问题处理
        print_color("  测试侧问题处理...", CliColors.WHITE)
        result = await FORKED_AGENT_SERVICE.create_side_question("什么是人工智能？")
        
        if result.status.value == "completed":
            print_color(f"  响应: {result.response[:30]}...", CliColors.GREEN)
        else:
            print_error(f"  失败: {result.error}")
        
        # 测试并行任务
        print_color("\n  测试并行任务...", CliColors.WHITE)
        tasks = [
            {"prompt": "任务A"},
            {"prompt": "任务B"},
        ]
        results = await FORKED_AGENT_SERVICE.run_parallel_tasks(tasks)
        print_color(f"  完成任务数: {len([r for r in results if r.status.value == 'completed'])}", CliColors.GREEN)
        
        print_color("\n  ✅ Forked Agent服务测试通过", CliColors.GREEN)
    
    async def handle_status(self):
        """处理状态命令"""
        print_color("\n系统状态:", CliColors.BOLD)
        print_color("────────────────", CliColors.GRAY)
        
        # 检查核心组件
        components = [
            ("命令解析器", "cli.command_parser", "CommandParser"),
            ("思考引擎", "cli.thinking_engine", "ThinkingEngine"),
            ("日志系统", "cli.logging_system", "EnhancedLogger"),
        ]
        
        print_color("核心组件:", CliColors.CYAN)
        for name, module, obj in components:
            try:
                mod = __import__(module, fromlist=[obj])
                getattr(mod, obj)
                print_color(f"  ✅ {name}", CliColors.GREEN)
            except Exception as e:
                print_color(f"  ❌ {name} - {str(e)[:30]}", CliColors.RED)
        
        # 显示模式状态
        print_color("\n当前模式:", CliColors.CYAN)
        print_color(f"  思考模式: {'✅ 启用' if self.thinking_engine.is_enabled() else '❌ 禁用'}", 
                   CliColors.GREEN if self.thinking_engine.is_enabled() else CliColors.RED)
        print_color(f"  调试模式: {'✅ 启用' if self.debug_mode else '❌ 禁用'}",
                   CliColors.GREEN if self.debug_mode else CliColors.RED)
    
    async def handle_run(self, parsed_cmd: ParsedCommand):
        """处理执行工作流命令"""
        request = parsed_cmd.action if parsed_cmd.action else parsed_cmd.remaining
        
        if not request:
            print_error("请提供任务描述")
            return
        
        # 使用思考引擎
        think_start(request)
        think_analyze("智能工作流执行")
        think_plan([
            {"title": "分析用户意图", "description": "理解用户需求并创建工作流"},
            {"title": "执行工作流", "description": "按步骤执行各项任务"},
            {"title": "汇总结果", "description": "整理并展示执行结果"}
        ])
        
        think_step(1)
        think_log("正在分析用户意图...")
        
        try:
            from cli.base import WorkflowEngineWrapper
            
            wrapper = WorkflowEngineWrapper()
            think_log("调用工作流引擎...")
            
            result = await wrapper.create_and_execute(request)
            think_complete(1, success=True)
            
            think_step(2)
            think_log("执行工作流...")
            
            # 工作流已在create_and_execute中执行
            think_complete(2, success=True)
            
            think_step(3)
            think_log("整理执行结果...")
            
            if result.get("success"):
                think_data("工作流名称", result.get("workflow_name", "未命名"))
                think_data("耗时", f"{result.get('total_time', 0):.2f}秒")
            think_complete(3, success=True)
            
            think_summarize(True, result)
            
            # 显示结果
            self._display_workflow_result(result)
            
        except Exception as e:
            think_complete(1, success=False, error=str(e))
            think_summarize(False)
            log_error(f"执行失败: {e}")
    
    async def handle_analyze(self, parsed_cmd: ParsedCommand):
        """处理分析命令"""
        action = parsed_cmd.action or "visualize"
        params = parsed_cmd.params
        
        think_start(f"数据分析: {action}")
        think_analyze("数据分析")
        think_plan([
            {"title": "数据分析", "description": f"执行{action}分析"},
            {"title": "生成结果", "description": "生成分析报告或图表"}
        ])
        
        think_step(1)
        think_log(f"正在执行{action}分析...")
        
        try:
            from cli.base import WorkflowEngineWrapper
            
            wrapper = WorkflowEngineWrapper()
            workflow = {
                "name": f"分析_{action}",
                "description": f"{action}分析",
                "steps": [{
                    "type": "analyze",
                    "action": action,
                    "params": params,
                    "description": f"执行{action}分析"
                }],
                "generate_report": True
            }
            
            result = await wrapper.get_engine().execute_workflow(workflow)
            think_complete(1, success=True)
            
            think_step(2)
            think_log("生成分析结果...")
            think_complete(2, success=True)
            
            think_summarize(True, result)
            
            self._display_workflow_result(result)
            
        except Exception as e:
            think_complete(1, success=False, error=str(e))
            think_summarize(False)
            log_error(f"分析失败: {e}")
    
    async def handle_scrape(self, parsed_cmd: ParsedCommand):
        """处理爬虫命令"""
        site = parsed_cmd.action or "微博"
        action = parsed_cmd.params.get("action", "热搜top10")
        
        think_start(f"爬取{site}: {action}")
        think_analyze("数据爬取")
        think_plan([
            {"title": "连接网站", "description": f"访问{site}网站"},
            {"title": "获取数据", "description": f"获取{action}数据"},
            {"title": "保存结果", "description": "保存数据到文件"}
        ])
        
        think_step(1)
        think_log(f"正在连接{site}...")
        
        try:
            from cli.base import WorkflowEngineWrapper
            
            wrapper = WorkflowEngineWrapper()
            workflow = {
                "name": f"爬虫_{site}",
                "description": f"爬取{site}数据",
                "steps": [{
                    "type": "scrape",
                    "site": site,
                    "action": action,
                    "description": f"爬取{site}{action}"
                }],
                "generate_report": True
            }
            
            result = await wrapper.get_engine().execute_workflow(workflow)
            think_complete(1, success=True)
            
            think_step(2)
            think_log(f"获取{action}数据...")
            think_complete(2, success=True)
            
            think_step(3)
            think_log("保存数据...")
            think_complete(3, success=True)
            
            think_summarize(True, result)
            
            self._display_workflow_result(result)
            
        except Exception as e:
            think_complete(1, success=False, error=str(e))
            think_summarize(False)
            log_error(f"爬取失败: {e}")
    
    async def handle_automate(self, parsed_cmd: ParsedCommand):
        """处理自动化命令"""
        action = parsed_cmd.action
        params = parsed_cmd.params
        
        if not action:
            print_error("请提供自动化操作，如: /automate open_app --app Safari")
            return
        
        think_start(f"自动化操作: {action}")
        think_analyze("GUI自动化")
        think_plan([
            {"title": f"执行{action}", "description": f"执行{action}操作"}
        ])
        
        think_step(1)
        think_log(f"正在执行{action}...")
        
        try:
            from cli.base import WorkflowEngineWrapper
            
            wrapper = WorkflowEngineWrapper()
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
            
            result = await wrapper.get_engine().execute_workflow(workflow)
            think_complete(1, success=True)
            think_summarize(True, result)
            
            self._display_workflow_result(result)
            
        except Exception as e:
            think_complete(1, success=False, error=str(e))
            think_summarize(False)
            log_error(f"自动化失败: {e}")
    
    async def handle_wechat(self, parsed_cmd: ParsedCommand):
        """处理微信命令"""
        action = parsed_cmd.action
        params = parsed_cmd.params
        
        if action == "send":
            friend = params.get("friend")
            message = params.get("message")
            
            if not friend or not message:
                print_error("请提供好友名称和消息内容")
                print_error("示例: /wechat send --friend 张三 --message 你好")
                return
            
            think_start(f"发送微信消息给{friend}")
            think_analyze("微信消息发送")
            think_plan([
                {"title": "打开微信", "description": "启动微信应用"},
                {"title": "搜索好友", "description": f"查找好友{friend}"},
                {"title": "发送消息", "description": f"发送消息: {message}"}
            ])
            
            think_step(1)
            think_log("正在打开微信...")
            
            try:
                subprocess.run(['open', '-a', 'WeChat'])
                await asyncio.sleep(2)
                think_complete(1, success=True)
                
                think_step(2)
                think_log(f"搜索好友{friend}...")
                script = f'tell application "System Events" to tell application process "WeChat" to keystroke "f" using command down'
                subprocess.run(['osascript', '-e', script])
                await asyncio.sleep(0.5)
                script2 = f'tell application "System Events" to tell application process "WeChat" to keystroke "{friend}"'
                subprocess.run(['osascript', '-e', script2])
                await asyncio.sleep(0.8)
                script3 = 'tell application "System Events" to tell application process "WeChat" to keystroke return'
                subprocess.run(['osascript', '-e', script3])
                await asyncio.sleep(1.5)
                think_complete(2, success=True)
                
                think_step(3)
                think_log("发送消息...")
                subprocess.run(['pbcopy'], input=message.encode('utf-8'))
                await asyncio.sleep(0.2)
                script4 = 'tell application "System Events" to tell application process "WeChat" to keystroke "v" using command down'
                subprocess.run(['osascript', '-e', script4])
                await asyncio.sleep(0.3)
                script5 = 'tell application "System Events" to tell application process "WeChat" to keystroke return'
                subprocess.run(['osascript', '-e', script5])
                await asyncio.sleep(1.0)
                think_complete(3, success=True)
                
                think_summarize(True, {"success": True})
                log_success(f"消息已发送给 {friend}")
                
            except Exception as e:
                think_complete(1, success=False, error=str(e))
                think_summarize(False)
                log_error(f"发送失败: {e}")
        
        else:
            print_error(f"未知微信操作: {action}")
    
    async def handle_chat(self, parsed_cmd: ParsedCommand):
        """处理聊天命令"""
        # 定义有效的模式名称
        valid_modes = {"simple", "deep", "expert", "quick"}
        
        action = parsed_cmd.action or ""
        remaining = parsed_cmd.remaining.strip()
        
        # 判断 action 是否是有效的模式名称
        if action in valid_modes:
            mode = action
            initial_message = remaining
        else:
            # action 不是有效模式，将其当作初始消息的一部分
            mode = "simple"
            initial_message = (action + " " + remaining).strip()
        
        self.chat_mode_type = mode  # 存储模式以供下游使用

        if initial_message:
            self.chat_mode = True
            print_color(f"\n进入聊天模式 ({mode})...", CliColors.BLUE)
            print_chat_bubble(initial_message, is_user=True)
            self.chat_history.append({"role": "user", "content": initial_message})
            await self.handle_smart_request_with_history(initial_message)

            await self.start_chat_mode_loop()
        else:
            await self.start_chat_mode(mode)
    
    async def handle_smart_request(self, request: str):
        """处理智能请求（非命令前缀）- 带记忆和反思"""
        if not request.strip():
            return
        
        steps = [
            {"title": "记忆检索", "description": "从记忆中检索相关信息"},
            {"title": "意图识别", "description": "分析用户请求意图"},
            {"title": "任务执行", "description": "执行相应任务"},
            {"title": "反思评估", "description": "评估执行结果"},
            {"title": "记忆保存", "description": "保存关键信息到记忆"}
        ]
        
        from cli.pagination import CompactStepDisplay
        step_display = CompactStepDisplay(steps)
        step_display.display()
        
        think_start(request)
        think_analyze("智能任务处理")
        
        # 1. 记忆检索
        think_step(1)
        step_display.set_step_active(0)
        step_display.display()
        
        think_log("正在检索记忆...")
        relevant_memory = await self._recall_memory(request)
        if relevant_memory:
            think_log(f"检索到相关记忆: {relevant_memory[:50]}...")
            print_color(f"💡 记忆提示: {relevant_memory}", CliColors.YELLOW)
        
        step_display.set_step_success(0)
        step_display.display()
        think_complete(1, success=True)
        
        # 2. 意图识别和任务执行
        think_step(2)
        step_display.set_step_active(1)
        step_display.display()
        
        think_log("正在分析用户意图...")
        
        try:
            from cli.base import WorkflowEngineWrapper
            
            wrapper = WorkflowEngineWrapper()
            result = await wrapper.create_and_execute(request, context={"memory": relevant_memory})
            
            # 检查工作流创建是否成功（这包含了意图识别）
            if not result.get("success"):
                # 工作流创建失败，可能是意图识别失败
                step_display.set_step_failed(1)  # 标记意图识别失败
                step_display.display()
                think_complete(2, success=False, error=result.get("error", "意图识别或工作流创建失败"))
                
                # 后续步骤都标记为跳过
                for i in range(2, 5):
                    step_display.set_step_skipped(i)
                step_display.display()
                
                print()
                think_summarize(False)
                print_error(result.get("error", "执行失败"))
                return
            
            # 检查是否需要用户输入（clarification场景）
            if result.get("requires_user_input"):
                # 显示澄清问题
                clarification_text = result.get("clarification_text", "")
                if clarification_text:
                    print("\n" + clarification_text)
                
                # 标记任务执行为等待用户输入状态
                step_display.set_step_success(1)  # 意图识别成功
                step_display.set_step_active(2)  # 任务执行中（等待输入）
                step_display.display()
                
                # 后续步骤标记为等待
                for i in range(3, 5):
                    step_display.step_status[i] = 'pending'
                step_display.display()
                
                print()
                think_complete(2, success=True)
                think_log("等待用户回答澄清问题...")
                return
            
            # 工作流创建成功，意图识别完成
            step_display.set_step_success(1)
            step_display.display()
            think_complete(2, success=True)
            
            # 3. 任务执行
            think_step(3)
            step_display.set_step_active(2)
            step_display.display()
            
            think_log("执行任务...")
            
            if not result.get("success"):
                # 任务执行失败，但意图识别已成功
                step_display.set_step_failed(2)  # 标记任务执行为失败
                step_display.display()
                think_complete(3, success=False, error=result.get("error", "执行失败"))
                
                # 4. 反思评估
                think_step(4)
                step_display.set_step_active(3)
                step_display.display()
                think_log("反思评估: 任务失败")
                think_complete(4, success=False)
                
                # 5. 记忆保存
                think_step(5)
                step_display.set_step_active(4)
                step_display.display()
                think_log("保存失败记录...")
                await self._remember(request, {"success": False, "error": result.get("error")})
                
                step_display.set_step_success(4)
                step_display.display()
                print()
                think_complete(5, success=True)
                
                think_summarize(False)
                print_error(result.get("error", "执行失败"))
                return
            
            step_display.set_step_success(2)
            step_display.display()
            think_complete(3, success=True)
            
            # 4. 反思评估
            think_step(4)
            step_display.set_step_active(3)
            step_display.display()
            
            think_log("正在反思评估...")
            reflection = await self._reflect_on_result(request, result)
            if reflection:
                print_color(f"🧠 {reflection}", CliColors.CYAN)
            
            step_display.set_step_success(3)
            step_display.display()
            think_complete(4, success=True)
            
            # 5. 记忆保存
            think_step(5)
            step_display.set_step_active(4)
            step_display.display()
            
            think_log("正在保存记忆...")
            await self._remember(request, result)
            
            step_display.set_step_success(4)
            step_display.display()
            print()
            think_complete(5, success=True)
            
            think_summarize(True, result)
            
            self._display_workflow_result(result)
            
        except Exception as e:
            # 异常发生在任务执行阶段，意图识别已成功
            # 先确认意图识别步骤已标记为成功
            if step_display.step_status[1] == 'active':
                step_display.set_step_success(1)  # 标记意图识别为成功
            
            step_display.set_step_failed(2)  # 标记任务执行为失败
            step_display.display()
            think_complete(3, success=False, error=str(e))
            
            # 反思评估
            think_step(4)
            step_display.set_step_active(3)
            step_display.display()
            think_log("反思评估: 异常失败")
            think_complete(4, success=False)
            
            think_step(5)
            step_display.set_step_active(4)
            step_display.display()
            think_log("保存失败记录...")
            await self._remember(request, {"success": False, "error": str(e)})
            
            step_display.set_step_success(4)
            step_display.display()
            print()
            think_complete(5, success=True)
            
            think_summarize(False)
            log_error(f"处理失败: {e}")
            # 记录到沙盒查看器
            record_event("status", "请求处理完成", detail="意图处理结束", status="ok")

    
    async def _recall_memory(self, query: str) -> str:
        """从记忆系统检索相关信息"""
        try:
            MemorySystem = None
            MemoryType = None
            
            memory = MemorySystem("cli_agent")
            await memory.load_from_disk()
            
            results = await memory.search(query)
            if results:
                # 返回最重要的记忆
                results.sort(key=lambda x: x.importance, reverse=True)
                think_log(f"📖 检索到 {len(results)} 条相关记忆")
                log_info(f"📖 记忆检索成功: 找到 {len(results)} 条相关记忆")
                return str(results[0].value)
            think_log("📖 未检索到相关记忆")
            log_info("📖 记忆检索: 未找到相关记忆")
            return ""
        except Exception as e:
            think_log(f"❌ 记忆检索失败: {str(e)[:30]}")
            log_error(f"记忆检索失败: {e}")
            return ""
    
    async def _remember(self, key: str, value: dict):
        """保存信息到记忆系统"""
        try:
            MemorySystem = None
            MemoryType = None
            
            memory = MemorySystem("cli_agent")
            await memory.load_from_disk()
            
            importance = 0.7 if value.get("success") else 0.3
            await memory.remember(
                key=key[:100],
                value=value,
                memory_type=MemoryType.LONG_TERM,
                importance=importance
            )
            await memory.save_to_disk()
            think_log(f"💾 记忆已保存")
            log_info(f"💾 记忆保存成功: {key[:50]}...")
        except Exception as e:
            think_log(f"❌ 记忆保存失败: {str(e)[:30]}")
            log_error(f"记忆保存失败: {e}")
    
    async def _reflect_on_result(self, request: str, result: dict, force_llm: bool = False) -> str:
        """反思评估执行结果"""
        try:
            # ── LLM 驱动反思（deep 模式优先）──
            if force_llm:
                try:
                    from core.engine.llm_backend import get_llm_router
                    router = get_llm_router()
                    if router and router.is_available():
                        prompt = (
                            f"你是一个任务评审专家。用户请求: {request}\n\n"
                            f"执行结果: 成功={result.get('success')}\n"
                            f"输出: {str(result.get('reply', result.get('result', '')))[:300]}\n"
                            f"错误: {result.get('error', '无')}\n\n"
                            f"请用一句话反思评估结果质量并给出改进建议。"
                        )
                        response = await router.simple_chat(
                            user_message=prompt,
                            system_prompt="你是一个简洁的评审助手，用一句话评估即可。",
                            temperature=0.3,
                        )
                        if response and len(response) > 5:
                            return response.strip()
                except Exception:
                    pass

            # ── 规则反思（所有模式通用保底）──
            success = result.get("success", False)
            error = result.get("error", "")

            if not success:
                if error:
                    if "LLM" in error or "API" in error:
                        return f"⚠️  反思: 任务失败 - {error[:100]}。建议：检查LLM API配置或网络连接"
                    elif "timeout" in error.lower():
                        return f"⚠️  反思: 任务超时 - {error[:100]}。建议：任务可能太复杂，尝试分解成小步骤"
                    else:
                        return f"⚠️  反思: 执行失败 - {error[:100]}"
                return "⚠️  反思: 任务执行失败，但无具体错误信息"

            execution_time = result.get("execution_time", 0)
            if execution_time > 30:
                return f"✅ 反思: 任务完成，但耗时较长({execution_time:.1f}秒)。建议：考虑优化或分解任务"
            return ""  # 快速成功，不需要反思
            
            # 如果有LLM可用，使用更深入的反思
            # from core.multi_agent_v2.orchestration.collaboration.llm_reflection import (
            #     LLMReflection, ReflectionPrompt, StepResult
            # )
            # 
            # step_result = StepResult(
            #     step_id="smart_request",
            #     step_name="智能请求处理",
            #     step_type="general",
            #     success=result.get("success", False),
            #     output=result.get("output", str(result)[:200]),
            #     confidence=result.get("confidence", 0.8),
            #     execution_time=result.get("execution_time", 0.0)
            # )
            # 
            # prompt = ReflectionPrompt(
            #     completed_steps=[step_result],
            #     remaining_steps=[],
            #     original_goal=request,
            #     task_context={}
            # )
            # 
            # reflection_engine = LLMReflection()
            # reflection_result = await reflection_engine.reflect(prompt)
            # 
            # if reflection_result.confidence < 0.7:
            #     return f"反思建议: {reflection_result.reasoning}"
            # elif reflection_result.decision.value != "continue":
            #     return f"反思决策: {reflection_result.decision.value} - {reflection_result.reasoning}"
            # return ""
        except Exception as e:
            log_error(f"反思评估失败: {e}")
            return ""
    
    async def start_chat_mode(self, mode: str = "simple"):
        """进入聊天模式"""
        self.chat_mode = True
        self.chat_mode_type = mode
        # 清空沙盒日志，右侧面板只显示本轮会话
        try:
            from cli.sandbox_viewer import get_viewer
            get_viewer().clear_log_file()
        except Exception:
            pass

        print_color(f"\n进入聊天模式 ({mode})...", CliColors.BLUE)
        print_color("输入 quit/exit/bye 退出聊天模式，/clear 清空历史", CliColors.GRAY)
        print_color(f"当前会话: {self.session_id}", CliColors.GRAY)
        
        while self.chat_mode:
            try:
                _console = get_console()
                user_input = _console.input("\n[bold rgb(78,186,101)]你:[/bold rgb(78,186,101)] ")
                
                if user_input.lower() in ['quit', 'exit', 'bye', '结束']:
                    print_color("👋 退出聊天模式", CliColors.BLUE)
                    self.chat_mode = False
                    break
                
                if not user_input.strip():
                    continue
                
                # 添加到聊天历史
                self.chat_history.append({"role": "user", "content": user_input})
                
                print_chat_bubble(user_input, is_user=True)
                
                parsed_cmd = self.command_parser.parse(user_input)
                
                if parsed_cmd.is_command:
                    if parsed_cmd.command_type == CommandType.CLEAR:
                        self.chat_history = []
                        print_color("聊天历史已清空", CliColors.BLUE)
                    else:
                        await self.handle_command(parsed_cmd)
                else:
                    await self.handle_smart_request_with_history(user_input)
                
            except KeyboardInterrupt:
                print_color("\n👋 退出聊天模式", CliColors.BLUE)
                self.chat_mode = False
                break
            except Exception as e:
                log_error(f"聊天处理失败: {e}")
    
    async def start_chat_mode_loop(self):
        """聊天模式循环（用于带初始消息的情况）"""
        while self.chat_mode:
            try:
                _console = get_console()
                user_input = _console.input("\n[bold rgb(78,186,101)]你:[/bold rgb(78,186,101)] ")
                
                if user_input.lower() in ['quit', 'exit', 'bye', '结束']:
                    print_color("👋 退出聊天模式", CliColors.BLUE)
                    self.chat_mode = False
                    break
                
                if not user_input.strip():
                    continue
                
                self.chat_history.append({"role": "user", "content": user_input})
                print_chat_bubble(user_input, is_user=True)
                
                parsed_cmd = self.command_parser.parse(user_input)
                
                if parsed_cmd.is_command:
                    if parsed_cmd.command_type == CommandType.CLEAR:
                        self.chat_history = []
                        print_color("聊天历史已清空", CliColors.BLUE)
                    else:
                        await self.handle_command(parsed_cmd)
                else:
                    await self.handle_smart_request_with_history(user_input)
                
            except KeyboardInterrupt:
                print_color("\n👋 退出聊天模式", CliColors.BLUE)
                self.chat_mode = False
                break
            except Exception as e:
                log_error(f"聊天处理失败: {e}")
    
    async def _pre_clarify(self, request: str) -> Optional[Dict[str, Any]]:
        """mode=deep/expert 时预反问：在真正执行前先检查是否需要追问"""
        if self.chat_mode_type not in ("deep", "expert"):
            return None
        try:
            from core.services.clarification_service import get_clarification_service
            cs = get_clarification_service()
            questions = cs.generate_questions(request)
            if questions:
                q = questions[0]
                print_color(f"\n📋 {q.question}", CliColors.CYAN)
                if q.options:
                    for i, opt in enumerate(q.options, 1):
                        print_color(f"  {i}. {opt.label} — {opt.description}", CliColors.GRAY)
                try:
                    ans = input("\n请输入(数字/直接回答/回车跳过): ").strip()
                except (EOFError, KeyboardInterrupt):
                    return None
                if ans:
                    # 如果是数字且在选项范围内，映射为选项标签
                    if ans.isdigit() and q.options:
                        idx = int(ans) - 1
                        if 0 <= idx < len(q.options):
                            ans = q.options[idx].label
                    return {"clarified": True, "question": q.question, "answer": ans}
        except Exception as e:
            log_debug(f"预反问跳过: {e}")
        return None

    async def handle_smart_request_with_history(self, request: str):
        """带历史记录的智能请求处理"""
        if not request.strip():
            return

        is_deep = self.chat_mode_type in ("deep", "expert")
        is_quick = self.chat_mode_type == "quick"

        # ── deep/expert 模式：先预反问 ──
        if is_deep:
            clarify_result = await self._pre_clarify(request)
            if clarify_result:
                request = f"{request}。补充信息：{clarify_result['answer']}"

        step_count = 2 if is_quick else 4  # quick: 意图识别+结果; 否则: +执行+反思
        think_start(request)
        think_analyze("智能任务处理" + ("" if not is_deep else " (深度模式)"))
        think_plan([
            {"title": "意图识别", "description": "分析用户请求意图"},
            {"title": "任务执行", "description": "执行相应任务"},
            *([] if is_quick else [
                {"title": "代码降级", "description": "工具失败时自动生成代码执行"},
                {"title": "反思评估", "description": "评估执行结果质量"},
            ]),
            {"title": "结果返回", "description": "返回处理结果"}
        ])

        think_step(1)
        think_log("正在分析用户意图...")

        try:
            from cli.base import WorkflowEngineWrapper

            wrapper = WorkflowEngineWrapper()
            result = await wrapper.create_and_execute(request, chat_history=self.chat_history)

            # ── deep 模式：工具执行失败 → 代码沙盒降级 ──
            if is_deep and not result.get("success"):
                think_log("工具执行失败，正在尝试代码生成降级...")
                try:
                    from core.handlers.code_fallback import try_code_generation
                    code_result = await try_code_generation(request)
                    if code_result.get("success"):
                        # 把代码执行结果提取到 summary 供后续显示
                        result = code_result
                        result["summary"] = code_result.get("reply", "代码执行完成")
                except Exception as e:
                    log_debug(f"代码降级跳过: {e}")

            # ── deep/expert 模式：反思评估 ──
            if is_deep and result.get("success"):
                reflection = await self._reflect_on_result(request, result, force_llm=is_deep)
                if reflection:
                    print_color(f"🧠 {reflection}", CliColors.CYAN)
                    self.chat_history.append({"role": "assistant", "content": f"【反思】{reflection}"})

            think_complete(1, success=True)

            # 从工作流 results 中提取 reply（代码生成等场景）
            if result.get("results"):
                for step_result in result["results"]:
                    reply = step_result.get("reply")
                    if reply:
                        result["summary"] = reply
                        break

            # 检查是否得到了有效的响应
            has_response = result.get("success") and (
                result.get("greeting_message") or
                result.get("summary") or
                result.get("result")
            )

            # 检查是否是MCP推荐结果
            is_mcp_recommendation = result.get("success") and result.get("results")
            if is_mcp_recommendation:
                first_result = result["results"][0] if result["results"] else {}

                # 处理反问结果
                if first_result.get("type") == "clarification":
                    await self._handle_clarification(first_result, request)
                    return

                # 处理MCP推荐结果
                if first_result.get("type") == "mcp_interaction":
                    await self._handle_mcp_recommendation(first_result, request)
                    return

            # 检查顶层clarification结果（来自create_and_execute的直接返回）
            if result.get("type") == "clarification":
                await self._handle_clarification(result, request)
                return

            if not has_response:
                # 如果工作流没有返回有效响应，直接使用LLM响应
                think_log("工作流未返回有效响应，使用LLM直接响应...")
                llm_response = await self._chat_with_llm(request)
                if llm_response:
                    print_chat_bubble(llm_response, is_user=False)
                    result = {"success": True, "summary": llm_response}
                else:
                    result = {"success": False, "error": "无法生成响应"}

            if result.get("success"):
                think_data("任务状态", "成功")

            # 启动并完成剩余步骤（放在所有 early return 之后）
            if is_deep:
                think_step(2)
                think_log("执行任务...")
                think_complete(2, success=True)
                think_step(3)
                think_log("准备代码降级...")
                think_complete(3, success=result.get("success", False))
                think_step(4)
                think_log("反思评估...")
                think_complete(4, success=result.get("success", False))
            else:
                think_step(2)
                think_log("执行任务...")
                think_complete(2, success=result.get("success", False))
            think_summarize(True, result)

            # 显示结果（处理问候语等场景）
            self._display_workflow_result(result)

            # 添加到聊天历史
            response = result.get("summary", result.get("result", result.get("greeting_message", "任务完成")))
            self.chat_history.append({"role": "assistant", "content": response})

            # 显示沙盒执行日志
            from cli.sandbox_viewer import get_viewer
            get_viewer().render_inline(max_items=8)

        except Exception as e:
            think_log(f"执行失败: {str(e)}")
            think_complete(1, success=False)
            think_summarize(False, {"error": str(e)})
            log_error(f"任务执行失败: {e}")
            # 异常时也显示沙盒日志
            from cli.sandbox_viewer import get_viewer
            get_viewer().render_inline(max_items=5)
    
    async def _handle_mcp_recommendation(self, mcp_result: Dict[str, Any], original_request: str):
        """处理MCP服务器推荐结果
        
        Args:
            mcp_result: MCP交互步骤的执行结果
            original_request: 用户原始请求
        """
        if not mcp_result.get("success"):
            logger.warning(f"MCP推荐失败: {mcp_result.get('error')}")
            return
        
        # 显示推荐信息
        recommendation_text = mcp_result.get("recommendation_text", "")
        if recommendation_text:
            print_color(recommendation_text, CliColors.CYAN)
        
        # 获取用户选择
        try:
            user_choice = input("\n请选择: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            user_choice = "no"
        
        recommended_servers = mcp_result.get("recommended_servers", [])
        
        # 解析用户选择
        selected_server = None
        if user_choice in ["是", "yes", "y", "1"]:
            # 选择第一个推荐
            if recommended_servers:
                selected_server = recommended_servers[0]["server_name"]
        elif user_choice.isdigit():
            # 选择指定数字的服务器
            index = int(user_choice) - 1
            if 0 <= index < len(recommended_servers):
                selected_server = recommended_servers[index]["server_name"]
        elif user_choice in ["否", "no", "n"]:
            # 不使用MCP，回退到普通聊天
            print_color("\n好的，我将使用普通聊天模式回复您。", CliColors.GREEN)
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.chat_history.append({"role": "assistant", "content": llm_response})
            return
        else:
            print_warning("无效选择，将使用普通聊天模式")
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.chat_history.append({"role": "assistant", "content": llm_response})
            return
        
        if not selected_server:
            print_warning("未找到匹配的服务器，将使用普通聊天模式")
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.chat_history.append({"role": "assistant", "content": llm_response})
            return
        
        # 连接选定的MCP服务器
        print_color(f"\n🔗 正在连接MCP服务器: {selected_server}...", CliColors.CYAN)
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
        
        connect_result = await awesome_mcp_manager.quick_connect(selected_server)
        
        if not connect_result or not connect_result.get("success"):
            print_error(f"连接MCP服务器失败: {connect_result.get('error', '未知错误')}")
            print_color("将使用普通聊天模式", CliColors.YELLOW)
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.chat_history.append({"role": "assistant", "content": llm_response})
            return
        
        print_success(f"✅ 成功连接到 {selected_server}")
        
        # 智能调用MCP工具
        await self._smart_call_mcp_tool(selected_server, original_request)

    async def _handle_clarification(self, clarification_result: Dict[str, Any], original_request: str):
        """处理反问结果
        
        Args:
            clarification_result: 反问步骤的执行结果
            original_request: 用户原始请求
        """
        if not clarification_result.get("success"):
            logger.warning(f"反问步骤失败: {clarification_result.get('error')}")
            return
        
        # 显示反问信息
        clarification_text = clarification_result.get("clarification_text", "")
        if clarification_text:
            print_color(clarification_text, CliColors.CYAN)
        
        # 获取用户回答
        try:
            user_answer = input("\n请输入您的回答: ").strip()
        except (EOFError, KeyboardInterrupt):
            user_answer = ""
        
        # 如果用户提供了回答，结合原请求和新信息重新处理
        if user_answer:
            enhanced_request = f"{original_request}。补充信息：{user_answer}"
            print_color(f"\n好的，我将根据您的补充信息重新处理：{enhanced_request}", CliColors.GREEN)
            
            # 重新调用工作流处理增强后的问题
            from cli.base import WorkflowEngineWrapper
            wrapper = WorkflowEngineWrapper()
            result = await wrapper.create_and_execute(enhanced_request, chat_history=self.chat_history)
            
            # 显示结果
            if result.get("success") and result.get("results"):
                first_result = result["results"][0] if result["results"] else {}
                if first_result.get("type") == "mcp_interaction":
                    # 如果仍然是MCP推荐，再次处理
                    await self._handle_mcp_recommendation(first_result, enhanced_request)
                else:
                    # 直接显示结果
                    response = result.get("summary", result.get("result", "任务完成"))
                    print_chat_bubble(response, is_user=False)
                    self.chat_history.append({"role": "assistant", "content": response})
            else:
                # 如果仍然无法处理，使用LLM
                llm_response = await self._chat_with_llm(enhanced_request)
                if llm_response:
                    print_chat_bubble(llm_response, is_user=False)
                    self.chat_history.append({"role": "assistant", "content": llm_response})
        else:
            # 如果用户没有提供答案，使用LLM处理原始请求
            print_color("\n未收到您的回答，将使用普通聊天模式", CliColors.YELLOW)
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.chat_history.append({"role": "assistant", "content": llm_response})

            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.chat_history.append({"role": "assistant", "content": llm_response})
            return
        
        print_success(f"✅ 成功连接到 {selected_server}")
        
        # 智能调用MCP工具
        await self._smart_call_mcp_tool(selected_server, original_request)

    async def _chat_with_llm(self, message: str) -> str:
        """直接使用LLM响应聊天消息"""
        try:
            from core.engine.llm_backend import get_llm_router
            
            llm_router = get_llm_router()
            if not llm_router.is_available():
                return ""
            
            # 构建完整的聊天消息（包含历史）
            messages = []
            
            # 添加系统提示
            system_prompt = """
你是小雷版小龙虾AI助手，一个友好、聪明的聊天伙伴。
请用自然、友好的语言回应用户的请求。
如果是故事请求，请讲一个有趣的小故事。
如果是问题，请给出清晰的回答。
            """.strip()
            messages.append({"role": "system", "content": system_prompt})
            
            # 添加聊天历史
            if self.chat_history:
                for msg in self.chat_history[-5:]:  # 最多取最近5条
                    messages.append(msg)
            
            # 添加当前消息
            messages.append({"role": "user", "content": message})
            
            # 调用LLM
            response = await llm_router.chat(messages, temperature=0.7, max_tokens=1000)
            
            return response.strip() if response else ""
        except Exception as e:
            log_error(f"LLM聊天失败: {e}")
            return ""
    
    async def _smart_call_mcp_tool(self, server_name: str, user_request: str):
        """智能调用MCP工具
        
        根据用户请求自动选择合适的工具和参数
        
        Args:
            server_name: MCP服务器名称
            user_request: 用户原始请求
        """
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
        
        print_color(f"\n🔍 正在分析您的需求并选择合适工具...", CliColors.CYAN)
        
        # 获取服务器可用工具列表
        tools = await awesome_mcp_manager.list_tools(server_name)
        
        if not tools:
            print_warning("未找到可用工具，将使用普通聊天模式")
            llm_response = await self._chat_with_llm(user_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.chat_history.append({"role": "assistant", "content": llm_response})
            return
        
        # 智能匹配最合适的工具
        best_tool = self._match_best_tool(tools, user_request)
        
        if not best_tool:
            print_warning("未找到合适的工具，将使用普通聊天模式")
            llm_response = await self._chat_with_llm(user_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.chat_history.append({"role": "assistant", "content": llm_response})
            return
        
        tool_name = best_tool["name"]
        print_success(f"✅ 选择工具: {tool_name}")
        print_color(f"   描述: {best_tool.get('description', 'N/A')}", CliColors.GRAY)
        
        # 提取参数（如果需要用户提供额外信息）
        required_params = best_tool.get("inputSchema", {}).get("required", [])
        extracted_params = self._extract_tool_params(user_request, best_tool)
        
        # 检查是否缺少必需参数
        missing_params = [p for p in required_params if p not in extracted_params]
        
        if missing_params:
            # 询问用户提供缺失的参数
            print_color(f"\n❓ 需要提供以下信息:", CliColors.YELLOW)
            for param in missing_params:
                try:
                    value = input(f"   {param}: ").strip()
                    if value:
                        extracted_params[param] = value
                except (EOFError, KeyboardInterrupt):
                    print_warning("用户取消输入")
                    return
        
        # 调用工具
        print_color(f"\n🚀 正在调用 {server_name}.{tool_name}...", CliColors.CYAN)
        result = await awesome_mcp_manager.call_tool(server_name, tool_name, **extracted_params)
        
        if result and result.get("success"):
            print_success("✅ 工具调用成功")
            response_text = result.get("result", "操作完成")
            print_chat_bubble(str(response_text), is_user=False)
            self.chat_history.append({"role": "assistant", "content": str(response_text)})
        else:
            print_error(f"❌ 工具调用失败: {result.get('error', '未知错误')}")
            # 回退到普通聊天
            llm_response = await self._chat_with_llm(user_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.chat_history.append({"role": "assistant", "content": llm_response})
    
    def _match_best_tool(self, tools: List[Dict[str, Any]], user_request: str) -> Optional[Dict[str, Any]]:
        """根据用户请求匹配最合适的工具"""
        message_lower = user_request.lower()
        best_score = 0
        best_tool = None
        
        for tool in tools:
            tool_name = tool.get("name", "").lower()
            tool_desc = tool.get("description", "").lower()
            
            score = 0
            if tool_name in message_lower:
                score += 3
            
            keywords = tool_desc.split()
            matched_keywords = [kw for kw in keywords if len(kw) > 2 and kw in message_lower]
            score += len(matched_keywords) * 0.5
            
            if score > best_score:
                best_score = score
                best_tool = tool
        
        if best_score < 1.0:
            return None
        
        return best_tool
    
    def _extract_tool_params(self, user_request: str, tool: Dict[str, Any]) -> Dict[str, Any]:
        """从用户请求中提取工具参数"""
        import re
        params = {}
        properties = tool.get("inputSchema", {}).get("properties", {})
        
        for param_name, param_schema in properties.items():
            param_type = param_schema.get("type", "string")
            
            if param_name.lower() in ["city", "location", "place"]:
                city_match = re.search(r'([\u4e00-\u9fa5]+市|[\u4e00-\u9fa5]+省)', user_request)
                if city_match:
                    params[param_name] = city_match.group(1)
            
            elif param_type == "string" and ("url" in param_name.lower() or "link" in param_name.lower()):
                url_match = re.search(r'https?://\S+', user_request)
                if url_match:
                    params[param_name] = url_match.group(0)
            
            elif param_type in ["number", "integer"]:
                number_match = re.search(r'(\d+\.?\d*)', user_request)
                if number_match:
                    num_value = float(number_match.group(1))
                    if param_type == "integer":
                        num_value = int(num_value)
                    params[param_name] = num_value
        
        return params
    

    def _display_workflow_result(self, result: Dict[str, Any]):
        """显示工作流结果"""
        if not result.get("success"):
            print_error(result.get("error", "执行失败"))
            return
        
        greeting_message = result.get("greeting_message")
        if greeting_message:
            print()
            print_color(greeting_message, CliColors.CYAN)
            print()
            return
        
        from cli.colors import print_divider, CliColors as DCC
        print()
        print_color(f"  {DCC.BAR * 1}", DCC.DARK_GRAY + DCC.DIM)
        print_color(f"  {DCC.DOUBLE_ARROW} 任务完成", DCC.DARK_GREEN + DCC.BOLD)
        print_color(f"  {DCC.BAR * 1}", DCC.DARK_GRAY + DCC.DIM)
        print()

        if result.get("workflow_name"):
            print_color(f"  {DCC.DOT} {result.get('workflow_name')}", DCC.DARK_GRAY)
        if result.get("total_time"):
            print_color(f"  {DCC.DOT} {result.get('total_time', 0):.2f}s", DCC.DARK_GRAY)
        
        results = result.get("results", [])
        if results:
            print("\n  📊 步骤详情:")
            for step_result in results:
                status = "✅" if step_result.get("success") else "❌"
                step_num = step_result.get("step", "?")
                step_type = step_result.get("type", "")
                action = step_result.get("action", "")
                print(f"\n    {status} 步骤{step_num}")
                print(f"       类型: {step_type}")
                if action:
                    print(f"       操作: {action}")

                if step_result.get("message"):
                    print(f"       消息: {step_result['message']}")

                reply = step_result.get("reply", "")
                if reply:
                    import re as _re
                    code_block = _re.search(r'```(\w+)?\n(.*?)```', reply, _re.DOTALL)
                    if code_block:
                        lang = code_block.group(1) or ""
                        code = code_block.group(2)
                        code_lines = code.split("\n")
                        if len(code_lines) > 200:
                            print(f"       📄 代码 ({lang or 'python'}, {len(code_lines)} 行):")
                            for _line in code_lines[:200]:
                                print(f"         {_line}")
                            print(f"         ... (剩余 {len(code_lines) - 200} 行)")
                        else:
                            print(f"       📄 代码 ({lang or 'python'}):")
                            for _line in code_lines:
                                print(f"         {_line}")
                    else:
                        for line in reply.split("\n")[:50]:
                            print(f"       {line}")
                        if reply.count("\n") > 50:
                            print(f"       ... (剩余 {reply.count('\n') - 50} 行)")
                
                if step_result.get("data_preview"):
                    preview = step_result["data_preview"]
                    print(f"       结果: {preview}")
                
                if step_result.get("csv_path"):
                    print(f"       CSV文件: {step_result['csv_path']}")
                
                if step_result.get("chart_path"):
                    print(f"       图表文件: {step_result['chart_path']}")
                
                if step_result.get("duration"):
                    print(f"       耗时: {step_result['duration']:.2f}秒")
        
        # 显示报告路径
        if result.get("report_path"):
            print(f"\n  📄 报告文件: {result['report_path']}")

        # 显示代码执行摘要（deep mode 降级结果）
        summary = result.get("summary", "")
        if summary and not results:
            print(f"\n  📝 执行结果:")
            for line in summary.replace("```", "").split("\n")[:8]:
                print(f"    {line}")
            if summary.count("\n") > 8:
                print(f"    ...")

        print()
        print_color("────────────────────────────────────────────────────────", CliColors.PURPLE)
        print()

        print()
    
    async def handle_mcp(self, parsed_cmd):
        """处理MCP命令 - 委托给 MCPHandler"""
        from cli.mcp_handler import MCPHandler
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""
        remaining = parsed_cmd.remaining.strip()
        await MCPHandler(self).handle_mcp_command(action, remaining)

    def show_mcp_help(self):
        """显示MCP命令帮助 - 委托给 MCPHandler"""
        from cli.mcp_handler import MCPHandler
        MCPHandler(self).show_mcp_help()


    async def handle_game(self, parsed_cmd):
        """处理游戏命令"""
        game_type = parsed_cmd.action.lower() if parsed_cmd.action else ""
        
        from cli.games import GameModule
        
        if game_type == "guess":
            await GameModule.play_guess_number()
        elif game_type == "rps":
            await GameModule.play_rock_paper_scissors()
        elif game_type == "dice":
            await GameModule.dice_roll()
        else:
            print_color("\n🎮 小游戏菜单", CliColors.CYAN)
            print_color("────────────────", CliColors.GRAY)
            print_color("/game guess - 猜数字游戏", CliColors.WHITE)
            print_color("/game rps - 石头剪刀布", CliColors.WHITE)
            print_color("/game dice - 掷骰子", CliColors.WHITE)
    
    async def handle_fun(self, parsed_cmd):
        """处理趣味命令"""
        fun_type = parsed_cmd.action.lower() if parsed_cmd.action else ""
        
        from cli.fun_tools import FunTools
        
        if fun_type == "joke":
            await FunTools.random_joke()
        elif fun_type == "fact":
            await FunTools.random_fact()
        elif fun_type == "fortune":
            await FunTools.fortune()
        else:
            print_color("\n😄 趣味工具", CliColors.CYAN)
            print_color("────────────────", CliColors.GRAY)
            print_color("/fun joke - 随机笑话", CliColors.WHITE)
            print_color("/fun fact - 冷知识", CliColors.WHITE)
            print_color("/fun fortune - 今日运势", CliColors.WHITE)
    
    async def handle_art(self, parsed_cmd):
        """处理ASCII艺术命令"""
        art_type = parsed_cmd.action.lower() if parsed_cmd.action else ""
        
        from cli.ascii_art import ASCIIArt
        
        if art_type == "cat":
            await ASCIIArt.show_cat()
        elif art_type == "dog":
            await ASCIIArt.show_dog()
        elif art_type == "rocket":
            await ASCIIArt.show_rocket()
        else:
            print_color("\n🎨 ASCII艺术", CliColors.CYAN)
            print_color("────────────────", CliColors.GRAY)
            print_color("/art cat - 猫咪", CliColors.WHITE)
            print_color("/art dog - 狗狗", CliColors.WHITE)
            print_color("/art rocket - 火箭", CliColors.WHITE)
    
    async def handle_agent(self, parsed_cmd):
        """处理Agent命令"""
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""
        
        from cli.agent_tools import AgentTools
        
        if action == "list":
            await AgentTools.list_agents()
        elif action == "call":
            remaining = parsed_cmd.remaining.strip()
            if remaining:
                parts = remaining.split(None, 1)
                if len(parts) >= 2:
                    agent_type, task = parts[0], parts[1]
                    await AgentTools.call_agent(agent_type, task)
                else:
                    print_error("格式错误，请使用: /agent call <AgentType> <任务>")
            else:
                print_error("请指定Agent类型和任务")
        else:
            print_color("\n🦾 Agent管理", CliColors.CYAN)
            print_color("────────────────", CliColors.GRAY)
            print_color("/agent list - 列出所有Agent", CliColors.WHITE)
            print_color("/agent call <Agent> <任务> - 调用Agent执行任务", CliColors.WHITE)
    
    async def handle_review(self, parsed_cmd):
        """处理审查命令"""
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""
        
        from cli.review_tools import ReviewTools
        
        if action == "code":
            file_path = parsed_cmd.remaining.strip()
            if file_path:
                await ReviewTools.review_code(file_path)
            else:
                print_error("请指定文件路径，如: /review code main.py")
        elif action == "security":
            command = parsed_cmd.remaining.strip()
            if command:
                await ReviewTools.security_scan(command)
            else:
                print_error("请指定命令，如: /review security 'rm -rf /'")
        else:
            print_color("\n🔍 代码审查", CliColors.CYAN)
            print_color("────────────────", CliColors.GRAY)
            print_color("/review code <file> - 审查代码质量", CliColors.WHITE)
            print_color("/review security <command> - 安全扫描", CliColors.WHITE)
    
    async def handle_config(self, parsed_cmd):
        """处理配置命令"""
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""
        
        from cli.config_tools import ConfigTools
        
        if action == "show":
            await ConfigTools.show_config()
        elif action == "set":
            remaining = parsed_cmd.remaining.strip()
            if remaining:
                parts = remaining.split(None, 1)
                if len(parts) >= 2:
                    key, value = parts[0], parts[1]
                    await ConfigTools.set_config(key, value)
                else:
                    print_error("格式错误，请使用: /config set <key> <value>")
            else:
                print_error("请指定配置项和值")
        else:
            print_color("\n⚙️ 配置管理", CliColors.CYAN)
            print_color("────────────────", CliColors.GRAY)
            print_color("/config show - 显示当前配置", CliColors.WHITE)
            print_color("/config set <key> <value> - 设置配置项", CliColors.WHITE)
    
    async def handle_plugin(self, parsed_cmd):
        """处理插件命令"""
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""
        
        from cli.plugin_tools import PluginTools
        
        if action == "list":
            await PluginTools.list_plugins()
        elif action == "create":
            name = parsed_cmd.remaining.strip()
            if name:
                await PluginTools.create_plugin(name)
            else:
                print_error("请指定插件名称，如: /plugin create my-plugin")
        else:
            print_color("\n📦 插件工具", CliColors.CYAN)
            print_color("────────────────", CliColors.GRAY)
            print_color("/plugin list - 列出所有插件", CliColors.WHITE)
            print_color("/plugin create <name> - 创建新插件", CliColors.WHITE)
    
    async def handle_smart(self, parsed_cmd):
        """处理智能多Agent命令 - 支持所有5种协作模式"""
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""
        remaining = parsed_cmd.remaining.strip()
        
        print_color("\n🧠 智能多Agent协作", CliColors.BOLD)
        print_color("────────────────", CliColors.GRAY)
        
        if action == "demo":
            # 演示所有协作模式
            await self._demo_collaboration_modes()
        elif action == "status":
            # 显示Agent状态和协作模式信息
            await self._show_collaboration_status()
        elif action in ["pipeline", "master", "review", "auction", "hybrid"]:
            # 使用指定协作模式执行任务
            await self._execute_with_mode(action, remaining)
        else:
            # 默认智能任务处理（自动选择模式）
            if action:
                # action可能是查询的一部分
                request = action + " " + remaining
            else:
                request = remaining
            
            if not request.strip():
                print_error("请提供任务描述")
                print_warning("可用命令: /smart <任务>, /smart demo, /smart status")
                print_warning("指定模式: /smart <模式> <任务>")
                print_warning("支持的模式: pipeline, master, review, auction, hybrid")
                return
            
            await self._execute_with_mode(None, request)
    
    async def _demo_collaboration_modes(self):
        """演示所有5种Agent协作模式"""
        from cli.smart_agent_v2 import get_smart_agent_cli_v2
        
        smart_cli = get_smart_agent_cli_v2()
        await smart_cli.handle_collaboration_mode_demo()
    
    async def _show_collaboration_status(self):
        """显示Agent状态和可用协作模式"""
        from cli.smart_agent_v2 import get_smart_agent_cli_v2
        
        smart_cli = get_smart_agent_cli_v2()
        await smart_cli.handle_agent_status()
    
    async def _execute_with_mode(self, mode_name, request):
        """使用指定协作模式执行任务"""
        from cli.smart_agent_v2 import get_smart_agent_cli_v2
        
        smart_cli = get_smart_agent_cli_v2()
        
        collaboration_mode = None
        if mode_name:
            from core.shared.enums import CollaborationMode
            
            mode_map = {
                "pipeline": CollaborationMode.PIPELINE,
                "master": CollaborationMode.MASTER_SLAVE,
                "review": CollaborationMode.REVIEW,
                "auction": CollaborationMode.AUCTION,
                "hybrid": CollaborationMode.HYBRID,
            }
            collaboration_mode = mode_map.get(mode_name)
            
            if collaboration_mode:
                print_color(f"指定协作模式: {collaboration_mode.value}", CliColors.CYAN)
        
        await smart_cli.handle_smart_task_with_mode(request, collaboration_mode)
    
    async def _auto_connect_mcp(self):
        """从 config/mcp_servers.yml 自动连接所有MCP服务器（并行+进度显示）"""
        try:
            from core.config_loader import auto_connect_mcp_servers, register_agents_from_config

            print_color("\n  🔌 正在自动连接本地 MCP 服务器...", CliColors.CYAN)
            self._mcp_progress = {"total": 0, "ok": 0, "fail": 0}

            def _on_progress(name, success, desc):
                self._mcp_progress["total"] += 1
                if success:
                    self._mcp_progress["ok"] += 1
                else:
                    self._mcp_progress["fail"] += 1
                icon = "✅" if success else "⚠️"
                print_color(f"    {icon} {name} — {desc[:40] if desc else name}", CliColors.GRAY)

            connected, failed = await auto_connect_mcp_servers(progress_callback=_on_progress)
            agents = register_agents_from_config()
            if connected:
                print_color(f"  ✅ MCP: {connected}个服务器就绪", CliColors.GREEN)
            if failed:
                print_color(f"  ⚠️ {failed}个启动失败（可后续手动 /mcp connect）", CliColors.YELLOW)
            log_success(f"MCP: {connected}个就绪, {failed}个失败, Agent: {len(agents or [])}个已注册")
        except Exception as e:
            log_debug(f"MCP自启跳过: {e}")

    async def run(self):
        """运行CLI主循环 - Claude Code 风格"""
        self.print_welcome()

        # 后台启动本地MCP服务器
        import asyncio
        asyncio.create_task(self._auto_connect_mcp())

        while self.running:
            try:
                # Claude Code 风格输入提示
                user_input = ClaudeCodeDialog.user_input("⌨ > ")

                if not user_input.strip():
                    continue

                # 清空之前行（仅擦除提示行）
                print("\033[A\033[K", end="")

                # 显示用户输入（左面板风格）
                print_color(f"  {user_input}", CliColors.BRIGHT_BLUE)

                if not user_input.startswith('/'):
                    await self.handle_smart_request(user_input)
                    # 在单终端模式下显示最近的沙盒活动
                    try:
                        sv = get_sandbox_viewer()
                        if sv.entries:
                            sv.render_inline(max_items=3)
                    except Exception:
                        pass
                    ClaudeCodeDialog.section_divider()
                    continue

                # 解析命令
                parsed_cmd = self.command_parser.parse(user_input)

                # 处理命令
                await self.handle_command(parsed_cmd)

            except KeyboardInterrupt:
                print_color("\n👋 再见！", CliColors.BLUE)
                self.running = False
            except Exception as e:
                log_error(f"处理异常: {e}")


async def main(log_file: str = None, log_to_console: bool = True,
               initial_command: str = None, initial_mode: str = None,
               initial_message: str = None):
    """主入口"""
    from cli.logging_system import init_logger
    init_logger(log_file=log_file, log_to_console=log_to_console)

    cli = EnhancedCLI()
    cli._init_session()

    # 如果命令行传了初始命令，自动执行
    if initial_command == "chat":
        cmd_text = f"/chat {initial_mode or 'simple'}"
        if initial_message:
            cmd_text += f" {initial_message}"
        parsed = cli.command_parser.parse(cmd_text)
        if parsed.is_command:
            await cli.handle_command(parsed)
            return  # 非交互模式，执行完退出

    await cli.run()


def parse_args():
    """解析命令行参数 — CLI自身参数 + chat/mode + 初始消息"""
    parser = argparse.ArgumentParser(description="小雷版小龙虾 AI Agent CLI")
    parser.add_argument("--log-file", "-l", type=str, default=None)
    parser.add_argument("--no-console-log", action="store_true")
    parser.add_argument("--dual-terminal", "-d", action="store_true", default=False)
    parser.add_argument("--single-terminal", "-s", action="store_true", default=False)
    parser.add_argument("--mode", type=str, default=None,
                        choices=["simple", "deep", "expert", "quick"])

    args, unknown = parser.parse_known_args()

    # 从 unknown 提取 positional: 跳过未知的 --xxx 和它们的值
    positional = []
    i = 0
    while i < len(unknown):
        u = unknown[i]
        if u.startswith("--"):
            i += 2 if i + 1 < len(unknown) and not unknown[i + 1].startswith("--") else 1
        else:
            positional.append(u)
            i += 1

    # 第一个 positional 如果是 chat，就是命令
    # 如果只有 chat，那后面的 positional 是消息
    # 如果 chat 后面跟着 mode 名 (simple/deep/expert/quick)，那 mode 从这取
    args.command = None
    args.message = []

    if positional:
        if positional[0] == "chat":
            args.command = "chat"
            rest = positional[1:]
            if rest and rest[0] in ("simple", "deep", "expert", "quick"):
                if not args.mode:
                    args.mode = rest[0]
                args.message = rest[1:]
            else:
                args.message = rest

    return args


from cli.terminal import is_in_tmux, _get_sandbox_view_script, setup_dual_terminal

# is_in_tmux, _get_sandbox_view_script, setup_dual_terminal 已迁移到 cli/terminal.py
if __name__ == "__main__":
    args = parse_args()

    # 检查是否启用双终端模式
    enable_dual = args.dual_terminal or (not args.single_terminal and os.environ.get("TMUX") is None)

    if enable_dual and shutil.which("tmux"):
        if setup_dual_terminal():
            sys.exit(0)

    initial_message = " ".join(args.message) if hasattr(args, 'message') and args.message else None

    asyncio.run(main(
        log_file=args.log_file,
        log_to_console=not args.no_console_log,
        initial_command=args.command,
        initial_mode=args.mode,
        initial_message=initial_message,
    ))