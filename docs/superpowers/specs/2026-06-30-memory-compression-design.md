# 保存时记忆压缩设计

## 问题

每轮 system prompt 注入 10 条原始消息（~2500 字），浪费 token。
读取时 4 层压缩在削减体积，但根源是自动全存原始消息。

## 方案

**保存时压缩**：对话结束后用 LLM 提取结构化记忆，后续轮次只注入索引。

## 改动

### 1. 新增 `core/memory/consolidator.py`

```
consolidate_session(user_id, user_message, assistant_reply)
  → 跳过太短的对话（<20 字）
  → LLM 提取 0-3 条 key insight
  → 每条: {name, type, content}
  → 存为 .md 到 ~/.小雷版小龙虾/memories/<slug>.md
  → 更新 MEMORY.md 索引
```

记忆类型：沿用现有 category（fact / preference / experience / insight），不加新 taxonomy。

MEMORY.md 格式：
```markdown
- [name](file.md) — content[:80]
```

LLM prompt（~30 行，硬编码在 consolidator.py 内）：
> 从这段对话中提取值得长期保存的关键信息（0-3条）。
> 只保存：用户偏好、个人事实、行为反馈。
> 不保存：代码模式、git 历史、临时任务状态。

### 2. 修改 `core/multi_agent_v2/agents/memory_middleware.py`

**on_think_start()** — 改为注入 MEMORY.md 索引 + 用户画像（不含原始消息）：
```
每轮注入:
  [记忆索引]
  - name — 描述
  - name — 描述
  [用户画像]
  姓名，3项事实，2项偏好
```

**on_finish()** — process_turn() 后追加 consolidate_session()。

### 3. 修改 `core/multi_agent_v2/tools/tool_registry.py`

新增 `query_raw_memory` 工具 — 查短期记忆原始消息：
- 参数：limit（默认10），keyword（可选过滤）
- 调用 ShortTermMemoryManager.get_context()

### 4. V1 不动

只改 V2 MemoryMiddleware 的注入逻辑，`core/memory/memory_middleware.py`（V1 共享路径）不改，不影响 Web API。

## 文件清单

| 操作 | 文件 | 行数 |
|------|------|------|
| 新增 | `core/memory/consolidator.py` | ~100 |
| 修改 | `core/multi_agent_v2/agents/memory_middleware.py` | ~20 行变动 |
| 修改 | `core/multi_agent_v2/tools/tool_registry.py` | ~40 行（新增 handler） |
| 不动 | `core/memory/memory_middleware.py` | 0 |

## 回滚

不改原有数据，新增的数据在 `~/.小雷版小龙虾/memories/`，删除即可。
`on_think_start()` 改回调用 V1 `get_user_context()` 即恢复原状。
