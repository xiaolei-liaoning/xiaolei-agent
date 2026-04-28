# 技能市场生态系统 - 文档导航

## 📚 快速导航

### 🚀 新手入门

- [**5分钟快速开始**](./QUICKSTART.md) - 从零开始，5分钟创建你的第一个技能
- [**完整演示**](./demo.py) - 运行演示脚本，查看所有功能

### 📖 深入学习

- [**完整使用指南**](./README.md) - 详细的功能说明和最佳实践
- [**系统架构文档**](./ARCHITECTURE.md) - 深入理解系统设计
- [**项目总结**](./PROJECT_SUMMARY.md) - 了解项目全貌和成果

### 🛠️ 开发参考

- [**CLI工具文档**](./cli.py) - 命令行工具使用
- [**Web API文档**](http://localhost:8004/docs) - RESTful API接口（需先启动服务）
- [**示例技能**](./example_skill/) - 完整的技能模板

### 🧪 测试与验证

- [**单元测试**](./test_marketplace.py) - 运行测试验证系统
- [**技能验证器**](./validator.py) - 代码质量和安全检查

---

## 📂 目录结构

```
skills/marketplace/
│
├── 📄 文档
│   ├── INDEX.md                    # 本文档（导航）
│   ├── QUICKSTART.md               # 快速入门指南
│   ├── README.md                   # 完整使用指南
│   ├── ARCHITECTURE.md             # 系统架构文档
│   └── PROJECT_SUMMARY.md          # 项目总结
│
├── 💻 核心代码
│   ├── __init__.py                 # 模块导出
│   ├── registry.py                 # 技能注册表
│   ├── version_manager.py          # 版本管理器
│   ├── dependency_resolver.py      # 依赖解析器
│   ├── rating_system.py            # 评分系统
│   ├── search_engine.py            # 搜索引擎
│   ├── validator.py                # 验证器
│   └── publisher.py                # 发布器
│
├── 🔌 用户接口
│   ├── cli.py                      # CLI命令行工具
│   └── api.py                      # Web API服务
│
├── 🧪 测试与演示
│   ├── test_marketplace.py         # 单元测试套件
│   └── demo.py                     # 完整功能演示
│
├── 📝 示例
│   └── example_skill/              # 示例技能模板
│       ├── handler.py
│       └── SKILL.md
│
└── 📦 数据
    ├── data/                       # 持久化数据
    │   └── registry.json
    └── published/                  # 发布的技能包
```

---

## 🎯 按场景查找文档

### 我想创建技能

1. 📖 阅读 [快速入门](./QUICKSTART.md) 的"创建你的第一个技能"部分
2. 🛠️ 运行 `python -m skills.marketplace.cli create my_skill`
3. 📝 参考 [示例技能](./example_skill/) 的结构
4. ✅ 运行 `python -m skills.marketplace.cli validate my_skill`
5. 🚀 运行 `python -m skills.marketplace.cli publish my_skill --author name`

### 我想搜索和使用技能

1. 🔍 使用CLI：`python -m skills.marketplace.cli search "关键词"`
2. 🌐 或使用API：访问 http://localhost:8004/docs
3. 📊 查看 [搜索引擎文档](./search_engine.py) 了解高级功能

### 我想了解系统架构

1. 📚 阅读 [架构文档](./ARCHITECTURE.md)
2. 🔍 查看各个核心组件的源码
3. 🧪 运行 [演示脚本](./demo.py) 观察系统行为

### 我想贡献代码

1. 📖 阅读 [完整指南](./README.md) 的"最佳实践"部分
2. 🧪 运行测试确保代码质量：`python skills/marketplace/test_marketplace.py`
3. 📝 遵循 [技能开发规范](./README.md#技能开发规范)
4. 🔍 提交前运行验证器检查

### 我想部署到生产环境

1. 📚 阅读 [架构文档](./ARCHITECTURE.md) 的"部署方案"部分
2. 🔧 配置环境变量和数据库
3. 🐳 使用Docker容器化部署（未来支持）
4. 📊 设置监控和日志

---

## 🔗 相关资源

### 内部链接

- [多智能体系统文档](../多智能体系统文档.md) - 了解技能如何被Agent调用
- [技能系统概述](../../小雷版小龙虾Agent系统完整技术文档.md) - 整体系统架构

### 外部资源

- [SemVer 2.0规范](https://semver.org/) - 语义化版本标准
- [FastAPI文档](https://fastapi.tiangolo.com/) - Web框架文档
- [Python异步编程](https://docs.python.org/3/library/asyncio.html) - asyncio指南

---

## ❓ 常见问题快速解答

### Q: 如何开始？
A: 阅读 [QUICKSTART.md](./QUICKSTART.md)，5分钟即可上手。

### Q: 技能的标准结构是什么？
A: 查看 [example_skill/](./example_skill/) 目录，包含完整示例。

### Q: 如何验证我的技能？
A: 运行 `python -m skills.marketplace.cli validate <skill_name>`

### Q: API文档在哪里？
A: 启动API服务后访问 http://localhost:8004/docs

### Q: 如何运行测试？
A: 执行 `python skills/marketplace/test_marketplace.py`

### Q: 遇到问题怎么办？
A: 
1. 查看 [README.md](./README.md) 的"常见问题"部分
2. 检查日志输出
3. 联系 support@xiaolei.com

---

## 📞 获取帮助

- 📧 **邮箱**：support@xiaolei.com
- 💬 **GitHub Issues**：提交问题和建议
- 📖 **文档**：从本文档开始导航
- 🚀 **快速开始**：[QUICKSTART.md](./QUICKSTART.md)

---

<div align="center">

## 🎉 开始你的技能开发之旅！

```bash
# 第一步：创建技能
python -m skills.marketplace.cli create hello_world

# 第二步：查看文档
open skills/marketplace/QUICKSTART.md

# 第三步：开始编码
# 编辑 skills/hello_world/handler.py
```

**祝你开发愉快！** 🚀

</div>
