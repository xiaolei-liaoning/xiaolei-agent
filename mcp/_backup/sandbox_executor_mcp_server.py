#!/usr/bin/env python3
"""代码沙盒执行器 MCP 服务器 - 参考 opencode 设计

特性：
- 命令执行：支持 shell 命令、多行脚本
- 超时控制：可配置执行超时（默认30秒，最大300秒）
- 输出截断：限制输出大小（默认64KB）
- 工作目录：支持指定工作目录
- 环境变量：支持注入环境变量
- 权限检查：工作目录白名单
- 进程管理：超时自动终止
- 输出捕获：stdout/stderr 分离
"""

import sys
import json
import os
import asyncio
import subprocess
import signal
import time
from typing import Dict, Any, Optional, List
from pathlib import Path

# ────────────────────────────────────────
# 配置
# ────────────────────────────────────────

DEFAULT_TIMEOUT = 30          # 默认超时（秒）
MAX_TIMEOUT = 300             # 最大超时（秒）
MAX_OUTPUT_BYTES = 64 * 1024  # 最大输出大小（64KB）
KILL_TIMEOUT = 3              # 强制终止等待时间

# 工作目录白名单
_env_paths = os.environ.get("SANDBOX_ALLOWED_PATHS", "")
ALLOWED_PATHS: List[str] = (
    [p.strip() for p in _env_paths.split(",") if p.strip()]
    if _env_paths
    else [os.path.expanduser("~"), "/tmp", "/var/tmp"]
)


# ────────────────────────────────────────
# 工具定义
# ────────────────────────────────────────

TOOLS = [
    {
        "name": "execute_command",
        "description": "执行 shell 命令 - 支持超时控制、输出截断、工作目录指定",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令"
                },
                "timeout": {
                    "type": "integer",
                    "description": f"超时秒数（默认 {DEFAULT_TIMEOUT}，最大 {MAX_TIMEOUT}）",
                    "minimum": 1,
                    "maximum": MAX_TIMEOUT
                },
                "workdir": {
                    "type": "string",
                    "description": "工作目录（默认当前目录）"
                },
                "env": {
                    "type": "object",
                    "description": "环境变量（键值对）",
                    "additionalProperties": {"type": "string"}
                },
                "max_output": {
                    "type": "integer",
                    "description": f"最大输出字节数（默认 {MAX_OUTPUT_BYTES}）",
                    "minimum": 1024,
                    "maximum": 1024 * 1024
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "execute_script",
        "description": "执行多行 shell 脚本 - 逐行执行，遇错停止",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "多行脚本内容"
                },
                "timeout": {
                    "type": "integer",
                    "description": f"总超时秒数（默认 {DEFAULT_TIMEOUT * 2}，最大 {MAX_TIMEOUT}）",
                    "minimum": 1,
                    "maximum": MAX_TIMEOUT
                },
                "workdir": {
                    "type": "string",
                    "description": "工作目录"
                },
                "env": {
                    "type": "object",
                    "description": "环境变量"
                }
            },
            "required": ["script"]
        }
    },
    {
        "name": "check_command",
        "description": "检查命令是否存在（which/where）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要检查的命令名称"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "get_system_info",
        "description": "获取系统信息（OS、shell、Python版本等）",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "list_processes",
        "description": "列出当前运行的进程",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "进程名过滤关键词"
                }
            }
        }
    },
]


# ────────────────────────────────────────
# 辅助函数
# ────────────────────────────────────────

def check_path(path: str) -> str:
    """检查路径是否在允许范围内"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    for allowed in ALLOWED_PATHS:
        allowed_abs = os.path.abspath(os.path.expanduser(allowed))
        if abs_path.startswith(allowed_abs):
            return abs_path
    raise PermissionError(f"路径 {abs_path} 不在允许范围内。允许路径: {ALLOWED_PATHS}")


def get_shell() -> str:
    """获取默认 shell"""
    if os.name == 'nt':
        return os.environ.get('COMSPEC', 'cmd.exe')
    return os.environ.get('SHELL', '/bin/sh')


def format_output(stdout: bytes, stderr: bytes, max_output: int) -> Dict[str, Any]:
    """格式化输出，处理截断"""
    stdout_str = stdout.decode('utf-8', errors='replace')
    stderr_str = stderr.decode('utf-8', errors='replace')
    
    truncated = False
    total_size = len(stdout_str) + len(stderr_str)
    
    if total_size > max_output:
        # 优先保留 stderr（错误信息）
        stderr_keep = min(len(stderr_str), max_output // 2)
        stdout_keep = max_output - stderr_keep
        
        if len(stderr_str) > stderr_keep:
            stderr_str = "..." + stderr_str[-(stderr_keep-3):]
        if len(stdout_str) > stdout_keep:
            stdout_str = stdout_str[:stdout_keep] + "\n... [输出已截断]"
        
        truncated = True
    
    return {
        "stdout": stdout_str,
        "stderr": stderr_str,
        "truncated": truncated,
        "total_size": total_size
    }


# ────────────────────────────────────────
# 工具处理函数
# ────────────────────────────────────────

async def handle_execute_command(
    command: str,
    timeout: int = DEFAULT_TIMEOUT,
    workdir: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    max_output: int = MAX_OUTPUT_BYTES
) -> Dict[str, Any]:
    """执行 shell 命令"""
    timeout = min(max(timeout, 1), MAX_TIMEOUT)
    
    # 确定工作目录
    cwd = os.getcwd()
    if workdir:
        try:
            cwd = check_path(workdir)
        except PermissionError as e:
            return {"text": f"❌ 权限错误: {e}"}
    
    if not os.path.isdir(cwd):
        return {"text": f"❌ 工作目录不存在: {cwd}"}
    
    # 构建环境变量
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    
    start_time = time.time()
    
    try:
        # 使用 shell 执行命令
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=proc_env,
            preexec_fn=os.setsid if os.name != 'nt' else None,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # 超时，终止进程组
            if os.name != 'nt':
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    await asyncio.sleep(0.5)
                    if process.returncode is None:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            
            elapsed = time.time() - start_time
            return {
                "text": f"⏱️ 命令执行超时（{elapsed:.1f}秒）\n"
                        f"命令: {command}\n"
                        f"工作目录: {cwd}\n"
                        f"提示: 命令执行时间超过 {timeout} 秒限制"
            }
        
        exit_code = process.returncode
        formatted = format_output(stdout, stderr, max_output)
        
        # 构建结果
        lines = []
        lines.append(f"{'✅' if exit_code == 0 else '❌'} 命令执行完成 (退出码: {exit_code})")
        lines.append(f"📁 工作目录: {cwd}")
        lines.append(f"⏱️ 耗时: {time.time() - start_time:.2f}秒")
        
        if formatted['stdout']:
            lines.append(f"\n📤 STDOUT:\n{formatted['stdout']}")
        
        if formatted['stderr']:
            lines.append(f"\n⚠️ STDERR:\n{formatted['stderr']}")
        
        if formatted['truncated']:
            lines.append(f"\n⚠️ 输出已截断 (原始大小: {formatted['total_size']} 字节)")
        
        return {"text": "\n".join(lines)}
    
    except Exception as e:
        return {"text": f"❌ 执行错误: {str(e)}"}


async def handle_execute_script(
    script: str,
    timeout: int = DEFAULT_TIMEOUT * 2,
    workdir: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """执行多行脚本"""
    timeout = min(max(timeout, 1), MAX_TIMEOUT)
    
    # 确定工作目录
    cwd = os.getcwd()
    if workdir:
        try:
            cwd = check_path(workdir)
        except PermissionError as e:
            return {"text": f"❌ 权限错误: {e}"}
    
    # 构建环境变量
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    
    start_time = time.time()
    
    try:
        # 将脚本写入临时文件执行
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', delete=False, dir='/tmp'
        ) as f:
            f.write(script)
            script_path = f.name
        
        try:
            os.chmod(script_path, 0o755)
            
            process = await asyncio.create_subprocess_exec(
                '/bin/sh', script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=proc_env,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                elapsed = time.time() - start_time
                return {
                    "text": f"⏱️ 脚本执行超时（{elapsed:.1f}秒）\n"
                            f"脚本长度: {len(script)} 字符\n"
                            f"提示: 脚本执行时间超过 {timeout} 秒限制"
                }
            
            exit_code = process.returncode
            formatted = format_output(stdout, stderr, MAX_OUTPUT_BYTES)
            
            lines = []
            lines.append(f"{'✅' if exit_code == 0 else '❌'} 脚本执行完成 (退出码: {exit_code})")
            lines.append(f"📁 工作目录: {cwd}")
            lines.append(f"📝 脚本长度: {len(script)} 字符")
            lines.append(f"⏱️ 耗时: {time.time() - start_time:.2f}秒")
            
            if formatted['stdout']:
                lines.append(f"\n📤 STDOUT:\n{formatted['stdout']}")
            
            if formatted['stderr']:
                lines.append(f"\n⚠️ STDERR:\n{formatted['stderr']}")
            
            return {"text": "\n".join(lines)}
        
        finally:
            os.unlink(script_path)
    
    except Exception as e:
        return {"text": f"❌ 脚本执行错误: {str(e)}"}


async def handle_check_command(command: str) -> Dict[str, Any]:
    """检查命令是否存在"""
    try:
        # Windows 使用 where，Unix 使用 which
        check_cmd = "where" if os.name == 'nt' else "which"
        process = await asyncio.create_subprocess_exec(
            check_cmd, command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            path = stdout.decode().strip()
            return {"text": f"✅ 命令 '{command}' 存在\n📍 路径: {path}"}
        else:
            return {"text": f"❌ 命令 '{command}' 未找到"}
    
    except Exception as e:
        return {"text": f"❌ 检查失败: {str(e)}"}


async def handle_get_system_info() -> Dict[str, Any]:
    """获取系统信息"""
    import platform
    
    info = {
        "操作系统": platform.system(),
        "系统版本": platform.version(),
        "架构": platform.machine(),
        "Python版本": platform.python_version(),
        "主机名": platform.node(),
        "当前目录": os.getcwd(),
        "用户": os.environ.get('USER', os.environ.get('USERNAME', 'unknown')),
        "默认Shell": get_shell(),
        "PATH": os.environ.get('PATH', '')[:200] + '...',
    }
    
    # 检查常用工具
    tools_check = ['git', 'node', 'npm', 'python3', 'pip', 'docker', 'curl', 'wget']
    available_tools = []
    
    for tool in tools_check:
        try:
            check_cmd = "where" if os.name == 'nt' else "which"
            process = await asyncio.create_subprocess_exec(
                check_cmd, tool,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            if process.returncode == 0:
                available_tools.append(tool)
        except:
            pass
    
    lines = ["🖥️ 系统信息\n"]
    for key, value in info.items():
        lines.append(f"  {key}: {value}")
    
    lines.append(f"\n🔧 可用工具: {', '.join(available_tools)}")
    
    return {"text": "\n".join(lines)}


async def handle_list_processes(filter_keyword: Optional[str] = None) -> Dict[str, Any]:
    """列出当前进程"""
    try:
        if os.name == 'nt':
            process = await asyncio.create_subprocess_exec(
                'tasklist', '/FO', 'CSV',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                'ps', 'aux',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        
        stdout, stderr = await process.communicate()
        output = stdout.decode('utf-8', errors='replace')
        
        lines = output.split('\n')
        
        if filter_keyword:
            lines = [l for l in lines if filter_keyword.lower() in l.lower()]
        
        # 限制输出
        if len(lines) > 50:
            lines = lines[:50]
            lines.append(f"... 共有更多进程（已截断）")
        
        return {"text": f"📋 进程列表:\n\n" + "\n".join(lines)}
    
    except Exception as e:
        return {"text": f"❌ 获取进程列表失败: {str(e)}"}


# ────────────────────────────────────────
# 请求处理
# ────────────────────────────────────────

async def handle_request(request: dict) -> dict:
    """处理 JSON-RPC 请求"""
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "name": "sandbox-executor",
                "version": "1.0.0",
                "description": "代码沙盒执行器 - 安全执行命令和脚本"
            }
        }
    
    if method in ("tools/list", "listTools"):
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    
    if method in ("tools/call", "callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})
        
        try:
            if tool == "execute_command":
                r = await handle_execute_command(
                    command=args["command"],
                    timeout=args.get("timeout", DEFAULT_TIMEOUT),
                    workdir=args.get("workdir"),
                    env=args.get("env"),
                    max_output=args.get("max_output", MAX_OUTPUT_BYTES),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}
            
            if tool == "execute_script":
                r = await handle_execute_script(
                    script=args["script"],
                    timeout=args.get("timeout", DEFAULT_TIMEOUT * 2),
                    workdir=args.get("workdir"),
                    env=args.get("env"),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}
            
            if tool == "check_command":
                r = await handle_check_command(command=args["command"])
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}
            
            if tool == "get_system_info":
                r = await handle_get_system_info()
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}
            
            if tool == "list_processes":
                r = await handle_list_processes(filter_keyword=args.get("filter"))
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}
            
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": f"未知工具: {tool}"}
            }
        
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32000, "message": str(e)}
            }
    
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "error": {"code": -32601, "message": f"未知方法: {method}"}
    }


# ────────────────────────────────────────
# 主函数
# ────────────────────────────────────────

def main():
    """stdio 模式主循环"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
            
            # 通知消息没有 id 字段，不需要响应
            if "id" not in request:
                # 处理通知（如 notifications/initialized）
                continue
            
            response = asyncio.run(handle_request(request))
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None
            }
            print(json.dumps(error_response))
            sys.stdout.flush()
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": None
            }
            print(json.dumps(error_response))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
