"""
Shell 命令安全卫士 — 危险命令检测 + 沙箱

对标 gemini-cli 的 ShellTool 安全机制
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskItem:
    """风险项"""
    level: str  # high/medium/low
    type: str  # pattern/path/injection
    description: str
    suggestion: str = ""


@dataclass
class ScanResult:
    """扫描结果"""
    safe: bool
    risks: List[RiskItem] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    command: str = ""


# ── 危险命令模式 ──
DANGEROUS_PATTERNS = [
    # 高危：递归删除
    (r'rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/', "递归删除根目录", "high"),
    (r'rm\s+-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*\s+/', "递归删除根目录", "high"),
    (r'rm\s+-rf\s+/', "递归删除根目录", "high"),
    (r'rm\s+-fr\s+/', "递归删除根目录", "high"),
    (r'rm\s+--recursive\s+--force\s+/', "递归删除根目录", "high"),

    # 高危：危险权限
    (r'chmod\s+777', "设置危险权限 777", "high"),
    (r'chmod\s+-R\s+777', "递归设置危险权限 777", "high"),
    (r'chmod\s+777\s+-R', "递归设置危险权限 777", "high"),

    # 高危：管道执行
    (r'curl\s+.*\|\s*sh', "curl 管道执行", "high"),
    (r'curl\s+.*\|\s*bash', "curl 管道执行", "high"),
    (r'wget\s+.*\|\s*sh', "wget 管道执行", "high"),
    (r'wget\s+.*\|\s*bash', "wget 管道执行", "high"),
    (r'curl\s+.*\|\s*sudo\s+sh', "curl 管道提权执行", "high"),
    (r'wget\s+.*\|\s*sudo\s+sh', "wget 管道提权执行", "high"),

    # 高危：动态执行
    (r'eval\s*\(', "eval 动态执行", "high"),
    (r'exec\s*\(', "exec 动态执行", "high"),
    (r'__import__\s*\(', "__import__ 动态导入", "high"),
    (r'compile\s*\(', "compile 动态编译", "high"),

    # 高危：系统文件修改
    (r'>\s*/etc/', "修改系统配置文件", "high"),
    (r'>\s*/usr/', "修改系统目录", "high"),
    (r'>\s*/var/', "修改系统目录", "high"),
    (r'>>\s*/etc/', "追加系统配置文件", "high"),

    # 高危：提权
    (r'sudo\s+', "使用 sudo 提权", "high"),
    (r'su\s+-', "切换用户", "high"),
    (r'chmod\s+s\s+', "设置 SUID/SGID", "high"),

    # 中危：网络操作
    (r'nc\s+-l', "监听网络端口", "medium"),
    (r'nc\s+-e', "网络反弹 shell", "medium"),
    (r'python\s+-c\s+[\'"]import\s+socket', "Python socket 反弹", "medium"),
    (r'perl\s+-e\s+[\'"]use\s+socket', "Perl socket 反弹", "medium"),

    # 中危：进程操作
    (r'kill\s+-9\s+1', "杀死 PID 1 进程", "medium"),
    (r'killall', "杀死所有进程", "medium"),
    (r'pkill\s+-9', "强制杀死进程", "medium"),

    # 低危：环境变量
    (r'export\s+PATH=', "修改 PATH 环境变量", "low"),
    (r'PATH\s*=\s*', "设置 PATH 环境变量", "low"),
]


# ── 敏感路径 ──
SENSITIVE_PATHS = [
    "/etc/",
    "/usr/",
    "/var/",
    "/bin/",
    "/sbin/",
    "/boot/",
    "/root/",
    "/home/",
    "~/.ssh/",
    "~/.aws/",
    "~/.azure/",
    "~/.config/",
    "~/.gnupg/",
    "~/.docker/",
]


# ── 注入模式 ──
INJECTION_PATTERNS = [
    # 命令拼接
    (r';\s*rm\s+', "命令拼接删除", "high"),
    (r'&&\s*rm\s+', "命令拼接删除", "high"),
    (r'\|\s*rm\s+', "管道拼接删除", "high"),
    (r';\s*chmod\s+', "命令拼接权限修改", "medium"),
    (r'&&\s*chmod\s+', "命令拼接权限修改", "medium"),

    # 变量注入
    (r'\$\{.*\}', "Shell 变量展开", "low"),
    (r'`.*`', "反引号命令替换", "medium"),

    # 引号逃逸
    (r'"\s*;\s*rm', "引号逃逸删除", "high"),
    (r"'\s*;\s*rm", "引号逃逸删除", "high"),
    (r'"\s*&&\s*rm', "引号逃逸删除", "high"),
    (r"'\s*&&\s*rm", "引号逃逸删除", "high"),
]


class ShellGuard:
    """Shell 命令安全卫士"""

    def __init__(self, sandbox_mode: bool = False):
        self.sandbox_mode = sandbox_mode
        self.dangerous_patterns = DANGEROUS_PATTERNS
        self.sensitive_paths = SENSITIVE_PATHS
        self.injection_patterns = INJECTION_PATTERNS

    def scan(self, command: str) -> ScanResult:
        """
        扫描命令安全性

        Args:
            command: 要扫描的 shell 命令

        Returns:
            ScanResult: 扫描结果
        """
        risks = []
        suggestions = []

        # 1. 检测危险模式
        for pattern, desc, level in self.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                risks.append(RiskItem(
                    level=level,
                    type="pattern",
                    description=desc,
                    suggestion=f"避免使用: {desc}",
                ))

        # 2. 检查路径边界
        for risk in self._check_path_boundary(command):
            risks.append(risk)

        # 3. 检测注入模式
        for pattern, desc, level in self.injection_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                risks.append(RiskItem(
                    level=level,
                    type="injection",
                    description=desc,
                    suggestion=f"检测到注入风险: {desc}",
                ))

        # 4. 检查沙箱模式
        if self.sandbox_mode:
            suggestions.append("沙箱模式已启用，命令将在隔离环境中执行")

        # 5. 生成建议
        if not risks:
            suggestions.append("命令安全，未检测到风险")
        else:
            high_risks = [r for r in risks if r.level == "high"]
            if high_risks:
                suggestions.append("检测到高危操作，建议拒绝执行")

        # 6. 判断是否安全
        high_risks = [r for r in risks if r.level == "high"]
        medium_risks = [r for r in risks if r.level == "medium"]

        safe = len(high_risks) == 0 and len(medium_risks) == 0

        return ScanResult(
            safe=safe,
            risks=risks,
            suggestions=suggestions,
            command=command,
        )

    def _check_path_boundary(self, command: str) -> List[RiskItem]:
        """检查路径边界"""
        risks = []

        # 提取命令中的路径
        path_patterns = [
            r'>\s*([^\s;|&]+)',  # 输出重定向
            r'>>\s*([^\s;|&]+)',  # 追加重定向
            r'cat\s+([^\s;|&]+)',  # cat 读取
            r'rm\s+([^\s;|&]+)',  # rm 删除
            r'mv\s+([^\s;|&]+)',  # mv 移动
            r'cp\s+([^\s;|&]+)',  # cp 复制
        ]

        for pattern in path_patterns:
            matches = re.findall(pattern, command)
            for match in matches:
                # 检查是否是敏感路径
                for sensitive in self.sensitive_paths:
                    if match.startswith(sensitive) or match.startswith(sensitive.replace("~", os.path.expanduser("~"))):
                        risks.append(RiskItem(
                            level="high",
                            type="path",
                            description=f"访问敏感路径: {match}",
                            suggestion=f"避免操作敏感路径: {sensitive}",
                        ))
                        break

        return risks

    def get_safe_command(self, command: str) -> str:
        """
        尝试生成安全的命令版本

        如果命令不安全，尝试移除危险部分
        """
        # 简单实现：移除 sudo
        safe = re.sub(r'sudo\s+', '', command)

        # 移除危险的 rm 选项
        safe = re.sub(r'rm\s+-rf\s+/', 'echo "危险操作已阻止"', safe)
        safe = re.sub(r'rm\s+-fr\s+/', 'echo "危险操作已阻止"', safe)

        return safe


# 全局 ShellGuard 实例
_shell_guard: Optional[ShellGuard] = None


def get_shell_guard(sandbox_mode: bool = False) -> ShellGuard:
    """获取全局 ShellGuard 实例"""
    global _shell_guard
    if _shell_guard is None:
        _shell_guard = ShellGuard(sandbox_mode)
    return _shell_guard
