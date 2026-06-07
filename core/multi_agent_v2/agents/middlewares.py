"""
中间件实现库 — 精简版

只保留核心中间件：
  - ReActDepthMiddleware   — 深度控制 + 连续失败检测
  - ReflectionMiddleware   — 定期反思，写入 temp_memory
  - KEPAMiddleware         — 知识沉淀 + 跨 Agent 共享（SharedBus）
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .middleware import BaseMiddleware, RunContext, HookResult

logger = logging.getLogger(__name__)

KEPA_PREFIX = "── KEPA 分析 ──"


# ════════════════════════════════════════════════════════════════
# ReActDepthMiddleware — ReAct 深度控制
# ════════════════════════════════════════════════════════════════

class ReActDepthMiddleware(BaseMiddleware):
    """追踪 ReAct 深度，防止无限循环 + 检测连续失败"""
    HOOKS = ("on_think_start", "on_tool_end")

    MAX_DEPTH = 30

    async def on_think_start(self, ctx: RunContext) -> None:
        if ctx.react_depth > self.MAX_DEPTH:
            ctx.interrupted = True
            logger.warning(f"ReAct 深度超过 {self.MAX_DEPTH}，终止执行")

    async def on_tool_end(self, ctx: RunContext) -> None:
        if ctx.tool_results:
            last = ctx.tool_results[-1]
            tc = last.get("tool_call", {})
            name = tc.get("name", "")
            if name and not last.get("success"):
                ctx.consecutive_failures[name] = ctx.consecutive_failures.get(name, 0) + 1
            elif name:
                ctx.consecutive_failures[name] = 0


# ════════════════════════════════════════════════════════════════
# ReflectionMiddleware — 执行反思
# ════════════════════════════════════════════════════════════════

class ReflectionMiddleware(BaseMiddleware):
    """定期对执行结果进行反思，沉淀经验到 temp_memory"""
    HOOKS = ("on_tool_end",)

    REFLECTION_INTERVAL = 3  # 每 N 轮反思一次

    async def on_tool_end(self, ctx: RunContext) -> None:
        if ctx.iteration < 2:
            return
        if ctx.iteration % self.REFLECTION_INTERVAL != 0:
            return

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
            if self.agent:
                self.agent.temp_memory["reflection"] = {
                    "problem": f"连续 {total} 次工具调用全部失败",
                    "tools_used": [r.get("tool_call", {}).get("name", "?") for r in recent],
                    "suggestion": "换工具或直接回答",
                    "iteration": ctx.iteration,
                }


# ════════════════════════════════════════════════════════════════
# KEPAMiddleware — KEPA 闭环
# ════════════════════════════════════════════════════════════════

class KEPAMiddleware(BaseMiddleware):
    """KEPA 闭环 — 知识沉淀 + 跨 Agent 共享

    - on_tool_end: 从工具结果提取知识 → 存入 SharedBus 共享存储
    - on_think_start: 查询 SharedBus 中的共享知识 → 注入到 LLM 提示词
    """
    HOOKS = ("on_think_start", "on_tool_end", "on_finish")

    async def on_think_start(self, ctx: RunContext) -> None:
        """在 LLM 思考前注入跨 Agent 共享知识"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.tool_results or ctx.iteration < 2:
            return

        try:
            shared = await self._fetch_shared_knowledge(ctx)
            knowledge_text = self._build_knowledge(ctx)
            evaluation_text = self._build_evaluation(ctx)
            planning_text = self._build_planning(ctx)

            lines = [KEPA_PREFIX]
            if shared:
                lines.append(f"[跨Agent知识] 其他Agent提供了: {shared}")
            lines.append(f"知识: {knowledge_text}")
            lines.append(f"评估: {evaluation_text}")
            lines.append(f"规划: {planning_text}")
            lines.append("──")
            ctx.task_description += f"\n\n{chr(10).join(lines)}\n"
        except Exception as e:
            logger.debug(f"KEPA 分析注入失败: {e}")

    async def _fetch_shared_knowledge(self, ctx: RunContext) -> str:
        """从 SharedBus 获取其他 Agent 沉淀的知识"""
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()

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
            relevant_tags.add("kepa")

            if not relevant_tags:
                return ""

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
        """工具执行后：提取知识 → 存入 SharedBus + temp_memory"""
        if not ctx.profile.get("use_shared_bus"):
            return
        if not ctx.tool_results:
            return

        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
            bus = get_shared_bus()

            for r in reversed(ctx.tool_results):
                if not r.get("success"):
                    continue
                tc = r.get("tool_call", {})
                name = tc.get("name", "")
                if not name:
                    continue

                result_str = str(r.get("result", ""))
                summary = result_str[:200]
                if len(summary) < 10:
                    continue

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

                if self.agent:
                    self.agent.temp_memory["kepa_summary"] = {
                        "tool": name,
                        "summary": summary[:100],
                        "iteration": ctx.iteration,
                        "tags": list(tags),
                    }
                break
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
        if not ctx.tool_results:
            return "尚未开始执行，需要收集数据"
        success_rate = sum(1 for r in ctx.tool_results if r.get("success")) / max(len(ctx.tool_results), 1)
        if success_rate > 0.7:
            return "执行顺利，可继续当前策略"
        elif any(count >= 2 for count in ctx.consecutive_failures.values()):
            return "存在连续失败，建议切换方法"
        return "需要继续收集信息"

    def _build_planning(self, ctx: RunContext) -> str:
        if not ctx.tool_results:
            return "开始执行"
        fail_count = sum(1 for r in ctx.tool_results if not r.get("success"))
        if fail_count >= 3:
            return "连续失败，建议换用替代工具或直接输出结果"
        return "继续当前任务"
