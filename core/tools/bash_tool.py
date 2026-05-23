"""Bash 沙盒执行工具 — 标准工具接口，非 MCP 绕路

基于 ShellExecutor 提供安全、可控的命令执行能力。

设计：
- BashTool 包装 ShellExecutor，添加沙盒约束
- 可直接导入使用，也可通过 MCP 调用
- 保持与现有 ShellExecutor/SandboxExecutor 的兼容
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class BashResult:
    """Bash 执行结果"""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration: float = 0.0
    truncated: bool = False
    timed_out: bool = False
    command: str = ""
    error_message: str = ""


class BashTool:
    """Bash 执行工具 — 标准沙盒接口

    使用方式：
        bash = BashTool()
        result = await bash.execute("ls -la", timeout=30)
        print(result.stdout)
    """

    def __init__(self, allowed_paths: Optional[List[str]] = None):
        self._executor: Any = None
        self.allowed_paths = allowed_paths or [os.path.expanduser("~"), "/tmp"]

    async def _get_executor(self):
        """延迟初始化 ShellExecutor"""
        if self._executor is None:
            from core.tools.shell_executor import ShellExecutor
            self._executor = ShellExecutor()
        return self._executor

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        max_output_chars: int = 10000,
    ) -> BashResult:
        """执行 Bash 命令

        Args:
            command: 要执行的命令
            timeout: 超时秒数（默认 30）
            cwd: 工作目录
            env: 环境变量
            max_output_chars: 最大输出字符数（默认 10000）

        Returns:
            BashResult 执行结果
        """
        result = BashResult(command=command)

        # 安全检查
        safe, msg = self._check_command_safety(command)
        if not safe:
            result.exit_code = -1
            result.error_message = msg
            result.stderr = msg
            return result

        # 检查 cwd
        if cwd:
            cwd = os.path.abspath(os.path.expanduser(cwd))
            if not os.path.isdir(cwd):
                result.exit_code = -1
                result.error_message = f"工作目录不存在: {cwd}"
                result.stderr = result.error_message
                return result

        start = datetime.now()
        try:
            executor = await self._get_executor()
            shell_result = await executor.execute(
                command=command,
                cwd=cwd,
                timeout=timeout,
                env=env,
                capture_output=True,
                background_on_timeout=False,
            )

            result.exit_code = shell_result.exit_code if shell_result.exit_code is not None else 0
            result.stdout = shell_result.stdout or ""
            result.stderr = shell_result.stderr or ""
            result.timed_out = shell_result.status.name == "KILLED" if hasattr(shell_result.status, 'name') else False

            # 输出截断
            stdout_truncated = self._truncate_output(result, "stdout", max_output_chars)
            stderr_truncated = self._truncate_output(result, "stderr", max_output_chars)
            result.truncated = stdout_truncated or stderr_truncated

            if result.timed_out:
                preview = result.stdout[:200] if result.stdout else ""
                result.error_message = f"命令执行超时（{timeout}秒）"
                if preview:
                    result.error_message += f"\n输出（前200字符）:\n{preview}"

        except ImportError:
            # fallback: 直接 subprocess
            result = await self._fallback_execute(command, timeout, cwd, env, max_output_chars)
        except Exception as e:
            result.exit_code = -1
            result.error_message = f"执行异常: {e}"
            result.stderr = str(e)

        elapsed = (datetime.now() - start).total_seconds()
        result.duration = elapsed

        return result

    async def execute_script(
        self,
        script: str,
        timeout: int = 60,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        max_output_chars: int = 10000,
    ) -> BashResult:
        """执行多行脚本（逐行执行，遇错停止）

        Args:
            script: 多行脚本内容
            timeout: 总超时秒数
            cwd: 工作目录
            env: 环境变量
            max_output_chars: 最大输出字符数

        Returns:
            BashResult 合并后的执行结果
        """
        from core.tools.shell_executor import ShellScriptRunner

        runner = ShellScriptRunner()
        start = datetime.now()

        try:
            results = await runner.run_script(script, cwd=cwd, timeout=timeout)
        except Exception as e:
            return BashResult(
                command=script,
                stderr=str(e),
                exit_code=-1,
                error_message=f"脚本执行异常: {e}",
            )

        stdout_parts = []
        stderr_parts = []
        last_exit = 0
        for r in results:
            if r.stdout:
                stdout_parts.append(f"$ {r.command}\n{r.stdout}")
            if r.stderr:
                stderr_parts.append(f"$ {r.command}\n{r.stderr}")
            if r.exit_code is not None:
                last_exit = r.exit_code
            if r.status.name in ("FAILED", "KILLED"):
                break

        merged = BashResult(
            command=script,
            exit_code=last_exit,
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            duration=(datetime.now() - start).total_seconds(),
        )

        self._truncate_output(merged, "stdout", max_output_chars)
        self._truncate_output(merged, "stderr", max_output_chars)
        merged.truncated = merged.truncated or False

        return merged

    def _check_command_safety(self, command: str) -> Tuple[bool, str]:
        """检查命令是否安全（30+ 种危险模式）"""
        dangerous_patterns = [
            # ── 文件系统破坏 ──
            "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf .", "rm -rf ..",
            "mkfs.", "fdisk", "dd if=/dev/zero", "dd if=/dev/random",
            "> /dev/sda", "> /dev/sdb", "> /dev/nvme", "> /dev/mmcblk",
            "format", "fat32", "ntfs",
            # ── 权限与系统操作 ──
            "chmod 777 /", "chown -R", "chmod -R 777 /",
            "passwd root", "usermod -aG sudo", "useradd",
            "visudo", "sudoers",
            # ── 网络与防火墙 ──
            "iptables -F", "iptables -P", "ufw disable",
            "systemctl stop firewalld",
            # ── 内核与系统 ──
            ":(){ :|:& };:",  # fork bomb
            "dd if=/dev/zero of=/dev/sda", "dd if=/dev/random of=/dev/sda",
            "echo 1 > /proc/sys/kernel/panic",
            "poweroff", "shutdown -h now", "reboot", "init 0", "init 6",
            "halt", "shutdown -r",
            # ── 远程操作危险 ──
            "wget -O /", "curl -o /", "curl -O /",
            "wget http://", "curl http://",
            "bash <(curl", "bash <(wget",
            # ── 容器逃逸 ──
            "privileged", "--pid=host", "--net=host", "--ipc=host",
            "cgroup", "docker run --", "kubectl exec",
            # ── 命令混淆绕过 ──
            "${IFS}", "base64 --decode | bash", "base64 -d | bash",
        ]
        cmd_lower = command.lower().strip()
        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                return False, f"禁止执行危险命令（匹配模式: {pattern}）"
        return True, ""

    def _truncate_output(self, result: BashResult, attr: str, max_chars: int) -> bool:
        """截断输出到最大字符数"""
        val = getattr(result, attr, "")
        if len(val) > max_chars:
            truncated = val[:max_chars]
            setattr(result, attr, truncated + f"\n\n... [输出已截断，原 {len(val)} 字符]")
            return True
        return False

    async def _fallback_execute(
        self,
        command: str,
        timeout: int,
        cwd: Optional[str],
        env: Optional[Dict[str, str]],
        max_output_chars: int,
    ) -> BashResult:
        """回退执行：直接 subprocess"""
        import subprocess

        result = BashResult(command=command)
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ, **(env or {})},
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                result.exit_code = proc.returncode or 0
                result.stdout = stdout.decode("utf-8", errors="replace")
                result.stderr = stderr.decode("utf-8", errors="replace")
                self._truncate_output(result, "stdout", max_output_chars)
                self._truncate_output(result, "stderr", max_output_chars)
            except asyncio.TimeoutError:
                proc.kill()
                result.timed_out = True
                result.error_message = f"命令执行超时（{timeout}秒）"
        except Exception as e:
            result.exit_code = -1
            result.error_message = str(e)
            result.stderr = str(e)
        return result


# 便捷函数
async def run_bash(command: str, **kwargs) -> BashResult:
    """便捷执行 Bash 命令"""
    tool = BashTool()
    return await tool.execute(command, **kwargs)
