/**
 * 这个文件由 LLM 根据用户需求自动生成
 * 用户说："帮我写一个 workflow，先并行搜索三个技术趋势，再让一个 Agent 综合对比"
 */

export const meta = {
  name: "技术趋势对比报告",
  description: "并行搜索 AI、Rust、Web 三大技术趋势，然后综合对比生成报告",
  phases: [
    { title: "搜索", detail: "并行搜索三大技术方向" },
    { title: "综合", detail: "综合对比生成报告" },
  ],
}

export default async function () {
  phase("搜索")
  log("开始并行搜索技术趋势...")

  // ── phase 1: 并行搜索 ──
  // 三个 agent() 会在 parallel() 中并发执行
  const [aiTrends, rustTrends, webTrends] = await parallel([
    () =>
      agent("搜索 2026 年 AI 领域的三个最重要趋势", {
        label: "AI趋势",
        model: "claude-sonnet-4-6",
        timeout: 60,
      }),
    () =>
      agent("搜索 Rust 语言在 2026 年的生态发展", {
        label: "Rust生态",
        timeout: 30,
      }),
    () =>
      agent("搜索 Web 前端在 2026 年的新技术方向", {
        label: "Web前端",
        timeout: 30,
      }),
  ])

  // ── phase 2: 综合对比 ──
  phase("综合")
  log("正在综合对比分析...")

  const report = await agent(
    `综合对比以下三个技术方向，输出一份对比报告：

AI 趋势：
${aiTrends}

Rust 生态：
${rustTrends}

Web 前端：
${webTrends}

要求：
1. 每个方向总结 3 个关键点
2. 对比它们的交叉领域
3. 给出学习建议优先级`,
    {
      label: "综合对比",
      model: "claude-sonnet-4-6",
      timeout: 120,
      isFinal: true,
    }
  )

  // ── 输出结果 ──
  const remaining = budget.remaining()
  log(`报告生成完成，剩余 token 预算：${remaining}`)

  return {
    title: "2026技术趋势对比报告",
    aiTrends,
    rustTrends,
    webTrends,
    report,
    modelUsage: budget.modelSpent,
  }
}
