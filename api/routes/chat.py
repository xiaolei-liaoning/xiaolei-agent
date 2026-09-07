"""聊天相关API路由

包含：
- POST /api/chat - 核心聊天API
- POST /api/upload - 文件上传API
- POST /api/chat/context - 获取对话上下文
- POST /api/chat/clear - 清除对话上下文

WebSocket 端点已移至 chat_ws.py。
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

import yaml

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from core.handlers import (
    handle_automation_workflow,
    handle_multi_step,
    handle_single_step,
    save_chat_history,
    save_task_log,
)
from core.memory.conversation_history import get_history_manager
from core.memory.context_compactor import get_compactor


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# WebSocket 连接管理器（从 chat_ws.py 导入，保持向后兼容性）
from api.routes.chat_ws import manager


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
    force_single_agent: bool = Field(default=False, description="强制使用单Agent模式")
    force_multi_agent: bool = Field(default=False, description="强制使用多Agent模式")


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
    """判断是否需要走Agent系统"""
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
# 内部函数：判断是否需要使用多Agent模式（multi_agent_v2）
# ---------------------------------------------------------------------------
def _needs_multi_agent(message: str) -> bool:
    """判断是否需要走 multi_agent_v2 unified_agent（不再是 V1 队长-队员）

    触发条件：
    1. 明确提到"深度思考"、"自主搜索"等深度思考触发词
    2. 需要多技能协作的复杂任务

    注：早期注释说 "V1 队长-队员多Agent系统" 是迁移前的描述，实际跑 V2 unified_agent。
    """
    try:
        from core.engine.skill_dispatcher import SkillDispatcher
        dispatcher = SkillDispatcher()
        return dispatcher.is_multi_agent_required(message)
    except Exception as e:
        logger.warning(f"多Agent检测失败，降级到关键词判断: {e}")
        message_lower = message.lower()
        
        # 明确的深度思考触发词
        deep_thinking_triggers = [
            "深度思考", "自主搜索", "联网查询", "最新信息", 
            "研究一下", "详细分析", "深入探讨", "最新动态",
            "综合分析", "全面评估", "系统分析", "多维度分析"
        ]
        
        if any(trigger in message_lower for trigger in deep_thinking_triggers):
            return True
        
        # 多技能协作需求
        skill_keywords = [
            ("爬取", "分析"), ("抓取", "分析"), ("搜索", "分析"),
            ("收集", "整理"), ("获取", "分析"), ("下载", "分析"),
            ("分析", "生成"), ("整理", "生成"), ("收集", "生成")
        ]
        
        for kw1, kw2 in skill_keywords:
            if kw1 in message_lower and kw2 in message_lower:
                return True
        
        return False


# ---------------------------------------------------------------------------
# 内部函数：获取上下文信息
# ---------------------------------------------------------------------------
def _get_context_info(user_id: int, query: str = "") -> Dict[str, Any]:
    """获取用户的上下文信息（包括向量记忆）

    Args:
        user_id: 用户ID
        query: 查询文本（用于向量检索相关记忆）
    """
    try:
        history = get_history_manager()
        context = history.get_context_info(user_id)

        # 如果有查询，检索相关向量记忆
        if query:
            relevant_memories = history.get_relevant_memories(
                user_id=user_id,
                query=query,
                top_k=5,
            )
            if relevant_memories:
                context["relevant_memories"] = [
                    {
                        "content": m.get("content", "")[:200],
                        "category": m.get("metadata", {}).get("category", "general"),
                        "distance": m.get("distance", 0),
                    }
                    for m in relevant_memories
                ]

        return context
    except Exception as e:
        logger.warning("获取上下文失败: %s", e)
        return {'has_context': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# API 端点：核心聊天
# ---------------------------------------------------------------------------
@router.post("/chat", response_model=ChatResponse, summary="核心聊天API")
async def chat(request: ChatRequest) -> ChatResponse:
    """核心聊天 API 入口

    Web 走 V2 unified_agent 系统（ReAct 循环 + 5 个 profile）。
    注：早期注释说的 "V1 队长-队员多Agent系统（LeaderAgent + LLMAgent）" 已迁移到 V2，
    旧入口 core/agent_system.py 已删除，不要再引用。

    特性：
    - 使用对话历史管理器（自动压缩）
    - 支持 MessageBus 通信
    - 集成 RAG 引擎
    - 智能 Agent 自动选择（auto_agent_selection=True 时启用）
    """
    message: str = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    start_time: float = time.time()

    # 获取上下文信息（包括向量记忆检索）
    context_info = _get_context_info(request.user_id, query=message)

    # 智能 Agent 自动选择（如果启用）
    execution_plan_info = None
    agents_used = None

    # 走 V2 unified_agent 系统（忽略 force_single_agent / force_multi_agent 等旧参数）
    return await _handle_with_multi_agent(request, message, start_time, context_info, execution_plan_info, agents_used)


async def _handle_with_multi_agent(
    request: ChatRequest,
    message: str,
    start_time: float,
    context_info: Dict[str, Any],
    execution_plan_info: Optional[Dict[str, Any]],
    agents_used: Optional[List[str]]
) -> ChatResponse:
    """通过 V2 unified_agent（unified_agent.run_unified）处理 Web 聊天请求"""
    try:
        logger.info("🚀 V2 unified_agent 开始处理: %s...", message[:60])

        # 保存用户消息到对话历史（自动压缩）
        try:
            history = get_history_manager()
            history.add_message(request.user_id, "user", message)
            logger.debug("已添加用户消息到对话历史")
        except Exception as e:
            logger.warning("添加到对话历史失败: %s", e)

        # 处理图片文件（OCR识别）
        ocr_results = []
        if request.file_paths:
            logger.info(f"检测到上传文件数量: {len(request.file_paths)}")
            ocr_text, ocr_results = await _process_image_files(request.file_paths)
            if ocr_text:
                message = f"{message}\n\n{ocr_text}"
                logger.info(f"已将OCR结果附加到消息，追加字符数: {len(ocr_text)}")

        # ========== V2 unified_agent 执行（5 个 profile 都共享 unified_agent.run_unified）==========
        from core.multi_agent_v2.agents.unified_agent import run_unified

        uid = str(request.user_id)

        # ===== 用户记忆：统一中间件 =====
        user_context_str = ""
        try:
            from core.memory.memory_middleware import get_memory_middleware
            mw = get_memory_middleware()
            user_context_str = await mw.get_user_context(uid, message)
        except Exception as e:
            logger.debug("用户记忆获取失败: %s", e)

        task_with_context = message
        if user_context_str:
            task_with_context = (
                f"{message}\n\n【用户已知信息（来自长期记忆）】\n{user_context_str}\n\n"
                "以上信息供参考。请按用户当前要求执行，不要仅凭历史记录作答。"
            )

        try:
            result = await asyncio.wait_for(
                run_unified(
                    task_with_context,
                    max_rounds=3,
                    mode="react",
                    user_id=uid,
                ),
                timeout=120,
            )
        except asyncio.TimeoutError:
            logger.warning("V2 统一 Agent 超时")
            result = {"success": False, "error": "执行超时", "results": [], "rounds": 0, "total_subtasks": 0}

        # ========== 格式化回复 ==========
        success = result.get("success", False)
        all_results = result.get("results", [])
        total_rounds = result.get("rounds", 0)
        total_subtasks = result.get("total_subtasks", 0)

        # 构建回复文本
        reply_parts = []
        if success:
            reply_parts.append(f"✅ 统一Agent 任务完成！共 {total_rounds} 轮，{total_subtasks} 个子任务。\n")
        else:
            reply_parts.append(f"❌ 统一Agent 任务未完全完成（{result.get('error', '未知错误')}）\n")

        # ponytail: 只显示最后一个结果（避免 batch_delegate 中间结果重复显示）
        if all_results:
            r = all_results[-1]
            worker_name = r.get("worker", "leader")
            task_desc = r.get("task", "")
            worker_ok = r.get("success", False)
            worker_result = r.get("result", {})
            status_icon = "✅" if worker_ok else "❌"
            reply_parts.append(f"\n{status_icon} **{worker_name}**: {task_desc[:80]}")
            result_text = ""
            if isinstance(worker_result, dict):
                # ponytail: batch_delegate 结果直接提取各 worker 的 tool_result_summary
                if "batch_results" in worker_result:
                    summaries = []
                    for br in worker_result["batch_results"]:
                        br_data = br.get("result", {})
                        if isinstance(br_data, dict):
                            s = br_data.get("tool_result_summary", br_data.get("content", ""))
                            if s:
                                summaries.append(s)
                    result_text = "\n".join(summaries) if summaries else str(worker_result)[:500]
                elif "result" in worker_result and isinstance(worker_result["result"], dict) and "batch_results" in worker_result["result"]:
                    # process_results 包装后的格式
                    inner = worker_result["result"]
                    summaries = []
                    for br in inner["batch_results"]:
                        br_data = br.get("result", {})
                        if isinstance(br_data, dict):
                            s = br_data.get("tool_result_summary", br_data.get("content", ""))
                            if s:
                                summaries.append(s)
                    result_text = "\n".join(summaries) if summaries else str(inner)[:500]
                else:
                    # ponytail: process_results 返回的 worker_result 结构: {"tool_result_summary": ..., "content": ..., "tool_calls": ...}
                    # tool_result_summary 可能在顶层，也可能在 result 子字段
                    result_text = worker_result.get("tool_result_summary", "")
                    if not result_text and isinstance(worker_result.get("result"), dict):
                        result_text = worker_result["result"].get("tool_result_summary", "")
                    if not result_text and "ok" in worker_result:
                        if worker_result.get("ok"):
                            result_text = worker_result.get("data", "")
                        else:
                            result_text = f"错误: {worker_result.get('error', '未知错误')}"
                    if not result_text:
                        content_raw = worker_result.get("content", "") or worker_result.get("result", "")
                        if content_raw:
                            try:
                                parsed = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
                                if isinstance(parsed, dict):
                                    result_text = parsed.get("result", "") or parsed.get("details", "") or parsed.get("text", "") or (
                                        parsed.get("data", "") if "ok" in parsed else ""
                                    )
                            except (json.JSONDecodeError, TypeError):
                                result_text = content_raw
                    if not result_text and isinstance(worker_result.get("result"), dict):
                        sub = worker_result["result"]
                        result_text = sub.get("content", "") or sub.get("result", "") or sub.get("text", "")
                        if not result_text and "ok" in sub:
                            result_text = sub.get("data", "")
            elif worker_result:
                result_text = str(worker_result)
            if result_text:
                # 截断过长输出，但保留实际数据
                reply_parts.append(f"   {result_text[:3000]}")

        reply_text = "\n".join(reply_parts)

        elapsed = time.time() - start_time
        logger.info("V2 统一Agent 处理完成，耗时: %.2fs, 成功: %s", elapsed, success)

        # 构建 multi_agents_used 列表
        team_names = ["V2 Unified Agent (Leader+Worker)"]

        # 保存聊天历史
        save_chat_history(request.user_id, request.agent_id, "user", message)
        save_chat_history(request.user_id, request.agent_id, "assistant", reply_text, {
            "skill": "v2_unified_agent",
            "elapsed": elapsed,
            "agents_used": team_names,
            "rounds": total_rounds,
            "subtasks": total_subtasks,
            "success": success,
        })

        # 保存AI回复到对话历史
        try:
            history = get_history_manager()
            history.add_message(request.user_id, "assistant", reply_text)
            logger.debug("已添加AI回复到对话历史")
        except Exception as e:
            logger.warning("添加AI回复到对话历史失败: %s", e)

        # ===== 对话结束后：自动提取事实 =====
        try:
            from core.memory.memory_middleware import get_memory_middleware
            mw = get_memory_middleware()
            asyncio.ensure_future(mw.process_turn(uid, message, reply_text))
        except Exception:
            pass

        return ChatResponse(
            reply=reply_text,
            skill="v1_multi_agent",
            thinking_process={
                "mode": "v1_leader_worker",
                "collaboration_mode": "leader_worker",
                "agents_used": team_names,
                "execution_plan": [
                    {"round": r + 1, "subtasks": len(all_results)} for r in range(total_rounds)
                ],
            },
            context_info=context_info,
            agents_used=team_names,
            execution_plan=execution_plan_info,
            ocr_results=ocr_results if ocr_results else None
        )

    except Exception as e:
        # V2 unified_agent 异常，降级到单 Agent 处理（V1 不存在）
        logger.error(f"V2 多Agent 异常，降级到单Agent处理: {e}", exc_info=True)
        return await _handle_with_agent(request, message, start_time, context_info, execution_plan_info, agents_used)


async def _handle_with_agent(
    request: ChatRequest,
    message: str,
    start_time: float,
    context_info: Dict[str, Any],
    execution_plan_info: Optional[Dict[str, Any]],
    agents_used: Optional[List[str]]
) -> ChatResponse:
    """通过Agent系统处理复杂任务，集成对话历史管理和智能选择"""
    try:
        logger.info("复杂任务，通过Agent系统处理: %s...", message[:50])

        from core.tasks.task_processor import task_processor

        # 保存用户消息到对话历史
        try:
            history = get_history_manager()
            history.add_message(request.user_id, "user", message)
            logger.debug("已添加用户消息到对话历史")
        except Exception as e:
            logger.warning("添加到对话历史失败: %s", e)

        # 🖼️ 处理图片文件（OCR识别）
        ocr_results = []
        if request.file_paths:
            logger.info(f"检测到上传文件数量: {len(request.file_paths)}")
            ocr_text, ocr_results = await _process_image_files(request.file_paths)
            if ocr_text:
                message = f"{message}\n\n{ocr_text}"
                logger.info(f"已将OCR结果附加到消息，追加字符数: {len(ocr_text)}")

        result_text = await task_processor.process(message)
        
        # 如果返回 TaskResult，实际执行子任务
        if hasattr(result_text, 'subtasks'):
            from core.handlers.task_utils import convert_action_to_natural_language
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
            
            # 获取工具注册表
            registry = get_tool_registry()
            
            execution_results = []
            for st in result_text.subtasks:
                action_desc = convert_action_to_natural_language(st.action, st.params)
                logger.info(f"执行子任务: {action_desc}")
                
                # 尝试执行子任务
                try:
                    # 根据 action 类型执行
                    if st.action == "weather":
                        # 天气查询
                        handler = registry.get_handler("skill_execute")
                        if handler:
                            result = await handler({"skill_name": "weather", "params": st.params})
                            execution_results.append(f"✅ {action_desc}: {result.get('result', '查询完成')}")
                        else:
                            execution_results.append(f"⚠️ {action_desc}: 工具不可用")
                    
                    elif st.action == "web_scraper":
                        # 网页爬取
                        handler = registry.get_handler("fetch_url")
                        if handler:
                            # 这里简化处理，实际应该根据 params 构建 URL
                            execution_results.append(f"📋 {action_desc}: 任务已记录")
                        else:
                            execution_results.append(f"⚠️ {action_desc}: 工具不可用")
                    
                    elif st.action == "translator":
                        # 翻译
                        handler = registry.get_handler("skill_execute")
                        if handler:
                            result = await handler({"skill_name": "translator", "params": st.params})
                            execution_results.append(f"✅ {action_desc}: {result.get('result', '翻译完成')}")
                        else:
                            execution_results.append(f"⚠️ {action_desc}: 工具不可用")
                    
                    elif st.action == "gui_automation":
                        # GUI 自动化
                        execution_results.append(f"📋 {action_desc}: GUI自动化任务已记录")
                    
                    elif st.action == "chat":
                        # 对话
                        execution_results.append(f"💬 {action_desc}")
                    
                    else:
                        execution_results.append(f"📋 {action_desc}")
                
                except Exception as e:
                    logger.warning(f"执行子任务失败: {e}")
                    execution_results.append(f"❌ {action_desc}: 执行失败 - {str(e)}")
            
            result_text = "\n".join(execution_results) if execution_results else "任务已处理"
        
        # 确保 result_text 是字符串
        if not isinstance(result_text, str):
            result_text = str(result_text)
        
        result = {"reply": result_text, "skill": "task_processor"}

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

        # 保存AI回复到对话历史
        try:
            history = get_history_manager()
            history.add_message(request.user_id, "assistant", reply_text)
            logger.debug("已添加AI回复到对话历史")
        except Exception as e:
            logger.warning("添加AI回复到对话历史失败: %s", e)

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
    """直接通过SkillDispatcher处理简单任务，跳过Agent，集成对话历史管理和智能选择"""
    try:
        from core.handlers import _dispatcher
        if _dispatcher is None:
            raise HTTPException(status_code=503, detail="系统尚未初始化完成")

        # 保存用户消息到对话历史
        try:
            history = get_history_manager()
            history.add_message(request.user_id, "user", message)
            logger.debug("已添加用户消息到对话历史")
        except Exception as e:
            logger.warning("添加到对话历史失败: %s", e)

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
                request.agent_id,
                _dispatcher
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

        # 保存AI回复到对话历史
        try:
            history = get_history_manager()
            history.add_message(request.user_id, "assistant", reply_text)
            logger.debug("已添加AI回复到对话历史")
        except Exception as e:
            logger.warning("添加AI回复到对话历史失败: %s", e)

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
        history = get_history_manager()
        messages = history.get_history(
            user_id=request.user_id,
            limit=request.limit
        )

        return {
            "success": True,
            "data": {
                "user_id": request.user_id,
                "message_count": len(messages),
                "messages": messages,
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
            short_term_memory.clear(request.user_id)
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
# API 端点：获取Agent列表（适配 coze.js 前端）
# ---------------------------------------------------------------------------
@router.get("/agents", summary="获取Agent列表")
async def get_agents():
    """获取系统所有可用 Agent 列表

    数据来源：config/agents.yml（使用 yaml.safe_load 加载）
    如果 agents.yml 不存在或加载失败，则返回默认的硬编码列表。
    返回格式适配 coze.js 前端的期望格式：
        { "success": true, "data": [{"id": "...", "name": "...", "description": "..."}, ...] }
    """
    agents_yml_path = Path(__file__).parent.parent.parent / "config" / "agents.yml"

    try:
        if agents_yml_path.exists():
            with open(agents_yml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            agents_config = data.get("agents", {})
            agent_list = []

            for agent_id, config in agents_config.items():
                role_prompt = config.get("role_prompt", "")
                # 从角色描述中提取简短名称: "你是一个通用助手，擅长处理各种日常问题" → "通用助手"
                name = agent_id
                if role_prompt.startswith("你是一个"):
                    if "，" in role_prompt:
                        name = role_prompt[4:role_prompt.index("，")]
                    else:
                        name = role_prompt[4:]

                agent_list.append({
                    "id": agent_id,
                    "name": name,
                    "description": role_prompt,
                })

            return {"success": True, "data": agent_list}
        else:
            logger.warning("agents.yml 不存在，返回默认Agent列表")
            return _get_default_agents_response()
    except Exception as e:
        logger.error(f"加载 agents.yml 失败: {e}")
        return _get_default_agents_response()


def _get_default_agents_response() -> Dict[str, Any]:
    """返回默认 Agent 列表（当 agents.yml 加载失败时）"""
    default_agents = [
        {"id": "general",        "name": "通用助手",       "description": "通用助手，擅长处理各种日常问题"},
        {"id": "weather_expert", "name": "天气查询助手",   "description": "天气查询助手，可以查询各城市的天气和预报"},
        {"id": "system_toolbox", "name": "系统工具助手",   "description": "系统工具助手，可以执行系统命令、管理文件"},
        {"id": "translator",     "name": "翻译专家",       "description": "翻译专家，精通多语言互译"},
        {"id": "creative",       "name": "创意助手",       "description": "创意助手，擅长生成有趣内容、故事和艺术"},
        {"id": "data_analyst",   "name": "数据分析专家",   "description": "数据分析专家，擅长数据处理、统计分析和可视化"},
        {"id": "web_scraper",    "name": "网页采集专家",   "description": "网络数据采集专家，擅长从各平台抓取公开数据"},
        {"id": "deep_thinker",   "name": "深度分析专家",   "description": "深度分析专家，擅长复杂问题的多维度分析和推理"},
    ]
    return {"success": True, "data": default_agents}
