# 上下文压缩系统：替换 BFS，实现 Claude Code 风格 3 层压缩

## TL;DR

> **Quick Summary:** 用 Claude Code 的 3 层压缩架构替换 BFS 上下文管理，实现统一的上下文压缩系统，支持 Web/CLI/V1/V2 全路径。
>
> **Deliverables:**
> - `core/memory/context_compactor.py` — 统一压缩入口
> - `core/memory/micro_compact.py` — Tier 1 确定性裁剪
> - `core/memory/summary_compact.py` — Tier 2 LLM 摘要
> - `core/memory/token_counter.py` — 统一 token 计数
> - `core/memory/context_rebuilder.py` — 压缩后重建
> - 更新 `api/routes/chat.py` 使用新压缩系统
> - 更新 `core/agent_system.py` 集成压缩
> - 测试验证
>
> **Estimated Effort:** Medium
> **Parallel Execution:** YES - 3 waves
> **Critical Path:** token_counter → micro_compact → summary_compact → context_compactor → integration

---

## Context

### Original Request
用户要求用 Claude Code 的 3 层压缩架构替换 BFS 上下文管理。

### Research Findings

**Claude Code 3 层压缩架构：**

| 层 | 机制 | 时机 | 成本 |
|---|------|------|------|
| **Tier 1: Microcompact** | 裁剪旧工具输出，保留最近5轮 | 每次API调用前 | 零（纯确定性） |
| **Tier 2: Autocompact** | 服务器端 token 阈值处理 | 接近上限时 | 低 |
| **Tier 3: Force compact** | LLM 9段式结构化摘要 | 80%+ token 时 | 高（最后手段） |

**核心设计原则：**
- Tier 1 是确定性的，不调用 LLM，只裁剪工具输出
- Tier 3 生成 9 段式摘要：意图、技术概念、修改文件、错误修复、用户消息、待办任务、当前工作
- 压缩后重建：摘要 + 最近5个文件 + 技能重注入 + CLAUDE.md 恢复
- **缓存感知**：用 `cache_edits` 而非修改消息，保护 prompt cache

**当前代码库问题：**
1. BFS 本质是数据库 dump，无压缩
2. STM 有 4 层压缩但只服务 CLI/V1
3. ContextBudgetManager 只服务 V2
4. Web 路径实际上下文来自 memory_middleware（向量记忆），绕过了所有压缩系统
5. 3 个独立系统共存，无统一管理

### 需求
- 统一上下文管理，替换分散的 BFS 逻辑
- 实现 Claude Code 风格 3 层压缩
- 支持 Web/CLI/V1/V2 全路径
- 保持向后兼容

---

## Work Objectives

### Core Objective
建立统一的上下文压缩系统，实现 Claude Code 风格的 3 层压缩架构，替换 BFS 上下文管理。

### Concrete Deliverables
- `core/memory/context_compactor.py` — 统一压缩入口
- `core/memory/micro_compact.py` — Tier 1 确定性裁剪
- `core/memory/summary_compact.py` — Tier 2 LLM 摘要
- `core/memory/token_counter.py` — 统一 token 计数
- `core/memory/context_rebuilder.py` — 压缩后重建
- 更新 `api/routes/chat.py` 使用新压缩系统
- 更新 `core/agent_system.py` 集成压缩
- 测试验证

### Definition of Done
- [ ] `python -c "from core.memory.context_compactor import ContextCompactor; print('OK')"` passes
- [ ] `python -c "from core.memory.micro_compact import MicroCompact; print('OK')"` passes
- [ ] `python -c "from core.memory.summary_compact import SummaryCompact; print('OK')"` passes
- [ ] Web 路径使用新压缩系统替代 BFS
- [ ] V1 Leader/Workers 使用新压缩系统

### Must Have
- 统一 token 计数（支持中英文）
- Tier 1 确定性裁剪（无 LLM 调用）
- Tier 2 LLM 摘要（9 段式结构化）
- 压缩后重建（摘要 + 最近文件 + 技能重注入）
- Web/CLI/V1/V2 全路径支持

### Must NOT Have（Guardrails）
- 不修改 memory_middleware.py（已验证工作正常）
- 不修改 user_profile.py（已验证工作正常）
- 不修改 fact_extractor.py（已验证工作正常）
- 不引入新的外部依赖（使用标准库 + 已有依赖）
- 不破坏现有测试

---

## Verification Strategy

### Test Decision
- **Infrastructure exists:** NO（无 pytest）
- **Automated tests:** None（ponytail: YAGNI，最小实现）
- **Framework:** none
- **验证方式:** 手动验证 + 脚本测试

### QA Policy
验证通过条件：
1. 导入测试通过
2. Web 路径使用新压缩系统
3. V1 Leader/Workers 使用新压缩系统
4. 压缩触发时生成 9 段式摘要
5. 压缩后上下文正确重建

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1（可并行，基础层）:
├── Task 1: token_counter.py（统一 token 计数）
├── Task 2: micro_compact.py（Tier 1 确定性裁剪）
└── Task 3: summary_compact.py（Tier 2 LLM 摘要）

Wave 2（依赖 Wave 1）:
├── Task 4: context_rebuilder.py（压缩后重建）
└── Task 5: context_compactor.py（统一压缩入口）

Wave 3（依赖 Wave 2）:
├── Task 6: 集成到 api/routes/chat.py
├── Task 7: 集成到 core/agent_system.py
└── Task 8: 测试验证
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1. token_counter.py | — | 2, 3, 4, 5 |
| 2. micro_compact.py | 1 | 5 |
| 3. summary_compact.py | 1 | 5 |
| 4. context_rebuilder.py | 1 | 5 |
| 5. context_compactor.py | 2, 3, 4 | 6, 7 |
| 6. 集成 chat.py | 5 | 8 |
| 7. 集成 agent_system.py | 5 | 8 |
| 8. 测试验证 | 6, 7 | — |

### Agent Dispatch Summary

- **Wave 1:** 3 tasks → `general`
- **Wave 2:** 2 tasks → `general`
- **Wave 3:** 3 tasks → `general`

---

## TODOs

- [ ] 1. 统一 Token 计数器

  **What to do:**
  - 创建 `core/memory/token_counter.py`
  - 实现 `estimate_tokens(text: str) -> int` 函数
  - 支持中英文混合文本（CJK ~1.5 字符/token，ASCII ~4 字符/token）
  - 添加 `count_messages_tokens(messages: list) -> int` 函数
  - 添加 `get_context_usage(messages: list, model_limit: int) -> float` 函数

  **Must NOT do:**
  - 不引入 tiktoken 等外部依赖
  - 不实现复杂的 tokenization 算法

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: 纯 Python 实现，无特殊领域知识需求

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 1 (with Tasks 2, 3)
  - **Blocks:** Tasks 2, 3, 4, 5
  - **Blocked By:** None

  **References:**
  - `core/memory/short_term_memory.py:51-58` — 现有 token 估算实现（CJK-aware）
  - `core/multi_agent_v2/agents/context_budget.py:38-42` — 另一个 token 估算实现
  - Pattern: 使用字符数 / 3.5 作为简单估算

  **Acceptance Criteria:**
  - [ ] `python -c "from core.memory.token_counter import estimate_tokens; print(estimate_tokens('你好世界 hello'))"` passes
  - [ ] 中文文本估算准确（~1.5 字符/token）
  - [ ] 英文文本估算准确（~4 字符/token）

  **QA Scenarios:**

  Scenario: 基本 token 估算
    Tool: Bash
    Steps:
      1. 运行 `python -c "from core.memory.token_counter import estimate_tokens; print(estimate_tokens('你好世界 hello'))"`
      2. 验证输出为合理的 token 数（约 5-7）
    Expected Result: 输出为合理的 token 数
    Evidence: .opencode/evidence/task-1-token-estimate.txt

  Scenario: 空文本处理
    Tool: Bash
    Steps:
      1. 运行 `python -c "from core.memory.token_counter import estimate_tokens; print(estimate_tokens(''))"`
      2. 验证输出为 0
    Expected Result: 输出为 0
    Evidence: .opencode/evidence/task-1-token-empty.txt

  **Commit:** YES
  - Message: `feat(memory): add unified token counter`
  - Files: `core/memory/token_counter.py`
  - Pre-commit: `python -c "from core.memory.token_counter import estimate_tokens; print('OK')"`

---

- [ ] 2. Tier 1 确定性裁剪（Microcompact）

  **What to do:**
  - 创建 `core/memory/micro_compact.py`
  - 实现 `MicroCompact` 类
  - `compact(messages: list, max_tool_results: int = 5) -> list` 方法
  - 保留最近 N 个工具结果，旧的替换为 `[旧工具结果已清理]`
  - 保留系统提示词和最近 3 轮对话完整
  - 无 LLM 调用，纯确定性逻辑

  **Must NOT do:**
  - 不调用 LLM
  - 不修改系统提示词
  - 不删除用户消息

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: 纯 Python 逻辑，无特殊领域知识需求

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 1 (with Tasks 1, 3)
  - **Blocks:** Task 5
  - **Blocked By:** Task 1

  **References:**
  - `core/memory/short_term_memory.py:472-510` — 现有 micro-compact 实现
  - Claude Code Tier 1: 保留最近 5 个工具结果，旧的替换为 `[Old tool result content cleared]`
  - Pattern: 遍历消息列表，计数工具结果，超过阈值时替换

  **Acceptance Criteria:**
  - [ ] `python -c "from core.memory.micro_compact import MicroCompact; print('OK')"` passes
  - [ ] 工具结果裁剪正确（保留最近 5 个）
  - [ ] 系统提示词保持完整
  - [ ] 最近 3 轮对话保持完整

  **QA Scenarios:**

  Scenario: 工具结果裁剪
    Tool: Bash
    Steps:
      1. 创建测试脚本，生成 10 个工具结果消息
      2. 调用 `MicroCompact().compact(messages)`
      3. 验证只有最近 5 个工具结果保留完整
      4. 验证旧工具结果被替换为 `[旧工具结果已清理]`
    Expected Result: 旧工具结果被正确裁剪
    Evidence: .opencode/evidence/task-2-micro-compact.txt

  Scenario: 系统提示词保护
    Tool: Bash
    Steps:
      1. 创建包含系统提示词的消息列表
      2. 调用 `MicroCompact().compact(messages)`
      3. 验证系统提示词保持完整
    Expected Result: 系统提示词未被修改
    Evidence: .opencode/evidence/task-2-system-prompt保护.txt

  **Commit:** YES (with other Wave 1 tasks)
  - Message: `feat(memory): add microcompact tier 1 deterministic trimming`
  - Files: `core/memory/micro_compact.py`
  - Pre-commit: `python -c "from core.memory.micro_compact import MicroCompact; print('OK')"`

---

- [ ] 3. Tier 2 LLM 摘要（Summary Compact）

  **What to do:**
  - 创建 `core/memory/summary_compact.py`
  - 实现 `SummaryCompact` 类
  - `compact(messages: list, token_budget: int = 2000) -> list` 方法
  - 生成 9 段式结构化摘要：
    1. 用户意图
    2. 技术概念
    3. 修改文件
    4. 错误修复
    5. 用户消息
    6. 待办任务
    7. 当前工作
    8. 关键决策
    9. 上下文摘要
  - 使用 `llm_backend.call_llm()` 调用 LLM
  - 添加回退机制（LLM 失败时使用模板摘要）

  **Must NOT do:**
  - 不修改系统提示词
  - 不删除最近 3 轮对话
  - 不引入新的 LLM 调用方式

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: LLM 调用逻辑简单，无需特殊领域知识

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 1 (with Tasks 1, 2)
  - **Blocks:** Task 5
  - **Blocked By:** Task 1

  **References:**
  - `core/memory/short_term_memory.py:543-591` — 现有 LLM 压缩实现
  - `core/multi_agent_v2/agents/context_budget.py:274-323` — V2 LLM 压缩实现
  - Claude Code 9 段式摘要：意图、技术概念、修改文件、错误修复、用户消息、待办任务、当前工作

  **Acceptance Criteria:**
  - [ ] `python -c "from core.memory.summary_compact import SummaryCompact; print('OK')"` passes
  - [ ] 生成 9 段式结构化摘要
  - [ ] LLM 失败时回退到模板摘要
  - [ ] 摘要包含关键信息（意图、文件、错误、待办）

  **QA Scenarios:**

  Scenario: LLM 摘要生成
    Tool: Bash
    Steps:
      1. 创建包含多轮对话的消息列表
      2. 调用 `SummaryCompact().compact(messages)`
      3. 验证输出包含 9 个段落
      4. 验证摘要包含关键信息
    Expected Result: 生成结构化摘要
    Evidence: .opencode/evidence/task-3-summary-compact.txt

  Scenario: LLM 失败回退
    Tool: Bash
    Steps:
      1. 模拟 LLM 调用失败
      2. 调用 `SummaryCompact().compact(messages)`
      3. 验证回退到模板摘要
    Expected Result: 使用模板摘要
    Evidence: .opencode/evidence/task-3-fallback.txt

  **Commit:** YES (with other Wave 1 tasks)
  - Message: `feat(memory): add summary compact tier 2 LLM summarization`
  - Files: `core/memory/summary_compact.py`
  - Pre-commit: `python -c "from core.memory.summary_compact import SummaryCompact; print('OK')"`

---

- [ ] 4. 压缩后重建（Context Rebuilder）

  **What to do:**
  - 创建 `core/memory/context_rebuilder.py`
  - 实现 `ContextRebuilder` 类
  - `rebuild(summary: str, messages: list, max_recent_files: int = 5) -> list` 方法
  - 重建逻辑：
    1. 添加压缩边界标记（包含压缩前元数据）
    2. 添加格式化摘要
    3. 添加最近 5 个文件（如果存在）
    4. 添加工具定义重声明
    5. 添加系统提示词恢复
  - 支持 `continuation_message` 参数（自主代理继续消息）

  **Must NOT do:**
  - 不修改摘要内容
  - 不删除关键信息
  - 不引入新的文件读取逻辑

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: 纯 Python 逻辑，无特殊领域知识需求

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 2 (with Task 5)
  - **Blocks:** Task 5
  - **Blocked By:** Task 1

  **References:**
  - Claude Code 压缩后重建：边界标记 + 摘要 + 最近文件 + 技能重注入 + CLAUDE.md 恢复
  - Pattern: 构建新消息列表，依次添加各组件

  **Acceptance Criteria:**
  - [ ] `python -c "from core.memory.context_rebuilder import ContextRebuilder; print('OK')"` passes
  - [ ] 重建后消息包含压缩边界标记
  - [ ] 重建后消息包含格式化摘要
  - [ ] 重建后消息包含系统提示词

  **QA Scenarios:**

  Scenario: 基本重建
    Tool: Bash
    Steps:
      1. 创建摘要和原始消息
      2. 调用 `ContextRebuilder().rebuild(summary, messages)`
      3. 验证输出包含边界标记
      4. 验证输出包含摘要
    Expected Result: 重建后消息结构正确
    Evidence: .opencode/evidence/task-4-rebuild.txt

  Scenario: 自主代理继续消息
    Tool: Bash
    Steps:
      1. 创建摘要和原始消息
      2. 调用 `ContextRebuilder().rebuild(summary, messages, continuation_message="继续工作")`
      3. 验证输出包含继续消息
    Expected Result: 包含继续消息
    Evidence: .opencode/evidence/task-4-continuation.txt

  **Commit:** YES (with other Wave 2 tasks)
  - Message: `feat(memory): add context rebuilder for post-compaction reconstruction`
  - Files: `core/memory/context_rebuilder.py`
  - Pre-commit: `python -c "from core.memory.context_rebuilder import ContextRebuilder; print('OK')"`

---

- [ ] 5. 统一压缩入口（Context Compactor）

  **What to do:**
  - 创建 `core/memory/context_compactor.py`
  - 实现 `ContextCompactor` 类
  - `__init__(self, model_limit: int = 8000)` 方法
  - `compact(messages: list, force: bool = False) -> list` 方法
  - 3 层压缩逻辑：
    1. **Tier 1: Microcompact** — 每次调用都执行（确定性）
    2. **Tier 2: Autocompact** — token 使用率 > 70% 时触发
    3. **Tier 3: Force compact** — token 使用率 > 85% 时触发（强制 LLM 摘要）
  - `get_compaction_stats() -> dict` 方法（返回压缩统计）
  - 使用 `token_counter` 统一计数
  - 使用 `micro_compact` 执行 Tier 1
  - 使用 `summary_compact` 执行 Tier 2/3
  - 使用 `context_rebuilder` 重建上下文

  **Must NOT do:**
  - 不修改已有压缩逻辑（STM、ContextBudgetManager）
  - 不引入新的压缩策略
  - 不破坏现有测试

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: 组合模式，无特殊领域知识需求

  **Parallelization:**
  - **Can Run In Parallel:** NO
  - **Parallel Group:** Wave 2 (sequential after Tasks 2, 3, 4)
  - **Blocks:** Tasks 6, 7
  - **Blocked By:** Tasks 2, 3, 4

  **References:**
  - `core/memory/short_term_memory.py` — 现有 4 层压缩实现
  - `core/multi_agent_v2/agents/context_budget.py` — V2 上下文预算管理
  - Claude Code 3 层压缩架构

  **Acceptance Criteria:**
  - [ ] `python -c "from core.memory.context_compactor import ContextCompactor; print('OK')"` passes
  - [ ] Tier 1 每次都执行
  - [ ] Tier 2 在 70% token 时触发
  - [ ] Tier 3 在 85% token 时触发
  - [ ] 压缩统计正确

  **QA Scenarios:**

  Scenario: Tier 1 始终执行
    Tool: Bash
    Steps:
      1. 创建小消息列表（< 50% token）
      2. 调用 `ContextCompactor().compact(messages)`
      3. 验证工具结果被裁剪
    Expected Result: Tier 1 始终执行
    Evidence: .opencode/evidence/task-5-tier1-always.txt

  Scenario: Tier 2 触发
    Tool: Bash
    Steps:
      1. 创建大消息列表（> 70% token）
      2. 调用 `ContextCompactor().compact(messages)`
      3. 验证生成 LLM 摘要
    Expected Result: Tier 2 触发
    Evidence: .opencode/evidence/task-5-tier2-trigger.txt

  Scenario: Tier 3 强制触发
    Tool: Bash
    Steps:
      1. 创建超大消息列表（> 85% token）
      2. 调用 `ContextCompactor().compact(messages, force=True)`
      3. 验证强制生成 LLM 摘要
    Expected Result: Tier 3 强制触发
    Evidence: .opencode/evidence/task-5-tier3-force.txt

  **Commit:** YES
  - Message: `feat(memory): add unified context compactor with 3-tier compression`
  - Files: `core/memory/context_compactor.py`
  - Pre-commit: `python -c "from core.memory.context_compactor import ContextCompactor; print('OK')"`

---

- [ ] 6. 集成到 Web 路径（api/routes/chat.py）

  **What to do:**
  - 修改 `api/routes/chat.py`
  - 导入 `ContextCompactor`
  - 在 `_handle_with_multi_agent()` 中集成压缩：
    1. 从 MySQL 获取历史消息（现有 `_get_bfs_context()` 逻辑）
    2. 调用 `ContextCompactor().compact(messages)` 执行压缩
    3. 将压缩后上下文传递给 V1 Leader
  - 保留 `bfs.add_node()` 写入逻辑（用于持久化）
  - 替换 `_get_bfs_context()` 的读取逻辑

  **Must NOT do:**
  - 不删除 `bfs.add_node()` 写入逻辑
  - 不修改 memory_middleware 集成
  - 不破坏现有测试

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: 集成逻辑简单，无需特殊领域知识

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 3 (with Tasks 7, 8)
  - **Blocks:** Task 8
  - **Blocked By:** Task 5

  **References:**
  - `api/routes/chat.py:238-260` — 现有 `_get_bfs_context()` 实现
  - `api/routes/chat.py:295` — `_handle_with_multi_agent()` 入口
  - `api/routes/chat.py:364-368` — memory_middleware 集成

  **Acceptance Criteria:**
  - [ ] Web 路径使用新压缩系统
  - [ ] 压缩后上下文正确传递给 V1 Leader
  - [ ] `bfs.add_node()` 写入逻辑保留
  - [ ] memory_middleware 集成保留

  **QA Scenarios:**

  Scenario: Web 路径压缩
    Tool: Bash
    Steps:
      1. 启动服务器 `python main.py`
      2. 发送多轮对话请求
      3. 验证日志显示压缩触发
      4. 验证响应正常
    Expected Result: 压缩正常触发，响应正常
    Evidence: .opencode/evidence/task-6-web-compression.txt

  Scenario: 向后兼容
    Tool: Bash
    Steps:
      1. 启动服务器 `python main.py`
      2. 发送单轮对话请求
      3. 验证响应正常（无压缩触发）
    Expected Result: 单轮对话正常工作
    Evidence: .opencode/evidence/task-6-backward兼容.txt

  **Commit:** YES
  - Message: `feat(api): integrate context compactor into Web path`
  - Files: `api/routes/chat.py`
  - Pre-commit: `python -c "from api.routes.chat import router; print('OK')"`

---

- [ ] 7. 集成到 V1 代理（core/agent_system.py）

  **What to do:**
  - 修改 `core/agent_system.py`
  - 导入 `ContextCompactor`
  - 在 `LLMAgent._handle_message()` 中集成压缩：
    1. 获取 STM 上下文（现有逻辑）
    2. 调用 `ContextCompactor().compact(messages)` 执行压缩
    3. 将压缩后上下文传递给 LLM
  - 在 V1 Leader `_react_think()` 中集成压缩：
    1. 获取 ReAct 历史（现有逻辑）
    2. 调用 `ContextCompactor().compact(messages)` 执行压缩
    3. 将压缩后上下文传递给 LLM

  **Must NOT do:**
  - 不删除 STM 集成
  - 不修改 memory_middleware 集成
  - 不破坏现有测试

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: 集成逻辑简单，无需特殊领域知识

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 3 (with Tasks 6, 8)
  - **Blocks:** Task 8
  - **Blocked By:** Task 5

  **References:**
  - `core/agent_system.py:401-494` — `LLMAgent._handle_message()` 实现
  - `core/agent_system.py:897-1036` — V1 Leader `_react_think()` 实现
  - `core/agent_system.py:413-424` — STM 上下文获取

  **Acceptance Criteria:**
  - [ ] V1 代理使用新压缩系统
  - [ ] STM 集成保留
  - [ ] memory_middleware 集成保留
  - [ ] 压缩后上下文正确传递给 LLM

  **QA Scenarios:**

  Scenario: V1 代理压缩
    Tool: Bash
    Steps:
      1. 启动服务器 `python main.py`
      2. 发送多轮对话请求（触发 V1 Leader）
      3. 验证日志显示压缩触发
      4. 验证响应正常
    Expected Result: 压缩正常触发，响应正常
    Evidence: .opencode/evidence/task-7-v1-compression.txt

  Scenario: STM 保留
    Tool: Bash
    Steps:
      1. 启动服务器 `python main.py`
      2. 发送多轮对话请求
      3. 验证 STM 上下文仍被使用
    Expected Result: STM 集成保留
    Evidence: .opencode/evidence/task-7-stm保留.txt

  **Commit:** YES
  - Message: `feat(agent): integrate context compactor into V1 agents`
  - Files: `core/agent_system.py`
  - Pre-commit: `python -c "from core.agent_system import LLMAgent; print('OK')"`

---

- [ ] 8. 测试验证

  **What to do:**
  - 创建 `tests/test_context_compactor.py`
  - 测试 token_counter：
    - 中文 token 估算
    - 英文 token 估算
    - 混合文本 token 估算
  - 测试 micro_compact：
    - 工具结果裁剪
    - 系统提示词保护
    - 最近对话保护
  - 测试 summary_compact：
    - 9 段式摘要生成
    - LLM 失败回退
  - 测试 context_rebuilder：
    - 基本重建
    - 自主代理继续消息
  - 测试 context_compactor：
    - Tier 1 始终执行
    - Tier 2 触发
    - Tier 3 强制触发
  - 集成测试：
    - Web 路径压缩
    - V1 代理压缩

  **Must NOT do:**
  - 不引入 pytest 等测试框架（使用简单脚本）
  - 不 mock LLM 调用（使用真实调用验证）
  - 不破坏现有测试

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: 测试逻辑简单，无需特殊领域知识

  **Parallelization:**
  - **Can Run In Parallel:** NO
  - **Parallel Group:** Wave 3 (sequential after Tasks 6, 7)
  - **Blocks:** None
  - **Blocked By:** Tasks 6, 7

  **References:**
  - `tests/` — 现有测试目录
  - `core/memory/short_term_memory.py` — 现有压缩实现（参考测试模式）

  **Acceptance Criteria:**
  - [ ] 所有单元测试通过
  - [ ] 集成测试通过
  - [ ] Web 路径压缩验证通过
  - [ ] V1 代理压缩验证通过

  **QA Scenarios:**

  Scenario: 单元测试
    Tool: Bash
    Steps:
      1. 运行 `python tests/test_context_compactor.py`
      2. 验证所有测试通过
    Expected Result: 所有测试通过
    Evidence: .opencode/evidence/task-8-unit-tests.txt

  Scenario: 集成测试
    Tool: Bash
    Steps:
      1. 启动服务器 `python main.py`
      2. 发送多轮对话请求
      3. 验证压缩正常触发
      4. 验证响应正常
    Expected Result: 集成测试通过
    Evidence: .opencode/evidence/task-8-integration-tests.txt

  **Commit:** YES
  - Message: `test(memory): add context compactor tests`
  - Files: `tests/test_context_compactor.py`
  - Pre-commit: `python tests/test_context_compactor.py`

---

## Final Verification Wave

- [ ] F1. 导入验证

  **What to do:**
  - 运行所有模块导入测试
  - 验证无导入错误
  - 验证依赖关系正确

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: 简单验证，无需特殊领域知识

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Final Verification

  **References:**
  - 所有新建模块

  **QA Scenarios:**

  Scenario: 模块导入
    Tool: Bash
    Steps:
      1. 运行 `python -c "from core.memory.token_counter import estimate_tokens; print('OK')"`
      2. 运行 `python -c "from core.memory.micro_compact import MicroCompact; print('OK')"`
      3. 运行 `python -c "from core.memory.summary_compact import SummaryCompact; print('OK')"`
      4. 运行 `python -c "from core.memory.context_rebuilder import ContextRebuilder; print('OK')"`
      5. 运行 `python -c "from core.memory.context_compactor import ContextCompactor; print('OK')"`
    Expected Result: 所有导入成功
    Evidence: .opencode/evidence/f1-imports.txt

- [ ] F2. 端到端验证

  **What to do:**
  - 启动服务器
  - 发送多轮对话请求
  - 验证压缩正常触发
  - 验证响应正常
  - 验证记忆系统正常工作

  **Recommended Agent Profile:**
  - **Category:** `general`
    - Reason: 端到端验证，无需特殊领域知识

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Final Verification

  **References:**
  - `main.py` — 服务器启动
  - `api/routes/chat.py` — Web 路径

  **QA Scenarios:**

  Scenario: 端到端压缩
    Tool: Bash
    Steps:
      1. 启动服务器 `python main.py`
      2. 发送 5 轮对话请求
      3. 验证日志显示压缩触发
      4. 验证每轮响应正常
      5. 验证记忆系统正常工作（发送"我叫小雷"，然后问"我叫什么"）
    Expected Result: 压缩正常触发，响应正常，记忆正常
    Evidence: .opencode/evidence/f2-e2e.txt

---

## Commit Strategy

- **1:** `feat(memory): add unified token counter` — token_counter.py
- **2:** `feat(memory): add microcompact tier 1 deterministic trimming` — micro_compact.py
- **3:** `feat(memory): add summary compact tier 2 LLM summarization` — summary_compact.py
- **4:** `feat(memory): add context rebuilder for post-compaction reconstruction` — context_rebuilder.py
- **5:** `feat(memory): add unified context compactor with 3-tier compression` — context_compactor.py
- **6:** `feat(api): integrate context compactor into Web path` — api/routes/chat.py
- **7:** `feat(agent): integrate context compactor into V1 agents` — core/agent_system.py
- **8:** `test(memory): add context compactor tests` — tests/test_context_compactor.py

---

## Success Criteria

### Verification Commands
```bash
# 模块导入验证
python -c "from core.memory.token_counter import estimate_tokens; print('OK')"
python -c "from core.memory.micro_compact import MicroCompact; print('OK')"
python -c "from core.memory.summary_compact import SummaryCompact; print('OK')"
python -c "from core.memory.context_rebuilder import ContextRebuilder; print('OK')"
python -c "from core.memory.context_compactor import ContextCompactor; print('OK')"

# 单元测试验证
python tests/test_context_compactor.py

# 端到端验证
python main.py  # 启动服务器
# 发送多轮对话请求，验证压缩触发
```

### Final Checklist
- [ ] 所有模块导入成功
- [ ] 所有单元测试通过
- [ ] Web 路径使用新压缩系统
- [ ] V1 代理使用新压缩系统
- [ ] Tier 1 确定性裁剪工作正常
- [ ] Tier 2 LLM 摘要工作正常
- [ ] Tier 3 强制压缩工作正常
- [ ] 压缩后重建工作正常
- [ ] 记忆系统正常工作
- [ ] 向后兼容性保持
