"""
技能版本管理器 - Version Manager

提供技能的语义化版本控制功能，支持版本比较、兼容性检查等。
遵循 SemVer 2.0.0 规范 (https://semver.org/)
"""

import logging
import re
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SemanticVersion:
    """语义化版本"""
    
    major: int  # 主版本号：不兼容的 API 修改
    minor: int  # 次版本号：向下兼容的功能性新增
    patch: int  # 修订号：向下兼容的问题修正
    
    # 预发布版本标识（可选）
    prerelease: Optional[str] = None
    
    # 构建元数据（可选）
    build: Optional[str] = None
    
    def __str__(self) -> str:
        """转换为字符串格式"""
        version = f"{self.major}.{self.minor}.{self.patch}"
        
        if self.prerelease:
            version += f"-{self.prerelease}"
        
        if self.build:
            version += f"+{self.build}"
        
        return version
    
    @classmethod
    def parse(cls, version_str: str) -> 'SemanticVersion':
        """
        从字符串解析版本号
        
        Args:
            version_str: 版本字符串，如 "1.2.3" 或 "1.2.3-beta+build.123"
            
        Returns:
            SemanticVersion: 解析后的版本对象
            
        Raises:
            ValueError: 版本格式无效
        """
        # SemVer 正则表达式
        pattern = r'^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
        
        match = re.match(pattern, version_str)
        if not match:
            raise ValueError(f"Invalid version format: {version_str}")
        
        return cls(
            major=int(match.group('major')),
            minor=int(match.group('minor')),
            patch=int(match.group('patch')),
            prerelease=match.group('prerelease'),
            build=match.group('build')
        )
    
    def __lt__(self, other: 'SemanticVersion') -> bool:
        """小于比较"""
        return self._compare_to(other) < 0
    
    def __le__(self, other: 'SemanticVersion') -> bool:
        """小于等于比较"""
        return self._compare_to(other) <= 0
    
    def __gt__(self, other: 'SemanticVersion') -> bool:
        """大于比较"""
        return self._compare_to(other) > 0
    
    def __ge__(self, other: 'SemanticVersion') -> bool:
        """大于等于比较"""
        return self._compare_to(other) >= 0
    
    def __eq__(self, other: object) -> bool:
        """等于比较"""
        if not isinstance(other, SemanticVersion):
            return False
        return self._compare_to(other) == 0
    
    def _compare_to(self, other: 'SemanticVersion') -> int:
        """
        比较两个版本
        
        Returns:
            -1: self < other
             0: self == other
             1: self > other
        """
        # 比较主版本号
        if self.major != other.major:
            return -1 if self.major < other.major else 1
        
        # 比较次版本号
        if self.minor != other.minor:
            return -1 if self.minor < other.minor else 1
        
        # 比较修订号
        if self.patch != other.patch:
            return -1 if self.patch < other.patch else 1
        
        # 比较预发布版本
        if self.prerelease and not other.prerelease:
            return -1  # 预发布版本优先级较低
        if not self.prerelease and other.prerelease:
            return 1
        
        if self.prerelease and other.prerelease:
            if self.prerelease < other.prerelease:
                return -1
            elif self.prerelease > other.prerelease:
                return 1
        
        return 0
    
    def is_compatible_with(self, constraint: str) -> bool:
        """
        检查版本是否满足约束条件
        
        Args:
            constraint: 版本约束，如 "^1.2.3", "~1.2.3", ">=1.2.3", "1.2.3"
            
        Returns:
            bool: 是否满足约束
        """
        constraint = constraint.strip()
        
        # 精确匹配
        if not any(constraint.startswith(op) for op in ['^', '~', '>=', '<=', '>', '<']):
            return self == SemanticVersion.parse(constraint)
        
        # 插入符 (^) - 允许更新到不改变最左边非零数字的版本
        if constraint.startswith('^'):
            target = SemanticVersion.parse(constraint[1:])
            if self.major == 0:
                # 0.x.y: 只允许 patch 更新
                return (self.major == target.major and 
                        self.minor == target.minor and 
                        self.patch >= target.patch)
            else:
                # x.y.z (x>0): 允许 minor 和 patch 更新
                return (self.major == target.major and 
                        self >= target)
        
        # 波浪号 (~) - 允许 patch 级别更新
        if constraint.startswith('~'):
            target = SemanticVersion.parse(constraint[1:])
            return (self.major == target.major and 
                    self.minor == target.minor and 
                    self.patch >= target.patch)
        
        # 大于等于 (>=)
        if constraint.startswith('>='):
            target = SemanticVersion.parse(constraint[2:])
            return self >= target
        
        # 小于等于 (<=)
        if constraint.startswith('<='):
            target = SemanticVersion.parse(constraint[2:])
            return self <= target
        
        # 大于 (>)
        if constraint.startswith('>'):
            target = SemanticVersion.parse(constraint[1:])
            return self > target
        
        # 小于 (<)
        if constraint.startswith('<'):
            target = SemanticVersion.parse(constraint[1:])
            return self < target
        
        return False


class VersionManager:
    """
    版本管理器
    
    管理技能的版本历史，提供版本比较、兼容性检查等功能。
    """
    
    def __init__(self):
        self._versions: dict = {}  # skill_name -> list of versions
    
    def add_version(self, skill_name: str, version: str) -> bool:
        """
        添加新版本
        
        Args:
            skill_name: 技能名称
            version: 版本号
            
        Returns:
            bool: 添加是否成功
        """
        try:
            semver = SemanticVersion.parse(version)
            
            if skill_name not in self._versions:
                self._versions[skill_name] = []
            
            # 检查是否已存在
            if any(str(v) == version for v in self._versions[skill_name]):
                logger.warning(f"Version {version} already exists for {skill_name}")
                return False
            
            self._versions[skill_name].append(semver)
            # 按版本号排序
            self._versions[skill_name].sort(reverse=True)
            
            logger.info(f"Added version {version} for {skill_name}")
            return True
            
        except ValueError as e:
            logger.error(f"Invalid version format: {e}")
            return False
    
    def get_latest_version(self, skill_name: str) -> Optional[str]:
        """
        获取最新版本号
        
        Args:
            skill_name: 技能名称
            
        Returns:
            str or None: 最新版本号
        """
        if skill_name not in self._versions or not self._versions[skill_name]:
            return None
        
        return str(self._versions[skill_name][0])
    
    def get_all_versions(self, skill_name: str) -> list:
        """
        获取所有版本号
        
        Args:
            skill_name: 技能名称
            
        Returns:
            list: 版本号列表（按降序排列）
        """
        if skill_name not in self._versions:
            return []
        
        return [str(v) for v in self._versions[skill_name]]
    
    def check_compatibility(self, skill_name: str, required_version: str) -> Tuple[bool, str]:
        """
        检查版本兼容性
        
        Args:
            skill_name: 技能名称
            required_version: 所需版本约束
            
        Returns:
            Tuple[bool, str]: (是否兼容, 推荐版本)
        """
        if skill_name not in self._versions:
            return False, f"Skill '{skill_name}' not found"
        
        available_versions = self._versions[skill_name]
        
        # 查找满足约束的最高版本
        compatible_versions = [
            v for v in available_versions
            if v.is_compatible_with(required_version)
        ]
        
        if not compatible_versions:
            latest = str(available_versions[0])
            return False, f"No compatible version found. Latest: {latest}"
        
        recommended = str(compatible_versions[0])
        return True, recommended
    
    def get_version_history(self, skill_name: str) -> list:
        """
        获取版本历史
        
        Args:
            skill_name: 技能名称
            
        Returns:
            list: 版本历史记录
        """
        if skill_name not in self._versions:
            return []
        
        return [
            {
                'version': str(v),
                'major': v.major,
                'minor': v.minor,
                'patch': v.patch,
                'prerelease': v.prerelease,
            }
            for v in self._versions[skill_name]
        ]
    
    def suggest_next_version(self, skill_name: str, change_type: str = 'patch') -> Optional[str]:
        """
        建议下一个版本号
        
        Args:
            skill_name: 技能名称
            change_type: 变更类型 ('major', 'minor', 'patch')
            
        Returns:
            str or None: 建议的下一个版本号
        """
        latest = self.get_latest_version(skill_name)
        if not latest:
            return "1.0.0"
        
        try:
            current = SemanticVersion.parse(latest)
            
            if change_type == 'major':
                return str(SemanticVersion(current.major + 1, 0, 0))
            elif change_type == 'minor':
                return str(SemanticVersion(current.major, current.minor + 1, 0))
            else:  # patch
                return str(SemanticVersion(current.major, current.minor, current.patch + 1))
                
        except ValueError:
            return None
