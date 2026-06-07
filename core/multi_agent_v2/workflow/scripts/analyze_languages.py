"""
Workflow 脚本 — 语言对比分析

用法:
    from core.multi_agent_v2.workflow import run_file
    result = await run_file("core/multi_agent_v2/workflow/scripts/analyze_languages.py")

META 定义元数据，run() 是入口。
agent/parallel/pipeline/phase/log 作为内置全局函数使用，无需 import。
"""

META = {
    "name": "语言对比分析",
    "description": "并行分析多种编程语言的特性并综合对比",
    "phases": [
        {"title": "并行分析", "detail": "同时分析多种语言"},
        {"title": "综合汇总", "detail": "对比分析结果"},
    ],
}


async def run():
    phase("并行分析")

    languages = ["Python", "Java", "Rust"]
    results = await parallel([
        lambda lang=l: agent(
            f"深入分析{lang}语言的核心特性、优缺点和适用场景",
            {"agentType": "analyst", "label": lang, "timeout": 120},
        )
        for l in languages
    ])

    phase("综合汇总")

    good = [r for r in results if r and r.success]
    context = "\n\n".join(
        f"【{r.label}】\n{r.text()[:500]}" for r in good
    )
    return await agent(
        f"综合以下各语言分析结果，给出对比结论:\n\n{context}",
        {"agentType": "analyst", "label": "综合对比", "timeout": 180},
    )
