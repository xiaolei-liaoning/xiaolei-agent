# 记忆反馈闭环实现计划

> **目标：** 让每轮 ReAct 工具执行结果通过 STM（短期记忆）回注到下一轮 LLM 上下文

**架构：** 只改 MemoryMiddleware 一个文件 — on_tool_end 把工具摘要写 STM，on_think_start 每轮读 STM。STM 自带 4 层压缩防膨胀。

**技术栈：** Python asyncio, 已有 STM 文件系统

---

### 任务 1：MemoryMiddleware 读写闭环

**文件：**
- 修改：`core/multi_agent_v2/agents/memory_middleware.py`
- 测试：`tests/test_memory_middleware.py`

- [ ] **步骤 1：编写失败的测试**

```python
@pytest.mark.asyncio
async def test_on_tool_end_writes_to_stm():
    """工具执行后写入 STM，下轮 on_think_start 能读到"""
    from core.multi_agent_v2.agents.memory_middleware import MemoryMiddleware
    from core.multi_agent_v2.agents.middleware import RunContext
    from core.memory.short_term_memory import get_memory_manager
    
    mw = MemoryMiddleware()
    ctx = RunContext(task_description="测试")
    ctx.tool_results = [
        {"success": True, "tool_call": {"name": "web_search", "arguments": {}},
         "result": "北京人口2188万"}
    ]
    agent = MagicMock()
    agent.user_id = "test_user_feedback"
    mw._agent = agent
    
    await mw.on_tool_end(ctx)
    
    stm = get_memory_manager()
    history = stm.get_context("test_user_feedback")
    entries = [h for h in history if "北京人口" in h.get("content", "")]
    assert len(entries) >= 1, f"STM 应包含工具结果，实际: {history}"
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent && python -m pytest tests/test_memory_middleware.py -v 2>&1
```

- [ ] **步骤 3：修改 on_tool_end — 工具结果写入 STM**

```python
async def on_tool_end(self, ctx: RunContext) -> None:
    if not ctx.tool_results:
        return
    latest = ctx.tool_results[-1]
    if not latest:
        return

    tc = latest.get("tool_call", {})
    exp = {
        "tool": tc.get("name", "?"),
        "success": latest.get("success", False),
        "result_summary": str(latest.get("result", ""))[:200],
        "iteration": ctx.iteration,
        "timestamp": time.time(),
    }
    self._tool_experiences.append(exp)

    if self._agent is not None and hasattr(self._agent, 'temp_memory'):
        self._agent.temp_memory["memory_experiences"] = self._tool_experiences[-10:]

    # ── 新增：工具结果写入 STM，供下轮 on_think_start 读取 ──
    try:
        from core.memory.short_term_memory import get_memory_manager
        stm = get_memory_manager()
        summary = f"[工具执行: {tc.get('name', '?')}] "
        if latest.get("success"):
            summary += str(latest.get("result", ""))[:300]
        else:
            summary += f"失败: {latest.get('error', '未知错误')[:200]}"
        stm.add(self._get_user_id(), "assistant", summary)
    except Exception as e:
        logger.debug(f"工具结果写入 STM 失败: {e}")
```

- [ ] **步骤 4：修改 on_think_start — 每轮都读 STM**

```python
async def on_think_start(self, ctx: RunContext) -> None:
    user_input = ctx.task_description
    if not user_input:
        return
    user_id = self._get_user_id()
    v1_mw = self._ensure_v1_mw()
    if v1_mw is None:
        return

    try:
        context = await v1_mw.get_user_context(user_id, user_input)
        if context:
            note = ("注意：下方 [最近对话] 中的信息优先级最高，"
                    "它反映了用户在本轮对话中刚说过的话。"
                    "如果 [最近对话] 与 [用户画像] 或 [相关记忆] 有冲突，以 [最近对话] 为准。")
            ctx.knowledge_context += (
                f"\n── 记忆上下文 ──\n{note}\n\n{context}\n──"
            )
            if len(ctx.knowledge_context) > 8000:
                ctx.knowledge_context = ctx.knowledge_context[-8000:]
            print(f"    \033[1;35m🧠 记忆: {len(context)} 字符上下文已注入\033[0m")
        else:
            print(f"    \033[2;35m🧠 记忆: 无相关历史\033[0m")
    except Exception as e:
        logger.debug(f"V1 记忆检索失败: {e}")
```

改动要点：
- 删掉 `self._last_query` 守卫，每轮都注入
- 删掉 `user_input != self._last_query` 条件
- 截断上限 4000→8000

- [ ] **步骤 5：运行测试**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent && python -m pytest tests/test_memory_middleware.py tests/test_v1_memory_e2e.py -v 2>&1
```
预期：全部通过

- [ ] **步骤 6：Commit**

```bash
git add core/multi_agent_v2/agents/memory_middleware.py
git add tests/test_memory_middleware.py
git commit -m "fix: MemoryMiddleware每轮写STM+每轮读STM，完成执行反馈闭环"
```
