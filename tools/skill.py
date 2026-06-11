"""
Skill工具 - 参考Open Code的SkillTool实现

支持：
- 技能加载
- 技能文件读取
- 技能元数据
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import logging
from pathlib import Path

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)

# 技能文件限制
FILE_LIMIT = 10

# 默认技能目录
DEFAULT_SKILLS_DIR = ".opencode/skills"


@dataclass
class SkillInfo:
    """技能信息"""
    name: str
    location: str
    content: str
    files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillInput(ToolInput):
    """Skill工具输入"""
    name: str


@dataclass
class SkillOutput(ToolOutput):
    """Skill工具输出"""
    name: str
    directory: str
    output: str
    success: bool
    error: Optional[str] = None


class SkillTool(Tool[SkillInput, SkillOutput]):
    """Skill工具 - 参考Open Code的SkillTool"""

    def __init__(self):
        super().__init__(
            name="skill",
            description="Load a specialized skill when the task at hand matches one of the available skills in the system context.",
            permission=ToolPermission.READ,
            timeout=30,
            max_retries=1
        )
        self._skills_dir = DEFAULT_SKILLS_DIR
        self._skills: Dict[str, SkillInfo] = {}

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the skill from the available skills list"
                }
            },
            "required": ["name"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "directory": {"type": "string"},
                "output": {"type": "string"},
                "success": {"type": "boolean"},
                "error": {"type": "string"}
            }
        }

    def validate_input(self, input_data: Any) -> SkillInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return SkillInput(name=input_data.get("name", ""))
        elif isinstance(input_data, SkillInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: SkillInput) -> SkillOutput:
        """执行技能加载"""
        skill_name = input_data.name

        # 扫描技能目录
        self._scan_skills()

        # 查找技能
        skill = self._skills.get(skill_name)
        if not skill:
            return SkillOutput(
                name=skill_name,
                directory="",
                output="",
                success=False,
                error=f"Skill not found: {skill_name}"
            )

        # 获取技能目录
        directory = str(Path(skill.location).parent)

        # 生成输出
        output = self._format_skill_output(skill)

        return SkillOutput(
            name=skill.name,
            directory=directory,
            output=output,
            success=True
        )

    def _scan_skills(self):
        """扫描技能目录"""
        self._skills.clear()

        # 检查技能目录是否存在
        if not os.path.exists(self._skills_dir):
            logger.warning(f"技能目录不存在: {self._skills_dir}")
            return

        # 扫描子目录
        for entry in os.listdir(self._skills_dir):
            entry_path = os.path.join(self._skills_dir, entry)
            if not os.path.isdir(entry_path):
                continue

            # 查找SKILL.md文件
            skill_md_path = os.path.join(entry_path, "SKILL.md")
            if os.path.exists(skill_md_path):
                try:
                    with open(skill_md_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # 获取技能文件列表
                    files = self._list_skill_files(entry_path)

                    # 解析技能名称
                    skill_name = self._parse_skill_name(content, entry)

                    self._skills[skill_name] = SkillInfo(
                        name=skill_name,
                        location=skill_md_path,
                        content=content,
                        files=files
                    )

                except Exception as e:
                    logger.error(f"加载技能失败 {entry}: {e}")

    def _list_skill_files(self, directory: str) -> List[str]:
        """列出技能文件"""
        files = []
        try:
            for entry in os.listdir(directory):
                entry_path = os.path.join(directory, entry)
                if os.path.isfile(entry_path) and entry != "SKILL.md":
                    files.append(entry)
                    if len(files) >= FILE_LIMIT:
                        break
        except Exception:
            pass
        return sorted(files)

    def _parse_skill_name(self, content: str, fallback: str) -> str:
        """解析技能名称"""
        # 尝试从内容中解析名称
        for line in content.split('\n'):
            if line.startswith('# Skill:'):
                return line[8:].strip()
            elif line.startswith('## '):
                return line[3:].strip()
        return fallback

    def _format_skill_output(self, skill: SkillInfo) -> str:
        """格式化技能输出"""
        lines = [
            f'<skill_content name="{skill.name}">',
            f"# Skill: {skill.name}",
            "",
            skill.content.strip(),
            "",
            f"Base directory for this skill: {Path(skill.location).parent}",
            "Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.",
            "Note: file list is sampled.",
            "",
            "<skill_files>",
        ]

        for file in skill.files:
            lines.append(f"<file>{file}</file>")

        lines.extend([
            "</skill_files>",
            "</skill_content>"
        ])

        return "\n".join(lines)

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有技能"""
        self._scan_skills()
        return [
            {
                "name": skill.name,
                "location": skill.location,
                "files": skill.files
            }
            for skill in self._skills.values()
        ]


# 注册工具
skill_tool = SkillTool()
