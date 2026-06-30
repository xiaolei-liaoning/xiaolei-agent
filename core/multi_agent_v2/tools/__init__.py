"""工具注册表模块"""
from .tool_registry import ToolRegistry, ToolDefinition

# 新增工具模块
from .permission import PermissionService, get_permission_service
from .shell_guard import ShellGuard, get_shell_guard
from .hooks import ToolHookManager, get_hook_manager
# tools/mcp_client.py (v1) 已废弃，实际 MCP 调用使用 core/mcp/mcp_client.py (v3)
# from .mcp_client import MCPClient, get_mcp_client  # DEPRECATED
from .schema import SchemaAdapter, get_schema_adapter
# tools/edit.py 已删除（SmartEditor 486 行死代码，_handle_edit_file 实际用 str.replace）
from .shell_analyzer import ShellAnalyzer, get_shell_analyzer
from .lsp_client import LSPClient, get_lsp_client
# tools/tail_call.py 已删除（TailCall 提取后从不执行，217 行死代码）
from .cache import ToolCache, get_tool_cache
from .recovery import RecoveryManager, get_recovery_manager
from .metrics import MetricsCollector, ExecutionLogger, get_metrics_collector, get_execution_logger

__all__ = [
    "ToolRegistry",
    "ToolDefinition",
    # 新增工具服务
    "PermissionService",
    "get_permission_service",
    "ShellGuard",
    "get_shell_guard",
    "ToolHookManager",
    "get_hook_manager",
    # "MCPClient", "get_mcp_client",  # DEPRECATED: 使用 core.mcp.mcp_client
    "SchemaAdapter",
    "get_schema_adapter",
    # "SmartEditor", "get_smart_editor",  # DELETED: 486 行死代码
    "ShellAnalyzer",
    "get_shell_analyzer",
    "LSPClient",
    "get_lsp_client",
    # "TailCallHandler", "get_tail_call_handler",  # DELETED: 217 行死代码
    "ToolCache",
    "get_tool_cache",
    "RecoveryManager",
    "get_recovery_manager",
    "MetricsCollector",
    "ExecutionLogger",
    "get_metrics_collector",
    "get_execution_logger"
]