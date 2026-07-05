<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 180'%3E%3Cdefs%3E%3ClinearGradient id='bg' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0%25' stop-color='%230F172A'/%3E%3Cstop offset='100%25' stop-color='%231E1B4B'/%3E%3C/linearGradient%3E%3ClinearGradient id='accent' x1='0' y1='0' x2='1' y2='0'%3E%3Cstop offset='0%25' stop-color='%238B5CF6'/%3E%3Cstop offset='100%25' stop-color='%2310B981'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='800' height='180' rx='20' fill='url(%23bg)'/%3E%3Ctext x='400' y='60' text-anchor='middle' fill='white' font-size='28' font-weight='800' font-family='system-ui'%3E小雷版 AI Agent%3C/text%3E%3Ctext x='400' y='90' text-anchor='middle' fill='%2394A3B8' font-size='14' font-family='system-ui'%3EReAct + 中间件管线 · 子代理即工具 · JS 编排%3C/text%3E%3Crect x='180' y='110' width='440' height='40' rx='20' fill='url(%23accent)' opacity='0.9'/%3E%3Ctext x='400' y='136' text-anchor='middle' fill='white' font-size='15' font-weight='700' font-family='system-ui'%3E35+ 工具 · 804 项测试 · Unified Agent 引擎%3C/text%3E%3C/svg%3E">
  <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 180'%3E%3Cdefs%3E%3ClinearGradient id='bg' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0%25' stop-color='%23F8FAFC'/%3E%3Cstop offset='100%25' stop-color='%23EDE9FE'/%3E%3C/linearGradient%3E%3ClinearGradient id='accent' x1='0' y1='0' x2='1' y2='0'%3E%3Cstop offset='0%25' stop-color='%238B5CF6'/%3E%3Cstop offset='100%25' stop-color='%2310B981'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='800' height='180' rx='20' fill='url(%23bg)' stroke='%23E2E8F0' stroke-width='1'/%3E%3Ctext x='400' y='60' text-anchor='middle' fill='%231E293B' font-size='28' font-weight='800' font-family='system-ui'%3E小雷版 AI Agent%3C/text%3E%3Ctext x='400' y='90' text-anchor='middle' fill='%2364748B' font-size='14' font-family='system-ui'%3EReAct + 中间件管线 · 子代理即工具 · JS 编排%3C/text%3E%3Crect x='180' y='110' width='440' height='40' rx='20' fill='url(%23accent)' opacity='0.9'/%3E%3Ctext x='400' y='136' text-anchor='middle' fill='white' font-size='15' font-weight='700' font-family='system-ui'%3E35+ 工具 · 804 项测试 · Unified Agent 引擎%3C/text%3E%3C/svg%3E">
</picture>

<br>

<img alt="Python" src="https://img.shields.io/badge/Python_3.13-3776AB?style=flat-square&logo=python&logoColor=white">
<img alt="OpenRouter" src="https://img.shields.io/badge/OpenRouter-FF6B6B?style=flat-square">
<img alt="DeepSeek" src="https://img.shields.io/badge/DeepSeek-FF6B6B?style=flat-square">
<img alt="35+ Tools" src="https://img.shields.io/badge/35%2B%20Tools-845EF7?style=flat-square">
<img alt="ChromaDB" src="https://img.shields.io/badge/ChromaDB-FF6B35?style=flat-square">
<img alt="77 Tests" src="https://img.shields.io/badge/77%20Tests%20Passing-10B981?style=flat-square">

</div>

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env 填入你的 API Key

# CLI — 启动 REPL
python cli.py

# 或直接执行
python cli.py "分析这个项目"
python cli.py /run "搜索百度热搜"
python cli.py /automate open_app --app Safari
```

---

## 架构总览

小雷版 AI Agent 的核心执行单元是 **Unified Agent** —— 一个基于 ReAct 循环 + 中间件管线的执行引擎。所有能力（文件操作、搜索、代码执行、甚至子代理）都通过 **ToolRegistry** 暴露为工具。

```
                    ┌──────────────────┐
                    │    CLI/REPL      │
                    │  EnhancedCLI     │
                    └────────┬─────────┘
                             │ task_description
                             ▼
                    ┌──────────────────┐
                    │  MiddlewareChain │   12 层中间件，5 个 Hook 点
                    │  (on_start →     │   on_llm_invoke → on_plan_check
                    │   on_tool_invoke │   → on_tool_end → on_finish
                    │   → on_wrap_*)   │
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │  PlanManager     │   两步法计划生成 + 进度追踪
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │  ToolRegistry    │   12 内置 + 25+ MCP + task/orchestrate
                    │  (SERVER_BUILTIN │   所有能力都是工具
                    │   + SERVER_MCP)  │
                    └──────────────────┘
```

---

## CLI 指令系统

所有命令以 `/` 开头，在 REPL 或 `python cli.py` 直接传入。

### 常用指令

| 命令 | 用途 | 示例 |
|------|------|------|
| `/run` | 执行智能工作流 | `/run "爬取微博热搜并分析"` |
| `/smart` | 多 Agent 协作（自动拆分维度并行） | `/smart "分析项目结构并生成报告"` |
| `/orchestrate` | 多 Agent 编排（/smart 别名） | `/orchestrate "分析项目结构"` |
| `/agents` | 多 Agent 协作（/orchestrate 别名） | `/agents "写报告在桌面"` |
| `/task` | 用子代理执行任务（general 角色） | `/task "分析项目结构"` |
| `/explore` | 用 explore 子代理探索代码 | `/explore "分析src目录"` |
| `/analyze` | 用 analyze 子代理深度分析 | `/analyze "代码库审查"` |
| `/build` | 用 build 子代理构建开发 | `/build "创建HTML游戏"` |
| `/chat` | 进入聊天模式 | `/chat` 或 `/chat deep` |
| `/automate` | GUI 自动化 | `/automate open_app --app Safari` |
| `/scrape` | 数据爬取 | `/scrape 微博 --action 热搜top10` |
| `/wechat` | 微信消息 (弃用) | `/wechat send --friend 张三 --message 你好` |
| `/mcp` | MCP 工具管理 | `/mcp list, /mcp connect` |
| `/review` | 代码审查 | `/review code main.py` |
| `/workflows` | 工作流进度 | `/workflows list` |
| `/tools` | 查看所有可用工具 | `/tools` |
| `/debug` | 切换调试模式 | `/debug` |
| `/think` | 切换思考模式 | `/think` |
| `/game` | 小游戏 | `/game guess` |
| `/fun` | 趣味工具 | `/fun joke` |
| `/reset` | 重置会话 | `/reset` 或 `/reset all` |
| `/status` | 系统状态 | `/status` |

### 两种运行方式

```bash
# REPL 模式 — 交互式
python cli.py
> /run "分析这个项目"

# 直传模式 — 一次性
python cli.py /run "搜索百度热搜"
python cli.py /automate open_app --app Safari
python cli.py /smart "分析项目结构"
```

### 子代理快捷指令

`/task`、`/explore`、`/analyze`、`/build` 对应四种子代理角色，内部调用 `task` 工具，走同一套 ReActCore + MiddlewareChain，只是角色 prompt 不同：

| 指令 | 角色 | 适用场景 |
|------|------|---------|
| `/task` | general | 通用任务执行 |
| `/explore` | explore | 代码探索、文件分析 |
| `/analyze` | analyze | 深度分析、报告生成 |
| `/build` | build | 代码生成、项目构建 |

---

## ReAct 循环 — 核心执行引擎

### 一回合流程

```
1. LLM Invoke — 系统提示 + 对话历史 + 工具列表 → LLM 回复
   ├─ 正常: 有 tool_calls → 进入 parse
   └─ 空跑: 无 tool_calls →
      ├─ 计划已完成 (all done) → final_answer, exit
      ├─ 空转 ≥6 轮 → final_answer + interrupted, exit
      └─ <6 轮 → inject forced_instructions + rebuild messages + retry (≤2次)

2. on_plan_check — LLM 回复解析后，工具执行前
   └─ ReActCoreMiddleware: 检查计划步骤是否应自动推进

3. Tools Execute — 通过 MiddlewareChain.on_wrap_tool_call
   ├─ PermissionMiddleware (洋葱最外层): 权限检查
   ├─ ToolCache: 缓存命中直接返回
   ├─ validate_arguments: 参数合法性校验
   └─ handler: 实际执行 + bound_result 统一截断

4. on_tool_end — 工具结果处理
   ├─ update_step_status: 计划进度自动推进（工具名匹配→done）
   ├─ 步骤失败 → mark failed + retry counter
   └─ HookMiddleware: KEPA 重试决策 → jump_to="retry"

5. 回到步骤 1，直到满足退出条件
```

### FinalAnswer 5 层兜底（post-loop）

```
1. 主路径:   计划完成 或 空转 ≥6 轮 → 用最后一次回复 → final_answer
2. 搜索报告: 有搜索数据但无 write_file → LLM 生成 HTML 报告 → 写入桌面
3. 纯文本:   无 tool_results → 从 _pending_reply 提取 (>20 chars)
4. LLM 总结: 有 tool_results → LLM 总结 (max_tokens=32768, 子代理结果优先, 取 8 条)
5. 原始结果: 取最后成功工具结果的纯文本
```

### 保护机制

| 机制 | 触发条件 | 行为 |
|------|---------|------|
| 空转退出 | consecutive_idle_rounds ≥ 6 | interrupted + final_answer |
| 回合内重试 | 空跑 <6 轮 | inject forced_instructions, rebuild messages, retry LLM |
| LLM 超时 | 60s 无响应 | interrupted |
| 重试上限 | 同一 LLM 回复最多 2 次空跑 | 用最后一次回复兜底 |
| 最终轮次 | react_depth > max_iterations | forced_instructions 标记最终轮 |

---

## 中间件管线 — 12 层

所有中间件按注册顺序依次执行。每个 HookResult 可控制流程：`jump_to: "continue" | "end" | "retry"`。

### 注册顺序

```
build_default_chain():

 ① ReActCoreMiddleware        on_plan_check     核心循环调度、计划推进
 ② TodoMiddleware             on_start          防止过早退出
  ③ MemoryMiddleware           on_llm_invoke     记忆注入 → knowledge_context
 ④ CompactionMiddleware       on_tool_end       LLM 摘要压缩 tool_results
 ⑤ TruncationMiddleware       on_tool_end       兜底截断（保留最近 5 轮）
 ⑥ LoopDetectionMiddleware    on_llm_invoke     哈希+频率循环检测
 ⑦ ClarificationMiddleware    on_llm_invoke     拦截 LLM 反问→等待用户确认
 ⑧ ReasoningMiddleware        on_llm_invoke     推理优化
 ⑨ PermissionMiddleware       on_wrap_tool_call 三级权限+Shell 安全（洋葱模式）
 ⑩ HookMiddleware             on_tool_end       KEPA 重试决策→jump_to="retry"
 ⑪ ReActDepthMiddleware       on_llm_invoke+    深度控制 (max 30) + 连续失败检测
                               on_tool_end
 ⑫ KEPAMiddleware             on_llm_invoke+    知识沉淀+跨 Agent 共享 SharedBus
                               on_tool_end
 ⑬ ReflectionMiddleware       on_tool_end       每 3 轮反思执行质量
```

### 执行顺序（一回合）

```
发起 LLM 调用:
  KEPAMiddleware.on_llm_invoke      — 注入 SharedBus 共享知识
  ReActDepthMiddleware.on_llm_invoke — 深度 ≥30 → interrupted
  LoopDetectionMiddleware            — 同内容重复 → 告警
  ClarificationMiddleware            — 检测反问 → 中断等待用户
  MemoryMiddleware                   — 记忆注入

工具执行:
  PermissionMiddleware.on_wrap_tool_call (洋葱最外层)
    └─ ToolCache → validate_arguments → handler → bound_result

工具结束:
  HookMiddleware.on_tool_end          — 工具失败 → jump_to="retry"
  ReActDepthMiddleware.on_tool_end    — 更新失败计数
  CompactionMiddleware                — LLM 压缩
  TruncationMiddleware                — 兜底截断
  ReflectionMiddleware                — 每 3 轮反思
  KEPAMiddleware.on_tool_end          — 提取知识 → SharedBus
```

---

## 计划系统 — PlanManager

### 两步生成

```
generate_plan(ctx):
  ① 理解 (10s timeout)
     prompt: "分析任务并输出自然语言拆解"
     注入: {role_description} ←  personality_prompt 前 3 行
     注入: {available_tools} ← 动态工具列表
   
  ② 结构化 (15s timeout)
     prompt: plan_generation.txt
     格式: "步骤|描述|工具名" (支持 "步骤|" 和 "\d+|" 两种格式)
     注入: {role_description}
     注意: 使用 .replace() 而非 .format()，防止 MCP 工具描述中的 {} 导致静默崩溃
     降级: 首次失败 → 极简中文 prompt 重试
   
  ③ 解析 _parse_plan_steps(text)
     正则匹配 → 映射到实际 ToolDefinition
     失败 → logger.warning + 可见终端输出 "◇ No plan generated"
```

### 进度追踪

```
update_step_status(ctx) — 每次 on_tool_end 自动调用:

  1. 获取当前 step = ctx.plan[done_count] (第一个 non-done)
  
  2. 自动推进 (工具成功匹配 → done):
     ├─ 搜索等价:   {web_search, fetch_url, fetch_json, hot_search} 互换
     ├─ 子代理等价: {task, orchestrate} 互换
     ├─ 探索等价:   {codegraph_explore, codegraph_files, search_files, execute_shell, read_file} 互换
     └─ 精确匹配:   step.tool_names & succeeded_keys 有交集
     
  3. 无 tool_names 的步骤:
     └─ total_success_count >= done_count + 1 → done
  
  4. 卡死检测 (react_depth ≥ 6):
     └─ 从未完成过任何 step 但有实质结果 → force-mark done
  
  5. read_file 循环破解 (react_depth ≥ 2):
     └─ 连续 3 次 read_file + 任务暗示编辑 → 禁止 read_file
  
  6. 工具失败:
     └─ mark current_step failed + ctx._step_retries[step.index] += 1
```

### 重规划

触发点：`react_core.py:1041` — 主循环每轮末尾扫描 `failed_steps`，对重试次数 `<2` 的步骤调用 `replan_failed`。

```
replan_failed(ctx):                                ← plan_manager.py:467
  ① 收集已完成步骤 (done) + 失败/待定步骤 (failed/pending)
  
  ② 构建 retry_prompt:
     - 已完成: "第1步: xxx, 第2步: yyy"
     - 失败:   "第3步: zzz"
     - 错误上下文 (last_error + 最后一次工具 error)
     - 角色 hint (personality_prompt 前 2 行)
  
  ③ 调用 generate_plan(task_description, ctx, retry_context=retry_prompt)
     └─ 空计划 → return False（重规划失败）
  
  ④ 保留 done steps，用新步骤替换 failed/pending（重新编号）
     kept = [s for s in ctx.plan if s.status == "done"]
     for i, s in enumerate(new_steps):
         s.index = offset + i + 1
         s.status = "pending"
     ctx.plan = kept + new_steps
  
  ⑤ ctx.plan_generation += 1
  ⑥ ctx._step_tool_snapshots.clear()   防止新步骤读到旧快照
  ⑦ return True
```

关键设计：保留已完成步骤不动，只重规划失败/待定部分，进度不丢失。最多重规划 2 次。

---

## 工具系统 — ToolRegistry

**所有能力都是工具。** 内置工具和 MCP 工具统一注册在全局单例 `ToolRegistry` 中。

### 注册模型

```
ToolRegistry (全局单例)
├── SERVER_BUILTIN ("__builtin__") — 12 个内置工具
│   ├─ read_file / write_file / edit_file      文件操作
│   ├─ execute_python / execute_shell           沙箱执行
│   ├─ web_search / fetch_url                   网络
│   ├─ search_files / git / write_todos         辅助
│   ├─ task — 子代理（单 Agent）                  ← 不是独立层！
│   └─ orchestrate — 子代理（DAG 编排）           ← 不是独立层！
│
└── SERVER_MCP (动态发现)
    ├─ CodeGraph (explore/files/callers/callees/impact)
    ├─ Playwright (浏览器自动化)
    ├─ DeepWiki / Context7 (代码知识)
    ├─ MemSearch / EverMem (跨会话记忆)
    └─ ... 25+ MCP 工具
```

### 子代理不是独立层

```
LLM 决定调用 "task" 工具
  → ToolRegistry.get_handler("task") 
    → spawn.task(prompt, opts)
      → run_unified(prompt, profile="explore|build|analyze|general")
        → 同一套 ReActCore + MiddlewareChain
          → 只是角色 prompt 不同 + _is_subagent=True
```

子代理是 **ToolRegistry 里注册的一个工具的产物**，不是架构分层。主 Agent 调用 `task` 就像调用 `read_file` 一样——这个工具的 handler 恰好是启动一个新 Agent 进程。

### MCP 自动发现

```
get_all_tools() 触发 MCP 连接 (一次性):

  1. _discover_mcp_configs()
     ├─ mcp_client.list_servers()       — 已注册的 MCP 服务器
     ├─ mcp/*_mcp_server.py             — 本地脚本自动发现
     └─ .mcp.json                       — 项目级 MCP 配置
     
  2. _connect_mcp_servers_parallel()
     ├─ asyncio.gather(每个 server 的 _list_mcp_tools)
     ├─ 单 server 超时 5s, 总超时 12s
     ├─ 去重: 同名工具自动加 {server}_ 前缀
     └─ handler 闭包: 代理到 mcp_client.call_tool(srv, tname, args)
```

### 工具执行流程 (on_wrap_tool_call)

```
1. PermissionMiddleware.check(tool_name, arguments)
   ├─ allowed  + need_ask  → 返回确认消息，等待用户允许/拒绝
   ├─ allowed  + !need_ask → 放行
   └─ !allowed             → 硬拒绝
   
2. execute_shell → ShellGuard.scan(command)
   ├─ High risk (rm -rf /, dd, mkfs)       → 硬拒绝 + 风险描述
   └─ Medium risk (sudo, chmod, curl|bash) → 警告 + 继续

3. ToolCache.get(name, args) → 命中? 返回缓存

4. validate_arguments(name, args) → 参数合法性
   └─ 失败 → forced_instructions + _validation_error=True → LLM 下轮修正

5. handler(args) → result → bound_result 统一截断

6. ToolCache.set(name, args, response)
```

---

## 多 Agent 协作

### 三种协作路径

```
单 Agent 内部 → task/orchestrate 工具
  └─ 主 Agent 的 LLM 判定需要子代理时，在工具列表中选 "task" 或 "orchestrate"
  └─ 子代理启动后跑同一套 ReActCore，只是角色 prompt 不同

CLI 快捷指令 → /smart /orchestrate /agents
  └─ 自动将任务拆解为多个维度（搜索/分析/生成/采集/代码/翻译），最多 5 个
  └─ asyncio.gather 并行执行各维度 → 结果汇总
  └─ 降级路径: orchestrator 不可用时回退到分步执行 (handle_task_with_steps)

JS Workflow → bridge.mjs
  └─ Node.js 脚本通过 IPC 调用 Python Agent
  └─ 见「JS 编排引擎」章节
```

### 跨 Agent 通信

**SharedBus（KEPA 闭环）：**
```
KEPAMiddleware 在每轮 on_tool_end 从工具结果提取知识：
  → 存入 SharedBus（键值存储，按 tag 分类: search/code/analysis/file/kepa）
  → 下轮 on_llm_invoke 查询 SharedBus 获取相关 tag 的新知识
  → 注入到 knowledge_context 供 LLM 参考

特点: 主 Agent 和子 Agent 共享同一个 SharedBus 实例
      知识带 source 标签 + summary，避免重复注入
```

**Parent Context 注入：**
```
子代理启动时，父 Agent 通过 spawn.py 注入:
  - task_description（原始任务）
  - personality_prompt（角色定义，前 3 行注入计划 prompt）
  - work_rules（所有子代理共享的工作规则）
  - parent_context（父级执行上下文摘要）
  - _is_subagent=True（标记为子代理，影响某些中间件行为: 
    如 MemoryMiddleware 跳过记忆写入）
```

**Workflow Context（JS 编排）：**
```
JS bridge 自动为每个 agent() 调用注入：
  - globalTask — 工作流全局任务描述
  - currentPhase — 当前阶段名称（由 phase() 设置）
  - previousPhaseResults — 上一阶段的结果
  - agentIndex — Agent 序号（用于去重和追踪）

这些上下文注入到 prompt 开头的 <workflow_context> 块中。
```

### 子代理共享资源

| 资源 | 共享方式 | 用途 |
|------|---------|------|
| ToolRegistry | 全局单例 | 所有 Agent（主/子/MCP）共享同一组工具 |
| SharedBus | 全局单例 | 跨 Agent 知识沉淀和检索 |
| LLMRouter | 全局单例 | 统一多模型路由（OpenAI/Anthropic/DeepSeek/OpenRouter） |
| AgentPool | 8 预热 WorkAgent | acquire/release 模式，即用即还 |
| Session 存储 | SQLite | 对话日志和 artifact 持久化 |

---

## Prompt 架构 — PromptBuilder

**34 个 `.txt` 文件替代 Python 硬编码字符串。** 所有系统提示、工具描述、子代理角色都从文件加载。

```
prompts/
├── system/                系统级提示 (9)
│   ├─ core.txt            核心系统提示（角色定义+行为规则）
│   ├─ plan_generation.txt 计划生成指令
│   ├─ code_gen.txt        代码生成任务
│   └─ ...
│
├── tools/                 工具描述 (14)
│   ├─ task.txt            子代理 task 工具描述
│   ├─ orchestrate.txt     子代理 orchestrate 工具描述
│   └─ ...每个工具一个 .txt
│
├── agents/                子代理角色 (5)
│   ├─ explore.txt         探索型（代码分析）
│   ├─ build.txt           构建型（代码生成）
│   ├─ analyze.txt         分析型（数据分析/报告）
│   ├─ general.txt         通用型
│   └─ work_rules.txt      所有子代理共享的工作规则
│
└── blocks/                可复用块 (5)
    ├─ architecture.txt    系统架构说明
    ├─ parent_context.txt  父上下文注入
    └─ ...
```

### PromptBuilder API

```
get_builder() → 全局单例

assemble_system(["core", "code_gen"])  — 拼接 system/core.txt + code_gen.txt
get_tool_desc("task")                  — 加载 prompts/tools/task.txt
get_agent_prompt("explore")            — 加载 explore.txt + work_rules.txt
get_block("output_format", ...vars)    — 加载 + .format(**vars)
```

### @requires 依赖系统

```
文件首行:    @requires: system/core, blocks/output_format

加载流程:
  ① 扫描 @requires: → [system/core, blocks/output_format]
  ② 为每个 dep 生成路径 + "{{dep_path}}" 占位符
  ③ 递归加载依赖内容
  ④ 替换占位符 → 缓存到 _cache
  ⑤ 循环依赖检测: 访问栈追踪 → raise CircularDependencyError
```

---

## 记忆系统

### 短期（会话内）

```
层            | 位置                      | 生命周期
──────────────┼──────────────────────────┼──────────────
tool_results  | RunContext.tool_results   | 当前 ReAct 轮次
conversation  | RunContext._conversation  | 整个会话
_history      | _history                  |
forced_       | RunContext.forced_        | 当前轮次
instructions  | _instructions             |
knowledge_    | RunContext.knowledge_     | 每轮增量注入
context       | context                   |
```

### 压缩管线（8 层 L0–L4）

```
ContextCompactor.compact() — 消息级压缩

  L0  ToolResultBudget
      单条消息 >100K chars → 写到磁盘文件 + [Tool result saved to disk] 引用

  L1a API-Level Context Mgmt
      清除旧 tool_use 块的 thinking 字段

  L1b CollapseReadSearch
      UI 折叠追踪（Python 后端 no-op，消息透传）

  L1c Time-Based MC
      gap >60 分钟无活动 → 只保留最近 5 条可清除的工具结果

  L2  CachedMicrocompact
      生成缓存断点 metadata（不修改消息体）

  L2b SnipCompact
      截断旧工具结果: 前一半 + 后四分之一保留，中间 "...[snip]..."

  L3  LLM Compaction
      调用 LLM 生成 9-section 结构化摘要
      9 sections: Goal / Search Results / Code Analysis / Data Files / Decisions /
                  Next Steps / Issues / Summary / Config
      PTL 重试循环: 不满足长度/格式 → 最多重试 3 次

  L4  Post-Compact Rebuild
      重建消息列表 + 注入附件: Files / Skills / Plans / Agents / MCP / Tools / Compact Summary

  Circuit Breaker: 连续 3 次失败 → 跳过压缩
  SessionMemoryCompact: L3+L4 失败时的启发式回退（无 LLM）
```

### V2 补充（ContextBudgetManager）

```
在消息级压缩后，额外对 tool_results 做 entry-level 压缩:
  1. 保护最近 N 轮的 tool_results 不动
  2. 对旧 tool_results 调用 LLM 生成摘要 (Goal / Progress / Key Findings / Next Steps)
  3. 重排为 [summary, tail, new]
  4. 注入 forced_instructions 重放指令
  5. SQLite 持久化对话记录
```

### 长期（跨会话）

```
VectorDB   ChromaDB + sentence-transformers     语义搜索/RAG
MemSearch  MCP 插件                              跨会话记忆搜索
EverMem    MCP 插件                              永久记忆存储
Session    SQLite + session_manager              对话日志 + artifact 归档
```

---

## JS 编排引擎 — GS Workflow

Node.js ↔ Python IPC 桥接，JS 脚本通过 `bridge.mjs` 调用 Python Agent。

### IPC 协议

```
JS → Python: stdout 写入 __IPC__:{"id":1,"type":"agent","data":{...}}\n
Python → JS: stdin 写入 __IPC__:{"id":1,"result":{...}}\n
并行控制: _ipc_semaphore = 16（限制同时 agent 调用数）
```

### 7 种编排原语

```javascript
// ① agent — 单 Agent 调用
let result = await agent("分析项目", {
  schema: { type: "object", properties: { summary: {} } },  // 结构化输出
  model: "claude-sonnet",                                     // 多模型路由
  label: "代码分析",                                          // 标签
  fullResult: true,                                           // 完整元数据
})

// ② parallel — 屏障并行 (Promise.allSettled)
let [a, b, c] = await parallel([
  () => agent("任务A"),
  () => agent("任务B"),
  () => agent("任务C"),
])

// ③ batchAgents — 批量并行（一次 IPC）
let results = await batchAgents([
  { prompt: "扫描", label: "扫描" },
  { prompt: "分析", label: "分析" },
], 120)

// ④ pipeline — 无屏障流水线（逐阶段传递）
let results = await pipeline(
  ["f1.py", "f2.py", "f3.py"],
  (f) => agent(`分析: ${f}`),
  (analysis) => agent(`总结: ${analysis}`)
)

// ⑤ $dag — 声明式 DAG 图编排
let results = await $dag({
  scan: () => agent("扫描"),
  analyze: { depends: "scan", task: (ctx) => agent(`分析: ${ctx.scan}`) },
  report:  { depends: ["scan", "analyze"], task: (ctx) => agent("报告") },
})
// 拓扑排序 + 并行执行无依赖节点 + 上游失败自动 skip

// ⑥ workflow — 嵌套子 Workflow
let result = await workflow("分析项目", { path: "./src" })

// ⑦ phase / log / budget — 辅助原语
await phase("代码扫描")
await log("发现 3 个问题")
console.log(budget.spent())                    // 已消耗
await budget.report(500, "claude-sonnet")      // 汇报 token 消耗
```

> ⚠️ **不稳定声明：** JS Workflow + V2 Agent 桥接层目前尚不稳定。`bridge.mjs` IPC 通信在复杂并行场景下可能出现超时或状态不同步，建议仅用于探索性编排。

完整 10 场景编排评估报告（含真实 LLM 生成的 workflow 脚本和评分）：
👉 [编排能力深度评估](workflow-templates.html)

---

## 三种执行模式 — 统一入口

```
                    ┌──────────────────┐
                    │    CLI/REPL      │
                    └────────┬─────────┘
                             │ task_description
                             ▼
                    ┌──────────────────┐
                    │   SkillRouter    │
                    │ 意图识别+技能匹配│
                    └────────┬─────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ↓                    ↓                    ↓
   ┌──────────┐      ┌──────────────┐      ┌──────────┐      ┌─────────────┐
   │ 单 Agent  │      │ CLI 编排     │      │ 子代理工具 │      │ JS 编排     │
   │ CLI 直调  │      │ /smart       │      │ task/      │      │ bridge      │
   │          │      │ /orchestrate │      │ orchestrate│      │ .mjs        │
   └──────────┘      └──────────────┘      └──────────┘      └─────────────┘
        │                    │                    │                    │
        └────────────────────┼────────────────────┼────────────────────┘
                             ▼
                    ┌──────────────────┐
                    │  Unified Agent   │
                    │  (ReActCore +    │
                    │   MiddlewareChain)│
                    │  + PlanManager   │
                    │  + ToolRegistry  │
                    └──────────────────┘
```

四类入口共用**同一套**执行引擎：
- **单 Agent** — CLI 直接传入任务描述 → ReAct → Plan → Tools → FinalAnswer
- **CLI 编排** — `/smart`/`/orchestrate` 自动拆维并行（关键词匹配 → 最多 5 维度 → asyncio.gather → 汇总）
- **子代理工具** — 主 Agent 在 ReAct 循环中调用 `task`/`orchestrate` 工具 → 启动子 Agent（同引擎，不同角色 prompt）
- **JS 编排** — Node.js 脚本通过 IPC 桥调用 Python Agent

---

## 技术栈

```
LLM 路由      OpenAI · Anthropic · DeepSeek · OpenRouter
执行引擎      ReActCore · MiddlewareChain · PlanManager
工具系统      ToolRegistry · 12 内置 + 25+ MCP
记忆          ContextCompactor L0-L4 · ChromaDB · SQLite
搜索          Web Search · RAG
GUI 自动化    PyAutoGUI · pyobjc (macOS)
浏览器        Playwright
数据分析      Pandas · Matplotlib
编排          JS bridge.mjs · IPC 协议 · DAG 调度
测试          pytest · pytest-asyncio
```

---

## 项目结构

```
小雷版agent/
├── cli.py               CLI 终端入口
│
├── cli/                  CLI 交互层 (42 文件)
│   ├── enhanced_cli.py   Enhanced REPL · 状态栏
│   ├── repl.py           REPL 循环
│   ├── smart_agent_v2.py V2 Agent 交互
│   └── handlers/         4 组处理器
│
├── core/                 执行引擎 ⭐
│   ├── engine/           LLM 路由 · 技能调度
│   ├── multi_agent_v2/   核心 (ReActCore · Middleware · Tools · Workflow · Prompts)
│   ├── memory/           ContextCompactor + SessionManager
│   ├── workflow/         JS 编排引擎
│   └── mcp/              MCP 客户端
│
├── mcp/                  25+ MCP 服务器
├── config/               配置
├── tests/                77+ 测试
└── agency-agents-zh/     216 专家角色
```

---

<div align="center">
  <br>
  <b>小雷版 AI Agent</b> · ReAct + 中间件管线 · 子代理即工具 · 35+ 工具 · 804 项测试
</div>
