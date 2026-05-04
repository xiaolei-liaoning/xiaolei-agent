"""错误码定义模块

统一的错误码和错误处理规范
"""

from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class ErrorInfo:
    """错误信息"""
    code: str
    message: str
    http_status: int
    detail: str = ""


class ErrorCode(Enum):
    """错误码枚举"""
    
    # 通用错误 (1xxx)
    SUCCESS = ErrorInfo("0000", "成功", 200)
    UNKNOWN_ERROR = ErrorInfo("1000", "未知错误", 500)
    INVALID_PARAMETER = ErrorInfo("1001", "参数错误", 400)
    UNAUTHORIZED = ErrorInfo("1002", "未授权", 401)
    FORBIDDEN = ErrorInfo("1003", "禁止访问", 403)
    NOT_FOUND = ErrorInfo("1004", "资源不存在", 404)
    TOO_MANY_REQUESTS = ErrorInfo("1005", "请求过于频繁", 429)
    SERVICE_UNAVAILABLE = ErrorInfo("1006", "服务暂时不可用", 503)
    
    # 用户相关 (2xxx)
    USER_NOT_FOUND = ErrorInfo("2000", "用户不存在", 404)
    USER_ALREADY_EXISTS = ErrorInfo("2001", "用户已存在", 400)
    INVALID_PASSWORD = ErrorInfo("2002", "密码错误", 401)
    INVALID_TOKEN = ErrorInfo("2003", "Token无效或已过期", 401)
    
    # LLM相关 (3xxx)
    LLM_CALL_FAILED = ErrorInfo("3000", "LLM调用失败", 500)
    LLM_TIMEOUT = ErrorInfo("3001", "LLM调用超时", 504)
    LLM_QUOTA_EXCEEDED = ErrorInfo("3002", "LLM配额已用完", 429)
    
    # 搜索相关 (4xxx)
    SEARCH_FAILED = ErrorInfo("4000", "搜索失败", 500)
    SEARCH_TIMEOUT = ErrorInfo("4001", "搜索超时", 504)
    
    # 数据库相关 (5xxx)
    DATABASE_ERROR = ErrorInfo("5000", "数据库错误", 500)
    DATABASE_CONNECTION_FAILED = ErrorInfo("5001", "数据库连接失败", 503)
    
    # Agent相关 (6xxx)
    AGENT_EXECUTION_FAILED = ErrorInfo("6000", "Agent执行失败", 500)
    AGENT_TIMEOUT = ErrorInfo("6001", "Agent执行超时", 504)
    
    # 技能相关 (7xxx)
    SKILL_NOT_FOUND = ErrorInfo("7000", "技能不存在", 404)
    SKILL_EXECUTION_FAILED = ErrorInfo("7001", "技能执行失败", 500)


def create_error_response(
    error_code: ErrorCode,
    detail: str = "",
    extra: Dict[str, Any] = None
) -> Dict[str, Any]:
    """创建错误响应"""
    info = error_code.value
    result = {
        "success": False,
        "error": {
            "code": info.code,
            "message": info.message,
            "detail": detail or info.detail
        }
    }
    if extra:
        result["error"]["extra"] = extra
    return result

