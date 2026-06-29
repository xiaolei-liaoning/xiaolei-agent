# Project Analyzer 深度分析重构实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让 `project_analyzer` 走通用 ReAct 流程，支持多轮工具调用深度读代码，生成 ≥3000 行 HTML 报告。

**架构：** 去除 `react_core.py` 中对 "Phase 1 扫描" 的 5 处特殊处理分支；统一走 `generate_plan`；`work_agent.py` 的 Phase 1 数据改为「参考资料」注入；`config/agents.yml` 重写 role_prompt 鼓励深度探索。

**技术栈：** Python 3.13+, asyncio, 现有 ReAct 中间件链

---

## 文件结构

| 文件 | 角色 | 变更类型 |
|------|------|----------|
| `config/agents.yml` | project_analyzer 角色定义 | 修改 role_prompt |
| `core/multi_agent_v2/agents/react_core.py` | ReAct 核心循环入口 | 删除 5 处特殊分支，统一计划生成 |
| `core/multi_agent_v2/agents/base/work_agent.py` | WorkAgent 执行入口 | Phase 1 数据注入改为参考资料 |
| `tests/v2/test_project_analysis_guard.py` | 现有测试 | 更新以匹配新行为 |
| `tests/v2/test_analysis_e2e.py` | 现有测试 | 更新以匹配新行为 |

---

### 任务 1：更新 `config/agents.yml` — project_analyzer role_prompt 重写

**文件：**
- 修改：`config/agents.yml:7-14`

- [ ] **步骤 1：编写失败的测试（验证 prompt 内容）**

```python
# test_agents_config.py
import yaml

def test_project_analyzer_prompt_encourages_deep_analysis():
    with open("config/agents.yml") as f:
        cfg = yaml.safe_load(f)
    prompt = cfg["agents"]["project_analyzer"]["role_prompt"]
    # 必须包含鼓励多轮工具使用的关键词
    assert "read_file" in prompt
    assert "search_code" in prompt or "execute_shell" in prompt
    assert "计划" in prompt or "plan" in prompt.lower()
    assert "write_file" in prompt
    assert "HTML" in prompt or "html" in prompt
    # 必须不包含禁止工具的语言
    assert "禁止" not in prompt or "禁止在首轮" not in prompt
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python test_agents_config.py`
预期：FAIL（旧 prompt 包含"只分析"、"禁止"等限制语言）

- [ ] **步骤 3：编写最少实现代码**

```yaml
# config/agents.yml 第 7-14 行替换为：
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

- [ ] **步骤 4：运行测试验证通过**

运行：`python test_agents_config.py`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add config/agents.yml test_agents_config.py
git commit -m "feat: rewrite project_analyzer prompt for deep analysis"
```

---

### 任务 2：修改 `react_core.py` — 删除第 841-849 行特殊处理分支

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py:841-849`

- [ ] **步骤 1：编写失败的测试**

```python
# test_react_core_no_special_branch.py
import ast

def test_run_react_no_phase1_special_branch():
    with open("core/multi_agent_v2/agents/react_core.py") as f:
        source = f.read()
    tree = ast.parse(source)
    # 找到 run_react 函数
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_react":
            # 检查函数体中没有 "Phase 1 扫描" 字符串字面量用于特殊分支
            for n in ast.walk(node):
                if isinstance(n, ast.If):
                    for cond_node in ast.walk(n.test):
                        if isinstance(cond_node, ast.Constant) and "Phase 1 扫描" in str(cond_node.value):
                            # 允许 _trim_desc 等工具函数里有，但 run_react 函数体内不应有
                            raise AssertionError("run_react 仍包含 Phase 1 特殊分支")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python test_react_core_no_special_branch.py`
预期：FAIL（旧代码有第 841-849 行特殊分支）

- [ ] **步骤 3：编写最少实现代码**

```python
# core/multi_agent_v2/agents/react_core.py
# 第 841-849 行删除，替换为：
    # 默认启用上下文预算管理
    ctx.context_budget = ContextBudgetManager()
```

（原第 841-849 行：`if "Phase 1 扫描" ... ctx.max_iterations = 3; ctx.disallowed_tools = ...; ctx.allowed_tools = ["write_file"]` 整块删除）

- [ ] **步骤 4：运行测试验证通过**

运行：`python test_react_core_no_special_branch.py`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py test_react_core_no_special_branch.py
git commit -m "refactor: remove Phase 1 special branch in run_react"
```

---

### 任务 3：修改 `react_core.py` — 删除第 865-877 行 _has_structure_data 特殊逻辑，统一走 generate_plan

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py:865-877`

- [ ] **步骤 1：编写失败的测试**

```python
# test_react_core_unified_plan.py
import ast

def test_run_react_unified_plan_generation():
    with open("core/multi_agent_v2/agents/react_core.py") as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_react":
            # 检查没有 _has_structure_data 变量赋值
            for n in ast.walk(node):
                if isinstance(n, ast.Assign):
                    for target in n.targets:
                        if isinstance(target, ast.Name) and target.id == "_has_structure_data":
                            raise AssertionError("_has_structure_data 仍存在")
                # 应统一走 generate_plan
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python test_react_core_unified_plan.py`
预期：FAIL

- [ ] **步骤 3：编写最少实现代码**

```python
# core/multi_agent_v2/agents/react_core.py 第 865-877 行替换为：
    # ── 规划阶段 ──
    ctx.plan = await generate_plan(task_description, ctx)
    if ctx.plan:
        display_plan(ctx, prefix=prefix)
    else:
        print(f"{prefix}    📋 无显式计划，自动按 ReAct 循环执行")
```

（原第 865-877 行：`_has_structure_data = ... if _has_structure_data: ... else: ctx.plan = await generate_plan...` 整块替换）

- [ ] **步骤 4：运行测试验证通过**

运行：`python test_react_core_unified_plan.py`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py test_react_core_unified_plan.py
git commit -m "refactor: unify plan generation for project_analysis"
```

---

### 任务 4：修改 `react_core.py` — 删除第 496-499 行 Phase 1 空转豁免

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py:496-499`

- [ ] **步骤 1：编写失败的测试**

```python
# test_react_core_no_phase1_idle_exempt.py
import ast

def test_no_phase1_idle_exempt():
    with open("core/multi_agent_v2/agents/react_core.py") as f:
        lines = f.readlines()
    # 第 496-499 行附近检查
    for i, line in enumerate(lines[490:510], start=491):
        if "Phase 1 扫描" in line and "_has_substance" in line:
            raise AssertionError(f"第 {i} 行仍有 Phase 1 空转豁免: {line.strip()}")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python test_react_core_no_phase1_idle_exempt.py`
预期：FAIL

- [ ] **步骤 3：编写最少实现代码**

```python
# core/multi_agent_v2/agents/react_core.py
# 删除第 496-499 行：
#                 # ponytail: 项目分析首轮是纯文本输出，不触发报告启发式/空跑重试，保存到历史后继续
#                 if "Phase 1 扫描" in ctx.task_description and _has_substance:
#                     ctx._conversation_history.append({"role": "assistant", "content": reply})
#                     ctx.final_answer = reply
#                     break
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python test_react_core_no_phase1_idle_exempt.py`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py test_react_core_no_phase1_idle_exempt.py
git commit -m "refactor: remove Phase 1 idle exempt in ReActCoreMiddleware"
```

---

### 任务 5：修改 `react_core.py` — 删除第 946-951 行 write_file 成功即跳出

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py:946-951`

- [ ] **步骤 1：编写失败的测试**

```python
# test_react_core_no_write_file_early_exit.py
import ast

def test_no_write_file_early_exit():
    with open("core/multi_agent_v2/agents/react_core.py") as f:
        lines = f.readlines()
    for i, line in enumerate(lines[940:960], start=941):
        if "_write_file_done" in line:
            raise AssertionError(f"第 {i} 行仍有 write_file 早退标记: {line.strip()}")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python test_react_core_no_write_file_early_exit.py`
预期：FAIL

- [ ] **步骤 3：编写最少实现代码**

```python
# core/multi_agent_v2/agents/react_core.py
# 删除第 946-951 行：
#         # ponytail: 项目分析 — write_file 成功即跳出循环，不走空转，让 fallback 总结
#         if _has_structure_data and ctx.tool_results:
#             _last = ctx.tool_results[-1]
#             if _last.get("success") and _last.get("tool_call", {}).get("name") == "write_file":
#                 ctx._write_file_done = True
#                 break
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python test_react_core_no_write_file_early_exit.py`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py test_react_core_no_write_file_early_exit.py
git commit -m "refactor: remove write_file early exit for project_analysis"
```

---

### 任务 6：修改 `react_core.py` — 删除第 964-975 行连续 read_file 检测强制中断

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py:964-975`

- [ ] **步骤 1：编写失败的测试**

```python
# test_react_core_no_consecutive_read_file_check.py
import ast

def test_no_consecutive_read_file_check():
    with open("core/multi_agent_v2/agents/react_core.py") as f:
        lines = f.readlines()
    for i, line in enumerate(lines[960:980], start=961):
        if "连续 read_file" in line or "连续多次调 read_file" in line:
            raise AssertionError(f"第 {i} 行仍有连续 read_file 检测: {line.strip()}")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python test_react_core_no_consecutive_read_file_check.py`
预期：FAIL

- [ ] **步骤 3：编写最少实现代码**

```python
# core/multi_agent_v2/agents/react_core.py
# 删除第 964-975 行整块：
#         # ── 项目分析：检测连续 read_file 不输出分析 → 强制中断 ──
#         if _has_structure_data:
#             _recent_tools = [r.get("tool_call", {}).get("name", "") for r in ctx.tool_results[-4:]]
#             if len(_recent_tools) >= 3 and all(t == "read_file" for t in _recent_tools[-3:]):
#                 if not ctx.forced_instructions:
#                     ctx.forced_instructions = (
#                         "⚠️ 你已经连续多次调 read_file 但没有输出分析。\n"
#                         "现在必须停下来分析刚才读到的文件内容。\n"
#                         "格式要求：对刚读的目录输出「📁 目录名: 职责分析（1-2句话）」\n"
#                         "然后再决定下一步读哪个文件。"
#                     )
#                     print(f"{prefix}    ⚠️ 检测到连续 read_file 未分析，注入提醒")
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python test_react_core_no_consecutive_read_file_check.py`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py test_react_core_no_consecutive_read_file_check.py
git commit -m "refactor: remove consecutive read_file detection for project_analysis"
```

---

### 任务 7：修改 `work_agent.py` — Phase 1 数据注入改为「参考资料」

**文件：**
- 修改：`core/multi_agent_v2/agents/base/work_agent.py:94-100`

- [ ] **步骤 1：编写失败的测试**

```python
# test_work_agent_phase1_reference.py
import ast

def test_phase1_data_injected_as_reference():
    with open("core/multi_agent_v2/agents/base/work_agent.py") as f:
        source = f.read()
    # 检查不再使用 "===== 项目结构概览（Phase 1 扫描）=====" 标记
    assert "===== 项目结构概览" not in source or "Phase 1 扫描" not in source
    # 检查使用 "【项目扫描参考资料】" 作为注入标记
    assert "【项目扫描参考资料】" in source
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python test_work_agent_phase1_reference.py`
预期：FAIL（旧代码用 "===== 项目结构概览（Phase 1 扫描）====="）

- [ ] **步骤 3：编写最少实现代码**

```python
# core/multi_agent_v2/agents/base/work_agent.py 第 94-100 行替换为：
            # ── 项目分析任务：Phase 1 扫描 → Phase 2 批量读 → 注入为参考资料 ──
            if await self._is_project_analysis(desc):
                phase_data = await self._phase1_and_2(desc, start)
                if phase_data:
                    # 不再拼接触发特殊模式的标记，而是作为背景资料注入
                    desc = f"{desc.rstrip()}\n\n【项目扫描参考资料】\n{phase_data}"
                    task.description = desc
                    print(f"    📦 项目扫描参考资料已注入 ({len(phase_data)} 字符)")
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python test_work_agent_phase1_reference.py`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/base/work_agent.py test_work_agent_phase1_reference.py
git commit -m "refactor: inject Phase 1 data as reference material not trigger"
```

---

### 任务 8：更新现有测试 `tests/v2/test_project_analysis_guard.py`

**文件：**
- 修改：`tests/v2/test_project_analysis_guard.py`

- [ ] **步骤 1：阅读现有测试理解预期**

```bash
cat tests/v2/test_project_analysis_guard.py
```

- [ ] **步骤 2：更新测试断言匹配新行为**

```python
# 关键变更点：
# 1. 不再期望 max_iterations=3
# 2. 不再期望 disallowed_tools 包含 read_file
# 3. 不再期望触发特殊模式标记
# 4. 期望统一走 generate_plan
```

- [ ] **步骤 3：运行测试验证通过**

运行：`pytest tests/v2/test_project_analysis_guard.py -v`
预期：PASS

- [ ] **步骤 4：Commit**

```bash
git add tests/v2/test_project_analysis_guard.py
git commit -m "test: update project_analysis_guard for deep analysis flow"
```

---

### 任务 9：更新现有测试 `tests/v2/test_analysis_e2e.py`

**文件：**
- 修改：`tests/v2/test_analysis_e2e.py`

- [ ] **步骤 1：阅读现有测试**

```bash
cat tests/v2/test_analysis_e2e.py
```

- [ ] **步骤 2：更新测试断言**

```python
# 关键变更：
# - 移除对 Phase 1 特殊模式的期望
# - 增加对多轮 read_file/search_code 的期望
# - 期望最终生成 HTML 报告
```

- [ ] **步骤 3：运行测试验证通过**

运行：`pytest tests/v2/test_analysis_e2e.py -v`
预期：PASS

- [ ] **步骤 4：Commit**

```bash
git add tests/v2/test_analysis_e2e.py
git commit -m "test: update analysis_e2e for deep analysis flow"
```

---

### 任务 10：端到端 CLI 验证

**文件：**
- 无新增文件，运行真实 CLI 测试

- [ ] **步骤 1：运行真实项目分析**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
python cli.py /run "深度分析 /Users/leiyuxuan/Desktop/opencode_副本"
```

- [ ] **步骤 2：验证成功标准**

- [ ] 轮数 ≥ 8
- [ ] read_file/search_code/execute_shell 总调用 ≥ 10
- [ ] 生成 ~/Desktop/project_analysis_report.html
- [ ] 报告 ≥ 3000 行，覆盖 9 大维度

- [ ] **步骤 3：Commit 验证记录**

```bash
git add -A
git commit -m "feat: project_analyzer deep analysis working end-to-end"
```

---

## 自检清单

- [ ] 规格覆盖度：设计文档 5 个改动点 ↔ 10 个任务全部覆盖
- [ ] 占位符扫描：无 "TODO" "待定" "后续实现"
- [ ] 类型一致性：所有测试文件引用的函数/变量名与实现一致
- [ ] 无重复：任务间无重复代码块，每个任务独立可运行

---

**执行方式选择：** 请选择子代理驱动 或 内联执行