export const meta = { name: "chain_runner", description: "链式执行 — 先扫描再分析，串行接力" };
export default async function() {
  // ponytail: 串行两阶段，每阶段输出传下阶段
  phase("扫描");
  const scanResult = await agent("列出 /Users/leiyuxuan/Desktop/小雷版agent 项目的顶层目录结构", { label: "扫描", timeout: 35 });
  phase("分析");
  const analysisResult = await agent("基于以下项目结构，分析这个小雷版agent项目的架构特点和技术栈:\n" + (scanResult||""), { label: "分析", timeout: 40 });
  phase("报告");
  return await agent("基于分析结果，生成一份简短的中文报告:\n" + (analysisResult||""), { label: "报告", timeout: 35, isFinal: true });
}
