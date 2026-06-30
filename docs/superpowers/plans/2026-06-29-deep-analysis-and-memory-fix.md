# Deep Analysis & Memory Fix 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 1) 让 project_analyzer 自动使用 codegraph_explore/callers/callees 做深层次分析；2) 修 ChromaDB 1.5.9 的 4 个 API 兼容错误

**架构：** 两个独立修改——prompt 改写让 LLM 走更深工具链；vector_memory.py 修 4 处 chromadb API 差异

**技术栈：** agents.yml + vector_memory.py + ChromaDB

---

### 任务 1：重写 project_analyzer prompt，加入 codegraph 工具链

**文件：**
- 修改：`config/agents.yml:9-13`
- 验证：CLI 运行 `深度分析 /path/to/project`

- [ ] **步骤 1：修改 project_analyzer.role_prompt**

替换现有的 3 行 prompt 为完整 codegraph 工具链描述：

```yaml
  project_analyzer:
    role_prompt: >
      你是一个资深代码架构分析师。

      【分析流程 — 按优先级使用工具】
      1. codegraph_files → 了解项目概览（文件数、语种分布、核心目录）
      2. codegraph_explore <入口/核心模块> → 定位关键符号（类、函数、接口）
      3. codegraph_callers/callees <关键函数> → 追踪调用链（数据流、依赖方向）
      4. read_file → 读具体实现代码（核心文件全文）
      5. codegraph_impact <改动的符号> → 如果需要评估改动影响面
      6. write_file → 输出完整 HTML 报告到桌面

      【规则】
      - 每个工具调用后分析结果，决定下一步读什么
      - 发现新符号 → 用 codegraph_explore 追踪
      - 发现新线索 → 即时调整计划
      - 报告覆盖：概览 → 目录结构 → 技术栈 → 架构分层 → 数据流 → 核心模块 → 改进建议
    tools: ["project-analyzer-mcp", "file-ops-mcp", "codegraph-mcp", "query_memory"]
    priority: 3
```

- [ ] **步骤 2：验证语法**

运行：`python3 -c "import yaml; yaml.safe_load(open('config/agents.yml'))"`
预期：无错误，正常打印 dict

- [ ] **步骤 3：Commit**

```bash
git add config/agents.yml
git commit -m "feat: rewrite project_analyzer prompt with codegraph tool chain"
```

---

### 任务 2：修复 ChromaDB 1.5.9 兼容错误

**文件：**
- 修改：`core/memory/vector_memory.py:328-331`（buffer 顺序）
- 修改：`core/memory/vector_memory.py:534-556`（search_memories 类型兼容）
- 修改：`core/memory/vector_memory.py:201-228`（`__call__` 输入适配）
- 修改：`core/memory/vector_memory.py:386-412`（`_ensure_collection` dimensionality 回退）

- [ ] **步骤 1：修复 `_memory_buffer` 线程竞争**

问题：`_start_embedding_init()` 在第 328 行调用，早于 `self._memory_buffer` 在第 331 行。后台线程的 `_flush_buffer()` 访问未初始化的 buffer。

```python
# 批量写入缓冲区（移至 start_embedding_init 之前）
self._memory_buffer: List[tuple] = []
self._buffer_lock = threading.Lock()
self._last_flush_time = time.time()
self._buffer_size = 10
self._flush_interval = 30  # 秒

self._start_embedding_init()
```

- [ ] **步骤 2：修复 `search_memories` 结果解析**

问题：ChromaDB 1.5 可能返回 int 而非 list，`zip(results["ids"][0], ...)` 对 int 调用 `len()` 报错。

```python
            memories: List[Dict[str, Any]] = []
            if results and results.get("ids"):
                ids0 = results["ids"][0]
                if not isinstance(ids0, list):
                    ids0 = [ids0] if ids0 is not None else []
                docs0 = results.get("documents", [[]])[0]
                if not isinstance(docs0, list):
                    docs0 = [docs0] if docs0 is not None else []
                metas0 = results.get("metadatas", [[]])[0]
                if not isinstance(metas0, list):
                    metas0 = [metas0] if metas0 is not None else []
                dists0 = results.get("distances", [[]])[0]
                if not isinstance(dists0, list):
                    dists0 = [dists0] if dists0 is not None else []
                for mem_id, doc, meta, dist in zip(ids0, docs0, metas0, dists0):
                    memories.append({"id": mem_id, "content": doc, "metadata": meta, "distance": dist})
```

- [ ] **步骤 3：修复 `__call__` 输入类型适配**

问题：ChromaDB 1.5 可能传非 list 输入给 embedding function。

```python
    def __call__(self, input):
        if input is None:
            return []
        if not isinstance(input, list):
            input = [input]
        if not input:
            return []
        # ... 原有逻辑不变
```

- [ ] **步骤 4：修复 `_ensure_collection` dimensionality 回退**

问题：ChromaDB 1.5 对 `get_or_create_collection` 的 metadata 格式有不同要求。

```python
        try:
            embed_fn = get_bge_embedding_function()
            try:
                self._collection = self._client.get_collection(
                    name="long_term_memory",
                    embedding_function=embed_fn,
                )
            except Exception:
                self._collection = self._client.get_or_create_collection(
                    name="long_term_memory",
                    embedding_function=embed_fn,
                )
            # ...
        except Exception as e:
            logger.error("ChromaDB 初始化失败: %s", e)
            # 回退到本地 TF-IDF
            try:
                embed_fn = LocalEmbeddingFunction()
                self._collection = self._client.get_or_create_collection(
                    name="long_term_memory",
                    embedding_function=embed_fn,
                )
                self._embedding_ready = True
                self._collection_ready_event.set()
                logger.info("ChromaDB 使用本地 TF-IDF 降级成功")
            except Exception as e2:
                logger.error("ChromaDB TF-IDF 降级也失败: %s", e2)
                self._collection = None
```

- [ ] **步骤 5：运行单元测试验证**

运行：`python3 -m pytest tests/v2/test_project_analysis_guard.py tests/v2/test_analysis_e2e.py -v --tb=short 2>&1 | tail -20`
预期：所有测试通过

- [ ] **步骤 6：运行端到端验证**

运行：`python3 -c "
from core.memory.vector_memory import VectorMemoryStore
vm = VectorMemoryStore()
vm.wait_for_collection(timeout=15)
r = vm.search_memories('测试', top_k=3)
print(f'查询成功: {len(r)} 条')
" 2>&1 | grep -E '查询成功|ERROR'`
预期：打印 "查询成功: N 条"，无 ERROR 日志

- [ ] **步骤 7：Commit**

```bash
git add core/memory/vector_memory.py
git commit -m "fix: chromadb 1.5.9 compat — buffer race, search_memories types, embedding input, dimensionality fallback"
```

---

### 验证清单

- [ ] `python3 -c "import yaml; yaml.safe_load(open('config/agents.yml'))"` 无错误
- [ ] `VectorMemoryStore().search_memories("test", top_k=3)` 返回结果列表而非异常
- [ ] 向量检索日志无 `dimensionality` / `no len()` / `float cannot be converted` / `_memory_buffer` 错误
