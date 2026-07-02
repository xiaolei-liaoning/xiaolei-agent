# Project Analysis: README-驱动探索设计

## 问题

v2 单 Agent 分析项目时，不主动读 README 等总结性文件，而是依赖 Phase 1+2 程序化扫描结果，LLM 仅做 HTML 格式化，浪费了 LLM 的深度分析能力。

## 当前流程

```
User: "分析项目 /path/to/project"
  │
  ├─ Phase 1+2 程序化扫描
  │   ├─ os.walk 全文件遍历
  │   ├─ 读 README 前 30 行（截断到 300 字）
  │   ├─ 读取 imports/classes/functions
  │   └─ CodeGraph 调用链
  │
  └─ 注入 ReAct 循环
      └─ _PROJECT_ANALYSIS_PROMPT: "禁止首轮调工具，数据已提供"
          └─ LLM 仅做 HTML 格式化 → 浪费分析能力
```

## 设计

### 1. `_PROJECT_ANALYSIS_PROMPT` 重构 — `react_core.py:104-130`

**删除：**
- "禁止在首轮调用任何工具" + "首轮必须直接输出分析报告"
- "禁止对已提供的文件调用 read_file"
- "禁止调用 execute_shell / search_files"
- "你只有 3 轮输出机会"

**改为：**
```
<project_analysis_protocol>
你正在深度分析一个项目。

【已提供的数据】
下方有初步扫描的结构数据（文件树、技术栈、核心代码头部、调用链），作为浏览上下文使用。

【探索指引 — 建议步骤】
1. 用 read_file 读 README.md、CLAUDE.md、AGENTS.md 等总结性文档，了解项目全貌
2. 用 glob / search_code 探索关键模块和入口文件
3. 结合下方数据和你的探索结果，输出深度分析报告

【任务】
基于已提供的数据 + 你自行探索的信息，输出完整分析报告...
```

### 2. Phase 1+2 README 读取扩展 — `work_agent.py:348-371, 403-409`

| 文件 | 当前 | 改为 |
|------|------|------|
| 根目录 README.md/CLAUDE.md/AGENTS.md | `read_file_head(rf)` 30 行 → `[:300]` | `read_file_head(rf, 200)` 不截断 |
| 新增：ARCHITECTURE.md/CONTRIBUTING.md | 未读取 | `read_file_head(_, 200)` 不截断 |
| 子目录 README.md | `read_file_head(_, 20)` → `[:200]` | `read_file_head(_, 100)` 不截断 |

### 3. Phase 1+2 返回值改造 — `work_agent.py:486-507`

**旧：**
```python
"【项目分析数据已就绪 — LLM 仅做 HTML 包装】\n\n"
"⚠️ IMPORTANT: 你只有 3 轮输出机会。不要调用 read_file 或任何其他工具..."
"第 1 轮：直接生成 HTML..."
"第 2 轮：用 write_file 写入..."
"第 3 轮：输出完成消息..."
```

**新：**
```python
"【项目分析数据已就绪 — 作为探索上下文使用】\n\n"
"下方是程序化扫描的初步结构数据。请用 read_file 深入读 README 等总结性文件，"
"结合上下文产出深度分析报告。\n\n"
"路径：{path}\n分析耗时：{elapsed:.1f}s\n\n"
"{analysis_text}"
```

### 4. 数据流

```
Phase 1+2 扫描（扩展 README 读取）
  │
  ├─ 扫描数据（文件树/imports/类函数/调用链）
  └─ README 等总结性文件全文（最多 200 行）
      │
      ▼
ReAct 循环（不再禁工具）
  │
  ├─ [第 1 轮] LLM 读 README/CLAUDE.md 等
  ├─ [第 2 轮] LLM 探索关键模块
  ├─ [第 3 轮] LLM 产出分析报告
  └─ [后续轮] 按需深入
```

### 5. 边界情况

| 场景 | 行为 |
|------|------|
| Phase 1+2 数据为空（路径未提取） | `_PROJECT_ANALYSIS_PROMPT` 仍允许工具调用，LLM 可自行探索 |
| README 不存在 | LLM 发现后跳过，读其他文件 |
| 大量 README 文件 | 限制每个最多 200 行，`read_file_head` 作为程序化读取也用 200 行上限 |

## 变更清单

| 文件 | 行号 | 变更 |
|------|------|------|
| `react_core.py` | 104-130 | `_PROJECT_ANALYSIS_PROMPT` 重写 |
| `work_agent.py` | 348-358 | 扩展 doc_candidates 加入 ARCHITECTURE.md 等 |
| `work_agent.py` | 363-370 | 根目录 README 30→200 行，移除 `[:300]` |
| `work_agent.py` | 407-409 | 子目录 README 20→100 行，移除 `[:200]` |
| `work_agent.py` | 486-507 | 返回值从 "HTML 包装" 改为 "探索上下文" |
| 测试文件 | 新增 | 验证 README 全文读取 + 工具探索流程 |

## 测试

现有测试 `test_analysis_e2e.py` 和 `test_project_analysis_guard.py` 需要更新：
- Phase 1+2 返回值不再包含 "LLM仅做HTML包装" 关键词
- 验证 README 内容出现在扫描数据中
- 验证 `_PROJECT_ANALYSIS_PROMPT` 不再包含 "禁止首轮调工具"
