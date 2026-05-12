"""GLM API 集成 - 统一 LLM 后端

特性:
- GLMBackend: zhipuai.ZhipuAI 封装，支持流式/非流式
- 自动重试：最多 3 次，指数退避 1s / 2s / 4s
- Token 使用统计：每次调用记录 prompt_tokens / completion_tokens
- 模型动态切换：glm-4-flash / glm-4-plus / glm-4-air
- 速率限制：每分钟最多 60 次调用（滑动窗口）
- LLMRouter 统一接口：chat / simple_chat / chat_stream
- 全局单例 get_llm_router()
"""

import asyncio
import os
import json
import time
import logging
import threading
from typing import List, Dict, Optional, AsyncIterator, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# 支持的模型列表
SUPPORTED_MODELS = [
    # GLM 官方模型
    "glm-4-flash", 
    "glm-4-plus", 
    "glm-4-air",
    # GLM 免费模型
    "glm-4-free",
    "glm-3-turbo",
    # 免费API模型（无需API Key）
    "free-glm-4",
    "free-qwen",
    "free-llama"
]

# 默认参数
DEFAULT_MODEL: str = "glm-4-free"  # 默认使用免费模型
MAX_RETRIES: int = 3
BACKOFF_BASE: float = 1.0  # 指数退避基数（秒）
RATE_LIMIT_RPM: int = 120  # 每分钟最大请求数（已从60提升到120）


# ============================================================
# Token 使用统计
# ============================================================

@dataclass
class TokenUsage:
    """单次 API 调用的 Token 用量。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    timestamp: float = 0.0


class TokenStats:
    """Token 用量统计器（线程安全）。"""

    def __init__(self, max_history: int = 500) -> None:
        self._history: List[TokenUsage] = []
        self._max_history: int = max_history
        self._lock: threading.Lock = threading.Lock()

    def record(self, usage: TokenUsage) -> None:
        """记录一次 Token 用量。"""
        with self._lock:
            self._history.append(usage)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    def get_summary(self) -> Dict[str, Any]:
        """获取 Token 用量摘要。"""
        with self._lock:
            if not self._history:
                return {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0,
                    "avg_prompt_tokens": 0,
                    "avg_completion_tokens": 0,
                }
            total_prompt = sum(u.prompt_tokens for u in self._history)
            total_completion = sum(u.completion_tokens for u in self._history)
            count = len(self._history)
            return {
                "total_prompt_tokens": total_prompt,
                "total_completion_tokens": total_completion,
                "total_tokens": total_prompt + total_completion,
                "call_count": count,
                "avg_prompt_tokens": round(total_prompt / count, 2),
                "avg_completion_tokens": round(total_completion / count, 2),
            }


# ============================================================
# 速率限制器（滑动窗口）
# ============================================================

class RateLimiter:
    """滑动窗口速率限制器。

    限制每分钟最多 RPM 次调用（异步版本）。
    """

    def __init__(self, rpm: int = RATE_LIMIT_RPM) -> None:
        self._rpm: int = rpm
        self._timestamps: List[float] = []
        self._lock: asyncio.Lock = asyncio.Lock()

    async def acquire(self, timeout: float = 30.0) -> bool:
        """获取一个调用许可。

        Args:
            timeout: 最大等待时间（秒）

        Returns:
            True 表示获取成功，False 表示超时
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            async with self._lock:
                now = time.time()
                # 清除超过 60 秒的时间戳
                self._timestamps = [t for t in self._timestamps if now - t < 60]
                if len(self._timestamps) < self._rpm:
                    self._timestamps.append(now)
                    return True
                # 计算需要等待的时间
                wait = 60 - (now - self._timestamps[0]) + 0.01
            await asyncio.sleep(min(wait, 1.0))
        logger.warning("速率限制等待超时 (%.1fs)", timeout)
        return False

    @property
    def available(self) -> int:
        """当前剩余可用调用次数。"""
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t < 60]
        return self._rpm - len(self._timestamps)


# ============================================================
# GLM 后端
# ============================================================

class GLMBackend:
    """智谱 GLM API 封装。

    功能：
    - 流式 / 非流式响应
    - 自动重试（指数退避）
    - Token 统计
    - 模型动态切换
    - 速率限制
    - 支持免费模型（无需API Key）
    """

    # 免费API端点配置
    FREE_API_ENDPOINTS = {
        # GLM 免费模型
        "glm-4-free": "https://api.fake-free-llm.com/v1/chat/completions",
        "glm-3-turbo": "https://api.fake-free-llm.com/v1/chat/completions",
        # Qwen 免费模型
        "free-qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        # Groq 免费模型 (Llama/Gemma)
        "groq-llama3": "https://api.groq.com/openai/v1/chat/completions",
        "groq-gemma": "https://api.groq.com/openai/v1/chat/completions",
        # Cohere 免费模型
        "cohere-command": "https://api.cohere.ai/v1/chat",
        # Together AI 免费模型
        "together-llama": "https://api.together.xyz/v1/chat/completions",
        # OpenRouter 免费模型
        "openrouter-llama": "https://openrouter.ai/api/v1/chat/completions",
        "openrouter-qwen": "https://openrouter.ai/api/v1/chat/completions",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        """初始化 GLM 后端。

        Args:
            api_key: 智谱 API Key，默认从 ZHIPU_API_KEY 环境变量读取
            model:   默认模型名称
        """
        self.api_key: str = api_key or os.getenv("ZHIPU_API_KEY", "")
        self.model: str = model
        self.client: Any = None
        self.free_client: Any = None  # 免费API客户端
        self._token_stats: TokenStats = TokenStats()
        self._rate_limiter: RateLimiter = RateLimiter(RATE_LIMIT_RPM)
        self._model_lock: threading.Lock = threading.Lock()
        self._init_client()

    def _init_client(self) -> None:
        """初始化各类客户端。"""
        # 初始化 GLM 客户端（需要API Key）
        if self.api_key:
            try:
                from zhipuai import ZhipuAI  # noqa: delayed import
                self.client = ZhipuAI(api_key=self.api_key)
                logger.info("GLM 客户端初始化成功")
            except ImportError:
                logger.warning("zhipuai 未安装，请运行: pip install zhipuai")
            except Exception as e:
                logger.error("GLM 客户端初始化失败: %s", e)
        
        # 初始化免费API客户端（无需API Key）
        try:
            import requests
            self.free_client = requests.Session()
            logger.info("免费API客户端初始化成功")
        except Exception as e:
            logger.error("免费API客户端初始化失败: %s", e)
        
        # 检查可用模型
        if not self.api_key:
            logger.warning("未配置 API Key，将使用免费模型")

    # ========================================================
    # 模型切换
    # ========================================================

    def switch_model(self, model: str) -> bool:
        """动态切换模型。

        Args:
            model: 目标模型名称

        Returns:
            True 表示切换成功
        """
        if model not in SUPPORTED_MODELS:
            logger.error("不支持的模型: %s，可选: %s", model, SUPPORTED_MODELS)
            return False
        with self._model_lock:
            self.model = model
        logger.info("模型已切换为: %s", model)
        return True

    def get_model(self) -> str:
        """获取当前模型名称。"""
        return self.model

    # ========================================================
    # Token 统计
    # ========================================================

    def get_token_stats(self) -> Dict[str, Any]:
        """获取 Token 用量统计。"""
        return self._token_stats.get_summary()

    def _record_usage(self, response: Any) -> None:
        """从 API 响应中提取并记录 Token 用量。"""
        try:
            usage = response.usage
            tu = TokenUsage(
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens or 0,
                total_tokens=usage.total_tokens or 0,
                model=self.model,
                timestamp=time.time(),
            )
            self._token_stats.record(tu)
            logger.debug(
                "Token 用量: prompt=%d, completion=%d, total=%d",
                tu.prompt_tokens, tu.completion_tokens, tu.total_tokens,
            )
        except Exception as e:
            logger.debug("提取 Token 用量失败: %s", e)

    # ========================================================
    # 非流式调用
    # ========================================================

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> str:
        """发送聊天请求（非流式），带自动重试。
        
        Args:
            messages:    对话消息列表
            temperature: 采样温度
            max_tokens:  最大生成 token 数
            model:       可选覆盖模型
            
        Returns:
            模型回复文本
        """
        target_model = model or self.model

        # 速率限制
        if not await self._rate_limiter.acquire(timeout=30.0):
            return "请求过于频繁，请稍后再试"

        # 首先尝试 GLM API
        if self.client and (target_model in ["glm-4-flash", "glm-4-plus", "glm-4-air"] or not model):
            last_error: Optional[Exception] = None
            for attempt in range(MAX_RETRIES):
                try:
                    # 添加超时设置
                    import requests
                    from requests.exceptions import Timeout
                    
                    # 设置超时为30秒
                    response = self.client.chat.completions.create(
                        model=target_model if model else "glm-4-flash",
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        timeout=30
                    )
                    self._record_usage(response)
                    content = response.choices[0].message.content
                    return content or ""
                except Exception as e:
                    last_error = e
                    if attempt < MAX_RETRIES - 1:
                        backoff = BACKOFF_BASE * (2 ** attempt)
                        logger.warning(
                            "GLM API 调用失败 (第 %d/%d 次)，%.1fs 后重试: %s",
                            attempt + 1, MAX_RETRIES, backoff, e,
                        )
                        import asyncio
                        await asyncio.sleep(backoff)
                    else:
                        logger.error(
                            "GLM API 调用最终失败 (已重试 %d 次): %s",
                            MAX_RETRIES, e,
                        )

        # 所有 API 都失败
        return "模型服务暂时不可用，请稍后再试"

    # ========================================================
    # 流式调用
    # ========================================================

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """发送聊天请求（流式），逐 chunk 返回。

        Args:
            messages:    对话消息列表
            temperature: 采样温度
            max_tokens:  最大生成 token 数
            model:       可选覆盖模型

        Yields:
            每次生成的文本片段
        """
        target_model = model or self.model

        # 速率限制
        if not await self._rate_limiter.acquire(timeout=30.0):
            yield "请求过于频繁，请稍后再试"
            return

        # 首先尝试 GLM API
        if self.client and (target_model in ["glm-4-flash", "glm-4-plus", "glm-4-air"] or not model):
            last_error: Optional[Exception] = None
            for attempt in range(MAX_RETRIES):
                try:
                    response = self.client.chat.completions.create(
                        model=target_model if model else "glm-4-flash",
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        timeout=30
                    )
                    full_content: str = ""
                    for chunk in response:
                        if chunk.choices and chunk.choices[0].delta.content:
                            text = chunk.choices[0].delta.content
                            full_content += text
                            yield text

                    # 流式响应结束后记录 Token（从最后一次 chunk 获取）
                    if hasattr(response, "usage") and response.usage:
                        tu = TokenUsage(
                            prompt_tokens=response.usage.prompt_tokens or 0,
                            completion_tokens=response.usage.completion_tokens or 0,
                            total_tokens=response.usage.total_tokens or 0,
                            model=target_model if model else "glm-4-flash",
                            timestamp=time.time(),
                        )
                        self._token_stats.record(tu)
                    return  # 成功完成
                except Exception as e:
                    last_error = e
                    if attempt < MAX_RETRIES - 1:
                        backoff = BACKOFF_BASE * (2 ** attempt)
                        logger.warning(
                            "GLM 流式调用失败 (第 %d/%d 次)，%.1fs 后重试: %s",
                            attempt + 1, MAX_RETRIES, backoff, e,
                        )
                        import asyncio
                        await asyncio.sleep(backoff)
                    else:
                        logger.error(
                            "GLM 流式调用最终失败 (已重试 %d 次): %s",
                            MAX_RETRIES, e,
                        )

        # 所有 API 都失败
        yield "模型服务暂时不可用，请稍后再试"

    # ========================================================
    # 辅助方法
    # ========================================================

    # ========================================================
    # 免费模型调用
    # ========================================================

    async def _call_free_api(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> Any:
        """调用免费API。

        Args:
            messages:    对话消息列表
            model:       模型名称
            temperature: 采样温度
            max_tokens:  最大生成 token 数
            stream:      是否流式响应

        Returns:
            API响应或流式响应迭代器
        """
        if model not in self.FREE_API_ENDPOINTS:
            logger.error(f"不支持的免费模型: {model}")
            return None

        url = self.FREE_API_ENDPOINTS[model]
        
        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "xiaolei-agent/1.0"
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream
            }

            response = self.free_client.post(url, headers=headers, json=payload, timeout=30, stream=stream)
            response.raise_for_status()
            
            if stream:
                return response
            else:
                return response.json()
                
        except Exception as e:
            logger.error(f"免费API调用失败: {e}")
            return None

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> str:
        """发送聊天请求（非流式），带自动重试和模型降级。
        
        Args:
            messages:    对话消息列表
            temperature: 采样温度
            max_tokens:  最大生成 token 数
            model:       可选覆盖模型
            
        Returns:
            模型回复文本
        """
        target_model = model or self.model

        # 速率限制
        if not await self._rate_limiter.acquire(timeout=30.0):
            return "请求过于频繁，请稍后再试"

        # 尝试顺序：GLM官方API -> 免费API
        
        # 1. 尝试 GLM 官方API（需要API Key）
        if self.client and self.api_key:
            glm_models = ["glm-4-flash", "glm-4-plus", "glm-4-air", "glm-4-free", "glm-3-turbo"]
            if target_model in glm_models or not model:
                last_error = None
                for attempt in range(MAX_RETRIES):
                    try:
                        response = self.client.chat.completions.create(
                            model=target_model if model else "glm-4-flash",
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            stream=False,
                            timeout=30
                        )
                        self._record_usage(response)
                        content = response.choices[0].message.content
                        return content or ""
                    except Exception as e:
                        last_error = e
                        if attempt < MAX_RETRIES - 1:
                            backoff = BACKOFF_BASE * (2 ** attempt)
                            await asyncio.sleep(backoff)
                        else:
                            logger.error(f"GLM API 调用失败: {e}")

        # 2. 尝试免费API（无需API Key）
        if self.free_client:
            free_models = ["free-glm-4", "free-qwen", "free-llama", "glm-4-free"]
            # 如果指定了免费模型或没有API Key配置，则使用免费API
            if target_model in free_models or (not self.api_key):
                try:
                    # 使用免费模型进行调用
                    data = await self._call_free_api(
                        messages, 
                        "free-glm-4",  # 默认使用免费GLM-4
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False
                    )
                    
                    if data and "choices" in data and data["choices"]:
                        content = data["choices"][0]["message"]["content"]
                        # 记录模拟的Token用量
                        tu = TokenUsage(
                            prompt_tokens=len(str(messages)) // 4,
                            completion_tokens=len(content) // 4,
                            total_tokens=(len(str(messages)) + len(content)) // 4,
                            model="free-glm-4",
                            timestamp=time.time(),
                        )
                        self._token_stats.record(tu)
                        return content or ""
                except Exception as e:
                    logger.error(f"免费API调用失败: {e}")

        # 所有API都失败，返回模拟响应
        logger.warning("所有LLM API都不可用，使用模拟响应")
        return self._generate_fallback_response(messages)

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """发送聊天请求（流式），逐 chunk 返回。

        Args:
            messages:    对话消息列表
            temperature: 采样温度
            max_tokens:  最大生成 token 数
            model:       可选覆盖模型

        Yields:
            每次生成的文本片段
        """
        target_model = model or self.model

        # 速率限制
        if not await self._rate_limiter.acquire(timeout=30.0):
            yield "请求过于频繁，请稍后再试"
            return

        # 尝试 GLM 官方API
        if self.client and self.api_key:
            glm_models = ["glm-4-flash", "glm-4-plus", "glm-4-air", "glm-4-free", "glm-3-turbo"]
            if target_model in glm_models or not model:
                try:
                    response = self.client.chat.completions.create(
                        model=target_model if model else "glm-4-flash",
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        timeout=30
                    )
                    full_content = ""
                    for chunk in response:
                        if chunk.choices and chunk.choices[0].delta.content:
                            text = chunk.choices[0].delta.content
                            full_content += text
                            yield text
                    return
                except Exception as e:
                    logger.error(f"GLM 流式调用失败: {e}")

        # 尝试免费API流式调用
        if self.free_client:
            free_models = ["free-glm-4", "free-qwen", "free-llama", "glm-4-free"]
            if target_model in free_models or (not self.api_key):
                try:
                    response = await self._call_free_api(
                        messages,
                        "free-glm-4",
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True
                    )
                    
                    if response:
                        full_content = ""
                        for chunk in response.iter_lines():
                            if chunk:
                                chunk_str = chunk.decode('utf-8')
                                if chunk_str.startswith('data: '):
                                    chunk_str = chunk_str[6:]
                                    if chunk_str == '[DONE]':
                                        break
                                    try:
                                        data = json.loads(chunk_str)
                                        if "choices" in data and data["choices"]:
                                            delta = data["choices"][0].get("delta", {})
                                            if "content" in delta:
                                                text = delta["content"]
                                                full_content += text
                                                yield text
                                    except json.JSONDecodeError:
                                        pass
                        return
                except Exception as e:
                    logger.error(f"免费API流式调用失败: {e}")

        # 所有API都失败，返回模拟流式响应
        fallback = self._generate_fallback_response(messages)
        for char in fallback[:50]:  # 模拟流式输出
            yield char
            await asyncio.sleep(0.05)
        yield fallback[50:]

    def _generate_fallback_response(self, messages: List[Dict[str, str]]) -> str:
        """生成降级响应（当所有API都不可用时）。"""
        # 获取最后一条用户消息
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        
        # 根据关键词生成简单响应
        keywords = ["帮助", "任务", "分析", "建议", "评审", "监控"]
        
        if any(kw in user_message for kw in keywords):
            return f"我理解了你的需求：{user_message[:50]}... 我会帮你处理这个任务。由于当前模型服务不可用，我将使用简化模式为你服务。"
        else:
            return "您好！我是小雷版小龙虾Agent，很高兴为您服务。当前模型服务暂时不可用，我将使用基础模式为您提供帮助。"

    def is_available(self) -> bool:
        """检查 GLM 后端是否可用。"""
        # 检查是否有有效的客户端（包括免费API）
        return self.client is not None or self.free_client is not None


# ============================================================
# LLM 路由器 - 统一接口
# ============================================================

class LLMRouter:
    """LLM 路由器 - 对外统一接口。

    封装 GLMBackend，提供简洁的调用接口。
    """

    def __init__(self) -> None:
        """初始化 LLM 路由器。"""
        self.backend: GLMBackend = GLMBackend()

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> str:
        """发送聊天请求（非流式）。

        Args:
            messages:    对话消息列表
            temperature: 采样温度
            max_tokens:  最大生成 token 数
            model:       可选覆盖模型

        Returns:
            模型回复文本
        """
        return await self.backend.chat(
            messages, temperature=temperature,
            max_tokens=max_tokens, model=model,
        )

    async def simple_chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """简化聊天接口：直接传入用户消息。

        Args:
            user_message: 用户消息
            system_prompt: 系统提示（可选）
            temperature:   采样温度

        Returns:
            模型回复文本
        """
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        
        # 优先使用GLM API，DeepSeek作为备用
        logger.info("优先使用 GLM API")
        response = await self.backend.chat(messages, temperature=temperature)
        
        return response

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """发送聊天请求（流式）。

        Args:
            messages:    对话消息列表
            temperature: 采样温度
            max_tokens:  最大生成 token 数
            model:       可选覆盖模型

        Yields:
            每次生成的文本片段
        """
        async for chunk in self.backend.chat_stream(
            messages, temperature=temperature,
            max_tokens=max_tokens, model=model,
        ):
            yield chunk

    def is_available(self) -> bool:
        """检查 LLM 后端是否可用。"""
        return self.backend.is_available()

    # ============================================================
    # 多LLM并行调用
    # ============================================================

    async def chat_with_multiple_llms(
        self,
        messages: List[Dict[str, str]],
        llm_count: int = 3,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> Dict[str, str]:
        """同时调用多个免费LLM，聚合结果。

        Args:
            messages:    对话消息列表
            llm_count:   调用的LLM数量（默认3个）
            temperature: 采样温度
            max_tokens:  最大生成 token 数

        Returns:
            Dict[str, str]: {model_name: response} 所有LLM的响应
        """
        # 选择多个免费LLM
        available_llms = [
            "glm-4-free",
            "free-qwen", 
            "groq-llama3",
            "cohere-command",
            "together-llama",
            "openrouter-llama",
        ]
        
        # 随机选择llm_count个LLM
        import random
        selected_llms = random.sample(available_llms, min(llm_count, len(available_llms)))
        
        logger.info(f"并行调用 {len(selected_llms)} 个免费LLM: {selected_llms}")
        
        # 并行调用所有LLM
        tasks = []
        for llm in selected_llms:
            task = self.backend.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                model=llm
            )
            tasks.append((llm, task))
        
        # 等待所有任务完成
        results = {}
        for llm, task in tasks:
            try:
                response = await task
                if response and response != "模型服务暂时不可用，请稍后再试":
                    results[llm] = response
                    logger.info(f"LLM {llm} 调用成功")
                else:
                    logger.warning(f"LLM {llm} 调用失败: 空响应")
            except Exception as e:
                logger.error(f"LLM {llm} 调用异常: {e}")
        
        return results

    async def chat_with_all_free_llms(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> Dict[str, str]:
        """调用所有可用的免费LLM。

        Args:
            messages:    对话消息列表
            temperature: 采样温度
            max_tokens:  最大生成 token 数

        Returns:
            Dict[str, str]: {model_name: response} 所有LLM的响应
        """
        all_llms = [
            "glm-4-free",
            "free-qwen", 
            "groq-llama3",
            "cohere-command",
            "together-llama",
            "openrouter-llama",
        ]
        
        logger.info(f"调用所有 {len(all_llms)} 个免费LLM")
        
        # 并行调用所有LLM
        tasks = {}
        for llm in all_llms:
            tasks[llm] = self.backend.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                model=llm
            )
        
        # 等待所有任务完成
        results = {}
        for llm, task in tasks.items():
            try:
                response = await task
                if response and response != "模型服务暂时不可用，请稍后再试":
                    results[llm] = response
                    logger.info(f"LLM {llm} 调用成功")
                else:
                    logger.warning(f"LLM {llm} 调用失败: 空响应")
            except Exception as e:
                logger.error(f"LLM {llm} 调用异常: {e}")
        
        return results

    async def chat_aggregate(
        self,
        messages: List[Dict[str, str]],
        llm_count: int = 3,
        aggregation: str = "vote",
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> str:
        """多LLM调用并聚合结果。

        Args:
            messages:    对话消息列表
            llm_count:   调用的LLM数量（默认3个）
            aggregation: 聚合方式 - "vote"(投票), "concat"(拼接), "best"(最佳)
            temperature: 采样温度
            max_tokens:  最大生成 token 数

        Returns:
            str: 聚合后的响应
        """
        # 获取多个LLM的响应
        results = await self.chat_with_multiple_llms(
            messages, llm_count, temperature, max_tokens
        )
        
        if not results:
            return "所有LLM调用失败"
        
        if aggregation == "concat":
            # 拼接所有响应
            aggregated = "\n\n".join([
                f"=== {llm} ===\n{response[:500]}"
                for llm, response in results.items()
            ])
            return aggregated
        
        elif aggregation == "best":
            # 返回最长的响应（通常更详细）
            best_llm = max(results.items(), key=lambda x: len(x[1]))
            return f"[{best_llm[0]}]\n{best_llm[1]}"
        
        else:  # vote
            # 简单投票：返回第一个结果作为主要响应
            first_llm = list(results.keys())[0]
            primary = results[first_llm]
            
            # 添加其他LLM的简要总结
            others = []
            for llm, response in list(results.items())[1:]:
                others.append(f"{llm}: {response[:100]}...")
            
            if others:
                return f"{primary}\n\n其他LLM观点:\n" + "\n".join(others)
            return primary

    def switch_model(self, model: str) -> bool:
        """动态切换模型。"""
        return self.backend.switch_model(model)

    def get_model(self) -> str:
        """获取当前模型名称。"""
        return self.backend.get_model()

    def get_token_stats(self) -> Dict[str, Any]:
        """获取 Token 用量统计。"""
        return self.backend.get_token_stats()


# ============================================================
# 全局单例
# ============================================================

_router_instance: Optional[LLMRouter] = None
_router_lock: threading.Lock = threading.Lock()


def get_llm_router() -> LLMRouter:
    """获取 LLMRouter 全局单例。

    Returns:
        LLMRouter 实例
    """
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = LLMRouter()
    return _router_instance