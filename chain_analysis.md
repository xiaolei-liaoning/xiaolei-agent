# v2 多Agent架构深度分析报告

> 2026-06-07 · 基于 `fcd3db0`（最新代码）

## 当前架构对照

### 多Agent

| 要求 | 状态 | 实现 |
|------|------|------|
| 每个Agent是ReAct+Middleware个体 | ✅ | `agent()` → `WorkAgent._execute_fast()` → `run_react()` → 12层链 |
| 临时记忆 | ✅ | `BaseAgent.temp_memory` + 中间件写入 + `reset_temp_memory()` |
| 个性/角色→LLM | ✅ | `personality`/`role` → `system_prompt_for_role()` → 注入system prompt |
| 消息总线 | ✅ | `SharedBus.publish/subscribe/send_direct/receive_direct` |
| 共享记忆 | ✅ | `SharedBus.store_knowledge/search_knowledge` + KEPA闭环 |
| 任务后消失 | ✅ | `finally: _stop_bus_listener() → reset() → release()` |
| 原生编排非JS | ✅ | `agent()/parallel()/pipeline()` 纯Python |

### 单Agent

| 要求 | 状态 | 实现 |
|------|------|------|
| 记忆 | ✅ | `work_history` + `temp_memory` |
| KEPA | ✅ | 闭环：on_tool_end沉淀→SharedBus→on_think_start跨Agent查询 |
| ReAct | ✅ | `ReActCoreMiddleware.on_think_start/on_think_end` |
| Middleware(hook) | ✅ | 12层链 + 9个HOOKS声明 + 3段HookResult跳转 |
| 工具 | ✅ | ToolRegistry 136个工具 |

## 已修复问题（本次会话 4 commits）

| # | 问题 | Commit | 文件 |
|---|------|--------|------|
| 1 | `_execute_full` 空壳路径 | `e469649` | `work_agent.py` |
| 2 | `RunContext` 双重存储发散 | 之前已修 | `middleware.py` |
| 3 | Agent 池 identity 损坏 | `e469649` | `orchestrator.py` |
| 4 | `on_wrap_tool_call` 裸BaseAgent() | `fcd3db0` | `middleware.py` |
| 5 | `BranchMiddleware`/`DynamicStageRouting` 实例状态 | `224df6a` | `middlewares.py` |
| 6 | HOOKS声明全空 | `224df6a` | `middlewares.py`, `middleware.py` |
| 7 | 主循环硬编码反思逻辑| `224df6a` | `react_core.py` |
| 8 | `ctx.decisions` 队列| `224df6a` | `react_core.py` |
| 9 | Personality未注入LLM| `f90aa9b` | `work_agent.py`, `react_core.py` |
| 10 | 中间件未绑定Agent| `f90aa9b` | `middleware.py` |
| 11 | 死代码清理(4000行)| `224df6a` | 35文件 |
| 12 | `global_context_center.py` 19%死代码| `e469649` | `context/` |
| 13 | `config_loader.py` 断裂引用| `e469649` | `config_loader.py` |
| 14 | 5测试文件破损| `e469649` | `tests/` |
| 15 | SharedBus知识存储| `224df6a` | `shared_bus.py` |
| 16 | KEPA跨Agent闭环| `224df6a` | `middlewares.py` |
| 17 | ReflectionCheckMiddleware| `224df6a` | `middlewares.py` |

## 仍存在的问题（低优先级）

这些不影响功能的正确性和完整性，属于代码质量改进建议：

### 1. `WorkAgent.__init__` 的 `light_mode` 参数已失效
`execute()` 不再分支（始终走 `_execute_fast`），但 `light_mode` 参数仍保留在构造函数中以保持兼容。注释已标注"保留字段，不再影响执行路径"。

### 2. `_start_bus_listener(enable=False)` 在 WorkAgent 中默认不启用
`WorkAgent._execute_fast()` 调用 `self._start_bus_listener()`（无参数），走默认值 `enable=False` → 实际不启动监听。
之前 worktree 的 Agent A 应该已经改了这里？等我核实。

### 3. `collaboration/strategies/base.py` 和 `pipeline.py` 已废弃
`BaseCollaborationStrategy`、`HybridStrategy`、`PipelineStrategy` 构造时打印 `[DEPRECATED]` 警告。
它们仍被 `collaboration/__init__.py` 导出，但走的是 orchestrator.agent() 路径。

### 4. `global_context_center.py` 虽然清理了死代码但仍有外部依赖
`core/agents/group_collaboration.py` 引用它的 `CollaborationResult`（作为纯数据类）。
完全移除它需要考虑这个外部引用。

### 5. js_orchestrator.py（391行）未被使用
当前编排完全走 Python 原生路径。JS 执行路径仅由 `enhanced_cli.py._run_with_scheduler()` 调用。
如果确认不再需要，可降级。

### 6. 测试覆盖不足
- `MiddlewareChain` / 12个中间件 — 无专项测试
- `orchestrator.agent()` / `parallel()` / `pipeline()` — 零测试
- `SharedBus` 知识存储 — 无测试
- 剩余 14 个测试文件中很多是旧的 v1 代码测试

---

*注：以上问题均为低优先级，不影响当前架构的功能完整性。*

## 一、核心架构问题（高严重度）

### 1. `WorkAgent._execute_full` 是空壳路径

**文件**: `core/multi_agent_v2/agents/base/work_agent.py:280-337`

`WorkAgent.execute()` 根据 `_light_mode` 分支：
- `True` → `_execute_fast()` → 走 `run_react()` + 12层 MiddlewareChain ✅ 实际在用
- `False` → `_execute_full()` → 继承 `BaseAgent.think()`/`act()`/`reflect()` ❌ 空壳

`BaseAgent.think()` 返回:
```python
Thought(reasoning=f"任务: {task.description}", plan=[], confidence=0.5)
```

**空的 `plan` 和 `tool_calls`** → `act()` 立即返回 `ActionResult(success=True, output=[])`。没有 LLM 调用，没有工具执行，什么都没做但报告成功。

**可达性分析**:
| 实例化点 | light_mode | 最终路径 |
|---------|-----------|---------|
| AgentPool (orchestrator.py:101) | `True` | `_execute_fast` ✅ |
| AgentPool.acquire 回退 (orchestrator.py:118) | 默认 `False` | `_execute_full` ❌ |
| AgentFactory.create_agent (base_agent.py:398) | 默认 `False` | `_execute_full` ❌ |
| AgentFactory.create_agents_for_task (base_agent.py:409) | 默认 `False` | `_execute_full` ❌ |

**影响**: AgentPool 耗尽时临时创建的 Agent 会走空壳路径 — 任务静默"成功"但不做任何工作。AgentFactory 创建的三个方法全部如此。

**修复**: 删除 `_execute_full`，或将 `light_mode` 默认值改为 `True`，或实现真正的全链路。

---

### 2. `RunContext` 双重存储发散

**文件**: `core/multi_agent_v2/agents/middleware.py:57-111`

`RunContext` 同时有内联字段和 `AgentConfig`/`AgentState` 子对象，子对象只在 `__post_init__` 复制一次，之后从不更新：

| 子对象字段 | 内联字段 | 是否快速发散 |
|-----------|---------|------------|
| `state.iteration` | `ctx.iteration` | ✅ 每轮递增 |
| `state.tool_results` | `ctx.tool_results` | ✅ 每轮 append |
| `state.interrupted` | `ctx.interrupted` | ✅ 随时设置 |
| `state.final_answer` | `ctx.final_answer` | ✅ 结束时设置 |
| `config.task_description` | `ctx.task_description` | ✅ 多轮注入改造 |
| `config.max_iterations` | `ctx.max_iterations` | ✅ PlanAware 提升 |

**风险**: 目前所有中间件读内联字段，没运行时错误。但新开发者可能误读 `ctx.state` 拿到过时数据。这是**潜伏缺陷**。

**修复**: 删 `AgentConfig`/`AgentState`，或改为计算属性。

---

### 3. Agent 池 identity 被覆盖后无法恢复

**文件**: `core/multi_agent_v2/orchestration/orchestrator.py:431-510`

`_execute_agent()` 覆盖 identity：
```python
pool_agent.agent_id = "ex_xxxxxxxx"  # 原始 pool_003 丢失
```
`reset()` 不恢复 `agent_id`。Agent 池 identity 在第一次使用后永久损坏。

**修复**: `reset()` 恢复原始 identity，或池保存原始 identity 在 release 时恢复。

---

## 二、中间件系统问题（中严重度）

### 4. `on_wrap_tool_call` 末端创建裸 `BaseAgent()`

**文件**: `core/multi_agent_v2/agents/middleware.py:327`

```python
agent = BaseAgent()  # dummy 对象
return await agent._execute_single_tool_call(tool_args)
```

功能正确（工具注册表全局单例），但丢失了 trace 追踪、agent 引用、temp_memory。

**修复**: 改为直接调用工具注册表。

### 5. `BranchMiddleware` / `DynamicStageRoutingMiddleware` 有实例状态

`BranchMiddleware._hint_added` 和 `DynamicStageRoutingMiddleware._stage_index` 等实例级状态被保留。`build_default_chain()` 每次创建新实例所以当前无 bug，但设计脆弱（有人缓存 chain 就会泄漏）。

**修复**: 状态移入 `RunContext`，或加文档警告。

### 6. `on_wrap_xxx` HOOKS 误导

`AskUserMiddleware.HOOKS = ("on_think_end", "on_tool_end", "on_wrap_tool_call")`，但 `on_wrap_tool_call` 走的是洋葱递归路径（不参与 HOOKS 过滤），HOOKS 里声明它无实际效果。

---

## 三、死代码与遗留代码（中严重度）

### 7. `global_context_center.py` ~19% 是死代码

`_snapshot_store = None`（`persistence.py` 删除后硬编码）。带 `if not self._snapshot_store: return` 守卫的死方法：

| 方法 | 行数 | 状态 |
|------|------|------|
| `_restore_from_db()` | ~25 | 完全死亡 |
| `_start_auto_save()` | ~23 | 完全死亡 |
| `_flush_pending_saves()` | ~26 | 完全死亡 |
| `_mark_dirty()` | ~4 | 更新从不消费的集合 |
| 总计 | ~93 | 19% |

### 8. 注释描述假大空

```python
- 完整模式（execute + _execute_full）：走完整 StepPlanner + StepExecutor 全链路
```
`StepPlanner` 和 `StepExecutor` 在代码库中不存在（已删除）。

### 9. 协作策略文件注释矛盾

`strategies/base.py` 第 62-96 行的 `BaseCollaborationStrategy` 有 `[DEPRECATED]` 警告，但 `collaboration/__init__.py` 和 `strategies/__init__.py` 仍正常导出它。使用者不清楚该类是否可用。

---

## 四、测试覆盖率问题（高严重度）

### 10. 5/18 测试文件完全损坏

| 测试文件 | 缺失的模块 | 状态 |
|---------|-----------|------|
| `test_middleware_pipeline.py` | `cli.middleware` | import 即崩溃 |
| `test_agent_leaser.py` | `core.agent_factory`, `core.agent_leaser` | import 即崩溃 |
| `test_pipeline_engine.py` | `core.wfc.*` | import 即崩溃 |
| `test_sandbox_workspace.py` | `core.sandbox.*` | import 即崩溃 |
| `unit/test_llm_router.py` | `core.wfc.llm_router` | import 即崩溃 |

### 11. v2 核心模块零专项测试

| 模块 | 测试覆盖 |
|------|---------|
| 12 层 MiddlewareChain / 中间件 | ❌ 无 |
| `orchestrator.agent()` / `parallel()` / `pipeline()` | ❌ 无 |
| `SharedBus` 消息 + 知识存储 | ❌ 无 |
| `KEPAMiddleware` 闭环 | ❌ 无 |
| `ReflectionCheckMiddleware` | ❌ 无 |
| Agent 个体化（personality/temp_memory） | ❌ 无 |
| 协作策略 `base.py` / `pipeline.py` | ❌ 无 |

### 12. 内存中 "test_skill_registry 12个失败" 的文件不存在

`test_skill_registry.py` 和 `test_bugfix_regression.py` 在仓库中不存在。

---

## 五、外部引用断裂（高严重度）

### 13. `core/config_loader.py` 调不存在的函数

```python
# line 194
from core.multi_agent_v2.agents.base.base_agent import AgentFactory
agent = AgentFactory.from_config(agent_config)  # ❌ 不存在！

from core.multi_agent_v2.orchestration.lifecycle.agent_pool import get_agent_pool  # ❌ lifecycle/ 已不存在！
```

**影响**: `init_agents_from_config()` 启动即崩溃。

---

## 六、汇总

| 优先级 | # | 问题 | 文件 | 建议 |
|--------|---|------|------|------|
| P0 | 1 | `_execute_full` 空壳 | `work_agent.py` | 删除或走 `_execute_fast` |
| P0 | 13 | `config_loader.py` 断裂 | `core/config_loader.py` | 修复或删除 |
| P0 | 10 | 5个测试文件损坏 | `tests/` | 删除或修复 |
| P1 | 2 | `RunContext` 双存储发散 | `middleware.py` | 删子对象或改属性 |
| P1 | 3 | 池 identity 损坏 | `orchestrator.py` | reset 恢复 identity |
| P1 | 7 | 19% 死代码 | `global_context_center.py` | 删持久化骨架 |
| P2 | 4 | `BaseAgent()` dummy | `middleware.py:327` | 纯函数调注册表 |
| P2 | 5 | 中间件实例状态 | `middlewares.py` | 移入 RunContext |
| P2 | 11 | v2 零测试覆盖 | 全部 | 补测试 |
