"""
技能市场 Web API - Skill Marketplace API

提供RESTful API接口，支持技能的搜索、发布、评分等功能。
"""

import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Path as PathParam
from pydantic import BaseModel, Field
from pathlib import Path

from .registry import SkillRegistry, SkillMetadata
from .version_manager import VersionManager
from .dependency_resolver import DependencyResolver
from .rating_system import RatingSystem
from .search_engine import SkillSearchEngine
from .validator import SkillValidator
from .publisher import SkillPublisher

logger = logging.getLogger(__name__)

# 初始化组件
registry = SkillRegistry()
version_manager = VersionManager()
dependency_resolver = DependencyResolver(version_manager)
rating_system = RatingSystem()
search_engine = SkillSearchEngine(registry)
validator = SkillValidator()
publisher = SkillPublisher(registry, version_manager, validator)

# 创建FastAPI应用
app = FastAPI(
    title="Skill Marketplace API",
    description="生态化技能市场API，支持技能的发布、搜索、评分和管理",
    version="1.0.0"
)


# ==================== Pydantic Models ====================

class SkillPublishRequest(BaseModel):
    """技能发布请求"""
    skill_path: str = Field(..., description="技能目录路径")
    author_id: str = Field(..., description="作者ID")
    force: bool = Field(False, description="是否强制发布")


class SkillUpdateRequest(BaseModel):
    """技能更新请求"""
    skill_path: str = Field(..., description="技能目录路径")
    author_id: str = Field(..., description="作者ID")
    change_type: str = Field("patch", description="变更类型: major/minor/patch")


class RatingRequest(BaseModel):
    """评分请求"""
    user_id: str = Field(..., description="用户ID")
    skill_name: str = Field(..., description="技能名称")
    skill_version: str = Field(..., description="技能版本")
    rating: int = Field(..., ge=1, le=5, description="评分(1-5)")
    comment: str = Field("", description="评论")


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field("", description="搜索关键词")
    category: Optional[str] = Field(None, description="分类过滤")
    tags: Optional[list] = Field(None, description="标签过滤")
    min_rating: float = Field(0, ge=0, le=5, description="最低评分")
    verified_only: bool = Field(False, description="只返回已验证技能")
    limit: int = Field(20, ge=1, le=100, description="返回数量限制")


# ==================== API Endpoints ====================

@app.get("/")
async def root():
    """API根路径"""
    return {
        "message": "Skill Marketplace API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


# ---------- 技能查询 ----------

@app.get("/api/skills")
async def list_skills(
    category: Optional[str] = Query(None, description="分类过滤"),
    tags: Optional[str] = Query(None, description="标签过滤（逗号分隔）"),
    status: Optional[str] = Query(None, description="状态过滤"),
    verified_only: bool = Query(False, description="只返回已验证技能"),
    limit: int = Query(50, ge=1, le=200)
):
    """列出所有技能"""
    tag_list = [t.strip() for t in tags.split(',')] if tags else None
    
    skills = registry.list_skills(
        category=category,
        tags=tag_list,
        status=status,
        verified_only=verified_only
    )
    
    return {
        "total": len(skills),
        "skills": [skill.to_dict() for skill in skills[:limit]]
    }


@app.get("/api/skills/{skill_name}")
async def get_skill(
    skill_name: str = PathParam(..., description="技能名称"),
    version: Optional[str] = Query(None, description="版本号")
):
    """获取技能详情"""
    skill = registry.get_skill(skill_name, version)
    
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    
    # 获取评分汇总
    rating_summary = rating_system.get_skill_summary(skill_name)
    
    # 获取依赖树
    dependency_tree = dependency_resolver.get_dependency_tree(skill_name)
    
    return {
        "skill": skill.to_dict(),
        "rating_summary": rating_summary.to_dict(),
        "dependency_tree": dependency_tree
    }


@app.get("/api/skills/{skill_name}/versions")
async def get_skill_versions(
    skill_name: str = PathParam(..., description="技能名称")
):
    """获取技能的所有版本"""
    versions = version_manager.get_all_versions(skill_name)
    
    if not versions:
        raise HTTPException(status_code=404, detail=f"No versions found for '{skill_name}'")
    
    return {
        "skill_name": skill_name,
        "versions": versions,
        "latest": version_manager.get_latest_version(skill_name)
    }


# ---------- 技能搜索 ----------

@app.post("/api/skills/search")
async def search_skills(request: SearchRequest):
    """搜索技能"""
    results = search_engine.search(
        query=request.query,
        category=request.category,
        tags=request.tags,
        min_rating=request.min_rating,
        verified_only=request.verified_only,
        limit=request.limit
    )
    
    return {
        "query": request.query,
        "total": len(results),
        "results": results
    }


@app.get("/api/skills/recommendations")
async def get_recommendations(
    user_history: str = Query("", description="用户使用历史（逗号分隔的技能名）")
):
    """获取个性化推荐"""
    history_list = [s.strip() for s in user_history.split(',') if s.strip()] if user_history else []
    
    recommendations = search_engine.get_recommendations(history_list, limit=10)
    
    return {
        "recommendations": recommendations
    }


@app.get("/api/skills/{skill_name}/similar")
async def get_similar_skills(
    skill_name: str = PathParam(..., description="技能名称"),
    limit: int = Query(5, ge=1, le=20)
):
    """获取相似技能"""
    similar = search_engine.get_similar_skills(skill_name, limit)
    
    return {
        "skill_name": skill_name,
        "similar_skills": similar
    }


# ---------- 技能发布 ----------

@app.post("/api/skills/publish")
async def publish_skill(request: SkillPublishRequest):
    """发布技能"""
    skill_path = Path(request.skill_path)
    
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"Skill path not found: {request.skill_path}")
    
    result = publisher.publish_skill(
        skill_path,
        request.author_id,
        request.force
    )
    
    if not result['success']:
        raise HTTPException(
            status_code=400,
            detail=result['message'],
            headers={"X-Errors": str(result.get('errors', []))}
        )
    
    return result


@app.post("/api/skills/update")
async def update_skill(request: SkillUpdateRequest):
    """更新技能"""
    skill_path = Path(request.skill_path)
    
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"Skill path not found: {request.skill_path}")
    
    result = publisher.update_skill(
        skill_path,
        request.author_id,
        request.change_type
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['message'])
    
    return result


# ---------- 评分系统 ----------

@app.post("/api/ratings")
async def add_rating(request: RatingRequest):
    """添加评分"""
    success = rating_system.add_rating(
        request.user_id,
        request.skill_name,
        request.skill_version,
        request.rating,
        request.comment
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to add rating")
    
    return {
        "success": True,
        "message": "Rating added successfully"
    }


@app.get("/api/ratings/{skill_name}")
async def get_ratings(
    skill_name: str = PathParam(..., description="技能名称")
):
    """获取技能评分"""
    summary = rating_system.get_skill_summary(skill_name)
    
    return summary.to_dict()


@app.get("/api/ratings/top")
async def get_top_rated(
    min_ratings: int = Query(5, description="最少评分数"),
    limit: int = Query(10, ge=1, le=50)
):
    """获取评分最高的技能"""
    top_skills = rating_system.get_top_rated_skills(min_ratings, limit)
    
    return {
        "top_skills": top_skills
    }


@app.get("/api/ratings/trending")
async def get_trending(
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(10, ge=1, le=50)
):
    """获取热门技能"""
    trending = rating_system.get_trending_skills(days, limit)
    
    return {
        "trending_skills": trending
    }


# ---------- 统计信息 ----------

@app.get("/api/stats")
async def get_statistics():
    """获取系统统计信息"""
    return {
        "registry": registry.get_statistics(),
        "rating_system": rating_system.get_statistics(),
        "search_engine": search_engine.get_statistics(),
        "dependency_resolver": dependency_resolver.get_statistics(),
        "publisher": publisher.get_publish_statistics()
    }


# ---------- 依赖管理 ----------

@app.get("/api/dependencies/{skill_name}")
async def get_dependencies(
    skill_name: str = PathParam(..., description="技能名称")
):
    """获取技能依赖"""
    dependency_tree = dependency_resolver.get_dependency_tree(skill_name)
    
    return {
        "skill_name": skill_name,
        "dependency_tree": dependency_tree
    }


@app.post("/api/dependencies/check")
async def check_dependencies(
    skill_name: str = Query(..., description="技能名称"),
    dependencies: dict = Query(..., description="依赖关系")
):
    """检查依赖冲突"""
    conflicts = dependency_resolver.detect_conflicts(skill_name, dependencies)
    
    return {
        "skill_name": skill_name,
        "conflicts": conflicts,
        "has_conflicts": len(conflicts) > 0
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8004)
