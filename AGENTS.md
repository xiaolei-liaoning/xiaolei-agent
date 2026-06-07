# Agent Instructions

## Project Overview

小雷版小龙虾 AI Agent — Python 3.13+ multi-agent framework with two architectures (V1 leader-worker, V2 intelligent collaboration), MCP tool integration, and code generation fallback.

## Key Commands

| Task | Command |
|------|---------|
| Web server (port 8001) | `python main.py` |
| CLI interactive | `python cli.py` |
| CLI one-shot | `python cli.py "你的命令"` |
| Run all tests | `python -m pytest tests/ -v --timeout=120` |
| Single test file | `python -m pytest tests/test_v2_workflow.py -v` |
| Install deps | `pip install -r requirements.txt` |
| Dev server (hot reload) | `./start.sh --dev` or `./dev.sh dev` |
| Service management | `./dev.sh start|stop|restart|status|logs` |

## Code Quality

Pre-commit hooks: black (line-length 88), isort (black profile), flake8. Run `pre-commit install` first.

```bash
black . && isort . && flake8 --max-line-length=88 --extend-ignore=E203,W503
```

## Architecture

- `core/agent_system.py` — V1: LeaderAgent + WorkerAgents, task decomposition, parallel execution
- `core/multi_agent_v2/` — V2: IntelligentScheduler, 5 collaboration strategies, SharedBus, CircuitBreaker
- `core/engine/llm_backend.py` — LLM routing (GLM API via zhipuai)
- `core/sandbox/enhanced_executor.py` — Sandboxed code execution (30s timeout, 512MB limit)
- `core/mcp/` — MCP tool discovery and invocation
- `config/agents.yml` — Agent role definitions (config-driven, not code)
- `config/mcp_servers.yml` — MCP server definitions

## Environment

- `.env` required — set `ZHIPU_API_KEY` (or `GLM_API_KEY`)
- LLM: zhipuai SDK (GLM models)
- Vector DB: ChromaDB
- Web: FastAPI + Uvicorn

## Testing

- Framework: pytest + pytest-asyncio (`asyncio_mode = "auto"`)
- Tests in `tests/` (unit + e2e), fixtures in `tests/conftest.py`
- CI runs with `continue-on-error: true` — tests may be flaky

## Claude MiniPet

Virtual pet integration — when user mentions 宠物/喂食/摸摸/升级:

```bash
claude-minipet status    # 查看状态
claude-minipet feed      # 喂食 (+30 饱食度)
claude-minipet pat       # 摸摸 (+10 心情, +2 亲密度)
claude-minipet rename <名字>
claude-minipet sync
claude-minipet redeem <兑换码>
```

## Permissions

### Allowed operations
- Python: `python3 *`, `python *`, `pip install *`
- Git: `git *`
- Search: `grep *`, `rg *`, `awk *`
- Web: `curl *`, WebSearch
- Files: `rm *`, `cp *`, `mkdir *`, `cat *`
- Packages: `npm *`, `brew *`
- Database: `sqlite3 *`

### MCP tools
- `mcp__codegraph__*` (codegraph_status, files, context, explore, search, callers, callees, impact, node)
- `mcp__evermem__evermem_search` — EverMem memory search (requires EverOS server running on port 8000)

### EverMem MCP Setup
```bash
# Start local TF-IDF embedding server (port 8002, no API key needed)
python3 /tmp/local_embedding_server.py &

# Start EverOS server (port 8000, uses local TF-IDF)
everos server start --port 8000

# MCP server wrapper is at /tmp/evermem_mcp_server.py
# Configured in .mcp.json as "evermem" server
```

### EverMem Config
- `.env` requires `EVEROS_EMBEDDING__MODEL=local-tfidf` + `EVEROS_EMBEDDING__BASE_URL=http://127.0.0.1:8002`
- Local TF-IDF: `core/memory/vector_memory.py` (LocalEmbeddingFunction), 1024-dim fixed output
- No external API needed for embeddings
