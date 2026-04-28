"""执行结果智能分析器

特性：
- 将原始执行结果交给AI进行深度分析
- 生成人性化、有价值的回复
- 支持多种数据类型（天气、新闻、数据等）
- 结合上下文提供个性化建议
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .llm_backend import get_llm_router
from .keyword_extractor import ExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """分析结果"""
    summary: str              # 简洁摘要
    detailed_analysis: str    # 详细分析
    suggestions: List[str]    # 建议列表
    key_insights: List[str]   # 关键洞察
    formatted_reply: str      # 格式化回复
    confidence: float         # 置信度


class ResultAnalyzer:
    """执行结果智能分析器"""
    
    def __init__(self):
        self.router = get_llm_router()
        logger.info("ResultAnalyzer 初始化完成")
    
    async def analyze(self, 
                     original_query: str,
                     execution_results: List[Dict[str, Any]],
                     extraction: Optional[ExtractionResult] = None) -> AnalysisResult:
        """分析执行结果
        
        Args:
            original_query: 用户原始查询
            execution_results: 执行结果列表
            extraction: 关键词提取结果（可选）
            
        Returns:
            分析结果
        """
        logger.info("开始分析执行结果，共 %d 个步骤", len(execution_results))
        
        try:
            # 1. 构建分析上下文
            context = self._build_analysis_context(original_query, execution_results, extraction)
            
            # 2. 调用AI进行分析
            analysis = await self._ai_analyze(context)
            
            # 3. 解析分析结果
            result = self._parse_analysis(analysis, execution_results)
            
            logger.info("结果分析完成")
            return result
            
        except Exception as e:
            logger.error("结果分析失败: %s", e)
            # 降级方案：返回简单总结
            return self._fallback_analysis(execution_results)
    
    def _build_analysis_context(self, 
                               original_query: str,
                               execution_results: List[Dict[str, Any]],
                               extraction: Optional[ExtractionResult]) -> Dict[str, Any]:
        """构建分析上下文
        
        Args:
            original_query: 原始查询
            execution_results: 执行结果
            extraction: 关键词提取结果
            
        Returns:
            上下文字典
        """
        context = {
            "original_query": original_query,
            "execution_summary": [],
            "extraction_info": None
        }
        
        # 汇总执行结果
        for result in execution_results:
            step_summary = {
                "step_id": result.get("step_id"),
                "description": result.get("description"),
                "success": result.get("success"),
            }
            
            if result.get("success"):
                step_summary["result"] = result.get("result")
            else:
                step_summary["error"] = result.get("error")
            
            context["execution_summary"].append(step_summary)
        
        # 添加关键词提取信息
        if extraction:
            context["extraction_info"] = {
                "main_intent": extraction.main_intent,
                "action_words": extraction.action_words,
                "target_words": extraction.target_words,
                "entities": {
                    "locations": extraction.entities.locations,
                    "times": extraction.entities.times,
                    "numbers": extraction.entities.numbers
                },
                "confidence": extraction.confidence
            }
        
        return context
    
    async def _ai_analyze(self, context: Dict[str, Any]) -> str:
        """调用AI进行分析
        
        Args:
            context: 分析上下文
            
        Returns:
            AI分析结果（JSON格式）
        """
        prompt = f"""请对以下任务执行结果进行智能分析和总结。

## 用户原始请求
{context['original_query']}

## 关键词提取信息
{self._format_json(context.get('extraction_info', {}))}

## 执行结果
{self._format_json(context['execution_summary'])}

请从以下角度进行分析：

1. **核心摘要**：用1-2句话概括整体结果（50字以内）
2. **详细分析**：深入分析执行结果的关键信息和价值（200-300字）
3. **关键洞察**：列出3-5个最重要的发现或要点
4. **实用建议**：基于结果给出2-4条 actionable 的建议
5. **后续行动**：推荐用户接下来可以做什么

返回JSON格式（不要用代码块）：
{{
  "summary": "核心摘要",
  "detailed_analysis": "详细分析内容",
  "key_insights": ["洞察1", "洞察2", "洞察3"],
  "suggestions": ["建议1", "建议2", "建议3"],
  "next_actions": ["后续行动1", "后续行动2"],
  "tone": "回复的语气风格（专业/友好/简洁/详细）"
}}

要求：
1. 语言自然流畅，像真人对话
2. 突出最有价值的信息
3. 避免技术术语，使用通俗语言
4. 如果有数据，要解读数据的含义
5. 如果执行失败，要说明原因并提供解决方案
6. 只返回JSON，不要其他内容"""
        
        try:
            response = await self.router.simple_chat(
                user_message=prompt,
                system_prompt="你是智能分析助手，擅长解读数据并给出有价值的见解，只返回JSON格式",
                temperature=0.7,
            )
            
            if not response or not response.strip():
                raise ValueError("AI返回空响应")
            
            # 清理markdown代码块
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            return response
            
        except Exception as e:
            logger.error("AI分析调用失败: %s", e)
            raise
    
    def _parse_analysis(self, analysis_json: str, 
                       execution_results: List[Dict[str, Any]]) -> AnalysisResult:
        """解析AI分析结果
        
        Args:
            analysis_json: AI返回的JSON字符串
            execution_results: 执行结果
            
        Returns:
            分析结果对象
        """
        import json
        
        try:
            data = json.loads(analysis_json)
            
            # 生成格式化回复
            formatted_reply = self._generate_formatted_reply(data, execution_results)
            
            return AnalysisResult(
                summary=data.get("summary", "分析完成"),
                detailed_analysis=data.get("detailed_analysis", ""),
                suggestions=data.get("suggestions", []),
                key_insights=data.get("key_insights", []),
                formatted_reply=formatted_reply,
                confidence=0.9
            )
        except Exception as e:
            logger.error("解析分析结果失败: %s", e)
            return self._fallback_analysis(execution_results)
    
    def _generate_formatted_reply(self, analysis_data: Dict[str, Any],
                                 execution_results: List[Dict[str, Any]]) -> str:
        """生成格式化回复
        
        Args:
            analysis_data: 分析数据
            execution_results: 执行结果
            
        Returns:
            格式化后的回复文本
        """
        reply_parts = []
        
        # 1. 核心摘要
        if analysis_data.get("summary"):
            reply_parts.append(f"📊 **核心摘要**\n{analysis_data['summary']}\n")
        
        # 2. 详细分析
        if analysis_data.get("detailed_analysis"):
            reply_parts.append(f"🔍 **详细分析**\n{analysis_data['detailed_analysis']}\n")
        
        # 3. 关键洞察
        if analysis_data.get("key_insights"):
            reply_parts.append("💡 **关键洞察**")
            for i, insight in enumerate(analysis_data["key_insights"], 1):
                reply_parts.append(f"{i}. {insight}")
            reply_parts.append("")
        
        # 4. 实用建议
        if analysis_data.get("suggestions"):
            reply_parts.append("✨ **实用建议**")
            for i, suggestion in enumerate(analysis_data["suggestions"], 1):
                reply_parts.append(f"{i}. {suggestion}")
            reply_parts.append("")
        
        # 5. 后续行动
        if analysis_data.get("next_actions"):
            reply_parts.append("🎯 **接下来可以**")
            for action in analysis_data["next_actions"]:
                reply_parts.append(f"• {action}")
        
        return "\n".join(reply_parts)
    
    def _fallback_analysis(self, execution_results: List[Dict[str, Any]]) -> AnalysisResult:
        """降级分析方案
        
        当AI分析失败时使用
        
        Args:
            execution_results: 执行结果
            
        Returns:
            简单的分析结果
        """
        success_count = sum(1 for r in execution_results if r.get("success"))
        total_count = len(execution_results)
        
        summary = f"任务执行完成，成功 {success_count}/{total_count} 个步骤"
        
        insights = []
        suggestions = []
        
        for result in execution_results:
            if result.get("success"):
                insights.append(f"✅ {result.get('description', '未知步骤')} 执行成功")
            else:
                insights.append(f"❌ {result.get('description', '未知步骤')} 执行失败: {result.get('error', '未知错误')}")
                suggestions.append("检查网络连接或重试")
        
        formatted_reply = f"{summary}\n\n"
        formatted_reply += "\n".join(insights)
        if suggestions:
            formatted_reply += "\n\n建议:\n" + "\n".join(f"• {s}" for s in suggestions)
        
        return AnalysisResult(
            summary=summary,
            detailed_analysis="",
            suggestions=suggestions,
            key_insights=insights,
            formatted_reply=formatted_reply,
            confidence=0.5
        )
    
    def _format_json(self, data: Any, indent: int = 2) -> str:
        """格式化JSON数据为字符串
        
        Args:
            data: 数据
            indent: 缩进
            
        Returns:
            格式化的JSON字符串
        """
        import json
        try:
            return json.dumps(data, ensure_ascii=False, indent=indent)
        except:
            return str(data)


# 全局单例
_result_analyzer = None


def get_result_analyzer() -> ResultAnalyzer:
    """获取结果分析器单例"""
    global _result_analyzer
    if _result_analyzer is None:
        _result_analyzer = ResultAnalyzer()
    return _result_analyzer
