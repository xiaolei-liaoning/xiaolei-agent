<div align="center">

<h1>🦐 小雷版小龙虾 AI Agent</h1>

<p>
  <a href="https://github.com/xiaolei-liaoning/xiaolei-agent/actions"><img src="https://img.shields.io/github/actions/workflow/status/xiaolei-liaoning/xiaolei-agent/ci-cd.yml?style=for-the-badge" alt="CI/CD"></a>
  <a href="https://github.com/xiaolei-liaoning/xiaolei-agent/blob/main/LICENSE"><img src="https://img.shields.io/github/license/xiaolei-liaoning/xiaolei-agent?style=for-the-badge" alt="License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge" alt="Python Version"></a>
</p>

<p>
  <strong>工业级 AI 智能助手系统 | 支持多 Agent 协作与智能降级</strong>
</p>

</div>

---

## 🌟 项目概述

> **小雷版小龙虾** 是一个面向生产环境的 AI Agent 框架，核心设计理念是 **"工具优先、智能降级、安全执行"**。

### 🎯 核心价值

| 维度 | 说明 |
|------|------|
| **架构创新** | 两套互补的多 Agent 架构，灵活应对不同场景 |
| **智能降级** | 无现成工具时自动生成代码解决问题 |
| **安全沙盒** | 隔离执行环境，严格资源限制 |
| **MCP 生态** | 标准化工具调用协议，易于扩展 |

---

## 🏗️ 架构设计

### 双架构模式

项目实现了两套互补的多 Agent 架构，根据任务复杂度自动选择：

#### **模式一：队长-队员模式** (V1)

```
┌─────────────────────────────────────────────────────────────┐
│                    TeamLeader                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  LLM分析 → 任务拆解 → 队员分配 → 结果聚合         │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                 │
│        ┌─────────────────┼─────────────────┐               │
│        ▼                 ▼                 ▼               │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │ TeamWorker│    │ TeamWorker│    │ TeamWorker│             │
│  │   Agent   │    │   Agent   │    │   Agent   │             │
│  └──────────┘    └──────────┘    └──────────┘             │
│        │                 │                 │               │
│        └─────────────────┴─────────────────┘               │
│                    TeamMessageCenter                       │
└─────────────────────────────────────────────────────────────┘
```

**特点**：层级式通信，队员只与队长交互，适合单一复杂任务。

#### **模式二：智能协作型** (V2)

```
┌─────────────────────────────────────────────────────────────┐
│              IntelligentScheduler                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │Analyzer  │→│Selector  │→│Matcher   │→│Planner   │     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
│                          │                                 │
│                          ▼                                 │
│              ┌─────────────────────┐                       │
│              │   SharedBus         │                       │
│              │  (消息总线)         │                       │
│              └─────────┬───────────┘                       │
│        ┌───────────────┼───────────────┐                   │
│        ▼               ▼               ▼                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │ WorkAgent│    │ WorkAgent│    │ WorkAgent│             │
│  │   (平等)  │    │   (平等)  │    │   (平等)  │             │
│  └──────────┘    └──────────┘    └──────────┘             │
│        │                 │                 │               │
│        └─────────────────┴─────────────────┘               │
│              GlobalContextCenter                           │
└─────────────────────────────────────────────────────────────┘
```

**特点**：平等协作，通过 SharedBus 自由通信，支持5种协作策略自动切换。

---

## 🧠 核心组件

### 1. BaseAgent - 智能体基类

每个 Agent 具备完整的自治能力：

```python
class BaseAgent:
    def __init__(self):
        self.mind = Mind(self)           # 思考引擎
        self.memory = MemorySystem(self)  # 记忆系统
        self.capabilities = [...]         # 能力集合
        self._bus = SharedBus()           # 通信总线
```

**设计亮点**：
- **独立心智**：每个 Agent 有独立的思考和决策能力
- **记忆系统**：支持短期/长期/情景记忆
- **主动通信**：可主动与其他 Agent 沟通协作

### 2. Mind - 思考引擎

```
思考流程：
用户输入 → 理解任务 → 制定计划 → 执行 → 检查结果 → 反思优化
     ↓          ↓           ↓        ↓         ↓          ↓
   LLM      LLM分析     LLM规划   工具/代码   LLM评估    LLM反思
```

**核心方法**：
- `think(task)` - LLM驱动的思考，最多重试3次
- `_think_with_llm(task)` - 调用LLM进行深度推理
- `reflect(result)` - 反思执行结果，优化下次决策

### 3. SharedBus - 消息总线

实现 **发布/订阅/直接消息** 三种通信模式：

```python
# 订阅主题
await bus.subscribe("agent:general", handler)

# 发布消息
await bus.publish("topic:task_completed", message)

# 直接消息
await bus.send_direct(target_agent_id, message)
```

### 4. CircuitBreaker - 熔断器

**故障处理机制**：
- **熔断状态**：关闭 → 半开 → 打开 → 自动恢复
- **触发条件**：连续失败次数阈值
- **恢复策略**：指数退避重试

---

## 🔌 MCP 系统

### 调用协议

MCP（Model Context Protocol）是标准化的工具调用协议：

```python
# 工具发现
tools = await registry.discover_all()

# 调用工具
result = await agent.call_tool(
    tool_name="search.web",
    arguments={"query": "人工智能"},
    server_name="the-agency"
)
```

### 工具定义格式

```json
{
  "name": "analyze_csv",
  "description": "分析CSV文件（自动查找最近导出的CSV）",
  "parameters": {
    "file_path": {"type": "string", "description": "CSV文件路径", "required": false},
    "analysis_type": {"type": "string", "description": "分析类型", "required": false}
  }
}
```

### 动态发现机制

系统启动时自动扫描 `mcp/*_mcp_server.py` 文件，建立工具缓存：

```python
# 缓存结构: {tool_name_lower: (server_name, script_path, description)}
cache = {
    "analyze_csv": ("data-analysis", "data_analysis_mcp_server.py", "..."),
    "search.web": ("the-agency", "agency_mcp_server.py", "...")
}
```

---

## 📦 代码沙盒

### 实现原理

**安全隔离架构**：

```
┌─────────────────────────────────────────────┐
│           代码生成降级流程                   │
├─────────────────────────────────────────────┤
│  用户请求                                   │
│      ↓                                     │
│  ToolRegistry 查找工具                      │
│      ↓                                     │
│  工具存在？                                 │
│    ├─ 是 → 执行工具 → 返回结果              │
│    └─ 否 → LLM生成代码                      │
│              ↓                             │
│         EnhancedExecutor                    │
│              ↓                             │
│         ResourceLimits                      │
│  ┌───────────────────────────────────────┐  │
│  │ timeout: 30s                         │  │
│  │ max_memory_mb: 512                   │  │
│  │ allowed_paths: [workspace_path]      │  │
│  │ forbidden_modules: [subprocess, ...] │  │
│  └───────────────────────────────────────┘  │
│              ↓                             │
│         安全执行 → 返回结果                  │
└─────────────────────────────────────────────┘
```

### 安全保障

| 机制 | 实现 |
|------|------|
| **超时控制** | 默认30秒，可配置 |
| **内存限制** | 默认512MB，防止内存泄漏 |
| **路径白名单** | 仅允许访问工作区目录 |
| **模块黑名单** | 禁止 subprocess、socket 等危险模块 |
| **代码审查** | 执行前检查危险操作 |

### 降级触发条件

```python
def should_trigger_code_generation(task):
    """判断是否触发代码生成降级"""
    # 1. 无匹配工具
    if not registry.has_tool_for_task(task):
        return True
    # 2. 工具执行失败
    if tool_execution_failed(task):
        return True
    # 3. LLM认为需要自定义处理
    if llm_judges_custom_code_needed(task):
        return True
    return False
```

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- GLM API Key（配置在 `.env`）

### 安装

```bash
git clone https://github.com/xiaolei-liaoning/xiaolei-agent.git
cd xiaolei-agent
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，配置 ZHIPU_API_KEY
```

### 运行

```bash
# 启动 CLI
python cli.py

# 启动 Web 服务 (Port 8001)
python main.py
```

---

## 💡 使用示例

### 基础命令

```bash
# 执行智能工作流
/run "帮我分析当前目录的文件结构"

# 进入聊天模式
/chat

# 切换思考模式（显示执行步骤）
/think
```

### MCP 工具调用

```bash
# 连接 MCP 服务器
/mcp connect the-agency

# 查看可用工具
/mcp tools

# 调用工具
/mcp quick joke
```

### 智能降级演示

当没有现成工具时，系统自动生成代码：

```bash
/run "计算1到100之间所有能被3或5整除的数的和"
```

**执行过程**：
1. 系统发现无匹配工具
2. LLM 分析需求，生成 Python 代码
3. 代码在安全沙盒中执行
4. 返回结果：`2318`

---

## 📊 架构对比

| 维度 | V1 队长-队员模式 | V2 智能协作型 |
|------|------------------|--------------|
| **通信方式** | 层级式（队长↔队员） | 总线式（平等通信） |
| **协作策略** | 1种（队长拆分+聚合） | 5种自动选择 |
| **决策中心** | TeamLeader（LLM） | IntelligentScheduler（规则+LLM） |
| **适用场景** | 单一复杂任务 | 批量标准化任务 |
| **容错机制** | LLM不可用回退单兵模式 | CircuitBreaker + 自动重试 |

---

## 🔧 扩展开发

### 添加新 MCP 工具

```python
# 在 mcp/ 目录创建 xxx_mcp_server.py
class MyMCPServer:
    def get_tools(self):
        return [{
            "name": "my_tool",
            "description": "我的工具",
            "parameters": {...}
        }]
    
    def call_tool(self, name, args):
        # 实现工具逻辑
        return {"success": True, "result": "..."}
```

### 添加新 Agent 能力

```python
# 在 core/multi_agent_v2/agents/ 目录添加
class MyCapability(Capability):
    def __init__(self):
        self.name = "my_capability"
        self.description = "我的能力"
    
    async def execute(self, task):
        # 实现能力逻辑
        return result
```

---

## 📝 许可证

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

<div align="center">

**Made with ❤️ by Xiaolei**

</div>
