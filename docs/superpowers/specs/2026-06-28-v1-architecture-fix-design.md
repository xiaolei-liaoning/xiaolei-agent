# V1 架构修复设计 — MCP / Skill / 内置工具

- **日期**: 2026-06-28
- **状态**: 待审查
- **影响范围**: V1 架构（`core/agent_system.py` + 新增 `core/agent_v1_tools/`）
- **核心约束**: V2 架构（`core/multi_agent_v2/`）零影响

---

## 1. 目标与范围

### 1.1 要解决的问题

| 维度 | 问题 | 现状 |
|------|------|------|
| 耦合 | V1 依赖 V2 ToolRegistry | `V1LeaderPool._ensure_tool_registry()` 引用 `core.multi_agent_v2.tools.tool_registry` |
| 耦合 | V1 依赖 V2 MCP client | `LLMAgent._execute_tool()` 间接通过 V2 ToolRegistry 调用 MCP |
| 能力 | V1 缺少参数校验 | Worker/Leader 直接传参给工具，无 schema 校验 |
| 能力 | V1 Skill 路由简陋 | `V1SkillRouter` 只做了 `SkillSystem.match()` 单层，无 LLM 兜底 |
| Bug  | 8 个已知缺陷 | KEPA/JSON/截断/重试/校验等（详见 §6） |
| 限制 | Worker 3 轮不足 | 工具调用 + 结果分析 + 报告生成共需更多轮次 |

### 1.2 不涉及的范围

- 记忆系统（`core/memory/`、`share_memory()`、SharedBus）— 保持现状
- V2 架构（`core/multi_agent_v2/`）— 零修改
- `core/mcp/mcp_client.py` — 保持现状，V2 继续使用

---

## 2. 新增目录结构

```
core/agent_v1_tools/              # 【新目录】V1 独立工具基础设施
├── __init__.py
├── v1_tool_registry.py           # V1 自有工具注册表（含参数校验）
└── v1_mcp_adapter.py             # V1 MCP 适配层（封装 core/mcp/mcp_client.py）
```

设计原则：每个文件一个职责，只依赖 Python 标准库和 `core/mcp/mcp_client.py`（Adapter 引用），不依赖 `core/multi_agent_v2/` 任何模块。

---

## 3. V1ToolRegistry — 独立工具注册表

### 3.1 职责

- 注册 11 个内置工具 handler
- 通过 `v1_mcp_adapter.py` 代理 MCP 工具
- 提供参数校验（JSON Schema）
- 提供工具列表（供 LLM 函数调用使用）

### 3.2 内置工具

表与 V2 `_SANDBOX_TOOL_DEFS` 相同，但 handler 引用 V1 自己的实现：

| 工具名 | handler | 说明 |
|--------|---------|------|
| `write_file` | `_handle_write_file` | 写入文件（含路径安全校验） |
| `read_file` | `_handle_read_file` | 读取文件/目录 |
| `edit_file` | `_handle_edit_file` | 精确字符串替换 |
| `search_files` | `_handle_search_files` | Glob 文件名 + 正则内容搜索 |
| `execute_python` | `_handle_execute_python` | 执行 Python 代码 |
| `execute_shell` | `_handle_execute_shell` | 执行 Shell 命令 |
| `git` | `_handle_git` | Git 操作 |
| `fetch_url` | `_handle_fetch_url` | HTTP GET 请求 |
| `web_search` | `_handle_search` | 多引擎搜索 |
| `text_analyzer` | `_handle_text_analyzer` | LLM 文本分析 |
| `write_todos` | `_handle_write_todos` | 任务跟踪 |

### 3.3 关键 API

```python
class V1ToolRegistry:
    async def discover_all(self) -> list[ToolDefinition]
        # 1. 注册内置工具
        # 2. 通过 V1MCPAdapter 发现 MCP 工具
        # 返回全量工具列表

    async def get_tools_for_task(self, task, max_tools=20, allowed=None, disallowed=None) -> list[ToolDefinition]
        # 按 allowed/disallowed 过滤

    def get_handler(self, name) -> Callable | None
        # 内置 → 返回内建 handler
        # MCP → 返回 V1MCPAdapter 闭包

    def validate_arguments(self, name, args) -> tuple[bool, str]
        # JSON Schema 校验，参照 V2 validate_arguments()
```

### 3.4 与 V2 ToolRegistry 的区别

- 无 `register_scoped()`（V1 无 orchestrator，不需要）
- 无 `_ScopedRegistry` 类
- 无 `_written_file_registry` / `_file_read_cache`（V1 自身的缓存走 v1_cache）
- MCP 工具名统一 `mcp_` 前缀，无 server 名混淆
- 更简单的 `discover_all()` — 不需要超时取消时的孤儿清理（V1 同步启动）

---

## 4. V1MCPAdapter — MCP 适配层

### 4.1 设计思路

不 fork `core/mcp/mcp_client.py`（留给 V2），而是创建适配层封装它。

V1 特有的策略（重试次数、超时、权限检查）在适配层实现，核心 JSON-RPC 通信委托给共享的 `MCPClientManager`。

### 4.2 关键 API

```python
class V1MCPAdapter:
    def __init__(self):
        self._client = mcp_client  # 引用 core/mcp/mcp_client.py 的全局单例

    async def discover_servers(self) -> list[str]
        # 从 mcp/ 目录 + .mcp.json 发现所有服务器
        # 调用 self._client.connect_server() 注册配置

    async def list_tools(self, server: str) -> list[dict]
        # 委托 self._client.list_tools(server)

    async def call_tool(self, server: str, tool: str, args: dict) -> str
        # 1. V1 权限检查（v1_safety）
        # 2. 委托 self._client.call_tool(server, tool, args)
        # 3. 结果格式化
```

### 4.3 V1 特有的策略

- **重试**: 2 次 + 指数退避（V1 自己的 v1_recovery 管理）
- **超时**: 30s 通用 + 特定工具覆盖（web_search=45s）
- **安全**: 调用前经过 v1_safety 权限检查

### 4.4 MCP 配置来源

| 来源 | 格式 | 服务器数 |
|------|------|----------|
| `mcp/*_mcp_server.py` | `python3 mcp/<name>.py` | 22 个本地 |
| `.mcp.json` | `{mcpServers: {name: {command, args}}}` | 7 个外部 |

---

## 5. V1SkillRouter 增强

### 5.1 现有实现

```python
class V1SkillRouter:
    async def match(self, task: str) -> str:
        return SkillSystem().match(task).skill_id or "general"
```

### 5.2 增强方案

保留对 `core/skills/base_skills.py` 中 `SkillSystem` 的引用（该模块不属于 V2），增加两层兜底：

```python
class V1SkillRouter:
    async def match(self, task: str) -> str:
        # 第1层: @skill 确定性路由
        if re.match(r"@(\w+)\s", task):
            return extracted_skill

        # 第2层: SkillSystem 三层匹配（现有逻辑）
        result = await SkillSystem().match(task)
        if result.skill_id != "general":
            return result.skill_id

        # 第3层: LLM 意图分类兜底（仅在第2层返回 "general" 时触发）
        if llm_available:
            llm_skill = await self._llm_classify(task)
            if llm_skill and confidence >= 0.6:
                return llm_skill

        # 第4层: 回退到 general
        return "general"
```

### 5.3 与 V2 SkillDispatcher 的区别

- V2 有 6 层降级（@格式→LLM→萃取→多步→否定→关键词）
- V1 只加 2 层（@格式→SkillSystem→LLM→general），不做多步/否定/关键词
- V1 不引入 `config/skill_keywords.yaml`（仍然使用 `agents.yml` + `SkillSystem`）

---

## 6. Bug 修复清单

在 `core/agent_system.py` 原地修复，不新增文件：

| # | 优先级 | 位置 | 问题 | 修复 |
|---|--------|------|------|------|
| 1 | 🔴 中 | `LLMAgent._kepa_reflect()` | `decision=="continue"` 优先于 `confidence>=0.85` 检查，低置信度也能退出 | 交换条件顺序：先判 `confidence >= 0.85`，再判 `decision` |
| 2 | 🟠 中 | `LeaderAgent._execute_batch()` | JSON 解析失败时被设为 `is_ok=True`，静默掩盖错误 | 改为 `is_ok=False`，保留原始 result+error |
| 3 | 🟡 低 | `LeaderAgent.supervise_task()` | `_activate_worker()` 定义但从未被调用 | 在 `_analyze_results` 返回 `reassign` 时调用 |
| 4 | 🟡 低 | `LeaderAgent._analyze_results()` | 截断结果到 200 字符，分析信息不足 | 截断从 200 改为 500 字符 |
| 5 | 🟡 低 | `_llm_json()` 模块函数 | JSON 解析失败后直接返回 `{}`，无重试 | 加 1 次重试（与 V2 对齐），注入错误提示 |
| 6 | 🟢 建议 | `LeaderAgent._decompose_task()` | 无子任务格式校验 | 加 `isinstance(s, str)` 过滤非字符串元素 |
| 7 | 🟢 建议 | `LeaderAgent._execute_batch()` | 异常结果 schema 与正常结果不统一 | 统一为 `{success, result, worker, error}` 格式 |
| 8 | 🟡 低 | `LLMAgent._handle_message()` | `max_react_rounds=3` 不够 | 改为 8（Worker 内循环轮次） |

> 注：原 v1-fix-plan.md 中的 bug #3（share_memory V2 依赖）已讨论确定不处理，因为记忆系统不在本次范围。

---

## 7. 轮次调整

| Agent | 当前值 | 调整后 | 配置方式 |
|-------|--------|--------|----------|
| Leader supervise_task | 默认 5 / Web 传入 3 | 默认 **10** | `AGENT_MAX_ROUNDS` 环境变量 |
| Worker _handle_message | 硬编码 3 | **8** | 常量 `_WORKER_MAX_ROUNDS = 8` |

---

## 8. 风险与缓解

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| V1ToolRegistry handler 与 V2 行为不一致 | 工具返回格式不同 | 低 | 从 V2 fork 时保留核心逻辑，只改 import/依赖 |
| V1MCPAdapter 与 `core/mcp/mcp_client.py` 版本不兼容 | MCP 调用失败 | 低 | Adapter 只封装公开 API，不依赖内部细节 |
| Bug 修复 #1 改变 KEPA 行为 | Worker 判定变严格 | 低 | 只改条件顺序（confidence 优先），不改阈值 |
| Worker 轮次提升到 8 轮 | 上下文超预算 | 中 | Leader 总轮次受限（默认 10），且 Worker 结果会被截断 |

---

## 9. 测试策略

- **新增测试**: `tests/test_v1_tool_registry.py` — V1ToolRegistry 的 11 个工具 + MCP 发现
- **新增测试**: `tests/test_v1_mcp_adapter.py` — V1MCPAdapter 连接/列表/调用
- **新增测试**: `tests/test_v1_skill_router.py` — 增强后 V1SkillRouter 匹配
- **已有测试**: `tests/test_v1_agent_system.py` — 更新以确保仍通过
- **已有测试**: `tests/test_v1_e2e_integration.py` — 更新以确保仍通过
- **V2 测试**: `tests/v2/` 全部 — 确认不受影响
