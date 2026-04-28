"""聊天相关API路由

包含：
- POST /api/chat - 核心聊天API
- POST /api/upload - 文件上传API
- WebSocket /ws/chat - 实时聊天端点
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from pydantic import BaseModel, Field

from core.handlers import (
    handle_automation_workflow,
    handle_multi_step,
    handle_multi_step_streaming,
    handle_single_step,
    save_chat_history,
    save_task_log,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    """聊天请求模型。"""
    message: str = Field(..., min_length=1, description="用户消息")
    user_id: int = Field(default=1, ge=1, description="用户ID")
    agent_id: str = Field(default="default", description="Agent ID")
    agent_name: str = Field(default="小龙虾助手", description="Agent 名称")
    file_paths: Optional[List[str]] = Field(default=None, description="已上传文件的路径列表")


class ChatResponse(BaseModel):
    """聊天响应模型。"""
    reply: str = Field(..., description="回复内容")
    tool_call: Optional[Dict[str, Any]] = Field(default=None, description="工具调用信息")
    skill: Optional[str] = Field(default=None, description="匹配的技能名")
    task_id: Optional[str] = Field(default=None, description="任务ID")


class UploadResponse(BaseModel):
    """文件上传响应模型。"""
    success: bool = Field(..., description="是否成功")
    file_path: str = Field(..., description="保存的文件路径")
    filename: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    message: str = Field(default="", description="附加消息")


# ---------------------------------------------------------------------------
# API 端点：核心聊天
# ---------------------------------------------------------------------------
@router.post("/chat", response_model=ChatResponse, summary="核心聊天API")
async def chat(request: ChatRequest) -> ChatResponse:
    """核心聊天 API 入口。

    处理流程：
    1. match_skill 意图识别
    2. 根据匹配结果分发到不同处理器：
       - advanced_automation → 工作流处理
       - multi_step → 多步任务（规则 → GLM → 执行）
       - 其他 → 单步执行 / 闲聊
    3. 如果有上传的文件，优先处理文件相关请求
    """
    from core.skill_dispatcher import SkillDispatcher
    
    message: str = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    dispatcher = SkillDispatcher.get_instance() if hasattr(SkillDispatcher, 'get_instance') else None
    
    # 尝试从全局状态获取dispatcher
    try:
        from core.handlers import _dispatcher as global_dispatcher
        if global_dispatcher is None:
            raise HTTPException(status_code=503, detail="系统尚未初始化完成，请稍后重试")
        dispatcher = global_dispatcher
    except ImportError:
        raise HTTPException(status_code=503, detail="系统尚未初始化完成，请稍后重试")

    start_time: float = time.time()
    
    # 如果用户上传了文件，检查是否需要 OCR 或其他文件处理
    if request.file_paths and len(request.file_paths) > 0:
        logger.info("检测到上传的文件: %s", request.file_paths)
        
        # 检查是否包含 OCR 相关的关键词
        ocr_keywords = ['ocr', '识别', '文字识别', '图片识别', '提取文字']
        is_ocr_request = any(keyword in message.lower() for keyword in ocr_keywords)
        
        # 如果是 OCR 请求，直接调用 OCR 处理
        if is_ocr_request:
            try:
                from skills.data_analysis.handler import DataAnalysisHandler
                
                handler = DataAnalysisHandler()
                file_path = request.file_paths[0]  # 取第一个文件
                
                logger.info("开始 OCR 识别: %s", file_path)
                
                result = handler.execute(
                    action="ocr",
                    file_path=file_path
                )
                
                elapsed = time.time() - start_time
                logger.info("OCR 识别完成，耗时: %.2fs", elapsed)
                
                reply_text = result.get('reply', 'OCR 识别完成')
                
                # 保存聊天历史
                save_chat_history(request.user_id, request.agent_id, "user", message)
                save_chat_history(request.user_id, request.agent_id, "assistant", reply_text, {
                    "name": "ocr_recognition",
                    "file_path": file_path,
                    "success": result.get('success', False)
                })
                
                return ChatResponse(
                    reply=reply_text,
                    tool_call={"name": "ocr_recognition", "params": {"file_path": file_path}},
                    skill="data_analysis",
                )
                
            except Exception as e:
                logger.error("OCR 处理失败: %s", e, exc_info=True)
                return ChatResponse(
                    reply=f"❌ OCR 识别失败: {str(e)}\n\n请确保已安装 PaddleOCR:\npip install paddleocr paddlepaddle",
                    skill="error",
                )
    
    # 正常的技能匹配流程
    skill_name: str = dispatcher.match_skill(message)
    logger.info("消息: %s... → 匹配技能: %s", message[:50], skill_name)

    try:
        reply_text: str = ""
        actual_skill: str = skill_name
        tool_call_info: Optional[Dict[str, Any]] = None
        task_success: bool = True

        # 高级自动化工作流
        if skill_name == "advanced_automation":
            result = await handle_automation_workflow(message, request.user_id)
            elapsed = time.time() - start_time
            logger.info("工作流完成，耗时: %.2fs", elapsed)
            reply_text = result.get("reply", str(result))
            actual_skill = "automation_workflow"
            tool_call_info = {"name": "automation_workflow", "params": {"message": message}}
            task_success = result.get("success", False)
            save_task_log(request.user_id, actual_skill, task_success,
                         tool_call_info, {"reply": reply_text}, elapsed)

        # 多步任务
        elif skill_name == "multi_step":
            result = await handle_multi_step(message, request.user_id)
            elapsed = time.time() - start_time
            logger.info("多步任务完成，耗时: %.2fs", elapsed)
            reply_text = result.get("reply", str(result))
            actual_skill = "multi_step"
            tool_call_info = {"name": "multi_step", "params": {}}
            save_task_log(request.user_id, actual_skill, task_success,
                         tool_call_info, {"reply": reply_text}, elapsed)

        # 单步任务
        else:
            result = await handle_single_step(
                message, request.user_id, skill_name, request.agent_id
            )
            elapsed = time.time() - start_time
            logger.info("任务完成 [%s]，耗时: %.2fs", skill_name, elapsed)
            reply_text = result.get("reply", "处理完成")
            tool_call_info = result.get("tool_call")
            task_success = result.get("success", True)
            if skill_name != "chat":
                save_task_log(request.user_id, skill_name, task_success,
                             tool_call_info, result, elapsed)

        # 保存聊天历史（异步，不阻塞响应）
        save_chat_history(request.user_id, request.agent_id, "user", message)
        save_chat_history(request.user_id, request.agent_id, "assistant", reply_text, tool_call_info)

        return ChatResponse(
            reply=reply_text,
            tool_call=tool_call_info,
            skill=actual_skill,
        )

    except Exception as e:
        logger.error("聊天处理失败: %s", e, exc_info=True)
        return ChatResponse(
            reply=f"抱歉，处理出了点问题：{e}",
            skill="error",
        )


# ---------------------------------------------------------------------------
# API 端点：文件上传
# ---------------------------------------------------------------------------
@router.post("/upload", response_model=UploadResponse, summary="文件上传API")
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    """文件上传 API 入口。

    支持图片、文档等格式的文件上传，用于后续的 OCR 识别和数据分析。
    
    Args:
        file: 上传的文件
        
    Returns:
        UploadResponse: 包含文件路径、大小等信息
    """
    try:
        # 验证文件类型
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', 
                            '.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx'}
        file_ext = Path(file.filename).suffix.lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的文件类型: {file_ext}。支持的类型: {', '.join(allowed_extensions)}"
            )
        
        # 验证文件大小（最大 10MB）
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE // (1024*1024)}MB）"
            )
        
        # 保存文件到指定目录
        upload_dir = Path("uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名，避免冲突
        import uuid
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        safe_filename = f"{timestamp}_{unique_id}{file_ext}"
        file_path = upload_dir / safe_filename
        
        with file_path.open("wb") as f:
            f.write(content)
        
        logger.info("文件上传成功: %s (%d bytes)", safe_filename, len(content))
        
        return UploadResponse(
            success=True,
            file_path=str(file_path),
            filename=file.filename,
            file_size=len(content),
            message="文件上传成功"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("文件上传失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


# ---------------------------------------------------------------------------
# API 端点：批量文件上传
# ---------------------------------------------------------------------------
@router.post("/upload/batch", summary="批量文件上传API")
async def upload_batch(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """批量文件上传 API。
    
    Args:
        files: 上传的文件列表
        
    Returns:
        包含所有上传结果的字典
    """
    results = []
    errors = []
    
    for file in files:
        try:
            # 复用单个上传逻辑
            result = await upload(file)
            results.append({
                "filename": result.filename,
                "file_path": result.file_path,
                "success": True
            })
        except Exception as e:
            errors.append({
                "filename": file.filename,
                "error": str(e),
                "success": False
            })
    
    return {
        "success": len(errors) == 0,
        "uploaded": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors
    }


# ---------------------------------------------------------------------------
# WebSocket 端点：实时聊天
# ---------------------------------------------------------------------------
@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket 实时聊天端点。

    协议：
    - 接收 JSON: {"message": str, "user_id": int, "character_id": str}
    - 发送 JSON: {"reply": str, "skill": str, "success": bool}
    - 心跳: 每 30s ping，客户端需 pong
    """
    await websocket.accept()
    client_id: str = f"ws_{id(websocket)}"
    logger.info("WebSocket 客户端已连接: %s", client_id)

    # 获取dispatcher
    try:
        from core.handlers import _dispatcher as global_dispatcher
        if global_dispatcher is None:
            await websocket.send_json({
                "reply": "系统尚未初始化完成，请稍后重试",
                "skill": "error",
                "success": False,
            })
            await websocket.close(code=1013, reason="Service Unavailable")
            return
        dispatcher = global_dispatcher
    except ImportError:
        await websocket.send_json({
            "reply": "系统尚未初始化完成，请稍后重试",
            "skill": "error",
            "success": False,
        })
        await websocket.close(code=1013, reason="Service Unavailable")
        return

    try:
        while True:
            # 带超时接收，支持心跳
            try:
                data: str = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # 发送心跳 ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue

            # 解析请求
            try:
                request_data: Dict[str, Any] = json.loads(data)
                message: str = request_data.get("message", "")
                user_id: int = request_data.get("user_id", 1)
                agent_id: str = request_data.get("agent_id", "default")
            except (json.JSONDecodeError, TypeError):
                message = data
                user_id = 1
                agent_id = "default"

            if not message.strip():
                await websocket.send_json({
                    "reply": "消息不能为空",
                    "skill": "error",
                    "success": False,
                })
                continue

            # 意图识别与分发
            skill_name: str = dispatcher.match_skill(message)

            try:
                if skill_name == "advanced_automation":
                    result = await handle_automation_workflow(message, user_id)
                    await websocket.send_json({
                        "reply": result.get("reply", "处理完成"),
                        "skill": skill_name,
                        "success": result.get("success", True),
                    })
                elif skill_name == "multi_step":
                    # 多步任务：逐个发送JSON响应
                    sub_results = await handle_multi_step_streaming(message, user_id, websocket)
                    # 最后发送聚合结果
                    await websocket.send_json({
                        "reply": sub_results.get("reply", "多步任务完成"),
                        "skill": "multi_step",
                        "success": sub_results.get("success", True),
                        "is_aggregated": True,
                    })
                else:
                    result = await handle_single_step(
                        message, user_id, skill_name, agent_id
                    )

                    await websocket.send_json({
                        "reply": result.get("reply", "处理完成"),
                        "skill": skill_name,
                        "success": result.get("success", True),
                    })
            except Exception as e:
                logger.error("WebSocket 消息处理失败: %s", e)
                await websocket.send_json({
                    "reply": f"处理失败: {e}",
                    "skill": "error",
                    "success": False,
                })

    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开: %s", client_id)
    except Exception as e:
        logger.info("WebSocket 连接异常关闭: %s (%s)", client_id, e)
    finally:
        logger.info("WebSocket 连接清理完成: %s", client_id)
