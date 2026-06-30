# 修复设计：Skill 匹配 + 向量记忆 + ReAct 流程

**日期**: 2026-06-30
**状态**: 待实现
**范围**: 三个独立问题，互不依赖

---

## Fix 1：Expert Skill 匹配不准确

### 问题

- `_match_expert()` 用 jieba 分词做预筛，对短查询（<15字）几乎无信号
- LLM 精排面对 4 个低分候选容易误选不相关 Expert
- "看看有什么记忆" 匹配到 "企业培训课程设计师"

### 方案

去掉 jieba 预筛，改用 category 过滤 + LLM 全量选择。

### 改动：`core/skills/base_skills.py` → `_match_expert()`

1. **删除 jieba 分词逻辑**（第 236-286 行的 `raw_tokens`、`task_words`、`scored` 计算）
2. **保留 category 过滤**：用 `BASE_TO_EXPERT_CATEGORIES[base_id]` 缩小候选范围
3. **构建 Expert 列表 prompt**：将该类别下所有 Expert 的 `name` + `description`（截断 60 字）格式化为选项列表
4. **LLM 全量选择**：让 LLM 从列表中选最匹配的 1 个，输出专家 ID
5. **无候选时返回 None**：category 下没有 Expert 则跳过

### 伪代码

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
        return candidates[0] if candidates else None  # LLM 不可用时取第一个

    # 构建选项列表
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
    return candidates[0]  # LLM 无结果时取第一个
```

---

## Fix 2：向量记忆错误

### 问题

- `object of type 'int' has no len()` — ChromaDB query 时 embedding function 返回类型错误
- `'dict' object has no attribute 'dimensionality'` — collection 内部 embedding function 引用不一致
- 根因：`_ensure_collection()` 和 `search_memories()` 使用的 embedding function 对象不一致

### 方案

统一 embedding function 来源 + query 报错时自动重建 collection。

### 改动：`core/memory/vector_memory.py`

#### 2a. 统一 `_ensure_collection()` 的 embedding function

```python
def _ensure_collection(self):
    embed_fn = get_bge_embedding_function()  # 始终用同一个 factory
    try:
        self._collection = self._client.get_or_create_collection(
            name="long_term_memory",
            embedding_function=embed_fn,
        )
        self._embedding_ready = True
        self._collection_ready_event.set()
    except Exception as e:
        logger.error("ChromaDB 初始化失败: %s", e)
        self._collection = None
```

#### 2b. `search_memories()` 加类型错误重试

```python
def search_memories(self, query, user_id=None, top_k=5):
    if not self._collection or not query or not query.strip():
        return []

    self._flush_buffer()

    try:
        results = self._collection.query(query_texts=[query], n_results=top_k, ...)
        # ... 解析结果 ...
    except TypeError as e:
        if "len" in str(e) or "dimensionality" in str(e):
            logger.warning("Embedding 类型错误，重建 collection: %s", e)
            self._rebuild_collection()
            # 重试一次
            results = self._collection.query(query_texts=[query], n_results=top_k, ...)
            # ... 解析结果 ...
        else:
            raise
    except Exception as e:
        logger.error("向量检索失败: %s", e)
        return []
```

#### 2c. 新增 `_rebuild_collection()`

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
    logger.info("ChromaDB collection 已重建")
```

---

## Fix 3：ReAct + 中间件流程修复

### 问题 A：on_plan_check 时序

**位置**: `react_core.py` 主循环第 903-924 行

**当前顺序**: `on_think_start` → `on_plan_check` → `on_think_end`
**问题**: `on_think_start` 中 LLM 已生成 tool_calls，`on_plan_check` 变成事后检查

**修复**: 调换为 `on_plan_check` → `on_think_start` → `on_think_end`

```python
# 修复前
hr_start = await chain.on_think_start(ctx)
# ...
hr_plan = await chain.on_plan_check(ctx)
# ...

# 修复后
hr_plan = await chain.on_plan_check(ctx)
if hr_plan and hr_plan.jump_to == "end":
    ctx.interrupted = True
    ctx.last_error = hr_plan.reason or "中间件终止(plan_check)"
    break
if hr_plan and hr_plan.jump_to == "retry":
    continue

hr_start = await chain.on_think_start(ctx)
# ...
```

### 问题 B：on_wrap_tool_call 未调用

**位置**: `tool_executor.py` 的 `execute_tool_call()`

**当前**: 直接调用 `handler(args)`
**修复**: 在 handler 调用前走 `chain.on_wrap_tool_call()`

```python
async def execute_tool_call(tc, chain=None, ctx=None, tool_defs=None):
    name = tc.get("function", {}).get("name", "")
    args = parse arguments...

    if chain and ctx:
        # 走洋葱模式：PermissionMiddleware → HookMiddleware → 实际执行
        result = await chain.on_wrap_tool_call(ctx, {"name": name, "arguments": args})
        return result
    else:
        # 无 chain 时直接执行（兼容旧路径）
        handler = registry.get_handler(name)
        return await handler(args)
```

### 问题 C：HookMiddleware retry 被忽略

**位置**: `react_core.py` 第 937-948 行

**当前**: `hr_tool = await chain.on_tool_end(ctx)` 后只处理 `jump_to="end"`，忽略 `retry`
**修复**: 加 retry 处理

```python
hr_tool = await chain.on_tool_end(ctx)
if hr_tool and hr_tool.jump_to == "end":
    ctx.interrupted = True
    ctx.last_error = hr_tool.reason or "中间件终止(tool_end)"
    break
if hr_tool and hr_tool.jump_to == "retry":
    ctx.warnings.append(f"[重试] {hr_tool.reason}。")
    # 标记当前步骤为 failed，触发 replan
    for step in ctx.plan:
        if step.status == "running":
            step.status = "failed"
            ctx._step_retries[step.index] = ctx._step_retries.get(step.index, 0) + 1
    continue
```

### 问题 D：forced_instructions 竞争

**位置**: `react_core.py` 第 362 行

**当前**: `ctx.forced_instructions = ""` 在 `on_think_start` 末尾无条件清除
**修复**: 用 flag 标记已使用，不在同轮内清除

```python
# on_think_start 末尾
if ctx.forced_instructions:
    system_content += f"\n\n<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>"
    ctx._fi_used = True  # 标记已使用，不清除

# on_think_end 中需要设置新指令时
if not getattr(ctx, '_fi_used', False):
    ctx.forced_instructions = "..."
```

### 问题 E：MemoryMiddleware 死代码

**位置**: `core/memory/memory_middleware.py`

**当前**: `class MemoryMiddleware` 不继承 `BaseMiddleware`，`chain.add()` 后不会被任何钩子调用
**修复**: 继承 `BaseMiddleware`，注册 `on_start` 钩子

```python
from core.multi_agent_v2.agents.middleware import BaseMiddleware, HookResult

class MemoryMiddleware(BaseMiddleware):
    HOOKS = ("on_start",)

    async def on_start(self, ctx: RunContext) -> None:
        """任务开始时注入记忆上下文"""
        user_id = ctx.profile.get("user_id", "default")
        memory_context = await self.get_user_context(user_id, ctx.task_description)
        if memory_context:
            ctx.knowledge_context += f"\n\n{memory_context}"
```

---

## 测试计划

1. **Fix 1 测试**: 用 "看看有什么记忆"、"你好"、"写一个八数码游戏" 等短查询验证 Expert 匹配结果
2. **Fix 2 测试**: 重启应用后立即执行 `query_memory`，验证不再报 `int has no len()` 错误
3. **Fix 3 测试**: 
   - 验证 `PermissionMiddleware` 的 Shell 命令拦截生效
   - 验证 `LoopDetectionMiddleware` 在 LLM 调用前检测
   - 验证 `HookMiddleware` 的 retry 返回值被主循环处理

## 不做的事

- 不重构 MiddlewareChain 的洋葱模式架构（改动太大，超出范围）
- 不修改 `_task_flags` 的 LLM 分类逻辑（那是另一个优化方向）
- 不调整 `_MAX_ROUNDS` 或 `max_iterations` 默认值
