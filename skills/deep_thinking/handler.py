"""深度思考技能处理器（基于 Deep Thinking Protocol）

核心功能：
- 5阶段深度思考框架
- 思考深度自动选择（Quick/Standard/Deep）
- 决策复杂度矩阵
- 质量标准验证
- 自主搜索功能
- 完整的思考-搜索-验证闭环
- 超时重试机制（新增）
- 资源监控（新增）
- 进度追踪（新增）

使用场景：
- 需要深度分析的问题
- 需要实时信息的问题
- 需要多步推理的问题
- 复杂任务规划
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 导入新的思考深度枚举
try:
    from core.reasoning_engine import ThinkingDepth
except ImportError:
    logger.warning("无法导入 ThinkingDepth，使用默认值")
    # 定义本地版本作为备用
    class ThinkingDepth:
        QUICK = "quick"
        STANDARD = "standard"
        DEEP = "deep"


class DeepThinkingHandler:
    """深度思考技能处理器（增强版）"""
    
    def __init__(self):
        self.reasoning_engine = None
        self.resource_monitor = None
        self.progress_tracker = None
        self._initialize_dependencies()
    
    def _initialize_dependencies(self):
        """初始化依赖"""
        try:
            from core.reasoning_engine import get_reasoning_engine
            self.reasoning_engine = get_reasoning_engine()
            logger.info("深度思考引擎初始化成功")
        except Exception as e:
            logger.error("深度思考引擎初始化失败: %s", e)
        
        # 初始化性能监控工具
        try:
            from core.performance_utils import get_resource_monitor, get_progress_tracker
            self.resource_monitor = get_resource_monitor()
            self.progress_tracker = get_progress_tracker()
            logger.info("性能监控工具初始化成功")
        except Exception as e:
            logger.warning("性能监控工具初始化失败: %s (可选功能)", e)
    
    async def execute(self, query: str, user_id: int = 1, 
                     depth: Optional[str] = None, 
                     show_thinking: bool = True,
                     progress_callback = None) -> Dict[str, Any]:
        """执行深度思考（增强版）
        
        Args:
            query: 用户查询
            user_id: 用户ID
            depth: 强制使用的思考深度 ("quick"/"standard"/"deep")，None表示自动选择
            show_thinking: 是否在回复中显示思考过程
            progress_callback: 可选的进度回调函数
            
        Returns:
            包含思考结果和最终答案的字典
        """
        if not self.reasoning_engine:
            return {
                "success": False,
                "error": "深度思考引擎未初始化",
                "reply": "抱歉，深度思考功能暂时不可用。"
            }
        
        # 检查资源状态
        resource_status = None
        if self.resource_monitor:
            try:
                resource_status = self.resource_monitor.check_resources()
            except Exception as e:
                logger.debug(f"资源检查跳过: {e}")
        
        # 发送初始进度（如果有回调）
        if progress_callback and self.progress_tracker:
            try:
                if asyncio.iscoroutinefunction(progress_callback):
                    await progress_callback("initializing", "正在初始化深度思考引擎", 0, 5)
                else:
                    progress_callback("initializing", "正在初始化深度思考引擎", 0, 5)
            except Exception as e:
                logger.debug(f"进度回调失败: {e}")
        
        try:
            # 解析深度参数
            force_depth = None
            if depth:
                depth_lower = depth.lower()
                if depth_lower == "quick":
                    force_depth = ThinkingDepth.QUICK
                elif depth_lower == "standard":
                    force_depth = ThinkingDepth.STANDARD
                elif depth_lower == "deep":
                    force_depth = ThinkingDepth.DEEP
            
            # 更新进度：问题理解
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback("understanding", "正在理解问题需求", 1, 5)
                    else:
                        progress_callback("understanding", "正在理解问题需求", 1, 5)
                except Exception as e:
                    logger.debug(f"进度回调失败: {e}")
            
            # 执行深度思考（使用新的 protocol）
            if hasattr(self.reasoning_engine, 'process_with_protocol'):
                result = await self.reasoning_engine.process_with_protocol(
                    query, user_id, force_depth=force_depth
                )
            else:
                # 回退到旧方法
                result = await self.reasoning_engine.process(query, user_id)
            
            # 发送完成进度
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback("complete", "思考完成", 5, 5)
                    else:
                        progress_callback("complete", "思考完成", 5, 5)
                except Exception as e:
                    logger.debug(f"进度回调失败: {e}")
            
            # 构建回复
            reply = self._build_reply_enhanced(result, show_thinking)
            
            result_data = {
                "success": True,
                "result": result,
                "reply": reply
            }
            
            # 附加资源状态（如果有）
            if resource_status:
                result_data["resource_status"] = resource_status
            
            return result_data
        except Exception as e:
            logger.error("深度思考执行失败: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "reply": f"抱歉，深度思考过程中出现错误：{e}"
            }
    
    def _build_reply_enhanced(self, result: Dict[str, Any], show_thinking: bool) -> str:
        """构建回复内容（增强版）
        
        Args:
            result: 深度思考结果
            show_thinking: 是否显示思考过程
            
        Returns:
            格式化的回复文本
        """
        final_answer = result.get("final_answer", "")
        thinking_process = result.get("thinking_process", {})
        thinking_depth = result.get("thinking_depth", "standard")
        quality_report = result.get("quality_report", {})
        elapsed_time = result.get("elapsed_time", 0)
        
        # 构建回复部分
        reply_parts = []
        
        # 1. 添加最终答案
        reply_parts.append("\n" + "=" * 60)
        reply_parts.append("💡 **答案**")
        reply_parts.append("=" * 60)
        reply_parts.append(final_answer)
        
        if show_thinking:
            # 2. 添加思考深度信息
            depth_emoji = {
                "quick": "⚡",
                "standard": "🔄",
                "deep": "🧠"
            }.get(thinking_depth, "🔄")
            
            depth_name = {
                "quick": "快速模式",
                "standard": "标准模式",
                "deep": "深度模式"
            }.get(thinking_depth, "标准模式")
            
            reply_parts.append(f"\n{depth_emoji} **思考模式**: {depth_name}")
            reply_parts.append(f"⏱️ **处理时间**: {elapsed_time:.2f} 秒")
            
            # 3. 添加质量报告（如果有）
            if quality_report:
                overall_score = quality_report.get("overall_score", 0)
                reply_parts.append(f"\n📊 **质量评分**: {overall_score:.2%}")
                
                standards = quality_report.get("standards", {})
                if standards:
                    reply_parts.append("**质量检查**:")
                    for std_name, std_info in standards.items():
                        status = "✅" if std_info.get("passed") else "⚠️"
                        score = std_info.get("score", 0)
                        reply_parts.append(f"  {status} {std_name}: {score:.2%}")
            
            # 4. 添加搜索结果（如果有）
            search_results = thinking_process.get("search_results", [])
            if search_results:
                reply_parts.append("\n" + "-" * 60)
                reply_parts.append("🔍 **参考信息**")
                reply_parts.append("-" * 60)
                for i, sr in enumerate(search_results[:3], 1):
                    title = sr.get("title", "")
                    snippet = sr.get("snippet", "")
                    url = sr.get("url", "")
                    reply_parts.append(f"[{i}] **{title}**")
                    if snippet:
                        reply_parts.append(f"    {snippet[:120]}...")
                    if url:
                        reply_parts.append(f"    🔗 {url}")
                    reply_parts.append("")
            
            # 5. 添加5阶段思考过程摘要
            phase1 = thinking_process.get("phase1", {})
            phase2 = thinking_process.get("phase2", {})
            phase3 = thinking_process.get("phase3", {})
            phase4 = thinking_process.get("phase4", {})
            phase5 = thinking_process.get("phase5", {})
            
            if any([phase1, phase2, phase3, phase4, phase5]):
                reply_parts.append("\n" + "-" * 60)
                reply_parts.append("📋 **思考过程**")
                reply_parts.append("-" * 60)
                
                # Phase 1: 问题理解
                if phase1:
                    understanding = phase1.get("understanding", {})
                    restated_goal = phase1.get("restated_goal", "")
                    reply_parts.append("1️⃣ **问题理解**")
                    if restated_goal:
                        reply_parts.append(f"   🎯 {restated_goal}")
                    q_type = understanding.get("question_type", "")
                    if q_type:
                        reply_parts.append(f"   📌 类型: {q_type}")
                    needs_realtime = understanding.get("needs_realtime_info", False)
                    reply_parts.append(f"   🕐 需要实时信息: {'是' if needs_realtime else '否'}")
                
                # Phase 2: 信息收集
                if phase2:
                    search_count = len(phase2.get("search_results", []))
                    rag_count = len(phase2.get("rag_knowledge", []))
                    reply_parts.append(f"\n2️⃣ **信息收集**")
                    reply_parts.append(f"   🔍 搜索结果: {search_count} 条")
                    reply_parts.append(f"   📚 知识库: {rag_count} 条")
                
                # Phase 3: 方案设计
                if phase3:
                    approaches = phase3.get("all_approaches", [])
                    selected = phase3.get("selected_approach", {})
                    reply_parts.append(f"\n3️⃣ **方案设计**")
                    reply_parts.append(f"   💡 备选方案: {len(approaches)} 个")
                    if selected:
                        reply_parts.append(f"   ✅ 采用: {selected.get('name', 'unknown')}")
                
                # Phase 4: 执行验证
                if phase4:
                    validation = phase4.get("validation", {})
                    passed = phase4.get("passed", False)
                    confidence = validation.get("confidence", 0)
                    reply_parts.append(f"\n4️⃣ **执行验证**")
                    reply_parts.append(f"   {'✅' if passed else '❌'} 验证: {'通过' if passed else '未通过'}")
                    reply_parts.append(f"   🎯 置信度: {confidence:.2%}")
                
                # Phase 5: 反思优化
                if phase5 and phase5.get("reflection_done"):
                    iterations = phase5.get("iterations_completed", 0)
                    learnings = phase5.get("key_learnings", [])
                    reply_parts.append(f"\n5️⃣ **反思优化**")
                    reply_parts.append(f"   🔄 迭代次数: {iterations}")
                    if learnings:
                        reply_parts.append(f"   💡 关键经验: {len(learnings)} 条")
        
        return "\n".join(reply_parts)
    
    def _build_reply(self, result: Dict[str, Any]) -> str:
        """构建回复内容（旧版本，保留兼容性）
        
        Args:
            result: 深度思考结果
            
        Returns:
            格式化的回复文本
        """
        return self._build_reply_enhanced(result, show_thinking=True)


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
