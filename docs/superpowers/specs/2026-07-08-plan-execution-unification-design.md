# Plan-Execution 统一 & Bridge 错误分级 & 中间件修复

**日期**: 2026-07-08
**范围**: `core/multi_agent_v2/agents/`, `core/multi_agent_v2/workflow/`, `cli/handlers/`

---

## 背景

当前系统有 14 个已识别的 bug，根因集中在三个系统性问题：

1. **Plan-Execution 脱节**: plan 生成和实际执行是两套独立系统，靠启发式规则（工具等价组、死锁断路器）强行对齐，导致步骤错误推进、ReAct 空转
2. **Bridge 错误传播不精确**: `ctx.last_error` 无分级，bridge 将非致命诊断信息当成致命错误，导致 workflow 级失败 + 全量重跑
3. **中间件检测粒度不够**: `_idle_rounds` 只看工具调用次数不看 plan 进度，并行 agent stdout 交叉混乱

---

## 设计概览

三个子系统依次改造，改动文件 ~10 个：

```
Part 1: TaskProgress 统一追踪  (修 P1/P2/P6/P7/P9/P10/P14)
Part 2: Bridge 错误分级         (修 P3/P4/P5/P8/P12)
Part 3: 中间件检测修复           (修 P11/P13)
```

---

## Part 1: TaskProgress - Plan-Execution 统一追踪

### 问题

```
plan_generate()  →  5 个 PlanStep (web_search → fetch_url → parse → explore → write)
实际执行            →  LLM 走 web_search → write_file(HTML) → 卡住
update_step_status  →  等价组: web_search≈fetch_url, deadlock breaker 强制标记 done
结果                →  步骤显示 2/5 但实际任务未完成
```

### 方案

新增 `TaskProgress` 类，替代分散在 `plan_manager.update_step_status()` 和 `react_core` 中的步骤推进逻辑。

#### 核心概念: Capability（能力）

不按工具名判断进度，而是检测 LLM 实际达成了什么**能力**：

```python
@dataclass
class Capability:
    kind: str           # "web_search" | "url_fetched" | "file_written" | "code_executed"
    timestamp: float
    metadata: dict      # {"query": "...", "path": "...", "size_bytes": N}

CAPABILITY_DETECTORS = {
    "web_search":    lambda r: r.tool in ("web_search", "fetch_url", "hot_search") and r.success,
    "url_fetched":   lambda r: r.tool == "fetch_url" and r.success and r.content_len > 500,
    "file_written":  lambda r: r.tool == "write_file" and r.success and r.content_len > 100,
    "code_executed": lambda r: r.tool == "execute_python" and r.success and r.stdout != "None",
    "file_read":     lambda r: r.tool == "read_file" and r.success,
}
```

每轮 LLM 回复后扫描 `ctx.tool_results`，提取新达成的能力，存入 `TaskProgress.completed_capabilities`。

#### step 匹配: 能力 → 步骤

PlanStep 的 `postconditions` 改为能力语义：

```python
step.postconditions = [
    "capability:web_search(query=百度热搜)",
    "capability:file_written(path=~/Desktop/*.html, size>1000)",
]
```

推进逻辑：

```
for each pending step (按顺序):
    required = step.postconditions  # ["capability:web_search(...)", "capability:file_written(...)"]
    matched = all(req 在 TaskProgress.completed_capabilities 中有匹配)
    if matched → step.status = "done", 继续下一个 pending step
```

匹配规则：`capability:kind(key1=val1, key2=pattern)` 与 `Capability` 对象比对：
- `kind` 精确匹配
- metadata 中的 key-value：`val1` 精确匹配，`pattern` 支持 glob（如 `*.html`）

当 LLM 走了捷径（比如 web_search → 直接 write_file HTML），系统识别到 `web_search` + `file_written` 两项能力都已达成，推断"数据收集 + 产出"完成，推进对应步骤。

如果 LLM 完成的工作**超出**当前 step 要求（一个 tool_call 同时产生多项能力），后续 step 也会被自动推进。

#### 自适应重规划（替代 deadlock breaker）

`react_core.py:546-585` 的死锁断路器**删除**，改为：

```
当 TaskProgress.stuck_counter >= 4（连续 4 轮无新能力）且还有 pending steps:
  → 用现有 llm_router 发轻量请求（temperature=0.2, max_tokens=200, timeout=10s）:
    prompt: "已完成能力: [Capability列表]。剩余步骤: [pending step descriptions]。"
           "用 1-2 步重新规划剩余任务，格式：步骤|描述|工具名。"
  → 解析为新 PlanStep，替换 pending steps
  → 重置 stuck_counter
```

> 这条 LLM 请求不改变 ctx.tool_results、不增加 react_depth，纯辅助性质。

#### 子代理 max_rounds 调整

`spawn.py:20`: `_MAX_SUBAGENT_ROUNDS` 10 → 15。10 轮对 5-step plan + 探索太紧。

### 改动文件

| 文件 | 改动 |
|------|------|
| `agents/task_progress.py` | **新增**，~150 行 |
| `agents/react_core.py` | `update_step_status` 调用 → `ctx.task_progress.update()`；删除死锁断路器 (L546-585)；_idle_rounds 改为能力检测 |
| `agents/plan_manager.py` | `_infer_postconditions` 改为生成 `capability:` 格式；`update_step_status` 保留签名 + deprecation log |
| `agents/middleware.py` | PlanStep.postconditions 文档更新 |
| `agents/subagent/spawn.py` | `_MAX_SUBAGENT_ROUNDS` 10 → 15 |

### 被修问题

P1, P2, P6, P7, P9, P10, P14

---

## Part 2: Bridge 错误分级 & 结构化结果传递

### 问题

```
run_react 返回: {success: True, answer: "报告OK", error: "连续12轮空转"}
    ↓
bridge: result.error truthy → throw Error → workflow 失败
    ↓
CLI: 回退单Agent → 全量重跑搜索
```

同时 `consecutive_idle_rounds` 因重试循环加速达到12（6轮×2次=12），应改为按轮计数。

### 方案

#### A. 错误分级：exit_reason

`RunContext` 增加字段 `exit_reason: str`，记录**精确的退出路径**：

| 退出场景 | exit_reason |
|---------|-------------|
| 所有 steps done | `plan_completed` |
| post-completion 3 轮用完 | `post_completion_exhausted` |
| 有 final_answer + postcondition 通过 | `completed_with_answer` |
| 8轮无步骤推进 | `no_progress_8_rounds` |
| 12轮空转无工具调用 | `empty_run_12_rounds` |
| LLM 调用超时 | `llm_timeout` |
| LLM 调用异常 | `llm_error` |
| 内部重试耗尽 | `retries_exhausted` |
| LoopDetection hard kill | `loop_detected` |
| 中间件终止 (各阶段) | `middleware_kill_llm` / `middleware_kill_plan` / `middleware_kill_tool` / `middleware_kill_toolend` |
| 用户中止 | `user_aborted` |

`run_react` 返回结构变更：

```python
return {
    "success": bool(ctx.final_answer),
    "answer": ctx.final_answer,
    "exit_reason": ctx.exit_reason,        # 新增
    "diagnostic": ctx.last_error or "",    # 改名, 仅日志用
    "iterations": ctx.react_depth,
    "tool_results": ctx.tool_results,
}
```

`ctx.last_error` 保留不变，仅用于日志输出。**不再出现在返回值的 error 字段中**。

#### B. Bridge 只认 exit_reason

`bridge.mjs:146-153`:

```js
// 旧
if (result.error) throw new Error(result.error);

// 新
const isFatal = result.exit_reason === "llm_error"
             || result.exit_reason === "retries_exhausted"
             || result.exit_reason === "loop_detected";
if (isFatal && !result.success) {
    throw new Error(result.diagnostic || "agent failed");
}
// empty_run_12_rounds, llm_timeout, no_progress → 有 output 就正常返回
```

`orchestrator.py` 和 `js_workflow.py` 同步更新字段名。

#### C. `consecutive_idle_rounds` 修正

`react_core.py:531`: `consecutive_idle_rounds` 的递增移到**每轮结束后**，而非每次 LLM 重试时。重试循环内部只设置一个 `_retry_idle` flag，循环结束且仍然无 tool_calls 时才 +1。

#### D. 结构化结果传递

并行阶段 results 增加 `artifacts` 字段：

```python
response_result = {
    "output": output,
    "artifacts": {
        "files": ["~/Desktop/baidu_hot.html", ...],
        "data_summary": "获取到 20 条热搜数据",
    },
    "exit_reason": result.exit_reason,
    ...
}
```

下游 agent 直接从 `artifacts.files` 读取文件路径，无需重新搜索。

#### E. Workflow 失败时复用产物

`chat_handler.py:251-268`: workflow 失败后，检查 `result.json` 中的 `artifacts`：

```
有 artifacts.files → 构建 fallback prompt（含已有文件路径）→ 用单 Agent 继续
无 artifacts      → 走现有回退逻辑
```

### 改动文件

| 文件 | 改动 |
|------|------|
| `agents/react_core.py` | exit_reason 设置（14处）；consecutive_idle_rounds 移到轮次级别；run_react 返回结构变更 |
| `agents/middleware.py` | RunContext 增加 exit_reason 字段 |
| `orchestration/orchestrator.py` | AgentResult.error → diagnostic |
| `workflow/bridge.mjs` | 错误检查改用 exit_reason；artifacts 字段提取 |
| `workflow/js_workflow.py` | IPC 响应增加 artifacts, exit_reason |
| `cli/handlers/chat_handler.py` | Workflow 失败时复用产物 |

### 被修问题

P3, P4, P5, P8, P12

---

## Part 3: 中间件检测修复

### 问题

- `_idle_rounds` (react_core:1071) 只看 `tool_results` 数量是否增长。LLM 反复调 read_file 但没有 plan 进展时检测无效。
- 并行 agent stdout buffer 用栈（LIFO），打印顺序混乱。

### 方案

#### A. `_idle_rounds` → 能力检测

```python
# 旧
_new_tool_count = len(ctx.tool_results)
if _new_tool_count > _had_tool_count: ...

# 新
_new_capabilities = ctx.task_progress.new_capabilities_this_round
if _new_capabilities: ...
```

`TaskProgress.update()` 返回本论新检测到的能力集合。

#### B. stdout buffer 栈 → 队列

`spawn.py:182-214` stdout capture 从栈改为队列：

```python
_stdout_queue: asyncio.Queue = asyncio.Queue()

def _push_stdout():
    buf = io.StringIO()
    sys.stdout = buf
    return buf

def _finish_stdout(buf):
    sys.stdout = sys.__stdout__
    captured = buf.getvalue()
    _stdout_queue.put_nowait(captured)
```

每个子代理完成后调用 `_finish_stdout(buf)` 入队，主循环在**所有并行 agent 完成后**统一出队打印（FIFO 顺序），保持打印与启动顺序一致。

### 改动文件

| 文件 | 改动 |
|------|------|
| `agents/react_core.py` | `_idle_rounds` 改为能力检测 |
| `agents/subagent/spawn.py` | stdout capture 改为队列顺序 |

### 被修问题

P11, P13

---

## 兼容性

- 所有改动向后兼容：旧 plan step 的 `postconditions` 如果没有 `capability:` 前缀，回退到 `tool_called:` 和 `file_exists:` 逻辑
- `update_step_status` 保留函数签名，内部调用 `task_progress.update()`
- Bridge 新增字段不影响旧 workflow（`diagnostic` 为 undefined 时走旧分支）

---

## 测试要点

1. Plan step 能正确推进：web_search → write_file 快捷路径
2. 死锁断路器删除后，自适应重规划能否在 4 轮无进展时触发
3. `exit_reason="empty_run_12_rounds"` + `success=True` 时 bridge 不 throw
4. `exit_reason="llm_error"` + `success=False` 时 bridge 正确 throw
5. `consecutive_idle_rounds` 不再因重试加速
6. 并行 agent stdout 按开始顺序打印
7. 子代理 15 轮能完成 5-step plan
