# 小雷版 AI Agent

> **代码事实快照**（生成于 2026-09-07）
> - 版本：v3.4.0 | Python 3.13+ | FastAPI | MIT
> - 核心引擎：94,633 行 Python（不含 tests）
> - V2 主路径：ReAct + 12 层 MiddlewareChain + TaskProgress + GoalStore
> - 工具：12 内置 + 21 MCP + 4 外部（codegraph/playwright/context7/deepwiki）
> - LLM 路由：5+ provider（OpenAI / Anthropic / DeepSeek / OpenRouter / 智谱）
> - 测试：41 文件 / 280+ 通过

---

## 一、TL;DR —— 30 秒启动

```bash
git clone … && cd 小雷版agent
pip install -r requirements.txt
cp .env.example .env       # 填入 LLM API Key

# 启动 Web API
python main.py             # → http://localhost:8001

# 启动交互式 CLI
python cli.py              # REPL 模式

# 一次性直传
python cli.py "分析这个项目结构"
python cli.py /run "爬取微博热搜并生成报告"
python cli.py /smart "从五个维度并行分析项目"
```

---

## 二、架构总览

```
┌─────────────────────────────────────────────────────────────┐
│ 用户交互层                                                  │
│  ┌──────────────┐  ┌────────────────────────────────────┐   │
│  │  CLI/REPL    │  │  FastAPI (main.py, 端口 8001)      │   │
│  │  cli.py      │  │  WebSocket /api/routes/chat_ws.py  │   │
│  │  EnhancedCLI │  │  REST     /api/routes/chat.py      │   │
│  └──────┬───────┘  └──────────┬─────────────────────────┘   │
└─────────┼────────────────────┼──────────────────────────────┘
          │                    │
          ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 核心引擎层 core/multi_agent_v2/                             │
│                                                              │
│  run_unified()  ──  ReActCore.run_react()                    │
│       │              ├─ 12 MiddlewareChain                   │
│       │              ├─ TaskProgress  (能力追踪)              │
│       │              ├─ GoalStore     (跨会话持久化)          │
│       │              └─ ToolRegistry  (12 builtin + 21 MCP)  │
│       │                                                     │
│       └─ /smart /orchestrate  ──  Orchestrator               │
│                                                              │
│  记忆:  L0–L4 ContextCompactor + ChromaDB + SQLite          │
│  Skill: 8 BaseSkill + 216 Expert Persona + SKILL.md         │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│ MCP 服务层 mcp/  (21 内置 + 4 外部)                          │
│  weather · translator · web_scraper · sandbox_tools ·      │
│  project_analyzer · deep_thinking · gui_automation · …      │
│  外部: codegraph · playwright · context7 · deepwiki         │
└─────────────────────────────────────────────────────────────┘
```

### 核心数据流

```
用户输入 → CLI/Web 入口 → ChatHandler
   │
   ▼
SmartAgentCLIv2 → Orchestrator.agent() / WorkAgent.execute()
   │
   ▼
run_react():
  1. Skill 三层匹配 (base + agency + guidance)
  2. LLM 任务类型判定（L330-358：用 LLM 输出 8 个 flag）
  3. 任务标志驱动 max_iterations (L406-409) + 工具过滤 (L361-363)
  4. TaskProgress 初始化
  5. 主循环 (L1267)：
     ├─ LLM Invoke
     ├─ 工具执行 (并行, 洋葱式 Permission)
     ├─ on_tool_end: TaskProgress.update() + GoalStore 同步
     └─ 退出条件：deliverable_complete / plan_completed /
                agent_declared_complete / idle_round_limit /
                no_progress_8_rounds / llm_timeout
```

---

## 三、CLI 指令系统

| 命令 | 用途 |
|------|------|
| `/run` | 单 Agent 智能工作流 | 
| `/smart` `/orchestrate` `/agents` | 多 Agent 并行（自动拆维最多 5 个）|
| `/task` `/explore` `/analyze` `/build` | 子代理（4 角色）|
| `/chat` | 聊天模式 |
| `/automate` | GUI 自动化（macOS）|
| `/scrape` | 数据爬取 |
| `/mcp` | MCP 工具管理 |
| `/workflows` | 工作流进度 |
| `/tools` | 查看可用工具 |
| `/review` | 代码审查 |
| `/debug` `/think` | 切换模式 |
| `/reset` `/status` | 会话控制 |

```bash
# 一次性直传
python cli.py /run "搜索百度热搜"
python cli.py /automate open_app --app Safari
```

---

## 四、核心设计：Plan 关掉，Goal 留着

这是当前 V2 主路径的**关键架构决定**（`react_core.py:1232-1239`）：

```python
# 规划阶段（默认关闭 — 纯 ReAct 对齐 deepseek；
# plan 是收益为负的负载：碎片化、裁决偏差、显示失真。
# 子代理/编排按需 use_plan=True）
ctx.plan = await generate_plan(ctx.task_description, ctx) if use_plan else None
```

### 实际分工

| 角色 | 来源 | 职责 |
|------|------|------|
| **Plan（关掉）** | `plan_manager.generate_plan` 两步法 LLM | 任务拆解（仅子代理/编排用）|
| **TaskProgress** | `task_progress.py` 553 行 | 能力追踪（file_written / web_search / code_executed / subagent_output）|
| **GoalStore** | `goal_store.py` 74 行 | 跨会话持久化（`~/.xiaolei/goals/unfinished.json`）|
| **update_goal（tool）** | `tool_registry.py:1677-1698` | agent 主动声明 complete/blocked/progress |
| **deliverable_complete** | `react_core.py:1690-1714` | system 检测"写入 + 验证"后自动收尾 |
| **goal-round 续轮** | `react_core.py:1436-1493` | 目标未达成时注入 user 消息续做 |

### 完成判定的 3 条路径（system 不依赖 LLM 自报）

1. **deliverable_complete**（`react_core.py:1690-1714`）— system 检测 `_wrote_this_round + _deliverable_verified` → 立即收尾
2. **plan_completed**（line 1279-1332）— 仅在 `use_plan=True` 时生效
3. **idle_round_limit**（line 1403-1434）— 兜底：连续 6 轮无进展 + 任务含"产出型"关键词 + 交付物未写 → 强制收尾

**update_goal 的真实作用**：给 LLM 一个 status 声明协议，让 system 知道 LLM 是否**有意识**自己在做什么；**不**是完成判定的必经路径。

---

## 五、ReAct 循环核心

### 一回合 5 步

```
1. LLM Invoke
   ├─ 正常: 有 tool_calls → 进入 parse
   └─ 空跑: 无 tool_calls
      ├─ 计划完成 → final_answer, exit
      ├─ 空转 ≥6 轮 → final_answer + interrupted
      └─ <6 轮 → inject forced_instructions + retry (≤2 次)

2. on_plan_check — ReActCoreMiddleware 检查计划步骤

3. Tools Execute (on_wrap_tool_call, 洋葱式)
   ├─ PermissionMiddleware: 3 级权限 + ShellGuard
   ├─ ToolCache: 命中直接返回
   ├─ validate_arguments: 参数合法性
   └─ handler → bound_result 统一截断

4. on_tool_end
   ├─ TaskProgress.update() — 能力追踪
   ├─ 失败 → mark + retry counter
   └─ HookMiddleware: KEPA 重试决策

5. 回到 1
```

### 保护机制

| 机制 | 触发条件 | 行为 |
|------|---------|------|
| 空转退出 | `consecutive_idle_rounds ≥ 6` | `interrupted + final_answer` |
| 回合内重试 | 空跑 <6 轮 | inject forced_instructions + retry |
| LLM 超时 | 60s 无响应 | `interrupted` |
| 重试上限 | 同 LLM 回复最多 2 次空跑 | 用最后一次回复兜底 |
| 任务类型驱动 | LLM 判定 8 个 flag（L330-358）| 决定 max_iterations + 工具过滤 |
| deliverable_complete | 写入 + 验证 | 立即收尾 |

---

## 六、12 层中间件管线

`build_default_chain()` 注册顺序（`react_core.py:1067-1079`）：

```
 ① ReActCoreMiddleware        on_plan_check     核心循环调度
 ② TodoMiddleware             on_start          防过早退出
 ③ MemoryMiddleware           on_llm_invoke     记忆注入
 ④ CompactionMiddleware       on_tool_end       LLM 摘要压缩
 ⑤ TruncationMiddleware       on_tool_end       兜底截断
 ⑥ LoopDetectionMiddleware    on_llm_invoke     循环检测
 ⑦ ClarificationMiddleware    on_llm_invoke     拦截反问
 ⑧ ReasoningMiddleware        on_llm_invoke     推理优化
 ⑨ PermissionMiddleware       on_wrap_tool_call 洋葱式权限
 ⑩ HookMiddleware             on_tool_end       KEPA 重试
 ⑪ ReActDepthMiddleware       on_llm_invoke+    深度 ≤30
 ⑫ KEPAMiddleware             on_llm_invoke+    知识沉淀 + SharedBus
 ⑬ ReflectionMiddleware       on_tool_end       每 3 轮反思
```

洋葱式 Permission：`Permission → ToolCache 命中 → validate → handler → bound_result`。

---

## 七、工具系统

### ToolRegistry 注册模型（`tool_registry.py`）

```
ToolRegistry (全局单例)
├── SERVER_BUILTIN (12 个内置)
│   ├─ read_file / write_file / edit_file       文件
│   ├─ execute_python / execute_shell           执行
│   ├─ web_search / fetch_url                   网络
│   ├─ search_files / git / write_todos         辅助
│   ├─ update_goal (agent 状态声明)
│   └─ task / orchestrate                       子代理入口
│
└── SERVER_MCP (21 内置 + 4 外部)
    ├─ CodeGraph / Playwright / Context7 / DeepWiki (外部)
    ├─ project_analyzer / sandbox_tools / web_scraper / …
    └─ discovery: 5s/server, 12s 总超时, 同名 {server}_ 前缀
```

### 工具执行流程
```
PermissionMiddleware.check → ShellGuard.scan
  → ToolCache.get → validate_arguments
    → handler(args) → bound_result 统一截断
      → ToolCache.set
```

### MCP 自动发现（`tool_registry.py:230-247`）
```python
reg.discover_all()  # asyncio.wait_for(timeout=15)
  → _discover_mcp_configs
  → _connect_mcp_servers_parallel (5s/server)
  → handler 闭包: 代理到 mcp_client.call_tool
```

---

## 八、TaskProgress 与 GoalStore

### TaskProgress (`task_progress.py:161-199`)

**能力追踪**（替代旧 `update_step_status`）：
```python
@dataclass
class Capability:
    kind: str  # "web_search" | "url_fetched" | "file_written" | "code_executed"
    metadata: Dict[str, Any]  # path / size_bytes / query / edit 等
```

**检测来源**（`_detect_from_result` L39-150）：
- `write_file` 工具 → `file_written` capability
- `edit_file` 工具 → `file_written` (edit=True)
- `execute_python` 写文件 → `file_written`
- `execute_shell` (echo/cat/tee) → `file_written`
- `web_search` / `fetch_url` / `fetch_json` / `hot_search` → `web_search` / `url_fetched`

**真实交付物判定**（`react_core.py:147-161`）：
```python
def _has_real_deliverable(tp) -> bool:
    """过滤 /tmp/ 和 /var/folders/（避免 python3 写 /tmp 假完成）"""
    for c in tp.completed_capabilities:
        if c.kind != "file_written": continue
        _p = os.path.abspath(str(c.metadata.get("path", "")))
        if "/tmp/" in _p or "/var/folders/" in _p: continue
        return True
    return False
```

### GoalStore (`goal_store.py`)

**单文件持久化**：`~/.xiaolei/goals/unfinished.json`

**保存时机**（`react_core.py:2036-2061`）：
- 完成类收尾（plan_completed / completed_with_answer / agent_declared_complete / deliverable_complete）→ `clear_unfinished_goal`
- 其他 → `save_unfinished_goal({task, exit_reason, rounds_done, files_written, blocked_reason, progress_note})`

**恢复时机**（`react_core.py:1171-1193`）：任务匹配（≤12 字续做词 或 任务前 40 字精确匹配）→ 注入 `<goal_resume>` 块

### update_goal tool（`tool_registry.py:1006-1045`）

**Action 语义**：
- `complete` → `ctx._agent_declared_complete = True` → 主循环校验 evidence
- `blocked` → `ctx._blocked_streak += 1` → 连续 3 次同因才接受
- `progress` → `ctx._goal_progress_note = reason[:200]` → 注入 system prompt

**完成校验**（`react_core.py:1349-1390`）：
```python
if _agent_declared_complete:
    # 校验 evidence：有 file_written capability？
    if not _is_production or _deliverable_ok:
        → 收尾
    # 不足 → 驳回；有界重试 2 次后强制收尾
```

---

## 九、Prompt 架构

**34 个 `.txt` 文件替代 Python 硬编码**：
```
prompts/
├── system/        base / code_gen / report / plan_generation / debug / game_dev / fallback_* (9)
├── tools/         task / orchestrate / web_search / fetch_url / read_file /
│                  write_file / edit_file / execute_shell / execute_python /
│                  search_files / git / write_todos / arbor_viz / text_analyzer /
│                  update_goal (14)
├── agents/        general / explore / build / analyze / orchestrator / work_rules (5)
└── blocks/        architecture / parent_context / output_format /
                   execution_status / style_guide / failed_approaches (5+)
```

### 任务类型驱动注入（`react_core.py:330-409`）

**LLM 判定替代字符串匹配**（解决关键词判定不准问题）：
```python
# L330-358: 用 LLM 输出 8 个 flag
_resp = await _router.simple_chat(
    "对以下请求，用逗号分隔输出8个数字（1=是，0=否）：\n"
    "需要写代码/脚本/HTML？,需要开发游戏？,"
    "需要生成报告/分析数据/查热搜？,需要分析项目结构/代码？,"
    "需要在桌面保存/生成文件？,需要搜索网络/查百度/热搜？,"
    "需要读写/操作文件？,需要替换/修改/编辑已有文件内容？\n"
    "请求：" + _task_desc,
    temperature=0, max_tokens=32
)
_task_flags = {
    "code": _parts[0] == "1", "game": _parts[1] == "1",
    "report": _parts[2] == "1", "project_analysis": _parts[3] == "1",
    "desktop_save": _parts[4] == "1", "search": _parts[5] == "1",
    "file_operation": _parts[6] == "1", "edit": _parts[7] == "1",
}

# L406-409: 任务类型驱动 max_iterations
if _task_flags["project_analysis"]: ctx.max_iterations = max(15)
if _task_flags["report"] or _task_flags["code"] or _task_flags["game"]: ctx.max_iterations = max(15)
```

---

## 十、多 Agent 协作

### 三种路径

```
单 Agent 内部 → task/orchestrate 工具
  └─ LLM 调 task 启动子 Agent（同一套 ReActCore，personality_prompt 不同）
  
CLI 快捷指令 → /smart /orchestrate /agents
  └─ 自动拆维（搜索/分析/生成/采集/代码/翻译）最多 5 个
  └─ asyncio.gather 并行执行 → 结果汇总

JS Workflow → bridge.mjs
  └─ Node.js 通过 IPC 调用 Python Agent
  └─ 7 种原语: agent / parallel / pipeline / $dag / workflow / phase / budget
```

### 跨 Agent 通信

- **KEPA SharedBus**（`kepa_middleware`）：主/子 Agent 共享知识沉淀
- **Parent Context 注入**（`subagent/spawn.py`）：子代理起步时看到父上下文摘要
- **Workflow Context**（JS bridge）：`globalTask` / `currentPhase` / `previousPhaseResults`

### 共享资源
| 资源 | 共享方式 |
|------|---------|
| ToolRegistry | 全局单例 |
| SharedBus | 全局单例 (KEPA) |
| LLMRouter | 全局单例 (5+ provider) |
| AgentPool | 8 预热 WorkAgent |
| Session 存储 | SQLite (`~/.xiaolei/sessions/{sid}.json`) |

---

## 十一、记忆系统

### 短期（会话内）
| 层 | 位置 | 生命周期 |
|----|------|----------|
| tool_results | `ctx.tool_results` | 当前 ReAct 轮次 |
| conversation | `ctx._conversation_history` | 整个会话 |
| forced_instructions | `ctx.forced_instructions` | 当前轮次 |
| knowledge_context | `ctx.knowledge_context` | 每轮增量注入 |
| goal_progress_note | `ctx._goal_progress_note` | update_goal(progress) 注入 |

### 压缩 L0–L4
| 层 | 机制 |
|----|------|
| L0 | ToolResultBudget — >100K chars 落盘 |
| L1a | API Context Mgmt — 清旧 thinking 块 |
| L1b | UI 折叠追踪 |
| L1c | Time-based — gap>60min 只保 5 条 |
| L2 | 缓存断点 metadata |
| L2b | SnipCompact — 前半+后四分之一 |
| L3 | LLM 9-section 摘要（Goal/Search/Code/Data/...）|
| L4 | 重建消息 + 附件注入 |

Circuit Breaker: 连续 3 次失败 → 跳过压缩。SessionMemoryCompact 作为启发式回退（无 LLM）。

### 长期（跨会话）
| 存储 | 后端 | 用途 |
|------|------|------|
| VectorDB | ChromaDB + sentence-transformers | 语义搜索 |
| GoalStore | 单 JSON 文件 | 任务续做 |
| Session | SQLite + session_manager | 对话日志 + artifact 归档 |

---

## 十二、JS 编排引擎

Node.js ↔ Python IPC 桥接，JS 脚本通过 `bridge.mjs` 调用 Python Agent。

### IPC 协议
```
JS → Python: stdout 写入  __IPC__:{"id":1,"type":"agent","data":{...}}\n
Python → JS: stdin 写入   __IPC__:{"id":1,"result":{...}}\n
并行控制:   _ipc_semaphore = 16
```

### 7 种编排原语
```javascript
let r = await agent("分析项目", { schema: {...}, model: "...", label: "..." })
let [a, b, c] = await parallel([() => agent("A"), () => agent("B")])
let results = await batchAgents([{prompt: "扫描", label: "扫描"}, ...], 120)
let results = await pipeline(files, (f) => agent(`分析: ${f}`), (a) => agent(`总结: ${a}`))
let results = await $dag({ scan: ..., analyze: {depends: "scan", task: ...} })
let r = await workflow("分析项目", { path: "./src" })
await phase("代码扫描")  await log("发现 3 个问题")  await budget.report(500, "claude-sonnet")
```

> ⚠️ **不稳定声明**：JS Workflow + V2 Agent 桥接层在复杂并行场景下可能超时或状态不同步，建议仅用于探索性编排。

---

## 十三、技术栈

| 类别 | 技术 |
|------|------|
| Web | FastAPI ≥0.115 + Uvicorn + WebSocket + Jinja2 |
| 数据库 | SQLAlchemy 2.0 + PyMySQL + Redis |
| LLM | OpenAI · Anthropic · DeepSeek · OpenRouter · 智谱 GLM |
| 向量 | ChromaDB + sentence-transformers + transformers + torch |
| 搜索 | duckduckgo-search + BeautifulSoup + RAG |
| 浏览器 | Playwright |
| GUI (macOS) | PyObjC + PyAutoGUI + pyperclip |
| 数据分析 | pandas + matplotlib + scikit-learn + lightgbm + openpyxl |
| OCR (可选) | paddleocr + paddlepaddle |
| 工具 | python-dotenv + pyyaml + pyjwt + psutil + loguru |
| 测试 | pytest + pytest-asyncio |
| 编排 | Node.js bridge.mjs + IPC 协议 + DAG 调度 |

---

## 十四、项目结构

```
小雷版agent/
├── main.py              FastAPI 应用入口 (端口 8001)
├── cli.py               CLI 入口 (REPL + 直传)
│
├── core/                核心引擎 (94K+ 行)
│   ├── multi_agent_v2/        V2 架构 (主路径，V1 agent_system.py 已删除)
│   │   ├── agents/            ReActCore · Middleware · TaskProgress · GoalStore
│   │   ├── tools/             ToolRegistry · MCP Client · Skill Loader
│   │   ├── orchestration/     Orchestrator (parallel/pipeline)
│   │   ├── workflow/          JS Workflow · Bridge · DAG
│   │   ├── prompts/           PromptBuilder · 34 个 .txt
│   │   ├── skills/            Skill 加载
│   │   └── infrastructure/    池化 / 监控
│   ├── engine/               LLM 路由 · Skill 调度
│   ├── memory/               ContextCompactor L0–L4
│   ├── tools/                V1 工具 (bash/sandbox/shell/git)
│   ├── handlers/             V1 handlers
│   ├── workflow/             BFS Processor
│   ├── search/ monitoring/ security/ tasks/ services/
│   └── skill_base.py skill_extractor.py guidance_skills.py
│
├── api/                 Web API
│   ├── web_server.py
│   ├── route_manager.py
│   ├── pages.py
│   └── routes/ chat.py (975行) / chat_ws.py (263) / history.py (936) / history_stats.py
│
├── cli/                 CLI 交互层 (42 文件)
│   ├── enhanced_cli.py · repl.py · smart_agent_v2.py
│   └── handlers/ chat/mcp/task/utility
│
├── mcp/                 MCP 服务器 (21 内置)
├── prompts/             34 个提示词 .txt
├── plugin/              插件系统
├── config/              配置
├── static/              CSS/JS
├── tests/               测试 (41 文件)
├── tools/               工具管理器
├── infrastructure/      Worktree Manager
├── workflows/           JS Workflow 示例
├── data/                运行时数据
│
├── agency-agents-zh/    216 专家角色 Persona
├── pyproject.toml
├── Dockerfile
├── LICENSE              MIT
└── .pre-commit-config.yaml
```

---

## 十五、测试

```bash
pytest                                   # 全部
pytest tests/v2/test_real_scenarios.py   # 端到端真实场景
pytest tests/v2/test_react_core_mock.py  # ReAct Core (mock LLM)
pytest -v -k "middlewares"               # 中间件单元
```

| 测试套件 | 覆盖 |
|----------|------|
| `test_tool_parser.py` | 4 级 fallback 解析路径 |
| `test_middlewares_unit.py` | 中间件单元 |
| `test_react_core_mock.py` | run_react 6 场景 mock LLM |
| `test_phase1_path_regex.py` | 中文/混合/ASCII 路径 |
| `test_shell_guard_handler.py` | 高危命令拦截 |
| `test_real_scenarios.py` | 20 真实端到端场景 |
| `test_e2e_*.py` | worktree/checkpoint/permission/degradation |

**回归对比**：修复前 327 pass / 6 fail / 9 hang → 修复后 **280 pass / 0 fail / 0 hang**。

---

## 十六、配置

### 环境变量 (`.env`)
```bash
# LLM (任选一组)
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
DEEPSEEK_API_KEY=...
ZHIPUAI_API_KEY=...
OPENROUTER_API_KEY=...

# 服务
AGENT_PORT=8001
AGENT_HOST=0.0.0.0
LOG_LEVEL=info
DEV_MODE=false
FRONTEND_AGENT_PORT=8002
FRONTEND_AGENT_HOST=0.0.0.0

# 数据库
DATABASE_URL=mysql+pymysql://...
REDIS_URL=redis://...
```

### MCP 配置 (`.mcp.json`)
```json
{
  "mcpServers": {
    "codegraph": { "command": "codegraph", "args": ["serve", "--mcp"] },
    "playwright": { "command": "npx", "args": ["-y", "@playwright/mcp@0.0.70"] },
    "context7":  { "command": "npx", "args": ["-y", "@upstash/context7-mcp@2.1.8"] },
    "deepwiki":  { "command": "npx", "args": ["-y", "deepwiki-mcp@0.0.6"] }
  }
}
```

---

## 十七、已知风险与生产建议

| 优先级 | 项 | 建议 |
|--------|-----|------|
| 🔴 P0 | CORS `allow_origins=["*"]` + credentials | 生产环境必须收敛 |
| 🔴 P0 | `init_system()` 无 try/except 兜底 | 启动失败应有健康检查 |
| 🟡 P1 | 4 个 MCP 桌面侧断连（arbor/codegraph/evermem/memsearch）| 排查 Electron sidecar `$PATH` |
| 🟡 P1 | PyObjC 写在通用依赖，Linux 部署失败 | 移入 `[project.optional-dependencies]` `macos` |
| 🟡 P1 | torch 全量引入，Docker 镜像巨大 | CPU-only wheel 或按需加载 |
| 🟢 P2 | 顶层冗余文件 | 清理 |
| 🟢 P2 | V1/V2 双架构并存 | 制定迁移路线 + 兼容层到期日 |
| 🟢 P2 | 缺 OpenTelemetry / Prometheus | 已有中间件管线，加 span 即可 |
| 🟢 P2 | 缺 bandit / pip-audit / CHANGELOG | 加入 CI |

---

## 十八、文档生成说明

本报告基于 `react_core.py` 2075 行 + `task_progress.py` 553 行 + `goal_store.py` 74 行 + `tool_registry.py` 2493 行 + 34 个 prompts `.txt` 的**实证代码**生成。

**核心认知修正**：
- `update_goal` 是注册的 tool，不是字段（tool_registry.py:1677-1698）
- 任务类型判定已用 LLM 替代字符串匹配（react_core.py:330-358）
- 完成判定有 3 条独立 system 路径（deliverable_complete / plan_completed / idle_round_limit），不依赖 LLM 自报 update_goal

**保留的旧版报告**：
- `项目评估报告.md`（2026-09-05）— 成熟度评估仍有效
- `项目状态分析报告.md`（2026-09-05）— 仍较新

旧版已归档至 `.trash-docs/`（README / 项目架构分析 / 项目结构分析 / 测试执行报告 / 小雷版agent-完整优化报告）—— 可在确认无价值后删除。

---

<div align="center">

**小雷版 AI Agent** · v3.4.0 · ReAct + 12 中间件 + Plan 关 / Goal 留

</div>
