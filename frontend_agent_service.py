#!/usr/bin/env python
"""前端Agent服务

提供前端Agent系统的后端支持，包括：
1. 前端Agent的注册和管理
2. 任务提交和处理
3. Agent状态监控
4. 与前端的WebSocket通信
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from core.frontend_agent_system import frontend_agent_system, agent_monitor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="前端Agent服务", version="1.0.0")

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic模型
class AgentRegisterRequest(BaseModel):
    """Agent注册请求模型"""
    agent_id: str
    name: str
    avatar: str
    max_workers: int = 5


class TaskSubmitRequest(BaseModel):
    """任务提交请求模型"""
    agent_id: str
    task_type: str
    params: Dict[str, Any]


class TaskStatusRequest(BaseModel):
    """任务状态查询请求模型"""
    agent_id: str
    task_id: str


# API端点
@app.post("/api/agents/register", summary="注册前端Agent")
async def register_agent(request: AgentRegisterRequest) -> Dict[str, Any]:
    """注册前端Agent"""
    try:
        from core.frontend_agent_system import FrontendAgent
        agent = FrontendAgent(
            agent_id=request.agent_id,
            name=request.name,
            avatar=request.avatar,
            max_workers=request.max_workers
        )
        frontend_agent_system.register_agent(agent)
        return {
            "success": True,
            "agent_id": request.agent_id,
            "name": request.name
        }
    except Exception as e:
        logger.error("注册Agent失败: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/agents/unregister", summary="注销前端Agent")
async def unregister_agent(agent_id: str) -> Dict[str, Any]:
    """注销前端Agent"""
    try:
        frontend_agent_system.unregister_agent(agent_id)
        return {
            "success": True,
            "agent_id": agent_id
        }
    except Exception as e:
        logger.error("注销Agent失败: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/agents/list", summary="获取所有Agent列表")
async def list_agents() -> Dict[str, Any]:
    """获取所有Agent列表"""
    try:
        agents_info = frontend_agent_system.get_all_agents_info()
        return {
            "success": True,
            "agents": agents_info
        }
    except Exception as e:
        logger.error("获取Agent列表失败: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/agents/{agent_id}", summary="获取Agent信息")
async def get_agent_info(agent_id: str) -> Dict[str, Any]:
    """获取Agent信息"""
    try:
        agent_info = frontend_agent_system.get_agent_info(agent_id)
        if "error" in agent_info:
            return {
                "success": False,
                "error": agent_info["error"]
            }
        return {
            "success": True,
            "agent": agent_info
        }
    except Exception as e:
        logger.error("获取Agent信息失败: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/tasks/submit", summary="提交任务")
async def submit_task(request: TaskSubmitRequest) -> Dict[str, Any]:
    """提交任务"""
    try:
        task_id = frontend_agent_system.submit_task(
            agent_id=request.agent_id,
            task_type=request.task_type,
            params=request.params
        )
        
        # 异步处理任务
        asyncio.create_task(
            frontend_agent_system.process_task(request.agent_id, task_id)
        )
        
        return {
            "success": True,
            "task_id": task_id,
            "agent_id": request.agent_id
        }
    except Exception as e:
        logger.error("提交任务失败: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/tasks/status", summary="查询任务状态")
async def get_task_status(request: TaskStatusRequest) -> Dict[str, Any]:
    """查询任务状态"""
    try:
        tasks = frontend_agent_system.get_agent_tasks(request.agent_id)
        task = next((t for t in tasks if t["id"] == request.task_id), None)
        if not task:
            return {
                "success": False,
                "error": "任务不存在"
            }
        return {
            "success": True,
            "task": task
        }
    except Exception as e:
        logger.error("查询任务状态失败: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/tasks/{agent_id}", summary="获取Agent的任务列表")
async def get_agent_tasks(agent_id: str) -> Dict[str, Any]:
    """获取Agent的任务列表"""
    try:
        tasks = frontend_agent_system.get_agent_tasks(agent_id)
        return {
            "success": True,
            "tasks": tasks
        }
    except Exception as e:
        logger.error("获取任务列表失败: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/monitor/agents", summary="监控所有Agent状态")
async def monitor_agents() -> Dict[str, Any]:
    """监控所有Agent状态"""
    try:
        agent_monitor.monitor_system()
        agents_status = agent_monitor.get_all_agents_status()
        return {
            "success": True,
            "agents": agents_status
        }
    except Exception as e:
        logger.error("监控Agent状态失败: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/monitor/tasks", summary="监控所有任务")
async def monitor_tasks() -> Dict[str, Any]:
    """监控所有任务"""
    try:
        all_tasks = agent_monitor.get_all_tasks()
        return {
            "success": True,
            "tasks": all_tasks
        }
    except Exception as e:
        logger.error("监控任务失败: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


# WebSocket端点
@app.websocket("/ws/agent")
async def websocket_agent(websocket: WebSocket) -> None:
    """WebSocket实时通信端点"""
    await websocket.accept()
    client_id: str = f"ws_{id(websocket)}"
    logger.info("WebSocket客户端已连接: %s", client_id)

    # 启动状态推送任务
    status_task = asyncio.create_task(push_status_updates(websocket))

    try:
        while True:
            # 接收消息
            data: str = await websocket.receive_text()
            
            # 解析请求
            try:
                request: Dict[str, Any] = json.loads(data)
                action: str = request.get("action", "")
            except (json.JSONDecodeError, TypeError):
                await websocket.send_json({
                    "success": False,
                    "error": "无效的请求格式"
                })
                continue

            # 处理不同的操作
            if action == "register_agent":
                # 注册Agent
                try:
                    agent_id = request.get("agent_id")
                    name = request.get("name")
                    avatar = request.get("avatar")
                    max_workers = request.get("max_workers", 5)
                    
                    from core.frontend_agent_system import FrontendAgent
                    agent = FrontendAgent(
                        agent_id=agent_id,
                        name=name,
                        avatar=avatar,
                        max_workers=max_workers
                    )
                    frontend_agent_system.register_agent(agent)
                    
                    await websocket.send_json({
                        "success": True,
                        "action": "register_agent",
                        "agent_id": agent_id,
                        "name": name
                    })
                except Exception as e:
                    await websocket.send_json({
                        "success": False,
                        "action": "register_agent",
                        "error": str(e)
                    })
            
            elif action == "submit_task":
                # 提交任务
                try:
                    agent_id = request.get("agent_id")
                    task_type = request.get("task_type")
                    params = request.get("params", {})
                    
                    task_id = frontend_agent_system.submit_task(
                        agent_id=agent_id,
                        task_type=task_type,
                        params=params
                    )
                    
                    # 异步处理任务
                    asyncio.create_task(
                        frontend_agent_system.process_task(agent_id, task_id)
                    )
                    
                    await websocket.send_json({
                        "success": True,
                        "action": "submit_task",
                        "task_id": task_id,
                        "agent_id": agent_id
                    })
                except Exception as e:
                    await websocket.send_json({
                        "success": False,
                        "action": "submit_task",
                        "error": str(e)
                    })
            
            elif action == "get_agent_status":
                # 获取Agent状态
                try:
                    agent_id = request.get("agent_id")
                    agent_info = frontend_agent_system.get_agent_info(agent_id)
                    
                    await websocket.send_json({
                        "success": True,
                        "action": "get_agent_status",
                        "agent": agent_info
                    })
                except Exception as e:
                    await websocket.send_json({
                        "success": False,
                        "action": "get_agent_status",
                        "error": str(e)
                    })
            
            elif action == "get_task_status":
                # 获取任务状态
                try:
                    agent_id = request.get("agent_id")
                    task_id = request.get("task_id")
                    
                    tasks = frontend_agent_system.get_agent_tasks(agent_id)
                    task = next((t for t in tasks if t["id"] == task_id), None)
                    
                    await websocket.send_json({
                        "success": True,
                        "action": "get_task_status",
                        "task": task
                    })
                except Exception as e:
                    await websocket.send_json({
                        "success": False,
                        "action": "get_task_status",
                        "error": str(e)
                    })
            
            elif action == "get_monitoring_data":
                # 获取监控数据
                try:
                    from core.monitoring import monitoring_manager
                    summary = monitoring_manager.get_summary()
                    
                    await websocket.send_json({
                        "success": True,
                        "action": "get_monitoring_data",
                        "data": summary
                    })
                except Exception as e:
                    await websocket.send_json({
                        "success": False,
                        "action": "get_monitoring_data",
                        "error": str(e)
                    })
            
            else:
                await websocket.send_json({
                    "success": False,
                    "error": "未知的操作"
                })

    except WebSocketDisconnect:
        logger.info("WebSocket客户端断开: %s", client_id)
    except Exception as e:
        logger.error("WebSocket连接异常: %s", e)
    finally:
        status_task.cancel()
        logger.info("WebSocket连接清理完成: %s", client_id)


async def push_status_updates(websocket: WebSocket):
    """推送实时状态更新"""
    try:
        while True:
            # 获取系统状态
            from core.monitoring import monitoring_manager
            summary = monitoring_manager.get_summary()
            
            # 获取Agent状态
            agents_info = frontend_agent_system.get_all_agents_info()
            
            # 推送状态更新
            await websocket.send_json({
                "type": "status_update",
                "system": summary,
                "agents": agents_info,
                "timestamp": time.time()
            })
            
            # 每5秒推送一次
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("推送状态更新失败: %s", e)


# 健康检查
@app.get("/health", summary="健康检查")
async def health_check() -> Dict[str, Any]:
    """健康检查"""
    return {
        "status": "ok",
        "service": "frontend_agent_service"
    }


if __name__ == "__main__":
    import uvicorn
    
    port: int = int(os.getenv("FRONTEND_AGENT_PORT", "8003"))
    host: str = os.getenv("FRONTEND_AGENT_HOST", "0.0.0.0")
    log_level: str = os.getenv("LOG_LEVEL", "info")
    
    logger.info("启动前端Agent服务，地址: %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level=log_level)