"""聊天相关API路由

包含：
- POST /api/chat - 核心聊天API
- POST /api/upload - 文件上传API
- WebSocket /ws/chat - 实时聊天端点
- POST /api/chat/context - 获取对话上下文
- POST /api/chat/clear - 清除对话上下文
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
from core.bfs_processor import get_bfs_processor
from core.intelligent_agent_selector import get_intelligent_selector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# ---------------------------------------------------------------------------
# 辅助函数：处理图片文件（OCR识别）
# ---------------------------------------------------------------------------
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}

def _is_image_file(file_path: str) -> bool:
    """判断文件是否是图片"""
    ext = Path(file_path).suffix.lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS

async def _process_image_files(file_paths: List[str]) -> tuple[str, List[Dict[str, Any]]]:
    """处理图片文件，执行OCR识别

    Args:
        file_paths: 文件路径列表

    Returns:
        (附加文本, OCR结果列表)
    """
    if not file_paths:
        return "", []

    ocr_results = []
    additional_text_parts = []

    for file_path in file_paths:
        if not _is_image_file(file_path):
            logger.info(f"跳过非图片文件: {file_path}")
            continue

        if not Path(file_path).exists():
            logger.warning(f"文件不存在: {file_path}")
            continue

        try:
            logger.info(f"开始OCR识别: {file_path}")

            from skills.data_analysis.handler import DataAnalysisHandler
            handler = DataAnalysisHandler()

            result = await handler.execute(
                action="ocr",
                image_path=file_path,
                language="chi_sim+eng"
            )

            if result.get("success"):
                ocr_text = result.get("result", {}).get("text", "")
                if ocr_text:
                    ocr_results.append({
                        "file_path": file_path,
                        "text": ocr_text,
                        "success": True
                    })
                    additional_text_parts.append(f"[图片OCR识别结果 from {Path(file_path).name}]\n{ocr_text}")
                    logger.info(f"OCR识别成功: {file_path}, 字符数: {len(ocr_text)}")
                else:
                    ocr_results.append({
                        "file_path": file_path,
                        "text": "",
                        "success": False,
                        "error": "未识别到文字"
                    })
            else:
                ocr_results.append({
                    "file_path": file_path,
                    "text": "",
                    "success": False,
                    "error": result.get("error", "未知错误")
                })
                logger.warning(f"OCR识别失败: {file_path}, 错误: {result.get('error')}")

        except Exception as e:
            logger.error(f"OCR处理异常: {file_path}, 错误: {e}")
            ocr_results.append({
                "file_path": file_path,
                "text": "",
                "success": False,
                "error": str(e)
            })

    additional_text = "\n\n".join(additional_text_parts) if additional_text_parts else ""
    return additional_text, ocr_results


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
    auto_agent_selection: bool = Field(default=True, description="是否启用智能Agent自动选择（取代agent小组）")


class ChatResponse(BaseModel):
    """聊天响应模型。"""
    reply: str = Field(..., description="回复内容")
    tool_call: Optional[Dict[str, Any]] = Field(default=None, description="工具调用信息")
    skill: Optional[str] = Field(default=None, description="匹配的技能名")
    task_id: Optional[str] = Field(default=None, description="任务ID")
    message_id: Optional[int] = Field(default=None, description="AI回复的消息ID（用于点赞）")
    thinking_process: Optional[Dict[str, Any]] = Field(default=None, description="AI思考过程")
    context_info: Optional[Dict[str, Any]] = Field(default=None, description="使用的上下文信息")
    agents_used: Optional[List[str]] = Field(default=None, description="实际使用的Agent列表（智能选择）")
    execution_plan: Optional[Dict[str, Any]] = Field(default=None, description="执行计划信息（智能选择）")
    md_path: Optional[str] = Field(default=None, description="MD报告路径（爬虫/搜索结果）")  # ✅ 新增
    ocr_results: Optional[List[Dict[str, Any]]] = Field(default=None, description="图片OCR识别结果列表")  # 🖼️ 新增


class UploadResponse(BaseModel):
    """文件上传响应模型。"""
    success: bool = Field(..., description="是否成功")
    file_path: str = Field(..., description="保存的文件路径")
    filename: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    message: str = Field(default="", description="附加消息")


class ContextRequest(BaseModel):
    """获取上下文请求模型。"""
    user_id: int = Field(default=1, ge=1, description="用户ID")
    depth: int = Field(default=3, ge=1, le=10, description="对话深度")
    limit: int = Field(default=20, ge=1, le=100, description="返回记录数")


# ---------------------------------------------------------------------------
# 内部函数：判断是否需要走Agent（智能版本）
# ---------------------------------------------------------------------------
def _needs_agent(message: str) -> bool:
    """判断是否需要走Agent系统（基于智能选择器）

    完全根据任务复杂度自动判断：
    - TRIVIAL/SIMPLE → 不需要Agent，直接走SkillDispatcher
    - MODERATE/COMPLEX/VERY_COMPLEX → 需要Agent，走Agent系统
    """
    try:
        selector = get_intelligent_selector()
        plan = selector.create_execution_plan(message)

        # 根据复杂度判断是否需要Agent
        # TRIVIAL 和 SIMPLE 复杂度不需要Agent
        if plan.complexity.value in ["trivial", "simple"]:
            return False

        # MODERATE 及以上复杂度需要Agent
        return True

    except Exception as e:
        # 如果智能选择失败，降级到关键词判断
        logger.warning(f"智能判断失败，降级到关键词判断: {e}")
        message_lower = message.lower()
        complex_keywords = [
            "深度思考", "深入分析", "详细分析", "研究", "最新动态",
            "分析一下", "研究一下", "怎么分析", "如何分析",
            "为什么", "为什么是", "原因是什么", "分析原因",
            "对比", "比较", "评估", "预测", "趋势",
            "生成报告", "写一份", "方案", "规划",
        ]
        for kw in complex_keywords:
            if kw in message_lower:
                return True
        return False


# ---------------------------------------------------------------------------
# 内部函数：获取BFS上下文
# ---------------------------------------------------------------------------
def _get_bfs_context(user_id: int, depth: int = 3, limit: int = 20) -> Dict[str, Any]:
    """获取用户的BFS上下文信息"""
    try:
        bfs = get_bfs_processor()
        context = bfs.get_context(user_id=user_id, depth=depth, limit=limit)

        # 提取关键信息
        context_summary = {
            'has_context': len(context) > 0,
            'message_count': len(context),
            'recent_messages': [
                {
                    'role': msg.get('role', ''),
                    'content_preview': msg.get('content', '')[:50],
                    'timestamp': msg.get('created_at', '')
                }
                for msg in context[:5]
            ]
        }
        return context_summary
    except Exception as e:
        logger.warning("获取BFS上下文失败: %s", e)
        return {'has_context': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# API 端点：核心聊天
# ---------------------------------------------------------------------------
@router.post("/chat", response_model=ChatResponse, summary="核心聊天API")
async def chat(request: ChatRequest) -> ChatResponse:
    """核心聊天 API 入口

    流程决策：
    - 简单任务 → SkillDispatcher → 直接执行 Skill（跳过 Agent）
    - 复杂任务（深度思考等）→ ChatAgent 系统

    特性：
    - 使用BFS管理上下文
    - 支持MessageBus通信
    - 集成RAG引擎
    - 智能Agent自动选择（auto_agent_selection=True时启用）
    """
    message: str = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    start_time: float = time.time()

    # 获取BFS上下文信息
    context_info = _get_bfs_context(request.user_id, depth=3, limit=10)

    # 智能Agent自动选择（如果启用）
    execution_plan_info = None
    agents_used = None
    if request.auto_agent_selection:
        try:
            selector = get_intelligent_selector()
            execution_plan = selector.create_execution_plan(message)
            execution_plan_info = {
                "complexity": execution_plan.complexity.value,
                "execution_mode": execution_plan.execution_mode.value,
                "agent_count": execution_plan.agent_count,
                "agents": execution_plan.agents,
                "estimated_time": execution_plan.estimated_time,
                "strategy": execution_plan.strategy,
                "auto_selected": True
            }
            agents_used = execution_plan.agents
            logger.info(f"智能选择: {execution_plan.strategy}")
        except Exception as e:
            logger.warning(f"智能选择失败: {e}")

    # 判断是否需要走Agent
    if _needs_agent(message):
        # 复杂任务 → 走Agent系统
        return await _handle_with_agent(request, message, start_time, context_info, execution_plan_info, agents_used)
    else:
        # 简单任务 → 直接走SkillDispatcher
        return await _handle_direct(request, message, start_time, context_info, execution_plan_info, agents_used)


async def _handle_with_agent(
    request: ChatRequest,
    message: str,
    start_time: float,
    context_info: Dict[str, Any],
    execution_plan_info: Optional[Dict[str, Any]],
    agents_used: Optional[List[str]]
) -> ChatResponse:
    """通过Agent系统处理复杂任务，集成BFS上下文管理和智能选择"""
    try:
        logger.info("复杂任务，通过Agent系统处理: %s...", message[:50])

        from core.multi_agent_system import ChatAgent, AgentTask

        # 保存用户消息到BFS上下文
        try:
            bfs = get_bfs_processor()
            bfs.add_node(user_id=request.user_id, role="user", content=message)
            logger.debug("已添加用户消息到BFS上下文")
        except Exception as e:
            logger.warning("添加到BFS上下文失败: %s", e)

        # 🖼️ 处理图片文件（OCR识别）
        ocr_results = []
        if request.file_paths:
            logger.info(f"检测到上传文件数量: {len(request.file_paths)}")
            ocr_text, ocr_results = await _process_image_files(request.file_paths)
            if ocr_text:
                message = f"{message}\n\n{ocr_text}"
                logger.info(f"已将OCR结果附加到消息，追加字符数: {len(ocr_text)}")

        chat_agent = ChatAgent()
        task = AgentTask(
            id=f"chat_{int(time.time()*1000)}",
            type="chat",
            params={
                "message": message,
                "user_id": request.user_id,
                "agent_id": request.agent_id,
                "agent_name": request.agent_name
            }
        )

        result = await chat_agent._run_task(task)

        elapsed = time.time() - start_time
        logger.info("Agent系统处理完成，耗时: %.2fs", elapsed)

        reply_text = result.get("reply", "任务已完成")
        skill_name = result.get("skill", "agent_system")
        thinking_process = result.get("thinking_process")
        md_path = result.get("md_path")  # ✅ 新增

        # 保存聊天历史
        save_chat_history(request.user_id, request.agent_id, "user", message)
        save_chat_history(request.user_id, request.agent_id, "assistant", reply_text, {
            "skill": skill_name,
            "elapsed": elapsed
        })

        # 保存到BFS上下文
        try:
            bfs = get_bfs_processor()
            bfs.add_node(user_id=request.user_id, role="assistant", content=reply_text)
            logger.debug("已添加AI回复到BFS上下文")
        except Exception as e:
            logger.warning("添加AI回复到BFS上下文失败: %s", e)

        return ChatResponse(
            reply=reply_text,
            skill=skill_name,
            thinking_process=thinking_process,
            context_info=context_info,
            agents_used=agents_used,
            execution_plan=execution_plan_info,
            md_path=md_path,  # ✅ 新增
            ocr_results=ocr_results if 'ocr_results' in dir() and ocr_results else None  # 🖼️ 新增
        )

    except Exception as e:
        logger.error(f"Agent系统异常，降级到直接处理: {e}", exc_info=True)
        return await _handle_direct(request, message, start_time, context_info, execution_plan_info, agents_used)


async def _handle_direct(
    request: ChatRequest,
    message: str,
    start_time: float,
    context_info: Dict[str, Any],
    execution_plan_info: Optional[Dict[str, Any]],
    agents_used: Optional[List[str]]
) -> ChatResponse:
    """直接通过SkillDispatcher处理简单任务，跳过Agent，集成BFS上下文管理和智能选择"""
    try:
        from core.handlers import _dispatcher
        if _dispatcher is None:
            raise HTTPException(status_code=503, detail="系统尚未初始化完成")

        # 保存用户消息到BFS上下文
        try:
            bfs = get_bfs_processor()
            bfs.add_node(user_id=request.user_id, role="user", content=message)
            logger.debug("已添加用户消息到BFS上下文")
        except Exception as e:
            logger.warning("添加到BFS上下文失败: %s", e)

        # 🖼️ 处理图片文件（OCR识别）
        ocr_results = []
        if request.file_paths:
            logger.info(f"检测到上传文件数量: {len(request.file_paths)}")
            ocr_text, ocr_results = await _process_image_files(request.file_paths)
            if ocr_text:
                message = f"{message}\n\n{ocr_text}"
                logger.info(f"已将OCR结果附加到消息，追加字符数: {len(ocr_text)}")

        skill_name: str = _dispatcher.match_skill(message)
        logger.info("[直接] 匹配技能: %s", skill_name)

        reply_text: str = ""
        actual_skill: str = skill_name
        tool_call_info: Optional[Dict[str, Any]] = None
        task_success: bool = True
        thinking_process = None
        md_path = None  # ✅ 新增

        # 高级自动化工作流
        if skill_name == "advanced_automation":
            result = await handle_automation_workflow(message, request.user_id)
            elapsed = time.time() - start_time
            logger.info("[直接] 工作流完成，耗时: %.2fs", elapsed)
            reply_text = result.get("reply", str(result))
            actual_skill = "automation_workflow"
            tool_call_info = {"name": "automation_workflow", "params": {"message": message}}
            task_success = result.get("success", False)

        # 多步任务
        elif skill_name == "multi_step":
            result = await handle_multi_step(message, request.user_id)
            elapsed = time.time() - start_time
            logger.info("[直接] 多步任务完成，耗时: %.2fs", elapsed)
            reply_text = result.get("reply", str(result))
            actual_skill = "multi_step"
            tool_call_info = {"name": "multi_step", "params": {}}

        # 单步任务
        else:
            result = await handle_single_step(
                message,
                request.user_id,
                skill_name,
                request.agent_id
            )
            elapsed = time.time() - start_time
            logger.info("[直接] 任务完成 [%s]，耗时: %.2fs", skill_name, elapsed)
            reply_text = result.get("reply", "处理完成")
            tool_call_info = result.get("tool_call")
            task_success = result.get("success", True)
            md_path = result.get("md_path")  # ✅ 新增

            # 提取thinking_process（如果存在）
            if skill_name == "deep_thinking" and result.get("result"):
                result_data = result.get("result")
                if isinstance(result_data, dict):
                    thinking_process = result_data.get("thinking_process")

        # 保存聊天历史
        save_chat_history(request.user_id, request.agent_id, "user", message)
        save_chat_history(request.user_id, request.agent_id, "assistant", reply_text, tool_call_info)

        # 保存到BFS上下文
        try:
            bfs = get_bfs_processor()
            bfs.add_node(user_id=request.user_id, role="assistant", content=reply_text)
            logger.debug("已添加AI回复到BFS上下文")
        except Exception as e:
            logger.warning("添加AI回复到BFS上下文失败: %s", e)

        # 保存任务日志
        save_task_log(request.user_id, actual_skill, task_success,
                     tool_call_info, {"reply": reply_text}, time.time() - start_time)

        return ChatResponse(
            reply=reply_text,
            tool_call=tool_call_info,
            skill=actual_skill,
            thinking_process=thinking_process,
            context_info=context_info,
            agents_used=agents_used,
            execution_plan=execution_plan_info,
            md_path=md_path,  # ✅ 新增
            ocr_results=ocr_results if 'ocr_results' in dir() and ocr_results else None  # 🖼️ 新增
        )

    except Exception as e:
        logger.error("处理失败: %s", e, exc_info=True)
        error_reply = f"抱歉，处理您的请求时出错: {str(e)}"
        save_chat_history(request.user_id, request.agent_id, "user", message)
        save_chat_history(request.user_id, request.agent_id, "assistant", error_reply)
        return ChatResponse(
            reply=error_reply,
            skill="error",
            agents_used=agents_used,
            execution_plan=execution_plan_info
        )


# ---------------------------------------------------------------------------
# API 端点：上下文管理
# ---------------------------------------------------------------------------
@router.post("/chat/context", summary="获取对话上下文")
async def get_context(request: ContextRequest):
    """获取用户对话上下文"""
    try:
        bfs = get_bfs_processor()
        context = bfs.get_context(
            user_id=request.user_id,
            depth=request.depth,
            limit=request.limit
        )

        return {
            "success": True,
            "data": {
                "user_id": request.user_id,
                "message_count": len(context),
                "messages": context,
                "depth": request.depth,
                "limit": request.limit
            }
        }
    except Exception as e:
        logger.error("获取上下文失败: %s", e, exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/chat/clear_context", summary="清除对话上下文")
async def clear_context(request: ContextRequest):
    """清除用户对话上下文"""
    try:
        # 尝试从数据库清除
        try:
            from core.database import get_session, ChatHistory
            session = get_session()
            if session:
                count = session.query(ChatHistory).filter(ChatHistory.user_id == request.user_id).delete()
                session.commit()
                session.close()
                logger.info("已清除用户 %d 的 %d 条历史记录", request.user_id, count)
        except Exception as e:
            logger.warning("清除数据库历史失败: %s", e)

        # 清除内存中的上下文（如果有）
        try:
            from core.handlers import short_term_memory
            short_term_memory.clear_for_user(request.user_id)
        except Exception as e:
            logger.warning("清除短期记忆失败: %s", e)

        return {
            "success": True,
            "message": "上下文已清除",
            "user_id": request.user_id
        }
    except Exception as e:
        logger.error("清除上下文失败: %s", e, exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


# ---------------------------------------------------------------------------
# API 端点：文件上传
# ---------------------------------------------------------------------------
@router.post("/upload", response_model=UploadResponse, summary="文件上传API")
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    """文件上传 API 入口。"""
    try:
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff',
                            '.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx'}
        file_ext = Path(file.filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {file_ext}"
            )

        MAX_FILE_SIZE = 10 * 1024 * 1024
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE // (1024*1024)}MB）"
            )

        upload_dir = Path("uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

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


@router.post("/upload/batch", summary="批量文件上传API")
async def upload_batch(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """批量文件上传 API。"""
    results = []
    errors = []

    for file in files:
        try:
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
    """WebSocket 实时聊天端点。"""
    await websocket.accept()
    client_id: str = f"ws_{id(websocket)}"
    logger.info("WebSocket 客户端已连接: %s", client_id)

    try:
        from core.handlers import _dispatcher
        if _dispatcher is None:
            await websocket.send_json({
                "reply": "系统尚未初始化完成",
                "skill": "error",
                "success": False,
            })
            await websocket.close(code=1013)
            return
    except ImportError:
        await websocket.send_json({
            "reply": "系统尚未初始化完成",
            "skill": "error",
            "success": False,
        })
        await websocket.close(code=1013)
        return

    try:
        while True:
            try:
                data: str = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue

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

            # 判断是否需要Agent
            if _needs_agent(message):
                # 复杂任务 → 走Agent（这里简化处理）
                await websocket.send_json({
                    "reply": "该任务需要深度处理，请使用HTTP API",
                    "skill": "agent",
                    "success": False,
                })
                continue

            # 简单任务 → 直接处理
            skill_name: str = _dispatcher.match_skill(message)

            try:
                if skill_name == "advanced_automation":
                    result = await handle_automation_workflow(message, user_id)
                    reply_text = result.get("reply", "处理完成")
                    tool_call_info = {"name": "automation_workflow", "params": {"message": message}}
                    thinking_process = result.get("thinking_process")

                    await websocket.send_json({
                        "reply": reply_text,
                        "skill": skill_name,
                        "success": result.get("success", True),
                        "thinking_process": thinking_process,
                    })
                elif skill_name == "multi_step":
                    sub_results = await handle_multi_step_streaming(message, user_id, websocket)
                    reply_text = sub_results.get("reply", "多步任务完成")
                    await websocket.send_json({
                        "reply": reply_text,
                        "skill": "multi_step",
                        "success": sub_results.get("success", True),
                        "is_aggregated": True,
                    })
                else:
                    result = await handle_single_step(message, user_id, skill_name, agent_id)
                    reply_text = result.get("reply", "处理完成")
                    tool_call_info = result.get("tool_call")

                    await websocket.send_json({
                        "reply": reply_text,
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
