"""核心模块导出 - 静态导入版本

导入所有核心子模块并提供向后兼容的命名空间导出。
"""
import logging
import sys

logger = logging.getLogger(__name__)

# ── 按功能域导入子包 ──
from . import engine
from . import search
from . import memory
from . import workflow
from . import tools
from . import infrastructure
from . import tasks
from . import mcp
from . import results

# 可选子包
try:
    from . import monitoring
except Exception:
    logger.debug("monitoring 子包导入跳过")

try:
    from . import security
except Exception:
    logger.debug("security 子包导入跳过")

try:
    from . import services
except Exception:
    logger.debug("services 子包导入跳过")

# ── 向后兼容的扁平化别名 ──
# 允许 from core.database import ... 等旧式导入
from .infrastructure import database
from .tools import tool_result_formatter
from .results import self_check_middleware
from .mcp import awesome_mcp_manager
from .monitoring import performance_utils

_sys_module_aliases = {
    "core.database": database,
    "core.tool_result_formatter": tool_result_formatter,
    "core.self_check_middleware": self_check_middleware,
    "core.awesome_mcp_manager": awesome_mcp_manager,
    "core.performance_utils": performance_utils,
}
for name, mod in _sys_module_aliases.items():
    if name not in sys.modules:
        sys.modules[name] = mod

__all__ = [
    "engine", "search", "memory", "workflow", "tools",
    "infrastructure", "tasks", "mcp", "results",
    "database", "tool_result_formatter", "self_check_middleware",
    "awesome_mcp_manager", "performance_utils",
]

logger.debug("core 包加载完成")
