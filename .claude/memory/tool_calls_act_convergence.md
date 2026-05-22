---
name: tool_calls-act-convergence
description: WorkerAgent.execute() 和 BaseAgent.run() 通过 act(tool_calls=...) 收敛的解决思路
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 56542e99-db69-4b88-8156-dc17a21d5f9d
---

**WorkerAgent.execute() 必须收敛到 BaseAgent.run()，不能走独立执行路径。**

之前 `run()` 调用 `act(thought.plan)` 时丢弃了 LLM 精确选择的 `tool_calls`，导致 `_execute_step()` 重新做不可靠的关键词匹配。而 `WorkerAgent.execute()` 虽然正确使用了 `_last_tool_calls`，但从 CLI 入口 (`WorkflowEngineWrapper.create_and_execute()`) 无法到达。

**Why:** `act()` 原来的签名只接受 `plan: List[str]`，`run()` 无法传递 LLM 构造的 tool_calls。两条路径各维护一套工具调用逻辑（`_execute_step` 的关键词路由 vs `_execute_task` 的 `_last_tool_calls`），分散且不一致。

**How to apply:** 修复方法是在 `act()` 签名增加 `tool_calls: Optional[List[Dict]] = None` 参数。当非空时直接委托给 `_execute_tool_calls(tool_calls)` 执行 LLM 选择结果，绕过 plan 的关键词匹配。对应地 `run()` 通过 `getattr(thought, 'tool_calls', None)` 获取并传递。`WorkerAgent.execute()` 改为调用 `self.act(thought.plan, thought.tool_calls)`，不再使用 `_last_tool_calls` 中间缓存。

同时增强了 `_extract_tool_calls()` 的支持格式（GLM → OpenAI → 正则提取三级级联），`_calculate_confidence()` 改为多因子而非仅文本长度。

涉及文件：`base_agent.py` 的 `act()`、`run()`、`_think_with_llm()`、`_parse_llm_response()`，以及 `worker_agent.py` 的 `execute()`。
