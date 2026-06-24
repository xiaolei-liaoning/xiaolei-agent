"""GLM API 集成 + 多LLM路由 — 统一 LLM 后端

特性:
- GLMBackend: zhipuai.ZhipuAI 封装，支持流式/非流式
- Auto-retry: 最多 3 次，指数退避
- Token 统计
- 速率限制（滑动窗口）
- LLMRouter: 多提供商路由，4 种策略（round_robin/least_load/priority/fallback_chain）
- 全局单例 get_llm_router()
"""

import asyncio
import os
import json
import time
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, AsyncIterator, Any

from dotenv import load_dotenv

try:
    from .config_manager import get_config
    HAS_CONFIG_MANAGER = True
except ImportError:
    HAS_CONFIG_MANAGER = False

load_dotenv()
logger = logging.getLogger(__name__)


def get_llm_config():
    if HAS_CONFIG_MANAGER:
        try:
            return get_config().llm
        except Exception:
            pass
    class FallbackLLMConfig:
        default_model = "glm-4-flash"
        max_retries = 3
        backoff_base = 2.0
        rate_limit_rpm = 300
        timeout = 30  # LLM 调用超时（秒），fallback 阶段可更快失败
        supported_models = [
            "glm-4-flash", "glm-4-plus", "glm-4-air",
            "glm-4.7-flash", "glm-4-free", "glm-3-turbo",
            "deepseek-chat",
        ]
    return FallbackLLMConfig()

llm_config = get_llm_config()
SUPPORTED_MODELS = llm_config.supported_models
DEFAULT_MODEL = llm_config.default_model
MAX_RETRIES = llm_config.max_retries
BACKOFF_BASE = llm_config.backoff_base
RATE_LIMIT_RPM = llm_config.rate_limit_rpm


# ============================================================
# Token 使用统计
# ============================================================

@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    timestamp: float = 0.0


@dataclass
class LLMResponse:
    """结构化 LLM 响应，含文本内容和原生 tool_calls"""
    content: str = ""
    tool_calls: List[Dict] = field(default_factory=list)

    def has_tools(self) -> bool:
        return bool(self.tool_calls)


class TokenStats:
    def __init__(self, max_history: int = 500):
        self._history: List[TokenUsage] = []
        self._max_history = max_history
        self._lock = threading.Lock()

    def record(self, usage: TokenUsage):
        with self._lock:
            self._history.append(usage)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            if not self._history:
                return {"total_prompt_tokens": 0, "total_completion_tokens": 0,
                        "total_tokens": 0, "call_count": 0}
            total = sum(u.total_tokens for u in self._history)
            return {
                "total_prompt_tokens": sum(u.prompt_tokens for u in self._history),
                "total_completion_tokens": sum(u.completion_tokens for u in self._history),
                "total_tokens": total,
                "call_count": len(self._history),
                "avg_tokens": round(total / len(self._history), 2),
            }


# ============================================================
# 速率限制器
# ============================================================

class RateLimiter:
    def __init__(self, rpm: int = RATE_LIMIT_RPM):
        self._rpm = rpm
        self._timestamps: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float = 5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            async with self._lock:
                now = time.time()
                self._timestamps = [t for t in self._timestamps if now - t < 60]
                if len(self._timestamps) < self._rpm:
                    self._timestamps.append(now)
                    return True
                wait = 60 - (now - self._timestamps[0]) + 0.01
            await asyncio.sleep(min(wait, 1.0))
        return False

    @property
    def available(self) -> int:
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t < 60]
        return self._rpm - len(self._timestamps)


# ============================================================
# GLM 后端（保留原有完整实现）
# ============================================================

class GLMBackend:
    """智谱 GLM API + DeepSeek 封装"""

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.getenv("ZHIPU_API_KEY", "")
        self.model = model or DEFAULT_MODEL
        self.client = None
        self.deepseek_client = None
        self.openrouter_client = None
        self.deepseek_model = os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-chat")
        self._token_stats = TokenStats()
        self._rate_limiter = RateLimiter(RATE_LIMIT_RPM)
        self._model_lock = threading.Lock()
        self.timeout = llm_config.timeout
        self._consecutive_failures = 0  # 连续失败计数
        self._max_consecutive_failures = 10  # 超过此值认为 API 不可用
        self._init_client()

    def _init_client(self):
        # 0. 初始化 DeepSeek (OpenAI 兼容)
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", os.getenv("ANTHROPIC_AUTH_TOKEN", ""))
        if deepseek_key:
            try:
                import openai
                self.deepseek_client = openai.AsyncOpenAI(
                    api_key=deepseek_key,
                    base_url="https://api.deepseek.com/v1",
                )
                logger.info("DeepSeek 客户端初始化成功: model=%s", self.deepseek_model)
            except ImportError:
                logger.warning("openai 未安装，DeepSeek 客户端不可用")
            except Exception as e:
                logger.warning("DeepSeek 客户端初始化失败: %s", e)

        # 1. 初始化 OpenRouter (OpenAI 兼容)
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        if openrouter_key:
            try:
                import openai
                self.openrouter_client = openai.AsyncOpenAI(
                    api_key=openrouter_key,
                    base_url="https://openrouter.ai/api/v1",
                )
                logger.info("OpenRouter 客户端初始化成功")
            except ImportError:
                logger.warning("openai 未安装，OpenRouter 客户端不可用")
            except Exception as e:
                logger.warning("OpenRouter 客户端初始化失败: %s", e)

        # 2. 初始化 GLM API (fallback)
        if self.api_key:
            try:
                from zhipuai import ZhipuAI
                self.client = ZhipuAI(api_key=self.api_key)
            except ImportError:
                logger.warning("zhipuai 未安装")
            except Exception as e:
                logger.error("GLM 客户端初始化失败: %s", e)

    def switch_model(self, model: str) -> bool:
        if model not in SUPPORTED_MODELS:
            return False
        with self._model_lock:
            self.model = model
        return True

    def get_model(self) -> str:
        return self.model

    def get_token_stats(self) -> Dict[str, Any]:
        return self._token_stats.get_summary()

    def _record_usage(self, response):
        try:
            usage = response.usage
            self._token_stats.record(TokenUsage(
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens or 0,
                total_tokens=usage.total_tokens or 0,
                model=self.model, timestamp=time.time(),
            ))
        except Exception:
            pass

    def _record_usage_from_response(self, data: Dict, model: str):
        try:
            usage = data.get("usage", {})
            self._token_stats.record(TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                model=model, timestamp=time.time(),
            ))
        except Exception:
            pass

    async def _chat_impl(self, messages, temperature=0.7, max_tokens=4096,
                         model=None, tools=None) -> LLMResponse:
        """内部实现：返回结构化 LLMResponse，包含原生 tool_calls"""
        # ── 清理 tool 消息顺序 — 防止 DeepSeek API 400 ──
        try:
            cleaned = []
            for m in messages:
                if m["role"] == "tool":
                    has_pending = any(
                        p.get("tool_calls") for p in cleaned if p["role"] == "assistant"
                    )
                    if not has_pending:
                        continue
                cleaned.append(m)
            messages = cleaned
        except Exception:
            pass

        target = model or self.model
        if not await self._rate_limiter.acquire(timeout=15.0):
            return LLMResponse(content="请求过于频繁，请稍后再试")

        logger.info("LLM.chat: api_key=%s client=%s tools=%s",
                     bool(self.api_key), bool(self.client), bool(tools))

        # 0. DeepSeek (OpenAI 兼容) — 优先
        if self.deepseek_client:
            try:
                payload = dict(model=self.deepseek_model, messages=messages,
                               temperature=temperature, max_tokens=max_tokens)
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                logger.info("LLM → DeepSeek (%s, tools=%s)", self.deepseek_model, bool(tools))
                response = await asyncio.wait_for(
                    self.deepseek_client.chat.completions.create(**payload),
                    timeout=180,
                )
                self._record_usage_from_response(response.model_dump() if hasattr(response, 'model_dump') else {}, self.deepseek_model)
                if hasattr(response, 'choices') and response.choices:
                    message = response.choices[0].message
                    content = getattr(message, 'content', None) or ""
                    tc = getattr(message, 'tool_calls', None)

                    finish_reason = getattr(response.choices[0], 'finish_reason', None)
                    is_truncated = finish_reason == 'length'
                    if is_truncated:
                        logger.warning(f"⚠️ LLM输出被截断! finish_reason=length, content_len={len(content)}")

                    logger.info("LLM DeepSeek返回: content_len=%d tool_calls=%s truncated=%s", len(content), bool(tc), is_truncated)
                    self._consecutive_failures = 0  # 成功，重置失败计数
                    if tc:
                        tc_list = [{"id": getattr(t, 'id', ''),
                                    "type": getattr(t, 'type', 'function'),
                                    "function": {"name": t.function.name,
                                                 "arguments": t.function.arguments}}
                                   for t in tc]
                        return LLMResponse(content=content, tool_calls=tc_list)
                    return LLMResponse(content=content or "")
                else:
                    logger.warning("DeepSeek 返回空响应")
            except asyncio.TimeoutError:
                logger.error("DeepSeek API 调用超时(25s)")
            except Exception as e:
                logger.error(f"DeepSeek API 调用异常: {e}")

        # 1. OpenRouter (OpenAI 兼容) — fallback
        if self.openrouter_client:
            try:
                payload = dict(model=self.deepseek_model, messages=messages,
                               temperature=temperature, max_tokens=max_tokens)
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                logger.info("LLM → OpenRouter (model=%s, tools=%s)", self.deepseek_model, bool(tools))
                response = await asyncio.wait_for(
                    self.openrouter_client.chat.completions.create(**payload),
                    timeout=180,
                )
                if hasattr(response, 'choices') and response.choices:
                    message = response.choices[0].message
                    content = getattr(message, 'content', None) or ""
                    tc = getattr(message, 'tool_calls', None)
                    logger.info("LLM OpenRouter返回: content_len=%d tool_calls=%s", len(content), bool(tc))
                    self._consecutive_failures = 0
                    if tc:
                        tc_list = [{"id": getattr(t, 'id', ''),
                                    "type": getattr(t, 'type', 'function'),
                                    "function": {"name": t.function.name,
                                                 "arguments": t.function.arguments}}
                                   for t in tc]
                        return LLMResponse(content=content, tool_calls=tc_list)
                    return LLMResponse(content=content or "")
            except asyncio.TimeoutError:
                logger.error("OpenRouter API 调用超时(25s)")
            except Exception as e:
                logger.error(f"OpenRouter API 调用异常: {e}")

        # 2. GLM (ZhipuAI) — 最后 fallback
        if self.client and self.api_key:
            try:
                kwargs = dict(model="glm-4-flash", messages=messages,
                              temperature=temperature, max_tokens=max_tokens,
                              stream=False, timeout=20)
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"

                logger.info("LLM → GLM (glm-4-flash, tools=%s)", bool(tools))
                response = await asyncio.wait_for(
                    asyncio.to_thread(self.client.chat.completions.create, **kwargs),
                    timeout=180,
                )
                self._record_usage(response)
                message = response.choices[0].message
                content = message.content or ""
                tc = getattr(message, 'tool_calls', None)
                logger.info("LLM GLM返回: content_len=%d tool_calls=%s", len(content), bool(tc))
                self._consecutive_failures = 0
                if tc:
                    tc_list = [{"id": getattr(t, 'id', ''),
                                "type": getattr(t, 'type', 'function'),
                                "function": {"name": t.function.name,
                                             "arguments": t.function.arguments}}
                               for t in tc]
                    return LLMResponse(content=content, tool_calls=tc_list)
                return LLMResponse(content=content or "")
            except asyncio.TimeoutError:
                logger.error("GLM API 调用超时(20s)")
            except Exception as e:
                logger.error(f"GLM API 调用异常: {e}")

        self._consecutive_failures += 1
        logger.warning("所有 LLM API 不可用 (deepseek=%s, openrouter=%s, glm=%s), 连续失败=%d",
                       bool(self.deepseek_client), bool(self.openrouter_client), bool(self.client), self._consecutive_failures)
        return LLMResponse(content="[LLM_MOCK] 系统正在处理您的请求...")

    async def chat(self, messages, temperature=0.7, max_tokens=4096,
                   model=None, tools=None) -> str:
        """向后兼容包装器：返回字符串，支持 tool_calls 的 JSON 序列化"""
        resp = await self._chat_impl(messages, temperature=temperature,
                                     max_tokens=max_tokens, model=model, tools=tools)
        if resp.tool_calls:
            return json.dumps({"choices": [{"message": {"role": "assistant",
                            "content": resp.content, "tool_calls": resp.tool_calls}}]},
                              ensure_ascii=False)
        return resp.content

    async def chat_structured(self, messages, temperature=0.7, max_tokens=4096,
                              model=None, tools=None) -> LLMResponse:
        """原生工具调用：返回 LLMResponse 含结构化 tool_calls"""
        return await self._chat_impl(messages, temperature=temperature,
                                     max_tokens=max_tokens, model=model, tools=tools)

    async def chat_stream(self, messages, temperature=0.7, max_tokens=4096,
                          model=None) -> AsyncIterator[str]:
        target = model or self.model
        if not await self._rate_limiter.acquire(timeout=30.0):
            yield "请求过于频繁"
            return

        if self.client and self.api_key:
            try:
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model="glm-4-flash", messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                    stream=True, timeout=self.timeout)
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception:
                pass

        if self.deepseek_client:
            try:
                response = await self.deepseek_client.chat.completions.create(
                    model=self.deepseek_model, messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                    stream=True)
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception:
                pass

        if self.openrouter_client:
            try:
                response = await self.deepseek_client.chat.completions.create(
                    model=self.deepseek_model, messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                    stream=True)
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception:
                pass
        yield "流式响应不可用，请使用非流式接口"

    async def chat_structured_stream(self, messages, temperature=0.7, max_tokens=4096,
                                      model=None, tools=None, on_text=None) -> LLMResponse:
        """流式工具调用 — 对标 Opencode 的 streamText + 事件处理器
        
        on_text: 可选回调，每收到文本块时调用 on_text(chunk)
        返回 LLMResponse（同 chat_structured），含 content + tool_calls
        
        流式处理逻辑：
          1. DeepSeek (OpenAI 兼容): 原生 async generator，支持 tool_calls 流式传输
          2. GLM (ZhipuAI): 同步 blocking + asyncio.to_thread
        """
        target = model or self.model
        if not await self._rate_limiter.acquire(timeout=30.0):
            return LLMResponse(content="请求过于频繁，请稍后再试")

        full_content = ""
        # tool_call 缓冲区: {index: {id, function: {name, arguments}}}
        tool_call_buffers: Dict[int, Dict] = {}
        finish_reason = None

        # ── DeepSeek (优先) ──
        if self.deepseek_client:
            try:
                payload = dict(model=self.deepseek_model, messages=messages,
                               temperature=temperature, max_tokens=max_tokens,
                               stream=True, stream_options={"include_usage": True})
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                logger.info("LLM → DeepSeek(stream) (model=%s, tools=%s)", self.deepseek_model, bool(tools))
                response = await self.deepseek_client.chat.completions.create(**payload)

                async for chunk in response:
                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason

                    if delta.content:
                        full_content += delta.content
                        if on_text:
                            on_text(delta.content)

                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
                            buf = tool_call_buffers[idx]
                            if tc_delta.id:
                                buf["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    buf["function"]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    buf["function"]["arguments"] += tc_delta.function.arguments

                self._consecutive_failures = 0

                tool_calls = []
                if tool_call_buffers:
                    for idx in sorted(tool_call_buffers.keys()):
                        buf = tool_call_buffers[idx]
                        tc_id = buf["id"]
                        if not tc_id:
                            tc_id = f"call_{buf['function']['name']}_{int(time.time())}"
                        tool_calls.append({
                            "id": tc_id, "type": "function",
                            "function": {"name": buf["function"]["name"], "arguments": buf["function"]["arguments"]},
                        })

                logger.info("LLM DeepSeek(stream)返回: content_len=%d tool_calls=%s finish=%s",
                            len(full_content), bool(tool_calls), finish_reason)
                return LLMResponse(content=full_content, tool_calls=tool_calls if tool_calls else None)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"DeepSeek 流式调用异常: {e}")

        # ── OpenRouter (fallback) ──
        if self.openrouter_client:
            try:
                payload = dict(model="deepseek-chat", messages=messages,
                               temperature=temperature, max_tokens=max_tokens,
                               stream=True, stream_options={"include_usage": True})
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                logger.info("LLM → OpenRouter(stream) (tools=%s)", bool(tools))
                response = await self.openrouter_client.chat.completions.create(**payload)

                async for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason

                    if delta.content:
                        full_content += delta.content
                        if on_text:
                            on_text(delta.content)

                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
                            buf = tool_call_buffers[idx]
                            if tc_delta.id:
                                buf["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    buf["function"]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    buf["function"]["arguments"] += tc_delta.function.arguments

                self._consecutive_failures = 0

                tool_calls = []
                if tool_call_buffers:
                    for idx in sorted(tool_call_buffers.keys()):
                        buf = tool_call_buffers[idx]
                        tool_calls.append({
                            "id": buf["id"] or f"call_{buf['function']['name']}_{int(time.time())}",
                            "type": "function",
                            "function": {"name": buf["function"]["name"], "arguments": buf["function"]["arguments"]},
                        })

                logger.info("LLM OpenRouter(stream)返回: content_len=%d tool_calls=%s finish=%s",
                            len(full_content), bool(tool_calls), finish_reason)
                return LLMResponse(content=full_content, tool_calls=tool_calls if tool_calls else None)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"OpenRouter 流式调用异常: {e}")

        # ── GLM (最后 fallback) ──
        if self.client and self.api_key:
            try:
                logger.info("LLM → GLM(stream) (tools=%s)", bool(tools))
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model="glm-4-flash", messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                    stream=True, timeout=self.timeout,
                )
                for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason

                    if delta.content:
                        full_content += delta.content
                        if on_text:
                            on_text(delta.content)

                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
                            buf = tool_call_buffers[idx]
                            if tc_delta.id:
                                buf["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    buf["function"]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    buf["function"]["arguments"] += tc_delta.function.arguments

                self._consecutive_failures = 0

                tool_calls = []
                if tool_call_buffers:
                    for idx in sorted(tool_call_buffers.keys()):
                        buf = tool_call_buffers[idx]
                        tc_id = buf["id"]
                        if not tc_id:
                            tc_id = f"call_{buf['function']['name']}_{int(time.time())}"
                        tool_calls.append({
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": buf["function"]["name"],
                                "arguments": buf["function"]["arguments"],
                            },
                        })

                return LLMResponse(content=full_content, tool_calls=tool_calls if tool_calls else None)

            except Exception as e:
                logger.error(f"GLM 流式调用异常: {e}")

        self._consecutive_failures += 1
        return LLMResponse(content="[LLM_MOCK] 流式调用失败")

    def is_available(self) -> bool:
        if self._consecutive_failures >= self._max_consecutive_failures:
            logger.warning(f"LLM 连续 {self._consecutive_failures} 次调用失败，标记为不可用")
            return False
        return self.client is not None or self.deepseek_client is not None or self.openrouter_client is not None

    def _generate_fallback_response(self, messages) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return f"已收到请求：{msg.get('content', '')[:50]}... 系统正在处理。"
        return "您好！系统已就绪。"


# ============================================================
# ★ 新路由层：多 LLM 提供商路由（参考小龙虾 LLMRouter）
# ============================================================

class RoutingStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_LOAD = "least_load"
    PRIORITY = "priority"
    FALLBACK_CHAIN = "fallback_chain"


@dataclass
class LLMProvider:
    """LLM 提供商配置"""
    name: str
    model: str
    api_key_env: str = ""
    base_url: str = ""
    weight: int = 1
    rate_limit: int = 60
    concurrency: int = 5

    # 运行时状态
    current_load: int = 0
    total_calls: int = 0
    failed_calls: int = 0
    last_active: float = 0.0


class MultiLLMRouter:
    """多 LLM 提供商路由 — 4 种策略

    用法:
        router = MultiLLMRouter()
        router.register_provider(LLMProvider(name="ds", model="ds-chat", weight=4))
        router.register_provider(LLMProvider(name="gpt4", model="gpt-4o", weight=2))
        provider = await router.select()  # 按策略选一个
        # ... 调用 provider ...
        router.record_success(provider.name, duration_ms=100)
    """

    _instance: Optional["MultiLLMRouter"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.providers: Dict[str, LLMProvider] = {}
        self.strategy = RoutingStrategy.ROUND_ROBIN
        self._rr_index: int = 0
        self._lock = asyncio.Lock()
        logger.info("MultiLLMRouter 初始化 (策略: %s)", self.strategy.value)

    def register_provider(self, provider: LLMProvider) -> None:
        self.providers[provider.name] = provider
        logger.info("注册 LLM 提供商: %s (%s)", provider.name, provider.model)

    def remove_provider(self, name: str) -> None:
        self.providers.pop(name, None)

    def clear(self) -> None:
        """清空所有 provider（方便测试）"""
        self.providers.clear()
        self._rr_index = 0

    def set_strategy(self, strategy: RoutingStrategy) -> None:
        self.strategy = strategy
        logger.info("切换路由策略: %s", strategy.value)

    def load_from_config(self, config: Dict[str, Any]) -> None:
        """从配置字典加载提供商"""
        strategy_name = config.get("strategy", "round_robin")
        try:
            self.strategy = RoutingStrategy(strategy_name)
        except ValueError:
            self.strategy = RoutingStrategy.ROUND_ROBIN
        for prov in config.get("providers", []):
            self.register_provider(LLMProvider(
                name=prov.get("name", "unknown"),
                model=prov.get("model", ""),
                api_key_env=prov.get("api_key_env", ""),
                weight=prov.get("weight", 1),
                rate_limit=prov.get("rate_limit", 60),
                concurrency=prov.get("concurrency", 5),
            ))

    async def select(self, task_type: str = "") -> Optional[LLMProvider]:
        """根据当前策略选出一个 LLM provider"""
        if not self.providers:
            return None
        async with self._lock:
            if self.strategy == RoutingStrategy.ROUND_ROBIN:
                return self._round_robin()
            elif self.strategy == RoutingStrategy.LEAST_LOAD:
                return self._least_load()
            elif self.strategy == RoutingStrategy.PRIORITY:
                return self._priority()
            elif self.strategy == RoutingStrategy.FALLBACK_CHAIN:
                return self._fallback_chain()
            return self._round_robin()

    def _round_robin(self) -> Optional[LLMProvider]:
        available = [p for p in self.providers.values() if p.current_load < p.concurrency]
        if not available:
            return None
        total_weight = sum(p.weight for p in available)
        idx = self._rr_index % max(total_weight, 1)
        self._rr_index = idx + 1
        cumulative = 0
        for p in available:
            cumulative += p.weight
            if idx < cumulative:
                p.current_load += 1
                return p
        return available[0]

    def _least_load(self) -> Optional[LLMProvider]:
        available = [p for p in self.providers.values() if p.current_load < p.concurrency]
        if not available:
            return None
        best = min(available, key=lambda p: p.current_load)
        best.current_load += 1
        return best

    def _priority(self) -> Optional[LLMProvider]:
        sorted_ps = sorted(self.providers.values(), key=lambda p: p.weight, reverse=True)
        for p in sorted_ps:
            if p.current_load < p.concurrency:
                p.current_load += 1
                return p
        return None

    def _fallback_chain(self) -> Optional[LLMProvider]:
        for p in self.providers.values():
            if p.current_load < p.concurrency:
                p.current_load += 1
                return p
        return None

    def release(self, provider_name: str) -> None:
        """ponytail: 调用方完成请求后必须调用，释放并发槽位"""
        if provider_name in self.providers:
            p = self.providers[provider_name]
            p.current_load = max(0, p.current_load - 1)

    def record_success(self, provider_name: str, duration_ms: float = 0) -> None:
        if provider_name in self.providers:
            p = self.providers[provider_name]
            p.total_calls += 1
            p.current_load = max(0, p.current_load - 1)
            p.last_active = time.time()

    def record_failure(self, provider_name: str) -> None:
        if provider_name in self.providers:
            p = self.providers[provider_name]
            p.failed_calls += 1
            p.current_load = max(0, p.current_load - 1)

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {"model": p.model, "total_calls": p.total_calls,
                   "failed_calls": p.failed_calls,
                   "success_rate": (p.total_calls - p.failed_calls) / max(p.total_calls, 1),
                   "current_load": p.current_load, "concurrency": p.concurrency}
            for name, p in self.providers.items()
        }


# ============================================================
# 向后兼容的 LLMRouter（包装 GLMBackend + 新路由）
# ============================================================

class LLMRouter:
    """LLM 路由器 — 兼容旧接口，底层使用 MultiLLMRouter 多路由"""

    def __init__(self):
        self.backend = GLMBackend()
        self.multi_router = MultiLLMRouter()
        # 自动注册默认 provider
        self.multi_router.register_provider(LLMProvider(
            name="default",
            model=DEFAULT_MODEL,
            api_key_env="ZHIPU_API_KEY",
            weight=1,
            concurrency=3,
        ))

    async def chat(self, messages, temperature=0.7, max_tokens=4096,
                   model=None, tools=None) -> str:
        return await self.backend.chat(messages, temperature=temperature,
                                       max_tokens=max_tokens, model=model, tools=tools)

    async def chat_structured(self, messages, temperature=0.7, max_tokens=4096,
                              model=None, tools=None) -> LLMResponse:
        return await self.backend.chat_structured(messages, temperature=temperature,
                                                  max_tokens=max_tokens, model=model, tools=tools)

    async def simple_chat(self, user_message: str, system_prompt=None,
                          temperature=0.7, max_tokens=None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        kwargs = {"temperature": temperature}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return await self.backend.chat(messages, **kwargs)

    async def chat_stream(self, messages, temperature=0.7, max_tokens=4096,
                          model=None) -> AsyncIterator[str]:
        async for chunk in self.backend.chat_stream(messages, temperature, max_tokens, model):
            yield chunk

    async def chat_structured_stream(self, messages, temperature=0.7, max_tokens=4096,
                                      model=None, tools=None, on_text=None) -> LLMResponse:
        """流式工具调用（路由层代理）"""
        return await self.backend.chat_structured_stream(
            messages, temperature=temperature, max_tokens=max_tokens,
            model=model, tools=tools, on_text=on_text,
        )

    def is_available(self) -> bool:
        return self.backend.is_available()

    def switch_model(self, model: str) -> bool:
        return self.backend.switch_model(model)

    def get_model(self) -> str:
        return self.backend.get_model()

    def get_token_stats(self) -> Dict[str, Any]:
        return self.backend.get_token_stats()

    # ── 新路由 API ──

    def register_provider(self, name: str, model: str, weight: int = 1,
                          concurrency: int = 3, api_key_env: str = "") -> None:
        self.multi_router.register_provider(LLMProvider(
            name=name, model=model, weight=weight,
            concurrency=concurrency, api_key_env=api_key_env,
        ))

    def set_routing_strategy(self, strategy: str) -> None:
        try:
            self.multi_router.set_strategy(RoutingStrategy(strategy))
        except ValueError:
            pass

    async def select_provider(self) -> Optional[str]:
        p = await self.multi_router.select()
        return p.name if p else None

    def get_router_stats(self) -> Dict[str, Any]:
        return self.multi_router.get_stats()


# ============================================================
# 全局单例
# ============================================================

_router_instance: Optional[LLMRouter] = None
_router_lock = threading.Lock()


def get_llm_router() -> LLMRouter:
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = LLMRouter()
    return _router_instance


def get_multi_router() -> MultiLLMRouter:
    """获取多 LLM 路由实例（直接访问新路由层）"""
    return get_llm_router().multi_router
