"""豆包对话处理器（工业级）

通过 LLMRouter 统一接口进行对话，支持：
- 角色扮演（system_prompt 定制）
- 对话历史管理（可选 Redis 持久化）
- 异步对话（async/await）
- 同步兼容（ToolManager 调用）

设计要点：
- 完整类型注解与 docstring
- 异常隔离（LLM 不可用时优雅降级）
- 连接复用（LLMRouter 单例）
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class DoubaoChatHandler:
    """豆包 AI 对话处理器。

    使用 LLMRouter 统一后端进行对话，支持角色扮演和上下文管理。
    提供 execute_sync / execute 异步两个入口，兼容 ToolManager 调用。
    """

    # 内置角色 system_prompt
    _SYSTEM_PROMPTS: Dict[str, str] = {
        "default": "你是豆包AI助手，友好、简洁地回答用户问题。回答要有深度，善于总结。",
        "creative": "你是一个富有创造力的AI助手，擅长创意写作和头脑风暴。",
        "professional": "你是一个专业的技术顾问，擅长编程、架构设计和技术分析。",
    }

    def __init__(self) -> None:
        self._router: Optional[Any] = None
        try:
            from core.short_term_memory import ShortTermMemoryManager
            self._memory_manager = ShortTermMemoryManager(window_size=10)
            self._use_new_memory = True
            logger.info("使用新的 ShortTermMemoryManager 管理对话历史")
        except ImportError:
            self._conversation_history: Dict[str, List[Dict[str, str]]] = {}
            self._max_history: int = 20
            self._use_new_memory = False
            logger.warning("未找到 ShortTermMemoryManager，使用传统对话历史管理")
        logger.info("DoubaoChatHandler 初始化完成")

    # ------------------------------------------------------------------
    # 核心入口
    # ------------------------------------------------------------------

    async def execute(
        self,
        message: str = "",
        role: str = "default",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """异步对话入口。

        Args:
            message: 用户消息
            role:    角色标识（default / creative / professional）
            **kwargs: 额外参数（user_id / system_prompt 等）

        Returns:
            包含 success / reply / action 的字典
        """
        if not message:
            return {"success": False, "error": "未指定消息", "action": "doubao_chat"}

        user_id: str = str(kwargs.get("user_id", "anonymous"))
        custom_prompt: Optional[str] = kwargs.get("system_prompt")

        system_prompt: str = custom_prompt or self._SYSTEM_PROMPTS.get(
            role, self._SYSTEM_PROMPTS["default"]
        )

        try:
            router = self._get_router()
            if router is None:
                return {
                    "success": False,
                    "error": "LLM 后端未配置",
                    "reply": "豆包对话功能暂不可用，请检查 LLM 配置。",
                    "action": "doubao_chat",
                }

            # 构建消息列表（含上下文）
            messages: List[Dict[str, str]] = self._build_messages(
                user_id, system_prompt, message
            )

            # 调用 LLM
            reply: str = await router.chat(messages)

            # 保存对话历史
            self._save_history(user_id, message, reply)

            logger.info("豆包对话完成，用户: %s，消息长度: %d", user_id, len(message))
            return {
                "success": True,
                "reply": reply,
                "action": "doubao_chat",
                "role": role,
            }

        except Exception as e:
            logger.error("豆包对话失败: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "action": "doubao_chat",
            }

    def execute_sync(
        self,
        message: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """同步对话入口（兼容 ToolManager 直接调用）。

        Args:
            message: 用户消息
            **kwargs: 额外参数

        Returns:
            包含 success / reply / action 的字典
        """
        if not message:
            return {"success": False, "error": "未指定消息", "action": "doubao_chat"}

        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # 在已有事件循环中，用 run_in_executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, self.execute(message=message, **kwargs)
                    )
                    return future.result(timeout=60)
            else:
                return asyncio.run(self.execute(message=message, **kwargs))

        except Exception as e:
            logger.error("豆包同步对话失败: %s", e)
            return {"success": False, "error": str(e), "action": "doubao_chat"}

    # ------------------------------------------------------------------
    # 对话历史管理
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        user_id: str,
        system_prompt: str,
        user_message: str,
    ) -> List[Dict[str, str]]:
        """构建发送给 LLM 的消息列表，包含历史上下文。

        Args:
            user_id:       用户标识
            system_prompt: 系统提示词
            user_message:  当前用户消息

        Returns:
            消息列表 [{"role": "...", "content": "..."}]
        """
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

        # 使用新的记忆管理系统
        if self._use_new_memory:
            # 获取历史上下文
            history_messages = self._memory_manager.get_context(user_id, depth=2)
            messages.extend(history_messages)
        else:
            # 传统方式
            history: List[Dict[str, str]] = self._conversation_history.get(user_id, [])
            if history:
                # 限制上下文长度
                truncated = history[-self._max_history:]
                messages.extend(truncated)

        # 当前消息
        messages.append({"role": "user", "content": user_message})

        return messages

    def _save_history(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: str,
    ) -> None:
        """保存对话到内存历史。

        Args:
            user_id:         用户标识
            user_message:    用户消息
            assistant_reply: 助手回复
        """
        # 使用新的记忆管理系统
        if self._use_new_memory:
            # 保存用户消息
            self._memory_manager.add_context(user_id, user_message, "user_message")
            # 保存助手回复
            self._memory_manager.add_context(user_id, assistant_reply, "assistant_reply")
        else:
            # 传统方式
            if user_id not in self._conversation_history:
                self._conversation_history[user_id] = []

            history = self._conversation_history[user_id]
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": assistant_reply})

            # 限制历史长度
            if len(history) > self._max_history * 2:
                self._conversation_history[user_id] = history[-self._max_history * 2:]

    def clear_history(self, user_id: str) -> None:
        """清除指定用户的对话历史。

        Args:
            user_id: 用户标识
        """
        if self._use_new_memory:
            self._memory_manager.clear_context(user_id)
        else:
            self._conversation_history.pop(user_id, None)
        logger.info("已清除用户 %s 的对话历史", user_id)

    def get_history(self, user_id: str) -> List[Dict[str, str]]:
        """获取指定用户的对话历史。

        Args:
            user_id: 用户标识

        Returns:
            历史消息列表
        """
        if self._use_new_memory:
            return self._memory_manager.get_context(user_id, depth=3)
        else:
            return list(self._conversation_history.get(user_id, []))

    # ------------------------------------------------------------------
    # 延迟加载
    # ------------------------------------------------------------------

    def _get_router(self) -> Optional[Any]:
        """延迟加载 LLMRouter 单例。"""
        if self._router is None:
            try:
                from core.llm_backend import get_llm_router
                self._router = get_llm_router()
                if not self._router.is_available():
                    logger.warning("LLM 后端不可用，豆包对话功能受限")
            except ImportError as e:
                logger.warning("LLM 后端未加载: %s", e)
        return self._router


# ---------------------------------------------------------------------------
# 模块级单例（供 ToolManager 注册）
# ---------------------------------------------------------------------------
doubao_handler = DoubaoChatHandler()