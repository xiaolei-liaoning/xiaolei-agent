"""权限系统模块 - 借鉴Claude Code的权限设计

提供多层权限检查和安全控制，支持：
1. 权限级别定义（read/write/execute/admin）
2. 规则匹配引擎
3. Auto Mode分类器（AI驱动的安全决策）
4. 用户确认机制
5. 拒绝追踪（连续拒绝次数限制）
6. 权限上下文管理
"""

import asyncio
import re
from typing import List, Dict, Any, Callable, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from abc import ABC, abstractmethod


class PermissionLevel(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class PermissionDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class AutoModeCategory(Enum):
    SAFE = "safe"
    CAUTIOUS = "cautious"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"


@dataclass
class PermissionRule:
    name: str
    pattern: str
    decision: PermissionDecision
    level: PermissionLevel = PermissionLevel.READ
    description: str = ""
    conditions: Optional[Dict[str, Any]] = None


@dataclass
class PermissionResult:
    decision: PermissionDecision
    rule_name: str = ""
    reason: str = ""
    requires_confirmation: bool = False
    category: AutoModeCategory = AutoModeCategory.UNKNOWN


@dataclass
class PermissionContext:
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tool_name: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    environment: Optional[str] = "production"
    is_auto_mode: bool = False
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class DenyTracker:
    def __init__(self, max_denies: int = 3, timeout_minutes: int = 30):
        self._deny_counts: Dict[str, Tuple[int, datetime]] = {}
        self._max_denies = max_denies
        self._timeout = timeout_minutes * 60
    
    def record_deny(self, key: str):
        now = datetime.now()
        if key in self._deny_counts:
            count, last_time = self._deny_counts[key]
            if (now - last_time).total_seconds() > self._timeout:
                count = 0
            self._deny_counts[key] = (count + 1, now)
        else:
            self._deny_counts[key] = (1, now)
    
    def get_deny_count(self, key: str) -> int:
        if key not in self._deny_counts:
            return 0
        count, last_time = self._deny_counts[key]
        if (datetime.now() - last_time).total_seconds() > self._timeout:
            return 0
        return count
    
    def is_blocked(self, key: str) -> bool:
        return self.get_deny_count(key) >= self._max_denies
    
    def reset(self, key: str):
        if key in self._deny_counts:
            del self._deny_counts[key]


class BasePermissionChecker(ABC):
    @abstractmethod
    async def check(self, context: PermissionContext) -> PermissionResult:
        pass


class RuleBasedChecker(BasePermissionChecker):
    def __init__(self, rules: List[PermissionRule]):
        self._rules = rules
    
    async def check(self, context: PermissionContext) -> PermissionResult:
        for rule in self._rules:
            if self._matches_rule(rule, context):
                return PermissionResult(
                    decision=rule.decision,
                    rule_name=rule.name,
                    reason=rule.description,
                    requires_confirmation=rule.decision == PermissionDecision.ASK
                )
        return PermissionResult(
            decision=PermissionDecision.ALLOW,
            rule_name="default",
            reason="无匹配规则，默认允许"
        )
    
    def _matches_rule(self, rule: PermissionRule, context: PermissionContext) -> bool:
        pattern = rule.pattern
        if context.tool_name and pattern in context.tool_name:
            return True
        if rule.conditions:
            for key, value in rule.conditions.items():
                if key == "environment" and context.environment != value:
                    return False
                if key == "is_auto_mode" and context.is_auto_mode != value:
                    return False
        return False


class AutoModeClassifier(BasePermissionChecker):
    def __init__(self):
        self._safety_patterns = {
            "safe": ["^/help$", "^/status$", "^/history$", "^/clear$", "^file_read$", "^weather$", "^calculator$"],
            "cautious": ["^file_write$", "^file_delete$", "^shell_exec$", "^web_scrape$"],
            "unsafe": ["^system_shutdown$", "^rm -rf", "^chmod -R", "^format "]
        }
    
    async def check(self, context: PermissionContext) -> PermissionResult:
        if not context.is_auto_mode:
            return PermissionResult(
                decision=PermissionDecision.ALLOW,
                rule_name="auto_mode_disabled",
                reason="Auto Mode未启用"
            )
        
        tool_name = context.tool_name or ""
        input_data = context.input_data or {}
        category = await self._classify(tool_name, input_data)
        
        if category == AutoModeCategory.SAFE:
            return PermissionResult(
                decision=PermissionDecision.ALLOW,
                rule_name="auto_mode_safe",
                reason="Auto Mode判定为安全操作",
                category=category
            )
        elif category == AutoModeCategory.CAUTIOUS:
            return PermissionResult(
                decision=PermissionDecision.ASK,
                rule_name="auto_mode_cautious",
                reason="Auto Mode判定为需要确认的操作",
                requires_confirmation=True,
                category=category
            )
        elif category == AutoModeCategory.UNSAFE:
            return PermissionResult(
                decision=PermissionDecision.DENY,
                rule_name="auto_mode_unsafe",
                reason="Auto Mode判定为危险操作",
                category=category
            )
        else:
            return PermissionResult(
                decision=PermissionDecision.ASK,
                rule_name="auto_mode_unknown",
                reason="Auto Mode无法判定，需要人工确认",
                requires_confirmation=True,
                category=category
            )
    
    async def _classify(self, tool_name: str, input_data: Dict[str, Any]) -> AutoModeCategory:
        for pattern in self._safety_patterns["unsafe"]:
            if re.match(pattern, tool_name, re.IGNORECASE):
                return AutoModeCategory.UNSAFE
            for value in input_data.values():
                if isinstance(value, str) and re.search(pattern, value, re.IGNORECASE):
                    return AutoModeCategory.UNSAFE
        
        for pattern in self._safety_patterns["safe"]:
            if re.match(pattern, tool_name, re.IGNORECASE):
                return AutoModeCategory.SAFE
        
        for pattern in self._safety_patterns["cautious"]:
            if re.match(pattern, tool_name, re.IGNORECASE):
                return AutoModeCategory.CAUTIOUS
        
        return AutoModeCategory.UNKNOWN


class UserConfirmationChecker(BasePermissionChecker):
    def __init__(self, confirmation_callback: Optional[Callable] = None):
        self._callback = confirmation_callback
    
    async def check(self, context: PermissionContext) -> PermissionResult:
        if self._callback:
            confirmed = await self._callback(context)
        else:
            confirmed = await self._default_confirmation(context)
        
        if confirmed:
            return PermissionResult(
                decision=PermissionDecision.ALLOW,
                rule_name="user_confirmed",
                reason="用户已确认"
            )
        else:
            return PermissionResult(
                decision=PermissionDecision.DENY,
                rule_name="user_denied",
                reason="用户拒绝"
            )
    
    async def _default_confirmation(self, context: PermissionContext) -> bool:
        print(f"\n⚠️ 需要确认操作")
        print(f"工具: {context.tool_name}")
        print(f"输入: {context.input_data}")
        
        while True:
            choice = input("确认执行? (y/n): ").strip().lower()
            if choice in ['y', 'yes']:
                return True
            elif choice in ['n', 'no']:
                return False
            print("请输入 y 或 n")


class PermissionPipeline:
    def __init__(self, checkers: List[BasePermissionChecker]):
        self._checkers = checkers
    
    async def check(self, context: PermissionContext) -> PermissionResult:
        needs_confirmation = False
        for checker in self._checkers:
            if isinstance(checker, UserConfirmationChecker):
                continue
            result = await checker.check(context)
            if result.decision == PermissionDecision.DENY:
                return result
            if result.decision == PermissionDecision.ASK:
                needs_confirmation = True
        if needs_confirmation:
            for checker in self._checkers:
                if isinstance(checker, UserConfirmationChecker):
                    return await checker.check(context)
        return PermissionResult(
            decision=PermissionDecision.ALLOW,
            rule_name="pipeline_complete",
            reason="所有检查通过"
        )


class PermissionSystem:
    def __init__(self):
        self._deny_tracker = DenyTracker()
        self._pipeline = self._build_pipeline()
        self._audit_logs: List[Dict[str, Any]] = []
    
    def _build_pipeline(self) -> PermissionPipeline:
        default_rules = [
            PermissionRule(
                name="deny_shutdown",
                pattern="system_shutdown",
                decision=PermissionDecision.DENY,
                level=PermissionLevel.ADMIN,
                description="禁止系统关机操作"
            ),
            PermissionRule(
                name="deny_dangerous_commands",
                pattern="rm -rf",
                decision=PermissionDecision.DENY,
                level=PermissionLevel.EXECUTE,
                description="禁止危险的删除命令"
            ),
            PermissionRule(
                name="ask_file_write",
                pattern="file_write",
                decision=PermissionDecision.ASK,
                level=PermissionLevel.WRITE,
                description="文件写入需要确认"
            ),
        ]
        
        checkers = [
            RuleBasedChecker(default_rules),
            AutoModeClassifier(),
            UserConfirmationChecker(),
        ]
        
        return PermissionPipeline(checkers)
    
    async def check_permissions(self, context: PermissionContext) -> PermissionResult:
        user_key = context.user_id or context.session_id or "anonymous"
        if self._deny_tracker.is_blocked(user_key):
            return PermissionResult(
                decision=PermissionDecision.DENY,
                rule_name="blocked_by_deny_tracker",
                reason="连续拒绝次数过多，请稍后再试"
            )
        
        result = await self._pipeline.check(context)
        self._log_audit(context, result)
        
        if result.decision == PermissionDecision.DENY:
            self._deny_tracker.record_deny(user_key)
        
        return result
    
    def _log_audit(self, context: PermissionContext, result: PermissionResult):
        log_entry = {
            "timestamp": context.timestamp.isoformat(),
            "user_id": context.user_id,
            "session_id": context.session_id,
            "tool_name": context.tool_name,
            "decision": result.decision.value,
            "rule_name": result.rule_name,
            "reason": result.reason,
            "is_auto_mode": context.is_auto_mode,
            "environment": context.environment,
        }
        self._log_audit_entry(log_entry)
    
    def _log_audit_entry(self, entry: Dict[str, Any]):
        self._audit_logs.append(entry)
        if len(self._audit_logs) > 1000:
            self._audit_logs = self._audit_logs[-1000:]
    
    def get_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._audit_logs[-limit:]
    
    def reset_deny_count(self, user_key: str):
        self._deny_tracker.reset(user_key)


class PermissionManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._permission_system = PermissionSystem()
        return cls._instance
    
    async def check(self, 
                   tool_name: str,
                   input_data: Optional[Dict[str, Any]] = None,
                   user_id: Optional[str] = None,
                   session_id: Optional[str] = None,
                   is_auto_mode: bool = False) -> PermissionResult:
        context = PermissionContext(
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            input_data=input_data,
            is_auto_mode=is_auto_mode,
            timestamp=datetime.now()
        )
        return await self._permission_system.check_permissions(context)
    
    def get_system(self) -> PermissionSystem:
        return self._permission_system


async def check_permissions(tool_name: str, **kwargs) -> PermissionResult:
    manager = PermissionManager()
    return await manager.check(tool_name, **kwargs)


def get_permission_manager() -> PermissionManager:
    return PermissionManager()