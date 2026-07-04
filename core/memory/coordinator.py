"""MemoryCoordinator — 统一协调三层记忆存储

职责：
  1. 单入口：MemoryMiddleware 只调 coordinator，不直接调三层
  2. 交叉引用：STM←→Session←→Vector 互相感知
  3. 去重：同一数据不写多次
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TRIVIAL_TOOLS = {"read_file", "write_todos", "search_files", "grep", "execute_shell"}


class MemoryCoordinator:
    """协调 STM + Session + Vector 三层记忆"""

    def __init__(self):
        self._stm = None
        self._session_mgr = None
        self._session_idx = None
        self._cache_profile = ""
        self._cache_vector = ""
        self._cache_meta = ""
        self._cache_session_block = ""

    # ── 工具执行记录（每轮 on_tool_end）──

    async def record_tool(self, tool_name: str, success: bool,
                          result_raw: Any, round_idx: int,
                          is_subagent: bool = False) -> Optional[str]:
        """记录一次工具执行到三层记忆，返回 artifact 路径（如有）"""
        artifact_path = None

        # 1. 始终 → STM 摘要
        stm_summary = self._stm_summary(tool_name, success, result_raw)
        if stm_summary:
            stm = self._get_stm()
            if stm:
                try:
                    await stm.add_async("cli_user", "assistant", stm_summary)
                except Exception as e:
                    logger.debug(f"STM add failed: {e}")

        # 2. 非琐碎工具 + 非子代理 → Session artifact
        if success and not is_subagent and tool_name not in _TRIVIAL_TOOLS:
            from core.multi_agent_v2.tools.tool_result import from_handler
            text = from_handler(result_raw)
            if len(text) > 200:
                session = self._get_session()
                if session:
                    try:
                        artifact_path = session.record_artifact(
                            f"tool_{tool_name}_round_{round_idx}",
                            f"## {tool_name} Result\n\n{text[:3000]}",
                        )
                    except Exception as e:
                        logger.debug(f"Session artifact failed: {e}")

        return artifact_path

    # ── 会话结束（on_finish）──

    async def finalize(self, user_id: str, task: str,
                       final_answer: str, is_subagent: bool = False):
        """结束会话，统一写入三层记忆"""
        if not final_answer:
            return

        if not is_subagent:
            # 1. STM process_turn（写对话+提取事实+写向量+更新画像）
            try:
                from core.memory.memory_middleware import get_memory_middleware
                v1_mw = get_memory_middleware()
                await v1_mw.process_turn(user_id, task, final_answer)
                logger.info("STM process_turn 完成")
            except Exception as e:
                logger.debug(f"STM process_turn failed: {e}")

        # 2. Session 结束
        session = self._get_session()
        if session and session.current_session_id:
            try:
                if not is_subagent:
                    session.record_artifact("final_answer",
                                            f"# Final Answer\n\n{final_answer}")
                summary = final_answer[:500]
                session.finalize_session(summary)
                logger.info("Session finalized")
            except Exception as e:
                logger.debug(f"Session finalize failed: {e}")

            # 3. 向量索引（仅主代理）
            if not is_subagent:
                idx = self._get_session_idx()
                if idx:
                    try:
                        idx.add_session(session.current_session_id, summary, task)
                        logger.info("Session indexed to vector DB")
                    except Exception as e:
                        logger.debug(f"Vector index failed: {e}")

    # ── 内部辅助 ──

    def _stm_summary(self, tool_name: str, success: bool, result_raw: Any) -> str:
        prefix = f"[工具执行: {tool_name}] "
        if success:
            text = str(result_raw)
            # ponytail: 从 result 中提取可读文本
            if isinstance(text, str) and len(text) > 300:
                text = text[:300]
            return prefix + text
        error = getattr(result_raw, 'get', lambda k, d='': d)('error', '')
        return prefix + f"失败: {str(error)[:200]}"

    def _get_stm(self):
        if self._stm is None:
            try:
                from core.memory.short_term_memory import get_memory_manager
                self._stm = get_memory_manager()
            except Exception:
                pass
        return self._stm

    def _get_session(self):
        if self._session_mgr is None:
            try:
                from core.memory.session_manager import get_session_manager
                self._session_mgr = get_session_manager()
            except Exception:
                pass
        return self._session_mgr

    def _get_session_idx(self):
        if self._session_idx is None:
            try:
                from core.memory.session_vector_index import get_session_index
                self._session_idx = get_session_index()
            except Exception:
                pass
        return self._session_idx

    # ── 统一读路径 ──

    async def get_context_for_llm(self, user_id: str, user_input: str) -> str:
        """从三层记忆读取上下文（STM 每轮新鲜，其余缓存）"""
        sections = []

        # 1. 短期记忆（每轮新鲜——工具结果在追加）
        try:
            from core.memory.short_term_memory import get_memory_manager
            _stm = get_memory_manager()
            short_term = _stm.get_context(user_id)
            if short_term:
                lines = ["<memory type=short_term>"]
                for msg in short_term[-5:]:
                    role = msg.get("role", "?")
                    content = msg.get("content", "")[:200]
                    lines.append(f"  [{role}] {content}")
                lines.append("</memory>")
                sections.append("\n".join(lines))
        except Exception:
            pass

        # 2-5：会话内不变的，读一次缓存
        if not self._cache_profile:
            try:
                from core.memory.user_profile import get_user_profile
                profile = get_user_profile(user_id)
                block = profile.to_system_prompt_block()
                if block:
                    self._cache_profile = f"<memory type=profile>\n{block}\n</memory>"
            except Exception:
                pass
        if self._cache_profile:
            sections.append(self._cache_profile)

        if not self._cache_vector:
            try:
                from core.memory.vector_memory import VectorMemoryStore
                vm = VectorMemoryStore()
                if vm.wait_for_collection(timeout=3.0):
                    memories = vm.search_memories(query=user_input, user_id=user_id, top_k=5)
                    if memories:
                        lines = ["<memory type=vector>"]
                        for m in memories:
                            cat = m.get("metadata", {}).get("category", "")
                            if cat in ("fact", "preference", "experience", "insight"):
                                lines.append(f"  [{cat}] {m['content'][:150]}")
                        lines.append("</memory>")
                        self._cache_vector = "\n".join(lines)
            except Exception:
                pass
        if self._cache_vector:
            sections.append(self._cache_vector)

        if not self._cache_meta:
            try:
                if self._stm is None:
                    from core.memory.short_term_memory import get_memory_manager
                    self._stm = get_memory_manager()
                _meta = self._stm.get_summary(user_id)
                if _meta and len(_meta) > 20:
                    self._cache_meta = f"<memory type=meta>\n{_meta[:500]}\n</memory>"
            except Exception:
                pass
        if self._cache_meta:
            sections.append(self._cache_meta)

        if not self._cache_session_block:
            try:
                if self._session_mgr is None:
                    from core.memory.session_manager import get_session_manager
                    self._session_mgr = get_session_manager()
                block = self._session_mgr.build_context_block(n=3)
                if block:
                    self._cache_session_block = block
            except Exception:
                pass
        if self._cache_session_block:
            sections.append(self._cache_session_block)

        return "\n\n".join(sections)


_COORDINATOR: Optional[MemoryCoordinator] = None


def get_coordinator() -> MemoryCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = MemoryCoordinator()
    return _COORDINATOR
