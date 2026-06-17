"""MCP (Model Context Protocol) handler — all /mcp sub-commands."""

import logging
from typing import Any, Dict, List, Optional

from cli.colors import CliColors, print_color, print_error, print_success, print_warning
from cli.command_parser import ParsedCommand
from cli.logging_system import log_error, log_warning


class McpHandler:
    """Handles all /mcp sub-commands."""

    def __init__(self, cli):
        self.cli = cli

    async def handle_mcp(self, parsed_cmd: ParsedCommand):
        """处理MCP命令 — 分派到各个子命令"""
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""

        if not action:
            self.show_mcp_help()
            return

        try:
            dispatcher = {
                "list": self.mcp_list_servers,
                "connect": self.mcp_connect,
                "disconnect": self.mcp_disconnect,
                "select": self.mcp_select,
                "tools": self.mcp_list_tools,
                "call": self.mcp_call_tool,
                "quick": self.mcp_quick_call,
                "agency": self.mcp_connect_agency,
                "fun": self.mcp_connect_fun,
                "weather": self.mcp_connect_weather,
                "calculator": self.mcp_connect_calculator,
                "file-ops": self.mcp_connect_file_ops,
                "text-processing": self.mcp_connect_text_processing,
                "status": self.mcp_status,
                "history": self.mcp_show_history,
                "register": self.mcp_register_server,
                "unregister": self.mcp_unregister_server,
                "custom": self.mcp_list_custom_servers,
            }
            handler = dispatcher.get(action)
            if handler:
                await handler(parsed_cmd)
            else:
                print_error(f"未知MCP命令: {action}")
                self.show_mcp_help()
        except Exception as e:
            log_error(f"MCP操作失败: {e}")

    def show_mcp_help(self):
        """显示MCP命令帮助"""
        current = self.cli.current_mcp_server or "未选择"
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

当前服务器: {current}

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

    async def mcp_list_servers(self, parsed_cmd: ParsedCommand = None):
        """列出已连接的MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n📡 已连接的MCP服务器:", CliColors.CYAN)
        servers = awesome_mcp_manager.get_connected_servers()

        if servers:
            for server in servers:
                print_color(f"  ✅ {server}", CliColors.GREEN)
        else:
            print_warning("  暂无已连接的MCP服务器")
            print_color("  提示: 使用 /mcp agency 连接默认服务器", CliColors.GRAY)

    async def mcp_connect(self, parsed_cmd: ParsedCommand):
        """连接MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        server_name = parsed_cmd.remaining.strip()
        if not server_name:
            print_error("请指定服务器名称，如: /mcp connect the-agency")
            return

        print_color(f"\n🔗 正在连接MCP服务器: {server_name}...", CliColors.CYAN)
        result = await awesome_mcp_manager.smart_connect(server_name)

        if result and result.get("success"):
            print_success(f"成功连接MCP服务器: {server_name}")
        else:
            print_error(f"连接MCP服务器失败: {server_name}")

    async def mcp_connect_agency(self, parsed_cmd: ParsedCommand = None):
        """连接the-agency MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n🔗 正在连接the-agency MCP服务器...", CliColors.CYAN)
        result = await awesome_mcp_manager.smart_connect("the-agency")

        if result and result.get("success"):
            print_success("成功连接the-agency MCP服务器")
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await awesome_mcp_manager.get_server_tools("the-agency")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接the-agency失败")

    async def mcp_connect_fun(self, parsed_cmd: ParsedCommand = None):
        """连接趣味MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n🔗 正在连接趣味MCP服务器...", CliColors.CYAN)
        result = await awesome_mcp_manager.smart_connect("fun-mcp")

        if result and result.get("success"):
            print_success("成功连接趣味MCP服务器")
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await awesome_mcp_manager.get_server_tools("fun-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接趣味MCP服务器失败")

    async def mcp_connect_weather(self, parsed_cmd: ParsedCommand = None):
        """连接天气MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n🔗 正在连接天气MCP服务器...", CliColors.CYAN)
        result = await awesome_mcp_manager.smart_connect("weather-mcp")

        if result and result.get("success"):
            print_success("成功连接天气MCP服务器")
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await awesome_mcp_manager.get_server_tools("weather-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接天气MCP服务器失败")

    async def mcp_connect_calculator(self, parsed_cmd: ParsedCommand = None):
        """连接计算器MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n🔗 正在连接计算器MCP服务器...", CliColors.CYAN)
        result = await awesome_mcp_manager.smart_connect("calculator-mcp")

        if result and result.get("success"):
            print_success("成功连接计算器MCP服务器")
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await awesome_mcp_manager.get_server_tools("calculator-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接计算器MCP服务器失败")

    async def mcp_connect_file_ops(self, parsed_cmd: ParsedCommand = None):
        """连接文件操作MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n🔗 正在连接文件操作MCP服务器...", CliColors.CYAN)
        result = await awesome_mcp_manager.smart_connect("file-ops-mcp")

        if result and result.get("success"):
            print_success("成功连接文件操作MCP服务器")
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await awesome_mcp_manager.get_server_tools("file-ops-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接文件操作MCP服务器失败")

    async def mcp_connect_text_processing(self, parsed_cmd: ParsedCommand = None):
        """连接文本处理MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n🔗 正在连接文本处理MCP服务器...", CliColors.CYAN)
        result = await awesome_mcp_manager.smart_connect("text-processing-mcp")

        if result and result.get("success"):
            print_success("成功连接文本处理MCP服务器")
            print_color("\n📦 可用工具:", CliColors.CYAN)
            tools = await awesome_mcp_manager.get_server_tools("text-processing-mcp")
            if tools:
                for tool in tools:
                    print_color(f"  - {tool}", CliColors.GREEN)
            else:
                print_warning("  暂无可用工具")
        else:
            print_error("连接文本处理MCP服务器失败")

    async def mcp_list_tools(self, parsed_cmd: ParsedCommand):
        """列出MCP服务器的可用工具"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        server_name = parsed_cmd.remaining.strip()
        if not server_name:
            print_error("请指定服务器名称，如: /mcp tools the-agency")
            return

        print_color(f"\n📦 {server_name} 的可用工具:", CliColors.CYAN)
        tools = await awesome_mcp_manager.get_server_tools(server_name)

        if tools:
            for tool in tools:
                print_color(f"  - {tool}", CliColors.GREEN)
        else:
            print_warning(f"  {server_name} 没有可用工具或未连接")

    async def mcp_call_tool(self, parsed_cmd: ParsedCommand):
        """调用MCP工具"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

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
        for part in parts[2:]:
            if "=" in part:
                key, value = part.split("=", 1)
                kwargs[key] = value

        print_color(f"\n🚀 调用 {server_name}.{tool_name}...", CliColors.CYAN)
        result = await awesome_mcp_manager.call_server_tool(server_name, tool_name, kwargs)

        if result:
            print_success("调用成功")
            print_color(f"结果:\n{result}", CliColors.WHITE)
        else:
            print_error("调用失败")

    async def mcp_disconnect(self, parsed_cmd: ParsedCommand):
        """断开MCP服务器连接"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        server_name = parsed_cmd.remaining.strip()
        if not server_name:
            print_error("请指定服务器名称，如: /mcp disconnect the-agency")
            return

        print_color(f"\n🔌 正在断开MCP服务器: {server_name}...", CliColors.CYAN)
        result = await awesome_mcp_manager.disconnect_server(server_name)

        if result:
            print_success(f"成功断开MCP服务器: {server_name}")
            if self.cli.current_mcp_server == server_name:
                self.cli.current_mcp_server = None
        else:
            print_error(f"断开MCP服务器失败: {server_name}")

    async def mcp_select(self, parsed_cmd: ParsedCommand):
        """设置当前活动MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        server_name = parsed_cmd.remaining.strip()
        if not server_name:
            print_error("请指定服务器名称，如: /mcp select the-agency")
            return

        servers = awesome_mcp_manager.get_connected_servers()
        if server_name in servers:
            self.cli.current_mcp_server = server_name
            print_success(f"已选择MCP服务器: {server_name}")
        else:
            print_error(f"未找到MCP服务器: {server_name}")
            print_warning(f"可用服务器: {', '.join(servers) if servers else '无'}")

    async def mcp_quick_call(self, parsed_cmd: ParsedCommand):
        """快速调用当前服务器的工具"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        if not self.cli.current_mcp_server:
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

        print_color(f"\n🚀 快速调用 {self.cli.current_mcp_server}.{tool_name}...", CliColors.CYAN)
        result = await awesome_mcp_manager.call_server_tool(
            self.cli.current_mcp_server, tool_name, kwargs
        )

        if result:
            print_success("调用成功")
            print_color(f"结果:\n{result}", CliColors.WHITE)
        else:
            print_error("调用失败")

    async def mcp_status(self, parsed_cmd: ParsedCommand = None):
        """查看MCP连接状态"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n📊 MCP连接状态:", CliColors.CYAN)
        print_color("────────────────", CliColors.GRAY)

        servers = awesome_mcp_manager.get_connected_servers()

        if servers:
            print_color(f"已连接服务器: {len(servers)}", CliColors.GREEN)
            for server in servers:
                status = "● 当前" if server == self.cli.current_mcp_server else "○"
                print_color(f"  {status} {server}", CliColors.WHITE)
        else:
            print_warning("  暂无已连接的MCP服务器")

        current = self.cli.current_mcp_server or "未选择"
        color = CliColors.CYAN if self.cli.current_mcp_server else CliColors.GRAY
        print_color(f"\n当前服务器: {current}", color)

    async def mcp_register_server(self, parsed_cmd: ParsedCommand):
        """注册自定义MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        remaining = parsed_cmd.remaining.strip()
        if not remaining:
            print_error('请提供服务器配置，如: /mcp register myserver --command npx --args "-y @my/mcp"')
            return

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

        print_color("\n📝 正在注册自定义MCP服务器...", CliColors.CYAN)
        success = awesome_mcp_manager.register_server(
            name=server_name,
            command=command,
            args=args,
            env=env if env else None,
            description=description,
        )

        if success:
            print_success(f"✅ 成功注册服务器: {server_name}")
            print_color(f"   命令: {command} {' '.join(args)}", CliColors.GRAY)
            if description:
                print_color(f"   描述: {description}", CliColors.GRAY)
            print_color(f"\n💡 使用 /mcp connect {server_name} 连接此服务器", CliColors.YELLOW)
        else:
            print_error("❌ 注册服务器失败")

    async def mcp_unregister_server(self, parsed_cmd: ParsedCommand):
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
            print_error("❌ 注销失败，服务器不存在或不是自定义服务器")

    async def mcp_list_custom_servers(self, parsed_cmd: ParsedCommand = None):
        """列出所有自定义MCP服务器"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n🔧 自定义MCP服务器:", CliColors.CYAN)
        print_color("────────────────", CliColors.GRAY)

        custom_servers = awesome_mcp_manager.get_custom_servers_list()

        if custom_servers:
            for server in custom_servers:
                print_color(f"  📦 {server['name']}", CliColors.GREEN)
                print_color(
                    f"     命令: {server['command']} {' '.join(server['args'])}",
                    CliColors.GRAY,
                )
                if server.get("description"):
                    print_color(f"     描述: {server['description']}", CliColors.GRAY)
                print()
        else:
            print_warning("  暂无自定义服务器")
            print_color("\n💡 使用 /mcp register 命令注册新服务器", CliColors.YELLOW)

    def mcp_show_history(self, parsed_cmd: ParsedCommand = None):
        """显示MCP调用历史"""
        print_color("\n📜 MCP调用历史:", CliColors.CYAN)
        print_color("────────────────", CliColors.GRAY)

        if hasattr(self.cli, "mcp_history") and self.cli.mcp_history:
            for i, entry in enumerate(reversed(self.cli.mcp_history[-10:]), 1):
                print_color(f"  {i}. {entry['server']}.{entry['tool']}", CliColors.WHITE)
        else:
            print_warning("  暂无MCP调用历史")
