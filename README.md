<div align="center">

<h1>🦐 小雷版小龙虾 AI Agent</h1>

<p>
  <a href="https://github.com/xiaolei-liaoning/xiaolei-agent/actions"><img src="https://img.shields.io/github/actions/workflow/status/xiaolei-liaoning/xiaolei-agent/ci-cd.yml?style=for-the-badge" alt="CI/CD"></a>
  <a href="https://github.com/xiaolei-liaoning/xiaolei-agent/blob/main/LICENSE"><img src="https://img.shields.io/github/license/xiaolei-liaoning/xiaolei-agent?style=for-the-badge" alt="License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge" alt="Python Version"></a>
</p>

<p>
  <strong>工业级 AI 智能助手系统 | 双架构设计 | 智能降级 | 安全沙盒</strong>
</p>

</div>

---

## 🌟 项目概述

> **小雷版小龙虾** 是面向生产环境的 AI Agent 框架，核心设计理念：**工具优先、智能降级、安全执行**

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

项目实现了两套互补的多 Agent 架构，根据任务复杂度**自动选择**：

#### **模式一：V1 队长-队员模式**

```
┌─────────────────────────────────────────────────────────────┐
│                    V1LeaderPool                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  create_team() → 1 Leader + 最多 5 Workers          │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                 │
│        ┌─────────────────┼─────────────────┐               │
│        ▼                 ▼                 ▼               │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │ Leader   │    │ Worker1  │    │ Worker2  │             │
│  │ Agent    │    │ LLMAgent │    │ LLMAgent │  ...        │
│  └────┬─────┘    └──────────┘    └──────────┘             │
│       │                                                    │
│       ▼                                                    │
│  ┌─────────────────────────────────────────────────┐       │
│  │ supervise_task() 主循环:                        │       │
│  │   ① _decompose_task() → 任务分解               │       │
│  │   ② _assign()        → round-robin 分配        │       │
│  │   ③ _execute_batch() → asyncio.gather 并行      │       │
│  │   ④ _analyze_results() → LLM 分析决策          │       │
│  │   循环：complete / retry / reassign             │       │
│  └─────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

**架构特点**：
- 中央协调型：1个LeaderAgent统筹任务分解、分配、分析决策
- 分批次执行：LLM分解 → round-robin分配 → 并行执行 → LLM分析 → 循环/完成
- 决策三选一：complete（完成）/ retry（重试失败子任务）/ reassign（唤醒更多Worker）
- 每个LLMAgent内置 **KEPA反思闭环** + **RAG检索增强** + **反问机制** + **ContextMemory**

---

#### **模式二：V2 智能协作型**

```
┌─────────────────────────────────────────────────────────────┐
│              IntelligentScheduler (核心大脑)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │Analyzer  │→│Selector  │→│Planner   │→│Matcher   │     │
│  │          │ │          │ │          │ │          │     │
│  │ 分析任务 │ │选择策略   │ │执行规划   │ │能力匹配   │     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
│                          │                                 │
│                          ▼                                 │
│              ┌─────────────────────┐                       │
│              │   5种协作策略       │                       │
│              │  ┌───────────────┐  │                       │
│              │  │Pipeline/Master│  │                       │
│              │  │Slave/Review/  │  │                       │
│              │  │Auction/Hybrid │  │                       │
│              │  └───────────────┘  │                       │
│              └──────────┬──────────┘                       │
│                         │                                 │
│              ┌──────────▼──────────┐                       │
│              │   OnDemandAgentPool │                       │
│              │   按需创建WorkAgent │                       │
│              └──────────┬──────────┘                       │
│                         │                                 │
│        ┌────────────────┼────────────────┐                 │
│        ▼                ▼                ▼                 │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐           │
│  │WorkAgent │     │WorkAgent │     │WorkAgent │           │
│  │  think   │     │  think   │     │  think   │           │
│  │  → act   │     │  → act   │     │  → act   │           │
│  │  → reflect│     │  → reflect│     │  → reflect│           │
│  └──────────┘     └──────────┘     └──────────┘           │
└─────────────────────────────────────────────────────────────┘
```

**架构特点**：
- 无预注册Agent，按需动态创建
- **IntelligentScheduler** 6子模块流水线：
  - TaskAnalyzer → ModeSelector → ExecutionPlanner → CapabilityMatcher → 反问确认 → ResultAggregator
- **ModeSelector** 策略选择优先级：关键词匹配 > 历史经验 > LLM决策 > 启发式兜底
- **5种协作模式**：Pipeline / MasterSlave / Review / Auction / Hybrid
- **CircuitBreaker熔断保护**：5次失败→OPEN→60s→HALF_OPEN→CLOSED

---

## 🧠 核心组件

### 1. IntelligentScheduler - 智能调度器

```python
class IntelligentScheduler:
    def __init__(self):
        self.task_analyzer = TaskAnalyzer()
        self.mode_selector = ModeSelector()
        self.execution_planner = ExecutionPlanner()
        self.capability_matcher = CapabilityMatcher()
        self.result_aggregator = ResultAggregator()
    
    async def schedule(self, task):
        # ① 分析任务复杂度
        complexity = self.task_analyzer.estimate_complexity(task)
        
        # ② 选择协作模式
        mode = self.mode_selector.select(task, complexity)
        
        # ③ 制定执行计划
        plan = self.execution_planner.create_plan(task, mode)
        
        # ④ 匹配Agent能力
        agents = self.capability_matcher.match(plan)
        
        # ⑤ 反问确认
        await self._ask_user_confirmation(mode, agents)
        
        # ⑥ 执行并聚合结果
        result = await self.result_aggregator.aggregate(agents, plan)
        return result
```

### 2. WorkAgent - 工作智能体

每个WorkAgent具备完整的自治能力：

```python
class WorkAgent(BaseAgent):
    def __init__(self):
        self.mind = Mind(self)           # LLM驱动推理
        self.memory = MemorySystem(self)  # 短期/长期/情景记忆
        self.capabilities = []            # 5种专项能力
        self._bus = SharedBus()           # 通信总线
    
    async def run(self, task):
        # ① 能力适配
        await self.adapt_to_task(task)
        
        # ② 三阶段循环
        thought = await self.mind.think(task)
        result = await self.mind.act(thought.plan, thought.tool_calls)
        reflection = await self.mind.reflect(result)
        
        # ③ 记录工作历史
        self.memory.record_work_history(task, result, reflection)
        return result
```

### 3. SharedBus - 消息总线

实现**发布/订阅/直接消息**三种通信模式：

| 方法 | 功能 |
|------|------|
| `publish(topic, message)` | 发布消息到主题 |
| `subscribe(topic, callback)` | 订阅主题 |
| `send_direct(receiver, message)` | 点对点消息 |
| `update_context(key, value)` | 共享内存更新 |
| `get_context(key)` | 获取共享内存 |

### 4. CircuitBreaker - 熔断器

**故障处理机制**：

```
状态机: CLOSED → OPEN → HALF_OPEN → CLOSED
         ↓5次失败  ↓60秒超时   ↓成功
```

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

### 核心实现

工具调用流程：

```
用户请求 → ToolRegistry匹配 → 找到工具 → 调用MCP服务器 → 返回结果
                           ↓
                      无匹配工具 → 触发代码生成降级
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

### 执行引擎核心

```python
class EnhancedExecutor:
    def __init__(self):
        self.sandbox = SandboxEnvironment()
        self.resource_limiter = ResourceLimiter()
    
    async def execute(self, code, context):
        # ① 代码审查
        await self._validate_code(code)
        
        # ② 设置资源限制
        limits = ResourceLimits(
            timeout=30,
            max_memory_mb=512,
            allowed_paths=[self.workspace_path]
        )
        
        # ③ 安全执行
        result = await self.sandbox.run(
            code=code,
            context=context,
            limits=limits
        )
        
        # ④ 返回结果
        return {"success": result.success, "output": result.output}
```

---

## 📊 架构对比

| 维度 | V1 队长-队员模式 | V2 智能协作型 |
|------|------------------|--------------|
| **架构模式** | 中央协调型 | 分布式协作型 |
| **Agent创建** | 预创建固定池 | 按需动态创建 |
| **协作策略** | 单一1+N模式 | 5种策略自动匹配 |
| **调度机制** | LeaderAgent.supervise_task() | IntelligentScheduler 6子模块 |
| **上下文管理** | 独立ContextMemory | GlobalContextCenter + MySQL持久化 |
| **容错机制** | LLM分析决策重试 | CircuitBreaker熔断保护 |
| **通信方式** | 队长→Worker单向 | SharedBus消息总线 |
| **适用场景** | 单一复杂任务 | 批量标准化任务 |

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

### 添加新协作策略

```python
# 在 core/multi_agent_v2/orchestration/collaboration/strategies/
class MyStrategy(CollaborationStrategy):
    def __init__(self):
        self.name = "my_strategy"
    
    async def execute(self, task, agents):
        # 实现策略逻辑
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
