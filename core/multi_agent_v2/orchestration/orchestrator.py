"""
Orchestrator — 多Agent 编排引擎

核心功能:
  - AgentPool 复用 WorkAgent 实例
  - agent() 从池借 WorkAgent，执行子任务，完成后清理
  - 纯 Python 编排（非 JS）
"""

import asyncio
import json
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_POOL_SIZE = 8


class AgentPool:
    """轻量 WorkAgent 复用池"""

    def __init__(self, size: int = _DEFAULT_POOL_SIZE):
        self._size = size
        self._pool: asyncio.Queue = asyncio.Queue()
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def _ensure(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            # 双重检查
            if self._initialized:
                return
            from core.multi_agent_v2.agents.base.work_agent import WorkAgent

            for i in range(self._size):
                agent = WorkAgent(
                    agent_id=f"pool_{i:03d}",
                    name=f"worker_{i}",
                )
                self._pool.put_nowait(agent)
            self._initialized = True
            logger.info(f"AgentPool: {self._size} 个 WorkAgent 已预热")

    async def acquire(self, label: str = "") -> Any:
        await self._ensure()
        try:
            agent = await asyncio.wait_for(self._pool.get(), timeout=30.0)
            agent._pool_original_id = agent.agent_id
            agent._pool_original_name = agent.agent_name
            return agent
        except asyncio.TimeoutError:
            logger.warning("AgentPool 耗尽，临时创建新 Agent")
            from core.multi_agent_v2.agents.base.work_agent import WorkAgent

            tmp = WorkAgent(
                agent_id=f"tmp_{uuid.uuid4().hex[:6]}",
                name=label or "tmp_worker",
            )
            tmp._pool_original_id = tmp.agent_id
            tmp._pool_original_name = tmp.agent_name
            return tmp

    def release(self, agent: Any) -> None:
        try:
            agent.reset()
            orig_id = getattr(agent, "_pool_original_id", None)
            orig_name = getattr(agent, "_pool_original_name", None)
            if orig_id:
                agent.agent_id = orig_id
            if orig_name:
                agent.agent_name = orig_name
            self._pool.put_nowait(agent)
        except asyncio.QueueFull:
            pass

    @property
    def available(self) -> int:
        return self._pool.qsize() if self._initialized else self._size

    @property
    def total(self) -> int:
        return self._size


_agent_pool = AgentPool()


class BudgetTracker:
    """Token预算追踪器"""

    def __init__(self, total_budget: int | None = None):
        self.total_budget = total_budget
        self._spent = 0
        self._records = []

    def spend(self, amount: int, label: str = ""):
        """记录token消耗"""
        self._spent += amount
        self._records.append({"amount": amount, "label": label, "time": time.time()})

    def spent(self) -> int:
        """获取已使用token数"""
        return self._spent

    def remaining(self) -> int:
        """获取剩余token数，无预算返回infinity"""
        if self.total_budget is None:
            return float("inf")
        return max(0, self.total_budget - self._spent)

    def has_budget(self) -> bool:
        """检查是否还有预算"""
        return self.remaining() > 0


# 全局budget追踪器（按需初始化）
_budget_tracker: BudgetTracker | None = None


def set_budget(total: int | None):
    """设置全局预算"""
    global _budget_tracker
    _budget_tracker = BudgetTracker(total)


def get_budget() -> BudgetTracker | None:
    """获取预算追踪器"""
    return _budget_tracker


@dataclass
class AgentResult:
    """子Agent执行结果"""

    success: bool = False
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    label: str = ""
    agent_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def text(self) -> str:
        output = self.output
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            for k in (
                "final_answer",
                "answer",
                "output",
                "result",
                "text",
                "summary",
                "report",
            ):
                v = output.get(k)
                if v and isinstance(v, (str, int, float)):
                    return str(v)
            return str(output)
        if isinstance(output, list):
            texts = []
            for item in output:
                if isinstance(item, dict):
                    for k in ("text", "result", "content", "summary"):
                        v = item.get(k)
                        if v:
                            texts.append(str(v)[:300])
            if texts:
                return "\n".join(texts)
            return str(output)[:2000]
        return str(output or "")

    def __bool__(self):
        return self.success


async def agent(
    prompt: str,
    opts: Optional[Dict] = None,
    *,
    subagent_type: Optional[str] = None,
) -> AgentResult:
    """启动一个子 Agent 执行子任务。

    从 AgentPool 借 WorkAgent，执行完归还。

    支持官方风格语法：agent("问题", subagent_type="Explore")

    Args:
        prompt: 子任务描述
        opts:
            label:     显示标签
            timeout:   超时秒数（默认 120）
            schema:    JSON Schema dict
            model:     LLM 模型名
        subagent_type: （关键字参数）Subagent 类型名，如 "Explore", "Plan"

    Returns:
        AgentResult
    """
    opts = opts or {}
    merged_opts = dict(opts)

    # 处理 subagent_type
    if subagent_type is None:
        # 兼容旧的 agentType
        subagent_type = opts.get("agentType") or opts.get("agent_type")

    if subagent_type:
        # 从 SubagentRegistry 分派
        from core.multi_agent_v2.workflow.subagent.registry import (
            get_subagent_registry,
        )

        registry = get_subagent_registry()
        profile = registry.dispatch(subagent_type)
        # 合并 profile 到 opts
        profile_opts = profile.to_opts()
        for key, value in profile_opts.items():
            if key not in merged_opts:
                merged_opts[key] = value
        # 如果有 initial_prompt 或 body，加入 prompt
        if profile.initial_prompt:
            prompt = f"{profile.initial_prompt}\n\n{prompt}"
        if profile.body:
            prompt = f"{profile.body}\n\n{prompt}"
        # 如果没有 label，用 profile name
        if "label" not in merged_opts:
            merged_opts["label"] = profile.name

    label = merged_opts.get("label", prompt[:40])
    timeout = merged_opts.get("timeout", 120)
    ar = await _execute_agent(prompt, label, timeout, merged_opts)
    return ar


async def _execute_agent(
        prompt: str,
        label: str,
        timeout: int,
        opts: Dict,
    ) -> AgentResult:
    """核心：从池借 Agent → 执行 → 归还"""
    from core.multi_agent_v2.agents.base.models import Task
    from core.multi_agent_v2.agents.base.work_agent import WorkAgent as _WA

    pool_agent = await _agent_pool.acquire(label)
    agent_id = f"ex_{uuid.uuid4().hex[:8]}"
    pool_agent.agent_id = agent_id
    pool_agent.agent_name = label
    pool_agent._agent_label = label  # 存储标签用于日志前缀

    model = opts.get("model", "")
    if model:
        pool_agent._model_override = model

    # 角色/个性注入
    personality = opts.get("personality", "")
    role = opts.get("role", "")
    if personality:
        pool_agent.personality = personality
    if role:
        pool_agent.role = role

    max_rounds = opts.get("max_rounds", 0)

    # Schema处理：注入格式提示
    schema = opts.get("schema")
    effective_prompt = prompt
    if schema:
        from core.multi_agent_v2.tools.schema_validator import SchemaValidator

        validator = SchemaValidator()
        schema_hint = validator.build_prompt_hint(schema)
        effective_prompt = f"{prompt}\n\n【输出要求】\n{schema_hint}"

    # 构建 task context，注入工具约束
    task_context = {}
    if model:
        task_context["model"] = model
    if max_rounds:
        task_context["max_rounds"] = max_rounds
    # 注入 Agent 类型的工具约束
    allowed_tools = opts.get("allowed_tools")
    disallowed_tools = opts.get("disallowed_tools")
    if allowed_tools:
        task_context["allowed_tools"] = allowed_tools
    if disallowed_tools:
        task_context["disallowed_tools"] = disallowed_tools

    task = Task(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        type="general",
        description=effective_prompt,
        context=task_context,
    )

    try:
        start = time.time()
        max_retries = opts.get("schema_max_retries", 3)
        result = None
        last_error = None
        ar = None

        for retry in range(max_retries):
            try:
                result = await asyncio.wait_for(
                    pool_agent.execute(task), timeout=timeout
                )
                elapsed = time.time() - start

                ar = AgentResult(
                    success=result.success,
                    output=result.output,
                    error=result.error,
                    execution_time=elapsed,
                    label=label,
                    agent_id=agent_id,
                    metadata=result.metadata or {},
                )

                # Schema校验+重试
                if schema and result.success:
                    # 当 schema 存在时，尝试将字符串输出解析为 JSON
                    if isinstance(result.output, str) and schema:
                        try:
                            result.output = json.loads(result.output)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    valid, errors = _validate_schema_with_status(result.output, schema)
                    if valid:
                        ar.output = result.output
                        break
                    else:
                        last_error = "; ".join(errors)
                        if retry < max_retries - 1:
                            # 注入错误反馈，让LLM修正
                            retry_prompt = f"{effective_prompt}\n\n【上次输出格式错误】\n{last_error}\n请严格按照要求输出！"
                            task = Task(
                                task_id=f"task_{uuid.uuid4().hex[:8]}",
                                type="general",
                                description=retry_prompt,
                                context=task.context,
                            )
                            logger.info(
                                f"Schema校验失败，第{retry+1}次重试: {last_error}"
                            )
                        else:
                            # 最后一次尝试，返回带_error的结果
                            ar.output = {
                                "_error": last_error,
                                **(
                                    result.output
                                    if isinstance(result.output, dict)
                                    else {}
                                ),
                            }
                            break
                else:
                    # 无schema或失败，直接返回
                    break
            except Exception as e:
                last_error = str(e)
                if retry == max_retries - 1:
                    raise
                continue

        if ar is None:
            ar = AgentResult(success=False, error=last_error or "未知错误", label=label)

        icon = "✅" if ar.success else "⚠️"
        detail = f"({ar.execution_time:.1f}s)"
        if not ar.success and ar.error:
            detail += f" {ar.error[:60]}"
        print(f"    \033[32m{icon} {label} {detail}\033[0m")
        return ar

    except asyncio.TimeoutError:
        print(f"    \033[33m⏰ {label} (超时)\033[0m")
        return AgentResult(success=False, error="超时", label=label)
    except Exception as e:
        print(f"    \033[31m❌ {label}: {str(e)[:80]}\033[0m")
        logger.warning(f"Agent [{label}] 异常: {traceback.format_exc()}")
        return AgentResult(success=False, error=str(e), label=label)
    finally:
        pool_agent.reset()
        _agent_pool.release(pool_agent)


def _validate_schema_with_status(output: Any, schema: Dict) -> tuple[bool, list[str]]:
    """代理 SchemaValidator 进行校验，返回 (valid, errors)"""
    if not isinstance(schema, dict):
        return False, ["schema不是dict"]
    if not isinstance(output, dict):
        return False, ["输出不是dict"]
    from core.multi_agent_v2.tools.schema_validator import SchemaValidator

    validator = SchemaValidator()
    return validator.validate(output, schema)


def _validate_schema(output: Any, schema: Dict) -> Optional[Any]:
    """代理 SchemaValidator 进行校验"""
    if not isinstance(schema, dict):
        return None
    if not isinstance(output, dict):
        return None
    from core.multi_agent_v2.tools.schema_validator import SchemaValidator

    validator = SchemaValidator()
    valid, errors = validator.validate(output, schema)
    if not valid:
        return {"_error": "; ".join(errors), **output}
    return output


def reset() -> None:
    """重置全局状态"""
    pass


async def parallel(
    tasks: List[Dict[str, Any]],
    timeout: int = 120,
) -> List[AgentResult]:
    """并行执行多个子任务。

    Args:
        tasks: 任务列表，每个任务是 dict:
            {
                "prompt": str,           # 任务描述
                "label": str,            # 显示标签 (可选)
                "subagent_type": str,    # 子代理类型 (可选)
                "model": str,            # 指定模型 (可选)
                "timeout": int,          # 单任务超时 (可选)
            }
        timeout: 整体超时秒数

    Returns:
        List[AgentResult] — 与 tasks 顺序对应的结果列表

    Example:
        results = await parallel([
            {"prompt": "搜索腾讯财报数据", "label": "财务分析"},
            {"prompt": "搜索腾讯负面新闻", "label": "舆情分析"},
            {"prompt": "搜索行业趋势", "label": "行业分析"},
        ])
    """

    async def _run_one(task: Dict[str, Any]) -> AgentResult:
        prompt = task.get("prompt", "")
        label = task.get("label", prompt[:40])
        opts = {}
        if "model" in task:
            opts["model"] = task["model"]
        if "subagent_type" in task:
            opts["agentType"] = task["subagent_type"]
        if "timeout" in task:
            opts["timeout"] = task["timeout"]
        return await agent(prompt, opts)

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[_run_one(t) for t in tasks], return_exceptions=True),
            timeout=timeout,
        )
        # Convert exceptions to AgentResult
        final = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final.append(AgentResult(
                    success=False,
                    error=str(r),
                    label=tasks[i].get("label", tasks[i].get("prompt", "")[:40]),
                ))
            else:
                final.append(r)
        return final
    except asyncio.TimeoutError:
        return [
            AgentResult(success=False, error="并行执行超时", label=t.get("label", ""))
            for t in tasks
        ]


async def pipeline(
    steps: List[Dict[str, Any]],
    timeout_per_step: int = 120,
) -> AgentResult:
    """流水线执行：前一步的输出作为后一步的输入。

    Args:
        steps: 步骤列表，每个步骤是 dict:
            {
                "prompt": str,           # 任务描述模板 (可用 {prev_output} 引用上一步结果)
                "label": str,            # 显示标签 (可选)
                "subagent_type": str,    # 子代理类型 (可选)
            }
        timeout_per_step: 每步超时秒数

    Returns:
        AgentResult — 最后一步的结果

    Example:
        result = await pipeline([
            {"prompt": "搜索百度热搜数据", "label": "获取数据"},
            {"prompt": "分析以下数据并生成报告:\n{prev_output}", "label": "分析报告"},
        ])
    """
    prev_output = ""
    for i, step in enumerate(steps):
        prompt_template = step.get("prompt", "")
        label = step.get("label", f"步骤{i+1}")

        # 替换 {prev_output} 占位符
        prompt = prompt_template.replace("{prev_output}", prev_output[:3000])

        opts = {"timeout": timeout_per_step}
        if "subagent_type" in step:
            opts["agentType"] = step["subagent_type"]

        result = await agent(prompt, opts)

        if not result.success:
            result.error = f"流水线在步骤 [{label}] 失败: {result.error}"
            return result

        prev_output = str(result.output) if result.output else ""

    return result


__all__ = [
    "agent",
    "parallel",
    "pipeline",
    "AgentResult",
    "AgentPool",
    "reset",
]