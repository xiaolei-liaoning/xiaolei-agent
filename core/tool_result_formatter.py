"""工具调用结果智能回复生成器

特性：
- 将原始工具执行结果转换为人性化的AI回复
- 包含：概述、耗时、文件位置、时间等关键信息
- 结合自我校验机制确保回复质量
- 支持多种工具类型（文件处理、数据查询、API调用等）

使用示例：
    from core.tool_result_formatter import ToolResultFormatter
    
    formatter = ToolResultFormatter()
    
    # 工具执行结果
    tool_result = {
        "tool_name": "file_processor",
        "success": True,
        "result": {"processed_files": 5, "output_path": "/Users/xxx/Desktop/output.pdf"},
        "execution_time": 3.5,
        "timestamp": "2026-04-28T18:00:00"
    }
    
    # 生成人性化回复
    reply = await formatter.format_response(
        user_query="帮我处理这些PDF文件",
        tool_result=tool_result,
        enable_self_check=True
    )
    
    print(reply)
    # 输出：
    # ✅ 已完成PDF文件处理
    # 
    # 📋 概述：成功处理了5个PDF文件，生成了合并后的输出文件
    # ⏱️ 耗时：3.5秒
    # 📁 文件位置：/Users/xxx/Desktop/output.pdf
    # 🕐 完成时间：2026-04-28 18:00:00
"""

import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from .llm_backend import get_llm_router
from .self_check_middleware import SelfCheckMiddleware

logger = logging.getLogger(__name__)


@dataclass
class FormattedToolResponse:
    """格式化后的工具响应"""
    
    overview: str           # 概述：处理了什么，得到了什么
    execution_time: float   # 耗时（秒）
    file_location: str      # 文件处理位置
    completion_time: str    # 完成时间
    full_reply: str         # 完整回复文本
    is_success: bool        # 是否成功
    quality_score: int = 0  # 质量评分（如果启用自检）


class ToolResultFormatter:
    """工具调用结果智能回复生成器
    
    将原始的工具执行结果转换为用户友好的自然语言回复，
    并可选择性地通过自我校验机制提升回复质量。
    """
    
    def __init__(self, enable_self_check: bool = True, pass_score: int = 80):
        """初始化工具结果格式化器
        
        Args:
            enable_self_check: 是否启用自我校验
            pass_score: 自检合格分数线
        """
        self.router = get_llm_router()
        self.enable_self_check = enable_self_check
        
        if enable_self_check:
            self.checker = SelfCheckMiddleware(
                pass_score=pass_score,
                max_retry=2,
                enable_logging=False  # 减少日志噪音
            )
        
        logger.info("ToolResultFormatter 初始化完成 (自检=%s)", enable_self_check)
    
    async def format_response(
        self,
        user_query: str,
        tool_result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        enable_self_check: Optional[bool] = None
    ) -> FormattedToolResponse:
        """生成工具调用的智能回复
        
        Args:
            user_query: 用户原始请求
            tool_result: 工具执行结果
            context: 额外上下文信息
            enable_self_check: 是否启用自检（覆盖默认设置）
            
        Returns:
            格式化的响应对象
        """
        start_time = time.time()
        use_self_check = enable_self_check if enable_self_check is not None else self.enable_self_check
        
        try:
            # 1. 提取关键信息
            extracted_info = self._extract_key_info(tool_result, context)
            
            # 2. 生成初步回复
            if use_self_check:
                # 带自检的生成
                response = await self._generate_with_self_check(
                    user_query, tool_result, extracted_info
                )
            else:
                # 直接生成
                response = await self._generate_direct_reply(
                    user_query, tool_result, extracted_info
                )
            
            # 3. 构建最终响应对象
            formatted_response = FormattedToolResponse(
                overview=response.overview,
                execution_time=extracted_info.get('execution_time', 0),
                file_location=response.file_location,
                completion_time=response.completion_time,
                full_reply=response.full_reply,
                is_success=tool_result.get('success', False),
                quality_score=getattr(response, 'quality_score', 0)
            )
            
            elapsed = time.time() - start_time
            logger.info(
                "工具回复生成完成: 耗时=%.2fs, 质量=%d分",
                elapsed, formatted_response.quality_score
            )
            
            return formatted_response
            
        except Exception as e:
            logger.error("工具回复生成失败: %s", str(e), exc_info=True)
            # 降级方案：返回基本信息
            return self._fallback_response(user_query, tool_result, str(e))
    
    def _extract_key_info(
        self,
        tool_result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """从工具结果中提取关键信息
        
        Args:
            tool_result: 工具执行结果
            context: 额外上下文
            
        Returns:
            提取的信息字典
        """
        info = {
            'tool_name': tool_result.get('tool_name', '未知工具'),
            'success': tool_result.get('success', False),
            'error': tool_result.get('error', ''),
            'execution_time': tool_result.get('execution_time', 0),
            'timestamp': tool_result.get('timestamp', datetime.now().isoformat()),
            'result_data': tool_result.get('result', {}),
        }
        
        # 提取文件位置
        result_data = info['result_data']
        file_location = ''
        
        # 尝试从不同字段获取文件路径
        for key in ['output_path', 'file_path', 'path', 'location', 'save_path']:
            if key in result_data and result_data[key]:
                file_location = str(result_data[key])
                break
        
        # 如果没有找到，检查是否有files列表
        if not file_location and isinstance(result_data.get('files'), list):
            files = result_data['files']
            if files:
                # 取第一个文件的路径
                first_file = files[0]
                if isinstance(first_file, dict):
                    file_location = first_file.get('path', first_file.get('location', ''))
                else:
                    file_location = str(first_file)
        
        info['file_location'] = file_location
        
        # 简化文件路径显示（如果是桌面文件）
        if file_location:
            if '/Desktop/' in file_location or '\\Desktop\\' in file_location:
                info['file_display'] = f"桌面/{file_location.split('Desktop/')[-1]}"
            else:
                info['file_display'] = file_location
        else:
            info['file_display'] = '无文件输出'
        
        # 添加上下文信息
        if context:
            info.update(context)
        
        return info
    
    async def _generate_with_self_check(
        self,
        user_query: str,
        tool_result: Dict[str, Any],
        extracted_info: Dict[str, Any]
    ) -> FormattedToolResponse:
        """使用自我校验生成高质量回复
        
        Args:
            user_query: 用户请求
            tool_result: 工具结果
            extracted_info: 提取的信息
            
        Returns:
            格式化的响应
        """
        # 定义生成函数
        async def generate_reply(query: str, ctx=None) -> str:
            """生成工具调用回复"""
            prompt = self._build_generation_prompt(
                user_query, tool_result, extracted_info
            )
            
            return await self.router.simple_chat(
                prompt,
                temperature=0.5,  # 较低温度保证稳定性
            )
        
        # 执行自检
        check_result = await self.checker.check_and_optimize(
            user_query=f"为工具调用生成回复：{user_query}",
            generate_func=generate_reply
        )
        
        # 解析生成的回复
        parsed = self._parse_generated_reply(check_result.answer, extracted_info)
        parsed.quality_score = check_result.score
        
        return parsed
    
    async def _generate_direct_reply(
        self,
        user_query: str,
        tool_result: Dict[str, Any],
        extracted_info: Dict[str, Any]
    ) -> FormattedToolResponse:
        """直接生成回复（不使用自检）
        
        Args:
            user_query: 用户请求
            tool_result: 工具结果
            extracted_info: 提取的信息
            
        Returns:
            格式化的响应
        """
        prompt = self._build_generation_prompt(
            user_query, tool_result, extracted_info
        )
        
        reply_text = await self.router.simple_chat(
            prompt,
            temperature=0.5,
        )
        
        parsed = self._parse_generated_reply(reply_text, extracted_info)
        parsed.quality_score = 0  # 未进行质检
        
        return parsed
    
    def _build_generation_prompt(
        self,
        user_query: str,
        tool_result: Dict[str, Any],
        extracted_info: Dict[str, Any]
    ) -> str:
        """构建回复生成提示词
        
        Args:
            user_query: 用户请求
            tool_result: 工具结果
            extracted_info: 提取的信息
            
        Returns:
            提示词文本
        """
        success_emoji = "✅" if extracted_info['success'] else "❌"
        status_text = "成功" if extracted_info['success'] else "失败"
        
        prompt = f"""请为以下工具调用生成用户友好的回复。

## 用户请求
{user_query}

## 工具执行结果
- 工具名称：{extracted_info['tool_name']}
- 执行状态：{status_text}
- 执行耗时：{extracted_info['execution_time']:.2f}秒
- 完成时间：{extracted_info['timestamp']}
- 文件位置：{extracted_info['file_display']}
- 详细结果：{self._format_result_data(extracted_info['result_data'])}

{f"- 错误信息：{extracted_info['error']}" if extracted_info['error'] else ""}

## 回复要求

请严格按照以下格式生成回复（不要使用代码块）：

{success_emoji} [简短的状态说明，如：已完成PDF文件处理]

📋 **概述**
[用1-2句话说明：处理了什么内容，得到了什么结果。突出最重要的信息。]

⏱️ **耗时**
[执行耗时，如：3.5秒]

📁 **文件位置**
[如果有文件输出，显示文件路径；如果没有，写"无文件输出"]

🕐 **完成时间**
[完成的日期时间，格式：YYYY-MM-DD HH:MM:SS]

{self._generate_additional_sections(extracted_info)}

注意事项：
1. 语气友好自然，像真人对话
2. 如果执行失败，要说明原因并提供解决建议
3. 如果有多个文件，列出所有文件位置
4. 突出对用户有价值的信息
5. 避免技术术语，使用通俗语言
6. 只返回上述格式的内容，不要其他解释

开始生成回复："""
        
        return prompt
    
    def _format_result_data(self, result_data: Dict[str, Any]) -> str:
        """格式化结果数据用于显示
        
        Args:
            result_data: 原始结果数据
            
        Returns:
            格式化后的字符串
        """
        if not result_data:
            return "无详细数据"
        
        # 如果是简单数据类型，直接返回
        if isinstance(result_data, (str, int, float, bool)):
            return str(result_data)
        
        # 如果是字典，格式化关键字段
        lines = []
        for key, value in result_data.items():
            # 跳过内部字段
            if key.startswith('_'):
                continue
            
            if isinstance(value, (list, dict)):
                # 复杂结构只显示摘要
                if isinstance(value, list):
                    lines.append(f"  - {key}: {len(value)}项")
                else:
                    lines.append(f"  - {key}: {len(value)}个字段")
            else:
                lines.append(f"  - {key}: {value}")
        
        return "\n".join(lines) if lines else "无详细数据"
    
    def _generate_additional_sections(self, extracted_info: Dict[str, Any]) -> str:
        """生成额外的回复章节
        
        Args:
            extracted_info: 提取的信息
            
        Returns:
            额外章节的提示词
        """
        sections = []
        
        # 如果有统计信息，添加统计章节
        result_data = extracted_info.get('result_data', {})
        has_stats = any(key in result_data for key in ['count', 'total', 'processed', 'success_count'])
        
        if has_stats:
            sections.append("""
📊 **统计信息**
[如果有统计数据，在这里展示，如：处理了X个文件，成功了Y个]""")
        
        # 如果执行失败，添加故障排除章节
        if not extracted_info['success']:
            sections.append("""
🔧 **故障排除**
[分析失败原因，并提供1-2条解决建议]""")
        
        # 如果有后续操作建议
        sections.append("""
💡 **下一步建议**
[基于当前结果，给出1-2条用户可以继续做的操作]""")
        
        return "\n".join(sections)
    
    def _parse_generated_reply(
        self,
        reply_text: str,
        extracted_info: Dict[str, Any]
    ) -> FormattedToolResponse:
        """解析生成的回复文本，提取结构化信息
        
        Args:
            reply_text: AI生成的回复文本
            extracted_info: 提取的信息
            
        Returns:
            格式化的响应对象
        """
        # 提取概述（在"📋 **概述**"之后）
        overview = ""
        if "📋 **概述**" in reply_text:
            parts = reply_text.split("📋 **概述**")
            if len(parts) > 1:
                overview_section = parts[1].split("\n\n")[0].strip()
                # 去除可能的换行和多余空格
                overview = ' '.join(overview_section.split())
        
        # 如果没有提取到，使用默认值
        if not overview:
            status = "成功" if extracted_info['success'] else "失败"
            overview = f"工具执行{status}"
        
        # 构建完整回复
        full_reply = reply_text.strip()
        
        return FormattedToolResponse(
            overview=overview,
            execution_time=extracted_info.get('execution_time', 0),
            file_location=extracted_info.get('file_location', ''),
            completion_time=extracted_info.get('timestamp', ''),
            full_reply=full_reply,
            is_success=extracted_info['success'],
            quality_score=0
        )
    
    def _fallback_response(
        self,
        user_query: str,
        tool_result: Dict[str, Any],
        error_msg: str
    ) -> FormattedToolResponse:
        """降级响应：当AI生成失败时使用
        
        Args:
            user_query: 用户请求
            tool_result: 工具结果
            error_msg: 错误信息
            
        Returns:
            基本的格式化响应
        """
        success = tool_result.get('success', False)
        emoji = "✅" if success else "❌"
        status = "成功" if success else "失败"
        
        overview = f"工具执行{status}"
        if not success:
            overview += f"（{tool_result.get('error', '未知错误')}）"
        
        full_reply = f"""{emoji} {overview}

📋 **概述**
{overview}

⏱️ **耗时**
{tool_result.get('execution_time', 0):.2f}秒

📁 **文件位置**
{tool_result.get('result', {}).get('output_path', '无文件输出')}

🕐 **完成时间**
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ 注意：智能回复生成失败，显示基本信息"""
        
        return FormattedToolResponse(
            overview=overview,
            execution_time=tool_result.get('execution_time', 0),
            file_location=tool_result.get('result', {}).get('output_path', ''),
            completion_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            full_reply=full_reply,
            is_success=success,
            quality_score=0
        )


# ============================================================
# 全局单例
# ============================================================

_default_formatter: Optional[ToolResultFormatter] = None


def get_tool_result_formatter(enable_self_check: bool = True) -> ToolResultFormatter:
    """获取工具结果格式化器单例
    
    Args:
        enable_self_check: 是否启用自检
        
    Returns:
        ToolResultFormatter 实例
    """
    global _default_formatter
    if _default_formatter is None or _default_formatter.enable_self_check != enable_self_check:
        _default_formatter = ToolResultFormatter(enable_self_check=enable_self_check)
    return _default_formatter
