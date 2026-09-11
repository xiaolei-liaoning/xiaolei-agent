"""快速端到端测试 — 核心功能验证"""

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, REPO_ROOT)
os.environ.setdefault('XIAOLEI_REAL_LLM', '1')


async def test_1_tool_registry():
    """测试 1: 工具注册表"""
    print("\n[TEST 1] 工具注册表")
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    
    reg = get_tool_registry()
    await reg.discover_all()
    
    total = len(reg._tools)
    print(f"  注册工具数: {total}")
    
    # 检查关键工具
    critical = ["web_search", "fetch_url", "read_file", "write_file", 
                "execute_python", "execute_shell", "task", "orchestrate"]
    missing = [t for t in critical if t not in reg._tools]
    
    if missing:
        print(f"  ❌ 缺失关键工具: {missing}")
        return False
    print(f"  ✅ 关键工具全部注册")
    return True


async def test_2_tool_selection():
    """测试 2: 工具选择质量"""
    print("\n[TEST 2] 工具选择质量")
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    
    reg = get_tool_registry()
    tools = await reg.get_tools_for_task("搜索 Python 文档", max_tools=10)
    
    tool_names = {t.name for t in tools}
    has_search = "web_search" in tool_names
    has_fetch = "fetch_url" in tool_names
    
    print(f"  web_search: {'✅' if has_search else '❌'}")
    print(f"  fetch_url: {'✅' if has_fetch else '❌'}")
    
    return has_search and has_fetch


async def test_3_mcp_tools():
    """测试 3: MCP 工具连接"""
    print("\n[TEST 3] MCP 工具")
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    
    reg = get_tool_registry()
    await reg.discover_all()
    
    mcp_tools = {
        "deepwiki": "get-deepwiki-page" in reg._tools,
        "context7": "query-docs" in reg._tools or "resolve-library-id" in reg._tools,
    }
    
    for name, ok in mcp_tools.items():
        print(f"  {name}: {'✅' if ok else '❌'}")
    
    return all(mcp_tools.values())


async def test_4_skill_system():
    """测试 4: Skill 系统"""
    print("\n[TEST 4] Skill 系统")
    from core.multi_agent_v2.skills.skill_loader import discover_skills, format_skills_xml
    
    skills = discover_skills()
    print(f"  发现 skills: {len(skills)}")
    
    if skills:
        xml = format_skills_xml(skills)
        has_xml = "<available_skills>" in xml
        print(f"  XML 格式化: {'✅' if has_xml else '❌'}")
        return has_xml
    
    print(f"  ⚠️ 无 skills 发现")
    return True  # 不算失败


async def test_5_llm_basic():
    """测试 5: LLM 基础调用"""
    print("\n[TEST 5] LLM 基础调用")
    from core.engine.llm_backend import get_llm_router
    
    router = get_llm_router()
    
    try:
        result = await router.simple_chat("Say hello in 3 words")
        result_str = str(result)
        has_response = len(result_str) > 5 and "mock" not in result_str.lower()
        print(f"  响应长度: {len(result_str)} 字符")
        print(f"  LLM 可用: {'✅' if has_response else '❌'}")
        return has_response
    except Exception as e:
        print(f"  ❌ LLM 调用失败: {e}")
        return False


async def test_6_llm_with_tools():
    """测试 6: LLM 工具调用"""
    print("\n[TEST 6] LLM 工具调用能力")
    from core.engine.llm_backend import get_llm_router
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    from core.multi_agent_v2.tools.schema import get_schema_adapter
    
    router = get_llm_router()
    reg = get_tool_registry()
    await reg.discover_all()
    
    # 准备工具
    tools = await reg.get_tools_for_task("搜索文档", max_tools=3)
    adapter = get_schema_adapter("deepseek-v4-flash")
    tool_defs = adapter.adapt([
        {'type': 'function', 'function': {'name': t.name, 'description': t.description, 'parameters': t.parameters}}
        for t in tools
    ])
    
    messages = [
        {'role': 'system', 'content': 'Use tools when needed.'},
        {'role': 'user', 'content': 'Search for Python docs'},
    ]
    
    try:
        result = await router.chat_stream_compat(messages, tools=tool_defs, max_tokens=100)
        result_str = str(result)
        
        has_tool_calls = "tool_calls" in result_str
        print(f"  返回 tool_calls: {'✅' if has_tool_calls else '❌'}")
        
        if has_tool_calls:
            import json
            try:
                data = json.loads(result_str)
                if data.get("choices"):
                    tc = data["choices"][0].get("message", {}).get("tool_calls", [])
                    print(f"  工具调用数量: {len(tc)}")
                    for t in tc:
                        print(f"    - {t.get('function', {}).get('name')}")
            except:
                pass
        
        return has_tool_calls
    except Exception as e:
        print(f"  ❌ LLM 工具调用失败: {e}")
        return False


async def test_7_react_simple():
    """测试 7: 简单 ReAct 循环"""
    print("\n[TEST 7] 简单 ReAct 循环")
    from core.multi_agent_v2.agents.react_core import run_react
    
    try:
        result = await run_react(
            task_description="用一句话回答：地球是什么形状？",
            max_rounds=1,
        )
        
        success = result.get("success", False)
        answer = result.get("answer", "")
        tools_used = len(result.get("tool_results", []))
        
        print(f"  完成: {'✅' if success else '❌'}")
        print(f"  答案长度: {len(answer)} 字符")
        print(f"  工具调用: {tools_used} 次")
        
        return success and len(answer) > 10
    except Exception as e:
        print(f"  ❌ ReAct 循环失败: {e}")
        return False


async def main():
    print("="*60)
    print("  深度端到端测试 — 快速版")
    print("="*60)
    
    results = {}
    
    # 运行测试
    results["tool_registry"] = await test_1_tool_registry()
    results["tool_selection"] = await test_2_tool_selection()
    results["mcp_tools"] = await test_3_mcp_tools()
    results["skill_system"] = await test_4_skill_system()
    results["llm_basic"] = await test_5_llm_basic()
    results["llm_with_tools"] = await test_6_llm_with_tools()
    results["react_simple"] = await test_7_react_simple()
    
    # 汇总
    print("\n" + "="*60)
    print("  测试结果汇总")
    print("="*60)
    
    passed = 0
    for name, result in results.items():
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{len(results)} 通过")
    
    return results


if __name__ == "__main__":
    results = asyncio.run(main())
