"""
中间件实现库 — BaseAgent ReAct 循环的模块化增强

所有中间件继承 BaseMiddleware，挂接到 MiddlewareChain 的生命周期钩子：
  on_start → on_think_start → on_think_end → on_tool_end → on_finish
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .middleware import BaseMiddleware, RunContext, DynamicStageRoutingMiddleware

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# ProfileMiddleware — 执行画像决策
# ════════════════════════════════════════════════════════════════

class ProfileMiddleware(BaseMiddleware):
    """根据任务描述决定执行画像（是否用 workspace / sandbox / RAG 等）"""

    async def on_start(self, ctx: RunContext) -> None:
        profile = ctx.profile
        desc = ctx.task_description.lower()

        # 检测是否包含显式路径
        import re
        has_explicit_path = bool(re.search(r'/[\w/]+\.\w+', desc))

        is_code = any(kw in desc for kw in [
            "写", "编写", "代码", "文件", "生成", "create", "write",
            "implement", "script", "程序", "游戏", "app", "工具",
            "优化", "修改", "改善", "编辑", "修复",
        ])
        is_project = any(kw in desc for kw in [
            "项目", "工程", "模块", "包", "依赖",
            "project", "module", "package",
        ])
        is_search = any(kw in desc for kw in [
            "搜索", "查询", "查找", "search", "find", "lookup",
        ])

        profile["has_explicit_path"] = has_explicit_path
        profile["use_workspace"] = (is_code and not has_explicit_path) or is_project
        profile["use_mcp_fallback"] = is_search or (not is_code and not is_project)
        profile["use_rag"] = is_search

        if has_explicit_path:
            ctx.is_code_task = False  # 直读直写
        else:
            ctx.is_code_task = is_code

        logger.debug(f"执行画像: workspace={profile['use_workspace']}, "
                     f"rag={profile['use_rag']}, code={ctx.is_code_task}")


# ════════════════════════════════════════════════════════════════
# ReActDepthMiddleware — ReAct 深度控制
# ════════════════════════════════════════════════════════════════

class ReActDepthMiddleware(BaseMiddleware):
    """追踪 ReAct 深度，防止无限循环（react_depth 由 ReActCoreMiddleware 递增）"""

    MAX_DEPTH = 10

    async def on_think_start(self, ctx: RunContext) -> None:
        # 不递增 react_depth——ReActCoreMiddleware.on_think_start 已做
        if ctx.react_depth > self.MAX_DEPTH:
            ctx.interrupted = True
            ctx.last_error = f"ReAct 深度超过 {self.MAX_DEPTH}，终止执行"
            logger.warning(f"ReAct 深度超过 {self.MAX_DEPTH}，终止执行")

    async def on_tool_end(self, ctx: RunContext) -> None:
        """检测连续失败的工具调用"""
        if ctx.tool_results:
            last = ctx.tool_results[-1]
            tc = last.get("tool_call", {})
            name = tc.get("name", "")
            if name and not last.get("success"):
                ctx.consecutive_failures[name] = ctx.consecutive_failures.get(name, 0) + 1
            elif name:
                ctx.consecutive_failures[name] = 0


# ════════════════════════════════════════════════════════════════
# ConfidenceMiddleware — 置信度评估
# ════════════════════════════════════════════════════════════════

class ConfidenceMiddleware(BaseMiddleware):
    """基于工具调用成功率和结果质量计算置信度。低置信度 → 推决策信号"""

    async def on_tool_end(self, ctx: RunContext) -> None:
        if not ctx.tool_results:
            return

        success_count = sum(1 for r in ctx.tool_results if r.get("success"))
        total = len(ctx.tool_results)
        success_rate = success_count / total if total > 0 else 0

        has_output = any(
            r.get("result") and str(r.get("result", "")) != "{}"
            for r in ctx.tool_results
        )

        base = 0.0
        if has_output and success_rate > 0.7:
            base = 0.85
        elif has_output and success_rate > 0.5:
            base = 0.7
        elif success_rate > 0.5:
            base = 0.5
        else:
            base = 0.3

        has_written = any(
            r.get("tool_call", {}).get("name", "") in ("file", "workspace_write_file", "write_file")
            and r.get("success")
            for r in ctx.tool_results
        )
        if has_written:
            base = max(base, 0.9)
        elif base < 0.5 and total >= 2 and not ctx.interrupted:
            ctx.decisions.append({"action": "retry", "reason": f"置信度过低({base:.1f})，建议换策略"})
            logger.info(f"置信度{base:.1f}触发决策信号")

        ctx.confidence_scores.append(base)
        ctx.confidence_total = sum(ctx.confidence_scores) / len(ctx.confidence_scores)


# ════════════════════════════════════════════════════════════════
# ReflectionMiddleware — 执行反思
# ════════════════════════════════════════════════════════════════

class ReflectionMiddleware(BaseMiddleware):
    """定期对执行结果进行反思。全部失败时推决策信号"""

    REFLECTION_INTERVAL = 2

    async def on_tool_end(self, ctx: RunContext) -> None:
        if ctx.iteration < 2:
            return
        if ctx.iteration % self.REFLECTION_INTERVAL != 0:
            return

        recent = ctx.tool_results[-self.REFLECTION_INTERVAL:]
        success = sum(1 for r in recent if r.get("success"))
        total = len(recent)

        reflection = {
            "iteration": ctx.iteration, "round": ctx.iteration,
            "success_rate": success / total if total > 0 else 0,
            "total_calls": len(ctx.tool_results),
            "success_calls": sum(1 for r in ctx.tool_results if r.get("success")),
            "timestamp": time.time(),
        }
        ctx.reflection_history.append(reflection)
        ctx.profile["reflection_data"] = reflection

        if success == 0 and total > 0 and not ctx.profile.get("reflection_feedback"):
            logger.warning(f"反思: 连续 {total} 次工具调用全部失败")
            ctx.decisions.append({"action": "retry", "reason": "全部工具调用失败，请换方法"})
            ctx.profile["reflection_feedback"] = True


# ════════════════════════════════════════════════════════════════
# SubtaskMiddleware — 子任务分解
# ════════════════════════════════════════════════════════════════

class SubtaskMiddleware(BaseMiddleware):
    """处理复杂任务的子任务分解和追踪"""

    async def on_think_start(self, ctx: RunContext) -> None:
        """在收集阶段后触发子任务分解"""
        stage_mw = self.agent.mind._chain.get(DynamicStageRoutingMiddleware) if hasattr(self.agent, 'mind') else None
        if not stage_mw:
            return

        # 如果是收集阶段完成且任务复杂，注入分解提示
        if ctx.iteration == 2 and len(ctx.task_description) > 80:
            logger.info("任务较长，子任务分解已就绪")


# ════════════════════════════════════════════════════════════════
# BranchMiddleware — 条件分支
# ════════════════════════════════════════════════════════════════

class BranchMiddleware(BaseMiddleware):
    """根据执行状态决定是否终止或重试（推决策信号）"""

    async def on_think_end(self, ctx: RunContext) -> None:
        if not ctx.last_error:
            ctx.profile["branch_hint_added"] = False
            return

        consecutive_fails = sum(1 for r in ctx.tool_results[-3:] if not r.get("success"))
        if consecutive_fails >= 3 and not ctx.profile.get("branch_hint_added"):
            logger.warning("连续 3 次失败，推终止信号")
            ctx.decisions.append({"action": "abort", "reason": f"连续{consecutive_fails}次失败，终止当前策略"})
            ctx.profile["branch_hint_added"] = True


# ════════════════════════════════════════════════════════════════
# KEPAMiddleware — KEPA 闭环
# ════════════════════════════════════════════════════════════════

class KEPAMiddleware(BaseMiddleware):
    """记录执行状态到 ctx.kepa_states（KEPA闭环感知），供后续中间件或上层消费"""

    async def on_tool_end(self, ctx: RunContext) -> None:
        if ctx.tool_results:
            last = ctx.tool_results[-1]
            state = "success" if last.get("success") else "failed"
            ctx.kepa_states.append(state)

    async def on_finish(self, ctx: RunContext) -> None:
        """记录最终执行摘要到 ctx.profile"""
        try:
            ctx.profile["kepa_summary"] = {
                "success": bool(ctx.final_answer) or ctx.confidence_total > 0.5,
                "iterations": ctx.iteration,
                "total_tools": len(ctx.tool_results),
                "confidence": ctx.confidence_total,
                "all_failed": bool(ctx.kepa_states) and all(s == "failed" for s in ctx.kepa_states),
            }
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
# AskUserMiddleware — 用户交互
# ════════════════════════════════════════════════════════════════

class AskUserMiddleware(BaseMiddleware):
    """在关键决策点询问用户"""

    async def on_think_end(self, ctx: RunContext) -> None:
        """首轮简单回答时确认"""
        if ctx.iteration != 1:
            return
        if ctx.tool_results:
            return  # 已有工具调用，说明 LLM 有实际行动，不需要确认

        # 没有工具调用且是首轮 — LLM 可能直接回答了
        # 交给 Agent 的 _ask_user_inline 处理
        pass

    async def on_tool_end(self, ctx: RunContext) -> None:
        """工具连续失败时询问用户"""
        if not ctx.tool_results:
            return

        last = ctx.tool_results[-1]
        tc = last.get("tool_call", {})
        name = tc.get("name", "")
        if not name:
            return

        failed = ctx.consecutive_failures.get(name, 0)
        if failed >= 2 and not last.get("success"):
            logger.info(f"工具 {name} 连续失败 {failed} 次，准备询问用户")
            ctx.task_description += (
                f"\n[系统] 工具 {name} 已连续失败 {failed} 次。"
                f"请换其他工具或直接输出最终结果。"
            )


# ════════════════════════════════════════════════════════════════
# DataPipelineMiddleware — 数据流水线
# ════════════════════════════════════════════════════════════════

class DataPipelineMiddleware(BaseMiddleware):
    """数据流水线 — 提取/注入步骤间数据流

    功能：
    - 从上一个步骤的结果中提取关键字段注入到提示词
    - 在步骤之间传递结构化数据
    - 自动截断过长的数据（保护 token 预算）
    """

    MAX_DATA_LENGTH = 1500

    async def on_think_start(self, ctx: RunContext) -> None:
        """在 LLM 思考前，将上一步工具结果格式化为提示词上下文"""
        if not ctx.tool_results:
            return

        last = ctx.tool_results[-1]
        if not last.get("success"):
            return

        # 提取观察文本
        obs = ctx.get_latest_observation()
        if not obs or len(obs) < 20:
            return

        # 截断过长数据
        if len(obs) > self.MAX_DATA_LENGTH:
            obs = obs[:self.MAX_DATA_LENGTH] + f"\n... 截断 ({len(obs)} 字符)"

        # 注入到任务描述
        pipeline_hint = f"\n\n[上一步结果]\n{obs}\n"
        ctx.task_description += pipeline_hint

    async def on_tool_end(self, ctx: RunContext) -> None:
        """工具执行后，记录输出摘要到执行上下文"""
        if not ctx.tool_results:
            return
        last = ctx.tool_results[-1]
        tc = last.get("tool_call", {})
        name = tc.get("name", "")
        if not name:
            return

        summary = ctx.get_latest_observation()[:200] if last.get("success") else last.get("error", "")
        if summary:
            logger.debug(f"数据流: [{name}] → {summary[:80]}...")
