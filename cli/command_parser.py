"""命令解析器模块 - Claude Code风格的命令前缀系统

支持的命令前缀:
    /help      - 显示帮助信息
    /run       - 执行工作流
    /analyze   - 数据分析
    /scrape    - 数据爬取
    /automate  - GUI自动化
    /wechat    - 微信消息
    /chat      - 进入聊天模式
    /status    - 系统状态
    /quit      - 退出
    /exit      - 退出
    /clear     - 清屏
    /history   - 查看历史记录
    /debug     - 调试模式切换
    /think     - 思考模式切换

示例:
    /run "帮我爬取微博热搜"
    /analyze wordcloud --file data.csv
    /automate open_app --app Safari
    /wechat send --friend 张三 --message 你好
    /chat deep
"""

import re
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum


class CommandType(Enum):
    """命令类型枚举"""
    HELP = "help"
    RUN = "run"
    ANALYZE = "analyze"
    SCRAPE = "scrape"
    AUTOMATE = "automate"
    WECHAT = "wechat"
    CHAT = "chat"
    STATUS = "status"
    QUIT = "quit"
    EXIT = "exit"
    CLEAR = "clear"
    HISTORY = "history"
    DEBUG = "debug"
    THINK = "think"
    MCP = "mcp"
    GAME = "game"
    FUN = "fun"
    ART = "art"
    AGENT = "agent"
    REVIEW = "review"
    CONFIG = "config"
    PLUGIN = "plugin"
    SMART = "smart"
    RESET = "reset"
    TEST = "test"
    TOOLS = "tools"
    SHOW = "show"
    ORCHESTRATE = "orchestrate"
    UNKNOWN = "unknown"


class ParsedCommand:
    """解析后的命令对象"""
    
    def __init__(self):
        self.command_type: CommandType = CommandType.UNKNOWN
        self.action: str = ""
        self.params: Dict[str, Any] = {}
        self.remaining: str = ""
        self.is_command: bool = False
    
    def __repr__(self):
        return f"<ParsedCommand type={self.command_type.value} action={self.action} params={self.params}>"


class CommandParser:
    """命令解析器 - 支持Claude Code风格的/xx+命令前缀"""
    
    # 命令映射表
    COMMAND_MAP = {
        "/help": CommandType.HELP,
        "/run": CommandType.RUN,
        "/analyze": CommandType.ANALYZE,
        "/scrape": CommandType.SCRAPE,
        "/automate": CommandType.AUTOMATE,
        "/wechat": CommandType.WECHAT,
        "/chat": CommandType.CHAT,
        "/status": CommandType.STATUS,
        "/quit": CommandType.QUIT,
        "/exit": CommandType.EXIT,
        "/clear": CommandType.CLEAR,
        "/history": CommandType.HISTORY,
        "/debug": CommandType.DEBUG,
        "/think": CommandType.THINK,
        "/mcp": CommandType.MCP,
        "/game": CommandType.GAME,
        "/fun": CommandType.FUN,
        "/art": CommandType.ART,
        "/agent": CommandType.AGENT,
        "/review": CommandType.REVIEW,
        "/test": CommandType.TEST,
        "/config": CommandType.CONFIG,
        "/plugin": CommandType.PLUGIN,
        "/smart": CommandType.SMART,
        "/reset": CommandType.RESET,
        "/tools": CommandType.TOOLS,
        "/show": CommandType.SHOW,
        "/orchestrate": CommandType.ORCHESTRATE,
    }
    
    # 命令帮助信息
    COMMAND_HELP = {
        "/help": "显示帮助信息",
        "/run": "执行智能工作流，如: /run \"帮我爬取微博热搜\"",
        "/analyze": "数据分析，如: /analyze wordcloud --file data.csv",
        "/scrape": "数据爬取，如: /scrape 微博 --action 热搜top10",
        "/automate": "GUI自动化，如: /automate open_app --app Safari",
        "/wechat": "微信消息，如: /wechat send --friend 张三 --message 你好",
        "/chat": "进入聊天模式，如: /chat 或 /chat deep",
        "/status": "查看系统状态",
        "/quit": "退出CLI",
        "/exit": "退出CLI",
        "/clear": "清屏",
        "/history": "查看历史记录",
        "/debug": "切换调试模式",
        "/think": "切换思考模式显示",
        "/mcp": "MCP工具调用，如: /mcp list, /mcp connect, /mcp register, /mcp call <tool>",
        "/game": "小游戏，如: /game guess, /game rps, /game dice",
        "/fun": "趣味工具，如: /fun joke, /fun fact, /fun fortune",
        "/art": "ASCII艺术，如: /art cat, /art dog, /art rocket",
        "/agent": "Agent管理，如: /agent list, /agent call Expert 分析问题",
        "/review": "代码审查，如: /review code main.py, /review security cmd",
        "/config": "配置管理，如: /config show, /config set key value",
        "/plugin": "插件工具，如: /plugin list, /plugin create name",
        "/smart": "智能多Agent协作，如: /smart \"任务\", /smart demo, /smart status, /smart <模式> <任务> (模式: pipeline/master/review/auction/hybrid)",
        "/reset": "重置会话，如: /reset (清空历史) 或 /reset all (清空历史和记忆)",
        "/tools": "查看所有可用工具及其状态（按类型分组）",
        "/show": "展开之前折叠的详细输出，如: /show <id>",
        "/orchestrate": "多Agent编排，如: /orchestrate parallel \"任务1\" \"任务2\"",
    }
    
    def __init__(self):
        self.debug_mode: bool = False
        self.think_mode: bool = True
        self.command_history: List[str] = []
    
    def parse(self, input_text: str) -> ParsedCommand:
        """解析用户输入，提取命令和参数"""
        result = ParsedCommand()
        input_text = input_text.strip()
        
        if not input_text:
            return result
        
        # 检查是否以命令前缀开头
        for prefix, cmd_type in self.COMMAND_MAP.items():
            # 支持两种格式: /chat 和 / chat（斜杠后有空格）
            matched = False
            remaining = ""
            
            if input_text.startswith(prefix):
                result.is_command = True
                result.command_type = cmd_type
                remaining = input_text[len(prefix):].strip()
                matched = True
            elif len(prefix) > 1 and input_text.startswith(prefix[0] + ' ' + prefix[1:]):
                # 支持 / chat 格式（斜杠后有空格）
                alt_prefix = prefix[0] + ' ' + prefix[1:]
                if input_text.startswith(alt_prefix):
                    result.is_command = True
                    result.command_type = cmd_type
                    remaining = input_text[len(alt_prefix):].strip()
                    matched = True
            
            if matched:
                # 解析动作和参数
                action, params, remaining_text = self._parse_action_params(remaining)
                result.action = action
                result.params = params
                result.remaining = remaining_text
                
                # 记录历史
                if len(self.command_history) > 50:
                    self.command_history.pop(0)
                self.command_history.append(input_text)
                
                if self.debug_mode:
                    print(f"[DEBUG] 解析结果: {result}")
                
                return result
        
        # 不是命令，返回原始文本
        result.remaining = input_text
        return result
    
    def _parse_action_params(self, text: str) -> Tuple[str, Dict[str, Any], str]:
        """解析动作和参数"""
        action = ""
        params = {}
        remaining = text
        
        if not text:
            return action, params, remaining
        
        # 使用正则提取引号内的内容
        quoted_pattern = r'"([^"]*)"'
        single_quoted_pattern = r"'([^']*)'"
        
        # 先找到第一个空格或引号的位置
        first_space = text.find(' ')
        first_quote = text.find('"')
        first_single_quote = text.find("'")
        
        # 确定动作结束位置
        action_end = len(text)
        if first_space > 0:
            action_end = min(action_end, first_space)
        if first_quote > 0:
            action_end = min(action_end, first_quote)
        if first_single_quote > 0:
            action_end = min(action_end, first_single_quote)
        
        action = text[:action_end].strip()
        
        # 解析剩余部分的参数
        remaining = text[action_end:].strip()
        
        # 提取 --key value 形式的参数
        param_pattern = r'--(\w+)\s+("[^"]*"|\'[^\']*\'|\S+)'
        matches = re.findall(param_pattern, remaining)
        
        for key, value in matches:
            # 移除引号
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            params[key] = value
        
        return action, params, remaining
    
    def get_help_text(self) -> str:
        """获取帮助文本"""
        help_lines = ["\n可用命令:", "─" * 40]
        
        for cmd, help_text in self.COMMAND_HELP.items():
            help_lines.append(f"  {cmd:<12} {help_text}")
        
        help_lines.append("─" * 40)
        help_lines.append("\n如果不以 / 开头，将作为智能任务请求处理")
        
        return "\n".join(help_lines)
    
    def toggle_debug(self) -> bool:
        """切换调试模式"""
        self.debug_mode = not self.debug_mode
        return self.debug_mode
    
    def toggle_think(self) -> bool:
        """切换思考模式"""
        self.think_mode = not self.think_mode
        return self.think_mode
    
    def get_history(self, limit: int = 10) -> List[str]:
        """获取历史记录"""
        return self.command_history[-limit:]
    
    def clear_history(self) -> None:
        """清空历史记录"""
        self.command_history = []


# 全局解析器实例
_global_parser = CommandParser()


def get_command_parser() -> CommandParser:
    """获取全局命令解析器实例"""
    return _global_parser


def parse_command(input_text: str) -> ParsedCommand:
    """便捷函数：解析命令"""
    return _global_parser.parse(input_text)