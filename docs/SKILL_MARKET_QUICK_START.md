# 技能市场快速开始指南

## 🚀 5分钟上手技能市场

### 1. 启动服务

```bash
# 启动主聊天服务（包含技能市场）
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾交流
python3 main.py

# 在另一个终端启动 Agent 引擎服务
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent
python3 main.py
```

### 2. 访问技能市场

打开浏览器访问：http://localhost:8000/skills-market

---

## 🎯 核心功能

### 浏览技能

**搜索技能**：
- 在搜索框输入关键词
- 实时过滤技能列表

**筛选分类**：
- 点击分类下拉框
- 选择感兴趣的分类（自动化、搜索、生活等）

**排序方式**：
- 热门度：按评分数量排序
- 评分：按平均评分排序
- 最新：按创建时间排序

### 查看技能详情

1. 点击技能卡片的"查看详情"按钮
2. 查看完整信息：
   - 📝 描述和功能
   - ⭐ 评分统计
   - 💬 用户评论
   - 📦 依赖关系
   - 🔄 版本历史

### 评分和评论

**评分步骤**：
1. 打开技能详情
2. 在"为此技能评分"区域
3. 鼠标悬停选择星级（1-5星）
4. 可选填写评论
5. 点击"提交评分"

**查看评论**：
- 滚动到"最新评论"区域
- 查看其他用户的评价

---

## 🔨 开发新技能

### 方法 1: 使用命令行工具（推荐）

```bash
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent

# 1. 创建技能模板
python -m skill_cli create my_awesome_skill \
  --description "我的超棒技能" \
  --category "自动化"

# 2. 编辑技能逻辑
vim skills/my_awesome_skill/handler.py

# 3. 完善文档
vim skills/my_awesome_skill/SKILL.md

# 4. 验证技能
python -m skill_cli validate my_awesome_skill

# 5. 运行测试
python -m pytest skills/my_awesome_skill/tests/

# 6. 打包技能
python -m skill_cli package my_awesome_skill
```

### 方法 2: 手动创建

**目录结构**：
```
skills/my_skill/
├── __init__.py          # 空文件
├── handler.py           # 技能核心逻辑
├── config.py            # 配置文件
├── SKILL.md             # 技能文档
├── requirements.txt     # 依赖声明
└── tests/
    └── test_handler.py  # 测试文件
```

**handler.py 模板**：
```python
#!/usr/bin/env python3
"""My Skill - 技能描述"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class MySkillHandler:
    """技能处理器"""
    
    def __init__(self):
        logger.info("My Skill 初始化")
    
    async def execute(self, **params) -> Dict[str, Any]:
        """执行技能
        
        Args:
            **params: 技能参数
            
        Returns:
            dict: 执行结果
        """
        try:
            logger.info(f"执行 My Skill，参数: {params}")
            
            # TODO: 实现你的逻辑
            result = "处理结果"
            
            return {
                "success": True,
                "result": result,
                "message": "执行成功"
            }
            
        except Exception as e:
            logger.error(f"My Skill 执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": f"执行失败: {str(e)}"
            }


# 导出技能实例
handler = MySkillHandler()
```

**SKILL.md 模板**：
```markdown
# My Skill - 技能描述

## 📋 功能描述
详细描述技能的功能和用途

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
→ my_skill.execute(param1='value1')
```

## 📦 依赖
- 依赖包1 (版本要求)

## 🎯 性能指标
- 响应时间: <500ms
- 准确率: 99%
```

---

## 📊 API 使用

### 获取技能列表

```bash
# 基础查询
curl http://localhost:8000/api/skills/list

# 带筛选
curl "http://localhost:8000/api/skills/list?category=自动化&sort_by=rating"

# 关键词搜索
curl "http://localhost:8000/api/skills/list?keyword=爬虫"
```

### 获取技能详情

```bash
curl http://localhost:8000/api/skills/web_scraper
```

### 提交评分

```bash
curl -X POST http://localhost:8000/api/skills/web_scraper/rate \
  -H "Content-Type: application/json" \
  -d '{
    "skill_name": "web_scraper",
    "user_id": 1,
    "rating": 5,
    "comment": "非常好用的爬虫工具！"
  }'
```

### 获取市场统计

```bash
curl http://localhost:8000/api/skills/stats
```

---

## 💡 最佳实践

### 技能命名
- ✅ 使用下划线分隔：`web_scraper`, `data_analysis`
- ❌ 避免空格和特殊字符

### 技能分类
选择合适的分类：
- 生活：天气、翻译等
- 数据采集：爬虫、抓取
- 分析：数据分析、可视化
- 自动化：工作流、GUI自动化
- 搜索：搜索引擎、RAG
- 对话：AI对话
- 系统：系统工具

### 文档编写
- 清晰的功能描述
- 详细的使用示例
- 完整的参数说明
- 准确的依赖声明

### 测试
- 编写单元测试
- 测试边界情况
- 验证错误处理

---

## 🔍 故障排查

### 问题 1: 技能列表为空

**原因**：Agent 引擎服务未启动

**解决**：
```bash
# 检查 Agent 服务
curl http://localhost:8001/api/tools

# 如果失败，启动服务
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent
python3 main.py
```

### 问题 2: 评分提交失败

**原因**：用户未登录或 token 过期

**解决**：
1. 重新登录
2. 清除浏览器缓存
3. 刷新页面

### 问题 3: 技能验证失败

**原因**：缺少必需文件或格式不正确

**解决**：
```bash
# 查看详细错误
python -m skill_cli validate my_skill

# 检查必需文件
ls -la skills/my_skill/

# 确保有 handler.py 和 SKILL.md
```

---

## 📚 更多资源

- **完整实施文档**: [docs/SKILL_MARKET_IMPLEMENTATION_PHASE1.md](./docs/SKILL_MARKET_IMPLEMENTATION_PHASE1.md)
- **技能开发指南**: 查看 `skill_cli.py` 源码
- **API 文档**: 访问 http://localhost:8000/docs

---

## 🎉 开始使用

现在你已经掌握了技能市场的基本用法：

1. ✅ 浏览和发现技能
2. ✅ 评分和评论
3. ✅ 开发新技能
4. ✅ 使用 API

祝你使用愉快！🚀
