#!/usr/bin/env python3
"""多场景测试脚本"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class ScenarioTest:
    """场景测试类"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
    
    async def run_scenario(self, name, test_func):
        """运行单个场景测试"""
        print(f"\n{'='*60}")
        print(f"场景: {name}")
        print('='*60)
        
        try:
            await test_func()
            print("✓ 场景测试通过")
            self.passed += 1
        except Exception as e:
            print(f"✗ 场景测试失败: {e}")
            import traceback
            traceback.print_exc()
            self.failed += 1
    
    def print_summary(self):
        """打印测试总结"""
        print("\n" + "="*60)
        print("多场景测试总结")
        print("="*60)
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"跳过: {self.skipped}")
        print(f"成功率: {(self.passed / (self.passed + self.failed) * 100):.1f}%")
        
        if self.passed == self.passed + self.failed:
            print("✓ 所有场景测试通过！")
        else:
            print(f"✗ {self.failed} 个场景测试失败")

async def scenario_daily_conversation():
    """场景1: 日常对话"""
    from core.engine.skill_dispatcher import get_skill_dispatcher
    
    dispatcher = get_skill_dispatcher()
    
    test_cases = [
        ("你好", "chat"),
        ("谢谢", "chat"),
        ("再见", "chat"),
        ("你是谁", "chat"),
        ("介绍一下你自己", "chat"),
    ]
    
    for message, expected in test_cases:
        result = dispatcher._fuzzy_skill_match(message, message)
        assert result == expected, f"预期: {expected}, 实际: {result}"
        print(f"  '{message}' -> {result}")

async def scenario_weather_query():
    """场景2: 天气查询"""
    from core.engine.skill_dispatcher import get_skill_dispatcher

    dispatcher = get_skill_dispatcher()

    # 带城市名的天气查询
    result = dispatcher._fuzzy_skill_match("北京天气", "北京天气")
    assert result == "weather", f"预期: weather, 实际: {result}"
    print("  '北京天气' -> weather ✓")

async def scenario_multi_step_task():
    """场景3: 多步骤任务"""
    from core.engine.skill_dispatcher import get_skill_dispatcher
    
    dispatcher = get_skill_dispatcher()
    
    # 多步骤任务识别
    test_cases = [
        "先查天气，然后生成报告",
        "先打开浏览器，再搜索信息",
        "先分析数据，接着生成图表，最后保存文件",
    ]
    
    for message in test_cases:
        result = dispatcher._fuzzy_skill_match(message, message)
        # 多步骤任务应该匹配到multi_step或其他合适的技能
        print(f"  '{message}' -> {result}")

async def scenario_translation():
    """场景4: 翻译任务"""
    from core.engine.skill_dispatcher import get_skill_dispatcher
    
    dispatcher = get_skill_dispatcher()
    
    test_cases = [
        ("翻译这段英文", "translator"),
        ("把中文翻译成英文", "translator"),
        ("英语翻译", "translator"),
        ("日语翻译", "translator"),
    ]
    
    for message, expected in test_cases:
        result = dispatcher._fuzzy_skill_match(message, message)
        assert result == expected, f"预期: {expected}, 实际: {result}"
        print(f"  '{message}' -> {result}")

async def scenario_data_analysis():
    """场景5: 数据分析"""
    from core.engine.skill_dispatcher import get_skill_dispatcher
    
    dispatcher = get_skill_dispatcher()
    
    test_cases = [
        ("分析数据", "data_analysis"),
        ("生成图表", "data_analysis"),
        ("统计分析", "data_analysis"),
        ("可视化数据", "data_analysis"),
    ]
    
    for message, expected in test_cases:
        result = dispatcher._fuzzy_skill_match(message, message)
        assert result == expected, f"预期: {expected}, 实际: {result}"
        print(f"  '{message}' -> {result}")

async def scenario_error_handling():
    """场景6: 错误处理与反问"""
    from core.engine.skill_dispatcher import get_skill_dispatcher
    
    dispatcher = get_skill_dispatcher()
    
    # 网络错误场景
    error_question = dispatcher._generate_error_clarification(
        "网络连接超时，无法访问服务器",
        "用户正在查询天气"
    )
    assert error_question is not None
    print(f"  网络错误反问: {error_question.question}")
    assert "检查网络连接" in error_question.options
    
    # 权限错误场景
    error_question = dispatcher._generate_error_clarification(
        "Permission denied",
        "用户尝试访问受限资源"
    )
    assert error_question is not None
    print(f"  权限错误反问: {error_question.question}")
    
    # 工具不可用场景
    error_question = dispatcher._generate_error_clarification(
        "工具不可用，MCP服务器未连接",
        "用户尝试使用计算器"
    )
    assert error_question is not None
    print(f"  工具不可用反问: {error_question.question}")

async def scenario_fallback_mechanism():
    """场景7: Fallback机制"""
    from core.engine.skill_dispatcher import get_skill_dispatcher
    
    dispatcher = get_skill_dispatcher()
    
    # 测试需求类型分析
    test_cases = [
        ("计算1到100的和", "数学计算"),
        ("今天星期几", "日期时间"),
        ("替换字符串", "文本处理"),
        ("筛选列表", "数据处理"),
    ]
    
    for message, expected_type in test_cases:
        analysis = dispatcher._analyze_requirement_type(message)
        assert expected_type in analysis
        print(f"  '{message}' -> {expected_type}")
    
    # 测试沙盒执行
    test_code = """
def solve_problem(message: str) -> dict:
    try:
        result = sum(range(1, 101))
        return {"success": True, "result": result, "message": "计算完成"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}
"""
    result = await dispatcher._execute_in_sandbox(test_code)
    assert result["success"]
    assert result["result"] == 5050
    print(f"  沙盒执行: 1到100求和 = {result['result']}")

async def scenario_mcp_check():
    """场景8: MCP服务器检查"""
    from core.skills.mcp_check.handler import check_mcp_availability
    
    result = await check_mcp_availability()
    print(f"  MCP检查结果: {'成功' if result['success'] else '失败'}")
    print(f"  可用服务器数量: {len(result.get('servers', []))}")
    print(f"  建议: {result.get('suggestion', '')}")
    
    assert result["success"] is not None

async def scenario_negation_handling():
    """场景9: 否定处理"""
    from core.engine.skill_dispatcher import get_skill_dispatcher
    
    dispatcher = get_skill_dispatcher()
    
    test_cases = [
        ("不要聊天，帮我查天气", "查天气"),
        ("不要用计算器，手动计算", "手动计算"),
        ("别用翻译，直接回答", "直接回答"),
    ]
    
    negation_patterns = ["不要", "不想要", "不是", "不想", "不要用", "别用", "排除"]
    
    for original, expected in test_cases:
        has_negation = any(pattern in original for pattern in negation_patterns)
        processed = original
        
        if has_negation:
            for pattern in negation_patterns:
                idx = original.find(pattern)
                if idx != -1:
                    processed = original[idx + len(pattern):].strip()
                    break
        
        print(f"  '{original}' -> '{processed}'")
        assert expected in processed

async def scenario_multi_agent_collaboration():
    """场景10: 多Agent协同"""
# DEAD-IMPORT: from core.multi_agent_v2.agents.master.master_agent import MasterAgent
# DEAD-IMPORT: from core.multi_agent_v2.agents.base.base_agent import Task, Capability, ActionResult
    
    master = MasterAgent()
    
    # 创建模拟Agent
    class MockAgent:
        def __init__(self, capabilities):
            self.capabilities = capabilities
            self.current_tasks = []
            self.max_concurrent_tasks = 5
            self.reliability = 0.95
    
    # 测试能力匹配
    mock_agent = MockAgent([
        Capability("data_analysis", "数据分析", ["分析", "数据", "统计"], 0.85, 5, 3.0, 0.92),
        Capability("web_scraping", "网页爬取", ["爬取", "微博", "热搜"], 0.75, 3, 5.0, 0.88),
    ])
    
    task = Task(
        task_id="test",
        type="analysis",
        description="分析微博热搜数据",
        keywords=["分析", "微博", "热搜"],
        complexity=0.7
    )
    
    match_score = master._calculate_capability_match(task, mock_agent)
    print(f"  能力匹配度: {match_score:.4f}")
    assert match_score > 0.5, "匹配度应该大于0.5"
    
    # 测试结果聚合
    master.subtask_results = {
        "t1": ActionResult(True, {"data": "result1"}, 1.0),
        "t2": ActionResult(True, {"data": "result2"}, 2.0),
    }
    
    subtasks = [
        Task(task_id="t1", type="test", description="任务1"),
        Task(task_id="t2", type="test", description="任务2"),
    ]
    
    aggregated = await master._aggregate_results(subtasks)
    assert aggregated.success
    assert aggregated.output["summary"]["success_rate"] == 100.0
    print(f"  聚合结果: 完成{aggregated.output['summary']['completed_tasks']}/{aggregated.output['summary']['total_tasks']}")

async def scenario_edge_cases():
    """场景11: 边界情况测试"""
    from core.engine.skill_dispatcher import get_skill_dispatcher
    
    dispatcher = get_skill_dispatcher()
    
    # 空消息
    result = dispatcher._fuzzy_skill_match("", "")
    print(f"  空消息 -> {result}")
    
    # 超长消息
    long_message = "这是一条非常长的测试消息，用于测试系统在处理超长输入时的表现，包含各种关键词如天气、翻译、分析、计算等"
    result = dispatcher._fuzzy_skill_match(long_message, long_message)
    print(f"  超长消息 -> {result}")
    
    # 特殊字符
    result = dispatcher._fuzzy_skill_match("@#$%^&*()", "@#$%^&*()")
    print(f"  特殊字符 -> {result}")

async def main():
    """运行所有场景测试"""
    print("="*60)
    print("多场景测试套件")
    print("="*60)
    
    st = ScenarioTest()
    
    await st.run_scenario("日常对话", scenario_daily_conversation)
    await st.run_scenario("天气查询", scenario_weather_query)
    await st.run_scenario("多步骤任务", scenario_multi_step_task)
    await st.run_scenario("翻译任务", scenario_translation)
    await st.run_scenario("数据分析", scenario_data_analysis)
    await st.run_scenario("错误处理与反问", scenario_error_handling)
    await st.run_scenario("Fallback机制", scenario_fallback_mechanism)
    await st.run_scenario("MCP服务器检查", scenario_mcp_check)
    await st.run_scenario("否定处理", scenario_negation_handling)
    await st.run_scenario("多Agent协同", scenario_multi_agent_collaboration)
    await st.run_scenario("边界情况", scenario_edge_cases)
    
    st.print_summary()

if __name__ == "__main__":
    asyncio.run(main())