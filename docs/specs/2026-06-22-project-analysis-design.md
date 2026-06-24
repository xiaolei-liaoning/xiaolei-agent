# 项目分析能力 + 路由精度改进设计方案

## 背景

小雷版 Agent 的项目分析能力存在两个独立问题：

1. **分析能力弱** — 只能用 `system_toolbox.file_list` 列文件名 + 逐条 `read_file` 读内容，缺乏批量读取能力和代码关系查询
2. **路由精度不够** — "分析一下 /xxx 项目" 常常路由到 `data_analysis` 甚至 `system_toolbox`，加载的 Expert 角色也不对口（如 "Filament 优化专家"）

## 改动思路

两个维度同时修复：

| 维度 | 当前 | 目标 |
|------|------|------|
| **路由精度** | 简单关键词命中（1 个词命中即触发） | 多因子加权评分（词组 + 路径检测 + X 信号 + LLM 消歧兜底） |
| **分析能力** | `file_list` + 逐条 `read_file` | 批量文件读取 MCP + codegraph 关系图查询 |

## 改动清单

| # | 改动 | 类型 | 涉及文件 | 估算行数 |
|---|------|------|----------|----------|
| 1 | 多因子路由评分器 | 修改 | `core/engine/skill_dispatcher.py` | ~150 |
| 2 | 新增 project_analysis skill | 配置 | `config/skill_keywords.yaml` | ~15 |
| 3 | 新增 project_analyzer Expert + skill_agent_map | 配置 | `config/agents.yml` + `config/skill_agent_map.yaml` | ~40 |
| 4 | 新增 project_analyzer MCP 服务器 | 新文件 | `mcp/project_analyzer_mcp_server.py` | ~250 |
| 5 | 修复 codegraph MCP 配置 | 配置 | `.mcp.json` + `config/mcp_servers.yml` | ~10 |

---

## 第一部分：路由精度改进

### 当前算法的问题

`skill_dispatcher.py` 目前的做法：遍历每个 skill 的 `keywords`，命中任意一个即加分，最高分胜出。

问题：**"分析一下"** 同时出现在 `data_analysis` 和 `project_analysis` 的意图映射中，且 `data_analysis` 有 `project_analysis` 没有的"分析一下"关键词，导致带路径的分析请求错误路由到数据分析。

### 多因子评分设计

```python
class SkillRouter:
    WEIGHTS = {
        "keyword": 1.0,    # 关键词/词组匹配
        "path": 2.0,       # 路径检测（高权重，因为带路径是强信号）
        "x_signal": -0.5,  # 反向排除
        "context": 0.3,    # 上下文复用（同一 session 内连续请求）
    }
```

#### 因子 1：关键词/词组匹配（keyword）

改进为三层信号：

```yaml
project_analysis:
  strong_patterns:        # 正则词组，匹配度更高
    - "分析.*项目"          # "分析这个项目"、"分析一下项目"
    - "分析.*代码"
    - "项目.*结构"
    - "项目.*(~/|/|[a-zA-Z]:\\)"  # "项目 /path" 带路径
    - "看(看|一下).*(项目|代码|仓库)"
  keywords:               # 完整关键词
    - "项目结构"
    - "代码库"
    - "源代码分析"
    - "项目目录"
  weak_keywords:           # 单次出现权重较低
    - "项目"
    - "代码"
    - "源码"
    - "库"
    - "仓库"
    - "分析"
```

评分方式：

```python
def _keyword_score(skill_config, user_input):
    score = 0
    for pattern in skill_config.get("strong_patterns", []):
        if re.search(pattern, user_input):
            score += 2.0  # 词组命中权重高
    for kw in skill_config.get("keywords", []):
        if kw in user_input:
            score += 1.5
    for kw in skill_config.get("weak_keywords", []):
        if kw in user_input:
            score += 0.3
    return score
```

#### 因子 2：路径检测（path）

```python
def _detect_path(user_input):
    """检测输入中是否包含文件系统路径"""
    path_patterns = [
        r"(~[/\w.-]+)",          # ~/xxx
        r"(/([\w./-]+))",        # /absolute/path
        r"(\.\.?/[\w./-]+)",     # ./path or ../path
    ]
    match = False
    for pattern in path_patterns:
        if re.search(pattern, user_input):
            candidate = re.search(pattern, user_input).group(1)
            # 验证路径真实存在
            expanded = os.path.expanduser(candidate)
            if os.path.exists(expanded) or os.path.isdir(expanded):
                return 2.0, expanded  # 真实路径 → 最高分
            else:
                return 1.0, candidate  # 路径格式匹配但不存在
    return 0, None
```

#### 因子 3：反向排除（X 信号）

某些 skill 配置 `x_keywords`，出现特定词就减分：

```yaml
data_analysis:
  x_keywords: ["项目", "代码", "仓库", "目录"]
  # "数据分析一下这个项目" → data_analysis 虽然匹配"分析一下"
  # 但"项目"出现 → 减 0.5，降权重
```

#### 因子 4：LLM 消歧（兜底）

当 top-2 分差 < 0.5 时，调用最小 LLM（glm-4-flash）做一次极轻量的消歧：

```
system: "从以下技能中选择最适合用户意图的一个：{top2}。只回复技能名。"
user:  "分析一下这个"
→ 回复: "project_analysis" 或 "data_analysis"
```

单次消歧调用 < 0.1 秒，token 消耗 < 50。

### 配置结构

新增 `config/skill_agent_map.yaml`：

```yaml
# Skill → Expert 映射
skill_agent_map:
  project_analysis: project_analyzer
  system_toolbox: system_operator
  data_analysis: data_analyst
  web_scraper: web_scraper_expert
  weather: weather_expert
  translator: translator
  deep_thinking: deep_thinker
  creative_writing: creative
  # 其他 skill 不指定 → fallback general
```

---

## 第二部分：分析能力改进

### 2.1 project_analyzer MCP 服务器

新增 `mcp/project_analyzer_mcp_server.py`，两个工具：

#### 工具 1：`analyze_project`

```
名称: analyze_project
描述: 扫描并读取项目目录中的关键文件内容

参数:
  path:       string    项目路径（必须）
  depth:     string    quick|normal|deep（默认 normal）

返回值:
  structure:  文件树概览（目录层级 + 文件计数 + 类型分布）
  language:   检测到的语言/框架（如 Python/FastAPI, TypeScript/Next.js）
  files:      按优先级读取的文件内容列表 [{path, content, size, lines}]
  unread:     未读取的文件统计（总数 + 最值得关注的文件名）
```

**内部实现：**

```python
def _score_file(rel_path: str, size: int) -> float:
    """按重要度给文件打分，用于决定读哪些文件"""
    name = rel_path.lower()
    ext = os.path.splitext(rel_path)[1].lower()
    score = 0

    # Tier 1 配置 / 文档
    if os.path.basename(rel_path).lower() in (
        "readme.md", "readme", "claude.md", "agents.md",
        "package.json", "pyproject.toml", "cargo.toml",
        "go.mod", "go.sum", "gemini.md",
    ): score += 5
    if "config" in name and ext in (".yaml", ".yml", ".json", ".toml"): score += 3

    # Tier 2 入口文件
    if os.path.basename(rel_path) in (
        "main.py", "app.py", "index.tsx", "index.ts",
        "main.go", "main.rs", "index.js",
    ): score += 4

    # Tier 3 源文件
    if ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"): score += 2
    if ext in (".md", ".rst"): score += 1

    # 减分项
    if ext in (".png", ".jpg", ".gif", ".svg", ".ico", ".woff2"): score -= 10
    if "/node_modules/" in rel_path or "/.git/" in rel_path or "__pycache__" in rel_path: score -= 100
    if "/test" in rel_path or "/tests/" in rel_path: score -= 3
    if "lock." in name or "lockfile" in name: score -= 5
    if size > 100_000: score -= 2
    if size > 500_000: score -= 5

    return max(score, 0)
```

**budget 控制：**

```python
MAX_TOKENS = {"quick": 3000, "normal": 12000, "deep": 50000}

def _read_by_budget(scored_files: list, budget: int) -> list:
    result = []
    used = 0
    for path, score, content in scored_files:
        tokens = estimate_tokens(content)
        if used + tokens > budget:
            break
        result.append({"path": path, "content": content})
        used += tokens
    return result, used, len(scored_files) - len(result)
```

#### 工具 2：`search_code`

```
名称: search_code
描述: 在项目中搜索代码片段（grep + 上下文）

参数:
  path:        string    项目路径
  query:       string    搜索关键词
  file_pat:    string    文件 glob 过滤（默认 "**/*")
  max_result:  int       最大结果数（默认 20）
  context:     int       上下行数（默认 3）

返回值:
  results: [{file, line, snippet}]  匹配的代码片段列表
  total: int                         总匹配数
```

### 2.2 codegraph MCP 修复

**`.mcp.json`** 修复：

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "codegraph",
      "args": ["serve", "--mcp"]
    }
  }
}
```

**`config/mcp_servers.yml`** 新增：

```yaml
codegraph-mcp:
  command: codegraph
  args: ["serve", "--mcp"]
  description: "代码关系图引擎：符号搜索、文件结构、函数调用分析"
  auto_connect: true
```

### 2.3 Expert 角色

**`config/agents.yml`** 新增：

```yaml
project_analyzer:
  name: "代码结构分析师"
  description: "分析项目目录结构、源代码架构、技术栈和功能模块"
  system_prompt: >
    你是一个经验丰富的代码结构分析师。你能快速理解一个项目的目录结构、
    技术栈选择、架构设计和各模块职责。

    分析时，你会先看文件结构概览和技术栈检测结果，再阅读关键配置文件
    （README、package.json、pyproject.toml 等），然后深入核心代码文件，
    最后给出完整的项目分析报告。

    报告中应包括：
    1. 项目概述（语言、框架、构建工具）
    2. 目录结构总览（主要目录的职责说明）
    3. 核心模块分析（入口、路由、数据流）
    4. 项目亮点和注意事项
  skill: project_analysis
```

---

## 第三部分：完整分析流程

```
用户输入: "分析一下 /xxx/deerflow"

skill_dispatcher:
  ├─ 多因子评分 → project_analysis 3.2 vs data_analysis 0.5 ✅
  ├─ 检测到路径 /xxx/deerflow 真实存在 → 路径因子 +2.0
  └─ project_analysis (2.8) → data_analysis (0.5) → 明确胜出

skill_agent_map:
  └─ project_analysis → project_analyzer Expert

分析执行（Agent ReAct 循环）:

  第 1 步: 文件扫描
    call project_analyzer.analyze(path, "normal")
    ← 文件树 + 28 个关键文件内容 (~11k tokens)

  [可选] 第 2 步: 关系查询
    call codegraph files + query (如已索引)
    ← 结构化文件树 + 符号定义

  第 3 步: 综合总结
    ← 代码结构分析师视角的报告

  响应给用户
```

### 缓存策略

```python
PROJECT_CACHE_DIR = "~/.xiaolei-agent/project_cache/"

def get_cached_analysis(path, depth):
    cache_key = hashlib.md5(path.encode()).hexdigest()
    cache_file = f"{PROJECT_CACHE_DIR}/{cache_key}_{depth}.json"

    current_mtime = _get_dir_mtime(path)
    cached = _load_cache(cache_file)

    if cached and cached.get("mtime") == current_mtime:
        return cached["result"]
    return None
```

---

## 实现顺序

1. `config/skill_agent_map.yaml` — 先配好映射，不改变现有路由行为
2. `config/skill_keywords.yaml` 新增 `project_analysis` — 定义信号词组
3. `core/engine/skill_dispatcher.py` 多因子评分 — 核心改动
4. `mcp/project_analyzer_mcp_server.py` — 新文件
5. `config/mcp_servers.yml` + `.mcp.json` 修复 — 激活 codegraph
6. `config/agents.yml` 新增 project_analyzer — 绑定角色

---

## 风险和回退

| 风险 | 概率 | 处理方式 |
|------|------|----------|
| 多因子评分反而误杀现有路由 | 中 | 保留旧的 `intent_skill_map` 机制作为 fallback |
| codegraph 首次索引太慢影响体验 | 中 | project_analyzer 独立可用，codegraph 只做增强 |
| project_analyzer MCP 读取大文件 OOM | 低 | 单文件上限 500KB，超出截断 |
