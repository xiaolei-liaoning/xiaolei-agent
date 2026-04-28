"""
知心闺蜜 Skill Handler
"""

class BestfriendHandler:
    """知心闺蜜角色扮演处理器"""
    
    def __init__(self):
        self.character_id = "bestfriend"
        self.name = "知心闺蜜"
    
    async def execute(self, **kwargs):
        """执行知心闺蜜角色对话"""
        # 延迟导入，避免循环导入
        from core.multi_agent_system import agent_scheduler
        
        # 调用agent的功能
        print("知心闺蜜正在调用agent功能...")
        # 执行检查任务
        check_result = await agent_scheduler.submit_task("check", {"url": "https://example.com"})
        print(f"检查任务结果: {check_result}")
        
        return {
            "success": True,
            "character_id": self.character_id,
            "role": self.name,
            "agent_result": check_result
        }

handler = BestfriendHandler()