"""MCP 命令处理器 - 从 EnhancedCLI 拆分"""

import json
import logging
from typing import Dict, Any, Optional

from cli.colors import CliColors, print_color, print_error, print_warning, print_info, print_success

logger = logging.getLogger(__name__)


async def _check_mcp_permission(action: str, server: str, tool: str = "") -> bool:
    """检查 MCP 操作权限"""
    try:
        from core.services.permission_service import get_permission_service, PermissionType
        perm_svc = get_permission_service()
        target = f"mcp:{server}/{tool}" if tool else f"mcp:{server}"
        return await perm_svc.request_permission(
            permission_type=PermissionType.MCP_SERVER_ACCESS,
            target=target,
            reason=f"MCP {action}: {server}",
        )
    except Exception:
        return True


class MCPHandler:
    """MCP 服务器管理命令"""

    def __init__(self, cli):
        self.cli = cli

    def show_mcp_help(self):
        """显示 MCP 命令帮助"""
        from cli.command_parser import get_command_parser
        parser = get_command_parser()
        help_text = parser.get_help("mcp")
        print_color(help_text, CliColors.CYAN)

    async def handle_mcp_command(self, action: str, remaining: str):
        """处理 MCP 相关命令"""
        mcp_handlers = {
            "list": self.mcp_list_servers,
            "connect": self.mcp_connect_server,
            "disconnect": self.mcp_disconnect_server,
            "select": self.mcp_select_server,
            "register": self.mcp_register_server,
            "unregister": self.mcp_unregister_server,
            "help": self.show_mcp_help,
            "history": self.mcp_show_history,
            "status": self.mcp_status,
            "quick": self.mcp_quick_call,
        }
        handler = mcp_handlers.get(action)
        if handler:
            await handler(remaining)
        else:
            print_error(f"未知 MCP 命令: {action}")
            self.show_mcp_help()

    async def mcp_list_servers(self, args: str = ""):
        """列出已连接和可用的 MCP 服务器"""
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager

            connected = awesome_mcp_manager.get_connected_servers()
            available = awesome_mcp_manager.get_available_quick_connect()

            print_color("\n📡 MCP 服务器列表:", CliColors.CYAN)
            print_color("  ─────────────────", CliColors.DARK_GRAY)

            if connected:
                print_color(f"\n  ✅ 已连接 ({len(connected)}):", CliColors.GREEN)
                for s in connected:
                    print_color(f"     • {s}", CliColors.WHITE)
            else:
                print_color("\n  ⚪ 已连接: 无", CliColors.GRAY)

            if available:
                print_color(f"\n  📦 可快速连接 ({len(available)}):", CliColors.CYAN)
                for s in available[:10]:
                    print_color(f"     • {s}", CliColors.WHITE)
                if len(available) > 10:
                    print_color(f"     ...及 {len(available) - 10} 个其他", CliColors.GRAY)
            else:
                print_color("\n  📦 可快速连接: 无", CliColors.GRAY)

            print()
        except Exception as e:
            print_error(f"获取 MCP 服务器列表失败: {e}")

    async def mcp_connect_server(self, server_name: str):
        """连接 MCP 服务器"""
        if not server_name:
            print_warning("请指定服务器名称")
            return

        # 权限检查
        if not await _check_mcp_permission("connect", server_name):
            print_error(f"❌ 连接 {server_name} 被拒绝（权限不足）")
            return

        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            print_color(f"\n  🔗 正在连接 {server_name}...", CliColors.CYAN)
            result = await awesome_mcp_manager.quick_connect(server_name)
            if result and result.get("success"):
                print_success(f"✅ 成功连接到 {server_name}")
                self.cli.current_mcp_server = server_name
            else:
                error = (result or {}).get("error", "未知错误")
                print_error(f"❌ 连接失败: {error}")
        except Exception as e:
            print_error(f"连接异常: {e}")

    async def mcp_disconnect_server(self, server_name: str):
        """断开 MCP 服务器"""
        if not server_name:
            print_warning("请指定服务器名称")
            return
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            result = await awesome_mcp_manager.disconnect(server_name)
            if result:
                print_success(f"已断开 {server_name}")
                if self.cli.current_mcp_server == server_name:
                    self.cli.current_mcp_server = None
            else:
                print_error(f"断开 {server_name} 失败")
        except Exception as e:
            print_error(f"断开异常: {e}")

    async def mcp_select_server(self, server_name: str):
        """设置当前活动 MCP 服务器"""
        if not server_name:
            print_warning("请指定服务器名称")
            return
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            connected = awesome_mcp_manager.get_connected_servers()
            if server_name in connected:
                self.cli.current_mcp_server = server_name
                print_success(f"当前 MCP 服务器已设为: {server_name}")
            else:
                print_warning(f"服务器 {server_name} 未连接，请先连接")
        except Exception as e:
            print_error(f"选择服务器失败: {e}")

    async def mcp_register_server(self, args: str = ""):
        """注册自定义 MCP 服务器"""
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            config_path = awesome_mcp_manager.get_config_path()
            print_color(f"\n  📝 自定义 MCP 服务器配置保存在: {config_path}", CliColors.CYAN)
            print_color("  " + "─" * 40, CliColors.DARK_GRAY)
            print()
            print_color("  格式示例:", CliColors.GRAY)
            print_color("  custom_servers:", CliColors.WHITE)
            print_color('    my_server:', CliColors.WHITE)
            print_color('      command: "python"', CliColors.WHITE)
            print_color('      args: ["-m", "my_mcp_server"]', CliColors.WHITE)
            print()
            print_color("  请编辑 config 文件后重启或使用 /mcp reload", CliColors.GRAY)
        except Exception as e:
            print_error(f"注册服务器失败: {e}")

    async def mcp_unregister_server(self, server_name: str):
        """注销自定义 MCP 服务器"""
        print_warning(f"注销功能尚未实现: {server_name}")

    async def mcp_status(self, args: str = ""):
        """显示 MCP 状态"""
        current = self.cli.current_mcp_server
        if current:
            print_color(f"\n  🔗 当前 MCP 服务器: {current}", CliColors.GREEN)
        else:
            print_color("\n  ⚪ 未选择 MCP 服务器", CliColors.GRAY)
        await self.mcp_list_servers()

    async def mcp_quick_call(self, args: str = ""):
        """快速 MCP 调用"""
        if not self.cli.current_mcp_server:
            print_warning("请先使用 /mcp select 选择服务器")
            return
        if not args:
            print_warning("请输入工具名和参数")
            return

        parts = args.strip().split(maxsplit=1)
        tool_name = parts[0]
        tool_args = parts[1] if len(parts) > 1 else ""

        # 权限检查
        if not await _check_mcp_permission("call", self.cli.current_mcp_server, tool_name):
            print_error(f"❌ 调用 {self.cli.current_mcp_server}.{tool_name} 被拒绝（权限不足）")
            return

        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            print_color(f"\n  🔧 调用 {self.cli.current_mcp_server}.{tool_name}...", CliColors.CYAN)
            result = await awesome_mcp_manager.call_tool(
                self.cli.current_mcp_server, tool_name, {"input": tool_args}
            )
            if result:
                content = result.get("content", [])
                for item in content:
                    if isinstance(item, dict):
                        print_color(f"  {item.get('text', str(item))}", CliColors.WHITE)
                    else:
                        print_color(f"  {str(item)}", CliColors.WHITE)
            else:
                print_error("调用无返回")
        except Exception as e:
            print_error(f"MCP 调用失败: {e}")

    def mcp_show_history(self):
        """显示 MCP 调用历史"""
        print_color("\n  📜 MCP 调用历史", CliColors.DARK_GRAY)
        print_color("  " + "─" * 20, CliColors.DARK_GRAY)
        print_color("  (功能开发中)", CliColors.GRAY)
