"""V1ToolRegistry — V1 独立工具注册表（11 内置工具 + MCP 代理）

与 V2 ToolRegistry 的区别：
- 无 scoped registry
- 无 _written_file_registry / _file_read_cache
- MCP 工具名统一 mcp_ 前缀
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)
SERVER_BUILTIN = "__builtin__"


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    server: str = ""
    tool_name: str = ""
    tags: List[str] = field(default_factory=list)
    handler: Optional[Callable] = None


_SANDBOX_TOOL_DEFS = [
    ToolDefinition(
        name="write_todos",
        server=SERVER_BUILTIN,
        tags=["task", "tracking"],
        description="【自动跟踪】任务进度由系统自动管理，无需手动调用此工具。",
        parameters={
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "任务描述"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"], "description": "任务状态"}
                        },
                        "required": ["content", "status"]
                    },
                    "description": "任务列表"
                }
            },
            "required": ["todos"]
        },
        handler=None,
    ),
    ToolDefinition(
        name="write_file",
        server=SERVER_BUILTIN,
        tags=["file", "write"],
        description="新建文件并写入完整内容。\n- 适用于创建脚本、HTML 游戏、报告等新文件\n- content 是文件的**完整**内容，不可截断或留占位符\n- ⚠️ 只需修改文件某几行 → 用 edit_file，不要全文重写",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径，如 ~/Desktop/game.html"},
                "content": {"type": "string", "description": "文件的完整内容（必填，不能为空，不能截断）"},
            },
            "required": ["path", "content"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="execute_python",
        server=SERVER_BUILTIN,
        tags=["code", "sandbox"],
        description="安全执行 Python 代码。\n- 适用于运行脚本、测试算法、pip 安装包、操作桌面文件\n- mode=sandbox（默认）：沙盒隔离，无法访问桌面/网络\n- mode=local：真实环境，可写 ~/Desktop，可访问网络\n- ⚠️ 需运行系统命令(ls/pwd/git) → 用 execute_shell\n- ⚠️ 抓取网页/API 数据 → 用 fetch_url（execute_python 不是爬虫工具）",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码字符串"},
                "mode": {
                    "type": "string",
                    "enum": ["sandbox", "local"],
                    "description": "sandbox=沙盒隔离(默认,安全) | local=本地(可写桌面文件,无安全隔离)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（默认30，最大60）",
                },
                "skip_module_check": {
                    "type": "boolean",
                    "description": "仅 sandbox 模式有效：是否跳过模块安全检查",
                },
            },
            "required": ["code"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="execute_shell",
        server=SERVER_BUILTIN,
        tags=["code", "shell"],
        description="执行 Shell 系统命令。\n- 适用于文件操作(ls/mkdir/cp)、包管理(pip/npm)、Git、curl 等\n- mode=sandbox（默认）：沙盒隔离\n- mode=local：用户真实终端执行\n- ⚠️ 需运行 Python 代码 → 用 execute_python",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell 命令字符串"},
                "mode": {
                    "type": "string",
                    "enum": ["sandbox", "local"],
                    "description": "sandbox=沙盒隔离(默认,安全) | local=本地(无安全隔离)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（默认30，最大60）",
                },
            },
            "required": ["command"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="git",
        server=SERVER_BUILTIN,
        tags=["git", "code"],
        description="Git 版本控制操作。\n- 支持：status / add / commit / log / diff / branch / pull\n- 在当前项目目录执行\n- 典型工作流：status → diff → add → commit",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "status",
                        "add",
                        "commit",
                        "log",
                        "diff",
                        "branch",
                        "pull",
                    ],
                    "description": "Git 操作类型",
                },
                "message": {"type": "string", "description": "commit 时的提交信息（仅 action=commit 时必填）"},
                "files": {
                    "type": "string",
                    "description": "add 时的文件路径，默认全部（.）",
                },
                "count": {
                    "type": "integer",
                    "description": "log 显示的提交数，默认5",
                },
            },
            "required": ["action"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="fetch_url",
        server=SERVER_BUILTIN,
        tags=["web", "fetch"],
        description="HTTP GET 获取网页或 API 数据。\n- 适用于抓取网页 HTML 内容、调用 REST API\n- URL 会自动升级 HTTP → HTTPS\n- 结果可能被截断（可设 max_length 控制）\n- ⚠️ 需要搜索信息 → 用 web_search",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL（自动升级 HTTP → HTTPS）"},
                "max_length": {"type": "integer", "description": "最大返回字符数，不设则返回全部"},
            },
            "required": ["url"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="web_search",
        server=SERVER_BUILTIN,
        tags=["web", "search"],
        description="联网搜索获取实时信息。\n- 适用于查资料、新闻、数据收集\n- 三种搜索类型：auto(默认,均衡)、fast(快速)、deep(深度搜索)\n- ⚠️ 需要抓取特定 URL 内容 → 用 fetch_url",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询（越具体结果越精准）"},
                "num_results": {"type": "integer", "description": "返回结果数量，默认8"},
                "type": {"type": "string", "enum": ["auto", "fast", "deep"], "description": "搜索类型：auto(默认,均衡) | fast(快速) | deep(深度搜索)"},
            },
            "required": ["query"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="read_file",
        server=SERVER_BUILTIN,
        tags=["file", "read"],
        description="读取文件内容或浏览目录结构。\n- 是了解文件内容和项目结构的起点\n- 支持分页读取：offset(起始行号,从1开始) / limit(行数限制)\n- 目录会列出所有条目（目录带 / 后缀）\n- 长行超过2000字符会被截断\n- 支持读取图片和 PDF（返回附件）",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录的绝对路径"},
                "offset": {"type": "integer", "description": "起始行号（从1开始，不设则从头读）"},
                "limit": {"type": "integer", "description": "读取行数上限（默认2000）"},
            },
            "required": ["path"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="edit_file",
        server=SERVER_BUILTIN,
        tags=["file", "edit", "write"],
        description="精确字符串替换，修改文件中特定内容。\n- 正确流程：先 read_file 确认 → old_string 提供足够上下文确保唯一匹配 → 替换为新内容\n- 适用于修复 bug、增删函数、修改样式等局部改动\n- 支持 replace_all 替换所有匹配项\n- ⚠️ 编辑前必须先 read_file 读取文件\n- ⚠️ 大范围改动 → 用 write_file 重写",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径"},
                "old_string": {"type": "string", "description": "要替换的原始文本（需提供足够上下文确保唯一匹配）"},
                "new_string": {"type": "string", "description": "替换后的新文本"},
                "replace_all": {"type": "boolean", "description": "是否替换所有匹配项（默认 false）"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        handler=None,
    ),
    ToolDefinition(
        name="search_files",
        server=SERVER_BUILTIN,
        tags=["search", "file"],
        description="搜索文件。两种模式**二选一，不可同时使用**：\n- 模式① pattern：按文件名 glob 搜索（如 **/*.py、src/**）\n- 模式② content_pattern：按文件内容正则搜索（如 def foo）\n- ⚠️ open-ended 搜索需要多轮 glob + grep → 用 Task agent",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "【与 content_pattern 二选一】Glob 文件名模式，如 *.py、**/*.ts"},
                "content_pattern": {"type": "string", "description": "【与 pattern 二选一】文件内容正则搜索，如 def foo"},
                "path": {"type": "string", "description": "搜索目录，默认当前项目目录"},
                "include": {"type": "string", "description": "内容搜索时的文件过滤，如 *.py（仅 content_pattern 模式有效）"},
                "limit": {"type": "integer", "description": "结果数量上限，默认200"},
            },
        },
        handler=None,
    ),
    ToolDefinition(
        name="text_analyzer",
        server=SERVER_BUILTIN,
        tags=["text", "analysis"],
        description="深度文本分析（基于 LLM）。\n- 分析文本主题、关键信息、情感倾向\n- 生成摘要和要点提取\n- 适用于文章分析、报告解读、内容理解\n- ⚠️ 只需统计字数/关键词 → 用 MCP text-analyzer",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待分析的文本内容"},
            },
            "required": ["text"],
        },
        handler=None,
    ),
]

_HANDLER_MAP: Dict[str, Callable] = {}


class V1ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False

    async def discover_all(self) -> List[ToolDefinition]:
        """发现内置工具（MCP 由 MCP adapter 补充）"""
        if not self._initialized:
            for sd in _SANDBOX_TOOL_DEFS:
                if sd.name not in self._tools:
                    self._tools[sd.name] = sd
            self._initialized = True
        return list(self._tools.values())
