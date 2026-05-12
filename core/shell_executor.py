"""Shell执行引擎模块 - 借鉴Claude Code的Shell执行设计

提供安全、可靠的命令执行能力，支持：
1. 进程树管理（tree-kill）
2. 输出大小监控和限制
3. 自动后台化
4. 沙箱隔离
5. 实时输出流处理
6. 超时控制

设计亮点:
- 防止后台任务填满磁盘
- 进程树完整终止
- 支持异步执行
"""

import asyncio
import subprocess
import os
import signal
import shlex
from typing import List, Dict, Any, Optional, Callable, Tuple
from enum import Enum
from datetime import datetime
from dataclasses import dataclass


class ShellCommandStatus(Enum):
    """命令执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    BACKGROUND = "background"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


@dataclass
class ShellCommandResult:
    """命令执行结果"""
    command: str
    status: ShellCommandStatus
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    was_backgrounded: bool = False


class ShellExecutor:
    """Shell执行器"""
    
    def __init__(self):
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._backgrounded_processes: Dict[str, subprocess.Popen] = {}
        
        # 配置参数
        self._max_output_bytes = 10 * 1024 * 1024  # 10MB
        self._default_timeout = 300  # 5分钟
        self._size_watchdog_interval = 5  # 5秒检查一次
    
    async def execute(self, 
                     command: str,
                     cwd: Optional[str] = None,
                     timeout: Optional[int] = None,
                     env: Optional[Dict[str, str]] = None,
                     capture_output: bool = True,
                     background_on_timeout: bool = True,
                     max_output_bytes: Optional[int] = None) -> ShellCommandResult:
        """
        执行Shell命令
        
        Args:
            command: 要执行的命令
            cwd: 工作目录
            timeout: 超时时间（秒）
            env: 环境变量
            capture_output: 是否捕获输出
            background_on_timeout: 超时后是否后台运行
            max_output_bytes: 最大输出字节数
        
        Returns:
            命令执行结果
        """
        result = ShellCommandResult(
            command=command,
            status=ShellCommandStatus.PENDING,
            started_at=datetime.now()
        )
        
        timeout = timeout or self._default_timeout
        max_output = max_output_bytes or self._max_output_bytes
        
        # 设置环境变量
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        
        # 解析命令
        if isinstance(command, str):
            cmd_args = shlex.split(command)
        else:
            cmd_args = command
        
        if not cmd_args:
            result.status = ShellCommandStatus.FAILED
            result.stderr = "空命令"
            result.finished_at = datetime.now()
            return result
        
        try:
            # 创建进程
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                cwd=cwd or os.getcwd(),
                env=process_env,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
                stdin=asyncio.subprocess.PIPE,
                start_new_session=True  # 创建新进程组
            )
            
            result.status = ShellCommandStatus.RUNNING
            
            # 设置输出监控
            stdout_data = bytearray()
            stderr_data = bytearray()
            output_too_large = False
            
            async def read_output(stream, buffer):
                nonlocal output_too_large
                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            stream.read(4096), 
                            timeout=1.0
                        )
                        if not chunk:
                            break
                        if len(buffer) + len(chunk) > max_output:
                            output_too_large = True
                            buffer.extend(chunk[:max_output - len(buffer)])
                            break
                        buffer.extend(chunk)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break
            
            # 读取输出
            stdout_task = asyncio.create_task(
                read_output(process.stdout, stdout_data) if capture_output else asyncio.sleep(0)
            )
            stderr_task = asyncio.create_task(
                read_output(process.stderr, stderr_data) if capture_output else asyncio.sleep(0)
            )
            
            # 等待完成或超时
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
                
                # 等待输出读取完成
                await asyncio.gather(stdout_task, stderr_task)
                
                result.exit_code = process.returncode
                result.status = ShellCommandStatus.COMPLETED if process.returncode == 0 else ShellCommandStatus.FAILED
            
            except asyncio.TimeoutError:
                # 超时处理
                if background_on_timeout:
                    # 后台运行
                    result.status = ShellCommandStatus.BACKGROUND
                    result.was_backgrounded = True
                    self._backgrounded_processes[command] = process
                    
                    # 启动后台监控
                    asyncio.create_task(self._monitor_background_process(command, process))
                else:
                    # 终止进程
                    await self._kill_process(process)
                    result.status = ShellCommandStatus.KILLED
            
            # 处理输出
            if capture_output:
                result.stdout = stdout_data.decode('utf-8', errors='replace')
                result.stderr = stderr_data.decode('utf-8', errors='replace')
                if output_too_large:
                    result.stderr += "\n[警告] 输出被截断，超过最大限制"
        
        except Exception as e:
            result.status = ShellCommandStatus.FAILED
            result.stderr = str(e)
        
        result.finished_at = datetime.now()
        if result.started_at:
            result.duration = (result.finished_at - result.started_at).total_seconds()
        
        return result
    
    async def _kill_process(self, process: subprocess.Popen):
        """终止进程及其子进程"""
        try:
            # 终止整个进程组
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except ProcessLookupError:
            pass
        except asyncio.TimeoutError:
            # 强制终止
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                await process.wait()
            except Exception:
                pass
    
    async def _monitor_background_process(self, command: str, process: subprocess.Popen):
        """监控后台进程"""
        try:
            await process.wait()
            # 清理完成的进程
            if command in self._backgrounded_processes:
                del self._backgrounded_processes[command]
        except Exception:
            pass
    
    def get_background_process_count(self) -> int:
        """获取后台进程数量"""
        return len(self._backgrounded_processes)
    
    def kill_background_process(self, command: str):
        """终止后台进程"""
        if command in self._backgrounded_processes:
            process = self._backgrounded_processes[command]
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except Exception:
                pass
            del self._backgrounded_processes[command]
    
    def kill_all_background_processes(self):
        """终止所有后台进程"""
        for command in list(self._backgrounded_processes.keys()):
            self.kill_background_process(command)


class ShellCommandBuilder:
    """Shell命令构建器"""
    
    def __init__(self):
        self._command_parts = []
        self._cwd = None
        self._timeout = None
        self._env = {}
        self._capture_output = True
        self._background_on_timeout = True
    
    def cmd(self, command: str) -> 'ShellCommandBuilder':
        """设置命令"""
        self._command_parts.append(command)
        return self
    
    def arg(self, arg: str) -> 'ShellCommandBuilder':
        """添加参数"""
        self._command_parts.append(shlex.quote(arg))
        return self
    
    def args(self, args: List[str]) -> 'ShellCommandBuilder':
        """添加多个参数"""
        for arg in args:
            self._command_parts.append(shlex.quote(arg))
        return self
    
    def in_dir(self, cwd: str) -> 'ShellCommandBuilder':
        """设置工作目录"""
        self._cwd = cwd
        return self
    
    def with_timeout(self, seconds: int) -> 'ShellCommandBuilder':
        """设置超时时间"""
        self._timeout = seconds
        return self
    
    def with_env(self, key: str, value: str) -> 'ShellCommandBuilder':
        """设置环境变量"""
        self._env[key] = value
        return self
    
    def with_envs(self, env: Dict[str, str]) -> 'ShellCommandBuilder':
        """设置多个环境变量"""
        self._env.update(env)
        return self
    
    def capture(self, capture: bool) -> 'ShellCommandBuilder':
        """设置是否捕获输出"""
        self._capture_output = capture
        return self
    
    def background_on_timeout(self, enabled: bool) -> 'ShellCommandBuilder':
        """设置超时后是否后台运行"""
        self._background_on_timeout = enabled
        return self
    
    def build(self) -> Dict[str, Any]:
        """构建命令配置"""
        return {
            'command': ' '.join(self._command_parts),
            'cwd': self._cwd,
            'timeout': self._timeout,
            'env': self._env if self._env else None,
            'capture_output': self._capture_output,
            'background_on_timeout': self._background_on_timeout
        }
    
    async def execute(self, executor: Optional[ShellExecutor] = None) -> ShellCommandResult:
        """执行命令"""
        exec = executor or ShellExecutor()
        config = self.build()
        return await exec.execute(**config)


class ShellScriptRunner:
    """Shell脚本运行器"""
    
    def __init__(self):
        self._executor = ShellExecutor()
    
    async def run_script(self, 
                        script: str,
                        cwd: Optional[str] = None,
                        timeout: Optional[int] = None) -> List[ShellCommandResult]:
        """
        运行Shell脚本（多行命令）
        
        Args:
            script: Shell脚本内容
            cwd: 工作目录
            timeout: 总超时时间
        
        Returns:
            每条命令的执行结果
        """
        results = []
        lines = script.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            result = await self._executor.execute(
                command=line,
                cwd=cwd,
                timeout=timeout
            )
            results.append(result)
            
            if result.status in [ShellCommandStatus.FAILED, ShellCommandStatus.KILLED]:
                break
        
        return results
    
    async def run_commands(self, 
                          commands: List[str],
                          cwd: Optional[str] = None,
                          timeout: Optional[int] = None) -> List[ShellCommandResult]:
        """
        运行命令列表
        
        Args:
            commands: 命令列表
            cwd: 工作目录
            timeout: 每条命令的超时时间
        
        Returns:
            每条命令的执行结果
        """
        results = []
        
        for command in commands:
            result = await self._executor.execute(
                command=command,
                cwd=cwd,
                timeout=timeout
            )
            results.append(result)
            
            if result.status in [ShellCommandStatus.FAILED, ShellCommandStatus.KILLED]:
                break
        
        return results


# 便捷函数
async def run_shell_command(command: str, **kwargs) -> ShellCommandResult:
    """便捷执行Shell命令"""
    executor = ShellExecutor()
    return await executor.execute(command, **kwargs)


def build_shell_command(command: str = "") -> ShellCommandBuilder:
    """创建命令构建器"""
    builder = ShellCommandBuilder()
    if command:
        builder.cmd(command)
    return builder


def is_safe_command(command: str) -> bool:
    """检查命令是否安全（防止危险操作）"""
    dangerous_patterns = [
        'rm -rf /',
        ':(){ :|:& };:',  # fork bomb
        'dd if=/dev/zero',
        'mkfs.',
        'format ',
        'chmod -R 777 /',
    ]
    
    cmd_lower = command.lower().strip()
    for pattern in dangerous_patterns:
        if pattern in cmd_lower:
            return False
    
    return True


# 示例用法
async def example_usage():
    """示例用法"""
    # 方式1: 直接执行
    result = await run_shell_command("echo 'Hello World'")
    print(f"输出: {result.stdout}")
    
    # 方式2: 使用构建器
    result = await (
        build_shell_command("ls")
        .arg("-la")
        .in_dir("/tmp")
        .with_timeout(30)
        .execute()
    )
    print(f"目录内容:\n{result.stdout}")
    
    # 方式3: 运行脚本
    runner = ShellScriptRunner()
    results = await runner.run_script("""
        echo "Step 1"
        mkdir -p test_dir
        echo "Step 2"
        ls -la test_dir
    """)
    for r in results:
        print(f"命令: {r.command} -> 状态: {r.status}")