"""统一执行上下文

类比 Claude Code 的 ToolUseContext——一个对象带齐执行路径所需的所有服务。
替代散落在各模块的 get_xxx() 全局单例调用链。

用法：
    ctx = ExecutionContext.create_default()
    await ctx.llm_router.simple_chat(...)
    await ctx.sandbox.execute_python(...)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .infrastructure.service_interfaces import ISandboxExecutor, IClarificationService

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """统一执行上下文

    汇聚核心服务实例。各字段可选——不传则自动从 DI 容器或全局单例加载。
    测试时直接传入 mock 实例即可。

    用法：
        # 自动从 DI 容器加载所有服务
        ctx = ExecutionContext.create_default()

        # 手动注入（测试用）
        ctx = ExecutionContext(sandbox=mock_sandbox, llm_router=mock_llm)
    """

    llm_router: Any = None
    sandbox: Optional[ISandboxExecutor] = None
    clarification: Any = None
    bfs_processor: Any = None
    short_term_memory: Any = None
    permission_service: Any = None
    viewer: Any = None

    _loaded: bool = False

    # ── 懒加载 ──────────────────────────────────────────────────────────

    def ensure_loaded(self):
        """确保所有未设置的服务从 DI 容器或全局单例加载"""
        if self._loaded:
            return
        self._load_missing()
        self._loaded = True

    def _load_missing(self):
        if self.llm_router is None:
            self.llm_router = _load_llm()
        if self.sandbox is None:
            self.sandbox = _load_sandbox()
        if self.clarification is None:
            self.clarification = _load_clarification()
        if self.bfs_processor is None:
            self.bfs_processor = _load_bfs()
        if self.short_term_memory is None:
            self.short_term_memory = _load_memory()
        if self.permission_service is None:
            self.permission_service = _load_permission()
        if self.viewer is None:
            self.viewer = _load_viewer()

    # ── 工厂方法 ─────────────────────────────────────────────────────────

    @classmethod
    def create_default(cls) -> "ExecutionContext":
        """创建默认上下文（优先从 DI 容器加载，降级到全局单例）"""
        ctx = cls()
        ctx.ensure_loaded()
        return ctx


# ═══════════════════════════════════════════════════════════════════════
#  按需加载器：先试 DI 容器，再试全局单例
# ═══════════════════════════════════════════════════════════════════════


def _try_di(interface_type):
    """从 DI 容器解析服务，失败则返回 None"""
    try:
        from .infrastructure.di_container import get_container
        container = get_container()
        if container.is_registered(interface_type):
            return container.resolve(interface_type)
    except Exception:
        pass
    return None


def _load_llm():
    from .engine.llm_backend import get_llm_router
    return get_llm_router()


def _load_sandbox() -> ISandboxExecutor:
    svc = _try_di(ISandboxExecutor)
    if svc:
        return svc
    from .tools.sandbox_executor import get_sandbox_executor
    return get_sandbox_executor()


def _load_clarification():
    svc = _try_di(IClarificationService)
    if svc:
        return svc
    from .services.clarification_service import get_clarification_service
    return get_clarification_service()


def _load_bfs():
    from .workflow.bfs_processor import get_bfs_processor
    return get_bfs_processor()


def _load_memory():
    from .memory.short_term_memory import ShortTermMemoryManager
    return ShortTermMemoryManager()


def _load_permission():
    try:
        from .services.permission_service import get_permission_service
        return get_permission_service()
    except Exception:
        return None


def _load_viewer():
    try:
        from cli.sandbox_viewer import get_viewer
        return get_viewer()
    except Exception:
        return None
