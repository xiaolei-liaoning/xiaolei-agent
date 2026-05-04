"""
结构化日志系统

特性:
- JSON格式日志输出
- 请求追踪ID集成
- 上下文信息记录
- 性能指标记录
- 日志分级存储
- 敏感信息脱敏
"""

import logging
import json
import sys
import time
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum
from functools import wraps
import traceback


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogContext:
    """日志上下文"""
    trace_id: str = ""
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    operation: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {}
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.agent_id:
            result["agent_id"] = self.agent_id
        if self.task_id:
            result["task_id"] = self.task_id
        if self.user_id:
            result["user_id"] = self.user_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.operation:
            result["operation"] = self.operation
        if self.extra:
            result.update(self.extra)
        return result


@dataclass
class StructuredLog:
    """结构化日志记录"""
    timestamp: str
    level: str
    logger_name: str
    message: str
    context: Dict[str, Any]
    performance: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(asdict(self), ensure_ascii=False)


class SensitiveDataFilter:
    """敏感数据过滤器"""
    
    SENSITIVE_KEYS = {
        'password', 'passwd', 'pwd',
        'token', 'access_token', 'refresh_token',
        'secret', 'api_key', 'apikey',
        'credential', 'auth',
        'private_key', 'privatekey',
        'session_id', 'sessionid',
    }
    
    MASK = '******'
    
    @classmethod
    def mask_sensitive(cls, data: Any) -> Any:
        """脱敏敏感数据"""
        if isinstance(data, dict):
            return {
                k: cls.MASK if k.lower() in cls.SENSITIVE_KEYS else cls.mask_sensitive(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [cls.mask_sensitive(item) for item in data]
        elif isinstance(data, str):
            if len(data) > 100:
                return data[:50] + '...' + data[-20:]
        return data


class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器"""
    
    def __init__(
        self,
        include_performance: bool = True,
        include_stack_trace: bool = True,
        mask_sensitive: bool = True
    ):
        super().__init__()
        self.include_performance = include_performance
        self.include_stack_trace = include_stack_trace
        self.mask_sensitive = mask_sensitive
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        timestamp = datetime.fromtimestamp(record.created).isoformat()
        
        context = {}
        if hasattr(record, 'context') and record.context:
            context = record.context if isinstance(record.context, dict) else asdict(record.context)
        
        if hasattr(record, 'trace_id'):
            context['trace_id'] = record.trace_id
        if hasattr(record, 'agent_id'):
            context['agent_id'] = record.agent_id
        if hasattr(record, 'task_id'):
            context['task_id'] = record.task_id
        
        if self.mask_sensitive:
            context = SensitiveDataFilter.mask_sensitive(context)
        
        performance = None
        if self.include_performance and hasattr(record, 'performance'):
            performance = record.performance
        
        error = None
        if record.levelno >= logging.ERROR:
            error = {
                "type": record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info and record.exc_info[1] else None,
            }
            if self.include_stack_trace and record.exc_info:
                error["stack_trace"] = self.formatException(record.exc_info)
        
        structured_log = StructuredLog(
            timestamp=timestamp,
            level=record.levelname,
            logger_name=record.name,
            message=record.getMessage(),
            context=context,
            performance=performance,
            error=error
        )
        
        return structured_log.to_json()


class StructuredLogger:
    """结构化日志记录器"""
    
    def __init__(
        self,
        name: str,
        context: Optional[LogContext] = None,
        level: int = logging.INFO
    ):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.context = context or LogContext()
        self._timers: Dict[str, float] = {}
    
    def _log(
        self,
        level: int,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        performance: Optional[Dict[str, Any]] = None,
        exc_info: bool = False
    ):
        """内部日志方法"""
        extra = {}
        
        if self.context.trace_id:
            extra['trace_id'] = self.context.trace_id
        if self.context.agent_id:
            extra['agent_id'] = self.context.agent_id
        if self.context.task_id:
            extra['task_id'] = self.context.task_id
        
        if context:
            extra['context'] = context
        
        if performance:
            extra['performance'] = performance
        
        self.logger.log(level, message, extra=extra, exc_info=exc_info)
    
    def debug(self, message: str, **kwargs):
        """调试日志"""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """信息日志"""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """警告日志"""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, exc_info: bool = False, **kwargs):
        """错误日志"""
        self._log(logging.ERROR, message, exc_info=exc_info, **kwargs)
    
    def critical(self, message: str, exc_info: bool = False, **kwargs):
        """严重错误日志"""
        self._log(logging.CRITICAL, message, exc_info=exc_info, **kwargs)
    
    def start_timer(self, operation: str):
        """开始计时"""
        self._timers[operation] = time.time()
    
    def stop_timer(self, operation: str) -> float:
        """停止计时并返回耗时"""
        if operation not in self._timers:
            return 0.0
        
        elapsed = time.time() - self._timers.pop(operation)
        return elapsed
    
    def log_performance(
        self,
        operation: str,
        duration: float,
        success: bool = True,
        **kwargs
    ):
        """记录性能指标"""
        performance = {
            "operation": operation,
            "duration_ms": round(duration * 1000, 2),
            "success": success,
            **kwargs
        }
        self.info(f"性能统计: {operation}", performance=performance)
    
    def log_agent_action(
        self,
        agent_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """记录Agent行为"""
        context = {
            "agent_id": agent_id,
            "action": action
        }
        if details:
            context["details"] = details
        self.info(f"Agent行为: {action}", context=context)
    
    def log_task_event(
        self,
        task_id: str,
        event: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """记录任务事件"""
        context = {
            "task_id": task_id,
            "event": event
        }
        if details:
            context["details"] = details
        self.info(f"任务事件: {event}", context=context)
    
    def with_context(self, **kwargs) -> 'StructuredLogger':
        """创建带有额外上下文的日志记录器"""
        new_context = LogContext(
            trace_id=kwargs.get('trace_id', self.context.trace_id),
            agent_id=kwargs.get('agent_id', self.context.agent_id),
            task_id=kwargs.get('task_id', self.context.task_id),
            user_id=kwargs.get('user_id', self.context.user_id),
            session_id=kwargs.get('session_id', self.context.session_id),
            operation=kwargs.get('operation', self.context.operation),
            extra={**self.context.extra, **kwargs.get('extra', {})}
        )
        return StructuredLogger(self.logger.name, new_context)


def setup_structured_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    include_performance: bool = True,
    include_stack_trace: bool = True,
    mask_sensitive: bool = True
):
    """设置结构化日志系统"""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    root_logger.handlers.clear()
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(StructuredFormatter(
        include_performance=include_performance,
        include_stack_trace=include_stack_trace,
        mask_sensitive=mask_sensitive
    ))
    root_logger.addHandler(console_handler)
    
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(StructuredFormatter(
            include_performance=include_performance,
            include_stack_trace=include_stack_trace,
            mask_sensitive=mask_sensitive
        ))
        root_logger.addHandler(file_handler)
    
    return root_logger


def get_structured_logger(
    name: str,
    context: Optional[LogContext] = None
) -> StructuredLogger:
    """获取结构化日志记录器"""
    return StructuredLogger(name, context)


def log_function_call(logger: Optional[StructuredLogger] = None):
    """函数调用日志装饰器"""
    def decorator(func):
        nonlocal logger
        if logger is None:
            logger = get_structured_logger(func.__module__)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger.debug(
                f"调用函数: {func.__qualname__}",
                context={"args": str(args)[:100], "kwargs": str(kwargs)[:100]}
            )
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                logger.log_performance(
                    func.__qualname__,
                    duration,
                    success=True
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.log_performance(
                    func.__qualname__,
                    duration,
                    success=False
                )
                logger.error(f"函数执行失败: {func.__qualname__} - {e}", exc_info=True)
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger.debug(
                f"调用函数: {func.__qualname__}",
                context={"args": str(args)[:100], "kwargs": str(kwargs)[:100]}
            )
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.log_performance(
                    func.__qualname__,
                    duration,
                    success=True
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.log_performance(
                    func.__qualname__,
                    duration,
                    success=False
                )
                logger.error(f"函数执行失败: {func.__qualname__} - {e}", exc_info=True)
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
