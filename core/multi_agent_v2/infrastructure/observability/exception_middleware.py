"""
统一异常处理中间件

特性:
- 全局异常捕获与统一响应
- 请求追踪ID（trace_id）
- 结构化错误日志
- 异常恢复机制
- 告警通知
"""

import asyncio
import logging
import traceback
import uuid
import time
from typing import Dict, Any, Optional, Callable, Type
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from contextvars import ContextVar

logger = logging.getLogger(__name__)

trace_id_var: ContextVar[str] = ContextVar('trace_id', default='')


def get_trace_id() -> str:
    """获取当前请求的追踪ID"""
    return trace_id_var.get()


def set_trace_id(trace_id: str = None) -> str:
    """设置追踪ID"""
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:8]
    trace_id_var.set(trace_id)
    return trace_id


class ExceptionSeverity(Enum):
    """异常严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ExceptionContext:
    """异常上下文"""
    trace_id: str
    timestamp: float
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    operation: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    additional_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExceptionRecord:
    """异常记录"""
    exception_type: str
    exception_message: str
    severity: ExceptionSeverity
    context: ExceptionContext
    stack_trace: str
    recovery_action: Optional[str] = None
    recovered: bool = False
    retry_count: int = 0


class ExceptionRegistry:
    """异常注册表 - 记录所有异常"""
    
    def __init__(self, max_records: int = 1000):
        self.max_records = max_records
        self.records: list = []
        self._lock = asyncio.Lock()
    
    async def add_record(self, record: ExceptionRecord):
        """添加异常记录"""
        async with self._lock:
            self.records.append(record)
            if len(self.records) > self.max_records:
                self.records = self.records[-self.max_records:]
    
    async def get_records(
        self,
        severity: Optional[ExceptionSeverity] = None,
        limit: int = 100
    ) -> list:
        """获取异常记录"""
        async with self._lock:
            if severity:
                filtered = [r for r in self.records if r.severity == severity]
            else:
                filtered = self.records.copy()
            return filtered[-limit:]
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取异常统计"""
        async with self._lock:
            if not self.records:
                return {"total": 0, "by_severity": {}, "by_type": {}}
            
            by_severity = {}
            by_type = {}
            
            for record in self.records:
                sev = record.severity.value
                by_severity[sev] = by_severity.get(sev, 0) + 1
                
                exc_type = record.exception_type
                by_type[exc_type] = by_type.get(exc_type, 0) + 1
            
            return {
                "total": len(self.records),
                "by_severity": by_severity,
                "by_type": by_type
            }


class RecoveryStrategy:
    """恢复策略"""
    
    @staticmethod
    async def retry_with_backoff(
        func: Callable,
        max_retries: int = 3,
        base_delay: float = 1.0,
        *args,
        **kwargs
    ) -> Any:
        """带退避的重试"""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"[{get_trace_id()}] 重试 {attempt + 1}/{max_retries} "
                        f"在 {delay}s 后，错误: {e}"
                    )
                    await asyncio.sleep(delay)
        
        raise last_exception
    
    @staticmethod
    async def fallback(
        func: Callable,
        fallback_func: Optional[Callable] = None,
        fallback_value: Any = None,
        *args,
        **kwargs
    ) -> Any:
        """降级处理"""
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"[{get_trace_id()}] 主函数失败，使用降级: {e}")
            if fallback_func:
                return await fallback_func(*args, **kwargs)
            return fallback_value
    
    @staticmethod
    async def circuit_breaker(
        func: Callable,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        *args,
        **kwargs
    ) -> Any:
        """熔断器模式"""
        pass


class ExceptionHandlerMiddleware:
    """异常处理中间件"""
    
    def __init__(
        self,
        alert_threshold: int = 5,
        alert_window: float = 60.0
    ):
        self.registry = ExceptionRegistry()
        self.recovery_strategy = RecoveryStrategy()
        self.alert_threshold = alert_threshold
        self.alert_window = alert_window
        self._recent_errors: list = []
        self._alert_handlers: list = []
        
        self._severity_map = {
            ValueError: ExceptionSeverity.LOW,
            KeyError: ExceptionSeverity.LOW,
            TypeError: ExceptionSeverity.MEDIUM,
            RuntimeError: ExceptionSeverity.MEDIUM,
            ConnectionError: ExceptionSeverity.HIGH,
            TimeoutError: ExceptionSeverity.HIGH,
            MemoryError: ExceptionSeverity.CRITICAL,
            SystemError: ExceptionSeverity.CRITICAL,
        }
        
        logger.info("异常处理中间件初始化完成")
    
    def register_alert_handler(self, handler: Callable):
        """注册告警处理器"""
        self._alert_handlers.append(handler)
    
    def _determine_severity(self, exception: Exception) -> ExceptionSeverity:
        """确定异常严重程度"""
        for exc_type, severity in self._severity_map.items():
            if isinstance(exception, exc_type):
                return severity
        return ExceptionSeverity.MEDIUM
    
    async def handle_exception(
        self,
        exception: Exception,
        context: Optional[ExceptionContext] = None,
        recovery_func: Optional[Callable] = None
    ) -> ExceptionRecord:
        """处理异常"""
        if context is None:
            context = ExceptionContext(
                trace_id=get_trace_id(),
                timestamp=time.time()
            )
        
        severity = self._determine_severity(exception)
        
        record = ExceptionRecord(
            exception_type=type(exception).__name__,
            exception_message=str(exception),
            severity=severity,
            context=context,
            stack_trace=traceback.format_exc()
        )
        
        await self.registry.add_record(record)
        
        self._recent_errors.append(time.time())
        self._recent_errors = [
            t for t in self._recent_errors 
            if time.time() - t < self.alert_window
        ]
        
        log_method = {
            ExceptionSeverity.LOW: logger.debug,
            ExceptionSeverity.MEDIUM: logger.warning,
            ExceptionSeverity.HIGH: logger.error,
            ExceptionSeverity.CRITICAL: logger.critical
        }.get(severity, logger.error)
        
        log_method(
            f"[{context.trace_id}] {severity.value.upper()}: "
            f"{type(exception).__name__} - {exception}\n"
            f"Context: agent={context.agent_id}, task={context.task_id}, "
            f"operation={context.operation}"
        )
        
        if len(self._recent_errors) >= self.alert_threshold:
            await self._trigger_alert(record)
        
        if recovery_func:
            try:
                await recovery_func(exception, context)
                record.recovered = True
                record.recovery_action = "recovery_function_executed"
                logger.info(f"[{context.trace_id}] 异常已恢复")
            except Exception as e:
                logger.error(f"[{context.trace_id}] 恢复失败: {e}")
        
        return record
    
    async def _trigger_alert(self, record: ExceptionRecord):
        """触发告警"""
        alert_message = (
            f"🚨 异常告警\n"
            f"类型: {record.exception_type}\n"
            f"严重程度: {record.severity.value}\n"
            f"消息: {record.exception_message}\n"
            f"追踪ID: {record.context.trace_id}\n"
            f"最近{self.alert_window}秒内发生{len(self._recent_errors)}次错误"
        )
        
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert_message, record)
                else:
                    handler(alert_message, record)
            except Exception as e:
                logger.error(f"告警处理器执行失败: {e}")
    
    def catch(
        self,
        severity: Optional[ExceptionSeverity] = None,
        recovery_func: Optional[Callable] = None,
        reraise: bool = False
    ):
        """异常捕获装饰器"""
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                trace_id = set_trace_id()
                
                context = ExceptionContext(
                    trace_id=trace_id,
                    timestamp=time.time(),
                    operation=f"{func.__module__}.{func.__qualname__}"
                )
                
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    record = await self.handle_exception(
                        e, context, recovery_func
                    )
                    if reraise:
                        raise
                    return {
                        "success": False,
                        "error": record.exception_message,
                        "trace_id": trace_id,
                        "severity": record.severity.value
                    }
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                trace_id = set_trace_id()
                
                context = ExceptionContext(
                    trace_id=trace_id,
                    timestamp=time.time(),
                    operation=f"{func.__module__}.{func.__qualname__}"
                )
                
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    record = asyncio.run(self.handle_exception(
                        e, context, recovery_func
                    ))
                    if reraise:
                        raise
                    return {
                        "success": False,
                        "error": record.exception_message,
                        "trace_id": trace_id,
                        "severity": record.severity.value
                    }
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    async def get_exception_stats(self) -> Dict[str, Any]:
        """获取异常统计"""
        return await self.registry.get_stats()


exception_middleware = ExceptionHandlerMiddleware()


def catch_exceptions(
    severity: Optional[ExceptionSeverity] = None,
    recovery_func: Optional[Callable] = None,
    reraise: bool = False
):
    """便捷装饰器函数"""
    return exception_middleware.catch(severity, recovery_func, reraise)
