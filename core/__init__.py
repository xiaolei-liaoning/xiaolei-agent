"""核心模块导出"""

try:
    from .workflow_engine import (
        WorkflowManager,
        Workflow,
        WorkflowTask,
        TaskStatus,
        TaskType,
        get_workflow_manager,
        execute_complex_task,
    )
except ImportError:
    WorkflowManager = Workflow = WorkflowTask = TaskStatus = TaskType = None
    get_workflow_manager = execute_complex_task = None

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
    TimerLogger = None

try:
    from .nlp_processor import NaturalLanguageProcessor, get_nlp_processor
    NLP_PROCESSOR_AVAILABLE = True
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
