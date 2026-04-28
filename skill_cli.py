#!/usr/bin/env python3
"""技能开发命令行工具

支持：
- 创建新技能模板
- 验证技能结构
- 打包技能
- 发布技能到市场
"""

import argparse
import sys
from pathlib import Path
import shutil
import json
from datetime import datetime


# ============================================================================
# 技能模板
# ============================================================================

SKILL_TEMPLATE = """#!/usr/bin/env python3
\"\"\"{skill_name} - {skill_description}

## 功能描述
{skill_description}

## 使用示例
```python
from skills.{skill_name}.handler import handler

result = await handler.execute(param1="value1")
print(result)
```
\"\"\"

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class {class_name}:
    \"\"\"{skill_name} 技能处理器\"\"\"
    
    def __init__(self):
        \"\"\"初始化技能\"\"\"
        logger.info("{skill_name} 技能初始化")
    
    async def execute(self, **params) -> Dict[str, Any]:
        \"\"\"执行技能
        
        Args:
            **params: 技能参数
            
        Returns:
            dict: 执行结果，包含 success, result/error 等字段
        \"\"\"
        try:
            logger.info(f"执行 {skill_name} 技能，参数: {params}")
            
            # TODO: 实现技能逻辑
            result = self._process(params)
            
            return {
                "success": True,
                "result": result,
                "message": "执行成功"
            }
            
        except Exception as e:
            logger.error(f"{skill_name} 技能执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": f"执行失败: {str(e)}"
            }
    
    def _process(self, params: Dict[str, Any]) -> Any:
        \"\"\"处理技能逻辑
        
        Args:
            params: 参数字典
            
        Returns:
            处理结果
        \"\"\"
        # TODO: 实现具体逻辑
        return "处理结果"


# 导出技能实例
handler = {class_name}()
"""

SKILL_MD_TEMPLATE = """# {skill_name} - {skill_description}

## 📋 功能描述
{skill_description}

## 🔑 触发关键词
- **中文**：关键词1, 关键词2
- **英文**：keyword1, keyword2

## ⚙️ 参数说明
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| param1 | str | 否 | default | 参数说明 |

## 💡 使用示例
```python
# 基础使用
用户: "示例命令"
→ {skill_name}.execute(param1='value1')

# 高级使用
用户: "复杂示例"
→ {skill_name}.execute(param1='value1', param2='value2')
```

## 📦 依赖
- 依赖包1 (版本要求)
- 依赖包2 (版本要求)

## 🎯 性能指标
- 响应时间: <500ms
- 准确率: 99%
- 限流: 无限制

## 📝 版本历史
### v1.0.0 ({date})
- 初始版本
"""

CONFIG_TEMPLATE = """\"\"\"{skill_name} 配置文件\"\"\"

# 技能配置
SKILL_CONFIG = {{
    "name": "{skill_name}",
    "version": "1.0.0",
    "description": "{skill_description}",
    "category": "未分类",
    "icon": "🔧",
    "author": "Your Name",
    "email": "your@email.com",
    "keywords": ["关键词1", "关键词2"],
    "tags": ["标签1", "标签2"],
    "dependencies": {{}},
}}

# 执行配置
EXECUTION_CONFIG = {{
    "timeout": 30,  # 超时时间（秒）
    "max_retries": 3,  # 最大重试次数
    "cache_enabled": True,  # 是否启用缓存
    "cache_ttl": 3600,  # 缓存有效期（秒）
}}
"""

TEST_TEMPLATE = """#!/usr/bin/env python3
\"\"\"{skill_name} 技能测试\"\"\"

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.{skill_name}.handler import handler


async def test_basic():
    \"\"\"测试基本功能\"\"\"
    print("测试1: 基本功能")
    result = await handler.execute()
    print(f"结果: {result}")
    assert result["success"] == True
    print("✅ 通过\\n")


async def test_with_params():
    \"\"\"测试带参数\"\"\"
    print("测试2: 带参数执行")
    result = await handler.execute(param1="test_value")
    print(f"结果: {result}")
    assert result["success"] == True
    print("✅ 通过\\n")


async def main():
    \"\"\"运行所有测试\"\"\"
    print("="*60)
    print(f"开始测试 {skill_name} 技能")
    print("="*60 + "\\n")
    
    tests = [
        ("基本功能", test_basic),
        ("带参数", test_with_params),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {name} 测试失败: {e}\\n")
            failed += 1
    
    print("="*60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
"""

REQUIREMENTS_TEMPLATE = """# {skill_name} 依赖
# 在这里列出技能所需的Python包
# 例如:
# httpx>=0.24.0
# beautifulsoup4>=4.12.0
"""


# ============================================================================
# 工具函数
# ============================================================================

def create_skill(skill_name: str, description: str = "", category: str = "未分类"):
    """创建新技能模板"""
    
    # 生成类名（驼峰命名）
    class_name = ''.join(word.capitalize() for word in skill_name.split('_')) + 'Handler'
    
    # 如果没有提供描述，使用默认描述
    if not description:
        description = f"{skill_name} 技能"
    
    # 创建技能目录
    skill_dir = Path("skills") / skill_name
    if skill_dir.exists():
        print(f"❌ 技能目录已存在: {skill_dir}")
        return False
    
    skill_dir.mkdir(parents=True)
    
    # 创建文件
    files = {
        "__init__.py": "",
        "handler.py": SKILL_TEMPLATE.format(
            skill_name=skill_name,
            class_name=class_name,
            skill_description=description
        ),
        "config.py": CONFIG_TEMPLATE.format(
            skill_name=skill_name,
            skill_description=description
        ),
        "SKILL.md": SKILL_MD_TEMPLATE.format(
            skill_name=skill_name,
            skill_description=description,
            date=datetime.now().strftime("%Y-%m-%d")
        ),
        "requirements.txt": REQUIREMENTS_TEMPLATE.format(skill_name=skill_name),
    }
    
    for filename, content in files.items():
        filepath = skill_dir / filename
        filepath.write_text(content, encoding="utf-8")
        print(f"✅ 创建文件: {filepath}")
    
    # 创建测试目录
    test_dir = skill_dir / "tests"
    test_dir.mkdir()
    
    test_file = test_dir / "test_handler.py"
    test_file.write_text(
        TEST_TEMPLATE.format(skill_name=skill_name),
        encoding="utf-8"
    )
    print(f"✅ 创建测试文件: {test_file}")
    
    print(f"\n🎉 技能 '{skill_name}' 创建成功！")
    print(f"📁 目录位置: {skill_dir.absolute()}")
    print(f"\n下一步:")
    print(f"  1. 编辑 {skill_dir}/handler.py 实现技能逻辑")
    print(f"  2. 编辑 {skill_dir}/SKILL.md 完善文档")
    print(f"  3. 运行测试: python -m pytest {skill_dir}/tests/")
    print(f"  4. 验证技能: python -m skill_cli validate {skill_name}")
    
    return True


def validate_skill(skill_name: str) -> bool:
    """验证技能结构和完整性"""
    
    skill_dir = Path("skills") / skill_name
    
    if not skill_dir.exists():
        print(f"❌ 技能目录不存在: {skill_dir}")
        return False
    
    # 必需文件检查
    required_files = [
        "__init__.py",
        "handler.py",
        "SKILL.md",
    ]
    
    missing_files = []
    for filename in required_files:
        if not (skill_dir / filename).exists():
            missing_files.append(filename)
    
    if missing_files:
        print(f"❌ 缺少必需文件: {', '.join(missing_files)}")
        return False
    
    # 检查 handler.py 是否有 execute 方法
    handler_file = skill_dir / "handler.py"
    content = handler_file.read_text(encoding="utf-8")
    
    if "async def execute" not in content:
        print("❌ handler.py 中缺少 execute 方法")
        return False
    
    if "return {" not in content or '"success"' not in content:
        print("⚠️  warning: execute 方法可能没有返回标准格式的结果")
    
    # 检查 SKILL.md 是否有必要信息
    skill_md = skill_dir / "SKILL.md"
    md_content = skill_md.read_text(encoding="utf-8")
    
    required_sections = ["功能描述", "使用示例"]
    missing_sections = [
        section for section in required_sections
        if section not in md_content
    ]
    
    if missing_sections:
        print(f"⚠️  SKILL.md 缺少章节: {', '.join(missing_sections)}")
    
    print(f"✅ 技能 '{skill_name}' 验证通过")
    print(f"📁 目录: {skill_dir.absolute()}")
    
    # 显示技能信息
    print(f"\n技能信息:")
    for line in md_content.split('\n'):
        if line.startswith('# '):
            print(f"  {line}")
            break
    
    return True


def package_skill(skill_name: str, output_dir: str = "packages"):
    """打包技能"""
    
    skill_dir = Path("skills") / skill_name
    
    if not skill_dir.exists():
        print(f"❌ 技能目录不存在: {skill_dir}")
        return False
    
    # 先验证
    if not validate_skill(skill_name):
        print("❌ 验证失败，无法打包")
        return False
    
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # 创建压缩包
    import zipfile
    
    package_file = output_path / f"{skill_name}.zip"
    
    with zipfile.ZipFile(package_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in skill_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(skill_dir.parent)
                zipf.write(file_path, arcname)
    
    print(f"✅ 技能打包成功: {package_file.absolute()}")
    print(f"📦 包大小: {package_file.stat().st_size / 1024:.2f} KB")
    
    return True


def publish_skill(skill_name: str, api_url: str = "http://localhost:8000/api/skills"):
    """发布技能到市场"""
    
    skill_dir = Path("skills") / skill_name
    
    if not skill_dir.exists():
        print(f"❌ 技能目录不存在: {skill_dir}")
        return False
    
    # 先验证和打包
    if not validate_skill(skill_name):
        print("❌ 验证失败，无法发布")
        return False
    
    package_skill(skill_name)
    
    print(f"\n🚀 准备发布技能 '{skill_name}'")
    print(f"📡 API地址: {api_url}")
    print(f"\n注意: 实际发布需要:")
    print(f"  1. 配置API密钥")
    print(f"  2. 提交审核")
    print(f"  3. 等待审核通过")
    print(f"\n💡 提示: 这是一个模拟发布，实际功能需要后端支持")
    
    return True


# ============================================================================
# 命令行接口
# ============================================================================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="技能开发命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 创建新技能
  python -m skill_cli create my_skill --description "我的技能描述"
  
  # 验证技能
  python -m skill_cli validate my_skill
  
  # 打包技能
  python -m skill_cli package my_skill
  
  # 发布技能
  python -m skill_cli publish my_skill
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # create 命令
    create_parser = subparsers.add_parser("create", help="创建新技能")
    create_parser.add_argument("skill_name", help="技能名称（使用下划线分隔）")
    create_parser.add_argument("--description", "-d", default="", help="技能描述")
    create_parser.add_argument("--category", "-c", default="未分类", help="技能分类")
    
    # validate 命令
    validate_parser = subparsers.add_parser("validate", help="验证技能")
    validate_parser.add_argument("skill_name", help="技能名称")
    
    # package 命令
    package_parser = subparsers.add_parser("package", help="打包技能")
    package_parser.add_argument("skill_name", help="技能名称")
    package_parser.add_argument("--output", "-o", default="packages", help="输出目录")
    
    # publish 命令
    publish_parser = subparsers.add_parser("publish", help="发布技能")
    publish_parser.add_argument("skill_name", help="技能名称")
    publish_parser.add_argument("--api-url", default="http://localhost:8000/api/skills", help="API地址")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 执行命令
    if args.command == "create":
        success = create_skill(args.skill_name, args.description, args.category)
    elif args.command == "validate":
        success = validate_skill(args.skill_name)
    elif args.command == "package":
        success = package_skill(args.skill_name, args.output)
    elif args.command == "publish":
        success = publish_skill(args.skill_name, args.api_url)
    else:
        parser.print_help()
        return
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
