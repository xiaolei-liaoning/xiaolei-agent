# 技能市场生态系统 - 完整使用指南

## 📋 目录

1. [系统概述](#系统概述)
2. [快速开始](#快速开始)
3. [核心组件](#核心组件)
4. [技能开发规范](#技能开发规范)
5. [命令行工具](#命令行工具)
6. [Web API](#web-api)
7. [最佳实践](#最佳实践)
8. [常见问题](#常见问题)

---

## 系统概述

技能市场生态系统是一个完整的技能管理平台，提供：

- ✅ **标准化技能创建**：统一的目录结构和元数据规范
- ✅ **版本控制**：语义化版本管理（SemVer）
- ✅ **依赖管理**：自动解析和处理技能间依赖
- ✅ **评分系统**：用户评分、评论和排行榜
- ✅ **智能搜索**：多维度搜索和个性化推荐
- ✅ **安全验证**：代码质量检查和安全扫描
- ✅ **发布流程**：一键打包和发布到技能市场

### 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                   技能市场平台                           │
├──────────────┬──────────────┬──────────────┬────────────┤
│ 技能注册表   │ 版本管理器   │ 依赖解析器   │ 评分系统   │
├──────────────┼──────────────┼──────────────┼────────────┤
│ 搜索引擎     │ 验证器       │ 发布器       │ CLI工具    │
└──────────────┴──────────────┴──────────────┴────────────┘
```

---

## 快速开始

### 1. 安装依赖

```bash
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent
pip install fastapi uvicorn pydantic
```

### 2. 创建第一个技能

```bash
# 使用CLI工具创建新技能
python -m skills.marketplace.cli create my_first_skill
```

这将创建以下结构：

```
skills/my_first_skill/
├── __init__.py
├── handler.py          # 技能核心逻辑
├── SKILL.md            # 技能元数据
├── requirements.txt    # 依赖声明
└── tests/
    ├── __init__.py
    └── test_handler.py
```

### 3. 实现技能逻辑

编辑 `skills/my_first_skill/handler.py`：

```python
class MyFirstSkillHandler:
    async def execute(self, **params):
        # 你的技能逻辑
        return {
            "success": True,
            "result": "Hello from my first skill!"
        }

handler = MyFirstSkillHandler()
```

### 4. 验证技能

```bash
python -m skills.marketplace.cli validate my_first_skill
```

### 5. 发布技能

```bash
python -m skills.marketplace.cli publish my_first_skill --author your_name
```

---

## 核心组件

### 1. SkillRegistry（技能注册表）

管理所有技能的元数据。

```python
from skills.marketplace import SkillRegistry

registry = SkillRegistry()

# 列出所有技能
skills = registry.list_skills()

# 搜索技能
results = registry.search_skills("weather")

# 获取技能详情
skill = registry.get_skill("weather_query", version="1.0.0")
```

### 2. VersionManager（版本管理器）

语义化版本控制。

```python
from skills.marketplace import VersionManager

vm = VersionManager()

# 添加版本
vm.add_version("my_skill", "1.0.0")

# 获取最新版本
latest = vm.get_latest_version("my_skill")

# 检查兼容性
compatible, recommended = vm.check_compatibility("my_skill", "^1.0.0")

# 建议下一个版本
next_version = vm.suggest_next_version("my_skill", "minor")
```

### 3. DependencyResolver（依赖解析器）

管理技能依赖关系。

```python
from skills.marketplace import DependencyResolver, VersionManager

vm = VersionManager()
resolver = DependencyResolver(vm)

# 注册依赖
resolver.register_dependencies("my_skill", {
    "helper_skill": "^1.0.0",
    "utils": "~2.1.0"
})

# 解析依赖树
success, order, errors = resolver.resolve_dependencies("my_skill")

# 检测冲突
conflicts = resolver.detect_conflicts("my_skill", {"dep": "^2.0.0"})
```

### 4. RatingSystem（评分系统）

用户评分和评论。

```python
from skills.marketplace import RatingSystem

rating_sys = RatingSystem()

# 添加评分
rating_sys.add_rating(
    user_id="user123",
    skill_name="weather_query",
    skill_version="1.0.0",
    rating=5,
    comment="非常好用的技能！"
)

# 获取评分汇总
summary = rating_sys.get_skill_summary("weather_query")
print(f"平均评分: {summary.average_rating}")
print(f"评分人数: {summary.total_ratings}")

# 获取热门技能
top_skills = rating_sys.get_top_rated_skills(min_ratings=5, limit=10)
```

### 5. SkillSearchEngine（搜索引擎）

智能搜索和推荐。

```python
from skills.marketplace import SkillRegistry, SkillSearchEngine

registry = SkillRegistry()
search_engine = SkillSearchEngine(registry)

# 综合搜索
results = search_engine.search(
    query="天气",
    category="utility",
    min_rating=4.0,
    limit=10
)

# 基于标签搜索
results = search_engine.search_by_tags(["weather", "forecast"])

# 获取推荐
recommendations = search_engine.get_recommendations(
    user_history=["weather_query", "temperature_converter"]
)

# 获取相似技能
similar = search_engine.get_similar_skills("weather_query", limit=5)
```

### 6. SkillValidator（验证器）

代码质量和安全检查。

```python
from skills.marketplace import SkillValidator
from pathlib import Path

validator = SkillValidator()

# 验证单个技能
result = validator.validate_skill(Path("skills/my_skill"))

if result.is_valid:
    print("✅ 验证通过")
else:
    print(f"❌ 发现 {len(result.errors)} 个错误")
    for error in result.errors:
        print(f"  - {error}")

# 批量验证
results = validator.validate_multiple_skills(Path("skills"))
summary = validator.get_validation_summary(results)
```

### 7. SkillPublisher（发布器）

技能打包和发布。

```python
from skills.marketplace import (
    SkillRegistry, VersionManager, 
    SkillValidator, SkillPublisher
)
from pathlib import Path

registry = SkillRegistry()
vm = VersionManager()
validator = SkillValidator()
publisher = SkillPublisher(registry, vm, validator)

# 发布技能
result = publisher.publish_skill(
    skill_path=Path("skills/my_skill"),
    author_id="developer123",
    force=False
)

if result['success']:
    print(f"✅ 成功发布: {result['skill_name']}@{result['version']}")

# 更新技能（自动递增版本）
result = publisher.update_skill(
    skill_path=Path("skills/my_skill"),
    author_id="developer123",
    change_type="minor"  # major/minor/patch
)
```

---

## 技能开发规范

### 目录结构

```
skill_name/
├── __init__.py              # 包初始化
├── handler.py               # 技能核心逻辑（必需）
├── SKILL.md                 # 技能元数据（必需）
├── config.py                # 配置文件（可选）
├── requirements.txt         # 依赖声明（推荐）
└── tests/                   # 测试文件（推荐）
    ├── __init__.py
    └── test_handler.py
```

### handler.py 标准模板

```python
"""
技能名称 - 简短描述

详细描述...
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SkillNameHandler:
    """技能处理器"""
    
    def __init__(self):
        """初始化技能"""
        pass
    
    async def execute(self, **params) -> Dict[str, Any]:
        """
        执行技能
        
        Args:
            **params: 技能参数
            
        Returns:
            dict: 执行结果
                - success (bool): 是否成功
                - result (str): 结果描述
                - data (dict): 详细数据
                - error (str): 错误信息（失败时）
        """
        try:
            # 参数验证
            required_param = params.get('required_param')
            if not required_param:
                return {
                    "success": False,
                    "error": "Missing required parameter: required_param"
                }
            
            # 业务逻辑
            result = await self._do_something(required_param)
            
            return {
                "success": True,
                "result": "操作成功",
                "data": result
            }
            
        except Exception as e:
            logger.error(f"Skill execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _do_something(self, param):
        """内部方法示例"""
        # 实现具体逻辑
        return {"value": param}


# 导出技能实例（必需）
handler = SkillNameHandler()
```

### SKILL.md 标准格式

```markdown
# 技能名称

## Description
技能的详细描述，包括功能、用途等。

## Version
1.0.0

## Author
作者名称

## Email
author@example.com

## Category
分类（如：utility, automation, data_analysis等）

## Tags
tag1, tag2, tag3

## Keywords
keyword1, keyword2, keyword3

## Dependencies
{
  "dependency1": "^1.0.0",
  "dependency2": "~2.1.0"
}

## Usage

```python
from skills.skill_name.handler import handler

result = await handler.execute(param1="value1")
print(result)
```

## Examples

### Example 1: 基本用法
```python
result = await handler.execute()
```

### Example 2: 高级用法
```python
result = await handler.execute(param1="value1", param2="value2")
```

## Changelog

### 1.0.0
- Initial release
- 功能列表

### 1.1.0
- 新增功能
- Bug修复
```

---

## 命令行工具

### 创建技能

```bash
python -m skills.marketplace.cli create my_skill
```

### 验证技能

```bash
python -m skills.marketplace.cli validate my_skill
```

输出示例：
```
============================================================
Validation Report for 'my_skill'
============================================================

✅ Validation PASSED

Warnings (1):
  ⚠️  No exception handling found. Consider adding try-except blocks.

Suggestions (2):
  💡 Add docstrings to improve code documentation
  💡 Consider adding requirements.txt for dependency management

============================================================
Summary: 100.0% validation rate
============================================================
```

### 打包技能

```bash
python -m skills.marketplace.cli package my_skill
```

### 发布技能

```bash
python -m skills.marketplace.cli publish my_skill --author your_name
```

强制发布（覆盖已有版本）：
```bash
python -m skills.marketplace.cli publish my_skill --author your_name --force
```

### 列出技能

```bash
# 列出所有技能
python -m skills.marketplace.cli list

# 按分类过滤
python -m skills.marketplace.cli list --category utility

# 只显示已验证技能
python -m skills.marketplace.cli list --verified
```

### 搜索技能

```bash
# 关键词搜索
python -m skills.marketplace.cli search "天气"

# 带过滤的搜索
python -m skills.marketplace.cli search "weather" --category utility --min-rating 4.0 --limit 10
```

---

## Web API

### 启动API服务

```bash
python -m skills.marketplace.api
```

访问 http://localhost:8004/docs 查看交互式API文档。

### API端点

#### 技能查询

```bash
# 列出所有技能
GET /api/skills?category=utility&verified_only=true&limit=50

# 获取技能详情
GET /api/skills/weather_query?version=1.0.0

# 获取技能版本历史
GET /api/skills/weather_query/versions
```

#### 技能搜索

```bash
POST /api/skills/search
Content-Type: application/json

{
  "query": "天气",
  "category": "utility",
  "min_rating": 4.0,
  "limit": 10
}
```

#### 个性化推荐

```bash
GET /api/skills/recommendations?user_history=weather_query,temperature_converter
```

#### 相似技能

```bash
GET /api/skills/weather_query/similar?limit=5
```

#### 技能发布

```bash
POST /api/skills/publish
Content-Type: application/json

{
  "skill_path": "skills/my_skill",
  "author_id": "developer123",
  "force": false
}
```

#### 技能更新

```bash
POST /api/skills/update
Content-Type: application/json

{
  "skill_path": "skills/my_skill",
  "author_id": "developer123",
  "change_type": "minor"
}
```

#### 评分系统

```bash
# 添加评分
POST /api/ratings
Content-Type: application/json

{
  "user_id": "user123",
  "skill_name": "weather_query",
  "skill_version": "1.0.0",
  "rating": 5,
  "comment": "非常好用！"
}

# 获取评分
GET /api/ratings/weather_query

# 获取Top评分技能
GET /api/ratings/top?min_ratings=5&limit=10

# 获取热门技能
GET /api/ratings/trending?days=7&limit=10
```

#### 统计信息

```bash
GET /api/stats
```

返回示例：
```json
{
  "registry": {
    "total_skills": 50,
    "verified_skills": 30,
    "categories": {"utility": 15, "automation": 20},
    "total_downloads": 10000,
    "average_rating": 4.5
  },
  "rating_system": {
    "total_ratings": 500,
    "total_skills_rated": 40,
    "total_users": 100,
    "global_average_rating": 4.3
  }
}
```

---

## 最佳实践

### 1. 技能命名规范

- 使用小写字母和下划线：`weather_query`, `data_analyzer`
- 名称应具有描述性
- 避免使用保留字

### 2. 版本管理

遵循语义化版本（SemVer）：

- **主版本号**（major）：不兼容的API修改
- **次版本号**（minor）：向下兼容的功能新增
- **修订号**（patch）：向下兼容的问题修正

示例：
- `1.0.0` → `1.0.1`：修复bug
- `1.0.1` → `1.1.0`：新增功能
- `1.1.0` → `2.0.0`：破坏性变更

### 3. 错误处理

始终提供清晰的错误信息：

```python
try:
    # 业务逻辑
    result = await do_something()
    return {"success": True, "data": result}
except ValueError as e:
    return {"success": False, "error": f"Invalid input: {e}"}
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    return {"success": False, "error": "Internal server error"}
```

### 4. 文档完善

- 在SKILL.md中提供详细的使用示例
- 添加Changelog记录变更
- 说明依赖和前置条件

### 5. 测试覆盖

编写单元测试：

```python
import pytest
from skills.my_skill.handler import handler

@pytest.mark.asyncio
async def test_execute_success():
    result = await handler.execute(param="test")
    assert result['success'] is True
    assert 'data' in result

@pytest.mark.asyncio
async def test_execute_missing_param():
    result = await handler.execute()
    assert result['success'] is False
    assert 'error' in result
```

### 6. 依赖管理

- 明确声明所有外部依赖
- 使用版本约束（^, ~, >=等）
- 定期检查依赖更新

### 7. 安全性

- 避免使用危险的函数（eval, exec, os.system等）
- 验证所有输入参数
- 记录敏感操作日志

---

## 常见问题

### Q1: 如何调试技能？

A: 启用详细日志：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Q2: 技能发布失败怎么办？

A: 先运行验证命令查看详细错误：

```bash
python -m skills.marketplace.cli validate my_skill
```

根据错误提示修复问题后重新发布。

### Q3: 如何处理技能依赖冲突？

A: 使用依赖解析器检查冲突：

```python
conflicts = resolver.detect_conflicts("my_skill", new_deps)
if conflicts:
    for conflict in conflicts:
        print(conflict['message'])
```

调整版本约束以解决冲突。

### Q4: 如何贡献技能到社区？

A: 
1. 确保技能通过验证
2. 编写完善的文档
3. 添加测试用例
4. 发布到技能市场
5. 在GitHub上分享（可选）

### Q5: 技能评分如何计算？

A: 采用加权平均算法：

```
平均评分 = 总评分 / 评分人数
```

同时考虑：
- 评分数量（越多越可信）
- 最近评分权重更高
- 有用点赞数

---

## 下一步

- 📖 阅读[多智能体系统文档](../多智能体系统文档.md)了解技能如何被Agent调用
- 🔧 查看[技能开发模板](./example_skill/)作为参考
- 🚀 开始创建你的第一个技能！

---

**版本**: 1.0.0  
**更新日期**: 2026-04-27  
**维护者**: 小雷版小龙虾团队
