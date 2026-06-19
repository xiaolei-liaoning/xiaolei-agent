"""HTML 页面端点 — 单页面聊天"""
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["页面"])

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/", response_class=HTMLResponse, summary="聊天页面")
@router.get("/chat", response_class=HTMLResponse, summary="聊天页面")
async def chat_page():
    return FileResponse(str(STATIC_DIR / "simple.html"), media_type="text/html")
