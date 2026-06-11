"""
Bash工具 - 参考Open Code的BashTool实现

支持：
- Shell命令执行
- 超时控制
- 输出捕获
- 工作目录设置
"""

import subprocess
import os
import time
import shlex
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600
MAX_CAPTURE_BYTES = 1024 * 1024  # 1MB


@dataclass
class BashInput(ToolInput):
    """Bash工具输入"""
    command: str
    workdir: Optional[str] = None
    timeout: Optional[int] = None
    description: Optional[str] = None


@dataclass
class BashOutput(ToolOutput):
    """Bash工具输出"""
    command: str
    cwd: str
    exit_code: Optional[int]
    output: str
    truncated: bool
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    timed_out: bool = False
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class BashTool(Tool[BashInput, BashOutput]):
    """Bash工具 - 参考Open Code的BashTool"""

    def __init__(self):
        super().__init__(
            name="bash",
            description="Execute one shell command string with the host user's filesystem, process, and network authority. The active Location is the default working directory. Relative workdir values resolve from that Location.",
            permission=ToolPermission.EXECUTE,
            timeout=DEFAULT_TIMEOUT,
            max_retries=1
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command string to execute"
                },
                "workdir": {
                    "type": "string",
                    "description": "Working directory. Defaults to the active Location; relative paths resolve from that Location."
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in milliseconds. Defaults to {DEFAULT_TIMEOUT * 1000} and may not exceed {MAX_TIMEOUT * 1000}.",
                    "minimum": 1,
                    "maximum": MAX_TIMEOUT * 1000
                },
                "description": {
                    "type": "string",
                    "description": "Concise description of the command's purpose"
                }
            },
            "required": ["command"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "exit_code": {"type": "integer"},
                "output": {"type": "string"},
                "truncated": {"type": "boolean"},
                "stdout_truncated": {"type": "boolean"},
                "stderr_truncated": {"type": "boolean"},
                "timed_out": {"type": "boolean"},
                "warnings": {"type": "array", "items": {"type": "string"}}
            }
        }

    def validate_input(self, input_data: Any) -> BashInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return BashInput(
                command=input_data.get("command", ""),
                workdir=input_data.get("workdir"),
                timeout=input_data.get("timeout"),
                description=input_data.get("description")
            )
        elif isinstance(input_data, BashInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: BashInput) -> BashOutput:
        """执行Bash命令"""
        # 确定工作目录
        cwd = input_data.workdir or os.getcwd()
        if not os.path.isabs(cwd):
            cwd = os.path.abspath(cwd)

        # 验证工作目录
        if not os.path.isdir(cwd):
            raise ValueError(f"Working directory is not a directory: {cwd}")

        # 验证超时时间
        timeout = input_data.timeout or (DEFAULT_TIMEOUT * 1000)
        if timeout > MAX_TIMEOUT * 1000:
            timeout = MAX_TIMEOUT * 1000
        timeout_seconds = timeout / 1000

        # 执行命令
        try:
            process = subprocess.Popen(
                input_data.command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False  # 使用二进制模式以正确处理编码
            )

            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                stdout = b""
                stderr = b"Command timed out"
                timed_out = True

            # 处理输出
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')

            # 检查输出截断
            stdout_truncated = len(stdout) > MAX_CAPTURE_BYTES
            stderr_truncated = len(stderr) > MAX_CAPTURE_BYTES

            if stdout_truncated:
                stdout_str = stdout_str[:MAX_CAPTURE_BYTES] + "\n\n[stdout capture truncated at the in-memory safety limit]"
            if stderr_truncated:
                stderr_str = stderr_str[:MAX_CAPTURE_BYTES] + "\n\n[stderr capture truncated at the in-memory safety limit]"

            # 组合输出
            output = self._compact_output(stdout_str, stderr_str)

            # 添加警告
            warnings = []
            if timed_out:
                output += f"\n\nCommand exceeded timeout of {timeout} ms. Retry with a larger timeout if the command is expected to take longer."

            return BashOutput(
                command=input_data.command,
                cwd=cwd,
                exit_code=process.returncode,
                output=output,
                truncated=stdout_truncated or stderr_truncated,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                timed_out=timed_out,
                warnings=warnings
            )

        except Exception as e:
            logger.error(f"执行命令失败: {e}")
            return BashOutput(
                command=input_data.command,
                cwd=cwd,
                exit_code=-1,
                output=f"Error executing command: {str(e)}",
                truncated=False,
                warnings=[f"Error: {str(e)}"]
            )

    def _compact_output(self, stdout: str, stderr: str) -> str:
        """组合stdout和stderr"""
        if stdout and stderr:
            return f"{stdout}\n\nstderr:\n{stderr}"
        elif stderr:
            return f"stderr:\n{stderr}"
        elif stdout:
            return stdout
        else:
            return "(no output)"


# 注册工具
bash_tool = BashTool()
