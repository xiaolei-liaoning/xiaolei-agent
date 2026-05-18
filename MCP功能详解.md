# MCP (Model Context Protocol) 实际功能详解

## 📋 MCP是什么？

MCP是一个标准化的协议，允许AI Agent通过JSON-RPC与外部服务通信。它提供了一种统一的方式来发现和调用各种工具和服务。

## 🎯 系统中的MCP服务器分类

### 【一、本地Python服务】(6个)
**特点**: 无需额外安装，开箱即用

#### 1. calculator - 计算器服务
- **工具**: add, subtract, multiply, divide, power, sqrt, random, percentage, average, sum
- **用途**: 数学计算、统计分析
- **示例**: `calculator.add(a=10, b=5)` → 15

#### 2. weather - 天气查询服务
- **工具**: get_weather, get_weather_forecast
- **用途**: 查询城市天气、天气预报
- **支持城市**: 北京、上海、广州、成都、杭州、深圳
- **示例**: `weather.get_weather(city="beijing")` → {温度: "25°C", 天气: "晴天"}

#### 3. fun - 趣味工具服务
- **工具**: 
  - get_joke - 获取笑话
  - get_riddle - 获取谜语
  - get_fun_fact - 获取趣味知识
  - get_ascii_art - ASCII艺术
  - get_horoscope - 星座运势
  - roll_dice - 掷骰子
  - magic_8ball - 魔法八球
- **用途**: 娱乐、游戏、随机内容

#### 4. joke - 笑话服务
- 与fun服务共用同一服务器

#### 5. text-processing - 文本处理服务
- **工具**: 文本格式化、转换、分析等
- **用途**: 文本操作和处理

#### 6. file-ops - 文件操作服务
- **工具**: 文件读写、目录管理、文件搜索等
- **用途**: 文件系统操作

### 【二、NPM包服务】(15个)
**特点**: 需要Node.js环境，功能强大

#### 数据库类
- **chroma**: 向量数据库操作
- **sqlite**: SQLite数据库管理
- **postgres**: PostgreSQL数据库操作

#### 浏览器自动化
- **playwright**: 网页自动化、截图、数据提取

#### 文件与存储
- **filesystem**: 文件系统操作（指定/tmp目录）

#### 开发工具
- **github**: GitHub API集成（仓库、PR、Issue管理）
- **gitlab**: GitLab API集成
- **sentry**: 错误追踪和监控

#### 搜索与信息
- **brave-search**: Brave搜索引擎
- **fetch**: HTTP请求和数据获取
- **tavily**: AI优化的搜索引擎

#### 通信工具
- **slack**: Slack消息发送和接收
- **discord**: Discord机器人集成

#### 其他实用工具
- **sequential-thinking**: 链式思维推理
- **e2b**: 云端沙盒执行环境

## 🔧 如何使用MCP？

### 方法1: CLI命令
```bash
/mcp list                              # 列出所有可用服务器
/mcp connect calculator                # 连接计算器服务
/mcp call calculator add {"a":10,"b":5}  # 调用工具
```

### 方法2: 智能Agent自动调用
```
用户: "帮我计算10加5"
→ Agent自动识别并调用calculator.add
→ 返回结果: 15
```

### 方法3: 工作流中使用
在 `/smart` 命令中，Agent可以组合多个MCP工具完成复杂任务

## 💡 实际应用示例

### 示例1: 数学计算
```
用户输入: "2+2等于多少"
→ 系统调用: calculator.add(a=2, b=2)
→ 返回结果: 4
```

### 示例2: 天气查询
```
用户输入: "今天北京天气怎么样"
→ 系统调用: weather.get_weather(city="beijing")
→ 返回: {温度: "25°C", 天气: "晴天", 湿度: "45%"}
```

### 示例3: 复合任务
```
用户输入: "查询北京天气并告诉我是否适合出门"
→ 步骤1: 调用weather.get_weather("beijing")
→ 步骤2: LLM分析天气数据
→ 步骤3: 给出建议
```

## ⚙️ 技术实现

- **协议**: JSON-RPC 2.0
- **通信方式**: stdin/stdout
- **进程管理**: subprocess.Popen
- **工具发现**: listTools RPC调用
- **工具调用**: tools/call RPC调用
- **生命周期**: 按需启动，手动停止

## 📊 当前状态

- **可用服务器总数**: 21个
  - 本地服务: 6个
  - NPM包: 15个
- **已连接服务器**: 按需连接

## 🎨 架构优势

1. **标准化**: 统一的JSON-RPC协议
2. **可扩展**: 轻松添加新的MCP服务器
3. **隔离性**: 每个服务独立进程运行
4. **灵活性**: 支持本地服务和远程服务
5. **自动化**: Agent可以智能选择和使用工具

## 🚀 未来扩展

可以轻松添加更多MCP服务器，例如：
- 社交媒体API（Twitter、微博）
- 云服务（AWS、Azure）
- AI服务（图像生成、语音合成）
- 企业工具（Jira、Confluence）
