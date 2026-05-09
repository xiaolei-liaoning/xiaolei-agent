#!/usr/bin/env python3
"""免费 LLM API Key 获取工具

帮助获取、配置和测试免费LLM API资源

功能:
- 列出所有可用的免费LLM API
- 提供API Key获取链接
- 生成配置模板
- 测试API连接

使用方法:
  python free_llm_setup.py list                    # 列出所有免费API
  python free_llm_setup.py guide groq              # 查看Groq获取指南
  python free_llm_setup.py config                  # 生成配置模板
  python free_llm_setup.py test groq               # 测试Groq API
"""

import argparse
import asyncio
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


class CliColors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_color(text: str, color: str) -> None:
    print(f"{color}{text}{CliColors.ENDC}")


def print_success(msg: str) -> None:
    print_color(f"✅ {msg}", CliColors.GREEN)


def print_error(msg: str) -> None:
    print_color(f"❌ {msg}", CliColors.RED)


def print_warning(msg: str) -> None:
    print_color(f"⚠️  {msg}", CliColors.YELLOW)


def print_info(msg: str) -> None:
    print_color(f"ℹ️  {msg}", CliColors.BLUE)


def print_header(title: str) -> None:
    print()
    print_color("=" * 70, CliColors.BOLD)
    print_color(f"  {title}", CliColors.BOLD)
    print_color("=" * 70, CliColors.BOLD)
    print()


# ============================================================================
# 免费LLM API注册信息
# ============================================================================

FREE_LLM_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "nvidia": {
        "name": "NVIDIA NIM",
        "website": "https://org.nvidia.ai/nim/keys",
        "description": "各种开源模型，支持Llama、Qwen、Mistral等",
        "models": ["Llama 3.1 70B", "Llama 3.3 70B", "Qwen 2.5 72B", "Mistral 7B", " Gemma 3 27B"],
        "free_tier": "40 RPM，模型有上下文窗口限制",
        "env_vars": ["NVIDIA_API_KEY"],
        "signup_notes": "需要手机号验证",
        "sdk": "openai",  # NVIDIA NIM兼容OpenAI API
        "install_cmd": "pip install openai",
    },
    "groq": {
        "name": "Groq",
        "website": "https://console.groq.com/keys",
        "description": "超快速推理，无RPM限制（按TPM计费）",
        "models": ["Llama 3.1 8B", "Llama 3.3 70B", "Qwen 3 32B", "Whisper Large v3"],
        "free_tier": "6000-30000 TPM，1000+ RPD",
        "env_vars": ["GROQ_API_KEY"],
        "signup_notes": "使用GitHub或Google账号登录，无需手机号",
        "sdk": "groq",
        "install_cmd": "pip install groq",
    },
    "cohere": {
        "name": "Cohere",
        "website": "https://dashboard.cohere.com/api-keys",
        "description": "Command R+ 和 Command A 系列",
        "models": ["command-r-plus-08-2024", "command-a-03-2025", "c4ai-aya-expanse-32b"],
        "free_tier": "20 RPM，1000次/月",
        "env_vars": ["COHERE_API_KEY"],
        "signup_notes": "需要手机号验证",
        "sdk": "cohere",
        "install_cmd": "pip install cohere",
    },
    "cerebras": {
        "name": "Cerebras",
        "website": "https://cerebras.ai/cloud",
        "description": "超大模型支持，100万tokens/月",
        "models": ["Qwen 3 235B A22B", "Llama 3.3 70B", "gpt-oss-120b"],
        "free_tier": "100万tokens/月",
        "env_vars": ["CEREBRAS_API_KEY"],
        "signup_notes": "需要手机号验证",
        "sdk": "cerebras",
        "install_cmd": "pip install cerebras",
    },
    "openrouter": {
        "name": "OpenRouter",
        "website": "https://openrouter.ai/keys",
        "description": "统一网关，支持多种开源模型",
        "models": ["Gemma 3 27B", "Llama 3.2 3B", "Qwen3 4B", "Mistral Small 3.1 24B"],
        "free_tier": "50次/天（充值后可达1000次/天）",
        "env_vars": ["OPENROUTER_API_KEY"],
        "signup_notes": "支持GitHub/Google登录",
        "sdk": "openai",
        "install_cmd": "pip install openai",
    },
    "google": {
        "name": "Google AI Studio",
        "website": "https://aistudio.google.com/app/apikey",
        "description": "Gemini系列模型",
        "models": ["gemini-2.5-flash", "gemini-3-flash", "gemma-3-27b-it"],
        "free_tier": "25万TPM，500RPM",
        "env_vars": ["GOOGLE_API_KEY"],
        "signup_notes": "需要Google账号",
        "sdk": "google-generativeai",
        "install_cmd": "pip install google-generativeai",
    },
    "mistral": {
        "name": "Mistral La Plateforme",
        "website": "https://console.mistral.ai/api-keys/",
        "description": "Mistral系列模型",
        "models": ["mistral-small-latest", "mistral-large-latest", "codestral"],
        "free_tier": "60 RPM，1000万tokens/月",
        "env_vars": ["MISTRAL_API_KEY"],
        "signup_notes": "需要手机号验证，同意数据训练",
        "sdk": "mistralai",
        "install_cmd": "pip install mistralai",
    },
    "huggingface": {
        "name": "HuggingFace Inference",
        "website": "https://huggingface.co/settings/inference-endpoints",
        "description": "各种开源模型",
        "models": ["各种小于10GB的开源模型"],
        "free_tier": "$0.10/月额度",
        "env_vars": ["HF_TOKEN"],
        "signup_notes": "免费额度有限",
        "sdk": "huggingface_hub",
        "install_cmd": "pip install huggingface_hub",
    },
    "cloudflare": {
        "name": "Cloudflare Workers AI",
        "website": "https://playground.ai.cloudflare.com/",
        "description": "边缘AI推理",
        "models": ["Llama 3.1 8B", "Mistral 7B", "Stable Diffusion"],
        "free_tier": "10000神经元/天",
        "env_vars": ["CF_API_TOKEN"],
        "signup_notes": "需要Cloudflare账号",
        "sdk": "@cloudflare/workers-sdk",
        "install_cmd": "npm install @cloudflare/workers-sdk",
    },
    "hyperbolic": {
        "name": "Hyperbolic",
        "website": "https://app.hyperbolic.xyz/api-keys",
        "description": "各种开源模型",
        "models": ["Llama 3.1 70B", "Qwen 2.5 72B", "Mistral"],
        "free_tier": "$1额度",
        "env_vars": ["HYPERBOLIC_API_KEY"],
        "signup_notes": "注册送$1额度",
        "sdk": "openai",
        "install_cmd": "pip install openai",
    },
    "novita": {
        "name": "Novita AI",
        "website": "https://novita.ai/model-api/create-instance",
        "description": "多种开源模型",
        "models": ["Llama 3.1 8B", "Qwen 2.5 72B", "DeepSeek V3"],
        "free_tier": "$0.5额度（有效期1年）",
        "env_vars": ["NOVITA_API_KEY"],
        "signup_notes": "注册送$0.5",
        "sdk": "openai",
        "install_cmd": "pip install openai",
    },
}


# ============================================================================
# 命令处理函数
# ============================================================================

def handle_list(args) -> None:
    """列出所有免费LLM API"""
    print_header("免费 LLM API 资源列表")
    
    for provider_id, info in FREE_LLM_PROVIDERS.items():
        print_color(f"\n🔹 {info['name']} ({provider_id})", CliColors.BOLD)
        print(f"   描述: {info['description']}")
        print(f"   免费额度: {info['free_tier']}")
        print(f"   模型: {', '.join(info['models'][:3])}")
        print(f"   API Key: {info['website']}")
        
        if args.verbose:
            print(f"   环境变量: {', '.join(info['env_vars'])}")
            print(f"   SDK安装: {info['install_cmd']}")
            print(f"   注册说明: {info['signup_notes']}")
    
    print()
    print_color("💡 使用说明:", CliColors.BOLD)
    print("  1. 选择一个提供商并访问其网站获取API Key")
    print("  2. 运行: python free_llm_setup.py guide <provider> 获取详细指南")
    print("  3. 将API Key添加到 .env 文件")
    print("  4. 运行: python free_llm_setup.py config 生成配置")
    print()


def handle_guide(args) -> None:
    """显示获取API Key的详细指南"""
    provider_id = args.provider.lower()
    
    if provider_id not in FREE_LLM_PROVIDERS:
        print_error(f"未知提供商: {provider_id}")
        print(f"可用提供商: {', '.join(FREE_LLM_PROVIDERS.keys())}")
        return
    
    info = FREE_LLM_PROVIDERS[provider_id]
    
    print_header(f"获取 {info['name']} API Key 指南")
    
    print_color("\n📋 步骤指南", CliColors.BOLD)
    print(f"  1. 访问: {info['website']}")
    print(f"  2. {'登录' if 'GitHub' in info['signup_notes'] else '注册'}账号")
    if info['signup_notes'] != '需要Google账号':
        print(f"  3. {info['signup_notes']}")
    print("  4. 创建新的API Key")
    print("  5. 复制API Key并妥善保管")
    
    print_color("\n🔧 安装SDK", CliColors.BOLD)
    print(f"  {info['install_cmd']}")
    
    print_color("\n📝 环境变量配置", CliColors.BOLD)
    for env_var in info['env_vars']:
        print(f"  export {env_var}=your_api_key_here")
    
    print_color("\n🧪 测试API", CliColors.BOLD)
    print(f"  python free_llm_setup.py test {provider_id}")
    
    if args.open:
        print_color("\n🌐 正在打开浏览器...", CliColors.BLUE)
        webbrowser.open(info['website'])
        print_success("已打开API Key页面")


def handle_config(args) -> None:
    """生成配置模板"""
    print_header("生成 LLM 配置模板")
    
    config_template = """
# ============================================================
# 免费 LLM API 配置
# ============================================================
# 使用 python free_llm_setup.py list 查看可用提供商

# Groq (推荐 - 速度快，无RPM限制)
# 获取: https://console.groq.com/keys
GROQ_API_KEY=your_groq_api_key_here

# OpenRouter (统一网关，支持多模型)
# 获取: https://openrouter.ai/keys
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Google AI Studio (Gemini系列)
# 获取: https://aistudio.google.com/app/apikey
GOOGLE_API_KEY=your_google_api_key_here

# Cohere (Command R+ 系列)
# 获取: https://dashboard.cohere.com/api-keys
COHERE_API_KEY=your_cohere_api_key_here

# Cerebras (超大模型)
# 获取: https://cerebras.ai/cloud
CEREBRAS_API_KEY=your_cerebras_api_key_here

# Mistral
# 获取: https://console.mistral.ai/api-keys/
MISTRAL_API_KEY=your_mistral_api_key_here

# Hyperbolic
# 获取: https://app.hyperbolic.xyz/api-keys
HYPERBOLIC_API_KEY=your_hyperbolic_api_key_here

# Novita AI
# 获取: https://novita.ai/model-api/create-instance
NOVITA_API_KEY=your_novita_api_key_here

# HuggingFace
# 获取: https://huggingface.co/settings/tokens
HF_TOKEN=your_huggingface_token_here

# ============================================================
# 当前启用的LLM后端
# ============================================================
LLM_PROVIDER=groq  # 可选: groq, cohere, cerebras, openai, google, mistral, deepseek, glm
DEFAULT_MODEL=llama-3.1-8b-instant  # Groq模型
FALLBACK_MODEL=command-r-plus-08-2024  # Cohere模型
"""
    
    output_file = Path(".env.free_llm")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(config_template.strip())
    
    print_success(f"配置模板已生成: {output_file}")
    print("\n下一步:")
    print("  1. 编辑 .env.free_llm 填入你的API Key")
    print("  2. 将内容合并到 .env 文件中")
    print("  3. 运行: python free_llm_setup.py test groq 测试连接")


async def handle_test(args) -> None:
    """测试API连接"""
    provider_id = args.provider.lower()
    
    if provider_id not in FREE_LLM_PROVIDERS:
        print_error(f"未知提供商: {provider_id}")
        return
    
    info = FREE_LLM_PROVIDERS[provider_id]
    env_var = info['env_vars'][0]
    
    print_header(f"测试 {info['name']} API")
    
    api_key = os.getenv(env_var)
    if not api_key or api_key == f"your_{env_var.lower()}_here":
        print_error(f"未找到 {env_var}，请先配置API Key")
        print(f"\n在 .env 文件中添加:")
        print(f"  {env_var}=your_api_key")
        return
    
    print_info(f"正在测试 {info['name']}...")
    
    try:
        if provider_id == "nvidia":
            result = await _test_nvidia(api_key)
        elif provider_id == "groq":
            result = await _test_groq(api_key)
        elif provider_id == "openrouter":
            result = await _test_openrouter(api_key)
        elif provider_id == "cohere":
            result = await _test_cohere(api_key)
        elif provider_id == "google":
            result = await _test_google(api_key)
        else:
            print_warning(f"测试脚本未实现，请手动验证")
            return
        
        if result:
            print_success("API连接成功！")
            if result.get("model"):
                print(f"   模型: {result['model']}")
            if result.get("response"):
                print(f"   响应: {result['response'][:100]}...")
    except Exception as e:
        print_error(f"API测试失败: {e}")


async def _test_nvidia(api_key: str) -> Dict[str, Any]:
    """测试NVIDIA NIM API"""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://integrate.api.nvidia.com/v1"
        )
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": "Hello, say 'OK' in one word"}],
            model="meta/llama-3.1-nemotron-70b-instruct",
        )
        
        return {
            "success": True,
            "model": chat_completion.model,
            "response": chat_completion.choices[0].message.content,
        }
    except ImportError:
        print_warning("请先安装openai: pip install openai")
        return {"success": False}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _test_groq(api_key: str) -> Dict[str, Any]:
    """测试Groq API"""
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": "Hello, say 'OK' in one word"}],
            model="llama-3.1-8b-instant",
        )
        
        return {
            "success": True,
            "model": chat_completion.model,
            "response": chat_completion.choices[0].message.content,
        }
    except ImportError:
        print_warning("请先安装groq: pip install groq")
        return {"success": False}


async def _test_openrouter(api_key: str) -> Dict[str, Any]:
    """测试OpenRouter API"""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": "Hello, say 'OK' in one word"}],
            model="openrouter/auto",
        )
        
        return {
            "success": True,
            "model": chat_completion.model,
            "response": chat_completion.choices[0].message.content,
        }
    except ImportError:
        print_warning("请先安装openai: pip install openai")
        return {"success": False}


async def _test_cohere(api_key: str) -> Dict[str, Any]:
    """测试Cohere API"""
    try:
        from cohere import AsyncClient
        client = AsyncClient(api_key=api_key)
        
        response = await client.chat(
            message="Say 'OK' in one word",
            model="command-r-plus-08-2024"
        )
        
        return {
            "success": True,
            "model": "command-r-plus-08-2024",
            "response": response.text,
        }
    except ImportError:
        print_warning("请先安装cohere: pip install cohere")
        return {"success": False}


async def _test_google(api_key: str) -> Dict[str, Any]:
    """测试Google AI API"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content("Say 'OK' in one word")
        
        return {
            "success": True,
            "model": "gemini-2.0-flash",
            "response": response.text,
        }
    except ImportError:
        print_warning("请先安装google-generativeai: pip install google-generativeai")
        return {"success": False}


# ============================================================================
# 主函数
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="免费 LLM API Key 获取和配置工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python free_llm_setup.py list                      # 列出所有免费API
  python free_llm_setup.py guide groq                 # 查看Groq获取指南
  python free_llm_setup.py guide groq --open          # 打开Groq注册页面
  python free_llm_setup.py config                     # 生成配置模板
  python free_llm_setup.py test groq                  # 测试Groq API
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    list_parser = subparsers.add_parser("list", help="列出所有免费LLM API")
    list_parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")
    
    guide_parser = subparsers.add_parser("guide", help="显示API Key获取指南")
    guide_parser.add_argument("provider", help="提供商名称 (groq/cohere/openrouter等)")
    guide_parser.add_argument("--open", "-o", action="store_true", help="打开注册页面")
    
    config_parser = subparsers.add_parser("config", help="生成配置模板")
    
    test_parser = subparsers.add_parser("test", help="测试API连接")
    test_parser.add_argument("provider", help="提供商名称")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "list":
        handle_list(args)
    elif args.command == "guide":
        handle_guide(args)
    elif args.command == "config":
        handle_config(args)
    elif args.command == "test":
        asyncio.run(handle_test(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
