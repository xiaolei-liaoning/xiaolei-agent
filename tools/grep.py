"""
Grep工具 - 参考Open Code的GrepTool实现

支持：
- 正则表达式搜索
- 文件内容搜索
- 结果限制
"""

import os
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import logging
from pathlib import Path

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)

# 默认结果限制
DEFAULT_RESULT_LIMIT = 200
# 行预览最大长度
MAX_LINE_PREVIEW = 240


@dataclass
class GrepInput(ToolInput):
    """Grep工具输入"""
    pattern: str
    path: Optional[str] = None
    include: Optional[str] = None
    limit: Optional[int] = None


@dataclass
class GrepMatch:
    """Grep匹配项"""
    resource: str
    line: int
    lines: str
    line_preview_truncated: bool = False


@dataclass
class GrepOutput(ToolOutput):
    """Grep工具输出"""
    items: List[GrepMatch]
    truncated: bool
    partial: bool
    total: int


class GrepTool(Tool[GrepInput, GrepOutput]):
    """Grep工具 - 参考Open Code的GrepTool"""

    def __init__(self):
        super().__init__(
            name="grep",
            description="Search file contents by regular expression within the active Location.",
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
                    "description": "Regex pattern to search for in file contents"
                },
                "path": {
                    "type": "string",
                    "description": "Relative file or directory to search. Defaults to the active Location."
                },
                "include": {
                    "type": "string",
                    "description": 'File glob to include in the search (for example, "*.js" or "*.{ts,tsx}")'
                },
                "limit": {
                    "type": "integer",
                    "description": f"Maximum matches to return (default: {DEFAULT_RESULT_LIMIT})",
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
                            "line": {"type": "integer"},
                            "lines": {"type": "string"},
                            "line_preview_truncated": {"type": "boolean"}
                        }
                    }
                },
                "truncated": {"type": "boolean"},
                "partial": {"type": "boolean"},
                "total": {"type": "integer"}
            }
        }

    def validate_input(self, input_data: Any) -> GrepInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return GrepInput(
                pattern=input_data.get("pattern", ""),
                path=input_data.get("path"),
                include=input_data.get("include"),
                limit=input_data.get("limit")
            )
        elif isinstance(input_data, GrepInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: GrepInput) -> GrepOutput:
        """执行内容搜索"""
        pattern = input_data.pattern
        path = input_data.path or "."
        include = input_data.include
        limit = input_data.limit or DEFAULT_RESULT_LIMIT

        # 编译正则表达式
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"无效的正则表达式: {pattern} - {e}")

        # 检查路径是否存在
        if not os.path.exists(path):
            raise FileNotFoundError(f"路径不存在: {path}")

        # 搜索文件
        matches = []
        truncated = False
        partial = False

        try:
            path_obj = Path(path)
            
            # 确定要搜索的文件
            if path_obj.is_file():
                files_to_search = [path_obj]
            else:
                # 使用include模式过滤文件
                if include:
                    files_to_search = list(path_obj.rglob(include))
                else:
                    files_to_search = list(path_obj.rglob("*"))

            # 搜索每个文件
            for file_path in files_to_search:
                if not file_path.is_file():
                    continue

                # 检查限制
                if len(matches) >= limit:
                    truncated = True
                    break

                try:
                    # 读取文件
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()

                    # 搜索匹配项
                    for line_num, line in enumerate(lines, 1):
                        if regex.search(line):
                            # 截断行预览
                            line_preview = line.rstrip('\n')
                            line_preview_truncated = False
                            if len(line_preview) > MAX_LINE_PREVIEW:
                                line_preview = line_preview[:MAX_LINE_PREVIEW] + "..."
                                line_preview_truncated = True

                            matches.append(GrepMatch(
                                resource=str(file_path),
                                line=line_num,
                                lines=line_preview,
                                line_preview_truncated=line_preview_truncated
                            ))

                            # 检查限制
                            if len(matches) >= limit:
                                truncated = True
                                break

                except (PermissionError, UnicodeDecodeError):
                    partial = True
                    continue
                except Exception as e:
                    partial = True
                    logger.warning(f"搜索文件时出错 {file_path}: {e}")
                    continue

        except Exception as e:
            partial = True
            logger.error(f"搜索内容时出错: {e}")

        return GrepOutput(
            items=matches,
            truncated=truncated,
            partial=partial,
            total=len(matches)
        )


# 注册工具
grep_tool = GrepTool()
