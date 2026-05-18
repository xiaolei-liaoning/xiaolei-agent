# 小雷版小龙虾 AI Agent — 功能大全

> 版本: v3.3.1 | 代码量: ~94,000 行 Python | 模块数: ~200 个

---

## 一、运行方式

```bash
python cli.py                      # 交互式 CLI（终端模式）
python main.py                     # FastAPI 服务（端口 8001）
python cli.py chat                 # 直接进入聊天模式
python cli.py chat --mode deep     # 直接进入深度聊天模式
```

---

## 二、CLI 命令全集 (24个)

### 2.1 系统命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/help` | 显示帮助 | `/help` |
| `/status` | 系统状态 | `/status` |
| `/quit` / `/exit` | 退出 | `/quit` |
| `/clear` | 清屏 | `/clear` |
| `/history` | 命令历史 | `/history` |
| `/debug` | 调试模式开关 | `/debug` |
| `/think` | 思考模式开关（可视化执行步骤） | `/think` |
| `/reset [all]` | 重置命令历史 / 全部数据 | `/reset all` |

### 2.2 聊天模式 (4种模式)

| 命令 | 模式 | 特点 |
|------|------|------|
| `/chat simple` | 简单模式 | 直接执行，不加追问和反思 |
| `/chat deep` | 深度模式 | **预反问 → 执行 → 失败代码降级 → LLM反思评估** |
| `/chat expert` | 专家模式 | 同深度模式，但路由到 Expert Agent |
| `/chat quick` | 极速模式 | 跳过追问和反思，最快返回 |

### 2.3 工作流命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/run <任务>` | 智能工作流执行 | `/run 帮我爬取微博热搜并生成词云分析报告` |
| `/analyze <类型>` | 数据分析 | `/analyze wordcloud --file data.csv` |
| `/scrape <网站>` | 数据爬取 | `/scrape 微博 热搜top10` |

### 2.4 自动化命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/automate <操作>` | macOS GUI 自动化 | `/automate open_app --app Safari` |
| `/wechat send` | 发送微信消息 (AppleScript) | `/wechat send --friend 张三 --message 你好` |

### 2.5 MCP 命令 (15个子命令)

| 命令 | 功能 |
|------|------|
| `/mcp list` | 列出已连接的 MCP 服务器 |
| `/mcp connect <name>` | 连接服务器 |
| `/mcp disconnect <name>` | 断开连接 |
| `/mcp select <name>` | 设置当前活动服务器 |
| `/mcp status` | 连接状态 |
| `/mcp tools [server]` | 列出工具 |
| `/mcp call <server> <tool> [args]` | 调用工具 |
| `/mcp quick <tool> [args]` | 快速调用当前服务器工具 |
| `/mcp agency` | 连接 the-agency |
| `/mcp fun` | 趣味 MCP |
| `/mcp weather` | 天气 MCP |
| `/mcp calculator` | 计算器 MCP |
| `/mcp file-ops` | 文件操作 MCP |
| `/mcp text-processing` | 文本处理 MCP |
| `/mcp register / unregister / custom / history` | 自定义服务器管理 |

### 2.6 趣味命令

| 命令 | 功能 | 子命令 |
|------|------|--------|
| `/game guess` | 猜数字 | guess / rps / dice |
| `/fun joke` | 随机笑话 | joke / fact / fortune |
| `/art cat` | ASCII 艺术 | cat / dog / rocket |

### 2.7 Agent / 工具命令

| 命令 | 功能 | 子命令 |
|------|------|--------|
| `/agent list` | 列出所有 Agent | list / call |
| `/agent call <type> <task>` | 调用 Agent 执行任务 | |
| `/smart <任务>` | 智能多 Agent 协作 | |
| `/smart demo` | 演示多 Agent 协作 | |
| `/review code <file>` | 代码审查 | code / security |
| `/config show` | 配置管理 | show / set |
| `/plugin list` | 插件管理 | list / create |
| `/test [clarify/permission/forked]` | 测试核心服务 | |

### 2.8 ConfigAgent (新增)

运行 `/chat` 进入聊天模式后，输入任意自然语言。系统会自动:
1. 从 `config/agents.yml` 加载 8 个预定义 Agent
2. 根据你的输入匹配合适的 Agent
3. Agent 自动调用配置的工具执行任务

---

## 三、Multi-Agent 系统

### 架构

```
用户输入 → IntelligentScheduler → AgentPool(Lazy) → 执行 → 结果聚合
                    │
         IntentUnderstanding → CapabilityMatcher → TaskAllocator
```

### Agent 类型

| Agent | 职责 |
|-------|------|
| **MasterAgent** | 任务分解 → 分配给子 Agent → 结果聚合 |
| **WorkerAgent** | 执行具体任务 |
| **ExpertAgent** | 领域专家知识 / MCP 工具代理 |
| **ReviewerAgent** | 质量评审 / 安全检查 |
| **LazyAgent** | 懒加载包装器，需要时才初始化 |
| **ConfigAgent** (新增) | 配置驱动，从 config/agents.yml 读取 Prompt + Tools |

### 配置驱动 Agent (不需要写代码)

在 `config/agents.yml` 中定义：

```yaml
agents:
  my_agent:
    role_prompt: "你的角色描述"
    tools: ["weather-mcp", "calculator-mcp"]
    priority: 3
```

系统自动创建的 8 个预定义 Agent：

| Agent | 工具 | 优先级 |
|-------|------|--------|
| deep_thinker | deep_thinking, text_analyzer, rag_search | 5 |
| web_scraper | 微博, 知乎, B站, 抖音, GitHub, 百度, 头条, file-ops-mcp | 4 |
| data_analyst | data_analysis, text_analyzer, text-processing-mcp | 3 |
| weather_expert | weather-mcp | 2 |
| system_toolbox | system_toolbox, file-ops-mcp | 2 |
| translator | translator | 2 |
| creative | fun-mcp, art, game | 2 |
| general | chat, calculator-mcp, fun-mcp | 1 |

---

## 四、MCP 系统

### 组件

| 组件 | 功能 |
|------|------|
| MCPClientManager | 连接池 + JSON-RPC + 指数退避重试 |
| AwesomeMCPManager | 从 awesome-mcp-servers 列表管理外部 MCP |
| MCPAgent | 专门处理 MCP 连接的 Agent |

### 本地 MCP 服务器 (5个)

| 服务器 | 工具数 | 功能 |
|--------|--------|------|
| calculator-mcp | 10 | 加减乘除、幂运算、平方根、随机数 |
| weather-mcp | 2 | 天气查询、天气预报 (6个城市) |
| fun-mcp | 7 | 笑话、谜语、趣味知识、ASCII艺术、星座运势 |
| file-ops-mcp | 9 | 文件读写、目录管理、复制删除 |
| text-processing-mcp | 12 | 大小写转换、字数统计、URL提取 |

### 添加外部 MCP 服务器

编辑 `config/mcp_servers.yml`：

```yaml
servers:
  brave-search:
    command: npx
    args: ["-y", "@anthropic-ai/mcp-server-brave-search"]
    env:
      BRAVE_API_KEY: "your_key"
```

### MCP REST API (新增)

```
GET  /api/v1/mcp/servers           → 列出所有配置的服务器
POST /api/v1/mcp/connect/{name}   → 连接指定服务器
POST /api/v1/mcp/call              → 调用工具
GET  /api/v1/mcp/tools/{name}     → 列出服务器工具
```

---

## 五、Web 爬虫 (8个)

| 爬虫 | 目标 | 状态 |
|------|------|------|
| weibo_scraper | 微博热搜 / 话题 | ✅ 已测试通过 |
| zhihu_scraper | 知乎热榜 | ⚠️ 功能极简 |
| bilibili_scraper | B站热门 / 视频 | ✅ 已测试通过 |
| douyin_scraper | 抖音热搜 / 视频 | ✅ 已测试通过 |
| baidu_scraper | 百度热搜 | ✅ 已测试通过 |
| toutiao_scraper | 头条热搜 | ✅ 已测试通过 |
| github_scraper | GitHub 趋势 / 仓库 | ✅ 已测试通过 |
| search_scraper | 通用搜索 | ⚠️ 骨架代码 |

---

## 六、基础设施

| 组件 | 技术栈 | 状态 |
|------|--------|------|
| Web 服务器 | FastAPI + Uvicorn | 端口 8001 |
| 数据库 | MySQL (SQLAlchemy) / SQLite | MySQL 可选 |
| 缓存 | Redis (连接池) | 可选 |
| 向量存储 | ChromaDB | 用于记忆系统 |
| LLM | 智谱 GLM (zhipuai) | 需 ZHIPU_API_KEY |
| LLM 备选 | DeepSeek | 可选 |
| 免费 LLM | NVIDIA / OpenRouter / Groq | 可选 |
| 前端模板 | 7 个 HTML 页面 | index/chat/coze/monitor/workflow |

---

## 七、认证与安全

- 沙盒执行器: 限制危险模块、超时30s、内存256MB
- 权限服务: 文件读写/代码执行/网络访问分级审批
- 安全检查: eval/exec/__import__ 等危险函数禁用
- 用户认证: JWT + 密码哈希 (bcrypt)

---

## 八、测试状态

```
总计: 165 个测试
通过: 149 (90.3%)
失败: 14  (8.5%)
跳过: 2   (1.2%)
```

### 通过的关键测试

- 微博/知乎/B站/GitHub 爬虫 E2E ✅
- MCP 客户端管理器 ✅
- MCP 连接器处理器 ✅
- 核心质量模块 (向量记忆/任务队列/错误处理) ✅
- 所有技能处理器 (8/8) ✅
- 人物角色技能 (6/6) ✅
- CLI 命令系统 ✅

---

## 九、环境变量

```env
# 必填
ZHIPU_API_KEY=你的智谱 API 密钥   # LLM 聊天/代码生成/反思

# 可选
DEEPSEEK_API_KEY=                # LLM 备选
NVIDIA_API_KEY=                  # 免费 LLM
REDIS_HOST=localhost             # 缓存
DB_HOST=localhost                # 数据库
PORT=8001                        # 服务端口
```

## 十、快速入门

```bash
# 1. 配置 API 密钥
cp .env.example .env
# 编辑 .env，填入 ZHIPU_API_KEY

# 2. 启动 CLI
python cli.py

# 3. 或启动 API 服务
python main.py
# 访问 http://localhost:8001/chat

# 4. 深度模式
# 在 CLI 中输入 /chat deep
```

---

*文档自动生成于 2026-05-16*
