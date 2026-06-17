"""Task-related handlers — game, fun, art, agent, review, config, plugin commands."""

import logging
from typing import Any, Dict, List, Optional

from cli.colors import CliColors, print_color, print_error, print_success
from cli.command_parser import ParsedCommand
from cli.logging_system import log_error


class TaskHandler:
    """Handles game, fun, art, agent, review, config, plugin, smart commands."""

    def __init__(self, cli):
        self.cli = cli

    # ──────────────────────────────────────────────
    # /game
    # ──────────────────────────────────────────────

    async def handle_game(self, parsed_cmd: ParsedCommand):
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

    # ──────────────────────────────────────────────
    # /fun
    # ──────────────────────────────────────────────

    async def handle_fun(self, parsed_cmd: ParsedCommand):
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

    # ──────────────────────────────────────────────
    # /art
    # ──────────────────────────────────────────────

    async def handle_art(self, parsed_cmd: ParsedCommand):
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

    # ──────────────────────────────────────────────
    # /agent
    # ──────────────────────────────────────────────

    async def handle_agent(self, parsed_cmd: ParsedCommand):
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

    # ──────────────────────────────────────────────
    # /review
    # ──────────────────────────────────────────────

    async def handle_review(self, parsed_cmd: ParsedCommand):
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

    # ──────────────────────────────────────────────
    # /config
    # ──────────────────────────────────────────────

    async def handle_config(self, parsed_cmd: ParsedCommand):
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

    # ──────────────────────────────────────────────
    # /plugin
    # ──────────────────────────────────────────────

    async def handle_plugin(self, parsed_cmd: ParsedCommand):
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
