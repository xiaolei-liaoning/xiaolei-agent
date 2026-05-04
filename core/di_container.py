"""依赖注入容器 - 类型安全的服务定位器

实现特性:
- 类型安全的依赖注入
- 单例与瞬态生命周期管理
- 延迟初始化支持
- 依赖关系声明与验证
- 线程安全的服务注册与解析

使用方式:
    from core.di_container import DIContainer, inject, Injectable
    
    # 定义服务接口
    class IDispatcher(Protocol):
        def match_skill(self, message: str) -> str: ...
    
    # 注册服务
    container.register_singleton(IDispatcher, SkillDispatcher)
    
    # 通过装饰器注入
    @inject
    class MyService:
        dispatcher: IDispatcher = Injectable()
"""

from __future__ import annotations

import logging
import threading
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Type,
    TypeVar,
    runtime_checkable,
)
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import inspect

logger = logging.getLogger(__name__)

T = TypeVar("T")
TService = TypeVar("TService", bound=type)


class ServiceLifetime(Enum):
    """服务生命周期"""
    SINGLETON = "singleton"
    SCOPED = "scoped"
    TRANSIENT = "transient"


@runtime_checkable
class IService(Protocol):
    """服务标记接口"""
    pass


@dataclass
class ServiceDescriptor(Generic[T]):
    """服务描述符"""
    service_type: Type[T]
    implementation_type: Optional[Type[T]] = None
    factory: Optional[Callable[[], T]] = None
    instance: Optional[T] = None
    lifetime: ServiceLifetime = ServiceLifetime.SINGLETON
    dependencies: Dict[str, Type] = field(default_factory=dict)


class Injectable:
    """可注入属性标记类"""
    
    def __init__(self, default: Any = None):
        self.default = default
        self._name: Optional[str] = None
    
    def __set_name__(self, owner: type, name: str):
        self._name = name
    
    def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
        if obj is None:
            return self
        
        if self._name is None:
            return self.default
        
        if hasattr(obj, f'_injected_{self._name}'):
            return getattr(obj, f'_injected_{self._name}')
        
        return self.default
    
    def __set__(self, obj: Any, value: Any):
        setattr(obj, f'_injected_{self._name}', value)


def inject(cls: Type[T]) -> Type[T]:
    """类装饰器：自动注入标记的依赖
    
    Usage:
        @inject
        class MyService:
            dispatcher: IDispatcher = Injectable()
            processor: IProcessor = Injectable()
    """
    original_init = cls.__init__
    
    def __init__(self, *args, **kwargs):
        container = DIContainer.get_instance()
        
        for name, attr in cls.__annotations__.items():
            if isinstance(getattr(cls, name, None), Injectable):
                injectable = getattr(cls, name)
                if injectable.default is None:
                    try:
                        service = container.resolve(attr)
                        setattr(self, f'_injected_{name}', service)
                    except ServiceNotFoundError:
                        pass
        
        if original_init:
            original_init(self, *args, **kwargs)
    
    cls.__init__ = __init__
    return cls


class ServiceNotFoundError(Exception):
    """服务未找到异常"""
    def __init__(self, service_type: Type):
        self.service_type = service_type
        super().__init__(f"Service not found: {service_type.__name__}")


class CircularDependencyError(Exception):
    """循环依赖异常"""
    def __init__(self, dependency_chain: List[Type]):
        chain_str = " -> ".join(t.__name__ for t in dependency_chain)
        super().__init__(f"Circular dependency detected: {chain_str}")


class DIContainer:
    """依赖注入容器 - 线程安全的服务定位器
    
    特性:
    - 单例模式：全局唯一容器实例
    - 线程安全：使用锁保护服务注册和解析
    - 生命周期管理：单例、作用域、瞬态
    - 依赖验证：启动时验证所有依赖关系
    """
    
    _instance: Optional[DIContainer] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> DIContainer:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._services: Dict[Type, ServiceDescriptor] = {}
                    cls._instance._resolving: set = set()
                    cls._instance._service_lock = threading.Lock()
                    cls._instance._initialized = False
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> DIContainer:
        """获取容器单例"""
        return cls()
    
    @classmethod
    def reset(cls) -> None:
        """重置容器（仅用于测试）"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._services.clear()
                cls._instance._resolving.clear()
                cls._instance._initialized = False
                cls._instance = None
    
    def register_singleton(
        self, 
        service_type: Type[T], 
        implementation: Optional[Type[T]] = None,
        factory: Optional[Callable[[], T]] = None
    ) -> DIContainer:
        """注册单例服务
        
        Args:
            service_type: 服务类型（通常是接口或抽象类）
            implementation: 实现类型
            factory: 工厂函数（优先于implementation）
            
        Returns:
            容器实例（支持链式调用）
        """
        with self._service_lock:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                implementation_type=implementation or service_type,
                factory=factory,
                lifetime=ServiceLifetime.SINGLETON
            )
            self._services[service_type] = descriptor
            logger.debug(f"注册单例服务: {service_type.__name__}")
        return self
    
    def register_scoped(
        self,
        service_type: Type[T],
        implementation: Optional[Type[T]] = None,
        factory: Optional[Callable[[], T]] = None
    ) -> DIContainer:
        """注册作用域服务"""
        with self._service_lock:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                implementation_type=implementation or service_type,
                factory=factory,
                lifetime=ServiceLifetime.SCOPED
            )
            self._services[service_type] = descriptor
            logger.debug(f"注册作用域服务: {service_type.__name__}")
        return self
    
    def register_transient(
        self,
        service_type: Type[T],
        implementation: Optional[Type[T]] = None,
        factory: Optional[Callable[[], T]] = None
    ) -> DIContainer:
        """注册瞬态服务（每次解析创建新实例）"""
        with self._service_lock:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                implementation_type=implementation or service_type,
                factory=factory,
                lifetime=ServiceLifetime.TRANSIENT
            )
            self._services[service_type] = descriptor
            logger.debug(f"注册瞬态服务: {service_type.__name__}")
        return self
    
    def register_instance(self, service_type: Type[T], instance: T) -> DIContainer:
        """注册已有实例"""
        with self._service_lock:
            descriptor = ServiceDescriptor(
                service_type=service_type,
                instance=instance,
                lifetime=ServiceLifetime.SINGLETON
            )
            self._services[service_type] = descriptor
            logger.debug(f"注册实例: {service_type.__name__}")
        return self
    
    def resolve(self, service_type: Type[T]) -> T:
        """解析服务
        
        Args:
            service_type: 要解析的服务类型
            
        Returns:
            服务实例
            
        Raises:
            ServiceNotFoundError: 服务未注册
            CircularDependencyError: 检测到循环依赖
        """
        with self._service_lock:
            if service_type not in self._services:
                raise ServiceNotFoundError(service_type)
            
            descriptor = self._services[service_type]
            
            if descriptor.lifetime == ServiceLifetime.SINGLETON:
                if descriptor.instance is not None:
                    return descriptor.instance
                
                if descriptor.instance is None:
                    if service_type in self._resolving:
                        raise CircularDependencyError(list(self._resolving) + [service_type])
                    
                    self._resolving.add(service_type)
                    try:
                        instance = self._create_instance(descriptor)
                        descriptor.instance = instance
                        return instance
                    finally:
                        self._resolving.discard(service_type)
            
            return self._create_instance(descriptor)
    
    def _create_instance(self, descriptor: ServiceDescriptor[T]) -> T:
        """创建服务实例"""
        if descriptor.factory:
            return descriptor.factory()
        
        if descriptor.implementation_type:
            impl_type = descriptor.implementation_type
            
            constructor_params = {}
            sig = inspect.signature(impl_type.__init__)
            
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                
                param_type = param.annotation
                if param_type != inspect.Parameter.empty:
                    try:
                        if param_type in self._services:
                            constructor_params[param_name] = self.resolve(param_type)
                    except ServiceNotFoundError:
                        if param.default == inspect.Parameter.empty:
                            raise
            
            return impl_type(**constructor_params)
        
        raise ServiceNotFoundError(descriptor.service_type)
    
    def is_registered(self, service_type: Type) -> bool:
        """检查服务是否已注册"""
        return service_type in self._services
    
    def get_all_services(self) -> Dict[Type, ServiceDescriptor]:
        """获取所有已注册服务"""
        return self._services.copy()
    
    def validate_dependencies(self) -> List[str]:
        """验证所有依赖关系
        
        Returns:
            错误消息列表
        """
        errors = []
        
        for service_type, descriptor in self._services.items():
            if descriptor.lifetime == ServiceLifetime.SINGLETON:
                try:
                    if descriptor.instance is None:
                        self.resolve(service_type)
                except ServiceNotFoundError as e:
                    errors.append(f"{service_type.__name__}: 依赖未注册 - {e.service_type.__name__}")
                except CircularDependencyError as e:
                    errors.append(f"{service_type.__name__}: {str(e)}")
        
        return errors


def get_container() -> DIContainer:
    """获取DI容器实例"""
    return DIContainer.get_instance()
