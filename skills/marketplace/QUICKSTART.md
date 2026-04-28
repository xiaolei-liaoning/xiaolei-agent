# 技能市场生态系统 - 快速入门指南

## 🎯 5分钟快速开始

### 1️⃣ 创建你的第一个技能（30秒）

```bash
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent

# 使用CLI工具创建新技能
python -m skills.marketplace.cli create hello_world
```

这将自动生成标准的技能结构：
```
skills/hello_world/
├── __init__.py
├── handler.py          # 技能核心代码
├── SKILL.md            # 技能元数据
├── requirements.txt    # 依赖声明
└── tests/
    └── test_handler.py
```

### 2️⃣ 实现技能逻辑（1分钟）

编辑 `skills/hello_world/handler.py`：

```python
class HelloWorldHandler:
    async def execute(self, **params):
        name = params.get('name', 'World')
        return {
            "success": True,
            "result": f"Hello, {name}!",
            "data": {"greeting": f"Hello, {name}!"}
        }

handler = HelloWorldHandler()
```

### 3️⃣ 验证技能（30秒）

```bash
python -m skills.marketplace.cli validate hello_world
```

输出示例：
```
✅ Validation PASSED
```

### 4️⃣ 发布技能（30秒）

```bash
python -m skills.marketplace.cli publish hello_world --author your_name
```

### 5️⃣ 搜索和使用技能（30秒）

```bash
# 搜索技能
python -m skills.marketplace.cli search "hello"

# 列出所有技能
python -m skills.marketplace.cli list
```

---

## 📚 核心概念速览

### 技能是什么？

技能是可重用的功能模块，可以被AI Agent调用执行特定任务。

**示例技能：**
- 🔍 天气查询
- 📊 数据分析
- 🌐 网页爬取
- 📝 文本翻译
- 🖼️ 图像处理

### 技能结构

每个技能必须包含：

1. **handler.py** - 核心逻辑
   ```python
   class MySkillHandler:
       async def execute(self, **params):
           # 你的业务逻辑
           return {"success": True, "result": "..."}
   
   handler = MySkillHandler()  # 必需！
   ```

2. **SKILL.md** - 元数据
   ```markdown
   # 技能名称
   ## Version: 1.0.0
   ## Author: Your Name
   ## Description: ...
   ```

### 版本管理

遵循语义化版本（SemVer）：

- `1.0.0` → `1.0.1`: 修复bug
- `1.0.1` → `1.1.0`: 新增功能
- `1.1.0` → `2.0.0`: 破坏性变更

---

## 🛠️ 常用命令

### CLI工具

```bash
# 创建技能
python -m skills.marketplace.cli create my_skill

# 验证技能
python -m skills.marketplace.cli validate my_skill

# 打包技能
python -m skills.marketplace.cli package my_skill

# 发布技能
python -m skills.marketplace.cli publish my_skill --author name

# 列出技能
python -m skills.marketplace.cli list

# 搜索技能
python -m skills.marketplace.cli search "keyword"
```

### Web API

启动API服务：
```bash
python -m skills.marketplace.api
```

访问 http://localhost:8004/docs 查看完整API文档。

**常用API：**

```bash
# 获取技能列表
curl http://localhost:8004/api/skills

# 搜索技能
curl -X POST http://localhost:8004/api/skills/search \
  -H "Content-Type: application/json" \
  -d '{"query": "天气", "limit": 10}'

# 添加评分
curl -X POST http://localhost:8004/api/ratings \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "skill_name": "weather_query",
    "skill_version": "1.0.0",
    "rating": 5,
    "comment": "很好用！"
  }'

# 获取统计信息
curl http://localhost:8004/api/stats
```

---

## 💡 最佳实践

### ✅ DOs

1. **编写清晰的文档**
   - 在SKILL.md中提供详细的使用示例
   - 说明参数和返回值

2. **处理异常**
   ```python
   try:
       result = await do_something()
       return {"success": True, "data": result}
   except Exception as e:
       return {"success": False, "error": str(e)}
   ```

3. **添加测试**
   ```python
   @pytest.mark.asyncio
   async def test_execute():
       result = await handler.execute()
       assert result['success'] is True
   ```

4. **声明依赖**
   - 在requirements.txt中列出所有外部依赖
   - 使用版本约束（^, ~, >=）

### ❌ DON'Ts

1. **不要使用危险函数**
   - 避免 `eval()`, `exec()`, `os.system()`

2. **不要硬编码敏感信息**
   - 使用环境变量或配置文件

3. **不要忘记错误处理**
   - 始终捕获并返回有意义的错误信息

---

## 🔍 常见问题

### Q: 如何调试技能？

A: 启用详细日志：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Q: 技能验证失败怎么办？

A: 查看详细错误信息：
```bash
python -m skills.marketplace.cli validate my_skill
```

根据提示修复问题。

### Q: 如何更新技能版本？

A: 
```bash
# 自动递增版本号并发布
python -m skills.marketplace.cli publish my_skill --author name
```

或者手动修改SKILL.md中的版本号。

### Q: 如何处理技能依赖？

A: 在SKILL.md中声明：
```markdown
## Dependencies
{
  "helper_skill": "^1.0.0",
  "utils": "~2.1.0"
}
```

系统会自动解析和安装依赖。

---

## 📖 深入学习

- 📘 [完整使用指南](./README.md)
- 🔧 [技能开发规范](./README.md#技能开发规范)
- 🌐 [Web API文档](http://localhost:8004/docs)
- 📝 [多智能体系统文档](../多智能体系统文档.md)

---

## 🎉 开始创造！

现在你已经掌握了基础知识，开始创建你的第一个技能吧！

```bash
python -m skills.marketplace.cli create my_awesome_skill
```

祝你开发愉快！🚀
