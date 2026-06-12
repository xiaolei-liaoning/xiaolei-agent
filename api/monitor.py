"""监控API接口 — 系统状态 + Agent/Task 监控"""
import logging
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import psutil

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/monitor", tags=["monitor"])


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


@router.get("/agents")
async def get_monitor_agents():
    """获取监控Agent列表（遗留页面兼容）"""
    logger.warning("GET /api/monitor/agents 被调用 — 返回空数据，原功能已移除")
    return {"agents": {}}


@router.get("/tasks")
async def get_monitor_tasks():
    """获取监控任务列表（遗留页面兼容）"""
    logger.warning("GET /api/monitor/tasks 被调用 — 返回空数据，原功能已移除")
    return {"tasks": {}}


@router.post("/tasks")
async def create_monitor_task(data: Dict[str, Any]):
    """创建监控任务（遗留页面兼容）"""
    logger.warning("POST /api/monitor/tasks 被调用 — 原功能已移除")
    return {"task_id": "", "agent_type": "", "status": "deprecated"}