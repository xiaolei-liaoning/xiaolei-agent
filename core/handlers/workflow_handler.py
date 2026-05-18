"""工作流处理器"""

import logging
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


async def handle_automation_workflow(message: str, user_id: int) -> Dict[str, Any]:
    """处理自动化工作流任务。

    Args:
        message: 用户消息
        user_id: 用户ID

    Returns:
        包含 reply 和 success 的字典
    """
    try:
        from ..workflow.automation_workflow import get_workflow_engine
        engine = get_workflow_engine()
    except ImportError as e:
        # 记录详细错误信息并重新抛出
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"导入工作流引擎失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"reply": f"工作流引擎未加载: {e}", "success": False}

    workflow_result = await engine.create_smart_workflow(message)
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
