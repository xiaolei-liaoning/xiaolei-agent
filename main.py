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
# 系统初始化
# ---------------------------------------------------------------------------
from core.engine.system_init import SystemInitializer


async def init_system() -> None:
    # 修复 #005: 加异常保护 — 其他 startup 步骤都有 try/except，唯独 init_system 是裸调
    try:
        await SystemInitializer(app, ctx).initialize()
    except Exception as e:
        logger.error(f"init_system 失败: {e}", exc_info=True)
        # 不 raise — 让应用继续启动，但 ctx.db_initialized 等标志位可能是 False
        # 下游应该检查 ctx.db_initialized 来决定是否能用 DB 功能


# ---------------------------------------------------------------------------
# Lifespan 上下文管理器（替代旧的 on_event 模式）
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — startup/yield/shutdown"""
    await init_system()

    # WebSocket 心跳检测
    try:
        from api.routes.chat_ws import manager
        await manager.start_heartbeat_check()
        logger.info("WebSocket 心跳检测已启动")
    except Exception as e:
        logger.warning("WebSocket 心跳检测启动失败: %s", e)

    # 加载短期记忆（文件式存储，无需显式加载，按需读取）

    # 文件 watcher
    try:
        from core.watcher_setup import setup_file_watcher
        setup_file_watcher(app)
    except Exception as e:
        logger.warning("文件watcher启动失败: %s", e)

    yield   # ← 应用开始服务请求

    # ── shutdown ──
    try:
        from api.routes.chat_ws import manager
        await manager.stop_heartbeat_check()
        logger.info("WebSocket 心跳检测已停止")
    except Exception as e:
        logger.warning("WebSocket 心跳检测停止失败: %s", e)

    try:
        from core.watcher_setup import shutdown_file_watcher
        shutdown_file_watcher(app)
    except Exception as e:
        logger.warning("文件watcher停止失败: %s", e)


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------
app = FastAPI(
    title="小雷版小龙虾 AI Agent",
    version="3.4.0",
    description="工业级 AI Agent 系统 - 意图识别 / 多步任务 / 工作流自动化 / 用户管理",
    lifespan=lifespan,
)

# CORS — 修复 #007: 修复浏览器规范冲突
# 浏览器规范：当 allow_credentials=True 时，allow_origins 不能是 "*"
# 解决方案：开发环境用显式列表（localhost 多端口），生产环境从 env 读
import os as _cors_os
_dev_origins = [
    "http://localhost:8001", "http://127.0.0.1:8001",
    "http://localhost:5500", "http://127.0.0.1:5500",  # Live Server
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:5173", "http://127.0.0.1:5173",  # Vite
]
_prod_origins = _cors_os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if _cors_os.getenv("CORS_ALLOWED_ORIGINS") else []
is_dev = _cors_os.getenv("DEV_MODE", "false").lower() == "true"
allow_origins = _dev_origins if is_dev else (_prod_origins or _dev_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
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
    """应用级依赖容器。

    修复 #006: 3 字段真在用 — V1 报告怀疑从未被赋值是错的。
    实际使用（实测 grep 全仓）:
      - ctx.dispatcher = SkillDispatcher()           # system_init.py:73
      - ctx.processor  = ConcurrentTaskProcessor()   # system_init.py:83
      - ctx.planner    = TaskPlanner()              # system_init.py:91
      - set_global_refs(ctx.dispatcher, ctx.processor, ctx.planner, ...)  # system_init.py:167

    V2 时代保留这 3 个字段是为了兼容 set_global_refs 旧调用链，
    unified_agent.run_unified() 内部已经不走 dispatcher/processor/planner。
    """
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
# 启动入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("AGENT_PORT", "8001"))
    host = os.getenv("AGENT_HOST", "0.0.0.0")
    log_level = os.getenv("LOG_LEVEL", "info")
    reload = os.getenv("DEV_MODE", "false").lower() == "true"
    # 修复 #008: 补全 6 个目录，漏的 cli/mcp/config/prompts/plugin/infrastructure 之前都列在二阶段扫描计划里
    reload_dirs = ["api", "core", "tools", "cli", "mcp", "config", "prompts", "plugin", "infrastructure"] if reload else None

    logger.info("=" * 70)
    logger.info("🚀 小雷版小龙虾 AI Agent v3.4.0")
    logger.info("=" * 70)
    logger.info(f"📡 服务地址: http://{host}:{port}")
    logger.info(f"🔧 日志级别: {log_level}")
    logger.info(f"♻️  热重载: {'✅ 已启用' if reload else '❌ 未启用'}")
    logger.info(f"📂 重载目录: {', '.join(reload_dirs) if reload_dirs else 'N/A'}")
    logger.info("=" * 70)

    # 修复 #009: 端口冲突时给清晰提示 + 可选自动 +1 重试
    actual_port = port
    max_port_attempts = int(os.getenv("MAX_PORT_ATTEMPTS", "0"))  # 0=不重试
    for attempt in range(max_port_attempts + 1):
        try:
            uvicorn.run(
                app, host=host, port=actual_port, log_level=log_level,
                reload=reload, reload_dirs=reload_dirs,
            )
            break
        except OSError as e:
            # 端口占用 (errno 48) 或绑定失败
            if "address already in use" in str(e).lower() or "errno 98" in str(e).lower() or "errno 48" in str(e).lower():
                if attempt < max_port_attempts:
                    actual_port += 1
                    logger.warning(f"端口 {actual_port - 1} 被占用，自动尝试 {actual_port}")
                    continue
                logger.error(
                    f"❌ 端口 {port} 被占用（已尝试 {max_port_attempts} 次失败）。\n"
                    f"   建议：\n"
                    f"   1) lsof -i :{port} 找占用进程并 kill\n"
                    f"   2) 改环境变量 AGENT_PORT={port + 1}\n"
                    f"   3) 设 MAX_PORT_ATTEMPTS=5 让程序自动找下一个空端口"
                )
                raise
            raise
        except KeyboardInterrupt:
            logger.info("\n👋 服务已停止")
        except Exception as e:
            logger.error(f"❌ 服务启动失败: {e}")
            raise
