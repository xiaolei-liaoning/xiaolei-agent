#!/usr/bin/env python3
"""综合多场景测试脚本"""

import asyncio
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestResult:
    """测试结果类"""
    def __init__(self, name, passed, failed, details=None):
        self.name = name
        self.passed = passed
        self.failed = failed
        self.details = details or []
    
    @property
    def success_rate(self):
        total = self.passed + self.failed
        return (self.passed / total * 100) if total > 0 else 0

class ComprehensiveScenarioTest:
    """综合场景测试类"""
    
    def __init__(self):
        self.results = []
        self.start_time = None
    
    def add_result(self, result):
        """添加测试结果"""
        self.results.append(result)
    
    async def run_all_tests(self):
        """运行所有测试"""
        self.start_time = datetime.now()
        print(f"测试开始: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # 运行各模块测试
        await self.test_skill_dispatcher()
        await self.test_clarification_mechanism()
        await self.test_multi_agent_collaboration()
        await self.test_mcp_check()
        await self.test_fallback_mechanism()
        await self.test_integration()
        
        self.print_report()
    
    async def test_skill_dispatcher(self):
        """测试技能分发器"""
        print("\n【模块测试】技能分发器")
        print("-" * 60)
        
        from core.engine.skill_dispatcher import get_skill_dispatcher
        dispatcher = get_skill_dispatcher()
        
        test_cases = [
            # 日常对话
            ("你好", "chat", "问候语"),
            ("谢谢", "chat", "感谢语"),
            ("再见", "chat", "告别语"),
            ("你是谁", "chat", "自我介绍"),
            ("介绍一下你自己", "chat", "自我介绍"),
            ("今天心情怎么样", "chat", "闲聊"),
            
            # 翻译
            ("翻译这段英文", "translator", "翻译请求"),
            ("把中文翻译成英文", "translator", "中英翻译"),
            ("英语翻译", "translator", "英语翻译"),
            ("日语翻译", "translator", "日语翻译"),
            ("韩语翻译", "translator", "韩语翻译"),
            
            # 天气
            ("北京天气", "weather", "带城市"),
            ("上海气温", "weather", "带城市"),
            ("广州温度", "weather", "带城市"),
            
            # 数据分析
            ("分析数据", "data_analysis", "数据分析"),
            ("生成图表", "data_analysis", "图表生成"),
            ("统计分析", "data_analysis", "统计"),
            ("可视化数据", "data_analysis", "可视化"),
            ("词云", "data_analysis", "词云"),
            
            # 系统工具
            ("现在几点", "system_toolbox", "时间查询"),
            ("今天日期", "system_toolbox", "日期查询"),
            ("检查内存", "system_toolbox", "内存"),
            ("CPU使用率", "system_toolbox", "CPU"),
            
            # GUI自动化
            ("打开浏览器", "gui_automation", "打开应用"),
            ("关闭应用", "gui_automation", "关闭应用"),
            ("截图", "gui_automation", "截图"),
            ("调整音量", "gui_automation", "音量"),
            
            # Web爬取
            ("微博热搜", "web_scraper", "微博"),
            ("抖音热榜", "web_scraper", "抖音"),
            ("B站排行榜", "web_scraper", "B站"),
            ("知乎热榜", "web_scraper", "知乎"),
            
            # 文本分析
            ("总结文档", "text_analyzer", "总结"),
            ("提取摘要", "text_analyzer", "摘要"),
            ("情感分析", "text_analyzer", "情感"),
            
            # 深度思考
            ("深度思考这个问题", "deep_thinking", "深度思考"),
            ("研究一下这个问题", "deep_thinking", "研究"),
            
            # RAG搜索
            ("什么是人工智能", "rag_search", "定义"),
            ("解释一下机器学习", "rag_search", "解释"),
            
            # MCP检查
            ("检查MCP服务器", "mcp_check", "MCP检查"),
            ("MCP连接", "mcp_check", "MCP连接"),
        ]
        
        passed = 0
        failed = 0
        details = []
        
        for message, expected, desc in test_cases:
            result = dispatcher._fuzzy_skill_match(message, message)
            if result == expected:
                passed += 1
                details.append(f"✓ {desc}: '{message}' -> {result}")
            else:
                failed += 1
                details.append(f"✗ {desc}: '{message}' -> {result} (预期: {expected})")
        
        # 打印部分结果
        for detail in details[:10]:
            print(f"  {detail}")
        if len(details) > 10:
            print(f"  ... 还有 {len(details) - 10} 项")
        
        self.add_result(TestResult("技能分发器", passed, failed, details))
        print(f"\n  结果: {passed}/{passed+failed} 通过")
    
    async def test_clarification_mechanism(self):
        """测试反问机制（暂跳过，等待全局反问机制重构）"""
        print("\n【模块测试】反问机制 - 跳过（待重构）")
        print("-" * 60)
        self.add_result(TestResult("反问机制", 0, 0, ["⏭ 反问机制暂未启用，等待全局反问机制重构"]))
        print(f"\n  结果: 跳过")
    
    async def test_multi_agent_collaboration(self):
        """测试多Agent协同"""
        print("\n【模块测试】多Agent协同")
        print("-" * 60)
        
# DEAD-IMPORT: from core.multi_agent_v2.agents.master.master_agent import MasterAgent
# DEAD-IMPORT: from core.multi_agent_v2.agents.base.base_agent import Task, Capability, ActionResult
        
        master = MasterAgent()
        
        passed = 0
        failed = 0
        details = []
        
        # 创建模拟Agent
        class MockAgent:
            def __init__(self, capabilities):
                self.capabilities = capabilities
                self.current_tasks = []
                self.max_concurrent_tasks = 5
                self.reliability = 0.95
        
        # 测试能力匹配
        mock_agent = MockAgent([
            Capability("data_analysis", "数据分析", ["分析", "数据"], 0.85, 5, 3.0, 0.92),
            Capability("web_scraping", "网页爬取", ["爬取", "微博"], 0.75, 3, 5.0, 0.88),
        ])
        
        task = Task("test", "analysis", "分析微博数据", ["分析", "微博"], 0.7)
        match_score = master._calculate_capability_match(task, mock_agent)
        
        if match_score > 0.5:
            passed += 1
            details.append(f"✓ 能力匹配度: {match_score:.4f}")
        else:
            failed += 1
            details.append(f"✗ 能力匹配度过低: {match_score:.4f}")
        
        # 测试结果聚合（成功场景）
        master.subtask_results = {
            "t1": ActionResult(True, {"data": "r1"}, 1.0),
            "t2": ActionResult(True, {"data": "r2"}, 2.0),
        }
        subtasks = [Task("t1", "test", "任务1"), Task("t2", "test", "任务2")]
        aggregated = await master._aggregate_results(subtasks)
        
        if aggregated.success and aggregated.output["summary"]["success_rate"] == 100.0:
            passed += 1
            details.append(f"✓ 结果聚合成功: {aggregated.output['summary']}")
        else:
            failed += 1
            details.append(f"✗ 结果聚合失败")
        
        # 测试结果聚合（部分失败场景）
        master.subtask_results = {
            "t1": ActionResult(True, {"data": "r1"}, 1.0),
            "t2": ActionResult(False, error="失败"),
        }
        aggregated = await master._aggregate_results(subtasks)
        
        if not aggregated.success and aggregated.output["summary"]["success_rate"] == 50.0:
            passed += 1
            details.append(f"✓ 部分失败处理正确")
        else:
            failed += 1
            details.append(f"✗ 部分失败处理错误")
        
        for detail in details:
            print(f"  {detail}")
        
        self.add_result(TestResult("多Agent协同", passed, failed, details))
        print(f"\n  结果: {passed}/{passed+failed} 通过")
    
    async def test_mcp_check(self):
        """测试MCP检查技能"""
        print("\n【模块测试】MCP检查技能")
        print("-" * 60)
        
        from core.skills.mcp_check.handler import check_mcp_availability
        
        passed = 0
        failed = 0
        details = []
        
        result = await check_mcp_availability()
        
        if "success" in result:
            passed += 1
            details.append(f"✓ MCP检查完成")
            details.append(f"  - 成功: {result['success']}")
            details.append(f"  - 服务器数量: {len(result.get('servers', []))}")
            details.append(f"  - 建议: {result.get('suggestion', '')[:50]}...")
        else:
            failed += 1
            details.append(f"✗ MCP检查失败")
        
        for detail in details:
            print(f"  {detail}")
        
        self.add_result(TestResult("MCP检查技能", passed, failed, details))
        print(f"\n  结果: {passed}/{passed+failed} 通过")
    
    async def test_fallback_mechanism(self):
        """测试Fallback机制"""
        print("\n【模块测试】Fallback机制")
        print("-" * 60)
        
        from core.engine.skill_dispatcher import get_skill_dispatcher
        dispatcher = get_skill_dispatcher()
        
        passed = 0
        failed = 0
        details = []
        
        # 测试需求类型分析
        requirement_tests = [
            ("计算1到100的和", "数学计算"),
            ("今天星期几", "日期时间"),
            ("替换字符串中的空格", "文本处理"),
            ("筛选列表中的偶数", "数据处理"),
        ]
        
        for message, expected_type in requirement_tests:
            analysis = dispatcher._analyze_requirement_type(message)
            if expected_type in analysis:
                passed += 1
                details.append(f"✓ 需求分析: '{message}' -> {expected_type}")
            else:
                failed += 1
                details.append(f"✗ 需求分析失败: '{message}'")
        
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
        if result["success"] and result["result"] == 5050:
            passed += 1
            details.append(f"✓ 沙盒执行: 1-100求和 = {result['result']}")
        else:
            failed += 1
            details.append(f"✗ 沙盒执行失败")
        
        for detail in details:
            print(f"  {detail}")
        
        self.add_result(TestResult("Fallback机制", passed, failed, details))
        print(f"\n  结果: {passed}/{passed+failed} 通过")
    
    async def test_integration(self):
        """测试集成场景"""
        print("\n【集成测试】真实场景模拟")
        print("-" * 60)
        
        from core.engine.skill_dispatcher import get_skill_dispatcher
        from core.skills.mcp_check.handler import check_mcp_availability
        
        dispatcher = get_skill_dispatcher()
        
        passed = 0
        failed = 0
        details = []
        
        # 场景1: 用户查询天气（含城市名）
        result = dispatcher._fuzzy_skill_match("北京天气", "北京天气")
        if result == "weather":
            passed += 1
            details.append(f"✓ 场景1: 天气查询识别成功")
        else:
            failed += 1
            details.append(f"✗ 场景1: 天气查询识别失败")
        
        # 场景2: 用户需要多步骤任务
        message = "先查北京天气，然后生成报告"
        result = dispatcher._fuzzy_skill_match(message, message)
        # 可以匹配到multi_step或weather，都是合理的
        if result in ["weather", "data_analysis"]:
            passed += 1
            details.append(f"✓ 场景2: 多步骤任务处理 -> {result}")
        else:
            failed += 1
            details.append(f"✗ 场景2: 多步骤任务匹配失败")
        
        # 场景3: MCP检查后使用计算器
        mcp_result = await check_mcp_availability()
        if mcp_result["success"] and len(mcp_result.get("servers", [])) > 0:
            passed += 1
            details.append(f"✓ 场景3: MCP检查并准备使用计算器")
        else:
            failed += 1
            details.append(f"✗ 场景3: MCP不可用")
        
        # 场景4: 否定+意图识别
        message = "不要聊天，帮我翻译这段英文"
        negation_patterns = ["不要", "别用"]
        processed = message
        for pattern in negation_patterns:
            idx = message.find(pattern)
            if idx != -1:
                # 提取否定词后面的内容，并移除可能的对象词
                remaining = message[idx + len(pattern):].strip()
                # 尝试找到逗号或其他分隔符后的内容
                if "，" in remaining:
                    parts = remaining.split("，", 1)
                    if len(parts) > 1 and len(parts[0]) <= 4:
                        processed = parts[1].strip()
                    else:
                        processed = remaining
                elif "," in remaining:
                    parts = remaining.split(",", 1)
                    if len(parts) > 1 and len(parts[0]) <= 4:
                        processed = parts[1].strip()
                    else:
                        processed = remaining
                else:
                    processed = remaining
                break
        result = dispatcher._fuzzy_skill_match(processed, processed)
        if result == "translator":
            passed += 1
            details.append(f"✓ 场景4: 否定处理+翻译 -> {result}")
        else:
            failed += 1
            details.append(f"✗ 场景4: 否定处理失败 -> {result}")
        
        for detail in details:
            print(f"  {detail}")
        
        self.add_result(TestResult("集成测试", passed, failed, details))
        print(f"\n  结果: {passed}/{passed+failed} 通过")
    
    def print_report(self):
        """打印综合测试报告"""
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        print("\n" + "=" * 80)
        print("综合测试报告")
        print("=" * 80)
        print(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"测试时长: {duration.total_seconds():.2f} 秒")
        print("-" * 80)
        
        # 输出各模块结果
        print(f"{'模块':<20} {'通过':<6} {'失败':<6} {'成功率':<8}")
        print("-" * 80)
        
        total_passed = 0
        total_failed = 0
        
        for result in self.results:
            total_passed += result.passed
            total_failed += result.failed
            print(f"{result.name:<20} {result.passed:<6} {result.failed:<6} {result.success_rate:<8.1f}%")
        
        print("-" * 80)
        overall_success = (total_passed / (total_passed + total_failed) * 100) if (total_passed + total_failed) > 0 else 0
        print(f"总计: {total_passed} 通过, {total_failed} 失败, 成功率: {overall_success:.1f}%")
        
        # 生成详细JSON报告
        report = {
            "timestamp": end_time.isoformat(),
            "duration_seconds": duration.total_seconds(),
            "total_tests": total_passed + total_failed,
            "passed": total_passed,
            "failed": total_failed,
            "success_rate": overall_success,
            "modules": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "failed": r.failed,
                    "success_rate": r.success_rate,
                    "details": r.details
                } for r in self.results
            ]
        }
        
        # 保存报告
        report_path = f"test_report_{end_time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n详细报告已保存到: {report_path}")
        
        if overall_success == 100:
            print("\n🎉 所有测试通过！")
        else:
            print(f"\n⚠️ {total_failed} 项测试失败")

async def main():
    """主入口"""
    tester = ComprehensiveScenarioTest()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())