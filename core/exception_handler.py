"""异常处理模块

实现全局异常捕获和统一响应封装
"""

import logging
from typing import Dict, Any, Callable, Type

logger = logging.getLogger(__name__)


class ExceptionHandler:
    """异常处理器"""
    
    def __init__(self):
        self.error_codes = {
            "NETWORK_ERROR": 1001,
            "PARAM_ERROR": 1002,
            "RESOURCE_ERROR": 1003,
            "CODE_ERROR": 1004,
            "TIMEOUT_ERROR": 1005,
            "SERVICE_ERROR": 1006,
            "AUTH_ERROR": 1007,
            "PERMISSION_ERROR": 1008
        }
        
        self.error_handlers = {}
        self._register_default_handlers()
        logger.info("异常处理器初始化完成")
    
    def _register_default_handlers(self):
        """注册默认异常处理器"""
        # 网络错误处理器
        async def network_error_handler(exception: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "success": False,
                "code": self.error_codes["NETWORK_ERROR"],
                "message": "网络连接错误",
                "details": str(exception)
            }
        
        # 参数错误处理器
        async def param_error_handler(exception: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "success": False,
                "code": self.error_codes["PARAM_ERROR"],
                "message": "参数错误",
                "details": str(exception)
            }
        
        # 资源错误处理器
        async def resource_error_handler(exception: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "success": False,
                "code": self.error_codes["RESOURCE_ERROR"],
                "message": "系统资源不足",
                "details": str(exception)
            }
        
        # 代码错误处理器
        async def code_error_handler(exception: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "success": False,
                "code": self.error_codes["CODE_ERROR"],
                "message": "代码执行错误",
                "details": str(exception)
            }
        
        # 超时错误处理器
        async def timeout_error_handler(exception: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "success": False,
                "code": self.error_codes["TIMEOUT_ERROR"],
                "message": "任务执行超时",
                "details": str(exception)
            }
        
        # 服务错误处理器
        async def service_error_handler(exception: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "success": False,
                "code": self.error_codes["SERVICE_ERROR"],
                "message": "服务错误",
                "details": str(exception)
            }
        
        # 注册默认处理器
        self.register_error_handler(ConnectionError, network_error_handler)
        self.register_error_handler(ValueError, param_error_handler)
        self.register_error_handler(ResourceError, resource_error_handler)
        self.register_error_handler(Exception, code_error_handler)
    
    async def handle_exception(self, exception: Exception, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理异常
        
        Args:
            exception: 异常对象
            context: 上下文信息
            
        Returns:
            错误响应
        """
        if context is None:
            context = {}
        
        logger.error(f"处理异常: {type(exception).__name__} - {exception}", exc_info=True)
        
        # 查找对应的处理器
        for exception_type, handler in self.error_handlers.items():
            if isinstance(exception, exception_type):
                return await handler(exception, context)
        
        # 默认处理器
        return {
            "success": False,
            "code": self.error_codes["CODE_ERROR"],
            "message": "未知错误",
            "details": str(exception)
        }
    
    def register_error_handler(self, error_type: Type[Exception], handler: Callable[[Exception, Dict[str, Any]], Dict[str, Any]]):
        """注册错误处理器
        
        Args:
            error_type: 错误类型
            handler: 错误处理器
        """
        self.error_handlers[error_type] = handler
        logger.info(f"注册错误处理器: {error_type.__name__}")
    
    def get_error_code(self, error_name: str) -> int:
        """获取错误代码
        
        Args:
            error_name: 错误名称
            
        Returns:
            错误代码
        """
        return self.error_codes.get(error_name, 1004)
    
    def get_error_message(self, error_code: int) -> str:
        """获取错误消息
        
        Args:
            error_code: 错误代码
            
        Returns:
            错误消息
        """
        error_messages = {
            1001: "网络连接错误",
            1002: "参数错误",
            1003: "系统资源不足",
            1004: "代码执行错误",
            1005: "任务执行超时",
            1006: "服务错误",
            1007: "认证错误",
            1008: "权限错误"
        }
        return error_messages.get(error_code, "未知错误")


class ResourceError(Exception):
    """资源错误"""
    pass


class ServiceError(Exception):
    """服务错误"""
    pass


class AuthError(Exception):
    """认证错误"""
    pass


class PermissionError(Exception):
    """权限错误"""
    pass


# 全局异常处理器实例
exception_handler = ExceptionHandler()