"""响应管理器模块

实现统一响应封装
"""

from typing import Dict, Any, Optional


class ResponseManager:
    """响应管理器"""
    
    def __init__(self):
        self.response_templates = {
            "success": {
                "success": True,
                "code": 200,
                "message": "Success",
                "data": None
            },
            "error": {
                "success": False,
                "code": 500,
                "message": "Internal Server Error",
                "details": None
            }
        }
    
    def success(self, data: Any = None, message: str = "Success") -> Dict[str, Any]:
        """成功响应
        
        Args:
            data: 响应数据
            message: 响应消息
            
        Returns:
            成功响应
        """
        response = self.response_templates["success"].copy()
        response["message"] = message
        response["data"] = data
        return response
    
    def error(self, code: int, message: str, details: Any = None) -> Dict[str, Any]:
        """错误响应
        
        Args:
            code: 错误代码
            message: 错误消息
            details: 错误详情
            
        Returns:
            错误响应
        """
        response = self.response_templates["error"].copy()
        response["code"] = code
        response["message"] = message
        response["details"] = details
        return response
    
    def pagination(self, data: Any, total: int, page: int, page_size: int) -> Dict[str, Any]:
        """分页响应
        
        Args:
            data: 数据列表
            total: 总数据量
            page: 当前页码
            page_size: 每页数据量
            
        Returns:
            分页响应
        """
        return self.success({
            "items": data,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
        })
    
    def validation_error(self, errors: Dict[str, str]) -> Dict[str, Any]:
        """验证错误响应
        
        Args:
            errors: 验证错误信息
            
        Returns:
            验证错误响应
        """
        return self.error(
            code=400,
            message="Validation Error",
            details=errors
        )
    
    def unauthorized(self, message: str = "Unauthorized") -> Dict[str, Any]:
        """未授权响应
        
        Args:
            message: 错误消息
            
        Returns:
            未授权响应
        """
        return self.error(
            code=401,
            message=message
        )
    
    def forbidden(self, message: str = "Forbidden") -> Dict[str, Any]:
        """禁止访问响应
        
        Args:
            message: 错误消息
            
        Returns:
            禁止访问响应
        """
        return self.error(
            code=403,
            message=message
        )
    
    def not_found(self, message: str = "Not Found") -> Dict[str, Any]:
        """资源不存在响应
        
        Args:
            message: 错误消息
            
        Returns:
            资源不存在响应
        """
        return self.error(
            code=404,
            message=message
        )
    
    def timeout(self, message: str = "Request Timeout") -> Dict[str, Any]:
        """请求超时响应
        
        Args:
            message: 错误消息
            
        Returns:
            请求超时响应
        """
        return self.error(
            code=408,
            message=message
        )
    
    def too_many_requests(self, message: str = "Too Many Requests") -> Dict[str, Any]:
        """请求过多响应
        
        Args:
            message: 错误消息
            
        Returns:
            请求过多响应
        """
        return self.error(
            code=429,
            message=message
        )


# 全局响应管理器实例
response_manager = ResponseManager()