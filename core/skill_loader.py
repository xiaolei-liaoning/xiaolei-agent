"""技能加载器 - 支持多目录加载和热加载

功能：
- 从多个目录加载技能（项目目录、用户目录、全局目录）
- 支持技能热加载（文件监听）
- 技能优先级管理
- 配置文件加载

搜索路径优先级（从高到低）：
1. ./skills/（项目目录）
2. ~/.xiaolongxia/skills/（用户目录）
3. ~/.trae/skills/（全局目录）
"""

import os
import re
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillInfo:
    """技能信息类"""
    
    def __init__(self, name: str, path: str, keywords: List[str] = None, 
                 priority: int = 5, version: str = "1.0", description: str = ""):
        self.name = name
        self.path = path
        self.keywords = keywords or []
        self.priority = priority
        self.version = version
        self.description = description
        self.source = self._detect_source(path)
    
    def _detect_source(self, path: str) -> str:
        """检测技能来源"""
        path_lower = path.lower()
        if "/.trae/" in path_lower:
            return "global"
        elif "/.xiaolongxia/" in path_lower:
            return "user"
        else:
            return "project"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "keywords": self.keywords,
            "priority": self.priority,
            "version": self.version,
            "description": self.description,
            "source": self.source,
        }


class SkillLoader:
    """技能加载器"""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self._skills: Dict[str, SkillInfo] = {}
        self._config_paths = []
        self._watch_tasks = []
        self._init_config_paths()
    
    @classmethod
    async def get_instance(cls):
        """获取单例实例"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = SkillLoader()
                await cls._instance.load_all_skills()
            return cls._instance
    
    def _init_config_paths(self):
        """初始化配置路径"""
        project_path = Path("./skills").resolve()
        user_path = Path.home() / ".xiaolongxia" / "skills"
        global_path = Path.home() / ".trae" / "skills"
        
        self._config_paths = [
            (project_path, "project"),
            (user_path, "user"),
            (global_path, "global"),
        ]
        
        logger.info("技能搜索路径:")
        for path, source in self._config_paths:
            logger.info(f"  {source}: {path}")
    
    async def load_all_skills(self):
        """加载所有技能"""
        self._skills = {}
        
        for path, source in self._config_paths:
            if path.exists() and path.is_dir():
                await self._load_skills_from_dir(path, source)
        
        logger.info(f"共加载 {len(self._skills)} 个技能")
    
    async def _load_skills_from_dir(self, dir_path: Path, source: str):
        """从目录加载技能"""
        try:
            for item in dir_path.iterdir():
                if item.is_dir():
                    await self._load_skill_from_dir(item, source)
                elif item.suffix == ".json":
                    await self._load_skill_from_json(item, source)
        except Exception as e:
            logger.warning(f"加载目录 {dir_path} 失败: {e}")
    
    async def _load_skill_from_dir(self, skill_dir: Path, source: str):
        """从技能目录加载"""
        skill_name = skill_dir.name
        config_file = skill_dir / "skill.json"
        
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                
                skill_info = SkillInfo(
                    name=skill_name,
                    path=str(skill_dir),
                    keywords=config.get("keywords", []),
                    priority=config.get("priority", 5),
                    version=config.get("version", "1.0"),
                    description=config.get("description", ""),
                )
                
                self._add_skill(skill_info, source)
            except Exception as e:
                logger.warning(f"加载技能 {skill_name} 配置失败: {e}")
    
    async def _load_skill_from_json(self, json_file: Path, source: str):
        """从JSON文件加载技能配置"""
        skill_name = json_file.stem
        
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            skill_info = SkillInfo(
                name=skill_name,
                path=str(json_file),
                keywords=config.get("keywords", []),
                priority=config.get("priority", 5),
                version=config.get("version", "1.0"),
                description=config.get("description", ""),
            )
            
            self._add_skill(skill_info, source)
        except Exception as e:
            logger.warning(f"加载技能配置 {json_file} 失败: {e}")
    
    def _add_skill(self, skill_info: SkillInfo, source: str):
        """添加技能（处理冲突）"""
        name = skill_info.name
        
        if name in self._skills:
            existing = self._skills[name]
            
            # 优先级判断：project > user > global
            source_priority = {"project": 3, "user": 2, "global": 1}
            if source_priority[source] > source_priority[existing.source]:
                logger.info(f"覆盖技能 {name}: {existing.source} -> {source}")
                self._skills[name] = skill_info
            elif source_priority[source] == source_priority[existing.source]:
                # 相同来源，版本高的优先
                if self._compare_version(skill_info.version, existing.version) > 0:
                    logger.info(f"升级技能 {name}: {existing.version} -> {skill_info.version}")
                    self._skills[name] = skill_info
            else:
                logger.debug(f"跳过技能 {name} ({source})，已有更高优先级")
        else:
            self._skills[name] = skill_info
    
    def _compare_version(self, v1: str, v2: str) -> int:
        """比较版本号"""
        parts1 = [int(p) for p in v1.split(".")]
        parts2 = [int(p) for p in v2.split(".")]
        
        for p1, p2 in zip(parts1, parts2):
            if p1 > p2:
                return 1
            elif p1 < p2:
                return -1
        
        return len(parts1) - len(parts2)
    
    def get_skill(self, name: str) -> Optional[SkillInfo]:
        """获取技能信息"""
        return self._skills.get(name)
    
    def get_all_skills(self) -> List[SkillInfo]:
        """获取所有技能"""
        return list(self._skills.values())
    
    def get_skills_by_source(self, source: str) -> List[SkillInfo]:
        """按来源获取技能"""
        return [s for s in self._skills.values() if s.source == source]
    
    def search_skills(self, query: str) -> List[SkillInfo]:
        """搜索技能（按关键词）"""
        query_lower = query.lower()
        results = []
        
        for skill in self._skills.values():
            if query_lower in skill.name.lower():
                results.append(skill)
            else:
                for keyword in skill.keywords:
                    if query_lower in keyword.lower():
                        results.append(skill)
                        break
        
        # 按优先级排序
        results.sort(key=lambda s: s.priority, reverse=True)
        return results
    
    async def reload_skills(self):
        """重新加载所有技能"""
        logger.info("重新加载技能...")
        await self.load_all_skills()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        by_source = {}
        for skill in self._skills.values():
            by_source[skill.source] = by_source.get(skill.source, 0) + 1
        
        return {
            "total": len(self._skills),
            "by_source": by_source,
        }


# 便捷函数
async def get_skill_loader() -> SkillLoader:
    """获取技能加载器实例"""
    return await SkillLoader.get_instance()


if __name__ == "__main__":
    import asyncio
    
    async def main():
        loader = await get_skill_loader()
        stats = loader.get_stats()
        print(f"技能统计: {stats}")
        
        skills = loader.get_all_skills()
        print(f"\n所有技能:")
        for skill in skills:
            print(f"  - {skill.name} (v{skill.version}, {skill.source}, priority={skill.priority})")
    
    asyncio.run(main())
