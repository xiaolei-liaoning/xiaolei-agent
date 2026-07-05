# Prompt 架构重构 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将所有 prompt 从 Python 字符串常量重构为组合式独立 .txt 文件架构，新增 PromptBuilder 类管理加载和依赖解析。

**架构：** 33 个 .txt 文件按 system/tools/agents/blocks 四个目录组织。PromptBuilder 提供 lazy-load + 缓存 + `@requires` 依赖解析 + `str.format(**vars)` 运行时注入。

**技术栈：** Python 3.12, pytest, 现有 V2 agent 框架

**总计：** 13 个任务，预计 ~2h

---

### 任务 1：创建目录结构 + PromptBuilder

**文件：**
- 创建：`core/multi_agent_v2/prompts/__init__.py`
- 创建：`core/multi_agent_v2/prompts/builder.py`

- [ ] **步骤 1：创建目录**

```bash
mkdir -p prompts/system prompts/tools prompts/agents prompts/blocks
```

- [ ] **步骤 2：编写 `core/multi_agent_v2/prompts/builder.py`**

```python
"""PromptBuilder — 组合式 .txt prompt 加载和依赖解析"""
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CircularDependencyError(Exception):
    pass


class PromptNotFoundError(FileNotFoundError):
    pass


class PromptBuilder:
    def __init__(self, root_dir: str = "prompts"):
        self._root = Path(root_dir)
        self._cache: Dict[str, str] = {}

    def _resolve_path(self, path: str) -> Path:
        return (self._root / path).with_suffix(".txt")

    def load(self, path: str, _stack: Optional[list] = None) -> str:
        if path in self._cache:
            return self._cache[path]

        if _stack is None:
            _stack = []
        if path in _stack:
            raise CircularDependencyError(
                f"循环依赖: {' → '.join(_stack)} → {path}"
            )

        file_path = self._resolve_path(path)
        if not file_path.exists():
            raise PromptNotFoundError(
                f"Prompt 文件不存在: {file_path}"
            )

        raw = file_path.read_text(encoding="utf-8")

        lines = raw.split("\n")
        requires = []
        body_start = 0

        for i, line in enumerate(lines[:3]):
            stripped = line.strip()
            if stripped.startswith("@requires:"):
                deps = stripped[len("@requires:"):].strip()
                requires.extend(d.strip() for d in deps.split(",") if d.strip())
                body_start = i + 1
            elif stripped:
                break
        body = "\n".join(lines[body_start:])

        _stack.append(path)
        resolved_deps = {}
        for dep in requires:
            resolved_deps[dep] = self.load(dep, _stack)
        _stack.pop()

        for dep_path, dep_content in resolved_deps.items():
            marker = f"{{{{{dep_path}}}}}"
            if marker in body:
                body = body.replace(marker, dep_content)
            else:
                body += f"\n\n{dep_content}"

        self._cache[path] = body
        return body

    def assemble_system(self, modules: list[str]) -> str:
        return "\n\n".join(self.load(f"system/{m}") for m in modules)

    def get_tool_desc(self, name: str) -> str:
        return self.load(f"tools/{name}")

    def get_agent_prompt(self, agent_type: str) -> str:
        role = self.load(f"agents/{agent_type}")
        rules = self.load("agents/work_rules")
        return f"{role}\n\n{rules}"

    def get_block(self, block_name: str, **vars) -> str:
        return self.load(f"blocks/{block_name}").format(**vars)

    def clear_cache(self):
        self._cache.clear()


_builder: Optional[PromptBuilder] = None


def get_builder(root_dir: str = "prompts") -> PromptBuilder:
    global _builder
    if _builder is None:
        _builder = PromptBuilder(root_dir)
    return _builder
```

- [ ] **步骤 3：编写 `core/multi_agent_v2/prompts/__init__.py`**

```python
from .builder import PromptBuilder, get_builder, CircularDependencyError, PromptNotFoundError

__all__ = ["PromptBuilder", "get_builder", "CircularDependencyError", "PromptNotFoundError"]
```

- [ ] **步骤 4：验证导入**

```bash
python -c "from core.multi_agent_v2.prompts import PromptBuilder, get_builder; print('OK')"
```

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/prompts/ prompts/
git commit -m "feat: add PromptBuilder with lazy-load + @requires + cache"
```

---

### 任务 2：创建 system/*.txt（9 个文件）

**文件：**
- 创建：`prompts/system/base.txt`
- 创建：`prompts/system/code_gen.txt`
- 创建：`prompts/system/game_dev.txt`
- 创建：`prompts/system/report.txt`
- 创建：`prompts/system/plan.txt`
- 创建：`prompts/system/debug.txt`
- 创建：`prompts/system/plan_generation.txt`
- 创建：`prompts/system/fallback_report.txt`
- 创建：`prompts/system/fallback_summary.txt`

**说明：** 每个文件从现有 Python 常量逐字移植，英文重写（保持现有语义不变）。

- [ ] **步骤 1：编写 `prompts/system/base.txt`**

```
Think before acting:
1. What is the task goal? Where is the current progress?
2. Use tools when needed, answer when data is available, ask follow-ups when information is insufficient.
3. Output reasoning in <thinking> tags before calling tools.

Key rules:
- Every round MUST output tool calls or a final answer — never idle.
- When the task is clear, execute directly — don't describe "I will...".
- Create files with write_file, writing complete code in one go.
- Modify code with edit_file (exact string replacement).
- Never output truncated/incomplete code.
- When codebase exploration to gather context is needed, or for queries that aren't single-file/class/function lookups, prefer using the task tool to delegate to sub-agents rather than direct search, to reduce context usage.
- When multiple independent information needs exist, invoke multiple task tools concurrently in a single message.
- Once a task is delegated to a sub-agent, do not duplicate the same work. Wait for results or continue with non-overlapping tasks.
- Sub-agent results are not visible to the user — you must summarize the result with a text message to the user.
```

- [ ] **步骤 2：编写 `prompts/system/code_gen.txt`**

```
<code_generation_workflow>
Initial creation: Use write_file to write complete, runnable code in one go.
Modification/fix order: First read_file to verify current content → then edit_file(old_string, new_string) for precise replacement (old_string must provide enough surrounding context to ensure unique match).
Quality requirements: Feature-complete, no placeholders/TODOs, no syntax errors.
Error recovery: If content is truncated → rewrite completely, never leave "need to add yourself" notes.
</code_generation_workflow>
```

- [ ] **步骤 3：编写 `prompts/system/game_dev.txt`**

```
<game_quality_requirements>
1. MUST listen for interaction events (keydown / click / touchstart)
2. MUST have a render/update function, called after state changes
3. MUST have game state variables
4. No static display — user must be able to interact, and the UI must update after interaction
5. Self-check after generation: Event listeners? Render function? State variables? Interactable? UI updates?
</game_quality_requirements>
```

- [ ] **步骤 4：编写 `prompts/system/report.txt`**

```
<report_workflow>
1. First use web_search/fetch_url to get real data — never fabricate.
2. Use write_file to generate HTML report, embedding real data.
3. Style requirements: gradient background, card layout, responsive design.
</report_workflow>
```

- [ ] **步骤 5：编写 `prompts/system/plan.txt`**

```
<plan_mode>
Follow the plan steps in order. Do not repeat completed steps. Do not skip the current step.
</plan_mode>
```

- [ ] **步骤 6：编写 `prompts/system/debug.txt`**

```
<error_recovery>
If content is incomplete/truncated → rewrite completely. If tool fails → try an alternative approach.
</error_recovery>
```

- [ ] **步骤 7：编写 `prompts/system/plan_generation.txt`**

```
Analyze the following task and describe in natural language how to complete it step by step to achieve the user's goal.

Task: {task_description}
Available tools: {tool_list}

Rules:
- One step = one specific action.
- For codebase structure exploration, prefer codegraph_explore or task(agent='explore').
- For independent sub-tasks, use orchestrate for parallel execution.

Output format: step_number|description|tool_name
```

- [ ] **步骤 8：编写 `prompts/system/fallback_report.txt`** + **`prompts/system/fallback_summary.txt`**

`fallback_report.txt`:
```
Based on the following search result data, generate a complete HTML report using write_file.
Do not fabricate data — only use data that appears in the search results.
{context}
```

`fallback_summary.txt`:
```
Based on the tool execution results, provide a complete and detailed summary in Chinese. Do not skip any important information.
```

- [ ] **步骤 9：验证加载**

```bash
python -c "
from core.multi_agent_v2.prompts import get_builder
b = get_builder()
for n in ['base','code_gen','game_dev','report','plan','debug','plan_generation','fallback_report','fallback_summary']:
    print(f'system/{n}: {len(b.load(\"system/\"+n))} chars')
"
```

- [ ] **步骤 10：Commit**

```bash
git add prompts/system/*.txt
git commit -m "feat: create system prompt .txt files"
```

---

### 任务 3：创建 tools/*.txt（14 个文件）

**文件：** 创建 14 个 tool 描述文件。

**关键：** `tools/task.txt` 和 `tools/orchestrate.txt` 使用 `@requires` 引用 agent 描述。

- [ ] **步骤 1：编写 `prompts/tools/task.txt`**

```
@requires: agents/explore, agents/build, agents/analyze, agents/general

Launch a new agent to handle complex, multistep tasks autonomously.

When using the Task tool, you must specify a subagent_type parameter to select which agent type to use.

When NOT to use the Task tool:
- If you want to read a specific file path, use the Read tool instead to find the match more quickly.
- If you are searching for a specific class definition like "class Foo", use the Grep tool instead to find the match more quickly.
- If you are searching for code within a specific file or set of 2-3 files, use the Read tool instead to find the match more quickly.
- If no available agent is a good fit for the task, use other tools directly.

Usage notes:
1. Launch multiple agents concurrently whenever possible — use a single message with multiple tool calls.
2. Once you have delegated work to an agent, do not duplicate that work yourself. Continue with non-overlapping tasks, or wait for the result.
3. When the agent is done, it will return a single message back to you. The result is not visible to the user. To show the user the result, send a text message with a concise summary.
4. Each agent invocation starts with a fresh context unless you provide task_id to resume. When starting fresh, your prompt should contain all the information the agent needs and specify exactly what it should return.
5. The agent's outputs should generally be trusted.
6. Clearly tell the agent whether to write code or just do research — it is not aware of the user's intent. Tell it how to verify (e.g., relevant test commands).
7. If the agent description says it should be used proactively, use it proactively.

Available agent types:
{{agents/explore}}
{{agents/build}}
{{agents/analyze}}
{{agents/general}}
```

- [ ] **步骤 2：编写 `prompts/tools/orchestrate.txt`**

```
@requires: agents/explore, agents/build, agents/analyze, agents/general

Run multiple tasks in parallel or with dependencies using sub-agents.

Use this tool when you need to execute multiple independent or related tasks efficiently.
Tasks without dependencies run simultaneously. Tasks with dependencies wait for their prerequisites to complete before starting.

Each task gets its own sub-agent session with appropriate permissions.
Results from dependency tasks are automatically passed as context to dependent tasks.

When to use:
- Multiple independent research tasks (e.g., "explore codebase" + "search web" + "read docs")
- Pipeline tasks where each step depends on the previous (e.g., "read file" → "analyze" → "summarize")
- Mixed parallel + sequential workflows

When NOT to use:
- Single simple tasks (use the regular Task tool instead)
- Tasks that need to share mutable state (they can't — each has its own session)

Available agent types:
{{agents/explore}}
{{agents/build}}
{{agents/analyze}}
{{agents/general}}
```

- [ ] **步骤 3：编写其余 12 个 tool 文件**（保持原中文 description）

| 文件 | 内容 |
|------|------|
| `write_file.txt` | "新建文件并写入完整内容。\n- 适用于创建脚本、HTML 游戏、报告等新文件\n- content 是文件的**完整**内容，不可截断或留占位符\n- ⚠️ 只需修改文件某几行 → 用 edit_file，不要全文重写" |
| `read_file.txt` | "读取文件内容或浏览目录结构。\n- 支持指定 offset（行号）和 limit（行数）进行部分读取\n- 可读取图片和 PDF 文件\n- 以绝对路径为参数" |
| `edit_file.txt` | "精确字符串替换，修改文件中特定内容。\n- oldString 必须精确匹配文件内容（含缩进/空格）\n- oldString 需提供足够上下文确保唯一匹配\n- 支持 replaceAll 参数批量替换\n- ⚠️ 创建新文件 → 用 write_file" |
| `execute_python.txt` | "安全执行 Python 代码。\n- 适用于运行脚本、测试算法、pip 安装包、操作桌面文件\n- mode=sandbox（默认）：沙盒隔离，无法访问桌面/网络\n- mode=local：真实环境，可写 ~/Desktop，可访问网络\n- ⚠️ 需运行系统命令(ls/pwd/git) → 用 execute_shell\n- ⚠️ 抓取网页/API 数据 → 用 fetch_url" |
| `execute_shell.txt` | "执行 Shell 系统命令。\n- 适用于文件操作(cp/mv/mkdir)、运行脚本、包管理(npm/pip/git)\n- 命令在子进程运行，超时自动终止（默认120s）\n- ⚠️ 执行 Python 代码 → 用 execute_python\n- ⚠️ 危险命令(rm -rf /)会被拦截" |
| `web_search.txt` | "联网搜索获取实时信息。\n- 返回搜索结果摘要，包含标题、URL、内容片段\n- 数据获取后，写入报告用 fetch_url 获取详情" |
| `fetch_url.txt` | "HTTP GET 获取网页或 API 数据。\n- 用于抓取搜索结果中的具体页面内容\n- ⚠️ 仅支持 HTTP GET，不支持 POST/登录" |
| `search_files.txt` | "搜索文件。两种模式**二选一**：\n- glob 模式：按文件名通配符搜索（如 src/**/*.py）\n- grep 模式：按文件内容正则搜索（如 class\\s+\\w+）" |
| `git.txt` | "Git 版本控制操作。\n- commit 时需先检查 git status、git diff、git log\n- 不要修改 git config、不要 force-push、不要创建空 commit\n- 使用 gh 命令处理 GitHub PR/issues/releases" |
| `write_todos.txt` | "【自动跟踪】任务进度由系统自动管理，无需手动调用此工具。" |
| `arbor_viz.txt` | "【ARBOR 假设树可视化】生成交互式 HTML 树形图，展示 ARBOR 推理的预测/选择/实施过程。" |
| `text_analyzer.txt` | "深度文本分析（基于 LLM）。可分析文档内容、提取关键信息、生成摘要。" |

- [ ] **步骤 4：验证加载（含 @requires 解析）**

```bash
python -c "
from core.multi_agent_v2.prompts import get_builder
b = get_builder()
b.clear_cache()
for name in ['task','orchestrate','write_file','read_file','edit_file','execute_python','execute_shell','web_search','fetch_url','search_files','git','write_todos','arbor_viz','text_analyzer']:
    c = b.load(f'tools/{name}')
    print(f'tools/{name}: {len(c)} chars')
# 验证 task 已内联 agent 描述
td = b.load('tools/task')
assert 'explore' in td.lower() and 'build' in td.lower()
assert '{{agents/' not in td
print('@requires resolution OK')
"
```

- [ ] **步骤 5：Commit**

```bash
git add prompts/tools/*.txt
git commit -m "feat: create tool description .txt files with @requires deps"
```

---

### 任务 4：创建 agents/*.txt + blocks/*.txt（10 个文件）

**文件：**
- 创建：`prompts/agents/explore.txt`, `build.txt`, `analyze.txt`, `general.txt`, `work_rules.txt`
- 创建：`prompts/blocks/architecture.txt`, `parent_context.txt`, `execution_status.txt`, `failed_approaches.txt`, `style_guide.txt`

- [ ] **步骤 1：编写 agents/explore.txt**

```
You are a file search specialist. You excel at thoroughly navigating and exploring codebases.

Your strengths:
- Rapidly finding files using glob patterns
- Searching code and text with powerful regex patterns
- Reading and analyzing file contents

Guidelines:
- Use Glob for broad file pattern matching. Use Grep for searching file contents with regex.
- Use Read when you know the specific file path you need to read.
- Use Bash for file operations like copying, moving, or listing directory contents.
- Adapt your search approach based on the thoroughness level specified by the caller.
- Return file paths as absolute paths in your final response.
- For clear communication, avoid using emojis.
- Do not create any files, or run bash commands that modify the user's system state in any way.

Complete the user's search request efficiently and report your findings clearly.
```

- [ ] **步骤 2：编写 agents/build.txt**

```
You are a build engineer. You write code, fix bugs, implement features, and refactor codebases.

Your strengths:
- Reading and understanding existing code
- Writing clean, functional code that follows existing patterns
- Running tests and verifying your work
- Making precise edits with edit_file

Guidelines:
- Read before you write — understand existing patterns first.
- Write complete, working code — no placeholders, no TODOs.
- Verify your work — run relevant tests after making changes.
- Return a clear summary of what you built or changed.
- Do not use emojis unless asked.
```

- [ ] **步骤 3：编写 agents/analyze.txt**

```
You are a code analyst. You deeply read, search, and analyze code to produce structured findings.

Your strengths:
- Thorough code review and analysis
- Identifying patterns, risks, and dependencies
- Producing structured, prioritized conclusions

Guidelines:
- Read widely before concluding — don't draw conclusions from a single file.
- Present findings in order of importance.
- Include file paths and line numbers for key findings.
- Do not edit or create any files.
- Do not use emojis unless asked.
```

- [ ] **步骤 4：编写 agents/general.txt**

```
You are a general-purpose developer agent. You handle complex, multi-step tasks that mix research and implementation.

Your strengths:
- Executing end-to-end workflows autonomously
- Switching between research, analysis, and code writing as needed
- Using all available tools effectively

Guidelines:
- Plan your approach before executing.
- Verify your work at key checkpoints.
- Return a comprehensive final message with all findings and changes.
- Do not use emojis unless asked.
```

- [ ] **步骤 5：编写 agents/work_rules.txt**

```
## Work Requirements
1. Return only ONE final message to the main agent. Include all your findings in detail.
2. Do not split your response into multiple messages. Do not ask follow-up questions.
3. Do not re-fetch information already in the parent agent's context — that is already known to the main agent.
4. Start working immediately. After completing necessary tool calls, return your final conclusions in one last message.
5. If the task involves writing code, run tests to verify after completion.
6. If you encounter a clear blocker (API unavailable, permission denied), state it in your final message — do not loop endlessly.
7. Your output will be embedded directly in the main agent's context, so information must be complete and accurate for the main agent to use.
```

- [ ] **步骤 6：编写 blocks/architecture.txt**（**新增** — LLM 系统心智模型）

```
<system_architecture>
You run inside a ReAct (Reasoning + Acting) loop. Each round:
1. You receive the system prompt + user message + conversation history.
2. You output either tool calls OR a final text answer.
3. If tool calls: each call passes through a middleware chain (Hook → LoopDetection → Clarification → Todo → Memory) before execution.
4. Tool results return to context. The loop repeats.

Key behaviors:
- Plan steps: if an active plan exists, completed steps auto-advance. Failed steps trigger auto-replan. Do NOT manually mark steps — the system handles this.
- Todo tracker: auto-managed. Use todowrite only if explicitly needed.
- Memory: conversation history older than 16 turns is compressed into a summary. Do not rely on very old context being verbatim.
- Validation: if write_file produces truncated/invalid content, <forced_instructions> will ask you to retry.

Sub-agent behavior:
- task and orchestrate spawn sub-agents. Each runs its own independent ReAct loop with fresh context.
- Sub-agent results are returned as structured XML. These results are NOT visible to the user — you must read them and summarize for the user.
- Sub-agents do not inherit your conversation history. Include all necessary context in the prompt parameter.
</system_architecture>
```

- [ ] **步骤 7：编写 blocks/parent_context.txt**

```
## Parent Agent Context (you do NOT need to re-acquire this)
- Main agent's original task: {task}
- Main agent's completed work: {conversation}
- Key information already known: {tool_results}
- Discovered artifacts: {artifacts}
```

- [ ] **步骤 8：编写 blocks/execution_status.txt**

```
<current_date>{date}</current_date>
<execution_status>Executed {total} rounds: {success} succeeded/{fail} failed, tools: {tools}</execution_status>
```

- [ ] **步骤 9：编写 blocks/failed_approaches.txt**

```
<failed_approaches>
The following approaches have already failed. Do NOT retry them:
{approaches}
</failed_approaches>
```

- [ ] **步骤 10：编写 blocks/style_guide.txt**

```
<output_style>
Be concise and direct. Keep responses short (CLI display).
Answer directly without preamble or postamble. No "The answer is...", no "Here is what I will do...".
Only use emojis if explicitly requested.
Do not add code comments unless asked.
After working on a file, stop — do not explain what you did unless asked.
</output_style>
```

- [ ] **步骤 11：验证加载**

```bash
python -c "
from core.multi_agent_v2.prompts import get_builder
b = get_builder(); b.clear_cache()
for g,n in [('agents','explore'),('agents','build'),('agents','analyze'),('agents','general'),('agents','work_rules'),('blocks','architecture'),('blocks','parent_context'),('blocks','execution_status'),('blocks','failed_approaches'),('blocks','style_guide')]:
    print(f'{g}/{n}: {len(b.load(f\"{g}/{n}\"))} chars')
# 验证 get_agent_prompt 组合
ap = b.get_agent_prompt('explore')
assert 'explore' in ap.lower() and 'work requirements' in ap.lower()
print('get_agent_prompt OK')
"
```

- [ ] **步骤 12：Commit**

```bash
git add prompts/agents/*.txt prompts/blocks/*.txt
git commit -m "feat: create agent role prompts and shared blocks"
```

---

### 任务 5：编写 PromptBuilder 单元测试

**文件：**
- 创建：`tests/v2/test_prompt_builder.py`

- [ ] **步骤 1：编写测试文件**

```python
"""PromptBuilder 单元测试"""
import tempfile
import pytest
from pathlib import Path
from core.multi_agent_v2.prompts.builder import (
    PromptBuilder, CircularDependencyError, PromptNotFoundError
)


@pytest.fixture
def builder():
    tmp = Path(tempfile.mkdtemp())
    for d in ["system", "tools", "agents", "blocks"]:
        (tmp / d).mkdir(exist_ok=True)
    (tmp / "system" / "base.txt").write_text("Base prompt content.")
    (tmp / "system" / "code_gen.txt").write_text("Code generation rules.")
    (tmp / "agents" / "explore.txt").write_text("You are an explorer.")
    (tmp / "agents" / "build.txt").write_text("You are a builder.")
    (tmp / "agents" / "work_rules.txt").write_text("Work rules content.")
    (tmp / "blocks" / "status.txt").write_text("Status: {value}")
    (tmp / "tools" / "task.txt").write_text(
        "@requires: agents/explore, agents/build\n"
        "Task description.\n"
        "{{agents/explore}}\n"
        "{{agents/build}}"
    )
    (tmp / "tools" / "circular_a.txt").write_text("@requires: tools/circular_b\nA content.")
    (tmp / "tools" / "circular_b.txt").write_text("@requires: tools/circular_a\nB content.")
    return PromptBuilder(str(tmp))


class TestPromptBuilder:
    def test_load_simple(self, builder):
        assert builder.load("system/base") == "Base prompt content."

    def test_load_cached(self, builder):
        builder.load("system/base")
        assert "system/base" in builder._cache

    def test_load_not_found(self, builder):
        with pytest.raises(PromptNotFoundError):
            builder.load("system/nonexistent")

    def test_load_with_deps(self, builder):
        content = builder.load("tools/task")
        assert "Task description." in content
        assert "You are an explorer." in content
        assert "You are a builder." in content
        assert "{{agents/" not in content

    def test_circular_dependency(self, builder):
        with pytest.raises(CircularDependencyError) as exc:
            builder.load("tools/circular_a")
        assert "circular_a" in str(exc.value)

    def test_assemble_system(self, builder):
        content = builder.assemble_system(["base", "code_gen"])
        assert "Base prompt content." in content
        assert "Code generation rules." in content

    def test_get_tool_desc(self, builder):
        content = builder.get_tool_desc("task")
        assert "Task description." in content
        assert "You are an explorer." in content

    def test_get_agent_prompt(self, builder):
        content = builder.get_agent_prompt("explore")
        assert "You are an explorer." in content
        assert "Work rules content." in content

    def test_get_block_with_vars(self, builder):
        assert builder.get_block("status", value="running") == "Status: running"

    def test_clear_cache(self, builder):
        builder.load("system/base")
        builder.clear_cache()
        assert "system/base" not in builder._cache
```

- [ ] **步骤 2：运行测试**

```bash
pytest tests/v2/test_prompt_builder.py -v
```
预期：10 tests pass

- [ ] **步骤 3：Commit**

```bash
git add tests/v2/test_prompt_builder.py
git commit -m "test: add PromptBuilder unit tests (10 scenarios)"
```

---

### 任务 6：替换 react_core.py — 删除常量，改用 PromptBuilder

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py`

- [ ] **步骤 1：删除 7 个 _XXX_PROMPT 常量（line 62-136）**

删除从 `_BASE_PROMPT = (` 到 `_DEBUG_PROMPT = (` 结束的全部内容（`_BASE_PROMPT` + `_TASK_GUIDANCE_PROMPT` + `_CODE_GEN_PROMPT` + `_GAME_DEV_PROMPT` + `_REPORT_PROMPT` + `_PLAN_PROMPT` + `_DEBUG_PROMPT`）。

- [ ] **步骤 2：在文件顶部添加 import**

```python
from core.multi_agent_v2.prompts import get_builder
```

- [ ] **步骤 3：替换 `on_llm_invoke()` 中模块组装逻辑（line 316-379）**

旧代码：
```python
        # ── 按任务类型组装提示词模块 ──
        # ponytail: 角色 .md 定义优先于 _BASE_PROMPT
        if getattr(ctx, 'personality_prompt'):
            modules = []
            if _task_flags.get("code"):
                modules.append(_CODE_GEN_PROMPT)
                if _task_flags.get("game"):
                    modules.append(_GAME_DEV_PROMPT)
            if _task_flags.get("report"):
                modules.append(_REPORT_PROMPT)
        else:
            modules = [_BASE_PROMPT]
            if _task_flags.get("code"):
                modules.append(_CODE_GEN_PROMPT)
                if _task_flags.get("game"):
                    modules.append(_GAME_DEV_PROMPT)
            if _task_flags.get("report"):
                modules.append(_REPORT_PROMPT)

        # 子代理工具可用 → 注入使用指南
        if ctx.tool_defs:
            _tool_names = {t.get("function", {}).get("name", "")
                           for t in ctx.tool_defs}
            if "task" in _tool_names:
                modules.append(_TASK_GUIDANCE_PROMPT)

        # ... [连续失败处理保持不变] ...

        if ctx.plan:
            modules.append(_PLAN_PROMPT)
        if ctx.forced_instructions or ctx.warnings:
            modules.append(_DEBUG_PROMPT)

        system_content = "\n\n".join(modules)

        # 注入强制指令
        if ctx.forced_instructions:
            system_content += f"\n\n<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>"
            ctx._fi_consumed = True

        # 注入警告信息
        if ctx.warnings:
            warnings_text = "\n".join(ctx.warnings)
            system_content += f"\n\n<warnings>\n{warnings_text}\n</warnings>"
            ctx.warnings.clear()

        if ctx.personality_prompt:
            system_content = f"{ctx.personality_prompt}\n\n{system_content}"
```

新代码：
```python
        builder = get_builder()

        # ── 按任务类型组装提示词模块 ──
        if getattr(ctx, 'personality_prompt'):
            modules = []
            if _task_flags.get("code"):
                modules.append("code_gen")
                if _task_flags.get("game"):
                    modules.append("game_dev")
            if _task_flags.get("report"):
                modules.append("report")
        else:
            modules = ["base"]
            modules.append("architecture")  # ponytail: system architecture awareness
            if _task_flags.get("code"):
                modules.append("code_gen")
                if _task_flags.get("game"):
                    modules.append("game_dev")
            if _task_flags.get("report"):
                modules.append("report")

        # ponytail: task guidance now lives in tools/task.txt description
        # (LLM gets it via tool definition, no need to inject into system prompt)

        # ... [连续失败处理保持不变] ...

        if ctx.plan:
            modules.append("plan")
        if ctx.forced_instructions or ctx.warnings:
            modules.append("debug")

        system_content = builder.assemble_system(modules)

        # 注入强制指令
        if ctx.forced_instructions:
            system_content += f"\n\n<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>"
            ctx._fi_consumed = True

        # 注入警告信息
        if ctx.warnings:
            warnings_text = "\n".join(ctx.warnings)
            system_content += f"\n\n<warnings>\n{warnings_text}\n</warnings>"
            ctx.warnings.clear()

        if ctx.personality_prompt:
            system_content = f"{ctx.personality_prompt}\n\n{system_content}"
```

**注意：** `blocks/architecture.txt` 作为系统模块被 `assemble_system()` 加载。需要在 `assemble_system()` 中支持加载 blocks。方案：在 system 目录下创建 `prompts/system/architecture.txt`，内容为一行 `<system_architecture>`...`</system_architecture>`，或修改 `assemble_system` 允许跨目录引用。

**最终采用：** 直接在 `react_core.py` 中追加 `blocks/architecture`:

```python
        system_content = builder.assemble_system(modules)
        system_content += "\n\n" + builder.load("blocks/architecture")
```

- [ ] **步骤 4：运行现有测试验证系统 prompt 组装正确**

```bash
pytest tests/v2/test_react_core_mock.py -v -k "test_llm_invoke or test_system_prompt" 2>&1 | head -50
```

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py
git commit -m "refactor: replace prompt constants with PromptBuilder in react_core"
```

---

### 任务 7：替换 spawn.py — 子代理 prompt 改用 builder

**文件：**
- 修改：`core/multi_agent_v2/agents/subagent/spawn.py`

- [ ] **步骤 1：删除 7 条工作规则（line 171-180）和 `_build_parent_context` 内联（line 63-94）**

- [ ] **步骤 2：替换 `spawn_subagent()` 中 `full_task` 组装逻辑（line 130-181）**

旧代码：
```python
    full_task = hint
    if allowed:
        full_task += (
            "\n\n## 可用工具\n"
            f"你可以使用以下工具：{', '.join(sorted(allowed))}。\n"
            "不在列表中的工具不可用。"
        )
    if disallowed:
        full_task += (
            f"\n以下工具明确禁止使用：{', '.join(sorted(disallowed))}。\n"
        )
    parent_ctx = _build_parent_context()
    if parent_ctx:
        full_task += parent_ctx
    full_task += (
        "\n\n## 工作要求\n"
        "1. 你只返回一条最终消息...\n"
        # ... 7 rules ...
    )
    full_task += f"\n\n---\n## 主代理分配给你的任务\n\n{task_description}"
```

新代码：
```python
    from core.multi_agent_v2.prompts import get_builder
    builder = get_builder()

    # 角色 prompt（agent_type + work_rules 组合）
    full_task = builder.get_agent_prompt(profile.value)

    # 工具范围
    if allowed:
        full_task += f"\n\n## Available Tools\nAllowed: {', '.join(sorted(allowed))}.\n"
    if disallowed:
        full_task += f"\nDisallowed: {', '.join(sorted(disallowed))}.\n"

    # 父代理上下文
    parent_ctx = builder.get_block("parent_context", **{
        "task": (ctx or {}).get("task", "")[:500],
        "conversation": (ctx or {}).get("conversation", "")[:1000],
        "tool_results": (ctx or {}).get("tool_results", "")[:2000],
        "artifacts": "",
    })
    full_task += parent_ctx

    # 主代理任务
    full_task += f"\n\n---\n## Task from Main Agent\n\n{task_description}"
```

**注意：** `hint` 变量（原 `system_hint`）已被 `builder.get_agent_prompt()` 替代。

- [ ] **步骤 3：删除 `_build_parent_context()` 函数（line 63-94）**

- [ ] **步骤 4：Commit**

```bash
git add core/multi_agent_v2/agents/subagent/spawn.py
git commit -m "refactor: replace sub-agent prompt assembly with PromptBuilder"
```

---

### 任务 8：替换 tool_registry.py — tool descriptions 改用 builder

**文件：**
- 修改：`core/multi_agent_v2/tools/tool_registry.py`

- [ ] **步骤 1：删除 task/orchestrate 条目（line 1510-1554）+ 旧 handler（line 1430-1481）**

从 `_SANDBOX_TOOL_DEFS` 列表中删除 task 和 orchestrate 的 ToolDefinition。deleter the old `_handle_task()` and `_handle_orchestrate()` functions.

- [ ] **步骤 2：修改其余 12 个 tool 的 `description=` 字段**

搜索所有 `description="【` 开头或直接字符串的 description，全部改为：

```python
from core.multi_agent_v2.prompts import get_builder
_builder = get_builder()

# 示例：
ToolDefinition(
    name="write_file",
    ...
    description=_builder.get_tool_desc("write_file"),
    ...
)
```

**关键：** 12 处修改，一一对应 12 个保留的 tool。

- [ ] **步骤 3：验证**

```bash
python -c "
from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
for t in _SANDBOX_TOOL_DEFS:
    print(f'{t.name}: {t.description[:50]}...')
"
```
预期：每个 tool 输出从 .txt 加载的 description，不包含旧的 `description="..."` 内联字符串。

- [ ] **步骤 4：Commit**

```bash
git add core/multi_agent_v2/tools/tool_registry.py
git commit -m "refactor: replace inline tool descriptions with PromptBuilder; remove stale task/orchestrate definitions"
```

---

### 任务 9：清理 tool_handler.py — 删除 task/orchestrate 覆盖逻辑

**文件：**
- 修改：`core/multi_agent_v2/agents/subagent/tool_handler.py`

- [ ] **步骤 1：删除 `_AGENT_TYPE_DESCRIPTIONS` 字典 + `_AGENT_TYPES_LIST`（line 98-108）**

- [ ] **步骤 2：删除 `_build_task_description()` 和 `_build_orchestrate_description()`（line 111-157）**

- [ ] **步骤 3：修改 `get_task_tool_def()` 和 `get_orchestrate_tool_def()` 的 description**

将 `description=_build_task_description()` 改为：
```python
from core.multi_agent_v2.prompts import get_builder
_builder = get_builder()

# 在 get_task_tool_def():
description=_builder.get_tool_desc("task"),

# 在 get_orchestrate_tool_def():
description=_builder.get_tool_desc("orchestrate"),
```

- [ ] **步骤 4：`register_subagent_tools()` 保持不变**

`register_subagent_tools()` 不需要改——它仍然注册 task/orchestrate 两个工具，但 ToolDefinition 现在从 .txt 加载 description。

- [ ] **步骤 5：验证**

```bash
python -c "
from core.multi_agent_v2.agents.subagent.tool_handler import get_task_tool_def, get_orchestrate_tool_def
td = get_task_tool_def()
assert 'When NOT to use' in td.description
assert 'explore' in td.description
print(f'task: {len(td.description)} chars OK')
od = get_orchestrate_tool_def()
assert 'When to use' in od.description
print(f'orchestrate: {len(od.description)} chars OK')
"
```

- [ ] **步骤 6：Commit**

```bash
git add core/multi_agent_v2/agents/subagent/tool_handler.py
git commit -m "refactor: replace dynamic tool desc builders with PromptBuilder; delete _AGENT_TYPE_DESCRIPTIONS"
```

---

### 任务 10：替换 plan_manager.py — plan 生成 prompt 改用 builder

**文件：**
- 修改：`core/multi_agent_v2/agents/plan_manager.py`

- [ ] **步骤 1：找到 `generate_plan()` 中内联的 LLM prompt（line 72-156）**

**步骤 2：替换为 PromptBuilder**

```python
from core.multi_agent_v2.prompts import get_builder

builder = get_builder()
plan_prompt = builder.get_block("plan_generation",  # ponytail: moved to system/plan_generation.txt
    task_description=task_description,
    tool_list=tool_list_str,
).format(task_description=task_description, tool_list=tool_list_str)

# 实际实现中两块 prompt 都用 builder.load()
```

**注意：** `plan_generation.txt` 已在任务 2 创建。如果需要 `str.format` 变量替换，使用 `builder.get_block()` 或直接 `builder.load().format()`。

- [ ] **步骤 2：验证**

```bash
python -c "
from core.multi_agent_v2.prompts import get_builder
b = get_builder()
p = b.load('system/plan_generation').format(task_description='test task', tool_list='grep, glob')
assert 'test task' in p and 'grep' in p
print('plan_generation format OK')
"
```

- [ ] **步骤 3：Commit**

```bash
git add core/multi_agent_v2/agents/plan_manager.py
git commit -m "refactor: replace inline plan generation prompt with PromptBuilder"
```

---

### 任务 11：替换 subagent/types.py — system_hint 改用 builder

**文件：**
- 修改：`core/multi_agent_v2/agents/subagent/types.py`

- [ ] **步骤 1：删除 `_load_profile_hint()`（line 24-41）**

- [ ] **步骤 2：修改 `PROFILE_PERMISSIONS` 中的 `system_hint`**

```python
from core.multi_agent_v2.prompts import get_builder

_builder = get_builder()

PROFILE_PERMISSIONS = {
    AgentProfile.EXPLORE: {
        "allowed": ["read_file", "search_files", "glob", "fetch_url", "web_search", "grep", "bash"],
        "disallowed": ["write_file", "edit_file", "execute_python", "execute_shell", "task", "orchestrate"],
        "system_hint": _builder.get_agent_prompt("explore"),
    },
    AgentProfile.BUILD: {
        "allowed": None, "disallowed": None,
        "system_hint": _builder.get_agent_prompt("build"),
    },
    AgentProfile.ANALYZE: {
        "allowed": None,
        "disallowed": ["write_file", "edit_file", "execute_shell"],
        "system_hint": _builder.get_agent_prompt("analyze"),
    },
    AgentProfile.GENERAL: {
        "allowed": None, "disallowed": None,
        "system_hint": _builder.get_agent_prompt("general"),
    },
    AgentProfile.ORCHESTRATOR: {
        "allowed": ["read_file", "write_file", "task", "orchestrate"],
        "disallowed": None,
        "system_hint": _builder.get_agent_prompt("general"),
    },
}
```

- [ ] **步骤 3：验证**

```bash
python -c "
from core.multi_agent_v2.agents.subagent.types import PROFILE_PERMISSIONS, AgentProfile
hint = PROFILE_PERMISSIONS[AgentProfile.EXPLORE]['system_hint']
assert 'file search specialist' in hint.lower()
assert 'work requirements' in hint.lower()
print('system_hint OK')
"
```

- [ ] **步骤 4：Commit**

```bash
git add core/multi_agent_v2/agents/subagent/types.py
git commit -m "refactor: replace _load_profile_hint with PromptBuilder.get_agent_prompt"
```

---

### 任务 12：清理 + 全量测试

- [ ] **步骤 1：确认无残留 import 旧常量**

```bash
grep -rn "_BASE_PROMPT\|_TASK_GUIDANCE_PROMPT\|_CODE_GEN_PROMPT\|_GAME_DEV_PROMPT\|_REPORT_PROMPT\|_PLAN_PROMPT\|_DEBUG_PROMPT\|_AGENT_TYPE_DESCRIPTIONS\|_build_task_description\|_build_orchestrate_description\|_load_profile_hint" core/ --include="*.py"
```
预期：无匹配

- [ ] **步骤 2：运行全部 V2 测试**

```bash
pytest tests/v2/ -v --tb=short
```
预期：87+ 测试通过（原有 87 + 新增 10）

- [ ] **步骤 3：端到端 CLI 验证**

```bash
python -m cli.main "list files in src" --max-rounds 2
```
预期：正常输出，不报 ImportError 或 PromptNotFoundError

- [ ] **步骤 4：子代理功能验证**

```bash
python -m cli.main "用 task 工具探索 src 目录结构" --max-rounds 3
```
预期：task 工具正确识别 subagent_type，返回子代理结果

- [ ] **步骤 5：Commit**

```bash
git add -A
git commit -m "chore: cleanup old prompt constants, final verification"
```

---

### 任务 13：最终验证 — 全量测试

- [ ] **步骤 1：运行全部测试套件**

```bash
pytest tests/v2/ -v 2>&1 | tail -20
```

- [ ] **步骤 2：确认无回归**

```bash
git diff --stat HEAD~12
```
预期：~20 文件修改，~330 行删除，~35 文件新增
