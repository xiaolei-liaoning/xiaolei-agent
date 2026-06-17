"""轻量 API Key 认证中间件。

使用方式（main.py）:
    from api.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)

环境变量:
    API_KEY=<密钥>        # 启用认证，未设置时跳过（向后兼容）
    API_KEY_NAME=X-Api-Key  # 自定义 header 名，默认 X-Api-Key

ponytail: 标准库 + FastAPI 原生 middleware，零外部依赖。
"""
from __future__ import annotations

import os
import logging

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# ── 静态路径白名单（无需认证）───────────────────────────────────────────────
SKIP_PATHS = frozenset({
    "/docs",
    "/openapi.json",
    "/redoc",
    "/health",
    "/favicon.ico",
})

SKIP_PREFIXES = tuple([
    "/static/",
])


class AuthMiddleware(BaseHTTPMiddleware):
    """检查请求中的 API Key，未配置时直接放行。"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.api_key = os.getenv("API_KEY", "").strip()
        self.header_name = os.getenv("API_KEY_NAME", "X-Api-Key")
        self.enabled = bool(self.api_key)

        if self.enabled:
            # 不打印密钥本身，避免日志泄露
            logger.info("API Key 认证已启用 (header: %s)", self.header_name)
        else:
            logger.info("API Key 认证未配置，所有请求放行（向后兼容模式）")

    async def dispatch(self, request: Request, call_next):
        # ── 未启用 → 直接放行 ──────────────────────────────────────────
        if not self.enabled:
            return await call_next(request)

        # ── 白名单路径 → 放行 ──────────────────────────────────────────
        path = request.url.path.rstrip("/") or "/"
        if path in SKIP_PATHS or path.startswith(SKIP_PREFIXES):
            return await call_next(request)

        # ── 从请求头中提取 Key ──────────────────────────────────────────
        # 支持 Authorization: Bearer <key> 和自定义 header
        auth_header = request.headers.get("Authorization", "")
        provided = request.headers.get(self.header_name, "")

        if auth_header.startswith("Bearer "):
            provided = provided or auth_header[len("Bearer "):]

        if not provided:
            logger.warning("认证失败: 缺少 API Key (path=%s)", path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API Key"},
            )

        if provided != self.api_key:
            logger.warning("认证失败: API Key 不匹配 (path=%s)", path)
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API Key"},
            )

        return await call_next(request)
