# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**小雷版小龙虾 AI Agent** (xiaolei-agent) - Version 3.3.1

An industrial-grade AI Agent system featuring multi-agent orchestration, skill-based tool execution, and a Claude Code-like CLI experience. The system intelligently falls back to code generation when tools aren't available, with strict sandbox execution constraints.

**Key Features:**
- Multi-agent system: Master, Worker, Expert, Reviewer, Planner, Character agents
- Intelligent tool-first strategy with code generation fallback
- CLI with command prefix system (`/run`, `/scrape`, `/analyze`, etc.)
- RESTful API with user auth, chat history, task logging
- Web server on port 8001, API docs at `/docs`

## Development Commands

### Running the System

```bash
# Standard startup
python main.py                    # Port 8001, CLI integration
python cli.py                     # Standalone CLI interface

# Development with hot reload
python dev_mode.py --module main.py --port 8001

# Service management (script-based)
./start.sh                        # Standard mode
./start.sh --dev                  # Development mode
./start.sh --debug                # Debug mode with detailed logging
./start.sh --test                 # Install deps and run tests

./dev.sh start                    # Production service
./dev.sh dev                      # Development service (hot reload)
./dev.sh stop                     # Stop service
./dev.sh logs                     # View logs
```

### Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/test_multi_agent_v2.py -v
python -m pytest tests/test_cli_services.py -v

# Run with coverage
pytest --cov=. --cov-report=html
```

### Installation

```bash
pip install -r requirements.txt
cp .env.example .env                 # Configure API keys
```

## Architecture Overview

### Module Structure

```
core/
├── agents/              # Multi-agent v2 system (Master, Worker, Expert, Reviewer)
├── engine/              # LLM backend, reasoning, skill dispatcher
├── handlers/            # Request processors (single_step, multi_step, code_fallback)
├── infrastructure/      # Database, cache, config, DI container
├── memory/              # Short-term, character, vector memory
├── monitoring/          # System metrics, alerts
├── multi_agent_v2/      # New multi-agent orchestration layer
├── workflow/            # Automation and XML workflow processing
└── skills/              # Skill handlers (web_scraper, data_analysis, etc.)

cli/
├── base.py              # Core CLI infrastructure
├── command_parser.py    # Command parsing (/help, /run, /scrape, etc.)
├── agent_tools.py       # Agent interaction tools
├── logging_system.py    # Colored, timestamped logging

skills/                  # Skill handlers (web scraping, analysis, automation)
api/                     # FastAPI routes (v1, routes/, schedule, workflow)

tests/                   # Test suite
```

### Core Processing Flow

1. **User Request** → CLI `command_parser.py` parses the input
2. **Handler Selection** → `handlers/single_step_handler.py` or `multi_step_handler.py`
3. **Task Processing** → `core/tasks/` task processor/planner
4. **Tool Execution** → `core/engine/skill_dispatcher.py` dispatches to skills
5. **Code Generation Fallback** → If tool not found, LLM generates code in `sandbox_executor.py`
6. **Multi-Agent Orchestration** → `core/multi_agent_v2/` coordinates agents

### Code Generation Fallback Mechanism

Located in `core/handlers/code_fallback.py`:

- Triggered when tool execution fails or no suitable tool exists
- LLM analyzes requirements and generates Python/Shell code
- Code executes in restricted sandbox (timeout: 30s, memory: 256MB)
- Dangerous modules (subprocess, socket, etc.) forbidden
- Safe modules (os, pathlib, json, re, math) allowed

**Safety Configuration:** Modify sandbox limits in `core/handlers/single_step_handler.py` or the `SandboxResourceLimits` class.

### Multi-Agent V2 Architecture

New orchestration layer under `core/multi_agent_v2/`:

- **Agents:** base, master, worker, reviewer, expert (lazily loaded)
- **Infrastructure:** LLM interface, memory, observability, persistence
- **Orchestration:** collaboration strategies, context management, lifecycle, scheduler

Agents communicate through shared memory and a message bus pattern.

## Important Files

| File | Purpose |
|------|---------|
| `cli/command_parser.py` | CLI command parsing, supports `/run`, `/scrape`, `/analyze`, etc. |
| `core/handlers/single_step_handler.py` | Single-step request processing, includes code generation fallback |
| `core/handlers/multi_step_handler.py` | Multi-step task execution with orchestration |
| `core/engine/skill_dispatcher.py` | Skill loading and execution dispatcher |
| `core/multi_agent_v2/agents/base/base_agent.py` | Base agent class |
| `core/multi_agent_v2/agents/master/master_agent.py` | Task coordination and scheduling |
| `skills/workflow_engine.py` | Workflow engine for chaining skills |

## Skill System (MCP-based)

### Claude Code 全局 Skills → MCP 迁移

所有功能型 Claude Code Skills 已迁移到 MCP Server。系统级 Skills (update-config, loop, init 等) 保留在原位。

**MCP 架构 (混合模式):**

| 模式 | 服务器 | 端口 | 用途 |
|------|--------|------|------|
| stdio | skill-server | 子进程 | 所有 46 个功能型 Skills 的指导内容 + 工具 |
| HTTP/SSE | skill-server-http | 6283 | 复杂能力型 Skills (产品、内容、媒体、AI) |
| HTTP | cc-workflow-studio | 6282 | 工作流编排可视化 |

**MCP 工具:**

| 工具 | 功能 |
|------|------|
| skill_list | 列出所有可用 Skills，可按分类筛选 |
| skill_get | 获取指定 Skill 的完整 SKILL.md 内容 |
| skill_search | 按关键词搜索 Skills |
| skill_execute | 执行指定 Skill，返回指导 + 执行计划 |
| skill_agent_run | 运行 Skill 的子 Agent 工作流 |

**调用方式 (代替 Skill 工具):**

```
mcp__skill_server__skill_execute(name="product-capability", task="产品能力分析")
mcp__skill_server__skill_get(name="api-design")
mcp__skill_server__skill_search(query="测试")
```

**Resources 访问:**

```
skill://{name}  如 skill://product-capability
```

### 项目内部 Skills

本地技能模块在 `skills/` 目录。添加新技能:
1. 创建 `skills/{name}/handler.py` 实现 `handle()` 函数
2. 注册到 `core/engine/skill_dispatcher.py`
3. 可选在 `mcp_servers.yml` 中添加 MCP 服务器配置

可用分类: web_scraper, data_analysis, gui_automation, translator, weather, deep_thinking, openclaw, mcp_orchestrator, calculator, fun。

MCP 服务器配置: `config/mcp_servers.yml` (内部 MCP 服务器)，`.mcp.json` (Claude Code 级别 MCP)。

## Environment Variables

Key variables in `.env`:
- `LLM_API_KEY` - ZhipuAI/OpenAI API key
- `LLM_BASE_URL` - Custom API endpoint
- `ALLOWED_ORIGINS` - CORS allowed origins (comma-separated)

## Project Status

This is an active project with recent refactoring:
- Multi-agent v2 system under active development
- CLI and API are integrated
- Test suite covers core functionality
- Code generation fallback is a key differentiator
