"""
Read工具 - 参考Open Code的ReadTool实现

支持：
- 文件读取
- 目录列表
- 分页读取
- 图片支持
"""

import os
import mimetypes
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Union
import logging
from pathlib import Path

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)

# 支持的图片MIME类型
SUPPORTED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# 默认分页大小
DEFAULT_PAGE_SIZE = 2000


@dataclass
class ReadInput(ToolInput):
    """Read工具输入"""
    path: str
    offset: Optional[int] = None
    limit: Optional[int] = None


@dataclass
class TextPage:
    """文本文件分页"""
    type: str = "text"
    content: str = ""
    total_lines: int = 0
    offset: int = 0
    limit: int = 0
    has_more: bool = False


@dataclass
class ListPage:
    """目录列表分页"""
    type: str = "list"
    items: List[Dict[str, Any]] = None
    total: int = 0
    offset: int = 0
    limit: int = 0
    has_more: bool = False

    def __post_init__(self):
        if self.items is None:
            self.items = []


@dataclass
class BinaryContent:
    """二进制内容（图片等）"""
    type: str = "binary"
    content: str = ""  # Base64编码的内容
    mime: str = ""


ReadOutput = Union[TextPage, ListPage, BinaryContent, str]


class ReadTool(Tool[ReadInput, ReadOutput]):
    """Read工具 - 参考Open Code的ReadTool"""

    def __init__(self):
        super().__init__(
            name="read",
            description="Read a text file or supported image, page through a large UTF-8 text file by line offset, or list a directory page relative to the current location.",
            permission=ToolPermission.READ,
            timeout=30,
            max_retries=1
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to read"
                },
                "offset": {
                    "type": "integer",
                    "description": "The 1-based directory entry or text line offset to start reading from",
                    "minimum": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "The maximum number of directory entries or text lines to read",
                    "minimum": 1
                }
            },
            "required": ["path"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["text"]},
                        "content": {"type": "string"},
                        "total_lines": {"type": "integer"},
                        "offset": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "has_more": {"type": "boolean"}
                    }
                },
                {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["list"]},
                        "items": {"type": "array"},
                        "total": {"type": "integer"},
                        "offset": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "has_more": {"type": "boolean"}
                    }
                },
                {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["binary"]},
                        "content": {"type": "string"},
                        "mime": {"type": "string"}
                    }
                },
                {"type": "string"}
            ]
        }

    def validate_input(self, input_data: Any) -> ReadInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return ReadInput(
                path=input_data.get("path", ""),
                offset=input_data.get("offset"),
                limit=input_data.get("limit")
            )
        elif isinstance(input_data, ReadInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: ReadInput) -> ReadOutput:
        """执行读取操作"""
        path = input_data.path
        
        # 检查路径是否存在
        if not os.path.exists(path):
            raise FileNotFoundError(f"文件或目录不存在: {path}")

        # 如果是目录，返回目录列表
        if os.path.isdir(path):
            return self._list_directory(path, input_data.offset, input_data.limit)

        # 如果是文件，读取文件内容
        return self._read_file(path, input_data.offset, input_data.limit)

    def _read_file(self, path: str, offset: Optional[int] = None, limit: Optional[int] = None) -> ReadOutput:
        """读取文件内容"""
        # 检查是否是图片
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type and mime_type in SUPPORTED_IMAGE_MIMES:
            return self._read_image(path, mime_type)

        # 读取文本文件
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # 尝试其他编码
            try:
                with open(path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()
            except Exception as e:
                raise ValueError(f"无法读取文件（编码错误）: {path}")

        total_lines = len(lines)
        
        # 应用分页
        if offset is not None:
            start = max(0, offset - 1)  # 转换为0-based索引
        else:
            start = 0

        if limit is not None:
            end = start + limit
        else:
            end = total_lines

        # 获取指定范围的行
        selected_lines = lines[start:end]
        content = ''.join(selected_lines)

        return TextPage(
            content=content,
            total_lines=total_lines,
            offset=start + 1,  # 转换为1-based
            limit=len(selected_lines),
            has_more=end < total_lines
        )

    def _read_image(self, path: str, mime_type: str) -> BinaryContent:
        """读取图片文件"""
        import base64
        try:
            with open(path, 'rb') as f:
                content = base64.b64encode(f.read()).decode('utf-8')
            return BinaryContent(
                content=content,
                mime=mime_type
            )
        except Exception as e:
            raise ValueError(f"无法读取图片: {path}")

    def _list_directory(self, path: str, offset: Optional[int] = None, limit: Optional[int] = None) -> ListPage:
        """列出目录内容"""
        try:
            entries = []
            for entry in sorted(Path(path).iterdir()):
                stat = entry.stat()
                entries.append({
                    'name': entry.name,
                    'path': str(entry),
                    'type': 'file' if entry.is_file() else 'directory',
                    'size': stat.st_size if entry.is_file() else None,
                    'modified': stat.st_mtime
                })
        except PermissionError:
            raise ValueError(f"无权访问目录: {path}")

        total = len(entries)
        
        # 应用分页
        if offset is not None:
            start = max(0, offset - 1)  # 转换为0-based索引
        else:
            start = 0

        if limit is not None:
            end = start + limit
        else:
            end = total

        # 获取指定范围的条目
        selected_entries = entries[start:end]

        return ListPage(
            items=selected_entries,
            total=total,
            offset=start + 1,  # 转换为1-based
            limit=len(selected_entries),
            has_more=end < total
        )


# 注册工具
read_tool = ReadTool()
