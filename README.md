# 小雷版小龙虾 Agent

一个强大的 AI 智能助手系统，支持多技能、多 Agent 协作和工作流编排。

## 功能特性

- 🤖 **多 Agent 系统** - 支持多个 Agent 协作完成复杂任务
- ⚡ **技能系统** - 丰富的技能库，支持热加载
- 🔄 **工作流引擎** - 可视化工作流搭建，支持 XML 配置
- 📊 **数据分析** - 内置数据处理和分析能力
- 🌐 **Web 爬虫** - 支持多个网站的数据抓取
- 🎯 **智能调度** - 任务分解和智能调度

## 快速开始

### 环境要求

- Python 3.10+
- 必要的依赖包

### 安装

```bash
git clone https://github.com/xiaolei-liaoning/xiaolei-agent.git
cd xiaolei-agent
pip install -r requirements.txt
```

### 运行

```bash
# 启动 CLI
python cli.py

# 启动 Web 服务
python web_server.py
```

## 项目结构

```
xiaolei-agent/
├── api/          # REST API 路由
├── cli/          # CLI 命令行工具
├── core/         # 核心模块
├── skills/       # 技能模块
├── tests/        # 测试文件
├── tools/        # 工具模块
├── docs/         # 文档
└── main.py       # 主入口
```

## 配置

复制 `.env.example` 到 `.env` 并配置相关参数：

```bash
cp .env.example .env
```

## 技能列表

- `weather` - 天气查询
- `web_scraper` - 网页爬虫
- `data_analysis` - 数据分析
- `gui_automation` - GUI 自动化
- `translator` - 翻译
- `deep_thinking` - 深度思考
- `code_sandbox` - 代码沙盒

## 使用示例

```python
from core.skill_dispatcher import SkillDispatcher

dispatcher = SkillDispatcher()
skill = dispatcher.match_skill("今天天气怎么样")
print(f"匹配到技能: {skill}")
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题，请提交 Issue 或联系开发者。