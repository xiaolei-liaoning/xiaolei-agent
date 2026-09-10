# AGENTS.md 历史会话记录（归档 2026-09-10）

> 具体历史修改过程 (KOF 修复/ReAct 11 bug/Postconditions 等) 移到这里来, 不占 AGENTS.md 主页

### Session 4: Root Cause — 完成契约 (PlanStep.postconditions)
- 根因分析: 5 个系统性问题 (无完成契约、输出验证位置错、等价级联、无循环不变式、中间件无类型安全)
- 修复: PlanStep 增加 `postconditions: List[str]` 字段
  - "file_exists:/path" — 标记 done 前验证文件在磁盘上存在
  - "tool_called:name" — 标记 done 前验证工具已成功调用
- `_infer_postconditions()`: 从 plan 步骤的 tool_names + task_description 自动推导
- `_verify_step_completion()`: 在 update_step_status 的每个 `status = "done"` 点前调用
- 替代了 swap guard 中 `_ever_written` 的逻辑，postconditions 提供更精确的验证
- 验证: 0 回归（15 pre-existing failures, 336 passed, 6 skipped）

### In Progress
- 4 MCP servers (arbor, codegraph, evermem_search, memsearch) disconnected in desktop UI → likely Electron $PATH issue

### Session 5: Root Cause — Python 3.14 `hasattr` 在 dataclass 动态属性上失效
- **根因分析**: `RunContext` 是 `@dataclass`，`task_progress` 是动态赋值的属性。Python 3.14.5 上 `hasattr(ctx, 'task_progress')` 在 while 循环第二轮后始终返回 `False`，导致 `TaskProgress.update()` 只在 round=1 执行。
- **修复**: 两处 `hasattr(ctx, 'task_progress')` 替换为 `getattr(ctx, 'task_progress', None) is not None`：
  - `react_core.py:1169` — while 循环内的主调度
  - `plan_manager.py:403` — `update_step_status` 调用路径
- **验证**: `getattr` 修复后所有 6 轮都正确调用 `TaskProgress.update()`，`_match_steps` 每轮正常执行
- **剩余问题**: Plan 仍可能卡在特定步骤（如 step 要求 `codegraph_explore` 但 `allowed_tools` 不含它）— 这是计划生成质量问题，非 TaskProgress 可用性问题

### Session 6: 工具策略重构 — 参考 OpenCode 全量暴露 + Skill 系统
- **OpenCode 设计分析**: OpenCode 不硬过滤工具，所有 built-in + MCP 全量暴露给 LLM，精度靠系统提示词引导 + LLM 推理，安全靠运行时权限系统 (deny/allow/ask)。
- **allowed_tools → None**: `run_react()` 默认 `allowed_tools=None`（已有），不传即全量暴露。`get_tools_for_task()` 在 `allowed=None` 时不过滤。之前测试卡住是因为手动传了 `allowed_tools=['write_file','execute_shell','read_file']` 硬限制。
  - 对比：不传 allowed_tools → 24 工具 → plan 2步 5轮完成；传 3 工具 → plan 6步 6轮卡死
- **MCP 连接**: 确认 3/7 服务器连接正常 (codegraph, deepwiki, context7)，12 个 MCP 工具 + 12 内置工具 = 24 工具全暴露
- **Skill 系统**: 照搬 OpenCode 模式，新增三个组件：
  1. `skill_loader.py` — 从 `~/.opencode/skills/` + `~/.agents/skills/` 扫描 SKILL.md（34 个技能），解析 YAML frontmatter
  2. `skill` 工具 — 注册到 ToolRegistry，按名加载 skill 内容返回给 LLM
  3. System prompt 注入 — `<available_skills>` 列表（OpenCode 格式），LLM 按需调用 skill 工具

### Key Decisions
- **Session 6**
  - `allowed_tools` 不再硬过滤，改为 None（全量暴露）。stuck≥6 动态限制机制保留
  - Skill 系统 = OpenCode 模式：system prompt 列出 + `skill` 工具按需加载
  - MCP 工具已天然绕过白名单（`get_tools_for_task` 的 MCP 放行逻辑）

### Relevant Files
- `core/multi_agent_v2/agents/react_core.py` — `hasattr`→`getattr` fix, skill system prompt injection (line ~378)
- `core/multi_agent_v2/agents/plan_manager.py` — `hasattr`→`getattr` fix
- `core/multi_agent_v2/agents/task_progress.py` — `_match_steps`, capability matching
- `core/multi_agent_v2/tools/tool_registry.py` — `_handle_skill` handler, skill tool definition
- `core/multi_agent_v2/skills/skill_loader.py` — **NEW** skill discovery + loading
