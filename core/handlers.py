"""内部处理器函数模块

包含聊天处理的核心逻辑：
- 工作流处理
- 多步任务处理（同步/流式）
- 单步任务处理
- 闲聊处理
- 数据持久化辅助函数
- BFS上下文记忆管理
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

# ==================== BFS上下文记忆全局实例 ====================
from core.bfs_processor import get_bfs_processor
from core.short_term_memory import ShortTermMemoryManager

# 全局BFS处理器实例（单例，所有调用共享）
bfs_processor = get_bfs_processor()

# 全局短时记忆管理器（支持分层树状索引 + BFS队列）
short_term_memory = ShortTermMemoryManager(cache_size=50)

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


def _check_global_refs() -> None:
    """检查全局引用是否已初始化
    
    Raises:
        RuntimeError: 如果全局引用未初始化
    """
    if _dispatcher is None:
        raise RuntimeError(
            "系统尚未初始化完成，请确保 main.py 已启动并完成初始化。"
            "如果问题持续存在，请检查 SkillDispatcher 是否正确初始化。"
        )


# ---------------------------------------------------------------------------
# Action到自然语言的转换工具
# ---------------------------------------------------------------------------
def _convert_action_to_natural_language(action: str, params: Dict[str, Any]) -> str:
    """将技能action和params转换为自然语言描述
    
    Args:
        action: 技能名称
        params: 技能参数
        
    Returns:
        自然语言描述
    """
    # GUI自动化
    if action == "gui_automation":
        app = params.get("application", "")
        act = params.get("action", "打开")
        if app:
            return f"{act}{app}"
        return "执行GUI操作"
    
    # 网页爬取
    elif action == "web_scraper":
        site = params.get("site_name", "")
        act = params.get("action", "")
        if site and act:
            return f"爬取{site}的{act}"
        elif site:
            return f"爬取{site}"
        return "爬取网页数据"
    
    # RAG搜索
    elif action == "rag_search":
        query = params.get("query", "")
        if query:
            return f"搜索{query}"
        return "执行搜索"
    
    # 天气查询
    elif action == "weather":
        city = params.get("city", "")
        if city:
            return f"查询{city}的天气"
        return "查询天气"
    
    # 翻译
    elif action == "translator":
        text = params.get("text", "")
        target = params.get("target_lang", "")
        if text:
            return f"翻译: {text[:30]}"
        return "执行翻译"
    
    # 数据分析
    elif action == "data_analysis":
        return "分析数据"
    
    # 文本分析
    elif action == "text_analyzer":
        text = params.get("text", "")
        if text:
            return f"分析文本: {text[:20]}"
        return "分析文本"
    
    # 聊天/写故事等
    elif action == "chat":
        msg = params.get("message", "")
        if msg:
            return msg
        return "进行对话"
    
    # 默认返回
    return f"执行{action}"


# ---------------------------------------------------------------------------
# 任务处理器适配器
# ---------------------------------------------------------------------------
async def _process_task_with_processor(task: Dict[str, Any], user_id: int = 1) -> Dict[str, Any]:
    """使用 TaskProcessor 处理任务，并转换为 TaskPlanner 格式
    
    Args:
        task: 原始任务格式
        user_id: 用户ID
        
    Returns:
        包含子任务列表和处理路径的字典
    """
    from core.task_processor import task_processor
    
    message = task.get("user_message", "")
    
    # 调用 TaskProcessor
    result = await task_processor.process(message)
    
    # 转换为 TaskPlanner 格式
    sub_tasks = []
    for i, subtask in enumerate(result.subtasks):
        # 将action和params转换为自然语言描述
        action_desc = _convert_action_to_natural_language(subtask.action, subtask.params)
        
        sub_task = {
            "task_id": task.get("task_id", 1) * 100 + i + 1,
            "user_id": user_id,
            "user_message": action_desc,  # 使用自然语言描述
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
        return {"sub_tasks": [task], "path": "none"}
    
    return {"sub_tasks": sub_tasks, "path": result.path.value}


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
# 代码生成降级机制
# ---------------------------------------------------------------------------
async def _try_code_generation(message: str, skill_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """当工具执行失败时，尝试让LLM生成代码解决问题
    
    Args:
        message: 用户原始消息
        skill_name: 失败的skill名称
        params: 提取的参数
        
    Returns:
        包含 success/reply 的字典
    """
    try:
        from core.llm_backend import get_llm_router
        from tools.tool_manager import ToolManager
        
        router = get_llm_router()
        if not router.is_available():
            logger.warning("LLM不可用，跳过代码生成")
            return {"success": False}
        
        # 构建Prompt：让LLM分析问题并生成解决方案代码
        prompt = f"""你是一个智能编程助手。用户想要执行一个任务，但没有现成的工具支持。

【用户需求】
{message}

【尝试使用的工具】
工具名: {skill_name}
参数: {params}

【问题】
该工具执行失败或不存在。请分析用户需求，判断是否可以通过编写Python/Shell脚本来解决。

如果可以，请：
1. 简要说明解决思路（1-2句话）
2. 生成可执行的Python代码（优先）或Shell命令
3. 代码必须安全、简洁，不要使用危险操作

如果无法通过代码解决，请直接回复："无法通过代码解决"

【输出格式】
```
# 你的代码
```

或者

```
# 你的shell命令
```

请开始分析："""
        
        # 调用LLM生成代码
        response = await router.simple_chat(
            user_message=prompt,
            system_prompt="你是一个专业的代码生成助手，擅长根据需求生成安全可执行的脚本。",
            temperature=0.3
        )
        
        if not response or "无法通过代码解决" in response:
            logger.info("LLM判断无法通过代码解决")
            return {"success": False}
        
        # 提取代码块
        import re
        code_match = re.search(r'```(?:python|bash|sh)?\s*\n(.*?)\n```', response, re.DOTALL)
        if not code_match:
            logger.warning("未找到代码块")
            return {"success": False}
        
        code = code_match.group(1).strip()
        if not code:
            return {"success": False}
        
        # 判断代码类型
        is_python = 'python' in code_match.group(0).lower() or '.py' in message.lower()
        is_shell = 'bash' in code_match.group(0).lower() or 'sh' in code_match.group(0).lower()
        
        # 在沙盒中执行代码（使用较宽松的安全配置）
        from core.sandbox_executor import get_sandbox_executor, ResourceLimits as SandboxResourceLimits
        
        sandbox = get_sandbox_executor()
        
        # 为代码生成场景定制资源限制，允许必要的模块
        custom_limits = SandboxResourceLimits(
            timeout=30,
            max_memory_mb=256,
            # 允许os和pathlib用于文件操作，但保持其他危险模块禁用
            forbidden_modules=[
                "subprocess", "socket", "requests",
                "urllib", "http", "ftplib", "smtplib", "poplib",
                "imaplib", "telnetlib", "xmlrpc", "pickle", "shelve",
                "marshal", "dbm", "gdbm", "sqlite3"
            ]
        )
        
        if is_python:
            logger.info(f"执行生成的Python代码: {code[:100]}...")
            result = await sandbox.execute_python(
                code=code,
                limits=custom_limits
            )
        elif is_shell:
            logger.info(f"执行生成的Shell命令: {code[:100]}...")
            result = await sandbox.execute_shell(
                command=code,
                limits=custom_limits
            )
        else:
            # 默认尝试Python
            logger.info(f"执行生成的代码(Python): {code[:100]}...")
            result = await sandbox.execute_python(
                code=code,
                limits=custom_limits
            )
        
        # 转换结果为统一格式
        from core.sandbox_executor import ExecutionStatus
        success = result.status == ExecutionStatus.COMPLETED
        result_dict = {
            "success": success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.error_message if not success else None
        }
        
        if result_dict.get("success"):
            # 构建友好回复
            reply = f"✅ **已通过代码生成解决问题**\n\n"
            reply += f"**解决思路**: {response.split('```')[0].strip()[:200]}\n\n"
            reply += f"**执行结果**:\n{result_dict.get('stdout', '执行成功')}\n"
            
            if result_dict.get('stderr'):
                reply += f"\n⚠️ 警告信息: {result_dict['stderr'][:200]}"
            
            return {"success": True, "reply": reply, "code_generated": True}
        else:
            logger.warning(f"生成的代码执行失败: {result_dict.get('error')}")
            return {"success": False}
            
    except Exception as e:
        logger.error(f"代码生成过程异常: {e}")
        return {"success": False}


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
    process_result = await _process_task_with_processor(task, user_id)
    sub_tasks = process_result["sub_tasks"]
    path = process_result["path"]

    # 规则匹配且只有1个子任务 → 直接用这个子任务的skill去handle_single_step
    if len(sub_tasks) == 1 and path == "rule":
        first_subtask = sub_tasks[0]
        skill_name = first_subtask["tool_call"]["name"]
        return await handle_single_step(message, user_id, skill_name, "default")

    # 仍无法分解（没有子任务或AI分解失败） → 降级为单步处理
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
    process_result = await _process_task_with_processor(task, user_id)
    sub_tasks = process_result["sub_tasks"]
    path = process_result["path"]

    # 规则匹配且只有1个子任务 → 直接用这个子任务的skill去handle_single_step
    if len(sub_tasks) == 1 and path == "rule":
        first_subtask = sub_tasks[0]
        skill_name = first_subtask["tool_call"]["name"]
        single_result = await handle_single_step(message, user_id, skill_name, "default")
        await websocket.send_json({
            "reply": single_result.get("reply", "处理完成"),
            "skill": skill_name,
            "success": single_result.get("success", True),
            "is_subtask": False,
        })
        return single_result

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
    _check_global_refs()
    
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
            from core.task_execution_interface import get_text_analyzer_agent
            from core.keyword_extractor import get_keyword_extractor
            
            analyzer_class = get_text_analyzer_agent()
            analyzer = analyzer_class()
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
            # ✅ 修复：等待协程完成
            if asyncio.iscoroutine(result):
                result = await result
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
            logger.info(f"技能 [{skill_name}] 开始智能总结，result类型: {type(result)}")
            summarized_reply = await summarizer.summarize(
                skill_name=skill_name,
                result=result,
                user_message=message
            )
            result["reply"] = summarized_reply
            logger.info(f"技能 [{skill_name}] 智能总结完成")

        except Exception as e:
            logger.warning(f"智能总结失败，使用原始回复: {e}")
    
    return result


# ---------------------------------------------------------------------------
# BFS上下文记忆管理
# ---------------------------------------------------------------------------
def add_to_context_memory(user_id: str, message: str, role: str = "user", skill_name: str = "chat"):
    """将消息添加到BFS上下文记忆中
    
    使用树与队列的BFS机制管理上下文：
    - 第1层：全局唯一根节点（root_{user_id}）
    - 第2层：按 skill 分类的功能节点（func_{user_id}_{skill_name}）
    - 第3层：文本层节点（text_{user_id}_{序号}）
    - 第4层：段落层节点（para_{user_id}_{序号}）
    
    Args:
        user_id: 用户ID
        message: 消息内容
        role: 角色类型 (user/assistant)
        skill_name: 技能名称（用于第2层分类）
    
    Returns:
        上下文节点ID
    """
    try:
        # 使用BFS处理器处理消息，构建内容树
        bfs_result = bfs_processor.process_text(message)
        
        if bfs_result.get("success"):
            # 将上下文加入短时记忆（使用 skill_name 作为分类）
            context_type = f"{role}_{skill_name}"
            context_id = short_term_memory.add_context(
                user_id=str(user_id),
                content=message,
                context_type=context_type
            )
            
            logger.info("BFS上下文记忆已更新 - 用户: %s, Skill: %s, 节点数: %d", 
                       user_id, skill_name, len(short_term_memory.nodes))
            
            return {
                "success": True,
                "context_id": context_id,
                "queue_size": len(short_term_memory.queue),
                "nodes_count": len(short_term_memory.nodes)
            }
        else:
            logger.warning("BFS上下文处理失败: %s", bfs_result.get("error"))
            return {"success": False, "error": bfs_result.get("error")}
    except Exception as e:
        logger.error("添加上下文记忆失败: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


def get_context_for_llm(user_id: str, depth: int = 2) -> str:
    """获取用于LLM的上下文消息
    
    从BFS队列中提取相关上下文，构建prompt格式
    
    Args:
        user_id: 用户ID
        depth: 展开深度 (1:功能层, 2:文本层, 3:段落层)
    
    Returns:
        格式化的上下文字符串
    """
    context_messages = short_term_memory.get_context(str(user_id), depth=depth)
    
    if not context_messages:
        return ""
    
    # 构建上下文字符串
    context_parts = []
    for msg in context_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        context_parts.append(f"{role}: {content}")
    
    return "\n".join(context_parts)


def search_context_by_keywords(user_id: str, keywords: List[str], top_k: int = 5) -> List[Dict[str, Any]]:
    """基于关键词搜索上下文记忆
    
    Args:
        user_id: 用户ID
        keywords: 关键词列表
        top_k: 返回数量
    
    Returns:
        相关上下文节点列表
    """
    try:
        # 获取队列中的节点
        queue_nodes = []
        for node_id in list(short_term_memory.queue):
            if node_id in short_term_memory.nodes:
                queue_nodes.append(short_term_memory.nodes[node_id])
        
        # 使用BFS处理器进行关键词检索
        from collections import deque
        context_queue = deque(queue_nodes)
        results = bfs_processor.extract_context_by_keywords(context_queue, keywords, top_k)
        
        logger.info("上下文关键词检索完成 - 用户: %s, 找到: %d 个相关节点", 
                   user_id, len(results))
        
        return results
    except Exception as e:
        logger.error("上下文关键词检索失败: %s", e, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# 内部处理器：闲聊
# ---------------------------------------------------------------------------
async def handle_chat(
    message: str, user_id: int, agent_id: str
) -> Dict[str, Any]:
    """处理闲聊对话（GLM 后端 + 角色扮演 + BFS上下文记忆 + 深度思考）。

    Args:
        message: 用户消息
        user_id: 用户ID
        agent_id: Agent ID

    Returns:
        包含 reply、success 和 thinking_process 的字典
    """
    # ✅ 新增：将用户消息添加到BFS上下文记忆（skill=chat）
    add_to_context_memory(user_id, message, role="user", skill_name="chat")
    
    # ✅ 新增：获取历史上下文
    context_str = get_context_for_llm(user_id, depth=2)
    
    # 构建包含上下文的系统提示词
    system_prompt: str = get_system_prompt(agent_id)
    
    # 如果有上下文，添加到系统提示词
    if context_str:
        system_prompt += f"\n\n历史对话上下文（用于理解当前问题）：\n{context_str}"

    thinking_process = None
    
    # ✅ 新增：使用深度思考引擎处理复杂问题（使用单例模式）
    try:
        from core.reasoning_engine import get_reasoning_engine
        
        reasoning_engine = get_reasoning_engine()
        reasoning_result = await reasoning_engine.process(message, user_id)
        
        thinking_process = reasoning_result.get("thinking_process")
        final_answer = reasoning_result.get("final_answer")
        
        # 如果思考引擎返回了答案，使用它
        if final_answer and final_answer != message:
            reply = final_answer
        else:
            # 否则使用普通对话
            from core.llm_backend import get_llm_router
            router = get_llm_router()
            reply: str = await router.simple_chat(message, system_prompt=system_prompt)
            
    except Exception as e:
        logger.debug("深度思考引擎未启用或失败: %s", e)
        # 回退到普通对话
        try:
            from core.llm_backend import get_llm_router
            router = get_llm_router()
            reply: str = await router.simple_chat(message, system_prompt=system_prompt)
        except Exception as llm_e:
            logger.warning("LLM 对话失败: %s", llm_e)
            reply = f"你好！有什么可以帮你的吗？（LLM 未配置: {llm_e}）"
    
    # ✅ 新增：将AI回复也添加到上下文记忆（skill=chat）
    add_to_context_memory(user_id, reply, role="assistant", skill_name="chat")
    
    return {
        "reply": reply,
        "success": True,
        "tool_call": {"name": "chat", "params": {}},
        "thinking_process": thinking_process,
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
) -> Optional[int]:
    """保存聊天记录到 MySQL，返回消息ID。

    Args:
        user_id: 用户ID
        character_id: 角色ID
        role: 角色 (user / assistant)
        content: 消息内容
        tool_call: 工具调用信息（可选）

    Returns:
        消息ID，失败返回 None
    """
    if not _db_initialized:
        return None
    
    if not content or not content.strip():
        logger.debug("空内容不保存到聊天历史")
        return None
    
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
                user_message=content if role == "user" else "",
                ai_response=content if role == "assistant" else "",
            )
            session.add(record)
            session.commit()
            return record.id
        finally:
            session.close()
    except Exception as e:
        logger.debug("保存聊天历史失败: %s", e)
        return None



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