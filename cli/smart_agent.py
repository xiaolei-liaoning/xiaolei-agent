"""CLI智能多Agent交互模块 - 真正的自主协作系统"""

import asyncio
from cli.colors import CliColors, print_color, print_success, print_error, print_warning, print_info


class SmartAgentCLI:
    """智能多Agent CLI交互模块"""
    
    def __init__(self):
        self.coordinator = None
        self._init_multi_agent_system()
    
    def _init_multi_agent_system(self):
        """初始化智能多Agent系统"""
        try:
            from core.smart_multi_agent import get_smart_multi_agent_system, CoordinatorAgent
            from core.agent_communication import communication_center
            
            self.coordinator = get_smart_multi_agent_system()
            self.coordinator.set_communication_center(communication_center)
            
            print_color("✅ 智能多Agent系统初始化完成", CliColors.GREEN)
        except Exception as e:
            print_error(f"❌ 智能多Agent系统初始化失败: {e}")
            self.coordinator = None
    
    async def handle_smart_task(self, user_query: str):
        """处理智能任务请求"""
        if not self.coordinator:
            print_error("智能多Agent系统未初始化")
            return
        
        print_color(f"\n🚀 智能任务处理: {user_query}", CliColors.CYAN)
        print_color("──────────────────────────────────────────────", CliColors.GRAY)
        
        try:
            # 提交任务给协调器
            plan = await self.coordinator.submit_task(user_query)
            
            # 显示结果摘要
            await self._display_plan_result(plan)
            
        except Exception as e:
            print_error(f"任务执行失败: {e}")
    
    async def _display_plan_result(self, plan):
        """显示执行计划结果"""
        print_color("\n📊 任务执行结果", CliColors.BOLD)
        print_color("────────────────", CliColors.GRAY)
        
        # 统计
        completed = 0
        failed = 0
        
        for node in plan.nodes.values():
            if node.status.value == "completed":
                completed += 1
            elif node.status.value == "failed":
                failed += 1
        
        print_color(f"任务总数: {len(plan.nodes)}", CliColors.WHITE)
        print_color(f"✅ 完成: {completed}", CliColors.GREEN)
        print_color(f"❌ 失败: {failed}", CliColors.RED)
        
        # 显示每个任务的结果
        print_color("\n📋 任务详情:", CliColors.CYAN)
        for node in plan.nodes.values():
            status_icon = "✅" if node.status.value == "completed" else "❌"
            print_color(f"  {status_icon} [{node.task_id}] {node.description}", 
                       CliColors.GREEN if node.status.value == "completed" else CliColors.RED)
            
            if node.result and node.result.get("success"):
                if "summary" in node.result:
                    print_color(f"     摘要: {node.result['summary'][:50]}...", CliColors.WHITE)
                elif "result" in node.result:
                    print_color(f"     结果: {node.result['result'][:50]}...", CliColors.WHITE)
        
        if failed == 0:
            print_color("\n🎉 任务全部执行成功!", CliColors.GREEN)
        else:
            print_color(f"\n⚠️ 有 {failed} 个任务失败，请检查日志", CliColors.YELLOW)
    
    async def handle_agent_collaboration_demo(self):
        """演示多Agent协作"""
        print_color("\n🎬 多Agent协作演示", CliColors.BOLD)
        print_color("──────────────────────────────────────────────", CliColors.GRAY)
        
        demo_queries = [
            "帮我爬取微博热搜并分析",
            "写一篇关于人工智能的短文",
            "搜索Python最新趋势"
        ]
        
        for i, query in enumerate(demo_queries, 1):
            print_color(f"\n[{i}/{len(demo_queries)}] 测试任务: {query}", CliColors.CYAN)
            await self.handle_smart_task(query)
            await asyncio.sleep(1)
    
    async def handle_agent_status(self):
        """显示Agent状态"""
        print_color("\n🦾 Agent状态监控", CliColors.BOLD)
        print_color("────────────────", CliColors.GRAY)
        
        agents = [
            {"name": "Planner", "type": "规划Agent", "status": "online", "role": "任务拆解与规划"},
            {"name": "Worker-Scraper", "type": "Worker", "status": "online", "role": "网页爬取"},
            {"name": "Worker-Analyzer", "type": "Worker", "status": "online", "role": "数据分析"},
            {"name": "Worker-Writer", "type": "Worker", "status": "online", "role": "内容创作"},
            {"name": "Reviewer", "type": "审查Agent", "status": "online", "role": "结果审查"},
            {"name": "Coordinator", "type": "协调Agent", "status": "online", "role": "任务协调"}
        ]
        
        print_color(f"{'Agent名称':<20} {'类型':<12} {'状态':<10} {'职责':<20}", CliColors.CYAN)
        print_color("─" * 62, CliColors.GRAY)
        
        for agent in agents:
            status_color = CliColors.GREEN if agent["status"] == "online" else CliColors.RED
            print_color(f"{agent['name']:<20} {agent['type']:<12} {agent['status']:<10} {agent['role']:<20}", 
                       status_color if agent["status"] == "online" else CliColors.WHITE)


# 全局实例
_smart_agent_cli = None

def get_smart_agent_cli():
    """获取智能Agent CLI实例"""
    global _smart_agent_cli
    if _smart_agent_cli is None:
        _smart_agent_cli = SmartAgentCLI()
    return _smart_agent_cli