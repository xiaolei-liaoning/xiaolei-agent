"""深度思考技能处理器

核心功能：
- 深度思考引擎集成
- 自主搜索功能
- 完整的思考-搜索-验证闭环

使用场景：
- 需要深度分析的问题
- 需要实时信息的问题
- 需要多步推理的问题
"""
import logging
import asyncio
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class DeepThinkingHandler:
    """深度思考技能处理器"""
    
    def __init__(self):
        self.reasoning_engine = None
        self._initialize_dependencies()
    
    def _initialize_dependencies(self):
        """初始化依赖"""
        try:
            from core.reasoning_engine import get_reasoning_engine
            self.reasoning_engine = get_reasoning_engine()
            logger.info("深度思考引擎初始化成功")
        except Exception as e:
            logger.error("深度思考引擎初始化失败: %s", e)
    
    async def execute(self, query: str, user_id: int = 1) -> Dict[str, Any]:
        """执行深度思考
        
        Args:
            query: 用户查询
            user_id: 用户ID
            
        Returns:
            包含思考结果和最终答案的字典
        """
        if not self.reasoning_engine:
            return {
                "success": False,
                "error": "深度思考引擎未初始化",
                "reply": "抱歉，深度思考功能暂时不可用。"
            }
        
        try:
            # 执行深度思考
            result = await self.reasoning_engine.process(query, user_id)
            
            # 构建回复
            reply = self._build_reply(result)
            
            return {
                "success": True,
                "result": result,
                "reply": reply
            }
        except Exception as e:
            logger.error("深度思考执行失败: %s", e)
            return {
                "success": False,
                "error": str(e),
                "reply": f"抱歉，深度思考过程中出现错误：{e}"
            }
    
    def _build_reply(self, result: Dict[str, Any]) -> str:
        """构建回复内容
        
        Args:
            result: 深度思考结果
            
        Returns:
            格式化的回复文本
        """
        final_answer = result.get("final_answer", "")
        thinking_process = result.get("thinking_process", {})
        search_results = thinking_process.get("search_results", [])
        
        # 构建回复
        reply_lines = []
        
        # 添加最终答案
        reply_lines.append("\n" + "=" * 60)
        reply_lines.append("💡 **深度思考结果**")
        reply_lines.append("=" * 60)
        reply_lines.append(final_answer)
        
        # 添加搜索结果（如果有）
        if search_results:
            reply_lines.append("\n" + "-" * 60)
            reply_lines.append("🔍 **参考信息**")
            reply_lines.append("-" * 60)
            for i, result in enumerate(search_results, 1):
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                url = result.get("url", "")
                reply_lines.append(f"[{i}] **{title}**")
                reply_lines.append(f"   {snippet[:100]}...")
                if url:
                    reply_lines.append(f"   🔗 {url}")
                reply_lines.append("")
        
        # 添加思考过程摘要
        reply_lines.append("\n" + "-" * 60)
        reply_lines.append("🧠 **思考过程**")
        reply_lines.append("-" * 60)
        
        understanding = thinking_process.get("understanding", {})
        if understanding:
            reply_lines.append(f"📝 **问题理解**: {understanding.get('question_type', '未知')}")
            reply_lines.append(f"   关键信息: {understanding.get('key_information', '')[:50]}...")
            reply_lines.append(f"   需要实时信息: {'是' if understanding.get('needs_realtime_info', False) else '否'}")
        
        plan = thinking_process.get("plan", {})
        if plan:
            steps = plan.get("steps", [])
            if steps:
                reply_lines.append("\n📋 **思考步骤**:")
                for i, step in enumerate(steps, 1):
                    reply_lines.append(f"   {i}. {step}")
        
        info_needed = thinking_process.get("info_needed", {})
        if info_needed:
            reply_lines.append(f"\n🔎 **信息需求**: {'需要搜索' if info_needed.get('needs_search', False) else '不需要搜索'}")
            if info_needed.get('needs_search', False):
                keywords = info_needed.get('search_keywords', [])
                if keywords:
                    reply_lines.append(f"   搜索关键词: {', '.join(keywords[:3])}")
        
        validation = thinking_process.get("validation", {})
        if validation:
            reply_lines.append(f"\n✅ **验证结果**: {'通过' if validation.get('validation_passed', False) else '未通过'}")
            reply_lines.append(f"   置信度: {validation.get('confidence', 0):.2f}")
            issues = validation.get('issues', [])
            if issues:
                reply_lines.append("   问题: " + ", ".join(issues[:2]))
        
        # 添加执行时间
        elapsed = result.get("elapsed_time", 0)
        reply_lines.append(f"\n⏱️ **执行时间**: {elapsed:.2f}秒")
        
        return "\n".join(reply_lines)


# 全局深度思考处理器实例
deep_thinking_handler = None

def get_deep_thinking_handler() -> DeepThinkingHandler:
    """获取深度思考处理器实例
    
    Returns:
        DeepThinkingHandler实例
    """
    global deep_thinking_handler
    if deep_thinking_handler is None:
        deep_thinking_handler = DeepThinkingHandler()
    return deep_thinking_handler