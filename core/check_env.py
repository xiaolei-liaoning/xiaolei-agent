"""环境变量检查 — 在启动时检测 API 密钥和关键配置状态"""

import os
import logging

logger = logging.getLogger(__name__)

# 需要检查的 API 密钥清单
REQUIRED_KEYS = {
    "LLM_API_KEY": ("LLM API", False),       # 也检查这个（可能用户配的是 LLM_API_KEY 而非 ZHIPU_API_KEY）
    "ZHIPU_API_KEY": ("智谱AI (LLM)", False), # 必须项，但用占位符检测
    "DEEPSEEK_API_KEY": ("DeepSeek (LLM备选)", True),
}
OPTIONAL_KEYS = {
    "NVIDIA_API_KEY": ("NVIDIA (免费LLM)", True),
    "OPENROUTER_API_KEY": ("OpenRouter (LLM备选)", True),
    "GROQ_API_KEY": ("Groq (LLM备选)", True),
    "WECHAT_APP_ID": ("微信小程序", True),
    "WECHAT_APP_SECRET": ("微信小程序Secret", True),
}

_PLACEHOLDER_VALUES = {
    "your_zhipu_api_key_here",
    "your_api_key_here",
    "your_key_here",
    "your_token_here",
    "placeholder",
    "",
}


def _is_placeholder(value: str) -> bool:
    return value.strip() in _PLACEHOLDER_VALUES or "your_" in value.lower()


def check_env() -> dict:
    """检查所有环境变量，返回状态报告"""
    # 优先尝试加载 .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    issues = []
    llm_ok = False
    configs = {"llm": [], "optional": [], "missing_llm": False}

    for key, (label, optional) in {**REQUIRED_KEYS, **OPTIONAL_KEYS}.items():
        value = os.getenv(key, "")
        if not value:
            if optional:
                continue  # 可选且无值，不报
            issues.append(f"  ❌ {label}: 未配置 (设置 {key}=your_key)")
            if "LLM" in label or "智谱" in label:
                configs["missing_llm"] = True
        elif _is_placeholder(value):
            issues.append(f"  ⚠️ {label}: 使用了占位符值，需要替换为真实密钥")
            if "LLM" in label or "智谱" in label:
                configs["missing_llm"] = True
        else:
            llm_ok = llm_ok or ("LLM" in label or "智谱" in label)
            configs["llm"].append(label)

    configs["llm_ok"] = llm_ok
    configs["issues"] = issues

    if not issues:
        configs["summary"] = "✅ 所有密钥已配置"
        logger.info("✅ 环境检查通过: 所有密钥已配置")
    else:
        configs["summary"] = f"⚠️ 发现 {len(issues)} 个配置问题"
        logger.warning(f"⚠️ 环境检查: {len(issues)} 个问题")
        for issue in issues:
            logger.warning(issue)

    return configs


def print_env_banner():
    """打印环境状态横幅"""
    configs = check_env()

    if configs["llm_ok"]:
        print("  ✅ LLM: 已配置 (", ", ".join(configs["llm"]), ")")
    else:
        print("  ❌ LLM: 未配置 — 聊天/代码生成/反思功能不可用")

    if configs["issues"]:
        print(f"  ⚠️ 共 {len(configs['issues'])} 个配置问题:")
        for issue in configs["issues"][:5]:  # 最多显示5条
            print(f"    {issue}")
        if len(configs["issues"]) > 5:
            print(f"    ...还有 {len(configs['issues']) - 5} 个问题")
