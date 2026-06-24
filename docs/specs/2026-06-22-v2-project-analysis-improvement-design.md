# V2 架构项目分析能力改造设计方案

## 问题背景

V2 架构的 ReAct 循环存在 6 个瓶颈：

| 瓶颈 | 现状 | 影响 |
|------|------|------|
| 工具粒度粗 | `read_file` 一次读 1 个文件 | 读 N 个文件要 N 轮 |
| LLM 轮次上限 | MAX_ROUNDS=10 | 最多读 8-10 个文件 |
| 缺少分析 prompt | 没有 `_PROJECT_ANALYSIS_PROMPT` | LLM 不知道该按什么顺序读 |
| 工具选择干扰 | 34 个工具同时可选 | LLM 可能选无关工具 |
| 对话历史膨胀 | 文件内容全塞进 `_conversation_history` | token 消耗快 |
| 无内容复用 | 同一文件可能被反复读 | 浪费轮次 |

## 改造范围

三个改动点，全部在 prompt 层和工具筛选层，**不改 ReActCore 循环逻辑**：

| 改动 | 文件 | 行数 |
|------|------|------|
| 新增 `_PROJECT_ANALYSIS_PROMPT` | `react_core.py` | ~25 |
| prompt 组装 + 轮次调整 | `react_core.py` | ~10 |
| 分析任务工具白名单 | `react_core.py` | ~10 |

## 改造细节

### 1. 新增两阶段分析 prompt

```python
_PROJECT_ANALYSIS_PROMPT = (
    "<project_analysis_protocol>\n"
    "你正在分析一个项目的结构和代码。请按两阶段执行：\n\n"
    "【第一阶段：收集信息】\n"
    "1. 先调用 analyze_project(path) 批量读取关键文件\n"
    "2. 信息不够时调 search_code(query) 补充搜索\n"
    "3. 收集完成后进入第二阶段\n\n"
    "【第二阶段：综合分析】\n"
    "基于已收集的数据，直接输出完整的项目分析报告：\n"
    "- 项目概览（语言、框架、构建工具）\n"
    "- 目录结构与模块职责\n"
    "- 核心技术栈分析\n"
    "- 架构亮点与注意事项\n"
    "</project_analysis_protocol>"
)
```

### 2. prompt 组装判断

在现有的按任务类型拼接 prompt 逻辑（第 217-228 行 `modules` 列表）中追加：

```python
if any(kw in task_lower for kw in
    ["分析项目", "项目结构", "项目目录", "看看.*代码",
     "看.*项目", "项目的代码", "分析.*项目"]):
    modules.insert(1, _PROJECT_ANALYSIS_PROMPT)
    ctx.max_iterations = max(ctx.max_iterations, 15)
```

### 3. 工具过滤白名单

```python
if any(kw in ctx.task_description.lower() for kw in
    ["分析项目", "项目结构", "项目目录", "项目分析"]):
    analysis_tools = {"analyze_project", "search_code", "read_file", "search_files"}
    filtered = [t for t in tool_cache if t.name in analysis_tools][:10]
else:
    filtered = await reg.get_tools_for_task(...)
```

## 完整执行链路（改造后）

```
用户: "分析一下 /xxx/项目"
  ↓
WorkAgent._execute_fast()
  ↓
Skill 匹配 → project_analysis → project_analyzer Expert
  ↓
run_react() → prompt 含 _PROJECT_ANALYSIS_PROMPT
  ↓
第1轮: LLM → analyze_project("/xxx/项目", "normal")
       → 返回 12+ 文件内容 + 技术栈
  ↓
第2轮: search_code("class Actor") 补充（可选）
  ↓
第3轮: 直接输出综合分析报告
→ ~3 轮 / ~9s （原来 ~10 轮 / ~30s）
```

## 不变的部分

- **ReActCore 循环**：不改 `on_think_start`/`on_think_end` 逻辑
- **中间件链**：不改 `build_default_chain()`
- **ToolRegistry**：不改发现机制
- **轮次上限默认值**：`_MAX_ROUNDS=10` 不变，只在分析任务时提高到 15
