"""
Workflow 子系统 — Claude Code Dynamic Workflows 风格的多 Agent 编排

核心组件:
  @workflow(name, description, phases)  — 装饰器，标记 async fn 为 Workflow 脚本
  run_workflow(fn)                       — 执行 Workflow 脚本
  agent(prompt, opts?)                   — 启动子 Agent（上下文自动注入）
  parallel(thunks)                       — 并行执行（barrier）
  pipeline(items, *stages)               — 流水线（无 barrier）
  phase(title)                           — 阶段标记
  log(msg)                               — 进度输出

典型用法:
    @workflow(name="语言对比", phases=[{"title": "研究"}, {"title": "汇总"}])
    async def analyze():
        phase("研究")
        r1 = await agent("分析Python", {agentType: "analyst"})
        r2 = await agent("分析Java", {agentType: "analyst"})

        phase("汇总")
        return await agent(f"对比: {r1.text()} vs {r2.text()}", {agentType: "analyst"})

    result = await run_workflow(analyze)
    # result.output, result.phases, result.agent_results
"""

import contextvars
import functools
from typing import Any, Callable, Dict, List, Optional

from .models import Meta, WorkflowContext, WorkflowResult
from .runtime import WorkflowRuntime, OrchestrationPatterns

# ── ContextVar — 供快捷函数从运行时上下文取值 ────────────────
_workflow_ctx_var: contextvars.ContextVar[WorkflowContext] = \
    contextvars.ContextVar("_workflow_ctx")


def workflow(name: str = "", description: str = "", phases: Optional[List[Dict]] = None):
    """装饰器：标记一个 async fn 为 Workflow 脚本

    用法:
        @workflow(name="分析", phases=[{"title": "阶段1"}, {"title": "阶段2"}])
        async def my_flow():
            ...
    """
    def decorator(fn):
        fn._meta = Meta(
            name=name or fn.__name__,
            description=description,
            phases=phases or [],
        )
        return fn
    return decorator


async def run_workflow(fn: Callable, **meta_overrides) -> WorkflowResult:
    """执行一个 @workflow 装饰过的 async 函数

    Args:
        fn: 被 @workflow 装饰过的 async 函数
        **meta_overrides: 可覆盖的 Meta 属性

    Returns:
        WorkflowResult
    """
    meta = getattr(fn, '_meta', Meta(name=getattr(fn, '__name__', 'unnamed')))
    for k, v in meta_overrides.items():
        setattr(meta, k, v)

    rt = WorkflowRuntime()
    return await rt.run(fn, meta)


async def run_script(script: str, **meta_overrides) -> WorkflowResult:
    """执行 JS 风格脚本字符串

    脚本内:
      META = {"name": "xxx", "phases": [...]}
      async def run():
          phase("A")
          data = await agent("...")
          return data

    agent/parallel/pipeline/phase/log 为内置全局函数，无需 import。
    """
    rt = WorkflowRuntime()
    return await rt.run_script(script, **meta_overrides)


async def run_file(path: str, **meta_overrides) -> WorkflowResult:
    """从文件加载并执行 workflow 脚本"""
    rt = WorkflowRuntime()
    return await rt.run_file(path, **meta_overrides)


# ── 快捷函数（从 ContextVar 获取上下文） ─────────────────────

def phase(title: str) -> None:
    """标记当前阶段"""
    ctx = _workflow_ctx_var.get()
    ctx.phase(title)


async def agent(prompt: str, opts: Optional[Dict] = None) -> Any:
    """启动一个子 Agent

    内部委托给 WorkflowRuntime._build_agent_fn()，
    通过 agentType 查 SubagentRegistry 并合并配置。
    """
    ctx = _workflow_ctx_var.get()
    return await ctx.agent(prompt, opts)


async def parallel(thunks: List[Callable]) -> List[Any]:
    """并行执行多个 thunk（barrier）

    所有 thunk 同时启动，等全部完成后返回。
    失败的 thunk 返回 None（不影响其他）。
    """
    ctx = _workflow_ctx_var.get()
    return await ctx.parallel(thunks)


async def pipeline(items: List, *stages: Callable) -> List[Any]:
    """流水线（无 barrier）

    每个 item 独立流经所有 stage，各 item 并发推进。
    stage 签名: (prev_result, original_item, index) -> new_result
    """
    ctx = _workflow_ctx_var.get()
    return await ctx.pipeline(items, *stages)


def log(msg: str) -> None:
    """输出进度信息"""
    ctx = _workflow_ctx_var.get()
    ctx.log(msg)


# ── 导出 ─────────────────────────────────────────────────────

__all__ = [
    "Meta", "WorkflowContext", "WorkflowResult",
    "WorkflowRuntime", "OrchestrationPatterns",
    "workflow", "run_workflow", "run_script", "run_file",
    "agent", "parallel", "pipeline", "phase", "log",
    "_workflow_ctx_var",
]
