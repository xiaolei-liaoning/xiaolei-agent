"""权限请求服务模块

提供完整的权限管理和请求系统，支持：
1. 权限类型定义
2. 权限检查和请求
3. 用户授权流程
4. 权限历史记录
5. 安全策略管理
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PermissionType(Enum):
    """权限类型枚举"""
    # 文件系统权限
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    DELETE_FILE = "delete_file"
    EXECUTE_FILE = "execute_file"
    
    # 系统权限
    SYSTEM_INFO = "system_info"
    PROCESS_MANAGEMENT = "process_management"
    NETWORK_ACCESS = "network_access"
    
    # GUI自动化权限
    GUI_AUTOMATION = "gui_automation"
    SCREEN_CAPTURE = "screen_capture"
    
    # MCP权限
    MCP_SERVER_ACCESS = "mcp_server_access"
    
    # 代码执行权限
    CODE_EXECUTION = "code_execution"
    
    # 网络请求权限
    WEB_REQUEST = "web_request"
    
    # 危险操作权限
    DANGEROUS_OPERATION = "dangerous_operation"

    # 沙盒模块访问权限（用户确认后可放行）
    SANDBOX_MODULE_ACCESS = "sandbox_module_access"


class PermissionDecision(Enum):
    """权限决策枚举"""
    ALLOW = "allow"
    DENY = "deny"
    PROMPT = "prompt"  # 需要询问用户


class PermissionLevel(Enum):
    """权限级别枚举"""
    LOW = "low"      # 低风险操作
    MEDIUM = "medium"  # 中等风险操作
    HIGH = "high"    # 高风险操作
    CRITICAL = "critical"  # 关键风险操作


@dataclass
class PermissionRequest:
    """权限请求"""
    permission_type: PermissionType
    level: PermissionLevel
    description: str
    target: Optional[str] = None  # 操作目标（如文件路径）
    reason: Optional[str] = None  # 请求原因
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "permission_type": self.permission_type.value,
            "level": self.level.value,
            "description": self.description,
            "target": self.target,
            "reason": self.reason
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionRequest":
        return cls(
            permission_type=PermissionType(data.get("permission_type")),
            level=PermissionLevel(data.get("level")),
            description=data.get("description", ""),
            target=data.get("target"),
            reason=data.get("reason")
        )


@dataclass
class PermissionResponse:
    """权限响应"""
    permission_type: PermissionType
    decision: PermissionDecision
    granted_at: datetime
    expires_at: Optional[datetime] = None
    user_note: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "permission_type": self.permission_type.value,
            "decision": self.decision.value,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "user_note": self.user_note
        }


@dataclass
class PermissionRule:
    """权限规则"""
    permission_type: PermissionType
    default_decision: PermissionDecision
    level: PermissionLevel
    auto_expire_minutes: int = 30  # 自动过期时间（分钟）
    require_confirmation: bool = False  # 是否需要确认
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "permission_type": self.permission_type.value,
            "default_decision": self.default_decision.value,
            "level": self.level.value,
            "auto_expire_minutes": self.auto_expire_minutes,
            "require_confirmation": self.require_confirmation
        }


@dataclass
class PermissionHistory:
    """权限历史记录"""
    timestamp: datetime
    request: PermissionRequest
    response: PermissionResponse
    context: Dict[str, Any] = field(default_factory=dict)


class PermissionMode(Enum):
    """权限模式"""
    DEFAULT = "default"      # 默认：高风险弹窗，低风险自动
    PERMISSIVE = "permissive"  # 宽松：全部自动放行（旧版行为）
    STRICT = "strict"        # 严格：全部弹窗确认


class PermissionService:
    """权限请求服务

    核心功能：
    1. 权限检查
    2. 权限请求（询问用户/自动决策）
    3. 权限缓存和过期管理
    4. 权限历史记录
    """

    def __init__(self, mode: str = "default"):
        # 权限模式
        self._mode = PermissionMode(mode)
        self._read_mode_from_config()

        # 权限规则配置
        self._rules: Dict[PermissionType, PermissionRule] = self._load_default_rules()

        # 权限缓存（已授予的权限）
        self._permissions_cache: Dict[PermissionType, PermissionResponse] = {}

        # 权限历史记录
        self._history: List[PermissionHistory] = []

        # 会话级临时权限
        self._session_permissions: Dict[str, PermissionResponse] = {}

        logger.info(f"✅ 权限服务初始化成功 mode={self._mode.value}")

    def _read_mode_from_config(self):
        """从应用配置读取权限模式"""
        try:
            import os
            env_mode = os.getenv("PERMISSION_MODE", "").lower()
            if env_mode in ("default", "permissive", "strict"):
                self._mode = PermissionMode(env_mode)
        except Exception:
            pass
    
    def _load_default_rules(self) -> Dict[PermissionType, PermissionRule]:
        """加载默认权限规则"""
        return {
            # 文件系统权限
            PermissionType.READ_FILE: PermissionRule(
                permission_type=PermissionType.READ_FILE,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.LOW,
                auto_expire_minutes=60
            ),
            PermissionType.WRITE_FILE: PermissionRule(
                permission_type=PermissionType.WRITE_FILE,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.MEDIUM,
                auto_expire_minutes=30,
                require_confirmation=True
            ),
            PermissionType.DELETE_FILE: PermissionRule(
                permission_type=PermissionType.DELETE_FILE,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.CRITICAL,
                auto_expire_minutes=5,
                require_confirmation=True
            ),
            PermissionType.EXECUTE_FILE: PermissionRule(
                permission_type=PermissionType.EXECUTE_FILE,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.HIGH,
                auto_expire_minutes=15,
                require_confirmation=True
            ),
            
            # 系统权限
            PermissionType.SYSTEM_INFO: PermissionRule(
                permission_type=PermissionType.SYSTEM_INFO,
                default_decision=PermissionDecision.ALLOW,
                level=PermissionLevel.LOW,
                auto_expire_minutes=120
            ),
            PermissionType.PROCESS_MANAGEMENT: PermissionRule(
                permission_type=PermissionType.PROCESS_MANAGEMENT,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.HIGH,
                auto_expire_minutes=15,
                require_confirmation=True
            ),
            PermissionType.NETWORK_ACCESS: PermissionRule(
                permission_type=PermissionType.NETWORK_ACCESS,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.MEDIUM,
                auto_expire_minutes=60
            ),
            
            # GUI自动化权限
            PermissionType.GUI_AUTOMATION: PermissionRule(
                permission_type=PermissionType.GUI_AUTOMATION,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.MEDIUM,
                auto_expire_minutes=30,
                require_confirmation=True
            ),
            PermissionType.SCREEN_CAPTURE: PermissionRule(
                permission_type=PermissionType.SCREEN_CAPTURE,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.MEDIUM,
                auto_expire_minutes=15,
                require_confirmation=True
            ),
            
            # MCP权限
            PermissionType.MCP_SERVER_ACCESS: PermissionRule(
                permission_type=PermissionType.MCP_SERVER_ACCESS,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.LOW,
                auto_expire_minutes=60
            ),
            
            # 代码执行权限
            PermissionType.CODE_EXECUTION: PermissionRule(
                permission_type=PermissionType.CODE_EXECUTION,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.CRITICAL,
                auto_expire_minutes=5,
                require_confirmation=True
            ),
            
            # 网络请求权限
            PermissionType.WEB_REQUEST: PermissionRule(
                permission_type=PermissionType.WEB_REQUEST,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.LOW,
                auto_expire_minutes=60
            ),
            
            # 危险操作权限
            PermissionType.DANGEROUS_OPERATION: PermissionRule(
                permission_type=PermissionType.DANGEROUS_OPERATION,
                default_decision=PermissionDecision.PROMPT,
                level=PermissionLevel.CRITICAL,
                auto_expire_minutes=1,
                require_confirmation=True
            )
        }
    
    def _check_cache(self, permission_type: PermissionType) -> Optional[PermissionResponse]:
        """检查权限缓存"""
        if permission_type in self._permissions_cache:
            response = self._permissions_cache[permission_type]
            
            # 检查是否过期
            if response.expires_at and response.expires_at < datetime.now():
                del self._permissions_cache[permission_type]
                return None
            
            return response
        
        return None
    
    def _update_cache(self, response: PermissionResponse):
        """更新权限缓存"""
        self._permissions_cache[response.permission_type] = response
    
    def _record_history(self, request: PermissionRequest, response: PermissionResponse, context: Dict[str, Any] = None):
        """记录权限历史"""
        self._history.append(PermissionHistory(
            timestamp=datetime.now(),
            request=request,
            response=response,
            context=context or {}
        ))
        
        # 保留最近100条记录
        if len(self._history) > 100:
            self._history = self._history[-100:]
    
    def check_permission(self, permission_type: PermissionType,
                        target: Optional[str] = None,
                        reason: Optional[str] = None) -> PermissionDecision:
        """检查权限

        Args:
            permission_type: 权限类型
            target: 操作目标
            reason: 请求原因

        Returns:
            权限决策
        """
        # 宽松模式全部放行
        if self._mode == PermissionMode.PERMISSIVE:
            return PermissionDecision.ALLOW

        # 首先检查缓存
        cached = self._check_cache(permission_type)
        if cached:
            logger.debug(f"权限缓存命中: {permission_type.value} -> {cached.decision.value}")
            return cached.decision

        # 获取权限规则
        rule = self._rules.get(permission_type)
        if not rule:
            logger.warning(f"未找到权限规则: {permission_type.value}")
            return PermissionDecision.PROMPT

        # 严格模式全部提示
        if self._mode == PermissionMode.STRICT:
            return PermissionDecision.PROMPT

        # 默认模式：按规则配置
        return rule.default_decision
    
    async def request_permission(self, permission_type: PermissionType,
                                target: Optional[str] = None,
                                reason: Optional[str] = None,
                                context: Optional[Dict[str, Any]] = None) -> bool:
        """请求权限（询问用户或按模式自动决策）

        Args:
            permission_type: 权限类型
            target: 操作目标
            reason: 请求原因
            context: 额外上下文

        Returns:
            是否获得授权
        """
        # 构建权限请求
        rule = self._rules.get(permission_type)
        request = PermissionRequest(
            permission_type=permission_type,
            level=rule.level if rule else PermissionLevel.MEDIUM,
            description=self._get_permission_description(permission_type, target),
            target=target,
            reason=reason
        )

        # 记录请求
        logger.info(f"请求权限: {permission_type.value}, 目标: {target}, 原因: {reason}")

        decision = PermissionDecision.ALLOW  # 默认放行

        # 根据模式决策
        if self._mode == PermissionMode.PERMISSIVE:
            decision = PermissionDecision.ALLOW
        elif self._mode == PermissionMode.STRICT:
            decision = PermissionDecision.PROMPT
        elif rule and rule.default_decision == PermissionDecision.PROMPT:
            # 默认模式 + 规则要求弹窗 → 走 clarification_service
            try:
                from core.services.clarification_service import get_clarification_service
                cs = get_clarification_service()
                should_proceed = await cs.ask_permission(
                    permission_type=permission_type,
                    description=self._get_permission_description(permission_type, target),
                    reason=reason,
                )
                if should_proceed:
                    decision = PermissionDecision.ALLOW
                else:
                    decision = PermissionDecision.DENY
            except Exception:
                # clarification 不可用时，规则要求弹窗的权限默认拒绝
                if rule and rule.require_confirmation:
                    decision = PermissionDecision.DENY
                    logger.warning(f"权限 [{permission_type.value}] 需要确认但无法弹窗，默认拒绝")
                else:
                    decision = PermissionDecision.ALLOW

        # 创建权限响应
        response = PermissionResponse(
            permission_type=permission_type,
            decision=decision,
            granted_at=datetime.now(),
            expires_at=self._calculate_expiry(rule) if rule and decision == PermissionDecision.ALLOW else None
        )

        # 更新缓存
        if decision == PermissionDecision.ALLOW:
            self._update_cache(response)

        # 记录历史
        self._record_history(request, response, context)

        if decision == PermissionDecision.ALLOW:
            logger.info(f"权限已授予: {permission_type.value}")
            return True
        else:
            logger.info(f"权限已拒绝: {permission_type.value}")
            return False
    
    def _get_permission_description(self, permission_type: PermissionType, 
                                   target: Optional[str] = None) -> str:
        """获取权限描述"""
        descriptions = {
            PermissionType.READ_FILE: f"读取文件: {target}" if target else "读取文件",
            PermissionType.WRITE_FILE: f"写入文件: {target}" if target else "写入文件",
            PermissionType.DELETE_FILE: f"删除文件: {target}" if target else "删除文件",
            PermissionType.EXECUTE_FILE: f"执行文件: {target}" if target else "执行文件",
            PermissionType.SYSTEM_INFO: "获取系统信息",
            PermissionType.PROCESS_MANAGEMENT: "进程管理",
            PermissionType.NETWORK_ACCESS: "网络访问",
            PermissionType.GUI_AUTOMATION: "GUI自动化操作",
            PermissionType.SCREEN_CAPTURE: "屏幕截图",
            PermissionType.MCP_SERVER_ACCESS: "访问MCP服务器",
            PermissionType.CODE_EXECUTION: "代码执行",
            PermissionType.WEB_REQUEST: "网络请求",
            PermissionType.DANGEROUS_OPERATION: f"危险操作: {target}" if target else "危险操作"
        }
        return descriptions.get(permission_type, str(permission_type.value))
    
    def _generate_permission_question(self, request: PermissionRequest) -> str:
        """生成权限请求问题"""
        level_icons = {
            PermissionLevel.LOW: "🔵",
            PermissionLevel.MEDIUM: "🟡",
            PermissionLevel.HIGH: "🟠",
            PermissionLevel.CRITICAL: "🔴"
        }
        
        level_labels = {
            PermissionLevel.LOW: "低风险",
            PermissionLevel.MEDIUM: "中风险",
            PermissionLevel.HIGH: "高风险",
            PermissionLevel.CRITICAL: "关键风险"
        }
        
        icon = level_icons.get(request.level, "⚪")
        label = level_labels.get(request.level, "未知")
        
        question = f"{icon} [{label}] {request.description}"
        
        if request.reason:
            question += f"\n原因: {request.reason}"
        
        if request.target:
            question += f"\n目标: {request.target}"
        
        return question
    
    def _calculate_expiry(self, rule: PermissionRule) -> Optional[datetime]:
        """计算过期时间"""
        if rule.auto_expire_minutes > 0:
            return datetime.now() + timedelta(minutes=rule.auto_expire_minutes)
        return None
    
    def get_permission_status(self, permission_type: PermissionType) -> Dict[str, Any]:
        """获取权限状态"""
        cached = self._check_cache(permission_type)
        
        result = {
            "permission_type": permission_type.value,
            "has_permission": cached is not None and cached.decision == PermissionDecision.ALLOW,
            "cached": cached is not None,
            "expires_at": cached.expires_at.isoformat() if cached and cached.expires_at else None
        }
        
        return result
    
    def get_history(self) -> List[Dict[str, Any]]:
        """获取权限历史记录"""
        return [
            {
                "timestamp": h.timestamp.isoformat(),
                "request": h.request.to_dict(),
                "response": h.response.to_dict(),
                "context": h.context
            }
            for h in self._history
        ]
    
    def reset_session(self):
        """重置会话权限"""
        self._session_permissions.clear()
        logger.info("会话权限已重置")
    
    def set_permission(self, permission_type: PermissionType, 
                      decision: PermissionDecision,
                      expires_in_minutes: int = 30):
        """手动设置权限"""
        response = PermissionResponse(
            permission_type=permission_type,
            decision=decision,
            granted_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=expires_in_minutes) if expires_in_minutes > 0 else None
        )
        self._update_cache(response)
        logger.info(f"手动设置权限: {permission_type.value} -> {decision.value}")


# 添加timedelta导入
from datetime import timedelta


# 全局单例
_permission_service = None

def get_permission_service() -> PermissionService:
    """获取权限服务实例"""
    global _permission_service
    if _permission_service is None:
        _permission_service = PermissionService()
    return _permission_service