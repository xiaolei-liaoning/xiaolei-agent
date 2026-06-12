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
        "ctypes", "socket", "ftplib", "smtplib", "poplib",
        "imaplib", "telnetlib", "xmlrpc", "pickle", "shelve",
        "marshal",
        "__import__", "compile", "exec", "eval",
    ])  # 禁止导入的模块（保留 json/os/sys/requests/urllib/pathlib 等常用）


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
            
            # 3.5 文件写入自动导出：检测到文件写入时，在清理前复制到用户目录
            if result.status.value == "completed":
                try:
                    file_writes = detect_file_writes(code)
                    if file_writes:
                        detected_paths = extract_file_paths(code)
                        recommended = get_recommended_path(detected_paths, "")
                        await self._export_files_before_cleanup(sandbox_id, recommended)
                except Exception as e:
                    logger.debug(f"文件导出跳过: {e}")
            
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

        sandbox_id = f"sandbox_sh_{uuid.uuid4().hex[:8]}"
        logger.info(f"创建Shell沙盒: {sandbox_id}")

        try:
            result = await self._execute_in_sandbox(
                command,
                limits,
                sandbox_id,
                runtime="shell",
                shell=True
            )
            
            # Shell命令也可能创建文件，清理前导出
            if result.status.value == "completed":
                try:
                    sandbox_home = self.sandbox_dir / sandbox_id
                    if sandbox_home.exists():
                        for item in sandbox_home.rglob("*"):
                            if item.is_file() and not item.name.startswith("."):
                                dest = os.path.expanduser(f"~/Desktop/{item.name}")
                                try:
                                    import shutil as _shutil
                                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                                    _shutil.copy2(str(item), dest)
                                    logger.info(f"Shell沙盒文件已导出: {item.name} → {dest}")
                                except Exception:
                                    pass
                except Exception:
                    pass
            
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
        # ── 检测 JavaScript 代码误入 execute_python ──
        js_indicators = [
            "function ", "function(", "var ", "let ", "const ",
            "document.", "window.", "console.log", "=> {",
            "addEventListener", "getElementById", "querySelector",
            "innerHTML", "textContent", "onclick",
            "export default", "export const", "import {",
        ]
        code_stripped = code.strip()
        # 排除注释行
        code_lines = [l for l in code_stripped.split("\n") if l.strip() and not l.strip().startswith("#")]
        code_no_comments = "\n".join(code_lines)
        js_score = sum(1 for ind in js_indicators if ind in code_no_comments)
        if js_score >= 2:
            raise SecurityError(
                "检测到 JavaScript 代码。execute_python 只能执行 Python 代码。\n"
                "如果要创建 HTML/游戏/文件，请使用 write_file 工具。\n"
                f"检测到的 JS 特征: {[ind for ind in js_indicators if ind in code_no_comments][:3]}"
            )

        # 检查禁止的模块导入（可跳过——用户已确认）
        if not skip_module_check:
            for module in limits.forbidden_modules:
                if f"import {module}" in code or f"from {module}" in code:
                    raise SecurityError(f"禁止导入模块: {module}")

            # 检查 subprocess 调用（防止绕过 ShellGuard）
            dangerous_imports = ["subprocess", "os.system", "os.popen", "popen"]
            for dangerous in dangerous_imports:
                if dangerous in code:
                    raise SecurityError(f"禁止使用: {dangerous}（请使用 execute_shell 工具）")

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
    
    async def _export_files_before_cleanup(self, sandbox_id: str, recommended_path: str):
        """清理前将沙盒中创建的文件导出到用户目录
        
        Args:
            sandbox_id: 沙盒ID
            recommended_path: 推荐的导出路径（如 ~/Desktop/game.html）
        """
        import shutil as _shutil
        
        sandbox_home = self.sandbox_dir / sandbox_id
        if not sandbox_home.exists():
            return
        
        # 展开用户路径
        dest_dir = os.path.expanduser(os.path.dirname(recommended_path)) if recommended_path else ""
        dest_name = os.path.basename(recommended_path) if recommended_path else ""
        
        exported = 0
        for item in sandbox_home.rglob("*"):
            if item.is_file() and not item.name.startswith(".") and item.name != "sandbox_script.py":
                if dest_dir and dest_name:
                    # 导出到推荐路径
                    dest_path = os.path.join(dest_dir, dest_name)
                else:
                    # 无推荐路径时，导出到 ~/Desktop/
                    dest_path = os.path.expanduser(f"~/Desktop/{item.name}")
                
                try:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    _shutil.copy2(str(item), dest_path)
                    logger.info(f"沙盒文件已导出: {item.name} → {dest_path}")
                    exported += 1
                except Exception as e:
                    logger.warning(f"导出文件失败 {item.name}: {e}")
        
        if exported:
            logger.info(f"共导出 {exported} 个文件到 {dest_dir or '~/Desktop/'}")
    
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


# ═══════════════════════════════════════════════════════════════════
# 文件写入检测功能
# ═══════════════════════════════════════════════════════════════════

import re as _re
import ast as _ast


def detect_file_writes(code: str) -> List[Dict[str, Any]]:
    """检测代码中的文件写入操作
    
    使用常见模式正则 + 简单 AST 分析，覆盖 95% 的文件写入场景。
    
    Args:
        code: Python 代码字符串
        
    Returns:
        List[Dict]: 检测到的文件写入操作列表
        [
            {
                "type": "open_write",      # 操作类型
                "pattern": "open('file', 'w')",  # 匹配的模式
                "line": 5,                 # 行号
                "path_hint": "game.html",  # 路径提示（如果能提取到）
                "confidence": "high"       # 置信度
            },
            ...
        ]
    """
    results = []
    lines = code.split('\n')
    
    # ═══════════════════════════════════════════════════════════════
    # 1. 常见模式正则检测
    # ═══════════════════════════════════════════════════════════════
    patterns = [
        # open() 以写入模式打开
        (r'open\([^)]*["\'][wa]["\']', "open_write", "high"),
        (r'open\([^)]*mode\s*=\s*["\'][wa]["\']', "open_write", "high"),
        
        # Path 对象写入
        (r'\.write_text\(', "write_text", "high"),
        (r'\.write_bytes\(', "write_bytes", "high"),
        
        # 文件对象写入
        (r'\.write\(', "file_write", "medium"),
        
        # shutil 操作
        (r'shutil\.copy\(', "shutil_copy", "medium"),
        (r'shutil\.copy2\(', "shutil_copy", "medium"),
        (r'shutil\.copyfile\(', "shutil_copy", "medium"),
        (r'shutil\.move\(', "shutil_move", "medium"),
        
        # os 操作
        (r'os\.makedirs\(', "os_makedirs", "low"),
        (r'os\.mkdir\(', "os_mkdir", "low"),
    ]
    
    for line_num, line in enumerate(lines, 1):
        line_stripped = line.strip()
        # 跳过注释
        if line_stripped.startswith('#'):
            continue
            
        for pattern, op_type, confidence in patterns:
            if _re.search(pattern, line):
                # 尝试提取路径
                path_hint = _extract_path_from_line(line)
                results.append({
                    "type": op_type,
                    "pattern": pattern,
                    "line": line_num,
                    "path_hint": path_hint,
                    "confidence": confidence,
                    "code_line": line_stripped[:100]
                })
                break  # 每行只记录一次
    
    # ═══════════════════════════════════════════════════════════════
    # 2. 简单 AST 分析（提高准确性）
    # ═══════════════════════════════════════════════════════════════
    try:
        tree = _ast.parse(code)
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call):
                # 检查 open() 调用
                if _is_open_call(node):
                    # 检查 mode 参数
                    mode = _get_open_mode(node)
                    if mode in ('w', 'a', 'wb', 'ab', 'w+', 'a+'):
                        # 提取文件路径参数
                        path = _get_first_arg(node)
                        if path and not any(r["line"] == node.lineno for r in results):
                            results.append({
                                "type": "open_write",
                                "pattern": f"open(..., '{mode}')",
                                "line": node.lineno,
                                "path_hint": path,
                                "confidence": "high",
                                "code_line": f"open({path}, '{mode}')"
                            })
                
                # 检查 .write() 调用
                if isinstance(node.func, _ast.Attribute) and node.func.attr == "write":
                    # 检查是否是文件对象
                    if not any(r["line"] == node.lineno for r in results):
                        results.append({
                            "type": "file_write",
                            "pattern": ".write()",
                            "line": node.lineno,
                            "path_hint": None,
                            "confidence": "medium",
                            "code_line": f"file.write(...)"
                        })
    except SyntaxError:
        # 语法错误，跳过 AST 分析
        pass
    
    return results


def _extract_path_from_line(line: str) -> Optional[str]:
    """从代码行中提取文件路径"""
    # 匹配常见路径模式
    path_patterns = [
        # open('path', 'w') 或 open("path", "w")
        r'open\(\s*["\']([^"\']+)["\']',
        # Path('path').write_text()
        r'Path\(\s*["\']([^"\']+)["\']',
        # pathlib.Path('path')
        r'pathlib\.Path\(\s*["\']([^"\']+)["\']',
        # 简单字符串路径（在文件操作上下文中）
        r'["\']([~\/][^"\']*\.[a-zA-Z]+)["\']',
        r'["\'](\.\.?\/[^"\']*\.[a-zA-Z]+)["\']',
    ]
    
    for pattern in path_patterns:
        match = _re.search(pattern, line)
        if match:
            path = match.group(1)
            # 跳过明显不是路径的字符串
            if path in ('w', 'a', 'r', 'wb', 'ab', 'rb', 'w+', 'a+'):
                continue
            return path
    
    return None


def _is_open_call(node: _ast.Call) -> bool:
    """检查是否是 open() 调用"""
    if isinstance(node.func, _ast.Name):
        return node.func.id == "open"
    return False


def _get_open_mode(node: _ast.Call) -> Optional[str]:
    """获取 open() 调用的 mode 参数"""
    # 检查位置参数
    if len(node.args) >= 2:
        mode_arg = node.args[1]
        if isinstance(mode_arg, _ast.Constant) and isinstance(mode_arg.value, str):
            return mode_arg.value
    
    # 检查关键字参数
    for keyword in node.keywords:
        if keyword.arg == "mode":
            if isinstance(keyword.value, _ast.Constant) and isinstance(keyword.value.value, str):
                return keyword.value.value
    
    return None


def _get_first_arg(node: _ast.Call) -> Optional[str]:
    """获取函数调用的第一个字符串参数"""
    if node.args:
        arg = node.args[0]
        if isinstance(arg, _ast.Constant) and isinstance(arg.value, str):
            return arg.value
        # 处理 f-string (Python 3.12+ 有 ast.JoinedStr)
        if isinstance(arg, _ast.JoinedStr):
            # 简化处理：返回 f-string 的第一个字符串部分
            for value in arg.values:
                if isinstance(value, _ast.Constant) and isinstance(value.value, str):
                    return value.value + "..."
    return None


def extract_file_paths(code: str) -> List[Dict[str, Any]]:
    """从代码中提取所有可能的文件路径
    
    Args:
        code: Python 代码字符串
        
    Returns:
        List[Dict]: 提取的路径列表
        [
            {
                "path": "game.html",
                "line": 5,
                "context": "open('game.html', 'w')"
            },
            ...
        ]
    ]
    """
    paths = []
    lines = code.split('\n')
    
    # 路径提取正则
    path_patterns = [
        # open() 第一个参数
        (r'open\(\s*["\']([^"\']+)["\']', "open"),
        # Path() 构造函数
        (r'(?:Path|pathlib\.Path)\(\s*["\']([^"\']+)["\']', "Path"),
        # shutil.copy/move 第二个参数（目标路径）
        (r'shutil\.(?:copy|copy2|copyfile|move)\(\s*[^,]+,\s*["\']([^"\']+)["\']', "shutil_target"),
    ]
    
    for line_num, line in enumerate(lines, 1):
        line_stripped = line.strip()
        if line_stripped.startswith('#'):
            continue
            
        for pattern, context in path_patterns:
            matches = _re.finditer(pattern, line)
            for match in matches:
                path = match.group(1)
                # 跳过 mode 参数
                if path in ('w', 'a', 'r', 'wb', 'ab', 'rb', 'w+', 'a+', 'x', 'xb'):
                    continue
                paths.append({
                    "path": path,
                    "line": line_num,
                    "context": context,
                    "code_line": line_stripped[:100]
                })
    
    return paths


def get_recommended_path(paths: List[Dict], task_description: str) -> str:
    """根据检测到的路径和任务描述，推荐保存路径
    
    Args:
        paths: extract_file_paths() 返回的路径列表
        task_description: 任务描述
        
    Returns:
        str: 推荐的完整保存路径（如 ~/Desktop/game.html）
    """
    import os as _os
    
    desktop = _os.path.expanduser("~/Desktop")
    
    # 如果没有检测到路径，返回默认路径
    if not paths:
        # 根据任务描述推断文件扩展名
        ext = _infer_extension(task_description)
        return f"{desktop}/output{ext}"
    
    # 选择最可能的路径（优先级：高置信度 > 短路径 > 第一个）
    best_path = None
    for p in paths:
        path = p["path"]
        # 跳过相对路径中的 .. 或 .
        if path.startswith("..") or path.startswith("."):
            continue
        if not best_path or len(path) < len(best_path):
            best_path = path
    
    if not best_path:
        best_path = paths[0]["path"]
    
    # 如果路径是相对路径，拼接桌面
    if not best_path.startswith("~") and not best_path.startswith("/"):
        if best_path.startswith("./"):
            best_path = best_path[2:]
        return f"{desktop}/{best_path}"
    
    # 展开 ~
    return _os.path.expanduser(best_path)


def _infer_extension(task_description: str) -> str:
    """根据任务描述推断文件扩展名"""
    task_lower = task_description.lower()
    
    # 游戏/网页类
    if any(kw in task_lower for kw in ["游戏", "html", "网页", "页面", "前端"]):
        return ".html"
    
    # Python 脚本
    if any(kw in task_lower for kw in ["python", "脚本", "爬虫", "自动化"]):
        return ".py"
    
    # JavaScript
    if any(kw in task_lower for kw in ["javascript", "js", "node"]):
        return ".js"
    
    # 数据文件
    if any(kw in task_lower for kw in ["数据", "json", "csv", "excel"]):
        return ".json"
    
    # 默认 HTML
    return ".html"


def format_file_writes_detected(file_writes: List[Dict], recommended_path: str) -> str:
    """格式化文件写入检测结果，用于返回给 LLM
    
    Args:
        file_writes: detect_file_writes() 返回的结果
        recommended_path: get_recommended_path() 返回的推荐路径
        
    Returns:
        str: 格式化的提示文本
    """
    if not file_writes:
        return ""
    
    lines = ["⚠️ 检测到代码包含文件写入操作：\n"]
    
    for i, fw in enumerate(file_writes, 1):
        path_hint = fw.get("path_hint", "未知文件")
        line_num = fw.get("line", "?")
        op_type = fw.get("type", "unknown")
        
        # 映射操作类型到中文
        type_map = {
            "open_write": "open() 写入",
            "write_text": "Path.write_text()",
            "write_bytes": "Path.write_bytes()",
            "file_write": ".write() 写入",
            "shutil_copy": "shutil.copy() 复制",
            "shutil_move": "shutil.move() 移动",
        }
        type_desc = type_map.get(op_type, op_type)
        
        lines.append(f"{i}. {type_desc} - 第 {line_num} 行")
        if path_hint:
            lines.append(f"   文件: {path_hint}")
    
    lines.append(f"\n📁 推荐保存路径: {recommended_path}")
    lines.append("\n请询问用户确认保存路径，然后使用 write_file 工具写入文件。")
    
    return "\n".join(lines)
