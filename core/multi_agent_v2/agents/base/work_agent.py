"""
WorkAgent - 统一智能体

单一 Agent 类型，根据任务需求动态调整行为和能力。
取代了原先分散的 WorkerAgent / MasterAgent / ReviewerAgent / ExpertAgent / CoordinatorAgent / MonitorAgent。

核心设计：
- 不预设角色：同一个 WorkAgent 实例可以根据不同任务动态调整
- 能力即配置：capabilities 由任务匹配动态生成，而非硬编码
- LLM 驱动的执行：所有任务通过 ReAct 快路径执行
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent
from .models import AgentType, Capability, Task, ActionResult, Thought

logger = logging.getLogger(__name__)


class WorkAgent(BaseAgent):
    """统一工作 Agent - 根据任务动态调整行为和能力

    替代 WorkerAgent / MasterAgent / ReviewerAgent / ExpertAgent / CoordinatorAgent / MonitorAgent。
    不再预设 specialization，而是根据任务类型动态适配。

    执行路径：统一走 _execute_fast 快路径（ReAct 直通），
    跳过已废弃的 StepPlanner/StepExecutor 全链路。
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "通用工作 Agent，根据任务动态调整",
        light_mode: bool = False,
        personality: str = "",
        role: str = "",
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.WORKER,
            name=name,
            description=description,
            personality=personality,
            role=role,
        )

        # 执行模式（保留字段以兼容旧构造调用，不再影响执行路径）
        self._light_mode = light_mode

        # 模型覆盖（orchestrator 动态设置）
        self._model_override: str = ""

        # 能力列表 - 非硬编码，根据任务动态生成
        self.capabilities: List[Capability] = self._default_capabilities()

        # 工作记录
        self.work_history: List[Dict[str, Any]] = []

        # SharedBus 监听
        self._bus_listener_task: Optional[asyncio.Task] = None

        logger.info(f"WorkAgent {'[轻量]' if light_mode else ''} 初始化完成: {self.agent_id}")

    def _default_capabilities(self) -> List[Capability]:
        """提供一组通用的默认能力，具体匹配由 scheduler 动态完成"""
        return [
            Capability(
                name="general_task",
                description="通用任务执行能力，适配各种类型的任务",
                keywords=["执行", "处理", "完成", "分析", "生成", "搜索"],
                expertise_level=0.7,
            ),
        ]

    def reset(self) -> None:
        """重置 Agent 状态，为下次复用做准备"""
        self.work_history = []
        self._model_override = ""
        self.reset_temp_memory()  # 清空临时记忆
        self.personality = ""
        self.role = ""
        self.capabilities = self._default_capabilities()
        logger.debug(f"WorkAgent {self.agent_id} 状态已重置")

    def adapt_to_task(self, task: Task) -> None:
        """根据任务动态调整 Agent 的能力配置

        每个 Agent 拥有完整能力（不做裁剪），根据任务类型追加专项能力。
        """
        task_type = task.type or "general"
        task_keywords = task.keywords or []

        # 追加全部能力类型（不做关键词过滤），每个 Agent 天然具备所有能力
        extra_capabilities = [
            Capability(
                name=f"analysis_{task_type}",
                description=f"分析能力: {task.description[:50]}",
                keywords=task_keywords + ["分析", "评估"],
                expertise_level=0.8,
            ),
            Capability(
                name=f"execution_{task_type}",
                description=f"执行能力: {task.description[:50]}",
                keywords=task_keywords + ["执行", "处理"],
                expertise_level=0.8,
            ),
            Capability(
                name=f"review_{task_type}",
                description=f"评审能力: {task.description[:50]}",
                keywords=task_keywords + ["评审", "质量"],
                expertise_level=0.85,
            ),
            Capability(
                name=f"research_{task_type}",
                description=f"研究能力: {task.description[:50]}",
                keywords=task_keywords + ["研究", "检索"],
                expertise_level=0.75,
            ),
            Capability(
                name=f"integration_{task_type}",
                description=f"整合能力: {task.description[:50]}",
                keywords=task_keywords + ["整合", "汇总"],
                expertise_level=0.8,
            ),
        ]

        self.capabilities = self._default_capabilities() + extra_capabilities
        logger.info(
            f"WorkAgent {self.agent_id} 已适配任务: {task_type} "
            f"(完整能力: 基础+分析/执行/评审/研究/整合)"
        )

    # ── SharedBus 监听 ─────────────────────────────────────────────────

    async def _start_bus_listener(self, enable: bool = False) -> None:
        """启动 SharedBus 监听 — 处理发送给本 Agent 的直接消息

        安全处理 SharedBus 不可用的情况（不崩溃）。
        """
        if not enable:
            return
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, Message
            bus = get_shared_bus()
        except Exception:
            logger.debug("SharedBus 不可用，跳过总线监听")
            return

        async def _listen_loop():
            """持续监听直接消息 — 带休眠防忙循环"""
            while True:
                try:
                    msg = await bus.receive_direct(self.agent_id, timeout=2.0)
                    if msg is None:
                        await asyncio.sleep(0.5)  # 避免空队列忙循环
                        continue
                    self._on_bus_message(msg)
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(0.5)
                    pass

        self._bus_listener_task = asyncio.create_task(_listen_loop())
        logger.debug(f"SharedBus 监听已启动: {self.agent_id}")

    def _stop_bus_listener(self) -> None:
        """停止 SharedBus 监听"""
        if self._bus_listener_task is not None and not self._bus_listener_task.done():
            self._bus_listener_task.cancel()
            self._bus_listener_task = None
            logger.debug(f"SharedBus 监听已停止: {self.agent_id}")

    def _on_bus_message(self, msg: "Message") -> None:
        """处理收到的总线消息 — 子类可覆盖"""
        logger.debug(f"收到总线消息: {msg.type} 来自 {msg.sender}")

    # ── 执行入口 ───────────────────────────────────────────────────────

    async def execute(self, task: Task) -> ActionResult:
        """执行任务 - 统一的执行入口

        统一走 _execute_fast 快路径（ReAct 直通）。
        """
        return await self._execute_fast(task)

    async def _execute_fast(self, task: Task) -> ActionResult:
        """轻量执行 — 直通 ReAct 快路径"""
        logger.info(f"WorkAgent [轻量] 执行任务: {task.task_id} ({task.type})")
        start = time.time()
        desc = task.description

        # ── 初始状态提示 ──
        print(f"\n    \033[1;36m⚡ 开始任务: {desc[:80]}\033[0m")

        # 启动总线监听
        await self._start_bus_listener()

        try:
            # ── 简单对话检测：30字以内且不含工具关键词 → 直接LLM调用 ──
            _TOOL_KW = ["搜索","查找","写","创建","生成","分析","报告","爬",
                        "保存","文件","数据","代码","游戏","脚本","curl","fetch",
                        "http","api","百度","谷歌","翻译"]
            is_simple = len(desc) < 30 and not any(kw in desc for kw in _TOOL_KW)
            logger.info("WorkAgent 分析 desc=%d is_simple=%s", len(desc), is_simple)
            if is_simple:
                from core.engine.llm_backend import get_llm_router
                router = get_llm_router()
                if router and router.is_available():
                    print(f"    \033[1;36m\U0001f914 LLM直接回答...\033[0m")
                    logger.info("WorkAgent 直接LLM提问")
                    resp = await router.chat([{"role": "user", "content": desc}])
                    answer = str(resp) if resp else ""
                    elapsed = time.time() - start
                    is_mock = "[LLM_MOCK]" in answer
                    logger.info("WorkAgent 直接回复 mock=%s len=%d: %s", is_mock, len(answer), answer[:100])
                    return ActionResult(
                        success=bool(answer) and not is_mock,
                        output=answer if not is_mock else "LLM暂不可用，请稍后重试",
                        execution_time=elapsed,
                        metadata={"light_mode": True, "direct_reply": True, "mock": is_mock},
                    )

            # ── 复杂任务：走 ReActCore 中间件链 ──
            logger.info("WorkAgent → ReActCore (max_rounds=%d)", 2 if self._light_mode else 10)
            from core.multi_agent_v2.agents.react_core import run_react
            result = await run_react(
                desc,
                max_rounds=2 if self._light_mode else 10,
                model=task.context.get("model", ""),
                personality_prompt=self.system_prompt_for_role(),
                agent=self,
            )

            elapsed = time.time() - start
            success = result.get("success", False)
            output = result.get("answer", "")
            error = result.get("error", "")

            ar = ActionResult(
                success=success,
                output=str(output) if output else None,
                error=error,
                execution_time=elapsed,
                metadata={"light_mode": True, "iterations": result.get("iterations", 0)},
            )

            # 记录工作历史
            self.work_history.append({
                "task_id": task.task_id,
                "task_type": task.type,
                "success": success,
                "execution_time": elapsed,
                "timestamp": time.time(),
            })
            # 保持最近的记录
            if len(self.work_history) > 100:
                self.work_history = self.work_history[-100:]

            logger.info(f"WorkAgent [轻量] 完成: success={success} {elapsed:.1f}s")
            return ar

        except Exception as e:
            logger.error(f"WorkAgent [轻量] 异常: {e}")
            return ActionResult(success=False, error=str(e), execution_time=time.time() - start)
        finally:
            self._stop_bus_listener()

    def get_work_stats(self) -> Dict[str, Any]:
        """获取工作统计"""
        if not self.work_history:
            return {"total_tasks": 0}

        total = len(self.work_history)
        successful = sum(1 for r in self.work_history if r.get("success"))
        by_type: Dict[str, int] = {}
        for r in self.work_history:
            t = r.get("task_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "total_tasks": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "by_type": by_type,
        }
