"""
技能发布器 - Skill Publisher

管理技能的打包、发布和版本更新流程。
"""

import json
import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .registry import SkillRegistry, SkillMetadata
from .version_manager import VersionManager
from .validator import SkillValidator, ValidationResult

logger = logging.getLogger(__name__)


class SkillPublisher:
    """
    技能发布器
    
    负责技能的打包、验证、发布到技能市场。
    """
    
    def __init__(self, 
                 registry: SkillRegistry,
                 version_manager: VersionManager,
                 validator: SkillValidator,
                 publish_dir: Optional[Path] = None):
        """
        初始化发布器
        
        Args:
            registry: 技能注册表
            version_manager: 版本管理器
            validator: 技能验证器
            publish_dir: 发布目录
        """
        self._registry = registry
        self._version_manager = version_manager
        self._validator = validator
        self._publish_dir = publish_dir or Path(__file__).parent / "published"
        self._publish_dir.mkdir(parents=True, exist_ok=True)
    
    def publish_skill(self, skill_path: Path, 
                     author_id: str,
                     force: bool = False) -> Dict:
        """
        发布技能
        
        Args:
            skill_path: 技能目录路径
            author_id: 作者ID
            force: 是否强制发布（跳过某些检查）
            
        Returns:
            Dict: 发布结果
        """
        result = {
            'success': False,
            'skill_name': '',
            'version': '',
            'message': '',
            'errors': [],
            'warnings': []
        }
        
        try:
            # 1. 验证技能
            validation_result = self._validator.validate_skill(skill_path)
            
            if not validation_result.is_valid and not force:
                result['errors'] = validation_result.errors
                result['message'] = f"Validation failed with {len(validation_result.errors)} errors"
                return result
            
            result['warnings'] = validation_result.warnings
            
            # 2. 解析元数据
            metadata = SkillMetadata.from_skill_md(skill_path)
            metadata.author = author_id
            
            result['skill_name'] = metadata.name
            result['version'] = metadata.version
            
            # 3. 检查版本冲突
            existing = self._registry.get_skill(metadata.name, metadata.version)
            if existing and not force:
                result['message'] = f"Version {metadata.version} already exists. Use force=True to overwrite."
                return result
            
            # 4. 打包技能
            package_path = self._package_skill(skill_path, metadata)
            
            # 5. 注册技能
            success = self._registry.register_skill(metadata)
            
            if not success:
                result['message'] = "Failed to register skill in registry"
                return result
            
            # 6. 添加版本记录
            self._version_manager.add_version(metadata.name, metadata.version)
            
            # 7. 保存包文件
            published_path = self._publish_dir / f"{metadata.name}-{metadata.version}.zip"
            
            # 避免复制到自己
            if package_path.resolve() != published_path.resolve():
                shutil.copy2(package_path, published_path)
            
            result['success'] = True
            result['message'] = f"Successfully published {metadata.name}@{metadata.version}"
            result['package_path'] = str(published_path)
            
            logger.info(f"Published skill: {metadata.name}@{metadata.version}")
            
        except Exception as e:
            result['message'] = f"Publish failed: {str(e)}"
            logger.error(f"Failed to publish skill: {e}", exc_info=True)
        
        return result
    
    def update_skill(self, skill_path: Path, 
                    author_id: str,
                    change_type: str = 'patch') -> Dict:
        """
        更新技能（自动递增版本号）
        
        Args:
            skill_path: 技能目录路径
            author_id: 作者ID
            change_type: 变更类型 ('major', 'minor', 'patch')
            
        Returns:
            Dict: 更新结果
        """
        result = {
            'success': False,
            'old_version': '',
            'new_version': '',
            'message': ''
        }
        
        try:
            # 获取当前最新版本
            metadata = SkillMetadata.from_skill_md(skill_path)
            latest_version = self._version_manager.get_latest_version(metadata.name)
            
            if not latest_version:
                result['message'] = f"Skill '{metadata.name}' not found. Use publish instead."
                return result
            
            result['old_version'] = latest_version
            
            # 计算新版本号
            new_version = self._version_manager.suggest_next_version(
                metadata.name, change_type
            )
            
            if not new_version:
                result['message'] = "Failed to generate new version number"
                return result
            
            result['new_version'] = new_version
            
            # 更新SKILL.md中的版本号
            self._update_version_in_md(skill_path, new_version)
            
            # 发布新版本
            publish_result = self.publish_skill(skill_path, author_id, force=False)
            
            if publish_result['success']:
                result['success'] = True
                result['message'] = f"Updated from {latest_version} to {new_version}"
            else:
                result['message'] = publish_result['message']
            
        except Exception as e:
            result['message'] = f"Update failed: {str(e)}"
            logger.error(f"Failed to update skill: {e}", exc_info=True)
        
        return result
    
    def _package_skill(self, skill_path: Path, metadata: SkillMetadata) -> Path:
        """
        打包技能
        
        Args:
            skill_path: 技能目录
            metadata: 技能元数据
            
        Returns:
            Path: 压缩包路径
        """
        package_name = f"{metadata.name}-{metadata.version}"
        package_path = self._publish_dir / f"{package_name}.zip"
        
        with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in skill_path.rglob('*'):
                if file_path.is_file():
                    # 计算相对路径
                    arcname = file_path.relative_to(skill_path.parent)
                    zipf.write(file_path, arcname)
        
        logger.debug(f"Packaged skill to {package_path}")
        return package_path
    
    def _update_version_in_md(self, skill_path: Path, new_version: str):
        """更新SKILL.md中的版本号"""
        md_file = skill_path / 'SKILL.md'
        
        if not md_file.exists():
            return
        
        content = md_file.read_text(encoding='utf-8')
        
        # 替换版本号
        import re
        updated_content = re.sub(
            r'(## Version\s*\n\s*)(\d+\.\d+\.\d+)',
            f'\\g<1>{new_version}',
            content
        )
        
        md_file.write_text(updated_content, encoding='utf-8')
        logger.info(f"Updated version in SKILL.md to {new_version}")
    
    def export_registry(self, output_path: Optional[Path] = None) -> Path:
        """
        导出注册表
        
        Args:
            output_path: 输出路径
            
        Returns:
            Path: 导出文件路径
        """
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = self._publish_dir / f"registry_export_{timestamp}.json"
        
        stats = self._registry.get_statistics()
        
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'statistics': stats,
            'skills': [
                skill.to_dict() 
                for skill in self._registry.list_skills()
            ]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Exported registry to {output_path}")
        return output_path
    
    def get_publish_statistics(self) -> Dict:
        """获取发布统计信息"""
        published_files = list(self._publish_dir.glob('*.zip'))
        
        return {
            'total_published_packages': len(published_files),
            'publish_directory': str(self._publish_dir),
            'registry_stats': self._registry.get_statistics(),
            'version_stats': {
                'total_skills_with_versions': len(self._version_manager._versions),
            }
        }
