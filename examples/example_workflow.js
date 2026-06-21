/**
 * JS Workflow 示例 — 所有可用原语一览
 *
 * 展示：
 *   基础原语：phase(), log(), agent(), parallel(), pipeline(), budget
 *   ✨ Resume 缓存：同一 prompt+opts 的 agent 调用自动命中缓存
 *   ✨ workflow() 嵌套：按名称或路径执行子 Workflow
 *   ✨ 多模型路由：每个 agent() 用 opts.model 指定不同模型
 *
 * 运行: node core/multi_agent_v2/workflow/js_workflow.py 内部调用
 * 或通过 /agents "xxx" 在 CLI 中触发
 */

// =========================================
// 元数据（必须）
// =========================================
export const meta = {
  name: "技术调研+代码审查",
  description: "并行调研多个技术方向，再嵌套子Workflow做代码审查",
  phases: [
    { title: "调研", detail: "并行搜索" },
    { title: "审查", detail: "嵌套子Workflow" },
    { title: "汇总", detail: "综合报告" },
  ],
}

// =========================================
// 入口函数（default 或 run()）
// =========================================
export default async function () {
  // ── phase() 标记阶段进度 ──
  phase("调研")

  // ── log() 输出日志 ──
  log("开始并行调研...")

  // ═══════════════════════════════════════════
  // ✨ 多模型路由
  //   每个 agent() 可以指定不同 model：
  //     - "claude-sonnet-4-6" — 最强的深度分析
  //     - "claude-haiku-4-5"  — 轻量快速查询
  //   不指定则用系统默认模型。
  // ═══════════════════════════════════════════
  const r1 = await agent("Rust 2026年的生态现状", {
    label: "Rust调研",
    model: "claude-sonnet-4-6",  // 复杂任务用最强模型
    timeout: 60,
  })

  const r2 = await agent("Go 1.24 的新特性", {
    label: "Go调研",
    model: "claude-haiku-4-5",  // 简单查询用轻量模型
    timeout: 60,
  })

  // ── parallel() 并行执行多个 agent ──
  const [r3, r4] = await parallel([
    () =>
      agent("Zig语言的亮点", {
        label: "Zig",
        model: "claude-haiku-4-5",
        timeout: 60,
      }),
    () =>
      agent("Mojo语言的亮点", {
        label: "Mojo",
        model: "claude-sonnet-4-6",  // Mojo 比较新，用强模型
        timeout: 60,
      }),
  ])

  // ═══════════════════════════════════════════
  // ✨ workflow() 嵌套
  //   调用另一个 Workflow 脚本作为子流程。
  //   支持两种方式：
  //     1. workflow("name") — 按名称从 .claude/workflows/ 查找
  //     2. workflow({scriptPath: "/path/to/wf.js"}) — 直接指定路径
  //   第二个参数传入 args，子 Workflow 通过全局 args 访问。
  // ═══════════════════════════════════════════
  phase("审查")
  log("嵌套子 Workflow 做代码审查...")

  // 这里演示按路径嵌套（由于没有提交实际文件，用 try/catch 兜底）
  let reviewResult = null
  try {
    reviewResult = await workflow(
      { scriptPath: "/tmp/sample_review.js" },
      { files: ["src/main.rs", "src/lib.rs"] }
    )
  } catch (e) {
    log(`嵌套 workflow 未找到（预期行为）: ${e.message}`)
    reviewResult = "（跳过）"
  }

  // ═══════════════════════════════════════════
  // ✨ Resume 缓存
  //   同一 session 内再次运行相同 workflow 时，
  //   agent("相同的prompt", {相同的opts}) 直接返回缓存结果。
  //   可通过 Python 侧 runtime.cache_stats() 查看命中率。
  // ═══════════════════════════════════════════
  phase("汇总")

  // pipeline() 无屏障流水线
  const topics = ["Rust", "Go", "Zig", "Mojo"]
  const enriched = await pipeline(
    topics,
    (item) => `语言: ${item}`,
    (prev) => `调研结论: 关于${prev}`,
  )

  // budget 预算追踪（支持多模型统计）
  const remaining = budget.remaining()
  const spent = budget.spent()
  const modelStats = budget.modelSpent  // { "claude-sonnet-4-6": 2, "claude-haiku-4-5": 2 }
  log(`剩余预算: ${remaining}, 已用: ${spent}`)
  log(`按模型统计: ${JSON.stringify(modelStats)}`)

  // ── 返回结果 ──
  return {
    results: { rust: r1, go: r2, zig: r3, mojo: r4 },
    pipelineItems: enriched,
    reviewResult: reviewResult,
    modelStats: modelStats,
  }
}
