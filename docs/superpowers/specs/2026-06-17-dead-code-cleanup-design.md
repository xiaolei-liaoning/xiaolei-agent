# 死代码清理 + 三阶段架构修复方案

**日期**: 2026-06-17
**项目**: 小雷版 AI Agent (xiaolongxia-agent v3.4.0)
**状态**: Phase 1 已完成

---

## 1. 设计目标

通过 Workflow + Subagent 编排，对项目进行渐进式清理和修复：

1. **清理减负** — 通过 `__init__.py` 链条追踪验证真·死代码并删除
2. **缺陷稳定** — 修复 ReAct 无限循环、plan_manager 状态卡死等核心缺陷
3. **架构统一** — 合并两套 MCP 管理器、配置归一、清理存根模块

## 2. 约束条件

- V1(Web) / V2(CLI) **保持独立**，互不干扰
- JS Workflow 三层执行链 **不动核心逻辑**
- 每阶段完成后用户审查确认，再进入下一阶段
- 每阶段修改独立 commit，可回退

## 3. 架构概览

```
三阶段 Workflow 编排:

Phase 1 (清理) ──→ 用户审查 ──→ Phase 2 (修复) ──→ 用户审查 ──→ Phase 3 (统一)
     │                        │                        
     ├─ 死代码扫描             ├─ ReAct 循环修复 (P0 #1)
     ├─ 真·死代码删除          ├─ plan_manager 状态修复 (P0 #3)
     ├─ pyproject.toml 修复    ├─ LoopDetection 窗口修复
     └─ 僵尸导入清理           └─ 运行测试验证

     Workflow 内部用 parallel()/pipeline() 调度并行子Agent
```

## 4. Phase 1 详细设计 → ✅ 已完成

### 4.1 扫描方法

使用 Workflow + 19 个子 Agent 并行扫描：

1. **GIT-D 文件扫描**: 追踪 9 个已 `D` 文件的反向引用链
2. **疑似死代码扫描**: 扫描 `core/monitoring`、`wechat_mini_server` 等 7 个可疑模块
3. **代码克隆扫描**: 对比 `skills/` vs `plugin/` 的 mcp_connector 和 mcp_orchestrator
4. **`__init__.py` 链分析**: 追踪所有 32 个 `__init__.py` 的完整导出链

### 4.2 扫描结果

| 类别 | 数量 | 说明 |
|------|------|------|
| 确认真·死代码 | 8 个文件 | 零外部引用 |
| 引用稀疏 | 2 个文件 | 仅在字符串字段中出现 |
| 代码克隆 | 2 组 | plugin/skills 零引用副本 |
| __init__.py 导出无人消费 | 71% (23/32) | 星号导出无外部 import |
| 僵尸导入 | 5 条 | skills/__init__.py 指向不存在文件 |

### 4.3 删除清单（已完成）

```
core/agency_agent.py              — V1 废弃模块
core/agent_communication.py        — V1 废弃模块
core/agents/__init__.py            — 指向已删除模块
core/agents/agent_communication.py — V1 废弃模块
core/agents/intelligent_agent_selector.py — V1 废弃模块
core/agents/smart_multi_agent.py   — V1 废弃模块
core/check_env.py                  — 迁移遗留
core/circuit_breaker.py            — 迁移遗留
core/config_loader.py              — 已迁至 core/engine/
core/infrastructure/ (8 files)     — 已迁至 engine/ handlers/
wechat_mini_server.py              — 存根，功能不可用
plugin/skills/mcp_connector/       — 零引用副本（skills/ 的字节级克隆）
skills/mcp_orchestrator/           — 已被 plugin/ 版取代
skills/ocr_recognition/            — 零引用存根
skills/mvp_checker/                — 标注"待实现"的存根
skills/__init__.py                 — 移除 5 条僵尸导入
```

总计：**-5,967 行代码，25 个文件变更**

### 4.4 测试结果

| 结果 | 数量 |
|------|------|
| V2 测试通过 | 62/62（新增 0 失败） |
| 已知预存失败 | 1（ReAct 循环缺陷，Phase 2 修复） |
| 清理新增失败 | 0 |

---

## 5. Phase 2 待办项

### P0 — ReAct 循环修复

| 序号 | 缺陷 | 位置 | 修复方案 |
|------|------|------|---------|
| #1 | write_file 降级自身导致无限循环 | `tool_registry.py` + `recovery.py` | 移除工具自调用的降级路径 |
| #3 | plan_manager 状态逻辑错误 | `plan_manager.py` | `forced_instructions` 不空时仍应允许标记 done |
| #4 | `\b` 转义破坏 | `shell_guard.py` (若有) 或工具参数传递 | 在 shell 参数传递前转义处理 |
| #5 | 超时不取消协程 → 协程泄漏 | `react_core.py` | `asyncio.wait_for()` + `cancel()` 处理 |
| #7 | 中间件状态跨任务泄漏 | `middleware.py` | 每个 RunContext 携带独立状态 |

### P1 — 需验证

| 序号 | 缺陷 | 位置 |
|------|------|------|
| #2 | recovery fallback 不执行 | `recovery.py` |
| #6 | 子 workflow 重置父状态 | `js_workflow.py` |

---

## 6. Phase 3 待办项

| 事项 | 说明 |
|------|------|
| 合并两套 MCP 管理器 | `mcp_client.py` vs `awesome_mcp_manager.py` |
| 配置归一 | `.env` / `app_config.json` / `config/*.yml` 三份配置对齐 |
| 清理 `core/monitoring/` | 已弃用的 900 行代码 |
| 删除 `plugin/skills/mcp_orchestrator/` | 如确认 skills/ 版完全取代 |

---

## 7. 决策记录

| 决策 | 理由 |
|------|------|
| 保留 `core/circuit_breaker.py` 的字符串字段名 | 仅字段名引用，模块引用为 0，字段名不碍事 |
| 保留 `core/monitoring/` 暂不删 | `task_scheduler.py` 和 `wechat_mini_server.py` 引用（后者已删，需调整） |
| 不动 keyword_extractors/ 7 个提取器 | 门面模式内部引用，是活的 |
| 不动各 `__init__.py` 导出（71%无人消费） | 不报错且不影响运行，删了徒增噪音 |
