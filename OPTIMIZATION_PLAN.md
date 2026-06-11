# v2 架构优化计划 — 对标 DeerFlow

> 基于深度对比分析，分 3 个阶段执行优化

## 核心差距

| 维度 | 当前 v2 | 目标（对标 DeerFlow） |
|------|---------|----------------------|
| System Prompt | 一段硬编码中文 | XML 结构化认知架构（思考/澄清/引用/子代理） |
| 中间件数量 | 4 个 | 8+ 个（循环检测/澄清/Todo/动态上下文） |
| 循环防护 | 仅深度上限 | 双层检测（哈希 + 频率）+ 强制停止 |
| 澄清机制 | 无 | 中断式澄清（等用户确认） |
| 退出保护 | 无 | 未完成任务不让退出 |
| 记忆注入 | 同步 KV | token-budgeted 动态注入 |

---

## 阶段一：P0 核心（影响最大）

### 1. 重构 System Prompt
**文件**: `core/multi_agent_v2/agents/react_core.py`

将硬编码的一段话替换为结构化 XML 提示词：
- `<thinking_style>` — 思考模式（先分析、再行动）
- `<clarification_system>` — 何时必须澄清
- `<tool_usage>` — 工具使用规范
- `<output_style>` — 输出格式
- `<critical_reminders>` — 关键提醒

### 2. 新增 LoopDetectionMiddleware
**文件**: `core/multi_agent_v2/agents/middlewares.py`

双层循环检测：
- **Hash-based**: 相同工具调用组合 hash，3 次警告，5 次强制停止
- **Frequency-based**: 同一工具类型调用 30 次警告，50 次强制停止

---

## 阶段二：P1 保障（提升可靠性）

### 3. 新增 ClarificationMiddleware
**文件**: `core/multi_agent_v2/agents/middlewares.py`

- 拦截 `ask_clarification` 工具调用
- 返回 `HookResult(jump_to="end")` 中断执行
- 格式化用户友好的澄清消息

### 4. 新增 TodoMiddleware
**文件**: `core/multi_agent_v2/agents/middlewares.py`

- 检测是否有未完成的 todo
- 防止 agent 在有未完成任务时退出
- 最多提醒 2 次后允许退出

---

## 阶段三：P2 增强（提升体验）

### 5. 增强 DynamicContext
在 `on_think_start` 中动态注入当前日期 + 工具状态摘要

### 6. 增强 ReflectionMiddleware
将反思结果从简单日志升级为可注入 LLM 的结构化反馈

---

## 执行策略

```
Agent A: Prompt 重构（react_core.py）
Agent B: LoopDetection + Clarification + Todo 中间件（middlewares.py）
Agent C: 主循环集成 + 验证（react_core.py 主循环 + orchestrator.py）
```
