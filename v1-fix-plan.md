# V1 队长-队员模式修复方案

## 架构图 vs 代码：8 项差异

基于对 `core/agent_system.py`（556 行）和架构图的逐项对照：

| # | 类型 | 问题 | 位置 | 严重程度 |
|---|------|------|------|----------|
| 1 | **BUG** | `_kepa_reflect()` 中 `decision=="continue"` 优先于 `confidence≥0.85`，低置信度也能退出 | line 226 | 🔴 中 |
| 2 | **BUG** | `_execute_batch()` JSON 解析失败时被设为 `is_ok=True`，静默掩盖错误 | lines 438-440 | 🟠 中 |
| 3 | **架构** | `share_memory()` 引入 V2 SharedBus 依赖，违反独立原则 | lines 527-528 | 🟠 高 |
| 4 | **缺失** | `_activate_worker()` 从未在 `supervise_task` 中被调用，休眠 Worker 无法被激活 | line 487 vs 372-378 | 🟡 低 |
| 5 | **质量** | `_analyze_results()` 截断结果到 200 字符，分析信息不足 | line 462 | 🟡 低 |
| 6 | **韧性** | `_llm_json()` JSON 解析失败后直接返回 `{}`，无重试 | line 92 | 🟡 低 |
| 7 | **健壮** | `_decompose_task()` 无子任务格式校验 | lines 404-409 | 🟢 建议 |
| 8 | **一致** | `_execute_batch()` 异常结果 schema 与正常结果不统一 | lines 449-454 | 🟢 建议 |

## 代码 vs 架构图：逐元素确认

| 架构图元素 | 代码中 | 状态 |
|-----------|--------|------|
| V1LeaderPool | ✅ `class V1LeaderPool` | ✅ 完好 |
| `create_team(3,5) → (Leader, LLMList)` | ✅ line 502 | ✅ 完好 |
| `share_memory()` 发布摘要 | ✅ line 524 | ⚠️ V2 依赖 |
| `discard()` 删除 agent | ✅ line 546 | ✅ 完好 |
| LeaderAgent(LLMAgent) | ✅ line 309 | ✅ 完好 |
| `supervise_task()` 主循环 | ✅ line 318 | ✅ 完好 |
| `_decompose_task()` LLM 分解 | ✅ line 390 | ✅ 完好 |
| `_assign()` round-robin | ✅ line 411 | ✅ 完好 |
| `_execute_batch()` asyncio.gather | ✅ line 423 | ⚠️ JSON 解析 bug |
| `_analyze_results()` → decision | ✅ line 457 | ⚠️ 200 字符截断 |
| `_activate_worker()` 唤醒 | ✅ line 487 （定义） | ❌ 从未被调用 |
| retry/reassign 循环 | ✅ lines 367-378 | ✅ 完好 |
| LLMAgent 基类 | ✅ line 153 | ✅ 完好 |
| `_rag_query()` RAG 检索 | ✅ line 169 | ✅ 完好 |
| `_kepa_reflect()` ≥0.85 退出 | ✅ line 204 | ❌ 条件顺序错误 |
| `_ask_user()` 反问 | ✅ line 185 | ✅ 完好 |
| ContextMemory 20 条 | ✅ line 131 | ✅ 完好 |
| `_llm_json()` 模块级函数 | ✅ line 81 | ⚠️ 无重试 |

## 执行计划（多 Agent 并行）

```
阶段 1 并行 ─────────────────────────────────
  Agent A: 修复 bug #1 _kepa_reflect() 退出条件
  Agent B: 修复 bug #2 _execute_batch() JSON错误处理
  Agent C: 修复 bug #3 share_memory() V2依赖 + 激活_activate_worker()
  Agent D: 修复 bug #5-8（截断/重试/校验/异常schema）

阶段 2 并行 ─────────────────────────────────
  Agent E: 创建 V1 测试文件 test_v1_agent.py
  Agent F: 手动验证 + 风险审计
```

## 风险预估

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| `_kepa_reflect` 行为改变 | Worker 判定更严格，可能误判 | 低 | 只改条件顺序，不改语义 |
| `_execute_batch` 错误暴露 | 之前掩饰的错误被暴露 | 中 | 改为 `is_ok=False` + 记录 error，不丢结果 |
| `_activate_worker` 激活 | 多 Worker 场景可能出问题 | 低 | 只在 reassign 路径触发 |
| `share_memory` 删除 | 历史 cross-V2 功能消失 | 低 | V1 本来就不该依赖 V2 |
