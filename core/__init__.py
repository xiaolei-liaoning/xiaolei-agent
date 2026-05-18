"""核心模块导出 - 完整版（重构后）

此文件整合所有core目录下的模块，支持新的功能域划分架构。

新架构：
- core.agents/ - Agent系统
- core.memory/ - 记忆管理
- core.search/ - 搜索检索
- core.workflow/ - 工作流引擎
- core.tasks/ - 任务处理
- core.tools/ - 工具框架
- core.infrastructure/ - 基础设施
- core.engine/ - 核心引擎
- core.mcp/ - MCP集成
- core.results/ - 结果处理
- core.agents/ - ⚠️ 已弃用，请使用 multi_agent_v2

向后兼容策略：
将所有子模块重新导出到 core. 命名空间，保持原有导入路径不变。
例如：core.memory.short_term_memory 也会作为 core.short_term_memory 可用

静态导入（供类型检查器使用）：
以下导入仅用于让Pylance等类型检查器能够识别模块结构，实际导入由动态机制处理。
"""

# 静态导入提示（供Pylance类型检查）— 包裹try/except避免缺失依赖导致崩溃
# 类型提示可能失效，但保证运行时不会因缺少可选依赖而崩溃
try:
    from .workflow import xml_workflow_mapper  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .engine import reasoning_engine, llm_backend, skill_dispatcher  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .tasks import task_processor, task_planner  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .search import rag_search_engine, search_engine_factory, keyword_extractor  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .memory import short_term_memory, character_memory, vector_memory  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .tools import sandbox_executor, shell_executor, screen_locator, tool_result_formatter  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .monitoring import monitoring, alert_manager, performance_utils  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .infrastructure import database, cache_manager, persistence, config_manager  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .security import security, error_handler  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .skills import skill_extractor  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .mcp import mcp_client, awesome_mcp_manager  # type: ignore[no-redef]
except ImportError:
    pass
try:
    from .results import result_summarizer, self_check_middleware  # type: ignore[no-redef]
except ImportError:
    pass

import sys
import logging
from pathlib import Path
import importlib

logger = logging.getLogger(__name__)

# 获取core根目录
CORE_DIR = Path(__file__).parent

# 定义功能域子目录映射
SUBDIR_MODULES = {
    'memory': ['short_term_memory', 'character_memory', 'vector_memory', 
               'memory_optimizer'],
    'search': ['rag_search_engine', 'search_engine_factory', 'keyword_extractor'],
    'workflow': ['automation_workflow', 'xml_workflow_mapper', 'bfs_processor'],
    'tools': ['sandbox_executor', 'shell_executor', 'screen_locator', 'tool_result_formatter'],
    # 'monitoring': ['monitoring', 'alert_manager', 'performance_utils'],  # 已弃用
    'infrastructure': ['database', 'cache_manager', 'persistence', 'redis_pool', 
                       'config_manager', 'di_container', 'service_registry', 'service_interfaces'],
    'engine': ['reasoning_engine', 'llm_backend', 'skill_dispatcher'],
    # 'skills': ['skill_extractor'],  # 已弃用
    'mcp': ['mcp_client', 'awesome_mcp_manager'],
    # 'scheduling': ['scheduled_tasks', 'scheduled_cleanup'],  # 已弃用
    # 'learning': ['continuous_learning', 'auto_reviewer'],  # 已弃用
    'results': ['self_check_middleware'],
    # 'security': ['security', 'error_handler'],  # 已弃用
    # 'interfaces': [],  # 已弃用
    # multi_agent_v2 已移除
}

# 根目录保留的模块
ROOT_MODULES = ['handlers', 'agent_communication', 'agent_system']

# 存储导入结果
IMPORT_RESULTS = {}
FAILED_IMPORTS = []

def import_and_register_module(module_path, export_name=None):
    """导入模块并注册到sys.modules以实现向后兼容"""
    if export_name is None:
        export_name = module_path.split('.')[-1]
    
    try:
        # 从子目录导入模块
        module = importlib.import_module(module_path)
        
        # 注册到sys.modules，使得 from core.xxx import 可以工作
        alias_path = f"core.{export_name}"
        sys.modules[alias_path] = module
        
        # 也添加到全局命名空间
        globals()[export_name] = module
        
        IMPORT_RESULTS[export_name] = {
            "success": True,
            "module": module,
            "error": None
        }
        return True
    except Exception as e:
        IMPORT_RESULTS[export_name] = {
            "success": False,
            "module": None,
            "error": str(e)
        }
        FAILED_IMPORTS.append(export_name)
        logger.warning(f"模块 {module_path} 导入失败: {e}")
        return False

# 第一步：导入并注册子目录中的模块
for subdir, modules in SUBDIR_MODULES.items():
    for module_name in modules:
        full_module_path = f"core.{subdir}.{module_name}"
        import_and_register_module(full_module_path, module_name)

# 第二步：导入并注册根目录模块
for module_name in ROOT_MODULES:
    full_module_path = f"core.{module_name}"
    import_and_register_module(full_module_path, module_name)

# 可用的模块列表
AVAILABLE_MODULES = [k for k, v in IMPORT_RESULTS.items() if v["success"]]

# 构建__all__列表
__all__ = sorted(AVAILABLE_MODULES)

# 统计信息
total = len(IMPORT_RESULTS)
available = len(AVAILABLE_MODULES)
failed = len(FAILED_IMPORTS)

logger.info(f"✅ Core模块导入完成: {available}/{total} 个成功")

if failed > 0:
    logger.warning(f"⚠️  {failed} 个模块导入失败: {', '.join(FAILED_IMPORTS)}")
    logger.warning("提示：检查对应子目录的__init__.py和模块内部导入是否正确")
