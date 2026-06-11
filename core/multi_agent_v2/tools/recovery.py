"""
错误恢复机制 — 自动重试 + 降级策略

提供：
- 指数退避重试
- 工具降级（失败时切换到替代工具）
- 错误分类和处理
- 恢复计划生成
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """错误分类"""
    TIMEOUT = "timeout"              # 超时
    RATE_LIMIT = "rate_limit"        # 限流
    AUTH_ERROR = "auth_error"        # 认证错误
    NETWORK_ERROR = "network_error"  # 网络错误
    VALIDATION_ERROR = "validation_error"  # 参数验证错误
    PERMISSION_ERROR = "permission_error"  # 权限错误
    TOOL_ERROR = "tool_error"        # 工具执行错误
    UNKNOWN = "unknown"              # 未知错误


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class FallbackConfig:
    """降级配置"""
    enabled: bool = True
    fallback_tools: Dict[str, str] = field(default_factory=dict)  # tool -> fallback_tool
    max_fallback_depth: int = 2


@dataclass
class RecoveryPlan:
    """恢复计划"""
    original_tool: str
    error_category: ErrorCategory
    strategy: str  # retry/fallback/abort
    fallback_tool: Optional[str] = None
    retry_delay: Optional[float] = None
    reason: str = ""


class ErrorClassifier:
    """错误分类器"""

    # 错误消息 -> 分类映射
    ERROR_PATTERNS = {
        ErrorCategory.TIMEOUT: [
            "timeout", "timed out", "deadline exceeded",
            "请求超时", "连接超时",
        ],
        ErrorCategory.RATE_LIMIT: [
            "rate limit", "too many requests", "429",
            "限流", "请求过于频繁",
        ],
        ErrorCategory.AUTH_ERROR: [
            "unauthorized", "authentication", "401", "403",
            "认证失败", "权限不足",
        ],
        ErrorCategory.NETWORK_ERROR: [
            "connection", "network", "dns", "socket",
            "连接失败", "网络错误",
        ],
        ErrorCategory.VALIDATION_ERROR: [
            "invalid", "validation", "required",
            "参数错误", "验证失败",
        ],
        ErrorCategory.PERMISSION_ERROR: [
            "permission", "denied", "forbidden",
            "权限", "禁止",
        ],
    }

    @classmethod
    def classify(cls, error: Exception) -> ErrorCategory:
        """分类错误"""
        error_msg = str(error).lower()

        for category, patterns in cls.ERROR_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in error_msg:
                    return category

        return ErrorCategory.UNKNOWN

    @classmethod
    def is_retriable(cls, category: ErrorCategory) -> bool:
        """检查错误是否可重试"""
        retriable = {
            ErrorCategory.TIMEOUT,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.NETWORK_ERROR,
        }
        return category in retriable


class RecoveryManager:
    """错误恢复管理器"""

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        fallback_config: Optional[FallbackConfig] = None,
    ):
        self.retry_config = retry_config or RetryConfig()
        self.fallback_config = fallback_config or FallbackConfig()
        self._stats: Dict[str, int] = {}

    def classify_error(self, error: Exception) -> ErrorCategory:
        """分类错误"""
        return ErrorClassifier.classify(error)

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """检查是否应该重试"""
        if attempt >= self.retry_config.max_retries:
            return False

        category = self.classify_error(error)
        return ErrorClassifier.is_retriable(category)

    def get_retry_delay(self, attempt: int) -> float:
        """获取重试延迟"""
        delay = self.retry_config.base_delay * (
            self.retry_config.exponential_base ** attempt
        )
        delay = min(delay, self.retry_config.max_delay)

        if self.retry_config.jitter:
            delay = delay * (0.5 + random.random())

        return delay

    def get_fallback_tool(self, tool_name: str) -> Optional[str]:
        """获取降级工具"""
        if not self.fallback_config.enabled:
            return None

        return self.fallback_config.fallback_tools.get(tool_name)

    def create_recovery_plan(
        self, tool_name: str, error: Exception, attempt: int
    ) -> RecoveryPlan:
        """创建恢复计划"""
        category = self.classify_error(error)

        # 检查是否可重试
        if self.should_retry(error, attempt):
            delay = self.get_retry_delay(attempt)
            return RecoveryPlan(
                original_tool=tool_name,
                error_category=category,
                strategy="retry",
                retry_delay=delay,
                reason=f"错误 {category.value}，将重试 (第 {attempt + 1} 次)",
            )

        # 检查是否有降级工具
        fallback = self.get_fallback_tool(tool_name)
        if fallback:
            return RecoveryPlan(
                original_tool=tool_name,
                error_category=category,
                strategy="fallback",
                fallback_tool=fallback,
                reason=f"错误 {category.value}，将降级到 {fallback}",
            )

        # 终止
        return RecoveryPlan(
            original_tool=tool_name,
            error_category=category,
            strategy="abort",
            reason=f"错误 {category.value}，无法恢复",
        )

    async def execute_with_recovery(
        self,
        func: Callable,
        tool_name: str,
        *args,
        **kwargs
    ) -> Any:
        """执行带恢复机制的函数"""
        last_error = None
        attempt = 0

        while attempt <= self.retry_config.max_retries:
            try:
                result = await func(*args, **kwargs)
                if attempt > 0:
                    logger.info(f"工具 {tool_name} 重试成功 (第 {attempt} 次)")
                return result
            except Exception as e:
                last_error = e
                attempt += 1

                plan = self.create_recovery_plan(tool_name, e, attempt - 1)
                logger.warning(f"工具 {tool_name} 执行失败: {plan.reason}")

                if plan.strategy == "retry":
                    await asyncio.sleep(plan.retry_delay)
                    continue
                elif plan.strategy == "fallback":
                    # 这里可以调用降级工具
                    logger.info(f"降级到 {plan.fallback_tool}")
                    break
                else:
                    break

        raise last_error

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self._stats.copy()


# 默认降级配置
DEFAULT_FALLBACK_CONFIG = FallbackConfig(
    enabled=True,
    fallback_tools={
        "web_search": "fetch_url",
        "fetch_json": "execute_python",
        "rag_search": "web_search",
        "fetch_url": "execute_python",
        "read_file": "execute_python",
        "edit_file": "execute_python",
        "glob_search": "execute_python",
        "grep_search": "execute_python",
    },
)


# 全局恢复管理器实例
_recovery_manager: Optional[RecoveryManager] = None


def get_recovery_manager(
    retry_config: Optional[RetryConfig] = None,
    fallback_config: Optional[FallbackConfig] = None,
) -> RecoveryManager:
    """获取全局恢复管理器实例"""
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = RecoveryManager(
            retry_config or RetryConfig(),
            fallback_config or DEFAULT_FALLBACK_CONFIG,
        )
    return _recovery_manager
