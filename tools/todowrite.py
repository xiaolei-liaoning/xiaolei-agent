"""
TodoWrite工具 - 参考Open Code的TodoWriteTool实现

支持：
- 任务列表管理
- 任务状态更新
- 任务优先级
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import logging
import json
from datetime import datetime

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)


@dataclass
class TodoItem:
    """任务项"""
    id: str
    content: str
    status: str  # "pending", "in_progress", "completed", "cancelled"
    priority: str = "medium"  # "low", "medium", "high"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TodoWriteInput(ToolInput):
    """TodoWrite工具输入"""
    todos: List[Dict[str, Any]]


@dataclass
class TodoWriteOutput(ToolOutput):
    """TodoWrite工具输出"""
    todos: List[Dict[str, Any]]
    updated_count: int
    message: str


class TodoWriteTool(Tool[TodoWriteInput, TodoWriteOutput]):
    """TodoWrite工具 - 参考Open Code的TodoWriteTool"""

    def __init__(self):
        super().__init__(
            name="todowrite",
            description="Create and maintain a structured task list for the current coding session. Use it to track progress during multi-step work and keep todo statuses current.",
            permission=ToolPermission.WRITE,
            timeout=30,
            max_retries=1
        )
        self._todos: List[TodoItem] = []

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                            "metadata": {"type": "object"}
                        },
                        "required": ["content"]
                    },
                    "description": "The updated todo list"
                }
            },
            "required": ["todos"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {"type": "object"}
                },
                "updated_count": {"type": "integer"},
                "message": {"type": "string"}
            }
        }

    def validate_input(self, input_data: Any) -> TodoWriteInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return TodoWriteInput(todos=input_data.get("todos", []))
        elif isinstance(input_data, TodoWriteInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: TodoWriteInput) -> TodoWriteOutput:
        """执行任务更新"""
        updated_todos = []
        updated_count = 0

        for todo_data in input_data.todos:
            # 确保有ID
            if "id" not in todo_data:
                todo_data["id"] = f"todo_{len(self._todos) + 1}"

            # 查找现有任务
            existing_todo = None
            for todo in self._todos:
                if todo.id == todo_data["id"]:
                    existing_todo = todo
                    break

            if existing_todo:
                # 更新现有任务
                if "content" in todo_data:
                    existing_todo.content = todo_data["content"]
                if "status" in todo_data:
                    existing_todo.status = todo_data["status"]
                if "priority" in todo_data:
                    existing_todo.priority = todo_data["priority"]
                if "metadata" in todo_data:
                    existing_todo.metadata.update(todo_data["metadata"])
                existing_todo.updated_at = datetime.now().isoformat()
                updated_todos.append(self._todo_to_dict(existing_todo))
                updated_count += 1
            else:
                # 创建新任务
                new_todo = TodoItem(
                    id=todo_data["id"],
                    content=todo_data.get("content", ""),
                    status=todo_data.get("status", "pending"),
                    priority=todo_data.get("priority", "medium"),
                    metadata=todo_data.get("metadata", {})
                )
                self._todos.append(new_todo)
                updated_todos.append(self._todo_to_dict(new_todo))
                updated_count += 1

        # 生成消息
        if updated_count > 0:
            message = f"成功更新 {updated_count} 个任务"
        else:
            message = "没有任务被更新"

        logger.info(f"任务更新: {message}")

        return TodoWriteOutput(
            todos=updated_todos,
            updated_count=updated_count,
            message=message
        )

    def _todo_to_dict(self, todo: TodoItem) -> Dict[str, Any]:
        """将TodoItem转换为字典"""
        return {
            "id": todo.id,
            "content": todo.content,
            "status": todo.status,
            "priority": todo.priority,
            "created_at": todo.created_at,
            "updated_at": todo.updated_at,
            "metadata": todo.metadata
        }

    def get_todos(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        return [self._todo_to_dict(todo) for todo in self._todos]

    def clear_todos(self):
        """清空所有任务"""
        self._todos.clear()
        logger.info("任务列表已清空")


# 注册工具
todowrite_tool = TodoWriteTool()
