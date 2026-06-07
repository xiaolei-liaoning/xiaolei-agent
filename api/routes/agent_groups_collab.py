"""多Agent协作 API（已迁移）

所有多Agent小组协作功能已迁移至 JS Workflow 编排系统。
"""
import logging
from fastapi import APIRouter
from typing import Dict, Any

logger = logging.getLogger(__name__)

collab_router = APIRouter(prefix="/api/agent-groups")


def _gone() -> Dict[str, Any]:
    """返回 410 Gone 响应"""
    from fastapi import HTTPException
    raise HTTPException(
        status_code=410,
        detail="已迁移至 JS Workflow 编排系统 (core/multi_agent_v2/workflow/js_workflow.py)"
    )


@collab_router.post("/collaborate/analyze")
async def analyze_and_recommend_agents():
    _gone()


@collab_router.post("/collaborate/start")
async def start_collaboration_session():
    _gone()


@collab_router.post("/collaborate/{session_id}/execute")
async def execute_collaboration(session_id: str):
    _gone()


@collab_router.get("/collaborate/{session_id}/status")
async def get_collaboration_status(session_id: str):
    _gone()


@collab_router.post("/missing-agent/analyze")
async def analyze_missing_agent():
    _gone()


@collab_router.post("/missing-agent/create-temporary")
async def create_temporary_agent():
    _gone()


@collab_router.get("/missing-agent/pending-requests")
async def get_pending_agent_requests():
    _gone()


@collab_router.post("/missing-agent/approve")
async def approve_agent_request():
    _gone()


# 初始化能力画像（已废弃）
def _register_group_profiles():
    pass


__all__ = ["collab_router"]
