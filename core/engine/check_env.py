"""环境检查 — 验证 LLM API Key 等基础设施是否就绪"""
import logging
import os

logger = logging.getLogger(__name__)


def check_env() -> dict:
    """检查运行时环境，返回状态字典（llm_ok 表示 LLM 是否可用）"""
    result = {"llm_ok": False}

    zhipu_key = os.getenv("ZHIPU_API_KEY", "")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    llm_key = os.getenv("LLM_API_KEY", "")

    if zhipu_key or deepseek_key or openrouter_key or llm_key:
        result["llm_ok"] = True
        label = "ZHIPU" if zhipu_key else ("OPENROUTER" if openrouter_key else ("DEEPSEEK" if deepseek_key else "CUSTOM"))
        logger.info("LLM 配置检测通过: %s", label)
    else:
        logger.warning("未找到 LLM API Key，请在 .env 中设置 ZHIPU_API_KEY 或 LLM_API_KEY")

    return result
