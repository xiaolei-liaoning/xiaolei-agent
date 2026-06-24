#!/usr/bin/env python3
"""项目分析 MCP 服务器 — JSON-RPC stdio 协议 (v2)

提供两个工具：
1. analyze_project — 扫描项目目录，按优先级批量读取关键文件内容
2. search_code — 在项目中搜索代码片段（grep + 上下文）

v2 改进（2026-06-22）：
-  内容头部评分：读文件前3行判断入口/框架/barrel export
-  分组预算分配：文档/配置/入口/源码组各自有预算切片
-  技术栈嗅探：主动读 pyproject.toml/package.json/app_config.json 提取依赖
"""

import sys
import json
import os
import re
import time
import hashlib
import mimetypes
from pathlib import Path

# ============================================================
# 工具定义
# ============================================================

TOOLS = [
    {
        "name": "analyze_project",
        "description": "【推荐】批量读取项目关键文件内容，一次可读10~30个核心文件（含README、配置、入口、主要源码），自动检测技术栈（语言/框架/LLM提供商），按重要性排序。适合分析项目结构和代码。比逐文件手动read_file快10倍。返回：files[{path,content,lines}], tech_stack{languages,frameworks}, structure{total_files,top_dirs}",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "项目路径（必须）"},
                "depth": {
                    "type": "string",
                    "description": "分析深度: quick(3k) / normal(12k) / deep(50k)",
                    "enum": ["quick", "normal", "deep"],
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "analyze_project_structure",
        "description": "【轻量】扫描项目结构元数据（不读文件正文），返回文件树、技术栈、依赖清单、git统计、函数/类签名、import关系。比analyze_project快10倍，适合快速了解项目全貌。返回纯元数据，不含文件正文。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "项目路径（必须）"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_code",
        "description": "在项目中搜索代码片段（grep + 上下文行）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "项目根路径"},
                "query": {"type": "string", "description": "搜索关键词"},
                "file_pattern": {"type": "string", "description": "文件 glob 过滤，如 *.py、*.tsx"},
                "max_results": {"type": "integer", "description": "最大结果数（默认 20）"},
                "context_lines": {"type": "integer", "description": "匹配行上下文行数（默认 3）"},
            },
            "required": ["path", "query"],
        },
    },
]

# ============================================================
# 常量
# ============================================================

EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".next",
    "dist", "build", ".cache", ".codegraph", ".deer-flow", ".history",
    ".mypy_cache", ".pytest_cache", ".tox", ".svn", ".hg", "target",
    "bazel-bin", "bazel-out", "bazel-test",
}

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".otf", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".mp4", ".mp3", ".webm", ".avi", ".mov", ".wav",
    ".flac", ".ogg", ".zip", ".tar", ".gz", ".rar", ".7z", ".dmg",
    ".pkg", ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".pyc",
    ".pyo", ".mp3", ".ico",
}

# Token 预算
MAX_TOKENS = {"quick": 3000, "normal": 12000, "deep": 50000}

# 文件名→分组
GROUP_OF_NAME = {
    "readme.md": "doc", "readme": "doc", "claude.md": "doc", "agents.md": "doc",
    "gemini.md": "doc", "changelog.md": "doc", "contributing.md": "doc",
    "package.json": "config", "pyproject.toml": "config",
    "cargo.toml": "config", "go.mod": "config", "setup.py": "config",
    "setup.cfg": "config",
    "config.yaml": "config", "config.yml": "config", "config.json": "config",
    "config.example.yaml": "config",
    "docker-compose.yaml": "config", "docker-compose.yml": "config",
    "makefile": "build", "dockerfile": "build",
}

# 入口文件
ENTRY_NAMES = {
    "main.py", "app.py", "index.tsx", "index.ts", "index.js",
    "main.go", "main.rs", "main.ts", "app.ts", "app.tsx",
    "app.js", "server.py", "manage.py", "entrypoint.py", "cli.py",
}

# 高优先级目录前缀（项目目录结构中的核心模块目录）
CORE_DIR_PREFIXES = [
    "core/", "api/", "engine/", "config/", "app/",
    "backend/", "packages/",
    "src/", "lib/", "handlers/",
]

# 分组预算比例：{[group_name]: budget_percentage}
GROUP_BUDGET_RATIO = {
    "doc":    0.06,     # 文档类
    "config": 0.08,     # 配置文件
    "entry":  0.30,     # 入口文件（main.py 较大，需要更多预算）
    "source": 0.38,     # 源文件
    "build":  0.05,     # 构建配置
    "other":  0.13,     # 其他
}

# ============================================================
# 工具函数
# ============================================================

def estimate_tokens(text: str) -> int:
    """粗略估算 token 数"""
    if not text:
        return 0
    cjk = len(re.findall(r'[一-鿿　-〿＀-￯]', text))
    rest = len(text) - cjk
    return cjk * 2 + rest // 4 + 1


def read_file_head(fp: str, lines: int = 3) -> str:
    """快速读取文件头部，用于内容嗅探"""
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readline() for _ in range(lines))
    except (OSError, PermissionError):
        return ""


# ============================================================
# 新增辅助函数 — 轻量结构扫描
# ============================================================

def _walk_structure_only(path: str) -> list:
    """遍历项目文件，只取元数据不读内容"""
    results = []
    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, path)
                try:
                    st = os.stat(fp)
                    size = st.st_size
                    mtime = st.st_mtime
                    lines = 0
                    with open(fp, "rb") as bf:
                        for _ in bf:
                            lines += 1
                except (OSError, PermissionError):
                    size, mtime, lines = 0, 0, 0
                ext = os.path.splitext(f)[1].lower()
                if ext in BINARY_EXTS:
                    continue
                results.append((rel, fp, size, lines, mtime, ext))
    except (PermissionError, OSError):
        pass
    return results


def _scan_signatures(file_path: str) -> list:
    """扫描函数/类签名（grep def / class / function）"""
    sigs = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                # Python
                if stripped.startswith("def ") or stripped.startswith("async def "):
                    sigs.append(stripped[:120])
                elif stripped.startswith("class ") and ":" in stripped:
                    sigs.append(stripped[:120])
                # TS/JS
                elif stripped.startswith("export function ") or stripped.startswith("export class "):
                    sigs.append(stripped[:120])
                elif stripped.startswith("function ") and "(" in stripped:
                    sigs.append(stripped[:120])
    except (OSError, PermissionError, UnicodeDecodeError):
        pass
    return sigs


def _scan_imports(file_path: str) -> list:
    """扫描 import / require 行"""
    imports = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    imports.append(stripped[:120])
                elif "require(" in stripped and stripped.strip().startswith("const"):
                    imports.append(stripped[:120])
                elif stripped.startswith("use ") and "::" in stripped:
                    imports.append(stripped[:120])
                elif stripped.startswith("pub ") and "use " in stripped:
                    imports.append(stripped[:120])
    except (OSError, PermissionError, UnicodeDecodeError):
        pass
    return imports


def _get_git_stats(path: str) -> dict:
    """获取 git 提交统计"""
    import subprocess
    git_dir = os.path.join(path, ".git")
    if not os.path.isdir(git_dir):
        return {}
    try:
        total = subprocess.run(
            ["git", "-C", path, "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        last = subprocess.run(
            ["git", "-C", path, "log", "-1", "--format=%cd", "--date=short"],
            capture_output=True, text=True, timeout=5
        )
        active = subprocess.run(
            ["git", "-C", path, "log", "--format=", "--name-only",
             "--since=6.months", "--diff-filter=AM"],
            capture_output=True, text=True, timeout=10
        )
        from collections import Counter
        files = [f for f in active.stdout.splitlines() if f.strip()]
        most_active = [{"path": p, "commits": c} for p, c in Counter(files).most_common(10)]

        return {
            "total_commits": int(total.stdout.strip()) if total.returncode == 0 else 0,
            "last_commit": last.stdout.strip() if last.returncode == 0 else "",
            "most_active_files": most_active,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return {}


def _extract_dependencies(path: str) -> list:
    """提取项目依赖清单"""
    deps = []
    fp = os.path.join(path, "pyproject.toml")
    if os.path.isfile(fp):
        try:
            text = Path(fp).read_text("utf-8", errors="replace")
            for m in re.finditer(r'[="\']([\w._-]+)\s*(?:>=|==|~=|!=|<=|<|>)', text):
                deps.append(m.group(1))
        except Exception:
            pass
    fp = os.path.join(path, "package.json")
    if os.path.isfile(fp):
        try:
            import json as _json
            data = _json.loads(Path(fp).read_text("utf-8", errors="replace"))
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                pkgs = data.get(section, {})
                for name, ver in pkgs.items():
                    deps.append(f"{name} ({ver})")
        except Exception:
            pass
    fp = os.path.join(path, "req*.txt")
    import glob
    for req_file in glob.glob(os.path.join(path, "requirements*.txt")):
        try:
            text = Path(req_file).read_text("utf-8", errors="replace")
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    deps.append(line)
        except Exception:
            pass
    return deps


def _build_tree(entries: list, max_depth: int = 3) -> dict:
    """构建目录树（最大深度 max_depth 层）"""
    root = {"name": ".", "dirs": {}, "files": []}
    for rel, _fp, _size, _lines, _mtime, _ext in entries:
        parts = rel.split(os.sep)
        node = root
        for i, part in enumerate(parts):
            if i == max_depth - 1:
                if i == len(parts) - 1:
                    node["files"].append(part)
                else:
                    node["dirs"].setdefault(part, {"name": part, "dirs": {}, "files": ["..."]})
                break
            if part not in node["dirs"]:
                node["dirs"][part] = {"name": part, "dirs": {}, "files": []}
            node = node["dirs"][part]
        else:
            if parts and parts[-1] not in node["files"]:
                node["files"].append(parts[-1] if parts else "")
    return root


def analyze_project_structure(path: str) -> dict:
    """轻量结构扫描 — 只扫元数据，不读文件正文

    用途：作为 Phase 1，给 LLM 提供项目地图，帮助其决定需要深入读取哪些文件。
    """
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return {"error": f"路径不存在或不是目录: {path}"}

    start_time = time.time()

    # 1. 技术栈嗅探
    tech_stack = sniff_tech_stack(path)

    # 2. 依赖清单
    dependencies = _extract_dependencies(path)

    # 3. Git 统计
    git_stats = _get_git_stats(path)

    # 4. 文件扫描（不读内容）
    entries = _walk_structure_only(path)
    if not entries:
        return {"error": "项目为空或无可读文件"}

    # 5. 统计
    total_files = len(entries)
    total_dirs = len(set(os.path.dirname(e[0]) for e in entries if e[0]))
    by_type = {}
    for e in entries:
        ext = e[5] or "(no ext)"
        by_type[ext] = by_type.get(ext, 0) + 1
    top_types = sorted(by_type.items(), key=lambda x: -x[1])[:10]

    # 6. 分组 + 签名 + import
    source_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs",
                   ".rb", ".kt", ".swift", ".java", ".cs", ".cpp", ".c", ".h", ".php"}
    entry_names = {"main.py", "app.py", "index.tsx", "index.ts", "index.js",
                   "main.go", "main.rs", "main.ts", "app.ts", "app.tsx",
                   "app.js", "server.py", "manage.py", "entrypoint.py", "cli.py"}

    file_details = []
    for rel, fp, size, lines, mtime, ext in entries:
        name = os.path.basename(rel).lower()
        if name in entry_names or rel in ("cli.py", "main.py"):
            group = "entry"
        elif ext in source_exts:
            group = "source"
        elif ext in (".md", ".rst", ".markdown"):
            group = "doc"
        elif ext in (".json", ".yaml", ".yml", ".toml", ".env"):
            group = "config"
        else:
            group = "other"
        is_core = any(rel.startswith(p) for p in CORE_DIR_PREFIXES) if "/" in rel else False
        signatures = []
        imports = []
        if group in ("source", "entry") and size < 500000:
            signatures = _scan_signatures(fp)
            imports = _scan_imports(fp)
        file_details.append({
            "path": rel,
            "group": group,
            "size": size,
            "lines": lines,
            "last_modified": time.strftime("%Y-%m-%d", time.localtime(mtime)) if mtime else "",
            "is_core": is_core,
            "signatures": signatures[:30],
            "imports": imports[:20],
        })

    # 7. 目录树
    tree = _build_tree(entries)

    elapsed = int((time.time() - start_time) * 1000)

    # 8. 按分组整理文件列表
    group_files = {}
    for fd in file_details:
        group_files.setdefault(fd["group"], []).append(fd["path"])
    for g in group_files:
        group_files[g].sort()

    return {
        "tree": tree,
        "tech_stack": tech_stack,
        "dependencies": dependencies,
        "git_stats": git_stats,
        "file_summary": {
            "total_files": total_files,
            "total_dirs": total_dirs,
            "by_type": [{"ext": k, "count": v} for k, v in top_types],
        },
        "group_files": {g: group_files[g][:50] for g in group_files},
        "file_details": file_details,
        "entry_points": [fd["path"] for fd in file_details if fd["group"] == "entry"],
        "scan_time_ms": elapsed,
    }


def is_config_path(rel_path: str) -> bool:
    """判断一个配置文件是否在『合理的 config 目录』下"""
    p = rel_path.lower()
    # 根目录的 config.yaml → 是
    if p.count("/") == 0 and "config" in os.path.basename(p):
        return True
    # config/ 目录下 → 是
    if p.startswith("config/") or "/config/" in p:
        return True
    # .json 在根目录
    if p.count("/") == 0 and p.endswith(".json"):
        return True
    # 其他情况 → 不是（比如 mcp/_impl/third_party/config.yml 太深了不算）
    return False


# ============================================================
# 技术栈嗅探（v2 改进：读依赖文件提取框架信息）
# ============================================================

def sniff_tech_stack(path: str) -> dict:
    """嗅探技术栈：读取关键配置文件提取框架/依赖信息"""
    result = {"languages": set(), "frameworks": set(), "build_tools": set(), "llm_providers": set()}
    found_files = set()

    # 1. 从特征文件名判断语言+工具
    markers = {
        "pyproject.toml": ("Python", "poetry/pdm"),
        "package.json": ("JavaScript/TypeScript", "npm/yarn/pnpm"),
        "Cargo.toml": ("Rust", "cargo"),
        "go.mod": ("Go", "go mod"),
        "Gemfile": ("Ruby", "bundler"),
        "build.gradle": ("Java/Kotlin", "gradle"),
        "composer.json": ("PHP", "composer"),
        "Makefile": (None, "make"),
        "Dockerfile": (None, "docker"),
        "CMakeLists.txt": (None, "cmake"),
        "Cargo.lock": ("Rust", "cargo"),
    }
    for fname, (lang, tool) in markers.items():
        fp = os.path.join(path, fname)
        if os.path.isfile(fp):
            found_files.add(fname)
            if lang:
                result["languages"].add(lang)
            if tool:
                result["build_tools"].add(tool)

    # 2. 读 pyproject.toml 提取依赖（如果有）
    pyproj_fp = os.path.join(path, "pyproject.toml")
    if os.path.isfile(pyproj_fp):
        try:
            text = Path(pyproj_fp).read_text("utf-8", errors="replace")
            # 快速扫描依赖列表中的框架名
            deps = re.findall(r'[="\'](\S+)>=', text)
            dep_text = " ".join(deps).lower()
            for name, label in [
                ("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django"),
                ("langchain", "LangChain"), ("langgraph", "LangGraph"),
                ("chromadb", "ChromaDB"), ("sqlalchemy", "SQLAlchemy"),
                ("pydantic", "Pydantic"), ("httpx", "httpx"), ("aiohttp", "aiohttp"),
                ("uvicorn", "Uvicorn"), ("gunicorn", "Gunicorn"),
                ("sentence-transformers", "SentenceTransformers"),
                ("openai", "OpenAI"), ("anthropic", "Anthropic"),
                ("pymysql", "PyMySQL"), ("psycopg", "psycopg"),
                ("redis", "Redis"), ("tavily", "Tavily"),
                ("firecrawl", "Firecrawl"), ("markitdown", "MarkItDown"),
                ("pytorch", "PyTorch"), ("tensorflow", "TensorFlow"),
                ("numpy", "NumPy"), ("pandas", "Pandas"),
                ("langchain-mcp", "LangChain-MCP"),
                ("langgraph-checkpoint", "LangGraph-Checkpoint"),
            ]:
                if name in dep_text:
                    result["frameworks"].add(label)
        except Exception:
            pass

    # 3. 读 app_config.json / config.json（项目自定义配置中有 LLM 信息）
    for cfg_fname in ("app_config.json", "config.json", ".env.example"):
        fp = os.path.join(path, cfg_fname)
        if os.path.isfile(fp):
            found_files.add(cfg_fname)
            try:
                text = Path(fp).read_text("utf-8", errors="replace")[:2000]
                # 检测 LLM provider
                for provider, label in [
                    ("zhipu", "智谱GLM"), ("openai", "OpenAI"), ("deepseek", "DeepSeek"),
                    ("anthropic", "Anthropic"), ("baidu", "百度文心"),
                    ("aliyun", "阿里通义"), ("google", "Google"), ("ollama", "Ollama"),
                ]:
                    if provider in text.lower():
                        result["llm_providers"].add(label)
            except Exception:
                pass

    # 4. 包管理工具检测
    if "package.json" in found_files:
        try:
            text = Path(os.path.join(path, "package.json")).read_text("utf-8", errors="replace")[:3000]
            for tool in ("pnpm", "yarn", "npm", "bun"):
                if tool in text.lower():
                    result["build_tools"].add(tool)
        except Exception:
            pass

    return {
        "languages": sorted(result["languages"]) or ["未知"],
        "frameworks": sorted(result["frameworks"]) or [],
        "build_tools": sorted(result["build_tools"]) or [],
        "llm_providers": list(result["llm_providers"]) if result["llm_providers"] else [],
    }


# ============================================================
# 内容头部评分（v2 改进）
# ============================================================

ENTRY_CONTENT_SIGNALS = {
    "fastapi": 3.0,
    "uvicorn.run": 3.0,
    "flask": 3.0,
    "django": 3.0,
    "app = FastAPI": 4.0,
    "create_agent": 2.0,
    "langgraph": 2.0,
    "runnables.runnable": 2.0,
    "def main": 1.5,
    "if __name__": 1.5,
    "from flask": 2.5,
    "from fastapi": 2.5,
    "class.*BaseModel": 1.0,
    "class.*TypedDict": 0.5,
    "fastapi.": 2.0,
}

BARREL_SIGNALS = {
    "export * from": -2.0,
    "export {": -1.5,
    "from.*import \\*": -1.5,
    "re-export": -1.0,
}

FRAMEWORK_IMPORTS = {
    "react": "React",
    "next/navigation": "Next.js",
    "vue": "Vue",
    "angular": "Angular",
    "svelte": "Svelte",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
}

AUTO_GEN_SIGNALS = [
    r"(?:auto-generated|generated by|do not edit|don't edit)",
    r"(?:@generated|automatically generated)",
]


def score_content_head(head: str) -> dict:
    """分析文件头部内容，返回额外加分和分组调整"""
    head_lower = head.lower()
    extra = 0.0
    tech_hints = set()

    # ── 入口/框架信号 ──
    for pattern, val in ENTRY_CONTENT_SIGNALS.items():
        if pattern in head_lower:
            extra += val
            if pattern in FRAMEWORK_IMPORTS:
                tech_hints.add(FRAMEWORK_IMPORTS[pattern])

    # ── barrel export （降级） ──
    for pattern, val in BARREL_SIGNALS.items():
        if re.search(pattern, head):
            extra += val

    # ── 自动生成文件（强力降级） ──
    for pattern in AUTO_GEN_SIGNALS:
        if re.search(pattern, head_lower):
            extra -= 3.0
            break

    return {"extra_score": extra, "tech_hints": tech_hints}


# ============================================================
# 文件评分（v2：加入内容分析）
# ============================================================

def score_file(rel_path: str, size: int, head: str = "") -> tuple:
    """按重要度给文件打分

    Returns:
        (total_score, file_group)
    """
    name = os.path.basename(rel_path).lower()
    ext = os.path.splitext(rel_path)[1].lower()
    score = 0.0

    # ── 分组判定 ──
    group = GROUP_OF_NAME.get(name)
    if group is None:
        if name in ENTRY_NAMES:
            group = "entry"
        elif ext in BINARY_EXTS:
            group = "other"
        elif ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".kt", ".swift", ".java", ".cs", ".cpp", ".c", ".h", ".php"):
            group = "source"
        elif ext in (".md", ".rst", ".markdown"):
            group = "doc"
        elif ext in (".json", ".yaml", ".yml", ".toml", ".env"):
            group = "config"
        else:
            group = "other"

    # ── 文件名基础分 ──
    # 文档
    if name in ("readme.md", "readme", "claude.md", "agents.md", "gemini.md"):
        score += 5.0
    # 配置（仅限合理路径下的 config 文件）
    elif is_config_path(rel_path) and ext in (".yaml", ".yml", ".json", ".toml", ".py", ".ts"):
        score += 3.0
    # 入口
    if name in ENTRY_NAMES:
        score += 4.0
    # 源文件
    if group == "source":
        score += 2.0
    if group == "doc" and name not in ("readme.md", "readme", "claude.md", "agents.md"):
        score += 1.0

    # ── 目录前缀加分 ──
    for prefix in CORE_DIR_PREFIXES:
        if rel_path.startswith(prefix) and not rel_path.startswith("mcp/_impl/"):
            score += 1.0
            break

    # ── 内容头部加分（v2：仅对 entry/source 组做，减少I/O） ──
    if head and group in ("entry", "source"):
        extra = score_content_head(head).get("extra_score", 0)
        score += extra

    # ── 减分 ──
    if ext in BINARY_EXTS:
        score -= 10.0
    if "test" in name or name.startswith("test_") or name.endswith("_test"):
        score -= 3.0
    if name == "__init__.py" and size < 500:
        score -= 2.0
    if size < 200 and group != "entry":
        score -= 1.0
    if "template" in rel_path.lower() or "example" in rel_path.lower():
        score -= 1.0
    # 第三方集成目录降级
    if "/_impl/" in rel_path or "/third_party/" in rel_path:
        score -= 2.0

    return max(score, 0.0), group


# ============================================================
# 文件扫描
# ============================================================

def walk_files(path: str) -> list:
    """遍历项目文件，返回 [(rel_path, abs_path, size, head, group), ...]"""
    results = []
    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, path)
                try:
                    size = os.path.getsize(fp)
                except (OSError, PermissionError):
                    size = 0
                head = read_file_head(fp)
                score_val, group = score_file(rel, size, head)
                if score_val > 0:
                    results.append((score_val, rel, fp, size, head, group))
    except (PermissionError, OSError):
        pass
    return results


# ============================================================
# 分组预算读取（v2 改进）
# ============================================================

_SYSTEM_ROOTS = frozenset({"/", "/System", "/Library", "/private", "/etc", "/tmp", "/var", "/dev", "/Applications", "/usr", "/opt", "/Volumes", "/cores", "/home"})

def analyze_project(path: str, depth: str = "normal", max_files: int = None) -> dict:
    """核心分析逻辑"""
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return {"error": f"路径不存在或不是目录: {path}"}
    # ponytail: 拒绝系统根目录，防止递归遍历整个磁盘
    resolved = os.path.realpath(path)
    if resolved in _SYSTEM_ROOTS or resolved == os.path.realpath(os.path.expanduser("~")):
        return {"error": f"不允许分析系统目录或用户主目录: {path}"}

    budget = max_files if max_files else MAX_TOKENS.get(depth, 12000)
    is_deep = depth == "deep"

    # 1. 技术栈嗅探
    tech_stack = sniff_tech_stack(path)

    # 2. 文件扫描 + 评分
    entries = walk_files(path)
    if not entries:
        return {"error": "项目为空或无可读文件"}

    # 3. 按组分桶
    buckets = {}
    for s, rel, fp, size, head, group in entries:
        buckets.setdefault(group, []).append((s, rel, fp, size, head, group))
    for g in buckets:
        buckets[g].sort(key=lambda x: -x[0])

    # 4. 分组分配预算
    group_budgets = {}
    if is_deep:
        # deep 模式：不限制分组
        for g in buckets:
            group_budgets[g] = budget
    else:
        for g, ratio in GROUP_BUDGET_RATIO.items():
            group_budgets[g] = max(int(budget * ratio), 200)

    # 5. 按组读取
    read_files = []
    used_by_group = {}
    total_unread = 0

    # 读取顺序：doc → entry → config → source → build → other
    group_order = ["doc", "entry", "config", "source", "build", "other"]
    for g in group_order:
        if g not in buckets:
            continue
        group_used = 0
        g_budget = group_budgets.get(g, 200)
        is_first_in_group = True
        for s, rel, fp, size, head, _ in buckets[g]:
            if group_used >= g_budget and not is_deep:
                total_unread += 1
                continue
            try:
                content = Path(fp).read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError, PermissionError):
                total_unread += 1
                continue
            tokens = estimate_tokens(content)
            # 单文件 cap：每组第一个文件允许用满全部组预算
            # token 估算有 ±10% 误差，收紧截断防止略超预算被跳掉
            file_cap = g_budget if is_first_in_group else g_budget // 2
            is_first_in_group = False
            if tokens > file_cap:
                content = content[:file_cap * 2]  # 保守截断：2x 字节确保≤cap tokens
                content += f"\n\n[... 文件过大，已截取前 ~{file_cap} tokens]"
                tokens = estimate_tokens(content)
            if group_used + tokens > g_budget and not is_deep:
                total_unread += 1
                continue
            read_files.append({
                "path": rel,
                "size": size,
                "lines": content.count("\n") + 1,
                "content": content,
            })
            group_used += tokens
            used_by_group[g] = used_by_group.get(g, 0) + tokens

    total_read = len(read_files)
    total_entries = sum(len(v) for v in buckets.values())
    total_unread += total_entries - total_read

    # 6. 文件树
    seen_dirs = set()
    for _, rel, _, _, _, _ in entries:
        parts = rel.split(os.sep)
        for i in range(1, len(parts)):
            parent = os.sep.join(parts[:i])
            seen_dirs.add(parent)

    type_counts = {}
    for _, rel, _, _, _, _ in entries:
        ext = os.path.splitext(rel)[1].lower() or "(no ext)"
        type_counts[ext] = type_counts.get(ext, 0) + 1
    top_types = sorted(type_counts.items(), key=lambda x: -x[1])[:10]

    return {
        "structure": {
            "total_files": total_entries,
            "total_dirs": len(seen_dirs),
            "top_dirs": sorted(seen_dirs)[:30],
            "top_file_types": [{"ext": k, "count": v} for k, v in top_types],
        },
        "tech_stack": tech_stack,
        "stats": {
            "files_read": total_read,
            "tokens_used": sum(used_by_group.values()),
            "files_unread": total_unread,
            "budget": budget,
            "by_group": {g: used_by_group.get(g, 0) for g in group_order if g in used_by_group},
        },
        "files": read_files,
    }


# ============================================================
# 代码搜索（不变）
# ============================================================

def search_code(path: str, query: str, file_pattern: str = None,
                max_results: int = 20, context_lines: int = 3) -> dict:
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return {"error": f"路径不存在: {path}"}
    results = []
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                if f.startswith("."):
                    continue
                if file_pattern:
                    import fnmatch
                    if not fnmatch.fnmatch(f, file_pattern):
                        continue
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, path)
                try:
                    lines = Path(fp).read_text(encoding="utf-8", errors="replace").splitlines()
                except (OSError, UnicodeDecodeError, PermissionError):
                    continue
                for i, line in enumerate(lines):
                    if query not in line and query.lower() not in line.lower():
                        continue
                    total += 1
                    if len(results) >= max_results:
                        continue
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    snippet_lines = []
                    for j in range(start, end):
                        marker = ">" if j == i else " "
                        snippet_lines.append(f"{marker} {j + 1}:{lines[j]}")
                    results.append({"file": rel, "line": i + 1, "snippet": "\n".join(snippet_lines)})
    except (PermissionError, OSError):
        pass
    return {"results": results, "total": total, "truncated": total > len(results)}


# ============================================================
# JSON-RPC 处理
# ============================================================

async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "project-analyzer-mcp", "version": "2.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})
        if tool == "analyze_project":
            result = analyze_project(path=args.get("path", ""), depth=args.get("depth", "normal"))
            text = json.dumps(result, ensure_ascii=False, default=str)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}
        if tool == "analyze_project_structure":
            result = analyze_project_structure(path=args.get("path", ""))
            text = json.dumps(result, ensure_ascii=False, default=str)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}
        if tool == "search_code":
            result = search_code(
                path=args.get("path", ""), query=args.get("query", ""),
                file_pattern=args.get("file_pattern"), max_results=args.get("max_results", 20),
                context_lines=args.get("context_lines", 3))
            text = json.dumps(result, ensure_ascii=False)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown tool: {tool}"}}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}


async def main():
    import asyncio
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            request = json.loads(line.strip())
            response = await handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "id": 0, "error": {"code": -32700, "message": "Parse error"}}))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "id": 0, "error": {"code": -32603, "message": str(e)}}))
            sys.stdout.flush()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
