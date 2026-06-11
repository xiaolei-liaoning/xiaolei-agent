"""
Shell 命令 AST 分析器 — 基于树结构解析

对标 opencode 的 AST Shell 分析
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """命令类型"""
    SIMPLE = "simple"        # 简单命令：ls, cat, etc.
    PIPE = "pipe"            # 管道：cmd1 | cmd2
    REDIRECT = "redirect"    # 重定向：cmd > file
    SEQUENCE = "sequence"    # 序列：cmd1; cmd2
    AND = "and"              # 逻辑与：cmd1 && cmd2
    OR = "or"                # 逻辑或：cmd1 || cmd2
    SUBSHELL = "subshell"    # 子shell：(cmd)
    GROUP = "group"          # 命令组：{ cmd; }
    BACKTICK = "backtick"    # 反引号：`cmd`
    DOLLAR = "dollarparen"   # $()：$(cmd)


class RiskLevel(Enum):
    """风险级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CommandAST:
    """命令 AST 节点"""
    raw: str                    # 原始命令
    command_type: CommandType   # 命令类型
    parts: List[str] = field(default_factory=list)      # 命令部分
    pipes: List['CommandAST'] = field(default_factory=list)  # 管道命令
    redirects: List[dict] = field(default_factory=list)      # 重定向
    subcommands: List['CommandAST'] = field(default_factory=list)  # 子命令
    risks: List[dict] = field(default_factory=list)         # 风险点
    variables: List[str] = field(default_factory=list)      # 变量引用
    exit_code: Optional[int] = None  # 退出码


@dataclass
class AnalysisRiskItem:
    """风险项（分析器专用）"""
    level: RiskLevel
    type: str
    description: str
    position: Tuple[int, int] = (0, 0)  # 位置 (start, end)
    suggestion: str = ""


class ShellAnalyzer:
    """Shell 命令 AST 分析器"""

    # 危险命令列表
    DANGEROUS_COMMANDS = {
        "rm", "rmdir", "shred", "dd", "mkfs", "fdisk", "mount", "umount",
        "chmod", "chown", "chgrp", "passwd", "useradd", "userdel", "usermod",
        "sudo", "su", "visudo", "iptables", "ip6tables",
        "systemctl", "service", "shutdown", "reboot", "halt", "poweroff",
    }

    # 网络命令
    NETWORK_COMMANDS = {
        "curl", "wget", "nc", "ncat", "netcat", "socat", "ssh", "scp", "rsync",
        "telnet", "ftp", "sftp", "dig", "nslookup", "host", "ping", "traceroute",
    }

    # 进程命令
    PROCESS_COMMANDS = {
        "kill", "killall", "pkill", "killall", "ps", "top", "htop", "pstree",
    }

    def analyze(self, command: str) -> CommandAST:
        """
        分析命令结构

        Args:
            command: shell 命令

        Returns:
            CommandAST: 分析结果
        """
        command = command.strip()
        if not command:
            return CommandAST(raw=command, command_type=CommandType.SIMPLE)

        # 检测命令类型
        cmd_type = self._detect_type(command)

        # 构建 AST
        ast = CommandAST(raw=command, command_type=cmd_type)

        # 解析不同类型的命令
        if cmd_type == CommandType.PIPE:
            ast.pipes = self._parse_pipes(command)
        elif cmd_type == CommandType.REDIRECT:
            ast.redirects = self._parse_redirects(command)
        elif cmd_type == CommandType.SEQUENCE:
            ast.subcommands = self._parse_sequence(command, ";")
        elif cmd_type == CommandType.AND:
            ast.subcommands = self._parse_sequence(command, "&&")
        elif cmd_type == CommandType.OR:
            ast.subcommands = self._parse_sequence(command, "||")
        elif cmd_type == CommandType.SUBSHELL:
            ast.subcommands = self._parse_subshell(command)
        else:
            ast.parts = self._parse_simple(command)

        # 提取变量
        ast.variables = self._extract_variables(command)

        # 检测风险
        ast.risks = self._detect_risks(ast)

        return ast

    def _detect_type(self, command: str) -> CommandType:
        """检测命令类型"""
        # 检查管道
        if "|" in command and "||" not in command:
            return CommandType.PIPE

        # 检查逻辑或
        if "||" in command:
            return CommandType.OR

        # 检查逻辑与
        if "&&" in command:
            return CommandType.AND

        # 检查序列
        if ";" in command:
            return CommandType.SEQUENCE

        # 检查重定向
        if any(op in command for op in [">", ">>", "<", "<<<", "<<<"]):
            return CommandType.REDIRECT

        # 检查子shell
        if command.startswith("(") and command.endswith(")"):
            return CommandType.SUBSHELL

        # 检查命令组
        if command.startswith("{") and command.endswith("}"):
            return CommandType.GROUP

        # 检查反引号
        if command.startswith("`") and command.endswith("`"):
            return CommandType.BACKTICK

        # 检查 $()
        if command.startswith("$(") and command.endswith(")"):
            return CommandType.DOLLAR

        return CommandType.SIMPLE

    def _parse_pipes(self, command: str) -> List[CommandAST]:
        """解析管道"""
        parts = command.split("|")
        pipes = []
        for part in parts:
            part = part.strip()
            if part:
                pipes.append(self.analyze(part))
        return pipes

    def _parse_redirects(self, command: str) -> List[dict]:
        """解析重定向"""
        redirects = []
        # 简单解析
        patterns = [
            (r'(\S+)\s*>\s*(\S+)', 'output'),
            (r'(\S+)\s*>>\s*(\S+)', 'append'),
            (r'(\S+)\s*<\s*(\S+)', 'input'),
        ]
        for pattern, rtype in patterns:
            matches = re.findall(pattern, command)
            for match in matches:
                redirects.append({
                    'type': rtype,
                    'source': match[0],
                    'target': match[1],
                })
        return redirects

    def _parse_sequence(self, command: str, delimiter: str) -> List[CommandAST]:
        """解析序列"""
        parts = command.split(delimiter)
        return [self.analyze(part.strip()) for part in parts if part.strip()]

    def _parse_subshell(self, command: str) -> List[CommandAST]:
        """解析子shell"""
        inner = command[1:-1].strip()
        if inner:
            return [self.analyze(inner)]
        return []

    def _parse_simple(self, command: str) -> List[str]:
        """解析简单命令"""
        # 简单的分词
        parts = []
        current = ""
        in_quotes = False
        quote_char = None

        for char in command:
            if char in ['"', "'"] and not in_quotes:
                in_quotes = True
                quote_char = char
                current += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current += char
            elif char == ' ' and not in_quotes:
                if current:
                    parts.append(current)
                current = ""
            else:
                current += char

        if current:
            parts.append(current)

        return parts

    def _extract_variables(self, command: str) -> List[str]:
        """提取变量引用"""
        variables = []
        # $VAR 格式
        variables.extend(re.findall(r'\$([A-Za-z_][A-Za-z0-9_]*)', command))
        # ${VAR} 格式
        variables.extend(re.findall(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', command))
        # $() 格式（子命令）
        variables.extend(re.findall(r'\$\(([^)]+)\)', command))
        return list(set(variables))

    def _detect_risks(self, ast: CommandAST) -> List[dict]:
        """检测风险"""
        risks = []
        command = ast.raw

        # 检查危险命令
        parts = ast.parts if ast.parts else [command]
        for part in parts:
            cmd_name = part.split()[0] if part.split() else ""
            if cmd_name in self.DANGEROUS_COMMANDS:
                risks.append({
                    'level': RiskLevel.MEDIUM,
                    'type': 'dangerous_command',
                    'description': f'使用危险命令: {cmd_name}',
                })

        # 检查网络命令
        for part in parts:
            cmd_name = part.split()[0] if part.split() else ""
            if cmd_name in self.NETWORK_COMMANDS:
                risks.append({
                    'level': RiskLevel.LOW,
                    'type': 'network_command',
                    'description': f'使用网络命令: {cmd_name}',
                })

        # 检查进程命令
        for part in parts:
            cmd_name = part.split()[0] if part.split() else ""
            if cmd_name in self.PROCESS_COMMANDS:
                risks.append({
                    'level': RiskLevel.MEDIUM,
                    'type': 'process_command',
                    'description': f'使用进程命令: {cmd_name}',
                })

        # 检查管道
        if ast.pipes:
            risks.append({
                'level': RiskLevel.LOW,
                'type': 'pipe',
                'description': f'使用管道，包含 {len(ast.pipes)} 个命令',
            })

        # 检查重定向
        if ast.redirects:
            risks.append({
                'level': RiskLevel.LOW,
                'type': 'redirect',
                'description': f'使用重定向，包含 {len(ast.redirects)} 个操作',
            })

        return risks

    def get_command_name(self, command: str) -> str:
        """提取命令名称"""
        parts = command.strip().split()
        if parts:
            return parts[0]
        return ""

    def get_arguments(self, command: str) -> List[str]:
        """提取命令参数"""
        parts = command.strip().split()
        if len(parts) > 1:
            return parts[1:]
        return []

    def is_safe(self, command: str) -> bool:
        """快速检查命令是否安全"""
        ast = self.analyze(command)
        high_risks = [r for r in ast.risks if r['level'] in (RiskLevel.HIGH, RiskLevel.CRITICAL)]
        return len(high_risks) == 0


# 全局分析器实例
_analyzer: Optional[ShellAnalyzer] = None


def get_shell_analyzer() -> ShellAnalyzer:
    """获取全局 Shell 分析器实例"""
    global _analyzer
    if _analyzer is None:
        _analyzer = ShellAnalyzer()
    return _analyzer
