<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>两种多Agent架构对比 — 小龙虾Agent</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #f0f2f5; font-family: -apple-system, "Microsoft YaHei", sans-serif; padding: 40px; color: #333; }
  .container { max-width: 1400px; margin: 0 auto; }
  h1 { text-align: center; font-size: 28px; margin-bottom: 8px; color: #1a1a2e; }
  .subtitle { text-align: center; font-size: 14px; color: #666; margin-bottom: 40px; }
  .section { background: #fff; border-radius: 12px; padding: 32px; margin-bottom: 40px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
  .section-title { font-size: 20px; font-weight: 600; margin-bottom: 6px; }
  .section-badge {
    display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 4px;
    font-weight: 500; margin-bottom: 16px;
  }
  .badge-v1 { background: #fff0f0; color: #d32f2f; }
  .badge-v2 { background: #f5f0ff; color: #6b3fa0; }
  .mermaid-wrap { overflow: auto; margin: 16px 0; position: relative; }
  .mermaid-wrap svg { max-width: 100%; height: auto; transition: transform 0.2s ease; }
  .mermaid-wrap.zoomed svg { max-width: none; }
  .zoom-controls {
    display: flex; gap: 6px; margin-bottom: 8px; align-items: center;
    position: sticky; top: 0; z-index: 10;
  }
  .zoom-btn {
    display: inline-flex; align-items: center; justify-content: center;
    width: 32px; height: 32px; border: 1px solid #d0d0d0; border-radius: 6px;
    background: #fff; cursor: pointer; font-size: 18px; line-height: 1;
    color: #555; transition: all 0.15s;
  }
  .zoom-btn:hover { background: #f0f0f0; border-color: #999; }
  .zoom-level { font-size: 12px; color: #888; min-width: 40px; text-align: center; font-variant-numeric: tabular-nums; }
  .zoom-reset { font-size: 12px; padding: 0 8px; height: 32px; }
  .divider { display: flex; align-items: center; gap: 16px; margin: 40px 0 20px; color: #999; font-size: 13px; }
  .divider-line { flex: 1; height: 1px; background: #e0e0e0; }
  table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }
  th, td { padding: 10px 14px; border: 1px solid #e0e0e0; text-align: left; }
  th { background: #f5f5f5; font-weight: 600; }
  tr:hover { background: #fafafa; }
  .tag { display: inline-block; padding: 1px 8px; border-radius: 3px; font-size: 11px; font-weight: 500; }
  .tag-v1 { background: #ffe0e0; color: #c62828; }
  .tag-v2 { background: #e8e0ff; color: #5e35b1; }
  .legend { display: flex; gap: 24px; margin: 12px 0; flex-wrap: wrap; font-size: 13px; }
  .legend-item { display: flex; align-items: center; gap: 6px; }
  .legend-dot { width: 14px; height: 14px; border-radius: 3px; }
  .legend-arrow { font-size: 18px; }
  footer { text-align: center; font-size: 12px; color: #999; margin-top: 32px; }
  @media (max-width: 768px) { body { padding: 16px; } .section { padding: 16px; } }
</style>
</head>
<body>
<div class="container">

<h1>两种多Agent架构对比</h1>
<p class="subtitle">小雷版小龙虾 Agent · V1 队长-队员模式 vs V2 智能协作型</p>
<p style="text-align:center;font-size:13px;color:#4CAF50;margin-bottom:30px;">
  🟢 67/67 深度集成测试通过（2026-05-23）| 实测发现并修复 7 个 bug
</p>

<!-- ============================== 架构一 ============================== -->
<div class="section">
  <div class="section-title">架构一：V1 队长-队员模式</div>
  <span class="section-badge badge-v1">伪多Agent — 1 LeaderAgent + N 个 LLMAgent(Worker) + KEPA/反思/上下文</span>

  <div class="legend">
    <span class="legend-item"><span class="legend-dot" style="background:#1565C0"></span> 队长Agent（LeaderAgent）</span>
    <span class="legend-item"><span class="legend-dot" style="background:#66BB6A"></span> 队员Agent（LLMAgent Worker）</span>
    <span class="legend-item"><span class="legend-dot" style="background:#D32F2F"></span> Agent池（V1LeaderPool）</span>
    <span class="legend-item"><span class="legend-dot" style="background:#FFA726"></span> 执行流程</span>
    <span class="legend-item"><span class="legend-dot" style="background:#7C8BFF"></span> 基础支撑</span>
    <span class="legend-item"><span class="legend-arrow">→</span> 控制流</span>
    <span class="legend-item"><span class="legend-arrow">..→</span> 生命周期</span>
  </div>

  <div class="mermaid-wrap" id="mermaid-v1">
    <div class="zoom-controls">
      <button class="zoom-btn" onclick="zoomIn('mermaid-v1')" title="放大">+</button>
      <button class="zoom-btn" onclick="zoomOut('mermaid-v1')" title="缩小">−</button>
      <button class="zoom-btn zoom-reset" onclick="zoomReset('mermaid-v1')" title="重置">1:1</button>
      <span class="zoom-level" id="zoom-level-mermaid-v1">100%</span>
    </div>
<pre class="mermaid">
flowchart TB
  subgraph V1LeaderPool["V1LeaderPool — 创建+生命周期管理"]
    Create["create_team(worker_count=3, max_workers=5)<br/>返回 (LeaderAgent, List[LLMAgent])"]

    Share["share_memory(agents)<br/>向 SharedBus 发布每个 Agent 的执行摘要"]
    Discard["discard(agents)<br/>从 _all_agents 字典移除"]
  end

  subgraph Team["1 个 Leader + 最多 5 个 Worker（默认 3 个活跃）"]
    Leader["LeaderAgent(LLMAgent)<br/>LEADER 角色<br/><small>supervise_task() 主循环<br/>_decompose_task → _assign →<br/>_execute_batch → _analyze_results</small>"]

    W1["LLMAgent 队员1<br/>WORKER 角色<br/>活跃"]
    W2["LLMAgent 队员2<br/>WORKER 角色<br/>活跃"]
    W3["LLMAgent 队员3<br/>WORKER 角色<br/>活跃"]
    W4["LLMAgent 队员4<br/>WORKER 角色<br/>休眠"]
    W5["LLMAgent 队员5<br/>WORKER 角色<br/>休眠"]
  end

  subgraph Flow["执行流程（分批循环，最多 3 轮）"]
    direction LR
    D["① 队长 _decompose_task()<br/>LLM 将任务分解为<br/>子任务列表"]
    A["② 队长 _assign()<br/>round-robin 分配<br/>给活跃 Worker"]
    E["③ 队长 _execute_batch()<br/>asyncio.gather<br/>Workers 并行执行"]
    AN["④ 队长 _analyze_results()<br/>LLM 分析结果<br/>返回 decision"]

    D --> A --> E --> AN
    AN -->|"decision=retry<br/>重试失败任务"| A
    AN -->|"decision=reassign<br/>唤醒更多 Worker<br/>重试失败任务"| A
  end

  subgraph LLMAgentInternal["每个 LLMAgent 内部（KEPA + RAG + 反问 + 上下文）"]
    direction TB
    Rag["_rag_query()<br/>RAG 检索增强<br/><small>RAGSearchEngine<br/>search_and_learn</small>"]
    Kepa["_kepa_reflect()<br/>KEPA 反思闭环<br/><small>think→act→reflect<br/>置信度≥0.85 退出<br/>最多 3 次迭代</small>"]
    Ask["_ask_user()<br/>反问机制<br/><small>LLM 调用失败时<br/>降级前反问用户</small>"]
    Ctx["ContextMemory<br/>上下文记忆<br/><small>最近 20 条记录<br/>环形缓冲</small>"]
    Rag --- Kepa
    Kepa --- Ask
    Ask --- Ctx
  end

  subgraph Infra["基础支撑"]
    LLM["_llm_json()<br/>asyncio.Lock 串行<br/>LLM JSON 解析"]
    QuestionReg["QuestionRegistry<br/>反问注册中心<br/><small>core.agents.agent_communication</small>"]
    ToolReg["ToolRegistry<br/>工具注册中心"]
  end

  %% 队内：队长持有所有 Worker 引用
  Create --> Leader
  Create --> W1
  Create --> W2
  Create --> W3
  Create --> W4
  Create --> W5
  W4 -.-x Dormant["激活条件：队长 decision=reassign 时<br/>_activate_worker(needed_count)"]
  W5 -.-x Dormant
  style Dormant fill:#f5f5f5,stroke:#ddd,stroke-dasharray:4,color:#999

  %% 队长驱动执行流程
  Leader -.->|"supervise_task()<br/>传入 Workers 列表"| Flow

  %% Worker 参与执行
  W1 -.->|"process_message()"| E
  W2 -.->|"process_message()"| E
  W3 -.->|"process_message()"| E

  %% 内部结构
  Leader -.-> LLMAgentInternal
  W1 -.-> LLMAgentInternal
  W2 -.-> LLMAgentInternal
  W3 -.-> LLMAgentInternal

  %% 生命周期
  Leader -.->|"执行完成"| Share
  W1 -.-> Share
  W2 -.-> Share
  W3 -.-> Share
  Share -.->|"下一个"| Discard

  %% 基础设施
  Leader -.->|"_llm_json()"| LLM
  Leader -.->|"_ask_user()"| QuestionReg
  ToolReg -.->|"工具注入"| LLMAgentInternal

  %% 架构特点
  Leader ~~~ Notes1["<b>★ 架构特点</b><br/>• V1LeaderPool.create_team() 返回 (LeaderAgent, List[LLMAgent])，不储存角色模板<br/>• AgentRole 只有两种：LEADER / WORKER，Worker 直接使用 LLMAgent 类<br/>• LeaderAgent 继承 LLMAgent，新增 supervise_task() 主循环<br/>• 分批次执行：LLM分解→round-robin分配→asyncio.gather并行执行→LLM分析→循环/完成<br/>• 决策三选一：complete（完成）/ retry（重试失败子任务）/ reassign（唤醒更多 Worker+重试）<br/>• 每个 LLMAgent 有 KEPA / RAG(RAGSearchEngine) / 反问(QuestionRegistry) / ContextMemory<br/>• share_memory() 通过 V2 的 SharedBus 广播 Message(MessageType.AGENT_BROADCAST)<br/>• 无 Agent 间协作协商，队长单向监管 Worker，适合 1+N 分层监管场景<br/><br/><b style='color:#D32F2F;'>🔴 实测已修复的 Bug</b><br/>• test_supervise_reassign_wakes_workers: mock 永远返回 reassign 不返回 complete，导致流程无法正常结束 ⇒ 修复: 第二轮 mock 返回 complete"]
  style Notes1 fill:#fff5f5,stroke:#ff6b6b,stroke-dasharray:4
</pre>
  </div>
</div>

<!-- ============================== 分隔 ============================== -->
<div class="divider"><span class="divider-line"></span> 实测验证 <span class="divider-line"></span></div>

<!-- ============================== 实测验证 ============================== -->
<div class="section" style="border-left: 4px solid #4CAF50;">
  <div class="section-title">实测验证报告</div>
  <span class="section-badge badge-v2">2026-05-23 实测 67/67 通过</span>

  <table>
    <thead>
      <tr><th>项目</th><th>结果</th><th>详情</th></tr>
    </thead>
    <tbody>
      <tr><td><strong>V1 测试</strong></td><td>40/40 ✅</td><td>LeaderPool 生命周期、supervise_task 完整流程（complete/retry/reassign 三条路径）、KEPA 反思闭环、handle_message（含 RAG+反问降级）、Worker 故障隔离</td></tr>
      <tr><td><strong>V2 测试</strong></td><td>27/27 ✅</td><td>OnDemandAgentPool、WorkAgent 5 种能力追加、IntelligentScheduler 6 子模块、CircuitBreaker 完整状态机、SharedBus pub/sub/memory、CollaborationStrategy 5 种初始化</td></tr>
      <tr><td><strong>V1 Bug 修复</strong></td><td>1 个</td><td>test_supervise_reassign_wakes_workers: mock 永远返回 reassign 无法 complete → 第二轮 mock 返回 complete 确保流程走通</td></tr>
      <tr><td><strong>V2 Bug 修复</strong></td><td>6 个</td><td>3 测试 bug（缺 await、copy-paste 断言）+ 3 源码 bug（熔断器 record_success 不重置、can_execute 不做超时过渡、结果聚合器对 list 调 .get()）</td></tr>
      <tr><td><strong>V2 shell 脚本</strong></td><td>部分失效</td><td><code>test_new_arch.sh</code> 引用了不存在的 <code>test_task_executor_integration.py</code>，并发测试因 agent_pool=None 失败（非代码问题）</td></tr>
    </tbody>
  </table>

  <p style="margin-top: 12px; font-size: 13px; color: #666;">
    📌 测试方式：pytest 深度集成测试，通过 mock LLM 调用聚焦代码逻辑正确性。<br>
    📌 快速验证：<code>python -m pytest tests/integration/test_v1_v2_deep.py -v</code>
  </p>
</div>

<div class="divider"><span class="divider-line"></span> V1 → V2 演进 <span class="divider-line"></span></div>

<!-- ============================== 架构二 ============================== -->
<div class="section">
  <div class="section-title">架构二：V2 智能协作型多Agent</div>
  <span class="section-badge badge-v2">真多Agent — IntelligentScheduler + OnDemandAgentPool + 5种协作策略</span>

  <div class="legend">
    <span class="legend-item"><span class="legend-dot" style="background:#9B59B6"></span> 调度器</span>
    <span class="legend-item"><span class="legend-dot" style="background:#8E44AD"></span> 协作策略层</span>
    <span class="legend-item"><span class="legend-dot" style="background:#2E7D32"></span> Agent池+生命周期</span>
    <span class="legend-item"><span class="legend-dot" style="background:#E65100"></span> Agent内部心智</span>
    <span class="legend-item"><span class="legend-dot" style="background:#1565C0"></span> 基础设施/通信</span>
    <span class="legend-item"><span class="legend-arrow">→</span> 控制流</span>
    <span class="legend-item"><span class="legend-arrow">↔</span> 双向通信</span>
    <span class="legend-item"><span class="legend-arrow">..→</span> 依赖/注入</span>
    <span class="legend-item"><span class="legend-arrow">-·→</span> 生命周期</span>
  </div>

  <div class="mermaid-wrap" id="mermaid-v2">
    <div class="zoom-controls">
      <button class="zoom-btn" onclick="zoomIn('mermaid-v2')" title="放大">+</button>
      <button class="zoom-btn" onclick="zoomOut('mermaid-v2')" title="缩小">−</button>
      <button class="zoom-btn zoom-reset" onclick="zoomReset('mermaid-v2')" title="重置">1:1</button>
      <span class="zoom-level" id="zoom-level-mermaid-v2">100%</span>
    </div>
<pre class="mermaid">
flowchart TB
  subgraph Scheduler["IntelligentScheduler — 核心大脑"]
    direction TB
    TA["TaskAnalyzer<br/>任务分析<br/><small>analyze() / understand()<br/>estimate_complexity()</small>"]
    MS["ModeSelector<br/>模式选择<br/><small>select() → CollaborationMode<br/>关键词→历史→LLM→启发式</small>"]
    EP["ExecutionPlanner<br/>执行规划<br/><small>create_plan() 按模式分发<br/>_create_pipeline / _master_slave<br/>_review / _auction / _hybrid</small>"]
    CM["CapabilityMatcher<br/>能力匹配<br/><small>match() → (Agent, score)<br/>assess_task_complexity()</small>"]
    RA["ResultAggregator<br/>结果聚合<br/><small>aggregate() → 去重→冲突消解<br/>→质量评分→总结</small><br/><span style='color:#D32F2F;font-size:11px'>⚠ 实测发现1个bug</span>"]
    ASK["IntelligentScheduler.schedule()<br/>反问确认<br/><small>模式选择+Agent分配后<br/>反问用户确认后才继续</small>"]

    TA --> MS
    MS --> EP
    EP -.->|"内部依赖"| CM
    EP --> ASK
    ASK --> RA
  end

  subgraph Strategies["5 种协作策略"]
    Pipe["PipelineStrategy<br/>流水线<br/><small>按阶段顺序执行<br/>+ RecursiveTaskDecomposer</small>"]
    MSStrat["MasterSlaveStrategy<br/>主从<br/><small>主分解 + 从并行执行<br/>主聚合校验</small>"]
    RevStrat["ReviewStrategy<br/>评审<br/><small>并行工作 + Reviewer<br/>评审 + ConsensusMechanism</small>"]
    AucStrat["AuctionStrategy<br/>拍卖<br/><small>Agent 竞标→中标执行<br/>+ DynamicTeamForming</small>"]
    HybStrat["HybridStrategy<br/>混合<br/><small>按复杂度分支选择<br/>简单 / 主从 / 评审</small>"]
  end

  subgraph Pool["OnDemandAgentPool — 按需创建"]
    Create["create_agents(task, count)<br/>创建 count 个全新 WorkAgent"]
    ShareMem["share_memory(agents)<br/>每个 Agent 记忆摘要<br/>发布到 SharedBus"]
    Discard["discard(agents)<br/>从 _all_agents 移除"]
  end

  subgraph AgentInternal["每个 WorkAgent 内部"]
    direction TB
    Adapt["adapt_to_task(task)<br/>追加 5 个专项能力<br/>不做关键词裁剪"]
    Think["think(task)<br/>生成 Thought<br/>含 plan + tool_calls"]
    Act["act(plan, tool_calls)<br/>执行计划<br/>调用工具"]
    Reflect["reflect(result)<br/>反思总结<br/>记录 work_history"]
    Adapt --> Think --> Act --> Reflect
  end

  subgraph Infra["基础设施"]
    TaskExe["TaskExecutor<br/>任务执行引擎<br/><small>execute() 委托给<br/>选中的 CollaborationStrategy</small>"]
    CB["CircuitBreaker<br/>熔断器<br/><small>5次失败触发 OPEN<br/>60s → HALF_OPEN</small><br/><span style='color:#D32F2F;font-size:11px'>⚠ 实测发现2个bug</span>"]
    ToolReg["ToolRegistry<br/>工具注册中心<br/><small>所有工具均可调用<br/>不做角色裁剪</small>"]
    SnapStore["TaskSnapshotStore<br/>快照存储<br/><small>决策日志·中间结果<br/>全链路审计</small>"]
  end

  subgraph Comm["通信层"]
    SharedBus["SharedBus<br/>全局消息总线<br/><small>publish / subscribe / send_direct<br/>通配符匹配·点对点队列<br/>共享内存 update/get_context<br/>任务快照 save/get_snapshot</small>"]
    GCC["GlobalContextCenter<br/>全局上下文中心<br/><small>任务生命周期·Agent注册<br/>事件系统·Token预算<br/>MySQL DB持久化</small>"]
  end

  %% 调度 → 策略
  MS -.->|"select() → 模式"| Pipe
  MS -.-> MSStrat
  MS -.-> RevStrat
  MS -.-> AucStrat
  MS -.-> HybStrat

  %% 策略 → 执行
  TaskExe -.->|"委托执行"| Pipe
  TaskExe -.-> MSStrat
  TaskExe -.-> RevStrat
  TaskExe -.-> AucStrat
  TaskExe -.-> HybStrat

  %% 调度 → 创建 Agent
  EP --> Create

  %% Agent 生命周期
  Create --> Adapt
  Adapt -.->|"执行完成"| ShareMem
  ShareMem -.->|"然后"| Discard

  %% 通信
  SharedBus <-->|"pub/sub"| AgentInternal
  SharedBus <-->|"事件/状态"| GCC
  SharedBus <-->|"记忆广播"| ShareMem

  %% 基础设施依赖
  TaskExe -.->|"调用"| Scheduler
  CB -.->|"熔断保护"| AgentInternal
  ToolReg -.->|"全部工具注入"| Act
  SnapStore -.->|"快照持久化"| SharedBus

  %% 全局上下文
  GCC -.->|"状态同步"| Scheduler
  GCC -.->|"上下文注入"| AgentInternal

  %% 架构特点
  Scheduler ~~~ Notes2["<b>★ 架构特点</b><br/>• 无预注册 Agent — OnDemandAgentPool.create_agents(task, count) 创建全新 WorkAgent<br/>• IntelligentScheduler 5子模块：TaskAnalyzer→ModeSelector→ExecutionPlanner(CapabilityMatcher)→反问确认→ResultAggregator<br/>• ModeSelector 选择策略优先级：关键词匹配 > 历史经验(跨次学习) > LLM 决策 > 启发式兜底<br/>• 5 种协作模式 (Pipeline / MasterSlave / Review / Auction / Hybrid)，每种有独立策略类<br/>• TaskExecutor.execute() 委托给选中的 CollaborationStrategy，消除双路执行路径<br/>• 每个 WorkAgent 通过 adapt_to_task() 追加全部 5 种能力（analysis/execution/review/research/integration），不做裁剪<br/>• WorkAgent 执行流程：think()→ act()→ reflect()→ 记录 work_history（上限 100 条）<br/>• CircuitBreaker 熔断保护（5次失败→OPEN→60s→HALF_OPEN→CLOSED）<br/>• SharedBus（pub/sub/direct/共享内存/快照）+ GlobalContextCenter（状态/事件/Token/DB持久化）<br/><br/><b style='color:#D32F2F;'>🔴 实测已修复的 Bug</b><br/>① CircuitBreaker.record_success(): CLOSED/OPEN 状态下不重置 failure_count ⇒ 修复: 任意状态都重置<br/>② CircuitBreaker.can_execute(): 不检查 OPEN→HALF_OPEN 超时过渡 ⇒ 修复: can_execute 内直接做超时检测<br/>③ ResultAggregator.aggregate(): _resolve_conflicts 返回 list，但调用 .get('_conflicts') 崩溃 ⇒ 修复: 从 list 末尾提取 conflicts dict 后截断<br/>④ 3 个测试 bug（await 遗漏、copy-paste 断言错误）"]
  style Notes2 fill:#f5f0ff,stroke:#6b3fa0,stroke-dasharray:4
</pre>
  </div>
</div>

<!-- ============================== 对比表 ============================== -->
<div class="section">
  <div class="section-title">核心差异对比</div>

  <table>
    <thead>
      <tr>
        <th style="width:14%">维度</th>
        <th style="width:43%"><span class="tag tag-v1">V1 队长-队员模式</span></th>
        <th style="width:43%"><span class="tag tag-v2">V2 智能协作型</span></th>
      </tr>
    </thead>
    <tbody>
      <tr><td><strong>Agent 定义</strong></td><td>V1LeaderPool 创建 1 个 LeaderAgent（继承 LLMAgent）+ 最多 5 个 LLMAgent（Worker）。<br/>每个有 KEPA / RAG / 反问 / ContextMemory</td><td>统一 <code>WorkAgent(BaseAgent)</code>，OnDemandAgentPool 按需创建。<br/>每个有 Mind(LLM推理+工具选择) + MemorySystem(短期/长期/情景)</td></tr>
      <tr><td><strong>Agent 类型</strong></td><td>两种：<code>AgentRole.LEADER</code>（队长）+ <code>AgentRole.WORKER</code>（队员）<br/>LeaderAgent 继承 LLMAgent，增加 supervise_task() 主循环<br/>Worker 直接用 LLMAgent (role=WORKER)，只负责 execute_with_context()</td><td>单一 <code>WorkAgent</code>（type=AgentType.WORKER），无预注册不预设 specialize。<br/><code>adapt_to_task()</code> 追加 5 种能力（analysis/execution/review/research/integration），不做关键词裁剪。</td></tr>
      <tr><td><strong>角色模板</strong></td><td>无。AgentRole 只有 LEADER(队长) / WORKER(队员) 两个值。<br/>Worker 角色配置：role="队员", desc="负责执行队长分配的具体任务", format="execute"</td><td>已删除（<code>role_templates.py</code> 已移除），不再有预设角色概念。</td></tr>
      <tr><td><strong>Agent 创建方式</strong></td><td><code>V1LeaderPool.create_team(worker_count=3, max_workers=5)</code><br/>返回 (LeaderAgent, List[LLMAgent]) — 1 队长 + 5 个 Worker（默认 3 活跃 2 休眠）</td><td><code>OnDemandAgentPool.create_agents(task, count)</code> — 按协作模式估算数量后创建 count 个全新 WorkAgent</td></tr>
      <tr><td><strong>Agent 能力</strong></td><td>统一 LLMAgent 基类能力：<br/>• RAG 检索（RAGSearchEngine.search_and_learn）<br/>• KEPA 反思（_kepa_reflect：置信度≥0.85 退出，最多 3 次迭代）<br/>• 反问用户（_ask_user → QuestionRegistry，仅 LLM 失败时）<br/>• ContextMemory 环形缓冲（最近 20 条）<br/>队长额外有：_decompose_task / _analyze_results / _activate_worker</td><td>每个 WorkAgent 通过 <code>adapt_to_task()</code> 追加全套 5 种能力：<br/>• analysis_{type}（expertise=0.8）<br/>• execution_{type}（expertise=0.8）<br/>• review_{type}（expertise=0.85）<br/>• research_{type}（expertise=0.75）<br/>• integration_{type}（expertise=0.8）<br/>不做关键词过滤，天然可调用所有工具。</td></tr>
      <tr><td><strong>协作模式</strong></td><td>1+N 队长单向监管模式。<br/>Leader 分解→分配→并行执行→分析→循环，决策 complete/retry/reassign。<br/>无 Agent 间协作协商。</td><td>5 种策略由 ModeSelector 自动选择：<br/>Pipeline / MasterSlave / Review / Auction / Hybrid。<br/>策略执行完整协作：Leader 分解+聚合 / 并行工作+评审 / 竞标+执行 / 按复杂度分支。</td></tr>
      <tr><td><strong>调度器结构</strong></td><td><code>V1LeaderPool</code>（创建队伍 + share_memory + discard）<br/><code>LeaderAgent.supervise_task()</code>（流程编排，非独立调度器类）</td><td><code>IntelligentScheduler</code> 含 6 个子模块：<br/>TaskAnalyzer → ModeSelector → ExecutionPlanner(CapabilityMatcher 注入) → 反问确认 → ResultAggregator</td></tr>
      <tr><td><strong>上下文管理</strong></td><td>每个 LLMAgent 独立 ContextMemory（环形缓冲，最近 20 条）<br/>队长持有完整任务上下文（result list / remaining list），Worker 只持子任务上下文</td><td>GlobalContextCenter 单例：全局上下文 + 事件系统(EventType) + Token预算三级剪枝 + MySQL DB持久化<br/>SharedBus 共享内存 (update/get_context)</td></tr>
      <tr><td><strong>任务分配</strong></td><td><code>LeaderAgent._decompose_task()</code> LLM 分解 →<br/><code>_assign()</code> round-robin 分配给活跃 Worker →<br/><code>_execute_batch()</code> asyncio.gather 并行执行 →<br/><code>_analyze_results()</code> LLM 分析 → 循环最多 3 轮</td><td><code>ModeSelector.select()</code> 选择模式 →<br/><code>ExecutionPlanner.create_plan()</code> 按模式分发到私有方法 →<br/><code>CapabilityMatcher.match()</code> 评分匹配 Agent →<br/><code>TaskExecutor.execute()</code> 委托给 CollaborationStrategy</td></tr>
      <tr><td><strong>通信方式</strong></td><td>队长 → Worker 单向。<br/>Leader 通过 AgentMessage 下发子任务，Worker process_message() 返回 JSON 字符串。</td><td>SharedBus 消息总线：publish(topic, Message) / subscribe(topic, callback) / send_direct(receiver, Message) / receive_direct()。<br/>Message 含 MessageType 枚举（8 种类型），支持通配符匹配。</td></tr>
      <tr><td><strong>Agent 内部分层</strong></td><td>KEPA + RAG + 反问 + ContextMemory（四个独立方法）<br/>_handle_message() 串行：RAG 检索 → LLM 调用 → KEPA 反思 → 反问降级</td><td>Mind（LLM驱动推理 + ToolRegistry 工具选择 + LLM Router 调用）<br/>+ MemorySystem（短期 / 长期 / 情景三种记忆存储）<br/>+ think → act → reflect 三阶段循环</td></tr>
      <tr><td><strong>反射机制</strong></td><td><code>_kepa_reflect()</code>：LLM 评估置信度(0-1)，decision 三选一(continue/retry/fail)。<br/>置信度 ≥0.85 或 decision=continue 退出，最多 3 次迭代。</td><td>think → act → reflect 三阶段循环 + KEPA 反思闭环 + 只读步骤并行/写步骤串行。<br/>AdaptivePipelineWithReflection 含 ReflectionTrigger + LLMReflection + 5 种决策(CONTINUE/SKIP_NEXT/ADD_STEPS/REORDER/RETRY/FAIL)。</td></tr>
      <tr><td><strong>故障处理</strong></td><td>单 Agent 故障不影响其他（each _run_one 独立 try/except）。<br/>队长 LLM 分析失败时保守重试（返回 decision=retry）。</td><td>CircuitBreaker 熔断器（CLOSED→OPEN(5次失败)→HALF_OPEN(60s)→CLOSED）+ 自动重试 + 降级 + handle_failure() 回调。</td></tr>
      <tr><td><strong>状态同步</strong></td><td>share_memory() → SharedBus AGENT_BROADCAST 消息（V2 基础设施复用）</td><td>SharedBus 统一状态广播 + KEPA 广播 + share_memory() 记忆共享 + GCC 事件系统 + TaskSnapshotStore 快照持久化</td></tr>
      <tr><td><strong>可观测性</strong></td><td>快照审计 + 反问记录</td><td>全链路追踪 + 决策日志 + 快照审计 + KEPA 广播 + 反问确认记录 + SchedulingMetrics</td></tr>
      <tr><td><strong>生命周期</strong></td><td>create_team() → supervise_task() → share_memory() → discard()</td><td>create_agents() → execute() → share_memory() → discard()<br/>+ shutdown()（超时清理）</td></tr>
      <tr><td><strong>工具管理</strong></td><td>ToolRegistry 注册，Agent 通过 _llm_json() 自行决定输出。<br/>不做工具注入，Worker 只执行 LLM JSON 响应。</td><td>ToolRegistry 集中注册，WorkAgent.act() 通过 Mind → ToolRegistry 获取工具，所有工具均可调用（不做角色裁剪）。</td></tr>
      <tr><td><strong>执行模式</strong></td><td>process_message() → RAG → _llm_json() → KEPA → 返回字符串。<br/>Workers 通过 asyncio.gather 并行执行。</td><td>think() → act() → reflect() 三阶段循环。<br/>只读步骤并行，写步骤串行。<br/>记录 work_history（上限 100 条）。</td></tr>
      <tr><td><strong>对应实现</strong></td><td><code>core/agent_system.py</code><br/>（LLMAgent + LeaderAgent + V1LeaderPool + KEPA/RAG/反问/ContextMemory）</td><td><code>core/multi_agent_v2/</code><br/>（IntelligentScheduler + OnDemandAgentPool + WorkAgent + SharedBus + GCC + 5 种 CollaborationStrategy）</td></tr>
    </tbody>
  </table>
</div>

<footer>小雷版小龙虾 Agent 架构文档 · 2026</footer>

</div>

<script>
  mermaid.initialize({
    startOnLoad: true,
    theme: 'default',
    themeVariables: {
      fontFamily: '-apple-system, "Microsoft YaHei", sans-serif',
      fontSize: '13px',
    },
    flowchart: {
      useMaxWidth: true,
      htmlLabels: true,
      curve: 'basis',
      padding: 16,
    },
    securityLevel: 'loose',
  });

  // 缩放功能
  function zoomIn(id) {
    const wrap = document.getElementById(id);
    if (!wrap) return;
    const svg = wrap.querySelector('svg');
    if (!svg) return;
    let level = parseFloat(svg.dataset.zoomLevel || '1');
    level = Math.min(level + 0.25, 3);
    applyZoom(wrap, svg, level);
  }

  function zoomOut(id) {
    const wrap = document.getElementById(id);
    if (!wrap) return;
    const svg = wrap.querySelector('svg');
    if (!svg) return;
    let level = parseFloat(svg.dataset.zoomLevel || '1');
    level = Math.max(level - 0.25, 0.25);
    applyZoom(wrap, svg, level);
  }

  function zoomReset(id) {
    const wrap = document.getElementById(id);
    if (!wrap) return;
    const svg = wrap.querySelector('svg');
    if (!svg) return;
    applyZoom(wrap, svg, 1);
  }

  function applyZoom(wrap, svg, level) {
    svg.dataset.zoomLevel = level;
    const pct = Math.round(level * 100);
    svg.style.transform = level === 1 ? '' : `scale(${level})`;
    svg.style.transformOrigin = 'top left';
    wrap.classList.toggle('zoomed', level !== 1);
    const levelEl = document.getElementById('zoom-level-' + wrap.id);
    if (levelEl) levelEl.textContent = pct + '%';
  }
</script>
</body>
</html>
