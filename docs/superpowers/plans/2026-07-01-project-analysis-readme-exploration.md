# 项目分析 README 探索 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在项目分析时，LLM 能主动读 README 等总结性文件来产生深度分析，而非仅做 Phase 1+2 数据的 HTML 排版。

**架构：** 三处改点：(1) `_PROJECT_ANALYSIS_PROMPT` 从"禁止调工具"改为"引导探索 README"；(2) Phase 1+2 README 截取从 30 行/20 行扩展到 200 行/100 行，不截断；(3) Phase 1+2 返回值从 "LLM仅做HTML包装" 改为 "作为探索上下文"。代码层无工具限制（已确认），改 prompt 文本即可。

**技术栈：** Python, ReActCore

---

### 任务 1：改写 `_PROJECT_ANALYSIS_PROMPT` 去除工具阻拦

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py:104-130`

- [ ] **步骤 1：确认当前 prompt 内容**

运行：`grep -n "禁止在首轮调用任何工具\|禁止对已提供的文件调用 read_file\|禁止调用 execute_shell" core/multi_agent_v2/agents/react_core.py`
预期：找到 3 行匹配

- [ ] **步骤 2：改写 `_PROJECT_ANALYSIS_PROMPT`**

替换 `react_core.py:104-130`：

```python
_PROJECT_ANALYSIS_PROMPT = (
    "<project_analysis_protocol>\n"
    "你正在深度分析一个项目。\n\n"
    "【已提供的数据】\n"
    "- 下方有程序化扫描的初步结构数据：文件树、技术栈、核心代码头部、调用链\n"
    "- 这些数据作为浏览上下文使用，不代表全部\n\n"
    "【探索指引】\n"
    "1. 先用 read_file 读 README.md、CLAUDE.md、AGENTS.md 等总结性文档，了解项目定位和全貌\n"
    "2. 用 glob / search_code 探索关键模块和入口文件\n"
    "3. 结合下方扫描数据和你的探索结果，输出深度分析报告\n\n"
    "【任务】\n"
    "基于已提供的数据 + 你自行探索的信息，输出完整的分析报告，覆盖以下维度：\n"
    "   - 项目概览（语言、框架、构建工具、依赖）\n"
    "   - 目录结构与各模块职责\n"
    "   - 核心技术栈分析\n"
    "   - 架构设计与分层\n"
    "   - 数据流与核心链路（入口 → 处理 → 输出）\n"
    "   - 关键模块的实现分析\n"
    "   - 错误处理与边界情况\n"
    "   - 代码质量评估\n"
    "   - 改进建议\n\n"
    "分析结构建议：先宏观（概览、架构）再微观（模块细节），最后总结建议。\n"
    "</project_analysis_protocol>"
)
```

关键变化：删除"禁止在首轮调用任何工具"、"禁止对已提供的文件调用 read_file"、"禁止调用 execute_shell"，改为主动引导读 README 等总结性文件。

- [ ] **步骤 3：确认旧文本已删除**

运行：`grep -n "禁止在首轮调用任何工具\|LLM仅做HTML包装\|禁止对已提供的文件" core/multi_agent_v2/agents/react_core.py`
预期：无匹配

- [ ] **步骤 4：运行现有测试验证未破坏**

运行：`python -m pytest tests/v2/test_project_analysis_guard.py tests/v2/test_analysis_e2e.py -v 2>&1 | tail -20`
预期：全部 PASS（测试不检查 prompt 精确文本，只检查 JSON 不泄露 + 总结内容）

---

### 任务 2：扩展 README 读取行数 + 截断移除

**文件：**
- 修改：`core/multi_agent_v2/agents/base/work_agent.py:348-371`
- 修改：`core/multi_agent_v2/agents/base/work_agent.py:403-409`

- [ ] **步骤 1：确认当前 README 读取逻辑**

运行：`grep -n "read_file_head\|head\[:300\]\|rh\[:200\]\|doc_candidates" core/multi_agent_v2/agents/base/work_agent.py`
预期：找到 doc_candidates 列表和截断代码

- [ ] **步骤 2：扩展 doc_candidates 加入 ARCHITECTURE.md 等**

在 `work_agent.py:349`，将：
```python
doc_candidates = ["README.md", "README", "Readme.md", "CLAUDE.md", "AGENTS.md"]
```
改为：
```python
doc_candidates = ["README.md", "README", "Readme.md", "CLAUDE.md", "AGENTS.md",
                  "ARCHITECTURE.md", "CONTRIBUTING.md", "CHANGELOG.md", "docs/README.md"]
```

- [ ] **步骤 3：扩展根目录 README 行数 + 移除截断**

替换 `work_agent.py:363-370`（约这部分）：

修改 `read_file_head(rf)` 为 `read_file_head(rf, 200)`，移除 `head[:300]` 截断：

```python
            if head:
                first_line = head.split("\n")[0][:100] if head else ""
                analysis_sections.append(f"📄 {rf}  ({lc}行)")
                analysis_sections.append(f"   首行: {first_line}")
                analysis_sections.append(f"   内容概要: {head}")
                analysis_sections.append("")
```

关键变化：`head[:300]` → `head`（不截断），`read_file_head(rf)` → `read_file_head(rf, 200)`（更多行）

- [ ] **步骤 4：扩展子目录 README 行数 + 移除截断**

替换 `work_agent.py:407-409`：

```python
            if dir_readme:
                rh = read_file_head(dir_readme[0], 100)
                if rh:
                    analysis_sections.append(f"  📖 README: {rh}")
```

关键变化：`read_file_head(_, 20)` → `read_file_head(_, 100)`，`rh[:200]` → `rh`

---

### 任务 3：改写 Phase 1+2 返回值

**文件：**
- 修改：`core/multi_agent_v2/agents/base/work_agent.py:486-507`

- [ ] **步骤 1：确认当前返回值内容**

运行：`sed -n '486,507p' core/multi_agent_v2/agents/base/work_agent.py`
预期：看到 "LLM仅做HTML包装" 和 "不要调用 read_file"

- [ ] **步骤 2：改写返回值**

替换 `work_agent.py:486-507`：

```python
        return (
            f"【项目分析数据已就绪 — 作为探索上下文使用】\n\n"
            f"下方是程序化扫描的初步结构数据（文件树、核心代码头部、调用链）。\n"
            f"请在此基础上使用 read_file 深入读 README、CLAUDE.md 等总结性文件，"
            f"结合上下文产出深度分析报告。\n\n"
            f"路径：{path}\n"
            f"分析耗时：{elapsed:.1f}s\n\n"
            f"{analysis_text}"
        )
```

关键变化：移除 HTML 包装指令、3 轮限制、"不要调工具"警告，改为引导探索

- [ ] **步骤 3：验证旧文本已删除**

运行：`grep -n "LLM仅做HTML包装\|不要调用 read_file\|所有数据已在此\|第 1 轮：直接生成\|第 2 轮：用 write_file" core/multi_agent_v2/agents/base/work_agent.py`
预期：无匹配

---

### 任务 4：更新测试

**文件：**
- 修改：`tests/v2/test_analysis_e2e.py:6-27`

- [ ] **步骤 1：确认 `_filter_scan_tools` 测试仍有效**

`_filter_scan_tools` 是死代码但未被删除，测试仍有效（测试的是函数本身而非集成流程）。保留测试。

- [ ] **步骤 2：更新 `test_analysis_non_truncated_summary` 注释**

`test_analysis_e2e.py:6` 注释 `"""验证 _has_structure_data 时扫描工具被过滤""""` — 这个测试只是单元测试 `_filter_scan_tools` 函数，不变。

- [ ] **步骤 3：运行全部测试**

运行：`python -m pytest tests/v2/ -v 2>&1 | tail -30`
预期：全部 PASS
