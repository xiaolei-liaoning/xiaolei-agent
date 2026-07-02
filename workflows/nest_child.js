export const meta = { name: "nest_child", description: "嵌套子工作流 — 被父工作流调用" };
export default async function() {
  phase("子阶段");
  const ctx = globalThis.args || {};
  const parentInfo = ctx.parentOutput ? "父工作流传入: " + ctx.parentOutput : "无父信息";
  return await agent("基于以下上下文，列出Python Web框架的优缺点:\n" + parentInfo, { label: "子Agent", timeout: 30, isFinal: true });
}
