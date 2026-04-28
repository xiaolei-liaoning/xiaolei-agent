#!/usr/bin/env python3
"""
PlanningAgent单元测试

测试内容：
1. PlanningAgent初始化
2. 创建任务计划
3. 优化现有计划
4. 验证计划可行性
5. 多Agent协作中的PlanningAgent
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path("/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent")
sys.path.insert(0, str(project_root))

from core.multi_agent_system import (
    PlanningAgent,
    AgentScheduler,
    AgentType,
    AgentTask
)


class TestPlanningAgent:
    """PlanningAgent测试类"""
    
    def __init__(self):
        self.results = []
    
    def add_result(self, test_name: str, passed: bool, details: str = ""):
        """添加测试结果"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        print(f"{status} - {test_name}")
        if details:
            print(f"   📝 {details}")
    
    async def test_planning_agent_initialization(self):
        """测试1: PlanningAgent初始化"""
        print("\n" + "="*80)
        print("🧪 测试1: PlanningAgent初始化")
        print("="*80)
        
        try:
            agent = PlanningAgent(max_workers=5)
            
            # 验证Agent类型
            if agent.agent_type == AgentType.PLANNING:
                self.add_result("测试1.1: Agent类型正确", True)
            else:
                self.add_result("测试1.1: Agent类型正确", False, f"实际类型: {agent.agent_type}")
            
            # 验证最大工作线程数
            if agent.max_workers == 5:
                self.add_result("测试1.2: max_workers设置正确", True)
            else:
                self.add_result("测试1.2: max_workers设置正确", False, f"实际值: {agent.max_workers}")
            
            # 验证Agent可以启动
            await agent.start()
            if agent._running:
                self.add_result("测试1.3: Agent启动成功", True)
            else:
                self.add_result("测试1.3: Agent启动成功", False)
            
            # 停止Agent
            await agent.stop()
            self.add_result("测试1.4: Agent停止成功", True)
            
        except Exception as e:
            self.add_result("测试1: PlanningAgent初始化", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_create_plan(self):
        """测试2: 创建任务计划"""
        print("\n" + "="*80)
        print("🧪 测试2: 创建任务计划")
        print("="*80)
        
        try:
            agent = PlanningAgent(max_workers=5)
            await agent.start()
            
            # 测试爬虫任务计划
            task = AgentTask(
                id="test_plan_001",
                type="create_plan",
                params={
                    "goal": "爬取微博热搜并分析趋势",
                    "constraints": ["时间限制: 30秒", "数据量: 最多100条"]
                }
            )
            
            result = await agent._run_task(task)
            
            if result["status"] == "success":
                self.add_result("测试2.1: 爬虫任务计划创建成功", True)
                
                # 验证计划步骤
                steps = result.get("steps", [])
                if len(steps) > 0:
                    self.add_result("测试2.2: 计划包含步骤", True, f"共{len(steps)}步")
                    
                    # 打印计划步骤
                    print("\n   📋 计划步骤:")
                    for step in steps:
                        print(f"      {step['step_id']}. {step['action']}: {step['description']}")
                else:
                    self.add_result("测试2.2: 计划包含步骤", False, "步骤为空")
                
                # 验证预估时间
                estimated_time = result.get("estimated_time", 0)
                if estimated_time > 0:
                    self.add_result("测试2.3: 预估时间合理", True, f"{estimated_time}秒")
                else:
                    self.add_result("测试2.3: 预估时间合理", False)
            else:
                self.add_result("测试2.1: 爬虫任务计划创建成功", False, f"状态: {result['status']}")
            
            await agent.stop()
            
        except Exception as e:
            self.add_result("测试2: 创建任务计划", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_optimize_plan(self):
        """测试3: 优化现有计划"""
        print("\n" + "="*80)
        print("🧪 测试3: 优化现有计划")
        print("="*80)
        
        try:
            agent = PlanningAgent(max_workers=5)
            await agent.start()
            
            # 创建一个包含重复步骤的计划
            current_plan = [
                {"step_id": 1, "action": "fetch_data", "description": "获取数据"},
                {"step_id": 2, "action": "process_data", "description": "处理数据"},
                {"step_id": 3, "action": "fetch_data", "description": "再次获取数据（重复）"},
                {"step_id": 4, "action": "analyze", "description": "分析数据"}
            ]
            
            task = AgentTask(
                id="test_optimize_001",
                type="optimize_plan",
                params={
                    "plan": current_plan,
                    "feedback": "发现重复步骤，需要优化"
                }
            )
            
            result = await agent._run_task(task)
            
            if result["status"] == "success":
                self.add_result("测试3.1: 计划优化成功", True)
                
                original_steps = result.get("original_steps", 0)
                optimized_steps = result.get("optimized_steps", 0)
                
                if optimized_steps < original_steps:
                    self.add_result("测试3.2: 步骤数量减少", True, 
                                  f"从{original_steps}步优化到{optimized_steps}步")
                else:
                    self.add_result("测试3.2: 步骤数量减少", False, 
                                  f"原始:{original_steps}, 优化后:{optimized_steps}")
                
                # 验证改进项
                improvements = result.get("improvements", [])
                if len(improvements) > 0:
                    self.add_result("测试3.3: 生成改进建议", True, f"共{len(improvements)}条")
                    print("\n   📋 改进建议:")
                    for imp in improvements:
                        print(f"      - {imp}")
                else:
                    self.add_result("测试3.3: 生成改进建议", False)
            else:
                self.add_result("测试3.1: 计划优化成功", False, f"状态: {result['status']}")
            
            await agent.stop()
            
        except Exception as e:
            self.add_result("测试3: 优化现有计划", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_validate_plan(self):
        """测试4: 验证计划可行性"""
        print("\n" + "="*80)
        print("🧪 测试4: 验证计划可行性")
        print("="*80)
        
        try:
            agent = PlanningAgent(max_workers=5)
            await agent.start()
            
            # 测试可行计划
            feasible_plan = [
                {"step_id": 1, "action": "query_api", "estimated_time": 2},
                {"step_id": 2, "action": "process_data", "estimated_time": 3}
            ]
            
            task = AgentTask(
                id="test_validate_001",
                type="validate_plan",
                params={
                    "plan": feasible_plan,
                    "resources": {"cpu": 4, "memory": "8GB"}
                }
            )
            
            result = await agent._run_task(task)
            
            if result["status"] == "success":
                self.add_result("测试4.1: 计划验证成功", True)
                
                is_feasible = result.get("is_feasible", False)
                if is_feasible:
                    self.add_result("测试4.2: 简单计划被识别为可行", True)
                else:
                    self.add_result("测试4.2: 简单计划被识别为可行", False)
                
                issues = result.get("issues", [])
                suggestions = result.get("suggestions", [])
                
                print(f"\n   📋 验证结果:")
                print(f"      可行性: {'✅ 可行' if is_feasible else '❌ 不可行'}")
                print(f"      问题数: {len(issues)}")
                print(f"      建议数: {len(suggestions)}")
            else:
                self.add_result("测试4.1: 计划验证成功", False, f"状态: {result['status']}")
            
            await agent.stop()
            
        except Exception as e:
            self.add_result("测试4: 验证计划可行性", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_planning_in_scheduler(self):
        """测试5: PlanningAgent在调度器中的集成"""
        print("\n" + "="*80)
        print("🧪 测试5: PlanningAgent在调度器中的集成")
        print("="*80)
        
        try:
            scheduler = AgentScheduler()
            await scheduler.start()
            
            # 检查PlanningAgent是否注册
            agent_info = scheduler.get_agent_info()
            
            if "planning" in agent_info:
                self.add_result("测试5.1: PlanningAgent已注册", True)
                
                planning_info = agent_info["planning"]
                if planning_info.get("running"):
                    self.add_result("测试5.2: PlanningAgent正在运行", True)
                else:
                    self.add_result("测试5.2: PlanningAgent正在运行", False)
            else:
                self.add_result("测试5.1: PlanningAgent已注册", False, "未在agent_info中找到")
            
            # 测试任务映射
            if "create_plan" in scheduler.task_mapping:
                mapped_type = scheduler.task_mapping["create_plan"]
                if mapped_type == AgentType.PLANNING:
                    self.add_result("测试5.3: 任务映射正确", True)
                else:
                    self.add_result("测试5.3: 任务映射正确", False, f"映射到: {mapped_type}")
            else:
                self.add_result("测试5.3: 任务映射正确", False, "未找到create_plan映射")
            
            await scheduler.stop()
            
        except Exception as e:
            self.add_result("测试5: PlanningAgent在调度器中的集成", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "🎯"*40)
        print("PlanningAgent单元测试")
        print("🎯"*40)
        
        await self.test_planning_agent_initialization()
        await self.test_create_plan()
        await self.test_optimize_plan()
        await self.test_validate_plan()
        await self.test_planning_in_scheduler()
        
        # 打印总结
        print("\n" + "="*80)
        print("📊 测试结果总结")
        print("="*80)
        
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        
        for result in self.results:
            status = "✅" if result["passed"] else "❌"
            print(f"{status} {result['test']}")
            if result["details"]:
                print(f"   └─ {result['details']}")
        
        print(f"\n总计: {passed}/{total} 测试通过")
        
        if passed == total:
            print("\n🎉 所有测试通过！PlanningAgent实现完整！")
        elif passed >= total * 0.8:
            print(f"\n⚠️  大部分测试通过（{passed}/{total}），建议修复失败项")
        else:
            print(f"\n❌ 多项测试失败（{passed}/{total}），需要立即修复")
        
        return passed == total


async def main():
    """主函数"""
    tester = TestPlanningAgent()
    success = await tester.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
