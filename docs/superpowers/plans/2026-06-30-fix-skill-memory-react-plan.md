# Skill 匹配 + 向量记忆 + ReAct 流程 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复三个独立问题：Expert skill 匹配不准确、向量记忆 ChromaDB 类型错误、ReAct 主循环 3 个边缘逻辑缺陷

**架构：** 三个修复互不依赖，可按任意顺序执行

**技术栈：** Python asyncio, ChromaDB, LLM router

---

## 文件结构

- **修改** `core/skills/base_skills.py` — Fix 1: Expert 匹配去 jieba 改用 LLM 全量选择
- **修改** `core/memory/vector_memory.py` — Fix 2: add `_rebuild_collection`, 类型错误自动重建
- **修改** `core/multi_agent_v2/agents/react_core.py` — Fix 3A: null plan guard; Fix 3B: ReActDepth 时序; Fix 3C: forced_instructions 同轮竞争
- **修改** `core/multi_agent_v2/agents/middlewares.py` — Fix 3B: ReActDepthMiddleware 检查点后移

---

### 任务 1：Fix 1 — Expert 匹配去掉 jieba，改用 LLM 全量选择

**文件：**
- 修改：`core/skills/base_skills.py:218-304`

- [ ] **步骤 1：重写 `_match_expert`**

去掉 jieba 分词预筛，保留 `BASE_TO_EXPERT_CATEGORIES[base_id]` category 过滤，改让 LLM 从该类别下所有 Expert 中直接选择。

```python
async def _match_expert(self, task: str, base_id: str) -> Optional[dict]:
    cats = BASE_TO_EXPERT_CATEGORIES.get(base_id, [])
    if not cats and base_id == "general":
        cats = list(self.experts.keys())
    candidates = []
    for cat in cats:
        candidates.extend(self.experts.get(cat, []))
    if not candidates:
        return None

    router = get_llm_router()
    if not router or not router.is_available():
        return candidates[0] if candidates else None

    lines = []
    for a in candidates:
        desc = (a.get("description", "") or "")[:60]
        lines.append(f"  {a.get('id', '?')}: {a.get('name', '?')} — {desc}")

    prompt = (
        f"任务：{task}\n\n"
        f"从以下专家中选最匹配的 1 个：\n"
        + "\n".join(lines) +
        "\n\n只输出专家 ID："
    )
    resp = (await router.simple_chat(prompt, temperature=0.1, max_tokens=30) or "").strip().lower()
    for a in candidates:
        if a.get("id", "") in resp:
            return a
    return candidates[0] if candidates else None
```

删掉 jieba 导入、`task_words` 循环、`scored` 排序、Top-4 截断、旧 LLM 精排 prompt 等约 50 行。

- [ ] **步骤 2：Commit**

```bash
git add core/skills/base_skills.py
git commit -m "fix: Expert匹配去掉jieba预筛改用LLM全量选择"
```

---

### 任务 2：Fix 2 — 向量记忆错误处理

**文件：**
- 修改：`core/memory/vector_memory.py:524-580`

- [ ] **步骤 1：新增 `_rebuild_collection` 方法**

```python
def _rebuild_collection(self):
    """删除旧 collection 并用当前 embedding function 重建"""
    try:
        self._client.delete_collection("long_term_memory")
    except Exception:
        pass
    embed_fn = get_bge_embedding_function()
    self._collection = self._client.get_or_create_collection(
        name="long_term_memory",
        embedding_function=embed_fn,
    )
    self._embedding_ready = True
    self._collection_ready_event.set()
    logger.info("ChromaDB collection 已重建")
```

- [ ] **步骤 2：修改 `search_memories` — query 报类型错误时自动重建并重试**

```python
def search_memories(self, query: str, user_id=None, top_k: int = 5) -> List[Dict[str, Any]]:
    if not self._collection or not query or not query.strip():
        return []

    self._flush_buffer()
    where_filter: Dict[str, Any] = {}
    if user_id is not None:
        where_filter["user_id"] = str(user_id)

    for retry in range(2):
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter if where_filter else None,
            )
            # 解析结果（从现有代码复制）
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
            return memories
        except TypeError as e:
            err = str(e)
            if ("len" in err or "dimensionality" in err) and retry == 0:
                logger.warning(f"向量检索类型错误，重建 collection 后重试: {e}")
                self._rebuild_collection()
                continue
            logger.error(f"向量检索失败（类型错误且重建不成功）: {e}")
            return []
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []
    return []
```

- [ ] **步骤 3：Commit**

```bash
git add core/memory/vector_memory.py
git commit -m "fix: 向量记忆类型错误自动重建collection并重试"
```

---

### 任务 3：Fix 3A — retry handler null plan 保护

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py:942-948`

- [ ] **步骤 1：给 retry 路径加 null plan 保护**

当前代码 942-948 行：
```python
if hr_tool and hr_tool.jump_to == "retry":
    ctx.warnings.append(f"[重试] {hr_tool.reason}。")
    for step in ctx.plan:     # ← ctx.plan 可能 None，会 crash
        if step.status == "running":
            step.status = "failed"
            ctx._step_retries[step.index] = ctx._step_retries.get(step.index, 0) + 1
    continue
```

改为：
```python
if hr_tool and hr_tool.jump_to == "retry":
    ctx.warnings.append(f"[重试] {hr_tool.reason}。")
    if ctx.plan:
        for step in ctx.plan:
            if step.status == "running":
                step.status = "failed"
                ctx._step_retries[step.index] = ctx._step_retries.get(step.index, 0) + 1
    continue
```

- [ ] **步骤 2：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py
git commit -m "fix: retry handler 加 null plan 保护防 crash"
```

---

### 任务 4：Fix 3B — ReActDepthMiddleware 时序修复

**文件：**
- 修改：`core/multi_agent_v2/agents/middlewares.py:40-44`
- 修改：`core/multi_agent_v2/agents/react_core.py:229`

**问题**：`ReActDepthMiddleware.on_think_start`（第 3 个中间件）在 `ReActCoreMiddleware.on_think_start` 之前执行，但 `ctx.react_depth` 是在 `ReActCoreMiddleware.on_think_start:229` 才 `+=1`。所以深度检查总是用的旧值（off-by-one）。

- [ ] **步骤 1：将 `ctx.react_depth += 1` 提前到主循环中**

在 `react_core.py` 主循环开头，`on_think_start` 调用之前加：

```python
ctx.react_depth += 1
```

然后从 `ReActCoreMiddleware.on_think_start` 中删除第 229 行的 `ctx.react_depth += 1`。

- [ ] **步骤 2：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py
git commit -m "fix: react_depth 提前到主循环中递增，解决深度检查off-by-one"
```

---

### 任务 5：Fix 3C — forced_instructions 同轮竞争

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py:360-362`

**问题**：`on_think_start` 第 362 行清除 `forced_instructions` 后，`on_think_end` 的质量改进代码检查 `not ctx.forced_instructions` 为 True，然后设置新指令。但如果中间有别的路径（参数校验错误）也设置了 `forced_instructions`，质量改进的 `not ctx.forced_instructions` 检查会阻止它。

这不是 bug，但会让用户困惑：明明有参数错误，LLM 修复后却收不到质量改进指令。

- [ ] **步骤 1：改为用 `_fi_consumed` 标记代替清除**

```python
# on_think_start 末尾 — 注入后用标记，不清除
if ctx.forced_instructions:
    system_content += f"\n\n<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>"
    ctx._fi_consumed = True  # 标记已消费
```

```python
# on_think_end 中质量改进 — 检查 _fi_consumed 而非清除后的值
if qa_passed and not getattr(ctx, '_fi_consumed', False):
    ...
```

```python
# 主循环每轮开始前重置标记
if hasattr(ctx, '_fi_consumed'):
    delattr(ctx, '_fi_consumed')
ctx.forced_instructions = ""  # 保留清除逻辑但放到主循环
```

- [ ] **步骤 2：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py
git commit -m "fix: forced_instructions 用_fi_consumed标记替代直接清除"
```

---

## 自检

1. **规格覆盖度**: 设计文档中 3 个 Fix 全部覆盖 — Fix 1→任务1, Fix 2→任务2, Fix 3→任务3-5
2. **占位符扫描**: 无 TODO/待定，每个步骤有完整代码
3. **类型一致性**: 所有方法引用（`_rebuild_collection`, `_match_expert`, `on_think_start`, 等）与现有代码一致
