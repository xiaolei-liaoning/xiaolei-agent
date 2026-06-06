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

from .middleware import BaseMiddleware, RunContext, DynamicStageRoutingMiddleware, HookResult


logger = logging.getLogger(__name__)

KEPA_PREFIX = "── KEPA 分析 ──"


# ════════════════════════════════════════════════════════════════
# ProfileMiddleware — 执行画像决策
# ════════════════════════════════════════════════════════════════

class ProfileMiddleware(BaseMiddleware):
    """根据任务描述决定执行画像（是否用 workspace / sandbox / RAG 等）"""
    HOOKS = ("on_start",)

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
    HOOKS = ("on_think_start", "on_tool_end")

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
    HOOKS = ("on_tool_end",)

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
    HOOKS = ("on_tool_end",)

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
    HOOKS = ("on_think_end",)

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


# ════════════════════════════════════════════════════════════════
# KEPAMiddleware — KEPA 闭环
# ════════════════════════════════════════════════════════════════

class KEPAMiddleware(BaseMiddleware):
    """KEPA 闭环 — 知识沉淀 + 跨 Agent 共享

    双向闭环：
    - on_tool_end: 从工具结果提取知识 → 存入 SharedBus 共享存储
    - on_think_start: 查询 SharedBus 中的共享知识 → 注入到 LLM 提示词
    """
    HOOKS = ("on_think_start", "on_tool_end", "on_finish")

    async def on_think_start(self, ctx: RunContext) -> None:
        """在 LLM 思考前注入 KEPA 分析 + 跨 Agent 共享知识"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.tool_results or ctx.iteration < 2:
            return

        try:
            # 1. 查询 SharedBus 中的共享知识（其他 Agent 沉淀的）
            shared = await self._fetch_shared_knowledge(ctx)

            # 2. 自身上下文的知识摘要
            knowledge_text = self._build_knowledge(ctx)
            evaluation_text = self._build_evaluation(ctx)
            planning_text = self._build_planning(ctx)

            # 3. 注入到提示词
            lines = [KEPA_PREFIX]
            if shared:
                lines.append(f"[跨Agent知识] 其他Agent提供了: {shared}")
            lines.append(f"知识: {knowledge_text}")
            lines.append(f"评估: {evaluation_text}")
            lines.append(f"规划: {planning_text}")
            lines.append("──")
            action_text = "\n".join(lines)
            ctx.task_description += f"\n\n{action_text}\n"
        except Exception as e:
            logger.debug(f"KEPA 分析注入失败: {e}")

    async def _fetch_shared_knowledge(self, ctx: RunContext) -> str:
        """从 SharedBus 获取其他 Agent 沉淀的共享知识"""
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()

            # 检测任务与哪些知识标签相关
            desc_lower = ctx.task_description.lower()
            relevant_tags = set()
            if any(kw in desc_lower for kw in ["搜索", "查询", "百度", "热搜", "search"]):
                relevant_tags.add("search")
            if any(kw in desc_lower for kw in ["代码", "程序", "脚本", "code", "python"]):
                relevant_tags.add("code")
            if any(kw in desc_lower for kw in ["数据", "分析", "统计", "data", "analysis"]):
                relevant_tags.add("analysis")
            if any(kw in desc_lower for kw in ["文件", "写入", "保存", "file", "write"]):
                relevant_tags.add("file")
            relevant_tags.add("kepa")  # 通用标签

            if not relevant_tags:
                return ""

            # 逐个标签查询，收集结果
            snippets = []
            for tag in relevant_tags:
                results = await bus.search_knowledge(tag)
                for key, entry in results.items():
                    meta = entry.get("meta", {})
                    summary = meta.get("summary", "")
                    source = meta.get("source", "")
                    if summary and len(str(summary)) > 10:
                        snippets.append(f"[{source}]: {summary[:200]}")
            if snippets:
                return " | ".join(snippets[:3])
            return ""
        except Exception:
            return ""

    async def on_tool_end(self, ctx: RunContext) -> None:
        """工具执行后：提取知识 → 存入 SharedBus"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.tool_results:
            return

        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()

            # 提取最后成功的工具结果
            for r in reversed(ctx.tool_results):
                if not r.get("success"):
                    continue
                tc = r.get("tool_call", {})
                name = tc.get("name", "")
                if not name:
                    continue

                # 提取摘要
                result_str = str(r.get("result", ""))
                summary = result_str[:200]
                if len(summary) < 10:
                    continue

                # 自动推断标签
                tags = {"kepa"}
                if name in ("search", "fetch_url", "rag_search"):
                    tags.add("search")
                elif name in ("execute_python", "execute_shell"):
                    tags.add("code")
                elif name == "file":
                    tags.add("file")
                if "分析" in ctx.task_description or "analysis" in ctx.task_description:
                    tags.add("analysis")

                key = f"kepa:{name}:{ctx.iteration}"
                source = ctx.profile.get("agent_id", "unknown")
                await bus.store_knowledge(key, {"result": summary, "tool": name},
                                          tags=tags, source=source, summary=summary)
                logger.debug(f"KEPA 知识已沉淀: {key} (tags={tags})")
                break  # 每轮只存一条
        except Exception as e:
            logger.debug(f"KEPA 知识沉淀失败: {e}")

    async def on_finish(self, ctx: RunContext) -> None:
        """执行完成：最终知识摘要到 SharedBus"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.final_answer:
            return
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()
            source = ctx.profile.get("agent_id", "unknown")
            await bus.store_knowledge(
                f"kepa:final:{source}",
                {"final": ctx.final_answer[:500]},
                tags={"kepa", "final"},
                source=source,
                summary=f"最终结果: {ctx.final_answer[:200]}",
            )
        except Exception:
            pass

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


# ════════════════════════════════════════════════════════════════
# AskUserMiddleware — 用户交互
# ════════════════════════════════════════════════════════════════

class AskUserMiddleware(BaseMiddleware):
    """在关键决策点询问用户"""
    HOOKS = ("on_think_end", "on_tool_end", "on_wrap_tool_call")

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
    HOOKS = ("on_think_start",)

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


# ════════════════════════════════════════════════════════════════
# ReflectionCheckMiddleware — 反思检查（替代主循环硬编码逻辑）
# ════════════════════════════════════════════════════════════════

class ReflectionCheckMiddleware(BaseMiddleware):
    """检查反思历史与工具执行结果，替代主循环中的两段硬编码反思逻辑

    职责：
    - on_think_start: 如果上轮全部失败，注入 [反思] 提示到本轮
    - on_tool_end: 检测本轮全部失败 → 设置 reflection_feedback → 返回 HookResult(end)
    """
    HOOKS = ("on_think_start", "on_tool_end")

    async def on_think_start(self, ctx: RunContext) -> Optional[HookResult]:
        """在 LLM 思考前注入反思反馈（替换主循环 L607-614 硬编码）"""
        if not ctx.reflection_history or ctx.final_answer:
            return

        last_ref = ctx.reflection_history[-1]
        if last_ref.get("success_rate", 1) == 0 and last_ref.get("total_calls", 0) > 0:
            if not ctx.task_description.endswith("[反思]"):
                ctx.task_description += "\n[反思] 上一轮全部失败，请换一种方法（换工具或直接回答）。"
                logger.info("ReflectionCheck: 注入反思提示到下一轮")

    async def on_tool_end(self, ctx: RunContext) -> Optional[HookResult]:
        """检测工具全部失败（替换主循环 L592-595 硬编码 + L596-605 决策队列）"""
        if ctx.iteration < 1 or not ctx.tool_results:
            return

        # 检查最近这轮的调用是否全部失败
        recent = ctx.tool_results[-3:]  # 最近 3 次调用
        if len(recent) == 0:
            return

        # 如果最近3次调用都失败且没有产出，标记终止
        all_failed = all(not r.get("success") for r in recent)
        no_output = not any(
            r.get("result") and str(r.get("result", "")) != "{}" and str(r.get("result", "")) != ""
            for r in recent
        )

        if all_failed and no_output and len(recent) >= 2:
            ctx.profile["reflection_feedback"] = True
            reason = f"连续 {len(recent)} 次工具调用全部失败且无产出"
            logger.warning(f"ReflectionCheck: {reason}")
            return HookResult(jump_to="end", reason=reason)
