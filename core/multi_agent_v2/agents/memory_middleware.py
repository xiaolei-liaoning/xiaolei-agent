"""
MemoryMiddleware — V2 全量记忆接入

将 V1 已有的短期记忆、向量记忆、自我进化引擎接入 V2 MiddlewareChain。

三阶段钩子：
  on_think_start  — 加载短期+向量记忆 → 注入到 knowledge_context
  on_tool_end     — 记录工具执行经验到 temp_memory
  on_finish       — 持久化 + 触发自进化

设计原则：
- 短期记忆始终可用（纯文件 I/O，无风险）
- 向量记忆 / 自进化按需懒加载（Chromadb 故障不影响主线）
- 所有异常被 try/except 兜底，不中断 ReAct 循环

重要：
- 不通过 'core.memory' 包导入（__init__.py 自动加载 Chromadb 导致死循环）
- 用 importlib.spec_from_file_location 绕过包导入
"""

import asyncio
import importlib.util
import logging
import os
import time
from typing import Any, Dict, List

from .middleware import BaseMiddleware, RunContext, HookResult

logger = logging.getLogger(__name__)

_DEFAULT_USER_ID = "v2_cli"

# ── 记忆模块文件路径（绕过 core.memory.__init__.py 的自动 Chromadb 加载）──
# memory_middleware.py → core/multi_agent_v2/agents/ → 上3级到项目根
_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_FILE_DIR)))
_MEMORY_DIR = os.path.join(_PROJECT_ROOT, "core", "memory")
_STM_PATH = os.path.join(_MEMORY_DIR, "short_term_memory.py")
_VM_PATH = os.path.join(_MEMORY_DIR, "vector_memory.py")
_EVOLUTION_PATH = os.path.join(_MEMORY_DIR, "self_evolution.py")


def _load_module(path: str, name: str):
    """从文件路径加载 Python 模块（绕过包 __init__.py）"""
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=[])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MemoryMiddleware(BaseMiddleware):
    """记忆中间件 — 在 ReAct 各阶段存取持久化记忆"""
    HOOKS = ("on_start", "on_think_start", "on_tool_end", "on_finish")
    MEMORY_PREFIX = "── 记忆上下文 ──"

    def __init__(self, user_id: str = _DEFAULT_USER_ID):
        super().__init__()
        self._user_id = user_id
        # 短期记忆（纯文件，始终可用）
        self._stm = None
        # 向量记忆 + 自进化（按需懒加载，故障后标记不再重试）
        self._vm = None
        self._vm_broken = False
        self._evolution = None
        self._evolution_broken = False
        # 状态跟踪
        self._last_query = ""
        self._tool_experiences: List[Dict] = []
        self._start_time = 0.0

    # ── 懒加载 ─────────────────────────────────────────────

    def _ensure_stm(self) -> bool:
        if self._stm is not None:
            return True
        try:
            if not os.path.isfile(_STM_PATH):
                return False
            mod = _load_module(_STM_PATH, "short_term_memory")
            self._stm = mod.ShortTermMemoryManager()
            return True
        except Exception as e:
            logger.warning(f"短期记忆不可用: {e}")
            return False

    def _ensure_vm(self) -> bool:
        if self._vm_broken:
            return False
        if self._vm is not None:
            return True
        try:
            if not os.path.isfile(_VM_PATH):
                self._vm_broken = True
                return False
            mod = _load_module(_VM_PATH, "vector_memory")
            self._vm = mod.VectorMemoryStore()
            return True
        except Exception as e:
            logger.warning(f"向量记忆不可用（降级）: {e}")
            self._vm_broken = True
            return False

    def _ensure_evolution(self) -> bool:
        if self._evolution_broken:
            return False
        if self._evolution is not None:
            return True
        try:
            if not os.path.isfile(_EVOLUTION_PATH):
                self._evolution_broken = True
                return False
            mod = _load_module(_EVOLUTION_PATH, "self_evolution")
            self._evolution = mod.SelfEvolutionEngine()
            return True
        except Exception as e:
            logger.debug(f"自进化引擎不可用（降级）: {e}")
            self._evolution_broken = True
            return False

    # ── on_start ───────────────────────────────────────────

    async def on_start(self, ctx: RunContext) -> None:
        self._start_time = time.time()
        self._tool_experiences.clear()
        self._last_query = ""
        self._ensure_stm()

    # ── on_think_start — 记忆注入 ──────────────────────────

    async def on_think_start(self, ctx: RunContext) -> None:
        """在 LLM 思考前注入短期+长期记忆

        策略：
        - 首次用户输入：向量搜索 + 短期记忆
        - 后续 ReAct 循环：只读短期记忆（避免重复向量搜索）
        """
        user_input = ctx.task_description
        if not user_input:
            return

        memory_lines = []

        # 1. 短期记忆（每次都读）
        if self._stm is not None:
            try:
                short_term = self._stm.get_context(self._user_id)
                if short_term:
                    memory_lines.append("[短期上下文]")
                    for msg in short_term[-3:]:
                        role = msg.get("role", "?")
                        content = msg.get("content", "")
                        memory_lines.append(f"  [{role}] {content[:200]}")
            except Exception as e:
                logger.debug(f"短期记忆读取失败: {e}")

        # 2. 向量记忆（仅新输入时搜索）
        is_new_query = (user_input != self._last_query)
        if is_new_query and self._ensure_vm():
            try:
                memories = self._vm.search_memories(
                    query=user_input,
                    user_id=self._user_id if self._user_id else None,
                    top_k=5,
                )
                if memories:
                    memory_lines.append("\n[长期记忆 — 相关历史]")
                    for i, m in enumerate(memories[:5], 1):
                        content = m.get("content", "")
                        meta = m.get("metadata", {})
                        cat = meta.get("category", "general")
                        ts = (meta.get("timestamp", "")[:16]
                              if meta.get("timestamp") else "")
                        line = content[:150].replace("\n", " ")
                        memory_lines.append(f"  {i}. [{cat}] {line}")
                        if ts:
                            memory_lines[-1] += f"  ({ts})"
                self._last_query = user_input
            except Exception as e:
                logger.debug(f"向量记忆检索失败: {e}")

        # 3. 注入到 knowledge_context
        if len(memory_lines) > 1:
            inject_text = "\n".join(memory_lines)
            serialized = f"\n{self.MEMORY_PREFIX}\n{inject_text}\n──"
            ctx.knowledge_context += serialized
            if len(ctx.knowledge_context) > 3000:
                ctx.knowledge_context = ctx.knowledge_context[-3000:]

    # ── on_tool_end — 经验记录 ─────────────────────────────

    async def on_tool_end(self, ctx: RunContext) -> None:
        if not ctx.tool_results:
            return
        latest = ctx.tool_results[-1]
        if not latest:
            return

        tc = latest.get("tool_call", {})
        exp = {
            "tool": tc.get("name", "?"),
            "success": latest.get("success", False),
            "result_summary": str(latest.get("result", ""))[:200],
            "iteration": ctx.iteration,
            "timestamp": time.time(),
        }
        self._tool_experiences.append(exp)

        if self.agent is not None:
            self.agent.temp_memory["memory_experiences"] = self._tool_experiences[-10:]

    # ── on_finish — 持久化 + 自进化 ───────────────────────

    async def on_finish(self, ctx: RunContext) -> None:
        """任务结束时持久化记忆并触发自我进化"""
        final_answer = ctx.final_answer
        if not final_answer:
            return

        # 1. 写入短期记忆
        if self._ensure_stm():
            try:
                self._stm.add(self._user_id, "user", ctx.task_description)
                self._stm.add(self._user_id, "assistant", final_answer[:2000])
            except Exception as e:
                logger.warning(f"短期记忆写入失败: {e}")

        # 2. 写入向量记忆
        if self._ensure_vm():
            try:
                qa_text = f"Q: {ctx.task_description}\nA: {final_answer[:1000]}"
                self._vm.add_memory(
                    user_id=self._user_id,
                    content=qa_text,
                    category="experience",
                    metadata={
                        "iterations": ctx.react_depth,
                        "success": bool(ctx.final_answer),
                        "tool_count": len(ctx.tool_results),
                    },
                )
            except Exception as e:
                logger.warning(f"向量记忆写入失败: {e}")

        # 3. 持久化反思/KEPA 摘要
        if self._ensure_vm() and self.agent is not None:
            try:
                reflection = self.agent.temp_memory.get("reflection", {})
                if reflection:
                    self._vm.add_memory(
                        user_id=self._user_id,
                        content=str(reflection.get("problem", ""))[:500],
                        category="insight",
                        metadata={
                            "source": "reflection",
                            "suggestion": str(reflection.get("suggestion", ""))[:200],
                        },
                    )
                kepa = self.agent.temp_memory.get("kepa_summary", {})
                if kepa:
                    self._vm.add_memory(
                        user_id=self._user_id,
                        content=(f"工具 {kepa.get('tool','?')}: "
                                 f"{kepa.get('summary','')}"),
                        category="experience",
                        metadata={"source": "kepa",
                                  "iteration": kepa.get("iteration", 0)},
                    )
            except Exception as e:
                logger.debug(f"反思/KEPA 持久化失败: {e}")

        # 4. 触发自我进化
        if self._ensure_evolution():
            try:
                await self._evolution.check_and_evolve(
                    user_id=self._user_id,
                    new_experience_count=len(self._tool_experiences),
                )
            except Exception as e:
                logger.debug(f"自我进化触发失败: {e}")

        elapsed = time.time() - self._start_time
        logger.info(
            "记忆持久化完成: 经验=%d条, 短期=%s, 向量=%s, 耗时=%.1fs",
            len(self._tool_experiences),
            "ok" if self._stm is not None else "off",
            "ok" if self._vm is not None else "off",
            elapsed,
        )
