# Prompt 架构重构：组合式 .txt 文件系统

**日期**: 2026-07-05
**目标**: 将 prompt 从 Python 字符串常量重构为 OpenCode 同款的组合式独立 .txt 文件架构，让 LLM 理解自己运行在什么样的系统里（而非"内定好的"执行木偶）。

## 当前问题

1. **20 个注入点**散布在 react_core.py、spawn.py、plan_manager.py、tool_handler.py 中，全为硬编码 Python 字符串
2. LLM 没有系统架构心智模型 — 不知道 middleware 链、ReAct 循环、plan step 自动推进
3. Tool description 写得像 API 文档而非 onboarding 手册 — 少负例、少行为契约
4. task/orchestrate 定义有两套冲突 schema（`_SANDBOX_TOOL_DEFS` vs `tool_handler.py`），靠覆盖逻辑救命
5. 子代理 role prompt 来自两套机制（`_AGENT_TYPE_DESCRIPTIONS` + `~/.xiaolei/roles/*.md`），维护不一致

## 目标架构

```
prompts/
  system/
    base.txt                    ← 核心行为规则（原 _BASE_PROMPT）
    code_gen.txt                ← 写代码/修代码工作流（原 _CODE_GEN_PROMPT）
    game_dev.txt                ← 游戏开发质量要求（原 _GAME_DEV_PROMPT）
    report.txt                  ← 报告生成工作流（原 _REPORT_PROMPT）
    plan.txt                    ← plan 模式规则（原 _PLAN_PROMPT）
    debug.txt                   ← 错误恢复指令（原 _DEBUG_PROMPT）
    plan_generation.txt         ← plan 生成 prompt（原 plan_manager.py 内联）
    fallback_report.txt         ← fallback 报告生成 prompt
    fallback_summary.txt        ← fallback 总结 prompt

  tools/
    task.txt                    ← task 工具：含 agent type 列表 + "何时不要用"
    orchestrate.txt             ← orchestrate 工具：DAG 语义 + "何时不要用"
    write_file.txt, read_file.txt, edit_file.txt
    execute_python.txt, execute_shell.txt
    web_search.txt, fetch_url.txt
    search_files.txt, git.txt
    write_todos.txt, arbor_viz.txt, text_analyzer.txt

  agents/
    explore.txt                 ← "You are a file search specialist..."
    build.txt                   ← "You are a build engineer..."
    analyze.txt                 ← "You are a code analyst..."
    general.txt                 ← "You are a general-purpose developer..."
    work_rules.txt              ← 7 条子代理行为规则（原 spawn.py 内联）

  blocks/
    architecture.txt            ← **新增**：系统架构描述（ReAct 循环/middleware/plan 流程）
    parent_context.txt          ← 子代理父上下文格式（原 spawn.py _build_parent_context）
    execution_status.txt        ← 执行状态块（轮数/成功/失败）
    failed_approaches.txt       ← 失败尝试记录块
    style_guide.txt             ← 输出风格约束（简洁/无 emoji/无解释）
```

## PromptBuilder API

**位置**: `core/multi_agent_v2/prompts/builder.py`，约 100 行。

```python
class PromptBuilder:
    def __init__(self, root_dir: str = "prompts")

    def load(self, path: str) -> str
        # 加载单个 .txt，解析 @requires 声明并递归内联依赖
        # 启动时一次性加载全部并缓存

    def assemble_system(self, modules: list[str]) -> str
        # 组装 system prompt：每个模块用 "\n\n" 连接

    def get_tool_desc(self, name: str) -> str
        # 给 ToolDefinition.description 用

    def get_agent_prompt(self, agent_type: str) -> str
        # 子代理 role prompt：agent.txt + work_rules.txt

    def get_block(self, block_name: str, **vars) -> str
        # 运行时注入的块，支持 str.format(**vars)
```

### @requires 机制

每个 .txt 文件顶部可选声明依赖行（以 `@requires:` 开头，第 1-3 行解析，遇到非 `@requires` 行即停止）：

```
@requires: agents/explore, agents/build
@requires: blocks/style_guide

（文件主体内容开始...）
```

`load()` 解析依赖后：
- 若正文有 `{{path}}` 标记（如 `{{agents/explore}}`），注入该位置
- 若正文无标记，追加到文件末尾
- 循环依赖检测：解析时记录访问栈，重复路径即抛 `CircularDependencyError`
- 缓存机制：模块首次 `load()` 时加载、解析依赖、组装、存入 `_cache`。后续调用直接返回缓存结果。所有 .txt 在首次被引用时懒加载，而非启动时全量预加载。

## 集成点改动

### 删除

| 文件 | 删除内容 | 行数 |
|------|---------|------|
| `react_core.py` | 7 个 `_XXX_PROMPT` 模块常量 | ~75 |
| `tool_registry.py` | task/orchestrate 条目 + 旧 handler（line 1430-1481, 1510-1554） | ~70 |
| `tool_handler.py` | `_build_task_description()`, `_build_orchestrate_description()`, `_AGENT_TYPE_DESCRIPTIONS`（line 98-157） | ~60 |
| `subagent/spawn.py` | 7 条工作规则（line 171-181）, `_build_parent_context()` | ~20 |
| `subagent/types.py` | `_load_profile_hint()`（line 24-41） | ~18 |
| `plan_manager.py` | plan 生成内联 prompt（line 72-156） | ~85 |

**总计删除 ~330 行 Python 字符串。**

### 修改

| 文件 | 改动 |
|------|------|
| `react_core.py` | 模块选择改用 `builder.assemble_system(modules)`；XML 块（forced_instructions/warnings）改用 `builder.get_block()` |
| `tool_registry.py` | `_SANDBOX_TOOL_DEFS` 中保留的 12 个 tool 的 `description=` 改为 `builder.get_tool_desc(name)` |
| `subagent/spawn.py` | `full_task` 组装改用 `builder.get_agent_prompt(agent_type)` |
| `subagent/types.py` | `system_hint` 改为 `builder.get_agent_prompt(profile)` |
| `plan_manager.py` | plan 生成 prompt 改用 `builder.load("system/plan_generation")` |

### 新增

| 文件 | 说明 |
|------|------|
| `core/multi_agent_v2/prompts/__init__.py` | 暴露 `builder` 单例 |
| `core/multi_agent_v2/prompts/builder.py` | PromptBuilder 类，~100 行 |
| `prompts/system/*.txt` | 9 个 system 模块 |
| `prompts/tools/*.txt` | 14 个 tool 描述 |
| `prompts/agents/*.txt` | 5 个 agent prompt |
| `prompts/blocks/*.txt` | 5 个共享块 |
| `tests/v2/test_prompt_builder.py` | PromptBuilder 单元测试 |

## task/orchestrate Schema 冲突修复

**现状**: `_SANDBOX_TOOL_DEFS` 中的 task/orchestrate 参数 schema 与 handler 代码不匹配：

| | `_SANDBOX_TOOL_DEFS` | `tool_handler.py` | 实际 handler 需要 |
|---|---|---|---|
| task 任务参数 | `description`（单字段） | `description` + `prompt`（双字段） | `prompt` 或 `description` |
| task agent 参数 | `agent` | `subagent_type` | `subagent_type` |
| task 额外参数 | 无 | `task_id`, `background` | 可选 |
| orchestrate 任务 | `task1..task5` 扁平字符串 | `tasks` JSON 数组 DAG | `tasks` 数组 |

`_HANDLER_MAP` 优先使用 `_SANDBOX_TOOL_DEFS` 的旧 handler（line 1997-1998），导致新 schema 的 `prompt`/`subagent_type` 参数被旧 handler 吞掉。

**修复**: 从 `_SANDBOX_TOOL_DEFS` 中删除 task/orchestrate 条目及旧 handler。工具由 `register_subagent_tools()` 注册的 tool_handler.py 版本作为唯一定义，handler 通过 `self._tools` fallback 路径获取。不再需要覆盖逻辑。

## 迁移策略（4 步，每步可独立验证）

### Step 1: 创建 .txt 文件（不改任何代码）
- 从现有 Python 常量逐字提取内容到对应 .txt 文件
- 每个文件注释出处：`# migrated from react_core.py:62`
- 验证：所有文件存在、内容完整

### Step 2: 实现 PromptBuilder + 跑通测试（旧代码仍在）
- 实现 `builder.py`，从 `prompts/` 加载并缓存
- 测试验证：`builder.load("system/base")` 输出 == 旧 `_BASE_PROMPT` 字符串
- 发现不一致 → 修 .txt 直到逐字符一致
- 验证：87 个现有单元测试全部通过（旧代码在跑，builder 在跑但未使用）

### Step 3: 逐模块替换（每步一个模块 + 跑测试）
- 3a. `react_core.py`: 7 个常量 → builder
- 3b. `spawn.py`: 子代理 prompt → builder
- 3c. `tool_registry.py`: tool descriptions → builder
- 3d. `tool_handler.py`: 删除 task/orchestrate 覆盖逻辑（含 schema 修复）
- 3e. `plan_manager.py`: plan 生成 prompt → builder
- 3f. `subagent/types.py`: system_hint → builder
- 每步完成后即刻删除旧代码，不留死代码

### Step 4: 清理 + 新测试
- 确认无 import 旧常量
- 确认 `~/.xiaolei/roles/*.md` 已搬迁到 `prompts/agents/`
- 添加 PromptBuilder 单元测试（缓存、循环依赖检测、文件不存在报错）
- 全量测试通过

## 验证

- `pytest tests/v2/test_react_core_mock.py` — 87+ 现有测试通过
- `pytest tests/v2/test_prompt_builder.py` — 新增 builder 测试通过
- 端到端 CLI 测试：`python -m cli.main "list files in src"` — tool 描述正确加载
- 子代理测试：task(orchestrate)ool 正确识别 agent type，返回完整结果
