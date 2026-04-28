#!/usr/bin/env python3
"""
技能市场命令行工具 - Skill Marketplace CLI

提供技能的创建、验证、打包和发布功能。

Usage:
    python -m skills.marketplace.cli create my_skill
    python -m skills.marketplace.cli validate my_skill
    python -m skills.marketplace.cli package my_skill
    python -m skills.marketplace.cli publish my_skill
"""

import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from skills.marketplace.registry import SkillRegistry
from skills.marketplace.version_manager import VersionManager
from skills.marketplace.dependency_resolver import DependencyResolver
from skills.marketplace.rating_system import RatingSystem
from skills.marketplace.search_engine import SkillSearchEngine
from skills.marketplace.validator import SkillValidator
from skills.marketplace.publisher import SkillPublisher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_skill(args):
    """创建新技能"""
    skill_name = args.name
    skills_dir = Path('skills') / skill_name
    
    if skills_dir.exists():
        print(f"❌ Skill '{skill_name}' already exists")
        return False
    
    # 创建目录结构
    skills_dir.mkdir(parents=True)
    
    # 创建 __init__.py
    (skills_dir / '__init__.py').write_text('')
    
    # 创建 handler.py 模板
    handler_template = '''"""
{skill_name} - 技能处理器

描述: {description}
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class {class_name}:
    """{skill_name} 技能处理器"""
    
    def __init__(self):
        """初始化技能"""
        pass
    
    async def execute(self, **params) -> Dict[str, Any]:
        """
        执行技能
        
        Args:
            **params: 技能参数
            
        Returns:
            dict: 执行结果，包含 success, result/error 等字段
        """
        try:
            logger.info(f"Executing {skill_name} with params: {{params}}")
            
            # TODO: 实现技能逻辑
            
            return {{
                "success": True,
                "result": "Skill executed successfully",
                "data": {{}}
            }}
            
        except Exception as e:
            logger.error(f"Skill execution failed: {{e}}")
            return {{
                "success": False,
                "error": str(e)
            }}


# 导出技能实例
handler = {class_name}()
'''
    
    class_name = ''.join(word.capitalize() for word in skill_name.split('_')) + 'Handler'
    
    handler_content = handler_template.format(
        skill_name=skill_name,
        description=f"{skill_name} skill",
        class_name=class_name
    )
    
    (skills_dir / 'handler.py').write_text(handler_content, encoding='utf-8')
    
    # 创建 SKILL.md 模板
    skill_md_template = '''# {skill_name}

## Description
{description}

## Version
1.0.0

## Author
Your Name

## Email
your.email@example.com

## Category
general

## Tags
tag1, tag2, tag3

## Keywords
keyword1, keyword2, keyword3

## Dependencies
{{}}

## Usage

```python
from skills.{skill_name}.handler import handler

result = await handler.execute(param1="value1", param2="value2")
print(result)
```

## Examples

### Example 1: Basic Usage
```python
result = await handler.execute()
```

## Changelog

### 1.0.0
- Initial release
'''
    
    skill_md_content = skill_md_template.format(
        skill_name=skill_name,
        description=f"A skill for {skill_name}"
    )
    
    (skills_dir / 'SKILL.md').write_text(skill_md_content, encoding='utf-8')
    
    # 创建 requirements.txt
    (skills_dir / 'requirements.txt').write_text('# Add your dependencies here\n')
    
    # 创建 tests 目录
    tests_dir = skills_dir / 'tests'
    tests_dir.mkdir()
    (tests_dir / '__init__.py').write_text('')
    (tests_dir / 'test_handler.py').write_text('''"""Tests for {skill_name}"""

import pytest


@pytest.mark.asyncio
async def test_execute():
    """Test skill execution"""
    from skills.{skill_name}.handler import handler
    
    result = await handler.execute()
    assert result['success'] is True
'''.format(skill_name=skill_name))
    
    print(f"✅ Created skill '{skill_name}' at {skills_dir}")
    print(f"📝 Next steps:")
    print(f"   1. Edit {skills_dir}/handler.py to implement your skill logic")
    print(f"   2. Update {skills_dir}/SKILL.md with proper metadata")
    print(f"   3. Run: python -m skills.marketplace.cli validate {skill_name}")
    
    return True


def validate_skill(args):
    """验证技能"""
    skill_name = args.name
    skill_path = Path('skills') / skill_name
    
    if not skill_path.exists():
        print(f"❌ Skill '{skill_name}' not found")
        return False
    
    validator = SkillValidator()
    result = validator.validate_skill(skill_path)
    
    print(f"\n{'='*60}")
    print(f"Validation Report for '{skill_name}'")
    print(f"{'='*60}\n")
    
    if result.is_valid:
        print("✅ Validation PASSED\n")
    else:
        print("❌ Validation FAILED\n")
    
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  ❌ {error}")
        print()
    
    if result.warnings:
        print(f"Warnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  ⚠️  {warning}")
        print()
    
    if result.suggestions:
        print(f"Suggestions ({len(result.suggestions)}):")
        for suggestion in result.suggestions:
            print(f"  💡 {suggestion}")
        print()
    
    summary = validator.get_validation_summary({skill_name: result})
    print(f"{'='*60}")
    print(f"Summary: {summary['validation_rate']}% validation rate")
    print(f"{'='*60}\n")
    
    return result.is_valid


def package_skill(args):
    """打包技能"""
    skill_name = args.name
    skill_path = Path('skills') / skill_name
    
    if not skill_path.exists():
        print(f"❌ Skill '{skill_name}' not found")
        return False
    
    # 先验证
    validator = SkillValidator()
    validation_result = validator.validate_skill(skill_path)
    
    if not validation_result.is_valid:
        print(f"❌ Cannot package: validation failed with {len(validation_result.errors)} errors")
        return False
    
    # 解析元数据
    from skills.marketplace.registry import SkillMetadata
    metadata = SkillMetadata.from_skill_md(skill_path)
    
    # 打包
    import zipfile
    from datetime import datetime
    
    package_dir = Path('packages')
    package_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    package_name = f"{metadata.name}-{metadata.version}_{timestamp}.zip"
    package_path = package_dir / package_name
    
    with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in skill_path.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(skill_path.parent)
                zipf.write(file_path, arcname)
    
    print(f"✅ Packaged skill to: {package_path}")
    print(f"📦 Package size: {package_path.stat().st_size / 1024:.2f} KB")
    
    return True


def publish_skill(args):
    """发布技能"""
    skill_name = args.name
    skill_path = Path('skills') / skill_name
    
    if not skill_path.exists():
        print(f"❌ Skill '{skill_name}' not found")
        return False
    
    author_id = args.author or "anonymous"
    
    # 初始化组件
    registry = SkillRegistry()
    version_manager = VersionManager()
    validator = SkillValidator()
    publisher = SkillPublisher(registry, version_manager, validator)
    
    # 发布
    result = publisher.publish_skill(skill_path, author_id, force=args.force)
    
    print(f"\n{'='*60}")
    print(f"Publish Result")
    print(f"{'='*60}\n")
    
    if result['success']:
        print(f"✅ Successfully published: {result['skill_name']}@{result['version']}")
        print(f"📦 Package: {result.get('package_path', 'N/A')}")
    else:
        print(f"❌ Publish failed: {result['message']}")
        
        if result.get('errors'):
            print(f"\nErrors:")
            for error in result['errors']:
                print(f"  ❌ {error}")
    
    if result.get('warnings'):
        print(f"\nWarnings:")
        for warning in result['warnings']:
            print(f"  ⚠️  {warning}")
    
    print(f"\n{'='*60}\n")
    
    return result['success']


def list_skills(args):
    """列出所有技能"""
    registry = SkillRegistry()
    
    skills = registry.list_skills(
        category=args.category,
        verified_only=args.verified
    )
    
    if not skills:
        print("No skills found")
        return
    
    print(f"\n{'='*80}")
    print(f"Skills Marketplace ({len(skills)} skills)")
    print(f"{'='*80}\n")
    
    for skill in skills:
        verified_badge = "✓" if skill.verified else " "
        print(f"[{verified_badge}] {skill.name}@{skill.version}")
        print(f"    Author: {skill.author}")
        print(f"    Category: {skill.category}")
        print(f"    Rating: {'⭐' * int(skill.rating)} ({skill.rating:.1f}/5.0)")
        print(f"    Downloads: {skill.downloads}")
        print(f"    Tags: {', '.join(skill.tags[:5])}")
        print(f"    Description: {skill.description[:100]}...")
        print()
    
    stats = registry.get_statistics()
    print(f"{'='*80}")
    print(f"Statistics:")
    print(f"  Total Skills: {stats['total_skills']}")
    print(f"  Verified: {stats['verified_skills']}")
    print(f"  Average Rating: {stats['average_rating']:.2f}")
    print(f"{'='*80}\n")


def search_skills(args):
    """搜索技能"""
    registry = SkillRegistry()
    search_engine = SkillSearchEngine(registry)
    
    results = search_engine.search(
        query=args.query,
        category=args.category,
        min_rating=args.min_rating,
        limit=args.limit
    )
    
    if not results:
        print(f"No skills found for query: '{args.query}'")
        return
    
    print(f"\n{'='*80}")
    print(f"Search Results for '{args.query}' ({len(results)} found)")
    print(f"{'='*80}\n")
    
    for i, result in enumerate(results, 1):
        skill = result['skill']
        score = result['relevance_score']
        
        print(f"{i}. {skill['name']}@{skill['version']} (Score: {score:.2f})")
        print(f"   Author: {skill['author']}")
        print(f"   Rating: {'⭐' * int(skill['rating'])} ({skill['rating']:.1f}/5.0)")
        print(f"   Downloads: {skill['downloads']}")
        print(f"   Description: {skill['description'][:150]}...")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Skill Marketplace CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # create command
    create_parser = subparsers.add_parser('create', help='Create a new skill')
    create_parser.add_argument('name', help='Skill name')
    create_parser.set_defaults(func=create_skill)
    
    # validate command
    validate_parser = subparsers.add_parser('validate', help='Validate a skill')
    validate_parser.add_argument('name', help='Skill name')
    validate_parser.set_defaults(func=validate_skill)
    
    # package command
    package_parser = subparsers.add_parser('package', help='Package a skill')
    package_parser.add_argument('name', help='Skill name')
    package_parser.set_defaults(func=package_skill)
    
    # publish command
    publish_parser = subparsers.add_parser('publish', help='Publish a skill')
    publish_parser.add_argument('name', help='Skill name')
    publish_parser.add_argument('--author', default='anonymous', help='Author ID')
    publish_parser.add_argument('--force', action='store_true', help='Force publish')
    publish_parser.set_defaults(func=publish_skill)
    
    # list command
    list_parser = subparsers.add_parser('list', help='List all skills')
    list_parser.add_argument('--category', help='Filter by category')
    list_parser.add_argument('--verified', action='store_true', help='Show only verified skills')
    list_parser.set_defaults(func=list_skills)
    
    # search command
    search_parser = subparsers.add_parser('search', help='Search skills')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--category', help='Filter by category')
    search_parser.add_argument('--min-rating', type=float, default=0, help='Minimum rating')
    search_parser.add_argument('--limit', type=int, default=20, help='Result limit')
    search_parser.set_defaults(func=search_skills)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    success = args.func(args)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
