"""小雷版小龙虾 AI Agent 系统 - 主入口

工业级 FastAPI 应用，提供 RESTful API、WebSocket、系统监控等。
Version: 3.4.0
"""
import asyncio
import logging
import os
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------
app = FastAPI(
    title="小雷版小龙虾 AI Agent",
    version="3.4.0",
    description="工业级 AI Agent 系统 - 意图识别 / 多步任务 / 工作流自动化 / 用户管理",
)

# CORS — 放宽以支持 Live Server 开发
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info("静态文件目录已挂载: %s", static_dir)
else:
    logger.warning("静态文件目录不存在: %s", static_dir)

# 前端页面路由 — 统一由 api/pages.py 提供
# main.py 不再重复注册 /、/chat、/coze 等页面路由

# ---------------------------------------------------------------------------
# 全局状态（AppContext 模式）
# ---------------------------------------------------------------------------
@dataclass
class AppContext:
    """应用级依赖容器。"""
    dispatcher: Optional[Any] = None
    processor: Optional[Any] = None
    planner: Optional[Any] = None
    db_initialized: bool = False
    startup_time: float = 0.0

ctx = AppContext()

# ---------------------------------------------------------------------------
# 请求日志中间件
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.time()
    method, path = request.method, request.url.path
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed = time.time() - start
        logger.error("请求异常 %s %s (%.3fs): %s", method, path, elapsed, exc)
        return JSONResponse(status_code=500, content={"detail": "内部服务器错误"})
    elapsed = time.time() - start
    logger.info("%s %s → %d (%.3fs)", method, path, response.status_code, elapsed)
    return response

# ---------------------------------------------------------------------------
# 路由注册
# ---------------------------------------------------------------------------
from api.route_manager import register_routes, mount_route, unmount_route
register_routes(app)

# ---------------------------------------------------------------------------
# HTML 页面端点
# ---------------------------------------------------------------------------
from api.pages import router as pages_router
app.include_router(pages_router)

# ---------------------------------------------------------------------------
# 系统初始化
# ---------------------------------------------------------------------------
from core.system_init import SystemInitializer


async def init_system() -> None:
    await SystemInitializer(app, ctx).initialize()


@app.on_event("startup")
async def startup_event() -> None:
    await init_system()

    # WebSocket 心跳检测
    try:
        from api.routes.chat_ws import manager
        await manager.start_heartbeat_check()
        logger.info("WebSocket 心跳检测已启动")
    except Exception as e:
        logger.warning("WebSocket 心跳检测启动失败: %s", e)

    # 加载短期记忆
    try:
        from core.handlers import short_term_memory
        from core.infrastructure.database import get_session, BFSContextNode
        with get_session() as session:
            user_ids = session.query(BFSContextNode.user_id).distinct().all()
        for (user_id,) in user_ids:
            short_term_memory.load_from_db(user_id)
        logger.info("短期记忆加载完成，共恢复 %d 个用户的记忆", len(user_ids))
    except Exception as e:
        logger.warning("短期记忆加载失败（首次启动或数据库未就绪）: %s", e)

    # 文件 watcher
    from core.watcher_setup import setup_file_watcher
    setup_file_watcher(app)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    # WebSocket 心跳停止
    try:
        from api.routes.chat_ws import manager
        await manager.stop_heartbeat_check()
        logger.info("WebSocket 心跳检测已停止")
    except Exception as e:
        logger.warning("WebSocket 心跳检测停止失败: %s", e)

    # 文件 watcher 停止
    from core.watcher_setup import shutdown_file_watcher
    shutdown_file_watcher(app)

# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("AGENT_PORT", "8001"))
    host = os.getenv("AGENT_HOST", "0.0.0.0")
    log_level = os.getenv("LOG_LEVEL", "info")
    reload = os.getenv("DEV_MODE", "false").lower() == "true"
    reload_dirs = ["api", "core", "skills", "tools"] if reload else None

    logger.info("=" * 70)
    logger.info("🚀 小雷版小龙虾 AI Agent v3.4.0")
    logger.info("=" * 70)
    logger.info(f"📡 服务地址: http://{host}:{port}")
    logger.info(f"🔧 日志级别: {log_level}")
    logger.info(f"♻️  热重载: {'✅ 已启用' if reload else '❌ 未启用'}")
    logger.info(f"📂 重载目录: {', '.join(reload_dirs) if reload_dirs else 'N/A'}")
    logger.info("=" * 70)

    try:
        uvicorn.run(
            app, host=host, port=port, log_level=log_level,
            reload=reload, reload_dirs=reload_dirs,
        )
    except KeyboardInterrupt:
        logger.info("\n👋 服务已停止")
    except Exception as e:
        logger.error(f"❌ 服务启动失败: {e}")
        raise
