---
name: agent-unification-refactor
description: Agent 角色别名清理、提示词统一、模拟思考降级删除
metadata:
  type: project
---

# Agent 统一化重构（2026-05-22）

## 改动清单

### 1. 砍掉预设角色别名
`core/multi_agent_v2/agents/__init__.py`
- 删了 `MasterAgent = WorkAgent`、`WorkerAgent = WorkAgent` 等 6 个别名
- 只导出 `WorkAgent`，统一对外接口

### 2. 清理 AgentType 枚举
`core/multi_agent_v2/agents/base/models.py`
- 删了 `MASTER`、`REVIEWER`、`EXPERT` 等 5 个假别名
- 只剩 `GENERIC` 和 `WORKER` 两个值

### 3. 6 套模板 → 1 套通用提示词
`core/multi_agent_v2/agents/prompts/agent_prompts.py`
- 从 1000+ 行缩到 ~100 行
- 删掉角色扮演式废话（"你是一位10年经验的项目管理专家"）
- 换成 4 步工作流：理解任务 → 制定计划 → 调工具/写代码 → 检查结果

### 4. 删除模拟思考降级
`core/multi_agent_v2/agents/base/mind.py`
- 删了 `_think_simulated` 和 3 个辅助方法
- LLM 失败就抛异常，不再静默降级模拟思考

### 连带清理
- `cli/base.py`、`tests/verify_e2e_real.py` — 旧别名引用换成 `WorkAgent`
- `capability_matcher.py` — 删了 `AgentType.MASTER` 引用
- `api/routes/chat.py` — `AgentType.MASTER.value` 换成 `AgentType.WORKER.value`

## 验证
- pytest: 91 passed，零失败
- 全部 import 检查通过
- 旧别名残留 grep 确认无遗漏

**Why:** 去掉角色扮演幻觉，让 agent 框架更薄、更直白。调用方不再需要知道 Worker/Master/Reviewer 的区别，只有一个 WorkAgent。
**How to apply:** 新加 agent 逻辑时直接引用 `WorkAgent` 和 `AgentType.WORKER`，不要引入新角色类型。
