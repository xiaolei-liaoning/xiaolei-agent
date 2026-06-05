"""
多Agent 编排示例脚本

展示真正的 Claude Code CLI 风格多Agent协作：
  - @workflow 定义编排脚本
  - phase() 划分阶段
  - parallel() 多Agent并发调研
  - pipeline() 流水线分析
  - agent() 派生子任务
"""

from typing import List

from core.multi_agent_v2.orchestration.orchestrator import (
    phase, log, agent, parallel, pipeline, AgentResult,
    workflow,
)


# ═════════════════════════════════════════════════════════════════════
# 示例1: 多Agent并行研究 → 汇总
# ═════════════════════════════════════════════════════════════════════

@workflow(
    name="并行调研",
    description="多个 Agent 同时搜索不同维度，最后汇总",
    phases=[
        {"title": "并行搜索"},
        {"title": "综合分析"},
        {"title": "汇总报告"},
    ],
)
async def parallel_research(topic: str = "AI Agent"):
    """编排脚本：3个 Agent 并行搜索不同维度，然后1个 Agent 汇总"""

    phase("并行搜索")

    # ── 3 个子 Agent 同时搜索不同维度 ──
    searches = [
        ("技术方案", f"搜索 {topic} 的主流实现框架和技术栈"),
        ("应用场景", f"搜索 {topic} 的典型应用场景和案例"),
        ("未来趋势",  f"搜索 {topic} 的最新发展趋势和挑战"),
    ]

    results = await parallel([
        lambda d=desc, l=label: agent(d, {"label": l})
        for label, desc in searches
    ])

    # 过滤成功的
    good = [r for r in results if r and r.success]
    if not good:
        log("所有搜索均失败")
        return AgentResult(success=False, error="搜索全部失败")

    phase("综合分析")

    # ── 用子 Agent 综合各维度结果 ──
    context = "\n\n".join(
        f"【{r.label}】\n{r.text()[:800]}"
        for r in good
    )
    analysis = await agent(
        f"综合以下 {topic} 的搜索结果，给出结构化分析报告:\n\n{context}",
        {"label": "综合分析", "timeout": 180},
    )

    phase("汇总报告")

    if analysis and analysis.success:
        final = await agent(
            f"基于分析结果，为 {topic} 写出完整的技术报告:\n{analysis.text()[:1000]}",
            {"label": "生成报告", "timeout": 180},
        )
        return final or analysis
    return analysis


# ═════════════════════════════════════════════════════════════════════
# 示例2: 流水线分析
# ═════════════════════════════════════════════════════════════════════

@workflow(
    name="流水线分析",
    description="多个项逐一流经分析→审查→报告阶段",
    phases=[
        {"title": "并行分析"},
        {"title": "审查"},
        {"title": "汇总"},
    ],
)
async def pipeline_analysis(items: List[str] = None):
    """编排脚本：每个 item 经过 分析→审查→汇总 流水线"""
    items = items or ["Python", "Go", "Rust"]

    phase("并行分析")

    # 每个 item 先搜索分析
    analyzed = await pipeline(
        items,
        lambda item, orig, i: agent(
            f"搜索并分析 {orig} 的核心特性和优缺点",
            {"label": f"分析_{orig}"},
        ),
    )

    phase("审查")
    verified = await pipeline(
        analyzed,
        lambda prev, orig, i: (
            agent(
                f"审查以下对 {orig} 的分析结果:\n{prev.text() if prev else '无'}\n\n核实准确性和完整性",
                {"label": f"审查_{orig}"},
            )
            if prev and prev.success
            else AgentResult(success=False, error="前步失败")
        ),
    )

    phase("汇总")
    context = "\n\n".join(
        f"【{r.label}】\n{r.text()[:600]}"
        for r in verified if r and r.success
    )
    final = await agent(
        f"综合以下技术分析，给出横向对比和选择建议:\n\n{context}",
        {"label": "汇总对比", "timeout": 180},
    )
    return final


# ═════════════════════════════════════════════════════════════════════
# 示例3: 研报复盘（MapReduce 模式）
# ═════════════════════════════════════════════════════════════════════

@workflow(
    name="研报复盘",
    description="并行阅读多份资料，交叉验证后生成报告",
    phases=[
        {"title": "阅读"},
        {"title": "交叉验证"},
        {"title": "产出报告"},
    ],
)
async def research_report(topic: str = "大模型"):
    """编排脚本：多 Agent 先独立阅读，再交叉验证，最后合成报告"""

    sources = [
        f"搜索 {topic} 在学术界的最新进展",
        f"搜索 {topic} 在工业界的落地案例",
        f"搜索 {topic} 的核心技术论文",
        f"搜索 {topic} 的开源项目",
    ]

    phase("阅读")
    readings = await parallel(
        [lambda s=s: agent(s, {"label": f"阅读_{i+1}"})
         for i, s in enumerate(sources)],
        max_concurrent=4,
    )

    phase("交叉验证")
    valid_readings = [r for r in readings if r and r.success]
    validation = await parallel(
        [
            lambda idx=i, r=r: agent(
                f"交叉验证以下信息是否准确:\n{r.text()[:500]}",
                {"label": f"验证_{idx+1}"},
            )
            for i, r in enumerate(valid_readings)
        ],
        max_concurrent=3,
    )

    phase("产出报告")
    context = "\n\n".join(
        f"【来源 {i+1}】\n{r.text()[:500]}"
        for i, r in enumerate(valid_readings)
    )
    report = await agent(
        f"以下是关于 {topic} 的多维度资料:\n\n{context}\n\n"
        f"请生成一份完整的研究报告，包含: 概述、各维度分析、交叉验证结论、总体建议",
        {"label": "生成报告", "timeout": 240},
    )
    return report


# ═════════════════════════════════════════════════════════════════════
# 运行入口
# ═════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    async def main():
        import sys
        from core.multi_agent_v2.orchestration.orchestrator import (
            list_workflows, run_workflow,
        )

        print("\n\033[36m━━━ 多Agent 编排示例 ━━━\033[0m")
        print(f"  已注册工作流: {list_workflows()}\n")

        # 默认跑第一个
        choice = "并行调研"
        if len(sys.argv) > 1:
            choice = sys.argv[1]

        print(f"\n  ▶ 运行: {choice}")
        result = await run_workflow(choice)

        print(f"\n\033[36m━━━ 结果 ━━━\033[0m")
        if isinstance(result, AgentResult):
            print(f"  {'✅' if result.success else '⚠️'} 耗时 {result.execution_time:.1f}s")
            if result.output:
                text = str(result.output)
                print(f"\n{text[:1000]}")
        else:
            print(f"  {str(result)[:500]}")

    asyncio.run(main())
