"""
Orchestrator — 多Agent 编排引擎

核心功能:
  - AgentPool 复用 WorkAgent 实例
  - agent() 从池借 WorkAgent，执行子任务，完成后清理
  - 纯 Python 编排（非 JS）
"""

import asyncio
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

    async def _ensure(self) -> None:
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
            orig_id = getattr(agent, '_pool_original_id', None)
            orig_name = getattr(agent, '_pool_original_name', None)
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
            for k in ("final_answer", "answer", "output", "result", "text", "summary", "report"):
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
) -> AgentResult:
    """启动一个子 Agent 执行子任务。

    从 AgentPool 借 WorkAgent，执行完归还。

    Args:
        prompt: 子任务描述
        opts:
            label:     显示标签
            timeout:   超时秒数（默认 120）
            schema:    JSON Schema dict
            model:     LLM 模型名

    Returns:
        AgentResult
    """
    opts = opts or {}
    label = opts.get("label", prompt[:40])
    timeout = opts.get("timeout", 120)
    ar = await _execute_agent(prompt, label, timeout, opts)
    return ar


async def _execute_agent(
    prompt: str,
    label: str,
    timeout: int,
    opts: Dict,
) -> AgentResult:
    """核心：从池借 Agent → 执行 → 归还"""
    from core.multi_agent_v2.agents.base.work_agent import WorkAgent as _WA
    from core.multi_agent_v2.agents.base.models import Task

    pool_agent = await _agent_pool.acquire(label)
    agent_id = f"ex_{uuid.uuid4().hex[:8]}"
    pool_agent.agent_id = agent_id
    pool_agent.agent_name = label

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

    task = Task(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        type="general",
        description=prompt,
        context={
            "model": model,
            "max_rounds": max_rounds,
        } if (model or max_rounds) else {},
    )

    try:
        start = time.time()
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

        schema = opts.get("schema")
        if schema and result.success:
            validated = _validate_schema(result.output, schema)
            if validated is not None:
                ar.output = validated

        icon = "✅" if result.success else "⚠️"
        detail = f"({elapsed:.1f}s)"
        if not result.success and result.error:
            detail += f" {result.error[:60]}"
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
        pool_agent._stop_bus_listener()
        pool_agent.reset()
        _agent_pool.release(pool_agent)


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


__all__ = [
    "agent", "AgentResult",
    "reset",
]
