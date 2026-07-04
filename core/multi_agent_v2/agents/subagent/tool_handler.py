"""Subagent 工具处理器 — 注册到 V2 ToolRegistry 中

作为 LLM 可调用的内置工具：
- task: 生成单个子代理（foreground/background）
- orchestrate: DAG 并行编排多个子代理
"""

import asyncio
import logging
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
            timeout=600,  # 10 分钟超时
        )
        return result
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "子代理执行超时 (600s)",
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

_AGENT_TYPE_DESCRIPTIONS = {
    "explore": "代码库探索专家 — 用 glob/grep/read_file 快速查找和读取文件。只读，不修改任何文件。调用时指定彻底程度：quick（快速定位）/ medium（适度深入）/ very thorough（全面覆盖）。",
    "build": "构建型代理 — 读写文件、执行代码、运行测试。适合 bug 修复、功能实现、重构。工作流：读→改→验证。",
    "general": "通用代理 — 执行复杂多步骤任务。可使用所有工具。适合需要研究和执行混合的场景。",
    "analyze": "分析型代理 — 深度阅读、搜索和分析。可读文件和搜索代码，不能编辑或创建文件。按重要性排序呈现结构化结论。",
}

_AGENT_TYPES_LIST = "\n".join(
    f"- {name}: {desc}"
    for name, desc in _AGENT_TYPE_DESCRIPTIONS.items()
)


def _build_task_description() -> str:
    """构建 task 工具描述，注入可用代理类型列表"""
    return f"""启动一个专门的子代理来处理复杂的多步骤任务。子代理自主运行并返回一条完整结果消息。

使用 Task 工具时，必须指定 subagent_type 参数来选择代理类型。

**何时不要用 Task 工具：**
- 如果要读取已知路径的具体文件，直接用 Read 工具更快
- 如果要搜索类定义如 "class Foo"，直接用 Grep 工具更快
- 如果要搜索 2-3 个特定文件内的代码，直接用 Read 工具更快
- 如果没有合适的代理类型匹配任务，直接用其他工具

**使用指南：**
1. 尽量并发启动多个代理，一次消息里调用多次 tool
2. 一旦委托了任务，不要重复做同样的工作。等结果或继续做不重叠的任务
3. 代理完成后会返回一条消息给你。这个结果不会直接展示给用户——你需要用文字消息总结后回复用户
4. 可通过 task_id 参数恢复已有子代理继续对话
5. 每次调用都从干净上下文开始（除非提供 task_id），你的 prompt 应包含代理需要的全部信息，以及明确告诉它要返回什么
6. 子代理的输出一般应该信任
7. 明确告诉代理它是写代码还是做研究（因为它不知道用户意图）。如果涉及代码，告诉它用哪个测试命令验证
8. 如果代理类型描述中提到应主动使用，积极使用

**可用代理类型及其拥有的工具：**
{_AGENT_TYPES_LIST}
"""


def _build_orchestrate_description() -> str:
    """构建 orchestrate 工具描述"""
    return f"""使用多个子代理并行或按依赖关系执行多个任务。支持 DAG 依赖。

无依赖的任务同时并行运行。有依赖的任务等待前置任务完成。
每个任务有自己的子代理会话，有适当的权限。
前置任务的结果自动作为上下文传递给依赖任务。

**何时使用：**
- 多个独立研究任务（如"探索代码库" + "搜索网页" + "阅读文档"）
- 流水线任务，每步依赖前一步（如"读取文件" → "分析" → "总结"）
- 混合并行 + 顺序工作流

**何时不要用：**
- 单个简单任务（用普通 task 工具即可）
- 需要共享可变状态的任务（每个子代理独立，不能互访）

**可用代理类型：**
{_AGENT_TYPES_LIST}
"""


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
        description=_build_task_description(),
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
        description=_build_orchestrate_description(),
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
