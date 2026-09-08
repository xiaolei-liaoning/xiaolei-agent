#!/usr/bin/env python3
"""
文件操作MCP服务器 - 使用JSON-RPC协议
"""

import sys
import json
import os
from pathlib import Path
import asyncio

# 导入沙盒路径检查（复用已有的安全逻辑）
try:
    from .sandbox_tools_mcp_server import check_path
except ImportError:
    # 兜底：如果导入失败，定义最小检查
    def check_path(path: str) -> str:
        abs_path = os.path.abspath(os.path.expanduser(path))
        # 仅允许当前工作目录及其子目录
        cwd = os.path.abspath(os.getcwd())
        if abs_path == cwd or abs_path.startswith(cwd + os.sep):
            return abs_path
        raise PermissionError(f"路径 {abs_path} 不在允许范围内")


# 可用工具列表
TOOLS = [
    {
        "name": "list_directory",
        "description": "列出目录内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径（默认当前目录）"}
            },
            "required": []
        }
    },
    {
        "name": "read_file",
        "description": "读取文件内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "encoding": {"type": "string", "description": "编码格式（默认utf-8）"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "写入文件内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
                "append": {"type": "boolean", "description": "是否追加模式（默认false）"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "create_directory",
        "description": "创建目录",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"},
                "recursive": {"type": "boolean", "description": "是否递归创建父目录（默认true）"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "delete_file",
        "description": "删除文件或目录",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录路径"},
                "recursive": {"type": "boolean", "description": "是否递归删除目录（默认false）"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "copy_file",
        "description": "复制文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源文件路径"},
                "destination": {"type": "string", "description": "目标文件路径"}
            },
            "required": ["source", "destination"]
        }
    },
    {
        "name": "file_exists",
        "description": "检查文件或目录是否存在",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "get_file_info",
        "description": "获取文件信息",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "search_files",
        "description": "搜索文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "搜索路径（默认当前目录）"},
                "pattern": {"type": "string", "description": "搜索模式（例如*.py）"}
            },
            "required": ["pattern"]
        }
    }
]


async def handle_request(request):
    """处理JSON-RPC请求"""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id", 1)
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"name": "file-operations-mcp-server", "version": "1.0.0"}
        }
    
    elif method == "listTools":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS}
        }
    
    elif method == "callTool":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        result_text = ""
        
        if tool_name == "list_directory":
            path = arguments.get("path", ".")
            try:
                p = check_path(path)
                p = Path(p)
                if not p.exists():
                    result_text = f"错误：目录不存在: {path}"
                elif not p.is_dir():
                    result_text = f"错误：不是目录: {path}"
                else:
                    items = list(p.iterdir())
                    files = [f for f in items if f.is_file()]
                    dirs = [d for d in items if d.is_dir()]
                    
                    result_parts = [f"📁 目录: {path}", ""]
                    if dirs:
                        result_parts.append("📂 子目录:")
                        for d in sorted(dirs):
                            result_parts.append(f"  {d.name}/")
                    if files:
                        result_parts.append("📄 文件:")
                        for f in sorted(files):
                            result_parts.append(f"  {f.name}")
                    result_text = "\n".join(result_parts)
            except PermissionError as e:
                result_text = f"权限错误: {e}"
            except Exception as e:
                result_text = f"错误：{str(e)}"
            
        elif tool_name == "read_file":
            path = arguments.get("path")
            encoding = arguments.get("encoding", "utf-8")
            try:
                p = check_path(path)
                with open(p, "r", encoding=encoding) as f:
                    content = f.read()
                lines = content.split("\n")
                result_text = f"📄 文件: {path} ({len(lines)} 行)\n\n{content}"
            except PermissionError as e:
                result_text = f"权限错误: {e}"
            except FileNotFoundError:
                result_text = f"错误：文件不存在: {path}"
            except Exception as e:
                result_text = f"错误：{str(e)}"
            
        elif tool_name == "write_file":
            path = arguments.get("path")
            content = arguments.get("content", "")
            append = arguments.get("append", False)
            try:
                p = check_path(path)
                mode = "a" if append else "w"
                with open(p, mode, encoding="utf-8") as f:
                    f.write(content)
                action = "追加到" if append else "写入"
                result_text = f"✅ {action}文件成功: {path}"
            except PermissionError as e:
                result_text = f"权限错误: {e}"
            except Exception as e:
                result_text = f"错误：{str(e)}"
            
        elif tool_name == "create_directory":
            path = arguments.get("path")
            recursive = arguments.get("recursive", True)
            try:
                p = check_path(path)
                p = Path(p)
                p.mkdir(parents=recursive, exist_ok=True)
                result_text = f"✅ 创建目录成功: {path}"
            except PermissionError as e:
                result_text = f"权限错误: {e}"
            except Exception as e:
                result_text = f"错误：{str(e)}"
            
        elif tool_name == "delete_file":
            path = arguments.get("path")
            recursive = arguments.get("recursive", False)
            try:
                p = check_path(path)
                p = Path(p)
                if not p.exists():
                    result_text = f"错误：文件不存在: {path}"
                elif p.is_file():
                    p.unlink()
                    result_text = f"✅ 删除文件成功: {path}"
                elif p.is_dir():
                    if recursive:
                        import shutil
                        shutil.rmtree(p)
                        result_text = f"✅ 删除目录成功: {path}"
                    else:
                        result_text = f"错误：目录不为空，请使用 recursive=true 进行递归删除"
                else:
                    result_text = f"✅ 删除成功: {path}"
            except PermissionError as e:
                result_text = f"权限错误: {e}"
            except Exception as e:
                result_text = f"错误：{str(e)}"
            
        elif tool_name == "copy_file":
            source = arguments.get("source")
            destination = arguments.get("destination")
            try:
                src = check_path(source)
                dst = check_path(destination)
                import shutil
                shutil.copy2(src, dst)
                result_text = f"✅ 复制文件成功: {source} -> {destination}"
            except PermissionError as e:
                result_text = f"权限错误: {e}"
            except Exception as e:
                result_text = f"错误：{str(e)}"
            
        elif tool_name == "file_exists":
            path = arguments.get("path")
            p = Path(path)
            if p.exists():
                if p.is_file():
                    result_text = f"✅ 文件存在: {path}"
                elif p.is_dir():
                    result_text = f"✅ 目录存在: {path}"
                else:
                    result_text = f"✅ 存在: {path}"
            else:
                result_text = f"❌ 不存在: {path}"
            
        elif tool_name == "get_file_info":
            path = arguments.get("path")
            try:
                p = Path(path)
                if not p.exists():
                    result_text = f"错误：文件不存在: {path}"
                else:
                    stat = p.stat()
                    info_parts = [
                        f"📄 文件信息: {path}",
                        f"类型: {'文件' if p.is_file() else '目录' if p.is_dir() else '其他'}",
                        f"大小: {stat.st_size} 字节",
                        f"创建时间: {stat.st_ctime}",
                        f"修改时间: {stat.st_mtime}",
                        f"访问时间: {stat.st_atime}",
                    ]
                    result_text = "\n".join(info_parts)
            except Exception as e:
                result_text = f"错误：{str(e)}"
            
        elif tool_name == "search_files":
            path = arguments.get("path", ".")
            pattern = arguments.get("pattern")
            try:
                p = Path(path)
                if not p.exists():
                    result_text = f"错误：目录不存在: {path}"
                else:
                    files = list(p.rglob(pattern))
                    if files:
                        result_parts = [f"🔍 找到 {len(files)} 个文件:", ""]
                        for f in sorted(files)[:20]:
                            result_parts.append(f"  {f}")
                        if len(files) > 20:
                            result_parts.append(f"  ... (还有 {len(files) - 20} 个文件)")
                        result_text = "\n".join(result_parts)
                    else:
                        result_text = f"未找到匹配文件: {pattern}"
            except Exception as e:
                result_text = f"错误：{str(e)}"
            
        else:
            result_text = f"未知工具: {tool_name}"
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"text": result_text}]}
        }
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"}
        }


async def main():
    """运行文件操作MCP服务器"""
    print("🚀 启动文件操作 MCP 服务器 (JSON-RPC模式)...", file=sys.stderr)
    
    try:
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
                
    except KeyboardInterrupt:
        print("✅ 服务器已停止", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
