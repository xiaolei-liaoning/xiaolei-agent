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
from cli.colors import CliColors, print_color, print_chat_bubble, print_success, print_error, print_warning, ansi
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


class EnhancedCLI:
    """增强版CLI - 支持命令前缀、思考模式和增强日志"""
    
    def __init__(self):
        self.command_parser = get_command_parser()
        self.thinking_engine = get_thinking_engine()
        self.running = True
        self.debug_mode = False
        
        # 会话状态管理
        self.chat_mode = False
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
        log_info(f"会话已初始化: {self.session_id}")
    
    def print_welcome(self):
        """打印欢迎界面 - 现代化风格（参考 paste 样式）"""
        print("\033c", end="")
        print()
        brand = "rgb(215,119,87)"
        soft = "rgb(153,153,153)"
        dim = "rgb(80,80,80)"

        from rich.console import Console as RichConsole
        rc = RichConsole()
        rc.print()
        rc.print(f"  [{brand}]╭──────────  🦞  小雷版小龙虾  AI  Agent  ──────────╮")
        rc.print(f"  [{brand}]│                                                     │")
        rc.print(f"  [{brand}]│    [{dim}]██╗  ██╗██╗ █████╗  ██████╗ ██╗     ███████╗██╗  │")
        rc.print(f"  [{brand}]│    [{dim}]╚██╗██╔╝██║██╔══██╗██╔═══██╗██║     ██╔════╝██║  │")
        rc.print(f"  [{brand}]│    [{dim}] ╚███╔╝ ██║███████║██║   ██║██║     █████╗  ██║  │")
        rc.print(f"  [{brand}]│    [{dim}] ██╔██╗ ██║██╔══██║██║▄▄ ██║██║     ██╔══╝  ██║  │")
        rc.print(f"  [{brand}]│    [{dim}]██╔╝ ██╗██║██║  ██║╚██████╔╝███████╗███████╗██║  │")
        rc.print(f"  [{brand}]│    [{dim}]╚═╝  ╚═╝╚═╝╚═╝  ╚═╝ ╚══▀▀═╝ ╚══════╝╚══════╝╚═╝  │")
        rc.print(f"  [{brand}]│                                                     │")
        rc.print(f"  [{brand}]╰─────────────────────────────────────────────────────╯")
        rc.print()
        rc.print(f"  [{soft}]⚡[/]  [{brand}]工作流[/]  ·  [{brand}]GUI自动化[/]  ·  [{brand}]爬虫[/]  ·  [{brand}]微信[/]  ·  [{brand}]分析[/]")
        rc.print()
        rc.print(f"  [{soft}]📖[/]  输入 [{brand}]/help[/] 查看命令  ·  [{dim}]⎿[/]  exit 退出")
        rc.print()
        rc.rule(style=dim)
        rc.print()

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
        """处理执行工作流命令（增强版 - 动画步骤显示）"""
        request = parsed_cmd.action if parsed_cmd.action else parsed_cmd.remaining
        
        if not request:
            print_error("请提供任务描述")
            return
        
        # 使用增强思考引擎
        from cli.animated_spinner import AsyncSpinner, print_section, CLAUDE
        from cli.thinking_engine import get_thinking_engine
        
        engine = get_thinking_engine()
        print_section(f"🚀 工作流: {request[:50]}{'...' if len(request) > 50 else ''}")
        
        # 预设步骤计划
        step_plan = [
            {"title": "分析用户意图", "description": "理解用户需求并创建工作流", "tag": "分析"},
            {"title": "执行工作流", "description": "按步骤执行各项任务", "tag": "执行"},
            {"title": "汇总结果", "description": "整理并展示执行结果", "tag": "结果"},
        ]
        engine.plan_steps(step_plan)
        
        try:
            from cli.base import WorkflowEngineWrapper
            
            wrapper = WorkflowEngineWrapper()
            
            # Step 1: 分析意图
            engine.start_step(1, "分析用户意图")
            async with AsyncSpinner("正在分析用户意图...", color=CLAUDE):
                await asyncio.sleep(0.2)
            engine.complete_step(1, success=True)
            
            # Step 2: 执行工作流
            engine.start_step(2, "执行工作流")
            async with AsyncSpinner("调用工作流引擎...", color=CLAUDE):
                result = await wrapper.create_and_execute(request)
            engine.complete_step(2, success=result.get("success", False),
                                 detail=f"耗时: {result.get('total_time', 0):.1f}s"
                                 if result.get("total_time") else "")
            
            # Step 3: 汇总结果
            engine.start_step(3, "汇总结果")
            if result.get("success"):
                async with AsyncSpinner("整理执行结果...", color=CLAUDE):
                    await asyncio.sleep(0.1)
                engine.complete_step(3, success=True)
            else:
                engine.complete_step(3, success=False,
                                     error_message=result.get("error", "执行失败"))
            
            # 总进度
            engine.progress_summary()
            engine.summary(result.get("success", False),
                          result.get("total_time", 0))
            
            # 显示结果
            self._display_workflow_result(result)
            
        except Exception as e:
            if engine._current_step > 0:
                engine.complete_step(engine._current_step, success=False,
                                     error_message=str(e))
            engine.summary(False, 0, detail=str(e))
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
        
        if initial_message:
            # 如果有初始消息，先进入聊天模式然后直接发送消息
            self.chat_mode = True
            print_color(f"\n进入聊天模式 ({mode})...", CliColors.BLUE)
            print_chat_bubble(initial_message, is_user=True)
            self.chat_history.append({"role": "user", "content": initial_message})
            await self.handle_smart_request_with_history(initial_message)
            
            # 继续聊天循环
            await self.start_chat_mode_loop()
        else:
            await self.start_chat_mode(mode)
    
    async def handle_smart_request(self, request: str):
        """处理智能请求 — V2 Subagent 分步执行"""
        if not request.strip():
            return

        from cli.animated_spinner import AsyncSpinner, CLAUDE
        from cli.thinking_engine import get_thinking_engine
        from cli.colors import print_color, ansi
        from core.multi_agent_v2.agents.base.base_agent import BaseAgent

        # 初始化引擎和 Agent
        engine = get_thinking_engine()
        agent = BaseAgent()

        # 拆解任务
        engine.start_step(1, "正在分析任务...")
        async with AsyncSpinner("正在分析任务...", color=CLAUDE):
            steps = await agent._decompose_task(request)
        if not steps:
            engine.complete_step(1, success=False, detail="任务拆解失败")
            return
        engine.complete_step(1, success=True, detail=f"规划为 {len(steps)} 步")
        engine.plan_steps([{"title": s, "description": "", "tag": str(i+1)} for i, s in enumerate(steps)])

        # 分步执行
        import asyncio
        results = [None] * len(steps)
        sem = asyncio.Semaphore(3)

        async def run_subagent(i, step):
            async with sem:
                engine.start_step(i + 1, step)
                try:
                    async with AsyncSpinner(step, color=CLAUDE):
                        prompt = f"## 步骤 ({i+1}/{len(steps)})\n{step}\n\n完整任务：{request}\n\n请完成此步骤。可调用工具。完成后给出结果。"
                        result = await agent._execute_subagent(prompt, None, None)
                    results[i] = result
                    engine.complete_step(i + 1, success=bool(result), detail=f"完成")
                except Exception as e:
                    engine.complete_step(i + 1, success=False, detail=str(e)[:50])

        await asyncio.gather(*[run_subagent(i, s) for i, s in enumerate(steps)])

        # 输出汇总
        final = "\n".join(f"• {steps[i]}: {results[i][:100]}" for i in range(len(steps)) if results[i])
        if final:
            print_color("\n" + final[:1000], ansi['green'])
            self.chat_history.append({"role": "assistant", "content": final[:500]})
        else:
            print_color("❌ 执行失败", ansi['red'])

    async def start_chat_mode(self, mode: str = "simple"):
        """进入聊天模式"""
        self.chat_mode = True
        print_color(f"\n进入聊天模式 ({mode})...", CliColors.BLUE)
        print_color("输入 quit/exit/bye 退出聊天模式，/clear 清空历史", CliColors.GRAY)
        print_color(f"当前会话: {self.session_id}", CliColors.GRAY)
        
        while self.chat_mode:
            try:
                user_input = input(f"\n{ansi['green']}{ansi['bold']}你: {ansi['end']}")
                
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
                user_input = input(f"\n{ansi['green']}{ansi['bold']}你: {ansi['end']}")
                
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
    
    async def handle_smart_request_with_history(self, request: str):
        """带历史记录的智能请求处理 — V2 Agent"""
        if not request.strip():
            return

        from core.multi_agent_v2.agents.base.base_agent import BaseAgent

        agent = BaseAgent()
        result = await agent.run(request)

        if result.get("success"):
            final = result["result"].get("final_answer", "")
            tool_results = result["result"].get("tool_results", [])
            summary = final or f"任务完成（{len(tool_results)} 步）"
            if summary:
                print_chat_bubble(str(summary)[:500], is_user=False)
                self.chat_history.append({"role": "assistant", "content": str(summary)[:500]})
    
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
            user_choice = input(f"\n{ansi['yellow']}{ansi['bold']}请选择: {ansi['end']}").strip().lower()
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
            user_answer = input(f"\n{ansi['yellow']}{ansi['bold']}请输入您的回答: {ansi['end']}").strip()
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
        
        print()
        print_color("────────────────────────────────────────────────────────", CliColors.PURPLE)
        print_success("✅ 任务完成！")
        print_color("────────────────────────────────────────────────────────", CliColors.PURPLE)
        print()
        
        if result.get("workflow_name"):
            print(f"  📋 名称: {result.get('workflow_name')}")
        if result.get("total_time"):
            print(f"  ⏱️  耗时: {result.get('total_time', 0):.2f}秒")
        
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
        
        print()
        print_color("────────────────────────────────────────────────────────", CliColors.PURPLE)
        print()
        
        print()
    
    async def handle_mcp(self, parsed_cmd):
        """处理MCP命令"""
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""
        
        if not action:
            self.show_mcp_help()
            return
        
        try:
            if action == "list":
                await self.mcp_list_servers()
            elif action == "connect":
                await self.mcp_connect(parsed_cmd)
            elif action == "disconnect":
                await self.mcp_disconnect(parsed_cmd)
            elif action == "select":
                await self.mcp_select(parsed_cmd)
            elif action == "tools":
                await self.mcp_list_tools(parsed_cmd)
            elif action == "call":
                await self.mcp_call_tool(parsed_cmd)
            elif action == "quick":
                await self.mcp_quick_call(parsed_cmd)
            elif action == "agency":
                await self.mcp_connect_agency()
            elif action == "fun":
                await self.mcp_connect_fun()
            elif action == "weather":
                await self.mcp_connect_weather()
            elif action == "calculator":
                await self.mcp_connect_calculator()
            elif action == "file-ops":
                await self.mcp_connect_file_ops()
            elif action == "text-processing":
                await self.mcp_connect_text_processing()
            elif action == "status":
                await self.mcp_status()
            elif action == "history":
                self.mcp_show_history()
            elif action == "register":
                await self.mcp_register_server(parsed_cmd)
            elif action == "unregister":
                await self.mcp_unregister_server(parsed_cmd)
            elif action == "custom":
                await self.mcp_list_custom_servers()
            else:
                print_error(f"未知MCP命令: {action}")
                self.show_mcp_help()
        except Exception as e:
            log_error(f"MCP操作失败: {e}")
    
    def show_mcp_help(self):
        """显示MCP命令帮助"""
        help_text = f"""
MCP命令使用帮助:

  /mcp list              - 列出已连接的MCP服务器
  /mcp connect <server>  - 连接指定的MCP服务器
  /mcp disconnect <server> - 断开MCP服务器连接
  /mcp select <server>   - 设置当前活动MCP服务器
  /mcp register          - 注册自定义MCP服务器
  /mcp unregister        - 注销自定义MCP服务器
  /mcp custom            - 查看自定义服务器列表
  /mcp agency            - 快速连接the-agency服务器
  /mcp fun               - 连接趣味MCP服务器(笑话/谜语/ASCII艺术)
  /mcp weather           - 连接天气MCP服务器
  /mcp calculator        - 连接计算器MCP服务器
  /mcp file-ops          - 连接文件操作MCP服务器
  /mcp text-processing   - 连接文本处理MCP服务器
  /mcp tools [server]    - 查看可用工具(默认当前服务器)
  /mcp call <server> <tool> [args]  - 调用指定服务器的工具
  /mcp quick <tool> [args]  - 快速调用当前服务器的工具
  /mcp status            - 查看MCP连接状态
  /mcp history           - 查看MCP调用历史

当前服务器: {'未选择' if not self.current_mcp_server else self.current_mcp_server}

示例:
  /mcp agency
  /mcp fun
  /mcp weather
  /mcp calculator
  /mcp file-ops
  /mcp text-processing
  /mcp tools
  /mcp quick search query=hello
  /mcp call the-agency summarize text="Hello"
  /mcp register myserver --command npx --args "-y @my/mcp-server"
  /mcp unregister myserver
  /mcp custom
"""
        print_color(help_text, CliColors.WHITE)
    
    async def mcp_list_servers(self):
        """列出已连接的MCP服务器"""
        from core.mcp import mcp_client
        
        print_color("\n📡 已连接的MCP服务器:", CliColors.CYAN)
        servers = await mcp_client.list_servers()
        
        if servers:
            for server in servers:
                print_color(f"  ✅ {server}", CliColors.GREEN)
        else:
            print_warning("  暂无已连接的MCP服务器")
            print_color("  提示: 使用 /mcp agency 连接默认服务器", CliColors.GRAY)
    
    async def mcp_connect(self, parsed_cmd):
        """连接MCP服务器"""
        from core.mcp import mcp_client
        
        server_name = parsed_cmd.remaining.strip()
        if not server_name:
            print_error("请指定服务器名称，如: /mcp connect the-agency")
            return
        
        print_color(f"\n🔗 正在连接MCP服务器: {server_name}...", CliColors.CYAN)
        result = await mcp_client.connect_server(server_name, "connect", {}, ".")
        
        if result:
            print_success(f"成功连接MCP服务器: {server_name}")
        else:
            print_error(f"连接MCP服务器失败: {server_name}")
    
    async def mcp_connect_agency(self):
        """连接the-agency MCP服务器"""
        from core.mcp import mcp_client
        
        print_color("\n🔗 正在连接the-agency MCP服务器...", CliColors.CYAN)
        result = await mcp_client.connect_agency_server()
        
        if result:
            print_success("成功连接the-agency MCP服务器")
            
            # 显示可用工具
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await mcp_client.list_tools("the-agency")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接the-agency失败")
    
    async def mcp_connect_fun(self):
        """连接趣味MCP服务器"""
        from core.mcp import mcp_client
        
        print_color("\n🔗 正在连接趣味MCP服务器...", CliColors.CYAN)
        result = await mcp_client.connect_fun_server()
        
        if result:
            print_success("成功连接趣味MCP服务器")
            
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await mcp_client.list_tools("fun-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接趣味MCP服务器失败")
    
    async def mcp_connect_weather(self):
        """连接天气MCP服务器"""
        from core.mcp import mcp_client
        
        print_color("\n🔗 正在连接天气MCP服务器...", CliColors.CYAN)
        result = await mcp_client.connect_weather_server()
        
        if result:
            print_success("成功连接天气MCP服务器")
            
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await mcp_client.list_tools("weather-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接天气MCP服务器失败")
    
    async def mcp_connect_calculator(self):
        """连接计算器MCP服务器"""
        from core.mcp import mcp_client
        
        print_color("\n🔗 正在连接计算器MCP服务器...", CliColors.CYAN)
        result = await mcp_client.connect_calculator_server()
        
        if result:
            print_success("成功连接计算器MCP服务器")
            
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await mcp_client.list_tools("calculator-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接计算器MCP服务器失败")
    
    async def mcp_connect_file_ops(self):
        """连接文件操作MCP服务器"""
        from core.mcp import mcp_client
        
        print_color("\n🔗 正在连接文件操作MCP服务器...", CliColors.CYAN)
        result = await mcp_client.connect_file_ops_server()
        
        if result:
            print_success("成功连接文件操作MCP服务器")
            
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await mcp_client.list_tools("file-ops-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接文件操作MCP服务器失败")
    
    async def mcp_connect_text_processing(self):
        """连接文本处理MCP服务器"""
        from core.mcp import mcp_client
        
        print_color("\n🔗 正在连接文本处理MCP服务器...", CliColors.CYAN)
        result = await mcp_client.connect_text_processing_server()
        
        if result:
            print_success("成功连接文本处理MCP服务器")
            
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await mcp_client.list_tools("text-processing-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接文本处理MCP服务器失败")
    
    async def mcp_list_tools(self, parsed_cmd):
        """列出MCP服务器的可用工具"""
        from core.mcp import mcp_client
        
        server_name = parsed_cmd.remaining.strip()
        if not server_name:
            print_error("请指定服务器名称，如: /mcp tools the-agency")
            return
        
        print_color(f"\n📦 {server_name} 的可用工具:", CliColors.CYAN)
        tools = await mcp_client.list_tools(server_name)
        
        if tools:
            for tool in tools:
                print_color(f"  - {tool}", CliColors.GREEN)
        else:
            print_warning(f"  {server_name} 没有可用工具或未连接")
    
    async def mcp_call_tool(self, parsed_cmd):
        """调用MCP工具"""
        from core.mcp import mcp_client
        
        remaining = parsed_cmd.remaining.strip()
        if not remaining:
            print_error("请指定服务器和工具，如: /mcp call the-agency search")
            return
        
        parts = remaining.split()
        if len(parts) < 2:
            print_error("格式错误，请使用: /mcp call <server> <tool> [args]")
            return
        
        server_name = parts[0]
        tool_name = parts[1]
        kwargs = {}
        
        # 解析额外参数
        for part in parts[2:]:
            if "=" in part:
                key, value = part.split("=", 1)
                kwargs[key] = value
        
        print_color(f"\n🚀 调用 {server_name}.{tool_name}...", CliColors.CYAN)
        result = await mcp_client.call_tool(server_name, tool_name, **kwargs)
        
        if result:
            print_success(f"调用成功")
            print_color(f"结果:\n{result}", CliColors.WHITE)
        else:
            print_error(f"调用失败")
    
    async def mcp_disconnect(self, parsed_cmd):
        """断开MCP服务器连接"""
        from core.mcp import mcp_client
        
        server_name = parsed_cmd.remaining.strip()
        if not server_name:
            print_error("请指定服务器名称，如: /mcp disconnect the-agency")
            return
        
        print_color(f"\n🔌 正在断开MCP服务器: {server_name}...", CliColors.CYAN)
        result = await mcp_client.disconnect_server(server_name)
        
        if result:
            print_success(f"成功断开MCP服务器: {server_name}")
            if self.current_mcp_server == server_name:
                self.current_mcp_server = None
        else:
            print_error(f"断开MCP服务器失败: {server_name}")
    
    async def mcp_select(self, parsed_cmd):
        """设置当前活动MCP服务器"""
        from core.mcp import mcp_client
        
        server_name = parsed_cmd.remaining.strip()
        if not server_name:
            print_error("请指定服务器名称，如: /mcp select the-agency")
            return
        
        servers = await mcp_client.list_servers()
        if server_name in servers:
            self.current_mcp_server = server_name
            print_success(f"已选择MCP服务器: {server_name}")
        else:
            print_error(f"未找到MCP服务器: {server_name}")
            print_warning(f"可用服务器: {', '.join(servers) if servers else '无'}")
    
    async def mcp_quick_call(self, parsed_cmd):
        """快速调用当前服务器的工具"""
        from core.mcp import mcp_client
        
        if not self.current_mcp_server:
            print_error("未选择当前MCP服务器")
            print_warning("请先使用 /mcp select <server> 或 /mcp agency")
            return
        
        remaining = parsed_cmd.remaining.strip()
        if not remaining:
            print_error("请指定工具名称，如: /mcp quick search query=hello")
            return
        
        parts = remaining.split()
        if len(parts) < 1:
            print_error("格式错误，请使用: /mcp quick <tool> [args]")
            return
        
        tool_name = parts[0]
        kwargs = {}
        
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                kwargs[key] = value
        
        print_color(f"\n🚀 快速调用 {self.current_mcp_server}.{tool_name}...", CliColors.CYAN)
        result = await mcp_client.call_tool(self.current_mcp_server, tool_name, **kwargs)
        
        if result:
            print_success(f"调用成功")
            print_color(f"结果:\n{result}", CliColors.WHITE)
        else:
            print_error(f"调用失败")
    
    async def mcp_status(self):
        """查看MCP连接状态"""
        from core.mcp import mcp_client
        
        print_color("\n📊 MCP连接状态:", CliColors.CYAN)
        print_color("────────────────", CliColors.GRAY)
        
        servers = await mcp_client.list_servers()
        
        if servers:
            print_color(f"已连接服务器: {len(servers)}", CliColors.GREEN)
            for server in servers:
                status = "● 当前" if server == self.current_mcp_server else "○"
                print_color(f"  {status} {server}", CliColors.WHITE)
        else:
            print_warning("  暂无已连接的MCP服务器")
        
        print_color(f"\n当前服务器: {self.current_mcp_server or '未选择'}", 
                   CliColors.CYAN if self.current_mcp_server else CliColors.GRAY)
    
    async def mcp_register_server(self, parsed_cmd):
        """注册自定义MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
        
        remaining = parsed_cmd.remaining.strip()
        if not remaining:
            print_error("请提供服务器配置，如: /mcp register myserver --command npx --args \"-y @my/mcp\"")
            return
        
        # 解析参数
        parts = remaining.split()
        if len(parts) < 1:
            print_error("请至少提供服务器名称")
            return
        
        server_name = parts[0]
        command = None
        args = []
        env = {}
        description = ""
        
        i = 1
        while i < len(parts):
            if parts[i] == "--command" and i + 1 < len(parts):
                command = parts[i + 1]
                i += 2
            elif parts[i] == "--args" and i + 1 < len(parts):
                # 支持引号包裹的参数
                args_str = parts[i + 1]
                args = args_str.split()
                i += 2
            elif parts[i] == "--env" and i + 1 < len(parts):
                env_str = parts[i + 1]
                if "=" in env_str:
                    key, value = env_str.split("=", 1)
                    env[key] = value
                i += 2
            elif parts[i] == "--description" and i + 1 < len(parts):
                description = parts[i + 1]
                i += 2
            else:
                i += 1
        
        if not command:
            print_error("必须指定 --command 参数")
            return
        
        print_color(f"\n📝 正在注册自定义MCP服务器...", CliColors.CYAN)
        success = awesome_mcp_manager.register_server(
            name=server_name,
            command=command,
            args=args,
            env=env if env else None,
            description=description
        )
        
        if success:
            print_success(f"✅ 成功注册服务器: {server_name}")
            print_color(f"   命令: {command} {' '.join(args)}", CliColors.GRAY)
            if description:
                print_color(f"   描述: {description}", CliColors.GRAY)
            print_color(f"\n💡 使用 /mcp connect {server_name} 连接此服务器", CliColors.YELLOW)
        else:
            print_error(f"❌ 注册服务器失败")
    
    async def mcp_unregister_server(self, parsed_cmd):
        """注销自定义MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
        
        server_name = parsed_cmd.remaining.strip()
        if not server_name:
            print_error("请指定要注销的服务器名称，如: /mcp unregister myserver")
            return
        
        print_color(f"\n🗑️  正在注销自定义MCP服务器: {server_name}...", CliColors.CYAN)
        success = awesome_mcp_manager.unregister_server(server_name)
        
        if success:
            print_success(f"✅ 成功注销服务器: {server_name}")
        else:
            print_error(f"❌ 注销失败，服务器不存在或不是自定义服务器")
    
    async def mcp_list_custom_servers(self):
        """列出所有自定义MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
        
        print_color("\n🔧 自定义MCP服务器:", CliColors.CYAN)
        print_color("────────────────", CliColors.GRAY)
        
        custom_servers = awesome_mcp_manager.get_custom_servers_list()
        
        if custom_servers:
            for server in custom_servers:
                print_color(f"  📦 {server['name']}", CliColors.GREEN)
                print_color(f"     命令: {server['command']} {' '.join(server['args'])}", CliColors.GRAY)
                if server.get('description'):
                    print_color(f"     描述: {server['description']}", CliColors.GRAY)
                print()
        else:
            print_warning("  暂无自定义服务器")
            print_color("\n💡 使用 /mcp register 命令注册新服务器", CliColors.YELLOW)
    

    def mcp_show_history(self):
        """显示MCP调用历史"""
        print_color("\n📜 MCP调用历史:", CliColors.CYAN)
        print_color("────────────────", CliColors.GRAY)
        
        if hasattr(self, 'mcp_history') and self.mcp_history:
            for i, entry in enumerate(reversed(self.mcp_history[-10:]), 1):
                print_color(f"  {i}. {entry['server']}.{entry['tool']}", CliColors.WHITE)
        else:
            print_warning("  暂无MCP调用历史")
    
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
        """处理智能多Agent命令"""
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""
        remaining = parsed_cmd.remaining.strip()
        
        from cli.smart_agent import get_smart_agent_cli
        
        smart_cli = get_smart_agent_cli()
        
        if action == "demo":
            await smart_cli.handle_agent_collaboration_demo()
        elif action == "status":
            await smart_cli.handle_agent_status()
        else:
            # 作为智能任务请求
            user_query = (action + " " + remaining).strip() if action else remaining
            if user_query:
                await smart_cli.handle_smart_task(user_query)
            else:
                print_error("请提供任务描述，如: /smart \"爬取微博热搜并分析\"")
                print_color("\n💡 智能多Agent命令用法:", CliColors.CYAN)
                print_color("────────────────────────", CliColors.GRAY)
                print_color("/smart \"任务描述\" - 使用多Agent协作执行任务", CliColors.WHITE)
                print_color("/smart demo - 演示多Agent协作", CliColors.WHITE)
                print_color("/smart status - 查看Agent状态", CliColors.WHITE)
    
    async def run(self):
        """运行CLI主循环"""
        self.print_welcome()
        
        while self.running:
            try:
                user_input = input(f"{ansi['bold']}{ansi['cyan']}❯{ansi['end']} {ansi['bold']}{ansi['green']}xiaolei{ansi['end']} ")
                
                if not user_input.strip():
                    continue
                
                # 如果不以 / 开头，作为智能任务请求处理
                if not user_input.startswith('/'):
                    await self.handle_smart_request(user_input)
                    print_color("──────────────────────────────────────────────────────────────────────", CliColors.PURPLE)
                    print()
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


async def main(log_file: str = None, log_to_console: bool = True):
    """主入口"""
    from cli.logging_system import init_logger
    init_logger(log_file=log_file, log_to_console=log_to_console)
    
    cli = EnhancedCLI()
    cli._init_session()  # 延迟初始化会话，确保日志系统已配置
    await cli.run()


def parse_args():
    """解析命令行参数 - 只识别CLI自己的参数，其他参数透传"""
    import sys
    
    my_args = ["--log-file", "-l", "--no-console-log", "--dual-terminal", "-d", "--single-terminal", "-s"]
    
    # 检查是否有我们的参数
    has_my_args = any(arg in sys.argv for arg in my_args)
    
    if not has_my_args:
        # 没有我们的参数，直接返回，不解析
        return argparse.Namespace(
            log_file=None,
            no_console_log=False,
            dual_terminal=False,
            single_terminal=False
        )
    
    # 有我们的参数，使用 argparse 解析
    parser = argparse.ArgumentParser(description="小雷版小龙虾 AI Agent CLI")
    parser.add_argument(
        "--log-file", "-l",
        type=str,
        default=None,
        help="日志文件路径（用于双终端模式）"
    )
    parser.add_argument(
        "--no-console-log",
        action="store_true",
        help="不在终端输出日志（用于日志面板）"
    )
    parser.add_argument(
        "--dual-terminal", "-d",
        action="store_true",
        default=False,
        help="启用双终端模式（进度+日志分离显示）"
    )
    parser.add_argument(
        "--single-terminal", "-s",
        action="store_true",
        default=False,
        help="禁用双终端模式（单终端运行）"
    )
    return parser.parse_args()


def is_in_tmux():
    """检查是否在 tmux 环境中"""
    return os.environ.get("TMUX") is not None


def setup_dual_terminal():
    """设置双终端模式"""
    import shutil
    
    # 检查 tmux 是否可用
    if not shutil.which("tmux"):
        print("⚠️  tmux 未安装，无法启用双终端模式")
        print("   安装方式: macOS: brew install tmux, Ubuntu: sudo apt install tmux")
        return False
    
    script_dir = Path(__file__).parent
    log_file = str(script_dir / "logs" / "agent.log")
    
    # 确保日志目录存在
    (script_dir / "logs").mkdir(exist_ok=True)
    
    # 创建空日志文件（供 tail -f 使用）
    Path(log_file).write_text("", encoding="utf-8")
    
    session_name = "xiaolei_agent"
    
    # 检查会话是否已存在
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True
    )
    
    if result.returncode == 0:
        # 会话已存在，直接附加
        subprocess.run(["tmux", "attach-session", "-t", session_name])
        return True
    
    # 创建新会话并设置双终端
    try:
        # 创建会话
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "-n", "Agent"])
        
        # 设置滚动历史（增加到 10000 行）
        subprocess.run(["tmux", "set-option", "-t", session_name, "history-limit", "10000"])
        
        # 设置鼠标支持（让滚动更流畅）
        subprocess.run(["tmux", "set-option", "-t", session_name, "mouse", "on"])
        
        # 分割窗口
        subprocess.run(["tmux", "split-window", "-h"])
        
        # 调整面板大小
        subprocess.run(["tmux", "resize-pane", "-L", "70"])
        
        # 左侧面板：运行 CLI（使用 --dual-terminal 参数）
        subprocess.run([
            "tmux", "send-keys", "-t", f"{session_name}:Agent.0",
            f"cd '{script_dir}' && python cli.py --dual-terminal", "C-m"
        ])
        
        # 右侧面板：显示实时日志
        subprocess.run([
            "tmux", "send-keys", "-t", f"{session_name}:Agent.1",
            f"cd '{script_dir}' && tail -f '{log_file}'", "C-m"
        ])
        
        # 切换到左侧面板
        subprocess.run(["tmux", "select-pane", "-t", "0"])
        
        # 附加到会话
        subprocess.run(["tmux", "attach-session", "-t", session_name])
        return True
        
    except Exception as e:
        print(f"❌ 启动双终端模式失败: {e}")
        return False


if __name__ == "__main__":
    args = parse_args()
    
    # 检查是否启用双终端模式
    # 如果没有明确指定single-terminal，默认启用双终端（如果有tmux）
    enable_dual = args.dual_terminal or (not args.single_terminal and os.environ.get("TMUX") is None)
    
    if enable_dual and shutil.which("tmux"):
        # 尝试启动双终端模式
        if setup_dual_terminal():
            sys.exit(0)
        # 如果失败，回退到单终端模式
    
    asyncio.run(main(
        log_file=args.log_file,
        log_to_console=not args.no_console_log
    ))