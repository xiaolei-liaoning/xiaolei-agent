"""
AGENCY.md 驱动的独立 Agent — 对标 Claude Code 架构

核心模式：LLM 驱动循环，工具用Schema定义，并发执行，权限控制。

用法：
    from core.agency_agent import run_agent, run_team
    reply = await run_agent("分析这份数据")
    team_reply = await run_team("分析项目")
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_AGENCY_PATH = Path(__file__).parent / "AGENCY.md"

# ═══════════════════════════════════════════════════════════════════════════════
# AGENCY.md 加载
# ═══════════════════════════════════════════════════════════════════════════════


def load_agency(path: str | None = None) -> str:
    p = Path(path) if path else DEFAULT_AGENCY_PATH
    if not p.exists():
        return "你是一个通用 AI 助手。请根据用户需求提供帮助。"
    return p.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# ToolSpec — 工具Schema定义（类比 Claude Code 的 Tool { inputSchema, call, ... }）
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ToolSpec:
    """工具定义 — 带Schema和元数据"""
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    is_concurrency_safe: bool = False   # 能否并行执行（只读工具可以）
    permission: str = "allow"           # allow / ask / deny
    priority: int = 5


def _build_tools() -> List[ToolSpec]:
    """从 ToolRegistry + SkillRegistry 构建工具列表（带Schema）"""
    tools: List[ToolSpec] = []
    seen: set = set()

    for source_name in ("ToolRegistry", "SkillRegistry"):
        try:
            if source_name == "ToolRegistry":
                from core.skill_base import ToolRegistry
                entries = [(e["name"], ToolRegistry.get(e["name"])) for e in ToolRegistry.list()]
            else:
                from core.skill_base import get_skill_registry
                entries = [(s.name, s) for s in get_skill_registry().all() if s.name not in seen]

            for name, obj in entries:
                if not obj or name in seen:
                    continue
                seen.add(name)
                tools.append(ToolSpec(
                    name=name,
                    description=getattr(obj, "description", ""),
                    is_concurrency_safe=getattr(obj, "is_read_only", False),
                    priority=getattr(obj, "priority", 5),
                ))
        except Exception:
            continue

    return tools


def _tools_to_prompt(tools: List[ToolSpec]) -> str:
    if not tools:
        return "（暂无可用工具）"
    return "\n".join(
        f"- {t.name}: {t.description}" + (" [只读]" if t.is_concurrency_safe else "")
        for t in sorted(tools, key=lambda x: -x.priority)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 权限系统（allow / deny / ask）
# ═══════════════════════════════════════════════════════════════════════════════


class PermissionHandler:
    """工具权限控制 — 类比 Claude Code 的 canUseTool + pre/post hooks

    mode:
        "allow" — 自动允许所有（默认）
        "ask"   — 需要调用的工具反问用户
        "strict" — 只允许白名单
    """

    def __init__(self, mode: str = "allow", allowed: Optional[List[str]] = None,
                 denied: Optional[List[str]] = None):
        self.mode = mode
        self.allowed = set(allowed or [])
        self.denied = set(denied or [])

    async def check(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """检查工具是否允许执行"""
        if tool_name in self.denied:
            return False
        if self.mode == "allow":
            return True
        if self.mode == "strict":
            return tool_name in self.allowed
        # ask: 反问用户
        from core.agents.agent_communication import get_question_registry
        future = get_question_registry().ask(
            agent_id="permission",
            agent_name="权限系统",
            question=f"是否允许调用工具「{tool_name}」？\n参数: {json.dumps(args, ensure_ascii=False)[:200]}",
            context="permission_check",
            timeout=60,
        )
        try:
            result = await asyncio.wait_for(future, timeout=65)
            return result == "proceed"
        except (asyncio.TimeoutError, Exception):
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# 并发工具执行 — 只读并行，写操作串行
# ═══════════════════════════════════════════════════════════════════════════════


async def _execute_single(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from core.skill_base import ToolRegistry
        result = await ToolRegistry.execute(name, args)
        return {"success": result.success, "result": result.data, "error": result.error}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def execute_tools(tool_calls: List[tuple[str, Dict[str, Any]]],
                         tools: List[ToolSpec],
                         permission: PermissionHandler) -> List[Dict[str, Any]]:
    """执行一组工具调用：只读并行 + 写操作串行"""

    tool_map = {t.name: t for t in tools}
    results: List[Dict[str, Any]] = []

    # 分拆：可以并行的 vs 需要串行的
    safe: List[tuple[int, str, Dict]] = []
    serial: List[tuple[int, str, Dict]] = []

    for i, (name, args) in enumerate(tool_calls):
        spec = tool_map.get(name)
        if not permission.allowed and permission.mode == "allow":
            # 快速路径：无权限限制 + 无白名单
            if spec and spec.is_concurrency_safe:
                safe.append((i, name, args))
            else:
                serial.append((i, name, args))
        else:
            serial.append((i, name, args))  # 有权限检查的也串行

    # 并行执行
    if safe:
        safe_results = await asyncio.gather(*[
            _execute_single(name, args) for _, name, args in safe
        ], return_exceptions=True)
        for (i, name, args), res in zip(safe, safe_results):
            if isinstance(res, Exception):
                results.append((i, {"success": False, "error": str(res)}))
            else:
                results.append((i, res))

    # 串行执行（含权限检查）
    for i, name, args in serial:
        ok = await permission.check(name, args)
        if not ok:
            results.append((i, {"success": False, "error": f"权限拒绝: {name}"}))
            continue
        res = await _execute_single(name, args)
        results.append((i, res))

    # 按原始顺序返回
    results.sort(key=lambda x: x[0])
    return [r for _, r in results]


# ═══════════════════════════════════════════════════════════════════════════════
# LLM 回复解析（支持多个工具调用）
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_tool_calls(reply: str) -> List[tuple[str, Dict[str, Any]]]:
    """从LLM回复解析工具调用，支持单条和多条"""
    text = reply.strip()
    calls: List[tuple[str, Dict]] = []
    candidates: List[str] = []

    if text.startswith(("{", "[")):
        candidates.append(text)
    if "```" in text:
        for block in text.split("```"):
            cleaned = block.strip().removeprefix("json").strip()
            if cleaned.startswith("{"):
                candidates.append(cleaned)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        # 多个工具调用: [{"$action": "tool", ...}, ...]
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("$action") == "tool" and item.get("name")
                    if name:
                        calls.append((name, item.get("args", {})))
        # 单个工具调用
        elif isinstance(parsed, dict):
            name = None
            if parsed.get("$action") == "tool":
                name = parsed.get("name")
            elif "name" in parsed and "args" in parsed:
                name = parsed["name"]
            if name:
                calls.append((name, parsed.get("args", {})))

    return calls


# ═══════════════════════════════════════════════════════════════════════════════
# 上下文管理 + 自动压缩
# ═══════════════════════════════════════════════════════════════════════════════

_ESTIMATE_TOKENS_PER_CHAR = 0.25  # 中英文混合估算


def _estimate_tokens(text: str) -> int:
    return int(len(text) * _ESTIMATE_TOKENS_PER_CHAR)


class Context:
    """单Agent上下文（记忆 + 事件 + 自动压缩）"""

    def __init__(self, max_tokens: int = 8000):
        self.messages: List[Dict[str, Any]] = []
        self._facts: Dict[str, Any] = {}
        self._episodes: List[Dict[str, Any]] = []
        self._max_tokens = max_tokens
        self._compressed_count = 0

    def note(self, key: str, value: Any) -> None:
        self._facts[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._facts.get(key, default)

    def record(self, kind: str, content: str) -> None:
        self._episodes.append({"kind": kind, "content": content, "time": time.time()})

    def summary(self) -> str:
        parts = []
        if self._facts:
            parts.append("关键信息:\n" + "\n".join(f"- {k}: {v}" for k, v in self._facts.items()))
        if self._episodes:
            parts.append("事件记录:\n" + "\n".join(
                f"- [{e['kind']}] {e['content']}" for e in self._episodes[-5:]
            ))
        return "\n\n".join(parts)

    async def compress(self, router: Any) -> None:
        """当消息总数或token超限时，自动压缩早期对话"""
        total = sum(_estimate_tokens(str(m.get("content", ""))) for m in self.messages)
        if total < self._max_tokens and len(self.messages) < 30:
            return

        # 保留 system prompt + 最近 6 轮
        system = [m for m in self.messages if m.get("role") == "system"]
        recent = self.messages[-12:] if len(self.messages) > 12 else self.messages
        to_compress = self.messages[len(system):-12] if len(self.messages) > 12 + len(system) else []

        if not to_compress:
            return

        try:
            summary = await asyncio.wait_for(
                router.chat([{"role": "user", "content": (
                    "请将以下对话压缩为一段保持关键信息的摘要（保留所有工具调用结果和决策）:\n\n"
                    + "\n".join(
                        f"[{m['role']}]: {str(m.get('content', ''))[:300]}"
                        for m in to_compress
                    )
                )}], temperature=0.3, max_tokens=500),
                timeout=20,
            )
            self._compressed_count += 1
            self.messages = system + [
                {"role": "system", "content": f"[上下文压缩 #{self._compressed_count}] {summary[:800]}"}
            ] + recent
            logger.info(f"上下文压缩完成: {len(to_compress)} 轮 → 摘要")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# 反问 & 反思
# ═══════════════════════════════════════════════════════════════════════════════


async def _ask_user(step_info: str, error: str, timeout: int = 60) -> str | None:
    try:
        from core.agents.agent_communication import get_question_registry
        future = get_question_registry().ask(
            agent_id="agency-agent", agent_name="Agency Agent",
            question=f"【当前步骤】{step_info}\n【遇到问题】{error}\n\n请选择操作：",
            context=step_info, timeout=timeout,
        )
        result = await asyncio.wait_for(future, timeout=timeout + 5)
        return result
    except (asyncio.TimeoutError, Exception):
        return None


async def _reflect(router: Any, tool_name: str, result: Dict) -> str | None:
    try:
        return await asyncio.wait_for(
            router.chat([{"role": "user", "content": (
                f"请评估工具「{tool_name}」的执行结果：\n\n"
                "1. **结果质量**：数据是否完整、格式是否正确\n"
                "2. **异常检查**：是否有错误、超时、空结果\n"
                "3. **下一步建议**：继续执行、调整参数重试、还是换方案\n\n"
                f"结果: {json.dumps(result, ensure_ascii=False)[:800]}\n\n"
                "输出格式：一句话判断 + 理由"
            )}], temperature=0.3, max_tokens=300), timeout=15,
        )
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 主循环
# ═══════════════════════════════════════════════════════════════════════════════


async def run_agent(
    user_input: str,
    agency_path: str | None = None,
    max_steps: int = 25,
    step_timeout: float = 30.0,
    system_prompt_extra: str = "",
    context: Context | None = None,
    enable_reflection: bool = False,
    permission: PermissionHandler | None = None,
) -> str:
    """LLM 驱动的 agent 主循环

    - 工具Schema定义 → 并发执行(只读并行/写串行)
    - 权限控制 → allow/ask/deny
    - 上下文自动压缩 → 超过token阈值时自动摘要
    - 反问 + 反思 + 查重
    """
    try:
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
    except Exception as e:
        return f"LLM 后端不可用: {e}"

    # 加载人格 + 工具
    agency_content = load_agency(agency_path)
    tools = _build_tools()
    tool_prompt = _tools_to_prompt(tools)

    system_prompt = (
        f"{agency_content}\n{system_prompt_extra}\n" if system_prompt_extra else agency_content
    )
    system_prompt += (
        f"\n\n## 可用工具\n{tool_prompt}\n\n"
        "## 工具调用规则\n"
        "- 需要执行操作时，返回以下 JSON 格式：\n"
        '  {"$action": "tool", "name": "工具名", "args": {"参数名": "参数值"}}\n'
        "- 多个工具可以同时调用：\n"
        '  [{"$action": "tool", "name": "工具A", "args":{}}, {"$action": "tool", "name": "工具B", "args":{}}]\n'
        "- 执行结果会返回给你，根据结果继续。\n"
        "- 不需要工具时，直接回复用户。"
    )

    if context:
        ctx_summary = context.summary()
        if ctx_summary:
            system_prompt += f"\n\n## 当前上下文\n{ctx_summary}"

    if permission is None:
        permission = PermissionHandler()

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    if context:
        context.messages = messages

    from core.repetition_tracker import RepetitionTracker
    tracker = RepetitionTracker(threshold=3)

    for step in range(1, max_steps + 1):
        logger.info(f"Agency Agent 步骤 {step}/{max_steps}")

        # 查重提醒
        advice = tracker.advice()
        msgs = messages[:]
        if advice:
            msgs = messages[:1] + [
                {"role": "user", "content": f"【系统提醒】\n{advice}\n\n请在回答中避免重复尝试。"}
            ] + messages[1:]

        # ---- LLM 调用 + 错误恢复(重试+回退) ----
        reply = None
        last_error = None
        for attempt in range(3):  # 最多重试3次
            try:
                reply = await asyncio.wait_for(
                    router.chat(msgs, temperature=0.7, max_tokens=2000),
                    timeout=step_timeout,
                )
                break
            except asyncio.TimeoutError:
                last_error = f"超时({step_timeout}s)"
                answer = await _ask_user(f"步骤{step}/{max_steps}", last_error)
                if answer == "retry":
                    continue
                elif answer == "cancel":
                    return "任务已取消。"
                break
            except Exception as e:
                last_error = str(e)
                answer = await _ask_user(f"步骤{step}/{max_steps}", last_error)
                if answer == "retry":
                    continue
                elif answer == "cancel":
                    return "任务已取消。"
                break

        if reply is None:
            return f"LLM 调用失败: {last_error}"

        # ---- 解析工具调用 ----
        tool_calls = _parse_tool_calls(reply)
        if not tool_calls:
            if context:
                context.note("最终回复", reply[:100])
            return reply

        if context:
            context.note(f"步骤{step}", f"调用 {len(tool_calls)} 个工具")

        messages.append({"role": "assistant", "content": reply})

        # ---- 并发执行工具 ----
        results = await execute_tools(tool_calls, tools, permission)

        # ---- 查重 + 反思 + KEPA ----
        for (name, args), result in zip(tool_calls, results):
            tracker.record(user_input, f"{name}({str(args)[:100]})", result)
            result_str = json.dumps(result, ensure_ascii=False)[:2000]

            reflection_text = None
            if enable_reflection and result.get("success"):
                reflection_text = await _reflect(router, name, result)
            elif not result.get("success"):
                reflection_text = f"工具执行失败: {result.get('error', '未知错误')}"

            if reflection_text:
                messages.append({"role": "assistant", "content": f"[反思] {reflection_text}"})
                if context:
                    context.record("反思", f"{name}: {reflection_text[:80]}")

            # KEPA 日志
            try:
                from core.execution_logger import get_execution_logger
                get_execution_logger().log(
                    tool_name=name, params=args,
                    status="success" if result.get("success") else "failed",
                    result=result_str[:500],
                    notes=reflection_text[:500] if reflection_text else None,
                )
            except Exception:
                pass

            messages.append({
                "role": "user",
                "content": f"工具「{name}」返回:\n{result_str}\n\n请根据结果继续。",
            })

        # ---- 上下文自动压缩 ----
        if context and step % 5 == 0:
            await context.compress(router)

    return "已达最大步数，如需继续请重新说明。"


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Team：队长 + 队员 + 消息总线
# ═══════════════════════════════════════════════════════════════════════════════


class TeamMailbox:
    """团队邮箱 — 类比 Claude Code 的 mailbox 通信

    队员通过邮箱收发消息，可同时拉取+持续监听。
    """

    def __init__(self):
        self._memory: Dict[str, Any] = {}
        self._events: List[Dict[str, Any]] = []
        self._inboxes: Dict[str, asyncio.Queue] = {}

    def set(self, key: str, value: Any) -> None:
        self._memory[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._memory.get(key, default)

    async def send(self, to: str, sender: str, content: str, kind: str = "message") -> None:
        """给指定队员发消息"""
        self._events.append({
            "from": sender, "to": to, "content": content,
            "kind": kind, "time": time.time(),
        })
        if to in self._inboxes:
            await self._inboxes[to].put({"from": sender, "content": content, "kind": kind})

    def register(self, agent_name: str) -> None:
        """队员注册自己的邮箱"""
        self._inboxes[agent_name] = asyncio.Queue()

    async def wait_for_message(self, agent_name: str, timeout: float = 30) -> Optional[Dict]:
        """队员等待新消息（阻塞）"""
        q = self._inboxes.get(agent_name)
        if not q:
            return None
        try:
            return await asyncio.wait_for(q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def broadcast(self, sender: str, content: str) -> None:
        self._events.append({
            "from": sender, "to": "*", "content": content,
            "kind": "broadcast", "time": time.time(),
        })

    def to_prompt(self) -> str:
        parts = []
        if self._memory:
            parts.append("## 团队目标")
            for k, v in self._memory.items():
                parts.append(f"- {k}: {v}")
        recent = self._events[-8:]
        if recent:
            parts.append("## 团队动态")
            for e in recent:
                target = f"→{e['to']}" if e.get("to") and e["to"] != "*" else ""
                parts.append(f"- [{e['from']}{target}] {e['content']}")
        return "\n".join(parts)


async def run_team(
    task: str,
    agency_path: str | None = None,
    max_agents: int = 5,
) -> str:
    """团队模式：队长分解 → 队员并行（带上下文继承 + 邮箱通信）"""
    try:
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
    except Exception as e:
        return f"LLM 后端不可用: {e}"

    # ── 1. 队长分解任务 ────────────────────────────────────────────────
    try:
        reply = await router.chat([{"role": "user", "content": (
            "你是团队队长。将以下任务拆解为2-5个可以并行执行的子任务，"
            "每个子任务配一个角色名和明确分工。\n\n"
            f"任务：{task}\n\n"
            "输出格式（每行一个子任务）：\n"
            "- 角色名: 具体分工描述"
        )}], temperature=0.5, max_tokens=1000)
    except Exception as e:
        return f"队长分解任务失败: {e}"

    members: list[tuple[str, str]] = []
    for line in reply.split("\n"):
        line = line.strip().removeprefix("- ").strip()
        if ":" in line and len(line) > 10 and not line.startswith(("```", "#")):
            role, desc = line.split(":", 1)
            members.append((role.strip(), desc.strip()))

    members = members[:max_agents]
    if not members:
        return await run_agent(task, agency_path)

    logger.info("队长: %s → %d 名队员", task[:40], len(members))

    # ── 2. 团队邮箱初始化 ─────────────────────────────────────────────
    mailbox = TeamMailbox()
    mailbox.set("任务", task)
    for role, _ in members:
        mailbox.register(role)

    mailbox.broadcast("队长", f"团队组建: {len(members)} 人")

    # ── 3. 队员并行执行（带上下文继承 + 权限系统）────────────────────
    async def _member_run(role: str, desc: str, idx: int) -> tuple[str, Context]:
        # 子Agent继承团队上下文
        sub_ctx = Context(max_tokens=4000)
        sub_ctx.note("我的角色", role)
        sub_ctx.note("我的分工", desc)
        sub_ctx.note("团队任务", task)

        mailbox.broadcast("队长", f"队员「{role}」开始: {desc}")

        extra = (
            f"\n## 你在团队中的角色\n"
            f"你是队员「{role}」，你的分工是: {desc}\n"
            f"完成报告格式：\n"
            f'{{"$summary": "关键发现"}}\n'
            f'{{"$report": "要报告到频道的内容"}}\n\n'
            f"## 团队当前状态\n{mailbox.to_prompt()}"
        )

        result = await run_agent(
            desc, agency_path,
            system_prompt_extra=extra,
            context=sub_ctx,
            enable_reflection=True,
            permission=PermissionHandler(),
        )

        # 队员完成 → 发消息到邮箱
        await mailbox.send("队长", role, f"任务完成", "done")
        return result, sub_ctx

    raw_results = await asyncio.gather(
        *[_member_run(r, d, i) for i, (r, d) in enumerate(members)]
    )

    # ── 4. 汇聚结果 ──────────────────────────────────────────────────
    results: list[str] = []
    for (role, _), (res, mctx) in zip(members, raw_results):
        results.append(res)
        for key, val in mctx._facts.items():
            if key not in ("我的角色", "我的分工", "团队任务"):
                mailbox.set(f"{role} {key}", val)
        for line in reversed(res.split("\n")):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                p = json.loads(line)
                if p.get("$summary"):
                    mailbox.set(f"{role} 发现", p["$summary"])
                if p.get("$report"):
                    mailbox.broadcast(role, p["$report"])
            except Exception:
                pass

    mailbox.broadcast("队长", "全部完成，汇总中")

    # ── 5. 队长汇总 ──────────────────────────────────────────────────
    member_report = "\n\n".join(
        f"## {role}\n结果: {res[:2000]}" for (role, _), res in zip(members, results)
    )
    try:
        return await router.chat([{"role": "user", "content": (
            f"原始任务: {task}\n\n"
            f"团队动态:\n{mailbox.to_prompt()}\n\n"
            f"{member_report}\n\n请整合成一份连贯的最终回答给用户。"
        )}], temperature=0.5, max_tokens=2000)
    except Exception:
        return "\n\n".join(f"【{role}】\n{r[:300]}" for (role, _), r in zip(members, results))
