#!/usr/bin/env python3
"""
安全管理模块

实现系统安全功能，包括：
1. 输入验证
2. 权限管理
3. 数据安全保护
4. 安全审计
"""

import hashlib
import hmac
import secrets
import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import jwt

logger = logging.getLogger(__name__)


class SecurityManager:
    """安全管理器"""
    
    def __init__(self):
        self.secret_key = secrets.token_hex(32)
        self.allowed_origins = set()
        self.api_keys = set()
        self.user_roles = {}
        self.session_tokens = {}
        logger.info("安全管理器初始化完成")
    
    def validate_input(self, input_data: Any, input_type: str = "string") -> bool:
        """验证输入数据
        
        Args:
            input_data: 输入数据
            input_type: 输入类型
            
        Returns:
            是否有效
        """
        try:
            if input_type == "string":
                if not isinstance(input_data, str):
                    return False
                # 检查字符串长度
                if len(input_data) > 10000:
                    return False
                # 检查XSS攻击模式
                xss_patterns = [
                    r'<script[^>]*>.*?</script>',
                    r'on\w+\s*=\s*["\']?[^"\'>]+["\']?',
                    r'javascript:',
                    r'vbscript:',
                ]
                for pattern in xss_patterns:
                    if re.search(pattern, input_data, re.IGNORECASE):
                        return False
                # 检查命令注入模式
                command_injection_patterns = [
                    r';\s*(rm|del|mkdir|rmdir|cp|mv|chmod|chown)',
                    r'\$\(.*\)',
                    r'`.*`',
                    r'&.*&',
                    r'\|.*\|',
                    r'>>.*',
                    r'>.*',
                    r'<.*',
                    r'__import__\(',
                    r'system\(',
                    r'exec\(',
                    r'eval\(',
                ]
                for pattern in command_injection_patterns:
                    if re.search(pattern, input_data):
                        return False
                return True
            
            elif input_type == "email":
                if not isinstance(input_data, str):
                    return False
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                return bool(re.match(email_pattern, input_data))
            
            elif input_type == "url":
                if not isinstance(input_data, str):
                    return False
                url_pattern = r'^https?://[\w\-._~:/?#[\]@!$&\'()*+,;=.]+$'
                return bool(re.match(url_pattern, input_data))
            
            elif input_type == "integer":
                return isinstance(input_data, int) and input_data >= 0
            
            elif input_type == "boolean":
                return isinstance(input_data, bool)
            
            elif input_type == "list":
                return isinstance(input_data, list)
            
            elif input_type == "dict":
                return isinstance(input_data, dict)
            
            return False
        except Exception as e:
            logger.error(f"输入验证失败: {e}")
            return False
    
    def validate_message(self, message: str) -> Dict[str, Any]:
        """验证用户消息
        
        Args:
            message: 用户消息
            
        Returns:
            验证结果
        """
        result = {
            "valid": True,
            "message": "",
            "risk_level": "low"
        }
        
        if not message:
            result["valid"] = False
            result["message"] = "消息不能为空"
            return result
        
        if len(message) > 1000:
            result["valid"] = False
            result["message"] = "消息长度不能超过1000字符"
            return result
        
        # 检查敏感内容
        sensitive_patterns = [
            r'password|密码',
            r'credit card|信用卡',
            r'social security|社保号',
            r'bank account|银行账户',
            r'private key|私钥',
            r'api key|API密钥'
        ]
        
        for pattern in sensitive_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                result["risk_level"] = "high"
                result["message"] = "消息包含敏感内容"
                break
        
        return result
    
    def generate_api_key(self) -> str:
        """生成API密钥
        
        Returns:
            API密钥
        """
        api_key = secrets.token_urlsafe(32)
        self.api_keys.add(api_key)
        return api_key
    
    def validate_api_key(self, api_key: str) -> bool:
        """验证API密钥
        
        Args:
            api_key: API密钥
            
        Returns:
            是否有效
        """
        return api_key in self.api_keys
    
    def generate_session_token(self, user_id: str) -> str:
        """生成会话令牌
        
        Args:
            user_id: 用户ID
            
        Returns:
            会话令牌
        """
        token = secrets.token_urlsafe(32)
        self.session_tokens[token] = {
            "user_id": user_id,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(hours=24)
        }
        return token
    
    def validate_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证会话令牌
        
        Args:
            token: 会话令牌
            
        Returns:
            会话信息，如果无效则返回None
        """
        if token not in self.session_tokens:
            return None
        
        session = self.session_tokens[token]
        if datetime.now() > session["expires_at"]:
            del self.session_tokens[token]
            return None
        
        return session
    
    def hash_password(self, password: str) -> str:
        """哈希密码
        
        Args:
            password: 原始密码
            
        Returns:
            哈希后的密码
        """
        salt = secrets.token_hex(16)
        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return f"{salt}:{hashed.hex()}"
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """验证密码
        
        Args:
            password: 原始密码
            hashed_password: 哈希后的密码
            
        Returns:
            是否匹配
        """
        try:
            salt, hashed = hashed_password.split(':')
            new_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return new_hash.hex() == hashed
        except Exception:
            return False
    
    def generate_jwt(self, user_id: str, role: str) -> str:
        """生成JWT令牌
        
        Args:
            user_id: 用户ID
            role: 用户角色
            
        Returns:
            JWT令牌
        """
        payload = {
            "user_id": user_id,
            "role": role,
            "exp": datetime.utcnow() + timedelta(hours=24),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
    
    def decode_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        """解码JWT令牌
        
        Args:
            token: JWT令牌
            
        Returns:
            令牌载荷，如果无效则返回None
        """
        try:
            return jwt.decode(token, self.secret_key, algorithms=["HS256"])
        except Exception:
            return None
    
    def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        """检查权限
        
        Args:
            user_id: 用户ID
            resource: 资源
            action: 操作
            
        Returns:
            是否有权限
        """
        role = self.user_roles.get(user_id, "user")
        
        # 权限矩阵
        permissions = {
            "admin": {
                "*": ["*"]  # 管理员可以访问所有资源的所有操作
            },
            "user": {
                "tasks": ["submit", "view"],
                "agents": ["view"],
                "monitoring": ["view"]
            }
        }
        
        if role not in permissions:
            return False
        
        role_permissions = permissions[role]
        if "*" in role_permissions:
            return True
        
        if resource not in role_permissions:
            return False
        
        resource_permissions = role_permissions[resource]
        if "*" in resource_permissions:
            return True
        
        return action in resource_permissions
    
    def sanitize_output(self, output: str) -> str:
        """清理输出内容
        
        Args:
            output: 输出内容
            
        Returns:
            清理后的内容
        """
        if not isinstance(output, str):
            return str(output)
        
        # 转义HTML特殊字符
        sanitized = output.replace('&', '&amp;')
        sanitized = sanitized.replace('<', '&lt;')
        sanitized = sanitized.replace('>', '&gt;')
        sanitized = sanitized.replace('"', '&quot;')
        sanitized = sanitized.replace("'", '&#x27;')
        
        return sanitized
    
    def add_allowed_origin(self, origin: str):
        """添加允许的来源
        
        Args:
            origin: 来源URL
        """
        self.allowed_origins.add(origin)
    
    def check_origin(self, origin: str) -> bool:
        """检查来源是否允许
        
        Args:
            origin: 来源URL
            
        Returns:
            是否允许
        """
        return origin in self.allowed_origins or "*" in self.allowed_origins
    
    def log_security_event(self, event_type: str, message: str, user_id: Optional[str] = None):
        """记录安全事件
        
        Args:
            event_type: 事件类型
            message: 事件消息
            user_id: 用户ID
        """
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{event_type.upper()}] {message}"
        if user_id:
            log_entry += f" (User: {user_id})"
        
        logger.info(log_entry)
    

# 全局安全管理器实例
security_manager = SecurityManager()