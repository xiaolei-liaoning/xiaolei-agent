#!/usr/bin/env python3
"""沙盒工具箱 MCP 服务器 - JSON-RPC stdio 协议

基于 Claude Code 工具系统分析进行升级，包含：
- FileReadTool: 设备路径封锁、编码检测、多类型支持、行号输出
- FileWriteTool: 文件历史追踪、git diff、密钥检查
- FileEditTool: 字符串替换（仅首处）、replace_all、CRLF/LF 保持、settings.json 验证
- GlobTool: 100 文件限制、node_modules/.git 排除、相对路径输出
- GrepTool: ripgrep 优先、head_limit=250、上下文行、VCS 排除
- WebFetchTool: URL 抓取转 markdown、内容大小限制
"""

import sys
import json
import os
import re
import stat
import shutil
import fnmatch
import subprocess
import asyncio
import hashlib
import time
import io
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

# 标准工具导入（非 MCP 绕路）
try:
    from core.tools.bash_tool import BashTool, BashResult
    _HAS_BASH_TOOL = True
except ImportError:
    _HAS_BASH_TOOL = False

try:
    from core.tools.text_matcher import TextMatcher, MatchStrategy, DiffVisualizer
    _HAS_TEXT_MATCHER = True
except ImportError:
    _HAS_TEXT_MATCHER = False

try:
    from core.tools.git_ops import GitTool, git_status, git_diff
    _HAS_GIT_TOOL = True
except ImportError:
    _HAS_GIT_TOOL = False

# ────────────────────────────────────────
# 配置
# ────────────────────────────────────────

_env_paths = os.environ.get("SANDBOX_ALLOWED_PATHS", "")
ALLOWED_PATHS: List[str] = (
    [p.strip() for p in _env_paths.split(",") if p.strip()]
    if _env_paths
    else [os.path.expanduser("~"), "/tmp"]
)

BLOCKED_DEVICE_PATHS = [
    "/dev/zero",
    "/dev/urandom",
    "/dev/random",
    "/proc/self/environ",
    "/proc/self/mem",
    "/dev/stdin",
]

MAX_GLOB_RESULTS = 100
MAX_GREP_RESULTS = 250
WEBFETCH_MAX_SIZE = 100_000

# 文件历史：path -> (before, after, timestamp, tool_use_id)
_file_history: dict = {}

# 文件 mtime 缓存：path -> mtime_ns
_file_mtime_cache: dict = {}


# ────────────────────────────────────────
# 工具定义
# ────────────────────────────────────────

TOOLS = [
    # ── 代码编辑工具（Claude Code 级别） ──
    {
        "name": "read_file",
        "description": "读取文件内容 - 支持文本/图片/PDF/ipynb，带设备路径封锁和编码检测",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径"},
                "offset": {"type": "integer", "description": "起始行号（0 开始）"},
                "limit": {"type": "integer", "description": "读取行数"},
                "pages": {"type": "string", "description": "PDF页码范围，如 '1-5'"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "写入文件（覆盖）- 带文件历史追踪和 git diff",
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
        "description": "在文件中查找替换文本（仅替换首次出现）- 支持 replace_all、CRLF/LF 保持",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_string": {"type": "string", "description": "被替换的文本（必须唯一，除非 replace_all=true）"},
                "new_string": {"type": "string", "description": "替换后的文本"},
                "replace_all": {"type": "boolean", "description": "是否替换所有匹配（默认 false）"}
            },
            "required": ["path", "old_string", "new_string"]
        }
    },
    {
        "name": "glob",
        "description": "递归搜索文件 - 最多 100 条结果，自动排除 node_modules/.git",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "glob 模式，如 '**/*.py'"},
                "path": {"type": "string", "description": "搜索根目录（默认当前目录）"}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "grep",
        "description": "在文件中搜索文本 - ripgrep 优先，head_limit=250，支持上下文行",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "搜索模式（正则表达式）"},
                "path": {"type": "string", "description": "搜索路径"},
                "glob": {"type": "string", "description": "文件过滤 glob，如 '*.py'"},
                "output_mode": {"type": "string", "description": "输出模式: content/files_with_matches/count"},
                "context": {"type": "integer", "description": "上下文行数"},
                "-i": {"type": "boolean", "description": "忽略大小写"},
                "head_limit": {"type": "integer", "description": "最大结果数（默认 250）"}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "web_fetch",
        "description": "获取 URL 内容并转为 markdown - HTML 清洗，大小限制 100K",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要获取的 URL"},
                "prompt": {"type": "string", "description": "对内容的特定关注点"}
            },
            "required": ["url"]
        }
    },
    # ── 原有工具 ──
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
        "description": "执行 shell 命令（标准沙盒执行器）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "timeout": {"type": "integer", "description": "超时秒数，默认30"},
                "cwd": {"type": "string", "description": "工作目录（可选）"},
                "env": {"type": "object", "description": "环境变量（可选）"},
                "max_output_chars": {"type": "integer", "description": "最大输出字符数，默认10000"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "run_script",
        "description": "执行多行 shell 脚本（逐行执行，遇错停止）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "多行脚本内容"},
                "timeout": {"type": "integer", "description": "总超时秒数，默认60"},
                "cwd": {"type": "string", "description": "工作目录（可选）"}
            },
            "required": ["script"]
        }
    },
    # ── Git 工作流工具 ──
    {
        "name": "git_status",
        "description": "显示 Git 仓库状态 - 未跟踪文件、修改文件、暂存文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径，默认当前目录"}
            }
        }
    },
    {
        "name": "git_diff",
        "description": "显示 Git 文件差异 - 支持工作区和暂存区差异",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "指定文件列表"},
                "cached": {"type": "boolean", "description": "是否显示暂存区差异"}
            }
        }
    },
    {
        "name": "git_log",
        "description": "显示 Git 提交历史",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径"},
                "count": {"type": "integer", "description": "显示条数，默认10"},
                "branch": {"type": "string", "description": "分支名"}
            }
        }
    },
    {
        "name": "git_branch",
        "description": "列出 Git 分支",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径"},
                "remote": {"type": "boolean", "description": "是否显示远程分支"}
            }
        }
    },
    {
        "name": "git_add",
        "description": "暂存文件到 Git",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "要暂存的文件列表"}
            },
            "required": ["files"]
        }
    },
    {
        "name": "git_commit",
        "description": "提交 Git 暂存区更改",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径"},
                "message": {"type": "string", "description": "提交信息"},
                "add_all": {"type": "boolean", "description": "是否自动暂存所有更改"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "git_push",
        "description": "推送 Git 提交到远程仓库",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径"},
                "remote": {"type": "string", "description": "远程仓库名，默认origin"},
                "branch": {"type": "string", "description": "分支名，默认当前分支"}
            }
        }
    },
    {
        "name": "create_pr",
        "description": "使用 gh CLI 创建 GitHub Pull Request",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径"},
                "title": {"type": "string", "description": "PR 标题"},
                "body": {"type": "string", "description": "PR 描述"},
                "base": {"type": "string", "description": "目标分支，默认main"}
            },
            "required": ["title"]
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


# ────────────────────────────────────────
# 辅助函数
# ────────────────────────────────────────

def check_path(path: str) -> str:
    abs_path = os.path.abspath(os.path.expanduser(path))
    for allowed in ALLOWED_PATHS:
        allowed_abs = os.path.abspath(os.path.expanduser(allowed))
        if abs_path.startswith(allowed_abs):
            return abs_path
    raise PermissionError(f"路径 {abs_path} 不在允许范围内")


def is_blocked_device_path(path: str) -> bool:
    """检查是否为被封锁的设备路径"""
    try:
        resolved = os.path.realpath(path)
    except OSError:
        return False
    for blocked in BLOCKED_DEVICE_PATHS:
        if resolved == blocked or resolved.startswith(blocked):
            return True
    return False


def detect_encoding(file_path: str) -> str:
    """检测文件编码 - BOM 检测 + UTF-8 启发式"""
    try:
        with open(file_path, "rb") as f:
            head = f.read(8192)
    except OSError:
        return "utf-8"

    # BOM 检测
    if head[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    if head[:2] == b"\xff\xfe":
        return "utf-16le"
    if head[:2] == b"\xfe\xff":
        return "utf-16be"

    # 尝试 UTF-8 解码
    try:
        head.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def detect_line_ending(content: str) -> str:
    """检测行尾风格"""
    crlf_count = content.count("\r\n")
    lf_count = content.count("\n") - crlf_count
    return "crlf" if crlf_count > lf_count else "lf"


def normalize_line_endings(content: str, original_ending: str) -> str:
    """保持原始行尾风格"""
    if original_ending == "crlf":
        return content.replace("\r\n", "\n").replace("\n", "\r\n")
    return content.replace("\r\n", "\n")


def format_with_line_numbers(lines: List[str], offset: int = 0) -> str:
    """带行号格式化输出"""
    result = []
    pad = len(str(offset + len(lines)))
    for i, line in enumerate(lines, start=1 + offset):
        result.append(f"{i:>{pad}}\t{line}")
    return "".join(result)


def compute_git_diff(file_path: str, old_content: str, new_content: str) -> str:
    """计算 git diff（如果文件在 git 仓库中）"""
    try:
        cwd = os.path.dirname(os.path.abspath(file_path))
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=cwd, capture_output=True, timeout=3, check=True,
        )
        result = subprocess.run(
            ["git", "diff", "--no-color", "--", file_path],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        return result.stdout[:2000]
    except Exception:
        return ""


def detect_secrets(content: str) -> List[str]:
    """检测内容中的敏感信息"""
    secrets = []
    patterns = [
        (r"ANTHROPIC_API_KEY", "Anthropic API Key"),
        (r"OPENAI_API_KEY", "OpenAI API Key"),
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI-style API Key"),
    ]
    for pat, name in patterns:
        if re.search(pat, content, re.IGNORECASE):
            secrets.append(name)
    return secrets


# ────────────────────────────────────────
# 工具处理函数
# ────────────────────────────────────────

async def handle_read_file(path: str, offset: int = 0, limit: Optional[int] = None,
                           pages: Optional[str] = None) -> dict:
    """FileReadTool - 带设备路径封锁、编码检测、多类型支持"""
    path = check_path(path)

    if is_blocked_device_path(path):
        return {"text": f"错误：路径 {path} 被封锁（设备文件或敏感路径）"}

    # 检查是否为图片
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    ext = os.path.splitext(path)[1].lower()
    if ext in image_exts:
        try:
            import base64
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return {"text": f"图片文件: {path} (base64)\n数据: data:image/{ext[1:]};base64,{b64[:5000]}..."}
        except Exception as e:
            return {"text": f"图片读取错误: {e}"}

    # 检查是否为 PDF
    if ext == ".pdf":
        try:
            import importlib
            if importlib.util.find_spec("PyPDF2") or importlib.util.find_spec("pypdf"):
                PdfReader = None
                try:
                    from PyPDF2 import PdfReader
                except ImportError:
                    from pypdf import PdfReader
                reader = PdfReader(path)
                page_count = len(reader.pages)
                if pages:
                    parts = pages.split("-")
                    start = max(0, int(parts[0]) - 1)
                    end = min(page_count, int(parts[1])) if len(parts) > 1 else start + 1
                else:
                    start, end = 0, min(page_count, 20)
                text = ""
                for i in range(start, end):
                    text += f"--- 第 {i + 1} 页 ---\n{reader.pages[i].extract_text()}\n"
                return {"text": f"📄 PDF: {path} ({page_count} 页, 显示 {start + 1}-{end})\n\n{text}"}
            else:
                size = os.path.getsize(path)
                return {"text": f"📄 PDF: {path} ({size} 字节)\n请安装 PyPDF2 以查看内容: pip install PyPDF2"}
        except Exception as e:
            return {"text": f"PDF 读取错误: {e}"}

    # 检查是否为 Jupyter Notebook
    if ext == ".ipynb":
        try:
            with open(path, "r", encoding="utf-8") as f:
                nb = json.load(f)
            cells = nb.get("cells", [])
            lines = [f"📓 Notebook: {path} ({len(cells)} 个 cell)", ""]
            for i, cell in enumerate(cells):
                ct = cell.get("cell_type", "code")
                src = "".join(cell.get("source", []))
                lines.append(f"[{i}] {'📝' if ct == 'markdown' else '💻'} {ct}:")
                lines.append(src[:500])
                if len(src) > 500:
                    lines.append("... (截断)")
                lines.append("")
            return {"text": "\n".join(lines)}
        except Exception as e:
            return {"text": f"Notebook 读取错误: {e}"}

    # 普通文本文件
    encoding = detect_encoding(path)
    try:
        with open(path, "r", encoding=encoding) as f:
            all_lines = f.readlines()
    except UnicodeDecodeError:
        size = os.path.getsize(path)
        return {"text": f"二进制文件: {path} ({size} 字节), 编码: {encoding}"}

    selected = all_lines[offset:]
    if limit is not None:
        selected = selected[:limit]

    header = f"📄 {path} ({len(all_lines)} 行, 编码: {encoding})"
    body = format_with_line_numbers(selected, offset)
    return {"text": f"{header}\n{body}"}


async def handle_write_file(path: str, content: str) -> dict:
    """FileWriteTool - 带文件历史追踪、git diff、密钥检查"""
    path = check_path(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 密钥检查
    secrets = detect_secrets(content)
    if secrets:
        return {"text": f"错误：检测到敏感信息: {', '.join(secrets)}"}

    # 记录写入前的状态
    before = ""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                before = f.read()
        except Exception:
            pass

    # 写入
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    # 记录文件历史
    _file_history[path] = {
        "before": before,
        "after": content,
        "timestamp": time.time(),
        "tool_use": f"write:{int(time.time())}",
    }

    # 计算 git diff
    diff = compute_git_diff(path, before, content)

    # 缓存 mtime
    try:
        _file_mtime_cache[path] = os.stat(path).st_mtime_ns
    except OSError:
        pass

    text = f"✅ 已写入 {path} ({len(content)} 字符)"

    # 变更摘要
    if _HAS_TEXT_MATCHER and before:
        summary = DiffVisualizer.format_change_summary(before, content)
        text += f"\n📊 {summary}"
    elif before:
        old_lines = before.splitlines()
        new_lines = content.splitlines()
        added = len(new_lines) - len(old_lines)
        text += f"\n📊 变更: {len(old_lines)} 行 → {len(new_lines)} 行 ({'+' if added >= 0 else ''}{added})"

    if diff:
        text += f"\n--- Git Diff ---\n{diff}"
    return {"text": text}


async def handle_edit_file(path: str, old_string: str, new_string: str,
                           replace_all: bool = False) -> dict:
    """FileEditTool - 带语义匹配的多策略编辑"""
    path = check_path(path)

    if not os.path.exists(path):
        return {"text": f"错误：文件不存在 {path}"}

    # 检查文件是否被外部修改
    try:
        current_mtime = os.stat(path).st_mtime_ns
        cached_mtime = _file_mtime_cache.get(path)
        if cached_mtime and current_mtime != cached_mtime:
            return {"text": f"警告：文件 {path} 自读取后被外部修改，跳过编辑以免覆盖用户手动更改"}
    except OSError:
        pass

    with open(path, "r", encoding="utf-8") as f:
        old_content = f.read()

    # 语义匹配（TextMatcher 多策略回退）
    match = None
    if _HAS_TEXT_MATCHER:
        matcher = TextMatcher()
        # 精确匹配
        exact_matches = await matcher.find_match(old_content, old_string, MatchStrategy.EXACT)
        if len(exact_matches) == 1:
            match = exact_matches[0]
        elif len(exact_matches) == 0:
            # 自动回退
            match = await matcher.find_best_match(old_content, old_string, auto_escalate=True)
        else:
            # 多匹配 + replace_all
            if replace_all:
                match = exact_matches[0]  # 用第一个，下面的 replace_all 会走旧路径
            else:
                return {"text": f"错误：找到 {len(exact_matches)} 处精确匹配，请提供更多上下文使其唯一，或设置 replace_all=true"}
    else:
        # 无 TextMatcher：保留旧行为
        if old_string not in old_content:
            return {"text": f"错误：在文件中未找到匹配文本，请检查要替换的文本是否精确匹配（包括缩进和空格）"}
        if not replace_all and old_content.count(old_string) > 1:
            return {"text": f"错误：找到 {old_content.count(old_string)} 处匹配，请提供更多上下文使其唯一，或设置 replace_all=true"}
        # 构造一个简单 MatchResult 模拟
        from types import SimpleNamespace
        match = SimpleNamespace(start_pos=old_content.find(old_string), end_pos=old_content.find(old_string)+len(old_string),
                                confidence=1.0, strategy_used="exact", matched_text=old_string, message="")

    if match is None:
        # TextMatcher 也未找到
        return {"text": "错误：未找到匹配文本。请检查目标文本是否正确，或使用 write_file 写入整个文件。"}

    if match.start_pos == -1 and match.message:
        # TextMatcher 返回了建议消息（未找到但有提示）
        return {"text": f"错误：{match.message}"}

    # 检测并保持行尾风格
    original_ending = detect_line_ending(old_content)

    # 执行替换
    if replace_all:
        # replace_all 必须用原始 old_string 才能全局替换
        if not old_string:
            count = 1
            new_content = old_content
        elif old_string in old_content:
            new_content = old_content.replace(old_string, new_string)
            count = old_content.count(old_string)
        else:
            # replace_all 但 old_string 不在内容中（模糊匹配场景）
            matched_text = match.matched_text if _HAS_TEXT_MATCHER and match.matched_text else old_string
            new_content = old_content.replace(matched_text, new_string)
            count = old_content.count(matched_text) if matched_text else 1
    else:
        # 使用匹配到的精确文本进行替换
        matched_text = match.matched_text if _HAS_TEXT_MATCHER and match.matched_text else old_string
        new_content = old_content.replace(matched_text, new_string, 1)
        count = 1

    # 保持行尾风格
    new_content = normalize_line_endings(new_content, original_ending)

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # 记录文件历史
    _file_history[path] = {
        "before": old_content,
        "after": new_content,
        "timestamp": time.time(),
        "tool_use": f"edit:{int(time.time())}",
    }

    # 更新 mtime 缓存
    try:
        _file_mtime_cache[path] = os.stat(path).st_mtime_ns
    except OSError:
        pass

    # 对 settings.json 进行额外验证
    if path.endswith("settings.json") or path.endswith("settings.local.json"):
        try:
            json.loads(new_content)
        except json.JSONDecodeError as e:
            return {"text": f"⚠️ 已替换 {count} 处，但 settings.json 格式无效: {e}"}

    # 构建响应
    parts = [f"✅ 已替换 {count} 处: {path}"]

    # 匹配策略说明
    if _HAS_TEXT_MATCHER and hasattr(match, 'strategy_used') and match.strategy_used != MatchStrategy.EXACT:
        if match.message:
            parts.append(f"📝 提示: {match.message}")
        elif hasattr(match, 'strategy_used'):
            parts.append(f"📝 匹配策略: {match.strategy_used.value}")

    # DiffVisualizer 语义摘要
    if _HAS_TEXT_MATCHER:
        summary = DiffVisualizer.format_change_summary(old_content, new_content)
        parts.append(f"📊 {summary}")

    # git diff
    diff = compute_git_diff(path, old_content, new_content)
    if diff:
        parts.append(f"--- Git Diff ---\n{diff}")

    return {"text": "\n".join(parts)}


async def handle_glob(pattern: str, path: str = ".") -> dict:
    """GlobTool - 最多 100 条结果，排除 node_modules/.git"""
    root = os.path.expanduser(path)
    if not os.path.isdir(root):
        return {"text": f"错误：无效目录 {root}"}

    IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".svn", ".hg", ".bzr", ".venv", ".idea"}

    matches = []
    try:
        import glob as glob_module
        full_pattern = os.path.join(root, pattern.lstrip("/"))
        for p in glob_module.glob(full_pattern, recursive=True):
            if os.path.isfile(p):
                rel = os.path.relpath(p, root)
                parts = rel.split(os.sep)
                if not any(part in IGNORE_DIRS for part in parts[:-1]):
                    matches.append(rel)
                    if len(matches) >= MAX_GLOB_RESULTS:
                        break
    except Exception:
        for root_dir, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for fname in files:
                rel_dir = os.path.relpath(root_dir, root)
                rel_path = os.path.join(rel_dir, fname) if rel_dir != "." else fname
                if fnmatch.fnmatch(rel_path, pattern):
                    matches.append(rel_path)
                    if len(matches) >= MAX_GLOB_RESULTS:
                        break
            if len(matches) >= MAX_GLOB_RESULTS:
                break

    if not matches:
        return {"text": f"未找到匹配文件: {pattern} (在 {root})"}

    # 按修改时间排序（最新优先）
    matches_with_mtime = []
    for m in matches:
        full = os.path.join(root, m)
        try:
            mt = os.path.getmtime(full)
            matches_with_mtime.append((mt, m))
        except OSError:
            matches_with_mtime.append((0, m))
    matches_with_mtime.sort(key=lambda x: -x[0])
    sorted_rel = [m[1] for m in matches_with_mtime]

    text = f"🔍 找到 {len(matches)} 个文件 (最多显示 {MAX_GLOB_RESULTS}):\n"
    text += "\n".join(sorted_rel[:MAX_GLOB_RESULTS])
    if len(matches) > MAX_GLOB_RESULTS:
        text += f"\n... 还有 {len(matches) - MAX_GLOB_RESULTS} 个文件未显示"
    return {"text": text}


async def handle_grep(pattern: str, path: str = ".", glob: Optional[str] = None,
                      output_mode: str = "content", context: Optional[int] = None,
                      case_insensitive: bool = False,
                      head_limit: Optional[int] = None) -> dict:
    """GrepTool - ripgrep 优先，vcs 排除，上下文行"""
    root = os.path.expanduser(path) if path else "."
    limit = head_limit or MAX_GREP_RESULTS

    rg_path = shutil.which("rg")
    if rg_path:
        try:
            args = ["--json", "--no-heading"]
            if case_insensitive:
                args.append("-i")
            if glob:
                args.extend(["--glob", glob])
            if context is not None:
                args.extend(["-C", str(context)])
            args.extend(["--glob", "!.git", "--glob", "!.svn", "--glob", "!.hg",
                         "--glob", "!.bzr", "--glob", "!.jj"])
            args.extend(["--max-count", str(limit)])
            args.append(pattern)
            args.append(root)

            proc = await asyncio.create_subprocess_exec(
                rg_path, *args,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode not in (0, 1):
                raise RuntimeError(f"rg 退出码 {proc.returncode}: {stderr.decode()}")

            if not stdout:
                return {"text": "未找到匹配"}

            matches = []
            file_count = set()
            for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") == "match":
                    data = entry.get("data", {})
                    fpath = data.get("path", {}).get("text", "")
                    line_num = data.get("line_number", 0)
                    sub = data.get("lines", {}).get("text", "").rstrip("\n")
                    file_count.add(fpath)
                    matches.append(f"{fpath}:{line_num}: {sub}")

            if output_mode == "files_with_matches":
                text = "\n".join(sorted(file_count)[:limit])
            elif output_mode == "count":
                text = f"匹配文件数: {len(file_count)}"
            else:
                text = "\n".join(matches[:limit])

            if len(matches) > limit:
                text += f"\n... 还有 {len(matches) - limit} 条结果"
            return {"text": text}

        except Exception:
            pass

    # 回退：os.walk + 逐行匹配
    IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".svn", ".hg", ".bzr", ".jj"}

    matches = []
    file_count = set()
    try:
        for root_dir, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for fname in files:
                if glob and not fnmatch.fnmatch(fname, glob):
                    continue
                fpath = os.path.join(root_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if case_insensitive:
                                matched = re.search(pattern, line, re.IGNORECASE)
                            else:
                                matched = re.search(pattern, line)
                            if matched:
                                file_count.add(fpath)
                                if output_mode in ("files_with_matches", "count"):
                                    break
                                matches.append(f"{fpath}:{i}: {line.rstrip()[:200]}")
                                if len(matches) >= limit:
                                    break
                        if matches and len(matches) >= limit:
                            break
                except Exception:
                    continue
            if matches and len(matches) >= limit:
                break
    except Exception:
        pass

    if output_mode == "files_with_matches":
        text = "\n".join(sorted(file_count)[:limit]) if file_count else "未找到匹配"
    elif output_mode == "count":
        text = f"匹配文件数: {len(file_count)}" if file_count else "未找到匹配"
    else:
        text = "\n".join(matches[:limit]) if matches else "未找到匹配"

    if len(matches) > limit:
        text += f"\n... 还有 {len(matches) - limit} 条结果"
    return {"text": text}


async def handle_web_fetch(url: str, prompt: Optional[str] = None) -> dict:
    """WebFetchTool - URL 抓取转 markdown，大小限制"""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SandboxTools/1.0)",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
    except Exception:
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-sSL", "--max-time", "15", url,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
            if proc.returncode != 0:
                return {"text": f"URL 获取失败: {stderr.decode()[:500]}"}
            content = stdout
        except Exception as e2:
            return {"text": f"URL 获取失败: {e2}"}

    text = content.decode("utf-8", errors="replace")

    # 简单 HTML 清洗
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) > WEBFETCH_MAX_SIZE:
        text = text[:WEBFETCH_MAX_SIZE] + "\n\n[内容已截断]"

    result = f"📄 {url}\n\n" + text
    if prompt:
        result = f"查询: {prompt}\n来源: {url}\n\n" + text
    return {"text": result}


# ────────────────────────────────────────
# 请求处理
# ────────────────────────────────────────

async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "sandbox-tools-mcp", "version": "2.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        try:
            # ── 升级后的代码编辑工具 ──
            if tool == "read_file":
                r = await handle_read_file(
                    path=args["path"],
                    offset=args.get("offset", 0),
                    limit=args.get("limit"),
                    pages=args.get("pages"),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}

            if tool == "write_file":
                r = await handle_write_file(
                    path=args["path"],
                    content=args["content"],
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}

            if tool == "edit_file":
                r = await handle_edit_file(
                    path=args["path"],
                    old_string=args["old_string"],
                    new_string=args["new_string"],
                    replace_all=args.get("replace_all", False),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}

            if tool == "glob":
                r = await handle_glob(
                    pattern=args["pattern"],
                    path=args.get("path", "."),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}

            if tool == "grep":
                r = await handle_grep(
                    pattern=args["pattern"],
                    path=args.get("path", "."),
                    glob=args.get("glob"),
                    output_mode=args.get("output_mode", "content"),
                    context=args.get("context"),
                    case_insensitive=args.get("-i", False),
                    head_limit=args.get("head_limit", MAX_GREP_RESULTS),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}

            if tool == "web_fetch":
                r = await handle_web_fetch(
                    url=args["url"],
                    prompt=args.get("prompt"),
                )
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": r["text"]}]}}

            # ── 原有工具 ──
            if tool == "append_file":
                path = check_path(args["path"])
                with open(path, "a", encoding="utf-8") as f:
                    f.write(args["content"])
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"✅ 已追加到 {path}"}]}}

            if tool == "list_dir":
                path = os.path.expanduser(args.get("path", "."))
                if not os.path.isdir(path):
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"错误：无效目录 {path}"}]}}
                items = sorted(os.listdir(path))
                dirs = [d for d in items if os.path.isdir(os.path.join(path, d)) and not d.startswith(".")]
                files = [f for f in items if not os.path.isdir(os.path.join(path, f)) and not f.startswith(".")]
                lines = [f"📂 {path}"]
                if dirs:
                    lines.append(f"📁 目录 ({len(dirs)}):\n" + "\n".join(f"  {d}" for d in dirs[:30]))
                if files:
                    lines.append(f"📄 文件 ({len(files)}):\n" + "\n".join(f"  {f}" for f in files[:30]))
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "\n".join(lines)}]}}

            if tool == "mkdir":
                p = check_path(args["path"])
                os.makedirs(p, exist_ok=True)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"✅ 已创建目录 {p}"}]}}

            if tool == "remove":
                p = check_path(args["path"])
                if os.path.isdir(p):
                    if args.get("recursive"):
                        shutil.rmtree(p)
                    else:
                        os.rmdir(p)
                else:
                    os.remove(p)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"✅ 已删除 {p}"}]}}

            if tool == "move":
                src = check_path(args["src"])
                dst = check_path(args["dst"])
                shutil.move(src, dst)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"✅ 已移动 {src} → {dst}"}]}}

            if tool == "copy":
                src = check_path(args["src"])
                dst = check_path(args["dst"])
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"✅ 已复制 {src} → {dst}"}]}}

            if tool == "head":
                path = check_path(args["path"])
                n = args.get("n", 10)
                with open(path, "r", encoding=detect_encoding(path)) as f:
                    lines = [next(f) for _ in range(int(n))]
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "".join(lines)}]}}

            if tool == "tail":
                path = check_path(args["path"])
                n = args.get("n", 10)
                with open(path, "r", encoding=detect_encoding(path)) as f:
                    lines = f.readlines()
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "".join(lines[-int(n):])}]}}

            if tool == "run_command":
                cmd = args["command"]
                timeout = args.get("timeout", 30)
                cwd = args.get("cwd")
                env = args.get("env")
                max_chars = args.get("max_output_chars", 10000)

                if _HAS_BASH_TOOL:
                    bash = BashTool(allowed_paths=ALLOWED_PATHS)
                    result = await bash.execute(
                        command=cmd,
                        timeout=timeout,
                        cwd=cwd,
                        env=env,
                        max_output_chars=max_chars,
                    )
                    text = result.stdout
                    if result.stderr:
                        text += "\n[STDERR]\n" + result.stderr
                    if result.timed_out:
                        text += f"\n⚠️ 命令执行超时（{timeout}秒）"
                    if result.truncated:
                        text += f"\n⚠️ 输出已截断（超过 {max_chars} 字符）"
                else:
                    # 回退：直接 subprocess
                    proc = await asyncio.create_subprocess_shell(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                    except asyncio.TimeoutError:
                        proc.kill()
                        return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "错误：命令执行超时"}]}}
                    text = stdout.decode("utf-8", errors="replace")
                    if stderr:
                        text += "\n[STDERR]\n" + stderr.decode("utf-8", errors="replace")
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text[:10000]}]}}

            if tool == "run_script":
                script = args["script"]
                timeout = args.get("timeout", 60)
                cwd = args.get("cwd")
                if _HAS_BASH_TOOL:
                    bash = BashTool(allowed_paths=ALLOWED_PATHS)
                    result = await bash.execute_script(
                        script=script,
                        timeout=timeout,
                        cwd=cwd,
                    )
                    text = result.stdout
                    if result.stderr:
                        text += "\n[STDERR]\n" + result.stderr
                    if result.timed_out:
                        text += f"\n⚠️ 脚本执行超时（{timeout}秒）"
                else:
                    text = "错误：BashTool 不可用，无法执行多行脚本"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text[:10000]}]}}

            # ── Git 工作流工具 ──
            if tool == "git_status":
                repo_path = args.get("path", ".")
                if _HAS_GIT_TOOL:
                    git_tool = GitTool(repo_path)
                    text = await git_tool.status()
                else:
                    text = "错误：GitTool 不可用"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "git_diff":
                repo_path = args.get("path", ".")
                files = args.get("files")
                cached = args.get("cached", False)
                if _HAS_GIT_TOOL:
                    git_tool = GitTool(repo_path)
                    text = await git_tool.diff(files=files, cached=cached)
                else:
                    text = "错误：GitTool 不可用"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "git_log":
                repo_path = args.get("path", ".")
                count = args.get("count", 10)
                branch = args.get("branch")
                if _HAS_GIT_TOOL:
                    git_tool = GitTool(repo_path)
                    text = await git_tool.log(count=count, branch=branch)
                else:
                    text = "错误：GitTool 不可用"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "git_branch":
                repo_path = args.get("path", ".")
                remote = args.get("remote", False)
                if _HAS_GIT_TOOL:
                    git_tool = GitTool(repo_path)
                    text = await git_tool.branch(remote=remote)
                else:
                    text = "错误：GitTool 不可用"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "git_add":
                repo_path = args.get("path", ".")
                files = args.get("files", [])
                if _HAS_GIT_TOOL:
                    git_tool = GitTool(repo_path)
                    text = await git_tool.add(files=files)
                else:
                    text = "错误：GitTool 不可用"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "git_commit":
                repo_path = args.get("path", ".")
                message = args.get("message", "")
                add_all = args.get("add_all", False)
                if _HAS_GIT_TOOL:
                    git_tool = GitTool(repo_path)
                    text = await git_tool.commit(message=message, add_all=add_all)
                else:
                    text = "错误：GitTool 不可用"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "git_push":
                repo_path = args.get("path", ".")
                remote = args.get("remote", "origin")
                branch = args.get("branch")
                if _HAS_GIT_TOOL:
                    git_tool = GitTool(repo_path)
                    text = await git_tool.push(remote=remote, branch=branch)
                else:
                    text = "错误：GitTool 不可用"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "create_pr":
                repo_path = args.get("path", ".")
                title = args.get("title", "")
                body = args.get("body", "")
                base = args.get("base", "main")
                if _HAS_GIT_TOOL:
                    git_tool = GitTool(repo_path)
                    text = await git_tool.create_pr(title=title, body=body, base=base)
                else:
                    text = "错误：GitTool 不可用"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

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
                subprocess.run(
                    ["osascript", "-e", f'display notification "{msg}" with title "{title}"'],
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
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"错误: {e}"}]}}

        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown tool: {tool}"}}

    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}


# ────────────────────────────────────────
# 主循环
# ────────────────────────────────────────

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
