# Task Classification Cleanup: 删除 hard-coded prompt 常量 + Expert 置信度

## 动机

当前 `react_core.py` 混入了大量硬编码的场景提示词和条件注入逻辑
（`_CODE_GEN_PROMPT`, `_GAME_DEV_PROMPT`, `_REPORT_PROMPT`,
`_PROJECT_ANALYSIS_PROMPT`），与 Skill 系统职能重叠。同时 Expert 匹配缺乏
置信度控制，经常加载不相关的专家角色。

## 变更概览

```
删:  4 个 prompt 常量定义 (约 70 行)
删:  30 行条件注入 if/else
改:  _BASE_PROMPT 合并通用规则 (新增 3 行)
改:  _match_expert 精排 prompt 加"无匹配"选项
改:  work_agent.py 显示"未匹配到"
搬:  _PROJECT_ANALYSIS_PROMPT 内容 → agents.yml role_prompt
保:  _task_flags 分类 (仅用于 tool 过滤)
保:  max_iterations 兜底一行
```

## 详细设计

### 1. 删除硬编码 prompt 常量

**删 `react_core.py`：**

```python
_CODE_GEN_PROMPT     # 67-75 行
_GAME_DEV_PROMPT     # 77-84 行
_REPORT_PROMPT       # 87-93 行
_PROJECT_ANALYSIS_PROMPT  # 104-131 行
```

**删条件注入：**
```python
# 325-332 行: _task_flags.get("code") → _CODE_GEN_PROMPT
# 349-354 行: _task_flags.get("project_analysis") → 插入 _PROJECT_ANALYSIS_PROMPT
```

**保留下游依赖：**
- `_PLAN_PROMPT` (95-97 行) — 计划执行约束，通用
- `_DEBUG_PROMPT` (99-102 行) — 错误恢复指令，通用
- `_task_flags` LLM 分类 (287-318 行) — 仅用于 tool 过滤
- `desktop_save → hide execute_python` (320-323 行) — tool 过滤
- 连续失败工具隐藏 (334-347 行) — 通用 loop 保护
- `max_iterations` 兜底 (353 行) — 精简为仅保留赋值

### 2. 合并 `_BASE_PROMPT`

将三个短 prompt 的核心规则合并到 `_BASE_PROMPT`：

```python
_BASE_PROMPT = (
    "先思考再行动：\n"
    "1. 任务目标是什么？当前进度在哪里？\n"
    "2. 需要工具就调用，有数据就回答，信息不够继续追问\n"
    "3. 不要输出思考过程描述，直接行动\n\n"
    "关键规则：\n"
    "- 每轮必须输出工具调用或最终答案，禁止空转\n"
    "- 创建文件用 write_file 一次性写入完整代码\n"
    "- 修改代码用 edit_file（精确字符串替换）\n"
    "- 禁止输出被截断/不完整的代码\n"
    "【代码生成】首次 write_file → 修改用 edit_file\n"
    "【报告生成】web_search 获取数据 → write_file 输出 HTML\n"
    "【游戏开发】必须监听事件(keydown/click)，有渲染函数\n"
)
```

LLM 看到后自行选择相关规则，无需 `_task_flags` 条件路由。

### 3. Expert 匹配加"无匹配"选项

**`base_skills.py` `_match_expert` 精排 prompt 修改：**

改前：
```
从以下专家中选最匹配的 1 个：
{lines}
只输出专家 ID：
```

改后：
```
从以下专家中选最匹配的 1 个，如果都不匹配则输出「无匹配」：
{lines}
只输出专家 ID 或「无匹配」：
```

LLM 返回"无匹配"时 `return None`，work_agent.py 打印 `👤 Expert: 未匹配到`。

### 4. `_PROJECT_ANALYSIS_PROMPT` 迁移

将 700 字分析指令移到 `config/agents.yml` 的 `project_analyzer` role_prompt。
react_core.py 不再插入分析 prompt —— skill 人格自然携带。

保留一行 max_iterations 兜底：
```python
# 项目分析无 Phase 1 数据时给更多轮次
if _task_flags.get("project_analysis") and not getattr(ctx, '_has_structure_data', False):
    ctx.max_iterations = max(ctx.max_iterations, 15)
```

### 5. 不受影响的部分

| 功能 | 状态 | 说明 |
|---|---|---|
| Phase 1 快速路径 | 保留 | `_has_structure_data=True → max_iterations=3` 不变 |
| 计划系统 | 保留 | `generate_plan / display_plan / steps_summary` 不变 |
| 上下文压缩 | 保留 | `ContextBudgetManager` 不变 |
| 循环检测 | 保留 | `LoopDetectionMiddleware` 不变 |
| 工具执行 | 保留 | `tool_executor / tool_parser` 不变 |
| 文件质量迭代 | 保留 | `on_think_end` 的 write_file 2-pass 不变 |

## 文件变更清单

| 文件 | 变更 |
|---|---|
| `core/multi_agent_v2/agents/react_core.py` | 删 4 个常量 + 30 行 if/else, 改 _BASE_PROMPT |
| `core/skills/base_skills.py` | _match_expert prompt 加"无匹配"选项 |
| `core/multi_agent_v2/agents/base/work_agent.py` | Expert 为空时打印"未匹配到" |
| `config/agents.yml` | project_analyzer role_prompt 追加分析指令 |

## 回滚方案

所有改动的都是删除和移动，不涉及逻辑重写。回滚 = `git checkout` 涉及文件。
