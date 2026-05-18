"""定时任务管理API"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

router = APIRouter(prefix="/api/schedule", tags=["定时任务"])


class CronJobRequest(BaseModel):
    task_id: str
    name: str
    cron: str
    workflow_id: Optional[str] = None
    action: Optional[str] = None
    params: Optional[Dict[str, Any]] = {}


class IntervalJobRequest(BaseModel):
    task_id: str
    name: str
    seconds: Optional[int] = 0
    minutes: Optional[int] = 0
    hours: Optional[int] = 0
    workflow_id: Optional[str] = None
    action: Optional[str] = None
    params: Optional[Dict[str, Any]] = {}


@router.post("/cron")
async def add_cron_job(request: CronJobRequest):
    """添加cron定时任务"""
    try:
        from core.tasks.task_scheduler import task_scheduler
        
        result = task_scheduler.add_cron_job(
            task_id=request.task_id,
            name=request.name,
            cron_expression=request.cron,
            workflow_id=request.workflow_id,
            action=request.action,
            params=request.params,
        )
        
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/interval")
async def add_interval_job(request: IntervalJobRequest):
    """添加间隔执行任务"""
    try:
        from core.tasks.task_scheduler import task_scheduler
        
        result = task_scheduler.add_interval_job(
            task_id=request.task_id,
            name=request.name,
            seconds=request.seconds,
            minutes=request.minutes,
            hours=request.hours,
            workflow_id=request.workflow_id,
            action=request.action,
            params=request.params,
        )
        
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def remove_job(task_id: str):
    """删除定时任务"""
    try:
        from core.tasks.task_scheduler import task_scheduler
        
        result = task_scheduler.remove_job(task_id)
        
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_jobs():
    """列出所有定时任务"""
    try:
        from core.tasks.task_scheduler import task_scheduler
        
        # 获取系统状态和队列状态
        system_status = task_scheduler.get_system_status()
        queue_status = task_scheduler.get_queue_status()
        
        return {
            "success": True, 
            "system_status": system_status,
            "queue_status": queue_status,
            "total_tasks": len(task_scheduler.tasks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
