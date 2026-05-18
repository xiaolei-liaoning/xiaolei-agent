"""API路由模块 — 支持动态自发现

导出所有路由路由器，便于在 main.py 中注册。
discover_routes() 用于运行时动态挂载/卸载路由。
"""

import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

from api.routes.chat import router as chat_router
from api.routes.history import router as history_router
from api.routes.system import router as system_router
from api.routes.self_check import router as self_check_router
from api.routes.plans import router as plans_router

__all__ = ["chat_router", "history_router", "system_router", "self_check_router", "plans_router"]


def discover_routes() -> Dict[str, Any]:
    """扫描 api/routes/ 目录，自发现所有路由模块

    约定：每个 .py 文件必须导出 router 对象（FastAPI APIRouter 实例）。
    返回 {模块名: router} 映射表，供 watcher 和 main.py 使用。
    """
    routes = {}
    routes_dir = Path(__file__).parent

    for entry in sorted(routes_dir.iterdir()):
        if not entry.is_file() or entry.suffix != ".py":
            continue
        if entry.name.startswith("_") or entry.name.startswith("."):
            continue

        mod_name = entry.stem  # 去掉 .py
        try:
            mod = __import__(f"api.routes.{mod_name}", fromlist=["router"])
            if hasattr(mod, "router"):
                routes[mod_name] = mod.router
                logger.debug("发现路由模块: %s", mod_name)
        except Exception as e:
            logger.warning("发现路由模块 %s 失败: %s", mod_name, e)

    return routes
