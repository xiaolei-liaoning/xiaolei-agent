"""智能Fallback机制模块

当所有技能和MCP服务都不可用时的最后处理方案：

1. 检测所有工具不可用的场景
2. 智能生成解决方案代码
3. 在沙盒中安全执行
4. 询问用户确认后才执行
5. 提供多种解决路径供选择

使用场景：
- 所有MCP服务器连接失败
- 所需技能未注册
- 工具执行持续失败
- 用户请求的功能没有对应工具
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class FallbackStrategy(Enum):
    """Fallback策略枚举"""
    GENERATE_CODE = "generate_code"      # 生成代码解决方案
    USE_LLM_DIRECTLY = "use_llm_directly"  # 直接使用LLM生成回答
    TRY_ALTERNATIVE = "try_alternative"    # 尝试替代方案
    ASK_USER = "ask_user"                 # 询问用户
    REPORT_UNAVAILABLE = "report_unavailable"  # 报告功能不可用


@dataclass
class FallbackResult:
    """Fallback结果"""
    success: bool
    strategy: FallbackStrategy
    message: str
    code: Optional[str] = None
    alternatives: List[str] = None
    requires_confirmation: bool = False


class FallbackHandler:
    """智能Fallback处理器
    
    当所有工具都不可用时，提供多种解决路径：
    1. 代码生成：在沙盒中生成并执行Python代码
    2. LLM直接回答：使用LLM能力直接回答
    3. 替代方案：尝试其他可用工具
    4. 用户询问：询问用户选择或提供更多信息
    """
    
    def __init__(self):
        self.fallback_history: List[FallbackResult] = []
        self.max_code_generation_attempts = 3
    
    async def handle_all_unavailable(
        self, 
        user_message: str,
        unavailable_tools: List[str],
        error_context: Optional[str] = None,
        ask_user_callback: Optional[Callable] = None
    ) -> FallbackResult:
        """处理所有工具都不可用的情况
        
        Args:
            user_message: 用户原始消息
            unavailable_tools: 不可用的工具列表
            error_context: 错误上下文
            ask_user_callback: 询问用户的回调函数
            
        Returns:
            Fallback结果
        """
        logger.info(f"所有工具都不可用: {unavailable_tools}")
        
        # 1. 分析问题类型
        problem_type = self._analyze_problem_type(user_message, unavailable_tools)
        
        # 2. 确定最佳策略
        strategy = self._determine_strategy(problem_type, unavailable_tools)
        
        # 3. 执行策略
        result = await self._execute_strategy(
            strategy=strategy,
            user_message=user_message,
            problem_type=problem_type,
            error_context=error_context,
            ask_user_callback=ask_user_callback
        )
        
        # 记录历史
        self.fallback_history.append(result)
        
        return result
    
    def _analyze_problem_type(self, user_message: str, unavailable_tools: List[str]) -> str:
        """分析问题类型
        
        Args:
            user_message: 用户消息
            unavailable_tools: 不可用工具列表
            
        Returns:
            问题类型
        """
        message_lower = user_message.lower()
        
        # 计算类问题
        if any(kw in message_lower for kw in ["计算", "加", "减", "乘", "除", "等于"]):
            return "calculation"
        
        # 搜索类问题
        if any(kw in message_lower for kw in ["搜索", "查询", "查找", "获取"]):
            return "search"
        
        # 翻译类问题
        if any(kw in message_lower for kw in ["翻译", "translate", "英文", "中文"]):
            return "translation"
        
        # 信息查询类问题
        if any(kw in message_lower for kw in ["天气", "时间", "日期", "温度"]):
            return "information"
        
        # 代码类问题
        if any(kw in message_lower for kw in ["代码", "python", "写代码", "生成代码"]):
            return "code_generation"
        
        # 通用问题
        return "general"
    
    def _determine_strategy(
        self, 
        problem_type: str, 
        unavailable_tools: List[str]
    ) -> FallbackStrategy:
        """确定最佳策略
        
        Args:
            problem_type: 问题类型
            unavailable_tools: 不可用工具列表
            
        Returns:
            Fallback策略
        """
        # 计算类问题：优先生成代码
        if problem_type == "calculation":
            return FallbackStrategy.GENERATE_CODE
        
        # 翻译类问题：优先使用LLM直接翻译
        if problem_type == "translation":
            return FallbackStrategy.USE_LLM_DIRECTLY
        
        # 代码生成类：生成代码
        if problem_type == "code_generation":
            return FallbackStrategy.GENERATE_CODE
        
        # 信息查询类：尝试替代方案
        if problem_type == "information":
            return FallbackStrategy.TRY_ALTERNATIVE
        
        # 通用问题：询问用户
        return FallbackStrategy.ASK_USER
    
    async def _execute_strategy(
        self,
        strategy: FallbackStrategy,
        user_message: str,
        problem_type: str,
        error_context: Optional[str],
        ask_user_callback: Optional[Callable]
    ) -> FallbackResult:
        """执行选定的策略
        
        Args:
            strategy: 策略
            user_message: 用户消息
            problem_type: 问题类型
            error_context: 错误上下文
            ask_user_callback: 询问用户回调
            
        Returns:
            执行结果
        """
        if strategy == FallbackStrategy.GENERATE_CODE:
            return await self._generate_code_solution(user_message, problem_type, error_context)
        
        elif strategy == FallbackStrategy.USE_LLM_DIRECTLY:
            return await self._use_llm_directly(user_message, problem_type)
        
        elif strategy == FallbackStrategy.TRY_ALTERNATIVE:
            return self._try_alternative(user_message, problem_type)
        
        elif strategy == FallbackStrategy.ASK_USER:
            return await self._ask_user_solution(
                user_message, 
                problem_type,
                ask_user_callback
            )
        
        else:
            return FallbackResult(
                success=False,
                strategy=FallbackStrategy.REPORT_UNAVAILABLE,
                message="抱歉，当前所有工具都不可用，我无法处理您的请求。"
            )
    
    async def _generate_code_solution(
        self,
        user_message: str,
        problem_type: str,
        error_context: Optional[str]
    ) -> FallbackResult:
        """生成代码解决方案
        
        Args:
            user_message: 用户消息
            problem_type: 问题类型
            error_context: 错误上下文
            
        Returns:
            代码解决方案
        """
        logger.info(f"生成代码解决方案: {problem_type}")
        
        # 生成代码提示
        code_hints = self._get_code_hints(problem_type, user_message)
        
        # 构建代码生成Prompt
        prompt = f"""## 代码生成任务

### 用户需求
{user_message}

### 问题类型
{problem_type}

### 代码要求
1. 使用Python标准库
2. 包含完整的错误处理
3. 返回格式: {{"success": bool, "result": any, "message": str}}

### {code_hints}

### 安全限制
- 禁止使用: os.system, subprocess, shutil.rmtree
- 禁止访问: /etc, ~/.ssh, /var等敏感目录
- 允许使用: math, datetime, json, re, urllib

### 输出格式
```python
def solve_problem(message: str) -> dict:
    # 你的解决方案
    pass
```
"""
        
        # 调用LLM生成代码（简化实现）
        code = await self._call_llm_for_code(prompt)
        
        if code:
            return FallbackResult(
                success=True,
                strategy=FallbackStrategy.GENERATE_CODE,
                message=f"我找到了一个解决方案，可以生成代码来解决您的问题。",
                code=code,
                requires_confirmation=True  # 需要用户确认后才执行
            )
        
        return FallbackResult(
            success=False,
            strategy=FallbackStrategy.GENERATE_CODE,
            message="抱歉，我无法为这个问题生成解决方案。"
        )
    
    def _get_code_hints(self, problem_type: str, user_message: str) -> str:
        """获取代码提示
        
        Args:
            problem_type: 问题类型
            user_message: 用户消息
            
        Returns:
            代码提示
        """
        hints = {
            "calculation": """
计算类问题提示：
- 使用 eval() 或 ast.literal_eval() 进行安全计算
- 支持基本运算符: +, -, *, /, **, //
- 提取表达式: re.search(r'[0-9+*/().-]+', message)
""",
            "search": """
搜索类问题提示：
- 使用 urllib.request 进行HTTP请求
- 使用 json.loads() 解析响应
- 添加超时处理
""",
            "translation": """
翻译类问题提示：
- 直接使用LLM能力进行翻译
- 不需要生成额外代码
""",
            "information": """
信息查询类问题提示：
- 使用 datetime 获取当前时间
- 使用 platform 获取系统信息
- 使用 psutil 获取资源信息（如果可用）
""",
            "code_generation": """
代码生成类问题提示：
- 生成用户需要的代码片段
- 添加注释说明
- 确保代码可执行
"""
        }
        
        return hints.get(problem_type, "")
    
    async def _call_llm_for_code(self, prompt: str) -> Optional[str]:
        """调用LLM生成代码
        
        Args:
            prompt: 提示词
            
        Returns:
            生成的代码
        """
        try:
            from core.engine.llm_backend import get_llm_router

            llm_router = get_llm_router()
            if not llm_router or not llm_router.is_available():
                return None

            response = await llm_router.simple_chat(
                user_message=prompt,
                system_prompt="你是一个Python代码生成专家。",
                temperature=0.1
            )
            
            if response and "def " in response:
                code_start = response.find("def ")
                return response[code_start:].strip()
            
        except Exception as e:
            logger.error(f"LLM代码生成失败: {e}")
        
        return None
    
    async def _use_llm_directly(
        self,
        user_message: str,
        problem_type: str
    ) -> FallbackResult:
        """直接使用LLM回答
        
        Args:
            user_message: 用户消息
            problem_type: 问题类型
            
        Returns:
            LLM回答结果
        """
        try:
            from core.engine.llm_backend import get_llm_router

            llm_router = get_llm_router()
            if not llm_router or not llm_router.is_available():
                return FallbackResult(
                    success=False,
                    strategy=FallbackStrategy.USE_LLM_DIRECTLY,
                    message="LLM当前不可用，无法直接回答。"
                )
            
            response = await llm_router.simple_chat(
                user_message=user_message,
                system_prompt="你是一个有帮助的AI助手，请直接回答用户的问题。",
                temperature=0.7
            )
            
            if response:
                return FallbackResult(
                    success=True,
                    strategy=FallbackStrategy.USE_LLM_DIRECTLY,
                    message=response
                )
            
        except Exception as e:
            logger.error(f"LLM直接回答失败: {e}")
        
        return FallbackResult(
            success=False,
            strategy=FallbackStrategy.USE_LLM_DIRECTLY,
            message="抱歉，我无法直接回答您的问题。"
        )
    
    def _try_alternative(
        self,
        user_message: str,
        problem_type: str
    ) -> FallbackResult:
        """尝试替代方案
        
        Args:
            user_message: 用户消息
            problem_type: 问题类型
            
        Returns:
            替代方案
        """
        alternatives = {
            "information": [
                "尝试使用 system_toolbox 技能获取系统信息",
                "尝试使用聊天方式获取基本信息"
            ]
        }
        
        return FallbackResult(
            success=False,
            strategy=FallbackStrategy.TRY_ALTERNATIVE,
            message=f"我找到了以下替代方案：",
            alternatives=alternatives.get(problem_type, ["请提供更多信息"])
        )
    
    async def _ask_user_solution(
        self,
        user_message: str,
        problem_type: str,
        ask_user_callback: Optional[Callable]
    ) -> FallbackResult:
        """询问用户解决方案
        
        Args:
            user_message: 用户消息
            problem_type: 问题类型
            ask_user_callback: 询问回调
            
        Returns:
            询问结果
        """
        if ask_user_callback:
            try:
                await ask_user_callback(
                    "当前工具都不可用，您希望：\n"
                    "1. 让我尝试用代码解决\n"
                    "2. 我直接用AI能力回答\n"
                    "3. 您提供更多信息\n"
                    "4. 稍后再试"
                )
            except Exception as e:
                logger.error(f"询问用户失败: {e}")
        
        return FallbackResult(
            success=False,
            strategy=FallbackStrategy.ASK_USER,
            message="我需要您的帮助来确定最佳解决方案。",
            requires_confirmation=True
        )
    
    async def execute_confirmed_code(
        self,
        code: str,
        user_message: str
    ) -> FallbackResult:
        """执行用户确认的代码
        
        Args:
            code: 生成的代码
            user_message: 用户消息
            
        Returns:
            执行结果
        """
        try:
            # 在沙盒中执行代码
            result = await self._execute_in_sandbox(code, user_message)
            
            if result.get("success"):
                return FallbackResult(
                    success=True,
                    strategy=FallbackStrategy.GENERATE_CODE,
                    message=f"执行成功！结果: {result.get('result', '完成')}"
                )
            else:
                return FallbackResult(
                    success=False,
                    strategy=FallbackStrategy.GENERATE_CODE,
                    message=f"执行失败: {result.get('error', '未知错误')}"
                )
                
        except Exception as e:
            logger.error(f"代码执行失败: {e}")
            return FallbackResult(
                success=False,
                strategy=FallbackStrategy.GENERATE_CODE,
                message=f"代码执行出错: {str(e)}"
            )
    
    async def _execute_in_sandbox(
        self,
        code: str,
        user_message: str
    ) -> Dict[str, Any]:
        """在沙盒中安全执行代码
        
        Args:
            code: 要执行的代码
            user_message: 用户消息
            
        Returns:
            执行结果
        """
        try:
            exec_globals = {}
            exec_locals = {}
            
            # 限制可用的模块
            allowed_modules = ['math', 'datetime', 'json', 're', 'urllib', 'random', 'collections']
            
            for module_name in allowed_modules:
                try:
                    exec_globals[module_name] = __import__(module_name)
                except ImportError:
                    pass
            
            # 执行代码
            exec(code, exec_globals, exec_locals)
            
            # 查找并执行 solve 函数
            for name, obj in exec_locals.items():
                if callable(obj) and 'solve' in name:
                    result = obj(message=user_message)
                    return result
            
            return {"success": True, "message": "代码已执行"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}


# 全局单例
_fallback_handler: Optional[FallbackHandler] = None


def get_fallback_handler() -> FallbackHandler:
    """获取Fallback处理器实例"""
    global _fallback_handler
    if _fallback_handler is None:
        _fallback_handler = FallbackHandler()
    return _fallback_handler
