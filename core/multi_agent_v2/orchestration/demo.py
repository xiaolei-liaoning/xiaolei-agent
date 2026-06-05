"""
多Agent编排 Demo

展示真正的 Claude Code CLI 风格编排：
  - @workflow 定义编排脚本
  - 多个 Agent 并发执行子任务
  - 结果在 Agent 间传递
  - phase() 可视化阶段进度

用法:
    python -m core.multi_agent_v2.orchestration.demo          # 交互选择
    python -m core.multi_agent_v2.orchestration.demo 并行调研  # 直接跑指定工作流
"""

import asyncio

from core.multi_agent_v2.orchestration.orchestrator import (
    phase, log, agent, parallel, AgentResult,
    workflow, list_workflows, run_workflow,
)

# ── 1. 导入并注册示例工作流 ──
from core.multi_agent_v2.orchestration.workflows import (
    parallel_research,
    pipeline_analysis,
    research_report,
)


# ═════════════════════════════════════════════════════════════════════
# 现场定义额外工作流
# ═════════════════════════════════════════════════════════════════════

@workflow(
    name="代码审查",
    description="多个 Agent 并行审查代码的不同维度",
    phases=[
        {"title": "并行审查"},
        {"title": "汇总报告"},
    ],
)
async def code_review_workflow(code: str = """def hello():
    print('hello world')
    return None
"""):
    """编排脚本：3 个 Agent 同时从不同角度审查同一段代码"""

    phase("并行审查")

    reviews = await parallel([
        lambda: agent(
            f"审查以下代码的正确性和bug:\n```python\n{code}\n```",
            {"label": "正确性审查"},
        ),
        lambda: agent(
            f"审查以下代码的性能和效率:\n```python\n{code}\n```",
            {"label": "性能审查"},
        ),
        lambda: agent(
            f"审查以下代码的可读性和最佳实践:\n```python\n{code}\n```",
            {"label": "代码风格审查"},
        ),
    ])

    good = [r for r in reviews if r and r.success]
    if not good:
        return AgentResult(success=False, error="审查全部失败")

    phase("汇总报告")

    context = "\n\n".join(
        f"【{r.label}】\n{r.text()[:600]}" for r in good
    )
    final = await agent(
        f"综合以下代码审查意见，给出统一的修复建议:\n\n{context}",
        {"label": "汇总建议", "timeout": 120},
    )
    return final


# ═════════════════════════════════════════════════════════════════════
# 交互入口
# ═════════════════════════════════════════════════════════════════════

async def main():
    import sys

    # 如果传了工作流名称，直接跑
    if len(sys.argv) > 1 and not sys.argv[1].startswith("python"):
        name = sys.argv[1]
        wfs = list_workflows()
        if name not in wfs:
            print(f"\n  ⚠️ 未知工作流: {name}")
            print(f"  可选: {wfs}")
            return
        print(f"\n  ▶ 运行: {name}")
        result = await run_workflow(name)
        _show_result(result)
        return

    # 交互选择
    wfs = list_workflows()
    print("\n" + "=" * 50)
    print("  \033[36m多Agent 编排器 Demo\033[0m")
    print("=" * 50)
    print(f"\n  已注册 {len(wfs)} 个工作流:\n")
    for i, name in enumerate(wfs, 1):
        wf = __import__("core.multi_agent_v2.orchestration.orchestrator",
                       fromlist=["get_workflow"]).get_workflow(name)
        desc = wf.meta.description if wf and hasattr(wf, 'meta') else ""
        phases_str = ""
        if wf and hasattr(wf, 'meta') and wf.meta.phases:
            phases_str = f"  ({' → '.join(p['title'] for p in wf.meta.phases)})"
        print(f"  [{i}] \033[1m{name}\033[0m")
        if desc:
            print(f"      {desc}")
        if phases_str:
            print(f"      {phases_str}")
        print()

    try:
        inp = input("  选择工作流编号或名称 (回车=1): ").strip()
        if not inp:
            inp = "1"
        # 尝试数字
        try:
            idx = int(inp) - 1
            name = wfs[idx] if 0 <= idx < len(wfs) else wfs[0]
        except (ValueError, IndexError):
            name = inp if inp in wfs else wfs[0]

        print(f"\n  ▶ 运行: {name}")
        result = await run_workflow(name)
        _show_result(result)

    except KeyboardInterrupt:
        print("\n  已取消")
    except Exception as e:
        print(f"\n  ❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()


def _show_result(result):
    """展示结果摘要"""
    print(f"\n  \033[36m{'═' * 40}\033[0m")
    print(f"  \033[1m结果\033[0m")
    print(f"  \033[36m{'═' * 40}\033[0m")

    if isinstance(result, AgentResult):
        print(f"  状态: {'✅ 成功' if result.success else '❌ 失败'}")
        print(f"  耗时: {result.execution_time:.1f}s")
        if result.error:
            print(f"  错误: {result.error}")
        if result.output:
            text = str(result.output)
            if len(text) > 800:
                print(f"\n  {text[:800]}...\n  \033[2m(截断, 共 {len(text)} 字符)\033[0m")
            else:
                print(f"\n  {text}")
    else:
        print(f"  {str(result)[:500]}")

    print(f"  \033[36m{'═' * 40}\033[0m")


if __name__ == "__main__":
    asyncio.run(main())
