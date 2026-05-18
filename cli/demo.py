"""CLI功能演示模块 - 展示所有新功能

演示以下功能:
1. 终端UI组件（进度条、表格、卡片、动画等）
2. 工具框架（build_tool模式）
3. Shell执行引擎
4. 交互增强（自动补全、历史记录）
5. 权限系统
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.colors import CliColors, print_color
from cli.ui_components import (
    ProgressBar, Table, Card, Spinner, Tree, StatusBar, Menu, Dialog,
    Panel, KeyValueDisplay, AnimatedText, show_progress, show_table, show_card
)

# 直接导入新模块
try:
    from core.tool_framework import build_tool, register_tool, get_tool_registry, ToolResult, ToolPermission
except ImportError:
    build_tool = register_tool = get_tool_registry = ToolResult = ToolPermission = None
from core.tools.shell_executor import run_shell_command, build_shell_command

# 直接导入权限系统模块
import importlib.util
permission_system_path = Path(__file__).parent.parent / "core" / "permission_system.py"
PermissionManager = None

if permission_system_path.exists():
    try:
        spec = importlib.util.spec_from_file_location("permission_system", permission_system_path)
        permission_system = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(permission_system)
        PermissionManager = permission_system.PermissionManager
    except Exception as e:
        print(f"Warning: Failed to load permission_system: {e}")
else:
    print(f"Warning: permission_system.py not found at {permission_system_path}")


class DemoRunner:
    """演示运行器"""
    
    def __init__(self):
        self._running = True
    
    async def run(self):
        """运行演示"""
        while self._running:
            choice = self._show_main_menu()
            if choice == 'exit':
                self._running = False
            elif choice == 'ui':
                await self._demo_ui_components()
            elif choice == 'tool':
                await self._demo_tool_framework()
            elif choice == 'shell':
                await self._demo_shell_executor()
            elif choice == 'permission':
                await self._demo_permission_system()
    
    def _show_main_menu(self) -> str:
        """显示主菜单"""
        print()
        print_color("╔════════════════════════════════════════════════════════════════╗", CliColors.CYAN + CliColors.BOLD)
        print_color("║                     🦐 小龙虾Agent 功能演示                    ║", CliColors.CYAN + CliColors.BOLD)
        print_color("╠════════════════════════════════════════════════════════════════╣", CliColors.CYAN)
        print_color("║  [1] UI组件演示     - 进度条、表格、卡片、动画等              ║", CliColors.WHITE)
        print_color("║  [2] 工具框架演示   - build_tool模式、工具注册和调用          ║", CliColors.WHITE)
        print_color("║  [3] Shell执行演示  - 命令执行、后台任务、输出监控            ║", CliColors.WHITE)
        print_color("║  [4] 权限系统演示   - 多层权限检查、Auto Mode分类             ║", CliColors.WHITE)
        print_color("║  [5] 退出                                                   ║", CliColors.WHITE)
        print_color("╚════════════════════════════════════════════════════════════════╝", CliColors.CYAN + CliColors.BOLD)
        
        while True:
            choice = input(f"\n{CliColors.GREEN}请选择演示项目 (1-5): {CliColors.ENDC}").strip()
            options = {'1': 'ui', '2': 'tool', '3': 'shell', '4': 'permission', '5': 'exit', 'ui': 'ui', 'tool': 'tool', 'shell': 'shell', 'permission': 'permission', 'exit': 'exit'}
            if choice.lower() in options:
                return options[choice.lower()]
            print_color("无效选择，请输入 1-5", CliColors.RED)
    
    async def _demo_ui_components(self):
        """演示UI组件"""
        print()
        print_color("─────────────────────────────────────────────────────────────", CliColors.GRAY)
        print_color("🎨 UI组件演示", CliColors.BOLD + CliColors.CYAN)
        print_color("─────────────────────────────────────────────────────────────", CliColors.GRAY)
        
        # 演示进度条
        print("\n1. 进度条演示:")
        pb = ProgressBar(total=100, width=40)
        for i in range(0, 101, 10):
            pb.update(i)
            await asyncio.sleep(0.1)
        pb.complete()
        
        # 演示表格
        print("\n2. 表格演示:")
        headers = ["工具名称", "类别", "版本", "权限"]
        data = [
            ["file_read", "文件操作", "1.0.0", "READ"],
            ["weather", "API", "1.0.0", "NONE"],
            ["shell_exec", "系统", "1.0.0", "EXECUTE"],
            ["file_write", "文件操作", "1.0.0", "WRITE"],
        ]
        show_table(headers, data)
        
        # 演示卡片
        print("\n3. 卡片演示:")
        show_card("📋 系统状态", "CPU: 25%\n内存: 4GB\n磁盘: 128GB\n网络: 在线")
        
        # 演示树形结构
        print("\n4. 树形结构演示:")
        tree_data = {
            "name": "项目结构",
            "children": [
                {"name": "cli/", "children": [
                    {"name": "ui_components.py"},
                    {"name": "colors.py"},
                    {"name": "interactive.py"}
                ]},
                {"name": "core/", "children": [
                    {"name": "tool_framework.py"},
                    {"name": "shell_executor.py"},
                    {"name": "permission_system.py"}
                ]},
                {"name": "skills/"}
            ]
        }
        from cli.ui_components import show_tree
        show_tree(tree_data)
        
        # 演示键值对显示
        print("\n5. 键值对显示演示:")
        kv = KeyValueDisplay({
            "版本": "2.0.0",
            "模式": "开发模式",
            "会话ID": "abc123",
            "连接数": 5
        })
        kv.render("系统信息")
        
        # 演示状态栏
        print("\n6. 状态栏演示:")
        status_bar = StatusBar()
        status_bar.add_item("🦐 小龙虾Agent", CliColors.CYAN)
        status_bar.add_item("v2.0.0", CliColors.GREEN)
        status_bar.add_item("在线", CliColors.GREEN)
        status_bar.render()
        
        # 演示打字机效果
        print("\n7. 打字机动画演示:")
        AnimatedText.typewriter("这是一个打字机效果演示...", delay=0.05, color=CliColors.CYAN)
        
        Dialog.info("UI组件演示完成！")
    
    async def _demo_tool_framework(self):
        """演示工具框架"""
        print()
        print_color("─────────────────────────────────────────────────────────────", CliColors.GRAY)
        print_color("🔧 工具框架演示", CliColors.BOLD + CliColors.CYAN)
        print_color("─────────────────────────────────────────────────────────────", CliColors.GRAY)

        if build_tool is None:
            print_color("⚠️ 工具框架模块不可用（tool_framework.py 已重构）", CliColors.YELLOW)
            Dialog.info("工具框架演示跳过")
            return

        # 创建示例工具
        greet_tool = (
            build_tool("greet", "向用户打招呼")
            .category("general")
            .tag("hello")
            .param("name", str, "用户姓名", required=True)
            .param("greeting", str, "问候语", required=False, default="你好")
            .output_field("message", str)
            .executes(lambda name, greeting="你好": ToolResult(
                success=True,
                data={"message": f"{greeting} {name}！欢迎使用小龙虾Agent！"},
                message="操作成功"
            ))
            .renders_with(lambda result: f"💬 {result.data.get('message', '')}")
            .build()
        )

        # 注册工具
        register_tool(greet_tool)
        print_color("✅ 工具已注册", CliColors.GREEN)

        # 获取工具
        registry = get_tool_registry()
        tool = registry.get("greet")

        if tool:
            print(f"\n📦 工具信息:")
            info = registry.get_tool_info("greet")
            for key, value in info.items():
                print(f"  {key}: {value}")

            # 执行工具
            print("\n🚀 执行工具:")
            result = await tool.execute(name="用户")
            print(tool.render_result(result))

            # 搜索工具
            print("\n🔍 搜索工具:")
            results = registry.search("greet")
            for t in results:
                print(f"  - {t.metadata.name}: {t.metadata.description}")

        Dialog.info("工具框架演示完成！")
    
    async def _demo_shell_executor(self):
        """演示Shell执行引擎"""
        print()
        print_color("─────────────────────────────────────────────────────────────", CliColors.GRAY)
        print_color("💻 Shell执行引擎演示", CliColors.BOLD + CliColors.CYAN)
        print_color("─────────────────────────────────────────────────────────────", CliColors.GRAY)
        
        # 方式1: 直接执行
        print("\n1. 直接执行命令:")
        result = await run_shell_command("echo 'Hello from Shell!'")
        print(f"   输出: {result.stdout.strip()}")
        print(f"   状态: {result.status}")
        print(f"   耗时: {result.duration:.2f}秒")
        
        # 方式2: 使用构建器
        print("\n2. 使用命令构建器:")
        result = await (
            build_shell_command("ls")
            .arg("-la")
            .in_dir("/tmp")
            .with_timeout(10)
            .execute()
        )
        print(f"   状态: {result.status}")
        print(f"   输出:\n{result.stdout}")
        
        # 方式3: 检查安全命令
        print("\n3. 安全命令检查:")
        from core.tools.shell_executor import is_safe_command
        commands = ["ls -la", "rm -rf /", "echo hello"]
        for cmd in commands:
            safe = is_safe_command(cmd)
            status = "✅ 安全" if safe else "❌ 危险"
            print(f"   '{cmd}' - {status}")
        
        Dialog.info("Shell执行引擎演示完成！")
    
    async def _demo_permission_system(self):
        """演示权限系统"""
        print()
        print_color("─────────────────────────────────────────────────────────────", CliColors.GRAY)
        print_color("🔐 权限系统演示", CliColors.BOLD + CliColors.CYAN)
        print_color("─────────────────────────────────────────────────────────────", CliColors.GRAY)
        
        if PermissionManager is None:
            print_color("❌ 权限系统模块未加载", CliColors.RED)
            print_color("   请检查 core/permission_system.py 文件", CliColors.GRAY)
            Dialog.info("权限系统演示跳过！")
            return
        
        manager = PermissionManager()
        
        # 测试安全操作
        print("\n1. 测试安全操作 (weather):")
        result = await manager.check("weather", {"city": "Beijing"}, is_auto_mode=True)
        print(f"   决策: {result.decision.value}")
        print(f"   原因: {result.reason}")
        if hasattr(result, 'category') and result.category:
            print(f"   分类: {result.category.value}")
        
        # 测试需要确认的操作
        print("\n2. 测试需要确认的操作 (file_write):")
        result = await manager.check("file_write", {"path": "/tmp/test.txt"}, is_auto_mode=True)
        print(f"   决策: {result.decision.value}")
        print(f"   原因: {result.reason}")
        
        # 测试危险操作
        print("\n3. 测试危险操作 (shell_exec with rm -rf):")
        result = await manager.check("shell_exec", {"command": "rm -rf /"}, is_auto_mode=True)
        print(f"   决策: {result.decision.value}")
        print(f"   原因: {result.reason}")
        
        # 测试非Auto模式
        print("\n4. 测试非Auto模式:")
        result = await manager.check("file_write", {"path": "/tmp/test.txt"}, is_auto_mode=False)
        print(f"   决策: {result.decision.value}")
        print(f"   原因: {result.reason}")
        
        # 查看审计日志
        print("\n5. 查看审计日志:")
        system = manager.get_system()
        logs = system.get_audit_logs(limit=3)
        for log in logs:
            print(f"   [{log['timestamp']}] {log['tool_name']} -> {log['decision']}")
        
        Dialog.info("权限系统演示完成！")


async def main():
    """主函数"""
    demo = DemoRunner()
    await demo.run()


if __name__ == "__main__":
    asyncio.run(main())