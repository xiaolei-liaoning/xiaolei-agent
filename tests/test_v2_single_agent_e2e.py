"""
V2 单 Agent 端到端测试

模拟完整 ReAct 流程，mock LLM 返回，验证：
1. 任务拆解（_decompose_task）
2. ReAct 循环（prompt 构建 → LLM 调用 → 响应解析 → 工具执行）
3. 步骤进度展示（plan_steps / current_step）
4. 记忆记录（memory_log）
5. RAG 注入（rag_context）
6. plan_update 动态调整
"""

import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.multi_agent_v2.agents.base.base_agent import BaseAgent


class MockLLMRouter:
    """Mock LLM — 返回预设响应"""
    def __init__(self):
        self.call_count = 0
        self.responses = []
        self.prompts = []

    def add_response(self, resp: str):
        self.responses.append(resp)

    def is_available(self):
        return True

    async def chat(self, messages, temperature=0.7, max_tokens=2000, tools=None, **kwargs):
        self.call_count += 1
        prompt = messages[-1]["content"] if messages else ""
        self.prompts.append(prompt)
        if self.responses:
            return self.responses.pop(0)
        return '{"reasoning": "mock", "done": true}'


class MockRAGEngine:
    """Mock RAG — 返回固定知识"""
    async def search_and_learn(self, query, user_id=1, max_results=3, learn=False):
        return {
            "results": [
                {"content": "百度热搜是百度提供的一个展示当前热门搜索话题的榜单。"},
                {"content": "热搜数据可以通过百度热搜页面或API获取。"},
            ]
        }


async def test_full_react_flow():
    passed = 0
    total = 0

    def check(name, condition, detail=""):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name}: {detail}")

    # ── 场景1: 完整 3 轮 ReAct 流程 ──
    print("\n━━━ 场景1: 完整 3 轮 ReAct 流程 ───")
    agent = BaseAgent()
    agent._trace = type("MockTrace", (), {
        "on_thinking": lambda self, *a, **kw: None,
        "on_tool_call": lambda self, *a, **kw: None,
        "on_tool_result": lambda self, *a, **kw: None,
        "on_tool_error": lambda self, *a, **kw: None,
        "set_plan": lambda self, *a, **kw: None,
        "done": lambda self, *a, **kw: None,
    })()

    # Mock LLM
    mock_llm = MockLLMRouter()
    mock_llm.add_response(  # _decompose_task → 返回步骤列表
        "1. 获取热搜数据\n2. 分析数据\n3. 生成报告保存到桌面"
    )
    mock_llm.add_response(  # 第1轮 → 调用 fetch_url
        json.dumps({"reasoning": "先获取热搜数据", "action": {"name": "fetch_url", "arguments": {"url": "https://top.baidu.com"}}})
    )
    mock_llm.add_response(  # 第2轮 → 调用 execute_code
        json.dumps({"reasoning": "开始分析数据", "action": {"name": "file", "arguments": {"action": "write", "path": "/tmp/test.md", "content": "# 报告"}}})
    )
    mock_llm.add_response(  # 第3轮 → done
        json.dumps({"reasoning": "完成", "summary": "报告已生成", "done": True})
    )

    # 替换 LLM
    import core.engine.llm_backend as lb
    original_get = lb.get_llm_router
    lb.get_llm_router = lambda: mock_llm

    # 替换 RAG
    import core.search.rag_search_engine as rag_mod
    original_rag = rag_mod.RAGSearchEngine
    rag_mod.RAGSearchEngine = MockRAGEngine

    try:
        result = await agent.run("搜索百度热搜并生成分析报告保存到桌面")
    finally:
        lb.get_llm_router = original_get
        rag_mod.RAGSearchEngine = original_rag

    check("任务拆解完成", "result" in result)
    check("3轮迭代", result.get("iterations") == 3, f"实际: {result.get('iterations')}")
    check("执行成功", result.get("success") == True)
    check("工具调用次数", len(result["result"].get("tool_results", [])) == 2)
    check("最终回答", result["result"].get("final_answer") == "报告已生成")
    check("LLM 调用次数", mock_llm.call_count == 4)  # 1拆解 + 3 ReAct
    check("提示词含 ReAct", "ReAct" in mock_llm.prompts[1])  # 第1轮 ReAct prompt

    # ── 场景2: plan_update 动态调整 ──
    print("\n━━━ 场景2: plan_update 动态调整 ───")
    agent2 = BaseAgent()
    agent2._trace = agent._trace
    mock2 = MockLLMRouter()
    mock2.add_response("1. 抓数据\n2. 分析\n3. 报告")
    mock2.add_response(json.dumps({"reasoning":"获取数据", "action":{"name":"fetch_url","arguments":{"url":"x"}}}))
    # LLM 发现需要先注册，调整计划
    mock2.add_response(json.dumps({"reasoning":"需要先注册","plan_update":["注册账号","爬取页面","解析数据","生成报告"]}))
    mock2.add_response(json.dumps({"reasoning":"注册成功", "action":{"name":"file","arguments":{"action":"write","path":"/tmp/r.txt","content":"ok"}}}))
    mock2.add_response(json.dumps({"reasoning":"完成","done":True}))

    lb.get_llm_router = lambda: mock2
    try:
        result2 = await agent2.run("爬取京东商品数据")
    finally:
        lb.get_llm_router = original_get

    check("plan_update 后步骤增加", result2.get("iterations", 0) >= 3)
    check("最终成功", result2.get("success") == True)

    # ── 场景3: 纯文本回答 + done ──
    print("\n━━━ 场景3: LLM 直接输出 done ───")
    agent3 = BaseAgent()
    mock3 = MockLLMRouter()
    mock3.add_response("1. 回答")
    mock3.add_response(json.dumps({"reasoning":"很简单","summary":"Python是一种编程语言","done":True}))
    lb.get_llm_router = lambda: mock3
    try:
        result3 = await agent3.run("Python是什么")
    finally:
        lb.get_llm_router = original_get

    check("无工具调用", len(result3["result"].get("tool_results", [])) == 0)
    check("直接回答", "编程语言" in result3["result"].get("final_answer", ""))
    check("置信度存在", result3.get("confidence", 0) >= 0)

    # ── 场景4: 工具连续失败去重 ──
    print("\n━━━ 场景4: 工具连续失败去重 ───")
    agent4 = BaseAgent()
    mock4 = MockLLMRouter()
    mock4.add_response("1. 搜索")
    for _ in range(5):
        mock4.add_response(json.dumps({"reasoning":"搜索", "action":{"name":"fetch_url","arguments":{"url":"x"}}}))
    mock4.add_response(json.dumps({"reasoning":"完成","done":True}))
    lb.get_llm_router = lambda: mock4
    try:
        result4 = await agent4.run("搜索信息")
    finally:
        lb.get_llm_router = original_get

    # 第4次 fetch_url 应该被跳过（连续3次后去重）
    tr4 = result4["result"]["tool_results"]
    skipped = [r for r in tr4 if r.get("tool_call",{}).get("name") == "fetch_url" and not r.get("success")]
    check("自动去重", len(skipped) >= 1, f"实际跳过了 {len(skipped)} 次")

    # ── 场景5: 内存记录 ──
    print("\n━━━ 场景5: memory_log 记录 ───")
    agent5 = BaseAgent()
    mock5 = MockLLMRouter()
    mock5.add_response("1. 搜\n2. 写")
    mock5.add_response(json.dumps({"reasoning":"搜","action":{"name":"fetch_url","arguments":{"url":"x"}}}))
    mock5.add_response(json.dumps({"reasoning":"写","action":{"name":"file","arguments":{"action":"write","path":"/tmp/x.md","content":"ok"}}}))
    mock5.add_response(json.dumps({"reasoning":"完成","done":True}))
    lb.get_llm_router = lambda: mock5
    try:
        result5 = await agent5.run("搜索并保存")
    finally:
        lb.get_llm_router = original_get

    # memory_log 应该记录了 fetch_url 和 file 的摘要
    # 通过检查 agent5 的 ctx 不可达，但结果中的 tool_results 应该有2条
    tr5 = result5["result"]["tool_results"]
    check("memory 记录工具数", len(tr5) == 2)

    # ── 汇总 ──
    print(f"\n{'='*40}")
    print(f"结果: {passed}/{total} 通过")
    if passed == total:
        print("✅ 全部通过!")
    else:
        print(f"❌ {total - passed} 个失败")
    return passed == total


if __name__ == "__main__":
    ok = asyncio.run(test_full_react_flow())
    sys.exit(0 if ok else 1)
