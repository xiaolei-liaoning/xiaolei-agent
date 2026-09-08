"""路由管理器 — 集中式路由注册"""
import importlib
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# 集中式路由清单（仅保留核心功能：聊天、WebSocket、历史）
ROUTE_MANIFEST = [
    ("api.routes.chat", "router"),
    ("api.routes.chat_ws", "ws_router"),
    ("api.routes.history", "router"),
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
# 记录 {module_name: {"router": router, "routes_before": [include前的app.routes快照]}}
# 卸载时移除 include 后新增的路由——FastAPI include_router 会深拷贝路由对象，
# 不能按 router.routes 对象身份移除；也不能按 path 前缀过滤（chat/chat_ws 的 prefix 都是 /api 会互相误删）
_router_index: dict = {}


def mount_route(app, module_name: str) -> bool:
    """动态挂载一个 API 路由模块（从 api/routes/ 发现）"""
    if module_name in _router_index:
        logger.debug("路由 %s 已挂载，跳过", module_name)
        return True
    try:
        mod = importlib.import_module(f"api.routes.{module_name}")
        # 不同模块的 router 属性名不同: chat.py→router, chat_ws.py→ws_router
        # 逐个探测, 兼容 ROUTE_MANIFEST 里声明的任意属性名
        router = None
        for attr_name in ("router", "ws_router", "api_router", "ws_api_router"):
            if hasattr(mod, attr_name):
                router = getattr(mod, attr_name)
                break
        if router is not None:
            routes_before = list(app.routes)
            app.include_router(router)
            _router_index[module_name] = {
                "router": router,
                "routes_before": routes_before,
            }
            logger.info("动态挂载路由: /api/%s", module_name)
            return True
        logger.warning("路由模块 %s 没有 router/ws_router 对象", module_name)
        return False
    except Exception as e:
        logger.warning("动态挂载路由失败 %s: %s", module_name, e)
        return False


def unmount_route(app, module_name: str) -> bool:
    """动态卸载一个 API 路由模块

    移除 include_router 后新增的路由（app.routes 快照差集）。
    不用 router.routes 对象身份（include 时被深拷贝，对不上）；
    不用 path 前缀过滤（chat/chat_ws 等 prefix 同为 /api 会互相误删）。
    """
    entry = _router_index.pop(module_name, None)
    if entry is None:
        return False
    try:
        routes_before = entry["routes_before"]
        original_count = len(app.routes)
        app.routes[:] = [r for r in app.routes if r in routes_before]
        removed_count = original_count - len(app.routes)
        if removed_count > 0:
            logger.info("动态卸载路由: /api/%s (移除 %d 条路由)", module_name, removed_count)
        return removed_count > 0
    except Exception as e:
        logger.warning("动态卸载路由失败 %s: %s", module_name, e)
        return False
