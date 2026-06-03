"""CLI智能多Agent交互模块 - 支持结构化分步执行"""

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

        try:
            # 智能调度器
            from core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler import (
                IntelligentScheduler
            )
            from core.multi_agent_v2.orchestration.context.global_context_center import (
                GlobalContextCenter
            )
            self.context_center = GlobalContextCenter()
            self.scheduler = IntelligentScheduler(self.context_center, self.llm_router)
            print_color("✅ 智能调度器初始化完成", CliColors.GREEN)
            print_color("   支持协作模式: PIPELINE, MASTER_SLAVE, REVIEW, AUCTION, HYBRID",
                       CliColors.GRAY)
        except Exception as e:
            print_warning(f"智能调度器未就绪（将使用分步执行模式）: {e}")
            self.scheduler = None

    # ════════════════════════════════════════════════════════════════
    # 新路径：结构化分步执行入口
    # ════════════════════════════════════════════════════════════════

    async def handle_task_with_steps(self, user_query: str):
        """使用 StepPlanner + StepExecutor 进行结构化分步执行

        流程:
          1. StepPlanner 将任务拆解为结构化步骤
          2. 展示步骤计划给用户
          3. StepExecutor 逐步执行
          4. 实时展示每步状态
          5. 汇总结果
        """
        print_color(f"\n📋 开始分步执行: {user_query}", CliColors.CYAN)
        print_color("──────────────────────────────────────────────", CliColors.GRAY)

        from cli.thinking_trace import get_trace
        trace = get_trace()
        trace.start(user_query)

        # 1. 创建 Task
        from core.multi_agent_v2.agents.base.models import Task
        task = Task(
            task_id=f"step_{int(time.time())}",
            type="user_task",
            description=user_query,
            keywords=user_query.split(),
            complexity=self._estimate_complexity(user_query),
            estimated_steps=self._estimate_steps(user_query),
        )

        # 2. StepPlanner 拆解
        print_color("\n🔍 正在拆解任务...", CliColors.WHITE)
        from core.multi_agent_v2.orchestration.scheduler.step_planner import StepPlanner

        planner = StepPlanner(llm_router=self.llm_router)

        # 获取可用工具列表（可选，用于提升 LLM 拆解质量）
        context = {}
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
            registry = get_tool_registry()
            if not registry._initialized:
                await registry.discover_all()
            tools = registry.get_tools_for_task(user_query, max_tools=15)
            if tools:
                context["available_tools"] = tools
        except Exception:
            pass

        steps = await planner.plan(task, context=context)

        if not steps:
            print_error("任务拆解失败，请重试")
            return

        print_color(f"\n📋 步骤计划 ({len(steps)} 步):", CliColors.BOLD)
        trace.display_step_plan(steps)

        # 展示依赖关系（如果有）
        has_deps = any(
            getattr(s, "dependencies", s.get("dependencies", []))
            for s in steps
        )
        if has_deps:
            trace.display_dependency_graph(steps)

        # 3. 用户确认
        print_color("\n是否执行上述步骤?", CliColors.WHITE)
        loop = asyncio.get_event_loop()
        confirmed = await loop.run_in_executor(
            None, lambda: input("  执行? (y/n/s:跳过确认) [Y]: ").strip().lower()
        )
        if confirmed in ("n", "no", "取消"):
            print_warning("用户取消执行")
            return

        skip_confirm = confirmed in ("s", "skip")

        # 4. StepExecutor 执行
        print_color("\n🚀 开始执行步骤...", CliColors.GREEN)

        from core.multi_agent_v2.infrastructure.step_executor import StepExecutor
        executor = StepExecutor(llm_router=self.llm_router)

        result = await executor.execute(
            steps=steps,
            task=task,
            on_step_start=trace.on_step_start,
            on_step_complete=trace.on_step_complete,
            on_step_failed=trace.on_step_failed,
        )

        # 5. 汇总结果
        print_color("\n" + "=" * 50, CliColors.GRAY)
        if result.success:
            print_color(f"✅ 全部完成! ({result.total_steps} 步, "
                       f"{result.total_execution_time:.1f}s)", CliColors.GREEN)
        else:
            print_warning(f"⚠️ 部分完成: {result.completed_steps}/{result.total_steps} 步成功, "
                         f"{result.failed_steps} 步失败")

        # 展示最终汇总
        if result.completed_steps > 0:
            print_color("\n📝 执行汇总:", CliColors.BOLD)
            for step in result.steps:
                status_icon = {
                    "success": "✓", "failed": "✗", "skipped": "→",
                    "blocked": "⊘", "running": "◐", "pending": "○",
                }.get(getattr(step, "status", "pending"), "?")
                status_val = getattr(step, "status", "pending")
                if isinstance(status_val, str):
                    status_str = status_val
                else:
                    status_str = getattr(status_val, "value", "pending")

                name = getattr(step, "name", getattr(step, "step_id", "?"))
                et = getattr(step, "execution_time", 0)
                time_str = f" ({et:.1f}s)" if et else ""

                if status_str == "success":
                    print_color(f"  {status_icon} {name}{time_str}", CliColors.GREEN)
                elif status_str == "failed":
                    err = getattr(step, "error", "")
                    print_color(f"  {status_icon} {name}: {err}", CliColors.RED)
                elif status_str == "skipped":
                    print_color(f"  {status_icon} {name}（跳过）", CliColors.GRAY)
                else:
                    print_color(f"  {status_icon} {name}", CliColors.WHITE)

        trace.done(result.success, result.total_execution_time,
                  f"{result.completed_steps}/{result.total_steps} steps")

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

        try:
            from core.multi_agent_v2.agents.base.models import Task

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
                    timeout=300.0
                )

                if exec_result["success"]:
                    print_color(f"\n🎉 任务执行完成! 耗时: {exec_result['execution_time']:.2f}s",
                               CliColors.GREEN)
                else:
                    print_error(f"任务执行失败: {exec_result.get('error', '未知错误')}")
            else:
                print_error(f"任务调度失败: {result.error}")

        except Exception as e:
            # 异常时降级到分步执行
            print_warning(f"调度器执行异常: {e}，降级到分步执行")
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
