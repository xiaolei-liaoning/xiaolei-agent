# 工具系统增强计划 — 对标 gemini-cli/opencode

> 基于工具系统对比分析，分 4 个阶段执行改进

## 核心差距

| 维度 | 当前 v2 | 目标（对标 gemini-cli/opencode） |
|------|---------|--------------------------------|
| 权限系统 | 无 | allow/deny/ask 三级规则引擎 |
| 命令安全 | 无 | Shell 命令注入检测 + 沙箱 |
| Hook 系统 | 无 | BeforeTool/AfterTool 拦截器 |
| 工具 Schema | 静态 dict | 模型感知动态 Schema |
| 编辑策略 | 单一替换 | 9 种模糊匹配策略 |

---

## 阶段一：P0 安全（影响最大）

### 1. 权限系统（PermissionService）
**文件**: `core/multi_agent_v2/tools/permission.py`（新建）

#### 功能设计
- **三级权限**: allow（自动执行）/ deny（禁止执行）/ ask（询问用户）
- **规则引擎**: 基于工具名、参数模式、路径匹配
- **配置来源**: YAML 文件 + 环境变量覆盖
- **默认策略**: 读操作 allow，写操作 ask，危险操作 deny

#### 规则格式
```yaml
permissions:
  # 读操作 - 自动允许
  allow:
    - pattern: "read:*"
    - pattern: "file:read"
    - pattern: "web_search:*"
    - pattern: "fetch_url:*"
  
  # 写操作 - 需要确认
  ask:
    - pattern: "file:write"
    - pattern: "execute_python:*"
    - pattern: "execute_shell:*"
    - pattern: "open_app:*"
  
  # 危险操作 - 禁止
  deny:
    - pattern: "execute_shell:rm -rf *"
    - pattern: "execute_python:import os; os.system(*)"
    - pattern: "file:write:/etc/*"
```

#### 核心类
```python
class PermissionService:
    """三级权限服务"""
    
    def __init__(self, config_path: str = None):
        self.rules = self._load_rules(config_path)
        self.cache = {}  # 权限缓存
    
    async def check(self, tool_name: str, arguments: dict) -> PermissionResult:
        """
        检查工具调用权限
        
        Returns:
            PermissionResult(allowed=True/False, reason="...", need_ask=True/False)
        """
        # 1. 检查缓存
        # 2. 按优先级匹配规则（deny > ask > allow）
        # 3. 返回结果
```

#### 集成点
- `react_core.py:ReActCoreMiddleware.on_tool_start()` — 工具执行前检查
- `middlewares.py` 新增 `PermissionMiddleware` — 中间件层拦截

### 2. Shell 命令注入检测
**文件**: `core/multi_agent_v2/tools/shell_guard.py`（新建）

#### 功能设计
- **危险命令检测**: rm -rf, chmod 777, curl|sh, wget|sh 等
- **路径边界检查**: 防止访问工作目录外的敏感路径
- **注入模式检测**: 检测命令拼接、变量注入、管道注入
- **沙箱模式**: 可选的 Docker/Podman 沙箱执行

#### 检测规则
```python
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/',           # 递归删除根目录
    r'chmod\s+777',            # 危险权限
    r'curl\s+.*\|\s*sh',       # 管道执行
    r'wget\s+.*\|\s*sh',       # 管道执行
    r'eval\s*\(',              # 动态执行
    r'exec\s*\(',              # 动态执行
    r'>\s*/etc/',              # 修改系统文件
    r'sudo\s+',                # 提权
]

SENSITIVE_PATHS = [
    '/etc/',
    '/usr/',
    '/var/',
    '~/.ssh/',
    '~/.aws/',
]
```

#### 核心类
```python
class ShellGuard:
    """Shell 命令安全卫士"""
    
    def __init__(self, sandbox_mode: bool = False):
        self.sandbox_mode = sandbox_mode
        self.dangerous_patterns = DANGEROUS_PATTERNS
        self.sensitive_paths = SENSITIVE_PATHS
    
    def scan(self, command: str) -> ScanResult:
        """
        扫描命令安全性
        
        Returns:
            ScanResult(safe=True/False, risks=[...], suggestions=[...])
        """
        # 1. 检测危险模式
        # 2. 检查路径边界
        # 3. 检测注入模式
        # 4. 返回扫描结果
```

#### 集成点
- `execute_shell` 和 `execute_command` 工具入口
- `PermissionMiddleware` 中调用

---

## 阶段二：P1 可观测性（提升调试体验）

### 3. BeforeTool/AfterTool Hook 系统
**文件**: `core/multi_agent_v2/tools/hooks.py`（新建）

#### 功能设计
- **Hook 类型**: BeforeTool（执行前）/ AfterTool（执行后）/ OnError（出错时）
- **Hook 注册**: 支持装饰器和配置两种方式
- **Hook 链**: 多个 Hook 按优先级执行
- **Hook 结果**: 可修改参数、跳过执行、终止流程

#### 核心类
```python
class ToolHookManager:
    """工具 Hook 管理器"""
    
    def __init__(self):
        self.before_hooks: List[BeforeToolHook] = []
        self.after_hooks: List[AfterToolHook] = []
        self.error_hooks: List[OnErrorHook] = []
    
    async def run_before(self, tool_name: str, arguments: dict) -> HookResult:
        """执行所有 BeforeTool Hook"""
        # 返回 HookResult(modify_args=True, skip=False, abort=False)
    
    async def run_after(self, tool_name: str, arguments: dict, result: Any) -> HookResult:
        """执行所有 AfterTool Hook"""
        # 返回 HookResult(modify_result=True)
    
    async def run_error(self, tool_name: str, arguments: dict, error: Exception) -> HookResult:
        """执行所有 OnError Hook"""
        # 返回 HookResult(retry=True/False)
```

#### 内置 Hook
```python
@before_tool
async def log_tool_call(tool_name: str, arguments: dict):
    """记录工具调用日志"""
    logger.info(f"Tool called: {tool_name}({arguments})")

@after_tool
async def cache_result(tool_name: str, arguments: dict, result: Any):
    """缓存工具结果"""
    cache.set(f"{tool_name}:{hash(arguments)}", result, ttl=3600)

@on_error
async def retry_on_timeout(tool_name: str, arguments: dict, error: TimeoutError):
    """超时重试"""
    if isinstance(error, TimeoutError):
        return HookResult(retry=True, max_retries=2)
```

#### 集成点
- `react_core.py:ReActCoreMiddleware._execute_tool()` — 工具执行前后调用
- `middleware.py` 新增 `HookMiddleware` — 中间件层管理

### 4. MCP 工具集成
**文件**: `core/multi_agent_v2/tools/mcp_client.py`（新建）

#### 功能设计
- **MCP 协议**: 支持 MCP 1.0 标准协议
- **工具发现**: 自动发现 MCP 服务器提供的工具
- **工具调用**: 透明调用 MCP 工具，无需修改上层代码
- **错误处理**: MCP 服务器超时、断连自动重连

#### 核心类
```python
class MCPClient:
    """MCP 客户端"""
    
    def __init__(self, server_configs: List[MCPConfig]):
        self.servers = {}
        self.tools = {}
    
    async def connect(self):
        """连接所有 MCP 服务器"""
    
    async def discover_tools(self) -> List[ToolDef]:
        """发现所有 MCP 工具"""
        # 返回标准 ToolDef 列表，与内置工具统一格式
    
    async def call_tool(self, server: str, tool: str, arguments: dict) -> Any:
        """调用 MCP 工具"""
        # 自动处理序列化、错误重试、超时控制
```

#### 配置格式
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"],
      "env": {}
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "xxx"}
    }
  }
}
```

#### 集成点
- `tool_registry.py` — 注册 MCP 工具
- `react_core.py:on_start()` — 启动时发现 MCP 工具

---

## 阶段三：P2 智能化（提升准确度）

### 5. 模型感知工具 Schema
**文件**: `core/multi_agent_v2/tools/schema.py`（新建）

#### 功能设计
- **模型族识别**: 检测当前使用的模型类型（GPT/Claude/Gemini/开源）
- **Schema 适配**: 根据模型特点调整工具描述和参数
- **Token 优化**: 为 token 窗口小的模型精简 Schema
- **能力感知**: 根据模型能力动态启用/禁用工具

#### 模型适配表
```python
MODEL_ADAPTERS = {
    "gpt-4": {
        "max_tools": 128,
        "supports_parallel": True,
        "schema_style": "openai",
    },
    "claude-3": {
        "max_tools": 128,
        "supports_parallel": True,
        "schema_style": "anthropic",
    },
    "gemini-pro": {
        "max_tools": 128,
        "supports_parallel": True,
        "schema_style": "gemini",
    },
    "qwen-turbo": {
        "max_tools": 32,
        "supports_parallel": False,
        "schema_style": "openai",
    },
}
```

#### 核心类
```python
class SchemaAdapter:
    """模型感知 Schema 适配器"""
    
    def __init__(self, model_name: str):
        self.model = model_name
        self.config = MODEL_ADAPTERS.get(model_name, DEFAULT_CONFIG)
    
    def adapt(self, tools: List[ToolDef]) -> List[dict]:
        """
        根据模型特点适配工具 Schema
        
        1. 精简描述（token 紧张时）
        2. 合并参数（开源模型）
        3. 调整格式（不同模型族）
        """
```

#### 集成点
- `react_core.py:on_think_start()` — 构建工具列表时调用
- `tool_registry.py:get_tools_for_task()` — 任务筛选时调用

### 6. 模糊匹配编辑策略
**文件**: `core/multi_agent_v2/tools/edit.py`（新建）

#### 功能设计
- **9 种替换策略**: 参考 opencode 的实现
- **上下文感知**: 利用行号、缩进、语法结构
- **批量编辑**: 支持多处同时替换
- **撤销支持**: 自动生成撤销点

#### 策略列表
```python
EDIT_STRATEGIES = [
    "exact_match",           # 1. 精确匹配
    "fuzzy_match",           # 2. 模糊匹配（容忍小差异）
    "line_number",           # 3. 行号定位
    "context_lines",         # 4. 上下文行匹配
    "indentation_match",     # 5. 缩进匹配
    "structure_match",       # 6. AST 结构匹配
    "regex_replace",         # 7. 正则替换
    "multi_replace",         # 8. 多处批量替换
    "smart_diff",            # 9. 智能差异合并
]
```

#### 核心类
```python
class SmartEditor:
    """智能文件编辑器"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.original_content = None
    
    async def edit(self, old_text: str, new_text: str, strategy: str = "auto") -> EditResult:
        """
        智能编辑
        
        strategy="auto" 时自动选择最佳策略：
        1. 尝试精确匹配
        2. 失败则尝试模糊匹配
        3. 再失败则尝试上下文匹配
        4. 最后报错
        """
    
    def _find_best_strategy(self, old_text: str) -> str:
        """自动选择最佳策略"""
```

#### 集成点
- 替换现有的 `file` 工具的写入逻辑
- 新增 `edit_file` 工具，支持模糊编辑

---

## 阶段四：P3 高级功能（扩展能力）

### 7. AST Shell 分析
**文件**: `core/multi_agent_v2/tools/shell_analyzer.py`（新建）

#### 功能设计
- **Tree-sitter 集成**: 解析 shell 命令语法树
- **安全检查**: 静态分析危险操作
- **参数提取**: 精确提取命令参数用于权限检查

#### 核心类
```python
class ShellAnalyzer:
    """Shell 命令 AST 分析器"""
    
    def __init__(self):
        self.parser = tree_sitter.Parser(tree_sitter.Language(shell_grammar()))
    
    def analyze(self, command: str) -> CommandAST:
        """
        分析命令结构
        
        Returns:
            CommandAST(
                commands=[...],      # 命令列表
                pipes=[...],         # 管道
                redirects=[...],     # 重定向
                variables=[...],     # 变量
                risks=[...]          # 风险点
            )
        """
```

### 8. LSP 集成
**文件**: `core/multi_agent_v2/tools/lsp_client.py`（新建）

#### 功能设计
- **语言服务器协议**: 支持 LSP 1.0 标准
- **代码智能**: 跳转定义、查找引用、自动补全
- **诊断信息**: 实时错误和警告

### 9. Tail Call
**文件**: `core/multi_agent_v2/agents/react_core.py`（修改）

#### 功能设计
- **工具后续调用**: 工具返回后可请求调用另一个工具
- **链式执行**: 支持工具链式调用
- **循环检测**: 与 LoopDetectionMiddleware 集成

---

## 执行顺序

```
阶段一（安全）: permission.py + shell_guard.py + PermissionMiddleware
阶段二（可观测）: hooks.py + mcp_client.py + HookMiddleware
阶段三（智能化）: schema.py + edit.py
阶段四（高级）: shell_analyzer.py + lsp_client.py + tail_call
```

## 测试策略

每个阶段完成后执行：
1. 单元测试：验证各模块功能
2. 集成测试：验证与现有系统兼容
3. 安全测试：验证权限和注入检测
4. 性能测试：验证对执行速度的影响

## 依赖关系

```
阶段一 ──→ 阶段二 ──→ 阶段三 ──→ 阶段四
   │           │           │           │
   ↓           ↓           ↓           ↓
  权限系统   Hook系统    Schema适配   高级功能
  Shell安全  MCP集成     编辑策略     LSP集成
```
