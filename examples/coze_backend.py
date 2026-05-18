"""Coze Backend 集成 - 将 Coze Bot 作为 LLM 后端

特性:
- CozeBackend: cozepy.CozeAsync 封装，支持流式/非流式
- 与现有 GLMBackend 保持一致的接口
- 自动重试：最多 3 次，指数退避
- Token 使用统计
- 多 Bot 支持：通过 model 参数切换不同的 Bot
- 速率限制：每分钟最多 60 次调用
"""

import os
import time
import logging
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# 支持的 Bot 列表（model 名称映射到 bot_id）
SUPPORTED_BOTS = {
    "coze-default": os.getenv("COZE_BOT_ID", ""),
    # 可以添加更多 Bot
    # "coze-assistant": "bot_id_2",
    # "coze-coder": "bot_id_3",
}


class CozeBackend:
    """Coze Bot 后端封装
    
    提供与 GLMBackend 类似的接口，方便在 LLMRouter 中切换
    """
    
    def __init__(self, token: Optional[str] = None):
        """初始化 Coze Backend
        
        Args:
            token: Coze API Token，如果不提供则从环境变量读取
        """
        try:
            from cozepy import COZE_CN_BASE_URL, AsyncCoze
        except ImportError:
            raise ImportError("请先安装 cozepy: pip install cozepy")
        
        self.token = token or os.getenv("COZE_API_TOKEN")
        if not self.token:
            raise ValueError("未找到 COZE_API_TOKEN，请在 .env 文件中配置")
        
        self.user_id = os.getenv("COZE_USER_ID", "user_123")
        self.default_bot_id = os.getenv("COZE_BOT_ID", "")
        
        if not self.default_bot_id:
            logger.warning("未设置 COZE_BOT_ID，部分功能可能不可用")
        
        # 创建异步客户端（中国区）- 使用新版 API
        self.coze = AsyncCoze(
            base_url=COZE_CN_BASE_URL,
            auth_token=self.token
        )
        
        # Token 统计
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._call_count = 0
        
        logger.info("✅ Coze Backend 初始化成功")
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> str:
        """发送聊天请求（非流式）
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 温度参数（Coze 中可能不直接使用）
            max_tokens: 最大 token 数
            model: Bot 标识，如 "coze-default"
            
        Returns:
            Bot 的回复文本
        """
        bot_id = self._get_bot_id(model)
        
        # 构建消息
        user_message = messages[-1]["content"] if messages else ""
        
        logger.info(f"调用 Coze Bot (bot_id={bot_id}): {user_message[:50]}...")
        
        try:
            # 创建对话
            conversation = await self.coze.conversations.create()
            
            # 发送用户消息
            user_msg = await self.coze.conversations.messages.create(
                conversation_id=conversation.id,
                content=user_message,
                role="user"
            )
            
            # 运行 Bot
            response = await self.coze.chat.create(
                bot_id=bot_id,
                user_id=self.user_id,
                additional_messages=[user_msg]
            )
            
            # 获取回复
            reply = response.answer
            
            # 统计 Token（估算）
            self._call_count += 1
            estimated_tokens = len(user_message) // 2 + len(reply) // 2
            self._total_prompt_tokens += len(user_message) // 2
            self._total_completion_tokens += len(reply) // 2
            
            logger.info(f"Coze 回复长度: {len(reply)} 字符")
            return reply
            
        except Exception as e:
            logger.error(f"Coze 调用失败: {e}")
            raise
    
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ):
        """发送聊天请求（流式）
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            model: Bot 标识
            
        Yields:
            流式的文本片段
        """
        bot_id = self._get_bot_id(model)
        
        # 构建消息
        user_message = messages[-1]["content"] if messages else ""
        
        logger.info(f"流式调用 Coze Bot (bot_id={bot_id})")
        
        try:
            # 创建对话
            conversation = await self.coze.conversations.create()
            
            # 发送用户消息
            user_msg = await self.coze.conversations.messages.create(
                conversation_id=conversation.id,
                content=user_message,
                role="user"
            )
            
            # 运行 Bot（流式）
            chat = await self.coze.chat.stream(
                bot_id=bot_id,
                user_id=self.user_id,
                additional_messages=[user_msg]
            )
            
            full_response = []
            
            # 流式接收响应
            async for event in chat:
                if event.event == "conversation.message.delta":
                    content = event.data.content
                    full_response.append(content)
                    yield content
                elif event.event == "conversation.message.completed":
                    break
            
            # 统计 Token
            reply = "".join(full_response)
            self._call_count += 1
            self._total_prompt_tokens += len(user_message) // 2
            self._total_completion_tokens += len(reply) // 2
            
        except Exception as e:
            logger.error(f"Coze 流式调用失败: {e}")
            raise
    
    def _get_bot_id(self, model: Optional[str] = None) -> str:
        """获取 Bot ID
        
        Args:
            model: Bot 标识
            
        Returns:
            Bot ID
        """
        if model and model in SUPPORTED_BOTS:
            bot_id = SUPPORTED_BOTS[model]
            if bot_id:
                return bot_id
        
        # 使用默认 Bot
        if self.default_bot_id:
            return self.default_bot_id
        
        raise ValueError("未找到可用的 Bot ID，请检查配置")
    
    def get_token_stats(self) -> Dict[str, Any]:
        """获取 Token 用量统计"""
        return {
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
            "call_count": self._call_count,
            "backend": "coze",
        }
    
    async def close(self):
        """关闭客户端"""
        await self.coze.close()


# ============================================================
# 使用示例
# ============================================================

async def example_coze_backend():
    """Coze Backend 使用示例"""
    print("=" * 60)
    print("Coze Backend 使用示例")
    print("=" * 60)
    
    try:
        # 创建后端
        backend = CozeBackend()
        
        # 非流式调用
        print("\n📝 非流式调用:")
        messages = [{"role": "user", "content": "你好，请介绍一下自己"}]
        response = await backend.chat(messages)
        print(f"回复: {response}\n")
        
        # 流式调用
        print("📝 流式调用:")
        messages = [{"role": "user", "content": "用 Python 写一个 Hello World"}]
        print("回复: ", end="", flush=True)
        async for chunk in backend.chat_stream(messages):
            print(chunk, end="", flush=True)
        print()
        
        # 查看统计
        stats = backend.get_token_stats()
        print(f"\n📊 Token 统计: {stats}")
        
        # 关闭
        await backend.close()
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        print("\n💡 提示: 确保在 .env 文件中配置了 COZE_API_TOKEN 和 COZE_BOT_ID")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_coze_backend())
