"""
WorkflowRuntime — Workflow 执行引擎

接收脚本（async callable / 字符串 / 文件路径），注入编排原语，返回 WorkflowResult。

三种模式模仿 Claude Code Dynamic Workflows:

模式 A — JS 风格脚本字符串（等价于 JS 的 export const meta + 全局函数）:
    script_text = '''  # ← 脚本就是你的编排代码
META = {"name": "对比", "phases": [{"title": "研究"}, {"title": "汇总"}]}

async def run():
    phase("研究")
    r1 = await agent("分析Python", {"agentType": "analyst"})
    r2 = await agent("分析Java", {"agentType": "analyst"})
    phase("汇总")
    return await agent("综合结果", {"agentType": "analyst"})
    '''
    result = await rt.run_script(script_text)
    # agent/parallel/phase/log/budget 作为内置函数注入，无需 import

模式 B — @workflow 装饰器 + run_workflow:
    @workflow(name="对比", phases=[{"title": "研究"}, {"title": "汇总"}])
    async def analyze():
        phase("研究")
        r1 = await agent("分析Python")
        r2 = await agent("分析Java")
        phase("汇总")
        return await agent("综合结果")
    result = await run_workflow(analyze)

模式 C — 直接传 async callable:
    async def analyze():
        ...
    result = await rt.run(analyze, Meta(name="对比"))
"""

import asyncio
import inspect
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from core.multi_agent_v2.orchestration.orchestrator import AgentResult
from core.multi_agent_v2.workflow.subagent import get_subagent_registry, SubagentProfile
from core.multi_agent_v2.workflow.models import Meta, PhaseRecord, WorkflowContext, WorkflowResult

logger = logging.getLogger(__name__)


class WorkflowRuntime:
    """Workflow 执行引擎

    用法:
        rt = WorkflowRuntime()
        result = await rt.run(my_script_fn, Meta(name="测试"))
    """

    def __init__(self):
        self._subagent_registry = get_subagent_registry()

    # ── 主入口 ─────────────────────────────────────────────────

    async def run(self, fn: Callable, meta: Meta) -> WorkflowResult:
        """执行编排脚本（模式 C）

        Args:
            fn: async callable — 编排脚本
            meta: Workflow 元数据

        Returns:
            WorkflowResult
        """
        ctx = self._build_context(meta)
        start = time.time()
        try:
            output = await self._execute_callable(fn, ctx)
            elapsed = time.time() - start
            return self._finalize(ctx, output, elapsed)
        except Exception as e:
            elapsed = time.time() - start
            logger.exception(f"Workflow '{meta.name}' 执行异常: {e}")
            return WorkflowResult(success=False, error=str(e), elapsed=elapsed, label=meta.name)
        finally:
            from core.multi_agent_v2.workflow import _workflow_ctx_var
            _workflow_ctx_var.reset(ctx._token)

    # ── 脚本字符串模式（等价 JS 的 script 字符串 → eval） ─────

    async def run_script(self, script: str, **meta_overrides) -> WorkflowResult:
        """执行 JS 风格脚本字符串（模式 A）

        脚本中 META 定义元数据，run() 是入口。
        agent/parallel/pipeline/phase/log/budget 作为全局内置函数使用，无需 import。

        Args:
            script: Python 脚本文本
            **meta_overrides: 可覆盖的 META 属性

        Returns:
            WorkflowResult
        """
        # ── 先 exec 提取 META（用占位，仅为了取 meta） ──
        async def _place(*a, **kw): ...
        _ns = {
            "agent": _place,
            "parallel": _place,
            "pipeline": _place,
            "phase": lambda x: None,
            "log": lambda x: None,
            "budget": None,
            "__builtins__": __builtins__,
        }
        exec(compile(script, "<workflow_script>", "exec"), _ns)

        meta_dict = _ns.get("META", {})
        meta = Meta(
            name=meta_dict.get("name", meta_overrides.pop("name", "unnamed")),
            description=meta_dict.get("description", meta_overrides.pop("description", "")),
            phases=meta_dict.get("phases", meta_overrides.pop("phases", [])),
        )
        for k, v in meta_overrides.items():
            setattr(meta, k, v)

        run_fn = _ns.get("run")
        if run_fn is None:
            return WorkflowResult(success=False, error="脚本缺少 run() 入口函数", label=meta.name)

        # ── 再次 exec，注入真实原语到 namespace ──
        ctx = self._build_context(meta)
        ns = {
            "agent": ctx.agent,
            "parallel": ctx.parallel,
            "pipeline": ctx.pipeline,
            "phase": ctx.phase,
            "log": ctx.log,
            "budget": None,
            "__builtins__": __builtins__,
        }
        exec(compile(script, "<workflow_script>", "exec"), ns)
        run_fn = ns.get("run")

        # ── contextvar 也设上（保证 import 进来的 agent/phase 也能用） ──
        from core.multi_agent_v2.workflow import _workflow_ctx_var
        _workflow_ctx_var.reset(ctx._token)
        token = _workflow_ctx_var.set(ctx)

        start = time.time()
        try:
            output = await self._execute_callable(run_fn, ctx)
            elapsed = time.time() - start
            return self._finalize(ctx, output, elapsed)
        except Exception as e:
            elapsed = time.time() - start
            logger.exception(f"Workflow script '{meta.name}' 异常: {e}")
            return WorkflowResult(success=False, error=str(e), elapsed=elapsed, label=meta.name)
        finally:
            _workflow_ctx_var.reset(token)

    async def run_file(self, path: str, **meta_overrides) -> WorkflowResult:
        """从文件加载并执行 workflow 脚本"""
        import pathlib
        p = pathlib.Path(path)
        if not p.exists():
            return WorkflowResult(success=False, error=f"文件不存在: {path}", label=path)
        script = p.read_text(encoding="utf-8")
        return await self.run_script(script, **meta_overrides)

    # ── 内部方法 ──────────────────────────────────────────────

    async def _execute_callable(self, fn: Callable, ctx: WorkflowContext) -> Any:
        """执行 callable，支持无参 / ctx 参数 / 协程 / async"""
        if inspect.iscoroutinefunction(fn):
            sig = inspect.signature(fn)
            has_ctx_param = any(
                p.name in ("ctx", "context") and p.default is inspect.Parameter.empty
                for p in sig.parameters.values()
            )
            if has_ctx_param:
                return await fn(ctx)
            return await fn()
        return await fn()

    def _build_context(self, meta: Meta) -> WorkflowContext:
        """创建上下文 + 注入编排原语 + 设定 contextvar"""
        from core.multi_agent_v2.workflow import _workflow_ctx_var
        ctx = WorkflowContext(meta=meta)
        ctx.agent = self._build_agent_fn(ctx)
        ctx.parallel = self._build_parallel_fn(ctx)
        ctx.pipeline = self._build_pipeline_fn(ctx)
        ctx.phase = self._build_phase_fn(ctx)
        ctx.log = self._build_log_fn(ctx)

        token = _workflow_ctx_var.set(ctx)
        ctx._token = token
        return ctx

    def _finalize(self, ctx: WorkflowContext, output: Any, elapsed: float) -> WorkflowResult:
        """收尾：记录最后阶段，组装 WorkflowResult"""
        if ctx._current_phase:
            now = time.time()
            record = PhaseRecord(
                title=ctx._current_phase,
                agent_calls=sum(1 for r in ctx._results if r.execution_time > 0),
                elapsed=now - ctx._phase_start,
            )
            ctx._phase_history.append(record)

        return WorkflowResult(
            success=True,
            output=output,
            phases=ctx._phase_history,
            agent_results=ctx._results,
            elapsed=elapsed,
            label=ctx.meta.name,
        )

    # ── 编排原语注入 ──────────────────────────────────────────

    def _build_agent_fn(self, ctx: WorkflowContext) -> Callable:
        """创建 agent() — 根据 agentType 查注册表，合并 profile 后委托 orchestrator"""

        async def _agent(prompt: str, opts: Optional[Dict] = None) -> AgentResult:
            opts = dict(opts or {})

            # ── agentType 分派：查注册表 → 合并 profile ──
            agent_type = opts.pop("agentType", "general")
            profile = self._subagent_registry.dispatch(agent_type)

            # profile 属性合并到 opts（opts 优先于 profile）
            _merge_profile(profile, opts)

            # ── 委托 orchestrator.agent() ──
            from core.multi_agent_v2.orchestration.orchestrator import agent as orch_agent
            result = await orch_agent(prompt, opts)

            # ── 记录 ──
            ctx._results.append(result)
            return result

        return _agent

    def _build_parallel_fn(self, ctx: WorkflowContext) -> Callable:
        """创建 parallel() — barrier：等所有 thunk 完成，失败的返回 None"""

        async def _parallel(thunks: List[Callable[[], Any]]) -> List[Any]:
            results = await asyncio.gather(
                *[t() for t in thunks],
                return_exceptions=True,
            )
            return [
                r if not isinstance(r, Exception) else None
                for r in results
            ]

        return _parallel

    def _build_pipeline_fn(self, ctx: WorkflowContext) -> Callable:
        """创建 pipeline() — 无 barrier

        每个 item 独立流经所有 stage，各 item 并发推进。
        stage 签名: (prev_result, original_item, index) -> new_result
        支持 sync 和 async stage。

        pipeline([A, B, C], stage1, stage2):
          → A stage1 → A stage2
          → B stage1 → B stage2
          → C stage1 → C stage2
          (无 barrier，不互相等待)
        """

        async def _pipeline(items: List, *stages: Callable) -> List[Any]:
            async def _run_item(item: Any, idx: int) -> Any:
                prev = item
                try:
                    for stage in stages:
                        result = stage(prev, item, idx)
                        if asyncio.iscoroutine(result):
                            prev = await result
                        else:
                            prev = result
                    return prev
                except Exception as e:
                    logger.debug(f"pipeline item[{idx}] 异常: {e}")
                    return None

            tasks = [_run_item(item, i) for i, item in enumerate(items)]
            return await asyncio.gather(*tasks)

        return _pipeline

    def _build_phase_fn(self, ctx: WorkflowContext) -> Callable:
        """创建 phase() — 阶段标记"""

        def _phase(title: str) -> None:
            now = time.time()
            # 关闭前一个阶段
            if ctx._current_phase:
                elapsed = now - ctx._phase_start
                record = PhaseRecord(
                    title=ctx._current_phase,
                    agent_calls=sum(1 for r in ctx._results if r.execution_time > 0),
                    elapsed=elapsed,
                )
                ctx._phase_history.append(record)
            # 开启新阶段
            ctx._current_phase = title
            ctx._phase_start = now

        return _phase

    def _build_log_fn(self, ctx: WorkflowContext) -> Callable:
        """创建 log() — 进度输出"""

        def _log(msg: str) -> None:
            print(f"    \033[2;37m📋 {msg}\033[0m")

        return _log


# ── 工具函数 ─────────────────────────────────────────────────

def _merge_profile(profile: SubagentProfile, opts: Dict) -> None:
    """将 SubagentProfile 属性合并到 opts，opts 已有值则优先"""
    if profile.model and "model" not in opts:
        opts["model"] = profile.model
    if profile.personality and "personality" not in opts:
        opts["personality"] = profile.personality
    if profile.role and "role" not in opts:
        opts["role"] = profile.role
    if profile.max_rounds and "max_rounds" not in opts:
        opts["max_rounds"] = profile.max_rounds


# ── 内置编排模式 — 常见组合模式 ─────────────────────────────

class OrchestrationPatterns:
    """内置编排模式 — 常见组合的封装

    这些不是 WorkflowScript，而是可被脚本或 CLI 直接调用的组合模式。
    在 WorkflowRuntime 执行上下文内使用。
    """

    @staticmethod
    async def fan_out_reduce(
        subtasks: List[str],
        analyze_fn: Callable[[str], Any],
        reduce_prompt: str,
        reduce_opts: Optional[Dict] = None,
    ) -> AgentResult:
        """扇出 → 减重 → 合成

        并行执行多个子任务 → 收集成功结果 → 用汇总 agent 合成
        """
        from core.multi_agent_v2.workflow import parallel, agent

        results = await parallel([
            lambda t=s: analyze_fn(t) for s in subtasks
        ])

        good = [r for r in results if r and (isinstance(r, AgentResult) and r.success or True)]
        if not good:
            return AgentResult(success=False, error="所有子任务失败")

        context_parts = []
        for r in good:
            text = r.text()[:500] if isinstance(r, AgentResult) else str(r)[:500]
            label = r.label if isinstance(r, AgentResult) else ""
            context_parts.append(f"【{label}】\n{text}")

        context = "\n\n".join(context_parts)
        return await agent(
            f"{reduce_prompt}\n\n子任务结果:\n{context}",
            reduce_opts or {"agentType": "analyst", "label": "综合汇总", "timeout": 180},
        )

    @staticmethod
    async def adversarial_verify(
        claim: str,
        n_skeptics: int = 3,
    ) -> bool:
        """质疑式验证 — N 个质疑者，多数不否决才通过

        Returns:
            True 表示结论通过了验证（幸存），False 表示被推翻
        """
        from core.multi_agent_v2.workflow import parallel, agent

        votes = await parallel([
            lambda i=i: agent(
                f"作为严格的审查员，质疑以下结论，找漏洞和反例。"
                f"输出一个 JSON: {{\"refuted\": true/false, \"reason\": \"...\"}}\n\n{claim}",
                {"agentType": "critic", "label": f"质疑者{i+1}"},
            )
            for i in range(n_skeptics)
        ])

        refuted = 0
        for v in votes:
            if v and isinstance(v, AgentResult) and v.success:
                text = v.text().lower()
                if '"refuted": true' in text or '"refuted":true' in text:
                    refuted += 1

        return refuted < (n_skeptics / 2)

    @staticmethod
    async def find_until_dry(
        finder_fn: Callable,
        key_fn: Callable = lambda x: str(x),
        max_dry: int = 2,
        max_total: int = 20,
    ) -> List:
        """发现直到干涸 — 持续发现直到连续 K 轮无新发现

        Args:
            finder_fn: async (seen_set) -> [new_items]
            key_fn: 去重键函数
            max_dry: 连续几轮无新发现则停止
            max_total: 最大总数

        Returns:
            所有发现的 items
        """
        from core.multi_agent_v2.workflow import parallel

        seen = set()
        dry = 0
        total = []

        while dry < max_dry and len(total) < max_total:
            batch = await finder_fn(seen)
            fresh = [b for b in batch if key_fn(b) not in seen]
            if not fresh:
                dry += 1
            else:
                dry = 0
                for b in fresh:
                    seen.add(key_fn(b))
                total.extend(fresh)

        return total
