"""Tools子系统 - 工具框架

包含：
- 沙盒执行器
- Shell执行器
- Bash 工具（标准沙盒接口）
- 语义文本匹配引擎
- Git 工作流工具
- 屏幕定位器
- 工具结果格式化器
"""

import logging
logger = logging.getLogger(__name__)

# 新工具（零依赖，优先导入）
from .bash_tool import BashTool, BashResult, run_bash
from .text_matcher import TextMatcher, MatchResult, MatchStrategy, DiffVisualizer
from .git_ops import GitTool, GitResult, git_status, git_diff, git_commit, create_github_pr

# 已有工具（包装 try/except，避免缺失依赖导致整个导入失败）
try:
    from .sandbox_executor import *  # noqa: F401, F403
except Exception as e:
    logger.debug(f"sandbox_executor 导入失败: {e}")

try:
    from .shell_executor import *  # noqa: F401, F403
except Exception as e:
    logger.debug(f"shell_executor 导入失败: {e}")

try:
    from .screen_locator import *  # noqa: F401, F403
except Exception as e:
    logger.debug(f"screen_locator 导入失败: {e}")

try:
    from .tool_result_formatter import *  # noqa: F401, F403
except Exception as e:
    logger.debug(f"tool_result_formatter 导入失败: {e}")
