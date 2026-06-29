# Deep Analysis & Memory Fix Design

## 问题

1. **深度分析太浅** — `project_analyzer` 只用 `codegraph_files` + `read_file`，不用 `codegraph_explore`/`codegraph_callers`/`codegraph_callees`/`codegraph_impact`，导致分析止于文件列表和文本浏览
2. **ChromaDB 1.5.9 不兼容** — 4 个 API 兼容错误（非致命但数据读写失败）

## 方案：Prompt + Embedding 双修

两个问题独立，改的不重叠，一个改动周期出完。

### 1. Deep Analysis — Prompt 重写

**文件**: `config/agents.yml` 的 `project_analyzer.role_prompt`

定义显式工具链调用优先级：

```
codegraph_files(概览) 
  → codegraph_explore(核心符号定位) 
  → codegraph_callers/callees(调用链追踪)
  → read_file(读实现)
  → codegraph_impact(影响分析)
  → write_file(报告)
```

### 2. ChromaDB 1.5.9 兼容修复

**文件**: `core/memory/vector_memory.py`

| 错误 | 根因 | 修复 |
|------|------|------|
| `'dict' object has no attribute 'dimensionality'` | ChromaDB 1.5 `get_or_create_collection` 返回 dict 而非对象 | catch 异常回退本地 TF-IDF embedding |
| `'float' object cannot be converted to 'Sequence'` | `__call__` 输入类型与 ChromaDB 1.5 预期不匹配 | `__call__` 加输入类型归一化（list 包裹标量） |
| `attribute '_memory_buffer'` | `_start_embedding_init()` 在 line 328 调用，早于 `self._memory_buffer` 在 line 331 | 交换顺序：先分配 buffer，再启动线程 |
| `object of type 'int' has no len()` | `search_memories` 的 `results["ids"][0]` 在 ChromaDB 1.5 返回 int 而非 list | 结果解析分支兼容：判断类型后分别处理 |

### 影响范围

- `config/agents.yml` — prompt 改写（~30 行）
- `core/memory/vector_memory.py` — 4 处兼容修复（~20 行）
- 其他文件不改

### 测试

- `query_memory("anything")` 返回结果而非静默失败
- `project_analyzer` 实际调用 `codegraph_explore` 而非仅 `codegraph_files`

### 回滚

两个问题独立，各改一个文件，可分别 `git checkout` 回滚。
