# V2 项目分析能力改造 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 V2 架构的 ReActCore 加上项目分析专用两阶段 prompt + 工具白名单，使"分析项目"任务从 ~10 轮 / 30s 降到 ~3 轮 / 9s

**Architecture:** 不改 ReActCore 循环逻辑、不改中间件链、不改 ToolRegistry——只在 prompt 层加 `_PROJECT_ANALYSIS_PROMPT` 引导 LLM 行为，在工具筛选层加白名单过滤无关工具。

**Tech Stack:** Python, ReActCore, ToolRegistry

**涉及文件（只改一个）：**
- `core/multi_agent_v2/agents/react_core.py`

**前置条件（已完成）：**
- `mcp/project_analyzer_mcp_server.py` — 批量读取工具
- `config/mcp_servers.yml` 新增 `project-analyzer-mcp` — MCP 注册
- `config/skill_keywords.yaml` 新增 `project_analysis` — 路由
- `config/skill_agent_map.yaml` — project_analysis → project_analyzer Expert

## Global Constraints

- 不改 ReActCore 的 `on_think_start` / `on_think_end` 逻辑
- 不改中间件链 `build_default_chain()`
- 不改 ToolRegistry 发现机制
- 不改 `_MAX_ROUNDS=10` 默认值，只在分析任务时提高到 15
- prompt 用 `<project_analysis_protocol>` 标签包围，与现有 prompt 风格一致

---

### Task 1: 添加 `_PROJECT_ANALYSIS_PROMPT` 常量

**Files:**
- Modify: `core/multi_agent_v2/agents/react_core.py`（在 prompt 模块区域，`_DEBUG_PROMPT` 之后追加）

**Interfaces:**
- 无外部接口——仅在 prompt 组装时引用

- [ ] **Step 1: 找到 prompt 模块区域**

找到 `_BASE_PROMPT`（~第 54 行）到 `_DEBUG_PROMPT`（~第 102 行）之间的区域。

- [ ] **Step 2: 添加 `_PROJECT_ANALYSIS_PROMPT`**

在 `_DEBUG_PROMPT` 定义之后添加：

```python
_PROJECT_ANALYSIS_PROMPT = (
    "<project_analysis_protocol>\n"
    "你正在分析一个项目的结构和代码。请按两阶段执行：\n\n"
    "【第一阶段：收集信息】\n"
    "1. 先调用 analyze_project(path) 批量读取关键文件\n"
    "2. 如果信息不够，调 search_code(query, file_pattern) 补充搜索\n"
    "3. 收集完成后进入第二阶段\n\n"
    "【第二阶段：综合分析】\n"
    "基于已收集的数据，直接输出完整的项目分析报告：\n"
    "- 项目概览（语言、框架、构建工具）\n"
    "- 目录结构与各模块职责\n"
    "- 核心技术栈分析\n"
    "- 架构亮点与注意事项\n"
    "</project_analysis_protocol>"
)
```

- [ ] **Step 3: 验证语法**

```bash
python3 -c "import ast; ast.parse(open('core/multi_agent_v2/agents/react_core.py').read()); print('✅')"
```

Expected: `✅`

---

### Task 2: 在 prompt 组装中插入项目分析 prompt

**Files:**
- Modify: `core/multi_agent_v2/agents/react_core.py`（第 216-228 行的 prompt 模块拼接逻辑）

- [ ] **Step 1: 找到 prompt 组装逻辑**

在 `on_think_start` 方法中，找到按任务类型组装 `modules` 的代码（第 216-228 行）。

- [ ] **Step 2: 追加项目分析分支**

在现有的模块拼接逻辑之后、`system_content` 拼接之前，追加：

```python
        # ── 项目分析任务：插入两阶段分析 prompt ──
        analysis_kw = ["分析项目", "项目结构", "项目目录",
                       "看.*项目", "项目的代码", "分析.*项目"]
        if any(re.search(kw, task_lower) for kw in analysis_kw):
            modules.insert(1, _PROJECT_ANALYSIS_PROMPT)
            ctx.max_iterations = max(ctx.max_iterations, 15)
```

- [ ] **Step 3: 验证语法**

```bash
python3 -c "import ast; ast.parse(open('core/multi_agent_v2/agents/react_core.py').read()); print('✅')"
```

Expected: `✅`

---

### Task 3: 项目分析任务工具白名单过滤

**Files:**
- Modify: `core/multi_agent_v2/agents/react_core.py`（第 172-188 行的 `get_tools_for_task` 调用附近）

- [ ] **Step 1: 找到工具筛选代码**

在 `on_think_start` 方法中，找到 `get_tools_for_task` 调用的位置（~第 179 行）。

- [ ] **Step 2: 增加分析任务白名单**

```python
                task_lower = ctx.task_description.lower()
                analysis_kw = ["分析项目", "项目结构", "项目目录", "项目分析"]
                if any(kw in task_lower for kw in analysis_kw):
                    analysis_tool_names = {"analyze_project", "search_code", "read_file", "search_files"}
                    filtered = [t for t in tool_cache if t.name in analysis_tool_names]
                    if not filtered:
                        filtered = await reg.get_tools_for_task(
                            ctx.task_description, max_tools=20,
                            allowed=ctx.allowed_tools,
                            disallowed=ctx.disallowed_tools,
                            tool_preference=ctx.tool_preference,
                        )
                else:
                    filtered = await reg.get_tools_for_task(
                        ctx.task_description, max_tools=20,
                        allowed=ctx.allowed_tools,
                        disallowed=ctx.disallowed_tools,
                        tool_preference=ctx.tool_preference,
                    )
```

- [ ] **Step 3: 验证语法**

```bash
python3 -c "import ast; ast.parse(open('core/multi_agent_v2/agents/react_core.py').read()); print('✅')"
```

Expected: `✅`

- [ ] **Step 4: 功能自检**

检查：
1. `analyze_project` 是 MCP 工具名（在 `project-analyzer-mcp` 中定义）✓
2. `search_code` 是 MCP 工具名 ✓
3. `read_file` 是内置工具名 ✓
4. `search_files` 是内置工具名 ✓
5. 白名单为空时 fallback 到正常筛选 ✓

---

### Task 4: 集成验证

- [ ] **Step 1: 验证三个改动共存**

```bash
grep -n "_PROJECT_ANALYSIS_PROMPT\|analysis_kw\|analysis_tool_names\|analyze_project" core/multi_agent_v2/agents/react_core.py
```

Expected: 三个改动都出现在文件中。

- [ ] **Step 2: 模拟 prompt 匹配**

```bash
python3 -c "
import re
tests = [
    ('分析一下 /xxx 项目', True),
    ('看看项目结构', True),
    ('帮我分析项目代码', True),
    ('今天天气怎么样', False),
]
for msg, exp in tests:
    analysis_kw = ['分析项目', '项目结构', '项目目录', '看.*项目', '项目的代码', '分析.*项目']
    ok = any(re.search(kw, msg) for kw in analysis_kw)
    status = '✅' if ok == exp else '❌'
    print(f'{status} \"{msg}\" → {\"分析\" if ok else \"普通\"} (期望: {\"分析\" if exp else \"普通\"})')
"
```

Expected: 全部 ✅

- [ ] **Step 3: 模拟工具过滤**

```bash
python3 -c "
tests = [
    ('分析项目结构', True),
    ('帮我看看项目目录', True),
    ('天气', False),
]
all_tools = {'analyze_project', 'search_code', 'read_file', 'search_files',
             'web_search', 'execute_shell', 'fetch_url', 'write_file'}
analysis_kw = ['分析项目', '项目结构', '项目目录', '项目分析']

for msg, exp in tests:
    is_a = any(kw in msg for kw in analysis_kw)
    if is_a:
        tools = all_tools & {'analyze_project', 'search_code', 'read_file', 'search_files'}
    else:
        tools = all_tools
    status = '✅' if is_a == exp else '❌'
    print(f'{status} \"{msg}\" → 可见工具: {len(tools)}个')
"
```

Expected: 分析任务可以看到 4 个工具，普通任务可以看到全量工具。
