"""服务注册模块 - 应用启动时初始化所有服务

使用方式:
    from core.service_registry import ServiceRegistry, initialize_services
    
    # 初始化所有服务
    container = initialize_services()
    
    # 解析服务
    dispatcher = container.resolve(ISkillDispatcher)
"""

import logging
from typing import Optional

from .di_container import DIContainer, get_container
from .service_interfaces import (
    ISkillDispatcher,
    ITaskProcessor,
    ITaskPlanner,
    IBFSProcessor,
    IRAGEngine,
    ILLMBackend,
    IMessageBus,
    IDatabase,
    ICacheManager,
    IMonitoringManager,
    IAgentCoordinator,
)
from .config_manager import get_config, AppConfig

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """服务注册器
    
    负责在应用启动时注册所有服务到DI容器
    """
    
    def __init__(self, container: Optional[DIContainer] = None):
        self.container = container or get_container()
        self._initialized = False
    
    def register_all(self, config: Optional[AppConfig] = None) -> DIContainer:
        """注册所有服务
        
        Args:
            config: 应用配置，如果为None则自动加载
            
        Returns:
            配置完成的DI容器
        """
        if self._initialized:
            logger.warning("服务已初始化，跳过重复注册")
            return self.container
        
        config = config or get_config()
        
        self._register_core_services(config)
        
        self._register_infrastructure_services(config)
        
        self._register_external_services(config)
        
        errors = self.container.validate_dependencies()
        if errors:
            for error in errors:
                logger.error(f"依赖验证失败: {error}")
            raise RuntimeError(f"服务依赖验证失败: {errors}")
        
        self._initialized = True
        logger.info("所有服务注册完成")
        
        return self.container
    
    def _register_core_services(self, config: AppConfig) -> None:
        """注册核心业务服务"""
        
        def create_skill_dispatcher():
            from core.skill_dispatcher import SkillDispatcher
            return SkillDispatcher()
        
        self.container.register_singleton(
            ISkillDispatcher,
            factory=create_skill_dispatcher
        )
        logger.debug("注册服务: ISkillDispatcher")
        
        def create_task_processor():
            from core.concurrent_processor import ConcurrentTaskProcessor
            return ConcurrentTaskProcessor()
        
        self.container.register_singleton(
            ITaskProcessor,
            factory=create_task_processor
        )
        logger.debug("注册服务: ITaskProcessor")
        
        def create_task_planner():
            from core.task_planner import TaskPlanner
            return TaskPlanner()
        
        self.container.register_singleton(
            ITaskPlanner,
            factory=create_task_planner
        )
        logger.debug("注册服务: ITaskPlanner")
        
        def create_bfs_processor():
            from core.bfs_processor import get_bfs_processor
            return get_bfs_processor()
        
        self.container.register_singleton(
            IBFSProcessor,
            factory=create_bfs_processor
        )
        logger.debug("注册服务: IBFSProcessor")
        
        def create_message_bus():
            from core.message_bus import message_bus
            return message_bus
        
        self.container.register_singleton(
            IMessageBus,
            factory=create_message_bus
        )
        logger.debug("注册服务: IMessageBus")
    
    def _register_infrastructure_services(self, config: AppConfig) -> None:
        """注册基础设施服务"""
        
        def create_database():
            from core.database import get_session, init_db
            init_db()
            
            class DatabaseAdapter:
                def get_session(self):
                    return get_session()
                
                def is_initialized(self) -> bool:
                    return True
            
            return DatabaseAdapter()
        
        self.container.register_singleton(
            IDatabase,
            factory=create_database
        )
        logger.debug("注册服务: IDatabase")
        
        def create_cache_manager():
            from core.cache_manager import get_cache_manager
            return get_cache_manager()
        
        self.container.register_singleton(
            ICacheManager,
            factory=create_cache_manager
        )
        logger.debug("注册服务: ICacheManager")
        
        def create_monitoring_manager():
            from core.monitoring import monitoring_manager
            return monitoring_manager
        
        self.container.register_singleton(
            IMonitoringManager,
            factory=create_monitoring_manager
        )
        logger.debug("注册服务: IMonitoringManager")
        
        def create_agent_coordinator():
            from core.agent_coordinator import get_agent_coordinator
            return get_agent_coordinator()
        
        self.container.register_singleton(
            IAgentCoordinator,
            factory=create_agent_coordinator
        )
        logger.debug("注册服务: IAgentCoordinator")
    
    def _register_external_services(self, config: AppConfig) -> None:
        """注册外部服务"""
        
        def create_llm_backend():
            from core.llm_backend import get_llm_router
            return get_llm_router()
        
        self.container.register_singleton(
            ILLMBackend,
            factory=create_llm_backend
        )
        logger.debug("注册服务: ILLMBackend")
        
        def create_rag_engine():
            try:
                from core.rag_search_engine import get_rag_engine
                return get_rag_engine()
            except Exception as e:
                logger.warning(f"RAG引擎初始化失败: {e}")
                return None
        
        self.container.register_singleton(
            IRAGEngine,
            factory=create_rag_engine
        )
        logger.debug("注册服务: IRAGEngine")
    
    def register_instance(self, service_type: type, instance: object) -> None:
        """注册已有实例
        
        Args:
            service_type: 服务类型
            instance: 服务实例
        """
        self.container.register_instance(service_type, instance)
        logger.debug(f"注册实例: {service_type.__name__}")
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized
    
    def reset(self) -> None:
        """重置所有服务（仅用于测试）"""
        DIContainer.reset()
        self._initialized = False
        logger.info("服务注册已重置")


def initialize_services(config: Optional[AppConfig] = None) -> DIContainer:
    """初始化所有服务
    
    Args:
        config: 应用配置
        
    Returns:
        配置完成的DI容器
    """
    registry = ServiceRegistry()
    return registry.register_all(config)


def get_service(service_type: type) -> object:
    """获取服务的便捷函数
    
    Args:
        service_type: 服务类型
        
    Returns:
        服务实例
    """
    container = get_container()
    return container.resolve(service_type)
