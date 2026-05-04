"""
LLM抽象层 - 统一模型接入

职责：
1. 模型路由 - 根据任务类型选择合适模型
2. 负载均衡 - 多副本时自动分配
3. 限流控制 - 防止API配额耗尽
4. 成本优化 - 优先使用低成本模型
5. 降级策略 - 主模型失败自动切换备选
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import os

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """模型类型"""
    GPT4 = "gpt-4"
    GPT35 = "gpt-3.5-turbo"
    CLAUDE = "claude"
    LOCAL = "local"


@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    model_type: ModelType
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4000
    temperature: float = 0.7
    cost_per_1k_tokens: float = 0.002
    rate_limit: int = 60
    is_available: bool = True


@dataclass
class LLMRequest:
    """LLM请求"""
    prompt: str
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stop: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    model: str
    usage: Dict[str, int]
    latency: float
    cost: float


@dataclass
class CostTracker:
    """成本追踪器"""
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    cost_by_model: Dict[str, float] = field(default_factory=dict)
    requests_by_model: Dict[str, int] = field(default_factory=dict)

    def record(self, model: str, tokens: int, cost: float) -> None:
        """记录成本"""
        self.total_requests += 1
        self.total_tokens += tokens
        self.total_cost += cost

        self.cost_by_model[model] = self.cost_by_model.get(model, 0) + cost
        self.requests_by_model[model] = self.requests_by_model.get(model, 0) + 1


class RateLimiter:
    """限流器"""

    def __init__(self):
        self.requests: Dict[str, List[float]] = {}
        self.locks: Dict[str, asyncio.Lock] = {}

    async def acquire(self, model: str, rate_limit: int) -> bool:
        """获取限流令牌"""
        if model not in self.locks:
            self.locks[model] = asyncio.Lock()

        async with self.locks[model]:
            current_time = time.time()
            window_start = current_time - 60

            if model in self.requests:
                self.requests[model] = [t for t in self.requests[model] if t > window_start]

            if len(self.requests.get(model, [])) >= rate_limit:
                return False

            if model not in self.requests:
                self.requests[model] = []
            self.requests[model].append(current_time)

            return True

    async def wait_for_slot(self, model: str, rate_limit: int, timeout: float = 60) -> bool:
        """等待限流槽位"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if await self.acquire(model, rate_limit):
                return True

            await asyncio.sleep(1)

        return False


class ModelRouter:
    """模型路由器"""

    def __init__(self, models: Dict[str, ModelConfig]):
        self.models = models

    def route(self, task_type: str, requirements: List[str]) -> Optional[str]:
        """路由到合适的模型"""
        candidates = []

        for model_name, config in self.models.items():
            if not config.is_available:
                continue

            score = 0

            if task_type in requirements:
                score += 30

            score += 20 if config.is_available else 0

            cost_score = max(0, 10 - config.cost_per_1k_tokens * 1000)
            score += cost_score

            rate_score = config.rate_limit / 60
            score += rate_score * 10

            candidates.append((model_name, score))

        candidates.sort(key=lambda x: x[1], reverse=True)

        return candidates[0][0] if candidates else None


class LLMFacade:
    """LLM抽象层 - 统一模型接入"""

    def __init__(self):
        self.models: Dict[str, ModelConfig] = {}
        self._initialize_models()

        self.router = ModelRouter(self.models)
        self.rate_limiter = RateLimiter()
        self.cost_tracker = CostTracker()

        self.on_generate: Optional[Callable] = None

        logger.info("LLM抽象层初始化完成")

    def _initialize_models(self) -> None:
        """初始化模型配置"""
        openai_key = os.getenv("OPENAI_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        if openai_key:
            self.models["gpt-4"] = ModelConfig(
                name="gpt-4",
                model_type=ModelType.GPT4,
                api_key=openai_key,
                max_tokens=8000,
                temperature=0.7,
                cost_per_1k_tokens=0.03,
                rate_limit=200
            )

        if openai_key:
            self.models["gpt-3.5-turbo"] = ModelConfig(
                name="gpt-3.5-turbo",
                model_type=ModelType.GPT35,
                api_key=openai_key,
                max_tokens=4000,
                temperature=0.7,
                cost_per_1k_tokens=0.002,
                rate_limit=300
            )

        if anthropic_key:
            self.models["claude"] = ModelConfig(
                name="claude",
                model_type=ModelType.CLAUDE,
                api_key=anthropic_key,
                max_tokens=8000,
                temperature=0.7,
                cost_per_1k_tokens=0.024,
                rate_limit=100
            )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成内容"""
        start_time = time.time()

        model_name = request.model or self._select_model(request)

        if not model_name:
            raise RuntimeError("没有可用的模型")

        model_config = self.models.get(model_name)

        if not model_config:
            raise RuntimeError(f"模型 {model_name} 不存在")

        if not await self.rate_limiter.wait_for_slot(model_name, model_config.rate_limit):
            fallback = self._find_fallback_model(model_name)
            if fallback:
                model_name = fallback
                model_config = self.models[model_name]
            else:
                raise RuntimeError(f"模型 {model_name} 限流超时")

        try:
            response = await self._call_model(model_name, model_config, request)
        except Exception as e:
            logger.error(f"模型 {model_name} 调用失败: {e}")

            fallback = self._find_fallback_model(model_name)
            if fallback:
                logger.info(f"降级到模型 {fallback}")
                response = await self._call_model(fallback, self.models[fallback], request)
            else:
                raise

        tokens = response.usage.get("total_tokens", 0)
        cost = tokens / 1000 * model_config.cost_per_1k_tokens
        self.cost_tracker.record(model_name, tokens, cost)

        logger.info(f"LLM调用: model={model_name}, tokens={tokens}, cost=${cost:.4f}")

        return response

    def _select_model(self, request: LLMRequest) -> Optional[str]:
        """选择模型"""
        task_type = request.metadata.get("task_type", "general")
        return self.router.route(task_type, request.metadata.get("requirements", []))

    def _find_fallback_model(self, failed_model: str) -> Optional[str]:
        """找到备选模型"""
        for model_name, config in self.models.items():
            if model_name != failed_model and config.is_available:
                return model_name
        return None

    async def _call_model(
        self,
        model_name: str,
        config: ModelConfig,
        request: LLMRequest
    ) -> LLMResponse:
        """调用模型"""
        if self.on_generate:
            content = await self.on_generate(request)
        else:
            await asyncio.sleep(0.1)
            content = f"模拟响应: {request.prompt[:50]}..."

        usage = {
            "prompt_tokens": len(request.prompt) // 4,
            "completion_tokens": len(content) // 4,
            "total_tokens": (len(request.prompt) + len(content)) // 4
        }

        latency = time.time() - start_time

        return LLMResponse(
            content=content,
            model=model_name,
            usage=usage,
            latency=latency,
            cost=0.0
        )

    def get_cost_summary(self) -> Dict[str, Any]:
        """获取成本摘要"""
        return {
            "total_requests": self.cost_tracker.total_requests,
            "total_tokens": self.cost_tracker.total_tokens,
            "total_cost": self.cost_tracker.total_cost,
            "cost_by_model": self.cost_tracker.cost_by_model,
            "requests_by_model": self.cost_tracker.requests_by_model
        }

    def update_model_status(self, model_name: str, available: bool) -> None:
        """更新模型状态"""
        if model_name in self.models:
            self.models[model_name].is_available = available
            logger.info(f"模型 {model_name} 状态更新: {'可用' if available else '不可用'}")
