# ECC Install Plan - 小雷版小龙虾agent

## STACK

- **Language**: Python 3.7+
- **Framework**: FastAPI (API), Click/Argparse (CLI)
- **Package Manager**: pip + requirements.txt
- **Test Stack**: pytest (inferred from pyproject.toml structure)
- **Linting**: black, isort
- **Primary Runtime**: CLI + API Server
- **Key Modules**:
  - `core/` - 核心业务逻辑 (50+ Python files)
  - `skills/` - 技能系统 (15+ skills)
  - `core/multi_agent_v2/` - 多Agent系统 (25+ files)
  - `api/` - REST API

---

## DAILY

### Skills (项目内置)

| Component | Type | Evidence | Justification |
|-----------|------|----------|---------------|
| `skills/conversation-compressor/` | skill | 已安装在 `.trae/skills/` | 项目已有ECC集成，每次会话都需要 |
| `skills/web_scraper/` | skill | 10+ scraper files, handler.py | 高频使用的核心技能 |
| `skills/deep_thinking/` | skill | handler.py + SKILL.md | CLI常用功能 |
| `skills/weather/` | skill | 简单天气查询 | 日常工具 |

### Core Modules (KEPA闭环)

| Component | Type | Evidence | Justification |
|-----------|------|----------|---------------|
| `core/execution_logger.py` | module | KEPA-K执行日志 | 每次任务执行都需要 |
| `core/auto_reviewer.py` | module | KEPA-E复盘 | 任务完成后自动触发 |
| `core/skill_extractor.py` | module | KEPA-P萃取 | 技能沉淀核心 |
| `core/skill_dispatcher.py` | module | 技能分发 | 每次技能调用都经过 |

### Rules

| Component | Type | Evidence | Justification |
|-----------|------|----------|---------------|
| Python formatting | rules | `pyproject.toml` with black/isort | 项目规范，每次提交都检查 |

---

## LIBRARY

### Skills (按需加载)

| Component | Type | Evidence | Justification |
|-----------|------|----------|---------------|
| `skills/marketplace/` | skill | 完整市场系统但功能复杂 | 需要时通过skill_cli调用 |
| `skills/third_party/` | skill | 钉钉/飞书/Jira等集成 | 非日常使用 |
| `skills/openclaw/` | skill | 桌面自动化 | 特定场景使用 |
| `skills/translator/` | skill | 翻译功能 | 需要时调用 |
| `skills/advanced_automation/` | skill | 高级自动化 | 复杂场景使用 |

### Multi-Agent System

| Component | Type | Evidence | Justification |
|-----------|------|----------|---------------|
| `core/multi_agent_v2/` | module | 85+ files, 复杂架构 | 普通任务不需要，复杂推理才用 |
| `core/multi_agent_system.py` | module | 多Agent协调 | 按需使用 |

### 文档和工具

| Component | Type | Evidence | Justification |
|-----------|------|----------|---------------|
| `docs/` | docs | 50+ markdown files | 参考使用，不需加载 |
| `examples/` | examples | self_check_integration_examples.py | 学习参考 |

---

## INSTALL PLAN

### 当前状态

- `.trae/skills/` 已安装: `conversation-compressor/`
- 全局 skills 目录: `/Users/leiyuxuan/.trae-cn/skills/`

### 建议操作

#### 1. DAILY - 保持加载

```
.trae/skills/
├── conversation-compressor/    ✅ 已安装 (KEPA优化相关)
└── (建议添加)
    └── deep-thinking-protocol/  (来自全局skills)
```

#### 2. LIBRARY - 按需访问

将以下skills标记为LIBRARY，通过skill-library路由访问：

| Skill | 触发关键词 |
|-------|-----------|
| `marketplace/` | "上传技能", "下载技能", "技能市场" |
| `third_party/` | "发送钉钉", "发送飞书", "Jira任务" |
| `openclaw/` | "桌面自动化", "打开应用", "点击按钮" |
| `translator/` | "翻译", "translate" |
| `advanced_automation/` | "高级自动化", "复杂操作" |

#### 3. KEPA闭环 - 优化项

基于KEPA分析报告，建议优化：

| 优先级 | 模块 | 优化内容 |
|--------|------|----------|
| 🔴 高 | `execution_logger.py` | 添加批量写入、异步IO |
| 🔴 高 | `auto_reviewer.py` | LLM缓存 + Mock降级 |
| 🔴 高 | `skill_extractor.py` | 从实际日志提取步骤 |
| 🟡 中 | `skill_dispatcher.py` | 优先检索萃取的技能 |
| 🟢 低 | 整体 | 添加异步处理 |

---

## VERIFICATION

### 检查项

- [x] 项目使用 Python (confirmed via pyproject.toml)
- [x] 已有 `.trae/skills/conversation-compressor/`
- [x] 全局 skills 目录存在于 `~/.trae-cn/skills/`
- [x] `deep-thinking-protocol` 可从全局skills访问

### 待验证

- [ ] `conversation-compressor` 是否正确加载
- [ ] KEPA模块是否在CLI启动时初始化

---

## 开放问题

1. 是否需要为KEPA闭环创建独立的skill包装器？
2. 是否需要将优化后的模块发布为可复用的skill？
