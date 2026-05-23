"""多Agent协作与缺失Agent处理 API

从 agent_groups.py 提取的协作相关功能：
- 场景1：多Agent小组协作（分析、启动、执行、状态查询）
- 场景2：缺失Agent处理（分析、创建临时Agent、审批）
- 能力画像注册

依赖：
- agent_groups._agent_groups（模块级共享状态）
- core.agents.group_collaboration（协作引擎）
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
import threading

from api.routes.agent_groups import _agent_groups

logger = logging.getLogger(__name__)

collab_router = APIRouter(prefix="/api/agent-groups")


# ==========================================
# 数据模型
# ==========================================

class CollaborationRequest(BaseModel):
    """协作请求"""
    task: str = Field(..., description="任务描述")
    strategy: Optional[str] = Field("parallel", description="协作策略: parallel, sequential")
    use_auto_coordination: bool = Field(True, description="是否使用自动协调")


class SessionStatusResponse(BaseModel):
    """会话状态响应"""
    session_id: str
    status: str
    phase: str
    total_subtasks: int
    completed_subtasks: int
    results: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class NewAgentRequest(BaseModel):
    """创建新Agent请求"""
    task_example: str = Field(..., description="任务示例")
    agent_name: Optional[str] = Field(None, description="Agent名称")
    agent_description: Optional[str] = Field(None, description="Agent描述")


class AgentRequestApproval(BaseModel):
    """Agent添加请求审批"""
    request_id: str
    approve: bool = Field(True, description="是否批准")
    make_permanent: bool = Field(False, description="是否转为永久Agent")


# ==========================================
# 简易执行器（包装 _agent_groups 调用）
# ==========================================

class _SimpleExecutor:
    """简易执行器，将协作者调用的 group_id 转接到 agent_group_executor"""

    async def execute_with_group_id(self, group_id: str, message: str):
        from agent_group_executor import agent_group_executor

        if group_id not in _agent_groups:
            return {"success": False, "error": "小组不存在"}

        group = _agent_groups[group_id]
        try:
            result = await agent_group_executor.execute_with_group(group, message)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}


# ==========================================
# 场景1：多Agent小组协作 API
# ==========================================

@collab_router.post("/collaborate/analyze")
async def analyze_and_recommend_agents(request: CollaborationRequest):
    """分析任务并推荐Agent小组"""
    try:
        from core.agents.group_collaboration import get_group_coordinator
        coordinator = get_group_coordinator()

        recommendation = coordinator.recommend_agent_groups(request.task)

        return {
            "success": True,
            "data": {
                "task_analysis": {
                    "required_capabilities": [cap.value for cap in recommendation.required_capabilities],
                    "task_type": "complex" if len(recommendation.required_capabilities) > 1 else "simple"
                },
                "recommended_groups": [
                    {
                        "group_id": g.group_id,
                        "name": g.name,
                        "description": g.description,
                        "capabilities": [c.value for c in g.capabilities],
                        "success_rate": g.success_rate
                    }
                    for g in recommendation.recommended_groups
                ],
                "requires_new_agent": recommendation.requires_new_agent,
                "suggested_agent": {
                    "name": recommendation.suggested_agent_name,
                    "description": recommendation.suggested_agent_description
                } if recommendation.requires_new_agent else None
            }
        }
    except Exception as e:
        logger.error(f"任务分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@collab_router.post("/collaborate/start")
async def start_collaboration_session(request: CollaborationRequest):
    """启动多Agent小组协作会话"""
    try:
        from core.agents.group_collaboration import get_group_coordinator, CollaborationStrategy

        coordinator = get_group_coordinator()

        strategy_map = {
            "parallel": CollaborationStrategy.PARALLEL,
            "sequential": CollaborationStrategy.SEQUENTIAL,
            "hierarchical": CollaborationStrategy.HIERARCHICAL
        }

        strategy = strategy_map.get(request.strategy, CollaborationStrategy.PARALLEL)

        session = await coordinator.start_collaboration_session(request.task, strategy)

        return {
            "success": True,
            "data": {
                "session_id": session.get("session_id", ""),
                "total_subtasks": len(session.get("subtasks", [])),
                "participant_groups": session.get("participant_groups", []),
                "subtasks": [
                    {
                        "subtask_id": st.get("subtask_id", ""),
                        "description": st.get("description", ""),
                        "required_capability": st.get("required_capability", {}).get("value", "") if isinstance(st.get("required_capability"), dict) else str(st.get("required_capability", "")),
                        "assigned_group": st.get("assigned_group", ""),
                        "priority": st.get("priority", 0)
                    }
                    for st in session.get("subtasks", [])
                ]
            }
        }
    except Exception as e:
        logger.error(f"启动协作会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@collab_router.post("/collaborate/{session_id}/execute")
async def execute_collaboration(session_id: str):
    """执行协作任务"""
    try:
        from core.agents.group_collaboration import get_group_coordinator

        coordinator = get_group_coordinator()
        session = coordinator.get_session_status(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        executor = _SimpleExecutor()
        result = await coordinator.execute_collaboration(session, executor)

        return {
            "success": True,
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"执行协作失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@collab_router.get("/collaborate/{session_id}/status")
async def get_collaboration_status(session_id: str):
    """获取协作会话状态"""
    try:
        from core.agents.group_collaboration import get_group_coordinator

        coordinator = get_group_coordinator()
        session = coordinator.get_session_status(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        completed = len([st for st in session.get("subtasks", []) if st.get("status") == "completed"])

        return {
            "success": True,
            "data": {
                "session_id": session.get("session_id", ""),
                "status": session.get("status", ""),
                "phase": session.get("phase", {}).get("value", "") if isinstance(session.get("phase"), dict) else str(session.get("phase", "")),
                "total_subtasks": len(session.get("subtasks", [])),
                "completed_subtasks": completed,
                "subtasks": [
                    {
                        "subtask_id": st.get("subtask_id", ""),
                        "description": st.get("description", ""),
                        "status": st.get("status", ""),
                        "assigned_group": st.get("assigned_group", "")
                    }
                    for st in session.get("subtasks", [])
                ]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 场景2：无对应Agent处理 API
# ==========================================

@collab_router.post("/missing-agent/analyze")
async def analyze_missing_agent(request: NewAgentRequest):
    """分析缺失的Agent需求"""
    try:
        from core.agents.group_collaboration import get_group_coordinator

        coordinator = get_group_coordinator()
        recommendation = coordinator.recommend_agent_groups(request.task_example)

        if not recommendation.requires_new_agent:
            return {
                "success": True,
                "data": {
                    "requires_new_agent": False,
                    "message": "已有合适的Agent可以处理此任务",
                    "recommended_groups": [
                        {"group_id": g.group_id, "name": g.name}
                        for g in recommendation.recommended_groups
                    ]
                }
            }

        return {
            "success": True,
            "data": {
                "requires_new_agent": True,
                "required_capabilities": [cap.value for cap in recommendation.required_capabilities],
                "suggested_agent": {
                    "name": recommendation.suggested_agent_name,
                    "description": recommendation.suggested_agent_description
                }
            }
        }
    except Exception as e:
        logger.error(f"分析缺失Agent失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@collab_router.post("/missing-agent/create-temporary")
async def create_temporary_agent(request: NewAgentRequest):
    """创建临时Agent"""
    try:
        from core.agents.group_collaboration import get_group_coordinator, get_temp_agent_creator, AgentCapability

        coordinator = get_group_coordinator()
        creator = get_temp_agent_creator()

        recommendation = coordinator.recommend_agent_groups(request.task_example)

        if not recommendation.requires_new_agent:
            raise HTTPException(status_code=400, detail="不需要创建新Agent")

        agent_name = request.agent_name or recommendation.suggested_agent_name
        agent_description = request.agent_description or recommendation.suggested_agent_description

        config = creator.create_temporary_agent_config(
            recommendation.required_capabilities,
            agent_name,
            agent_description
        )

        return {
            "success": True,
            "data": {
                "temporary_agent": config,
                "message": "临时Agent已创建，管理员将收到添加请求",
                "requires_supervision": config["requires_supervision"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建临时Agent失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@collab_router.get("/missing-agent/pending-requests")
async def get_pending_agent_requests():
    """获取待审批的Agent添加请求"""
    try:
        from core.agents.group_collaboration import get_temp_agent_creator

        creator = get_temp_agent_creator()
        pending = creator.get_pending_requests()

        return {
            "success": True,
            "data": {
                "pending_requests": pending
            }
        }
    except Exception as e:
        logger.error(f"获取待处理请求失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@collab_router.post("/missing-agent/approve")
async def approve_agent_request(approval: AgentRequestApproval):
    """审批Agent添加请求"""
    try:
        from core.agents.group_collaboration import get_temp_agent_creator

        creator = get_temp_agent_creator()

        if approval.approve:
            success = creator.approve_agent_request(approval.request_id, approval.make_permanent)
            if success:
                return {
                    "success": True,
                    "data": {
                        "message": "Agent添加请求已批准" + ("并已转为永久Agent" if approval.make_permanent else "")
                    }
                }
            else:
                raise HTTPException(status_code=404, detail="请求不存在")
        else:
            return {
                "success": True,
                "data": {
                    "message": "Agent添加请求已拒绝"
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"审批请求失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 初始化能力画像
# ==========================================

def _register_group_profiles():
    """为示例小组注册能力画像"""
    try:
        from core.agents.group_collaboration import get_group_coordinator, AgentGroupProfile, AgentCapability

        coordinator = get_group_coordinator()

        for group_id, group in _agent_groups.items():
            capabilities = []

            if "技术" in group.name or "技术智囊团" == group.name:
                capabilities.extend([AgentCapability.DATA_ANALYSIS, AgentCapability.WEB_SEARCH, AgentCapability.REASONING])
            elif "文学" in group.name or "文学创作" in group.name:
                capabilities.extend([AgentCapability.CREATIVE_WRITING, AgentCapability.TRANSLATION, AgentCapability.TEXT_GENERATION])
            elif "科学" in group.name or "研究" in group.name:
                capabilities.extend([AgentCapability.DATA_ANALYSIS, AgentCapability.REASONING, AgentCapability.TEXT_GENERATION])
            else:
                capabilities.append(AgentCapability.REASONING)

            profile = AgentGroupProfile(
                group_id=group_id,
                name=group.name,
                capabilities=capabilities,
                description=group.description,
                success_rate=group.success_rate,
                total_tasks=group.task_count
            )

            coordinator.register_group_profile(profile)

        logger.info("Agent小组能力画像注册完成")
    except Exception as e:
        logger.warning(f"注册能力画像失败: {e}")


# 注册能力画像（延迟执行，避免循环导入）
threading.Thread(target=_register_group_profiles, daemon=True).start()

__all__ = ["collab_router"]
