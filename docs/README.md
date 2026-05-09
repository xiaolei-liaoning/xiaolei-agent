# 🦞 小雷版小龙虾Agent系统

> 一个功能强大的多智能体系统，支持并行处理大量不同类型任务

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-45/45-brightgreen.svg)](tests/)

---

## ✨ 核心特性

- 🤖 **多智能体架构**: 检查、爬虫、漏洞、总结等独立Agent并行工作
- 🔍 **RAG搜索引擎**: 向量搜索 + 知识摘要 + 智能缓存
- 💭 **深度思考**: 两层大脑架构，实现思考-搜索-验证-回答闭环
- 🎭 **人物SKILL**: 知心闺蜜、李白、Linus等6个角色对话
- 📊 **数据分析**: Pandas处理 + Matplotlib可视化
- 🌐 **第三方集成**: 微信、钉钉、GitHub等应用对接
- 💾 **数据备份**: 自动备份 + 版本管理 + 恢复机制

---

## 🚀 快速开始

### 1️⃣ 一键配置环境

```bash
# 克隆项目
git clone <repository-url>
cd 小雷版小龙虾agent

# 运行配置脚本（自动安装依赖、配置环境）
./setup_dev.sh
```

### 2️⃣ 配置API密钥

编辑 `.env` 文件：
```bash
ZHIPU_API_KEY=your_api_key_here
COZE_API_TOKEN=your_coze_token_here
```

### 3️⃣ 启动服务

```bash
# 标准模式
./start.sh

# 开发模式（热重载）
./start.sh --dev
```

访问：
- 🌐 http://localhost:8001
- 📊 http://localhost:8001/monitor
- 📖 http://localhost:8001/docs

---

## 📖 文档

- [📘 完整技术文档](小雷版小龙虾Agent系统完整技术文档.md)
- [👨‍💻 开发者指南](docs/DEVELOPER_GUIDE.md)
- [🔧 优化历史](docs/OPTIMIZATION_COMPLETE.md)
- [📊 测试报告](tests/FINAL_VERIFICATION_REPORT.md)

---

## 🛠️ 开发工具

### 代码格式化
```bash
black .          # 格式化代码
isort .          # 排序import
```

### 运行测试
```bash
pytest tests/ -v                    # 所有测试
pytest tests/test_xxx.py -v         # 单个测试
pytest --cov=core --cov-report=html # 覆盖率报告
```

### Git预提交检查
```bash
pre-commit install                  # 安装钩子
pre-commit run --all-files          # 手动检查
```

---

## 📊 测试结果

✅ **测试覆盖率**: 100% (45/45)  
✅ **PlanningAgent**: 15/15通过  
✅ **RAG搜索**: 10/10通过  
✅ **向量备份**: 20/20通过  

详见 [测试报告](tests/FINAL_VERIFICATION_REPORT.md)

---

## 🏗️ 系统架构

```
客户端 → API层 → 调度中心 → Agent执行层 → 核心支撑层 → 基础设施
```

详细架构图见 [技术文档第9章](小雷版小龙虾Agent系统完整技术文档.md#9-系统架构)

---

## 🤝 贡献指南

欢迎贡献！请阅读 [开发者指南](docs/DEVELOPER_GUIDE.md)

1. Fork本项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启Pull Request

---

## 📝 License

MIT License - 详见 [LICENSE](LICENSE) 文件

---

**Made with ❤️ by 小雷版小龙虾团队**
