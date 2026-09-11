"""端到端测试 - 验证 Agent 完整工作流程（使用 Agnes）"""

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, REPO_ROOT)

# 加载 .env
from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault('XIAOLEI_REAL_LLM', '1')


async def test_agent_workflow():
    """测试完整 Agent 工作流程"""
    print("=" * 60)
    print("端到端测试: Agent 工作流程")
    print("=" * 60)
    
    # 1. 初始化后端
    from core.engine.llm_backend import GLMBackend
    backend = GLMBackend(api_key=os.getenv('GLM_API_KEY', ''))
    
    print(f"\n🔧 LLM 后端初始化:")
    print(f"   - openrouter_client: {backend.openrouter_client is not None}")
    print(f"   - deepseek_client: {getattr(backend, 'deepseek_client', None) is not None}")
    print(f"   - available: {backend.is_available()}")
    
    # 2. 测试基础聊天
    messages = [{'role': 'user', 'content': '你好，请回复 OK'}]
    print(f"\n💬 测试基础聊天...")
    response = await backend.chat(messages)
    print(f"   ✓ 响应长度: {len(response)} 字符")
    print(f"   ✓ 前50字符: {response[:50]}...")
    
    # 3. 测试工具调用
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    reg = get_tool_registry()
    await reg.discover_all()
    
    tools = await reg.get_tools_for_task("搜索百度热搜并分析")
    print(f"\n🔧 工具选择测试:")
    print(f"   - 注册工具数: {len(reg._tools)}")
    print(f"   - 选中工具数: {len(tools)}")
    if tools:
        # ToolDefinition 对象，用属性访问
        tool_names = [getattr(t, 'function', {}).get('name', str(t)) if isinstance(t, dict) else t.name for t in tools[:5]]
        print(f"   - 工具列表: {tool_names}")
    
    # 3. 测试带工具的 LLM 调用
    print(f"\n💬 测试工具调用...")
    
    # 转换工具为 OpenAI 格式
    from core.multi_agent_v2.tools.schema import get_schema_adapter
    adapter = get_schema_adapter()
    raw_defs = [{
        'name': t.name,
        'description': t.description,
        'parameters': t.parameters or {}
    } for t in tools]
    # 包装成 {"function": {...}} 格式
    wrapped_defs = [{'function': d} for d in raw_defs]
    formatted_tools = adapter.adapt(wrapped_defs)
    
    messages_with_tools = [
        {'role': 'system', 'content': '你是一个助手'},
        {'role': 'user', 'content': '什么是 Python？'}
    ]
    
    try:
        resp = await backend.chat_structured(messages_with_tools, tools=formatted_tools)
        print(f"   ✓ 响应类型: {type(resp)}")
        print(f"   ✓ 有 tool_calls: {resp.tool_calls is not None and len(resp.tool_calls) > 0}")
        if resp.tool_calls:
            print(f"   ✓ tool_calls 数量: {len(resp.tool_calls)}")
            for tc in resp.tool_calls:
                print(f"     - {tc['function']['name']}({tc['function']['arguments'][:50]})")
        else:
            print(f"   ✓ 直接回复: {resp.content[:100]}...")
    except Exception as e:
        print(f"   ✗ 错误: {e}")
    
    # 5. 运行完整 Agent
    print(f"\n🤖 运行完整 Agent...")
    from core.multi_agent_v2.agents.react_core import run_react
    
    task = "搜索百度热搜榜 今日 TOP10 并总结"
    print(f"   任务: {task}")
    
    try:
        result = await asyncio.wait_for(
            run_react(task, session_id="test_e2e"),
            timeout=120
        )
        print(f"   ✓ 完成")
        print(f"   ✓ 角色: {result.get('role', 'unknown')}")
        print(f"   ✓ 答案长度: {len(result.get('final_answer', ''))} 字符")
        print(f"   ✓ 工具调用: {result.get('tool_calls_used', 0)} 次")
        
        answer = result.get('final_answer', '')
        if answer and len(answer) > 20:
            print(f"\n✅ 测试通过！")
            print(f"   答案: {answer[:200]}...")
        else:
            print(f"\n⚠️ 答案过短或为空")
    except asyncio.TimeoutError:
        print(f"   ✗ 超时")
    except Exception as e:
        print(f"   ✗ 错误: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 60)


if __name__ == '__main__':
    asyncio.run(test_agent_workflow())
