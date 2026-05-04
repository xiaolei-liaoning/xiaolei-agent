"""API路由模块

导出所有路由路由器，便于在 main.py 中注册。
"""

from api.routes.chat import router as chat_router
from api.routes.history import router as history_router
from api.routes.system import router as system_router
from api.routes.self_check import router as self_check_router
from api.routes.plans import router as plans_router

__all__ = ["chat_router", "history_router", "system_router", "self_check_router", "plans_router"]
