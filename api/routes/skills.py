"""技能安装管理API

提供技能的安装、卸载、启用、禁用等功能
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import logging

from core.infrastructure.database import get_session, UserSkillInstallation, Session
from sqlalchemy import and_

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])


# ==================== 请求/响应模型 ====================

class InstallSkillRequest(BaseModel):
    """安装技能请求"""
    skill_name: str = Field(..., description="技能名称")
    skill_version: str = Field("1.0.0", description="技能版本")
    user_id: int = Field(1, description="用户ID（临时默认值）")
    config: Optional[dict] = Field(None, description="技能配置")


class SkillStatusResponse(BaseModel):
    """技能状态响应"""
    success: bool
    message: str
    data: Optional[dict] = None


class SkillListResponse(BaseModel):
    """技能列表响应"""
    success: bool
    total: int
    skills: List[dict]


# ==================== API端点 ====================

@router.post("/install", response_model=SkillStatusResponse, summary="安装技能")
async def install_skill(request: InstallSkillRequest, db: Session = Depends(get_session)):
    """
    安装技能到用户账户
    
    - **skill_name**: 技能名称
    - **skill_version**: 技能版本（默认1.0.0）
    - **user_id**: 用户ID
    - **config**: 可选的技能配置
    """
    try:
        # 检查技能是否已安装
        existing = db.query(UserSkillInstallation).filter(
            and_(
                UserSkillInstallation.user_id == request.user_id,
                UserSkillInstallation.skill_name == request.skill_name
            )
        ).first()
        
        if existing:
            # 如果已安装，更新状态为enabled
            existing.status = "enabled"
            existing.enabled_at = datetime.now()
            existing.updated_at = datetime.now()
            if request.config:
                existing.config = request.config
            
            db.commit()
            
            return SkillStatusResponse(
                success=True,
                message=f"技能 '{request.skill_name}' 已重新启用",
                data={
                    "skill_name": request.skill_name,
                    "status": "enabled",
                    "installed_at": existing.installed_at.isoformat()
                }
            )
        
        # 创建新的安装记录
        new_installation = UserSkillInstallation(
            user_id=request.user_id,
            skill_name=request.skill_name,
            skill_version=request.skill_version,
            status="enabled",
            config=request.config,
            enabled_at=datetime.now()
        )
        
        db.add(new_installation)
        db.commit()
        db.refresh(new_installation)
        
        logger.info(f"用户 {request.user_id} 安装了技能: {request.skill_name}")
        
        return SkillStatusResponse(
            success=True,
            message=f"技能 '{request.skill_name}' 安装成功",
            data={
                "skill_name": request.skill_name,
                "version": request.skill_version,
                "status": "enabled",
                "installed_at": new_installation.installed_at.isoformat()
            }
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"安装技能失败: {e}")
        raise HTTPException(status_code=500, detail=f"安装技能失败: {str(e)}")


@router.delete("/uninstall/{skill_name}", response_model=SkillStatusResponse, summary="卸载技能")
async def uninstall_skill(skill_name: str, user_id: int = 1, db: Session = Depends(get_session)):
    """
    从用户账户卸载技能
    
    - **skill_name**: 技能名称
    - **user_id**: 用户ID
    """
    try:
        # 查找技能安装记录
        installation = db.query(UserSkillInstallation).filter(
            and_(
                UserSkillInstallation.user_id == user_id,
                UserSkillInstallation.skill_name == skill_name
            )
        ).first()
        
        if not installation:
            raise HTTPException(status_code=404, detail=f"技能 '{skill_name}' 未安装")
        
        # 删除记录
        db.delete(installation)
        db.commit()
        
        logger.info(f"用户 {user_id} 卸载了技能: {skill_name}")
        
        return SkillStatusResponse(
            success=True,
            message=f"技能 '{skill_name}' 已卸载",
            data={"skill_name": skill_name}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"卸载技能失败: {e}")
        raise HTTPException(status_code=500, detail=f"卸载技能失败: {str(e)}")


@router.put("/enable/{skill_name}", response_model=SkillStatusResponse, summary="启用技能")
async def enable_skill(skill_name: str, user_id: int = 1, db: Session = Depends(get_session)):
    """
    启用已安装的技能
    
    - **skill_name**: 技能名称
    - **user_id**: 用户ID
    """
    try:
        # 查找技能安装记录
        installation = db.query(UserSkillInstallation).filter(
            and_(
                UserSkillInstallation.user_id == user_id,
                UserSkillInstallation.skill_name == skill_name
            )
        ).first()
        
        if not installation:
            raise HTTPException(status_code=404, detail=f"技能 '{skill_name}' 未安装，请先安装")
        
        # 更新状态
        installation.status = "enabled"
        installation.enabled_at = datetime.now()
        installation.updated_at = datetime.now()
        
        db.commit()
        
        logger.info(f"用户 {user_id} 启用了技能: {skill_name}")
        
        return SkillStatusResponse(
            success=True,
            message=f"技能 '{skill_name}' 已启用",
            data={
                "skill_name": skill_name,
                "status": "enabled",
                "enabled_at": installation.enabled_at.isoformat()
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"启用技能失败: {e}")
        raise HTTPException(status_code=500, detail=f"启用技能失败: {str(e)}")


@router.put("/disable/{skill_name}", response_model=SkillStatusResponse, summary="禁用技能")
async def disable_skill(skill_name: str, user_id: int = 1, db: Session = Depends(get_session)):
    """
    禁用已安装的技能
    
    - **skill_name**: 技能名称
    - **user_id**: 用户ID
    """
    try:
        # 查找技能安装记录
        installation = db.query(UserSkillInstallation).filter(
            and_(
                UserSkillInstallation.user_id == user_id,
                UserSkillInstallation.skill_name == skill_name
            )
        ).first()
        
        if not installation:
            raise HTTPException(status_code=404, detail=f"技能 '{skill_name}' 未安装")
        
        # 更新状态
        installation.status = "disabled"
        installation.updated_at = datetime.now()
        
        db.commit()
        
        logger.info(f"用户 {user_id} 禁用了技能: {skill_name}")
        
        return SkillStatusResponse(
            success=True,
            message=f"技能 '{skill_name}' 已禁用",
            data={
                "skill_name": skill_name,
                "status": "disabled"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"禁用技能失败: {e}")
        raise HTTPException(status_code=500, detail=f"禁用技能失败: {str(e)}")


@router.get("/my-skills", response_model=SkillListResponse, summary="获取已安装技能列表")
async def get_my_skills(user_id: int = 1, db: Session = Depends(get_session)):
    """
    获取用户已安装的所有技能
    
    - **user_id**: 用户ID
    """
    try:
        # 查询所有安装的技能
        installations = db.query(UserSkillInstallation).filter(
            UserSkillInstallation.user_id == user_id
        ).all()
        
        skills_list = []
        for inst in installations:
            skills_list.append({
                "skill_name": inst.skill_name,
                "skill_version": inst.skill_version,
                "status": inst.status,
                "config": inst.config,
                "installed_at": inst.installed_at.isoformat(),
                "enabled_at": inst.enabled_at.isoformat() if inst.enabled_at else None,
                "updated_at": inst.updated_at.isoformat()
            })
        
        return SkillListResponse(
            success=True,
            total=len(skills_list),
            skills=skills_list
        )
    
    except Exception as e:
        logger.error(f"获取技能列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取技能列表失败: {str(e)}")


@router.get("/check/{skill_name}", response_model=SkillStatusResponse, summary="检查技能安装状态")
async def check_skill_status(skill_name: str, user_id: int = 1, db: Session = Depends(get_session)):
    """
    检查指定技能的安装状态
    
    - **skill_name**: 技能名称
    - **user_id**: 用户ID
    """
    try:
        # 查找技能安装记录
        installation = db.query(UserSkillInstallation).filter(
            and_(
                UserSkillInstallation.user_id == user_id,
                UserSkillInstallation.skill_name == skill_name
            )
        ).first()
        
        if not installation:
            return SkillStatusResponse(
                success=True,
                message=f"技能 '{skill_name}' 未安装",
                data={
                    "skill_name": skill_name,
                    "installed": False,
                    "status": "not_installed"
                }
            )
        
        return SkillStatusResponse(
            success=True,
            message=f"技能 '{skill_name}' 状态: {installation.status}",
            data={
                "skill_name": skill_name,
                "installed": True,
                "status": installation.status,
                "version": installation.skill_version,
                "installed_at": installation.installed_at.isoformat(),
                "enabled_at": installation.enabled_at.isoformat() if installation.enabled_at else None
            }
        )
    
    except Exception as e:
        logger.error(f"检查技能状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"检查技能状态失败: {str(e)}")


# ==================== 技能列表/搜索（从文件系统扫描） ====================

from pathlib import Path
from typing import List


def _get_all_skills() -> List[dict]:
    """递归扫描 skills/ 目录获取所有技能信息。"""
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    skills = []
    if not skills_dir.exists():
        return skills

    for skill_md in skills_dir.rglob("SKILL.md"):
        parent_dir = skill_md.parent
        if any(part.startswith('.') or part.startswith('_') for part in parent_dir.parts):
            continue
        try:
            content = skill_md.read_text(encoding='utf-8')
            skill_name = parent_dir.name
            description = ""
            keywords = []
            in_description = False
            in_keywords = False
            for line in content.split('\n'):
                if '功能描述' in line:
                    in_description = True
                    in_keywords = False
                    continue
                elif '触发关键词' in line:
                    in_keywords = True
                    in_description = False
                    continue
                elif line.startswith('##'):
                    in_description = False
                    in_keywords = False
                    continue
                if in_description and line.strip():
                    description += line.strip() + ' '
                elif in_keywords and line.strip():
                    keywords.append(line.strip())
            skills.append({
                'name': skill_name,
                'display_name': skill_name.replace('_', ' ').title(),
                'description': description.strip(),
                'keywords': keywords,
                'tag': f"@{skill_name}"
            })
        except Exception as e:
            logger.error("读取技能失败: %s, 错误: %s", skill_md, e)
    return skills


_skills_cache = None
_skills_cache_loaded = False


def _get_cached_skills() -> list:
    global _skills_cache, _skills_cache_loaded
    if not _skills_cache_loaded:
        _skills_cache = _get_all_skills()
        _skills_cache_loaded = True
    return _skills_cache


@router.get("/list", summary="获取可用技能列表")
async def list_skills():
    """获取所有可用技能。"""
    return {"success": True, "data": _get_cached_skills()}


@router.get("/search", summary="搜索技能")
async def search_skills(q: str = ""):
    """按名称或关键词搜索技能。"""
    query = q.lower()
    skills = _get_cached_skills()
    if not query:
        return {"success": True, "data": skills}
    filtered = []
    for skill in skills:
        if query in skill['name'].lower() or query in skill['display_name'].lower():
            filtered.append(skill)
            continue
        for kw in skill['keywords']:
            if query in kw.lower():
                filtered.append(skill)
                break
    return {"success": True, "data": filtered}
