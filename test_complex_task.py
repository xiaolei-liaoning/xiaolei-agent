import asyncio 
import sys 
from pathlib import Path 

sys.path.insert(0, str(Path(__file__).parent)) 

from core.intent_recognizer import IntentRecognizer, get_skills_for_intent 
from core.task_decomposer import TaskDecomposer 


async def test_complex_task(): 
    """测试超长复杂任务""" 
    print("=" * 70) 
    print("测试: 超长复杂任务处理") 
    print("=" * 70) 
    
    # 超长复杂任务 
    complex_task = """ 
    请帮我完成以下任务： 
    1. 首先搜索人工智能领域的最新研究进展，包括大语言模型、计算机视觉、强化学习三个方向 
    2. 然后爬取相关的学术论文和技术博客 
    3. 对收集到的数据进行分析，提取关键技术趋势 
    4. 将分析结果翻译成英文 
    5. 生成一份详细的技术报告，包括图表和总结 
    6. 最后发送邮件给团队成员分享这份报告 
    """ 
    
    # 意图识别 
    print("\n【步骤1: 意图识别】") 
    recognizer = IntentRecognizer() 
    result = recognizer.recognize(complex_task) 
    
    print(f"主意图: {result['primary_intent']}") 
    print(f"置信度: {result['confidence']:.2f}") 
    print(f"多意图识别:") 
    for intent in result["multi_intents"]: 
        print(f"  - {intent['intent']} (置信度: {intent['confidence']:.2f})") 
    
    # 获取推荐技能 
    print(f"\n推荐技能: {get_skills_for_intent(result['primary_intent'])}") 
    
    # 任务拆解（模拟，不实际调用LLM） 
    print("\n【步骤2: 任务拆解】") 
    print("复杂任务拆解为以下子任务:") 
    
    # 模拟拆解结果 
    subtasks = [ 
        {"step": 1, "action": "search", "description": "搜索大语言模型最新进展", "params": {"query": "大语言模型 2024 最新研究"}}, 
        {"step": 2, "action": "search", "description": "搜索计算机视觉最新进展", "params": {"query": "计算机视觉 2024 最新研究"}}, 
        {"step": 3, "action": "search", "description": "搜索强化学习最新进展", "params": {"query": "强化学习 2024 最新研究"}}, 
        {"step": 4, "action": "scrape", "description": "爬取学术论文", "params": {"source": "arXiv"}}, 
        {"step": 5, "action": "scrape", "description": "爬取技术博客", "params": {"source": "Medium, Towards Data Science"}}, 
        {"step": 6, "action": "analyze", "description": "分析数据提取技术趋势", "params": {"data_source": "scraped_data"}}, 
        {"step": 7, "action": "translate", "description": "翻译分析结果", "params": {"target_language": "English"}}, 
        {"step": 8, "action": "summarize", "description": "生成技术报告", "params": {"format": "detailed_report"}}, 
        {"step": 9, "action": "send", "description": "发送邮件", "params": {"recipients": "team@example.com", "attachment": "report.pdf"}} 
    ] 
    
    for task in subtasks: 
        print(f"  [{task['step']}] {task['action']}: {task['description']}") 
    
    print(f"\n总子任务数: {len(subtasks)}") 
    print("预计执行时间: 根据各子任务复杂度估算") 


if __name__ == "__main__": 
    asyncio.run(test_complex_task())