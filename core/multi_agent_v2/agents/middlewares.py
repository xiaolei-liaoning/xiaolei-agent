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

from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, Message, MessageType

logger = logging.getLogger(__name__)

KEPA_PREFIX = "── KEPA 分析 ──"


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
    """追踪 ReAct 深度，防止无限循环"""

    MAX_DEPTH = 30

    async def on_think_start(self, ctx: RunContext) -> None:
        # 注意：react_depth 由 ReActCoreMiddleware.on_think_start 自增
        # 这里只做深度检查，不自增（否则 ReActCore 读到的是未调用前的值）
        if ctx.react_depth > self.MAX_DEPTH:
            ctx.interrupted = True
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
    """基于工具调用成功率和结果质量计算置信度"""

    async def on_tool_end(self, ctx: RunContext) -> None:
        if not ctx.tool_results:
            return

        success_count = sum(1 for r in ctx.tool_results if r.get("success"))
        total = len(ctx.tool_results)
        success_rate = success_count / total if total > 0 else 0

        # 是否有有效输出
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

        # 检查最终写入
        has_written = any(
            r.get("tool_call", {}).get("name", "") in ("workspace_write_file", "write_file")
            and r.get("success")
            for r in ctx.tool_results
        )
        if has_written:
            base = max(base, 0.9)

        ctx.confidence_scores.append(base)
        ctx.confidence_total = sum(ctx.confidence_scores) / len(ctx.confidence_scores)


# ════════════════════════════════════════════════════════════════
# ReflectionMiddleware — 执行反思
# ════════════════════════════════════════════════════════════════

class ReflectionMiddleware(BaseMiddleware):
    """定期对执行结果进行反思，沉淀经验"""

    REFLECTION_INTERVAL = 3  # 每 N 轮反思一次

    async def on_tool_end(self, ctx: RunContext) -> None:
        if ctx.iteration < 2:
            return
        if ctx.iteration % self.REFLECTION_INTERVAL != 0:
            return

        # 统计本轮执行
        recent = ctx.tool_results[-self.REFLECTION_INTERVAL:]
        success = sum(1 for r in recent if r.get("success"))
        total = len(recent)

        reflection = {
            "iteration": ctx.iteration,
            "success_rate": success / total if total > 0 else 0,
            "total_calls": len(ctx.tool_results),
            "timestamp": time.time(),
        }
        ctx.reflection_history.append(reflection)

        if success == 0 and total > 0:
            logger.warning(f"反思: 连续 {total} 次工具调用全部失败")


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
    """根据执行状态决定是否需要切换策略"""

    def __init__(self):
        super().__init__()
        self._hint_added = False  # 防止重复添加

    async def on_think_end(self, ctx: RunContext) -> None:
        if not ctx.last_error:
            self._hint_added = False
            return

        consecutive_fails = sum(1 for r in ctx.tool_results[-3:] if not r.get("success"))
        if consecutive_fails >= 3 and not self._hint_added:
            logger.warning("连续 3 次失败，尝试切换策略")
            ctx.task_description += "\n[系统] 当前策略连续失败，请换一种方法。"
            self._hint_added = True

            # 发布分支决策到 SharedBus
            if ctx.profile.get("use_shared_bus"):
                try:
                    bus = get_shared_bus()
                    decision_msg = Message(
                        type=MessageType.AGENT_MESSAGE,
                        sender=self.agent.agent_id if self.agent else "unknown",
                        topic="branch:decision",
                        payload={
                            "consecutive_failures": consecutive_fails,
                            "decision": "retry_with_different_strategy",
                            "error": (ctx.last_error or "")[:200],
                            "iteration": ctx.iteration,
                            "timestamp": time.time(),
                        },
                    )
                    await bus.publish("branch:decision", decision_msg)
                except Exception as e:
                    logger.debug(f"BranchMiddleware 发布失败: {e}")


# ════════════════════════════════════════════════════════════════
# KEPAMiddleware — KEPA 闭环
# ════════════════════════════════════════════════════════════════

class KEPAMiddleware(BaseMiddleware):
    """KEPA 闭环 — 将 Knowledge/Evaluation/Planning/Action 注入提示词并发布到 SharedBus"""

    async def on_think_start(self, ctx: RunContext) -> None:
        """在 LLM 思考前注入 KEPA 分析并发布到 SharedBus"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.tool_results or ctx.iteration < 2:
            return

        try:
            bus = get_shared_bus()

            # Knowledge: 数据摘要
            knowledge_text = self._build_knowledge(ctx)
            msg_knowledge = Message(
                type=MessageType.AGENT_MESSAGE,
                sender=self.agent.agent_id if self.agent else "unknown",
                topic="kepa:knowledge",
                payload={
                    "summary": knowledge_text,
                    "iteration": ctx.iteration,
                    "timestamp": time.time(),
                },
            )
            await bus.publish("kepa:knowledge", msg_knowledge)

            # Evaluation: 充分性判断
            evaluation_text = self._build_evaluation(ctx)
            msg_evaluation = Message(
                type=MessageType.AGENT_MESSAGE,
                sender=self.agent.agent_id if self.agent else "unknown",
                topic="kepa:evaluation",
                payload={
                    "judgment": evaluation_text,
                    "iteration": ctx.iteration,
                    "timestamp": time.time(),
                },
            )
            await bus.publish("kepa:evaluation", msg_evaluation)

            # Planning: 下一步建议
            planning_text = self._build_planning(ctx)
            msg_planning = Message(
                type=MessageType.AGENT_MESSAGE,
                sender=self.agent.agent_id if self.agent else "unknown",
                topic="kepa:planning",
                payload={
                    "suggestions": planning_text,
                    "iteration": ctx.iteration,
                    "timestamp": time.time(),
                },
            )
            await bus.publish("kepa:planning", msg_planning)

            # Action: 注入到提示词的内容
            action_lines = [
                KEPA_PREFIX,
                f"知识: {knowledge_text}",
                f"评估: {evaluation_text}",
                f"规划: {planning_text}",
                "──",
            ]
            action_text = "\n".join(action_lines)
            ctx.task_description += f"\n\n{action_text}\n"

            msg_action = Message(
                type=MessageType.AGENT_MESSAGE,
                sender=self.agent.agent_id if self.agent else "unknown",
                topic="kepa:action",
                payload={
                    "injected": action_text,
                    "iteration": ctx.iteration,
                    "timestamp": time.time(),
                },
            )
            await bus.publish("kepa:action", msg_action)

        except Exception as e:
            logger.debug(f"KEPA 分析注入/发布失败: {e}")

    def _build_knowledge(self, ctx: RunContext) -> str:
        """从工具结果构建知识摘要"""
        if not ctx.tool_results:
            return "尚未收集到数据"
        lines = []
        for r in ctx.tool_results[-5:]:
            tc = r.get("tool_call", {})
            name = tc.get("name", "?")
            ok = "成功" if r.get("success") else "失败"
            preview = str(r.get("result", ""))[:80]
            lines.append(f"[{ok}] {name}: {preview}")
        return "\n".join(lines)

    def _build_evaluation(self, ctx: RunContext) -> str:
        """评估当前信息是否充分"""
        if not ctx.tool_results:
            return "尚未开始执行，需要收集数据"
        success_rate = sum(1 for r in ctx.tool_results if r.get("success")) / max(len(ctx.tool_results), 1)
        has_written = any(
            r.get("tool_call", {}).get("name", "") in ("workspace_write_file", "write_file")
            for r in ctx.tool_results
        )
        if has_written and success_rate > 0.5:
            return "信息充分，可继续推进"
        elif success_rate > 0.7:
            return "执行顺利，可继续当前策略"
        elif any(count >= 2 for count in ctx.consecutive_failures.values()):
            return "存在连续失败，建议切换方法"
        return "需要继续收集信息"

    def _build_planning(self, ctx: RunContext) -> str:
        """建议下一步操作"""
        if not ctx.tool_results:
            return "开始执行"
        fail_count = sum(1 for r in ctx.tool_results if not r.get("success"))
        if fail_count >= 3:
            return "连续失败，建议换用替代工具或直接输出结果"
        has_written = any(
            r.get("tool_call", {}).get("name", "") in ("workspace_write_file", "write_file")
            for r in ctx.tool_results
        )
        if has_written:
            return "文件已写入，建议验证和总结"
        return "继续当前任务"

    async def on_tool_end(self, ctx: RunContext) -> None:
        if not ctx.profile.get("use_shared_bus"):
            return
        try:
            bus = get_shared_bus()
            if ctx.tool_results:
                last = ctx.tool_results[-1]
                msg = Message(
                    type=MessageType.TASK_PROGRESS if last.get("success") else MessageType.TASK_FAILED,
                    sender=self.agent.agent_id if self.agent else "unknown",
                    topic="kepa:tool_result",
                    payload={
                        "type": "tool_result",
                        "agent_id": self.agent.agent_id if self.agent else "unknown",
                        "iteration": ctx.iteration,
                        "tool_name": last.get("tool_call", {}).get("name", "?"),
                        "success": last.get("success", False),
                        "preview": str(last.get("result", ""))[:200],
                        "timestamp": time.time(),
                    },
                )
                await bus.publish(msg.topic, msg)
        except Exception as e:
            logger.debug(f"KEPA 发布失败: {e}")

    async def on_finish(self, ctx: RunContext) -> None:
        """发布最终执行报告"""
        if not ctx.profile.get("use_shared_bus"):
            return
        try:
            bus = get_shared_bus()
            msg = Message(
                type=MessageType.TASK_COMPLETED,
                sender=self.agent.agent_id if self.agent else "unknown",
                topic="agent:done",
                payload={
                    "success": ctx.confidence_total > 0.5,
                    "iterations": ctx.iteration,
                    "total_tools": len(ctx.tool_results),
                    "confidence": ctx.confidence_total,
                    "final_answer": ctx.final_answer[:500],
                    "timestamp": time.time(),
                },
            )
            await bus.publish(msg.topic, msg)
        except Exception as e:
            logger.debug(f"KEPA 完成消息发布失败: {e}")


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
        """工具执行后，记录输出摘要到执行上下文，并发布到 SharedBus"""
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

        # 发布流水线数据到 SharedBus
        if ctx.profile.get("use_shared_bus"):
            try:
                bus = get_shared_bus()
                data_msg = Message(
                    type=MessageType.TASK_PROGRESS,
                    sender=self.agent.agent_id if self.agent else "unknown",
                    topic="pipeline:data",
                    payload={
                        "tool_name": name,
                        "success": last.get("success", False),
                        "summary": summary[:300] if summary else "",
                        "iteration": ctx.iteration,
                        "timestamp": time.time(),
                    },
                )
                await bus.publish("pipeline:data", data_msg)
            except Exception as e:
                logger.debug(f"DataPipeline 发布失败: {e}")
