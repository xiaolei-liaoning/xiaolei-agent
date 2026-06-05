# Claude Code CLI 编排模式深度分析

> 基于官方文档 + 社区实践（2025-2026）的综合分析

## 一、概述

Claude Code 的 **Dynamic Workflows（动态工作流）** 是一种**脚本驱动的确定性多Agent编排系统**。
关键区分：**行动计划在脚本代码中**（JavaScript），而不是在 Claude 逐轮对话的判断中。

### 核心哲学

| 维度 | 传统 Chat | Sub-Agent | **Workflow（本分析目标）** |
|------|-----------|-----------|--------------------------|
| 谁决定下一步 | LLM 逐轮判断 | LLM 委派子任务 | **脚本代码控制** |
| 中间结果位置 | LLM 上下文窗口 | 子 Agent 上报 | **脚本变量** |
| 可重复性 | 低（每次不同） | 低 | **高（脚本确定性）** |
| 规模 | 单轮 3-5 步 | 几轮委派 | **数十到数百 Agent** |
| 中断恢复 | 需重来 | 需重来 | **同一会话可恢复** |

---

## 二、脚本结构

### 2.1 meta 块（纯字面量）

每个工作流脚本以 `export const meta` 开头。**必须**是纯字面量——不能用变量、函数调用、模板插值。

```javascript
export const meta = {
  name: '代码审查',                    // 工作流名称
  description: '并行审查代码各维度',    // 人类可读描述
  phases: [                            // 阶段定义（与 runtime phase() 调用精确匹配）
    { title: 'Review', detail: '并行审查各维度' },
    { title: 'Verify', detail: '验证每个发现' },
  ],
};
```

`phases` 中的 `title` 必须与脚本中 `phase()` 调用精确匹配，否则显示错位。

### 2.2 脚本体 — 运行时注入的全局 API

脚本在 sandbox 中执行，全局对象由 workflow runtime 注入——**不是 Node.js，不是 Python**。

#### 核心 API

| API | 签名 | 说明 |
|-----|------|------|
| `phase(title)` | `(string) -> void` | 标记当前进度阶段，UI 分组用 |
| `log(msg)` | `(string) -> void` | 输出进度消息 |
| `agent(prompt, opts?)` | `(string, object) -> AgentResult` | **核心**——启动子 Agent |
| `parallel(thunks)` | `(()->Promise)[] -> any[]` | **屏障**——所有完成才继续 |
| `pipeline(items, ...stages)` | `(any[], ...stageFn) -> any[]` | **无屏障流**——逐项过阶段 |
| `budget` | 全局对象 | token 预算追踪 |
| `workflow(nameOrRef, args?)` | 嵌套子工作流 | 调用另一个已注册/保存的工作流 |
| `args` | 任意 | 用户传入的参数值 |

---

## 三、`agent()` — 子 Agent API 深度解析

### 3.1 完整签名

```javascript
const result = await agent(
  prompt,       // string — 子任务描述
  {
    label,      // string — 显示标签
    phase,      // string — 归属阶段
    schema,     // object — JSON Schema，强制结构化输出
    model,      // string — 模型覆盖（claude-opus-4-8 等）
    isolation,  // 'worktree' — git worktree 隔离
    agentType,  // string — 使用自定义子 Agent 类型（如 'Explore'）
  }
);
```

### 3.2 schema — 结构化输出

**最关键的特性**。指定 schema 后，子 Agent 的响应会被强制校验为 JSON：

```javascript
const BUGS = {
  type: 'object',
  properties: {
    bugs: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'number' },
          severity: { type: 'string', enum: ['low', 'medium', 'high', 'critical'] },
          description: { type: 'string' },
        },
        required: ['file', 'description'],
      },
    },
  },
  required: ['bugs'],
};

const result = await agent('审查代码找 bug', { schema: BUGS });
// result.bugs 已经是类型校验过的结构化数组
// result.bugs[0].file, result.bugs[0].description
```

### 3.3 isolation: worktree — 隔离执行

当多个子 Agent 并发操作文件系统时，设置 `isolation: 'worktree'` 让每个 Agent 在独立的 git worktree 中运行。代价：每次约 200-500ms 的 worktree 创建/清理开销。

### 3.4 model — 异构模型

不像传统编排全部用同一模型，workflow 允许**每 agent() 调用选择不同模型**：

```javascript
// 重任务用 Opus
const analysis = await agent('复杂分析', { model: 'claude-opus-4-8' });
// 轻任务用 Haiku
const search = await agent('简单搜索', { model: 'claude-haiku-4-5-20251001' });
```

### 3.5 返回值

- 无 schema：返回子 Agent 最终文本（string）
- 有 schema：返回校验过的结构化对象。校验在 tool-call 层完成，模型可以自动重试

---

## 四、`parallel()` vs `pipeline()` — 最关键的架构决策

### 4.1 parallel() — 屏障

```javascript
const all = await parallel([
  () => agent('搜索 A', { phase: 'Scan' }),
  () => agent('搜索 B', { phase: 'Scan' }),
  () => agent('搜索 C', { phase: 'Scan' }),
]);
// 这里 —— 必须等上面 3 个全部完成
```

**什么时候用 barrier？** 只在下一阶段**真的需要全部结果在一起**时：

- ✅ 全局去重后再做昂贵的下游处理
- ✅ "0 bugs 找到 → 跳过验证阶段"
- ✅ 对比分析需要所有来源的数据

### 4.2 pipeline() — 无屏障流

```javascript
const results = await pipeline(
  DIMENSIONS,                        // 输入数组
  d => agent(d.prompt, { phase: 'Review', schema: FINDINGS }),  // Stage 1
  review => parallel(                 // Stage 2
    review.findings.map(f => () =>
      agent(`Verify: ${f.title}`, { phase: 'Verify', schema: VERDICT })
    )
  ),
);
// Item A 的 Stage 2 可以和 Item B 的 Stage 1 同时执行
```

**默认选项**。官方文档明确指出：**pipeline 是多阶段工作的默认选择**。

| | parallel() | pipeline() |
|---|---|---|
| 同步点 | **屏障**——全部完成才下一步 | **无屏障**——逐项流式 |
| 墙钟时间 | = 最慢任务的完成时间 | ≈ 最慢单链的完成时间（可能更短） |
| 适用场景 | 全局去重、总量决策、跨项对比 | 大部分多阶段工作 |
| 错误影响 | 单项失败不影响其他 | 单项失败跳过该链后续阶段 |

### 4.3 直觉判断

```
// ❌ 不应该用 barrier
const a = await parallel(...)
const b = transform(a)      // 纯映射/扁平化
const c = await parallel(b.map(...))

// ✅ 应该用 pipeline
const results = await pipeline(
  items,
  stage1,
  r => transform(r).flat(),  // transform 嵌入 stage
  stage3,
)
```

---

## 五、budget — Token 预算追踪

全局 `budget` 对象（由 `+500k` 等指令设置）：

```javascript
budget.total       // 预算上限（null = 无限制）
budget.spent()     // 已用 token
budget.remaining() // 剩余（总 - 已用，无限制则 Infinity）
```

### 典型模式：loop-until-budget

```javascript
while (budget.total && budget.remaining() > 50_000) {
  const result = await agent('再找一轮 bug', { schema: BUGS });
  bugs.push(...result.bugs);
  log(`${bugs.length} found, ${Math.round(budget.remaining()/1000)}k remaining`);
}
```

### 典型模式：loop-until-dry

```javascript
let dry = 0;
while (dry < 2) {
  const found = await agent('找 bug（不要重复已有的）', { schema: BUGS });
  const fresh = found.filter(b => !seen.has(key(b)));
  if (!fresh.length) { dry++; continue; }
  dry = 0;
  // 验证 fresh
}
```

---

## 六、生命周期与约束

### 并发限制

```
实际并发 = min(16, cpu内核数 - 2)
总 Agent 数上限 = 1000（防止死循环）
```

### 中断与恢复

- 运行中可在 `/workflows` 查看进度
- 同一会话内可按 `p` 键恢复
- 恢复基于 journal（确定性回放），已完成 agent() 返回缓存结果
- `Date.now()` / `Math.random()` 在脚本中不可用（破坏确定性）

### 重复性

```
同一脚本 + 同一 args → 100% 缓存命中
编辑脚本后恢复 → 最长未变前缀命中缓存，后续重跑
```

---

## 七、质量模式

以下是从官方+社区提炼的实战模式：

### 7.1 对抗性验证

每个发现由 3 个独立的 Skeptic Agent 审查，目标是**推翻**它：

```javascript
const votes = await parallel([
  () => agent(`证伪: ${claim}. 不确定也倾向已证伪。`, { schema: VERDICT }),
  () => agent(`证伪: ${claim}. 不确定也倾向已证伪。`, { schema: VERDICT }),
  () => agent(`证伪: ${claim}. 不确定也倾向已证伪。`, { schema: VERDICT }),
]);
const survives = votes.filter(v => v && !v.refuted).length >= 2;
```

### 7.2 评审团

同一问题从 N 个不同角度各生成一个方案，再并行评分，胜者综合败者优点：

```javascript
const approaches = await parallel([
  () => agent('MVP-first 方案', { label: 'mvp' }),
  () => agent('risk-first 方案', { label: 'risk' }),
  () => agent('user-first 方案', { label: 'ux' }),
]);
// → 并行评分 → 胜者 + 嫁接
```

### 7.3 多维扫描

同一目标由多个 Agent 从不同路径独立搜索：

```javascript
const results = await parallel([
  () => agent('按容器类型搜索', { label: 'by-container' }),
  () => agent('按文件内容搜索', { label: 'by-content' }),
  () => agent('按实体关系搜索', { label: 'by-entity' }),
]);
// 每个 Agent 不知道自己之外有其他搜索路径
```

### 7.4 完整性批评者

最终阶段用一个 Agent 问"漏了什么"，然后产出到下一轮：

```javascript
const gap = await agent(
  '前面做了什么？漏了什么类别？哪些声明未验证？哪些来源未读？',
  { label: 'completeness-critic' }
);
```

---

## 八、与你的实现的差距分析

对比 `orchestrator.py` 当前实现 vs Claude Code 官方:

| 特性 | Claude Code 官方 | 你的实现 | 差距 |
|------|-----------------|----------|------|
| 脚本语言 | JavaScript（sandbox） | Python（原生） | **JS sandbox 更安全**，但 Python 更易上手 |
| schema 结构化输出 | ✅ tool-call 层强制校验 | ❌ 简易校验 | 缺少强制重试 |
| `pipeline()` 无屏障 | ✅ 正式支持 | ✅ 已实现 | 基本一致 |
| `parallel()` 并发控制 | ✅ `min(16, cpus-2)` | ✅ max_concurrent | 基本一致 |
| Agent ID 隔离 | ✅ 每个 agent() 独立 | ✅ light_mode WorkAgent | 基本一致 |
| budget 追踪 | ✅ 全局 budget 对象 | ❌ 简易实现 | **需要加强** |
| 确定性恢复 | ✅ journal + playback | ❌ 无 | 重要特性 |
| git worktree 隔离 | ✅ isolation: worktree | ❌ 无 | 大项目必需 |
| 异构模型 | ✅ 每 agent() 可选模型 | ❌ 固定 | 节省成本关键 |
| meta 块提前展示 | ✅ phases 在跑前预览 | ❌ 无提前展示 | UX 改进 |
| 中断恢复 | ✅ p 键恢复 | ❌ 无 | 大任务关键 |
| 命名工作流持久化 | ✅ 保存到 .claude/workflows/ | ✅ workflow 注册表 | 部分一致 |

### 关键差距详解

1. **schema 结构化输出** — Claude Code 在 tool-call 层完成 schema 校验和重试，模型输出不合法时自动重试。你的实现只是一个简易的 `required` 字段检查。

2. **确定性恢复** — 这是最复杂但最有价值的特性。Claude Code 为每个 agent() 调用写 journal，恢复时已完成的直接返回缓存。需要在 Python 中实现等价的 `journal replay`。

3. **git worktree 隔离** — 当多个子 Agent 并发修改同一个文件时必然冲突。worktree 给每个 Agent 一个独立的工作目录。可以使用 `git worktree add` 实现。

4. **异构模型路由** — Claude Code 允许每个 agent() 指定不同模型（Opus 做复杂推理、Haiku 做简单搜索），对成本控制至关重要。当前你的所有子 Agent 共用同一个 LLM 后端。

---

## 九、总结

Claude Code Workflow 的核心设计决策可归纳为：

1. **脚本即计划** — 不再由 LLM 逐轮决定下一步，而是脚本编码了整个 DAG
2. **pipeline > parallel** — 默认无屏障流，barrier 只在真正需要时才用
3. **结构化输出优先** — schema 强制让子 Agent 返回可编程消费的 JSON
4. **确定性可恢复** — journal 让大规模 (1000 Agent) 编排可以中断继续
5. **异构模型** — 好钢用在刀刃上，简单任务不给 Opus 浪费

---

*文档最后更新: 2026-06-05*
