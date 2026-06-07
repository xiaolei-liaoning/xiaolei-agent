"""
Workflow 子系统 — Claude Code Dynamic Workflows 风格的 JS 多 Agent 编排

核心运行时:
  run_claude_workflow(script)  — 执行 JS Workflow 脚本（通过 Node.js 子进程）

模型:
  Meta, PhaseRecord, WorkflowResult

典型用法:
    script = '''
    export const meta = {
        name: "分析对比",
        description: "并行分析两个语言特性",
        phases: [{"title": "研究"}, {"title": "汇总"}]
    }

    export default async function() {
        phase("研究")
        const r1 = await agent("分析Python特性")
        const r2 = await agent("分析Java特性")

        phase("汇总")
        return await agent("对比: " + r1 + " vs " + r2)
    }
    '''
    result = await run_claude_workflow(script)
    # result.output, result.phases, result.success
"""

from .models import Meta, PhaseRecord, WorkflowResult
from .js_workflow import ClaudeCodeWorkflow, WorkflowConfig, run_claude_workflow

# ── 导出 ──

__all__ = [
    "Meta", "PhaseRecord", "WorkflowResult",
    "ClaudeCodeWorkflow", "WorkflowConfig",
    "run_claude_workflow",
]
