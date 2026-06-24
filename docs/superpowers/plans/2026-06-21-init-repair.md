# 启动修复方案 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 `main.py` 启动日志全部 12 个错误/警告，恢复降级功能

**Architecture:** 分 5 个独立任务，每个任务对应一个文件改动，互不依赖。所有修复不改变业务逻辑。

**Tech Stack:** Python 3.11+, FastAPI, asyncio, SQLAlchemy, YAML

## Global Constraints

- 不改业务逻辑，不重构结构，只消除错误和恢复降级功能
- 配置清理：只移除僵尸引用，不修改现有 API
- `plugin.json` 的修改必须保持格式有效 JSON

---

### Task 1: P0 — ToolRegistry 崩溃 + check_env 文件缺失

**Files:**
- Modify: `core/engine/system_init.py:41`
- Create: `core/engine/check_env.py`

**Interfaces:**
- Consumes: `ToolRegistry` 实例 `@property count`（已定义）
- Produces: `check_env()` 函数返回 `{"llm_ok": True/False}`，与 `system_init.py:167-168` 的调用签名匹配

- [ ] **Step 1: 修复 `reg.count()` → `reg.count`**

将 `system_init.py` 第 41 行的圆括号去掉：

```python
# BEFORE (line 41):
logger.info("V2 ToolRegistry 工具发现完成 (%d 个)", reg.count())

# AFTER:
logger.info("V2 ToolRegistry 工具发现完成 (%d 个)", reg.count)
```

**根因:** `ToolRegistry.count` 是 `@property`，返回 `int` 实例。`reg.count()` 相当于 `42()` → `TypeError: 'int' object is not callable`。此异常导致整个 `_step_register_tools()` 提前退出，MCP 工具发现结果丢失。

- [ ] **Step 2: 创建 `core/engine/check_env.py`**

```python
"""环境检查 — 验证 LLM API Key 等基础设施是否就绪"""
import logging
import os

logger = logging.getLogger(__name__)


def check_env() -> dict:
    """检查运行时环境，返回状态字典（llm_ok 表示 LLM 是否可用）"""
    result = {"llm_ok": False}

    zhipu_key = os.getenv("ZHIPU_API_KEY", "")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    llm_key = os.getenv("LLM_API_KEY", "")

    if zhipu_key or deepseek_key or llm_key:
        result["llm_ok"] = True
        label = "ZHIPU" if zhipu_key else ("DEEPSEEK" if deepseek_key else "CUSTOM")
        logger.info("LLM 配置检测通过: %s", label)
    else:
        logger.warning("未找到 LLM API Key，请在 .env 中设置 ZHIPU_API_KEY 或 LLM_API_KEY")

    return result
```

**根因:** `system_init.py:167` 执行 `from .check_env import check_env`，但 `core/engine/check_env.py` 不存在 → ImportError 被 `except Exception: pass` 吞掉 → `self.env_status` 保持 `{}` → `{}.get("llm_ok")` 返回 `None` → `not None` 为 `True` → 永远打印"LLM 未配置"警告。实际 `.env` 中已有 `ZHIPU_API_KEY`。

- [ ] **Step 3: 验证修复**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
python -c "from core.engine.check_env import check_env; print(check_env())"
```
预期输出: `{'llm_ok': True}`（因为 `.env` 已有 ZHIPU_API_KEY）

```bash
python -c "
from core.multi_agent_v2.tools.tool_registry import get_tool_registry
reg = get_tool_registry()
print('count:', reg.count)  # 不加括号不会崩
"
```
预期输出: `count: 0`

- [ ] **Step 4: Commit**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
git add core/engine/system_init.py core/engine/check_env.py
git commit -m "fix: ToolRegistry count property 调用改为 reg.count 避免 TypeError

- core/engine/system_init.py: reg.count() → reg.count（@property 返回值不可调用）
- core/engine/check_env.py 缺失，导致 LLM 配置检测永远返回未配置
- check_env.py 检查 ZHIPU_API_KEY / DEEPSEEK_API_KEY / LLM_API_KEY 环境变量"
```

---

### Task 2: P1 — 本地 MCP 服务器连接修复

**Files:**
- Modify: `core/plugin_loader.py:344-388`
- Modify: `core/mcp/mcp_client.py:115-149`

**Interfaces:**
- Consumes: `mcp_client.connect_server(name, command, args, env)`（已定义于 `mcp_client.py:153`）
- Produces: `plugin_loader.load_mcp_servers()` 正确连接所有本地 MCP 服务器

- [ ] **Step 1: 改造 `plugin_loader.load_mcp_servers()` 支持双路径**

本地服务器（有 `command` 字段）→ 用 `mcp_client.connect_server()` 直接注册
外部服务器（无 `command` 字段或 `from_awesome`）→ 继续走 `awesome_mcp_manager.quick_connect()`

修改 `core/plugin_loader.py` 第 359-382 行：

```python
            for name, cfg in servers.items():
                if not cfg.get("auto_connect", True):
                    continue

                # 双路径 — 有 command 的是本地服务器，无 command 的是外部
                if cfg.get("command"):
                    # 本地 MCP 服务器 → 用 mcp_client.connect_server() 直接注册
                    args = cfg.get("args", [])
                    try:
                        from core.mcp.mcp_client import mcp_client
                        await mcp_client.connect_server(
                            name=name,
                            command=cfg["command"],
                            args=args,
                            env={"PYTHONPATH": str(PLUGIN_DIR.parent)},
                        )
                        self.loaded_mcp_servers.append(name)
                        results.append(name)
                        logger.debug(f"  ✅ MCP: {name}")
                    except Exception as e:
                        logger.warning(f"  ⚠️ MCP {name} 配置失败: {e}")
                else:
                    # 外部 MCP 服务器 → awesome_mcp_manager.quick_connect()
                    try:
                        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
                        result = await awesome_mcp_manager.quick_connect(name)
                        if result.get("success"):
                            self.loaded_mcp_servers.append(name)
                            results.append(name)
                            logger.debug(f"  ✅ MCP: {name}")
                        else:
                            logger.warning(f"  ⚠️ MCP {name} 连接失败: {result.get('message')}")
                    except Exception as e:
                        logger.warning(f"  ⚠️ MCP {name} 异常: {e}")
```

同时删除不再需要的 `adjusted_args` 死代码（第 365-370 行）：

```python
                # ── 删除以下死代码 ──
                # args = cfg.get("args", [])
                # adjusted_args = []
                # for arg in args:
                #     if arg.startswith("mcp/") and not arg.startswith("plugin/mcp/"):
                #         adjusted_args.append(arg.replace("mcp/", "plugin/mcp/", 1))
                #     else:
                #         adjusted_args.append(arg)
```

**根因:** `plugin_loader.load_mcp_servers()` 对所有服务器统一调用 `awesome_mcp_manager.quick_connect(name)`，该函数只在 114 个精选 MCP 服务器的 name 数据库中查找。本地服务器（`calculator-mcp`, `weather-mcp` 等 13 个）不在该数据库中，全部返回"未知的快速连接服务器"。

- [ ] **Step 2: 改造 `mcp_client.auto_connect_local_servers()` 动态扫描**

修改 `core/mcp/mcp_client.py` 第 115-149 行：

```python
    async def auto_connect_local_servers(self):
        """动态扫描 mcp/ 目录，自动连接所有 *_mcp_server.py 文件"""
        mcp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "mcp")
        if not os.path.exists(mcp_dir):
            logger.warning(f"MCP 服务器目录不存在: {mcp_dir}")
            return

        for fn in sorted(os.listdir(mcp_dir)):
            if not fn.endswith("_mcp_server.py"):
                continue
            server_name = fn.replace("_mcp_server.py", "").replace("_", "-")
            script_path = os.path.join(mcp_dir, fn)
            if not os.path.exists(script_path):
                continue

            try:
                await self.connect_server(
                    name=server_name,
                    command="python3",
                    args=[script_path],
                    env={"PYTHONPATH": os.path.dirname(mcp_dir)},
                )
                logger.info(f"  ✅ {server_name} 服务器就绪")
            except Exception as e:
                logger.warning(f"  ⚠️ {server_name} 服务器启动失败: {e}")
```

- [ ] **Step 3: 验证**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
python main.py 2>&1 | grep -E "MCP.*✅|MCP.*⚠️"
```
预期：没有 `未知的快速连接服务器` 错误。

- [ ] **Step 4: Commit**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
git add core/plugin_loader.py core/mcp/mcp_client.py
git commit -m "fix: 本地 MCP 服务器连接修复

- plugin_loader.load_mcp_servers(): 双路径逻辑
  有 command 字段 → mcp_client.connect_server() 直接注册
  无 command 字段 → awesome_mcp_manager.quick_connect()
- 移除无用的 adjusted_args 死代码
- mcp_client.auto_connect_local_servers(): 动态扫描 mcp/ 目录
- 修复 13 个服务器 '未知的快速连接服务器' 错误"
```

---

### Task 3: P2 — plugin.json 配置清理

**Files:**
- Modify: `plugin/plugin.json`

- [ ] **Step 1: 移除僵尸引用**

编辑 `plugin/plugin.json`：

```json
{
  "name": "xiaolei-agent-plugins",
  "version": "3.4.0",
  "description": "小龙虾 Agent 功能级插件集 — MCP 服务器、本地 Skills、API 路由、配置",
  "dependencies": {},

  "mcp_servers": {
    "config_file": "../config/mcp_servers.yml",
    "servers_dir": "mcp"
  },

  "skills": {
    "local_skills": [
      "mcp_connector",
      "mcp_orchestrator"
    ],
    "guidance_skills": {
      "source": "",
      "system_skills": []
    },
    "persona_skills": [
      "libai", "goddess", "first_love", "bestfriend",
      "linus_torvalds", "john_carmack"
    ]
  },

  "config_files": {
    "mcp_servers": "config/mcp_servers.yml",
    "skill_keywords": "config/skill_keywords.yaml",
    "app_config": "config/app_config.yaml",
    "agents": "config/agents.yml"
  },

  "registration": {
    "auto_connect_mcp": true,
    "auto_register_skills": true,
    "auto_mount_api_routes": true,
    "load_guidance_skills": true
  }
}
```

**改了什么:**
1. `skills.local_skills`: 移除 `"workflow_engine"`
2. `skills.guidance_skills.source`: 清空
3. `skills.guidance_skills.system_skills`: 清空
4. `api_routes` 整块移除

- [ ] **Step 2: 验证**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
python -c "import json; json.load(open('plugin/plugin.json')); print('JSON OK')"
python main.py 2>&1 | grep -E "⚠️ Skill|⚠️ API|指导型技能"
```
预期：无警告输出。

- [ ] **Step 3: Commit**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
git add plugin/plugin.json
git commit -m "chore: 清理 plugin.json 僵尸引用

- 移除不存在的 workflow_engine 技能配置
- 清空 guidance_skills 的无效路径引用
- 移除不存在的 api_routes 整块配置"
```

---

### Task 4: P2 — main.py `on_event` 迁移到 `lifespan`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 替换 `on_event` 为 `lifespan`**

删除 `main.py` 第 114-161 行的 `@app.on_event("startup")` 和 `@app.on_event("shutdown")` 定义。

在第 110-113 行 `init_system()` 定义之后插入 `lifespan` 函数：

```python
# ---------------------------------------------------------------------------
# Lifespan 上下文管理器（替代旧的 on_event 模式）
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — startup/yield/shutdown"""
    await init_system()

    # WebSocket 心跳检测
    try:
        from api.routes.chat_ws import manager
        await manager.start_heartbeat_check()
        logger.info("WebSocket 心跳检测已启动")
    except Exception as e:
        logger.warning("WebSocket 心跳检测启动失败: %s", e)

    # 加载短期记忆
    try:
        from core.handlers import short_term_memory
        from core.database import get_session, BFSContextNode
        with get_session() as session:
            user_ids = session.query(BFSContextNode.user_id).distinct().all()
        for (user_id,) in user_ids:
            short_term_memory.load_from_db(user_id)
        logger.info("短期记忆加载完成，共恢复 %d 个用户的记忆", len(user_ids))
    except Exception as e:
        logger.warning("短期记忆加载失败（首次启动或数据库未就绪）: %s", e)

    # 文件 watcher
    try:
        from core.watcher_setup import setup_file_watcher
        setup_file_watcher(app)
    except Exception as e:
        logger.warning("文件watcher启动失败: %s", e)

    yield   # ← 应用开始服务请求

    # ── shutdown ──
    try:
        from api.routes.chat_ws import manager
        await manager.stop_heartbeat_check()
        logger.info("WebSocket 心跳检测已停止")
    except Exception as e:
        logger.warning("WebSocket 心跳检测停止失败: %s", e)

    try:
        from core.watcher_setup import shutdown_file_watcher
        shutdown_file_watcher(app)
    except Exception as e:
        logger.warning("文件watcher停止失败: %s", e)
```

修改 `app = FastAPI(...)` 第 39 行，添加 `lifespan=lifespan`：

```python
app = FastAPI(
    title="小雷版小龙虾 AI Agent",
    version="3.4.0",
    description="工业级 AI Agent 系统 - 意图识别 / 多步任务 / 工作流自动化 / 用户管理",
    lifespan=lifespan,          # ← 新增
)
```

- [ ] **Step 2: 验证**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
python -c "from main import app; print('lifespan:', app.router.lifespan_context is not None)"
```
预期: `lifespan: True`

```bash
python main.py 2>&1 | grep -i deprecat
```
预期：无输出（无弃用警告）

- [ ] **Step 3: Commit**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
git add main.py
git commit -m "refactor: main.py on_event 迁移到 lifespan 模式

- 替换 @app.on_event('startup') / 'shutdown' 为 lifespan 上下文管理器
- 消除 FastAPI DeprecationWarning
- 行为完全一致，yield 前后分别执行 startup/shutdown 逻辑"
```

---

### Task 5: P3 — 版本号统一 + 移除监控重复初始化 + 安装 watchdog

**Files:**
- Modify: `core/engine/system_init.py:178`

- [ ] **Step 1: 版本号统一 v3.3.1 → v3.4.0**

```python
# system_init.py:178 修改：
# BEFORE:
logger.info("  小雷版小龙虾 AI Agent v3.3.1 启动成功！")

# AFTER:
logger.info("  小雷版小龙虾 AI Agent v3.4.0 启动成功！")
```

- [ ] **Step 2: 移除监控管理器重复初始化**

`_step_init_other_components()` 中删除已废弃的 `监控管理器` 条目：

```python
    async def _step_init_other_components(self):
        components = [
            ("TaskProcessor", "core.tasks.task_processor", "task_processor"),
            ("自主搜索引擎", "core.search.rag_search_engine", "RAGSearchEngine"),
            # 已移除: ("监控管理器", "core.monitoring", "monitoring_manager"),  # DEPRECATED
        ]
```

- [ ] **Step 3: 安装 watchdog**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
pip install watchdog
python -c "import watchdog; print('watchdog', watchdog.__version__, '已安装')"
```

- [ ] **Step 4: 最终验证**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
python main.py 2>&1 | grep -E "ERROR|WARNING|Deprecation|失败|未配置|启动成功"
```

预期输出中不应出现 `V2 ToolRegistry 发现失败` / `LLM 未配置` / `未知的快速连接服务器` / `on_event is deprecated` / `Skill workflow_engine` 等错误。
应出现 `v3.4.0 启动成功`。

- [ ] **Step 5: Commit**

```bash
cd /Users/leiyuxuan/Desktop/小雷版agent
git add core/engine/system_init.py
git commit -m "chore: 版本号统一 + 清理重复初始化 + 安装 watchdog

- system_init.py: v3.3.1 → v3.4.0（与 main.py 一致）
- 移除已废弃的监控管理器重复初始化
- pip install watchdog 启用动态文件监听"
```

---

### 额外步骤: MySQL 启动

**如果需要数据库功能:**

```bash
# Homebrew 启动
brew services start mysql

# 验证
python -c "from core.database import init_db; init_db(); print('DB OK')"
```
