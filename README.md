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

## 🏗️ 架构设计深度解析

### 架构演进历程

```
V1 队长-队员模式 ──────────────────────────────────► V2 智能协作型
    │                                                     │
    │ 中央协调型                                          │ 分布式协作型
    │ 1 Leader + N Workers                                │ N 个平等 WorkAgent
    │ 单向监管                                            │ 双向通信
    │ 静态角色分配                                        │ 动态能力匹配
    │                                                        │
    └────────────────────────────────────────────────────────┘
                        演进方向
```

---

### 模式一：V1 队长-队员模式（中央协调型）

**架构定位**：适合单一复杂任务的分层监管场景

#### 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                    V1LeaderPool                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  create_team(worker_count=3, max_workers=5)        │   │
│  │  返回: (LeaderAgent, List[LLMAgent])               │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                 │
│        ┌─────────────────┼─────────────────┐               │
│        ▼                 ▼                 ▼               │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │ Leader   │    │ Worker1  │    │ Worker2  │  ...        │
│  │ Agent    │    │ LLMAgent │    │ LLMAgent │             │
│  └────┬─────┘    └──────────┘    └──────────┘             │
│       │                                                    │
│       ▼                                                    │
│  ┌─────────────────────────────────────────────────┐       │
│  │ 主循环 supervise_task():                        │       │
│  │   ① _decompose_task()  → LLM任务分解           │       │
│  │   ② _assign()          → round-robin分配       │       │
│  │   ③ _execute_batch()   → asyncio.gather并行    │       │
│  │   ④ _analyze_results() → LLM分析决策           │       │
│  │                                                 │       │
│  │   决策三选一: complete / retry / reassign      │       │
│  │   最多循环3轮                                   │       │
│  └─────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

#### LLMAgent 内部架构（KEPA + RAG + 反问 + 上下文）

```
每个 LLMAgent 具备完整的自治能力：

┌─────────────────────────────────────────────────┐
│              LLMAgent 内部                       │
├─────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐            │
│  │ _rag_query()│───►│ _llm_json() │            │
│  │  RAG检索    │    │  LLM调用    │            │
│  └─────────────┘    └──────┬──────┘            │
│                            │                    │
│                            ▼                    │
│  ┌─────────────┐    ┌─────────────┐            │
│  │ _kepa_reflect│◄───│ _ask_user()│            │
│  │  KEPA反思   │    │  反问用户   │            │
│  └──────┬──────┘    └─────────────┘            │
│         │                                       │
│         ▼                                       │
│  ┌─────────────┐                                │
│  │ContextMemory│  环形缓冲，最近20条记录         │
│  └─────────────┘                                │
└─────────────────────────────────────────────────┘

KEPA反思闭环流程：
  think → act → reflect → confidence≥0.85 → 退出
                           ↓
                    最多3次迭代
```

#### 设计特点

| 特性 | 实现方式 |
|------|----------|
| **任务分解** | LeaderAgent._decompose_task() 通过LLM将任务拆分为子任务列表 |
| **任务分配** | round-robin算法分配给活跃Worker |
| **并行执行** | asyncio.gather实现Workers并行执行 |
| **结果分析** | LeaderAgent._analyze_results() 通过LLM分析并决策 |
| **决策机制** | complete（完成）/ retry（重试）/ reassign（唤醒更多Worker） |
| **KEPA反思** | 置信度≥0.85退出，最多3次迭代 |
| **RAG增强** | RAGSearchEngine.search_and_learn() 检索知识库 |
| **反问降级** | LLM失败时通过QuestionRegistry向用户确认 |

---

### 模式二：V2 智能协作型（分布式协作型）

**架构定位**：适合批量标准化任务，支持多种协作策略自动切换

#### 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│           IntelligentScheduler (核心大脑)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │Analyzer  │→│Selector  │→│Planner   │→│Matcher   │     │
│  │ 分析任务 │ │选择策略   │ │执行规划   │ │能力匹配   │     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
│                          │                                 │
│                          ▼                                 │
│              ┌─────────────────────┐                       │
│              │   5种协作策略       │                       │
│              │  Pipeline/MasterSlave│                       │
│              │  /Review/Auction/   │                       │
│              │  Hybrid             │                       │
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
│  │ think→act│     │ think→act│     │ think→act│           │
│  │  →reflect│     │  →reflect│     │  →reflect│           │
│  └──────────┘     └──────────┘     └──────────┘           │
└─────────────────────────────────────────────────────────────┘
```

#### IntelligentScheduler 子模块架构

```
IntelligentScheduler 包含6个子模块，形成完整的调度流水线：

┌──────────────────────────────────────────────────────────────┐
│                    IntelligentScheduler                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  TaskAnalyzer        ModeSelector        ExecutionPlanner     │
│       │                    │                    │            │
│       ▼                    ▼                    ▼            │
│  analyze()           select()            create_plan()       │
│  understand()        优先级:             _create_pipeline   │
│  estimate_complexity()                      │               │
│       │              关键词>历史>LLM>启发式  ▼               │
│       │                                    CapabilityMatcher│
│       │                                         │           │
│       │                                         ▼           │
│       │                              ResultAggregator       │
│       │                                    aggregate()      │
│       │                                         │           │
│       └─────────────────────────────────────────┘           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

#### 5种协作策略

| 策略 | 适用场景 | 核心机制 |
|------|----------|----------|
| **Pipeline** | 流水线任务 | 按阶段顺序执行 + RecursiveTaskDecomposer |
| **MasterSlave** | 主从协作 | 主Agent分解 + 从Agent并行执行 + 主Agent聚合校验 |
| **Review** | 质量评审 | 多Agent并行工作 + Reviewer评审 + ConsensusMechanism |
| **Auction** | 任务竞标 | Agent竞标 → 中标执行 + DynamicTeamForming |
| **Hybrid** | 复杂任务 | 按复杂度分支选择：简单/主从/评审 |

#### WorkAgent 设计

```python
class WorkAgent(BaseAgent):
    def __init__(self):
        self.mind = Mind(self)           # LLM驱动推理
        self.memory = MemorySystem(self)  # 短期/长期/情景记忆
        self.capabilities = []            # 5种专项能力
        
    async def execute(task):
        # 动态适配：根据任务追加能力
        self.adapt_to_task(task)  # 追加 analysis/execution/review/research/integration
        
        # 三阶段循环
        thought = await self.mind.think(task)
        result = await self.mind.act(thought.plan, thought.tool_calls)
        reflection = await self.mind.reflect(result)
        
        # 记录工作历史（上限100条）
        self.memory.record_work_history(task, result, reflection)
```

---

## 🧠 核心组件深度解析

### 1. IntelligentScheduler - 智能调度器

**职责**：多Agent系统的核心大脑，负责任务理解、模式选择、Agent匹配、流程编排、动态调整、结果聚合

**核心流程**（schedule方法）：

```python
async def schedule(task):
    # ① 任务理解
    task_analysis = self.analyzer.analyze(task)
    
    # ② 模式选择（优先级：关键词 > 历史经验 > LLM > 启发式）
    collaboration_mode = await self.mode_selector.select(
        task, task_analysis,
        collaboration_history=self.collaboration_history  # 跨次学习
    )
    
    # ③ 按需创建Agent
    agent_count = self._estimate_agent_count(collaboration_mode, task)
    available_agents = await self.agent_pool.create_agents(task, agent_count)
    
    # ④ 创建任务上下文
    await self.context_center.create_task_context(...)
    
    # ⑤ Agent匹配 + 执行计划
    execution_plan = await self.planner.create_plan(...)
    
    # ⑥ 反问确认（可选）
    user_confirmed = await self._ask_user_confirmation(...)
    
    # ⑦ 更新任务状态 + 发布到SharedBus + 持久化快照
    ...
```

### 2. SharedBus - 消息总线

**三种通信模式**：

| 模式 | 方法 | 用途 |
|------|------|------|
| **发布/订阅** | `publish(topic, message)` / `subscribe(topic, callback)` | 广播消息、事件通知 |
| **点对点** | `send_direct(receiver, message)` | Agent间直接通信 |
| **共享内存** | `update_context(key, value)` / `get_context(key)` | 全局状态共享 |

### 3. CircuitBreaker - 熔断器

**状态机设计**：

```
         ┌─────────────────────────────────────────────┐
         │                                             │
         ▼                                             │
┌────────────────┐        ┌────────────────┐        ┌────────────────┐
│   CLOSED       │        │    OPEN        │        │   HALF_OPEN    │
│  正常执行      │        │  故障熔断      │        │  试探恢复      │
└───────┬────────┘        └───────┬────────┘        └───────┬────────┘
        │                         │                         │
        │ 5次失败                 │ 60秒超时                │ 成功
        ▼                         ▼                         ▼
┌────────────────────────────────────────────────────────────────────┐
│                         record_failure()                          │
│                         record_success()                          │
│                         can_execute()                             │
└────────────────────────────────────────────────────────────────────┘
```

### 4. KEPA 反思闭环

**V2增强版反思机制**（AdaptivePipelineWithReflection）：

```
执行步骤 → 触发反思条件 → LLM评估 → 决策执行 → 动态调整

反思决策类型：
├── CONTINUE    → 继续执行下一阶段
├── SKIP_NEXT   → 跳过下一个步骤
├── ADD_STEPS   → 添加新步骤
├── RETRY       → 重试当前步骤
└── FAIL        → 标记任务失败
```

---

## 🔌 MCP 系统深度解析

### 调用协议

MCP（Model Context Protocol）是标准化的工具调用协议：

```python
# 工具发现
tools = await registry.discover_all()  # 扫描 mcp/*_mcp_server.py

# 调用工具
result = await agent.call_tool(
    tool_name="search.web",
    arguments={"query": "人工智能"},
    server_name="the-agency"
)
```

### 动态发现机制

```python
# 缓存结构: {tool_name_lower: (server_name, script_path, description)}
cache = {
    "analyze_csv": ("data-analysis", "data_analysis_mcp_server.py", "..."),
    "search.web": ("the-agency", "agency_mcp_server.py", "...")
}
```

### 工具调用流程

```
用户请求 → ToolRegistry匹配 → 找到工具 → 调用MCP服务器 → 返回结果
                           ↓
                      无匹配工具 → 触发代码生成降级
```

---

## 📦 代码沙盒深度解析

### 安全隔离架构

```
┌─────────────────────────────────────────────────────────────┐
│                    代码生成降级流程                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户请求                                                    │
│      ↓                                                      │
│  ToolRegistry 查找工具                                       │
│      ↓                                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 工具存在？                                           │   │
│  │   ├─ 是 → 执行工具 → 返回结果                        │   │
│  │   └─ 否 → LLM生成代码                               │   │
│  │             ↓                                       │   │
│  │        EnhancedExecutor                             │   │
│  │             ↓                                       │   │
│  │        ResourceLimits                               │   │
│  │   ┌────────────────────────────────────────────┐    │   │
│  │   │ timeout: 30s                              │    │   │
│  │   │ max_memory_mb: 512                        │    │   │
│  │   │ allowed_paths: [workspace_path]            │    │   │
│  │   │ forbidden_modules: [subprocess, socket...] │    │   │
│  │   └────────────────────────────────────────────┘    │   │
│  │             ↓                                       │   │
│  │        安全执行 → 返回结果                           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 降级触发条件

```python
def should_trigger_code_generation(task):
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

## 📊 V1 vs V2 架构深度对比

| 维度 | V1 队长-队员模式 | V2 智能协作型 |
|------|------------------|--------------|
| **架构模式** | 中央协调型（1 Leader + N Workers） | 分布式协作型（N 个平等 WorkAgent） |
| **Agent创建** | 预创建固定池：`V1LeaderPool.create_team()` | 按需动态创建：`OnDemandAgentPool.create_agents()` |
| **角色定义** | 固定角色：LEADER / WORKER | 无预设角色，通过 `adapt_to_task()` 动态追加能力 |
| **协作策略** | 单一1+N模式：分解→分配→并行→分析→循环 | 5种策略自动匹配：Pipeline/MasterSlave/Review/Auction/Hybrid |
| **调度机制** | LeaderAgent.supervise_task() 主循环 | IntelligentScheduler 6子模块流水线 |
| **决策机制** | complete/retry/reassign 三选一 | 5种反思决策 + 跨次学习 |
| **上下文管理** | 每个Agent独立ContextMemory（环形缓冲20条） | GlobalContextCenter + MySQL持久化 + SharedBus |
| **通信方式** | 队长→Worker单向 | SharedBus发布/订阅/点对点/共享内存 |
| **容错机制** | LLM分析决策重试 | CircuitBreaker熔断保护（5次失败→OPEN→60s→HALF_OPEN） |
| **跨次学习** | 无 | 协作模式成功率记录 + Agent能力动态更新 |
| **适用场景** | 单一复杂任务，需要分层监管 | 批量标准化任务，需要灵活协作 |

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

### 智能降级演示

```bash
/run "计算1到100之间所有能被3或5整除的数的和"
```

**执行过程**：
1. 系统发现无匹配工具
2. LLM 分析需求，生成 Python 代码
3. 代码在安全沙盒中执行（超时30s，内存512MB限制）
4. 返回结果：`2318`

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
