/**
 * JS Workflow 示例 — 所有可用原语一览
 *
 * 运行: node core/multi_agent_v2/workflow/js_workflow.py 内部调用
 * 或通过 /agents "xxx" 在 CLI 中触发
 */

// =========================================
// 元数据（必须）
// =========================================
export const meta = {
  name: "技术调研",
  description: "并行调研多个技术方向并对比",
  phases: [
    { title: "调研", detail: "并行搜索" },
    { title: "对比", detail: "综合汇总" },
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

  // ── agent() 调用子Agent ──
  //    参数: prompt + opts { label, timeout, schema, model }
  //    返回: 子Agent的输出文本
  const r1 = await agent("Rust 2026年的生态现状", {
    label: "Rust调研",
    timeout: 60,
  })

  const r2 = await agent("Go 1.24 的新特性", {
    label: "Go调研",
    timeout: 60,
  })

  // ── parallel() 并行执行多个 agent ──
  //    参数: 函数数组 [() => agent(...), ...]
  //    返回: 结果数组，失败的返回 null
  const [r3, r4] = await parallel([
    () =>
      agent("Zig语言的亮点", {
        label: "Zig",
        timeout: 60,
      }),
    () =>
      agent("Mojo语言的亮点", {
        label: "Mojo",
        timeout: 60,
      }),
  ])

  // ── pipeline() 无屏障流水线 ──
  //    每个 item 独立流过所有 stage
  //    stage 签名: (prevResult, originalItem, index) => newResult
  phase("对比")
  const topics = ["Rust", "Go", "Zig", "Mojo"]
  const enriched = await pipeline(
    topics,
    (item) => `语言: ${item}`,
    (prev) => `调研结论: 关于${prev}`,
  )

  // ── budget 预算追踪 ──
  const remaining = budget.remaining()
  log(`剩余预算: ${remaining}`)

  // ── 返回结果 ──
  // 可以是字符串、对象、数组——最终被序列化为 JSON
  return {
    results: {
      rust: r1,
      go: r2,
      zig: r3,
      mojo: r4,
    },
    pipelineItems: enriched,
  }
}
