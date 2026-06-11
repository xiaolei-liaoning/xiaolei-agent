# 架构统一方案：Web端 + CLI 统一到 V2 ReActCore

## 现状分析（CodeGraph 验证）

### 实际路由图

```
Web/API (api/routes/chat.py)
  ├─ force_multi_agent? → _handle_with_multi_agent() → task_processor.process()  [V1 已移除，降级]
  ├─ _needs_mcp_tools? → _handle_with_agency_agent() → agency_agent.run_agent()
  ├─ _needs_agent? → _handle_with_agent() → task_processor.process()
  └─ else → _handle_direct() → SkillDispatcher

CLI (cli/enhanced_cli.py)
  ├─ natural language → handle_smart_request() → WorkAgent() → run_react()  [V2 MiddlewareChain]
  ├─ /commands → handle_command() type dispatch
  ├─ /orchestrate → JS Workflow Bridge
  └─ /smart → handle_smart() → WorkAgent.execute()
```

### V1 代码真实死亡状态（CodeGraph 追踪验证）

| 文件 | 状态 | 证据 |
|------|------|------|
| `core/agent_system.py` (556行) | 🔴 完全死亡 | **零引用** — grep 不到任何 `from core.agent_system import` |
| `core/agent_coordinator.py` | 🔴 死，导入即崩 | 模块级 `raise ImportError`，被 `main.py` try/except 兜住 |
| `core/agents/smart_multi_agent.py` | 🔴 死存根 | 仅在 `cli/smart_agent.py` 的 never-fire except 块中 |
| `core/agents/agent_communication.py` | 🟡 半活 | `CommunicationCenter` = 死；`QuestionRegistry` = 活 |
| `core/agents/intelligent_agent_selector.py` | 🟢 活 | `chat.py` 在用 |

### 核心问题

1. **Web 走了老路但没走 V1** — `_handle_with_multi_agent` 内部早就是"已移除"的 fallback。Web 实际走的是 `task_processor.process()`（规则路由）或 `agency_agent.run_agent()`（MCP工具）
2. **CLI 走了 V2 新路** — `WorkAgent` + `MiddlewareChain 10 层`
3. **两边能力不对等** — CLI 有循环检测、权限控制、KEPA、Reflection，Web 没有
4. **~700 行 V1 死代码未清理**

---

## 方案：分 3 阶段 + 风险控制

### 阶段一：死代码删除 + 引用修复（低风险，~30 分钟）

**目标：** 清理 V1 遗留死代码，减少认知负担

**删除文件：**
- `core/agent_system.py`（556 行 V1 LeaderAgent/LLMAgent/V1LeaderPool）
- `core/agent_coordinator.py`（248 行，导入即崩）
- `core/agents/smart_multi_agent.py`（664 字节，死存根）

**修复引用：**
- `cli/smart_agent.py:24` — 移除死 except 块中的导入
- `core/infrastructure/service_registry.py:186-192` — 移除 `create_agent_coordinator` 工厂
- `main.py:138` — 移除 `agent_coordinator` 的 try/except 启动块

**测试方法：**
1. `python -c "from core.handlers import *"` — 确保各 handler 能正常导入
2. `python -c "from cli.smart_agent import SmartAgentCLI; s = SmartAgentCLI()"` — SmartAgentCLI 正常初始化
3. `python main.py` — 正常启动到端口 8001
4. `python cli.py /status` — CLI 正常

---

### 阶段二：Web 切换到 V2 WorkAgent 路径（中风险，~4 小时）

**目标：** 让 Web API 的"复杂任务"路径走 CLI 同等的 V2 MiddlewareChain

**修改 `api/routes/chat.py`：**

1. 删 `_handle_with_multi_agent()` 整个函数（内部已死）
2. `_handle_with_agent()` 中，将 `task_processor.process(message)` 替换为：

```python
from core.multi_agent_v2.agents.base.work_agent import WorkAgent

agent = WorkAgent()
task = {
    "id": str(uuid.uuid4())[:8],
    "description": message,
    "max_rounds": 10,
    "user_id": request.user_id,
}
result = await agent.execute(task)
reply_text = result.output if result.output else ""
```

3. `_needs_multi_agent()` 改为调用 V2 WorkAgent（或直接删除该分支）

**关键决策点：** `_handle_with_agency_agent` 是否保留？
- **保留**：它处理文件操作/MCP 工具场景，与 WorkAgent 的通用场景不重叠
- 但可以将它改为走 WorkAgent + 特定工具白名单

**风险控制：**
- 加 `try/except` 兜底，失败降级到原 `task_processor.process()`
- 加 feature flag `USE_V2_AGENT = True/False`，默认 False，逐步放量
- 增加超时 30 秒兜底

**测试方法：**
1. `python cli.py` → 发一条自然语言 → 走 WorkAgent V2（验证原有路径不受影响）
2. `curl -X POST http://localhost:8001/chat` → 复杂任务 → 返回结果（验证 Web 新路径）
3. `curl -X POST http://localhost:8001/chat` → 简单"你好" → 走 `_handle_direct`（验证未受影响）
4. `curl -X POST http://localhost:8001/chat` → 文件操作 → 走 `_handle_with_agency_agent`（验证未受影响）

---

### 阶段三：Web 和 CLI 共享 V2 基础设施（中风险，~6 小时）

**目标：** Web 和 CLI 完全共享 V2 基础设施，消除代码重复

**具体修改：**

1. 新建 `core/multi_agent_v2/agents/api_adapter.py` — Web API 用的适配器：

```python
class WebAgentAdapter:
    """Web API → V2 WorkAgent 的适配器"""
    
    def __init__(self):
        self.agent = None
    
    async def process(
        self,
        message: str,
        user_id: int = 1,
        max_rounds: int = 10,
        allowed_tools: Optional[List[str]] = None,
    ) -> str:
        from .work_agent import WorkAgent
        self.agent = WorkAgent()
        task = {
            "id": str(uuid.uuid4())[:8],
            "description": message,
            "max_rounds": max_rounds,
            "user_id": user_id,
        }
        if allowed_tools:
            task["allowed_tools"] = allowed_tools
        
        result = await self.agent.execute(task)
        return result.output if result.output else str(result)
```

2. `api/routes/chat.py` 中的 `_handle_with_agent` 改用 `WebAgentAdapter`

3. 删除 `core/tasks/task_processor.py` 或标记为 deprecated（如仍有引用）

**风险控制：**
- 与阶段二相同：try/except 兜底 + feature flag
- 首次部署用 50% 流量灰度

**测试方法：**
1. 所有阶段二的测试
2. `python -m pytest tests/test_chat_routes.py` — API 路由测试（如果有）
3. 手动测试 Web 端全流程：简单对话 → 复杂分析 → 文件操作

---

## 执行顺序与并行方案

```
阶段一（死代码清理）         → 单独执行，30 分钟
       ↓
阶段二（Web 切 V2）         → Workflow 多Agent并行：
                               Agent 1: chat.py 改造
                               Agent 2: 测试 + 验证
       ↓
阶段三（共享基础设施）       → Workflow 多Agent并行：
                               Agent 1: api_adapter.py 创建
                               Agent 2: chat.py 适配
                               Agent 3: 清理 task_processor
                               Agent 4: 端到端测试
```

## 总风险评估

| 阶段 | 风险 | 缓解措施 |
|------|------|----------|
| 一 | 低 — 死代码无引用 | grep 验证 + try/except 兜底 |
| 二 | 中 — Web 路径行为变化 | try/except 降级、feature flag、30s 超时 |
| 三 | 中 — task_processor 依赖未知 | 先标记 deprecated，跟踪日志 1 周后再删 |
