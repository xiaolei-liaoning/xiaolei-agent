"""命令自动补全模块"""

import readline
from typing import List, Dict, Callable
from cli.colors import CliColors


class AutoCompleter:
    """命令自动补全器"""
    
    def __init__(self):
        self.commands = []
        self.aliases = {}
        self._setup_readline()
    
    def _setup_readline(self):
        """配置readline"""
        readline.set_completer(self._completer)
        readline.parse_and_bind('tab: complete')
        readline.set_completer_delims(' \t\n;')
        
        try:
            readline.read_history_file('.history')
        except FileNotFoundError:
            pass
    
    def add_command(self, command: str, description: str = ""):
        """添加命令"""
        if command not in self.commands:
            self.commands.append(command)
    
    def add_commands(self, commands: List[str]):
        """批量添加命令"""
        for cmd in commands:
            self.add_command(cmd)
    
    def set_aliases(self, aliases: Dict[str, str]):
        """设置命令别名"""
        self.aliases.update(aliases)
    
    def _completer(self, text: str, state: int) -> str:
        """补全函数"""
        matches = [cmd for cmd in self.commands if cmd.startswith(text)]
        
        if state < len(matches):
            return matches[state]
        return None
    
    def get_input(self, prompt: str = "> ") -> str:
        """获取用户输入（带补全）"""
        try:
            return input(f"{CliColors.GREEN}{prompt}{CliColors.ENDC}").strip()
        except EOFError:
            return ""
    
    def save_history(self):
        """保存命令历史"""
        try:
            readline.write_history_file('.history')
        except Exception:
            pass
    
    def show_commands(self):
        """显示所有可用命令"""
        print(f"\n{CliColors.BOLD + CliColors.CYAN}可用命令:{CliColors.ENDC}")
        for cmd in sorted(self.commands):
            print(f"  {cmd}")
        print()


class CommandRegistry:
    """命令注册表"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._commands = {}
            cls._completer = AutoCompleter()
        return cls._instance
    
    def register(self, command: str, handler: Callable, description: str = ""):
        """注册命令"""
        self._commands[command] = {
            'handler': handler,
            'description': description
        }
        self._completer.add_command(command)
    
    def execute(self, command: str, *args) -> bool:
        """执行命令"""
        if command in self._commands:
            try:
                self._commands[command]['handler'](*args)
                return True
            except Exception as e:
                print(f"{CliColors.RED}命令执行错误: {e}{CliColors.ENDC}")
        return False
    
    def get_completer(self) -> AutoCompleter:
        """获取补全器"""
        return self._completer
    
    def get_command_list(self) -> List[str]:
        """获取命令列表"""
        return list(self._commands.keys())
    
    def get_command_info(self, command: str) -> Dict:
        """获取命令信息"""
        return self._commands.get(command, {})


def get_command_registry() -> CommandRegistry:
    """获取命令注册表"""
    return CommandRegistry()


def get_completer() -> AutoCompleter:
    """获取自动补全器"""
    return get_command_registry().get_completer()