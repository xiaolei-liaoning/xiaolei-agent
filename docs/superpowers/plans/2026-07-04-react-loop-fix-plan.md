# ReAct 循环重复调用修复 — 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复项目分析中 ReAct 循环的 4 个关联问题：同轮重复工具调用、子代理工具重叠、只读步骤跳过、过早 fallback。

**架构：** 3 个独立模块，各自修改单一文件，互不依赖：
- 模块 1: `react_core.py:on_tool_invoke` — 同轮 (tool_name, args) 去重
- 模块 2: `plan_manager.py:update_step_status` — 泛化工具自动完成后续步骤
- 模块 3: `react_core.py` 主循环 — 只读步骤询问用户是否跳过

**技术栈：** Python 3.10+ asyncio, pytest mock

---

### 任务 1：同轮去重

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py:662-670`
- 测试：`tests/v2/test_react_core_mock.py`

- [ ] **步骤 1：编写失败的测试**

```python
@pytest.mark.asyncio
async def test_dedup_identical_tool_calls():
    """同轮相同参数去重：2 个 read_file('t.txt') → 只执行 1 次"""
    import core.multi_agent_v2.agents.react_core as _rc
    import core.engine.llm_backend as _lb
    import core.multi_agent_v2.tools.tool_registry as _tr

    _call_count = 0
    async def _count_handler(args):
        nonlocal _call_count
        _call_count += 1
        return {"ok": True, "data": "content"}

    reg = _make_reg([
        ("read_file", AsyncMock(side_effect=_count_handler),
         {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    ])
    _rc.ReActCoreMiddleware.on_start.side_effect = lambda ctx: setattr(
        ctx, '_tool_cache', list(reg._tools.values())
    ) or None
    _lb.get_llm_router.return_value = _make_router([
        "分析", "步骤|测|read_file",
        '[{"type":"function","function":{"name":"read_file","arguments":{"path":"t.txt"}}},'
        '{"type":"function","function":{"name":"read_file","arguments":{"path":"t.txt"}}}]',
    ])
    with patch.object(_tr, "get_tool_registry", return_value=reg):
        result = await run_react("dedup test")
    assert _call_count == 1, f"Expected 1 execution, got {_call_count}"
```

- [ ] **步骤 2：运行测试验证失败**

```
pytest tests/v2/test_react_core_mock.py::test_dedup_identical_tool_calls -v
```
预期：FAIL，`_call_count == 2` 而不是 1

- [ ] **步骤 3：实现去重代码**

在 `react_core.py` 的 `on_tool_invoke` 中、`excute_tool_calls_parallel` 之前插入：

```python
# 同轮内相同 (tool_name + 参数) 去重
_seen = set()
_unique = []
for tc in tool_calls:
    _fn = tc.get("function", {})
    _key = (_fn.get("name", ""), json.dumps(_fn.get("arguments", {}), sort_keys=True))
    if _key not in _seen:
        _seen.add(_key)
        _unique.append(tc)
tool_calls = _unique
```

- [ ] **步骤 4：运行测试验证通过**

```
pytest tests/v2/test_react_core_mock.py::test_dedup_identical_tool_calls -v
```
预期：PASS，`_call_count == 1`

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py tests/v2/test_react_core_mock.py
git commit -m "fix: 同轮相同参数工具调用去重"
```

---

### 任务 2：子代理步骤合并

**文件：**
- 修改：`core/multi_agent_v2/agents/plan_manager.py` — `update_step_status` 末尾
- 测试：`tests/v2/test_react_core_mock.py`

- [ ] **步骤 1：编写失败的测试**

```python
@pytest.mark.asyncio
async def test_step_consolidation_task_orchestrate():
    """orchestrate 完成后后续 task 步骤自动 done"""
    from core.multi_agent_v2.agents.plan_manager import update_step_status
    from core.multi_agent_v2.agents.middleware import PlanStep, RunContext

    ctx = RunContext("test")
    ctx.plan = [
        PlanStep(index=1, description="探索项目", tool_names=["codegraph_explore"]),
        PlanStep(index=2, description="子代理分析", tool_names=["orchestrate"]),
        PlanStep(index=3, description="子代理详情", tool_names=["task"]),
    ]
    ctx.plan[0].status = "done"

    # mock context: orchestrate 已调用成功
    ctx.tool_results = [
        {"tool_call": {"name": "orchestrate", "arguments": {"task1": "..."}},
         "success": True,
         "result": {"output": "探索结果"}},
    ]
    update_step_status(ctx)
    assert ctx.plan[2].status == "done", "task 步骤应被 orchestrate 覆盖"
```

- [ ] **步骤 2：运行测试验证失败**

```
pytest tests/v2/test_react_core_mock.py::test_step_consolidation_task_orchestrate -v
```
预期：FAIL

- [ ] **步骤 3：实现步骤合并代码**

在 `plan_manager.py` 的 `update_step_status` 中，当前步骤标记 done 后但在 `return` 前插入：

```python
# 泛化工具覆盖：当前步骤的泛工具完成后续同类型步骤
_subagent_tools = {"task", "orchestrate"}
if current_step.tool_names and set(current_step.tool_names) & _subagent_tools:
    for s in ctx.plan:
        if s.status == "pending" and s.tool_names and set(s.tool_names) & _subagent_tools:
            s.status = "done"
            logger.debug(f"步骤 {s.index} 被步骤 {current_step.index} 覆盖，自动完成")
```

- [ ] **步骤 4：运行测试验证通过**

```
pytest tests/v2/test_react_core_mock.py::test_step_consolidation_task_orchestrate -v
```
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/plan_manager.py tests/v2/test_react_core_mock.py
git commit -m "fix: orchestrate/task 泛化覆盖后续子代理步骤"
```

---

### 任务 3：用户裁决只读步骤

**文件：**
- 修改：`core/multi_agent_v2/agents/react_core.py` — 主循环，`on_llm_invoke` 返回后
- 测试：`tests/v2/test_react_core_mock.py`

- [ ] **步骤 1：编写失败的测试**

```python
@pytest.mark.asyncio
async def test_user_bypass_readonly_steps():
    """只读步骤 + LLM 输出结论 + 用户按 Enter → 剩余步骤自动完成"""
    import core.multi_agent_v2.agents.react_core as _rc
    import core.engine.llm_backend as _lb
    import core.multi_agent_v2.tools.tool_registry as _tr

    reg = _make_reg()
    _rc.ReActCoreMiddleware.on_start.side_effect = lambda ctx: setattr(
        ctx, '_tool_cache', list(reg._tools.values())
    ) or None

    # mock asyncio.to_thread → 模拟用户按 Enter
    _orig_to_thread = asyncio.to_thread

    # LLM 第二次回复是结论文本，没有工具调用
    _lb.get_llm_router.return_value = _make_router([
        "分析项目任务",                             # plan take1
        "步骤|探索项目|codegraph_explore\n步骤|检查配置|read_file",  # plan take2
        '{"type":"function","function":{"name":"read_file","arguments":{"path":"README.md"}}}',  # round1 tool
        "## 项目分析\n\n该项目是一个测试框架\n## 结论\n结构清晰",  # round2 text
    ])

    with (
        patch.object(_tr, "get_tool_registry", return_value=reg),
        patch("asyncio.to_thread", new=AsyncMock(return_value="")),  # 用户按 Enter
    ):
        result = await run_react("analyze project")
    assert result["success"], "应成功产出最终结论"
```

- [ ] **步骤 2：运行测试验证失败**

```
pytest tests/v2/test_react_core_mock.py::test_user_bypass_readonly_steps -v
```
预期：FAIL（代码尚不存在）

- [ ] **步骤 3：实现用户裁决逻辑**

在 `react_core.py` 主循环中，`chain.on_llm_invoke` 返回后、`chain.on_tool_invoke` 前插入：

```python
# 用户裁决：LLM 没调工具 + 剩余步骤只读 → 询问用户是否跳过
if not ctx._pending_tool_calls and ctx.plan and not getattr(ctx, '_is_subagent', False):
    _pending = [s for s in ctx.plan if s.status == "pending"]
    _readonly_tools = {"read_file", "codegraph_explore", "codegraph_files", "search_files"}
    if _pending and all(
        not s.tool_names or set(s.tool_names) <= _readonly_tools
        for s in _pending
    ):
        from core.multi_agent_v2.tools.tool_result import from_handler as _fmt_result
        _last = str(getattr(ctx, '_pending_reply', ''))
        if _last.startswith("{"):
            _extracted = _extract_text_from_json(_last)
            if _extracted:
                _last = _extracted
        print(f"\n  【当前结论片段】{_last[:200]}...")
        print(f"  剩余步骤未执行：{', '.join(s.description[:40] for s in _pending)}")
        _ans = await asyncio.to_thread(
            input, "  当前结论已足够？按 Enter 跳过剩余步骤，输入 '继续' 执行: "
        )
        if not _ans or _ans.lower() in ('y', 'yes', ''):
            for s in _pending:
                s.status = "done"
            continue
```

- [ ] **步骤 4：运行测试验证通过**

```
pytest tests/v2/test_react_core_mock.py::test_user_bypass_readonly_steps -v
```
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add core/multi_agent_v2/agents/react_core.py tests/v2/test_react_core_mock.py
git commit -m "fix: 只读步骤用户裁决跳过"
```

---

### 验证

```bash
pytest tests/v2/test_react_core_mock.py -v
```

预期：全部 9+ 测试 PASS（原有 6 个 + 新增 3 个）
