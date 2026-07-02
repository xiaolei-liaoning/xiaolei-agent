# Session Summary

## Goal
- Fix 11 critical ReAct loop bugs in xiaolei agent (empty-run protection, middleware dead code, error handling) and restore all 7 MCP server connections in opencode desktop.

## Constraints & Preferences
- All MCP servers (arbor, codegraph, context7, deepwiki, evermem_search, memsearch, playwright) must connect.

## Progress
### Done
- Fix 1: `chain.on_plan_check(ctx)` called between `on_llm_invoke` and `on_tool_invoke` in `react_core.py` main loop → LoopDetectionMiddleware and ClarificationMiddleware now active.
- Fix 2: `HookMiddleware.on_tool_end()` returns `HookResult(jump_to="retry")` instead of `None` → retry requests consumed.
- Fix 3: Main loop calls `async_check_and_compact()` (async, LLM-capable), falls back to template compaction on exception.
- Fix 4: Final answer heuristic tightened: requires plan completed + >100 chars, or explicit report markers.
- Fix 5: Empty-run retry picks first available tool from `ctx.tool_defs` in priority order.
- Fix 6: `consecutive_idle_rounds` incremented on idle rounds, reset on tool calls; exits at ≥3.
- Fix 7: Post-completion `forced_instructions` loop capped at 3 rounds.
- Fix 8: `write_file` fallback uses base64 encode/decode, replacing fragile `'''` approach.
- Fix 9: `replan_failed()` clears `ctx._step_tool_snapshots`.
- Fix 10: `on_tool_invoke()` skips writing `_validation_error` results to conversation history.
- Fix 11: `update_step_status()` eliminated redundant re-computations.
- Verified via unit tests (16 scenarios) + 2 end-to-end CLI tasks.
- Investigated MCP: all 7 servers defined in `~/.config/opencode/opencode.jsonc` (v1 format, top-level `mcp` key). Desktop sidecar reads global config + plugin-registered MCP servers.
- 3 plugin-loading errors identified: `opencode-antigravity-auth` (ESM dir import), `@zilliz/memsearch-opencode` (TS stripping), `superpowers` (no git in $PATH).
- `.mcp.json` only read by CLI binary, NOT by desktop sidecar.

### Session 2: 项目分析输出截断修复
- Fix A: 移除 fallback 输出 `[:2000]` `[:1000]` 人肉截断
- Fix B: LLM max_tokens 16384→32768（主循环 + fallback + 自动报告）
- Fix C: post-execution 守卫 — write_file 成功即跳出循环，跳过 3 轮空转
- Fix D: `_extract_text_from_json()` — knowledge_context 存纯文本而非 JSON
- Fix E: `_trim_desc()` — fallback 总结 prompt 只取前 500 字，释放 context window
- Fix F: 守卫 final_answer 从 tool_result 提取可读文本（`from_handler`），非 raw JSON
- 新增 3 个测试用例验证 JSON 泄露/截断/纯文本提取
- 77 tests passing

### In Progress
- 4 MCP servers (arbor, codegraph, evermem_search, memsearch) disconnected in desktop UI → likely Electron $PATH issue for binaries, missing script paths.

### Blocked
- Need desktop app sidecar logs to confirm root cause of 4 MCP failures.

## Key Decisions
- Global config is source of truth for MCP (no project-level `opencode.json` in 小雷版agent).
- ReAct fixes are small, targeted patches in-place rather than middleware chain refactor.
- 项目分析 fallback 不应偷懒避开 — 需要保留 fallback 总结 LLM 调用来生成完整摘要，而非用工具确认消息草草了事。

## Relevant Files
- `core/multi_agent_v2/agents/react_core.py` — Fixes 1, 3-7, 10, A-F
- `core/multi_agent_v2/agents/middlewares.py` — Fix 2
- `core/multi_agent_v2/agents/tool_executor.py` — Fix 8
- `core/multi_agent_v2/agents/plan_manager.py` — Fixes 9, 11
- `~/.config/opencode/opencode.jsonc` — All 7 MCP servers
- `~/.config/opencode/opencode.json` — Plugin definitions + providers
