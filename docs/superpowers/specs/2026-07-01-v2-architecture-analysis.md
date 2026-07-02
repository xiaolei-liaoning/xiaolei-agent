# V2 多 Agent 架构深度分析报告

日期: 2026-07-01
作者: 头脑风暴 → 设计文档

---

## 第一章：架构总览

### 1.1 核心组件关系

```
react_core.py ──→ run_react() 主循环
    │
    ├── MiddlewareChain (middleware.py)
    │   ├── MemoryMiddleware        (memory_middleware.py)  — 记忆读写
    │   ├── TruncationMiddleware    (middlewares.py)        — 历史截断
    │   ├── LoopDetectionMiddleware (middlewares.py)        — 循环检测
    │   ├── ClarificationMiddleware (middlewares.py)        — 澄清拦截
    │   ├── TodoMiddleware          (middlewares.py)        — 任务完整性
    │   ├── PermissionMiddleware    (middlewares.py)        — 权限控制
    │   ├── HookMiddleware          (middlewares.py)        — Before/After Hook
    │   ├── ReActDepthMiddleware    (middlewares.py)        — 深度控制
    │   ├── ReActCoreMiddleware     (react_core.py)         — ★ 核心执行器
    │   ├── ReflectionMiddleware    (middlewares.py)        — 定期反思
    │   └── KEPAMiddleware          (middlewares.py)        — 知识沉淀
    │
    ├── plan_manager.py    — 计划生成/Replan
    ├── tool_executor.py   — 工具执行 + 重试 + 降级
    ├── tool_parser.py     — 工具调用解析
    ├── tool_evaluator.py  — 结果格式化
    ├── file_validator.py  — 文件内容校验
    ├── context_budget.py  — 上下文预算管理(压缩)
    └── output_bounder.py  — 输出截断统计

orchestrator.py ──→ agent() / parallel() / pipeline()
    │
    ├── AgentPool (8 个 WorkAgent 预热)
    ├── SubAgentRegistry (6 种内置类型)
    └── BudgetTracker (全局 Token 追踪)

work_agent.py ──→ 单一 Agent 任务执行
    │
    ├── run_react() — 走完整 ReAct 循环
    ├── Skill 匹配 (base_skills → personality)
    ├── project_analysis (Phase 1+2)
    └── SharedBus 工作记忆读写

js_workflow.py ──→ Node.js 桥接引擎
    │
    ├── IPC 通信 (agent / batch_agents / workflow / phase / log / budget)
    ├── Resume 缓存 (同会话 MD5 缓存)
    └── DAG 图编排 ($dag)

shared_bus.py ──→ 全局单例
    ├── 消息通信 (publish/subscribe — 已废弃)
    ├── 知识存储 (store_knowledge / search_knowledge)
    └── 知识清理 (cleanup_old_knowledge)
```

### 1.2 覆盖文件清单

| # | 文件 | 行数 | 职责 |
|---|------|------|------|
| 1 | `react_core.py` | 1085 | ReAct 主循环 + 提示词模块 + 中间件链构建 |
| 2 | `middleware.py` | 377 | MiddlewareChain 管道 + RunContext 数据类 |
| 3 | `middlewares.py` | 985 | 10 个中间件实现 |
| 4 | `context_budget.py` | 537 | 上下文预算管理 + LLM 压缩 |
| 5 | `output_bounder.py` | 59 | 输出截断统计(委托 tool_result) |
| 6 | `tool_executor.py` | 320 | 工具执行 + 重试 + 降级 |
| 7 | `tool_parser.py` | - | 工具调用解析 |
| 8 | `tool_evaluator.py` | - | 结果格式化 |
| 9 | `tool_result.py` | 176 | 统一输出截断 + ok/err 协议 |
| 10 | `orchestrator.py` | 579 | 多 Agent 编排引擎 |
| 11 | `work_agent.py` | 524 | 统一工作 Agent |
| 12 | `memory_middleware.py` | 165 | V2 记忆中间件 |
| 13 | `shared_bus.py` | 245 | 共享总线 + 知识存储 |
| 14 | `js_workflow.py` | 990 | JS Workflow 引擎 |
| 15 | `workflow/models.py` | 41 | 数据模型 |
| 16 | `workflow/subagent/models.py` | 205 | SubagentProfile 定义 |
| 17 | `workflow/subagent/registry.py` | 147 | SubagentRegistry |

---

## 第二章：限制/阈值/截断全览（按文件遍历）

> 本章列出所有硬编码的限制、阈值、截断值，标注所在文件:行号。

### 2.1 react_core.py

```
48:   _MAX_ROUNDS = 10                              ← 默认最大轮次
214:  if ctx.react_depth >= ctx.max_iterations       ← 深度检查
243:  max_tools=20                                   ← 工具筛选上限
266:  ctx._task_flags 中每个 task_desc[:300]         ← 任务分类截断
285:  _task_desc = (ctx.task_description or "")[:300] ← 分类输入截断
297:  max_tokens=32                                  ← 分类 LLM 调用
435:  max_tokens=32768                               ← 主 LLM 调用
454:  reply[:500]                                    ← 日志截断
456:  _ctx_text[:300]                                ← knowledge_context 记录
476:  consecutive_idle_rounds >= 3                   ← 空转强制退出
486:  len(reply) > 100                               ← 有实质内容判断
688:  count == 1 / count == 2                        ← 文件质量改进轮次
697:  result_text[:200]                              ← 打印截断
645:  result_text[:2000]                             ← 对话历史结果截断
874:  _post_rounds >= 3                              ← 完成后强制指令上限
886:  done_count == 0 && react_depth >= 8            ← 无推进提前结束
```

### 2.2 tool_result.py

```
18-41: TOOL_OUTPUT_LIMITS:                          ← 每工具输出截断阈值
        read_file:    100,000  (从 3000 提升)
        web_search:   4,000
        fetch_url:    4,000
        bash/shell:   5,000
        execute_python: 5,000
        git/task/todo: 2,000
        默认:         3,000
80-88:  _truncate(): head=60%, tail=余量-30, 中间截断
```

### 2.3 middlewares.py

```
38:    ReActDepthMiddleware.MAX_DEPTH = 30           ← 最大深度
320-328: LoopDetectionMiddleware.TOOL_FREQ_LIMITS:   ← 工具频率阈值
           read_file:     warn=20,  hard=999
           execute_shell: warn=6,   hard=12
           execute_python: warn=6,  hard=12
           web_search:    warn=4,   hard=8
           fetch_url:     warn=4,   hard=8
           write_file:    warn=5,   hard=10
           edit_file:     warn=5,   hard=10
367-372: _PROFILE_THRESHOLDS:                        ← 任务画像阈值覆盖
           game:   write_file warn=4,  hard=8
           code:   write_file warn=3,  hard=6
           design: write_file warn=4,  hard=8
           report: write_file warn=3,  hard=5
336:    window_size = 50                             ← 滑动窗口大小
530:    count >= hard_limit                           ← 哈希重复硬上限
540:    count >= warn_threshold=5                     ← 哈希重复警告
567:    _tool_freq[name] >= _warn                     ← 单工具频率警告
627:    _tool_freq[path_key] == 5                     ← 文件写入 5 次警告
633:    _tool_freq[path_key] >= 10                    ← 文件写入 10 次强制停止
646-656: 模式循环检测: len≥8, pattern_len=2~4        ← 工具模式循环检测
713:    _MAX_REMINDERS = 2                            ← TodoMiddleware 提醒上限
758:    keep_recent = 5                               ← TruncationMiddleware 保留轮次
        max_messages = 40
787-793: CompactionMiddleware 默认值:
           max_context_chars=80000
           safety_margin=20000
           protected_recent_turns=3
           min_rounds_before_compact=4
           use_llm_compaction=True
```

### 2.4 context_budget.py

```
88-97:  ContextBudgetManager 默认值:
           max_context_chars = 80000
           safety_margin = 20000
           min_prune_chars = 15000
           protected_recent_turns = 3
           min_rounds_before_compact = 4
           history_token_budget = 6000
           use_llm_compaction = True
312:    max_tokens=1024                              ← LLM 压缩输出上限
378:    _MAX_TOOL_RESULTS = 16                        ← 压缩后 tool_results 上限
```

### 2.5 orchestorator.py

```
22:    _DEFAULT_POOL_SIZE = 8                         ← AgentPool 大小
53:    asyncio.wait_for(pool.get(), timeout=30.0)     ← Acquire 超时
310:   max_retries = 3                                ← Schema 校验重试
```

### 2.6 js_workflow.py

```
34-38:  WorkflowConfig 默认值:
            timeout = 600                            ← JS Workflow 总超时
            max_concurrent_agents = 16               ← IPC 并发上限
            max_agents = 1000
            budget_total = 1,000,000                 ← 100 万 Token 预算
```

### 2.7 work_agent.py

```
128:    max_rounds = max(_mr, 10) if _mr else 10     ← WorkAgent 默认轮次
222:    self.work_history = self.work_history[-100:]  ← 工作历史保留 100 条
```

### 2.8 memory_middleware.py

```
82:     ctx.knowledge_context[-8000:]                 ← 记忆上下文截断 8000 字符
```

### 2.9 tool_executor.py

```
19-30:  TOOL_TIMEOUTS:
            web_search:      45s
            fetch_url:       20s
            execute_python:  45s
            execute_shell:   20s
            write_file:      15s
            read_file:        8s
            edit_file:        8s
            search_files:    10s
            git:             15s
            DEFAULT:         30s
33:     RETRYABLE_TOOLS = {"web_search", "fetch_url", "execute_python", "write_file"}
101:    max_attempts = 2                               ← 默认重试次数
```

### 2.10 各处字符串截断汇总

| 位置 | 截断值 | 用途 |
|------|--------|------|
| react_core.py:139 | `[:200]` | `_trim_desc` head |
| react_core.py:140 | `[:3000]` | `_trim_desc` phase |
| react_core.py:142 | `[:500]` | `_trim_desc` fallback |
| react_core.py:285 | `[:300]` | 任务分类输入 |
| react_core.py:454 | `[:500]` | 日志预览 |
| react_core.py:456 | `[:300]` | knowledge_context 记录 |
| react_core.py:645 | `[:2000]` | 对话历史结果 |
| react_core.py:697 | `[:200]` | 打印 |
| react_core.py:975 | `[:3000]` | 搜索报告兜底数据 |
| middlewares.py:194 | `[:200]` | KEPA 摘要 |
| middlewares.py:200 | `[:200]` | KEPA 共享知识 |
| middlewares.py:600 | `[:200]` | 错误重复检测 |
| context_budget.py:83 | `[-8000:]` | knowledge_context |
| context_budget.py:144 | `[-3000:]` | KEPA knowledge_context |
| context_budget.py:384 | `[-2000:]` | 压缩后 knowledge_context |
| work_agent.py:152 | `[:12000]` | Expert personality |
| work_agent.py:183 | `[:2000]` | Guidance |

---

## 第三章：写死的提示词

> 本节按文件 catalog 所有硬编码的 Prompt 字符串。

### 3.1 react_core.py

| 变量名 | 行号 | 用途 | 大致长度 |
|--------|------|------|---------|
| `_BASE_PROMPT` | 54-65 | 基础行为规则 | 6 行 |
| `_CODE_GEN_PROMPT` | 67-75 | 代码生成工作流 | 8 行 |
| `_GAME_DEV_PROMPT` | 77-85 | 游戏开发质量要求 | 8 行 |
| `_REPORT_PROMPT` | 87-93 | 报告生成工作流 | 6 行 |
| `_PLAN_PROMPT` | 95-97 | 计划执行提示 | 1 行 |
| `_DEBUG_PROMPT` | 99-102 | 错误恢复提示 | 2 行 |
| `_PROJECT_ANALYSIS_PROMPT` | 104-130 | 项目分析协议（长） | 27 行 |
| LLM 任务分类 prompt | 292-299 | 8 分类路由 | 4 行（内联） |
| 空跑重试 forced_instructions | 499-501 | 强制调工具 | 2 行（内联） |
| 质量改进 forced_instructions | 675-685 / 687-694 | 1st/2nd 迭代 | 10 行（内联） |
| 搜索报告自动生成 prompt | 978-987 | 兜底 HTML 报告 | 10 行（内联） |
| 兜底总结 system prompt | 1041-1042 | 最后总结 | 2 行（内联） |
| `_data_fetched` 后 forced_instructions | 612-616 | 数据已获取 → write_file | 4 行（内联） |

### 3.2 context_budget.py

| 变量名 | 行号 | 用途 | 大致长度 |
|--------|------|------|---------|
| `_COMPACTION_SYSTEM_PROMPT` | 25-35 | LLM 摘要压缩 | 11 行 |
| `_set_replay_instructions` | 399-403 | 压缩后重放指令 | 5 行（内联） |

### 3.3 middleware.py

| 位置 | 行号 | 用途 |
|------|------|------|
| 参数校验失败 forced_instructions | 342-346 | 参数错误重试提示 |

### 3.4 work_agent.py

| 位置 | 行号 | 用途 |
|------|------|------|
| `_is_project_analysis` prompt | 257-260 | 判断是否为项目分析任务 |
| Phase 1+2 结果注入 prompt | 487-507 | 项目分析数据 HTML 包装指令 |

### 3.5 orchestrator.py

| 位置 | 行号 | 用途 |
|------|------|------|
| Schema 重试 prompt | 356 | 格式错误修正提示 |

### 3.6 js_workflow.py

| 位置 | 行号 | 用途 |
|------|------|------|
| `_generate_node_bridge()` | 619-931 | 300+ 行 JS 模板字符串（完整的 Node.js 桥接脚本） |
| IPC workflow_context 注入 | 425-428 | `<workflow_context>` 模板 |

---

## 第四章：REACT + 中间件执行流程深度分析

### 4.1 主循环执行顺序 (`react_core.py:858-1083`)

```
run_react() 入口 (811)
  │
  ├── 1. 创建 RunContext
  ├── 2. build_default_chain() / build_configured_chain()
  ├── 3. chain.bind_agent(agent)
  ├── 4. chain.on_start(ctx)          → 工具发现 (ReActCoreMiddleware)
  │
  ├── 5. generate_plan()              → plan_manager 生成计划
  │
  ├── 6. while not interrupted:       ← ReAct 主循环
  │     │
  │     ├── a. 计划完成检查 (post_completion_rounds >= 3 强制结束)
  │     ├── b. 无推进检测 (done_count==0 && depth>=8)
  │     ├── c. 最后轮次警告注入
  │     │
  │     ├── d. context_budget.async_check_and_compact()
  │     │        └── LLM 压缩 / 模板压缩（回退）
  │     │
  │     ├── e. react_depth += 1
  │     │
  │     ├── f. chain.on_think_start(ctx)
  │     │        ├── ReActDepthMiddleware      → 深度上限检查
  │     │        ├── TruncationMiddleware      → 历史截断
  │     │        ├── LoopDetectionMiddleware   (HOOKS: on_plan_check, 此步不触发)
  │     │        ├── ClarificationMiddleware   (HOOKS: on_plan_check, 此步不触发)
  │     │        ├── MemoryMiddleware          → 记忆注入
  │     │        ├── KEPAMiddleware            → 共享知识注入
  │     │        └── ReActCoreMiddleware       → ★ LLM 调用 + 工具调用解析
  │     │
  │     ├── g. chain.on_plan_check(ctx)
  │     │        ├── LoopDetectionMiddleware   → 6 层循环检测
  │     │        └── ClarificationMiddleware   → 澄清请求拦截
  │     │
  │     ├── h. chain.on_think_end(ctx)
  │     │        └── ReActCoreMiddleware       → ★ 执行工具调用
  │     │
  │     ├── i. update_step_status(ctx)         → 更新计划状态
  │     ├── j. replan_failed(ctx)              → 失败步骤重新规划（最多 2 次重试）
  │     │
  │     └── k. chain.on_tool_end(ctx)
  │              ├── ReActDepthMiddleware      → 记录连续失败
  │              ├── ReflectionMiddleware      → 定期反思
  │              ├── KEPAMiddleware            → 知识沉淀
  │              ├── HookMiddleware            → AfterTool/OnError Hook
  │              ├── MemoryMiddleware          → 工具经验记录
  │              └── TodoMiddleware            (HOOKS: on_finish, 此步不触发)
  │
  ├── 7. 搜索报告自动生成兜底 (954-1019)
  ├── 8. 兜底 LLM 总结 (1022-1053)
  ├── 9. 长文本自动保存桌面 (1065-1072)
  │
  └── 10. chain.on_finish(ctx)
              ├── KEPAMiddleware       → 最终知识摘要
              ├── TodoMiddleware       → 任务完整性检查
              └── MemoryMiddleware     → 持久化记忆
```

### 4.2 中间件链初始化顺序

`build_default_chain()` (`react_core.py:726-752`) 中间件注册顺序：

```
(1) MemoryMiddleware        ← 先注入记忆，供后面中间件读取
(2) TruncationMiddleware    ← 截断历史，避免 LLM 调用时溢出
(3) LoopDetectionMiddleware ← 尽早检测循环
(4) ClarificationMiddleware ← 尽早拦截澄清请求
(5) TodoMiddleware          ← 防止过早退出
(6) PermissionMiddleware    ← 工具权限检查
(7) HookMiddleware          ← Before/After Hook
(8) ReActDepthMiddleware    ← 深度控制（紧挨核心）
(9) ReActCoreMiddleware     ← ★ 核心执行器
(10) ReflectionMiddleware   ← 执行后反思
(11) KEPAMiddleware         ← 知识沉淀（最后）
```

### 4.3 生命周期钩子调用关系

```
chain.on_start()      ─→ 所有中间件.on_start()         → 收集工具定义
chain.on_think_start() ─→ 所有中间件.on_think_start()    → 构建消息 + LLM 调用
chain.on_plan_check()  ─→ 所有中间件.on_plan_check()     → 循环检测 + 澄清拦截
chain.on_think_end()   ─→ 所有中间件.on_think_end()      → 执行工具
chain.on_tool_end()    ─→ 所有中间件.on_tool_end()       → 反思 + 知识沉淀
chain.on_finish()      ─→ 所有中间件.on_finish()         → 持久化
```

每个钩子的返回值 `HookResult(jump_to, reason)`：
- `"continue"` — 正常继续
- `"end"` — 终止执行（设置 `ctx.interrupted = True`）
- `"retry"` — 重试当前轮（注入 warning 后 continue）

### 4.4 on_wrap_tool_call 洋葱模式

`MiddlewareChain.on_wrap_tool_call()` (`middleware.py:308-371`) 使用递归链：

```
PermissionMiddleware.on_wrap_tool_call → next()
    └── HookMiddleware.on_wrap_tool_call → next()
        └── 实际工具执行（registry → handler → bound_result）
```

权限检查在洋葱外层（先检查），Hook 在中间层，实际执行在最内层。

### 4.5 错误处理路径

1. **LLM 不可用** → `ctx.interrupted = True`, `last_error = "LLM 不可用"`
2. **LLM 超时** → 60s 超时 → `interrupted = True`
3. **LLM 空转** → 最多 2 次回合内重试 → 连续 3 轮空转强制结束
4. **工具执行失败** → 重试 1 次 → 降级（连续 3 次失败）→ 记录 `_failed_approaches`
5. **参数校验失败** → `_validation_error=True` → 跳过历史记录 → forced_instructions 驱动重试
6. **核心中间件异常** → 以 "Core" 命中的中间件异常 → `interrupted = True`
7. **主循环后兜底**：搜索数据有但无报告 → 自动生成 HTML；有结果无 final_answer → LLM 总结

### 4.6 循环检测 6 层防御 (`LoopDetectionMiddleware`, `middlewares.py:476-656`)

| Layer | 检测方法 | 阈值 | 处置 |
|-------|---------|------|------|
| 0 | 已完成步骤文件重复写入 | pending 不匹配 | retry |
| 1 | 滑动窗口哈希重复 | warn=5 hard=10 | warn / end |
| 2 | 单工具频率 | 按工具配置 | warn / end |
| 3 | Doom Loop（同轮≥3次） | ≥3 | warn |
| 4 | MCP 错误重复 | 连续 2 次相同 | warn |
| 5 | 文件写入路径重复 | 5次warn 10次end | warn / end |
| 6 | 多轮模式循环 | len≥8, pattern≥2 | warn |

---

## 第五章：多 Agent 交互与协作模式

### 5.1 架构概览

V2 的多 Agent 系统由 3 个层次组成：

```
┌──────────────────────────────────────────────┐
│          Orchestrator (orchestrator.py)       │
│  agent() │ parallel() │ pipeline()            │
│  ┌──────────────────────────┐                 │
│  │      AgentPool (8)       │  ← WorkAgent 池 │
│  │  worker_0 ... worker_7   │                 │
│  └──────────────────────────┘                 │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│       WorkAgent (work_agent.py)              │
│  execute() → _execute_fast() → run_react()   │
│  → ReActCoreMiddleware (完整 ReAct 循环)      │
│  → MiddlewareChain (11 个中间件)              │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│       SharedBus (shared_bus.py)              │
│  store_knowledge() │ search_knowledge()       │
│  cleanup_old_knowledge()                      │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│    JS Workflow Bridge (js_workflow.py)        │
│  run() → Node.js 进程 → IPC 通信              │
│  agent / batch_agents / workflow / phase      │
│  ← ClaudeCodeWorkflow 运行时                  │
└──────────────────────────────────────────────┘
```

### 5.2 协作模式 1: Orchestrator Agent Pool

`orchestrator.py:agent()` → `_execute_agent()`:

1. `_agent_pool.acquire(label)` — 从池借 WorkAgent（最多等 30s）
2. 从 `SubagentRegistry.dispatch(subagent_type)` 获取 Profile
3. Profile 中的 `allowed_tools` / `disallowed_tools` 注入到 Task Context
4. `pool_agent.execute(task)` — 异步执行（带超时）
5. **Schema 校验 + 重试**：最多 3 次，循环错误检测
6. 执行完后 `pool_agent.reset()` + `_agent_pool.release()`

**并行执行**：`parallel()` → `asyncio.gather` + `return_exceptions=True`，带整体超时。
**流水线**：`pipeline()` → 顺序执行，前一步输出通过 `{prev_output}` 注入下一步。

### 5.3 协作模式 2: SharedBus 知识共享

`shared_bus.py` 是全局单例，核心方法：

```
store_knowledge(key, data, tags, source, summary)     → 存储知识
search_knowledge(tag)                                  → 按标签检索
list_knowledge()                                       → 列出所有
cleanup_old_knowledge(max_age=1800)                    → 30 分钟清理
```

**写入路径**：
- `KEPAMiddleware.on_tool_end()` → 工具成功执行后写入（key=`kepa:{name}:{iteration}`）
- `KEPAMiddleware.on_finish()` → 任务完成时写入最终摘要（key=`kepa:final:{source}`）
- `WorkAgent._execute_fast()` → 分析任务完成后写入（key=`analysis:{agent_id}`）

**读取路径**：
- `KEPAMiddleware.on_think_start()` → 每 N 轮（3 轮）按标签搜索 → 注入 `knowledge_context`
- `WorkAgent._execute_fast()` → 执行前关键词检索 → 注入 task_description

### 5.4 协作模式 3: JS Workflow Bridge

`js_workflow.py:ClaudeCodeWorkflow.run()`:

1. 准备 `workflow.js` + `bridge.mjs` 到临时目录
2. 启动 Node.js 子进程（`create_subprocess_exec`）
3. IPC 通信（`__IPC__:` 协议）：
   - `agent` → 调用 `orchestrator.agent()`（支持 Resume 缓存）
   - `batch_agents` → 调用 `orchestrator.parallel()`
   - `workflow` → 递归 `self.run()`（状态隔离）
   - `phase` / `log` / `budget_report` → 记录执行数据
4. 结果写入 `result.json`

**Resume 缓存**：同会话内 MD5(prompt+opts) 缓存 agent 调用结果，支持 `clear_cache()`。
**并发控制**：`_ipc_semaphore` 限制最多 `max_concurrent_agents`（16）个同时运行。

### 5.5 协作模式 4: Subagent 分类与工具约束

`subagent/registry.py` 内置 6 种类型：

| 类型 | 工具白名单 | 用途 |
|------|-----------|------|
| Explore | read_file, search_files, web_search, fetch_url | 只读搜索 |
| Plan | read_file, search_files, web_search, fetch_url | 规划 |
| Coder | 全工具（除 git） | 编码 |
| Analyst | read/search/web/execute_python/write_file | 数据分析 |
| Operator | shell/git/文件读写 | 运维 |
| general-purpose | 无限制 | 通用 |

### 5.6 JS 模板约定遵从性分析

| JS 模板特性 | V2 实现状态 | 文件 |
|-------------|------------|------|
| `agent()` | ✅ 支持（含 `_workflowContext` 注入） | `js_workflow.py:369-469` |
| `parallel()` | ✅ 支持（`Promise.allSettled`） | `js_workflow.py:780-787` |
| `batchAgents()` | ✅ 支持（一次 IPC 批量） | `js_workflow.py:773-777` |
| `pipeline()` | ✅ 支持 | `js_workflow.py:839-859` |
| `$dag()` | ✅ 支持（拓扑排序 + 依赖图） | `js_workflow.py:790-836` |
| `workflow()` | ✅ 支持（递归嵌套，状态隔离） | `js_workflow.py:862-871` |
| `phase()` | ✅ | `js_workflow.py:719-724` |
| `log()` | ✅ | `js_workflow.py:727-731` |
| `budget` | ✅（含多模型追踪） | `js_workflow.py:697-712` |
| Schema 校验 | ✅（`opts.schema` → JSON parse + validate） | `js_workflow.py:754-762` |
| Resume 缓存 | ✅（MD5 键，同会话） | `js_workflow.py:64-77` |
| 多模型路由 | ✅（`model` 字段 + `_model_records`） | `js_workflow.py:371` |
| `fullResult` | ✅ | `js_workflow.py:766-769` |
| `stripSchema` | ✅ | `js_workflow.py:434` |

**已知问题**：
1. `parallel` 假并行已修复（`middlewares.py V2-C7` — `create_task` + `semaphore`，而不是阻塞 await）
2. `workflow` 嵌套状态隔离已修复（`middlewares.py V2-M11` — 保存/恢复父子状态）
3. `on_wrap_model_call` 在 `middleware.py:298-299` 标注了 TODO：当前未被调用，LLM 调用直接从 `react_core.py` 调用 `router.chat`，跳过了洋葱链

### 5.7 Agent 间通信模式总结

| 模式 | 手段 | 适用场景 |
|------|------|---------|
| 知识共享 | SharedBus `store_knowledge` / `search_knowledge` | 异步数据传递 |
| 任务编排 | Orchestrator `agent()` + `parallel()` + `pipeline()` | 同步任务调度 |
| IPC 桥接 | JS Workflow `__IPC__` 协议 | JS ↔ Python 跨语言通信 |
| 嵌套编排 | `workflow()` 递归 | 子工作流 |
| 依赖图 | `$dag()` 拓扑排序 | 复杂 DAG 编排 |

---

## 第六章：跟踪清单

> 本节列出所有值得跟进的问题点，标注严重程度和建议修改。

### P0 — 必须修复

| # | 问题 | 位置 | 描述 | 建议 |
|---|------|------|------|------|
| 1 | `_MAX_ROUNDS=10` 和 `RunContext.max_iterations=10` 双重默认值 | react_core.py:48, middleware.py:38 | `run_react()` 用 `_MAX_ROUNDS`，`RunContext` 也有 `max_iterations=10`，`build_configured_chain` 另有 `depth_max=30`，三者关系不清晰 | 统一为单一来源，消除冗余 |
| 2 | 硬编码 JS 桥接脚本 300+ 行 | js_workflow.py:619-931 | `_generate_node_bridge()` 返回的 JS 字符串包含完整的 IPC/agent/dag/pipeline 实现，不可维护 | 提取到独立 `.mjs` 文件，运行时读取 |
| 3 | `_PROJECT_ANALYSIS_PROMPT` 与 LLM 任务分类重叠 | react_core.py:104-130 + 283-314 | 任务分类先 LLM 判断 8 个 flag，然后 `_task_flags.get("project_analysis")` 再插另一个 prompt | 合并为单一提示体系 |
| 4 | `on_wrap_model_call` 未接入 | middleware.py:298-299 | LLM 调用直接从 `react_core.py:432` 调用 `router.chat()`，跳过 `MiddlewareChain.on_wrap_model_call` | 将 LLM 调用移到链中，或删除死代码 |

### P1 — 建议改进

| # | 问题 | 位置 | 描述 | 建议 |
|---|------|------|------|------|
| 5 | `_trim_desc` 截断逻辑与后续 LLM 兜底总结不匹配 | react_core.py:133-142 + 1038-1053 | 兜底总结传 `_trim_desc(task_description)` 可能丢失关键上下文 | 改用完整的 task_description，或保留更多 Phase 1 数据 |
| 6 | Tool output limits 分散两处 | tool_result.py:18-41 + react_core.py:645 | `bound_result()` 截断一次，`result_text[:2000]` 再截断一次，双重截断 | 统一为 bound_result 单一截断点 |
| 7 | AgentPool 大小固定 8 | orchestrator.py:22 | 不支持动态调整 | 改为可配置（环境变量或参数） |
| 8 | WorkflowConfig timeout=600s 硬编码 | js_workflow.py:34-38 | 不支持从 JS meta 覆盖 | 支持从 `export const meta` 读取 timeout |
| 9 | `_conversation_history` 只在某些路径写入 | react_core.py:550,642 | assistant 消息和 tool 结果写入但不统一（`_validation_error` 跳过逻辑） | 统一写入策略，所有路径覆盖 |

### P2 — 低优先级

| # | 问题 | 位置 | 描述 |
|---|------|------|------|
| 10 | SharedBus publish/subscribe 已废弃但代码保留 | shared_bus.py:71-133 | 无调用者，保留 ~60 行 dead code |
| 11 | BounderStats 双重统计 | output_bounder.py + tool_result.py | `bound_result` 内部记录日志，`BounderStats` 另有一套统计 |
| 12 | `_step_retries` 上限 2 硬编码 | react_core.py:933 | `if retries < 2` 硬编码 |
| 13 | memory_middleware.py `knowledge_context` 两处不同截断值 | memory_middleware.py:82（8000） vs middlewares.py:144（3000） | 不一致 |
| 14 | `_filter_scan_tools` 函数未被调用 | react_core.py:145-149 | 定义了但未在任何路径中调用，死代码 |

---

## 附录 A：约定与术语

- **ReAct** = Reason + Act，LLM 自主决定调工具还是直接回答
- **MiddlewareChain** = 按序执行中间件的管道模式
- **KEPA** = 知识沉淀（Knowledge Extraction, Processing, Accumulation）
- **DAG** = Directed Acyclic Graph，有向无环图编排
- **IPC** = Inter-Process Communication，进程间通信
- **SharedBus** = 全局共享总线，Agent 间知识交换中心
- **AgentPool** = WorkAgent 复用池，避免频繁创建销毁

## 附录 B：数据流核心链路

```
用户请求
    │
    ▼
orchestrator.agent("分析项目X")
    │
    ▼
WorkAgent.execute()
    │
    ├── Skill 匹配 → personality
    ├── SharedBus 工作记忆检索
    │
    ▼
run_react(task_description)
    │
    ▼
generate_plan() → 计划列表
    │
    ▼
[ReAct Loop]
    │
    ├─ LLM 思考 → 生成回复
    ├─ parse_tool_calls() → 解析工具调用
    ├─ execute_tool_calls_parallel() → 执行
    │   ├─ PermissionMiddleware 权限检查
    │   ├─ HookMiddleware BeforeTool
    │   ├─ Registry → Handler → bound_result
    │   └─ HookMiddleware AfterTool
    └─ 格式化结果 → 下一轮
    │
    ▼
[兜底] 搜索报告自动生成 / LLM 总结
    │
    ▼
chain.on_finish → 记忆持久化
    │
    ▼
返回 AgentResult → 返回 orchestrator
```
