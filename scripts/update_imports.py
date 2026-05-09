#!/usr/bin/env python3
"""安全更新 core/__init__.py 和 skills/__init__.py"""

import os

# ========== 1. 更新 core/__init__.py ==========
core_init = '''"""核心模块导出"""

from .workflow_engine import (
    WorkflowManager,
    Workflow,
    WorkflowTask,
    TaskStatus,
    TaskType,
    get_workflow_manager,
    execute_complex_task,
)

# 新增：可选增强模块
try:
    from .dynamic_short_term_memory import DynamicShortTermMemory
    DYNAMIC_MEMORY_AVAILABLE = True
except ImportError:
    DYNAMIC_MEMORY_AVAILABLE = False
    DynamicShortTermMemory = None

try:
    from .enhanced_logger import setup_enhanced_logging, get_logger, log_performance, TimerLogger
    ENHANCED_LOGGER_AVAILABLE = True
except ImportError:
    ENHANCED_LOGGER_AVAILABLE = False
    setup_enhanced_logging = None
    get_logger = None
    log_performance = None
                                                                         Na                                                 _PROCESSOR_AVAILABLE = True
except ImportError:
    NLP_PROCESSOR_AVAILABLE = False
    NaturalLanguageProcessor = None
    get_nlp_processor = None

try:
    from .scheduled_cleanup import ScheduledCleanupManager, get_cleanup_manager
    SCHEDULED_CLEANUP_AVAILABLE = True
except ImportError:
    SCHEDULED_CLEANUP_AVAILABLE = False
    ScheduledCleanupManager = None
    get_cleanup_manager = None

__all__ = [
    "WorkflowManager", "Workflow", "WorkflowTask", "TaskStatus", "TaskType",
    "get_workflow_manager", "execute_complex_task",
    "DYNAMIC_MEMORY_AVAILABLE", "DynamicShortTermMemory",
    "ENHANCED_LOGGER_AVAILABLE", "setup_enhanced_logging", "get_logger", "log_performance", "TimerLogger",
    "NLP_PROCESSOR_AVAILABLE", "NaturalLanguageProcessor", "get_nlp_processor",
    "SCHEDULED_CLEANUP_AVAILABLE", "ScheduledCleanupManager", "get_cleanup_manager",
]
'''

with open("core/__init__.py", "w", encoding="utf-8") as f:
    f.write(core_init)

print("✅ core/__init__.py 已更新")

# ========== 2. 更新 skills/__init__.py ==========
skill_dirs = []
skills_path = "skills"

if os.path.exists(skills_path):
    for item in os.listdir(skills_path):
        item_path = os.path.join(skills_path, item)
        if os.path.isdir(item_path) and not item.startswith(('_', '.', '__')):
            has_init = os.path.exists(os.path.join(item_path, "__init__.py"))
            has_handler = os.path.exists(os.path.join(item_path, "handler.py"))
            if has_init or has_handler:
                skill_dirs.append(item)

skill_dirs.sort()

# 生成skills/__init__.py
lines = ['"""Skills模块导出"""', '']
for skill in skill_dirs:
    lines.append(f'from .{skill} import *')
    
lines.append('')
lines.append('__all__ = [')
for i, skill in enumerate(skill_dirs):
    if i < len(skill_dirs) - 1:
        lines.append(f'    "{skill}",')
    else:
        lines.append(f'    "{skill}"')
lines.append(']')

skills_init = '\n'.join(lines)

with open("skills/__init__.py", "w", encoding="utf-8") as f:
    f.write(skills_init)

print(f"✅ skills/__init__.py 已更新 ({len(skill_dirs)} 个skill)")
for skill in skill_dirs:
    print(f"   - {skill}")

print("\n✅ 全部完成！")
