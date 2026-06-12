"""路由管理器 — 集中式路由注册"""
import importlib
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# 集中式路由清单
ROUTE_MANIFEST = [
    ("api.routes.chat", "router"),
    ("api.routes.chat_ws", "ws_router"),
    ("api.routes.history", "router"),
    ("api.routes.system", "router"),
    ("api.workflow", "router"),
    ("api.schedule", "router"),
    ("api.monitor", "router"),
    ("api.routes.skills", "router"),
    ("api.routes.agent_groups", "router"),
    ("api.routes.agent_groups_collab", "collab_router"),
    ("api.routes.self_check", "router"),
    ("api.routes.plans", "router"),
    ("api.routes.frontend_agent", "router"),
    ("api.routes.simple_chat", "router"),  # 简化聊天 API
]


def register_routes(app) -> Dict[str, Any]:
    """注册所有路由到 FastAPI 应用。

    Args:
        app: FastAPI 应用实例

    Returns:
        {模块名: 是否成功} 字典
    """
    results = {}
    for module_path, router_attr in ROUTE_MANIFEST:
        try:
            mod = importlib.import_module(module_path)
            router = getattr(mod, router_attr)
            app.include_router(router)
            tag = module_path.split(".")[-1]
            results[tag] = True
            logger.info("路由注册成功: %s", module_path)
        except Exception as e:
            tag = module_path.split(".")[-1]
            results[tag] = False
            logger.warning("路由注册失败 %s: %s", module_path, e)
    return results


# 动态路由 — 供 watcher 在运行时增删路由
_router_index: dict = {}


def mount_route(app, module_name: str) -> bool:
    """动态挂载一个 API 路由模块（从 api/routes/ 发现）"""
    if module_name in _router_index:
        logger.debug("路由 %s 已挂载，跳过", module_name)
        return True
    try:
        mod = importlib.import_module(f"api.routes.{module_name}")
        if hasattr(mod, "router"):
            router = mod.router
            app.include_router(router)
            _router_index[module_name] = router
            logger.info("动态挂载路由: /api/%s", module_name)
            return True
        logger.warning("路由模块 %s 没有 router 对象", module_name)
        return False
    except Exception as e:
        logger.warning("动态挂载路由失败 %s: %s", module_name, e)
        return False


def unmount_route(app, module_name: str) -> bool:
    """动态卸载一个 API 路由模块"""
    router = _router_index.pop(module_name, None)
    if router is None:
        return False
    try:
        prefix = getattr(router, "prefix", f"/api/{module_name}")
        original_count = len(app.routes)
        app.routes[:] = [
            r for r in app.routes
            if not (str(r.path) == prefix or str(r.path).startswith(prefix + "/"))
        ]
        removed_count = original_count - len(app.routes)
        if removed_count > 0:
            logger.info("动态卸载路由: /api/%s (移除 %d 条路由)", module_name, removed_count)
        return removed_count > 0
    except Exception as e:
        logger.warning("动态卸载路由失败 %s: %s", module_name, e)
        return False
