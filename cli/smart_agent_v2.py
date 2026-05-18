"""CLI智能多Agent交互模块 - 支持所有协作模式"""

import asyncio
from cli.colors import CliColors, print_color, print_success, print_error, print_warning, print_info

class SmartAgentCLIv2:
    """智能多Agent CLI交互模块 - 支持所有5种协作模式"""
    
    def __init__(self):
        self.scheduler = None
        self.context_center = None
        self._init_scheduler()
    
    def _init_scheduler(self):
        """初始化智能调度器（支持所有协作模式）"""
        try:
            pass
            IntelligentScheduler = None
            GlobalContextCenter = None
            
            self.context_center = GlobalContextCenter()
            self.scheduler = IntelligentScheduler(self.context_center)
            print_color("✅ 智能调度器初始化完成 (v2)", CliColors.GREEN)
            print_color("   支持协作模式: PIPELINE, MASTER_SLAVE, REVIEW, AUCTION, HYBRID", CliColors.GRAY)
        except Exception as e:
            import traceback
            error_msg = f"❌ 智能调度器初始化失败: {e}"
            print_error(error_msg)
            print_error(f"详细错误: {traceback.format_exc()}")
            self.scheduler = None
    
    async def handle_smart_task_with_mode(self, user_query: str, collaboration_mode=None):
        """使用指定协作模式处理智能任务"""
        if not self.scheduler:
            print_error("智能调度器未初始化")
            return
        
        print_color(f"\n🚀 智能任务处理: {user_query}", CliColors.CYAN)
        print_color("──────────────────────────────────────────────", CliColors.GRAY)
        
        try:
            Task = None
            
            # 创建任务
            task = Task(
                task_id=f"cli_task_{int(asyncio.get_event_loop().time())}",
                type="user_task",
                description=user_query,
                keywords=user_query.split(),
                complexity=self._estimate_complexity(user_query),
                estimated_steps=self._estimate_steps(user_query)
            )
            
            # 设置协作模式（可选）
            if collaboration_mode:
                from core.shared.enums import CollaborationMode
                task.metadata = {"preferred_mode": collaboration_mode}
            
            # 使用智能调度器调度任务
            result = await self.scheduler.schedule(task)
            
            if result.success:
                print_color(f"\n✅ 任务调度成功!", CliColors.GREEN)
                print_color(f"   协作模式: {result.collaboration_mode.value}", CliColors.CYAN)
                print_color(f"   分配Agent数: {len(result.assigned_agents)}", CliColors.CYAN)
                
                # 执行任务 - 使用 TaskExecutor
                from core.multi_agent_v2.infrastructure.task_executor import TaskExecutor
                executor = TaskExecutor(agent_pool=self.scheduler.agent_pool)
                exec_result = await executor.execute(
                    schedule_result=result,
                    original_task=task,
                    timeout=300.0  # 5分钟超时
                )
                
                if exec_result["success"]:
                    print_color(f"\n🎉 任务执行完成! 耗时: {exec_result['execution_time']:.2f}s", CliColors.GREEN)
                else:
                    print_error(f"任务执行失败: {exec_result.get('error', '未知错误')}")
            else:
                print_error(f"任务调度失败: {result.error}")

        except Exception as e:
            print_error(f"任务执行失败: {e}")
    
    def _estimate_complexity(self, query: str) -> float:
        """估算任务复杂度"""
        complexity = 0.3
        
        # 根据关键词判断复杂度
        complex_keywords = ["分析", "报告", "复杂", "深入", "全面", "详细"]
        simple_keywords = ["简单", "快速", "简短", "一句话"]
        
        for kw in complex_keywords:
            if kw in query:
                complexity += 0.2
        
        for kw in simple_keywords:
            if kw in query:
                complexity -= 0.1
        
        # 根据长度判断
        if len(query) > 50:
            complexity += 0.1
        if len(query) > 100:
            complexity += 0.1
        
        return min(0.95, max(0.1, complexity))
    
    def _estimate_steps(self, query: str) -> int:
        """估算任务步骤数"""
        if "并且" in query or "同时" in query or "然后" in query:
            return 3
        if "先" in query or "再" in query or "最后" in query:
            return 2
        return 1
    
    async def _execute_scheduled_task(self, task, schedule_result):
        """执行已调度的任务"""
        print_color("\n📋 开始执行任务...", CliColors.BOLD)
        
        TaskState = None
        
        # 更新任务状态
        await self.context_center.update_task_state(
            task.task_id, 
            TaskState.RUNNING,
            {"collaboration_mode": schedule_result.collaboration_mode.value}
        )
        
        # 模拟执行（实际应调用Agent执行）
        for step, agent_id in schedule_result.assigned_agents.items():
            print_color(f"\n  🔄 [{step}] 执行中 (Agent: {agent_id})...", CliColors.WHITE)
            await asyncio.sleep(0.5)  # 模拟执行时间
            print_color(f"     ✅ 完成", CliColors.GREEN)
        
        # 更新任务状态为完成
        await self.context_center.update_task_state(
            task.task_id, 
            TaskState.COMPLETED,
            {"result": "任务执行成功"}
        )
        
        print_color("\n🎉 任务执行完成!", CliColors.GREEN)
    
    async def handle_collaboration_mode_demo(self):
        """演示所有协作模式"""
        print_color("\n🎬 多Agent协作模式演示", CliColors.BOLD)
        print_color("──────────────────────────────────────────────", CliColors.GRAY)
        
        from core.shared.enums import CollaborationMode
        
        demo_tasks = [
            (CollaborationMode.PIPELINE, "帮我爬取微博热搜并分析数据生成报告"),
            (CollaborationMode.MASTER_SLAVE, "处理一个复杂的计算任务"),
            (CollaborationMode.REVIEW, "审核并优化这个关键系统设计方案"),
            (CollaborationMode.AUCTION, "搜索多个数据源并找到最佳答案"),
            (CollaborationMode.HYBRID, "简单查询今天的天气"),
        ]
        
        for mode, query in demo_tasks:
            print_color(f"\n[{mode.value}] 测试任务: {query}", CliColors.CYAN)
            await self.handle_smart_task_with_mode(query, mode)
            await asyncio.sleep(1)
    
    async def handle_agent_status(self):
        """显示Agent状态和可用协作模式"""
        print_color("\n🦾 Agent状态监控", CliColors.BOLD)
        print_color("────────────────", CliColors.GRAY)
        
        # 显示支持的协作模式
        print_color("\n支持的协作模式:", CliColors.CYAN)
        from core.shared.enums import CollaborationMode
        modes = [
            ("PIPELINE", "流水线模式 - 多步骤顺序执行"),
            ("MASTER_SLAVE", "主从模式 - Master协调，Slave执行"),
            ("REVIEW", "评审模式 - 执行后进行质量评审"),
            ("AUCTION", "拍卖模式 - Agent竞标任务"),
            ("HYBRID", "混合模式 - 简单任务直接处理"),
        ]
        
        for mode_name, desc in modes:
            print_color(f"  • {mode_name}: {desc}", CliColors.WHITE)
        
        # 显示调度器状态
        if self.scheduler:
            print_color("\n调度器状态:", CliColors.CYAN)
            print_color(f"  ✅ 智能调度器已就绪", CliColors.GREEN)
        else:
            print_color("\n调度器状态:", CliColors.CYAN)
            print_color(f"  ❌ 智能调度器未初始化", CliColors.RED)


# 全局实例
_smart_agent_cli_v2 = None

def get_smart_agent_cli_v2():
    """获取智能Agent CLI v2实例（支持所有协作模式）"""
    global _smart_agent_cli_v2
    if _smart_agent_cli_v2 is None:
        _smart_agent_cli_v2 = SmartAgentCLIv2()
    return _smart_agent_cli_v2
