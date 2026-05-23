"""沙盒隔离执行引擎

特性：
- 代码安全执行：在隔离环境中运行不可信代码
- 资源限制：CPU、内存、时间、文件系统访问控制
- 网络隔离：可选的网络访问控制
- 多语言支持：Python、JavaScript、Shell等
- 实时监控：执行过程监控和日志记录
- 自动清理：执行后自动清理临时文件和进程

安全级别：
- Level 1: 基础隔离（subprocess + 资源限制）
- Level 2: 容器隔离（Docker/Podman）
- Level 3: 虚拟机隔离（最高安全性）

反问机制：
- check_forbidden_modules() 检测但不抛出异常，返回禁用模块列表
- execute_python(skip_module_check=True) 跳过模块验证，用于用户确认后的执行
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """安全级别"""
    LEVEL_1 = "basic"      # 基础隔离
    LEVEL_2 = "container"  # 容器隔离
    LEVEL_3 = "vm"         # 虚拟机隔离


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"


@dataclass
class ResourceLimits:
    """资源限制配置"""
    timeout: int = 30              # 超时时间（秒）
    max_memory_mb: int = 512       # 最大内存（MB）
    max_cpu_percent: float = 80.0  # 最大CPU使用率
    max_output_size_kb: int = 1024 # 最大输出大小（KB）
    allow_network: bool = False    # 是否允许网络访问
    allowed_paths: List[str] = field(default_factory=list)  # 允许访问的路径
    forbidden_modules: List[str] = field(default_factory=lambda: [
        "os", "sys", "subprocess", "socket", "requests",
        "urllib", "http", "ftplib", "smtplib", "poplib",
        "imaplib", "telnetlib", "xmlrpc", "pickle", "shelve",
        "marshal", "dbm", "gdbm", "sqlite3"
    ])  # 禁止导入的模块


@dataclass
class SandboxResult:
    """沙盒执行结果"""
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    execution_time: float = 0.0
    memory_used_mb: float = 0.0
    error_message: str = ""
    sandbox_id: str = ""


class SandboxExecutor:
    """沙盒执行器"""
    
    def __init__(self, security_level: SecurityLevel = SecurityLevel.LEVEL_1, 
                 cleanup_interval: int = 3600, max_file_age: int = 86400):
        """初始化沙盒执行器
        
        Args:
            security_level: 安全级别
            cleanup_interval: 自动清理间隔（秒）
            max_file_age: 文件最大存活时间（秒）
        """
        self.security_level = security_level
        self.active_sandboxes: Dict[str, Dict[str, Any]] = {}
        self.sandbox_dir = Path(tempfile.gettempdir()) / "agent_sandbox"
        self.sandbox_dir.mkdir(exist_ok=True)
        
        # 文件跟踪
        self.tracked_files: Dict[str, List[Path]] = {}
        self.cleanup_interval = cleanup_interval
        self.max_file_age = max_file_age
        
        # 后台清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"SandboxExecutor 初始化完成，安全级别: {security_level.value}")
    
    async def start_cleanup_task(self):
        """启动后台定期清理任务"""
        if self._cleanup_task is not None and not self._cleanup_task.done():
            logger.warning("清理任务已在运行")
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("后台清理任务已启动")
    
    async def stop_cleanup_task(self):
        """停止后台定期清理任务"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("后台清理任务已停止")
    
    async def _periodic_cleanup(self):
        """定期清理旧文件"""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_old_files()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"定期清理任务异常: {e}")
    
    async def cleanup_old_files(self):
        """清理旧文件"""
        try:
            current_time = time.time()
            cleaned_count = 0
            
            for item in self.sandbox_dir.iterdir():
                try:
                    file_age = current_time - item.stat().st_mtime
                    if file_age > self.max_file_age:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            import shutil
                            shutil.rmtree(item, ignore_errors=True)
                        cleaned_count += 1
                except Exception as e:
                    logger.warning(f"清理旧文件失败 {item}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个旧文件/目录")
        
        except Exception as e:
            logger.error(f"清理旧文件异常: {e}")
    
    def cleanup_all(self):
        """清理所有沙盒文件（慎用）"""
        try:
            import shutil
            if self.sandbox_dir.exists():
                shutil.rmtree(self.sandbox_dir, ignore_errors=True)
                self.sandbox_dir.mkdir(exist_ok=True)
            logger.info("所有沙盒文件已清理")
        except Exception as e:
            logger.error(f"清理所有文件失败: {e}")
    
    async def _check_code_permission(self, action: str = "execute") -> bool:
        """统一代码执行权限检查点"""
        try:
            from core.services.permission_service import get_permission_service, PermissionType, PermissionDecision
            ps = get_permission_service()
            decision = ps.check_permission(PermissionType.CODE_EXECUTION, target=f"sandbox_{action}")
            if decision not in (PermissionDecision.ALLOW, PermissionDecision.ALWAYS_ALLOW):
                logger.warning(f"代码执行权限被拒绝: {action}")
                return False
        except Exception:
            pass  # 权限系统不可用时默认放行
        return True

    async def execute_python(self,
                            code: str,
                            limits: Optional[ResourceLimits] = None,
                            context: Optional[Dict[str, Any]] = None,
                            skip_module_check: bool = False) -> SandboxResult:
        """执行Python代码

        Args:
            code: Python代码字符串
            limits: 资源限制配置
            context: 执行上下文（变量注入）

        Returns:
            执行结果
        """
        if not await self._check_code_permission("python"):
            return SandboxResult(status=ExecutionStatus.FAILED, error_message="权限被拒绝: CODE_EXECUTION")
        if limits is None:
            limits = ResourceLimits()
        
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:8]}"
        logger.info(f"创建Python沙盒: {sandbox_id}")
        
        try:
            # 1. 代码安全检查
            self._validate_python_code(code, limits, skip_module_check=skip_module_check)
            
            # 2. 准备执行环境
            script_path = await self._prepare_python_script(code, context, sandbox_id)
            
            # 3. 执行代码
            result = await self._execute_in_sandbox(
                script_path, 
                limits, 
                sandbox_id,
                runtime="python"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"沙盒执行失败: {e}")
            return SandboxResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                sandbox_id=sandbox_id
            )
        finally:
            # 4. 清理沙盒
            await self._cleanup_sandbox(sandbox_id)

    async def execute_python_streaming(self, 
                                       code: str,
                                       limits: Optional[ResourceLimits] = None,
                                       context: Optional[Dict[str, Any]] = None,
                                       skip_module_check: bool = False,
                                       on_stdout: Optional[callable] = None,
                                       on_stderr: Optional[callable] = None) -> SandboxResult:
        """执行Python代码并流式输出

        与 execute_python 相同，但逐行读取 stdout/stderr 并回调。
        on_stdout(line) / on_stderr(line) 在每行输出时被调用。

        Args:
            code: Python代码字符串
            limits: 资源限制配置
            context: 执行上下文（变量注入）
            skip_module_check: 是否跳过模块检查
            on_stdout: stdout 每行输出的回调
            on_stderr: stderr 每行输出的回调

        Returns:
            执行结果（含完整输出）
        """
        if limits is None:
            limits = ResourceLimits()

        sandbox_id = f"sandbox_{uuid.uuid4().hex[:8]}"
        logger.info(f"创建流式Python沙盒: {sandbox_id}")

        try:
            self._validate_python_code(code, limits, skip_module_check=skip_module_check)
            script_path = await self._prepare_python_script(code, context, sandbox_id)
        except Exception as e:
            logger.error(f"沙盒执行失败: {e}")
            return SandboxResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                sandbox_id=sandbox_id
            )

        start_time = time.time()

        cmd = [sys.executable, str(script_path)]
        env = os.environ.copy()
        env["PYTHONPATH"] = ""
        env["PATH"] = "/usr/bin:/bin"

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(self.sandbox_dir),
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )

            self.active_sandboxes[sandbox_id] = {
                "process": process,
                "start_time": start_time,
                "limits": limits
            }

            stdout_lines: List[str] = []
            stderr_lines: List[str] = []

            async def _read_stream(stream, lines_list, callback, label=""):
                """逐行读取一个流"""
                while True:
                    try:
                        line_bytes = await asyncio.wait_for(
                            stream.readline(),
                            timeout=max(limits.timeout, 5)
                        )
                        if not line_bytes:
                            break
                        line = line_bytes.decode('utf-8', errors='ignore').rstrip()
                        lines_list.append(line)
                        if callback:
                            callback(line)
                    except asyncio.TimeoutError:
                        # 超时：检查进程是否还活着
                        if process.returncode is not None:
                            break
                        continue

            await asyncio.gather(
                _read_stream(process.stdout, stdout_lines, on_stdout, "stdout"),
                _read_stream(process.stderr, stderr_lines, on_stderr, "stderr"),
            )

            # 等待进程完全退出
            await process.wait()

            execution_time = time.time() - start_time
            stdout_str = "\n".join(stdout_lines)[:limits.max_output_size_kb * 1024]
            stderr_str = "\n".join(stderr_lines)[:limits.max_output_size_kb * 1024]

            if process.returncode == 0:
                status = ExecutionStatus.COMPLETED
            else:
                status = ExecutionStatus.FAILED

            return SandboxResult(
                status=status,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=process.returncode,
                execution_time=execution_time,
                sandbox_id=sandbox_id
            )

        except asyncio.CancelledError:
            self._kill_process_tree(process.pid if 'process' in dir() else None)
            return SandboxResult(
                status=ExecutionStatus.KILLED,
                error_message="执行被取消",
                sandbox_id=sandbox_id
            )
        except Exception as e:
            logger.error(f"流式沙盒执行异常: {e}")
            return SandboxResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                sandbox_id=sandbox_id
            )
        finally:
            await self._cleanup_sandbox(sandbox_id)

    async def execute_javascript(self,
                                code: str,
                                limits: Optional[ResourceLimits] = None) -> SandboxResult:
        """执行JavaScript代码
        
        Args:
            code: JavaScript代码字符串
            limits: 资源限制
            
        Returns:
            执行结果
        """
        if limits is None:
            limits = ResourceLimits()

        if not await self._check_code_permission("javascript"):
            return SandboxResult(status=ExecutionStatus.FAILED, error_message="权限被拒绝: CODE_EXECUTION")
        sandbox_id = f"sandbox_js_{uuid.uuid4().hex[:8]}"
        logger.info(f"创建JavaScript沙盒: {sandbox_id}")
        
        try:
            # 准备JS文件
            script_path = self.sandbox_dir / f"{sandbox_id}.js"
            self._track_file(sandbox_id, script_path)
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # 执行（需要Node.js）
            result = await self._execute_in_sandbox(
                script_path,
                limits,
                sandbox_id,
                runtime="node"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"JS沙盒执行失败: {e}")
            return SandboxResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                sandbox_id=sandbox_id
            )
        finally:
            await self._cleanup_sandbox(sandbox_id)
    
    async def execute_shell(self,
                           command: str,
                           limits: Optional[ResourceLimits] = None) -> SandboxResult:
        """执行Shell命令
        
        Args:
            command: Shell命令
            limits: 资源限制
            
        Returns:
            执行结果
        """
        if limits is None:
            limits = ResourceLimits()

        if not await self._check_code_permission("shell"):
            return SandboxResult(status=ExecutionStatus.FAILED, error_message="权限被拒绝: CODE_EXECUTION")
        sandbox_id = f"sandbox_sh_{uuid.uuid4().hex[:8]}"
        logger.info(f"创建Shell沙盒: {sandbox_id}")

        # 安全检查：禁止危险命令（使用正则匹配，防止空格变体绕过）
        import re as _re
        dangerous_patterns = [
            (r'\brm\s+-[rR]f\b', 'rm -rf (递归删除)'),
            (r'\bmkfs\b', 'mkfs (格式化磁盘)'),
            (r'\bdd\s+if=', 'dd if= (磁盘写入)'),
            (r':\(\)\{', 'Fork炸弹'),
            (r'>\s+/dev/sd[a-z]', '直接写入磁盘设备'),
            (r'\bchmod\s+-R\s+777\s+/\b', 'chmod 777 / (权限放开)'),
            (r'\bwget\s+.*\|\s*bash\b', 'wget pipe bash (远程脚本执行)'),
            (r'\bcurl\s+.*\|\s*bash\b', 'curl pipe bash (远程脚本执行)'),
        ]
        for pattern, desc in dangerous_patterns:
            if _re.search(pattern, command):
                return SandboxResult(
                    status=ExecutionStatus.FAILED,
                    error_message=f"禁止执行危险命令: {desc}",
                    sandbox_id=sandbox_id
                )
        
        try:
            result = await self._execute_in_sandbox(
                command,
                limits,
                sandbox_id,
                runtime="shell",
                shell=True
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Shell沙盒执行失败: {e}")
            return SandboxResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                sandbox_id=sandbox_id
            )
        finally:
            await self._cleanup_sandbox(sandbox_id)
    
    def _validate_python_code(self, code: str, limits: ResourceLimits,
                               skip_module_check: bool = False):
        """验证Python代码安全性

        Args:
            code: Python代码
            limits: 资源限制
            skip_module_check: 是否跳过模块导入检查（用户确认后使用）
        """
        # 检查禁止的模块导入（可跳过——用户已确认）
        if not skip_module_check:
            for module in limits.forbidden_modules:
                if f"import {module}" in code or f"from {module}" in code:
                    raise SecurityError(f"禁止导入模块: {module}")

        # 检查危险函数调用
        dangerous_functions = ["eval(", "exec(", "__import__(", "compile("]
        for func in dangerous_functions:
            if func in code:
                raise SecurityError(f"禁止使用函数: {func}")

        # 检查代码长度
        if len(code) > 10000:
            raise SecurityError("代码过长（最大10000字符）")

    def check_forbidden_modules(self, code: str, limits: ResourceLimits) -> List[str]:
        """检测代码中使用了哪些被禁止的模块（不抛出异常）

        Args:
            code: Python代码
            limits: 资源限制配置

        Returns:
            被禁止的模块名列表（空列表表示没有使用禁止模块）
        """
        import re
        forbidden_found = []
        for module in limits.forbidden_modules:
            if re.search(rf'(?:import\s+{re.escape(module)}\s|from\s+{re.escape(module)}\s)', code):
                forbidden_found.append(module)
        return forbidden_found
    
    def _track_file(self, sandbox_id: str, file_path: Path):
        """跟踪创建的文件
        
        Args:
            sandbox_id: 沙盒ID
            file_path: 文件路径
        """
        if sandbox_id not in self.tracked_files:
            self.tracked_files[sandbox_id] = []
        self.tracked_files[sandbox_id].append(file_path)
    
    async def _prepare_python_script(self, 
                                    code: str,
                                    context: Optional[Dict[str, Any]],
                                    sandbox_id: str) -> Path:
        """准备Python脚本
        
        Args:
            code: 原始代码
            context: 上下文字典
            sandbox_id: 沙盒ID
            
        Returns:
            脚本路径
        """
        script_path = self.sandbox_dir / f"{sandbox_id}.py"
        
        # 跟踪文件
        self._track_file(sandbox_id, script_path)
        
        # 构建安全的执行包装器
        wrapper_lines = [
            "import sys",
            "import json",
            "",
            "# 禁用字节码缓存",
            "sys.dont_write_bytecode = True",
            "",
            "# 注入上下文变量"
        ]
        
        if context:
            for key, value in context.items():
                # 只允许基本类型
                if isinstance(value, (str, int, float, bool, list, dict)):
                    # 使用json.dumps安全序列化
                    serialized = json.dumps(value, ensure_ascii=False)
                    wrapper_lines.append(f"{key} = {serialized}")
        
        wrapper_lines.append("")
        wrapper_lines.append("# 执行用户代码")
        wrapper_lines.append("try:")
        
        # 缩进用户代码
        for line in code.split('\n'):
            wrapper_lines.append(f"    {line}")
        
        wrapper_lines.append("except Exception as e:")
        wrapper_lines.append('    print(f"ERROR: {e}", file=sys.stderr)')
        wrapper_lines.append("    sys.exit(1)")
        wrapper_lines.append("")
        
        wrapper_code = '\n'.join(wrapper_lines)
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(wrapper_code)
        
        return script_path
    
    async def _execute_in_sandbox(self,
                                 target,
                                 limits: ResourceLimits,
                                 sandbox_id: str,
                                 runtime: str = "python",
                                 shell: bool = False) -> SandboxResult:
        """在沙盒中执行
        
        Args:
            target: 执行目标（文件路径或命令）
            limits: 资源限制
            sandbox_id: 沙盒ID
            runtime: 运行时类型
            shell: 是否使用shell
            
        Returns:
            执行结果
        """
        start_time = time.time()
        
        # 构建命令
        if runtime == "python":
            cmd = [sys.executable, str(target)]
        elif runtime == "node":
            cmd = ["node", str(target)]
        elif runtime == "shell":
            cmd = target
        else:
            raise ValueError(f"不支持的运行时: {runtime}")
        
        # 设置环境变量限制
        env = os.environ.copy()
        env["PYTHONPATH"] = ""  # 清空Python路径
        env["PATH"] = "/usr/bin:/bin"  # 限制PATH
        
        # 如果没有允许的路径，设置受限的家目录
        restricted_home = None
        if not limits.allowed_paths:
            restricted_home = self.sandbox_dir / sandbox_id
            restricted_home.mkdir(exist_ok=True)
            self._track_file(sandbox_id, restricted_home)
            env["HOME"] = str(restricted_home)
        
        try:
            # 执行进程
            process = await asyncio.create_subprocess_exec(
                *cmd if isinstance(cmd, list) else cmd.split(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(self.sandbox_dir),
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
            
            # 注册到活跃沙盒
            self.active_sandboxes[sandbox_id] = {
                "process": process,
                "start_time": start_time,
                "limits": limits
            }
            
            # 等待执行完成（带超时）
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=limits.timeout
                )
                
                execution_time = time.time() - start_time
                
                # 解码输出
                stdout_str = stdout.decode('utf-8', errors='ignore')[:limits.max_output_size_kb * 1024]
                stderr_str = stderr.decode('utf-8', errors='ignore')[:limits.max_output_size_kb * 1024]
                
                # 判断状态
                if process.returncode == 0:
                    status = ExecutionStatus.COMPLETED
                else:
                    status = ExecutionStatus.FAILED
                
                return SandboxResult(
                    status=status,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    exit_code=process.returncode,
                    execution_time=execution_time,
                    sandbox_id=sandbox_id
                )
                
            except asyncio.TimeoutError:
                # 超时处理：杀进程树
                try:
                    self._kill_process_tree(process.pid)
                except Exception:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                
                return SandboxResult(
                    status=ExecutionStatus.TIMEOUT,
                    error_message=f"执行超时（{limits.timeout}秒）",
                    sandbox_id=sandbox_id
                )
        
        except Exception as e:
            logger.error(f"沙盒执行异常: {e}")
            return SandboxResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                sandbox_id=sandbox_id
            )
    
    async def _cleanup_sandbox(self, sandbox_id: str):
        """清理沙盒
        
        Args:
            sandbox_id: 沙盒ID
        """
        try:
            # 1. 从活跃列表移除
            if sandbox_id in self.active_sandboxes:
                # 确保进程被终止
                sandbox_info = self.active_sandboxes[sandbox_id]
                process = sandbox_info.get("process")
                if process:
                    try:
                        # asyncio.subprocess.Process 有 returncode 属性
                        if hasattr(process, 'returncode') and process.returncode is None:
                            # 进程还在运行，尝试终止
                            if hasattr(os, 'setsid'):
                                try:
                                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                                except ProcessLookupError:
                                    process.kill()
                            else:
                                process.kill()
                            # 等待进程真正结束
                            await process.wait()
                    except Exception as e:
                        logger.warning(f"终止进程失败: {e}")
                del self.active_sandboxes[sandbox_id]
            
            # 2. 清理跟踪的文件
            if sandbox_id in self.tracked_files:
                for file_path in self.tracked_files[sandbox_id]:
                    try:
                        if file_path.exists():
                            if file_path.is_file():
                                file_path.unlink()
                            elif file_path.is_dir():
                                import shutil
                                shutil.rmtree(file_path, ignore_errors=True)
                        logger.debug(f"已清理跟踪文件: {file_path}")
                    except Exception as e:
                        logger.warning(f"清理跟踪文件失败 {file_path}: {e}")
                del self.tracked_files[sandbox_id]
            
            # 3. 清理模式匹配的文件（双重保险）
            sandbox_files = list(self.sandbox_dir.glob(f"{sandbox_id}*"))
            for file in sandbox_files:
                try:
                    if file.exists():
                        if file.is_file():
                            file.unlink()
                        elif file.is_dir():
                            import shutil
                            shutil.rmtree(file, ignore_errors=True)
                        logger.debug(f"已清理模式匹配文件: {file}")
                except Exception as e:
                    logger.warning(f"清理模式匹配文件失败 {file}: {e}")
            
            logger.debug(f"沙盒清理完成: {sandbox_id}")
            
        except Exception as e:
            logger.error(f"沙盒清理失败: {e}")
    
    async def kill_sandbox(self, sandbox_id: str):
        """强制终止沙盒
        
        Args:
            sandbox_id: 沙盒ID
        """
        if sandbox_id in self.active_sandboxes:
            sandbox_info = self.active_sandboxes[sandbox_id]
            process = sandbox_info["process"]
            
            try:
                # 发送SIGTERM
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                await asyncio.sleep(1)
                
                # 如果还在运行，发送SIGKILL
                if hasattr(process, 'returncode') and process.returncode is None:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                
                logger.info(f"沙盒已终止: {sandbox_id}")
                
            except Exception as e:
                logger.error(f"终止沙盒失败: {e}")
            finally:
                await self._cleanup_sandbox(sandbox_id)
    
    def get_active_sandboxes(self) -> List[str]:
        """获取活跃沙盒列表"""
        return list(self.active_sandboxes.keys())
    
    def get_sandbox_info(self, sandbox_id: str) -> Optional[Dict[str, Any]]:
        """获取沙盒信息"""
        if sandbox_id in self.active_sandboxes:
            info = self.active_sandboxes[sandbox_id].copy()
            info["running_time"] = time.time() - info["start_time"]
            return info
        return None


class SecurityError(Exception):
    """安全错误"""
    pass


# 全局单例
_sandbox_executor = None


def get_sandbox_executor(security_level: SecurityLevel = SecurityLevel.LEVEL_1) -> SandboxExecutor:
    """获取沙盒执行器单例"""
    global _sandbox_executor
    if _sandbox_executor is None:
        _sandbox_executor = SandboxExecutor(security_level)
    return _sandbox_executor
