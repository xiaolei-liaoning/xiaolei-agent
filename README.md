# 🦐 小雷版小龙虾 AI Agent

**版本**: 3.3.1

一个功能强大的 AI 智能助手系统，支持多技能、多 Agent 协作和工作流编排，提供类似 Claude Code 的交互体验。

---

## ✨ 功能特性

### 🤖 多 Agent 系统
- **Master Agent** - 任务调度与协调中心
- **Worker Agent** - 执行具体任务
- **Expert Agent** - 领域专家（爬虫、分析、翻译等）
- **Reviewer Agent** - 结果审查与优化
- **Planning Agent** - 智能任务规划与拆解
- **Character Agent** - 人物角色（李白、Linus Torvalds等）

### ⚡ 技能系统
- 网页爬虫（微博、知乎、抖音、B站等）
- 数据分析与可视化
- GUI 自动化
- 翻译（支持多语言）
- 深度思考引擎
- 代码沙盒执行
- **动态代码生成** - 当无现成工具时，LLM自动生成Python/Shell脚本解决问题

### 🎯 智能降级机制
- **工具优先策略** - 优先使用预配置的工具和技能
- **代码生成降级** - 工具不可用时自动触发LLM生成解决方案代码
- **安全沙盒执行** - 所有生成的代码在隔离环境中运行，防止安全风险
- **资源限制保护** - 超时控制、内存限制、模块白名单管理

### 🎯 CLI 命令系统（类似 Claude Code）

#### 基础命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/help` | 显示帮助 | `/help` |
| `/run` | 执行智能工作流 | `/run "爬取微博热搜并分析"` |
| `/chat` | 进入聊天模式 | `/chat` 或 `/chat simple "你好"` |
| `/think` | 切换思考模式 | `/think` |
| `/status` | 系统状态 | `/status` |
| `/clear` | 清屏 | `/clear` |
| `/history` | 历史记录 | `/history` |
| `/debug` | 调试模式 | `/debug` |
| `/reset` | 重置 | `/reset` 或 `/reset all` |
| `/quit` | 退出 | `/quit` 或 `/exit` |

#### 工具命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/mcp` | MCP服务器管理 | `/mcp agency`, `/mcp fun` |
| `/agent` | Agent管理 | `/agent list`, `/agent call Writer "写文章"` |
| `/analyze` | 数据分析 | `/analyze wordcloud --file data.csv` |
| `/scrape` | 数据爬取 | `/scrape weibo` |
| `/game` | 小游戏 | `/game guess`, `/game rps`, `/game dice` |
| `/fun` | 趣味工具 | `/fun joke`, `/fun fact`, `/fun fortune` |
| `/art` | ASCII艺术 | `/art cat`, `/art dog`, `/art rocket` |
| `/review` | 代码审查 | `/review code main.py`, `/review security 'rm -rf /'` |
| `/config` | 配置管理 | `/config show`, `/config set key value` |
| `/plugin` | 插件工具 | `/plugin list`, `/plugin create my-plugin` |
| `/smart` | 智能多Agent | `/smart "任务描述"`, `/smart demo` |
| `/wechat` | 微信消息 | `/wechat send --friend 张三 --message 你好` |
| `/automate` | GUI自动化 | `/automate open_app --app Safari` |

#### MCP 服务器命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/mcp list` | 列出已连接的服务器 | `/mcp list` |
| `/mcp connect <server>` | 连接指定服务器 | `/mcp connect the-agency` |
| `/mcp disconnect <server>` | 断开服务器 | `/mcp disconnect fun` |
| `/mcp select <server>` | 设置当前服务器 | `/mcp select weather` |
| `/mcp agency` | 连接the-agency服务器 | `/mcp agency` |
| `/mcp fun` | 连接趣味MCP服务器 | `/mcp fun` |
| `/mcp weather` | 连接天气MCP服务器 | `/mcp weather` |
| `/mcp calculator` | 连接计算器MCP服务器 | `/mcp calculator` |
| `/mcp file-ops` | 连接文件操作MCP服务器 | `/mcp file-ops` |
| `/mcp text-processing` | 连接文本处理MCP服务器 | `/mcp text-processing` |
| `/mcp tools [server]` | 查看可用工具 | `/mcp tools` |
| `/mcp call <server> <tool>` | 调用指定服务器的工具 | `/mcp call weather get_weather` |
| `/mcp quick <tool> [args]` | 快速调用当前服务器的工具 | `/mcp quick joke` |
| `/mcp status` | 查看连接状态 | `/mcp status` |
| `/mcp history` | 查看调用历史 | `/mcp history` |

### 🔄 智能工作流引擎
- 可视化工作流搭建
- XML 配置支持
- 任务依赖管理
- 错误重试与反思机制

### 📊 增强日志系统
- 时间戳显示
- 颜色区分级别
- 结构化输出

---

## 🚀 快速开始

### 环境要求
- Python 3.10+
- 必要的依赖包

### 安装

```bash
git clone https://github.com/xiaolei-liaoning/xiaolei-agent.git
cd xiaolei-agent
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env 配置文件
```

### 运行

```bash
# 启动 CLI
python cli.py

# 启动 Web 服务
python web_server.py
```

---

## 📁 项目结构

```
xiaolei-agent/
├── api/                          # REST API 路由
│   ├── routes/
│   │   ├── chat.py              # 聊天API
│   │   ├── history.py           # 历史记录API
│   │   ├── system.py            # 系统API
│   │   ├── skills.py            # 技能管理API
│   │   ├── agent_groups.py      # Agent小组API
│   │   ├── self_check.py        # 自我校验API
│   │   └── plans.py             # 计划管理API
│   ├── workflow.py              # 工作流API
│   ├── schedule.py              # 定时任务API
│   └── monitor.py               # 监控API
│
├── cli/                          # CLI 命令行工具
│   ├── base.py                   # 基础命令
│   ├── colors.py                 # 颜色输出
│   ├── command_parser.py         # 命令解析器
│   ├── thinking_engine.py        # 思考引擎
│   ├── logging_system.py         # 日志系统
│   ├── pagination.py             # 分页显示
│   ├── games.py                 # 游戏模块
│   ├── fun_tools.py             # 趣味工具
│   ├── ascii_art.py             # ASCII艺术
│   ├── agent_tools.py           # Agent工具
│   ├── review_tools.py          # 审查工具
│   ├── config_tools.py          # 配置工具
│   ├── plugin_tools.py          # 插件工具
│   ├── smart_agent.py           # 智能Agent
│   ├── analyze.py               # 分析工具
│   ├── scrape.py                # 爬虫工具
│   └── automate.py              # 自动化工具
│
├── core/                         # 核心模块
│   ├── engine/                  # 引擎层
│   │   ├── llm_backend.py       # LLM后端
│   │   ├── reasoning_engine.py   # 推理引擎
│   │   └── skill_dispatcher.py  # 技能分发器
│   │
│   ├── multi_agent_v2/          # 多Agent系统 v2
│   │   ├── agents/              # Agent实现
│   │   │   ├── base/            # 基础Agent
│   │   │   ├── master/          # MasterAgent
│   │   │   ├── worker/          # WorkerAgent
│   │   │   ├── expert/          # ExpertAgent
│   │   │   └── reviewer/        # ReviewerAgent
│   │   │
│   │   ├── infrastructure/      # 基础设施
│   │   │   ├── llm/            # LLM接口
│   │   │   ├── memory/         # 记忆系统
│   │   │   ├── observability/  # 可观测性
│   │   │   └── persistence/    # 持久化
│   │   │
│   │   └── orchestration/      # 编排层
│   │       ├── collaboration/   # 协作策略
│   │       ├── context/        # 上下文管理
│   │       ├── lifecycle/      # 生命周期
│   │       └── scheduler/       # 调度器
│   │
│   ├── infrastructure/          # 通用基础设施
│   │   ├── database.py         # 数据库
│   │   ├── cache_manager.py    # 缓存管理
│   │   ├── config_manager.py   # 配置管理
│   │   └── di_container.py     # DI容器
│   │
│   ├── agents/                  # Agent通信与协作
│   │   ├── agent_communication.py
│   │   ├── smart_multi_agent.py
│   │   └── group_collaboration.py
│   │
│   ├── workflow/                # 工作流引擎
│   │   ├── xml_workflow_mapper.py
│   │   ├── bfs_processor.py
│   │   └── automation_workflow.py
│   │
│   ├── mcp/                     # MCP客户端
│   │   └── mcp_client.py
│   │
│   ├── memory/                  # 记忆系统
│   │   ├── short_term_memory.py
│   │   ├── character_memory.py
│   │   └── vector_memory.py
│   │
│   ├── security/                # 安全模块
│   │   ├── security.py
│   │   └── error_handler.py
│   │
│   ├── monitoring/              # 监控模块
│   │   └── monitoring.py
│   │
│   ├── handlers.py              # 请求处理器
│   ├── agent_coordinator.py     # Agent协调器
│   ├── execution_logger.py      # 执行日志
│   └── multi_agent_system.py   # 多Agent系统
│
├── skills/                       # 技能模块
│   ├── weather/                 # 天气技能
│   ├── fun/                     # 趣味技能
│   ├── marketplace/             # 技能市场
│   ├── openclaw/                # OpenClaw集成
│   ├── workflow_engine.py       # 工作流引擎
│   └── xmi_converter.py         # XMI转换器
│
├── mcp/                          # MCP服务器
│   ├── fun_mcp_server.py
│   └── weather_mcp_server.py
│
├── docs/                         # 文档
│   ├── ARCHITECTURE.md         # 架构文档
│   ├── DEVELOPER_GUIDE.md      # 开发者指南
│   └── DOCUMENTATION_AUDIT_REPORT.md  # 文档审计报告
│
├── tests/                        # 测试文件
│
├── static/                       # 静态文件
│
├── templates/                    # HTML模板
│
├── main.py                       # 主入口 (Port 8001)
├── cli.py                        # CLI入口
├── web_server.py                # Web服务器
├── pyproject.toml               # 项目配置
└── requirements.txt             # 依赖
```

---

## 🎮 使用示例

### 基础命令

```bash
# 查看帮助
/help

# 执行智能工作流
/run "帮我爬取微博热搜并生成词云分析报告"

# 进入聊天模式
/chat

# 切换思考模式（显示执行步骤）
/think

# 调用Agent
/agent call Writer "写一篇关于人工智能的短文"
```

### 爬虫技能

```bash
# 爬取微博热搜
/scrape weibo

# 爬取知乎热榜
/scrape zhihu

# 爬取抖音热点
/scrape douyin
```

### MCP 服务器

```bash
# 连接趣味MCP服务器
/mcp fun

# 连接天气MCP服务器
/mcp weather

# 连接计算器MCP服务器
/mcp calculator

# 调用工具
/mcp quick joke
```

### 数据分析

```bash
# 生成词云
/analyze wordcloud --file data.csv

# 数据可视化
/analyze visualize --type chart
```

### 趣味功能

```bash
# 随机笑话
/fun joke

# 冷知识
/fun fact

# 猜数字游戏
/game guess

# 石头剪刀布
/game rps
```

### 🎯 代码生成能力（智能降级）

当系统没有现成工具时，Agent会自动生成代码来解决问题：

```bash
# 文件统计 - Agent自动生成Python脚本统计文件
/run "帮我统计当前目录下有多少个Python文件"

# 复杂计算 - Agent生成数学计算代码
/run "计算1到100之间所有能被3或5整除的数的和"

# 数据处理 - Agent创建数据处理脚本
/run "创建一个包含10个随机数的列表并找出最大值"

# 字符串操作 - Agent编写字符串处理代码
/run "把'HelloWorld'反转并转成大写"
```

**工作原理：**
1. 用户发起请求
2. 系统尝试匹配现有工具
3. 若无合适工具 → LLM分析需求并生成解决方案代码
4. 代码在安全沙盒中执行
5. 返回结果给用户

**安全保障：**
- ✅ 隔离的沙盒环境
- ✅ 超时保护（默认30秒）
- ✅ 内存限制（默认256MB）
- ✅ 危险模块禁用（subprocess、socket等）
- ✅ 必要模块白名单（os、pathlib用于文件操作）

---

## 🧠 多 Agent 架构

### Agent 类型

| Agent | 职责 | 能力 |
|-------|------|------|
| **Master** | 任务调度与协调 | 任务分发、结果汇总 |
| **Worker** | 执行具体任务 | 技能调用、工具执行 |
| **Expert** | 领域专家 | 专业知识、深度分析 |
| **Reviewer** | 结果审查 | 质量检查、优化建议 |
| **Planner** | 任务规划 | 任务拆解、执行图生成 |
| **Character** | 人物角色 | 个性化对话、角色扮演 |

### 交互流程

```
用户输入
    ↓
规划 Agent → 任务拆解 → 生成执行图
    ↓
调度中心 → 动态分配 → 负载均衡
    ↓
多个 Agent 并行执行
    ↓
消息总线 → 共享记忆 → 状态同步
    ↓
反思 Agent → 检查结果 → 不满意重跑
    ↓
返回最终答案
```

### 🔧 智能降级机制

**传统Agent的局限：**
- ❌ 只能调用预配置的工具
- ❌ 无合适工具时直接失败或终止会话
- ❌ 无法处理未预见的任务类型

**小雷版小龙虾的解决方案：**

```
工具执行成功？
    ↓ 是
返回结果 ✅
    ↓ 否
触发代码生成降级
    ↓
LLM分析用户需求
    ↓
生成Python/Shell解决方案代码
    ↓
安全沙盒执行
    ↓
返回执行结果 ✅
```

**核心优势：**
1. **能力边界扩展** - 不再受限于预配置工具，可处理任意编程任务
2. **无缝用户体验** - 用户无需关心底层使用工具还是生成代码
3. **安全保障** - 所有生成代码在隔离沙盒中运行，有严格的资源限制
4. **智能优先级** - 优先使用现成工具（更快、更可靠），仅在必要时生成代码
5. **统一输出格式** - 无论工具执行还是代码生成，返回格式保持一致

**技术实现：**
- 文件：`core/handlers.py` - `_try_code_generation()` 函数
- 沙盒：`core/sandbox_executor.py` - 安全的代码执行环境
- 提示词：`core/multi_agent_v2/agents/prompts/agent_prompts.py` - LLM代码生成引导

---

## 📚 技能列表

### 爬虫技能
- `weibo` - 微博热搜
- `zhihu` - 知乎热榜
- `douyin` - 抖音热点
- `bilibili` - B站热门
- `github` - GitHub趋势
- `baidu` - 百度搜索

### 分析技能
- `wordcloud` - 词云生成
- `visualize` - 数据可视化
- `summary` - 文本摘要

### 自动化技能
- `gui_automation` - GUI自动化
- `web_scraper` - 网页爬虫

### 人物角色
- `libai` - 李白（诗人）
- `linus_torvalds` - Linus Torvalds
- `john_carmack` - John Carmack
- `bestfriend` - 好友
- `first_love` - 初恋
- `goddess` - 女神

---

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_multi_agent_collaboration.py -v

# 生成测试报告
python generate_test_report.py
```

### 测试覆盖

- ✅ 多 Agent 协同测试
- ✅ 人物记忆系统测试
- ✅ 技能调度测试
- ✅ MCP 客户端测试
- ✅ CLI 命令测试
- ✅ 工作流引擎测试

---

## 🔧 开发

### 添加新技能

1. 在 `skills/` 目录下创建新技能文件夹
2. 创建 `handler.py` 实现技能逻辑
3. 创建 `SKILL.md` 文档
4. 在 `core/skill_dispatcher.py` 中注册技能

### 添加新命令

1. 在 `cli/` 目录下创建命令处理函数
2. 在 `cli/command_parser.py` 中添加命令定义
3. 在 `cli.py` 中注册命令处理器

### 配置代码生成策略

如需调整代码生成的安全策略或行为，可修改以下配置：

**1. 沙盒资源限制**（`core/handlers.py`）
```python
# 调整超时时间、内存限制等
custom_limits = SandboxResourceLimits(
    timeout=30,              # 超时秒数
    max_memory_mb=256,       # 最大内存
    forbidden_modules=[...]  # 禁止导入的模块列表
)
```

**2. LLM提示词优化**（`core/multi_agent_v2/agents/prompts/agent_prompts.py`）
- 修改Worker Agent的system prompt
- 明确代码生成的使用场景和优先级
- 添加特定领域的代码生成指导

**3. 降级触发条件**（`core/handlers.py` - `handle_single_step()`）
- 调整何时触发代码生成（工具失败、工具不存在等）
- 自定义重试策略和错误处理逻辑

---

## 📝 许可证

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📞 联系方式

如有问题，请提交 Issue 或联系开发者。