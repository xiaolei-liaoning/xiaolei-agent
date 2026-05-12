"""
知心闺蜜 Skill Handler - 集成记忆系统
"""

import logging

logger = logging.getLogger(__name__)


class BestFriendHandler:
    """知心闺蜜角色处理器"""
    
    def __init__(self):
        self.character_id = "bestfriend"
        self.name = "知心闺蜜"
        self.memory_manager = None
        self.llm_router = None
        self._init_dependencies()
    
    def _init_dependencies(self):
        """初始化依赖"""
        try:
            from core.character_memory import character_memory_manager
            from core.llm_backend import get_llm_router
            self.memory_manager = character_memory_manager
            self.llm_router = get_llm_router()
            logger.info(f"知心闺蜜Skill依赖初始化成功")
        except Exception as e:
            logger.warning(f"知心闺蜜Skill依赖初始化失败: {e}")
    
    async def execute(self, message: str = "", **kwargs):
        """执行知心闺蜜风格回复"""
        # 记录对话到记忆
        if self.memory_manager and message:
            await self.memory_manager.add_memory_to_character(
                self.character_id,
                f"用户说: {message}"
            )
        
        # 获取性格和记忆上下文
        context = ""
        if self.memory_manager:
            context = await self.memory_manager.get_character_response_context(self.character_id)
        
        # 使用LLM生成响应（如果可用）
        response_text = ""
        if self.llm_router and message:
            try:
                system_prompt = f"""你是知心闺蜜，亲密的女性朋友。
性格描述: 善解人意，乐于倾听，温暖支持
说话风格: 亲切、温暖、支持
语气: 关心、鼓励
常用表达方式: 亲爱的...、我理解...、加油哦...

{context}

请用知心闺蜜的温暖语气回复用户。"""
                
                response = await self.llm_router.simple_chat(
                    user_message=message,
                    system_prompt=system_prompt,
                    temperature=0.85
                )
                response_text = response
            except Exception as e:
                logger.warning(f"LLM调用失败: {e}")
                response_text = f"[知心闺蜜] {message}"
        
        # 如果LLM不可用，使用默认回复
        if not response_text:
            response_text = f"[知心闺蜜模式] {message}"
        
        # 记录响应到记忆
        if self.memory_manager:
            await self.memory_manager.add_memory_to_character(
                self.character_id,
                f"我回复: {response_text[:50]}..."
            )
        
        return {
            "success": True,
            "character_id": self.character_id,
            "character": self.name,
            "reply": response_text
        }


handler = BestFriendHandler()
