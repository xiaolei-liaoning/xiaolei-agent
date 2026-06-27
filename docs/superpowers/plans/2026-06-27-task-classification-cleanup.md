# Task Classification 清理 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 `react_core.py` 删除 4 个硬编码 prompt 常量 + 条件注入逻辑，合并通用规则到 `_BASE_PROMPT`，Expert 匹配加"无匹配"选项。

**Architecture:** 纯删除 + 移动，不改执行逻辑、中间件链或工具系统。

**Tech Stack:** Python, ReActCore, SkillSystem

---

### Task 1: 合并 `_BASE_PROMPT`（追加通用规则）

**Files:**
- Modify: `core/multi_agent_v2/agents/react_core.py`（~54-65 行）

- [ ] **Step 1: 找到 `_BASE_PROMPT` 定义**

定位到 ~54 行的 `_BASE_PROMPT = (`。

- [ ] **Step 2: 在末尾追加 3 行通用规则**

```python
_BASE_PROMPT = (
    "先思考再行动：\n"
    "1. 任务目标是什么？当前进度在哪里？\n"
    "2. 需要工具就调用，有数据就回答，信息不够继续追问\n"
    "3. 不要输出思考过程描述，直接行动\n\n"
    "关键规则：\n"
    "- 每轮必须输出工具调用或最终答案，禁止空转\n"
    "- 如果任务明确，直接执行，不要描述'我将...'\n"
    "- 创建文件用 write_file 一次性写入完整代码\n"
    "- 修改代码用 edit_file（精确字符串替换）\n"
    "- 禁止输出被截断/不完整的代码\n"
    "【代码生成】首次 write_file → 修改用 edit_file\n"
    "【报告生成】web_search 获取数据 → write_file 输出 HTML\n"
    "【游戏开发】必须监听事件(keydown/click)，有渲染函数\n"
)
```

新增最后三行 `【代码生成】` / `【报告生成】` / `【游戏开发】`。其余不变。

---

### Task 2: 删除 `_CODE_GEN_PROMPT` / `_GAME_DEV_PROMPT` / `_REPORT_PROMPT` 常量

**Files:**
- Modify: `core/multi_agent_v2/agents/react_core.py`

- [ ] **Step 1: 删除 `_CODE_GEN_PROMPT`（~67-75 行）**

整块删除，从 `_CODE_GEN_PROMPT = (` 到对应的 `)`。

- [ ] **Step 2: 删除 `_GAME_DEV_PROMPT`（~77-84 行）**

整块删除。

- [ ] **Step 3: 删除 `_REPORT_PROMPT`（~87-93 行）**

整块删除。

---

### Task 3: 删除 `_PROJECT_ANALYSIS_PROMPT` 常量

**Files:**
- Modify: `core/multi_agent_v2/agents/react_core.py`

- [ ] **Step 1: 删除 `_PROJECT_ANALYSIS_PROMPT`（~104-131 行）**

整块删除，从 `_PROJECT_ANALYSIS_PROMPT = (` 到对应的 `)`。

---

### Task 4: 清理 `on_think_start` 的条件注入逻辑

**Files:**
- Modify: `core/multi_agent_v2/agents/react_core.py`（~325-354 行）

- [ ] **Step 1: 删除 prompt 条件注入块（~325-332 行）**

删除：
```python
# ── 按任务类型组装提示词模块 ──
modules = [_BASE_PROMPT]
if _task_flags.get("code"):
    modules.append(_CODE_GEN_PROMPT)
    if _task_flags.get("game"):
        modules.append(_GAME_DEV_PROMPT)
if _task_flags.get("report"):
    modules.append(_REPORT_PROMPT)
```

改为：
```python
modules = [_BASE_PROMPT]
```

- [ ] **Step 2: 删除项目分析条件注入（~349-354 行）**

删除 `_PROJECT_ANALYSIS_PROMPT` 插入行和 `_skip_plan` 赋值。保留 max_iterations 兜底：

```python
# 项目分析无 Phase 1 数据时给更多轮次
if _task_flags.get("project_analysis") and not getattr(ctx, '_has_structure_data', False):
    ctx.max_iterations = max(ctx.max_iterations, 15)
```

确认注释的清理（"# ponytail: Phase 1 已有结构化数据" 注释可以移除）。

---

### Task 5: Expert 匹配加"无匹配"选项

**Files:**
- Modify: `core/skills/base_skills.py`（~289-303 行）

- [ ] **Step 1: 修改精排 prompt**

改前：
```python
prompt = (
    f"任务：{task}\n\n"
    f"从以下专家中选最匹配的 1 个：\n"
    + "\n".join(lines) +
    "\n\n仔细阅读任务和每个专家的描述，只输出专家 ID："
)
```

改后：
```python
prompt = (
    f"任务：{task}\n\n"
    f"从以下专家中选最匹配的 1 个，如果都不匹配则输出「无匹配」：\n"
    + "\n".join(lines) +
    "\n\n仔细阅读任务和每个专家的描述，只输出专家 ID 或「无匹配」："
)
```

- [ ] **Step 2: 处理"无匹配"返回**

LLM 返回包含"无匹配"时 `return None`：
```python
resp = (await router.simple_chat(prompt, temperature=0.1, max_tokens=30) or "").strip().lower()
if "无匹配" in resp or "no match" in resp:
    return None
for a in top:
    if a.get("id", "") in resp:
        logger.debug(f"Expert LLM 精排选中: {a.get('name')}")
        return a
logger.debug(f"Expert LLM 精排无结果，降级为规则 Top-1: {scored[0][2].get('name')}")
return scored[0][2] if scored else None
```

---

### Task 6: work_agent.py Expert 空显示

**Files:**
- Modify: `core/multi_agent_v2/agents/base/work_agent.py`（~144-154 行）

- [ ] **Step 1: 补充 else 分支**

```python
if skill_result.expert_personality and skill_result.skill_id not in ("project_analyzer", "project_analysis"):
    ep = skill_result.expert_personality
    if ep.startswith('---'):
        idx = ep.find('---', 3)
        if idx > 0:
            ep = ep[idx + 3:].strip()
    self.personality += f"\n\n---\n【Expert】\n{ep[:12000]}"
    print(f"    \033[1;36m👤 Expert: {skill_result.expert_name}\033[0m")
    if len(ep) > 100:
        print(f"    \033[2m📄 角色定义已加载 ({len(ep[:12000])} 字)\033[0m")
else:
    print(f"    \033[2;37m👤 Expert: 未匹配到\033[0m")
```

注意保持原有的 `project_analyzer` 跳过逻辑：当 `expert_personality` 为空或 skill 是 project_analyzer 时，都打印"未匹配到"。

---

### Task 7: agents.yml project_analyzer role_prompt 追加分析指令

**Files:**
- Modify: `config/agents.yml`（project_analyzer 段）

- [ ] **Step 1: 找到 project_analyzer role_prompt**

在 `config/agents.yml` 中定位到 `project_analyzer` 的 `role_prompt` 值。

- [ ] **Step 2: 追加 `_PROJECT_ANALYSIS_PROMPT` 内容**

将 `react_core.py` 中删除的 `_PROJECT_ANALYSIS_PROMPT` 正文追加到现有 role_prompt 末尾。

内容（原 ~104-131 行）：
```
你正在深度分析一个项目。\n\n
【已提供的数据】\n
- 项目结构概览：文件树、技术栈、依赖、git 统计、import 关系\n
- 核心代码：选中的关键文件的头部（声明/import）和尾部（调用/main）\n\n
【重要规则】\n
- 禁止在首轮调用任何工具\n
- 禁止对已提供的文件调用 read_file\n
- 禁止调用 execute_shell / search_files 重新扫描目录\n\n
【任务】\n
基于已提供的数据输出完整的分析报告，覆盖以下维度：...\n\n
```

---

### Task 8: 运行测试验证

- [ ] **Step 1: 运行现有测试**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
python -m pytest tests/ -x -q 2>&1 | tail -20
```

预期：原有测试全部通过，无回归。

- [ ] **Step 2: 检查 KeyError / ImportError**

确保删除的常量没有任何残留引用。检查：
```bash
rg "_CODE_GEN_PROMPT|_GAME_DEV_PROMPT|_REPORT_PROMPT|_PROJECT_ANALYSIS_PROMPT" core/
```

预期：只在 `config/agents.yml` 的 role_prompt 字符串中出现（作为非代码文本），不在 `react_core.py` 中出现。
