"""
FastAPI接口层 - 提供RESTful API接口

包含：
1. 任务管理接口
2. Agent管理接口
3. 监控接口
4. 健康检查接口
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks
    from pydantic import BaseModel
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
except ImportError:
    raise ImportError("请安装fastapi和pydantic")

logger = logging.getLogger(__name__)


class TaskCreateRequest(BaseModel):
    """任务创建请求"""
    goal: str
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    priority: int = 1
    timeout: Optional[int] = None


class TaskResponse(BaseModel):
    """任务响应"""
    task_id: str
    status: str
    goal: str
    progress: float = 0.0
    created_at: float
    updated_at: float
    result: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    """Agent响应"""
    agent_id: str
    agent_type: str
    name: Optional[str]
    state: str
    load: float
    capabilities: List[str]


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    timestamp: float
    components: Dict[str, str]


class MetricsResponse(BaseModel):
    """指标响应"""
    timestamp: float
    agent_metrics: Dict[str, Any]
    system_metrics: Dict[str, Any]


class MultiAgentAPI:
    """多Agent系统API"""

    def __init__(self, orchestrator: Optional[Any] = None):
        self.app = FastAPI(
            title="多Agent系统API",
            description="多Agent协作引擎的RESTful API",
            version="1.0.0"
        )

        self.orchestrator = orchestrator

        # 配置CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 注册路由
        self._register_routes()

    def _register_routes(self) -> None:
        """注册API路由"""

        @self.app.get("/health", response_model=HealthResponse)
        async def health_check():
            """健康检查"""
            components = {
                "api": "healthy",
                "orchestrator": "healthy" if self.orchestrator else "not_available",
                "storage": "healthy"  # 这里应该检查实际存储状态
            }

            return HealthResponse(
                status="healthy",
                timestamp=asyncio.get_event_loop().time(),
                components=components
            )

        @self.app.post("/tasks", response_model=TaskResponse)
        async def create_task(request: TaskCreateRequest, background_tasks: BackgroundTasks):
            """创建任务"""
            if not self.orchestrator:
                raise HTTPException(status_code=500, detail="Orchestrator not available")

            try:
                # 创建任务
                task_id = await self.orchestrator.create_task(
                    goal=request.goal,
                    description=request.description or "",
                    keywords=request.keywords or [],
                    priority=request.priority,
                    timeout=request.timeout
                )

                # 获取任务状态
                task = await self.orchestrator.get_task(task_id)

                return TaskResponse(
                    task_id=task_id,
                    status=task.get("status", "pending"),
                    goal=request.goal,
                    progress=0.0,
                    created_at=task.get("created_at", asyncio.get_event_loop().time()),
                    updated_at=asyncio.get_event_loop().time()
                )

            except Exception as e:
                logger.error(f"创建任务失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/tasks/{task_id}", response_model=TaskResponse)
        async def get_task(task_id: str):
            """获取任务状态"""
            if not self.orchestrator:
                raise HTTPException(status_code=500, detail="Orchestrator not available")

            try:
                task = await self.orchestrator.get_task(task_id)

                if not task:
                    raise HTTPException(status_code=404, detail="任务不存在")

                return TaskResponse(
                    task_id=task_id,
                    status=task.get("status", "unknown"),
                    goal=task.get("goal", ""),
                    progress=task.get("progress", 0.0),
                    created_at=task.get("created_at", 0.0),
                    updated_at=task.get("updated_at", 0.0),
                    result=task.get("result")
                )

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"获取任务失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/tasks", response_model=List[TaskResponse])
        async def list_tasks(status: Optional[str] = None):
            """列出任务"""
            if not self.orchestrator:
                raise HTTPException(status_code=500, detail="Orchestrator not available")

            try:
                tasks = await self.orchestrator.list_tasks(status)

                return [
                    TaskResponse(
                        task_id=t.get("task_id", ""),
                        status=t.get("status", "unknown"),
                        goal=t.get("goal", ""),
                        progress=t.get("progress", 0.0),
                        created_at=t.get("created_at", 0.0),
                        updated_at=t.get("updated_at", 0.0)
                    )
                    for t in tasks
                ]

            except Exception as e:
                logger.error(f"列出任务失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete("/tasks/{task_id}")
        async def cancel_task(task_id: str):
            """取消任务"""
            if not self.orchestrator:
                raise HTTPException(status_code=500, detail="Orchestrator not available")

            try:
                success = await self.orchestrator.cancel_task(task_id)

                if not success:
                    raise HTTPException(status_code=404, detail="任务不存在或无法取消")

                return {"message": "任务已取消", "task_id": task_id}

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"取消任务失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/agents", response_model=List[AgentResponse])
        async def list_agents(state: Optional[str] = None):
            """列出Agent"""
            if not self.orchestrator:
                raise HTTPException(status_code=500, detail="Orchestrator not available")

            try:
                agents = await self.orchestrator.list_agents(state)

                return [
                    AgentResponse(
                        agent_id=a.get("agent_id", ""),
                        agent_type=a.get("agent_type", ""),
                        name=a.get("name"),
                        state=a.get("state", "unknown"),
                        load=a.get("load", 0.0),
                        capabilities=a.get("capabilities", [])
                    )
                    for a in agents
                ]

            except Exception as e:
                logger.error(f"列出Agent失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/agents/{agent_id}", response_model=AgentResponse)
        async def get_agent(agent_id: str):
            """获取Agent详情"""
            if not self.orchestrator:
                raise HTTPException(status_code=500, detail="Orchestrator not available")

            try:
                agent = await self.orchestrator.get_agent(agent_id)

                if not agent:
                    raise HTTPException(status_code=404, detail="Agent不存在")

                return AgentResponse(
                    agent_id=agent.get("agent_id", ""),
                    agent_type=agent.get("agent_type", ""),
                    name=agent.get("name"),
                    state=agent.get("state", "unknown"),
                    load=agent.get("load", 0.0),
                    capabilities=agent.get("capabilities", [])
                )

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"获取Agent失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/agents/{agent_id}/stop")
        async def stop_agent(agent_id: str):
            """停止Agent"""
            if not self.orchestrator:
                raise HTTPException(status_code=500, detail="Orchestrator not available")

            try:
                success = await self.orchestrator.stop_agent(agent_id)

                if not success:
                    raise HTTPException(status_code=404, detail="Agent不存在")

                return {"message": "Agent已停止", "agent_id": agent_id}

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"停止Agent失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/metrics", response_model=MetricsResponse)
        async def get_metrics():
            """获取系统指标"""
            if not self.orchestrator:
                raise HTTPException(status_code=500, detail="Orchestrator not available")

            try:
                metrics = await self.orchestrator.get_metrics()

                return MetricsResponse(
                    timestamp=asyncio.get_event_loop().time(),
                    agent_metrics=metrics.get("agent_metrics", {}),
                    system_metrics=metrics.get("system_metrics", {})
                )

            except Exception as e:
                logger.error(f"获取指标失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/execute")
        async def execute_task(request: TaskCreateRequest):
            """执行任务（同步模式）"""
            if not self.orchestrator:
                raise HTTPException(status_code=500, detail="Orchestrator not available")

            try:
                result = await self.orchestrator.execute_task(
                    goal=request.goal,
                    description=request.description or "",
                    keywords=request.keywords or []
                )

                return JSONResponse(content=result, status_code=200)

            except Exception as e:
                logger.error(f"执行任务失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """启动API服务"""
        try:
            import uvicorn
            logger.info(f"启动API服务: {host}:{port}")
            uvicorn.run(self.app, host=host, port=port)
        except ImportError:
            logger.error("请安装uvicorn")
            raise

    async def shutdown(self):
        """关闭API服务"""
        logger.info("关闭API服务")
