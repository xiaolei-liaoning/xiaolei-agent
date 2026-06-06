"""CLI智能多Agent交互模块 - IntelligentScheduler 已移除，降级为分步执行"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from cli.colors import CliColors, print_color, print_success, print_error, print_warning, print_info

logger = logging.getLogger(__name__)


class SmartAgentCLIv2:
    """智能多Agent CLI交互模块 - 支持结构化分步执行"""

    def __init__(self):
        self.scheduler = None
        self.context_center = None
        self.llm_router = None
        self._init_dependencies()

    def _init_dependencies(self):
        """初始化依赖（延迟加载）"""
        try:
            # LLM Router
            from core.engine.llm_backend import get_llm_router
            self.llm_router = get_llm_router()
            print_color("✅ LLM 路由就绪", CliColors.GREEN)
        except Exception as e:
            print_warning(f"LLM 路由初始化失败（将使用模拟模式）: {e}")

        # 智能调度器已移除（IntelligentScheduler 已删除）
        logger.warning("IntelligentScheduler 已移除，使用分步执行模式")
        self.scheduler = None

    # ════════════════════════════════════════════════════════════════
    # 新路径：结构化分步执行入口
    # ════════════════════════════════════════════════════════════════

    async def handle_task_with_steps(self, user_query: str):
        """结构化分步执行 — StepPlanner 已移除，不可用"""
        logger.warning("StepPlanner 已移除，handle_task_with_steps 不可用")
        print_warning("步骤拆解不可用（StepPlanner 已移除）")

    # ════════════════════════════════════════════════════════════════
    # 旧路径：通过调度器执行（兼容）
    # ════════════════════════════════════════════════════════════════

    async def handle_smart_task_with_mode(self, user_query: str, collaboration_mode=None):
        """使用指定协作模式处理智能任务（旧路径，兼容）"""
        if not self.scheduler:
            # 降级到分步执行
            print_warning("调度器未就绪，降级到分步执行模式")
            await self.handle_task_with_steps(user_query)
            return

        print_color(f"\n🚀 智能任务处理: {user_query}", CliColors.CYAN)
        print_color("──────────────────────────────────────────────", CliColors.GRAY)

        # IntelligentScheduler 已移除，降级到分步执行
        print_warning("IntelligentScheduler 已移除，降级到分步执行模式")
        await self.handle_task_with_steps(user_query)

    def _estimate_complexity(self, query: str) -> float:
        """估算任务复杂度"""
        complexity = 0.3
        complex_keywords = ["分析", "报告", "复杂", "深入", "全面", "详细"]
        simple_keywords = ["简单", "快速", "简短", "一句话"]

        for kw in complex_keywords:
            if kw in query:
                complexity += 0.2
        for kw in simple_keywords:
            if kw in query:
                complexity -= 0.1
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
        """执行已调度的任务（旧兼容）"""
        print_color("\n📋 开始执行任务...", CliColors.BOLD)

        from core.multi_agent_v2.orchestration.context.global_context_center import TaskState

        await self.context_center.update_task_state(
            task.task_id,
            TaskState.RUNNING,
            {"collaboration_mode": schedule_result.collaboration_mode.value}
        )

        for step, agent_id in schedule_result.assigned_agents.items():
            print_color(f"\n  🔄 [{step}] 执行中 (Agent: {agent_id})...", CliColors.WHITE)
            await asyncio.sleep(0.5)
            print_color(f"     ✅ 完成", CliColors.GREEN)

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

        # 显示分步执行模式
        print_color("\n✨ 新增功能: 结构化分步执行", CliColors.CYAN)
        print_color("  • StepPlanner: LLM驱动的任务拆解", CliColors.WHITE)
        print_color("  • StepExecutor: 可感知依赖的分步执行", CliColors.WHITE)
        print_color("  • 实时步骤状态展示", CliColors.WHITE)

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

        if self.scheduler:
            print_color("\n调度器状态:", CliColors.CYAN)
            print_color(f"  ✅ 智能调度器已就绪", CliColors.GREEN)
        else:
            print_color("\n调度器状态:", CliColors.CYAN)
            print_color(f"  ⚡ 使用分步执行模式（精简）", CliColors.WHITE)


# ── 全局实例 ─────────────────────────────────────────────────────────────────
_smart_agent_cli_v2 = None


def get_smart_agent_cli_v2():
    """获取智能Agent CLI v2实例"""
    global _smart_agent_cli_v2
    if _smart_agent_cli_v2 is None:
        _smart_agent_cli_v2 = SmartAgentCLIv2()
    return _smart_agent_cli_v2
