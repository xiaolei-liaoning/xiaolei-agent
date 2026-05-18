"""智能结果总结器 - Smart Result Summarizer

负责将技能执行的原始结果转换为人性化的自然语言回复。

核心功能：
1. 识别数据类型（文本、数据表格、文件等）
2. 对于生成文本类结果，只告知位置
3. 对于数据类结果，提取关键信息并总结
4. 使用LLM生成人性化回复
5. ✅ 新增：白名单机制，特定工具直接返回结果，不经过智能总结
"""

import logging
from typing import Any, Dict, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SummaryConfig:
    """总结配置"""
    # 是否启用AI总结
    enable_ai_summary: bool = True
    
    # 最大摘要长度（字符）
    max_summary_length: int = 200
    
    # 文本类型关键词（这些类型的结果只告知位置）
    text_type_keywords: list = field(default_factory=lambda: [
        "报告", "文档", "文章", "论文", "小说", "邮件", "消息"
    ])
    
    # 文件扩展名（这些类型的文件只告知保存位置）
    file_extensions: list = field(default_factory=lambda: [
        ".pdf", ".doc", ".docx", ".txt", ".md", ".html"
    ])
    
    # ✅ 白名单：这些工具的执行结果直接返回，不经过智能总结
    # 适用于：所有工具类回复，保持原始格式和简洁性
    direct_reply_whitelist: Set[str] = field(default_factory=lambda: {
        # 基础工具
        "translator",      # 翻译工具
        "calculator",      # 计算器
        "unit_converter",  # 单位转换
        "currency",        # 汇率查询
        "dictionary",      # 词典查询
        
        # 数据工具
        "weather",         # 天气查询
        "web_scraper",     # 网页爬虫
        "data_analysis",   # 数据分析
        "search_engine",   # 搜索引擎
        "ocr_recognition", # OCR识别
        
        # 自动化工具
        "advanced_automation",  # 高级自动化
        "gui_automation",       # GUI自动化
        "system_toolbox",       # 系统工具箱
        
        # AI工具
        "deep_thinking",   # 深度思考
        "rag_search",      # RAG搜索（也匹配 skills.rag_search_handler）
        "rag_search_handler",  # RAG搜索处理器（兼容旧名称）
        
        # 第三方工具
        "third_party",     # 第三方集成
        "openclaw",        # OpenClaw
        
        # 其他工具
        "marketplace",     # 市场相关
        "workflows",       # 工作流
        "人物",            # 人物相关
        "test_demo_skill", # 测试演示
    })


class SmartResultSummarizer:
    """智能结果总结器
    
    根据技能执行结果的类型，生成不同风格的人性化回复。
    
    ✅ 新增特性：
    - 白名单机制：特定工具直接返回原始回复，避免过度包装
    - 保持LLM多轮评分效果不受影响
    """
    
    def __init__(self, config: Optional[SummaryConfig] = None):
        self.config = config or SummaryConfig()
        self._llm_router = None
    
    async def _get_llm_router(self):
        """懒加载LLM路由器"""
        if self._llm_router is None:
            try:
                from ...engine.llm_backend import get_llm_router
                self._llm_router = get_llm_router()
            except Exception as e:
                logger.warning(f"LLM路由器初始化失败: {e}，将使用模板回复")
                self._llm_router = None
        return self._llm_router
    
    async def summarize(self, skill_name: str, result: Dict[str, Any], 
                       user_message: str = "") -> str:
        """智能总结技能执行结果
        
        Args:
            skill_name: 技能名称
            result: 技能执行结果
            user_message: 用户原始消息
            
        Returns:
            人性化的回复文本
        """
        logger.info(f"summarize被调用: skill_name={skill_name}, result类型={type(result)}")
        try:
            # 检查执行是否成功
            if not result.get("success", False):
                error_msg = result.get("error", "未知错误")
                return f" 执行失败：{error_msg}"
            
            # ✅ 白名单检查：如果工具在白名单中，直接返回原始回复
            if self._is_in_whitelist(skill_name):
                logger.info(f"技能 [{skill_name}] 在白名单中，直接返回原始回复")
                return self._get_direct_reply(result)
            
            # 获取结果数据
            result_data = result.get("result", result.get("data", {}))
            logger.info(f"技能 [{skill_name}] result_data类型: {type(result_data)}")

            # 判断结果类型并选择总结策略
            summary = await self._choose_summary_strategy(
                skill_name, result_data, user_message
            )
            
            logger.info(f"技能 [{skill_name}] 结果总结完成")
            return summary
            
        except Exception as e:
            logger.error(f"结果总结失败: {e}", exc_info=True)
            return f"处理完成（总结异常：{e}）"
    
    def _is_in_whitelist(self, skill_name: str) -> bool:
        """检查技能是否在白名单中
        
        Args:
            skill_name: 技能名称
            
        Returns:
            True 如果在白名单中
        """
        # 精确匹配
        if skill_name in self.config.direct_reply_whitelist:
            return True
        
        # 前缀匹配（支持带命名空间的技能名，如 "skills.translator"）
        for whitelisted in self.config.direct_reply_whitelist:
            if skill_name.endswith(whitelisted) or whitelisted in skill_name:
                return True
        
        return False
    
    def _get_direct_reply(self, result: Dict[str, Any]) -> str:
        """获取直接回复（白名单工具）
        
        优先使用工具自带的 reply 字段，如果没有则返回简单提示
        
        Args:
            result: 工具执行结果
            
        Returns:
            直接回复文本
        """
        # 优先使用工具生成的 reply
        if result.get("reply"):
            return result["reply"]
        
        # 其次使用 result 中的文本内容
        result_data = result.get("result", {})
        if isinstance(result_data, dict):
            # 尝试从常见字段获取
            for key in ["translated", "text", "content", "message"]:
                if key in result_data:
                    value = result_data[key]
                    if isinstance(value, str) and value:
                        return value
        
        # 最后返回简单提示
        return "✅ 执行完成"
    
    async def _choose_summary_strategy(self, skill_name: str, 
                                      result_data: Any,
                                      user_message: str) -> str:
        """选择总结策略
        
        根据数据类型选择不同的处理方式：
        1. 文本/文件类 → 告知位置
        2. 结构化数据 → 提取关键信息
        3. 简单字符串 → 直接返回
        """
        
        # 策略1: 检查是否是文件路径
        if isinstance(result_data, str):
            # 检测是否为文件路径
            if self._is_file_path(result_data):
                return self._format_file_location_reply(result_data, skill_name)
            
            # 检测是否包含文本类型关键词
            if self._contains_text_keywords(result_data):
                return self._format_text_location_reply(result_data, skill_name)
            
            # 普通字符串，直接返回或简短总结
            if len(result_data) <= 100:
                return result_data
            else:
                # 长文本，使用AI总结
                return await self._ai_summarize_text(result_data, skill_name)
        
        # 策略2: 字典类型（结构化数据）
        elif isinstance(result_data, dict):
            return await self._summarize_structured_data(
                skill_name, result_data, user_message
            )
        
        # 策略3: 列表类型
        elif isinstance(result_data, list):
            return await self._summarize_list_data(
                skill_name, result_data, user_message
            )
        
        # 策略4: 其他类型，转为字符串
        else:
            return str(result_data)
    
    def _is_file_path(self, text: str) -> bool:
        """判断是否为文件路径"""
        # 检查常见文件扩展名
        for ext in self.config.file_extensions:
            if text.lower().endswith(ext):
                return True
        
        # 检查是否包含路径分隔符
        if '/' in text or '\\' in text:
            return True
        
        return False
    
    def _contains_text_keywords(self, text: str) -> bool:
        """检查是否包含文本类型关键词"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.config.text_type_keywords)
    
    def _format_file_location_reply(self, file_path: str, skill_name: str) -> str:
        """格式化文件位置回复"""
        # 提取文件名
        import os
        filename = os.path.basename(file_path)
        
        # 提取目录
        directory = os.path.dirname(file_path) or "当前目录"
        
        skill_icons = {
            "weather": "🌤️",
            "web_scraper": "🕷️",
            "data_analysis": "📊",
            "text_analyzer": "📝",
        }
        icon = skill_icons.get(skill_name, "✅")
        
        return (
            f"{icon} **处理完成！**\n\n"
            f"📄 文件已生成：`{filename}`\n"
            f"📁 保存位置：`{directory}`\n\n"
            f"💡 提示：您可以直接打开该文件查看完整内容"
        )
    
    def _format_text_location_reply(self, text_preview: str, skill_name: str) -> str:
        """格式化文本位置回复"""
        # 截取前50字符作为预览
        preview = text_preview[:50].replace('\n', ' ')
        if len(text_preview) > 50:
            preview += "..."
        
        skill_icons = {
            "text_analyzer": "📝",
            "summarizer": "📋",
        }
        icon = skill_icons.get(skill_name, "✅")
        
        return (
            f"{icon} **文本已生成！**\n\n"
            f"📝 预览：{preview}\n\n"
            f"💡 提示：完整文本已保存到系统，您可以通过以下方式查看：\n"
            f"   • 在对话历史中查看\n"
            f"   • 导出为文件"
        )
    
    async def _ai_summarize_text(self, text: str, skill_name: str) -> str:
        """使用AI总结长文本"""
        llm_router = await self._get_llm_router()
        
        if not llm_router or not self.config.enable_ai_summary:
            # 降级：不使用AI，返回简短提示
            preview = text[:100].replace('\n', ' ')
            if len(text) > 100:
                preview += "..."
            return f"✅ 已生成文本内容（{len(text)}字符）\n\n预览：{preview}"
        
        try:
            prompt = f"""请对以下文本进行简洁总结（不超过{self.config.max_summary_length}字）：

{text[:500]}

要求：
1. 提取核心要点
2. 用通俗易懂的语言
3. 突出重要信息
4. 保持客观准确"""
            
            summary = await llm_router.simple_chat(prompt)
            
            skill_icons = {
                "text_analyzer": "📝",
                "summarizer": "📋",
            }
            icon = skill_icons.get(skill_name, "✅")
            
            return f"{icon} **文本总结**\n\n{summary}"
            
        except Exception as e:
            logger.warning(f"AI总结失败，使用降级方案: {e}")
            preview = text[:100].replace('\n', ' ')
            if len(text) > 100:
                preview += "..."
            return f"✅ 已生成文本内容（{len(text)}字符）\n\n预览：{preview}"
    
    async def _summarize_structured_data(self, skill_name: str, 
                                        data: dict,
                                        user_message: str) -> str:
        """总结结构化数据"""
        
        # ✅ 防御性编程：确保data是字典类型
        if not isinstance(data, dict):
            logger.warning(f"结构化数据格式异常 [{skill_name}]，期望dict，实际为{type(data).__name__}: {str(data)[:100]}")
            # 如果是字符串，直接返回
            if isinstance(data, str):
                return data if data else "✅ 执行完成"
            return f"✅ {skill_name} 执行完成"
        
        # 特殊处理：天气数据
        if skill_name == "weather" or "weather" in skill_name:
            return self._summarize_weather_data(data)
        
        # 特殊处理：爬虫数据
        if skill_name == "web_scraper" or "scraper" in skill_name:
            return self._summarize_scraper_data(data)
        
        # 通用结构化数据总结
        return await self._generic_structured_summary(skill_name, data, user_message)
    
    def _summarize_weather_data(self, data: dict) -> str:
        """总结天气数据"""
        # ✅ 防御性编程：确保data是字典类型
        if not isinstance(data, dict):
            logger.warning(f"天气数据格式异常，期望dict，实际为{type(data).__name__}: {data}")
            # 尝试从原始结果中提取天气信息
            return f"🌤️ 天气查询完成"
        
        city = data.get("city", "未知城市")
        temperature = data.get("temperature", data.get("temp", "N/A"))
        condition = data.get("condition", data.get("weather", "N/A"))
        humidity = data.get("humidity", "")
        wind = data.get("wind", data.get("wind_speed", ""))
        
        # 构建天气图标
        weather_icons = {
            "晴": "☀️",
            "多云": "⛅",
            "阴": "☁️",
            "雨": "🌧️",
            "雪": "❄️",
            "雷": "⛈️",
        }
        
        icon = "🌤️"
        for key, value in weather_icons.items():
            if key in str(condition):
                icon = value
                break
        
        reply = f"{icon} **{city}天气**\n\n"
        reply += f"🌡️ 温度：{temperature}\n"
        reply += f"🌤️ 天气：{condition}"
        
        if humidity:
            reply += f"\n💧 湿度：{humidity}"
        if wind:
            reply += f"\n🌬️ 风力：{wind}"
        
        reply += "\n\n💡 建议："
        if "雨" in str(condition):
            reply += "记得带伞哦！☂️"
        elif "晴" in str(condition) and "25" in str(temperature):
            reply += "天气不错，适合出门！😊"
        else:
            reply += "注意适时增减衣物"
        
        return reply
    
    def _summarize_scraper_data(self, data: dict) -> str:
        """总结爬虫数据"""
        site = data.get("site", "网站")
        items = data.get("items", data.get("results", []))
        
        if not items:
            return f"🕷️ 爬取完成\n\n未找到数据"
        
        count = len(items)
        reply = f"🕷️ **{site}爬取完成**\n\n"
        reply += f"📊 共获取 {count} 条数据\n\n"
        
        # 显示前3条
        reply += "**热门内容：**\n"
        for i, item in enumerate(items[:3], 1):
            if isinstance(item, dict):
                title = item.get("title", item.get("name", "无标题"))
                reply += f"{i}. {title}\n"
            else:
                reply += f"{i}. {str(item)[:50]}\n"
        
        if count > 3:
            reply += f"\n... 还有 {count - 3} 条数据"
        
        return reply
    
    async def _generic_structured_summary(self, skill_name: str, 
                                         data: dict,
                                         user_message: str) -> str:
        """通用结构化数据总结"""
        
        # 尝试提取关键字段
        keys = list(data.keys())
        
        # 如果字段太多，使用AI总结
        if len(keys) > 5 and self.config.enable_ai_summary:
            llm_router = await self._get_llm_router()
            if llm_router:
                try:
                    prompt = f"""请用一句话总结以下数据的核心内容（不超过50字）：

{str(data)[:300]}

用户问题：{user_message}"""
                    
                    summary = await llm_router.simple_chat(prompt)
                    return f"✅ **处理完成**\n\n{summary}"
                except Exception:
                    pass
        
        # 简单展示关键字段
        reply = f"✅ **{skill_name} 执行完成**\n\n"
        
        # 展示前3个关键字段
        important_keys = ["result", "status", "message", "count", "total"]
        shown_keys = []
        
        for key in important_keys:
            if key in data:
                value = data[key]
                if isinstance(value, (str, int, float)):
                    reply += f"• {key}: {value}\n"
                    shown_keys.append(key)
        
        # 如果没有重要字段，展示前3个
        if not shown_keys:
            for key in keys[:3]:
                value = data[key]
                if isinstance(value, (str, int, float)):
                    reply += f"• {key}: {value}\n"
        
        return reply
    
    async def _summarize_list_data(self, skill_name: str,
                                  data: list,
                                  user_message: str) -> str:
        """总结列表数据"""
        
        count = len(data)
        
        if count == 0:
            return f"✅ **处理完成**\n\n未找到数据"
        
        reply = f"✅ **{skill_name} 执行完成**\n\n"
        reply += f"📊 共 {count} 条结果\n\n"
        
        # 显示前5条
        reply += "**结果预览：**\n"
        for i, item in enumerate(data[:5], 1):
            if isinstance(item, dict):
                # 尝试提取有意义的字段
                title = item.get("title", item.get("name", 
                         item.get("content", str(item)[:30])))
                reply += f"{i}. {title}\n"
            else:
                preview = str(item)[:50]
                reply += f"{i}. {preview}\n"
        
        if count > 5:
            reply += f"\n... 还有 {count - 5} 条结果"
        
        return reply


# 全局单例
_summarizer = None


def get_result_summarizer() -> SmartResultSummarizer:
    """获取结果总结器单例"""
    global _summarizer
    if _summarizer is None:
        _summarizer = SmartResultSummarizer()
    return _summarizer
