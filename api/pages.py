"""HTML 页面端点 — 提取自 main.py"""
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["页面"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _read_template(name: str) -> str:
    """读取模板文件，不存在时返回占位消息。"""
    path = TEMPLATES_DIR / name
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return f"<html><body><h1>{name} 文件不存在</h1></body></html>"


@router.get("/", response_class=HTMLResponse, summary="系统首页")
async def index_page():
    return _read_template("index.html")


@router.get("/chat_page", response_class=HTMLResponse, summary="聊天界面")
@router.get("/chat", response_class=HTMLResponse, summary="聊天界面")
async def chat_page():
    return _read_template("chat.html")


@router.get("/monitor", response_class=HTMLResponse, summary="监控界面")
async def monitor_page():
    return _read_template("monitor.html")


@router.get("/coze", response_class=HTMLResponse, summary="AI Agent低代码平台")
async def coze_page():
    return _read_template("coze.html")


@router.get("/workflow_editor", response_class=HTMLResponse, summary="智能工作流编辑器")
async def workflow_editor_page():
    return _read_template("workflow_editor.html")
