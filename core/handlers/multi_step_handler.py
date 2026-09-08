"""多步任务处理器"""

import logging
from typing import Dict, Any, List

from fastapi import WebSocket

logger = logging.getLogger(__name__)


async def handle_multi_step(
    message: str, 
    user_id: int,
    planner,
    processor,
    dispatcher,
    db_initialized: bool = False
) -> Dict[str, Any]:
    """处理多步任务（规则分解 → GLM兜底 → 并发执行）。

    Args:
        message: 用户消息
        user_id: 用户ID
        planner: TaskPlanner 实例
        processor: ConcurrentTaskProcessor 实例
        dispatcher: SkillDispatcher 实例
        db_initialized: 数据库是否已初始化

    Returns:
        包含 reply 和 success 的字典
    """
    from .single_step_handler import handle_single_step
    from .task_utils import process_task_with_processor
    
    if planner is None:
        # 修复 #126: 原实现静默降级到单步, 用户/调用方不知情。记日志。
        logger.debug("Multi-step: planner 未提供, 降级到单步处理")
        return await handle_single_step(message, user_id, "chat", "default", dispatcher, db_initialized)

    task: Dict[str, Any] = {
        "user_message": message,
        "tool_call": {"name": "multi_step", "params": {}},
        "status": "pending",
    }

    process_result = await process_task_with_processor(task, user_id)
    sub_tasks = process_result["sub_tasks"]
    path = process_result["path"]

    if len(sub_tasks) == 1 and path == "rule":
        first_subtask = sub_tasks[0]
        skill_name = first_subtask["tool_call"]["name"]
        return await handle_single_step(message, user_id, skill_name, "default", dispatcher, db_initialized)

    if len(sub_tasks) <= 1:
        return await handle_single_step(message, user_id, "chat", "default", dispatcher, db_initialized)

    if processor is not None:
        results = await processor.submit_tasks(sub_tasks)
    else:
        # 修复 #124: 原实现假装成功(返回"已处理"+success:True), 用户以为子任务真执行了。
        # 改为诚实降级——明确告知子任务未被实际执行。
        logger.warning("Multi-step: processor 未提供, %d 个子任务未实际执行", len(sub_tasks))
        results = []
        for sub_task in sub_tasks:
            results.append({
                "success": False,
                "reply": f"⚠️ 子任务未执行(处理器未配置): {sub_task.get('user_message', '')}",
            })

    reply_lines: List[str] = ["多步任务执行结果："]
    for sub_task, result in zip(sub_tasks, results):
        success = result.get("success", False)
        status_icon: str = "[OK]" if success else "[FAIL]"
        task_msg: str = sub_task.get("user_message", "")
        if result.get("reply"):
            reply_lines.append(f"  {status_icon} {task_msg}: {result['reply']}")
        else:
            reply_lines.append(f"  {status_icon} {task_msg}")

    # 自动审查：多步任务完成后生成复盘
    try:
        from core.auto_reviewer import AutoReviewer
        from core.learning.feedback import get_hub, create_task_completion_event
        reviewer = AutoReviewer()
        # 修复 #241 (生产端): 复盘日志改用结构化前缀 [OK]/[FAIL]（保留 emoji 便于人读）。
        # auto_reviewer._parse_status_line 优先识别前缀，emoji 判定只是兼容兜底。
        logs = "\n".join(
            f"{'[OK] ✅' if r.get('success') else '[FAIL] ❌'} [{s.get('tool_call', {}).get('name','?')}] {s.get('user_message','')}"
            for s, r in zip(sub_tasks, results)
        )
        review = reviewer.review(
            task_id=f"multi_{hash(message)}",
            task_name="多步任务",
            execution_logs=logs,
        )
        logger.debug("多步任务复盘完成: %s", review.review_id)

        # 方案C: 同时 emit task_completion 事件，让 FeedbackHub 同步记录
        all_success = all(r.get("success") for r in results)
        try:
            hub = get_hub()
            event = create_task_completion_event(
                user_id=str(user_id),
                task_id=f"multi_{hash(message)}",
                success=all_success,
                source="multi_step_handler",
            )
            event.payload["description"] = message[:200]
            event.payload["logs"] = logs[:5000]  # 限制大小
            await hub.emit(event)
        except Exception as hub_e:
            logger.debug(f"FeedbackHub emit 失败（不影响主流程）: {hub_e}")
    except Exception as e:
        # 修复 #125: 原 except: pass 完全静默吞掉审查失败, 无法排障。记日志。
        logger.warning("多步任务复盘失败(不影响主流程): %s", e)

    # 修复 #124: success 不再硬编码 True, 反映实际子任务执行结果
    all_ok = all(r.get("success") for r in results)
    return {"reply": "\n".join(reply_lines), "success": all_ok}


async def handle_multi_step_streaming(
    message: str, 
    user_id: int, 
    websocket: WebSocket,
    planner=None,
    processor=None,
    dispatcher=None,
    db_initialized: bool = False
) -> Dict[str, Any]:
    """处理多步任务并通过 WebSocket 实时推送每个子任务的执行结果。

    Args:
        message: 用户消息
        user_id: 用户ID
        websocket: WebSocket 连接对象
        planner: TaskPlanner 实例（None 时降级为单步处理）
        processor: ConcurrentTaskProcessor 实例（None 时子任务仅记录不实跑）
        dispatcher: SkillDispatcher 实例
        db_initialized: 数据库是否已初始化

    Returns:
        包含 reply 和 success 的字典

    注: planner/processor/dispatcher 均有 None 保护——
        chat_ws.py 的调用仅传 (message, user_id, websocket)，缺省走降级路径。
    """
    from .single_step_handler import handle_single_step
    from .task_utils import process_task_with_processor
    
    if planner is None:
        # 修复 #126: 原实现静默降级到单步, 用户/调用方不知情。记日志。
        logger.debug("Multi-step: planner 未提供, 降级到单步处理")
        return await handle_single_step(message, user_id, "chat", "default", dispatcher, db_initialized)

    task: Dict[str, Any] = {
        "user_message": message,
        "tool_call": {"name": "multi_step", "params": {}},
        "status": "pending",
    }

    process_result = await process_task_with_processor(task, user_id)
    sub_tasks = process_result["sub_tasks"]
    path = process_result["path"]

    if len(sub_tasks) == 1 and path == "rule":
        first_subtask = sub_tasks[0]
        skill_name = first_subtask["tool_call"]["name"]
        single_result = await handle_single_step(message, user_id, skill_name, "default", dispatcher, db_initialized)
        await websocket.send_json({
            "reply": single_result.get("reply", "处理完成"),
            "skill": skill_name,
            "success": single_result.get("success", True),
            "is_subtask": False,
        })
        return single_result

    if len(sub_tasks) <= 1:
        single_result = await handle_single_step(message, user_id, "chat", "default", dispatcher, db_initialized)
        await websocket.send_json({
            "reply": single_result.get("reply", "处理完成"),
            "skill": "chat",
            "success": single_result.get("success", True),
            "is_subtask": False,
        })
        return single_result

    reply_lines: List[str] = ["多步任务执行结果："]
    all_success: bool = True

    for idx, sub_task in enumerate(sub_tasks, 1):
        task_msg: str = sub_task.get("user_message", "")
        
        await websocket.send_json({
            "type": "subtask_start",
            "index": idx,
            "total": len(sub_tasks),
            "message": task_msg,
        })

        try:
            if processor is not None:
                results = await processor.submit_tasks([sub_task])
                result = results[0] if results else {"success": False, "reply": "执行失败"}
            else:
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
