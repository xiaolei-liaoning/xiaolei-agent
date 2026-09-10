# 小雷版 Agent — 协作开发指南 (AGENTS.md)

> 本文件供所有 AI 会话/协作者在改代码前必读。硬性规则，非建议。

## 测试纪律（读改前必跑）

```bash
scripts/run_tests.sh                      # 全套 (36 文件, ~45s, 必须 exit 0)
scripts/run_tests.sh tests/v2/            # 单目录
XIAOLEI_REAL_LLM=1 python -m pytest tests/v2/test_comprehensive_real.py  # 真LLM opt-in
```

- **基线 (2026-09-10)**: 493 passed / 35 skipped / 0 failed
- 改代码前先跑，必须有绿基线。跑不绿 → 先修环境，不要在红基线上叠加改动
- **真实 LLM 测试默认跳过**（`XIAOLEI_REAL_LLM=1` 才跑）— 无开关的"调真 LLM"测试曾导致套件挂死

## 回归守卫约定 (最重要的规则)

> 参考 hermes-agent：**修一个 bug 必须**同时在 `tests/regress/` 提交 1 个最小回归测试。
> 文件名：`test_regress_<来源编号或一句话>_<行为>.py`

- 修完 bug，测试**变绿**才允许 commit（TDD：先红后绿）
- commit 单一语义：`fix(x): <根因>` 与守卫测试同一 commit
- **永不删除回归测试**（代码语义变更时迁移并注明）
- 详细约定：`tests/regress/README.md`

示例（真实案例）:
```
2026-09-10 | shell_guard mv/cp 目标路径漏检 | tests/test_shell_guard_bounds.py::TestSensitivePaths
2026-09-10 | edit_file 精确匹配占位 | 不调 SmartEngine 9级匹配 | tests/test_edit_file.py
2026-09-10 | CircuitBreaker 缺 sync_* | context_compactor 调用崩溃 | tests/test_compaction_lifecycle.py
```

## 硬性约束

- **语法检查门禁**: 改 `.py` 后必须 `python -c "import ast; ast.parse(open(...).read())"`
- **不动 `.venv`/`data`**：清缓存只删 `__pycache__`/`.pyc`/`.pytest_cache`
- **绝对路径**: 用户态代码用 `os.path.expanduser("~/.xiaolei/...")`，测试必须用 `tmp_path` 或 `_hermetic_environment` 临时目录
- **禁止在测试中真实写生产目录** `~/.xiaolei/`（conftest 写保护会拦截）
- **禁止测试打非 localhost 外网**（conftest 网络守卫会拒绝，需 mock 或 `real_network` 标记）

## ReAct 核心机制备忘

- `_MAX_ROUNDS = 10`（全局轮次上限）、`_MAX_STEPS_PER_ROUND = 15`（每轮内步数上限）
- `react_depth` 只在**步骤循环结束后 +1**（不要在步骤循环内递增——0d9af24 引入过这个 bug）
- 每轮结构: `while react_depth < 10 { while steps < 15 { LLM → tool → check } react_depth += 1 }`

## 关键架构入口

- `core/multi_agent_v2/agents/react_core.py` — ReAct 主循环
- `core/multi_agent_v2/tools/tool_registry.py` — 工具注册 + `_handle_edit_file`（**已是 SmartEditor 9级匹配**）
- `core/multi_agent_v2/tools/shell_guard.py` — shell 命令安全边界（请勿绕过）
- `core/memory/context_compactor.py` — 7 层压缩编排器（L0→L4 + 熔断）
- `tests/conftest.py` — 测试封闭宇宙（凭据清空/生产目录写保护/外网阻断）

---
**历史会话记录** (KOF 修复/ReAct 11 bug/Postconditions/工具策略重构等):
见 `docs/session_history_agenda.md`
