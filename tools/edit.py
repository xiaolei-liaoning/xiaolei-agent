"""
Edit工具 - 参考Open Code的EditTool实现

支持：
- 精确文本替换
- 替换所有匹配项
- 行尾处理
- BOM处理
"""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)


@dataclass
class EditInput(ToolInput):
    """Edit工具输入"""
    path: str
    old_string: str
    new_string: str
    replace_all: bool = False


@dataclass
class EditOutput(ToolOutput):
    """Edit工具输出"""
    operation: str  # "write"
    target: str
    resource: str
    existed: bool
    replacements: int


class EditTool(Tool[EditInput, EditOutput]):
    """Edit工具 - 参考Open Code的EditTool"""

    def __init__(self):
        super().__init__(
            name="edit",
            description="Replace exact text in one file. Relative paths resolve within the active Location.",
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
                    "description": "File path to edit. Relative paths resolve within the active Location."
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact text to replace"
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement text, which must differ from old_string"
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all exact occurrences of old_string (default false)"
                }
            },
            "required": ["path", "old_string", "new_string"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["write"]},
                "target": {"type": "string"},
                "resource": {"type": "string"},
                "existed": {"type": "boolean"},
                "replacements": {"type": "integer"}
            }
        }

    def validate_input(self, input_data: Any) -> EditInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return EditInput(
                path=input_data.get("path", ""),
                old_string=input_data.get("old_string", ""),
                new_string=input_data.get("new_string", ""),
                replace_all=input_data.get("replace_all", False)
            )
        elif isinstance(input_data, EditInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: EditInput) -> EditOutput:
        """执行编辑操作"""
        path = input_data.path
        old_string = input_data.old_string
        new_string = input_data.new_string
        replace_all = input_data.replace_all

        # 验证输入
        if old_string == new_string:
            raise ValueError("No changes to apply: old_string and new_string are identical.")
        
        if old_string == "":
            raise ValueError("old_string must not be empty. Use write to create or overwrite a file.")

        # 检查文件是否存在
        if not os.path.exists(path):
            raise FileNotFoundError(f"文件不存在: {path}")

        # 读取文件内容
        try:
            # 处理BOM
            with open(path, 'rb') as f:
                raw_content = f.read()
            
            bom = raw_content[:3] == b'\xef\xbb\xbf'
            if bom:
                content = raw_content[3:].decode('utf-8')
            else:
                content = raw_content.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError(f"无法读取文件（编码错误）: {path}")

        # 检测行尾
        ending = self._detect_line_ending(content)
        
        # 转换行尾
        old_string_converted = self._convert_line_ending(old_string, ending)
        new_string_converted = self._convert_line_ending(new_string, ending)

        # 计算替换次数
        replacements = self._count_occurrences(content, old_string_converted)
        
        if replacements == 0:
            raise ValueError(
                "Could not find old_string in the file. It must match exactly, including whitespace and indentation."
            )
        
        if replacements > 1 and not replace_all:
            raise ValueError(
                "Found multiple exact matches for old_string. Provide more surrounding context or set replace_all to true."
            )

        # 执行替换
        if replace_all:
            new_content = content.replace(old_string_converted, new_string_converted)
        else:
            new_content = content.replace(old_string_converted, new_string_converted, 1)

        # 写入文件
        try:
            with open(path, 'wb') as f:
                if bom:
                    f.write(b'\xef\xbb\xbf')
                f.write(new_content.encode('utf-8'))
            
            # 获取文件大小
            size = os.path.getsize(path)
            
            logger.info(f"文件编辑成功: {path}, 替换了 {replacements} 处")
            
            return EditOutput(
                operation="write",
                target=path,
                resource=path,
                existed=True,
                replacements=replacements
            )

        except Exception as e:
            logger.error(f"编辑文件失败 {path}: {e}")
            raise

    def _detect_line_ending(self, text: str) -> str:
        """检测行尾字符"""
        if "\r\n" in text:
            return "\r\n"
        return "\n"

    def _convert_line_ending(self, text: str, ending: str) -> str:
        """转换行尾字符"""
        if ending == "\r\n":
            return text.replace("\n", "\r\n")
        return text.replace("\r\n", "\n")

    def _count_occurrences(self, content: str, search: str) -> int:
        """计算出现次数"""
        if search == "":
            return content.count(search) + 1
        
        count = 0
        offset = 0
        while True:
            index = content.find(search, offset)
            if index == -1:
                break
            count += 1
            offset = index + len(search)
        return count


# 注册工具
edit_tool = EditTool()
