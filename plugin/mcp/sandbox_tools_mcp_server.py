#!/usr/bin/env python3
"""沙盒工具箱 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import os
import re
import stat
import shutil
import fnmatch
import subprocess
import asyncio
from pathlib import Path

ALLOWED_PATHS = [
    os.path.expanduser("~"),
    "/tmp",
]

TOOLS = [
    {
        "name": "read_file",
        "description": "读取文件内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "offset": {"type": "integer", "description": "起始行"},
                "limit": {"type": "integer", "description": "读取行数"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "写入文件（覆盖）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "写入内容"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "edit_file",
        "description": "在文件中查找替换文本",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_string": {"type": "string", "description": "被替换的文本"},
                "new_string": {"type": "string", "description": "替换后的文本"}
            },
            "required": ["path", "old_string", "new_string"]
        }
    },
    {
        "name": "append_file",
        "description": "追加内容到文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "追加内容"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_dir",
        "description": "列出目录内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径，默认当前目录"}
            }
        }
    },
    {
        "name": "mkdir",
        "description": "创建目录",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "remove",
        "description": "删除文件或目录",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "路径"},
                "recursive": {"type": "boolean", "description": "是否递归删除目录"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "move",
        "description": "移动/重命名文件或目录",
        "inputSchema": {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源路径"},
                "dst": {"type": "string", "description": "目标路径"}
            },
            "required": ["src", "dst"]
        }
    },
    {
        "name": "copy",
        "description": "复制文件或目录",
        "inputSchema": {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源路径"},
                "dst": {"type": "string", "description": "目标路径"}
            },
            "required": ["src", "dst"]
        }
    },
    {
        "name": "grep",
        "description": "在文件中搜索文本",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "搜索模式"},
                "path": {"type": "string", "description": "搜索路径"},
                "pattern_type": {"type": "string", "description": "模式类型: text/regex, 默认text"}
            },
            "required": ["pattern", "path"]
        }
    },
    {
        "name": "find_files",
        "description": "查找文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "搜索起始路径"},
                "pattern": {"type": "string", "description": "文件通配符模式，如 *.py"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "head",
        "description": "查看文件前N行",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "n": {"type": "integer", "description": "行数，默认10"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "tail",
        "description": "查看文件后N行",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "n": {"type": "integer", "description": "行数，默认10"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "run_command",
        "description": "执行 shell 命令",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "timeout": {"type": "integer", "description": "超时秒数，默认30"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "macos_info",
        "description": "获取 macOS 系统信息",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "macos_open_app",
        "description": "打开 macOS 应用程序",
        "inputSchema": {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "应用名称，如 Safari, 微信"}
            },
            "required": ["app"]
        }
    },
    {
        "name": "macos_notification",
        "description": "发送 macOS 系统通知",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "通知标题"},
                "message": {"type": "string", "description": "通知内容"}
            },
            "required": ["title", "message"]
        }
    },
    {
        "name": "macos_screenshot",
        "description": "截取 macOS 屏幕截图",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "保存路径（可选）"}
            }
        }
    },
    {
        "name": "macos_clipboard",
        "description": "获取 macOS 剪贴板内容",
        "inputSchema": {"type": "object", "properties": {}}
    },
]


def check_path(path):
    abs_path = os.path.abspath(os.path.expanduser(path))
    for allowed in ALLOWED_PATHS:
        allowed_abs = os.path.abspath(os.path.expanduser(allowed))
        if abs_path.startswith(allowed_abs):
            return abs_path
    raise PermissionError(f"路径 {abs_path} 不在允许范围内")


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "sandbox-tools-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        try:
            if tool == "read_file":
                path = check_path(args["path"])
                offset = args.get("offset", 0)
                limit = args.get("limit") or None
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                selected = lines[offset:offset + limit] if limit else lines[offset:]
                text = ''.join(selected)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "write_file":
                path = check_path(args["path"])
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(args["content"])
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已写入 {path}"}]}}

            if tool == "edit_file":
                path = check_path(args["path"])
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if args["old_string"] not in content:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "未找到匹配文本"}]}}
                content = content.replace(args["old_string"], args["new_string"])
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已编辑 {path}"}]}}

            if tool == "append_file":
                path = check_path(args["path"])
                with open(path, 'a', encoding='utf-8') as f:
                    f.write(args["content"])
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已追加到 {path}"}]}}

            if tool == "list_dir":
                path = os.path.expanduser(args.get("path", "."))
                if not os.path.isdir(path):
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"无效目录: {path}"}]}}
                items = sorted(os.listdir(path))
                dirs = [d for d in items if os.path.isdir(os.path.join(path, d)) and not d.startswith('.')]
                files = [f for f in items if not os.path.isdir(os.path.join(path, f)) and not f.startswith('.')]
                lines = [f"📂 {path}"]
                if dirs:
                    lines.append(f"📁 目录 ({len(dirs)}):\n" + '\n'.join(f'  {d}' for d in dirs[:30]))
                if files:
                    lines.append(f"📄 文件 ({len(files)}):\n" + '\n'.join(f'  {f}' for f in files[:30]))
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": '\n'.join(lines)}]}}

            if tool == "mkdir":
                p = check_path(args["path"])
                os.makedirs(p, exist_ok=True)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已创建目录 {p}"}]}}

            if tool == "remove":
                p = check_path(args["path"])
                if os.path.isdir(p):
                    if args.get("recursive"):
                        shutil.rmtree(p)
                    else:
                        os.rmdir(p)
                else:
                    os.remove(p)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已删除 {p}"}]}}

            if tool == "move":
                src = check_path(args["src"])
                dst = check_path(args["dst"])
                shutil.move(src, dst)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已移动 {src} → {dst}"}]}}

            if tool == "copy":
                src = check_path(args["src"])
                dst = check_path(args["dst"])
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已复制 {src} → {dst}"}]}}

            if tool == "grep":
                pattern = args["pattern"]
                path = args["path"]
                ptype = args.get("pattern_type", "text")
                results = []
                for root, dirs, files in os.walk(path):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        try:
                            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                                for i, line in enumerate(f, 1):
                                    if ptype == "regex":
                                        if re.search(pattern, line):
                                            results.append(f"{fpath}:{i}: {line.rstrip()[:200]}")
                                    else:
                                        if pattern in line:
                                            results.append(f"{fpath}:{i}: {line.rstrip()[:200]}")
                        except Exception:
                            continue
                text = '\n'.join(results[:100]) if results else "未找到匹配"
                extra = f"\n... 还有 {len(results) - 100} 条" if len(results) > 100 else ""
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text + extra}]}}

            if tool == "find_files":
                path = args["path"]
                pattern = args.get("pattern", "*")
                matches = []
                for root, dirs, files in os.walk(path):
                    for fname in files:
                        if fnmatch.fnmatch(fname, pattern):
                            matches.append(os.path.join(root, fname))
                text = '\n'.join(matches[:100]) if matches else "未找到匹配文件"
                extra = f"\n... 还有 {len(matches) - 100} 个" if len(matches) > 100 else ""
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text + extra}]}}

            if tool == "head":
                path = check_path(args["path"])
                n = args.get("n", 10)
                with open(path, 'r', encoding='utf-8') as f:
                    lines = [next(f) for _ in range(int(n))]
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": ''.join(lines)}]}}

            if tool == "tail":
                path = check_path(args["path"])
                n = args.get("n", 10)
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": ''.join(lines[-int(n):])}]}}

            if tool == "run_command":
                cmd = args["command"]
                timeout = args.get("timeout", 30)
                proc = await asyncio.create_subprocess_shell(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                except asyncio.TimeoutError:
                    proc.kill()
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "命令执行超时"}]}}
                text = stdout.decode('utf-8', errors='replace')
                if stderr:
                    text += "\n[STDERR]\n" + stderr.decode('utf-8', errors='replace')
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text[:5000]}]}}

            if tool == "macos_info":
                info = f"系统: {os.uname().sysname} {os.uname().release}\n主机: {os.uname().nodename}\n架构: {os.uname().machine}"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": info}]}}

            if tool == "macos_open_app":
                app = args["app"]
                subprocess.run(["open", "-a", app], check=False, timeout=10)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已打开应用: {app}"}]}}

            if tool == "macos_notification":
                title = args["title"]
                msg = args["message"]
                subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}"'],
                               check=False, timeout=5)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"通知已发送: {title}"}]}}

            if tool == "macos_screenshot":
                path = args.get("path", os.path.expanduser("~/Desktop/screenshot.png"))
                subprocess.run(["screencapture", path], check=False, timeout=10)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"截图已保存: {path}"}]}}

            if tool == "macos_clipboard":
                proc = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": proc.stdout[:2000] or "(空)"}]}}

        except PermissionError as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"权限错误: {e}"}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"错误: {str(e)}"}]}}

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
