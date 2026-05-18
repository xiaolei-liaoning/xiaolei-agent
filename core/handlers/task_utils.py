"""任务处理工具函数"""

import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


def convert_action_to_natural_language(action: str, params: Dict[str, Any]) -> str:
    """将技能action和params转换为自然语言描述
    
    Args:
        action: 技能名称
        params: 技能参数
        
    Returns:
        自然语言描述
    """
    if action == "gui_automation":
        app = params.get("application", "")
        act = params.get("action", "打开")
        if app:
            return f"{act}{app}"
        return "执行GUI操作"
    
    elif action == "web_scraper":
        site = params.get("site_name", "")
        act = params.get("action", "")
        if site and act:
            return f"爬取{site}的{act}"
        elif site:
            return f"爬取{site}"
        return "爬取网页数据"
    
    elif action == "rag_search":
        query = params.get("query", "")
        if query:
            return f"搜索{query}"
        return "执行搜索"
    
    elif action == "weather":
        city = params.get("city", "")
        if city:
            return f"查询{city}的天气"
        return "查询天气"
    
    elif action == "translator":
        text = params.get("text", "")
        if text:
            return f"翻译: {text[:30]}"
        return "执行翻译"
    
    elif action == "data_analysis":
        return "分析数据"
    
    elif action == "text_analyzer":
        text = params.get("text", "")
        if text:
            return f"分析文本: {text[:20]}"
        return "分析文本"
    
    elif action == "chat":
        msg = params.get("message", "")
        if msg:
            return msg
        return "进行对话"
    
    return f"执行{action}"


async def process_task_with_processor(task: Dict[str, Any], user_id: int = 1) -> Dict[str, Any]:
    """使用 TaskProcessor 处理任务，并转换为 TaskPlanner 格式
    
    Args:
        task: 原始任务格式
        user_id: 用户ID
        
    Returns:
        包含子任务列表和处理路径的字典
    """
    from ..tasks.task_processor import task_processor
    
    message = task.get("user_message", "")
    
    result = await task_processor.process(message)
    
    sub_tasks = []
    for i, subtask in enumerate(result.subtasks):
        action_desc = convert_action_to_natural_language(subtask.action, subtask.params)
        
        sub_task = {
            "task_id": task.get("task_id", 1) * 100 + i + 1,
            "user_id": user_id,
            "user_message": action_desc,
            "ai_response": f"执行: {subtask.action}",
            "tool_call": {
                "name": subtask.action,
                "params": subtask.params
            },
            "status": "pending",
            "timestamp": datetime.now().isoformat(),
        }
        sub_tasks.append(sub_task)
    
    if not sub_tasks:
        return {"sub_tasks": [task], "path": "none"}
    
    return {"sub_tasks": sub_tasks, "path": result.path.value}
