"""
ApplyPatch工具 - 参考Open Code的ApplyPatchTool实现

支持：
- 补丁应用
- 文件添加/更新/删除
- 多文件操作
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import logging
from pathlib import Path

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)


@dataclass
class PatchHunk:
    """补丁块"""
    type: str  # "add", "update", "delete"
    path: str
    contents: str = ""
    chunks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AppliedOperation:
    """已应用的操作"""
    type: str  # "add", "update", "delete"
    resource: str
    target: str


@dataclass
class ApplyPatchInput(ToolInput):
    """ApplyPatch工具输入"""
    patch_text: str


@dataclass
class ApplyPatchOutput(ToolOutput):
    """ApplyPatch工具输出"""
    applied: List[AppliedOperation]
    success: bool
    error: Optional[str] = None


class ApplyPatchTool(Tool[ApplyPatchInput, ApplyPatchOutput]):
    """ApplyPatch工具 - 参考Open Code的ApplyPatchTool"""

    def __init__(self):
        super().__init__(
            name="apply_patch",
            description="Apply one patch containing add, update, and delete file operations.",
            permission=ToolPermission.WRITE,
            timeout=60,
            max_retries=1
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patch_text": {
                    "type": "string",
                    "description": "The full patch text describing add, update, and delete operations"
                }
            },
            "required": ["patch_text"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "applied": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["add", "update", "delete"]},
                            "resource": {"type": "string"},
                            "target": {"type": "string"}
                        }
                    }
                },
                "success": {"type": "boolean"},
                "error": {"type": "string"}
            }
        }

    def validate_input(self, input_data: Any) -> ApplyPatchInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return ApplyPatchInput(patch_text=input_data.get("patch_text", ""))
        elif isinstance(input_data, ApplyPatchInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: ApplyPatchInput) -> ApplyPatchOutput:
        """执行补丁应用"""
        patch_text = input_data.patch_text

        if not patch_text.strip():
            return ApplyPatchOutput(
                applied=[],
                success=False,
                error="patch_text is required"
            )

        # 解析补丁
        try:
            hunks = self._parse_patch(patch_text)
        except Exception as e:
            return ApplyPatchOutput(
                applied=[],
                success=False,
                error=f"Failed to parse patch: {str(e)}"
            )

        if not hunks:
            return ApplyPatchOutput(
                applied=[],
                success=False,
                error="patch rejected: empty patch"
            )

        # 应用补丁
        applied = []
        for hunk in hunks:
            try:
                if hunk.type == "add":
                    result = self._apply_add(hunk)
                elif hunk.type == "delete":
                    result = self._apply_delete(hunk)
                elif hunk.type == "update":
                    result = self._apply_update(hunk)
                else:
                    continue

                if result:
                    applied.append(result)

            except Exception as e:
                logger.error(f"Failed to apply hunk: {e}")
                return ApplyPatchOutput(
                    applied=applied,
                    success=False,
                    error=f"Failed to apply patch at {hunk.path}: {str(e)}"
                )

        return ApplyPatchOutput(
            applied=applied,
            success=True
        )

    def _parse_patch(self, patch_text: str) -> List[PatchHunk]:
        """解析补丁文本"""
        hunks = []
        lines = patch_text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # 跳过空行和注释
            if not line or line.startswith('#'):
                i += 1
                continue

            # 解析文件操作
            if line.startswith('---') or line.startswith('+++'):
                # 这是diff格式，跳过
                i += 1
                continue

            # 解析自定义补丁格式
            # 格式: <type> <path>
            # 例如: add src/new_file.js
            #       update src/existing_file.js
            #       delete src/old_file.js
            
            match = re.match(r'^(add|update|delete|create)\s+(.+)$', line)
            if match:
                op_type = match.group(1)
                path = match.group(2)
                
                # 收集内容直到下一个操作或文件结束
                contents = []
                i += 1
                while i < len(lines):
                    next_line = lines[i].strip()
                    if next_line.startswith(('add ', 'update ', 'delete ', 'create ')):
                        break
                    if next_line == '---':  # 内容分隔符
                        i += 1
                        while i < len(lines):
                            next_line = lines[i].strip()
                            if next_line == '---' or next_line.startswith(('add ', 'update ', 'delete ', 'create ')):
                                break
                            contents.append(lines[i])
                            i += 1
                        break
                    contents.append(lines[i])
                    i += 1
                
                # 规范化类型
                if op_type == "create":
                    op_type = "add"
                
                hunks.append(PatchHunk(
                    type=op_type,
                    path=path,
                    contents='\n'.join(contents)
                ))
            else:
                i += 1

        return hunks

    def _apply_add(self, hunk: PatchHunk) -> Optional[AppliedOperation]:
        """应用添加操作"""
        path = hunk.path
        
        # 检查文件是否已存在
        if os.path.exists(path):
            raise ValueError(f"File already exists: {path}")

        # 确保目录存在
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # 写入文件
        with open(path, 'w', encoding='utf-8') as f:
            content = hunk.contents
            if content and not content.endswith('\n'):
                content += '\n'
            f.write(content)

        return AppliedOperation(
            type="add",
            resource=path,
            target=path
        )

    def _apply_delete(self, hunk: PatchHunk) -> Optional[AppliedOperation]:
        """应用删除操作"""
        path = hunk.path
        
        # 检查文件是否存在
        if not os.path.exists(path):
            raise ValueError(f"File does not exist: {path}")

        # 删除文件
        os.remove(path)

        return AppliedOperation(
            type="delete",
            resource=path,
            target=path
        )

    def _apply_update(self, hunk: PatchHunk) -> Optional[AppliedOperation]:
        """应用更新操作"""
        path = hunk.path
        
        # 检查文件是否存在
        if not os.path.exists(path):
            raise ValueError(f"File does not exist: {path}")

        # 读取现有内容
        with open(path, 'r', encoding='utf-8') as f:
            existing_content = f.read()

        # 应用更新
        # 这里简化处理，直接替换内容
        # 实际应用中应该支持更复杂的diff操作
        with open(path, 'w', encoding='utf-8') as f:
            content = hunk.contents
            if content and not content.endswith('\n'):
                content += '\n'
            f.write(content)

        return AppliedOperation(
            type="update",
            resource=path,
            target=path
        )


# 注册工具
apply_patch_tool = ApplyPatchTool()
