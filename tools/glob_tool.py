"""
Glob工具 - 参考Open Code的GlobTool实现

支持：
- 文件模式匹配
- 递归搜索
- 结果限制
"""

import os
import fnmatch
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import logging
from pathlib import Path

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)

# 默认结果限制
DEFAULT_RESULT_LIMIT = 200


@dataclass
class GlobInput(ToolInput):
    """Glob工具输入"""
    pattern: str
    path: Optional[str] = None
    limit: Optional[int] = None


@dataclass
class GlobItem:
    """Glob结果项"""
    resource: str
    name: str
    type: str  # "file" 或 "directory"


@dataclass
class GlobOutput(ToolOutput):
    """Glob工具输出"""
    items: List[GlobItem]
    truncated: bool
    partial: bool
    total: int


class GlobTool(Tool[GlobInput, GlobOutput]):
    """Glob工具 - 参考Open Code的GlobTool"""

    def __init__(self):
        super().__init__(
            name="glob",
            description="Find files by glob pattern within the active Location. Returns concise relative file resources.",
            permission=ToolPermission.READ,
            timeout=30,
            max_retries=1
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files against"
                },
                "path": {
                    "type": "string",
                    "description": "Relative directory to search. Defaults to the active Location."
                },
                "limit": {
                    "type": "integer",
                    "description": f"Maximum results to return (default: {DEFAULT_RESULT_LIMIT})",
                    "minimum": 1
                }
            },
            "required": ["pattern"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "resource": {"type": "string"},
                            "name": {"type": "string"},
                            "type": {"type": "string", "enum": ["file", "directory"]}
                        }
                    }
                },
                "truncated": {"type": "boolean"},
                "partial": {"type": "boolean"},
                "total": {"type": "integer"}
            }
        }

    def validate_input(self, input_data: Any) -> GlobInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return GlobInput(
                pattern=input_data.get("pattern", ""),
                path=input_data.get("path"),
                limit=input_data.get("limit")
            )
        elif isinstance(input_data, GlobInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: GlobInput) -> GlobOutput:
        """执行文件搜索"""
        pattern = input_data.pattern
        path = input_data.path or "."
        limit = input_data.limit or DEFAULT_RESULT_LIMIT

        # 检查路径是否存在
        if not os.path.exists(path):
            raise FileNotFoundError(f"目录不存在: {path}")

        if not os.path.isdir(path):
            raise ValueError(f"路径不是目录: {path}")

        # 搜索文件
        matches = []
        truncated = False
        partial = False

        try:
            # 使用Path.rglob进行递归搜索
            path_obj = Path(path)
            for item in path_obj.rglob("*"):
                # 检查是否匹配模式
                if fnmatch.fnmatch(item.name, pattern) or fnmatch.fnmatch(str(item), pattern):
                    # 检查限制
                    if len(matches) >= limit:
                        truncated = True
                        break

                    # 获取相对路径
                    try:
                        relative_path = item.relative_to(path)
                    except ValueError:
                        relative_path = item

                    matches.append(GlobItem(
                        resource=str(relative_path),
                        name=item.name,
                        type="file" if item.is_file() else "directory"
                    ))

        except PermissionError:
            partial = True
            logger.warning(f"无权访问某些目录: {path}")
        except Exception as e:
            partial = True
            logger.error(f"搜索文件时出错: {e}")

        return GlobOutput(
            items=matches,
            truncated=truncated,
            partial=partial,
            total=len(matches)
        )


# 注册工具
glob_tool = GlobTool()
