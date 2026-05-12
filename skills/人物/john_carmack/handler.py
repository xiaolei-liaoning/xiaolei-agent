"""
John Carmack Skill Handler - 集成记忆系统
"""

import logging

logger = logging.getLogger(__name__)


class JohnCarmackHandler:
    """John Carmack角色处理器"""
    
    def __init__(self):
        self.character_id = "john_carmack"
        self.name = "John Carmack"
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
            logger.info(f"John Carmack Skill依赖初始化成功")
        except Exception as e:
            logger.warning(f"John Carmack Skill依赖初始化失败: {e}")
    
    async def execute(self, message: str = "", **kwargs):
        """执行John Carmack风格回复"""
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
                system_prompt = f"""你是John Carmack，传奇游戏程序员，id Software创始人。
性格描述: 技术天才，专注于游戏引擎开发和性能优化
说话风格: 技术型、简洁、逻辑性强
语气: 专业、理性
常用表达方式: 从技术角度看...、关键在于...、优化的关键是...

{context}

请用技术专家的风格回复用户。"""
                
                response = await self.llm_router.simple_chat(
                    user_message=message,
                    system_prompt=system_prompt,
                    temperature=0.6
                )
                response_text = response
            except Exception as e:
                logger.warning(f"LLM调用失败: {e}")
                response_text = f"[John Carmack] {message}"
        
        # 如果LLM不可用，使用默认回复
        if not response_text:
            response_text = f"[John Carmack模式] {message}"
        
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


handler = JohnCarmackHandler()
