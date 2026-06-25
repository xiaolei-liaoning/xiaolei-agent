# core/memory/memory_middleware.py
"""记忆中间件 — 统一所有路径的记忆读写

V1/V2 共用入口：
  - get_user_context → 短期记忆 + 用户画像 + RAG 向量搜索
  - process_turn     → 短期记忆写入（自动4层压缩）+ 事实提取 + 画像更新 + 向量记忆写入
"""

import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MemoryMiddleware:
    """统一记忆读写中间件"""

    def __init__(self):
        self._profile_cache: Dict[str, object] = {}

    async def get_user_context(self, user_id: str, message: str) -> str:
        """获取用户上下文（短期对话 + 画像 + RAG 相关记忆）"""
        parts = []

        # 1. 短期记忆（最近对话）
        try:
            from .short_term_memory import ShortTermMemoryManager
            stm = ShortTermMemoryManager()
            short_term = stm.get_context(user_id)
            if short_term:
                lines = ["[最近对话]"]
                for msg in short_term[-5:]:
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    lines.append(f"  [{role}] {content[:200]}")
                parts.append("\n".join(lines))
        except Exception as e:
            logger.debug("短期记忆读取失败: %s", e)

        # 2. 用户画像
        try:
            from .user_profile import get_user_profile
            profile = get_user_profile(user_id)
            profile_block = profile.to_system_prompt_block()
            if profile_block:
                parts.append(profile_block)
        except Exception as e:
            logger.debug("获取用户画像失败: %s", e)

        # 3. RAG 向量记忆搜索
        try:
            from .vector_memory import VectorMemoryStore
            vm = VectorMemoryStore()
            if vm.wait_for_collection(timeout=3.0):
                memories = vm.search_memories(
                    query=message,
                    user_id=user_id,
                    top_k=5,
                )
                if memories:
                    mem_lines = []
                    for m in memories:
                        cat = m.get("metadata", {}).get("category", "")
                        if cat in ("fact", "preference", "personal_info", "experience", "analysis", "insight"):
                            mem_lines.append(f"- {m['content'][:150]}")
                    if mem_lines:
                        parts.append("【相关记忆】\n" + "\n".join(mem_lines))
        except Exception as e:
            logger.debug("搜索向量记忆失败: %s", e)

        return "\n\n".join(parts) if parts else ""

    async def process_turn(self, user_id: str, user_message: str, assistant_reply: str) -> None:
        """对话结束后：短期记忆写入 → 提取事实 → 更新画像 → 存入向量记忆"""
        # 0. 短期记忆写入（自动触发 4 层压缩链）
        try:
            from .short_term_memory import ShortTermMemoryManager
            stm = ShortTermMemoryManager()
            stm.add(user_id, "user", user_message)
            if assistant_reply:
                stm.add(user_id, "assistant", assistant_reply[:2000])
        except Exception as e:
            logger.debug("短期记忆写入失败: %s", e)

        # 1. 事实提取
        try:
            from .fact_extractor import get_fact_extractor
            extractor = get_fact_extractor()
            facts = await extractor.extract(user_message)

            if not facts:
                return

            from .user_profile import get_user_profile
            profile = get_user_profile(user_id)

            for fact in facts:
                ftype = fact.get("type", "fact")
                content = fact.get("content", "")
                if not content:
                    continue

                if ftype == "name":
                    name = content.replace("用户姓名是", "").replace("用户叫", "").strip()
                    if name and len(name) < 20:
                        profile.name = name
                        logger.info("用户画像更新: 姓名=%s", name)
                elif ftype == "preference":
                    if profile.add_preference(content):
                        logger.info("用户画像更新: 偏好=%s", content[:30])
                else:
                    if profile.add_fact(content):
                        logger.info("用户画像更新: 事实=%s", content[:30])

            try:
                from .vector_memory import VectorMemoryStore
                vm = VectorMemoryStore()
                if vm.wait_for_collection(timeout=3.0):
                    for fact in facts:
                        content = fact.get("content", "")
                        ftype = fact.get("type", "fact")
                        if content:
                            vm.add_memory(
                                user_id=user_id,
                                content=content,
                                category=ftype if ftype != "name" else "fact",
                                metadata={"source": "auto_extract", "type": ftype},
                            )
            except Exception as e:
                logger.debug("向量记忆写入失败: %s", e)

        except Exception as e:
            logger.debug("记忆处理失败: %s", e)


_middleware: Optional[MemoryMiddleware] = None


def get_memory_middleware() -> MemoryMiddleware:
    global _middleware
    if _middleware is None:
        _middleware = MemoryMiddleware()
    return _middleware
