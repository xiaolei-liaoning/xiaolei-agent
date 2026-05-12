"""系统相关API路由

包含：
- GET /api/health - 健康检查
- GET /api/metrics - 系统指标
- GET /api/characters - 角色列表
- POST /api/characters - 创建角色
- PUT /api/characters/{character_id} - 更新角色
- DELETE /api/characters/{character_id} - 删除角色
- POST /auth/login - 用户登录
- POST /auth/register - 用户注册
- GET /auth/users - 获取用户列表
- PUT /auth/profile - 更新个人资料
- PUT /auth/password - 修改密码
"""

import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    """登录请求模型。"""
    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


class RegisterRequest(BaseModel):
    """注册请求模型。"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    display_name: Optional[str] = Field(default=None, max_length=50, description="显示名称")


class UpdateProfileRequest(BaseModel):
    """更新资料请求模型。"""
    user_id: int = Field(..., ge=1, description="用户ID")
    display_name: Optional[str] = Field(default=None, max_length=50, description="显示名称")


class ChangePasswordRequest(BaseModel):
    """修改密码请求模型。"""
    user_id: int = Field(..., ge=1, description="用户ID")
    old_password: str = Field(..., min_length=1, description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")


class CharacterCreateRequest(BaseModel):
    """创建角色请求模型。"""
    character_id: str = Field(..., min_length=1, max_length=50, description="角色ID")
    name: str = Field(..., min_length=1, max_length=50, description="角色名称")
    description: Optional[str] = Field(default="", description="角色描述")
    system_prompt: Optional[str] = Field(default="", description="系统提示词")
    avatar_url: Optional[str] = Field(default=None, max_length=255, description="头像URL")
    is_default: bool = Field(default=False, description="是否默认角色")


# ---------------------------------------------------------------------------
# 全局状态引用（由 main.py 注入）
# ---------------------------------------------------------------------------
_db_initialized: bool = False
_startup_time: float = 0.0
_processor: Optional[Any] = None


def set_system_refs(db_initialized: bool, startup_time: float, processor: Any) -> None:
    """设置系统引用，由 main.py 在初始化后调用。
    
    Args:
        db_initialized: 数据库是否已初始化
        startup_time: 启动时间戳
        processor: ConcurrentTaskProcessor 实例
    """
    global _db_initialized, _startup_time, _processor
    _db_initialized = db_initialized
    _startup_time = startup_time
    _processor = processor


# ---------------------------------------------------------------------------
# API 端点：健康检查
# ---------------------------------------------------------------------------
@router.get("/api/health", summary="健康检查")
async def health_check() -> Dict[str, Any]:
    """返回系统健康状态，包含工具数量、数据库状态、版本号。"""
    tools_count: int = 0
    try:
        from tools.tool_manager import ToolManager
        tm = ToolManager.get_instance()
        tools_count = len(tm._tools)
    except Exception:
        pass

    return {
        "status": "healthy",
        "version": "3.3.0",
        "tools_count": tools_count,
        "db_initialized": _db_initialized,
        "uptime_seconds": round(time.time() - _startup_time, 2) if _startup_time else 0,
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# API 端点：角色列表
# ---------------------------------------------------------------------------
@router.get("/api/characters", summary="列出所有角色")
async def list_characters() -> Dict[str, Any]:
    """返回所有可用角色。优先从数据库读取，失败时使用内置默认列表。"""
    if not _db_initialized:
        return _default_characters()

    try:
        from core.database import get_session, Character
        session = get_session()
        try:
            characters = session.query(Character).all()
            if not characters:
                return _default_characters()
            return {
                "characters": [
                    {
                        "character_id": c.character_id,
                        "name": c.name,
                        "description": c.description,
                        "is_default": c.is_default,
                        "system_prompt": c.system_prompt,
                        "avatar_url": c.avatar_url,
                    }
                    for c in characters
                ]
            }
        finally:
            session.close()
    except Exception as e:
        logger.warning("从数据库读取角色失败，使用默认列表: %s", e)
        return _default_characters()


def _default_characters() -> Dict[str, Any]:
    """内置默认角色列表。"""
    return {
        "characters": [
            {"character_id": "default", "name": "小龙虾助手", "description": "默认AI助手", "is_default": True},
            {"character_id": "first_love", "name": "温柔初恋", "description": "温柔体贴的初恋", "is_default": False},
            {"character_id": "bestfriend", "name": "知心闺蜜", "description": "最懂你的闺蜜", "is_default": False},
            {"character_id": "goddess", "name": "高冷女神", "description": "高冷但有内涵", "is_default": False},
            {"character_id": "libai", "name": "诗仙李白", "description": "唐代诗仙", "is_default": False},
        ]
    }


# ---------------------------------------------------------------------------
# API 端点：系统指标
# ---------------------------------------------------------------------------
@router.get("/api/metrics", summary="系统指标")
async def system_metrics() -> Dict[str, Any]:
    """返回系统运行指标，包含并发处理器状态。"""
    metrics: Dict[str, Any] = {
        "version": "3.3.0",
        "db_initialized": _db_initialized,
        "uptime_seconds": round(time.time() - _startup_time, 2) if _startup_time else 0,
        "timestamp": datetime.now().isoformat(),
    }

    # 并发处理器指标
    if _processor is not None:
        try:
            metrics["processor"] = _processor.get_metrics()
        except Exception as e:
            metrics["processor_error"] = str(e)

    # 工具数量
    try:
        from tools.tool_manager import ToolManager
        tm = ToolManager.get_instance()
        metrics["tools_count"] = len(tm._tools)
    except Exception:
        metrics["tools_count"] = 0

    # Redis 状态
    try:
        from core.redis_pool import RedisPoolManager
        rpm = RedisPoolManager.get_instance()
        metrics["redis"] = rpm.health_check_all()
    except Exception:
        metrics["redis"] = {"status": "unavailable"}

    return metrics


# ═══════════════════════════════════════════════════════════════════════════
# API 端点：用户认证
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/auth/login", summary="用户登录")
async def auth_login(request: LoginRequest) -> Dict[str, Any]:
    """用户登录验证。

    验证用户名密码，成功后返回 JWT token 和用户基本信息。
    数据库不可用时使用内置管理员账号 (admin/admin123) 兜底。
    """
    if not _db_initialized:
        logger.warning("数据库未初始化，使用内置管理员验证")
        if request.username == "admin" and request.password == "admin123":
            import datetime as _dt
            import jwt as _jwt
            payload = {
                "sub": "1",
                "username": "admin",
                "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=168),
                "iat": _dt.datetime.utcnow(),
            }
            secret = os.getenv("JWT_SECRET", "xiaolei-jwt-secret-2024")
            token = _jwt.encode(payload, secret, algorithm="HS256")
            return {
                "success": True,
                "token": token,
                "user": {"id": 1, "username": "admin", "display_name": "管理员"},
            }
        return {"success": False, "detail": "数据库未初始化，仅支持 admin/admin123 登录"}

    try:
        from core.database import get_session, User
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
        
        session = get_session()
        try:
            user = session.query(User).filter_by(name=request.username).first()
            if not user:
                return {"success": False, "detail": "用户名或密码错误"}
            if not pwd_context.verify(request.password, user.password):
                return {"success": False, "detail": "用户名或密码错误"}

            import datetime as _dt
            import jwt as _jwt
            payload = {
                "sub": str(user.id),
                "username": user.name,
                "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=168),
                "iat": _dt.datetime.utcnow(),
            }
            secret = os.getenv("JWT_SECRET", "xiaolei-jwt-secret-2024")
            token = _jwt.encode(payload, secret, algorithm="HS256")
            logger.info("用户登录成功: %s (id=%d)", user.name, user.id)
            return {
                "success": True,
                "token": token,
                "user": {
                    "id": user.id,
                    "username": user.name,
                    "display_name": user.name,
                    "email": user.email,
                },
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("登录失败: %s", e)
        return {"success": False, "detail": f"登录失败: {e}"}


@router.post("/auth/register", summary="用户注册")
async def auth_register(request: RegisterRequest) -> Dict[str, Any]:
    """用户注册。

    创建新用户，自动密码哈希。数据库不可用时返回错误。
    """
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化，无法注册"}

    try:
        from core.database import get_session, User
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
        
        session = get_session()
        try:
            existing = session.query(User).filter_by(name=request.username).first()
            if existing:
                return {"success": False, "detail": "用户名已存在"}

            user = User(
                name=request.username,
                password=pwd_context.hash(request.password),
                email=f"{request.username}@example.com",
            )
            session.add(user)
            session.commit()
            logger.info("新用户注册成功: %s (id=%d)", user.name, user.id)
            return {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.name,
                    "display_name": user.name,
                },
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    except Exception as e:
        logger.error("注册失败: %s", e)
        return {"success": False, "detail": f"注册失败: {e}"}


@router.get("/auth/users", summary="获取用户列表")
async def list_users() -> Dict[str, Any]:
    """获取所有用户列表（不含密码）。"""
    if not _db_initialized:
        return {"users": []}
    try:
        from core.database import get_session, User
        session = get_session()
        try:
            users = session.query(User).all()
            return {
                "users": [
                    {
                        "id": u.id,
                        "username": u.username,
                        "display_name": u.display_name,
                        "created_at": u.created_at.isoformat() if u.created_at else None,
                    }
                    for u in users
                ]
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("获取用户列表失败: %s", e)
        return {"users": [], "error": str(e)}


@router.put("/auth/profile", summary="更新个人资料")
async def update_profile(request: UpdateProfileRequest) -> Dict[str, Any]:
    """更新用户显示名称等个人资料。"""
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    try:
        from core.database import get_session, User
        session = get_session()
        try:
            user = session.query(User).filter_by(id=request.user_id).first()
            if not user:
                return {"success": False, "detail": "用户不存在"}
            if request.display_name:
                user.display_name = request.display_name
            session.commit()
            return {"success": True, "display_name": user.display_name}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("更新资料失败: %s", e)
        return {"success": False, "detail": str(e)}


@router.put("/auth/password", summary="修改密码")
async def change_password(request: ChangePasswordRequest) -> Dict[str, Any]:
    """修改用户密码。需验证旧密码。"""
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    try:
        from core.database import get_session, User, verify_password, hash_password
        session = get_session()
        try:
            user = session.query(User).filter_by(id=request.user_id).first()
            if not user:
                return {"success": False, "detail": "用户不存在"}
            if not verify_password(request.old_password, user.password_hash):
                return {"success": False, "detail": "旧密码错误"}
            user.password_hash = hash_password(request.new_password)
            session.commit()
            logger.info("用户 %s (id=%d) 修改密码成功", user.username, user.id)
            return {"success": True}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("修改密码失败: %s", e)
        return {"success": False, "detail": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# API 端点：角色 CRUD
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/api/characters", summary="创建角色")
async def create_character(request: CharacterCreateRequest) -> Dict[str, Any]:
    """创建新的 AI 角色。

    Args:
        request: 角色创建请求体
    """
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    try:
        from core.database import get_session, Character
        session = get_session()
        try:
            existing = session.query(Character).filter_by(
                character_id=request.character_id
            ).first()
            if existing:
                return {"success": False, "detail": f"角色ID '{request.character_id}' 已存在"}
            character = Character(
                character_id=request.character_id,
                name=request.name,
                description=request.description or "",
                system_prompt=request.system_prompt or "",
                avatar_url=request.avatar_url,
                is_default=request.is_default,
            )
            session.add(character)
            session.commit()
            logger.info("角色创建成功: %s (%s)", request.name, request.character_id)
            return {
                "success": True,
                "character": {
                    "character_id": character.character_id,
                    "name": character.name,
                    "description": character.description,
                    "system_prompt": character.system_prompt,
                    "avatar_url": character.avatar_url,
                    "is_default": character.is_default,
                },
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("创建角色失败: %s", e)
        return {"success": False, "detail": str(e)}


@router.put("/api/characters/{character_id}", summary="更新角色")
async def update_character(character_id: str, request: CharacterCreateRequest) -> Dict[str, Any]:
    """更新现有角色的信息。

    Args:
        character_id: 角色ID
        request: 角色更新请求体
    """
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    try:
        from core.database import get_session, Character
        session = get_session()
        try:
            character = session.query(Character).filter_by(
                character_id=character_id
            ).first()
            if not character:
                return {"success": False, "detail": f"角色 '{character_id}' 不存在"}
            character.name = request.name
            character.description = request.description or character.description
            character.system_prompt = request.system_prompt or character.system_prompt
            if request.avatar_url is not None:
                character.avatar_url = request.avatar_url
            character.is_default = request.is_default
            session.commit()
            logger.info("角色更新成功: %s", character_id)
            return {"success": True, "character_id": character_id}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("更新角色失败: %s", e)
        return {"success": False, "detail": str(e)}


@router.delete("/api/characters/{character_id}", summary="删除角色")
async def delete_character(character_id: str) -> Dict[str, Any]:
    """删除指定角色（不可删除默认角色 default）。

    Args:
        character_id: 角色ID
    """
    if character_id == "default":
        return {"success": False, "detail": "默认角色不可删除"}
    if not _db_initialized:
        return {"success": False, "detail": "数据库未初始化"}
    try:
        from core.database import get_session, Character
        session = get_session()
        try:
            character = session.query(Character).filter_by(
                character_id=character_id
            ).first()
            if not character:
                return {"success": False, "detail": f"角色 '{character_id}' 不存在"}
            session.delete(character)
            session.commit()
            logger.info("角色删除成功: %s", character_id)
            return {"success": True, "deleted": character_id}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("删除角色失败: %s", e)
        return {"success": False, "detail": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# API 端点：用户反馈
# ═══════════════════════════════════════════════════════════════════════════

class FeedbackRequest(BaseModel):
    """用户反馈请求模型。"""
    task: str = Field(..., description="原始任务描述")
    skill_used: str = Field(..., description="使用的技能名称")
    success: bool = Field(..., description="是否成功")
    comment: Optional[str] = Field(default="", description="用户评论")
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="评分（1-5星）")


@router.post("/api/feedback", summary="提交用户反馈")
async def submit_feedback(request: FeedbackRequest) -> Dict[str, Any]:
    """提交用户反馈，用于持续学习。

    Args:
        request: 反馈请求体
    """
    try:
        from core.task_processor import task_processor
        from core.continuous_learning import get_learner
        
        await task_processor.record_feedback(request.task, request.skill_used, request.success)
        
        learner = get_learner()
        await learner.learn_from_execution(request.task, request.skill_used, request.comment or "", request.success)
        
        logger.info(f"用户反馈已记录: task='{request.task[:30]}' skill='{request.skill_used}' success={request.success}")
        
        return {
            "success": True,
            "message": "反馈已收到，感谢您的意见！",
            "data": {
                "task": request.task,
                "skill_used": request.skill_used,
                "success": request.success,
                "comment": request.comment,
                "rating": request.rating
            }
        }
    except Exception as e:
        logger.error("提交反馈失败: %s", e)
        return {"success": False, "detail": str(e)}


@router.get("/api/feedback/stats", summary="获取反馈统计")
async def get_feedback_stats() -> Dict[str, Any]:
    """获取用户反馈统计信息。"""
    try:
        from core.task_processor import task_processor
        
        summary = task_processor.get_feedback_summary()
        
        return {
            "success": True,
            "data": summary
        }
    except Exception as e:
        logger.error("获取反馈统计失败: %s", e)
        return {"success": False, "detail": str(e)}


@router.get("/api/learning/stats", summary="获取学习统计")
async def get_learning_stats() -> Dict[str, Any]:
    """获取持续学习系统的统计信息。"""
    try:
        from core.continuous_learning import get_learner
        
        learner = get_learner()
        stats = learner.learning_engine.get_learning_stats()
        
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error("获取学习统计失败: %s", e)
        return {"success": False, "detail": str(e)}
