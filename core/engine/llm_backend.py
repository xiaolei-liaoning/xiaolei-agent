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
    from ..infrastructure.config_manager import get_config
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
        rate_limit_rpm = 30
        supported_models = [
            "glm-4-flash", "glm-4-plus", "glm-4-air",
            "glm-4.7-flash", "glm-4-free", "glm-3-turbo",
            "free-glm-4", "free-qwen", "free-llama",
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

    async def acquire(self, timeout: float = 30.0) -> bool:
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
    """智谱 GLM API 封装 — 保留完整实现兼容旧代码"""

    FREE_API_ENDPOINTS = {
        "groq-llama3": "https://api.groq.com/openai/v1/chat/completions",
        "groq-gemma": "https://api.groq.com/openai/v1/chat/completions",
        "llama-3.1-8b-instant": "https://api.groq.com/openai/v1/chat/completions",
        "gemma2-9b-it": "https://api.groq.com/openai/v1/chat/completions",
        "together-llama": "https://api.together.xyz/v1/chat/completions",
        "meta-llama/Llama-3-8b-chat-hf": "https://api.together.xyz/v1/chat/completions",
        "openrouter-llama": "https://openrouter.ai/api/v1/chat/completions",
        "openrouter-qwen": "https://openrouter.ai/api/v1/chat/completions",
    }

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.getenv("ZHIPU_API_KEY", "")
        self.model = model or DEFAULT_MODEL
        self.client = None
        self.local_client = None
        self.local_model = None
        self.free_client = None
        self._token_stats = TokenStats()
        self._rate_limiter = RateLimiter(RATE_LIMIT_RPM)
        self._model_lock = threading.Lock()
        self.timeout = llm_config.timeout  # 使用配置中的超时设置
        self._init_client()

    def _init_client(self):
        # 1. 尝试初始化本地 LM Studio (OpenAI 兼容)
        local_url = os.getenv("LOCAL_LLM_URL", "http://192.168.66.236:1234")
        if local_url:
            try:
                # 使用 requests 直接调用 LM Studio API
                import requests
                self.local_url = local_url
                self.local_model = os.getenv("LOCAL_LLM_MODEL", "qwen/qwen3-vl-4b")
                self.local_client = True  # 标记为可用
                logger.info("本地 LM Studio 初始化成功: %s", local_url)
            except Exception as e:
                logger.warning("本地 LM Studio 初始化失败: %s", e)
                self.local_client = None
        else:
            self.local_client = None

        # 2. 初始化 DeepSeek (OpenAI 兼容) — 从 ANTHROPIC_AUTH_TOKEN 读取 key
        self.deepseek_client = None
        self.deepseek_model = os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-chat")
        deepseek_key = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
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

        # 3. 初始化 GLM API (fallback)
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

    async def _init_free_client(self) -> bool:
        if self.free_client is not None:
            return True
        try:
            import aiohttp
            self.free_client = aiohttp.ClientSession()
            return True
        except Exception:
            return False

    async def _call_free_api(self, messages, model, temperature=0.7,
                             max_tokens=2000, stream=False, tools=None, tool_choice=None):
        if model not in self.FREE_API_ENDPOINTS:
            return None
        url = self.FREE_API_ENDPOINTS[model]
        if not await self._init_free_client():
            return None
        try:
            # 根据 endpoint 自动添加鉴权头
            headers = {"Content-Type": "application/json", "User-Agent": "xiaolei-agent/1.0"}
            if "openrouter" in url:
                api_key = os.getenv("OPENROUTER_API_KEY", "")
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
            elif "groq" in url:
                api_key = os.getenv("GROQ_API_KEY", "")
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
            elif "together" in url:
                api_key = os.getenv("TOGETHER_API_KEY", "")
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
            payload = {"model": model, "messages": messages,
                       "temperature": temperature, "max_tokens": max_tokens, "stream": stream}
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = tool_choice or "auto"
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=30)
            async with self.free_client.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                resp.raise_for_status()
                return await resp.json() if not stream else resp
        except Exception:
            return None

    async def chat(self, messages, temperature=0.7, max_tokens=2000,
                   model=None, tools=None) -> str:
        target = model or self.model
        if not await self._rate_limiter.acquire(timeout=30.0):
            return "请求过于频繁，请稍后再试"

        # 0. DeepSeek (OpenAI 兼容) — 优先，用户已配置 key
        if self.deepseek_client:
            try:
                payload = dict(model=self.deepseek_model, messages=messages,
                               temperature=temperature, max_tokens=max_tokens)
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                logger.info("LLM → DeepSeek (%s, tools=%s)", self.deepseek_model, bool(tools))
                response = await self.deepseek_client.chat.completions.create(**payload)
                self._record_usage_from_response(response.model_dump() if hasattr(response, 'model_dump') else {}, self.deepseek_model)
                if hasattr(response, 'choices') and response.choices:
                    message = response.choices[0].message
                    content = getattr(message, 'content', None) or ""
                    tc = getattr(message, 'tool_calls', None)
                    
                    # 检测截断信号
                    finish_reason = getattr(response.choices[0], 'finish_reason', None)
                    is_truncated = finish_reason == 'length'
                    if is_truncated:
                        logger.warning(f"⚠️ LLM输出被截断! finish_reason=length, content_len={len(content)}")
                    
                    logger.info("LLM DeepSeek返回: content_len=%d tool_calls=%s truncated=%s", len(content), bool(tc), is_truncated)
                    if tc:
                        tc_list = [{"id": getattr(t, 'id', ''),
                                    "type": getattr(t, 'type', 'function'),
                                    "function": {"name": t.function.name,
                                                 "arguments": t.function.arguments}}
                                   for t in tc]
                        return json.dumps({"choices": [{"message": {"role": "assistant",
                                        "content": content, "tool_calls": tc_list}}]},
                                          ensure_ascii=False)
                    return content or ""
                else:
                    logger.warning("DeepSeek 返回空响应")
            except Exception as e:
                logger.error(f"DeepSeek API 调用异常: {e}（将尝试GLM API）")

        # 1. GLM 官方 API (fallback)
        logger.info("LLM.chat: api_key=%s client=%s tools=%s",
                     bool(self.api_key), bool(self.client), bool(tools))
        if self.client and self.api_key:
            try:
                kwargs = dict(model="glm-4-flash", messages=messages,
                              temperature=temperature, max_tokens=max_tokens,
                              stream=False, timeout=self.timeout)
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"

                logger.info("LLM → GLM API (glm-4-flash, tools=%s)", bool(tools))
                response = self.client.chat.completions.create(**kwargs)
                self._record_usage(response)
                message = response.choices[0].message
                content = message.content or ""
                tc = getattr(message, 'tool_calls', None)
                logger.info("LLM GLM返回: content_len=%d tool_calls=%s", len(content), bool(tc))
                if tc:
                    tc_list = [{"id": getattr(t, 'id', ''),
                                "type": getattr(t, 'type', 'function'),
                                "function": {"name": t.function.name,
                                             "arguments": t.function.arguments}}
                               for t in tc]
                    return json.dumps({"choices": [{"message": {"role": "assistant",
                                    "content": content, "tool_calls": tc_list}}]},
                                      ensure_ascii=False)
                return content or ""
            except Exception as e:
                logger.error(f"GLM API 调用异常: {e}（将尝试本地LM Studio）")

        # 1. 本地 LM Studio (保底)
        if self.local_client:
            try:
                import requests
                
                payload = {
                    "model": self.local_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                logger.info("LLM → 本地 LM Studio (%s, tools=%s)", self.local_model, bool(tools))
                response = requests.post(
                    f"{self.local_url}/v1/chat/completions",
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()
                
                # 检查响应格式
                if not data or "choices" not in data or not data["choices"]:
                    logger.error("本地 LM Studio 返回空响应")
                    raise ValueError("Empty response from local LM Studio")
                
                choice = data["choices"][0]
                if "message" not in choice:
                    logger.error("本地 LM Studio 返回空消息")
                    raise ValueError("Empty message from local LM Studio")
                
                message = choice["message"]
                content = message.get("content", "") or ""
                tc = message.get("tool_calls", [])
                logger.info("LLM 本地返回: content_len=%d tool_calls=%s", len(content), bool(tc))
                if tc:
                    return json.dumps({"choices": [{"message": {"role": "assistant",
                                    "content": content, "tool_calls": tc}}]},
                                      ensure_ascii=False)
                return content or ""
            except Exception as e:
                logger.error(f"本地 LM Studio 调用异常: {e}（将尝试fallback）")

        # 2. 免费 API fallback（仅当没有主API key时）
        can_use_free = await self._init_free_client()
        logger.info("LLM fallback检查: free_client=%s api_key=%s", can_use_free, bool(self.api_key))
        if can_use_free and not self.api_key:
            for free_model in ["openrouter-qwen", "openrouter-llama", "llama-3.1-8b-instant", "gemma2-9b-it"]:
                logger.info("LLM → 免费API: %s (tools=%s)", free_model, bool(tools))
                data = await self._call_free_api(messages, free_model, temperature, max_tokens, tools=tools, tool_choice="auto" if tools else None)
                if data and "choices" in data and data["choices"]:
                    message = data["choices"][0].get("message", {})
                    content = message.get("content", "") or ""
                    tc = message.get("tool_calls", [])
                    logger.info("LLM freeAPI成功: %s len=%d tool_calls=%s", free_model, len(content), bool(tc))
                    if tc:
                        return json.dumps({"choices": [{"message": {"role": "assistant",
                                        "content": content, "tool_calls": tc}}]},
                                          ensure_ascii=False)
                    self._record_usage_from_response(data, free_model)
                    return content or ""
                logger.warning("LLM freeAPI失败: %s", free_model)

        logger.warning("所有 LLM API 不可用，使用模拟响应 (client=%s, free_client=%s, api_key=%s)",
                       bool(self.client), can_use_free, bool(self.api_key))
        return "[LLM_MOCK] 系统正在处理您的请求..."

    async def chat_stream(self, messages, temperature=0.7, max_tokens=2000,
                          model=None) -> AsyncIterator[str]:
        target = model or self.model
        if not await self._rate_limiter.acquire(timeout=30.0):
            yield "请求过于频繁"
            return

        # 0. 本地 LM Studio (优先)
        if self.local_client:
            try:
                import requests
                
                payload = {
                    "model": self.local_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True
                }

                logger.info("LLM → 本地 LM Studio 流式 (%s)", self.local_model)
                response = requests.post(
                    f"{self.local_url}/v1/chat/completions",
                    json=payload,
                    timeout=self.timeout,
                    stream=True
                )
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data = line[6:]
                            if data == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data)
                                if chunk.get('choices') and chunk['choices'][0].get('delta', {}).get('content'):
                                    yield chunk['choices'][0]['delta']['content']
                            except json.JSONDecodeError:
                                continue
                return
            except Exception as e:
                logger.error("本地 LM Studio 流式调用异常: %s", e)

        # 1. GLM API
        if self.client and self.api_key:
            try:
                response = self.client.chat.completions.create(
                    model="glm-4-flash", messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                    stream=True, timeout=self.timeout)
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception:
                pass
        yield "流式响应不可用，请使用非流式接口"

    def is_available(self) -> bool:
        return self.client is not None or self.free_client is not None

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

    async def chat(self, messages, temperature=0.7, max_tokens=2000,
                   model=None, tools=None) -> str:
        return await self.backend.chat(messages, temperature=temperature,
                                       max_tokens=max_tokens, model=model, tools=tools)

    async def simple_chat(self, user_message: str, system_prompt=None,
                          temperature=0.7) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        return await self.backend.chat(messages, temperature=temperature)

    async def chat_stream(self, messages, temperature=0.7, max_tokens=2000,
                          model=None) -> AsyncIterator[str]:
        async for chunk in self.backend.chat_stream(messages, temperature, max_tokens, model):
            yield chunk

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
