# 开发者指南

## 🚀 快速开始

### 1. 环境准备

#### 系统要求
- Python 3.7+
- Git
- Redis（可选，用于缓存）

#### 一键配置开发环境
```bash
# 克隆项目
git clone <repository-url>
cd 小雷版小龙虾agent

# 运行配置脚本
./setup_dev.sh
```

这会自动完成：
- ✅ 创建虚拟环境
- ✅ 安装所有依赖
- ✅ 配置Git预提交钩子
- ✅ 生成.env配置文件

### 2. 启动服务

```bash
# 标准模式
./start.sh

# 开发模式（热重载）
./start.sh --dev

# 首次运行需要安装依赖
./start.sh --install
```

访问地址：
- 🌐 主界面: http://localhost:8001
- 📊 监控面板: http://localhost:8001/monitor
- 📖 API文档: http://localhost:8001/docs

---

## 🛠️ 开发工具链

### 代码格式化

项目使用 **Black** + **isort** 进行代码格式化。

#### VS Code自动格式化
已配置`.vs已配置`.vs已配，保存时自动格式化。

#### 手动格式化
```bash
# 格式化所有Python文件
black .

# 排序import
isort .

# 或者使用pre-commit
pre-commit run --all-files
```

### 代码检查

```bash
# Flake8检查
flake8 core/ skills/ tests/

# Pre-commit全面检查
pre-commit run --all-files
```

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_planning_agent.py -v

# 带覆盖率报告
pytest tests/ --cov=core --cov-report=html
```

---

## 📁 项目结构

```
小雷版小龙虾agent/
├── core/                    # 核心模块
│   ├── multi_agent_system.py    # 多智能体系统
│   ├── rag_search_engine.py     # RAG搜索引擎
│   ├── vector_store_backup.py   # 向量存储备份
│   └── ...
├── skills/                  # 技能模块
│   ├── deep_thinking/       # 深度思考
│   ├── web_scraper/         # 网页爬虫
│   └── ...
├── tests/                   # 测试用例
├── docs/                    # 文档
├── main.py                  # 入口文件
├── start.sh                 # 启动脚本
└── setup_dev.sh            # 环境配置脚本
```

---

## 🔧 常用开发任务

### 添加新技能

1. 在`skills/`目录下创建新文件夹
2. 实现`handler.py`，继承BaseSkillHandler
3. 在`tool_manager.py`中注册技能
4. 编写单元测试

示例：
```python
# skills/my_skill/handler.py
from tools.base import BaseSkillHandler

class MySkillHandler(BaseSkillHandler):
    async def execute(self, **kwargs):
        # 实现技能逻辑
        return {"success": True, "result": "..."}
```

### 添加新Agent

1. 在`core/multi_agent_system.py`中创建Agent类
2. 继承BaseAgent，实现`_run_task`方法
3. 在AgentScheduler中注册

### 修改API接口

1. 在`main.py`中添加新的路由
2. 遵循RESTful规范
3. 添加输入验证和错误处理
4. 更新API文档

---

## 🐛 调试技巧

### 日志查看

```bash
# 实时查看日志
tail -f logs/app.log

# 只查看错误
grep ERROR logs/app.log
```

### 交互式调试

在代码中插入断点：
```python
import pdb; pdb.set_trace()
```

或使用VS Code的图形化调试器。

### 性能分析

```bash
# 使用cProfile分析性能
python -m cProfile -o profile.stats main.py

# 可视化分析结果
snakeviz profile.stats
```

---

## 📝 代码规范

### Python风格指南
- 遵循PEP 8规范
- 使用Black自动格式化（行长度88）
- Import按isort规则排序

### 命名规范
- 变量/函数: `snake_case`
- 类名: `CamelCase`
- 常量: `UPPER_CASE`
- 私有方法: `_leading_underscore`

### 注释规范
- 所有公共API必须有docstring
- 复杂逻辑添加行内注释
- 使用TODO标记待办事项

---

## 🧪 测试规范

### 编写测试

```python
import pytest
from core.xxx import XXX

def test_xxx():
    # Arrange
    obj = XXX()
    
    # Act
    result = obj.method()
    
    # Assert
    assert result == expected
```

### 测试覆盖率目标
- 核心功能: ≥ 90%
- 新增代码: 必须包含测试
- 回归测试: 每次提交前运行

---

## 🚢 提交流程

### Git提交规范

```bash
# 功能新增
git commit -m "feat: 添加XXX功能"

# Bug修复
git commit -m "fix: 修复XXX问题"

# 文档更新
git commit -m "docs: 更新XXX文档"

# 重构
git commit -m "refactor: 重构XXX模块"

# 测试
git commit -m "test: 添加XXX测试"
```

### 提交前检查清单
- [ ] 代码已通过flake8检查
- [ ] 所有测试通过
- [ ] 更新了相关文档
- [ ] 添加了必要的注释
- [ ] 没有遗留的调试代码

---

## ❓ 常见问题

### Q: 如何重置虚拟环境？
```bash
rm -rf .venv
./setup_dev.sh
```

### Q: 测试失败怎么办？
1. 查看详细错误信息
2. 检查依赖是否完整安装
3. 确认环境变量配置正确
4. 查看CI/CD日志对比

### Q: 如何贡献代码？
1. Fork项目
2. 创建特性分支 (`git checkout -b feature/xxx`)
3. 提交更改
4. 推送到分支
5. 创建Pull Request

---

## 📚 参考资料

- [系统完整技术文档](../小雷版小龙虾Agent系统完整技术文档.md)
- [API文档](http://localhost:8001/docs)
- [优化历史](OPTIMIZATION_COMPLETE.md)

---

**Happy Coding! 🎉**
