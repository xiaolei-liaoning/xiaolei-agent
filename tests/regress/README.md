# 回归守卫约定 (Regression Guard Convention)

> 参考 hermes-agent：每个 bug 修复 commit 必须带 1 个最小回归测试，
> 文件名带 issue/疑点编号，永久保留机器可验证的守卫。

## 规则

1. **修 bug 前**，先在 `tests/regress/` 写一个会**失败**的最小测试。
2. 修完 bug，测试**变绿**，commit 一起提交（一个 commit 一个语义）。
3. 命名：`test_regress_<疑点编号>_<一句话>.py`
   - 示例: `test_regress_243_circuit_breaker_lock.py`
   - 无编号也接受: `test_regress_shell_guard_mv_path.py`（2026-09-10 修的 mv/cp 目标路径漏检）
4. 每个 docstring 顶部写清：根因一句话 + 修复位置 file:line。
5. **永远不删** regress 目录的测试（除非代码根语义变更，迁移时也要留的意图注释）。

## 与主测试目录的关系

- 主目录（tests/、tests/v2/）关注**功能生命周期**（compaction/shell_guard/subagent）
- regress/ 只关注**历史 bug 守卫**，细化到具体修复行为

## 当前守卫清单

| 日期 | 疑点/bug | 守卫文件 |
|------|---------|---------|
| 2026-09-10 | shell_guard mv/cp 目标路径漏检 | （包含在 tests/test_shell_guard_bounds.py） |
| 2026-09-10 | memory CircuitBreaker 缺 sync_record_* | （包含在 tests/test_compaction_lifecycle.py） |
| 2026-09-10 | js_workflow._depth 未初始化 | （包含在 tests/v2/test_real_scenarios.py 的 pattern 测试） |
| 2026-09-10 | react_depth 轮次推进丢失 | tests/v2/test_react_core_mock.py (iterative ≥1 断言) |
