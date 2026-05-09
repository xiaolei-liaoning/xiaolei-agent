#!/usr/bin/env python3
"""安全地更新 core/__init__.py 和 skills/__init__.py"""

import os

# ========== 1. 更新 core/__init__.py ==========
core_init_content = '''"""核心模块导出"""

# 原有模块
from .workflow_engine import (
    WorkflowManager,
    Workflow,
    WorkflowTask,
    TaskStatus,
    TaskType,
    get_workflow_manager,
    execute_complex_task,
)

# 新增：可选的增强模块（按需导入）
try:
    from .dynamic_short_term_memory import DynamicShortTermMemory
    DYNAMIC_MEMORY_AVAILABLE = True
except ImportError:
    DYNAMIC_MEMORY_AVAILABLE = False
    DynamicShortTermMemory = None

try:
    from .enhanced_logger import (
        setup_enhanced_logging,
        get_logger,
        log_performance,
        TimerLogger,
    )
    ENHANCED_LOGGER_AVAILABLE = True
except ImportError:
    ENHANCED_LOGGER_AVAILABLE = False
    setup_enhanced_logging =    setup_enhanced_logging =    setup_enhanced_logging =    setup_enhr =    setup_enhanced_m .natural_language_processor import (
        NaturalLanguageProcessor,
        get_nlp_processor,
    )
    NLP_PROCESSOR_AVAILABLE = True
except ImportError:
    NLP_PROCESSOR_AVAILABLE = False
    NaturalLanguageProcessor = None
    get_nlp_processor = None

try:
    from .scheduled_cleanup import (
        ScheduledCleanupManager,
        get_cleanup_manager,
    )
    SCHEDULED_CLEANUP_AVAILABLE = True
except ImportError:
    SCHEDULED_CLEANUP_AVAILABLE = False
    ScheduledCleanupManager = None
    get_cleanup_manager = None

__all__ = [
    # 原有模块
    "WorkflowManager",
    "Workflow",
    "WorkflowTask",
    "TaskStatus",
    "TaskType",
    "get_workflow_manager",
    "execute_complex_task",
    # 新增：可选增强模块
    "DYNAMIC_MEMORY_AVAILABLE",
    "DynamicShortTermMemory",
    "ENHANCED_LOGGER_AVAILABLE",
    "setup_enhanced_logging",
    "get_logger",
    "log_performance",
    "TimerLogger",
    "NLP_PROCESSOR_AVAILABLE",
    "NaturalLanguageProcessor",
    "get_nlp_processor",
    "SCHEDULED_CLEANUP_AVAILABLE",
    "ScheduledCleanupManager",
    "get_cleanup_manager",
]
'''

with open("core/__init__.py", "w", encoding="utf-8") as f:
    f.write(core_init_content)

print("✅ core/__init__.py 已更新")

# ========== 2. 更新 skills/__init__.py ==========
# 收集所有可用的skill目录
skill_dirs = []
skills_path = "skills"

if os.path.exists(skills_path):
    for item in os.listdir(skills_path):
        item_path = os.path.join(skills_path, item)
        if os.path.isdir(item_path) and not item.startswith(('_', '.', '__')):
            # 检查是否有 __init__.py 或 handler.py
            has_init = os.path.exists(os.path.join(item_path, "__init__.py"))
            has_handler = os.path.exists(os.path.join(item_path, "handler.py"))
            if has_init or has_handler:
                skill_dirs.append(item)

skill_dirs.sort()

# 生成 skills/__init__.py 内容
skills_import_lines = []
skills_all_lines = ["__all__ = ["]

for skill in skill_dirs:
    skills_import_lines.append(f"from .{skill} import *")
    skills_all_lines.append(f'    "{skill}",')

skills_all_lines.append("]")

skills_init_content = '"""Skills模块导出"""\n\n'
skills_init_content += '\n'.join(skills_import_lines)
skills_init_content += '\n\n'
skills_init_content += '\n'.join(skills_all_lines)
skills_init_content += '\n'

with open("skills/__init__.py", "w", encoding="utf-8") as f:
    f.write(skills_init_content)

print(f"✅ skills/__init__.py 已更新，导入了 {len(skill_dirs)} 个skill:")
for skill in skill_dirs:
    print(f"   - {skill}")

print("\n✅ 全部更新完成！")
