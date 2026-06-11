"""
Write工具 - 参考Open Code的WriteTool实现

支持：
- 文件写入
- 目录创建
- BOM处理
- 写入元数据
"""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging
from pathlib import Path

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)


@dataclass
class WriteInput(ToolInput):
    """Write工具输入"""
    path: str
    content: str


@dataclass
class WriteOutput(ToolOutput):
    """Write工具输出"""
    operation: str  # "write" 或 "create"
    target: str
    resource: str
    existed: bool
    size: int = 0


class WriteTool(Tool[WriteInput, WriteOutput]):
    """Write工具 - 参考Open Code的WriteTool"""

    def __init__(self):
        super().__init__(
            name="write",
            description="Write content to one file. Relative paths resolve within the active Location. Absolute paths inside the Location are accepted.",
            permission=ToolPermission.WRITE,
            timeout=30,
            max_retries=1
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to write. Relative paths resolve within the active Location."
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["path", "content"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["write", "create"]},
                "target": {"type": "string"},
                "resource": {"type": "string"},
                "existed": {"type": "boolean"},
                "size": {"type": "integer"}
            }
        }

    def validate_input(self, input_data: Any) -> WriteInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return WriteInput(
                path=input_data.get("path", ""),
                content=input_data.get("content", "")
            )
        elif isinstance(input_data, WriteInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: WriteInput) -> WriteOutput:
        """执行写入操作"""
        path = input_data.path
        content = input_data.content

        # 检查文件是否已存在
        existed = os.path.exists(path)

        # 确保目录存在
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # 处理BOM
        bom = False
        if content.startswith('\ufeff'):
            bom = True
            content = content[1:]

        # 写入文件
        try:
            with open(path, 'w', encoding='utf-8') as f:
                if bom:
                    f.write('\ufeff')
                f.write(content)
            
            # 获取文件大小
            size = os.path.getsize(path)
            
            # 确定操作类型
            operation = "write" if existed else "create"
            
            logger.info(f"文件写入成功: {path}")
            
            return WriteOutput(
                operation=operation,
                target=path,
                resource=path,
                existed=existed,
                size=size
            )

        except Exception as e:
            logger.error(f"写入文件失败 {path}: {e}")
            raise


# 注册工具
write_tool = WriteTool()
