"""
技能注册表 - Skill Registry

管理所有技能的元数据，提供技能的注册、查询和管理功能。
支持中心化数据库存储和缓存机制。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """技能元数据"""
    
    # 基本信息
    name: str
    version: str
    description: str
    author: str
    email: str
    
    # 分类与标签
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    # 依赖关系
    dependencies: Dict[str, str] = field(default_factory=dict)
    
    # 统计信息
    downloads: int = 0
    rating: float = 0.0
    rating_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    
    # 状态
    status: str = "active"  # active, deprecated, under_review
    verified: bool = False
    
    # 文件路径
    path: str = ""
    handler_module: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SkillMetadata':
        """从字典创建"""
        return cls(**data)
    
    @classmethod
    def from_skill_md(cls, skill_path: Path) -> 'SkillMetadata':
        """从SKILL.md文件解析元数据"""
        md_file = skill_path / "SKILL.md"
        if not md_file.exists():
            raise FileNotFoundError(f"SKILL.md not found in {skill_path}")
        
        content = md_file.read_text(encoding='utf-8')
        metadata = {}
        
        # 简单的Markdown解析
        lines = content.split('\n')
        current_key = None
        current_value = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('## '):
                # 保存之前的键值对
                if current_key:
                    metadata[current_key] = '\n'.join(current_value).strip()
                
                current_key = line[3:].lower().replace(' ', '_')
                current_value = []
            elif current_key and line:
                current_value.append(line)
        
        # 保存最后一个键值对
        if current_key:
            metadata[current_key] = '\n'.join(current_value).strip()
        
        # 解析关键字段
        return cls(
            name=metadata.get('skill_name', skill_path.name),
            version=metadata.get('version', '1.0.0'),
            description=metadata.get('description', ''),
            author=metadata.get('author', 'Unknown'),
            email=metadata.get('email', ''),
            category=metadata.get('category', 'general'),
            tags=[t.strip() for t in metadata.get('tags', '').split(',') if t.strip()],
            keywords=[k.strip() for k in metadata.get('keywords', '').split(',') if k.strip()],
            path=str(skill_path),
            handler_module=f"skills.{skill_path.name}.handler"
        )


class SkillRegistry:
    """
    技能注册表
    
    负责管理所有技能的元数据，提供注册、查询、更新等功能。
    支持内存缓存和持久化存储。
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        """
        初始化技能注册表
        
        Args:
            storage_path: 持久化存储路径，默认为 skills/marketplace/data
        """
        self._skills: Dict[str, SkillMetadata] = {}
        self._storage_path = storage_path or Path(__file__).parent / "data"
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._registry_file = self._storage_path / "registry.json"
        
        # 加载已注册的技能
        self._load_registry()
    
    def register_skill(self, metadata: SkillMetadata) -> bool:
        """
        注册技能
        
        Args:
            metadata: 技能元数据
            
        Returns:
            bool: 注册是否成功
        """
        try:
            skill_key = f"{metadata.name}@{metadata.version}"
            
            # 检查是否已存在
            if skill_key in self._skills:
                logger.warning(f"Skill {skill_key} already registered")
                return False
            
            # 验证元数据
            if not self._validate_metadata(metadata):
                logger.error(f"Invalid metadata for skill {metadata.name}")
                return False
            
            # 注册技能
            self._skills[skill_key] = metadata
            self._save_registry()
            
            logger.info(f"Successfully registered skill: {skill_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register skill: {e}")
            return False
    
    def unregister_skill(self, name: str, version: str) -> bool:
        """
        注销技能
        
        Args:
            name: 技能名称
            version: 技能版本
            
        Returns:
            bool: 注销是否成功
        """
        skill_key = f"{name}@{version}"
        
        if skill_key in self._skills:
            del self._skills[skill_key]
            self._save_registry()
            logger.info(f"Unregistered skill: {skill_key}")
            return True
        
        return False
    
    def get_skill(self, name: str, version: Optional[str] = None) -> Optional[SkillMetadata]:
        """
        获取技能元数据
        
        Args:
            name: 技能名称
            version: 技能版本（可选，不指定则返回最新版本）
            
        Returns:
            SkillMetadata or None: 技能元数据
        """
        if version:
            skill_key = f"{name}@{version}"
            return self._skills.get(skill_key)
        else:
            # 返回最新版本
            versions = [
                (k, v) for k, v in self._skills.items()
                if k.startswith(f"{name}@")
            ]
            if not versions:
                return None
            
            # 按版本号排序，返回最新的
            versions.sort(key=lambda x: x[1].version, reverse=True)
            return versions[0][1]
    
    def list_skills(self, 
                   category: Optional[str] = None,
                   tags: Optional[List[str]] = None,
                   status: Optional[str] = None,
                   verified_only: bool = False) -> List[SkillMetadata]:
        """
        列出技能
        
        Args:
            category: 分类过滤
            tags: 标签过滤
            status: 状态过滤
            verified_only: 只返回已验证的技能
            
        Returns:
            List[SkillMetadata]: 技能列表
        """
        skills = list(self._skills.values())
        
        # 应用过滤器
        if category:
            skills = [s for s in skills if s.category == category]
        
        if tags:
            skills = [s for s in skills if any(tag in s.tags for tag in tags)]
        
        if status:
            skills = [s for s in skills if s.status == status]
        
        if verified_only:
            skills = [s for s in skills if s.verified]
        
        return skills
    
    def search_skills(self, query: str) -> List[SkillMetadata]:
        """
        搜索技能
        
        Args:
            query: 搜索关键词
            
        Returns:
            List[SkillMetadata]: 匹配的技能列表
        """
        query_lower = query.lower()
        results = []
        
        for skill in self._skills.values():
            # 在名称、描述、标签、关键字中搜索
            if (query_lower in skill.name.lower() or
                query_lower in skill.description.lower() or
                any(query_lower in tag.lower() for tag in skill.tags) or
                any(query_lower in kw.lower() for kw in skill.keywords)):
                results.append(skill)
        
        return results
    
    def update_skill_stats(self, name: str, version: str, 
                          downloads: Optional[int] = None,
                          rating: Optional[float] = None) -> bool:
        """
        更新技能统计信息
        
        Args:
            name: 技能名称
            version: 技能版本
            downloads: 下载量增量
            rating: 新评分
            
        Returns:
            bool: 更新是否成功
        """
        skill_key = f"{name}@{version}"
        skill = self._skills.get(skill_key)
        
        if not skill:
            return False
        
        if downloads is not None:
            skill.downloads += downloads
        
        if rating is not None:
            # 更新平均评分
            total_rating = skill.rating * skill.rating_count + rating
            skill.rating_count += 1
            skill.rating = total_rating / skill.rating_count
        
        skill.updated_at = datetime.now().isoformat()
        self._save_registry()
        
        return True
    
    def _validate_metadata(self, metadata: SkillMetadata) -> bool:
        """验证技能元数据"""
        if not metadata.name or not metadata.version:
            return False
        
        if not metadata.description:
            return False
        
        if not metadata.author:
            return False
        
        return True
    
    def _load_registry(self):
        """从文件加载注册表"""
        if not self._registry_file.exists():
            logger.info("No existing registry file found")
            return
        
        try:
            with open(self._registry_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for skill_data in data.get('skills', []):
                metadata = SkillMetadata.from_dict(skill_data)
                skill_key = f"{metadata.name}@{metadata.version}"
                self._skills[skill_key] = metadata
            
            logger.info(f"Loaded {len(self._skills)} skills from registry")
            
        except Exception as e:
            logger.error(f"Failed to load registry: {e}")
    
    def _save_registry(self):
        """保存注册表到文件"""
        try:
            data = {
                'version': '1.0',
                'updated_at': datetime.now().isoformat(),
                'skills': [skill.to_dict() for skill in self._skills.values()]
            }
            
            with open(self._registry_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Saved registry with {len(self._skills)} skills")
            
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取注册表统计信息"""
        total_skills = len(self._skills)
        categories = {}
        verified_count = 0
        
        for skill in self._skills.values():
            categories[skill.category] = categories.get(skill.category, 0) + 1
            if skill.verified:
                verified_count += 1
        
        return {
            'total_skills': total_skills,
            'verified_skills': verified_count,
            'categories': categories,
            'total_downloads': sum(s.downloads for s in self._skills.values()),
            'average_rating': (
                sum(s.rating for s in self._skills.values()) / total_skills
                if total_skills > 0 else 0
            )
        }
