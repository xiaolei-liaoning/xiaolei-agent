"""CLI模块 - 小雷版小龙虾AI Agent命令行接口

模块化设计，按功能拆分为：
- colors: 颜色和样式
- base: 基础类和辅助函数
- smart: 智能工作流命令
- automate: GUI自动化命令
- scrape: 爬虫命令
- analyze: 分析命令
"""

from cli.colors import (
    CliColors,
    print_color,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_header,
    print_section,
    print_section_end,
    print_chat_bubble,
)

from cli.base import (
    WorkflowEngineWrapper,
    display_workflow_result,
)

from cli.smart import (
    handle_smart,
    handle_workflow_run,
    handle_workflow_list,
    handle_workflow_save,
)

from cli.automate import (
    handle_automate,
)

from cli.scrape import (
    handle_scrape,
    handle_scrape_list,
)

from cli.analyze import (
    handle_analyze,
    handle_analyze_wordcloud,
    handle_analyze_chart,
    handle_analyze_report,
)

__all__ = [
    # Colors
    "CliColors",
    "print_color",
    "print_success",
    "print_error",
    "print_warning",
    "print_info",
    "print_header",
    "print_section",
    "print_section_end",
    "print_chat_bubble",
    # Base
    "WorkflowEngineWrapper",
    "display_workflow_result",
    # Smart
    "handle_smart",
    "handle_workflow_run",
    "handle_workflow_list",
    "handle_workflow_save",
    # Automate
    "handle_automate",
    # Scrape
    "handle_scrape",
    "handle_scrape_list",
    # Analyze
    "handle_analyze",
    "handle_analyze_wordcloud",
    "handle_analyze_chart",
    "handle_analyze_report",
]
