"""
工具 Hook 系统 — BeforeTool/AfterTool/OnError 拦截器

对标 gemini-cli 的 coreToolHookTriggers
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HookType(Enum):
    """Hook 类型"""
    BEFORE = "before"
    AFTER = "after"
    ERROR = "error"


class HookPriority(Enum):
    """Hook 优先级（数值越小越先执行）"""
    HIGH = 10
    NORMAL = 50
    LOW = 100


@dataclass
class HookResult:
    """Hook 执行结果"""
    modify_args: bool = False  # 是否修改了参数
    modify_result: bool = False  # 是否修改了结果
    skip: bool = False  # 是否跳过工具执行
    abort: bool = False  # 是否终止整个流程
    retry: bool = False  # 是否重试
    max_retries: int = 3  # 最大重试次数
    reason: str = ""  # 原因说明
    args: Optional[Dict] = None  # 修改后的参数
    result: Optional[Any] = None  # 修改后的结果
    abort_reason: str = ""  # 终止原因


@dataclass
class ToolHook:
    """工具 Hook 定义"""
    name: str
    hook_type: HookType
    func: Callable
    priority: HookPriority = HookPriority.NORMAL
    tool_pattern: str = "*"  # 工具名匹配模式（* 匹配所有）
    enabled: bool = True


class BeforeToolHook:
    """BeforeTool Hook 基类"""

    def __init__(self, name: str, tool_pattern: str = "*", priority: HookPriority = HookPriority.NORMAL):
        self.name = name
        self.tool_pattern = tool_pattern
        self.priority = priority

    async def execute(self, tool_name: str, arguments: dict) -> HookResult:
        """
        执行 Hook

        Args:
            tool_name: 工具名
            arguments: 工具参数

        Returns:
            HookResult: 执行结果
        """
        raise NotImplementedError


class AfterToolHook:
    """AfterTool Hook 基类"""

    def __init__(self, name: str, tool_pattern: str = "*", priority: HookPriority = HookPriority.NORMAL):
        self.name = name
        self.tool_pattern = tool_pattern
        self.priority = priority

    async def execute(self, tool_name: str, arguments: dict, result: Any) -> HookResult:
        """
        执行 Hook

        Args:
            tool_name: 工具名
            arguments: 工具参数
            result: 工具执行结果

        Returns:
            HookResult: 执行结果
        """
        raise NotImplementedError


class OnErrorHook:
    """OnError Hook 基类"""

    def __init__(self, name: str, tool_pattern: str = "*", priority: HookPriority = HookPriority.NORMAL):
        self.name = name
        self.tool_pattern = tool_pattern
        self.priority = priority

    async def execute(self, tool_name: str, arguments: dict, error: Exception) -> HookResult:
        """
        执行 Hook

        Args:
            tool_name: 工具名
            arguments: 工具参数
            error: 异常

        Returns:
            HookResult: 执行结果
        """
        raise NotImplementedError


import fnmatch
import time
from functools import wraps


def before_tool(name: str = None, tool_pattern: str = "*", priority: HookPriority = HookPriority.NORMAL):
    """
    BeforeTool Hook 装饰器

    Usage:
        @before_tool("log_call", "*")
        async def log_call(tool_name: str, arguments: dict):
            logger.info(f"Tool called: {tool_name}")
            return HookResult()
    """
    def decorator(func):
        hook_name = name or func.__name__
        hook = ToolHook(
            name=hook_name,
            hook_type=HookType.BEFORE,
            func=func,
            priority=priority,
            tool_pattern=tool_pattern,
        )
        func._tool_hook = hook
        return func
    return decorator


def after_tool(name: str = None, tool_pattern: str = "*", priority: HookPriority = HookPriority.NORMAL):
    """
    AfterTool Hook 装饰器

    Usage:
        @after_tool("cache_result", "*")
        async def cache_result(tool_name: str, arguments: dict, result: Any):
            cache.set(f"{tool_name}:{hash(str(arguments))}", result)
            return HookResult()
    """
    def decorator(func):
        hook_name = name or func.__name__
        hook = ToolHook(
            name=hook_name,
            hook_type=HookType.AFTER,
            func=func,
            priority=priority,
            tool_pattern=tool_pattern,
        )
        func._tool_hook = hook
        return func
    return decorator


def on_error(name: str = None, tool_pattern: str = "*", priority: HookPriority = HookPriority.NORMAL):
    """
    OnError Hook 装饰器

    Usage:
        @on_error("retry_on_timeout", "*")
        async def retry_on_timeout(tool_name: str, arguments: dict, error: Exception):
            if isinstance(error, TimeoutError):
                return HookResult(retry=True, max_retries=2)
            return HookResult()
    """
    def decorator(func):
        hook_name = name or func.__name__
        hook = ToolHook(
            name=hook_name,
            hook_type=HookType.ERROR,
            func=func,
            priority=priority,
            tool_pattern=tool_pattern,
        )
        func._tool_hook = hook
        return func
    return decorator


class ToolHookManager:
    """工具 Hook 管理器"""

    def __init__(self):
        self.before_hooks: List[ToolHook] = []
        self.after_hooks: List[ToolHook] = []
        self.error_hooks: List[ToolHook] = []
        self._stats: Dict[str, int] = {}

    def register(self, hook_func: Callable) -> None:
        """
        注册 Hook 函数

        支持通过装饰器注册的函数（带 _tool_hook 属性）
        """
        if hasattr(hook_func, "_tool_hook"):
            hook = hook_func._tool_hook
            if hook.hook_type == HookType.BEFORE:
                self.before_hooks.append(hook)
            elif hook.hook_type == HookType.AFTER:
                self.after_hooks.append(hook)
            elif hook.hook_type == HookType.ERROR:
                self.error_hooks.append(hook)
            logger.debug(f"注册 Hook: {hook.name} ({hook.hook_type.value})")
        else:
            logger.warning(f"Hook 函数 {hook_func.__name__} 缺少 _tool_hook 属性")

    def add_before_hook(self, hook: ToolHook) -> None:
        """手动添加 BeforeTool Hook"""
        if hook.hook_type == HookType.BEFORE:
            self.before_hooks.append(hook)
            self.before_hooks.sort(key=lambda h: h.priority.value)

    def add_after_hook(self, hook: ToolHook) -> None:
        """手动添加 AfterTool Hook"""
        if hook.hook_type == HookType.AFTER:
            self.after_hooks.append(hook)
            self.after_hooks.sort(key=lambda h: h.priority.value)

    def add_error_hook(self, hook: ToolHook) -> None:
        """手动添加 OnError Hook"""
        if hook.hook_type == HookType.ERROR:
            self.error_hooks.append(hook)
            self.error_hooks.sort(key=lambda h: h.priority.value)

    def _match_tool(self, tool_name: str, pattern: str) -> bool:
        """检查工具名是否匹配 Hook 模式"""
        return fnmatch.fnmatch(tool_name, pattern)

    async def run_before(self, tool_name: str, arguments: dict) -> HookResult:
        """
        执行所有 BeforeTool Hook

        Args:
            tool_name: 工具名
            arguments: 工具参数

        Returns:
            HookResult: 综合结果
        """
        combined = HookResult()
        args = arguments.copy()

        for hook in self.before_hooks:
            if not hook.enabled:
                continue
            if not self._match_tool(tool_name, hook.tool_pattern):
                continue

            try:
                result = await hook.func(tool_name, args)
                if result.modify_args and result.args:
                    args = result.args
                    combined.modify_args = True
                    combined.args = args
                if result.skip:
                    combined.skip = True
                    combined.reason = result.reason
                    break
                if result.abort:
                    combined.abort = True
                    combined.abort_reason = result.abort_reason
                    break
                self._stats[hook.name] = self._stats.get(hook.name, 0) + 1
            except Exception as e:
                logger.error(f"Hook {hook.name} 执行失败: {e}")

        return combined

    async def run_after(self, tool_name: str, arguments: dict, result: Any) -> HookResult:
        """
        执行所有 AfterTool Hook

        Args:
            tool_name: 工具名
            arguments: 工具参数
            result: 工具执行结果

        Returns:
            HookResult: 综合结果
        """
        combined = HookResult()
        modified_result = result

        for hook in self.after_hooks:
            if not hook.enabled:
                continue
            if not self._match_tool(tool_name, hook.tool_pattern):
                continue

            try:
                hook_result = await hook.func(tool_name, arguments, modified_result)
                if hook_result.modify_result and hook_result.result:
                    modified_result = hook_result.result
                    combined.modify_result = True
                    combined.result = modified_result
                self._stats[hook.name] = self._stats.get(hook.name, 0) + 1
            except Exception as e:
                logger.error(f"Hook {hook.name} 执行失败: {e}")

        return combined

    async def run_error(self, tool_name: str, arguments: dict, error: Exception) -> HookResult:
        """
        执行所有 OnError Hook

        Args:
            tool_name: 工具名
            arguments: 工具参数
            error: 异常

        Returns:
            HookResult: 综合结果
        """
        combined = HookResult()

        for hook in self.error_hooks:
            if not hook.enabled:
                continue
            if not self._match_tool(tool_name, hook.tool_pattern):
                continue

            try:
                result = await hook.func(tool_name, arguments, error)
                if result.retry:
                    combined.retry = True
                    combined.max_retries = max(combined.max_retries, result.max_retries)
                self._stats[hook.name] = self._stats.get(hook.name, 0) + 1
            except Exception as e:
                logger.error(f"Hook {hook.name} 执行失败: {e}")

        return combined

    def get_stats(self) -> Dict[str, int]:
        """获取 Hook 执行统计"""
        return self._stats.copy()

    def clear_stats(self) -> None:
        """清除统计"""
        self._stats.clear()


# ════════════════════════════════════════════════════════════════
# 内置 Hook 实现
# ════════════════════════════════════════════════════════════════

@before_tool("log_tool_call", "*")
async def log_tool_call(tool_name: str, arguments: dict) -> HookResult:
    """记录工具调用日志"""
    logger.info(f"Tool called: {tool_name}({arguments})")
    return HookResult()


@after_tool("cache_result", "*")
async def cache_result(tool_name: str, arguments: dict, result: Any) -> HookResult:
    """缓存工具结果（简单内存缓存）"""
    # 这里可以集成 Redis 或其他缓存系统
    cache_key = f"{tool_name}:{hash(str(arguments))}"
    logger.debug(f"Caching result for {cache_key}")
    return HookResult(modify_result=False)


@on_error("retry_on_timeout", "*")
async def retry_on_timeout(tool_name: str, arguments: dict, error: Exception) -> HookResult:
    """超时重试"""
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return HookResult(retry=True, max_retries=2)
    return HookResult()


# 全局 Hook 管理器实例
_hook_manager: Optional[ToolHookManager] = None


def get_hook_manager() -> ToolHookManager:
    """获取全局 Hook 管理器实例"""
    global _hook_manager
    if _hook_manager is None:
        _hook_manager = ToolHookManager()
        # 注册内置 Hook
        _hook_manager.register(log_tool_call)
        _hook_manager.register(cache_result)
        _hook_manager.register(retry_on_timeout)
    return _hook_manager
