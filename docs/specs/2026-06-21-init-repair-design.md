# 小雷版小龙虾 AI Agent 启动修复方案

**日期:** 2026-06-21  
**版本:** v1.0  
**状态:** 待实施  

## 概述

针对 `main.py` 启动日志暴露的 12 个问题，进行系统性修复。所有修复不改变业务逻辑，只消除错误、恢复降级功能、清理配置。

## 问题清单与修复方案

### P0 — 启动阻塞 / 严重功能缺失

#### 1. ToolRegistry `count` 属性被当作函数调用

- **症状:** `V2 ToolRegistry 发现失败: 'int' object is not callable`
- **根因:** `system_init.py:41` 调用 `reg.count()`，但 `ToolRegistry.count` 是 `@property`，返回 `int` 不可调用
- **修复:** `system_init.py:41` 将 `reg.count()` → `reg.count`
- **改动:** 1 行，1 文件

#### 2. `check_env.py` 文件缺失导致 LLM 误报未配置

- **症状:** `LLM 未配置 — 聊天/代码生成/反思将不可用`，但 `.env` 中已有 `ZHIPU_API_KEY` 和 `DEEPSEEK_API_KEY`
- **根因:** `system_init.py` 的 `_step_check_env()` 尝试 `from .check_env import check_env`，但 `core/engine/check_env.py` 不存在 → ImportError 被 `try/except` 吞掉 → `env_status = {}`（空字典）→ `llm_ok` 永远 False
- **修复:** 新建 `core/engine/check_env.py`，检查环境变量并返回正确状态
- **改动:** 1 文件

#### 3. MySQL 服务未启动

- **症状:** `连接 MySQL 失败: Can't connect to MySQL server on 'localhost'`
- **根因:** MySQL 服务未运行
- **修复:** 启动 MySQL 服务（命令根据用户环境选择）
- **改动:** 无代码改动

### P1 — 功能降级

#### 4. 13 个本地 MCP 服务器无法通过 `awesome_mcp_manager.quick_connect()` 启动

- **症状:** `⚠️ MCP calculator-mcp 连接失败: 未知的快速连接服务器: calculator-mcp`（共 13 个服务器同样报错）
- **根因:** `plugin_loader.load_mcp_servers()` 对 `mcp_servers.yml` 中所有服务器统一调用 `awesome_mcp_manager.quick_connect(name)`，但该函数只在 114 个精选 MCP 数据库 中查找 name 匹配。本地服务器（带 `command`/`args` 配置）的名字不在数据库里，全失败
- **修复:** 将 `plugin_loader.load_mcp_servers()` 改造为双路径：
  - 服务器配置有 `command` 字段 → 使用 `MCPProcess` 或 `mcp_client.connect_server()` 直接启动本地进程
  - 无 `command` 字段（或 `from_awesome` 模式）→ 继续走 `awesome_mcp_manager.quick_connect()`
- **改动:** 2 文件（`plugin_loader.py` + 可选 `awesome_mcp_manager.py`）

#### 5. `mcp_client.auto_connect_local_servers()` 硬编码遗漏

- **症状:** 部分已实现的 MCP 服务器（`skill_mcp_server.py`, `openclaw_mcp_server.py` 等）未被自动连接
- **根因:** `mcp_client.py` 的 `auto_connect_local_servers()` 使用硬编码字典，只覆盖 10 个服务器
- **修复:** 改为动态扫描 `mcp/` 目录，自动发现所有 `*_mcp_server.py` 文件
- **改动:** 1 文件

### P2 — 配置噪声

#### 6. `plugin.json` 引用不存在的 `workflow_engine` 技能

- **症状:** `⚠️ Skill workflow_engine 加载失败: No module named 'plugin.skills.workflow_engine'`
- **修复:** 从 `plugin.json` 的 `skills.local_skills` 列表中移除 `workflow_engine`
- **改动:** 1 文件，1 行

#### 7. `plugin.json` 引用不存在的 `plugin.api.*` 路由

- **症状:** `⚠️ API skills / agent_groups / system / chat 加载失败: No module named 'plugin.api'`
- **根因:** `plugin.json` 的 `api_routes.enabled` 声明了 4 个模块，但 `plugin/api/` 目录不存在
- **修复:** 从 `plugin.json` 移除 `api_routes` 配置块，或清空 `enabled` 列表。API 路由已由 `api/route_manager.py` 管理
- **改动:** 1 文件

#### 8. 指导型技能路径不存在

- **症状:** `⚠️ 指导型技能路径不存在: ~/Desktop/claude/everything-claude-code-main/.agents/skills`
- **修复:** 移除或修正 `plugin.json` 中 `guidance_skills.source` 的路径配置
- **改动:** 1 文件

#### 9. FastAPI `on_event` 弃用警告

- **症状:** `DeprecationWarning: on_event is deprecated, use lifespan event handlers instead`
- **根因:** `main.py:114` 和 `main.py:146` 使用 `@app.on_event("startup")` / `@app.on_event("shutdown")`
- **修复:** 改为 FastAPI 推荐的 `lifespan` 上下文管理器模式
- **改动:** 1 文件（`main.py`）

### P3 — 轻微问题

#### 10. 监控管理器初始化两次

- **症状:** 日志中监控管理器初始化消息出现两次
- **根因:** `system_init.py` 的 `_step_init_other_components()` 初始化了监控管理器，后续又有独立初始化
- **修复:** 标记已废弃，移除重复初始化（`monitoring/__init__.py` 已注释 `DEPRECATED`）
- **改动:** 1 文件

#### 11. 版本号不一致

- **症状:** `main.py` 写 v3.4.0，`system_init.py` 启动横幅写 v3.3.1
- **修复:** `system_init.py` 横幅统一为 v3.4.0
- **改动:** 1 行

#### 12. `watchdog` 未安装

- **症状:** `⚠️ watchdog 未安装，动态自动加载不可用`
- **修复:** `pip install watchdog`
- **改动:** 无代码改动

## 影响分析

| 维度 | 评估 |
|------|------|
| 业务逻辑变更 | **无** — 只修错误，不改行为 |
| 总改动文件 | 约 6 个（`system_init.py`, `check_env.py`（新）, `plugin_loader.py`, `plugin.json`, `main.py`, `mcp_client.py`） |
| API 兼容性 | 完全不变 |
| 数据库兼容性 | 不变 |
| 回滚难度 | 低 — 每项修复独立可逆 |

## 实施顺序

1. P0 修复（ToolRegistry + check_env 文件缺失）
2. P1 修复（MCP 连接架构）
3. P2 配置清理（plugin.json + on_event）
4. P3 收尾（版本号 + watchdog）
5. 启动 MySQL 验证
