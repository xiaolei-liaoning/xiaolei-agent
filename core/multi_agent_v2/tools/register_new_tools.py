"""
新工具注册到原有系统

将tools/目录下的新工具注册到core/multi_agent_v2/tools/tool_registry.py中
"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 添加tools目录到路径
tools_dir = os.path.join(project_root, 'tools')
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from core.multi_agent_v2.tools.tool_registry import ToolDefinition, ToolDomain, SERVER_BUILTIN


def _handle_question(args: dict) -> str:
    """Question工具handler"""
    from question import QuestionTool
    tool = QuestionTool()
    input_data = tool.validate_input(args)
    result = tool.execute(input_data)
    return result.message


def _handle_skill(args: dict) -> str:
    """Skill工具handler"""
    from skill import SkillTool
    tool = SkillTool()
    input_data = tool.validate_input(args)
    result = tool.execute(input_data)

    if result.success:
        return result.output
    else:
        return f"加载技能失败: {result.error}"


def _handle_apply_patch(args: dict) -> str:
    """ApplyPatch工具handler"""
    from apply_patch import ApplyPatchTool
    tool = ApplyPatchTool()
    input_data = tool.validate_input(args)
    result = tool.execute(input_data)

    if result.success:
        ops = [f"{op.type}: {op.resource}" for op in result.applied]
        return f"补丁应用成功:\n" + "\n".join(ops)
    else:
        return f"补丁应用失败: {result.error}"


# 仅保留未迁移至 _SANDBOX_TOOL_DEFS 的工具
# bash → execute_shell, fetch_webpage → fetch_url, read_file/edit_file/glob_search/grep_search/todo_write 已迁移
NEW_TOOL_DEFINITIONS = [
    ToolDefinition(
        name="ask_user",
        server=SERVER_BUILTIN,
        tags=["interaction", "question", "user"],
        domains={ToolDomain.MISC},
        description="向用户提问。支持多选、自定义输入。用于获取用户反馈、澄清需求。",
        parameters={
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {"type": "array", "items": {"type": "object"}},
                            "multiple": {"type": "boolean"},
                        },
                        "required": ["question"],
                    },
                    "description": "问题列表",
                },
            },
            "required": ["questions"],
        },
        handler=_handle_question,
    ),
    ToolDefinition(
        name="load_skill",
        server=SERVER_BUILTIN,
        tags=["skill", "load"],
        domains={ToolDomain.SKILL},
        description="加载技能。用于获取特定任务的专业指导和工作流程。",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "技能名称"},
            },
            "required": ["name"],
        },
        handler=_handle_skill,
    ),
    ToolDefinition(
        name="apply_patch",
        server=SERVER_BUILTIN,
        tags=["file", "patch", "edit"],
        domains={ToolDomain.FILE},
        description="应用补丁。支持文件添加、更新、删除操作。用于批量修改文件。",
        parameters={
            "type": "object",
            "properties": {
                "patch_text": {"type": "string", "description": "补丁文本"},
            },
            "required": ["patch_text"],
        },
        handler=_handle_apply_patch,
    ),
]


import asyncio
from typing import Callable


def _make_async_handler(sync_fn: Callable) -> Callable:
    """将同步handler包装为async handler，使其兼容await调用"""
    async def async_handler(args: dict):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sync_fn, args)
    return async_handler


def register_new_tools(registry):
    """将新工具注册到ToolRegistry"""
    for tool_def in NEW_TOOL_DEFINITIONS:
        if tool_def.name not in registry._tools:
            # 包装handler为async版本
            if tool_def.handler and not asyncio.iscoroutinefunction(tool_def.handler):
                tool_def.handler = _make_async_handler(tool_def.handler)
            registry._tools[tool_def.name] = tool_def


if __name__ == "__main__":
    from core.multi_agent_v2.tools.tool_registry import get_tool_registry
    
    # 获取全局注册表实例
    registry = get_tool_registry()
    
    # 注册新工具（在discover_all之前）
    register_new_tools(registry)
    
    # 然后初始化内置工具
    import asyncio
    asyncio.run(registry.discover_all())
    
    # 列出所有工具
    print(f"\n总工具数: {registry.count}")
    
    # 列出所有工具名称
    print("\n所有工具:")
    for name in sorted(registry._tools.keys()):
        tool = registry.get_tool(name)
        print(f"  - {name}")
