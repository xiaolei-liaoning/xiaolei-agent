"""内部处理器函数模块

包含聊天处理的核心逻辑：
- 工作流处理
- 多步任务处理（同步/流式）
- 单步任务处理
- 闲聊处理
- 数据持久化辅助函数
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 全局状态引用（由 main.py 注入）
# ---------------------------------------------------------------------------
_dispatcher: Optional[Any] = None
_processor: Optional[Any] = None
_planner: Optional[Any] = None
_db_initialized: bool = False


def set_global_refs(
    dispatcher: Any,
    processor: Any,
    planner: Any,
    db_initialized: bool
) -> None:
    """设置全局引用，由 main.py 在初始化后调用。
    
    Args:
        dispatcher: SkillDispatcher 实例
        processor: ConcurrentTaskProcessor 实例
        planner: TaskPlanner 实例
        db_initialized: 数据库是否已初始化
    """
    global _dispatcher, _processor, _planner, _db_initialized
    _dispatcher = dispatcher
    _processor = processor
    _planner = planner
    _db_initialized = db_initialized


# ---------------------------------------------------------------------------
# 任务处理器适配器
# ---------------------------------------------------------------------------
async def _process_task_with_processor(task: Dict[str, Any], user_id: int = 1) -> List[Dict[str, Any]]:
    """使用 TaskProcessor 处理任务，并转换为 TaskPlanner 格式
    
    Args:
        task: 原始任务格式
        user_id: 用户ID
        
    Returns:
        TaskPlanner 格式的子任务列表
    """
    from core.task_processor import task_processor
    
    message = task.get("user_message", "")
    
    # 调用 TaskProcessor
    result = await task_processor.process(message)
    
    # 转换为 TaskPlanner 格式
    sub_tasks = []
    for i, subtask in enumerate(result.subtasks):
        sub_task = {
            "task_id": task.get("task_id", 1) * 100 + i + 1,
            "user_id": user_id,
            "user_message": f"{subtask.action}: {subtask.params}",
            "ai_response": f"执行: {subtask.action}",
            "tool_call": {
                "name": subtask.action,
                "params": subtask.params
            },
            "status": "pending",
            "timestamp": datetime.now().isoformat(),
        }
        sub_tasks.append(sub_task)
    
    # 如果没有子任务，返回原任务
    if not sub_tasks:
        return [task]
    
    return sub_tasks


# ---------------------------------------------------------------------------
# 内部处理器：工作流
# ---------------------------------------------------------------------------
async def handle_automation_workflow(message: str, user_id: int) -> Dict[str, Any]:
    """处理自动化工作流任务。

    Args:
        message: 用户消息
        user_id: 用户ID

    Returns:
        包含 reply 和 success 的字典
    """
    try:
        from core.automation_workflow import get_workflow_engine
        engine = get_workflow_engine()
    except ImportError as e:
        return {"reply": f"工作流引擎未加载: {e}", "success": False}

    workflow_result = engine.create_smart_workflow(message)
    if not workflow_result.get("success"):
        return {"reply": "无法识别工作流意图", "success": False}

    result = await engine.execute_workflow(workflow_result["workflow"], generate_report=True)

    reply_lines: List[str] = [f"工作流 [{result['workflow_name']}] 执行完成"]
    reply_lines.append(f"总耗时: {result['total_time']}s")

    for r in result.get("results", []):
        step: int = r.get("step", 0)
        success: bool = r.get("success", False)
        status_icon: str = "[OK]" if success else "[FAIL]"
        step_type: str = r.get("type", "")

        if step_type == "scrape":
            reply_lines.append(
                f"  {status_icon} 步骤{step}: 爬取{r.get('site', '')}"
                f" - {r.get('data', {}).get('count', 0)}条"
            )
        elif step_type == "analyze":
            reply_lines.append(f"  {status_icon} 步骤{step}: 数据分析完成")
        elif step_type == "automate":
            reply_lines.append(f"  {status_icon} 步骤{step}: {r.get('action', '')}")
        else:
            reply_lines.append(f"  {status_icon} 步骤{step}: {step_type}")

    if result.get("report_path"):
        report_name = Path(result["report_path"]).name
        reply_lines.append(f"\n报告已保存到桌面: {report_name}")

    return {"reply": "\n".join(reply_lines), "success": result.get("success", False)}


# ---------------------------------------------------------------------------
# 内部处理器：多步任务（非流式）
# ---------------------------------------------------------------------------
async def handle_multi_step(message: str, user_id: int) -> Dict[str, Any]:
    """处理多步任务（规则分解 → GLM兜底 → 并发执行）。

    Args:
        message: 用户消息
        user_id: 用户ID

    Returns:
        包含 reply 和 success 的字典
    """
    if _planner is None:
        return await handle_single_step(message, user_id, "chat", "default")

    task: Dict[str, Any] = {
        "user_message": message,
        "tool_call": {"name": "multi_step", "params": {}},
        "status": "pending",
    }

    # 规则分解
    sub_tasks: List[Dict[str, Any]] = await _process_task_with_processor(task, user_id)

    # 仍无法分解，降级为单步处理
    if len(sub_tasks) <= 1:
        return await handle_single_step(message, user_id, "chat", "default")

    # 并发执行所有子任务
    if _processor is not None:
        results = await _processor.submit_tasks(sub_tasks)
    else:
        # fallback: 串行执行
        results = []
        for sub_task in sub_tasks:
            results.append({"success": True, "reply": f"已处理: {sub_task.get('user_message', '')}"})

    reply_lines: List[str] = ["多步任务执行结果："]
    for sub_task, result in zip(sub_tasks, results):
        success = result.get("success", False)
        status_icon: str = "[OK]" if success else "[FAIL]"
        task_msg: str = sub_task.get("user_message", "")
        if result.get("reply"):
            reply_lines.append(f"  {status_icon} {task_msg}: {result['reply']}")
        else:
            reply_lines.append(f"  {status_icon} {task_msg}")

    return {"reply": "\n".join(reply_lines), "success": True}


# ---------------------------------------------------------------------------
# 内部处理器：多步任务（WebSocket 流式）
# ---------------------------------------------------------------------------
async def handle_multi_step_streaming(
    message: str, user_id: int, websocket: WebSocket
) -> Dict[str, Any]:
    """处理多步任务并通过 WebSocket 实时推送每个子任务的执行结果。

    Args:
        message: 用户消息
        user_id: 用户ID
        websocket: WebSocket 连接对象

    Returns:
        包含 reply 和 success 的字典
    """
    if _planner is None:
        return await handle_single_step(message, user_id, "chat", "default")

    task: Dict[str, Any] = {
        "user_message": message,
        "tool_call": {"name": "multi_step", "params": {}},
        "status": "pending",
    }

    # 规则分解
    sub_tasks: List[Dict[str, Any]] = await _process_task_with_processor(task, user_id)

    # 仍无法分解，降级为单步处理
    if len(sub_tasks) <= 1:
        single_result = await handle_single_step(message, user_id, "chat", "default")
        await websocket.send_json({
            "reply": single_result.get("reply", "处理完成"),
            "skill": "chat",
            "success": single_result.get("success", True),
            "is_subtask": False,
        })
        return single_result

    # 逐个执行子任务并实时推送
    reply_lines: List[str] = ["多步任务执行结果："]
    all_success: bool = True

    for idx, sub_task in enumerate(sub_tasks, 1):
        task_msg: str = sub_task.get("user_message", "")
        
        # 发送子任务开始通知
        await websocket.send_json({
            "type": "subtask_start",
            "index": idx,
            "total": len(sub_tasks),
            "message": task_msg,
        })

        # 执行单个子任务
        try:
            if _processor is not None:
                results = await _processor.submit_tasks([sub_task])
                result = results[0] if results else {"success": False, "reply": "执行失败"}
            else:
                # fallback: 直接执行
                result = {"success": True, "reply": f"已处理: {task_msg}"}
        except Exception as e:
            logger.error("子任务执行失败: %s", e)
            result = {"success": False, "reply": f"执行错误: {e}"}

        success = result.get("success", False)
        all_success = all_success and success
        status_icon: str = "[OK]" if success else "[FAIL]"
        
        if result.get("reply"):
            reply_text = f"{status_icon} {task_msg}: {result['reply']}"
        else:
            reply_text = f"{status_icon} {task_msg}"
        
        reply_lines.append(f"  {reply_text}")

        # 实时推送子任务结果
        await websocket.send_json({
            "type": "subtask_result",
            "index": idx,
            "total": len(sub_tasks),
            "message": task_msg,
            "success": success,
            "reply": result.get("reply", ""),
        })

    final_reply = "\n".join(reply_lines)
    return {"reply": final_reply, "success": all_success}


# ---------------------------------------------------------------------------
# 内部处理器：单步任务
# ---------------------------------------------------------------------------
async def handle_single_step(
    message: str, user_id: int, skill_name: str, agent_id: str
) -> Dict[str, Any]:
    """处理单步任务（工具调用或闲聊）。

    Args:
        message: 用户消息
        user_id: 用户ID
        skill_name: 匹配的技能名
        agent_id: Agent ID

    Returns:
        包含 reply / tool_call / success 的字典
    """
    # 闲聊
    if skill_name == "chat":
        return await handle_chat(message, user_id, agent_id)

    # 提取参数
    params: Dict[str, Any] = _dispatcher.extract_params(message, skill_name)

    # 上下文参数补充
    if skill_name == "rag_search":
        params["query"] = message
        params["user_id"] = user_id
    elif skill_name == "system_toolbox":
        if "时间" in message or "几点" in message:
            params["action"] = "time"
        elif "日期" in message or "几号" in message:
            params["action"] = "date"

    # 处理第三方应用技能
    if skill_name.startswith("third_party_"):
        try:
            from skills.third_party.handler import app_manager
            app_name = skill_name.replace("third_party_", "")
            
            # 根据应用名称和消息内容提取操作类型和参数
            action = params.get("action")
            if not action:
                # 根据消息内容自动提取操作类型
                if app_name == "github":
                    if "仓库" in message or "repo" in message.lower():
                        import re
                        repo_match = re.search(r'(?:查看|查询|获取)\s*(\w+)/([\w-]+)\s*(?:仓库|repo)', message)
                        if repo_match:
                            action = "get_repo"
                            params["owner"] = repo_match.group(1)
                            params["repo"] = repo_match.group(2)
                        else:
                            action = "get_info"
                    elif "用户" in message or "user" in message.lower():
                        import re
                        user_match = re.search(r'(?:查看|查询|获取)\s*(?:用户|user)\s*(\w+)', message)
                        if user_match:
                            action = "get_user"
                            params["username"] = user_match.group(1)
                        else:
                            action = "get_info"
                    else:
                        action = "get_info"
                elif app_name == "twitter":
                    if "用户" in message or "user" in message.lower():
                        import re
                        user_match = re.search(r'(?:查看|查询|获取)\s*(?:用户|user)\s*(\w+)', message)
                        if user_match:
                            action = "get_user"
                            params["username"] = user_match.group(1)
                        else:
                            action = "get_info"
                    elif "推文" in message or "tweet" in message.lower():
                        import re
                        user_match = re.search(r'(?:查看|查询|获取)\s*(\w+)\s*(?:的|\'s)\s*(?:推文|tweet)', message)
                        if user_match:
                            action = "get_tweets"
                            params["username"] = user_match.group(1)
                        else:
                            action = "get_info"
                    else:
                        action = "get_info"
                else:
                    action = "get_info"
            
            result = await app_manager.execute(app_name, action, params)
            # 处理第三方应用的执行结果
            if not result.get("success"):
                error_msg = result.get('error', result.get('data', {}).get('error', '未知错误'))
                
                if '密钥未配置' in error_msg or 'API key' in error_msg.lower() or 'token' in error_msg.lower():
                    result["reply"] = f"⚠️ {app_name} 功能需要配置API密钥才能使用。\n\n" \
                                    f"您可以在 skills/third_party/config.yml 中配置 {app_name} 的API密钥，\n" \
                                    f"或者尝试其他不需要API的功能。"
                else:
                    result["reply"] = f"{app_name} 应用执行失败: {error_msg}"
            else:
                data = result.get("data", {})
                if isinstance(data, dict):
                    if data.get('success') is False:
                        error_msg = data.get('error', '未知错误')
                        if '密钥未配置' in error_msg or 'API key' in error_msg.lower():
                            result["reply"] = f"⚠️ {app_name} 功能需要配置API密钥才能使用。\n\n" \
                                            f"您可以在 skills/third_party/config.yml 中配置 {app_name} 的API密钥，\n" \
                                            f"或者尝试其他不需要API的功能。"
                        else:
                            result["reply"] = f"{app_name} 应用执行失败: {error_msg}"
                    else:
                        result["reply"] = f"{app_name} 应用执行成功:\n" + "\n".join([f"{k}: {v}" for k, v in data.items()])
                else:
                    result["reply"] = f"{app_name} 应用执行成功: {data}"
        except Exception as e:
            logger.error("第三方应用 %s 执行异常: %s", skill_name, e)
            result = {"success": False, "error": str(e), "reply": f"第三方应用执行异常: {str(e)}"}
    
    # 处理批量操作
    elif skill_name == "batch_operations":
        try:
            from skills.third_party.batch_operations import batch_manager
            operation_type = params.get("operation_type", "execute_batch")
            
            if operation_type == "execute_batch":
                operations = params.get("operations", [])
                result = await batch_manager.execute_batch(operations)
                success_count = sum(1 for r in result if r.get('success'))
                failure_count = len(result) - success_count
                result["reply"] = f"批量操作完成: 成功 {success_count} 个, 失败 {failure_count} 个"
            elif operation_type == "sync_data":
                source_app = params.get("source_app")
                target_apps = params.get("target_apps", [])
                data_type = params.get("data_type")
                sync_params = params.get("params", {})
                result = await batch_manager.sync_data(source_app, target_apps, data_type, sync_params)
                result["reply"] = f"数据同步完成: 成功 {result.get('success_count', 0)} 个, 失败 {result.get('failure_count', 0)} 个"
            elif operation_type == "compare_data":
                apps = params.get("apps", [])
                data_type = params.get("data_type")
                compare_params = params.get("params", {})
                result = await batch_manager.compare_data(apps, data_type, compare_params)
                result["reply"] = f"数据比较完成: 所有应用都有数据: {result.get('all_have_data', False)}"
            else:
                result = {"success": False, "error": f"未知操作类型: {operation_type}", "reply": f"未知操作类型: {operation_type}"}
        except Exception as e:
            logger.error("批量操作执行异常: %s", e)
            result = {"success": False, "error": str(e), "reply": f"批量操作执行异常: {str(e)}"}
    
    # 处理文本分析
    elif skill_name == "text_analyzer":
        try:
            from core.multi_agent_system import TextAnalyzerAgent
            from core.keyword_extractor import get_keyword_extractor
            
            analyzer = TextAnalyzerAgent()
            text_content = message.replace("文本分析:", "").strip()
            extractor = get_keyword_extractor()
            extraction = await extractor.extract(text_content)
            paragraphs = analyzer._split_into_paragraphs(text_content)
            summaries = []
            for i, paragraph in enumerate(paragraphs):
                summary = analyzer._generate_summary(paragraph)
                summaries.append({
                    "paragraph_index": i,
                    "content": paragraph,
                    "summary": summary
                })
            title = analyzer._generate_title(text_content)
            tree = analyzer._build_content_tree(title, paragraphs, summaries)
            analyzer._update_context_memory(tree)
            keywords = [kw.word for kw in extraction.keywords[:5]] if extraction.keywords else []
            
            if keywords:
                relevant_nodes = analyzer.search_by_keywords(keywords, top_n=5)
                reply = f"📊 **文本分析完成**\n\n"
                reply += f"**标题**: {title}\n"
                reply += f"**段落数**: {len(paragraphs)}\n"
                reply += f"**主要意图**: {extraction.main_intent}\n"
                reply += f"**置信度**: {extraction.confidence:.2%}\n\n"
                
                if keywords:
                    reply += f"🔑 **提取的关键词**: {', '.join(keywords)}\n\n"
                
                if relevant_nodes:
                    reply += f"🔍 **找到 {len(relevant_nodes)} 个相关段落**:\n\n"
                    for i, item in enumerate(relevant_nodes, 1):
                        node = item['node']
                        score = item['score']
                        matched = item['matched_keywords']
                        reply += f"**{i}. [{node['type']}]** (相关度: {score:.1f})\n"
                        reply += f"   - 匹配关键词: {', '.join(matched)}\n"
                        content_preview = node['content'][:100].replace('\n', ' ')
                        if len(node['content']) > 100:
                            content_preview += '...'
                        reply += f"   - 内容: {content_preview}\n\n"
                else:
                    reply += "⚠️ 未找到相关段落\n\n"
                
                reply += f"📝 **段落概要**:\n"
                for i, item in enumerate(summaries[:5], 1):
                    reply += f"  {i}. {item.get('summary', '无')[:80]}...\n"
                
                if len(summaries) > 5:
                    reply += f"  ... 还有 {len(summaries) - 5} 个段落\n"
            else:
                reply = f"📊 **文本分析完成**\n\n"
                reply += f"**标题**: {title}\n"
                reply += f"**段落数**: {len(paragraphs)}\n\n"
                reply += f"📝 **段落概要**:\n"
                for i, item in enumerate(summaries, 1):
                    reply += f"  {i}. {item.get('summary', '无')}\n"
            
            result = {"success": True, "reply": reply}
        except Exception as e:
            logger.error("文本分析执行异常: %s", e)
            import traceback
            traceback.print_exc()
            result = {"success": False, "error": str(e), "reply": f"❌ 文本分析失败: {str(e)}"}
    
    # 通过 ToolManager 执行
    else:
        try:
            from tools.tool_manager import ToolManager
            tm = ToolManager.get_instance()
            result = tm.execute(skill_name, **params)
        except Exception as e:
            logger.error("工具 %s 执行异常: %s", skill_name, e)
            result = {"success": False, "error": str(e)}

    if not isinstance(result, dict):
        result = {"success": True, "result": str(result)}

    result["tool_call"] = {"name": skill_name, "params": params}
    
    # ✅ 新增：智能总结技能执行结果
    if result.get("success", False) and skill_name != "chat":
        try:
            from core.result_summarizer import get_result_summarizer
            summarizer = get_result_summarizer()
            summarized_reply = await summarizer.summarize(
                skill_name=skill_name,
                result=result,
                user_message=message
            )
            result["reply"] = summarized_reply
            result["original_data"] = result.get("result")
            logger.info(f"技能 [{skill_name}] 已应用智能总结")
        except Exception as e:
            logger.warning(f"智能总结失败，使用原始回复: {e}")
    
    return result


# ---------------------------------------------------------------------------
# 内部处理器：闲聊
# ---------------------------------------------------------------------------
async def handle_chat(
    message: str, user_id: int, agent_id: str
) -> Dict[str, Any]:
    """处理闲聊对话（GLM 后端 + 角色扮演）。

    Args:
        message: 用户消息
        user_id: 用户ID
        agent_id: Agent ID

    Returns:
        包含 reply 和 success 的字典
    """
    system_prompt: str = get_system_prompt(agent_id)

    try:
        from core.llm_backend import get_llm_router
        router = get_llm_router()
        reply: str = await router.simple_chat(message, system_prompt=system_prompt)
        return {
            "reply": reply,
            "success": True,
            "tool_call": {"name": "chat", "params": {}},
        }
    except Exception as e:
        logger.warning("LLM 对话失败: %s", e)
        return {
            "reply": f"你好！有什么可以帮你的吗？（LLM 未配置: {e}）",
            "success": True,
            "tool_call": {"name": "chat", "params": {}},
        }


def get_system_prompt(agent_id: str) -> str:
    """获取Agent的 system_prompt。优先从数据库读取。

    Args:
        agent_id: Agent ID

    Returns:
        系统提示词字符串
    """
    _builtin_prompts: Dict[str, str] = {
        "default": "你是小雷版小龙虾AI助手，友好、专业、高效。简洁回答用户问题。",
        "first_love": "你是温柔体贴的初恋角色，说话温柔，善解人意。",
        "bestfriend": "你是用户的知心闺蜜，可以畅所欲言。",
        "goddess": "你是高冷女神，说话简洁有力。",
        "libai": "你是诗仙李白，性格豪放，说话常带诗意。",
    }

    if not _db_initialized:
        return _builtin_prompts.get(agent_id, _builtin_prompts["default"])

    try:
        from core.database import get_session, Character
        session = get_session()
        try:
            character = session.query(Character).filter_by(
                character_id=agent_id
            ).first()
            if character and character.system_prompt:
                return character.system_prompt
        finally:
            session.close()
    except Exception as e:
        logger.warning("读取Agent system_prompt 失败: %s", e)

    return _builtin_prompts.get(agent_id, _builtin_prompts["default"])


# ---------------------------------------------------------------------------
# 数据持久化辅助函数
# ---------------------------------------------------------------------------
def save_chat_history(
    user_id: int,
    character_id: str,
    role: str,
    content: str,
    tool_call: Optional[Dict[str, Any]] = None,
) -> None:
    """异步保存聊天记录到 MySQL（失败静默，不影响用户体验）。

    Args:
        user_id: 用户ID
        character_id: 角色ID
        role: 角色 (user / assistant)
        content: 消息内容
        tool_call: 工具调用信息（可选）
    """
    if not _db_initialized:
        return
    try:
        from core.database import get_session, ChatHistory
        session = get_session()
        try:
            record = ChatHistory(
                user_id=user_id,
                character_id=character_id,
                role=role,
                content=content[:5000],
                tool_call=tool_call,
            )
            session.add(record)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        logger.debug("保存聊天历史失败: %s", e)


def save_task_log(
    user_id: int,
    task_type: str,
    success: bool,
    params: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    duration: float = 0.0,
) -> None:
    """异步保存任务日志到 MySQL（失败静默）。

    Args:
        user_id: 用户ID
        task_type: 任务类型（技能名）
        success: 是否成功
        params: 任务参数
        result: 任务结果
        duration: 耗时（秒）
    """
    if not _db_initialized:
        return
    try:
        from core.database import get_session, TaskLog
        session = get_session()
        try:
            log = TaskLog(
                user_id=user_id,
                task_type=task_type,
                status="success" if success else "failed",
                params=params,
                result=_safe_json(result),
                duration=round(duration, 3),
            )
            session.add(log)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        logger.debug("保存任务日志失败: %s", e)


def _safe_json(data: Any) -> Optional[Dict[str, Any]]:
    """安全地序列化数据为 JSON 可存储的字典。"""
    if data is None:
        return None
    try:
        if isinstance(data, dict):
            return {
                str(k): str(v)[:2000] if not isinstance(v, (int, float, bool, type(None))) else v
                for k, v in data.items()
            }
        return {"raw": str(data)[:2000]}
    except Exception:
        return {"raw": "unserializable"}
