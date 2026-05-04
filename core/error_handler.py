"""标准化错误处理机制

特性:
- 完整的错误码体系
- 统一的错误响应格式
- 错误等级分类
- 错误上下文信息
- 错误追踪ID

使用方式:
    from core.error_handler import ErrorCode, ErrorResponse, AppException
    
    raise AppException(
        code=ErrorCode.SKILL_NOT_FOUND,
        message="技能不存在",
        details={"skill_name": "unknown_skill"}
    )
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """错误类别"""
    SYSTEM = "SYSTEM"           # 系统级错误
    BUSINESS = "BUSINESS"       # 业务级错误
    NETWORK = "NETWORK"         # 网络错误
    DATABASE = "DATABASE"       # 数据库错误
    EXTERNAL = "EXTERNAL"       # 外部服务错误
    VALIDATION = "VALIDATION"   # 验证错误
    AUTH = "AUTH"               # 认证授权错误
    RATE_LIMIT = "RATE_LIMIT"   # 限流错误


class ErrorLevel(Enum):
    """错误等级"""
    INFO = "INFO"           # 信息提示
    WARNING = "WARNING"     # 警告
    ERROR = "ERROR"         # 错误
    CRITICAL = "CRITICAL"   # 严重错误


class ErrorCode(Enum):
    """错误码定义
    
    格式: [类别][模块][序号]
    - 类别: 1=系统, 2=业务, 3=网络, 4=数据库, 5=外部, 6=验证, 7=认证, 8=限流
    - 模块: 01=通用, 02=用户, 03=任务, 04=技能, 05=Agent, 06=配置
    - 序号: 001-999
    """
    
    # 系统错误 (1xxxxx)
    SYSTEM_INTERNAL_ERROR = ("10001", "系统内部错误", ErrorCategory.SYSTEM, ErrorLevel.CRITICAL)
    SYSTEM_NOT_INITIALIZED = ("10002", "系统未初始化", ErrorCategory.SYSTEM, ErrorLevel.ERROR)
    SYSTEM_SHUTDOWN = ("10003", "系统正在关闭", ErrorCategory.SYSTEM, ErrorLevel.WARNING)
    SYSTEM_CONFIG_ERROR = ("10004", "配置错误", ErrorCategory.SYSTEM, ErrorLevel.ERROR)
    SYSTEM_RESOURCE_EXHAUSTED = ("10005", "资源耗尽", ErrorCategory.SYSTEM, ErrorLevel.CRITICAL)
    
    # 业务错误 (2xxxxx)
    BUSINESS_RULE_VIOLATION = ("20001", "业务规则违反", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    BUSINESS_STATE_ERROR = ("20002", "业务状态错误", ErrorCategory.BUSINESS, ErrorLevel.ERROR)
    
    # 用户相关 (202xx)
    USER_NOT_FOUND = ("20201", "用户不存在", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    USER_ALREADY_EXISTS = ("20202", "用户已存在", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    USER_INVALID_CREDENTIALS = ("20203", "用户名或密码错误", ErrorCategory.AUTH, ErrorLevel.WARNING)
    USER_PERMISSION_DENIED = ("20204", "权限不足", ErrorCategory.AUTH, ErrorLevel.ERROR)
    USER_TOKEN_EXPIRED = ("20205", "令牌已过期", ErrorCategory.AUTH, ErrorLevel.WARNING)
    USER_TOKEN_INVALID = ("20206", "无效令牌", ErrorCategory.AUTH, ErrorLevel.WARNING)
    
    # 任务相关 (203xx)
    TASK_NOT_FOUND = ("20301", "任务不存在", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    TASK_ALREADY_COMPLETED = ("20302", "任务已完成", ErrorCategory.BUSINESS, ErrorLevel.INFO)
    TASK_EXECUTION_FAILED = ("20303", "任务执行失败", ErrorCategory.BUSINESS, ErrorLevel.ERROR)
    TASK_TIMEOUT = ("20304", "任务执行超时", ErrorCategory.BUSINESS, ErrorLevel.ERROR)
    TASK_CANCELED = ("20305", "任务已取消", ErrorCategory.BUSINESS, ErrorLevel.INFO)
    TASK_DEPENDENCY_ERROR = ("20306", "任务依赖错误", ErrorCategory.BUSINESS, ErrorLevel.ERROR)
    
    # 技能相关 (204xx)
    SKILL_NOT_FOUND = ("20401", "技能不存在", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    SKILL_EXECUTION_FAILED = ("20402", "技能执行失败", ErrorCategory.BUSINESS, ErrorLevel.ERROR)
    SKILL_NOT_REGISTERED = ("20403", "技能未注册", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    SKILL_PARAMETER_ERROR = ("20404", "技能参数错误", ErrorCategory.VALIDATION, ErrorLevel.WARNING)
    
    # Agent相关 (205xx)
    AGENT_NOT_FOUND = ("20501", "Agent不存在", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    AGENT_UNAVAILABLE = ("20502", "Agent不可用", ErrorCategory.BUSINESS, ErrorLevel.ERROR)
    AGENT_OVERLOADED = ("20503", "Agent过载", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    AGENT_CIRCUIT_OPEN = ("20504", "Agent熔断中", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    
    # 网络错误 (3xxxxx)
    NETWORK_CONNECTION_ERROR = ("30001", "网络连接错误", ErrorCategory.NETWORK, ErrorLevel.ERROR)
    NETWORK_TIMEOUT = ("30002", "网络请求超时", ErrorCategory.NETWORK, ErrorLevel.ERROR)
    NETWORK_DNS_ERROR = ("30003", "DNS解析失败", ErrorCategory.NETWORK, ErrorLevel.ERROR)
    
    # 数据库错误 (4xxxxx)
    DATABASE_CONNECTION_ERROR = ("40001", "数据库连接错误", ErrorCategory.DATABASE, ErrorLevel.CRITICAL)
    DATABASE_QUERY_ERROR = ("40002", "数据库查询错误", ErrorCategory.DATABASE, ErrorLevel.ERROR)
    DATABASE_TRANSACTION_ERROR = ("40003", "数据库事务错误", ErrorCategory.DATABASE, ErrorLevel.ERROR)
    DATABASE_NOT_INITIALIZED = ("40004", "数据库未初始化", ErrorCategory.DATABASE, ErrorLevel.ERROR)
    
    # 外部服务错误 (5xxxxx)
    EXTERNAL_SERVICE_ERROR = ("50001", "外部服务错误", ErrorCategory.EXTERNAL, ErrorLevel.ERROR)
    EXTERNAL_SERVICE_TIMEOUT = ("50002", "外部服务超时", ErrorCategory.EXTERNAL, ErrorLevel.ERROR)
    EXTERNAL_SERVICE_UNAVAILABLE = ("50003", "外部服务不可用", ErrorCategory.EXTERNAL, ErrorLevel.ERROR)
    EXTERNAL_API_ERROR = ("50004", "外部API错误", ErrorCategory.EXTERNAL, ErrorLevel.ERROR)
    
    # LLM相关 (501xx)
    LLM_API_ERROR = ("50101", "LLM API错误", ErrorCategory.EXTERNAL, ErrorLevel.ERROR)
    LLM_RATE_LIMITED = ("50102", "LLM请求限流", ErrorCategory.RATE_LIMIT, ErrorLevel.WARNING)
    LLM_CONTEXT_TOO_LONG = ("50103", "上下文过长", ErrorCategory.BUSINESS, ErrorLevel.WARNING)
    
    # 验证错误 (6xxxxx)
    VALIDATION_ERROR = ("60001", "验证错误", ErrorCategory.VALIDATION, ErrorLevel.WARNING)
    VALIDATION_REQUIRED_FIELD = ("60002", "必填字段缺失", ErrorCategory.VALIDATION, ErrorLevel.WARNING)
    VALIDATION_INVALID_FORMAT = ("60003", "格式无效", ErrorCategory.VALIDATION, ErrorLevel.WARNING)
    VALIDATION_OUT_OF_RANGE = ("60004", "值超出范围", ErrorCategory.VALIDATION, ErrorLevel.WARNING)
    
    # 限流错误 (8xxxxx)
    RATE_LIMIT_EXCEEDED = ("80001", "请求频率超限", ErrorCategory.RATE_LIMIT, ErrorLevel.WARNING)
    RATE_LIMIT_GLOBAL = ("80002", "全局请求限流", ErrorCategory.RATE_LIMIT, ErrorLevel.WARNING)
    
    def __init__(
        self, 
        code: str, 
        message: str, 
        category: ErrorCategory, 
        level: ErrorLevel
    ):
        self.code = code
        self.message = message
        self.category = category
        self.level = level
    
    @property
    def http_status(self) -> int:
        """获取对应的HTTP状态码"""
        if self.category == ErrorCategory.AUTH:
            if "TOKEN" in self.name:
                return 401
            return 403
        elif self.category == ErrorCategory.VALIDATION:
            return 400
        elif self.category == ErrorCategory.RATE_LIMIT:
            return 429
        elif self.category == ErrorCategory.DATABASE:
            return 503
        elif self.category == ErrorCategory.EXTERNAL:
            return 502
        elif self.level == ErrorLevel.CRITICAL:
            return 500
        elif "NOT_FOUND" in self.name:
            return 404
        return 400


@dataclass
class ErrorDetail:
    """错误详情"""
    field: Optional[str] = None
    value: Optional[Any] = None
    message: Optional[str] = None
    constraint: Optional[str] = None


@dataclass
class ErrorResponse:
    """统一错误响应格式"""
    success: bool = False
    code: str = ""
    message: str = ""
    category: str = ""
    level: str = ""
    details: List[ErrorDetail] = field(default_factory=list)
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    suggestion: Optional[str] = None
    documentation_url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "error": {
                "code": self.code,
                "message": self.message,
                "category": self.category,
                "level": self.level,
                "details": [
                    {
                        "field": d.field,
                        "value": str(d.value) if d.value is not None else None,
                        "message": d.message,
                        "constraint": d.constraint
                    }
                    for d in self.details
                ],
                "trace_id": self.trace_id,
                "timestamp": self.timestamp,
                "suggestion": self.suggestion,
                "documentation_url": self.documentation_url
            }
        }
    
    @classmethod
    def from_exception(cls, exc: AppException) -> ErrorResponse:
        """从异常创建响应"""
        return cls(
            success=False,
            code=exc.code.code,
            message=exc.message or exc.code.message,
            category=exc.code.category.value,
            level=exc.code.level.value,
            details=exc.details,
            trace_id=exc.trace_id,
            suggestion=exc.suggestion,
            documentation_url=exc.documentation_url
        )


class AppException(Exception):
    """应用异常基类"""
    
    def __init__(
        self,
        code: ErrorCode,
        message: Optional[str] = None,
        details: Optional[List[ErrorDetail]] = None,
        suggestion: Optional[str] = None,
        documentation_url: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        self.code = code
        self.message = message or code.message
        self.details = details or []
        self.suggestion = suggestion
        self.documentation_url = documentation_url
        self.cause = cause
        self.trace_id = str(uuid.uuid4())[:8]
        self.timestamp = time.time()
        
        super().__init__(self.message)
        
        logger.error(
            f"[{self.trace_id}] {code.code} - {self.message}",
            extra={
                "error_code": code.code,
                "error_category": code.category.value,
                "error_level": code.level.value,
                "trace_id": self.trace_id
            }
        )
    
    def to_response(self) -> ErrorResponse:
        """转换为错误响应"""
        return ErrorResponse.from_exception(self)
    
    @property
    def http_status(self) -> int:
        """获取HTTP状态码"""
        return self.code.http_status


class ValidationException(AppException):
    """验证异常"""
    
    def __init__(
        self,
        field: str,
        value: Any,
        message: str,
        constraint: Optional[str] = None
    ):
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            details=[ErrorDetail(
                field=field,
                value=value,
                message=message,
                constraint=constraint
            )]
        )


class NotFoundException(AppException):
    """资源未找到异常"""
    
    def __init__(
        self,
        resource_type: str,
        resource_id: Any,
        suggestion: Optional[str] = None
    ):
        code_map = {
            "user": ErrorCode.USER_NOT_FOUND,
            "task": ErrorCode.TASK_NOT_FOUND,
            "skill": ErrorCode.SKILL_NOT_FOUND,
            "agent": ErrorCode.AGENT_NOT_FOUND,
        }
        
        code = code_map.get(resource_type.lower(), ErrorCode.TASK_NOT_FOUND)
        
        super().__init__(
            code=code,
            message=f"{resource_type}不存在: {resource_id}",
            suggestion=suggestion
        )


class RateLimitException(AppException):
    """限流异常"""
    
    def __init__(
        self,
        limit: int,
        window: int,
        retry_after: int
    ):
        super().__init__(
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message=f"请求频率超限，{window}秒内最多允许{limit}次请求",
            suggestion=f"请{retry_after}秒后重试"
        )
        self.retry_after = retry_after


def handle_errors(func):
    """错误处理装饰器"""
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AppException as e:
            raise e
        except ValueError as e:
            raise ValidationException(
                field="unknown",
                value=None,
                message=str(e)
            )
        except Exception as e:
            logger.exception(f"未处理的异常: {e}")
            raise AppException(
                code=ErrorCode.SYSTEM_INTERNAL_ERROR,
                message=str(e),
                cause=e
            )
    
    return wrapper
