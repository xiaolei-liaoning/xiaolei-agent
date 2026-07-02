export const meta = { name: "nest_parent", description: "嵌套父工作流 — 调用子工作流" };
export default async function() {
  phase("父阶段");
  const r1 = await agent("列出Python的3个Web框架", { label: "父Agent", timeout: 30 });
  phase("嵌套子");
  // ponytail: 通过 workflow() 调用另一个 .js 文件
  const r2 = await workflow("nest_child", { parentOutput: r1 });
  phase("汇总");
  return await agent("对比父结果和子结果:\n父:" + (r1||"") + "\n子:" + (r2||""), { label: "汇总", timeout: 30, isFinal: true });
}
