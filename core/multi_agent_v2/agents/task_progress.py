"""TaskProgress — 统一 Plan-Execution 进度追踪

用「能力」(Capability) 替代工具名等价组来追踪 LLM 实际完成的工作。
每轮扫描 tool_results，检测新达成的能力，反向匹配 plan step，推进进度。

ponytail: replaces update_step_status deadlock breaker + tool equivalence groups
"""

import asyncio
import fnmatch
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .middleware import PlanStep, RunContext

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# Capability — LLM 实际产出的「能力」
# ════════════════════════════════════════════════════════════════

@dataclass
class Capability:
    kind: str               # "web_search" | "url_fetched" | "file_written" | "code_executed"
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Capability({self.kind}, {self.metadata})"


# ── 能力检测器：工具结果 → 可选能力 ──

def _detect_from_result(r: Dict[str, Any]) -> List[Capability]:
    """从一个 tool_result 中提取所有达成的新能力"""
    tc = r.get("tool_call", {})
    name = tc.get("name", "")
    if not name:
        return []

    # ponytail: execute_shell/execute_python failures often just mean command
    # was truncated. The LLM tried — count it as tool_called.
    is_shell_fail = name in ("execute_shell", "execute_python") and not r.get("success")
    if not r.get("success") and not is_shell_fail:
        return []

    args = tc.get("arguments", {}) or {}
    caps = []
    result_text = str(r.get("result", ""))

    if is_shell_fail:
        caps.append(Capability(kind="code_executed", metadata={
            "code_snippet": str(args.get("command", args.get("code", "")))[:200],
            "failed": True,
        }))
        return caps

    # 搜索类
    if name in ("web_search", "fetch_url", "fetch_json", "hot_search"):
        query = args.get("query", args.get("url", ""))
        caps.append(Capability(kind="web_search", metadata={
            "query": query,
            "result_len": len(result_text),
        }))
        if name == "fetch_url" and len(result_text) > 500:
            caps.append(Capability(kind="url_fetched", metadata={
                "url": args.get("url", ""),
                "size_bytes": len(result_text),
            }))

    # 文件写入
    if name == "write_file":
        path = args.get("path", args.get("filepath", ""))
        content = str(args.get("content", ""))
        caps.append(Capability(kind="file_written", metadata={
            "path": path,
            "size_bytes": len(content),
            "has_html": "<html" in content.lower() or "<!doctype" in content.lower(),
        }))

    # 文件编辑
    if name == "edit_file":
        path = args.get("path", "")
        caps.append(Capability(kind="file_written", metadata={
            "path": path,
            "size_bytes": 0,
            "edit": True,
        }))

    # 代码执行
    if name == "execute_python":
        code = args.get("code", "")
        caps.append(Capability(kind="code_executed", metadata={
            "code_snippet": code[:200],
            "stdout_len": len(result_text) if result_text != "None" else 0,
            "has_html_parse": "BeautifulSoup" in code or "lxml" in code or "html.parser" in code,
        }))
        # ponytail: execute_python 写文件 → 也产生 file_written（agent 可能用代码写交付物）
        _writes = any(p in code for p in ("write_text", "write_bytes", "to_file", "savefig")) or (
            "open(" in code and (".write(" in code or "writelines" in code)
        )
        if _writes:
            caps.append(Capability(kind="file_written", metadata={
                "path": "", "via": "execute_python",
                "size_bytes": 0,
            }))

    # Shell 执行
    if name == "execute_shell":
        command = args.get("command", args.get("cmd", ""))
        caps.append(Capability(kind="code_executed", metadata={
            "code_snippet": command[:200],
            "stdout_len": len(result_text) if result_text != "None" else 0,
        }))
        # ponytail: execute_shell 写文件（echo/cat/tee > file）→ 也产生 file_written
        _shell_writes = any(p in command for p in ("cat > ", "echo ", "tee ", "> ", ">> ")) and (
            any(p in command for p in (".py", ".html", ".js", ".css", ".json", ".md", ".txt", ".html"))
        )
        if _shell_writes:
            caps.append(Capability(kind="file_written", metadata={
                "path": "", "via": "execute_shell",
                "size_bytes": 0,
            }))

    # 文件读取
    if name == "read_file":
        path = args.get("path", args.get("filepath", ""))
        caps.append(Capability(kind="file_read", metadata={
            "path": path,
            "size_bytes": len(result_text),
        }))

    # text_analyzer, codegraph_explore, search_files — 分析类工具
    if name in ("text_analyzer", "codegraph_explore", "codegraph_search", "search_files", "codegraph_files"):
        caps.append(Capability(kind="tool_called", metadata={"tool": name}))

    # ponytail: task/orchestrate 子代理是真产出（真实测试：3 个 task 分析子代理成功
    # 但 Step2"深入分析"不推进 — tool_called 不是 productive。子代理输出算实质分析产出）
    if name in ("task", "orchestrate"):
        caps.append(Capability(kind="subagent_output", metadata={
            "tool": name,
            "result_len": len(result_text),
        }))

    # ponytail: 兜底 — 任何成功调用的工具至少产生 tool_called
    if not caps:
        caps.append(Capability(kind="tool_called", metadata={"tool": name}))

    return caps


# ════════════════════════════════════════════════════════════════
# TaskProgress
# ════════════════════════════════════════════════════════════════

class TaskProgress:
    def __init__(self, ctx: RunContext):
        self._ctx = ctx
        self.completed_capabilities: List[Capability] = []
        self.new_capabilities_this_round: List[Capability] = []
        self.stuck_counter: int = 0

    def update(self) -> None:
        self.new_capabilities_this_round = []
        if not self._ctx.plan:
            return

        _snapshot = getattr(self._ctx, '_progress_tool_snapshot', 0)
        _current = len(self._ctx.tool_results)

        if _current > _snapshot:
            new_results = self._ctx.tool_results[_snapshot:]
            self._ctx._progress_tool_snapshot = _current
            for r in new_results:
                caps = _detect_from_result(r)
                for cap in caps:
                    # ponytail: 失败的能力不入 completed（失败≠达成）—
                    # 否则历史成功 code_executed 会让 postcondition 匹配放行失败轮的推进
                    if cap.metadata.get("failed"):
                        continue
                    if not self._has_capability(cap):
                        self.completed_capabilities.append(cap)
                        self.new_capabilities_this_round.append(cap)

        _pending_before = next((s.index for s in self._ctx.plan if s.status == "pending"), None)
        self._match_steps()
        _pending_after = next((s.index for s in self._ctx.plan if s.status == "pending"), None)

        if _pending_after is None:
            self.stuck_counter = 0
        elif _pending_after == _pending_before:
            self.stuck_counter += 1
        else:
            self.stuck_counter = 0


    def _new_capability_helps_current_step(self) -> bool:
        """检查本轮新能力是否对当前待执行步骤有帮助"""
        if not self.new_capabilities_this_round or not self._ctx.plan:
            return False
        _step = next((s for s in self._ctx.plan if s.status == "pending"), None)
        if not _step or not _step.postconditions:
            return bool(self.new_capabilities_this_round)  # warmup: any capability helps
        for cap in self.new_capabilities_this_round:
            for cond in _step.postconditions:
                # bare condition match
                if cond.startswith(f"capability:{cap.kind}"):
                    return True
                # ponytail: legacy tool_called: 格式也走能力匹配
                if cond.startswith("tool_called:") and cap.kind == "tool_called":
                    if cap.metadata.get("tool") == cond[12:]:
                        return True
        return False

    def _has_capability(self, cap: Capability) -> bool:
        for existing in self.completed_capabilities:
            if existing.kind == cap.kind and existing.metadata == cap.metadata:
                return True
        return False

    def _match_cap(self, condition: str) -> bool:
        """匹配单个 postcondition (capability: 格式) 是否已被满足"""
        if not condition.startswith("capability:"):
            return self._match_legacy(condition)

        spec = condition[11:]  # "web_search" or "web_search(query=xxx)"
        m = re.match(r'(\w+)\((.*)\)', spec)
        if m:
            kind = m.group(1)
            params_str = m.group(2)
        else:
            # bare condition: match by kind only
            kind = spec.strip()
            for cap in self.completed_capabilities:
                if cap.kind == kind:
                    return True
            return False

        expected: Dict[str, str] = {}
        for pair in _split_params(params_str):
            if "=" in pair:
                k, v = pair.split("=", 1)
                expected[k.strip()] = v.strip()
            elif ">" in pair:
                k, v = pair.split(">", 1)
                expected[k.strip() + "_gt"] = v.strip()

        for cap in self.completed_capabilities:
            if cap.kind != kind:
                continue
            if self._metadata_matches(cap.metadata, expected):
                return True
        return False

    def _metadata_matches(self, actual: Dict, expected: Dict) -> bool:
        for key, val in expected.items():
            if key.endswith("_gt"):
                real_key = key[:-3]
                actual_val = actual.get(real_key)
                if actual_val is None:
                    return False
                try:
                    if not (actual_val > int(val)):
                        return False
                except (TypeError, ValueError):
                    return False
            else:
                actual_val = actual.get(key)
                if actual_val is None:
                    return False
                # glob matching for paths
                if "*" in val or "?" in val:
                    if not fnmatch.fnmatch(str(actual_val), val):
                        return False
                else:
                    # ponytail: normalize paths (~ vs /Users/...)
                    _norm_actual = os.path.expanduser(str(actual_val))
                    _norm_expected = os.path.expanduser(val)
                    if _norm_actual != _norm_expected:
                        return False
        return True

    def _match_legacy(self, condition: str) -> bool:
        """兼容旧 postconditions (file_exists: / tool_called:)"""
        if condition.startswith("file_exists:"):
            path = os.path.expanduser(condition[12:])
            return os.path.exists(path)
        if condition.startswith("tool_called:"):
            required = condition[12:]
            for r in self._ctx.tool_results:
                if r.get("tool_call", {}).get("name") == required and r.get("success"):
                    return True
            for cap in self.completed_capabilities:
                if cap.kind == "tool_called" and cap.metadata.get("tool") == required:
                    return True
            # ponytail: 智能降级 — LLM 不调所需工具但调了等价工具时，用能力替代
            _tool_to_cap = {
                "read_file": "file_read", "write_file": "file_written",
                "edit_file": "file_written", "web_search": "web_search",
                "fetch_url": "web_search", "hot_search": "web_search",
                "execute_python": "code_executed", "execute_shell": "code_executed",
                "codegraph_explore": "file_read",    # 项目探索 ≈ 读文件
                "codegraph_search": "file_read",
                "codegraph_files": "file_read",
                "search_files": "file_read",
            }
            if required in _tool_to_cap:
                for cap in self.completed_capabilities:
                    if cap.kind == _tool_to_cap[required]:
                        return True
            return False
        return False

    def _match_steps(self) -> None:
        """匹配计划步骤 — 有实质产出就推进，每轮最多一步"""
        if not self._ctx.plan:
            return

        # ponytail: 失败的工具调用不产生推进资格（真实测试：execute_shell 失败仍推进了 Step1）
        _productive_new = [
            c for c in self.new_capabilities_this_round if not c.metadata.get("failed")
        ]
        _can_advance = bool(_productive_new) or (
            self.stuck_counter >= 2 and self.completed_capabilities
        )

        for step in self._ctx.plan:
            if step.status != "pending":
                continue

            if step.postconditions:
                # ponytail: 工具级条件（无参数）= 可选工具集，任一达成即完成（OR）；
                # 含精确条件（如 file_written(path=...)）= 硬性交付要求，全部满足（AND）。
                # 修复真实测试 bug：Step1 绑定 [execute_shell, read_file] 推断出两个条件，
                # agent 只调 read_file → AND 语义下永远卡住（Plan 显示 0/2 失真）
                _tool_level = all(c in (
                    "capability:file_written", "capability:web_search",
                    "capability:code_executed", "capability:file_read",
                ) for c in step.postconditions)
                if _tool_level:
                    matched = any(self._match_cap(c) for c in step.postconditions)
                else:
                    matched = True
                    for cond in step.postconditions:
                        if not self._match_cap(cond):
                            matched = False
                            break
                        if cond.startswith("capability:file_written(path="):
                            _path = cond[len("capability:file_written(path="):].rstrip(")")
                            if not os.path.exists(os.path.expanduser(_path)):
                                matched = False
                                self._ctx.forced_instructions = (
                                    f"⚠️ 文件 {_path} 不存在，请 write_file！"
                                )
                                break
                if not matched and self.stuck_counter >= 2 and self.completed_capabilities:
                    matched = True
                if matched:
                    step.status = "done"
                    # ponytail: 记录推进轮号 — stall guard 用轮差判据（空转轮 on_tool_end
                    # 不触发，stuck 冻结；轮差在主循环每轮检查，无法被假活动规避）
                    self._ctx._last_step_progress_round = getattr(self._ctx, 'react_depth', 0)
                break

            # 新格式：有资格就推进
            if _can_advance:
                # ponytail: 产出型步骤需产出型能力才能推进 —
                # 探索能力（ls/read_file 产生的 code_executed/file_read/tool_called）
                # 不得推进"写/生成/报告/清洗/分析"类步骤（真实测试：ls Desktop 连推 Step2/Step3）
                _step_desc = step.description or ""
                _is_output_step = any(kw in _step_desc for kw in (
                    "写", "生成", "报告", "保存", "输出", "创建", "清洗", "处理", "分析", "统计",
                    "write", "create", "report", "save", "output", "analyze", "process",
                ))
                if _is_output_step:
                    # ponytail: 浏览类命令（ls/find/cat/wc/du/df/head/tail/echo）输出再大也只是浏览，
                    # 不得推进"写/生成/报告/清洗/分析"步骤（真实测试：ls -la 桌面输出大被当 productive）
                    _exec_cmd = ""
                    for _nc in self.new_capabilities_this_round:
                        if _nc.kind == "code_executed":
                            _exec_cmd = _nc.metadata.get("code_snippet", "") or ""
                            break
                    _browse_cmd = _exec_cmd.strip().split(maxsplit=1)[0].lower() if _exec_cmd else ""
                    _is_browse = _browse_cmd in {
                        "ls", "find", "cat", "head", "tail", "wc", "du", "df", "echo", "pwd", "tree",
                    }
                    _productive = any(
                        (c.kind in ("file_written", "web_search", "url_fetched", "subagent_output")
                         or (c.kind == "code_executed" and (c.metadata.get("stdout_len") or 0) > 500))
                        and not c.metadata.get("failed")
                        for c in self.new_capabilities_this_round
                        if not _is_browse or c is not _nc  # 浏览命令的 code_executed 不算 productive
                    )
                    if not _productive:
                        break  # 本轮只有浏览能力 → 不推进产出型步骤

                # 最后一步需有实质产出才推进（仅产出型步骤用严格标准；探索型步骤任何能力即可）
                _is_last = step.index == len(self._ctx.plan)
                if _is_last and _is_output_step:
                    _has_substance = any(
                        c.kind in ("file_written", "subagent_output")
                        or (c.kind == "code_executed" and (c.metadata.get("stdout_len") or 0) > 500)
                        for c in self.completed_capabilities
                    ) or getattr(self._ctx, 'final_answer', None)
                    if not _has_substance:
                        break  # 没有实质产出，不推进最后一步

                step.status = "done"
                self._ctx._last_step_progress_round = getattr(self._ctx, 'react_depth', 0)
                _pending = [s for s in self._ctx.plan if s.status == "pending"]
                if _pending and not self._ctx.forced_instructions:
                    # 过程信号：告诉 LLM 上一步已完成，给出下一步方向
                    _remaining = len(_pending)
                    _hint = ""
                    if _remaining == 1:
                        _hint = "这是最后一步，检查已有数据是否够直接输出"
                    elif _remaining <= 2:
                        _hint = f"还剩{_remaining}步，已有数据足够的话尽量跳过中间步骤直接产出"
                    self._ctx.forced_instructions = (
                        f"✅ 上一步已完成。{_hint}下一步：{_pending[0].description}。立即执行，不要输出解释文本。"
                    )
            break

    async def adaptive_replan(self) -> bool:
        """当 stuck 时调用 LLM 重新规划剩余步骤。返回 True 表示已重规划。"""
        if not self._ctx.plan:
            return False
        pending = [s for s in self._ctx.plan if s.status == "pending"]
        if not pending:
            return False

        cap_summary = ", ".join(
            f"{c.kind}" for c in self.completed_capabilities[-6:]
        )
        stuck_step = pending[0]
        stuck_tool = stuck_step.tool_names[0] if stuck_step.tool_names else "write_file"
        step_summary = "; ".join(s.description[:60] for s in pending)

        # ponytail: inject original task so replan doesn't lose intent
        _task = getattr(self._ctx, 'task_description', '') or ''
        if _task and len(_task) > 300:
            _task = _task[:300] + "..."
        prompt = (
            f"卡在步骤「{stuck_step.description[:60]}」无法推进（需要 {stuck_tool}）。\n"
            f"原始任务: {_task or '未知'}\n"
            f"已完成: {cap_summary or '无'}.\n"
            f"请重新规划剩余任务，用 1-2 步替代。必须完成原始任务要求的产出。"
            "工具名必须用这些: write_file, execute_shell, read_file, web_search, execute_python。"
            f"\n格式：步骤|描述|write_file"
        )

        try:
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()
            if not router or not router.is_available():
                return False
            resp = await asyncio.wait_for(
                router.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=200,
                ),
                timeout=10.0,
            )
            text = str(resp).strip() if resp else ""
            if not text or "[LLM_MOCK]" in text:
                return False

            from .plan_manager import _parse_plan_steps
            new_steps = _parse_plan_steps(text)
            if not new_steps:
                return False

            # 保留 done 步骤，替换 pending
            kept = [s for s in self._ctx.plan if s.status == "done"]
            offset = len(kept)
            # ponytail: preserve file paths from original plan's postconditions
            _preserved_paths = []
            for ps in pending:
                for pc in (ps.postconditions or []):
                    if pc.startswith("capability:file_written(path="):
                        _m = re.search(r"path=([^)]+)", pc)
                        if _m:
                            _p = _m.group(1)
                            if _p not in _preserved_paths:
                                _preserved_paths.append(_p)

            for i, s in enumerate(new_steps):
                s.index = offset + i + 1
                s.status = "pending"
                if not s.tool_names:
                    s.tool_names = ["write_file"]
                s.postconditions = _replan_postconditions(s, _preserved_paths)
            self._ctx.plan = kept + new_steps
            self._ctx.plan_generation += 1
            self.stuck_counter = 0
            logger.info(f"TaskProgress: adaptive replan, {len(kept)} done + {len(new_steps)} new")
            return True
        except Exception as e:
            logger.debug(f"TaskProgress: adaptive replan failed: {e}")
            return False


def _split_params(s: str) -> List[str]:
    """拆分逗号分隔参数，尊重括号嵌套"""
    parts = []
    depth = 0
    current = []
    for ch in s:
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _replan_postconditions(step: 'PlanStep', preserved_paths: List[str] = None) -> List[str]:
    """REPLAN 专用 — 工具名直接映射能力，不检查探索关键词。
    如果提供 preserved_paths，则 write_file 步骤附加原始计划的文件路径。
    """
    conds = []
    if not step.tool_names:
        if preserved_paths:
            for _p in preserved_paths:
                conds.append(f"capability:file_written(path={_p})")
            return conds
        return ["capability:file_written"]
    for tool in step.tool_names:
        if tool in ("write_file", "edit_file"):
            if preserved_paths:
                for _p in preserved_paths:
                    conds.append(f"capability:file_written(path={_p})")
            else:
                conds.append("capability:file_written")
        elif tool in ("web_search", "fetch_url", "fetch_json", "hot_search"):
            conds.append("capability:web_search")
        elif tool in ("execute_python", "execute_shell"):
            conds.append("capability:code_executed")
        elif tool == "read_file":
            conds.append("capability:file_read")
    return conds if conds else (["capability:file_written"] if not preserved_paths else [f"capability:file_written(path={_p})" for _p in preserved_paths])
