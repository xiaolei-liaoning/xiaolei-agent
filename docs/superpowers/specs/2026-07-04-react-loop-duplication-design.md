# ReAct 循环重复调用与步骤自动完成 — 设计规格

## 问题

项目分析类任务中 ReAct 循环的 4 个关联问题：

1. **同轮重复调用** — LLM 在一轮中生成多个相同 (tool_name + 参数) 的工具调用，全部执行浪费
2. **子代理工具重叠** — `orchestrate` 已派发多个子代理覆盖探索工作，后续步骤仍强迫 LLM 再调 `task`，子代理重复运行
3. **只读步骤跳过** — LLM 已有足够信息直接出结论，但不执行剩余计划步骤；系统无绕过机制，循环空转耗尽后走 fallback Summarizing
4. **过早 fallback** — 主循环空转退出后，fallback summarization 生成报告，skip 了一个未执行的步骤

## 方案概要

三个独立模块，~25 行总改动，不动现有逻辑结构。

## 模块 1：同轮去重

**文件**: `core/multi_agent_v2/agents/react_core.py` — `on_tool_invoke`

在工具调用执行前，按 (tool_name, arguments_hash) 去重。

```python
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

## 模块 2：子代理步骤合并

**文件**: `core/multi_agent_v2/agents/plan_manager.py` — `update_step_status`

步骤工具集合满足"泛化关系"时，自动标记后续步骤完成：

| 当前工具 | 覆盖的下游工具 |
|---------|--------------|
| orchestrate | task |
| task | orchestrate |

实现：在 `update_step_status` 标记当前步骤 done 前，扫描剩余 pending 步骤，如果它们的工具被当前步骤工具覆盖，一并标记 done。

## 模块 3：用户裁决只读步骤

**文件**: `core/multi_agent_v2/agents/react_core.py` — 主循环，`on_llm_invoke` 返回后

LLM 本轮未调工具 + 剩余步骤均为只读/探索类 → 打印结论片段，询问用户是否跳过。

触发条件：
- `ctx._pending_tool_calls` 为空
- `ctx.plan` 有剩余 pending 步骤
- 剩余步骤的 tool_names 均为 `{read_file, codegraph_explore, codegraph_files, search_files}` 子集

用户体验：
```
【当前结论片段】根据分析，Arbor 项目是一个......
剩余步骤未执行：检查配置文件和示例代码
当前结论已足够？按 Enter 跳过剩余步骤，输入 '继续' 执行:
```

用户按 Enter → 标记剩余步骤 done → 循环检测 all_done → 正常退出
用户输入 '继续' → 继续执行，不干涉 LLM

### 边界情况

- 子代理场景 `_is_subagent=True`：不触发用户询问（子代理不与用户交互）
- 所有工具类型包括 write_file/edit_file：不属于只读，不触发
- 剩余步骤混有读写 + 只读：不触发
