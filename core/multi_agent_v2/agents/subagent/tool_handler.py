"""Subagent 工具处理器 — 注册到 V2 ToolRegistry 中

作为 LLM 可调用的内置工具：
- task: 生成单个子代理（foreground/background）
- orchestrate: DAG 并行编排多个子代理
"""

import asyncio
import logging
from core.multi_agent_v2.prompts import get_builder
_builder = get_builder()
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def _handle_task(args: Dict[str, Any]) -> Dict[str, Any]:
    """task 工具处理器 — 生成子代理执行子任务

    LLM 调用参数:
      description: str — 3-5 词简短描述
      prompt: str — 子代理要执行的任务
      subagent_type: str — explore|build|general|analyze
      task_id: str (optional) — 恢复已有子代理
      background: bool (optional) — 后台执行
    """
    from .spawn import task as do_task

    description = args.get("description", "")
    prompt = args.get("prompt", "")
    subagent_type = args.get("subagent_type", "general")
    task_id = args.get("task_id")
    background = args.get("background", False)

    task_description = prompt or description
    if not task_description:
        return {"success": False, "error": "缺少 prompt 或 description 参数"}

    try:
        result = await asyncio.wait_for(
            do_task(
                description=task_description,
                agent=subagent_type,
                background=background,
                parent_id=task_id or "",
            ),
            timeout=900,  # ponytail: LLM 慢，600→900
        )
        return result
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "子代理执行超时 (900s)",
            "output": f"<task_error>子代理 {task_description[:60]} 执行超时</task_error>",
        }
    except Exception as e:
        logger.error(f"task 工具异常: {e}")
        return {"success": False, "error": str(e)}


async def _handle_orchestrate(args: Dict[str, Any]) -> Dict[str, Any]:
    """orchestrate 工具处理器 — DAG 并行编排多个子代理

    LLM 调用参数:
      tasks: [{id, description, prompt, agent?, depends_on?: [str]}]
      max_concurrent: int (optional) — 最大并发数
    """
    from .spawn import orchestrate as do_orch

    tasks = args.get("tasks", [])
    max_concurrent = args.get("max_concurrent", 5)

    if not tasks:
        return {"success": False, "error": "缺少 tasks 参数"}

    try:
        result = await asyncio.wait_for(
            do_orch(
                tasks=tasks,
                max_concurrent=min(max_concurrent, 5),
            ),
            timeout=900,  # 15 分钟超时
        )
        return result
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "编排执行超时 (900s)",
            "output": "<orchestration_error>执行超时</orchestration_error>",
        }
    except Exception as e:
        logger.error(f"orchestrate 工具异常: {e}")
        return {"success": False, "error": str(e)}


# ════════════════════════════════════════════════════════════════
# 可用代理类型列表（注入到 task/orchestrate 工具描述中）
# ════════════════════════════════════════════════════════════════










# ════════════════════════════════════════════════════════════════
# ToolDefinition 定义 — 供 ToolRegistry 注册
# ════════════════════════════════════════════════════════════════

def get_task_tool_def():
    """返回 task 工具的 ToolDefinition"""
    from core.multi_agent_v2.tools.tool_registry import ToolDefinition, SERVER_BUILTIN

    return ToolDefinition(
        name="task",
        server=SERVER_BUILTIN,
        tags=["agent", "subagent", "delegation"],
        description=_builder.get_tool_desc("task"),
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "简短描述 (3-5 词)",
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "子代理要执行的完整任务。必须包含：\n"
                        "1. 清晰的任务描述\n"
                        "2. 预期的输出格式（返回什么信息）\n"
                        "3. 是否需要写代码还是只做研究\n"
                        "4. 如何验证结果（如相关测试命令）"
                    ),
                },
                "subagent_type": {
                    "type": "string",
                    "enum": ["explore", "build", "general", "analyze"],
                    "description": "子代理类型",
                },
                "task_id": {
                    "type": "string",
                    "description": "恢复已有子代理时传入其 session_id",
                },
                "background": {
                    "type": "boolean",
                    "description": "后台执行（不等待结果即返回）",
                },
            },
            "required": ["description", "prompt", "subagent_type"],
        },
        handler=_handle_task,
    )


def get_orchestrate_tool_def():
    """返回 orchestrate 工具的 ToolDefinition"""
    from core.multi_agent_v2.tools.tool_registry import ToolDefinition, SERVER_BUILTIN

    return ToolDefinition(
        name="orchestrate",
        server=SERVER_BUILTIN,
        tags=["agent", "orchestrate", "parallel"],
        description=_builder.get_tool_desc("orchestrate"),
        parameters={
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "任务唯一标识"},
                            "description": {"type": "string", "description": "简短描述 (3-5 词)"},
                            "prompt": {"type": "string", "description": "子代理的完整任务提示"},
                            "agent": {
                                "type": "string",
                                "enum": ["explore", "build", "general", "analyze"],
                                "description": "代理类型"
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "依赖的其他任务 id 列表"
                            },
                        },
                        "required": ["id", "description", "prompt"],
                    },
                    "description": "任务列表",
                },
                "max_concurrent": {
                    "type": "integer",
                    "description": "最大并发数（默认5）",
                },
            },
            "required": ["tasks"],
        },
        handler=_handle_orchestrate,
    )


def register_subagent_tools(extra: dict = None) -> List[str]:
    """将 task + orchestrate 工具注册到全局 V2 ToolRegistry

    在 run_unified() 或 run_react() 初始化时调用。
    幂等调用 — 重复注册不会重复添加。

    Returns:
        注册的工具名列表
    """
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()

    registered = []
    for name, getter in [
        ("task", get_task_tool_def),
        ("orchestrate", get_orchestrate_tool_def),
    ]:
        if name not in registry._tools:
            td = getter()
            registry.register({name: td})
            registered.append(name)
            logger.info(f"Subagent 工具已注册: {name}")

    # 注册额外工具（调用方传入）
    if extra:
        for name, getter in extra.items():
            if name not in registry._tools:
                registry.register({name: getter()})
                registered.append(name)

    return registered
