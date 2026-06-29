# Project Analyzer 深度分析重构设计

**日期**: 2026-06-29
**状态**: 已批准，待实现

---

## 1. 背景与问题

### 现状
`project_analyzer` 通过 `work_agent.py` 的 `_phase1_and_2` 做 CodeGraph 扫描 + 读文件头部，数据注入 task_description 标记为 `"===== 项目结构概览（Phase 1 扫描）====="`。

`react_core.py` 的 `run_react` 检测到该标记后触发**特殊处理分支**：
- 强制 `max_iterations = 3`
- 禁用 `read_file`，只允许 `write_file`
- 注入 `_PROJECT_ANALYSIS_PROMPT`：明文禁止首轮调工具，强制直接输出报告
- 计划固定为 2 步（浏览目录 + 读配置）

**结果**：LLM 拿着目录树+文件头部，被禁止读代码，3 轮内只能输出 ~200 行浅层 Markdown。

### 目标
让 `project_analyzer` 走**通用 ReAct 流程**：
- LLM 自主制定计划（读入口 → 读核心模块 → 搜调用链 → 读配置/测试 → 写报告）
- 全工具开放：`read_file` `search_code` `execute_shell` `write_file`
- 8-15 轮深度探索
- 生成 ≥3000 行 HTML 报告，覆盖 9 大维度

---

## 2. 设计方案

### 2.1 `config/agents.yml` — role_prompt 重写

```yaml
project_analyzer:
  role_prompt: >
    你是一个资深代码架构分析师。用户给定项目路径，要求深度分析。

    【工作流程】
    1. 先用 read_file/execute_shell 了解目录结构、入口文件、核心配置
    2. 基于初步了解，制定分析计划（可多步）：读核心模块 → 读关键调用链 → 读配置/测试 → 综合
    3. 按计划执行：用 read_file 深度读代码、用 search_code 追踪调用、用 execute_shell 跑命令验证
    4. 综合所有发现，用 write_file 生成完整 HTML 报告到桌面

    【工具使用原则】
    - 多用 read_file 读核心文件全文（不要只看头部）
    - 用 search_code 追踪关键函数的调用者/被调用者
    - 用 execute_shell 跑 grep/find/rg 补充搜索
    - 发现新线索即时调整计划，不要机械执行

    【报告要求】
    - 覆盖：概览、目录结构、技术栈、架构分层、数据流、核心模块实现、错误处理、代码质量、改进建议
    - 输出完整 HTML（含样式），保存到 ~/Desktop/project_analysis_report.html
  tools: ["project-analyzer-mcp", "file-ops-mcp", "codegraph-mcp"]
  priority: 3
```

### 2.2 `react_core.py` — 去除特殊处理分支

**删除位置：**

| 行号范围 | 删除内容 |
|----------|----------|
| 841-849 | `if "Phase 1 扫描" ...` 特殊处理块（限制轮数/工具） |
| 865-877 | `_has_structure_data` 检测及特殊逻辑，改为统一走 `generate_plan` |
| 496-499 | `if "Phase 1 扫描" in ctx.task_description` 空转豁免 |
| 946-951 | `write_file` 成功即跳出循环 |
| 964-975 | 连续 `read_file` 检测强制中断 |

**保留工具函数**：`_trim_desc`、`_filter_scan_tools`、`_PROJECT_ANALYSIS_PROMPT`（供其他场景用）

**替换为统一计划生成：**
```python
# 第 864-877 行替换为：
ctx.plan = await generate_plan(task_description, ctx)
if ctx.plan:
    display_plan(ctx, prefix=prefix)
else:
    print(f"{prefix}    📋 无显式计划，自动按 ReAct 循环执行")
```

### 2.3 `work_agent.py` — Phase 1 数据作为「参考资料」注入

**第 94-100 行修改：**
```python
if await self._is_project_analysis(desc):
    phase_data = await self._phase1_and_2(desc, start)
    if phase_data:
        # 不再拼接触发特殊模式的标记，而是作为背景资料注入
        desc = f"{desc.rstrip()}\n\n【项目扫描参考资料】\n{phase_data}"
        task.description = desc
        print(f"    📦 项目扫描参考资料已注入 ({len(phase_data)} 字符)")
```

**去除关键字**：不再使用 `"===== 项目结构概览（Phase 1 扫描）====="` 作为触发标记。

---

## 3. 数据流对比

| 环节 | 现状（浅层） | 目标（深度） |
|------|--------------|--------------|
| 入口检测 | 关键字匹配 → 特殊模式 | LLM 判断 `_is_project_analysis` → 通用模式 |
| 工具集 | 禁用 `read_file`，只能 `write_file` | 全工具开放：`read_file` `search_code` `execute_shell` `write_file` |
| 轮数 | 强制 3 轮 | 10-15 轮（由 `max_rounds` 控制） |
| 计划 | 固定 2 步 | LLM 动态生成，随发现调整 |
| Phase 1 数据 | 作为"已提供数据"，禁止重复读 | 作为"参考资料"，LLM 自主决定是否补充读 |
| 触发写报告 | `write_file` 成功即跳出 | 计划完成 + 报告生成双重条件 |

---

## 4. 成功标准

1. **轮数**：opencode_副本 (5796 文件) 跑 8-12 轮
2. **工具调用**：≥ 10 次 `read_file`/`search_code`/`execute_shell`
3. **读文件深度**：读完整核心文件（非头部 30 行）
4. **输出质量**：HTML 报告 ≥ 3000 行，覆盖 9 大维度
5. **计划动态性**：中途根据发现新增/调整计划步骤

---

## 5. 风险与对策

| 风险 | 对策 |
|------|------|
| LLM 陷入无限读文件 | `generate_plan` 生成明确步骤；`consecutive_idle_rounds >= 3` 强制结束 |
| 上下文爆炸 | 保留 `ContextBudgetManager` 自动压缩；`_trim_desc` 限制注入资料长度 |
| Phase 1 扫描耗时 | 并行化 `os.walk` 和文件读取；可选缓存 |
| 破坏其他技能 | 仅去除 `project_analysis` 特殊分支，不改动通用 ReAct 逻辑 |

---

## 6. 实现顺序

1. `config/agents.yml` — role_prompt 重写
2. `core/multi_agent_v2/agents/react_core.py` — 删除 5 处特殊分支，统一计划生成
3. `core/multi_agent_v2/agents/base/work_agent.py` — Phase 1 数据注入改为参考资料
4. 运行现有测试验证不回归
5. 手动 CLI 测试：`/run "深度分析 /path/to/opencode_副本"`