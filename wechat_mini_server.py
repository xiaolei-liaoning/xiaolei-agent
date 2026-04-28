"""微信小程序后端API服务"""
import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from pydantic import BaseModel
import uvicorn

from skills.third_party.handler import app_manager
from core.multi_agent_system import agent_scheduler
from core.monitoring import monitoring_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/wechat_mini_server.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 导入GUI自动化处理器
try:
    from skills.gui_automation.handler import GUIAutomationHandler
    gui_handler = GUIAutomationHandler()
    logger.info("GUI自动化处理器初始化成功")
except Exception as e:
    logger.error(f"GUI自动化处理器初始化失败: {e}")
    gui_handler = None

app = FastAPI()

# 任务发布请求模型
class TaskRequest(BaseModel):
    task_type: str
    params: dict
    priority: int = 5

# 聊天请求模型
class ChatRequest(BaseModel):
    message: str
    user_id: str

# WebSocket连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"WebSocket发送失败: {e}")
                self.disconnect(connection)

manager = ConnectionManager()

# 定时推送监控数据
async def push_monitoring_data():
    while True:
        try:
            # 获取监控数据
            monitor_data = monitoring_manager.get_metrics()
            # 广播监控数据
            await manager.broadcast({
                'type': 'monitoring',
                'data': monitor_data
            })
        except Exception as e:
            logger.error(f"推送监控数据失败: {e}")
        await asyncio.sleep(5)  # 每5秒推送一次

@app.on_event("startup")
async def startup_event():
    # 启动监控数据推送任务
    asyncio.create_task(push_monitoring_data())
    # 启动Agent调度中心
    try:
        await agent_scheduler.start()
        logger.info("Agent调度中心启动成功")
    except Exception as e:
        logger.error(f"Agent调度中心启动失败: {e}")

@app.post("/api/wechat/task")
async def create_task(task: TaskRequest):
    """发布任务"""
    try:
        # 尝试提交任务到Agent系统
        try:
            result = await agent_scheduler.submit_task(
                task_type=task.task_type,
                params=task.params
            )
            if result.get('success'):
                task_id = result.get('data', {}).get('task_id')
                return {
                    'success': True,
                    'task_id': task_id
                }
            else:
                error = result.get('error', '发布任务失败')
                return {
                    'success': False,
                    'error': error
                }
        except Exception as e:
            logger.error(f"发布任务失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    except Exception as e:
        logger.error(f"处理任务发布请求失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.get("/api/wechat/task/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    try:
        # 尝试获取任务状态
        try:
            status = await agent_scheduler.get_task_status(task_id)
            if status:
                return {
                    'success': True,
                    'status': status
                }
            else:
                return {
                    'success': False,
                    'error': '任务不存在'
                }
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    except Exception as e:
        logger.error(f"处理任务状态请求失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.get("/api/wechat/tasks")
async def get_tasks():
    """获取任务列表"""
    try:
        # 尝试获取任务列表
        try:
            tasks = await agent_scheduler.get_tasks()
        except Exception as e:
            # 如果获取任务失败，返回空列表
            logger.error(f"获取任务列表失败: {e}")
            tasks = []
        
        return {
            'success': True,
            'tasks': tasks
        }
    except Exception as e:
        logger.error(f"处理任务列表请求失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.post("/api/wechat/chat")
async def send_chat(chat: ChatRequest):
    """发送聊天消息"""
    try:
        # 尝试处理聊天消息
        try:
            result = await agent_scheduler.submit_task(
                task_type='chat',
                params={
                    'message': chat.message,
                    'user_id': chat.user_id
                }
            )
            if result.get('success'):
                task_id = result.get('data', {}).get('task_id')
                return {
                    'success': True,
                    'task_id': task_id
                }
            else:
                error = result.get('error', '发送聊天消息失败')
                return {
                    'success': False,
                    'error': error
                }
        except Exception as e:
            logger.error(f"发送聊天消息失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    except Exception as e:
        logger.error(f"处理聊天消息请求失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@app.post("/api/wechat/agent/connect")
async def connect_agent(request: Request):
    """连接Agent"""
    try:
        # 从请求体获取参数
        data = await request.json()
        user_id = data.get('user_id', '1')
        agent_id = data.get('agent_id', 'default')
        
        # 尝试连接到Agent
        try:
            # 这里可以添加连接Agent的逻辑
            return {
                'success': True,
                'message': 'Agent连接成功',
                'agent_id': agent_id,
                'user_id': user_id
            }
        except Exception as e:
            logger.error(f"Agent连接失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    except Exception as e:
        logger.error(f"处理Agent连接请求失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.get("/api/wechat/agent/status")
async def get_agent_status():
    """获取Agent状态"""
    try:
        # 检查Agent调度中心状态
        agent_info = agent_scheduler.get_agent_info()
        
        # 检查是否所有Agent都在运行
        all_agents_running = all(agent.get('running', False) for agent in agent_info.values())
        
        return {
            'success': True,
            'status': 'connected' if all_agents_running else 'disconnected',
            'agents': agent_info,
            'message': 'Agent连接成功' if all_agents_running else '部分Agent未运行'
        }
    except Exception as e:
        logger.error(f"获取Agent状态失败: {e}")
        return {
            'success': False,
            'status': 'disconnected',
            'error': str(e)
        }


def _identify_task_type(message: str) -> str:
    """智能识别任务类型
    
    Args:
        message: 用户消息
        
    Returns:
        任务类型
    """
    # 任务类型识别规则
    task_patterns = {
        "search": ["搜索", "查找", "查询", "找一下"],
        "analyze": ["分析", "研究", "评估"],
        "summarize": ["总结", "概括", "归纳"],
        "compare": ["比较", "对比", "vs", " versus "],
        "scan": ["扫描", "检测", "检查"],
        "scrape": ["爬取", "抓取", "获取"],
        "translate": ["翻译", "转换语言"],
        "sentiment": ["情感分析", "情绪分析"],
        "ner": ["命名实体识别", "实体识别"],
        "chat": ["聊天", "对话", "交流", "研究", "了解", "学习", "探索"]
    }
    
    # 识别任务类型
    for task_type, patterns in task_patterns.items():
        for pattern in patterns:
            if pattern in message:
                return task_type
    
    # 默认返回chat
    return "chat"

@app.post("/api/wechat/agent/message")
async def send_agent_message(request: Request):
    """发送消息到Agent"""
    try:
        # 从请求体获取参数
        data = await request.json()
        message = data.get('message', '')
        user_id = data.get('user_id', '1')
        agent_id = data.get('agent_id', 'default')
        
        if not message:
            return {
                'success': False,
                'error': '消息不能为空'
            }
        
        # 尝试处理消息
        try:
            logger.info(f"开始处理消息: {message[:50]}... (用户: {user_id}, Agent: {agent_id})")
            
            # 直接通过WebSocket推送消息已接收的通知
            try:
                await manager.broadcast({
                    'type': 'message_received',
                    'message': message,
                    'user_id': user_id,
                    'agent_id': agent_id
                })
                logger.info(f"消息已接收通知已通过WebSocket推送")
            except Exception as e:
                logger.error(f"WebSocket推送失败: {e}")
            
            # 检查是否是操作指令
            operation_result = None
            if gui_handler:
                # 识别打开应用程序的指令
                if message.startswith('打开'):
                    app_name = message[2:].strip()
                    logger.info(f"识别到打开应用指令: {app_name}")
                    try:
                        operation_result = gui_handler.execute(action='open_app', app=app_name)
                        logger.info(f"GUI操作结果: {operation_result}")
                    except Exception as e:
                        logger.error(f"GUI操作失败: {e}")
                # 识别关闭应用程序的指令
                elif message.startswith('关闭') or message.startswith('退出'):
                    app_name = message[2:].strip()
                    logger.info(f"识别到关闭应用指令: {app_name}")
                    try:
                        operation_result = gui_handler.execute(action='quit_app', app=app_name)
                        logger.info(f"GUI操作结果: {operation_result}")
                    except Exception as e:
                        logger.error(f"GUI操作失败: {e}")
                # 识别打开URL的指令
                elif message.startswith('访问') or message.startswith('打开网页'):
                    url = message[2:].strip()
                    if not url.startswith('http'):
                        url = 'https://' + url
                    logger.info(f"识别到打开URL指令: {url}")
                    try:
                        operation_result = gui_handler.execute(action='open_url', url=url)
                        logger.info(f"GUI操作结果: {operation_result}")
                    except Exception as e:
                        logger.error(f"GUI操作失败: {e}")
                # 识别其他GUI操作指令
                elif message.startswith('通知'):
                    content = message[2:].strip()
                    logger.info(f"识别到通知指令: {content}")
                    try:
                        operation_result = gui_handler.execute(action='notification', title='通知', subtitle='', message=content)
                        logger.info(f"GUI操作结果: {operation_result}")
                    except Exception as e:
                        logger.error(f"GUI操作失败: {e}")
                elif message.startswith('输入'):
                    text = message[2:].strip()
                    logger.info(f"识别到输入文本指令: {text}")
                    try:
                        operation_result = gui_handler.execute(action='type_text', text=text)
                        logger.info(f"GUI操作结果: {operation_result}")
                    except Exception as e:
                        logger.error(f"GUI操作失败: {e}")
                elif message.startswith('截图'):
                    logger.info(f"识别到截图指令")
                    try:
                        operation_result = gui_handler.execute(action='screenshot')
                        logger.info(f"GUI操作结果: {operation_result}")
                    except Exception as e:
                        logger.error(f"GUI操作失败: {e}")
            
            if operation_result and operation_result.get('success'):
                # 操作执行成功，通过WebSocket推送结果
                try:
                    reply = operation_result.get('reply', f'已执行操作: {message}')
                    logger.info(f"准备推送操作结果: {reply}")
                    await manager.broadcast({
                        'type': 'message',
                        'task_id': 'operation_' + str(int(asyncio.get_event_loop().time() * 1000)),
                        'message': message,
                        'reply': reply,
                        'user_id': user_id,
                        'agent_id': agent_id
                    })
                    logger.info(f"操作结果已通过WebSocket推送")
                except Exception as e:
                    logger.error(f"WebSocket推送失败: {e}")
                
                return {
                    'success': True,
                    'message': message,
                    'result': operation_result
                }
            else:
                # 不是操作指令，提交任务到Agent系统
                logger.info(f"准备提交任务到Agent系统: {message[:50]}...")
                
                # 智能识别任务类型
                task_type = _identify_task_type(message)
                logger.info(f"任务类型: {task_type}, 用户ID: {user_id}, Agent ID: {agent_id}")
                
                # 检查Agent调度中心状态
                try:
                    agent_info = agent_scheduler.get_agent_info()
                    logger.info(f"Agent状态: {agent_info}")
                except Exception as e:
                    logger.error(f"获取Agent状态失败: {e}")
                
                # 尝试提交任务
                try:
                    result = await agent_scheduler.submit_task(
                        task_type=task_type,
                        params={
                            'message': message,
                            'user_id': user_id,
                            'agent_id': agent_id
                        }
                    )
                    logger.info(f"任务提交结果: {result}")
                except Exception as e:
                    logger.error(f"提交任务失败: {e}")
                    return {
                        'success': False,
                        'error': f"提交任务失败: {e}"
                    }
                
                if result.get('success'):
                    task_id = result.get('data', {}).get('task_id')
                    logger.info(f"任务提交成功，任务ID: {task_id}")
                    
                    # 等待任务完成并获取结果
                    import asyncio
                    max_retries = 5
                    retry_count = 0
                    task_status = None
                    
                    while retry_count < max_retries:
                        await asyncio.sleep(1)  # 等待1秒
                        
                        # 获取任务状态
                        task_status = await agent_scheduler.get_task_status(task_id)
                        logger.info(f"获取任务状态: {task_status}")
                        
                        if task_status:
                            logger.info(f"任务状态: {task_status.get('status')}, 结果: {task_status.get('result')}")
                            if task_status.get('result'):
                                logger.info(f"任务处理完成，获取到结果: {task_status.get('result')}")
                                break
                        else:
                            logger.warning(f"任务状态获取失败: {task_id}")
                        
                        retry_count += 1
                        logger.info(f"任务处理中，重试 {retry_count}/{max_retries}")
                        if retry_count < max_retries:
                            await asyncio.sleep(1)  # 每次重试间隔1秒
                    
                    if task_status and task_status.get('result'):
                        # 通过WebSocket推送任务结果
                        try:
                            reply = task_status.get('result', {}).get('reply', '处理完成')
                            logger.info(f"准备推送回复: {reply}")
                            await manager.broadcast({
                                'type': 'message',
                                'task_id': task_id,
                                'message': message,
                                'reply': reply,
                                'user_id': user_id,
                                'agent_id': agent_id
                            })
                            logger.info(f"消息回复已通过WebSocket推送")
                        except Exception as e:
                            logger.error(f"WebSocket推送失败: {e}")
                    else:
                        logger.warning(f"任务处理超时，未能获取到结果")
                        # 即使超时也推送一个默认回复
                        try:
                            await manager.broadcast({
                                'type': 'message',
                                'task_id': task_id,
                                'message': message,
                                'reply': '处理完成',
                                'user_id': user_id,
                                'agent_id': agent_id
                            })
                            logger.info(f"默认回复已通过WebSocket推送")
                        except Exception as e:
                            logger.error(f"WebSocket推送失败: {e}")
                    
                    return {
                        'success': True,
                        'task_id': task_id,
                        'message': message
                    }
                else:
                    error = result.get('error', '发送消息失败')
                    logger.error(f"任务提交失败: {error}")
                    return {
                        'success': False,
                        'error': error
                    }
        except Exception as e:
            logger.error(f"发送消息到Agent失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    except Exception as e:
        logger.error(f"处理Agent消息请求失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.get("/api/wechat/monitor")
async def get_monitoring_data():
    """获取监控数据"""
    try:
        # 尝试获取监控数据
        try:
            data = monitoring_manager.get_metrics()
            return {
                'success': True,
                'data': data
            }
        except Exception as e:
            logger.error(f"获取监控数据失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    except Exception as e:
        logger.error(f"处理监控数据请求失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.websocket("/ws/wechat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点"""
    await manager.connect(websocket)
    try:
        while True:
            # 接收消息
            data = await websocket.receive_json()
            # 处理消息
            if data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong'})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)