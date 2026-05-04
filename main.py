"""小雷版小龙虾 AI Agent 系统 - 主入口

工业级 FastAPI 应用，提供：
- RESTful API 端点（健康检查 / 工具列表 / 角色管理 / 核心聊天）
- 用户认证（登录 / 注册 / 个人资料 / 修改密码）
- 聊天历史记录（按用户/角色分页查询）
- 任务日志（按用户/状态分页查询）
- 角色完整 CRUD（创建 / 读取 / 更新 / 删除）
- WebSocket 实时通信
- 请求日志中间件
- 系统指标监控

Version: 3.3.1
"""

import asyncio
import os
import time
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

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
    version="3.3.1",
    description="工业级 AI Agent 系统 - 意图识别 / 多步任务 / 工作流自动化 / 用户管理",
)

# 从环境变量读取CORS配置
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost,http://127.0.0.1").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 挂载静态文件
# ---------------------------------------------------------------------------
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info("静态文件目录已挂载: %s", static_dir)
else:
    logger.warning("静态文件目录不存在: %s", static_dir)

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
_dispatcher: Optional[Any] = None
_processor: Optional[Any] = None
_planner: Optional[Any] = None
_db_initialized: bool = False
_startup_time: float = 0.0


# ---------------------------------------------------------------------------
# 请求日志中间件
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """记录每个 HTTP 请求的方法、路径和耗时。"""
    start = time.time()
    method: str = request.method
    path: str = request.url.path

    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed = time.time() - start
        logger.error("请求异常 %s %s (%.3fs): %s", method, path, elapsed, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "内部服务器错误"},
        )

    elapsed = time.time() - start
    logger.info(
        "%s %s → %d (%.3fs)",
        method,
        path,
        response.status_code,
        elapsed,
    )
    return response


# ---------------------------------------------------------------------------
# 系统初始化
# ---------------------------------------------------------------------------
def init_system() -> None:
    """初始化系统核心组件。"""
    global _dispatcher, _processor, _planner, _db_initialized, _startup_time
    _startup_time = time.time()

    # 1. 注册所有技能
    try:
        from tools.tool_manager import register_all_skills
        register_all_skills()
        logger.info("技能注册完成")
    except Exception as e:
        logger.error("技能注册失败: %s", e, exc_info=True)

    # 2. 初始化 SkillDispatcher
    try:
        from core.skill_dispatcher import SkillDispatcher
        _dispatcher = SkillDispatcher()
        try:
            from skills.third_party.handler import register_third_party_skills
            register_third_party_skills(_dispatcher)
            logger.info("第三方应用技能注册完成")
        except Exception as e:
            logger.warning("第三方应用技能注册失败: %s", e)
        logger.info("SkillDispatcher 初始化完成")
    except Exception as e:
        logger.error("SkillDispatcher 初始化失败: %s", e, exc_info=True)

    # 3. 初始化 ConcurrentTaskProcessor
    try:
        from core.concurrent_processor import ConcurrentTaskProcessor
        _processor = ConcurrentTaskProcessor()
        logger.info("ConcurrentTaskProcessor 初始化完成")
    except Exception as e:
        logger.error("ConcurrentTaskProcessor 初始化失败: %s", e, exc_info=True)

    # 3.5 初始化 TaskPlanner
    try:
        from core.task_planner import TaskPlanner
        _planner = TaskPlanner()
        logger.info("TaskPlanner 初始化完成")
    except Exception as e:
        logger.error("TaskPlanner 初始化失败: %s", e, exc_info=True)

    # 4-17. 其他组件初始化（简化显示）
    components = [
        ("TaskProcessor", "core.task_processor", "task_processor"),
        ("深度思考引擎", "core.reasoning_engine", "get_reasoning_engine"),
        ("自主搜索引擎", "core.search_engine", "get_self_search_engine"),
        ("消息总线", "core.message_bus", "message_bus"),
        ("边界管理器", "core.boundary_manager", "boundary_manager"),
        ("异常处理器", "core.exception_handler", "exception_handler"),
        ("响应管理器", "core.response_manager", "response_manager"),
        ("Agent协调器", "core.agent_coordinator", "agent_coordinator"),
        ("持久化管理器", "core.persistence", "persistence_manager"),
        ("监控管理器", "core.monitoring", "monitoring_manager"),
        ("内存优化器", "core.memory_optimizer", "memory_optimizer"),
        ("缓存管理器", "core.cache_manager", "get_cache_manager"),
    ]
    
    for name, module, obj in components:
        try:
            mod = __import__(module, fromlist=[obj])
            getattr(mod, obj)() if callable(getattr(mod, obj)) else getattr(mod, obj)
            if name == "监控管理器":
                getattr(mod, obj).start()
            elif name == "内存优化器":
                getattr(mod, obj).start()
            logger.info(f"{name}初始化完成")
        except Exception as e:
            logger.error(f"{name}初始化失败: {e}", exc_info=True)

    # 任务调度器（异步启动）
    try:
        from core.task_scheduler import task_scheduler
        import asyncio
        asyncio.create_task(task_scheduler.start())
        logger.info("任务调度器初始化完成")
    except Exception as e:
        logger.error("任务调度器初始化失败: %s", e, exc_info=True)

    # 定时任务
    try:
        from core.scheduled_tasks import init_scheduled_tasks
        init_scheduled_tasks()
        logger.info("定时任务初始化完成")
    except Exception as e:
        logger.error("定时任务初始化失败: %s", e, exc_info=True)

    # 18. 初始化数据库
    try:
        from core.database import init_db
        init_db()
        _db_initialized = True
        logger.info("MySQL 数据库初始化完成")
    except Exception as e:
        _db_initialized = False
        logger.warning("MySQL 数据库初始化失败（系统仍可运行）: %s", e)

    # 19. 注入全局引用到 handlers
    try:
        from core.handlers import set_global_refs
        set_global_refs(_dispatcher, _processor, _planner, _db_initialized)
        logger.info("Handlers 全局引用设置完成")
    except Exception as e:
        logger.error("Handlers 全局引用设置失败: %s", e, exc_info=True)
    
    # 19.5. 注入任务执行接口引用
    try:
        from core.task_execution_interface import set_task_handlers
        from core.multi_agent_system import TextAnalyzerAgent
        from core.handlers import handle_multi_step, handle_single_step
        set_task_handlers(TextAnalyzerAgent, handle_multi_step, handle_single_step)
        logger.info("任务执行接口引用注入完成")
    except Exception as e:
        logger.error("任务执行接口引用注入失败: %s", e, exc_info=True)

    # 20. 注入全局引用到 system 路由
    try:
        from api.routes.system import set_system_refs
        set_system_refs(_db_initialized, _startup_time, _processor)
        logger.info("System 路由全局引用设置完成")
    except Exception as e:
        logger.error("System 路由全局引用设置失败: %s", e, exc_info=True)

    uptime = time.time() - _startup_time
    logger.info("=" * 60)
    logger.info("  小雷版小龙虾 AI Agent v3.3.1 启动成功！")
    logger.info("  初始化耗时: %.2fs | DB: %s", uptime, "OK" if _db_initialized else "OFF")
    logger.info("=" * 60)


@app.on_event("startup")
async def startup_event() -> None:
    """FastAPI 启动事件。"""
    init_system()
    
    # ✅ 新增：从数据库加载短期记忆（按用户ID）
    try:
        from core.handlers import short_term_memory
        from core.database import get_session, BFSContextNode
        
        session = get_session()
        # 获取所有有记忆的用户ID
        user_ids = session.query(BFSContextNode.user_id).distinct().all()
        session.close()
        
        for (user_id,) in user_ids:
            logger.info("🔄 正在为用户 %s 加载短期记忆...", user_id)
            short_term_memory.load_from_db(user_id)
        
        logger.info("✅ 短期记忆加载完成，共恢复 %d 个用户的记忆", len(user_ids))
    except Exception as e:
        logger.warning("短期记忆加载失败（首次启动或数据库未就绪）: %s", e)
    
    try:
        from core.agent_coordinator import get_agent_coordinator
        agent_coordinator = get_agent_coordinator()
        await agent_coordinator.start()
        logger.info("Agent协调器初始化完成")
    except Exception as e:
        logger.error("Agent协调器初始化失败: %s", e, exc_info=True)
    
    try:
        from core.multi_agent_system import agent_scheduler
        await agent_scheduler.start()
        logger.info("Agent调度器已启动")
    except Exception as e:
        logger.error("Agent调度器启动失败: %s", e, exc_info=True)


# ---------------------------------------------------------------------------
# 注册路由模块
# ---------------------------------------------------------------------------
try:
    from api.routes.chat import router as chat_router
    app.include_router(chat_router)
    logger.info("聊天API路由已注册")
except Exception as e:
    logger.warning(f"聊天API路由注册失败: {e}")

try:
    from api.routes.history import router as history_router
    app.include_router(history_router)
    logger.info("历史记录API路由已注册")
except Exception as e:
    logger.warning(f"历史记录API路由注册失败: {e}")

try:
    from api.routes.system import router as system_router
    app.include_router(system_router)
    logger.info("系统API路由已注册")
except Exception as e:
    logger.warning(f"系统API路由注册失败: {e}")

try:
    from api.workflow import router as workflow_router
    app.include_router(workflow_router)
    logger.info("工作流API路由已注册")
except Exception as e:
    logger.warning(f"工作流API路由注册失败: {e}")

try:
    from api.schedule import router as schedule_router
    app.include_router(schedule_router)
    logger.info("定时任务API路由已注册")
except Exception as e:
    logger.warning(f"定时任务API路由注册失败: {e}")

try:
    from api.monitor import router as monitor_router
    app.include_router(monitor_router)
    logger.info("监控API路由已注册")
except Exception as e:
    logger.warning(f"监控API路由注册失败: {e}")

try:
    from api.routes.skills import router as skills_router
    app.include_router(skills_router)
    logger.info("技能管理API路由已注册")
except Exception as e:
    logger.warning(f"技能管理API路由注册失败: {e}")

try:
    from api.routes.agent_groups import router as agent_groups_router
    app.include_router(agent_groups_router)
    logger.info("Agent小组管理API路由已注册")
except Exception as e:
    logger.warning(f"Agent小组管理API路由注册失败: {e}")

try:
    from api.routes.self_check import router as self_check_router
    app.include_router(self_check_router)
    logger.info("自我校验API路由已注册")
except Exception as e:
    logger.warning(f"自我校验API路由注册失败: {e}")

try:
    from api.routes.plans import router as plans_router
    app.include_router(plans_router)
    logger.info("计划管理API路由已注册")
except Exception as e:
    logger.warning(f"计划管理API路由注册失败: {e}")

# ---------------------------------------------------------------------------
# Web 界面路由
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, summary="系统首页")
async def index_page():
    templates_dir = Path(__file__).parent / "templates"
    index_html = templates_dir / "index.html"
    if index_html.exists():
        with open(index_html, "r", encoding="utf-8") as f:
            return f.read()
    return "<html><body><h1>系统首页文件不存在</h1></body></html>"

@app.get("/chat_page", response_class=HTMLResponse, summary="聊天界面")
@app.get("/chat", response_class=HTMLResponse, summary="聊天界面")
async def chat_page():
    templates_dir = Path(__file__).parent / "templates"
    chat_html = templates_dir / "chat.html"
    if chat_html.exists():
        with open(chat_html, "r", encoding="utf-8") as f:
            return f.read()
    return "<html><body><h1>聊天界面文件不存在</h1></body></html>"

@app.get("/monitor", response_class=HTMLResponse, summary="监控界面")
async def monitor_page():
    templates_dir = Path(__file__).parent / "templates"
    monitor_html = templates_dir / "monitor.html"
    if monitor_html.exists():
        with open(monitor_html, "r", encoding="utf-8") as f:
            return f.read()
    return "<html><body><h1>监控界面文件不存在</h1></body></html>"

@app.get("/coze", response_class=HTMLResponse, summary="AI Agent低代码平台")
async def coze_page():
    templates_dir = Path(__file__).parent / "templates"
    coze_html = templates_dir / "coze.html"
    if coze_html.exists():
        with open(coze_html, "r", encoding="utf-8") as f:
            return f.read()
    return "<html><body><h1>AI Agent低代码平台文件不存在</h1></body></html>"


# ==================== 技能列表 API ====================

def get_all_skills() -> List[Dict[str, Any]]:
    """获取所有技能信息"""
    skills_dir = Path(__file__).parent / "skills"
    skills = []
    
    if not skills_dir.exists():
        return skills
    
    for item in skills_dir.iterdir():
        if item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding='utf-8')
                    
                    # 提取技能信息
                    skill_name = item.name
                    description = ""
                    keywords = []
                    
                    lines = content.split('\n')
                    in_description = False
                    in_keywords = False
                    
                    for line in lines:
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


# 技能列表（延迟加载）
_skills_cache = None
_skills_cache_loaded = False

def get_cached_skills() -> list:
    """延迟加载技能列表"""
    global _skills_cache, _skills_cache_loaded
    if not _skills_cache_loaded:
        _skills_cache = get_all_skills()
        _skills_cache_loaded = True
        logger.info("加载了 %d 个技能", len(_skills_cache))
    return _skills_cache


@app.get("/api/skills")
async def get_skills_api():
    """获取所有技能API"""
    return JSONResponse({
        'success': True,
        'data': get_cached_skills()
    })


@app.get("/api/skills/search")
async def search_skills_api(q: str = ""):
    """搜索技能API"""
    query = q.lower()
    skills = get_cached_skills()
    
    if not query:
        return JSONResponse({
            'success': True,
            'data': skills
        })
    
    # 搜索匹配的技能
    filtered_skills = []
    for skill in skills:
        # 匹配技能名称
        if query in skill['name'].lower():
            filtered_skills.append(skill)
            continue
        
        # 匹配显示名称
        if query in skill['display_name'].lower():
            filtered_skills.append(skill)
            continue
        
        # 匹配关键词
        for keyword in skill['keywords']:
            if query in keyword.lower():
                filtered_skills.append(skill)
                break
    
    return JSONResponse({
        'success': True,
        'data': filtered_skills
    })


@app.get("/workflow_editor", response_class=HTMLResponse, summary="智能工作流编辑器")
async def workflow_editor_page():
    """提供工作流编辑器页面"""
    templates_dir = Path(__file__).parent / "templates"
    workflow_html = templates_dir / "workflow_editor.html"
    if workflow_html.exists():
        with open(workflow_html, "r", encoding="utf-8") as f:
            return f.read()
    return "<html><body><h1>工作流编辑器文件不存在</h1></body></html>"


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    
    # 从环境变量读取配置
    port: int = int(os.getenv("AGENT_PORT", "8001"))
    host: str = os.getenv("AGENT_HOST", "0.0.0.0")
    log_level: str = os.getenv("LOG_LEVEL", "info")
    
    # 开发模式配置
    reload: bool = os.getenv("DEV_MODE", "false").lower() == "true"
    reload_dirs = ["api", "core", "skills", "tools"] if reload else None
    
    logger.info("=" * 70)
    logger.info("🚀 小雷版小龙虾 AI Agent v3.3.1")
    logger.info("=" * 70)
    logger.info(f"📡 服务地址: http://{host}:{port}")
    logger.info(f"🔧 日志级别: {log_level}")
    logger.info(f"♻️  热重载: {'✅ 已启用' if reload else '❌ 未启用'}")
    logger.info(f"📂 重载目录: {', '.join(reload_dirs) if reload_dirs else 'N/A'}")
    logger.info("=" * 70)
    logger.info("")
    logger.info("💡 提示:")
    logger.info("   - 访问工作流编辑器: http://localhost:{}/workflow_editor".format(port))
    logger.info("   - 访问 Coze 聊天: http://localhost:{}/coze".format(port))
    logger.info("   - API 文档: http://localhost:{}/docs".format(port))
    logger.info("   - 启用热重载: export DEV_MODE=true && python main.py")
    logger.info("")
    
    # 启动服务
    try:
        uvicorn.run(
            app, 
            host=host, 
            port=port, 
            log_level=log_level,
            reload=reload,
            reload_dirs=reload_dirs
        )
    except KeyboardInterrupt:
        logger.info("\n👋 服务已停止")
    except Exception as e:
        logger.error(f"❌ 服务启动失败: {e}")
        raise
