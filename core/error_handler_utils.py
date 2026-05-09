"""统一错误处理和重试机制模块"""

import asyncio
import logging
import functools
import time
from typing import Callable, Any, Optional, Type, Tuple, TypeVar
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


class LogLevel(Enum):
    """标准化日志级别"""
    DEBUG = "debug"      # 详细调试信息
    INFO = "info"        # 一般信息
    WARNING = "warning"  # 警告（可恢复的错误）
    ERROR = "error"     # 错误（需要处理）
    CRITICAL = "critical"  # 严重错误（可能导致系统故障）


@dataclass
class ErrorInfo:
    """错误信息结构"""
    error_type: str
    message: str
    module: str
    function: str
    timestamp: str
    recoverable: bool = False
    retry_count: int = 0


class ErrorHandler:
    """统一错误处理器"""

    # 错误类型到日志级别的映射
    ERROR_LEVEL_MAP = {
        "TimeoutError": LogLevel.WARNING,
        "ConnectionError": LogLevel.WARNING,
        "NetworkError": LogLevel.WARNING,
        "RetryExhausted": LogLevel.ERROR,
        "ValidationError": LogLevel.WARNING,
        "AuthError": LogLevel.ERROR,
        "PermissionError": LogLevel.ERROR,
        "NotFoundError": LogLevel.WARNING,
        "RateLimitError": LogLevel.WARNING,
        "ServerError": LogLevel.ERROR,
        "UnknownError": LogLevel.ERROR,
    }

    # 可恢复错误（值得重试）
    RECOVERABLE_ERRORS = (
        "TimeoutError",
        "ConnectionError",
        "NetworkError",
        "RateLimitError",
        "ServerError",
    )

    @classmethod
    def get_log_level(cls, error_type: str) -> LogLevel:
        """获取错误对应的日志级别"""
        return cls.ERROR_LEVEL_MAP.get(error_type, LogLevel.ERROR)

    @classmethod
    def is_recoverable(cls, error_type: str) -> bool:
        """判断错误是否可恢复"""
        return error_type in cls.RECOVERABLE_ERRORS

    @classmethod
    def format_error(cls, error: Exception, module: str = "", function: str = "") -> ErrorInfo:
        """格式化错误信息"""
        error_type = type(error).__name__
        return ErrorInfo(
            error_type=error_type,
            message=str(error),
            module=module or error.__class__.__module__,
            function=function,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            recoverable=cls.is_recoverable(error_type),
        )

    @classmethod
    def log_error(cls, error: Exception, module: str = "", function: str = "",
                   extra_info: str = ""):
        """统一错误日志记录"""
        error_info = cls.format_error(error, module, function)
        log_level = cls.get_log_level(error_info.error_type)

        log_message = f"[{error_info.error_type}] {error_info.message}"
        if extra_info:
            log_message += f" | {extra_info}"
        log_message += f" | 模块: {error_info.module}.{error_info.function}"

        if log_level == LogLevel.DEBUG:
            logger.debug(log_message)
        elif log_level == LogLevel.INFO:
            logger.info(log_message)
        elif log_level == LogLevel.WARNING:
            logger.warning(log_message)
        elif log_level == LogLevel.ERROR:
            logger.error(log_message)
        else:
            logger.critical(log_message)

        return error_info


def retry_on_error(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    log_retry: bool = True,
):
    """重试装饰器

    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 退避倍数
        exceptions: 需要重试的异常类型
        log_retry: 是否记录重试日志
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt >= max_retries:
                        if log_retry:
                            ErrorHandler.log_error(
                                e, module=func.__module__, function=func.__name__,
                                extra_info=f"重试{attempt}次后失败"
                            )
                        raise

                    if log_retry:
                        logger.warning(
                            f"[{func.__name__}] 第{attempt + 1}次尝试失败: {e}, "
                            f"{current_delay:.1f}秒后重试..."
                        )

                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt >= max_retries:
                        if log_retry:
                            ErrorHandler.log_error(
                                e, module=func.__module__, function=func.__name__,
                                extra_info=f"重试{attempt}次后失败"
                            )
                        raise

                    if log_retry:
                        logger.warning(
                            f"[{func.__name__}] 第{attempt + 1}次尝试失败: {e}, "
                            f"{current_delay:.1f}秒后重试..."
                        )

                    time.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def handle_errors(
    default_return: Any = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    log_level: str = "error",
    error_message: str = "",
):
    """错误处理装饰器

    Args:
        default_return: 错误时的默认返回值
        exceptions: 要捕获的异常类型
        log_level: 日志级别 (debug/info/warning/error/critical)
        error_message: 自定义错误消息
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                error_info = ErrorHandler.log_error(
                    e, module=func.__module__, function=func.__name__,
                    extra_info=error_message
                )

                if not error_info.recoverable:
                    logger.error(
                        f"[{func.__name__}] 不可恢复错误: {e}"
                    )

                return default_return

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                error_info = ErrorHandler.log_error(
                    e, module=func.__module__, function=func.__name__,
                    extra_info=error_message
                )

                if not error_info.recoverable:
                    logger.error(
                        f"[{func.__name__}] 不可恢复错误: {e}"
                    )

                return default_return

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class CircuitBreaker:
    """熔断器 - 防止故障扩散"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "closed"  # closed, open, half_open

    @property
    def state(self) -> str:
        """获取当前状态"""
        if self._state == "open":
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = "half_open"
                logger.info("[CircuitBreaker] 进入半开状态")
        return self._state

    def is_available(self) -> bool:
        """检查是否可用"""
        return self.state != "open"

    def record_success(self):
        """记录成功"""
        if self._state == "half_open":
            logger.info("[CircuitBreaker] 恢复成功，关闭熔断器")
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        """记录失败"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                f"[CircuitBreaker] 熔断器打开，"
                f"失败次数: {self._failure_count}, "
                f"将在{self.recovery_timeout}秒后尝试恢复"
            )

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """带熔断保护的调用"""
        if not self.is_available():
            raise Exception(f"CircuitBreaker opened, call rejected")

        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except self.expected_exception as e:
            self.record_failure()
            raise


class ErrorRecovery:
    """错误恢复策略"""

    @staticmethod
    async def retry_with_fallback(
        primary_func: Callable,
        fallback_func: Callable,
        max_retries: int = 3,
    ) -> Any:
        """主函数失败时使用备用函数"""
        last_error = None

        for attempt in range(max_retries):
            try:
                return await primary_func()
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(f"主函数失败，尝试备用函数: {e}")
                    await asyncio.sleep(1 * (attempt + 1))

        logger.warning("主函数完全失败，使用备用函数")
        return await fallback_func()

    @staticmethod
    def graceful_degrade(error: Exception, default_value: Any = None) -> Any:
        """优雅降级 - 发生错误时返回默认值"""
        ErrorHandler.log_error(error)
        logger.info(f"优雅降级，返回默认值: {default_value}")
        return default_value
