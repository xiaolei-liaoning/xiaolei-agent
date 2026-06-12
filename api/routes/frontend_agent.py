"""前端Agent监控API（遗留页面兼容）"""
import logging
from fastapi import APIRouter
from typing import Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/frontend_agent", tags=["frontend_agent"])


@router.get("/monitor/agents")
async def get_frontend_agents():
    """获取前端Agent状态（原功能已移除，返回空数据）"""
    logger.warning("GET /api/frontend_agent/monitor/agents 被调用 — 返回空数据")
    return {"agents": {}}


@router.post("/tasks/submit")
async def submit_frontend_task(data: Dict[str, Any]):
    """提交前端Agent任务（原功能已移除）"""
    logger.warning("POST /api/frontend_agent/tasks/submit 被调用 — 原功能已移除")
    return {"task_id": "", "status": "deprecated"}
