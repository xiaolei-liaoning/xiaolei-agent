"""
中间件实现库 — BaseAgent ReAct 循环的模块化增强

所有中间件继承 BaseMiddleware，挂接到 MiddlewareChain 的生命周期钩子：
  on_start → on_think_start → on_think_end → on_tool_end → on_finish
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .middleware import BaseMiddleware, RunContext, DynamicStageRoutingMiddleware, HookResult

logger = logging.getLogger(__name__)


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
    """追踪 ReAct 深度，防止无限循环（react_depth 由 ReActCoreMiddleware 递增）"""
    HOOKS = ("on_think_start", "on_tool_end")

    MAX_DEPTH = 10
    ADAPTIVE_MAX_DEPTH = 15

    async def on_think_start(self, ctx: RunContext) -> None:
        # 自适应深度：如果 plan_state 有创建且有进度，扩展到 15
        max_depth = self.MAX_DEPTH
        plan_state = getattr(ctx, "plan_state", None)
        if plan_state and plan_state.created:
            try:
                progress_str = plan_state.progress()
                if progress_str and "/" in progress_str:
                    done_part = progress_str.split("/")[0]
                    if int(done_part) > 0:
                        max_depth = self.ADAPTIVE_MAX_DEPTH
            except (ValueError, AttributeError):
                pass

        if ctx.react_depth > max_depth:
            ctx.interrupted = True
            ctx.last_error = f"ReAct 深度超过 {max_depth}，终止执行"
            logger.warning(f"ReAct 深度超过 {max_depth}，终止执行")
            return HookResult(jump_to="end", reason=f"ReAct 深度超过 {max_depth}")

    async def on_tool_end(self, ctx: RunContext) -> None:
        """检测连续失败的工具调用 + 工具重复检测 + 旋转检测"""
        if ctx.tool_results:
            last = ctx.tool_results[-1]
            tc = last.get("tool_call", {})
            name = tc.get("name", "")
            if name and not last.get("success"):
                ctx.consecutive_failures[name] = ctx.consecutive_failures.get(name, 0) + 1
            elif name:
                ctx.consecutive_failures[name] = 0

            # —— 工具调用重复检测 ——
            if len(ctx.tool_results) >= 3:
                recent = ctx.tool_results[-3:]
                names = [r.get("tool_call", {}).get("name", "") for r in recent]
                if len(set(names)) == 1 and names[0]:
                    args_sigs = []
                    for r in recent:
                        args = r.get("tool_call", {}).get("arguments", {})
                        sig = str(sorted(args.items())[:3]) if isinstance(args, dict) else str(args)[:100]
                        args_sigs.append(sig)
                    if len(set(args_sigs)) == 1:
                        logger.warning(f"工具重复检测: {names[0]} 连续调用 3 次参数一致")
                        return HookResult(jump_to="retry", reason=f"连续 3 次调用相同工具 {names[0]} 且参数完全一致，建议换策略")

            # —— 旋转检测（无进展轮次） ——
            if len(ctx.tool_results) >= 4:
                prev_two = ctx.tool_results[-4:-2]
                last_two = ctx.tool_results[-2:]
                if all(prev_two) and all(last_two):
                    prev_len = sum(len(str(r.get("result", ""))) for r in prev_two)
                    last_len = sum(len(str(r.get("result", ""))) for r in last_two)
                    prev_count = len(prev_two)
                    last_count = len(last_two)
                    if prev_len == last_len and prev_count == last_count:
                        logger.warning("旋转检测: 连续 2 轮无进展")
                        return HookResult(jump_to="retry", reason="旋转检测: 连续 2 轮无进展")


# ════════════════════════════════════════════════════════════════
# ConfidenceMiddleware — 置信度评估
# ════════════════════════════════════════════════════════════════

class ConfidenceMiddleware(BaseMiddleware):
    """基于工具调用成功率和结果质量计算置信度。低置信度 → 推决策信号"""
    HOOKS = ("on_tool_end",)

    # 工具类型权重映射
    TOOL_WEIGHTS = {
        "write_file": 0.9,
        "workspace_write_file": 0.9,
        "file": 0.9,
        "search": 0.7,
        "web_search": 0.7,
        "execute_python": 0.7,
        "python": 0.7,
        "fetch_url": 0.6,
        "curl": 0.6,
    }
    # 结果质量降权关键词
    QUALITY_DOWNGRADE_KEYWORDS = [
        "没有找到", "抱歉", "error", "404", "无法访问",
        "not found", "sorry", "failed", "timeout",
        "无结果", "未找到", "找不到",
    ]

    async def on_tool_end(self, ctx: RunContext) -> None:
        if not ctx.tool_results:
            return

        # 取最近 5 轮工具调用
        recent = ctx.tool_results[-5:]

        # 按工具类型分权重计算每轮分数
        weighted_scores = []
        for r in recent:
            tc = r.get("tool_call", {})
            name = tc.get("name", "")
            success = r.get("success", False)

            if not success:
                weighted_scores.append(0.0)
                continue

            # 基础权重
            base_weight = self.TOOL_WEIGHTS.get(name, 0.5)

            # 结果质量检测
            result_content = str(r.get("result", {})).lower()
            for kw in self.QUALITY_DOWNGRADE_KEYWORDS:
                if kw.lower() in result_content:
                    base_weight = max(0.1, base_weight * 0.5)
                    break

            # search 专用：空结果降权
            if name in ("search", "web_search") and success:
                res = r.get("result", {})
                if isinstance(res, dict):
                    items = res.get("result", {}).get("content", [])
                    if isinstance(items, list):
                        has_content = any(
                            c.get("text", "").strip()
                            for c in items if isinstance(c, dict)
                        )
                        if not has_content:
                            base_weight = 0.4

            weighted_scores.append(base_weight)

        # 累积置信度：最近 5 轮加权平均值
        if weighted_scores:
            rolling_confidence = sum(weighted_scores) / len(weighted_scores)
        else:
            rolling_confidence = 0.0

        # 多维度综合
        has_write_success = any(
            r.get("tool_call", {}).get("name", "") in ("file", "workspace_write_file", "write_file")
            and r.get("success")
            for r in recent
        )
        has_search_success = any(
            r.get("tool_call", {}).get("name", "") in ("search", "web_search")
            and r.get("success")
            for r in recent
        )

        if has_write_success and has_search_success:
            final_confidence = 0.95
        elif has_write_success:
            final_confidence = max(rolling_confidence, 0.8)
        elif has_search_success:
            final_confidence = min(rolling_confidence, 0.7)
        elif rolling_confidence < 0.3:
            final_confidence = 0.3
        else:
            final_confidence = rolling_confidence

        # 所有搜索均无具体结果降权
        all_search_empty = all(
            r.get("tool_call", {}).get("name", "") in ("search", "web_search") and r.get("success")
            for r in recent
        ) and has_search_success and rolling_confidence <= 0.4

        if all_search_empty:
            final_confidence = 0.4

        ctx.confidence_scores.append(final_confidence)
        ctx.confidence_total = sum(ctx.confidence_scores) / len(ctx.confidence_scores)

        if final_confidence < 0.5 and len(recent) >= 2 and not ctx.interrupted:
            logger.info(f"置信度{final_confidence:.1f}触发决策信号")
            return HookResult(jump_to="retry", reason=f"置信度过低({final_confidence:.1f})")


# ════════════════════════════════════════════════════════════════
# ReflectionMiddleware — 执行反思
# ════════════════════════════════════════════════════════════════

class ReflectionMiddleware(BaseMiddleware):
    """定期对执行结果进行反思。全部失败时推决策信号"""
    HOOKS = ("on_tool_end",)

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
            ctx.profile["reflection_feedback"] = True
            return HookResult(jump_to="retry", reason="全部工具调用失败，请换方法")

        # —— 方法耗尽检测 ——
        if len(ctx.tool_results) >= 3:
            last_3 = ctx.tool_results[-3:]
            names = list(set(r.get("tool_call", {}).get("name", "") for r in last_3))
            all_failed = all(not r.get("success") for r in last_3)
            if len(names) >= 2 and all_failed:
                logger.warning(f"方法耗尽检测: {names} 全部失败")
                return HookResult(jump_to="output", reason=f"方法耗尽：尝试了 {', '.join(names)} 均失败，建议输出当前已有结果")

        # —— 结构化反思输出 ——
        structured_reflection = {
            "iteration": ctx.iteration,
            "findings": f"最近{total}轮成功率{success}/{total}",
            "suggestion": "继续当前策略" if success > 0 else "全部失败，建议换方法或输出已有结果",
        }
        ctx.profile["structured_reflection"] = structured_reflection

        # —— 跨轮模式分析 ——
        if ctx.iteration >= 6:
            recent_6 = ctx.tool_results[-6:]
            fail_count = sum(1 for r in recent_6 if not r.get("success"))
            groups = [recent_6[i:i+2] for i in range(0, 6, 2)]
            all_groups_failed = all(
                sum(1 for r in g if not r.get("success")) >= 1
                for g in groups
            )
            if all_groups_failed and fail_count >= 3:
                logger.warning("跨轮模式: 连续 3 组失败率 > 50%，触发 abort")
                return HookResult(jump_to="end", reason=f"跨轮模式：连续 3 组失败率均 > 50%，建议终止避免无限重试")


# ════════════════════════════════════════════════════════════════
# SubtaskMiddleware — 子任务分解
# ════════════════════════════════════════════════════════════════
# ReflectionCheckMiddleware — 反思检查
# ════════════════════════════════════════════════════════════════

class ReflectionCheckMiddleware(BaseMiddleware):
    """把主循环里的两段硬编码反思逻辑塞进中间件链。

    on_think_start: 检测反思反馈 → 终止执行
    on_tool_end: 检查反思历史 → 注入换方法提示
    """
    HOOKS = ("on_think_start", "on_tool_end")

    async def on_think_start(self, ctx: RunContext) -> None:
        """反思反馈 → 终止"""
        if ctx.profile.get("reflection_feedback") and not ctx.final_answer:
            ctx.interrupted = True
            logger.warning("检测到反思反馈且无产出，提前终止空转")

    async def on_tool_end(self, ctx: RunContext) -> None:
        """反思历史 → 注入换方法提示"""
        if ctx.reflection_history and not ctx.final_answer:
            last_ref = ctx.reflection_history[-1]
            if last_ref.get("success_rate", 1) == 0 and last_ref.get("total_calls", 0) > 0:
                if not ctx.task_description.endswith("[反思]"):
                    ctx.task_description += "\n[反思] 上一轮全部失败，请换一种方法（换工具或直接回答）。"
                    logger.info("已注入反思提示到下一轮")


# ════════════════════════════════════════════════════════════════

class SubtaskMiddleware(BaseMiddleware):
    """处理复杂任务的子任务分解和追踪"""
    HOOKS = ("on_think_start",)

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
    """根据执行状态决定是否终止或重试（推决策信号）

    多维度终止条件：
    - 空转检测：连续 3 轮 react_depth 不变 + tool_results 不变
    - 相同错误重复：最后 3 个 tool_results 全部失败且 error 含相同关键词
    - LLM 卡住：最后 2 轮 LLM 回复内容相同且不调工具
    - 兜底：final_answer 已设置但 interrupted 没设 → 推 end
    """
    HOOKS = ("on_think_end",)

    async def on_think_end(self, ctx: RunContext) -> None:
        if not ctx.last_error:
            ctx.profile["branch_hint_added"] = False

        # —— 空转检测：连续 3 轮 react_depth 不变 + tool_results 没变 ——
        if len(ctx.tool_results) >= 3:
            last_3 = ctx.tool_results[-3:]
            names_depths = set()
            for i, r in enumerate(last_3):
                tc = r.get("tool_call", {})
                name = tc.get("name", "")
                depth = ctx.react_depth - (2 - i) if ctx.react_depth >= (2 - i) else 0
                names_depths.add(f"{name}@{depth}")
            if len(names_depths) == 1:
                result_sigs = set(str(r.get("result", ""))[:200] for r in last_3)
                if len(result_sigs) == 1:
                    logger.warning("空转检测触发")
                    return HookResult(jump_to="end", reason=f"空转检测：连续 3 轮工具({last_3[-1].get('tool_call',{}).get('name','?')})结果无变化")

        # —— 相同错误重复 ——
        if len(ctx.tool_results) >= 3:
            last_3 = ctx.tool_results[-3:]
            all_failed = all(not r.get("success") for r in last_3)
            if all_failed:
                common_kw = None
                for r in last_3:
                    err = (r.get("error", "") or str(r.get("result", ""))).lower()
                    for kw in ["timeout", "denied", "not found", "不存在", "权限", "refused"]:
                        if kw in err:
                            common_kw = kw
                            break
                if common_kw:
                    logger.warning(f"相同错误重复: {common_kw}")
                    return HookResult(jump_to="end", reason=f"相同错误重复：最后 3 个工具均失败且均包含关键词 '{common_kw}'")

        # —— 兜底：final_answer 已设置但 interrupted 没设 ——
        if ctx.final_answer and not ctx.interrupted:
            return HookResult(jump_to="end", reason=f"final_answer 已设置({ctx.final_answer[:60]}...)，标记结束")

        # —— 连续失败 abort（原有逻辑增强） ——
        consecutive_fails = sum(1 for r in ctx.tool_results[-3:] if not r.get("success"))
        if consecutive_fails >= 3 and not ctx.profile.get("branch_hint_added"):
            logger.warning("连续 3 次失败，推终止信号")
            ctx.profile["branch_hint_added"] = True
            return HookResult(jump_to="end", reason=f"连续{consecutive_fails}次失败，终止当前策略")


# ════════════════════════════════════════════════════════════════
# KEPAMiddleware — KEPA 闭环
# ════════════════════════════════════════════════════════════════

class KEPAMiddleware(BaseMiddleware):
    """实现真正的 KEPA 四阶段（Knowledge / Evaluation / Planning / Action）

    规则型实现，不调 LLM：
    - Knowledge: 从 tool_results 提取数据摘要
    - Evaluation: 判断数据是否充分
    - Planning: 生成下一步建议
    - Action: 将 plan 注入到 ctx.task_description
    """
    HOOKS = ("on_tool_end", "on_finish")

    async def on_tool_end(self, ctx: RunContext) -> None:
        if ctx.tool_results:
            last = ctx.tool_results[-1]
            state = "success" if last.get("success") else "failed"
            ctx.kepa_states.append(state)

            # —— KEPA 四阶段闭环（每次工具调用后执行）——
            # 1. Knowledge: 数据摘要
            successful_tools = []
            total_data_length = 0
            for r in ctx.tool_results:
                if r.get("success"):
                    tc = r.get("tool_call", {})
                    name = tc.get("name", "")
                    result_len = len(str(r.get("result", "")))
                    successful_tools.append(f"{name}({result_len}chars)")
                    total_data_length += result_len

            knowledge_summary = f"成功工具: {', '.join(successful_tools)}" if successful_tools else "无成功工具调用"
            knowledge_summary += f" | 总数据量: {total_data_length}字符"

            # 2. Evaluation: 数据充分性判断
            has_successful_search = any(
                r.get("tool_call", {}).get("name", "") in ("search", "web_search")
                and r.get("success")
                for r in ctx.tool_results
            )
            has_file_read = any(
                r.get("tool_call", {}).get("name", "") == "file"
                and r.get("tool_call", {}).get("arguments", {}).get("action") == "read"
                and r.get("success")
                for r in ctx.tool_results if r.get("tool_call", {})
            )
            all_failed = all(not r.get("success") for r in ctx.tool_results) if ctx.tool_results else True

            if has_successful_search or has_file_read:
                evaluation = "数据充分"
            elif all_failed:
                evaluation = "全部失败"
            else:
                evaluation = "数据不充分"

            # 3. Planning: 生成建议
            if evaluation == "全部失败":
                plan_suggestion = "建议总结已有结果或换工具"
            elif evaluation == "数据不充分":
                plan_suggestion = "建议换工具或直接输出当前结果"
            else:
                plan_suggestion = "继续当前策略"

            # 4. Action: 注入到 task_description（避免重复注入）
            kepa_inject = f"\n[KEPA] 数据状态: {knowledge_summary} | 评估: {evaluation} | 建议: {plan_suggestion}"
            if "[KEPA]" not in ctx.task_description:
                ctx.task_description += kepa_inject
                logger.debug(f"KEPA注入: {kepa_inject[:80]}...")

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
    """在关键决策点注入提示给 LLM（非阻塞，不实际询问用户）

    所有注入提示格式为 "\\n[用户确认] XXX"，前缀标记方便后续调试。
    超时自动跳过：本身不做 input() 阻塞，只注入提示让 LLM 自行决定。
    """
    HOOKS = ("on_think_start", "on_think_end", "on_tool_end", "on_wrap_tool_call")

    DESTRUCTIVE_KEYWORDS = ["rm ", "del ", "remove ", "drop ", "truncate "]

    async def on_think_start(self, ctx: RunContext) -> None:
        """在 LLM 思考前注入提示（占位检测 + 破坏性操作检测）"""
        # —— 文件写入确认 ——
        current_tool = self._detect_current_tool(ctx)
        if current_tool:
            name = current_tool.get("name", "")
            args = current_tool.get("arguments", {})
            if name in ("file", "workspace_write_file", "write_file"):
                path = args.get("path", "") if isinstance(args, dict) else ""
                if "Desktop" in path or "/Users/" in path:
                    inject = f"\n[用户确认] 即将写入文件: {path}，请确保内容完整正确"
                    if "用户确认" not in ctx.task_description:
                        ctx.task_description += inject

            # —— 破坏性操作检测 ——
            name = current_tool.get("name", "")
            args = current_tool.get("arguments", {})
            full_cmd = ""
            if name in ("execute_shell", "bash"):
                full_cmd = args.get("command", "") if isinstance(args, dict) else ""
            elif name == "file":
                full_cmd = args.get("content", "") if isinstance(args, dict) else ""
            elif name == "call_api":
                full_cmd = args.get("url", "") if isinstance(args, dict) else ""

            destructive_kw = self._find_destructive_keywords(full_cmd.lower())
            if destructive_kw:
                inject = f"\n[用户确认] 检测到可能具有破坏性的操作: '{destructive_kw[0]}'，请谨慎执行"
                if "用户确认" not in ctx.task_description:
                    ctx.task_description += inject

    def _detect_current_tool(self, ctx: RunContext) -> Optional[Dict]:
        """检测 LLM 当前准备调用的工具

        在 on_think_start 阶段无法直接获取 LLM 即将调用的工具（LLM 尚未思考）。
        此处返回 None 作为占位；实际拦截由 on_wrap_tool_call 完成。
        """
        return None

    def _find_destructive_keywords(self, text: str) -> List[str]:
        """查找破坏性关键词"""
        found = []
        for kw in self.DESTRUCTIVE_KEYWORDS:
            if kw in text:
                found.append(kw.strip())
        return found

    async def on_wrap_tool_call(self, ctx: RunContext, next_mw: Callable) -> Any:
        """包裹工具调用：在工具执行前做安全检测"""
        # 获取当前要调用的工具参数
        import inspect
        frame = inspect.currentframe()
        tool_args = {}
        if frame and frame.f_back and frame.f_back.f_locals:
            tool_args = frame.f_back.f_locals.get("tool_args", {})

        name = tool_args.get("name", "") if isinstance(tool_args, dict) else ""
        arguments = tool_args.get("arguments", {}) if isinstance(tool_args, dict) else {}

        # —— 文件写入确认（洋葱层内，真正执行前） ——
        if name in ("file", "workspace_write_file", "write_file"):
            path = arguments.get("path", "") if isinstance(arguments, dict) else ""
            if "Desktop" in path or "/Users/" in path:
                inject = f"\n[用户确认] 即将写入文件: {path}，请确保内容完整正确"
                if "用户确认" not in ctx.task_description:
                    ctx.task_description += inject
                    logger.info(f"写文件检测: {path}")

        # —— 破坏性操作检测 ——
        if name in ("execute_shell", "bash"):
            cmd = arguments.get("command", "") if isinstance(arguments, dict) else ""
            destructive_kw = self._find_destructive_keywords(cmd.lower())
            if destructive_kw:
                inject = f"\n[用户确认] 检测到可能具有破坏性的 shell 操作: '{destructive_kw[0]}'，请谨慎执行"
                if "用户确认" not in ctx.task_description:
                    ctx.task_description += inject
                    logger.warning(f"破坏性操作检测: {destructive_kw[0]}")

        return await next_mw()

    async def on_think_end(self, ctx: RunContext) -> None:
        """首轮简单回答时确认 + 任务模糊检测"""
        if ctx.iteration != 1:
            return
        if ctx.tool_results:
            return  # 已有工具调用，说明 LLM 有实际行动，不需要确认

        # —— 任务模糊检测 ——
        if len(ctx.task_description) < 30:
            inject = "\n[用户确认] 这是个非常简短的任务，如果任务描述不够明确，请在回答中先确认需求再行动"
            ctx.task_description += inject

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
    - 按工具类型提取不同字段
    - 多步上下文累积
    """
    HOOKS = ("on_think_start",)

    MAX_DATA_LENGTH = 1500

    async def on_think_start(self, ctx: RunContext) -> None:
        """在 LLM 思考前，将上一步工具结果格式化为提示词上下文"""
        if not ctx.tool_results:
            return

        # —— 多步上下文累积（最近 3 步）——
        recent_results = ctx.tool_results[-3:]
        pipeline_parts = []

        for result in recent_results:
            if not result.get("success"):
                continue

            tc = result.get("tool_call", {})
            name = tc.get("name", "")
            if not name:
                continue

            # 按工具类型提取
            extracted = self._extract_by_tool_type(name, result)
            if extracted and len(extracted) > 10:
                pipeline_parts.append(f"[{name}] {extracted}")

        if not pipeline_parts:
            return

        # 注入格式
        pipeline_block = "\n\n[数据流水线]\n" + "\n---\n".join(pipeline_parts) + "\n"

        # 上一步关键输出
        latest_obs = ctx.get_latest_observation()
        if latest_obs and len(latest_obs) > 10:
            pipeline_block += f"上一步关键输出: {latest_obs}\n"

        ctx.task_description += pipeline_block

    def _extract_by_tool_type(self, name: str, result: Dict) -> str:
        """按工具类型提取内容摘要"""
        try:
            if name in ("search", "web_search"):
                res = result.get("result", {})
                if isinstance(res, dict):
                    content = res.get("result", {}).get("content", [])
                    if isinstance(content, list):
                        texts = []
                        for c in content:
                            if isinstance(c, dict):
                                txt = c.get("text", "")
                                if txt:
                                    texts.append(txt)
                        raw = "\n".join(texts)
                    elif isinstance(content, str):
                        raw = content
                    else:
                        raw = str(res)[:500]
                else:
                    raw = str(result.get("result", ""))[:500]
                return self._truncate_by_paragraph(raw, self.MAX_DATA_LENGTH)

            elif name == "file":
                args = result.get("tool_call", {}).get("arguments", {})
                action = args.get("action", "") if isinstance(args, dict) else ""
                if action == "read" and result.get("success"):
                    raw = str(result.get("result", ""))
                    return self._truncate_by_paragraph(raw, 300)
                return ""

            elif name in ("execute_python", "python"):
                res = result.get("result", {})
                if isinstance(res, dict):
                    stdout = res.get("result", {}).get("stdout", "")
                    stderr = res.get("result", {}).get("stderr", "")
                    parts = []
                    if stdout:
                        parts.append(f"stdout({len(stdout)}chars): {self._truncate_by_line(stdout, 5)}")
                    if stderr:
                        parts.append(f"stderr({len(stderr)}chars): {self._truncate_by_line(stderr, 3)}")
                    return " | ".join(parts)
                return str(res)[:500]

            elif name == "fetch_url":
                res = result.get("result", {})
                if isinstance(res, dict):
                    text = res.get("result", {}).get("text", "") or str(res)[:500]
                else:
                    text = str(res)[:500]
                return self._truncate_by_paragraph(text, 500)

            elif name in ("execute_shell", "bash"):
                res = result.get("result", {})
                if isinstance(res, dict):
                    output = res.get("result", {}).get("output", "") or str(res)[:500]
                else:
                    output = str(res)[:500]
                return self._truncate_by_line(output, 10)

            else:
                raw = str(result.get("result", ""))[:500]
                if len(raw) > 10:
                    return raw[:200]
                return ""
        except Exception:
            return ""

    def _truncate_by_paragraph(self, text: str, max_chars: int) -> str:
        """按段落截断，保留完整段落"""
        if len(text) <= max_chars:
            return text
        paragraphs = text.split("\n\n")
        result = []
        total = 0
        for p in paragraphs:
            if total + len(p) <= max_chars:
                result.append(p)
                total += len(p) + 2
            else:
                if not result:
                    sentences = p.split("。")
                    for s in sentences:
                        if total + len(s) <= max_chars:
                            result.append(s)
                            total += len(s) + 1
                        else:
                            break
                    result.append("...")
                else:
                    result.append("...")
                break
        return "\n\n".join(result)

    def _truncate_by_line(self, text: str, max_lines: int) -> str:
        """按行截断，保留完整行"""
        lines = text.split("\n")
        if len(lines) <= max_lines:
            return text
        result = "\n".join(lines[:max_lines])
        result += f"\n... 截断 ({len(lines) - max_lines} 行)"
        return result

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


# ═══════════════════════════════════════════════════════════════════
# ToolCorrectionMiddleware — 工具选错纠正
# ═══════════════════════════════════════════════════════════════════

class ToolCorrectionMiddleware(BaseMiddleware):
    """工具选择纠错中间件

    检测 LLM 选错工具的场景，注入换工具建议。
    区分三种情况：
    - 空结果：工具本身正确但结果为空（如搜索无结果）→ 建议换关键词或改搜索源
    - 持续空结果：同一工具多次返回空 → 建议完全换工具类型
    - 错误或空转：工具返回错误/无实际内容 → 建议换策略

    与 ReActDepthMiddleware 的区别：
    - ReActDepth 检测的是"连续相同工具+相同参数"的重复调用
    - 本中间件检测的是"工具返回空/无意义结果"的无效选择
    """
    HOOKS = ("on_tool_end", "on_think_start")

    # 空结果检测特征集（结果文本中出现以下内容 = 工具可能选错了）
    EMPTY_RESULT_PATTERNS = [
        "没有找到", "未找到", "找不到", "无结果", "暂无", "暂时没有",
        "not found", "no results", "no result", "nothing found",
        "返回为空", "搜索结果为空",
        "请求失败", "failed",
    ]

    # 空结果工具计数器（记录每个工具连续返回空结果的次数）
    # key = tool_name, value = {
    #   "empty_count": 连续空结果次数,
    #   "total_calls": 总共被调次数,
    #   "empty_results": [摘要],  # 最近空结果摘要
    # }

    async def on_tool_end(self, ctx: RunContext) -> None:
        """检测工具返回空结果 → 计数 + 触发换工具提示"""
        if not ctx.tool_results:
            return

        last = ctx.tool_results[-1]
        tc = last.get("tool_call", {})
        name = tc.get("name", "")
        if not name:
            return

        if not last.get("success"):
            return  # 失败由其他中间件处理

        result_str = str(last.get("result", {}))
        is_empty = self._is_empty_result(result_str)

        # 初始化工具空结果追踪器
        if not hasattr(ctx, "_tool_empty_tracker"):
            ctx._tool_empty_tracker = {}
        tracker = ctx._tool_empty_tracker

        if name not in tracker:
            tracker[name] = {"empty_count": 0, "total_calls": 0, "empty_results": []}
        tracker[name]["total_calls"] += 1

        if is_empty:
            tracker[name]["empty_count"] += 1
            # 保留最近 3 条空结果摘要
            summary = result_str[:100].replace("\n", " ")
            tracker[name]["empty_results"].append(summary)
            tracker[name]["empty_results"] = tracker[name]["empty_results"][-3:]

            logger.info(f"工具 [{name}] 返回空结果 (连续{tracker[name]['empty_count']}次)")

            # —— 检测策略 A：同一工具连续 2 次返回空 → 可能是工具选错了 ——
            if tracker[name]["empty_count"] >= 2:
                # 检查 LLM 是否已经得到过提示
                if "[换工具]" not in ctx.task_description:
                    ctx.task_description += (
                        f"\n[换工具] 工具「{name}」连续 2 次返回空结果，"
                        "说明这个工具不适合当前任务。请换一个不同类型的工具，"
                        "或者直接基于已有信息回答问题。不要重复调同一个工具。"
                    )
                    logger.info(f"工具 [{name}] 连续空结果，已注入换工具提示")
            elif tracker[name]["empty_count"] >= 1:
                # 首次空结果：温和提醒
                pass  # LLM 自己可能意识到，先不动
        else:
            # 工具返回了有效结果 → 重置计数器
            tracker[name]["empty_count"] = 0
            tracker[name]["empty_results"] = []

    async def on_think_start(self, ctx: RunContext) -> None:
        """检测工具选择模式：多种工具都返回空 → 全局换策略"""
        tracker = getattr(ctx, "_tool_empty_tracker", None)
        if not tracker:
            return

        # 统计有多少工具空转
        empty_tools = {n: d for n, d in tracker.items() if d["empty_count"] >= 2}
        if len(empty_tools) >= 2:
            # 超过 2 种不同工具都返回空 → 可能是方向性问题
            tool_list = ", ".join(empty_tools.keys())
            if "[全局换策略]" not in ctx.task_description:
                ctx.task_description += (
                    f"\n[全局换策略] 多个工具（{tool_list}）都返回空结果，"
                    "当前搜索/查询方向可能有问题。请换个思路："
                    "1) 换搜索引擎或换关键词  "
                    "2) 直接基于已有信息回答  "
                    "3) 如果任务是获取最新信息，换个完全不同的角度"
                )
                logger.info(f"多工具空转检测: {tool_list} → 已注入全局换策略提示")

        # 检查是否有工具本来有结果、后来变空了（退化检测）
        for name, d in tracker.items():
            if d["total_calls"] >= 3 and d["empty_count"] >= 1:
                ratio = d["empty_count"] / d["total_calls"]
                if ratio > 0.6:
                    logger.info(f"工具 [{name}] 退化检测: 空结果率 {ratio:.0%}")

    @staticmethod
    def _is_empty_result(result_str: str) -> bool:
        """判断工具结果是否为空/无意义"""
        if not result_str or result_str == "{}" or result_str == '{"content": [{"text": ""}]}':
            return True

        result_lower = result_str.lower()

        # 检测空结果关键词
        for pattern in ToolCorrectionMiddleware.EMPTY_RESULT_PATTERNS:
            if pattern in result_lower:
                return True

        # 搜索结果的特殊检测：content 数组全空
        import re
        # 匹配 content: [{"text": ""}] 或 {'text': ''} 风格（JSON/Python dict 双兼容）
        has_content_key = re.search(r'["\']content["\']\s*:\s*\[', result_lower)
        if has_content_key:
            # 提取所有 text 字段的值
            texts = re.findall(r'["\']text["\']\s*:\s*["\']([^"\']*)["\']', result_lower)
            if texts and all(t.strip() == "" for t in texts):
                return True

        return False
