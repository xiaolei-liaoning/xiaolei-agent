"""计划管理API路由

包含：
- GET /api/plans - 获取计划列表
- POST /api/plans - 创建新计划
- GET /api/plans/stats - 获取计划统计
- GET /api/plans/{plan_id} - 获取计划详情
- PUT /api/plans/{plan_id} - 更新计划
- DELETE /api/plans/{plan_id} - 删除计划
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["plans"])


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------
class CreatePlanRequest(BaseModel):
    """创建计划请求"""
    goal: str
    user_id: int = 1


class UpdatePlanRequest(BaseModel):
    """更新计划请求"""
    name: Optional[str] = None
    goal: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[float] = None
    steps: Optional[list] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------
@router.get("/plans", summary="获取计划列表")
async def get_plans(
    user_id: int = 1,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """获取用户的计划列表
    
    Args:
        user_id: 用户ID
        status: 状态筛选（待开始/进行中/已完成/已暂停）
        limit: 每页条数
        offset: 偏移量
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {"plans": [], "total": 0}
    
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    
    try:
        from core.infrastructure.database import get_session, Plan
        from sqlalchemy import desc
        
        session = get_session()
        try:
            # 构建查询
            query = session.query(Plan).filter_by(user_id=user_id)
            
            # 状态筛选
            if status and status != "all":
                query = query.filter_by(status=status)
            
            # 获取总数
            total = query.count()
            
            # 分页查询
            plans = query.order_by(desc(Plan.created_at)).offset(offset).limit(limit).all()
            
            # 转换为字典
            plans_data = []
            for plan in plans:
                plans_data.append({
                    "id": plan.id,
                    "name": plan.name,
                    "goal": plan.goal,
                    "status": plan.status,
                    "progress": plan.progress,
                    "steps": plan.steps or [],
                    "start_date": plan.start_date.strftime("%Y-%m-%d") if plan.start_date else None,
                    "end_date": plan.end_date.strftime("%Y-%m-%d") if plan.end_date else None,
                    "created_at": plan.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "updated_at": plan.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                })
            
            return {
                "plans": plans_data,
                "total": total,
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"获取计划列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取计划列表失败: {str(e)}")


@router.post("/plans", summary="创建新计划")
async def create_plan(request: CreatePlanRequest) -> Dict[str, Any]:
    """创建新计划
    
    Args:
        request: 创建计划请求
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        raise HTTPException(status_code=500, detail="数据库未初始化")
    
    try:
        from core.infrastructure.database import get_session, Plan
        
        session = get_session()
        try:
            # 创建计划
            plan = Plan(
                user_id=request.user_id,
                name=request.goal[:50],  # 使用前50个字符作为名称
                goal=request.goal,
                status="待开始",
                progress=0.0,
            )
            
            session.add(plan)
            session.commit()
            session.refresh(plan)
            
            logger.info(f"创建计划成功: {plan.id} - {plan.name}")
            
            return {
                "success": True,
                "plan_id": plan.id,
                "message": "计划创建成功",
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "goal": plan.goal,
                    "status": plan.status,
                    "progress": plan.progress,
                    "created_at": plan.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建计划失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建计划失败: {str(e)}")


@router.get("/plans/stats", summary="获取计划统计")
async def get_plan_stats(user_id: int = 1) -> Dict[str, Any]:
    """获取计划统计数据
    
    Args:
        user_id: 用户ID
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        return {
            "total": 0,
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "paused": 0,
        }
    
    try:
        from core.infrastructure.database import get_session, Plan
        
        session = get_session()
        try:
            # 总数
            total = session.query(Plan).filter_by(user_id=user_id).count()
            
            # 各状态数量
            pending = session.query(Plan).filter_by(user_id=user_id, status="待开始").count()
            in_progress = session.query(Plan).filter_by(user_id=user_id, status="进行中").count()
            completed = session.query(Plan).filter_by(user_id=user_id, status="已完成").count()
            paused = session.query(Plan).filter_by(user_id=user_id, status="已暂停").count()
            
            return {
                "total": total,
                "pending": pending,
                "in_progress": in_progress,
                "completed": completed,
                "paused": paused,
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"获取计划统计失败: {e}", exc_info=True)
        return {
            "total": 0,
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "paused": 0,
        }


@router.get("/plans/{plan_id}", summary="获取计划详情")
async def get_plan_detail(plan_id: int) -> Dict[str, Any]:
    """获取计划详情
    
    Args:
        plan_id: 计划ID
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        raise HTTPException(status_code=500, detail="数据库未初始化")
    
    try:
        from core.infrastructure.database import get_session, Plan
        
        session = get_session()
        try:
            plan = session.query(Plan).filter_by(id=plan_id).first()
            
            if not plan:
                raise HTTPException(status_code=404, detail="计划不存在")
            
            return {
                "id": plan.id,
                "user_id": plan.user_id,
                "name": plan.name,
                "goal": plan.goal,
                "status": plan.status,
                "progress": plan.progress,
                "steps": plan.steps or [],
                "start_date": plan.start_date.strftime("%Y-%m-%d") if plan.start_date else None,
                "end_date": plan.end_date.strftime("%Y-%m-%d") if plan.end_date else None,
                "created_at": plan.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": plan.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取计划详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取计划详情失败: {str(e)}")


@router.put("/plans/{plan_id}", summary="更新计划")
async def update_plan(plan_id: int, request: UpdatePlanRequest) -> Dict[str, Any]:
    """更新计划
    
    Args:
        plan_id: 计划ID
        request: 更新请求
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        raise HTTPException(status_code=500, detail="数据库未初始化")
    
    try:
        from core.infrastructure.database import get_session, Plan
        
        session = get_session()
        try:
            plan = session.query(Plan).filter_by(id=plan_id).first()
            
            if not plan:
                raise HTTPException(status_code=404, detail="计划不存在")
            
            # 更新字段
            if request.name is not None:
                plan.name = request.name
            if request.goal is not None:
                plan.goal = request.goal
            if request.status is not None:
                plan.status = request.status
            if request.progress is not None:
                plan.progress = request.progress
            if request.steps is not None:
                plan.steps = request.steps
            if request.start_date is not None:
                plan.start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
            if request.end_date is not None:
                plan.end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
            
            session.commit()
            session.refresh(plan)
            
            logger.info(f"更新计划成功: {plan.id}")
            
            return {
                "success": True,
                "message": "计划更新成功",
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "status": plan.status,
                    "progress": plan.progress,
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新计划失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新计划失败: {str(e)}")


@router.delete("/plans/{plan_id}", summary="删除计划")
async def delete_plan(plan_id: int) -> Dict[str, Any]:
    """删除计划
    
    Args:
        plan_id: 计划ID
    """
    from core.handlers import _db_initialized
    
    if not _db_initialized:
        raise HTTPException(status_code=500, detail="数据库未初始化")
    
    try:
        from core.infrastructure.database import get_session, Plan
        
        session = get_session()
        try:
            plan = session.query(Plan).filter_by(id=plan_id).first()
            
            if not plan:
                raise HTTPException(status_code=404, detail="计划不存在")
            
            plan_name = plan.name
            session.delete(plan)
            session.commit()
            
            logger.info(f"删除计划成功: {plan_id} - {plan_name}")
            
            return {
                "success": True,
                "message": f"计划'{plan_name}'已删除",
            }
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除计划失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除计划失败: {str(e)}")
