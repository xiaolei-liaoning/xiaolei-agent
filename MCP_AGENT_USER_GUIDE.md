# MCPAgent 用户操作指南

## 📖 概述

MCPAgent 是一个专门处理 MCP（Model Context Protocol）的智能 Agent，让您可以轻松连接和调用各种 MCP 工具。

## 🚀 快速开始

### 方式 1：交互式 CLI

```bash
# 进入项目目录
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent

# 启动交互式界面
python -m core.cli
```

### 方式 2：Python 代码调用

```python
from core.multi_agent_v2.agents.expert.mcp_agent import MCPAgent, get_mcp_agent

# 创建 Agent（方式1）
agent = MCPAgent(name="我的 MCP 助手")

# 或使用单例（方式2）
agent = get_mcp_agent()
```

---

## 📱 使用方式

### 方式 1：动态属性访问（最优雅）

```python
# 调用计算器工具
result = await agent.calculator.add(a=10, b=20)
print(result)  # 输出: {'success': True, 'result': 30}

# 获取天气
weather = await agent.weather.get_weather(city="北京")

# 列出文件
files = await agent.file_ops.list_files(path=".")
```

### 方式 2：call() 方法（最简单）

```python
result = await agent.call('calculator', 'add', a=10, b=20)
result = await agent.call('weather', 'get_weather', city="上海")
```

### 方式 3：快捷方法

```python
# 快捷计算器
result = await agent.quick_calc("25 * 4 + 10")

# 快捷天气
weather = await agent.quick_weather("广州")
```

---

## 🔧 可用工具

### 计算器 (calculator)
```python
await agent.calculator.add(a=1, b=2)      # 加法
await agent.calculator.subtract(a=5, b=3) # 减法
await agent.calculator.multiply(a=4, b=5) # 乘法
await agent.calculator.divide(a=10, b=2)  # 除法
await agent.calculator.calculate(expression="(1+2)*3") # 表达式计算
```

### 天气 (weather)
```python
await agent.weather.get_weather(city="北京")     # 获取天气
await agent.weather.get_forecast(city="上海")    # 获取天气预报
```

### 文件操作 (file_ops)
```python
await agent.file_ops.list_files(path=".")           # 列出文件
await agent.file_ops.read_file(path="test.txt")    # 读取文件
await agent.file_ops.write_file(path="test.txt", content="Hello") # 写入文件
```

### 文本处理 (text_processing)
```python
await agent.text_processing.summarize(text="长文本内容...")  # 摘要
await agent.text_processing.translate(text="Hello", target_lang="zh") # 翻译
await agent.text_processing.analyze_sentiment(text="我很开心") # 情感分析
```

### 趣味工具 (fun)
```python
await agent.fun.joke()           # 讲笑话
await agent.fun.quote()          # 名言警句
await agent.fun.ascii_art(text="Hi") # ASCII 艺术
```

---

## 📝 完整示例

```python
import asyncio
from core.multi_agent_v2.agents.expert.mcp_agent import MCPAgent

async def main():
    # 创建 Agent
    agent = MCPAgent(name="我的助手")
    
    # 使用计算器
    result = await agent.calculator.add(a=100, b=200)
    print(f"计算结果: {result}")
    
    # 获取天气
    weather = await agent.weather.get_weather(city="北京")
    print(f"北京天气: {weather}")
    
    # 使用快捷方法
    calc_result = await agent.quick_calc("(2+3)*4")
    print(f"快捷计算: {calc_result}")

asyncio.run(main())
```

---

## 🤝 多 Agent 协作

MCPAgent 可以与其他 Agent 协作完成复杂任务：

```python
from core.multi_agent_v2.agents.expert.mcp_agent import MCPAgent

agent = MCPAgent()

# 创建协作任务
task = {
    "target_agent": "analysis_agent",
    "data": {
        "type": "mcp_data",
        "content": await agent.call('calculator', 'add', a=10, b=20)
    }
}

# 发送协作请求
result = await agent.coordinate(task)
```

---

## ⚠️ 注意事项

1. **异步调用**：所有方法都需要使用 `await` 调用
2. **网络连接**：部分工具需要网络连接（如天气）
3. **服务器配置**：首次使用某些工具可能需要配置
4. **错误处理**：建议使用 try-except 包裹调用

---

## 📞 帮助

```python
# 获取可用服务器列表
servers = await agent.get_available_servers()
print(servers)

# 获取 Agent 信息
print(agent.agent_name)
print(agent.capabilities)
```

---

## 🎉 祝您使用愉快！

如有问题，请查看项目文档或联系开发团队。
