"""技能沉淀模块 - Hermes自我进化第三步

把复盘结果写成"操作手册"，下次直接照搬。

技能结构：
- 名称、适用场景
- 操作步骤
- 参数说明
- 坑点（避坑指南）
- 依赖工具
- 版本历史（支持Patch增量更新）
"""

import json
import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """技能定义"""
    name: str
    version: str
    applicable_scenarios: List[str]
    steps: List[str]
    params: Dict[str, str]
    pitfalls: List[str]
    dependencies: List[str]
    created_at: str
    updated_at: str
    last_review_id: Optional[str] = None
    usage_count: int = 0
    success_rate: float = 1.0

    def to_markdown(self) -> str:
        """转换为Markdown格式"""
        md = f"""# 技能: {self.name}

## 基本信息
- 版本: {self.version}
- 创建时间: {self.created_at}
- 更新时间: {self.updated_at}
- 使用次数: {self.usage_count}
- 成功率: {self.success_rate:.0%}

## 适用场景
"""
        for scenario in self.applicable_scenarios:
            md += f"- {scenario}\n"

        md += "\n## 操作步骤\n"
        for i, step in enumerate(self.steps, 1):
            md += f"{i}. {step}\n"

        md += "\n## 参数说明\n"
        for param, desc in self.params.items():
            md += f"- `{param}`: {desc}\n"

        md += "\n## 坑点（避坑指南）\n"
        for pitfall in self.pitfalls:
            md += f"- ⚠️ {pitfall}\n"

        md += "\n## 依赖工具\n"
        for dep in self.dependencies:
            md += f"- {dep}\n"

        md += "\n## 版本历史\n"
        md += f"- v{self.version}: 上次更新 ({self.updated_at})\n"

        return md

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Skill":
        return cls(**data)

    @classmethod
    def from_markdown(cls, md_content: str) -> "Skill":
        """从Markdown内容解析技能"""
        name = re.search(r"# 技能: (.+)", md_content)
        name = name.group(1) if name else "未命名技能"

        version = re.search(r"- 版本: (.+)", md_content)
        version = version.group(1) if version else "1.0"

        created = re.search(r"- 创建时间: (.+)", md_content)
        created = created.group(1) if created else datetime.now().isoformat()

        updated = re.search(r"- 更新时间: (.+)", md_content)
        updated = updated.group(1) if updated else datetime.now().isoformat()

        usage = re.search(r"- 使用次数: (\d+)", md_content)
        usage = int(usage.group(1)) if usage else 0

        rate = re.search(r"- 成功率: ([\d.]+)", md_content)
        rate = float(rate.group(1)) if rate else 1.0

        scenarios = re.findall(r"- (.+)", md_content.split("## 适用场景")[1].split("## 操作步骤")[0])
        scenarios = [s.strip() for s in scenarios]

        steps_section = md_content.split("## 操作步骤")[1].split("## 参数说明")[0]
        steps = re.findall(r"\d+\. (.+)", steps_section)

        params = {}
        params_section = md_content.split("## 参数说明")[1].split("## 坑点")[0]
        for match in re.findall(r"- `(.+?)`: (.+)", params_section):
            params[match[0]] = match[1]

        pitfalls = re.findall(r"- ⚠️ (.+)", md_content.split("## 坑点")[1].split("## 依赖工具")[0])

        deps_section = md_content.split("## 依赖工具")[1].split("## 版本历史")[0]
        dependencies = re.findall(r"- (.+)", deps_section)

        return cls(
            name=name,
            version=version,
            applicable_scenarios=scenarios,
            steps=steps,
            params=params,
            pitfalls=pitfalls,
            dependencies=dependencies,
            created_at=created,
            updated_at=updated,
            usage_count=usage,
            success_rate=rate,
        )


class SkillExtractor:
    """技能萃取器

    功能：
    - 从复盘结果提取技能
    - 维护技能库（Markdown文件）
    - 支持Patch增量更新
    - 技能检索（按场景、按名称）
    """

    def __init__(self, skills_dir: Optional[str] = None):
        if skills_dir is None:
            skills_dir = Path.home() / ".小雷版小龙虾" / "skills"

        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        self._skills_cache: Dict[str, Skill] = {}
        self._load_existing_skills()

        logger.info("SkillExtractor 初始化完成，技能库: %s", self.skills_dir)

    def _load_existing_skills(self):
        """加载已有技能"""
        for md_file in self.skills_dir.glob("*.md"):
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    skill = Skill.from_markdown(content)
                    self._skills_cache[skill.name] = skill
            except Exception as e:
                logger.warning("加载技能文件失败: %s, %s", md_file, e)

    def extract_from_review(self, review_result, execution_logs: Optional[str] = None) -> Optional[Skill]:
        """从复盘结果萃取技能

        Args:
            review_result: 复盘结果
            execution_logs: 原始执行日志（可选，用于提取真实步骤）
        """
        if not review_result.is_worth_saving or not review_result.skill_name:
            logger.info("复盘结果不值得沉淀为技能")
            return None

        skill = Skill(
            name=review_result.skill_name,
            version="1.0",
            applicable_scenarios=review_result.applicable_scenarios or [],
            steps=self._extract_steps_from_review(review_result, execution_logs),
            params={},
            pitfalls=self._extract_pitfalls_from_review(review_result),
            dependencies=self._extract_dependencies_from_logs(execution_logs),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            last_review_id=review_result.review_id,
        )

        self.save_skill(skill)
        logger.info("技能萃取成功: %s", skill.name)

        return skill

    def _extract_steps_from_review(self, review_result, execution_logs: Optional[str] = None) -> List[str]:
        """从复盘结果提取步骤（增强实现）

        Args:
            review_result: 复盘结果
            execution_logs: 原始执行日志（可选）
        """
        if execution_logs:
            steps = self._parse_steps_from_logs(execution_logs)
            if steps:
                logger.debug("从执行日志提取到 %d 个步骤", len(steps))
                return steps

        logger.warning("无法从执行日志提取步骤，使用改进建议")
        return [
            "根据任务描述确定目标",
            review_result.improvement,
            "执行并记录日志",
        ]

    def _parse_steps_from_logs(self, execution_logs: str) -> List[str]:
        """从执行日志解析真实步骤

        解析格式如：
        1. ✅ [web_scraper] 参数: {"site": "GitHub"}... 耗时: 1523ms
        2. ❌ [data_analysis] 参数: {...} 错误: xxx
        """
        import re
        steps = []

        lines = execution_logs.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            tool_match = re.search(r'\[([\w_]+)\]', line)
            if tool_match:
                tool_name = tool_match.group(1)

                param_match = re.search(r'参数:\s*(\{[^}]+\})', line)
                params_str = param_match.group(1) if param_match else "{}"

                try:
                    params = json.loads(params_str)
                    param_desc = self._describe_params(tool_name, params)
                    step = f"调用 {tool_name} {param_desc}"
                except json.JSONDecodeError:
                    step = f"调用 {tool_name}"

                if "❌" in line or "失败" in line:
                    step += " (注意：此步骤曾失败)"
                elif "用户纠正" in line:
                    step += " (注意：此步骤被用户纠正)"

                steps.append(step)

        return steps

    def _describe_params(self, tool_name: str, params: Dict[str, Any]) -> str:
        """将参数转换为人类可读的描述"""
        if not params:
            return ""

        descriptions = []
        for key, value in params.items():
            if isinstance(value, str) and len(value) > 50:
                value = value[:50] + "..."
            descriptions.append(f"{key}={value}")

        return f"参数: {', '.join(descriptions)}"

    def _extract_dependencies_from_logs(self, execution_logs: Optional[str]) -> List[str]:
        """从执行日志中提取依赖工具"""
        if not execution_logs:
            return []

        import re
        tools = set()

        lines = execution_logs.strip().split('\n')
        for line in lines:
            tool_match = re.search(r'\[([\w_]+)\]', line)
            if tool_match:
                tools.add(tool_match.group(1))

        return list(tools)

    def _extract_pitfalls_from_review(self, review_result) -> List[str]:
        """从复盘结果提取坑点"""
        pitfalls = []
        if review_result.pitfalls:
            pitfalls.append(review_result.pitfalls)
        return pitfalls

    def save_skill(self, skill: Skill):
        """保存技能到文件"""
        skill.updated_at = datetime.now().isoformat()

        safe_name = re.sub(r'[^\w\s-]', '', skill.name)
        safe_name = re.sub(r'\s+', '_', safe_name)
        md_file = self.skills_dir / f"{safe_name}.md"

        with open(md_file, "w", encoding="utf-8") as f:
            f.write(skill.to_markdown())

        self._skills_cache[skill.name] = skill
        logger.info("技能已保存: %s", md_file)

    def patch_update(self, skill_name: str, new_insight: str, section: str = "pitfalls",
                    version_bump: str = "patch"):
        """增量更新技能（只更新指定部分）- 语义化版本

        Args:
            skill_name: 技能名称
            new_insight: 新增内容
            section: 要更新的部分（pitfalls/steps/scenarios）
            version_bump: 版本递增类型 (major/minor/patch)

        语义化版本规范:
        - patch: Bug修复，向后兼容
        - minor: 新功能添加，向后兼容
        - major: 不兼容的变更
        """
        skill = self._skills_cache.get(skill_name)
        if not skill:
            logger.warning("技能不存在: %s", skill_name)
            return False

        old_version = skill.version
        skill.version = self._bump_version(old_version, version_bump)

        if section == "pitfalls":
            if new_insight not in skill.pitfalls:
                skill.pitfalls.append(new_insight)
        elif section == "steps":
            if new_insight not in skill.steps:
                skill.steps.append(new_insight)
        elif section == "scenarios":
            if new_insight not in skill.applicable_scenarios:
                skill.applicable_scenarios.append(new_insight)

        self.save_skill(skill)
        logger.info("技能补丁更新成功: %s -> v%s (%s)", skill_name, skill.version, version_bump)

        return True

    def _bump_version(self, version: str, bump_type: str = "patch") -> str:
        """语义化版本递增

        Args:
            version: 当前版本 (如 "1.2.3")
            bump_type: major/minor/patch

        Returns:
            新版本号
        """
        try:
            parts = version.split(".")
            while len(parts) < 3:
                parts.append("0")

            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

            if bump_type == "major":
                major += 1
                minor = 0
                patch = 0
            elif bump_type == "minor":
                minor += 1
                patch = 0
            else:
                patch += 1

            return f"{major}.{minor}.{patch}"
        except (ValueError, IndexError):
            logger.warning("无效版本号格式: %s，使用默认版本 1.0.0", version)
            return "1.0.0"

    def major_update(self, skill_name: str, new_insight: str, section: str = "pitfalls"):
        """不兼容变更 - Major版本递增"""
        return self.patch_update(skill_name, new_insight, section, version_bump="major")

    def minor_update(self, skill_name: str, new_insight: str, section: str = "pitfalls"):
        """新增功能 - Minor版本递增"""
        return self.patch_update(skill_name, new_insight, section, version_bump="minor")

    def get_skill(self, name: str) -> Optional[Skill]:
        """获取指定技能"""
        return self._skills_cache.get(name)

    def search_skills(self, query: str) -> List[Skill]:
        """搜索技能（按名称或场景）"""
        query_lower = query.lower()
        results = []

        for skill in self._skills_cache.values():
            if query_lower in skill.name.lower():
                results.append(skill)
                continue

            for scenario in skill.applicable_scenarios:
                if query_lower in scenario.lower():
                    results.append(skill)
                    break

        return results

    def get_all_skills(self) -> List[Skill]:
        """获取全部技能"""
        return list(self._skills_cache.values())

    def increment_usage(self, skill_name: str, success: bool = True):
        """更新技能使用统计"""
        skill = self._skills_cache.get(skill_name)
        if not skill:
            return

        skill.usage_count += 1

        if success:
            total = skill.usage_count
            old_total = total - 1
            skill.success_rate = (skill.success_rate * old_total + 1.0) / total
        else:
            total = skill.usage_count
            old_total = total - 1
            skill.success_rate = (skill.success_rate * old_total) / total

        self.save_skill(skill)

    def format_skill_summary(self, skill: Skill) -> str:
        """格式化技能摘要"""
        return f"""
📝 技能: {skill.name}
   版本: {skill.version}
   使用: {skill.usage_count}次 | 成功率: {skill.success_rate:.0%}
   场景: {', '.join(skill.applicable_scenarios[:2])}{'...' if len(skill.applicable_scenarios) > 2 else ''}
"""


_skill_extractor_instance: Optional[SkillExtractor] = None


def get_skill_extractor() -> SkillExtractor:
    """获取技能萃取器单例"""
    global _skill_extractor_instance
    if _skill_extractor_instance is None:
        _skill_extractor_instance = SkillExtractor()
    return _skill_extractor_instance
