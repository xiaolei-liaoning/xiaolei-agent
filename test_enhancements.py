"""测试增强后的意图识别和任务拆解功能"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from core.intent_recognizer import IntentRecognizer, get_skills_for_intent, get_intent_category
from core.task_splitter import TaskSplitter


async def test_intent_recognition():
    """测试意图识别功能"""
    print("=" * 70)
    print("测试1: 意图识别（增强版）")
    print("=" * 70)
    
    recognizer = IntentRecognizer()
    
    # 测试用例
    test_cases = [
        "请帮我搜索人工智能最新发展",
        "打开微信",
        "天气怎么样",
        "翻译这段文字",
        "分析数据并总结",
        "你好，我想了解一下产品",
        "紧急！帮我查一下股票",
        "先搜索资料，然后分析，最后总结",
        "比较iPhone和安卓手机",
        "谢谢，再见"
    ]
    
    for message in test_cases:
        result = recognizer.recognize(message)
        skills = get_skills_for_intent(result["primary_intent"])
        category = get_intent_category(result["primary_intent"])
        
        print(f"\n用户输入: {message}")
        print(f"  主意图: {result['primary_intent']} (置信度: {result['confidence']:.2f})")
        print(f"  意图分类: {category}")
        print(f"  推荐技能: {skills}")
        
        # 如果有多个意图
        if len(result["multi_intents"]) > 1:
            print(f"  多意图识别:")
            for intent in result["multi_intents"]:
                print(f"    - {intent['intent']} (置信度: {intent['confidence']:.2f})")


async def test_task_splitter():
    """测试任务拆解功能"""
    print("\n" + "=" * 70)
    print("测试2: 任务拆解（增强版）")
    print("=" * 70)
    
    splitter = TaskSplitter()
    
    # 测试规则拆解
    print("\n测试规则拆解:")
    research_result = await splitter.split("research_topic", {"topic": "人工智能"})
    print(f"任务类型: research_topic")
    print(f"生成子任务数: {len(research_result)}")
    for i, task in enumerate(research_result, 1):
        print(f"  步骤{i}: {task['type']} - {task.get('params', {})}")
    
    # 测试缓存
    print("\n测试缓存机制:")
    stats = splitter.get_global_cache_stats()
    print(f"全局缓存统计: {stats}")
    
    # 测试LLM拆解（简单测试，不实际调用LLM）
    print("\n测试LLM拆解（模拟）:")
    # 创建一个简单的测试，不调用实际LLM
    simple_result = [
        {"type": "search", "params": {"query": "测试"}, "step_number": 1, "total_steps": 2},
        {"type": "summarize", "params": {"text": "$search_result"}, "step_number": 2, "total_steps": 2}
    ]
    print(f"生成子任务数: {len(simple_result)}")
    for task in simple_result:
        print(f"  步骤{task['step_number']}: {task['type']} - {task['params']}")


async def test_context_understanding():
    """测试上下文理解"""
    print("\n" + "=" * 70)
    print("测试3: 上下文理解")
    print("=" * 70)
    
    recognizer = IntentRecognizer()
    
    # 模拟对话历史
    print("\n对话历史测试:")
    messages = [
        "你好",
        "帮我查一下天气",
        "北京的",
        "明天的"
    ]
    
    for i, message in enumerate(messages):
        result = recognizer.recognize(message)
        history_info = recognizer.get_history_summary()
        print(f"\n消息{i+1}: {message}")
        print(f"  识别意图: {result['primary_intent']} (置信度: {result['confidence']:.2f})")
        print(f"  历史消息数: {history_info['history_length']}")


if __name__ == "__main__":
    print("\n" + "*" * 70)
    print("Agent系统增强功能测试")
    print("*" * 70)
    
    asyncio.run(test_intent_recognition())
    asyncio.run(test_task_splitter())
    asyncio.run(test_context_understanding())
    
    print("\n" + "*" * 70)
    print("测试完成！")
    print("*" * 70)