"""小雷版 TOOLSETS — 工具分组 (对标 hermes toolsets.py)

参考 hermes:
- 35 组单 dict, `_ts/_bundle/_core_without` 组合器
- 一个工具必须被 toolset 引用才**暴露**给 system prompt
- 按回合动态裁剪 (per-platform / per-env / `XIAOLEI_TOOLSETS` 环境变量)

小雷版 15 核心工具 + 2 可选工具:
  file: read_file/write_file/edit_file/search_files
  terminal: execute_shell/execute_python
  web: web_search/fetch_url
  agent_core: write_todos/update_goal/git
  subagent: task/orchestrate
  viz: arbor_viz/text_analyzer
  skills (opt-in): skill/search_history
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional

# ── 每工具重复使用的小 helper ──


def _ts(description: str, tools=(), includes=None, **extra) -> dict:
    return {"description": description, "tools": list(tools), "includes": list(includes or ()), **extra}


def _core_without(*excluded, keep: Optional[List[str]] = None) -> List[str]:
    """参照 hermes _core_without — 从 CORE minus*excluded 组合列表 (顺序保留)"""
    if keep is None:
        keep = CORE_TOOLS
    return [t for t in keep if t not in excluded]


# ════════════════════════════════════════════════════════════════
# 核心 17 工具 (对标 hermes _HERMES_CORE_TOOLS)
# ════════════════════════════════════════════════════════════════

# 核心工具（默认暴露）
CORE_TOOLS = [
    "write_todos", "update_goal", "write_file",
    "execute_python", "execute_shell",
    "git", "fetch_url", "web_search",
    "read_file", "edit_file", "search_files",
    "arbor_viz", "text_analyzer",
    "task", "orchestrate",
]

# Skill 工具独立 toolset — 不污染核心，需显式启用
OPTIONAL_TOOLSETS = {
    "skills": {
        "description": "Load skill documents on demand (opt-in)",
        "tools": ["skill", "search_history"],
    },
}

# 平台 / 安全子集
_WEBHOOK_SAFE_TOOLS = ["web_search", "fetch_url", "text_analyzer"]
_PLUGINS_SAFE_TOOLS = CORE_TOOLS  # 默认插件拥有全 CORE 权限(后期-list)

# ════════════════════════════════════════════════════════════════
# TOOLSETS 单 dict
# ════════════════════════════════════════════════════════════════

TOOLSETS: Dict[str, dict] = {
    # ── 基础类别 ──
    "file": _ts(
        "File manipulation: read, write, fuzzy-edit, and search",
        ["read_file", "write_file", "edit_file", "search_files"],
    ),
    "terminal": _ts(
        "Command execution (shell / python) and process management",
        ["execute_shell", "execute_python"],
    ),
    "web": _ts(
        "Web research: search + fetch",
        ["web_search", "fetch_url"],
    ),
    "agent_core": _ts(
        "Task lifecycle tools: plan steps, goal, git",
        ["write_todos", "update_goal", "git"],
    ),
    "skills": _ts(
        "Skill listing/loading/managing via the curated provider",
        ["skill", "search_history"],
    ),
    "subagent": _ts(
        "Spawn subagents (task) and orchestrate DAG (orchestrate)",
        ["task", "orchestrate"],
    ),
    "viz": _ts(
        "Visual analysis (arbor viz / text analyzer)",
        ["arbor_viz", "text_analyzer"],
    ),

    # ── 组合 (对标 hermes "coding"/"safe") ──
    "coding": _ts(
        "Coding-focused toolset: file + terminal + web docs + subagent",
        # _core_without 移除 social/... 组合器示范
        _core_without("text_analyzer", "arbor_viz", "task", "orchestrate",
                      keep=CORE_TOOLS),
    ),
    "safe": _ts(
        "Minimal safe tools (webhook/permit-exposed)",
        ["read_file", "web_search", "text_analyzer", "search_files"],
    ),

    # ── mist 平台: user-site tools 在这里 (fallback toolset) ──
    "misc": _ts("Unclassified tools", []),
}


def resolve_toolset_keys(allow: Optional[List[str]] = None,
                         deny: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """按 allow/deny resolve 工具集 → 暴露的tool名列表 (uncal sets, dedup)"""
    allow = allow or list(TOOLSETS.keys())
    allow = [a for a in allow if a in TOOLSETS]
    deny = deny or []
    allow = [a for a in allow if a not in deny]

    out: List[str] = []
    for a in allow:
        spec = TOOLSETS[a]
        out.extend(spec["tools"])       # group list
        for inc in spec.get("includes", []):
            if inc in TOOLSETS:
                out.extend(TOOLSETS[inc]["tools"])
    # dedup 保序
    seen, ordered = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return {"toolsets": allow, "tools": ordered}


def load_enabled_from_env(default: Optional[List[str]] = None) -> List[str]:
    """XIAOLEI_TOOLSETS=web,file,coding (逗号分隔, 大小写不敏感)"""
    raw = os.environ.get("XIAOLEI_TOOLSETS", "").strip()
    if not raw:
        return default or CORE_TOOLS
    names = [x.strip().lower() for x in raw.split(",") if x.strip()]
    valid = [n for n in names if n in TOOLSETS]
    if not valid:
        logger_name = __name__
        import logging
        logging.getLogger(logger_name).warning(
            f"XIAOLEI_TOOLSETS 无有效工具组 {names!r} — 全部 fcore 兜底")
        return default or CORE_TOOLS
    return valid


def add_runtime_toolset(name: str, description: str, tools: List[str],
                        includes: Optional[List[str]] = None) -> None:
    """插件 register 时动态添加 toolset (per-plugin toolsets)"
    容器化测试/用户插件用, 核心 TOOLSETS 永不被 shadow (内置 Only)
    """
    if name in TOOLSETS:
        import logging
        logging.getLogger(__name__).debug(f"toolset `{name}` 已存在, skip add")
        return
    TOOLSETS[name] = _ts(description, tools=tools, includes=includes)
