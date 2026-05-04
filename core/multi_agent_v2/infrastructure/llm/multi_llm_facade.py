"""
多LLM支持模块 - 实现对主流大语言模型的适配与集成

功能：
1. 多模型支持（OpenAI, Anthropic, Google, 国产模型等）
2. 模型路由与负载均衡
3. 降级策略
4. 成本控制
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """模型提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    BAIDU = "baidu"
    BYTEDANCE = "bytedance"
    TONGYI = "tongyi"
    QWEN = "qwen"
    DOUBAO = "doubao"
    CUSTOM = "custom"


class ModelType(Enum):
    """模型类型"""
    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    TOOL = "tool"


@dataclass
class ModelInfo:
    """模型信息"""
    model_name: str
    provider: ModelProvider
    model_type: ModelType
    max_tokens: int
    context_window: int
    cost_per_token: float
    availability: float = 1.0
    latency: float = 0.0


@dataclass
class LLMRequest:
    """LLM请求"""
    prompt: str
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    top_p: float = 0.9
    stream: bool = False
    tools: Optional[List[Dict]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    model: str
    token_count: int
    latency: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteStrategy(Enum):
    """路由策略"""
    ROUND_ROBIN = "round_robin"
    LEAST_COST = "least_cost"
    LOWEST_LATENCY = "lowest_latency"
    AVAILABILITY = "availability"
    CUSTOM = "custom"


class ModelRouter:
    """模型路由器"""

    def __init__(self, models: List[ModelInfo], strategy: RouteStrategy = RouteStrategy.ROUND_ROBIN):
        self.models = models
        self.strategy = strategy
        self.round_robin_index = 0

    def select_model(self, request: LLMRequest) -> Optional[ModelInfo]:
        """选择模型"""
        if not self.models:
            return None

        # 过滤可用模型
        available_models = [m for m in self.models if m.availability > 0.7]

        if not available_models:
            return None

        if self.strategy == RouteStrategy.ROUND_ROBIN:
            return self._round_robin(available_models)
        elif self.strategy == RouteStrategy.LEAST_COST:
            return self._least_cost(available_models)
        elif self.strategy == RouteStrategy.LOWEST_LATENCY:
            return self._lowest_latency(available_models)
        elif self.strategy == RouteStrategy.AVAILABILITY:
            return self._highest_availability(available_models)
        else:
            return available_models[0]

    def _round_robin(self, models: List[ModelInfo]) -> ModelInfo:
        """轮询选择"""
        model = models[self.round_robin_index % len(models)]
        self.round_robin_index += 1
        return model

    def _least_cost(self, models: List[ModelInfo]) -> ModelInfo:
        """选择成本最低的模型"""
        return min(models, key=lambda m: m.cost_per_token)

    def _lowest_latency(self, models: List[ModelInfo]) -> ModelInfo:
        """选择延迟最低的模型"""
        return min(models, key=lambda m: m.latency)

    def _highest_availability(self, models: List[ModelInfo]) -> ModelInfo:
        """选择可用性最高的模型"""
        return max(models, key=lambda m: m.availability)


class OpenAIAdapter:
    """OpenAI模型适配器"""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成响应"""
        start_time = time.time()

        try:
            import openai

            client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

            response = await client.chat.completions.create(
                model=request.model or "gpt-3.5-turbo",
                messages=[{"role": "user", "content": request.prompt}],
                max_tokens=request.max_tokens or 1024,
                temperature=request.temperature,
                top_p=request.top_p
            )

            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                token_count=response.usage.total_tokens,
                latency=time.time() - start_time,
                success=True
            )

        except Exception as e:
            return LLMResponse(
                content="",
                model=request.model or "unknown",
                token_count=0,
                latency=time.time() - start_time,
                success=False,
                error=str(e)
            )


class AnthropicAdapter:
    """Anthropic模型适配器"""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成响应"""
        start_time = time.time()

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)

            response = client.messages.create(
                model=request.model or "claude-3-sonnet-20240229",
                max_tokens=request.max_tokens or 1024,
                temperature=request.temperature,
                messages=[{"role": "user", "content": request.prompt}]
            )

            return LLMResponse(
                content=response.content[0].text,
                model=response.model,
                token_count=response.usage.output_tokens,
                latency=time.time() - start_time,
                success=True
            )

        except Exception as e:
            return LLMResponse(
                content="",
                model=request.model or "unknown",
                token_count=0,
                latency=time.time() - start_time,
                success=False,
                error=str(e)
            )


class GoogleAdapter:
    """Google模型适配器"""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成响应"""
        start_time = time.time()

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(request.model or "gemini-pro")

            response = await model.generate_content_async(request.prompt)

            return LLMResponse(
                content=response.text,
                model=request.model or "gemini-pro",
                token_count=0,
                latency=time.time() - start_time,
                success=True
            )

        except Exception as e:
            return LLMResponse(
                content="",
                model=request.model or "unknown",
                token_count=0,
                latency=time.time() - start_time,
                success=False,
                error=str(e)
            )


class CustomAdapter:
    """自定义模型适配器"""

    def __init__(self, endpoint: str, api_key: Optional[str] = None):
        self.endpoint = endpoint
        self.api_key = api_key

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成响应"""
        start_time = time.time()

        try:
            import aiohttp

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            payload = {
                "prompt": request.prompt,
                "max_tokens": request.max_tokens or 1024,
                "temperature": request.temperature
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.endpoint, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return LLMResponse(
                            content=data.get("content", ""),
                            model=data.get("model", "custom"),
                            token_count=data.get("token_count", 0),
                            latency=time.time() - start_time,
                            success=True
                        )
                    else:
                        return LLMResponse(
                            content="",
                            model="custom",
                            token_count=0,
                            latency=time.time() - start_time,
                            success=False,
                            error=f"HTTP {resp.status}"
                        )

        except Exception as e:
            return LLMResponse(
                content="",
                model="custom",
                token_count=0,
                latency=time.time() - start_time,
                success=False,
                error=str(e)
            )


class MultiLLMFacade:
    """多LLM门面 - 统一接口"""

    def __init__(self):
        self.adapters: Dict[str, Any] = {}
        self.models: List[ModelInfo] = []
        self.router = ModelRouter([])
        self.route_strategy = RouteStrategy.ROUND_ROBIN
        self.rate_limiter = None
        self.fallback_model = None

    def register_adapter(self, provider: ModelProvider, adapter: Any):
        """注册模型适配器"""
        self.adapters[provider.value] = adapter
        logger.info(f"已注册适配器: {provider.value}")

    def add_model(self, model_info: ModelInfo):
        """添加模型"""
        self.models.append(model_info)
        self.router = ModelRouter(self.models, self.route_strategy)
        logger.info(f"已添加模型: {model_info.model_name}")

    def set_route_strategy(self, strategy: RouteStrategy):
        """设置路由策略"""
        self.route_strategy = strategy
        self.router = ModelRouter(self.models, strategy)
        logger.info(f"路由策略已更新: {strategy.value}")

    def set_fallback_model(self, model_name: str):
        """设置降级模型"""
        self.fallback_model = model_name
        logger.info(f"降级模型已设置: {model_name}")

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成响应"""
        start_time = time.time()

        # 选择模型
        model_info = self.router.select_model(request)

        if not model_info:
            return LLMResponse(
                content="",
                model="unknown",
                token_count=0,
                latency=time.time() - start_time,
                success=False,
                error="没有可用的模型"
            )

        # 获取适配器
        adapter = self.adapters.get(model_info.provider.value)

        if not adapter:
            return LLMResponse(
                content="",
                model=model_info.model_name,
                token_count=0,
                latency=time.time() - start_time,
                success=False,
                error=f"未找到适配器: {model_info.provider.value}"
            )

        # 设置请求模型
        request.model = model_info.model_name

        # 调用适配器
        response = await adapter.generate(request)

        # 如果失败且有降级模型，尝试降级
        if not response.success and self.fallback_model:
            fallback_info = next((m for m in self.models if m.model_name == self.fallback_model), None)
            if fallback_info:
                fallback_adapter = self.adapters.get(fallback_info.provider.value)
                if fallback_adapter:
                    logger.warning(f"主模型失败，尝试降级到: {self.fallback_model}")
                    request.model = self.fallback_model
                    response = await fallback_adapter.generate(request)

        # 更新模型可用性和延迟
        model_info.latency = response.latency
        if response.success:
            model_info.availability = min(1.0, model_info.availability + 0.01)
        else:
            model_info.availability = max(0.0, model_info.availability - 0.05)

        return response

    async def generate_with_retry(self, request: LLMRequest, max_retries: int = 2) -> LLMResponse:
        """带重试的生成"""
        for attempt in range(max_retries + 1):
            response = await self.generate(request)
            if response.success:
                return response

            if attempt < max_retries:
                await asyncio.sleep(1)  # 等待1秒后重试

        return response

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """获取模型信息"""
        return next((m for m in self.models if m.model_name == model_name), None)

    def list_models(self) -> List[ModelInfo]:
        """列出所有模型"""
        return self.models

    def get_cost_estimate(self, prompt_tokens: int, completion_tokens: int, model_name: str) -> float:
        """估算成本"""
        model_info = self.get_model_info(model_name)
        if not model_info:
            return 0.0

        return (prompt_tokens + completion_tokens) * model_info.cost_per_token / 1000
