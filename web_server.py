#!/usr/bin/env python
"""FastAPI Web服务器 - 支持@+标签技能选择

提供Web界面和API接口，支持：
1. @+标签技能选择
2. 实时任务分解
3. 技能推荐和搜索
4. WebSocket实时通信
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn
from datetime import datetime
import asyncio

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from core.task_decomposer import TaskDecomposer
from core.skill_dispatcher import SkillDispatcher
from planning_agent import planning_agent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="AI任务分解系统", version="1.0.0")

# 初始化组件
task_decomposer = TaskDecomposer()
skill_dispatcher = SkillDispatcher()

# WebSocket连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error("发送消息失败: %s", e)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("广播消息失败: %s", e)

manager = ConnectionManager()

# 配置模板和静态文件
templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"

templates_dir.mkdir(exist_ok=True)
static_dir.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(templates_dir))

# 挂载静态文件
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Pydantic模型
class DecomposeRequest(BaseModel):
    task: str
    selected_skills: List[str] = []

class ChatRequest(BaseModel):
    message: str
    character_id: str = "default"


# 简单的内存存储，用于演示历史记录
chat_history = []


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """聊天页面"""
    return templates.TemplateResponse("chat.html", {"request": request})


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket聊天端点"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message")
            character_id = data.get("character_id", "default")
            
            # 保存用户消息
            user_message = {
                "id": len(chat_history) + 1,
                "user_id": 1,
                "character_id": character_id,
                "role": "user",
                "content": message,
                "created_at": datetime.now().isoformat()
            }
            chat_history.append(user_message)
            
            # 检查是否需要使用PlanningAgent
            if any(keyword in message for keyword in ["爬取", "抓取", "crawl", "scrape", "热搜", "天气", "weather", "检索", "搜索", "查找"]):
                # 使用PlanningAgent执行复杂任务
                try:
                    result = await planning_agent.execute(message)
                    reply = f"✅ 任务执行完成\n\n**执行结果:**\n{result['message']}\n\n**执行时间:**\n预估: {result['estimated_time']}秒\n实际: {result['actual_time']}秒"
                    if result.get("detailed_steps"):
                        reply += "\n\n**详细步骤:**"
                        for step in result['detailed_steps']:
                            reply += f"\n{step['step']}. {step['description']} (约{step['estimated_time']}秒)"
                except Exception as e:
                    logger.error("PlanningAgent执行失败: %s", e)
                    reply = f"抱歉，执行任务时出错: {str(e)}"
            else:
                # 生成简单的回复
                reply = f"我收到了你的消息: {message}"
            
            # 保存助手回复
            assistant_message = {
                "id": len(chat_history) + 1,
                "user_id": 1,
                "character_id": character_id,
                "role": "assistant",
                "content": reply,
                "created_at": datetime.now().isoformat()
            }
            chat_history.append(assistant_message)
            
            # 发送回复
            await manager.send_personal_message({"reply": reply, "character_id": character_id}, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket错误: %s", e)
        manager.disconnect(websocket)


@app.get("/api/history")
async def get_chat_history(
    user_id: int = 1,
    character_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by_session: bool = False,
) -> Dict[str, Any]:
    """获取聊天历史"""
    try:
        # 过滤历史记录
        filtered_history = chat_history
        if character_id:
            filtered_history = [h for h in filtered_history if h.get("character_id") == character_id]
        
        # 按时间倒序排序
        filtered_history.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        # 分页
        paginated_history = filtered_history[offset:offset + limit]
        
        if group_by_session:
            # 按会话分组
            sessions = {}
            for record in paginated_history:
                session_id = record.get("character_id", "default")
                if session_id not in sessions:
                    sessions[session_id] = {
                        "session_id": session_id,
                        "character_id": session_id,
                        "message_count": 0,
                        "last_message_time": None,
                        "preview": ""
                    }
                sessions[session_id]["message_count"] += 1
                sessions[session_id]["last_message_time"] = record.get("created_at")
                if record.get("role") == "user":
                    sessions[session_id]["preview"] = record.get("content", "")[:50]
            
            return {
                "sessions": list(sessions.values()),
                "total": len(filtered_history)
            }
        else:
            return {
                "history": paginated_history,
                "total": len(filtered_history)
            }
    except Exception as e:
        logger.error("获取聊天历史失败: %s", e)
        return {"history": [], "total": 0, "error": str(e)}


@app.get("/api/history/session/{session_id}")
async def get_session_history(
    session_id: str,
    user_id: int = 1,
) -> Dict[str, Any]:
    """获取会话历史"""
    try:
        # 过滤该会话的历史记录
        session_history = [
            h for h in chat_history 
            if h.get("character_id") == session_id
        ]
        
        # 按时间正序排序
        session_history.sort(key=lambda x: x.get("created_at", ""))
        
        return {"messages": session_history}
    except Exception as e:
        logger.error("获取会话历史失败: %s", e)
        return {"messages": []}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> Dict[str, Any]:
    """处理聊天请求"""
    try:
        # 保存用户消息
        user_message = {
            "id": len(chat_history) + 1,
            "user_id": 1,
            "character_id": request.character_id,
            "role": "user",
            "content": request.message,
            "created_at": datetime.now().isoformat()
        }
        chat_history.append(user_message)
        
        # 检查是否需要使用PlanningAgent
        if any(keyword in request.message for keyword in ["爬取", "抓取", "crawl", "scrape", "热搜", "天气", "weather", "检索", "搜索", "查找"]):
            # 使用PlanningAgent执行复杂任务
            try:
                result = await planning_agent.execute(request.message)
                reply = f"✅ 任务执行完成\n\n**执行结果:**\n{result['message']}\n\n**执行时间:**\n预估: {result['estimated_time']}秒\n实际: {result['actual_time']}秒"
                if result.get("detailed_steps"):
                    reply += "\n\n**详细步骤:**"
                    for step in result['detailed_steps']:
                        reply += f"\n{step['step']}. {step['description']} (约{step['estimated_time']}秒)"
            except Exception as e:
                logger.error("PlanningAgent执行失败: %s", e)
                reply = f"抱歉，执行任务时出错: {str(e)}"
        else:
            # 生成简单的回复
            reply = f"我收到了你的消息: {request.message}"
        
        # 保存助手回复
        assistant_message = {
            "id": len(chat_history) + 1,
            "user_id": 1,
            "character_id": request.character_id,
            "role": "assistant",
            "content": reply,
            "created_at": datetime.now().isoformat()
        }
        chat_history.append(assistant_message)
        
        return {
            "success": True,
            "message": request.message,
            "reply": reply,
            "conversation_id": request.character_id
        }
    except Exception as e:
        logger.error("处理聊天请求失败: %s", e)
        return {"success": False, "error": str(e)}



def get_all_skills() -> List[Dict[str, Any]]:
    """获取所有技能信息"""
    skills_dir = Path(__file__).parent / "skills"
    skills = []
    
    if not skills_dir.exists():
        return skills
    
    for item in skills_dir.iterdir():
        if item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding='utf-8')
                    
                    # 提取技能信息
                    skill_name = item.name
                    description = ""
                    keywords = []
                    
                    lines = content.split('\n')
                    in_description = False
                    in_keywords = False
                    
                    for line in lines:
                        if '功能描述' in line:
                            in_description = True
                            in_keywords = False
                            continue
                        elif '触发关键词' in line:
                            in_keywords = True
                            in_description = False
                            continue
                        elif line.startswith('##'):
                            in_description = False
                            in_keywords = False
                            continue
                        
                        if in_description and line.strip():
                            description += line.strip() + ' '
                        elif in_keywords and line.strip():
                            keywords.append(line.strip())
                    
                    skills.append({
                        'name': skill_name,
                        'display_name': skill_name.replace('_', ' ').title(),
                        'description': description.strip(),
                        'keywords': keywords,
                        'tag': f"@{skill_name}"
                    })
                    
                except Exception as e:
                    logger.error("读取技能失败: %s, 错误: %s", skill_md, e)
    
    return skills


# 缓存技能列表
SKILLS_CACHE = get_all_skills()
logger.info("加载了 %d 个技能", len(SKILLS_CACHE))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "skills": SKILLS_CACHE
    })


@app.get("/api/skills")
async def get_skills_api():
    """获取所有技能API"""
    return JSONResponse({
        'success': True,
        'data': SKILLS_CACHE
    })


@app.get("/api/skills/search")
async def search_skills_api(q: str = ""):
    """搜索技能API"""
    query = q.lower()
    
    if not query:
        return JSONResponse({
            'success': True,
            'data': SKILLS_CACHE
        })
    
    # 搜索匹配的技能
    filtered_skills = []
    for skill in SKILLS_CACHE:
        # 匹配技能名称
        if query in skill['name'].lower():
            filtered_skills.append(skill)
            continue
        
        # 匹配显示名称
        if query in skill['display_name'].lower():
            filtered_skills.append(skill)
            continue
        
        # 匹配关键词
        for keyword in skill['keywords']:
            if query in keyword.lower():
                filtered_skills.append(skill)
                break
    
    return JSONResponse({
        'success': True,
        'data': filtered_skills
    })


@app.post("/api/decompose")
async def decompose_task_api(request: DecomposeRequest):
    """任务分解API"""
    try:
        task = request.task
        selected_skills = request.selected_skills
        
        if not task:
            raise HTTPException(status_code=400, detail="任务描述不能为空")
        
        logger.info("任务分解请求: %s, 选中技能: %s", task, selected_skills)
        
        # 执行任务分解
        result = await task_decomposer.decompose(task)
        
        # 转换为字典格式
        result_dict = task_decomposer.to_dict(result)
        
        # 如果用户选择了特定技能，优先使用这些技能
        if selected_skills:
            logger.info("用户选择了技能: %s", selected_skills)
            # 可以在这里添加逻辑来调整分解结果，优先使用用户选择的技能
        
        return JSONResponse({
            'success': True,
            'data': result_dict
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("任务分解失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/skill/{skill_name}")
async def get_skill_detail(skill_name: str):
    """获取技能详情API"""
    skill_dir = Path(__file__).parent / "skills" / skill_name
    skill_md = skill_dir / "SKILL.md"
    
    if not skill_md.exists():
        raise HTTPException(status_code=404, detail="技能不存在")
    
    try:
        content = skill_md.read_text(encoding='utf-8')
        return JSONResponse({
            'success': True,
            'data': {
                'name': skill_name,
                'content': content
            }
        })
    except Exception as e:
        logger.error("读取技能详情失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """健康检查"""
    return JSONResponse({
        'status': 'healthy',
        'skills_count': len(SKILLS_CACHE),
        'active_connections': len(manager.active_connections)
    })


if __name__ == '__main__':
    # 启动服务器
    logger.info("启动FastAPI服务器...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )