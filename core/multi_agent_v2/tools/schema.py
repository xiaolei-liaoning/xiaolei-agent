"""
模型感知工具 Schema — 根据模型特点动态调整工具描述

对标 gemini-cli 的模型感知 FunctionDeclaration
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    max_tools: int = 128
    supports_parallel: bool = True
    schema_style: str = "openai"  # openai/anthropic/gemini
    max_tokens: int = 4096
    supports_function_calling: bool = True
    compact_description: bool = False  # 是否精简工具描述以节省 token


# 模型适配表
MODEL_ADAPTERS = {
    # OpenAI 系列
    "gpt-4": ModelConfig(
        name="gpt-4",
        max_tools=128,
        supports_parallel=True,
        schema_style="openai",
        max_tokens=8192,
    ),
    "gpt-4-turbo": ModelConfig(
        name="gpt-4-turbo",
        max_tools=128,
        supports_parallel=True,
        schema_style="openai",
        max_tokens=4096,
    ),
    "gpt-4o": ModelConfig(
        name="gpt-4o",
        max_tools=128,
        supports_parallel=True,
        schema_style="openai",
        max_tokens=16384,
    ),
    "gpt-3.5-turbo": ModelConfig(
        name="gpt-3.5-turbo",
        max_tools=64,
        supports_parallel=True,
        schema_style="openai",
        max_tokens=4096,
        compact_description=True,
    ),

    # Anthropic 系列
    "claude-3-opus": ModelConfig(
        name="claude-3-opus",
        max_tools=128,
        supports_parallel=True,
        schema_style="anthropic",
        max_tokens=4096,
    ),
    "claude-3-sonnet": ModelConfig(
        name="claude-3-sonnet",
        max_tools=128,
        supports_parallel=True,
        schema_style="anthropic",
        max_tokens=4096,
    ),
    "claude-3-haiku": ModelConfig(
        name="claude-3-haiku",
        max_tools=64,
        supports_parallel=True,
        schema_style="anthropic",
        max_tokens=4096,
        compact_description=True,
    ),

    # Google 系列
    "gemini-pro": ModelConfig(
        name="gemini-pro",
        max_tools=128,
        supports_parallel=True,
        schema_style="gemini",
        max_tokens=8192,
    ),
    "gemini-1.5-pro": ModelConfig(
        name="gemini-1.5-pro",
        max_tools=128,
        supports_parallel=True,
        schema_style="gemini",
        max_tokens=8192,
    ),

    # 开源模型
    "qwen-turbo": ModelConfig(
        name="qwen-turbo",
        max_tools=32,
        supports_parallel=False,
        schema_style="openai",
        max_tokens=2048,
        compact_description=True,
    ),
    "qwen-plus": ModelConfig(
        name="qwen-plus",
        max_tools=64,
        supports_parallel=True,
        schema_style="openai",
        max_tokens=4096,
    ),
    "glm-4": ModelConfig(
        name="glm-4",
        max_tools=64,
        supports_parallel=True,
        schema_style="openai",
        max_tokens=4096,
    ),

    # Nemotron
    "nemotron-3-ultra": ModelConfig(
        name="nemotron-3-ultra",
        max_tools=64,
        supports_parallel=True,
        schema_style="openai",
        max_tokens=4096,
    ),
}

# 默认配置
DEFAULT_CONFIG = ModelConfig(
    name="default",
    max_tools=32,
    supports_parallel=False,
    schema_style="openai",
    max_tokens=2048,
    compact_description=True,
)


class SchemaAdapter:
    """模型感知 Schema 适配器"""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or "default"
        self.config = self._get_config(self.model_name)

    def _get_config(self, model_name: str) -> ModelConfig:
        """获取模型配置"""
        # 精确匹配
        if model_name in MODEL_ADAPTERS:
            return MODEL_ADAPTERS[model_name]

        # 模糊匹配（支持部分名称）
        for key, config in MODEL_ADAPTERS.items():
            if model_name.lower() in key.lower() or key.lower() in model_name.lower():
                return config

        # 使用默认配置
        logger.debug(f"未找到模型 {model_name} 的配置，使用默认配置")
        return DEFAULT_CONFIG

    def adapt(self, tools: List[Dict]) -> List[Dict]:
        """
        根据模型特点适配工具 Schema

        Args:
            tools: 原始工具定义列表

        Returns:
            适配后的工具定义列表
        """
        if not tools:
            return tools

        adapted = []
        for tool in tools[:self.config.max_tools]:
            adapted_tool = self._adapt_tool(tool)
            adapted.append(adapted_tool)

        if len(tools) > self.config.max_tools:
            logger.warning(
                f"工具数量 {len(tools)} 超过模型限制 {self.config.max_tools}，"
                f"已截断为 {len(adapted)} 个"
            )

        return adapted

    def _adapt_tool(self, tool: Dict) -> Dict:
        """适配单个工具定义"""
        if "function" not in tool:
            return tool

        func = tool["function"].copy()
        name = func.get("name", "")
        description = func.get("description", "")
        parameters = func.get("parameters", {})

        # 根据 schema_style 调整格式
        if self.config.schema_style == "anthropic":
            # Anthropic 格式：使用 input_schema
            adapted = {
                "name": name,
                "description": description,
                "input_schema": parameters,
            }
        elif self.config.schema_style == "gemini":
            # Gemini 格式：简化参数
            adapted = {
                "name": name,
                "description": description,
                "parameters": self._simplify_parameters(parameters),
            }
        else:
            # OpenAI 格式（默认）
            adapted = {
                "name": name,
                "description": description,
                "parameters": parameters,
            }

        # 如果需要compact_description
        if self.config.compact_description:
            adapted["description"] = self._truncate_description(description)

        return {
            "type": "function",
            "function": adapted,
        }

    def _simplify_parameters(self, parameters: Dict) -> Dict:
        """简化参数定义（用于 token 紧张的模型）"""
        if not parameters:
            return parameters

        simplified = parameters.copy()

        # 移除 description 中的长文本
        if "properties" in simplified:
            for prop_name, prop in simplified["properties"].items():
                if isinstance(prop, dict) and "description" in prop:
                    # 截断长描述
                    desc = prop["description"]
                    if len(desc) > 100:
                        prop["description"] = desc[:100] + "..."

        return simplified

    def _truncate_description(self, description: str, max_length: int = 200) -> str:
        """截断工具描述"""
        if len(description) <= max_length:
            return description
        return description[:max_length - 3] + "..."

    def get_max_tools(self) -> int:
        """获取模型支持的最大工具数"""
        return self.config.max_tools

    def supports_parallel(self) -> bool:
        """是否支持并行工具调用"""
        return self.config.supports_parallel

    def get_schema_style(self) -> str:
        """获取 Schema 风格"""
        return self.config.schema_style

    def should_simplify(self) -> bool:
        """是否需要简化 Schema"""
        return self.config.compact_description


def get_schema_adapter(model_name: str = None) -> SchemaAdapter:
    """获取 Schema 适配器实例"""
    return SchemaAdapter(model_name)


def detect_model_from_response(response: Dict) -> str:
    """
    从 LLM 响应中检测模型名称

    用于自动适配 Schema
    """
    # OpenAI 格式
    if "model" in response:
        return response["model"]

    # Anthropic 格式
    if "model" in response.get("metadata", {}):
        return response["metadata"]["model"]

    # 其他格式
    return "default"
