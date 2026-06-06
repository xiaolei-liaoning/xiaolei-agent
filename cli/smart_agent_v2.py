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
        self.llm_router = None
        self._orchestrator = None
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
            # 编排器模块 — 验证导入正常
            from core.multi_agent_v2.orchestration import orchestrator as orch_mod
            # 验证关键 API 存在
            _ = orch_mod.agent
            _ = orch_mod.parallel
            _ = orch_mod.pipeline
            self._orchestrator = orch_mod
            print_color("✅ Orchestrator 编排引擎就绪", CliColors.GREEN)
            print_color("   支持: agent / parallel / pipeline / phase / log", CliColors.GRAY)
        except Exception as e:
            print_warning(f"Orchestrator 编排引擎未就绪: {e}")
            self._orchestrator = None

    # ════════════════════════════════════════════════════════════════
    # 新路径：结构化分步执行入口
    # ════════════════════════════════════════════════════════════════

    async def handle_task_with_steps(self, user_query: str):
        """使用编排引擎顺序 agent() 调用进行分步执行

        流程:
          1. 将任务拆解为 3 个顺序步骤
          2. 每个步骤通过 orchestrator.agent() 顺序执行
          3. 上一步的输出传递为下一步的上下文
          4. 汇总结果
        """
        print_color(f"\n📋 开始分步执行: {user_query}", CliColors.CYAN)
        print_color("──────────────────────────────────────────────", CliColors.GRAY)

        # 估算步骤
        n_steps = self._estimate_steps(user_query)
        print_color(f"🔍 计划 {n_steps} 个顺序步骤", CliColors.WHITE)

        if not self._orchestrator:
            print_error("Orchestrator 未就绪，无法执行")
            return

        orch = self._orchestrator

        # 通用 3 步分解模板
        step_templates = [
            f"分析理解：{user_query}\n请仔细理解任务目标，分析所需资源和前置条件，输出分析结果。",
            f"执行实施：{user_query}\n基于分析结果，实际执行任务。利用可用的工具完成工作。",
            f"验证总结：{user_query}\n检查执行结果是否完整准确，输出最终总结。",
        ]

        # 如果用户查询特别短，使用精简步骤
        if len(user_query) < 20:
            step_templates = [
                f"执行：{user_query}\n直接完成任务。",
                f"总结：{user_query}\n输出执行结果总结。",
            ]

        # 根据估计的步数截取
        steps_to_run = step_templates[:n_steps]

        try:
            orch.phase("分步执行")
            step_results = []
            context_buffer = ""

            for i, step_prompt in enumerate(steps_to_run, 1):
                label = f"步骤{i}/{len(steps_to_run)}"

                # 注入上下文（上一步的输出）
                if context_buffer:
                    full_prompt = f"{step_prompt}\n\n上一步完成结果：\n{context_buffer[:1000]}"
                else:
                    full_prompt = step_prompt

                print_color(f"\n  🔄 [{label}] 执行中...", CliColors.CYAN)
                result = await orch.agent(
                    full_prompt,
                    {"label": label, "timeout": 180},
                )

                step_results.append(result)

                # 传递输出作为下一步上下文
                if result.success:
                    context_buffer = result.text()
                    icon = "✅"
                    detail = f"({result.execution_time:.1f}s)"
                else:
                    context_buffer = f"(步骤{i}失败: {result.error or '未知错误'})"
                    icon = "⚠️"
                    detail = f"({result.execution_time:.1f}s) {result.error or ''}"

                print_color(f"  {icon} [{label}] {detail}",
                           CliColors.GREEN if result.success else CliColors.YELLOW)

            # 汇总
            print_color("\n" + "=" * 50, CliColors.GRAY)
            success_count = sum(1 for r in step_results if r.success)
            if success_count == len(step_results):
                print_color(f"✅ 全部完成! ({len(step_results)} 步)", CliColors.GREEN)
            else:
                print_warning(f"⚠️ 部分完成: {success_count}/{len(step_results)} 步成功")

            if step_results and step_results[-1].success:
                final = step_results[-1]
                print_color("\n📝 执行汇总:", CliColors.BOLD)
                snippet = final.text()[:300]
                if snippet:
                    print_color(f"  {snippet}", CliColors.WHITE)

        except Exception as e:
            print_error(f"分步执行异常: {e}")
            logger.exception("handle_task_with_steps failed")

    # ════════════════════════════════════════════════════════════════
    # 旧路径：通过调度器执行（兼容）
    # ════════════════════════════════════════════════════════════════

    async def handle_smart_task_with_mode(self, user_query: str, collaboration_mode=None):
        """使用编排引擎并行处理智能任务（旧路径兼容）"""
        if not self._orchestrator:
            # 降级到分步执行
            print_warning("编排引擎未就绪，降级到分步执行模式")
            await self.handle_task_with_steps(user_query)
            return

        print_color(f"\n🚀 智能任务处理: {user_query}", CliColors.CYAN)
        print_color("──────────────────────────────────────────────", CliColors.GRAY)

        try:
            orch = self._orchestrator

            # 根据复杂度/关键词动态拆分为多个维度
            complexity = self._estimate_complexity(user_query)
            dimensions = self._break_into_dimensions(user_query, complexity)

            if len(dimensions) <= 1:
                # 简单任务：单 agent 顺序执行
                orch.phase("执行")
                result = await orch.agent(user_query, {"label": "执行", "timeout": 120})
                print_color(f"\n{'✅' if result.success else '⚠️'} 执行完成 ({result.execution_time:.1f}s)",
                           CliColors.GREEN if result.success else CliColors.YELLOW)
                return result

            # 复杂任务：多维度并行
            orch.phase("并行调研")

            # 每个 thunk 是 lambda: coroutine，parallel() 内部会 await 执行
            thunks = [
                lambda d=d: orch.agent(d, {"label": d[:30], "timeout": 180})
                for d in dimensions
            ]

            results = await orch.parallel(thunks, max_concurrent=len(thunks))

            # 汇总阶段
            orch.phase("汇总")
            success_count = sum(1 for r in results if r.success)
            total = len(results)
            print_color(f"\n📊 并行执行完成: {success_count}/{total} 成功", CliColors.CYAN)

            for r in results:
                icon = "✅" if r.success else "⚠️"
                detail = f"({r.execution_time:.1f}s)"
                if not r.success and r.error:
                    detail += f" {r.error[:60]}"
                print_color(f"  {icon} {r.label} {detail}",
                           CliColors.GREEN if r.success else CliColors.YELLOW)

            # 汇总结果
            if success_count > 0:
                orch.phase("结果整合")
                summary_prompt = f"整合以下 {success_count} 个并行维度的结果为一个完整回答：\n"
                for i, r in enumerate(results):
                    if r.success:
                        summary_prompt += f"\n维度{i+1} ({r.label}):\n{r.text()[:500]}\n"
                summary_prompt += f"\n原始任务: {user_query}"
                summary = await orch.agent(summary_prompt,
                                          {"label": "结果整合", "timeout": 120})
                if summary.success:
                    print_color(f"\n✅ 汇总完成", CliColors.GREEN)

            return results

        except Exception as e:
            print_warning(f"编排引擎执行异常: {e}，降级到分步执行")
            await self.handle_task_with_steps(user_query)

    def _break_into_dimensions(self, query: str, complexity: float) -> list:
        """将任务拆解为多个独立维度用于并行执行"""
        dimensions = []

        # 关键词检测拆维
        if "搜索" in query or "查找" in query or "调研" in query:
            dimensions.append(f"搜索调研: {query}")
        if "分析" in query or "统计" in query or "评估" in query:
            dimensions.append(f"分析评估: {query}")
        if "写" in query or "生成" in query or "创建" in query or "报告" in query:
            dimensions.append(f"生成写作: {query}")
        if "爬" in query or "采集" in query or "抓取" in query:
            dimensions.append(f"数据采集: {query}")
        if "代码" in query or "脚本" in query or "函数" in query:
            dimensions.append(f"代码开发: {query}")
        if "翻译" in query or "convert" in query.lower():
            dimensions.append(f"翻译转换: {query}")

        # 高复杂任务额外增加维度
        if complexity > 0.6 and not dimensions:
            dimensions.append(f"详细分析: {query}")
            dimensions.append(f"方案建议: {query}")
        if complexity > 0.8:
            dimensions.append(f"质量评审: {query}")

        # 兜底：至少一个维度
        if not dimensions:
            dimensions.append(query)

        return dimensions[:5]  # 最多 5 个维度

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
        """执行已调度的任务（旧兼容 — 委托给 orchestrator.agent）"""
        print_color("\n📋 开始执行任务（编排引擎）...", CliColors.BOLD)
        if self._orchestrator:
            result = await self._orchestrator.agent(
                task.description or str(task),
                {"label": f"task_{task.task_id[:8]}", "timeout": 300},
            )
            if result.success:
                print_color(f"\n✅ 执行完成 ({result.execution_time:.1f}s)", CliColors.GREEN)
            else:
                print_color(f"\n⚠️ 执行失败: {result.error}", CliColors.RED)
        else:
            print_warning("编排引擎未就绪，跳过执行")

    async def handle_collaboration_mode_demo(self):
        """演示编排引擎功能"""
        print_color("\n🎬 Orchestrator 编排引擎演示", CliColors.BOLD)
        print_color("──────────────────────────────────────────────", CliColors.GRAY)

        demo_tasks = [
            ("agent", "简单查询今天的天气"),
            ("parallel", "帮我爬取微博热搜并分析数据生成报告"),
            ("pipeline", "处理一个复杂的计算任务"),
        ]

        for mode, query in demo_tasks:
            print_color(f"\n[{mode}] 测试任务: {query}", CliColors.CYAN)
            await self.handle_smart_task_with_mode(query, mode)
            await asyncio.sleep(1)

    async def handle_agent_status(self):
        """显示Agent状态和可用编排模式"""
        print_color("\n🦾 Agent状态监控", CliColors.BOLD)
        print_color("────────────────", CliColors.GRAY)

        # 显示分步执行模式
        print_color("\n✨ Orchestrator 编排引擎", CliColors.CYAN)
        print_color("  • agent(): 单 Agent 子任务执行", CliColors.WHITE)
        print_color("  • parallel(): 多 Agent 并行执行", CliColors.WHITE)
        print_color("  • pipeline(): 流水线无屏障执行", CliColors.WHITE)
        print_color("  • phase()/log(): 阶段可视化", CliColors.WHITE)

        # 显示支持的编排模式
        print_color("\n支持的编排模式:", CliColors.CYAN)
        modes = [
            ("agent", "单 Agent 顺序执行"),
            ("parallel", "多 Agent 并行执行"),
            ("pipeline", "流水线多阶段执行"),
        ]

        for mode_name, desc in modes:
            print_color(f"  • {mode_name}: {desc}", CliColors.WHITE)

        if self._orchestrator:
            print_color("\n编排器状态:", CliColors.CYAN)
            print_color(f"  ✅ Orchestrator 编排引擎已就绪", CliColors.GREEN)
        else:
            print_color("\n编排器状态:", CliColors.CYAN)
            print_color(f"  ⚡ 编排引擎未就绪（使用降级模式）", CliColors.WHITE)


# ── 全局实例 ─────────────────────────────────────────────────────────────────
_smart_agent_cli_v2 = None


def get_smart_agent_cli_v2():
    """获取智能Agent CLI v2实例"""
    global _smart_agent_cli_v2
    if _smart_agent_cli_v2 is None:
        _smart_agent_cli_v2 = SmartAgentCLIv2()
    return _smart_agent_cli_v2
