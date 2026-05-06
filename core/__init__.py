"""核心模块导出 - 完整版

此文件整合所有core目录下的模块。
"""

import sys
import logging
from pathlib import Path
import importlib
import ast

logger = logging.getLogger(__name__)

# 获取所有core模块
CORE_DIR = Path(__file__).parent
ALL_MODULES = []

for py_file in CORE_DIR.glob("*.py"):
    if py_file.name.startswith("_") or py_file.name == "__init__.py":
        continue
    module_name = py_file.stem
    ALL_MODULES.append(module_name)

ALL_MODULES.sort()

# 存储导入结果
IMPORT_RESULTS = {}
FAILED_IMPORTS = []

# 特殊模块导出配置 - 明确指定要导出的类/函数
SPECIAL_EXPORTS = {
    "dynamic_short_term_memory": ["DynamicShortTermMemory"],
    "enhanced_logger": ["get_logger", "setup_enhanced_logging", "log_performance", "TimerLogger"],
    "natural_language_processor": ["NaturalLanguageProcessor", "get_nlp_processor"],
    "scheduled_cleanup": ["ScheduledCleanupManager", "get_cleanup_manager"],
    "workflow_engine": ["WorkflowManager", "Workflow", "WorkflowTask", "TaskStatus", "TaskType", "get_workflow_manager", "execute_complex_task"],
}

def auto_export_classes_and_functions(module_name, module):
    """自动导出模块中的类和函数"""
    exported = []
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue

        attr = getattr(module, attr_name, None)
        if attr is None:
            continue

        # 导出以大写开头的类
        if attr_name[0].isupper() and callable(attr):
            try:
                globals()[attr_name] = attr
                exported.append(attr_name)
            except:
                pass

        # 导出常见的实用函数
        elif attr_name in ["get_logger", "get_workflow_manager", "get_cleanup_manager",
                          "get_nlp_processor", "get_rag_engine", "get_skill_dispatcher",
                          "get_cache_manager", "get_llm_router"]:
            try:
                globals()[attr_name] = attr
                exported.append(attr_name)
            except:
                pass

    return exported

# 逐个安全导入所有模块
for module_name in ALL_MODULES:
    try:
        # 动态导入模块
        module = importlib.import_module(f"core.{module_name}")

        IMPORT_RESULTS[module_name] = {
            "success": True,
            "module": module,
            "error": None
        }

        # 添加到全局命名空间
        globals()[module_name] = module

        # 如果有特殊导出配置，导出指定的类/函数
        if module_name in SPECIAL_EXPORTS:
            for attr_name in SPECIAL_EXPORTS[module_name]:
                try:
                    attr = getattr(module, attr_name, None)
                    if attr is not None:
                        globals()[attr_name] = attr
                except Exception as e:
                    logger.debug(f"导出 {module_name}.{attr_name} 失败: {e}")

        # 自动导出类（以大写开头）
        auto_export_classes_and_functions(module_name, module)

    except Exception as e:
        IMPORT_RESULTS[module_name] = {
            "success": False,
            "module": None,
            "error": str(e)
        }
        FAILED_IMPORTS.append(module_name)
        logger.warning(f"模块 {module_name} 导入失败: {e}")

# 可用的模块列表
AVAILABLE_MODULES = [k for k, v in IMPORT_RESULTS.items() if v["success"]]

# 构建__all__列表 - 包含所有模块名和重要的类/函数
_all_items = AVAILABLE_MODULES.copy()

# 添加特殊导出的类/函数
for module_name, exports in SPECIAL_EXPORTS.items():
    if module_name in AVAILABLE_MODULES:
        _all_items.extend(exports)

# 添加常见的全局函数
common_functions = [
    "get_logger", "get_workflow_manager", "get_cleanup_manager",
    "get_nlp_processor", "get_rag_engine", "get_skill_dispatcher",
    "get_cache_manager", "get_llm_router"
]
for func in common_functions:
    if func not in _all_items:
        _all_items.append(func)

__all__ = sorted(set(_all_items))

# 统计信息
total = len(ALL_MODULES)
available = len(AVAILABLE_MODULES)
failed = len(FAILED_IMPORTS)

logger.info(f"✅ Core模块导入完成: {available}/{total} 个成功")

if failed > 0:
    logger.warning(f"⚠️  {failed} 个模块导入失败: {', '.join(FAILED_IMPORTS)}")
