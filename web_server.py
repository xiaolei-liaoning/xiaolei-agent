#!/usr/bin/env python
"""FastAPI Web服务器 - 前端代理层

架构说明：
- web_server.py (端口8000): 仅提供Web界面和静态文件服务
- main.py (端口8001): 核心业务逻辑（Agent系统、RAG、BFS记忆等）
- 所有API请求通过HTTP转发到main.py，实现状态共享和统一入口

提供功能：
1. Web界面托管（聊天页面、工作流编辑器等）
2. WebSocket实时通信代理
3. API请求转发到main.py
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
import httpx

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# ⚠️ 移除本地组件初始化，改为转发到main.py
from core.tasks.task_processor import task_processor
# from core.engine.skill_dispatcher import SkillDispatcher
# from planning_agent import planning_agent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="AI任务分解系统", version="1.0.0")

# main.py服务地址
MAIN_API_BASE = os.getenv("MAIN_API_URL", "http://localhost:8001")

# 注册 Agent 小组路由
try:
    from api.routes.agent_groups import router as agent_groups_router
    app.include_router(agent_groups_router)
    logger.info("Agent小组管理API路由已注册")
except Exception as e:
    logger.warning(f"Agent小组管理API路由注册失败: {e}")

# 注册计划管理路由
try:
    from api.routes.plans import router as plans_router
    app.include_router(plans_router)
    logger.info("计划管理API路由已注册")
except Exception as e:
    logger.warning(f"计划管理API路由注册失败: {e}")

# 注册工作流管理路由
try:
    from api.workflow import router as workflow_router
    app.include_router(workflow_router)
    logger.info("工作流管理API路由已注册")
except Exception as e:
    logger.warning(f"工作流管理API路由注册失败: {e}")

# 初始化组件 - 已移除，改为转发到main.py
# skill_dispatcher = SkillDispatcher()

# WebSocket连接管理
class ConnectionManager:
    def __init__(self, heartbeat_interval: int = 30, heartbeat_timeout: int = 60):
        """
        初始化连接管理器
        
        Args:
            heartbeat_interval: 心跳间隔（秒）
            heartbeat_timeout: 心跳超时时间（秒）
        """
        self.active_connections: List[WebSocket] = []
        self.connection_info: Dict[WebSocket, Dict[str, Any]] = {}
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start_heartbeat_check(self):
        """启动心跳检测任务"""
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            logger.warning("心跳检测任务已在运行")
            return
        
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("心跳检测任务已启动")
    
    async def stop_heartbeat_check(self):
        """停止心跳检测任务"""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        logger.info("心跳检测任务已停止")
    
    async def _heartbeat_loop(self):
        """心跳检测循环"""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._check_heartbeats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳检测循环异常: {e}")
    
    async def _check_heartbeats(self):
        """检查所有连接的心跳状态"""
        now = datetime.now()
        connections_to_remove = []
        
        for websocket in self.active_connections:
            info = self.connection_info.get(websocket, {})
            last_pong = info.get("last_pong")
            
            # 发送 ping
            try:
                await websocket.send_json({
                    "type": "ping",
                    "timestamp": now.isoformat()
                })
                info["last_ping"] = now
                logger.debug(f"发送 ping 到连接: {id(websocket)}")
            except Exception as e:
                logger.warning(f"发送 ping 失败: {e}")
                connections_to_remove.append(websocket)
                continue
            
            # 检查超时
            if last_pong:
                time_since_pong = (now - last_pong).total_seconds()
                if time_since_pong > self.heartbeat_timeout:
                    logger.warning(f"连接超时: {id(websocket)}, 最后 pong: {time_since_pong:.1f}秒前")
                    connections_to_remove.append(websocket)
        
        # 清理超时连接
        for websocket in connections_to_remove:
            try:
                await self.disconnect(websocket)
            except Exception as e:
                logger.error(f"清理超时连接失败: {e}")
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_info[websocket] = {
            "connected_at": datetime.now(),
            "last_pong": datetime.now(),
            "last_ping": None
        }
        logger.info(f"新连接: {id(websocket)}, 当前活跃连接数: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.connection_info:
            del self.connection_info[websocket]
        # 尝试关闭连接
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"连接断开: {id(websocket)}, 当前活跃连接数: {len(self.active_connections)}")
    
    def update_pong(self, websocket: WebSocket):
        """更新 pong 时间"""
        if websocket in self.connection_info:
            self.connection_info[websocket]["last_pong"] = datetime.now()
            logger.debug(f"收到 pong 从连接: {id(websocket)}")
    
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
    user_id: int = 1
    agent_id: str = "auto"  # 默认为智能匹配


# 简单的内存存储，用于演示历史记录
chat_history = []


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """聊天页面"""
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/coze", response_class=HTMLResponse)
async def coze_page(request: Request):
    """Coze平台页面"""
    return templates.TemplateResponse("coze.html", {"request": request})


@app.get("/workflow_editor", response_class=HTMLResponse)
async def workflow_editor_page(request: Request):
    """工作流编辑器页面"""
    return templates.TemplateResponse("workflow_editor.html", {"request": request})


@app.on_event("startup")
async def startup_event():
    """应用启动时启动心跳检测"""
    await manager.start_heartbeat_check()

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时停止心跳检测"""
    await manager.stop_heartbeat_check()

@app.websocket("/api/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket聊天端点"""
    await manager.connect(websocket)
    try:
        while True:
            # 记录请求开始时间
            request_start_time = datetime.now()
            
            data = await websocket.receive_json()
            
            # 检查是否是 pong 消息
            message_type = data.get("type")
            if message_type == "pong":
                manager.update_pong(websocket)
                continue
            
            message = data.get("message")
            character_id = data.get("character_id", "default")
            
            logger.info(f"收到消息: {message[:50]}... (用户ID: 1, 角色: {character_id})")
            
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
            
            # 发送处理中状态(流式反馈)
            await manager.send_personal_message({
                "type": "status",
                "status": "processing",
                "message": "正在处理您的请求...",
                "timestamp": datetime.now().isoformat()
            }, websocket)

            # 转发到main.py处理
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"{MAIN_API_BASE}/api/chat",
                        json={"message": message, "user_id": 1, "agent_id": character_id},
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        reply = result.get("reply", "") or result.get("result", "")
                    else:
                        reply = f"服务暂时不可用 ({resp.status_code})"
            except httpx.ConnectError:
                reply = f"核心服务未启动，请确认 python main.py 已启动 (端口8001)"
            except Exception as e:
                logger.error("转发到main.py失败: %s", e)
                reply = f"处理失败: {str(e)[:100]}"
            
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
            
            # 计算响应时间
            response_time = (datetime.now() - request_start_time).total_seconds()
            logger.info(f"响应完成: {response_time:.2f}秒")
            
            # 发送回复（包含 message_id、thinking_process 和响应时间）
            await manager.send_personal_message({
                "type": "reply",
                "reply": reply,
                "character_id": character_id,
                "message_id": assistant_message["id"],
                "thinking_process": None,  # 后续可以添加思考过程
                "response_time": round(response_time, 2),
                "timestamp": datetime.now().isoformat()
            }, websocket)
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


@app.delete("/api/history")
async def clear_chat_history(user_id: int = 1, character_id: Optional[str] = None) -> Dict[str, Any]:
    """清空聊天历史
    
    Args:
        user_id: 用户ID
        character_id: 可选，指定角色ID，如果提供则只删除该角色的历史
    """
    global chat_history
    
    try:
        before_count = len(chat_history)
        
        if character_id:
            # 只删除指定角色的历史
            chat_history = [h for h in chat_history if h.get("character_id") != character_id or h.get("user_id") != user_id]
        else:
            # 删除该用户的所有历史
            chat_history = [h for h in chat_history if h.get("user_id") != user_id]
        
        deleted_count = before_count - len(chat_history)
        
        return {
            "success": True,
            "deleted": deleted_count,
            "message": f"已删除 {deleted_count} 条消息"
        }
    except Exception as e:
        logger.error("清空聊天历史失败: %s", e)
        return {"success": False, "error": str(e)}


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
    """处理聊天请求 - 转发到main.py
    
    支持智能匹配模式：当 agent_id='auto' 时，后端会自动选择最佳 Agent
    
    所有聊天逻辑由main.py统一处理，确保：
    - Agent系统正常工作
    - RAG知识库检索
    - BFS上下文记忆
    - MessageBus协作
    - 智能Agent自动选择（auto_agent_selection）
    """
    try:
        # 将 agent_id='auto' 转换为 'general'，并启用后端的智能选择
        # 后端 chat.py 会根据 auto_agent_selection 参数自动选择最佳Agent
        final_agent_id = request.agent_id if request.agent_id != 'auto' else 'general'
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 转发请求到main.py
            response = await client.post(
                f"{MAIN_API_BASE}/api/chat",
                json={
                    "message": request.message,
                    "user_id": request.user_id,
                    "agent_id": final_agent_id,
                    "agent_name": "小龙虾助手",
                    "auto_agent_selection": request.agent_id == 'auto'
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # 保存到本地历史记录（仅用于前端展示）
                user_message = {
                    "id": len(chat_history) + 1,
                    "user_id": request.user_id,
                    "character_id": request.agent_id,
                    "role": "user",
                    "content": request.message,
                    "created_at": datetime.now().isoformat()
                }
                chat_history.append(user_message)
                
                assistant_message = {
                    "id": len(chat_history) + 1,
                    "user_id": request.user_id,
                    "character_id": request.agent_id,
                    "role": "assistant",
                    "content": result.get("reply", ""),
                    "created_at": datetime.now().isoformat()
                }
                chat_history.append(assistant_message)
                
                return {
                    "success": True,
                    "message": request.message,
                    "reply": result.get("reply", ""),
                    "conversation_id": request.agent_id,
                    "message_id": assistant_message["id"],
                    "thinking_process": result.get("thinking_process"),
                    "skill": result.get("skill"),
                    "task_id": result.get("task_id")
                }
            else:
                logger.error(f"main.py返回错误: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"服务暂时不可用 ({response.status_code})"
                }
    except httpx.ConnectError as e:
        logger.error(f"无法连接到main.py ({MAIN_API_BASE}): {e}")
        return {
            "success": False,
            "error": f"核心服务未启动或无法访问 {MAIN_API_BASE}，请确认 python main.py 已启动"
        }
    except httpx.TimeoutException as e:
        logger.error(f"连接main.py超时: {e}")
        return {
            "success": False,
            "error": "核心服务响应超时，请稍后重试"
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"main.py返回HTTP错误: {e.response.status_code} - {e.response.text}")
        return {
            "success": False,
            "error": f"核心服务返回错误 ({e.response.status_code})，请检查服务日志"
        }
    except Exception as e:
        logger.error(f"转发聊天请求失败: {e}", exc_info=True)
        return {"success": False, "error": f"请求处理失败: {str(e)}"}


class EditMessageRequest(BaseModel):
    """编辑消息请求模型"""
    message_id: int
    content: str


class DeleteMessageRequest(BaseModel):
    """删除消息请求模型"""
    message_id: int


@app.put("/api/chat/edit")
async def edit_message(request: EditMessageRequest) -> Dict[str, Any]:
    """编辑消息内容"""
    try:
        # 查找消息
        message = next((m for m in chat_history if m.get("id") == request.message_id), None)
        if not message:
            return {"success": False, "detail": "消息不存在"}
        
        # 更新内容
        message["content"] = request.content
        message["updated_at"] = datetime.now().isoformat()
        
        return {"success": True, "message_id": request.message_id, "content": request.content}
    except Exception as e:
        logger.error("编辑消息失败: %s", e)
        return {"success": False, "error": str(e)}


@app.delete("/api/chat/delete")
async def delete_message(request: DeleteMessageRequest) -> Dict[str, Any]:
    """删除消息"""
    try:
        # 查找消息索引
        index = next((i for i, m in enumerate(chat_history) if m.get("id") == request.message_id), -1)
        if index == -1:
            return {"success": False, "detail": "消息不存在"}
        
        # 删除消息
        deleted_message = chat_history.pop(index)
        
        return {"success": True, "message_id": request.message_id, "deleted_content": deleted_message.get("content", "")}
    except Exception as e:
        logger.error("删除消息失败: %s", e)
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


@app.get("/api/agents")
async def get_agents_api():
    """获取所有配置的Agent列表"""
    try:
        import yaml
        agents_config_path = Path(__file__).parent / "config" / "agents.yml"
        
        if agents_config_path.exists():
            with open(agents_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            agents = []
            for agent_id, agent_info in config.get('agents', {}).items():
                # 根据Agent类型生成能力标签
                capabilities = []
                tools = agent_info.get('tools', [])
                
                # 根据工具推断能力
                for tool in tools:
                    if 'chat' in tool:
                        capabilities.append('聊天')
                    elif 'calculator' in tool or 'calculator-mcp' in tool:
                        capabilities.append('计算')
                    elif 'data' in tool or 'analysis' in tool:
                        capabilities.append('数据')
                    elif 'web' in tool or 'scraper' in tool:
                        capabilities.append('爬虫')
                    elif 'weather' in tool:
                        capabilities.append('天气')
                    elif 'system' in tool:
                        capabilities.append('系统')
                    elif 'translator' in tool or 'translate' in tool:
                        capabilities.append('翻译')
                    elif 'deep' in tool or 'thinking' in tool:
                        capabilities.append('思考')
                    elif 'fun' in tool or 'creative' in tool or 'art' in tool:
                        capabilities.append('创意')
                
                # 去重并限制数量
                capabilities = list(dict.fromkeys(capabilities))[:3]
                
                # 生成友好的显示名称
                display_names = {
                    'general': '👤 通用助手',
                    'data_analyst': '📊 数据分析师',
                    'web_scraper': '🌐 网络爬虫',
                    'weather_expert': '☀️ 天气预报员',
                    'system_toolbox': '🛠️ 系统工具',
                    'translator': '🌍 翻译官',
                    'deep_thinker': '🧠 深度思考者',
                    'creative': '🎨 创意助手'
                }
                
                agents.append({
                    'id': agent_id,
                    'name': display_names.get(agent_id, agent_id.replace('_', ' ').title()),
                    'description': agent_info.get('role_prompt', ''),
                    'capabilities': capabilities,
                    'priority': agent_info.get('priority', 1),
                    'tools': tools
                })
            
            return JSONResponse({
                'success': True,
                'data': agents
            })
        else:
            # 返回默认Agent列表
            default_agents = [
                {'id': 'general', 'name': '👤 通用助手', 'description': '擅长处理各种日常问题', 'capabilities': ['聊天', '计算', '娱乐']},
                {'id': 'data_analyst', 'name': '📊 数据分析师', 'description': '擅长数据处理、统计分析和可视化', 'capabilities': ['数据', '分析', '可视化']},
                {'id': 'web_scraper', 'name': '🌐 网络爬虫', 'description': '擅长从各平台抓取公开数据', 'capabilities': ['爬虫', '数据', '搜索']},
                {'id': 'weather_expert', 'name': '☀️ 天气预报员', 'description': '可以查询各城市的天气和预报', 'capabilities': ['天气', '预报', '查询']},
                {'id': 'system_toolbox', 'name': '🛠️ 系统工具', 'description': '可以执行系统命令、管理文件', 'capabilities': ['系统', '命令', '文件']},
                {'id': 'translator', 'name': '🌍 翻译官', 'description': '精通多语言互译', 'capabilities': ['翻译', '语言', '多语种']},
                {'id': 'deep_thinker', 'name': '🧠 深度思考者', 'description': '擅长复杂问题的多维度分析和推理', 'capabilities': ['思考', '分析', '推理']},
                {'id': 'creative', 'name': '🎨 创意助手', 'description': '擅长生成有趣内容、故事和艺术', 'capabilities': ['创意', '写作', '艺术']}
            ]
            return JSONResponse({
                'success': True,
                'data': default_agents
            })
    except Exception as e:
        logger.error(f"获取Agent列表失败: {e}")
        return JSONResponse({
            'success': False,
            'error': str(e)
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
        result = await task_processor.process(task)
        
        # 转换为字典格式（兼容原有 API）
        result_dict = {
            "path": result.path.value,
            "subtasks": [
                {
                    "id": subtask.id,
                    "action": subtask.action,
                    "params": subtask.params,
                    "dependencies": subtask.dependencies,
                    "priority": subtask.priority,
                }
                for subtask in result.subtasks
            ],
            "success": result.success,
        }
        
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


@app.get("/api/history/stats")
async def get_chat_history_stats(user_id: int = 1) -> Dict[str, Any]:
    """获取聊天历史统计信息"""
    try:
        # 从内存中计算统计信息
        user_messages = [h for h in chat_history if h.get("role") == "user" and h.get("user_id") == user_id]
        assistant_messages = [h for h in chat_history if h.get("role") == "assistant" and h.get("user_id") == user_id]
        
        # 计算各角色消息分布
        character_breakdown = {}
        for h in chat_history:
            if h.get("user_id") == user_id:
                char_id = h.get("character_id", "default")
                character_breakdown[char_id] = character_breakdown.get(char_id, 0) + 1
        
        # 计算每日趋势
        daily_breakdown = {}
        for h in chat_history:
            if h.get("user_id") == user_id:
                date_str = h.get("created_at", "").split("T")[0]
                if date_str:
                    daily_breakdown[date_str] = daily_breakdown.get(date_str, 0) + 1
        
        # 获取最早和最晚消息时间
        timestamps = [h.get("created_at") for h in chat_history if h.get("user_id") == user_id and h.get("created_at")]
        earliest_message = min(timestamps) if timestamps else None
        latest_message = max(timestamps) if timestamps else None
        
        return {
            "stats": {
                "total_messages": len(user_messages) + len(assistant_messages),
                "user_messages": len(user_messages),
                "assistant_messages": len(assistant_messages),
                "character_breakdown": character_breakdown,
                "daily_trend": daily_breakdown,
                "earliest_message": earliest_message,
                "latest_message": latest_message,
                "conversation_days": len(daily_breakdown)
            }
        }
    except Exception as e:
        logger.error("获取聊天历史统计失败: %s", e)
        return {"stats": {}}


# ==================== 补充缺失的 History API ====================
# 注意：具体路径必须在参数化路径之前定义，避免路由冲突

@app.get("/api/history/context")
async def get_intelligent_context(
    user_id: int = 1,
    query: Optional[str] = None,
    character_id: Optional[str] = None,
    max_tokens: int = 2000,
    prefer_liked: bool = True,
    include_recent: bool = True,
    max_messages: int = 10
) -> Dict[str, Any]:
    """智能检索获取上下文"""
    try:
        # 过滤历史记录
        filtered = chat_history
        
        if character_id:
            filtered = [h for h in filtered if h.get("character_id") == character_id]
        
        # 优先返回点赞的消息
        if prefer_liked:
            liked_messages = [h for h in filtered if h.get("is_liked", False)]
            other_messages = [h for h in filtered if not h.get("is_liked", False)]
            
            # 按权重排序
            liked_messages.sort(key=lambda x: x.get("weight", 1.0), reverse=True)
            other_messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            # 组合结果
            result = liked_messages[:max_messages // 2] + other_messages[:max_messages // 2]
        else:
            # 按时间倒序
            filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            result = filtered[:max_messages]
        
        return {
            "success": True,
            "context": result,
            "total": len(result)
        }
    except Exception as e:
        logger.error("智能检索失败: %s", e)
        return {"success": False, "error": str(e)}


@app.delete("/api/history/cleanup")
async def cleanup_expired_messages(user_id: int = 1, expire_days: int = 1) -> Dict[str, Any]:
    """清理过期消息（未点赞且超过指定天数）"""
    try:
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=expire_days)
        
        # 找出需要删除的消息
        to_delete = []
        for i, message in enumerate(chat_history):
            if message.get("user_id") != user_id:
                continue
            
            # 跳过点赞的消息
            if message.get("is_liked", False):
                continue
            
            # 检查是否过期
            created_at = datetime.fromisoformat(message.get("created_at", ""))
            if created_at < cutoff_date:
                to_delete.append(i)
        
        # 删除消息（从后往前删，避免索引变化）
        deleted_count = 0
        for i in reversed(to_delete):
            chat_history.pop(i)
            deleted_count += 1
        
        return {
            "success": True,
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error("清理过期消息失败: %s", e)
        return {"success": False, "error": str(e)}


@app.get("/api/history/{history_id}")
async def get_history_detail(history_id: int, user_id: int = 1) -> Dict[str, Any]:
    """获取单条历史记录详情"""
    try:
        message = next((m for m in chat_history if m.get("id") == history_id), None)
        if not message:
            return {"success": False, "detail": "历史记录不存在"}
        
        return {
            "success": True,
            "message": message
        }
    except Exception as e:
        logger.error("获取历史详情失败: %s", e)
        return {"success": False, "error": str(e)}


@app.put("/api/history/{history_id}")
async def update_history(history_id: int, request: EditMessageRequest, user_id: int = 1) -> Dict[str, Any]:
    """更新历史记录"""
    try:
        message = next((m for m in chat_history if m.get("id") == history_id), None)
        if not message:
            return {"success": False, "detail": "历史记录不存在"}
        
        message["content"] = request.content
        message["updated_at"] = datetime.now().isoformat()
        
        return {"success": True, "message_id": history_id, "content": request.content}
    except Exception as e:
        logger.error("更新历史失败: %s", e)
        return {"success": False, "error": str(e)}


@app.delete("/api/history/{history_id}")
async def delete_history(history_id: int, user_id: int = 1) -> Dict[str, Any]:
    """删除单条历史记录"""
    try:
        index = next((i for i, m in enumerate(chat_history) if m.get("id") == history_id), -1)
        if index == -1:
            return {"success": False, "detail": "历史记录不存在"}
        
        deleted_message = chat_history.pop(index)
        
        return {
            "success": True,
            "message_id": history_id,
            "deleted_content": deleted_message.get("content", "")
        }
    except Exception as e:
        logger.error("删除历史失败: %s", e)
        return {"success": False, "error": str(e)}


@app.post("/api/history/{history_id}/like")
async def toggle_like(history_id: int, user_id: int = 1) -> Dict[str, Any]:
    """点赞/取消点赞消息"""
    try:
        message = next((m for m in chat_history if m.get("id") == history_id), None)
        if not message:
            return {"success": False, "detail": "消息不存在"}
        
        # 切换点赞状态
        is_liked = not message.get("is_liked", False)
        message["is_liked"] = is_liked
        
        return {
            "success": True,
            "message_id": history_id,
            "is_liked": is_liked
        }
    except Exception as e:
        logger.error("点赞操作失败: %s", e)
        return {"success": False, "error": str(e)}


@app.post("/api/history/{history_id}/weight")
async def set_message_weight(history_id: int, weight: float = 1.0, user_id: int = 1) -> Dict[str, Any]:
    """设置消息权重"""
    try:
        message = next((m for m in chat_history if m.get("id") == history_id), None)
        if not message:
            return {"success": False, "detail": "消息不存在"}
        
        message["weight"] = weight
        
        return {
            "success": True,
            "message_id": history_id,
            "weight": weight
        }
    except Exception as e:
        logger.error("设置权重失败: %s", e)
        return {"success": False, "error": str(e)}


# ==================== 文件上传 API ====================

from fastapi import UploadFile, File
import shutil

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """上传文件"""
    try:
        # 验证文件大小（最大10MB）
        MAX_FILE_SIZE = 10 * 1024 * 1024
        
        # 创建上传目录
        upload_dir = Path(__file__).parent / "uploads"
        upload_dir.mkdir(exist_ok=True)
        
        # 生成唯一文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        file_path = upload_dir / filename
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 检查文件大小
        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            file_path.unlink()  # 删除超限文件
            raise HTTPException(status_code=413, detail=f"文件大小超过限制（最大10MB）")
        
        return {
            "success": True,
            "filename": filename,
            "file_path": str(file_path),
            "file_size": file_size,
            "original_filename": file.filename
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("文件上传失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    # 启动服务器（注意：此端口需与 main.py (8001) 和 start_web.py (8000) 区分）
    logger.info("启动FastAPI服务器...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
