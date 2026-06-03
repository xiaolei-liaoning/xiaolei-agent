# 协作模式 JavaScript 模板

本文件定义了 7 种多 Agent 协作模式的 JavaScript 工作流模板。
可直接用于 `SandboxWorkflowEngine` 或 `PipelineWorkflowEngine`。

## 选择指南

| 任务特征 | 推荐模式 |
|---------|---------|
| 明确步骤顺序 | Pipeline |
| 一个总指挥+多个执行者 | MasterSlave |
| 需要质量把关 | Review |
| 多种方案择优 | Auction |
| 多轮判断达一致 | Consensus |
| 微任务拆解 | Market |
| 复杂问题层层拆解 | Recursive |

---

## 1. Pipeline（流水线）

按阶段顺序执行，每个阶段输出自动传给下一阶段。

```javascript
module.exports = {
  name: "数据采集工作流",
  description: "爬取→分析→报告",
  agents: [
    { id: "crawler",  type: "worker", llm: "ds",   capabilities: ["web","scrape"] },
    { id: "analyzer", type: "worker", llm: "gpt4", capabilities: ["nlp","analysis"] },
    { id: "reporter", type: "worker", llm: "ds",   capabilities: ["writing","report"] },
  ],
  steps: [
    {
      id: "step_crawl",
      agent: "crawler",
      depends_on: [],
      action: {
        tool: "fetch_url",
        params: { url: "{{input_url}}", max_length: 80000 }
      },
      output: "$crawl_data"
    },
    {
      id: "step_analyze",
      agent: "analyzer",
      depends_on: ["step_crawl"],
      action: {
        tool: "llm",
        params: { prompt: "分析以下数据并提取关键信息：\\n" + $crawl_data }
      },
      output: "$analysis"
    },
    {
      id: "step_report",
      agent: "reporter",
      depends_on: ["step_analyze"],
      action: {
        tool: "workspace_file",
        params: { action: "write", path: "/tmp/report.md", content: "# 分析报告\\n\\n" + $analysis }
      },
      output: "$report_path"
    },
  ],
  llm_routing: {
    strategy: "round_robin",
    providers: [
      { name: "ds", model: "ds-chat", weight: 3, rate_limit: 100, concurrency: 5 },
      { name: "gpt4", model: "gpt-4o", weight: 2, rate_limit: 50, concurrency: 5 },
    ],
  },
};
```

---

## 2. MasterSlave（主从）

Master 分解任务 → Slaves 并行执行 → Master 汇总。

```javascript
module.exports = {
  name: "并行分析工作流",
  description: "Master分配→Slaves并行→Master汇总",
  agents: [
    { id: "master",  type: "supervisor", llm: "ds",   capabilities: ["planning","integration"] },
    { id: "worker1", type: "worker",     llm: "gpt4", capabilities: ["analysis"] },
    { id: "worker2", type: "worker",     llm: "gpt4", capabilities: ["analysis"] },
    { id: "worker3", type: "worker",     llm: "ds",   capabilities: ["analysis"] },
  ],
  steps: [
    {
      id: "step_decompose",
      agent: "master",
      depends_on: [],
      action: {
        tool: "llm",
        params: { prompt: "将以下任务分解为3个独立的子任务：\\n{{task}}" }
      },
      output: "$subtasks"
    },
    {
      id: "step_work1",
      agent: "worker1",
      depends_on: ["step_decompose"],
      action: { tool: "llm", params: { prompt: "执行子任务1：" + $subtasks } },
      output: "$result1"
    },
    {
      id: "step_work2",
      agent: "worker2",
      depends_on: ["step_decompose"],
      action: { tool: "llm", params: { prompt: "执行子任务2：" + $subtasks } },
      output: "$result2"
    },
    {
      id: "step_work3",
      agent: "worker3",
      depends_on: ["step_decompose"],
      action: { tool: "llm", params: { prompt: "执行子任务3：" + $subtasks } },
      output: "$result3"
    },
    {
      id: "step_integrate",
      agent: "master",
      depends_on: ["step_work1", "step_work2", "step_work3"],
      action: {
        tool: "llm",
        params: { prompt: "汇总以下3个结果：\\n1: " + $result1 + "\\n2: " + $result2 + "\\n3: " + $result3 }
      },
      output: "$final"
    },
  ],
};
```

---

## 3. Review（评审）

多 Worker 产出 → Reviewer 评审 → 修改 → 定稿。

```javascript
module.exports = {
  name: "代码审查工作流",
  description: "多方案→评审→定稿",
  agents: [
    { id: "dev1",     type: "worker",     llm: "ds",   capabilities: ["coding"] },
    { id: "dev2",     type: "worker",     llm: "gpt4", capabilities: ["coding"] },
    { id: "reviewer", type: "supervisor", llm: "claude", capabilities: ["review"] },
  ],
  steps: [
    {
      id: "step_code1",
      agent: "dev1",
      depends_on: [],
      action: { tool: "llm", params: { prompt: "实现功能：" + "{{task}}" } },
      output: "$impl1"
    },
    {
      id: "step_code2",
      agent: "dev2",
      depends_on: [],
      action: { tool: "llm", params: { prompt: "用不同方法实现：" + "{{task}}" } },
      output: "$impl2"
    },
    {
      id: "step_review",
      agent: "reviewer",
      depends_on: ["step_code1", "step_code2"],
      action: {
        tool: "llm",
        params: {
          prompt: "评审以下两个实现，选择最佳方案并说明理由：\\n方案A：" + $impl1 + "\\n方案B：" + $impl2
        }
      },
      output: "$final"
    },
  ],
};
```

---

## 4. Auction（拍卖）

Agent 竞标 → 评分选最优 → 中标者执行。

```javascript
module.exports = {
  name: "方案竞标工作流",
  description: "竞标→评分→执行",
  agents: [
    { id: "bidder1", type: "worker", llm: "ds",   capabilities: ["design"] },
    { id: "bidder2", type: "worker", llm: "gpt4", capabilities: ["design"] },
    { id: "judge",   type: "supervisor", llm: "ds", capabilities: ["evaluation"] },
    { id: "executor", type: "worker", llm: "gpt4", capabilities: ["implementation"] },
  ],
  steps: [
    {
      id: "step_bid1",
      agent: "bidder1",
      depends_on: [],
      action: { tool: "llm", params: { prompt: "为任务设计技术方案：" + "{{task}}" } },
      output: "$bid1"
    },
    {
      id: "step_bid2",
      agent: "bidder2",
      depends_on: [],
      action: { tool: "llm", params: { prompt: "为任务设计另一方案：" + "{{task}}" } },
      output: "$bid2"
    },
    {
      id: "step_judge",
      agent: "judge",
      depends_on: ["step_bid1", "step_bid2"],
      action: {
        tool: "llm",
        params: { prompt: "评估两个方案，用1-10打分并选择最佳：\\nA: " + $bid1 + "\\nB: " + $bid2 }
      },
      output: "$best_bid"
    },
    {
      id: "step_execute",
      agent: "executor",
      depends_on: ["step_judge"],
      action: { tool: "llm", params: { prompt: "按中标方案执行：\\n" + $best_bid } },
      output: "$result"
    },
  ],
};
```

---

## 5. Consensus（共识）

多轮独立判断，直到达成共识或达到最大轮次。

```javascript
module.exports = {
  name: "共识决策工作流",
  description: "多轮判断→达成共识",
  agents: [
    { id: "judge1", type: "worker", llm: "ds",   capabilities: ["evaluation"] },
    { id: "judge2", type: "worker", llm: "gpt4", capabilities: ["evaluation"] },
    { id: "judge3", type: "worker", llm: "claude", capabilities: ["evaluation"] },
    { id: "facilitator", type: "supervisor", llm: "ds", capabilities: ["mediation"] },
  ],
  max_rounds: 3,
  steps: [
    {
      id: "round1_judge1",
      agent: "judge1",
      depends_on: [],
      action: { tool: "llm", params: { prompt: "独立判断任务：" + "{{task}}" } },
      output: "$j1"
    },
    {
      id: "round1_judge2",
      agent: "judge2",
      depends_on: [],
      action: { tool: "llm", params: { prompt: "独立判断任务：" + "{{task}}" } },
      output: "$j2"
    },
    {
      id: "round1_judge3",
      agent: "judge3",
      depends_on: [],
      action: { tool: "llm", params: { prompt: "独立判断任务：" + "{{task}}" } },
      output: "$j3"
    },
    {
      id: "step_compare",
      agent: "facilitator",
      depends_on: ["round1_judge1", "round1_judge2", "round1_judge3"],
      action: {
        tool: "llm",
        params: { prompt: "比较3个判断：\\nA: " + $j1 + "\\nB: " + $j2 + "\\nC: " + $j3 + "\\n是否一致？如不一致，说明分歧点" }
      },
      output: "$consensus_result"
    },
  ],
};
```

---

## 6. Market（市场）

拆微任务 → Agent 认领 → 分配执行 → 归并。

```javascript
module.exports = {
  name: "微任务市场工作流",
  description: "拆解→认领→执行→归并",
  agents: [
    { id: "planner",  type: "supervisor", llm: "ds",   capabilities: ["decomposition"] },
    { id: "worker_a", type: "worker",     llm: "gpt4", capabilities: ["general"] },
    { id: "worker_b", type: "worker",     llm: "ds",   capabilities: ["general"] },
    { id: "merger",   type: "supervisor", llm: "gpt4", capabilities: ["integration"] },
  ],
  steps: [
    {
      id: "step_split",
      agent: "planner",
      depends_on: [],
      action: {
        tool: "llm",
        params: { prompt: "将任务拆解为2个可并行执行的微任务：\\n" + "{{task}}" }
      },
      output: "$micro_tasks"
    },
    {
      id: "step_work_a",
      agent: "worker_a",
      depends_on: ["step_split"],
      action: { tool: "llm", params: { prompt: "执行微任务1：" + $micro_tasks } },
      output: "$result_a"
    },
    {
      id: "step_work_b",
      agent: "worker_b",
      depends_on: ["step_split"],
      action: { tool: "llm", params: { prompt: "执行微任务2：" + $micro_tasks } },
      output: "$result_b"
    },
    {
      id: "step_merge",
      agent: "merger",
      depends_on: ["step_work_a", "step_work_b"],
      action: {
        tool: "workspace_file",
        params: { action: "write", path: "{{output_path}}", content: $result_a + "\\n\\n" + $result_b }
      },
      output: "$output_path"
    },
  ],
};
```

---

## 7. Recursive（递归）

递归分解直到叶子 → 自底向上合并。

```javascript
module.exports = {
  name: "递归分解工作流",
  description: "递归分解→逐层合并",
  agents: [
    { id: "decomposer", type: "supervisor", llm: "ds",   capabilities: ["decomposition"] },
    { id: "solver",     type: "worker",     llm: "gpt4", capabilities: ["problem_solving"] },
    { id: "integrator", type: "supervisor", llm: "ds",   capabilities: ["integration"] },
  ],
  max_depth: 3,
  steps: [
    {
      id: "step_root",
      agent: "decomposer",
      depends_on: [],
      action: {
        tool: "llm",
        params: { prompt: "判断是否可以分解任务。如果可以，分解为2个子任务；如果已是最简，直接求解。\\n任务：" + "{{task}}" }
      },
      output: "$decomposition"
    },
    {
      id: "step_resolve",
      agent: "solver",
      depends_on: ["step_root"],
      action: { tool: "llm", params: { prompt: "求解：\\n" + $decomposition } },
      output: "$solution"
    },
    {
      id: "step_integrate",
      agent: "integrator",
      depends_on: ["step_resolve"],
      action: {
        tool: "workspace_file",
        params: { action: "write", path: "/tmp/solution.md", content: "# 解决方案\\n\\n" + $solution }
      },
      output: "$final"
    },
  ],
};
```
