"""监控API接口 — 仅保留系统状态监控"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import psutil

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