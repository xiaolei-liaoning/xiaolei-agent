#!/usr/bin/env python3
"""系统工具箱 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import platform
import os
import shutil
import asyncio
from datetime import datetime

TOOLS = [
    {
        "name": "system_info",
        "description": "获取系统信息（OS/版本/架构/Python版本等）",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "time",
        "description": "获取当前时间",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "date",
        "description": "获取当前日期",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "memory",
        "description": "获取内存使用情况（需psutil）",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "cpu",
        "description": "获取CPU使用信息（需psutil）",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "disk",
        "description": "获取磁盘使用情况",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "calculate",
        "description": "安全表达式计算（仅支持数字和+-*/.()）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "数学表达式，如 2+3*4"}
            },
            "required": ["expression"]
        }
    },
    {
        "name": "file_list",
        "description": "列出指定目录的文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径，默认当前目录"}
            }
        }
    },
    {
        "name": "network",
        "description": "获取网络信息（主机名和本地IP）",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "public_ip",
        "description": "获取公网IP地址",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "process_list",
        "description": "获取进程列表（需psutil）",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "network_speed",
        "description": "获取网络速度（需psutil）",
        "inputSchema": {"type": "object", "properties": {}}
    },
]


def format_size(size_bytes):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(size_bytes) < 1024:
            return f'{size_bytes:.1f}{unit}' if unit != 'B' else f'{size_bytes}{unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f}PB'


def progress_bar(percent, length=20):
    filled = int(length * percent / 100)
    return '█' * filled + '░' * (length - filled)


def get_system_info():
    return {
        "system": platform.system(),
        "version": platform.version(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or '未知',
        "hostname": platform.node(),
        "python_version": platform.python_version(),
        "architecture": platform.architecture()[0],
    }


def get_public_ip():
    try:
        import httpx
        apis = [
            ('https://api.ipify.org?format=json', 'ip'),
            ('https://httpbin.org/ip', 'origin'),
        ]
        for url, key in apis:
            try:
                resp = httpx.get(url, timeout=5)
                resp.raise_for_status()
                ip = resp.json().get(key, '') if key else resp.text.strip()
                if ip:
                    return ip
            except Exception:
                continue
    except Exception:
        pass
    return "无法获取"


def safe_calculate(expression):
    allowed = set('0123456789+-*/.() ')
    for c in expression:
        if c not in allowed:
            return None, f"包含不允许的字符: '{c}'"
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        result = round(float(result), 10) if isinstance(result, float) else result
        return result, None
    except ZeroDivisionError:
        return None, "除零错误"
    except Exception as e:
        return None, str(e)


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "system-toolbox-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        if tool == "system_info":
            info = get_system_info()
            text = (
                f"💻 系统: {info['system']} {info['release']} {info['version']}\n"
                f"架构: {info['machine']} {info['architecture']}\n"
                f"主机: {info['hostname']}\n"
                f"Python: {info['python_version']}\n"
                f"处理器: {info['processor']}"
            )
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

        if tool == "time":
            now = datetime.now().strftime('%H:%M:%S')
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"🕐 当前时间: {now}"}]}}

        if tool == "date":
            now = datetime.now()
            weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"📅 {now.strftime('%Y年%m月%d日')} {weekdays[now.weekday()]}"}]}}

        if tool == "memory":
            try:
                import psutil
                mem = psutil.virtual_memory()
                total = mem.total / 1e9
                used = mem.used / 1e9
                avail = mem.available / 1e9
                bar = progress_bar(mem.percent)
                text = f"🧠 内存: {mem.percent}%\n[{bar}] {used:.1f}GB / {total:.1f}GB\n可用: {avail:.1f}GB"
            except ImportError:
                text = "psutil未安装"
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

        if tool == "cpu":
            try:
                import psutil
                p = psutil.cpu_percent(interval=1)
                phys = psutil.cpu_count(logical=False) or psutil.cpu_count()
                logic = psutil.cpu_count(logical=True)
                freq = psutil.cpu_freq()
                freq_s = f'{freq.current:.0f}MHz' if freq else '未知'
                bar = progress_bar(p)
                text = f"⚡ CPU: {p}%\n[{bar}]\n核心: {phys}物理/{logic}逻辑\n频率: {freq_s}"
            except ImportError:
                text = "psutil未安装"
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

        if tool == "disk":
            try:
                t, u, f = shutil.disk_usage('/')
                p = u / t * 100
                bar = progress_bar(p)
                text = f"💾 磁盘: {p:.1f}%\n[{bar}] {format_size(u)} / {format_size(t)}\n可用: {format_size(f)}"
            except Exception as e:
                text = f"获取磁盘信息失败: {e}"
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

        if tool == "calculate":
            expr = args.get("expression", "")
            if not expr:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "请提供表达式"}]}}
            result, error = safe_calculate(expr)
            if error:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"错误: {error}"}]}}
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"🔢 {expr} = {result}"}]}}

        if tool == "file_list":
            path = args.get("path", ".")
            path = os.path.expanduser(path)
            if not os.path.isdir(path):
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"无效目录: {path}"}]}}
            items = sorted(os.listdir(path))
            files = []
            dirs = []
            for item in items:
                if item.startswith('.'):
                    continue
                fp = os.path.join(path, item)
                if os.path.isdir(fp):
                    dirs.append(item)
                else:
                    size = os.path.getsize(fp)
                    files.append(f'{item} ({format_size(size)})')
            lines = [f"📂 {path}"]
            if dirs:
                lines.append(f"📁 目录 ({len(dirs)}):")
                lines.extend(f'  {d}' for d in dirs[:30])
            if files:
                lines.append(f"📄 文件 ({len(files)}):")
                lines.extend(f'  {f}' for f in files[:30])
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": '\n'.join(lines)}]}}

        if tool == "network":
            import socket
            try:
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
            except Exception:
                hostname = "未知"
                local_ip = "未知"
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"🌐 主机名: {hostname}\n本地IP: {local_ip}"}]}}

        if tool == "public_ip":
            ip = get_public_ip()
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"🌐 公网IP: {ip}"}]}}

        if tool == "process_list":
            try:
                import psutil
                procs = []
                for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                    try:
                        info = p.info
                        procs.append({
                            'PID': info['pid'],
                            '名称': info['name'] or '',
                            'CPU%': f"{info['cpu_percent'] or 0:.1f}",
                            '内存%': f"{info['memory_percent'] or 0:.1f}",
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                procs.sort(key=lambda x: float(x['CPU%']), reverse=True)
                lines = ["📊 进程列表 (Top 20)", f"总进程数: {len(procs)}", '', 'PID  | 名称           | CPU% | 内存%', '-' * 40]
                for p in procs[:20]:
                    lines.append(f"{p['PID']:5d} | {p['名称'][:14]:14s} | {p['CPU%']:5s} | {p['内存%']:6s}")
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": '\n'.join(lines)}]}}
            except ImportError:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "psutil未安装"}]}}

        if tool == "network_speed":
            try:
                import psutil
                import time as ttime
                n1 = psutil.net_io_counters()
                ttime.sleep(1)
                n2 = psutil.net_io_counters()
                up = format_size(n2.bytes_sent - n1.bytes_sent) + '/s'
                down = format_size(n2.bytes_recv - n1.bytes_recv) + '/s'
                text = f"📶 网络速度\n上传: {up}\n下载: {down}"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}
            except ImportError:
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "psutil未安装"}]}}

        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown tool: {tool}"}}

    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}


async def main():
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            request = json.loads(line.strip())
            response = await handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "id": 0, "error": {"code": -32700, "message": "Parse error"}}))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "id": 0, "error": {"code": -32603, "message": str(e)}}))
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
