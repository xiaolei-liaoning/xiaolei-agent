"""监控API接口"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import psutil
from core.multi_agent_system import agent_scheduler

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("/agents")
async def get_agents():
    """获取所有Agent的信息和状态"""
    try:
        agent_info = agent_scheduler.get_agent_info()
        return {"agents": agent_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_type}/tasks")
async def get_agent_tasks(agent_type: str):
    """获取指定Agent的任务列表"""
    try:
        tasks = agent_scheduler.get_agent_tasks(agent_type)
        return {"tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks")
async def get_all_tasks():
    """获取所有Agent的任务列表"""
    try:
        all_tasks = agent_scheduler.get_all_tasks()
        return {"tasks": all_tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/status")
async def get_system_status():
    """获取系统状态和性能指标"""
    try:
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        network = psutil.net_io_counters()
        
        return {
            "cpu_percent": cpu_percent,
            "memory": {
                "percent": memory.percent,
                "used": memory.used,
                "total": memory.total
            },
            "disk": {
                "percent": disk.percent,
                "used": disk.used,
                "total": disk.total
            },
            "network": {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks")
async def create_task(task: Dict[str, Any]):
    """提交新任务"""
    try:
        task_type = task.get("type")
        params = task.get("params", {})
        
        if not task_type:
            raise HTTPException(status_code=400, detail="任务类型不能为空")
        
        result = await agent_scheduler.submit_task(task_type, params)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))