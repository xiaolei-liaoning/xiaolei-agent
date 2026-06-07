#!/usr/bin/env python3
"""
EverMem → Claude Memory 桥接同步工具

双向桥接：
  ← 从 EverMem API 拉取记忆 → 写入 Claude Memory 格式（~/.claude/projects/*/memory/）
  → 将 Claude Memory 变更推回 EverMem（可选）

用法：
  python3 scripts/sync-evermem.py pull          # 从 EverMem 拉取到 Claude Memory
  python3 scripts/sync-evermem.py push          # 从 Claude Memory 推回 EverMem
  python3 scripts/sync-evermem.py sync          # 双向同步
  python3 scripts/sync-evermem.py watch         # 持续监听（文件变化自动同步）
  python3 scripts/sync-evermem.py status        # 查看两边状态

原理：
  1. 查 EverOS /api/v1/memory/search 获得用户记忆（episodes/atomic_facts/profile）
  2. 查 EverOS /api/v1/memory/get 获得列表
  3. 转为 Claude Memory markdown 格式，写到 project memory 目录
  4. 反向：监听 memory/ 目录文件变化 → 调 EverOS /api/v1/memory/add 回写
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("evermem-bridge")

# ── 配置 ──────────────────────────────────────────────────────────────────

EVEROS_API = os.environ.get("EVEROS_API", "http://localhost:8000")
EVEROS_USER_ID = os.environ.get("EVEROS_USER_ID", "xiaolei")
EVEROS_APP_ID = os.environ.get("EVEROS_APP_ID", "default")
EVEROS_PROJECT_ID = os.environ.get("EVEROS_PROJECT_ID", "default")

# Claude Memory 目录（从当前项目推测）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_MEMORY_DIR = os.path.expanduser(
    f"~/.claude/projects/-Users-leiyuxuan-Desktop----agent/memory"
)

# EverMem 本地文件路径（直接读取兜底）
EVERMEM_DIR = os.path.expanduser("~/.evermem")
EVERMEM_USER_DIR = os.path.join(
    EVERMEM_DIR, "default_app", "default_project", "users", EVEROS_USER_ID
)

# ── HTTP Helper ───────────────────────────────────────────────────────────

def _api_post(path: str, body: dict) -> Optional[dict]:
    """调 EverOS API（POST JSON）"""
    url = f"{EVEROS_API}{path}"
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        log.warning(f"  ⚠️  API 请求失败 {url}: {e}")
        return None
    except json.JSONDecodeError:
        log.warning(f"  ⚠️  API 返回非 JSON")
        return None
    except Exception as e:
        log.warning(f"  ⚠️  API 异常: {e}")
        return None


def _api_get(path: str) -> Optional[dict]:
    """调 EverOS API（GET）"""
    url = f"{EVEROS_API}{path}"
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning(f"  ⚠️  GET {path} 失败: {e}")
        return None


# ── Claude Memory 写入 ────────────────────────────────────────────────────

def _claude_memory_path(name: str) -> str:
    """Claude memory 文件路径"""
    return os.path.join(CLAUDE_MEMORY_DIR, name)


def _write_claude_memory(
    name: str,
    description: str,
    memory_type: str,
    content: str,
) -> bool:
    """写一条 Claude Memory

    Args:
        name: 文件名（不含 .md）
        description: 描述（一行摘要）
        memory_type: user | project | reference | feedback
        content: markdown 正文
    Returns:
        True 表示写入成功（或已存在无需更新）
    """
    path = _claude_memory_path(name)
    existing = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()

    # 生成 frontmatter
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    fm = f"""---
name: {name}
description: {description}
metadata:
  type: {memory_type}
  synced_from: evermem
  synced_at: {now}
---

"""
    body = fm + content.strip() + "\n"

    if existing == body:
        return False  # 无变化

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return True


def _update_memory_index(name: str, description: str) -> None:
    """更新 MEMORY.md 索引"""
    index_path = os.path.join(CLAUDE_MEMORY_DIR, "MEMORY.md")
    line = f"- [{name}]({name}.md) — {description}\n"

    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 检查是否已存在
        if f"[{name}]" in content:
            return
    else:
        content = ""

    with open(index_path, "a", encoding="utf-8") as f:
        f.write(line)


# ── 从 EverMem 拉取 ───────────────────────────────────────────────────────

def _safe_slug(text: str, max_len: int = 40) -> str:
    """转短横线式 slug"""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug[:max_len]


def pull_api() -> int:
    """从 EverOS API 拉取记忆 → Claude Memory

    Returns: 新写入的文件数
    """
    log.info(f"\n  ── 从 EverOS API 拉取记忆 ──")
    log.info(f"  API: {EVEROS_API}")
    log.info(f"  User: {EVEROS_USER_ID}")
    log.info(f"  Target: {CLAUDE_MEMORY_DIR}")

    written = 0

    # ── 1. 拉取用户 profile ──
    log.info(f"\n  📋 拉取用户画像...")
    resp = _api_post("/api/v1/memory/search", {
        "user_id": EVEROS_USER_ID,
        "app_id": EVEROS_APP_ID,
        "project_id": EVEROS_PROJECT_ID,
        "query": "user profile",
        "method": "hybrid",
        "include_profile": True,
    })
    if resp and "data" in resp:
        data = resp["data"]
        profiles = data.get("profiles", [])
        if profiles:
            for prof in profiles:
                pd = prof.get("profile_data", {})
                summary = pd.get("summary", "用户画像")
                explicit = pd.get("explicit_info", [])
                implicit = pd.get("implicit_traits", [])

                lines = [f"# {summary}\n"]
                if explicit:
                    lines.append("## 明确信息\n")
                    for e in explicit:
                        lines.append(f"- **{e.get('category','')}**: {e.get('description','')}")
                    lines.append("")
                if implicit:
                    lines.append("## 隐含特征\n")
                    for t in implicit:
                        lines.append(f"- **{t.get('trait','')}**: {t.get('description','')}")
                    lines.append("")

                ok = _write_claude_memory(
                    name="evermem-user-profile",
                    description=summary,
                    memory_type="user",
                    content="\n".join(lines),
                )
                if ok:
                    _update_memory_index("evermem-user-profile", summary)
                    log.info(f"  ✅ 用户画像已同步")
                    written += 1
    else:
        # 兜底：直接从本地文件读取
        user_md = os.path.join(EVERMEM_USER_DIR, "user.md")
        if os.path.exists(user_md):
            with open(user_md, "r", encoding="utf-8") as f:
                content = f.read()
            # 提取 frontmatter 后的正文
            body = content.split("---", 2)[-1].strip() if content.startswith("---") else content
            ok = _write_claude_memory(
                name="evermem-user-profile",
                description="EverMem 用户画像",
                memory_type="user",
                content=body,
            )
            if ok:
                _update_memory_index("evermem-user-profile", "EverMem 用户画像")
                log.info(f"  ✅ 用户画像已同步（本地文件）")
                written += 1

    # ── 2. 拉取 episodes/atomic_facts ──
    log.info(f"\n  📋 拉取对话记录...")
    resp = _api_post("/api/v1/memory/search", {
        "user_id": EVEROS_USER_ID,
        "app_id": EVEROS_APP_ID,
        "project_id": EVEROS_PROJECT_ID,
        "query": "development claude code agent",
        "method": "hybrid",
    })
    if resp and "data" in resp:
        data = resp["data"]
        episodes = data.get("episodes", [])
        if episodes:
            log.info(f"  找到 {len(episodes)} 条对话记录")
            for ep in episodes[:5]:  # 最多 5 条
                ep_id = _safe_slug(ep.get("subject", "episode")[:30])
                summary = ep.get("summary", "")
                subject = ep.get("subject", "")
                timestamp = ep.get("timestamp", "")
                facts = ep.get("atomic_facts", [])

                lines = [f"# {subject}\n"]
                if summary:
                    lines.append(f"{summary}\n")
                if timestamp:
                    lines.append(f"- **时间**: {timestamp}")
                lines.append("")

                if facts:
                    lines.append("## 关键事实\n")
                    for f in facts:
                        lines.append(f"- {f.get('content', '')}")
                    lines.append("")

                ok = _write_claude_memory(
                    name=f"evermem-episode-{ep_id}",
                    description=f"对话: {subject[:60]}",
                    memory_type="project",
                    content="\n".join(lines),
                )
                if ok:
                    _update_memory_index(f"evermem-episode-{ep_id}", subject[:60])
                    log.info(f"  ✅ 对话记录同步: {subject[:50]}...")
                    written += 1

    # ── 3. 拉取 agent cases ──
    log.info(f"\n  📋 拉取 Agent 案例...")
    resp = _api_post("/api/v1/memory/search", {
        "agent_id": EVEROS_USER_ID,
        "app_id": EVEROS_APP_ID,
        "project_id": EVEROS_PROJECT_ID,
        "query": "task execution tool call",
        "method": "hybrid",
    })
    if resp and "data" in resp:
        data = resp["data"]
        cases = data.get("agent_cases", [])
        if cases:
            log.info(f"  找到 {len(cases)} 条 Agent 案例")
            for case in cases[:5]:
                intent = case.get("task_intent", "Agent 任务")
                approach = case.get("approach", "")
                insight = case.get("key_insight", "")

                lines = [f"# Agent 案例: {intent[:60]}\n"]
                if approach:
                    lines.append(f"**方法**: {approach}\n")
                if insight:
                    lines.append(f"**洞察**: {insight}\n")

                ok = _write_claude_memory(
                    name=f"evermem-agent-case-{_safe_slug(intent[:20])}",
                    description=f"Agent: {intent[:60]}",
                    memory_type="reference",
                    content="\n".join(lines),
                )
                if ok:
                    log.info(f"  ✅ Agent 案例同步: {intent[:50]}...")
                    written += 1

    # ── 4. 本地兜底：直接读 atomic_facts 和 foresights ──
    log.info(f"\n  📋 本地兜底文件扫描...")
    for af_file in sorted(Path(EVERMEM_USER_DIR).rglob(".atomic_facts/*.md")):
        with open(af_file, "r", encoding="utf-8") as f:
            content = f.read()
        # 提取纯事实列表
        facts = re.findall(r"### Fact\n(.+)", content)
        if facts:
            ok = _write_claude_memory(
                name="evermem-atomic-facts",
                description="原子事实摘要",
                memory_type="user",
                content="\n".join(f"- {f}" for f in facts),
            )
            if ok:
                log.info(f"  ✅ 原子事实已同步")
                written += 1

    for fs_file in sorted(Path(EVERMEM_USER_DIR).rglob(".foresights/*.md")):
        with open(fs_file, "r", encoding="utf-8") as f:
            content = f.read()
        # 提取 foresight 条目
        entries = re.findall(r"### Foresight\n(.+?)\n### Evidence\n(.+?)(?=\n<!--|\n##|$)", content, re.DOTALL)
        if entries:
            lines = ["# 前瞻洞察\n"]
            for foresight, evidence in entries[:10]:
                lines.append(f"- **预见**: {foresight.strip()}")
                lines.append(f"  **依据**: {evidence.strip()}")
                lines.append("")
            ok = _write_claude_memory(
                name="evermem-foresights",
                description="前瞻洞察预测",
                memory_type="reference",
                content="\n".join(lines),
            )
            if ok:
                log.info(f"  ✅ 前瞻洞察已同步")
                written += 1

    return written


# ── 推回 EverMem ─────────────────────────────────────────────────────────

def push() -> int:
    """将 Claude Memory 变更推回 EverMem

    Returns: 推回的消息数
    """
    log.info(f"\n  ── 推回 EverMem ──")
    log.info(f"  Source: {CLAUDE_MEMORY_DIR}")

    if not os.path.isdir(CLAUDE_MEMORY_DIR):
        log.warning("  ⚠️  Claude Memory 目录不存在")
        return 0

    pushed = 0
    # 收集 memory 文件
    for fname in sorted(os.listdir(CLAUDE_MEMORY_DIR)):
        if not fname.endswith(".md") or fname == "MEMORY.md":
            continue

        fpath = os.path.join(CLAUDE_MEMORY_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析 frontmatter
        fm_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
        if not fm_match:
            continue

        fm_text = fm_match.group(1)
        body = fm_match.group(2).strip()

        # 跳过已同步过的
        if "synced_from: evermem" in fm_text:
            continue

        # 提取 description
        desc_match = re.search(r"description: (.+)", fm_text)
        description = desc_match.group(1) if desc_match else fname

        memory_type = "user"
        type_match = re.search(r"type: (\w+)", fm_text)
        if type_match:
            memory_type = type_match.group(1)

        # 推回 EverMem（作为 agent 记忆）
        session_id = f"claude-memory-{fname.replace('.md','')}"
        msgs = [{
            "sender_id": "claude",
            "sender_name": "Claude",
            "role": "assistant",
            "timestamp": int(time.time() * 1000),
            "content": f"[Memory Sync] {description}\n\n{body[:2000]}",
        }]

        resp = _api_post("/api/v1/memory/add", {
            "session_id": session_id,
            "app_id": EVEROS_APP_ID,
            "project_id": EVEROS_PROJECT_ID,
            "messages": msgs,
        })
        if resp:
            log.info(f"  ✅ 推回: {fname}")
            pushed += 1
        else:
            log.warning(f"  ⚠️  推回失败: {fname}")

    return pushed


# ── 状态 ──────────────────────────────────────────────────────────────────

def status() -> None:
    """查看两边状态"""
    log.info(f"\n  ── 状态 ──")

    # EverMem 状态
    log.info(f"\n  📦 EverMem:")
    log.info(f"     API: {EVEROS_API}")
    try:
        resp = _api_get("/health")
        if resp and resp.get("status") == "ok":
            log.info(f"     ✅ 服务正常")
        else:
            log.info(f"     ❌ 服务异常")
    except Exception:
        log.info(f"     ❌ 服务不可达")

    # 查询统计
    resp = _api_post("/api/v1/memory/search", {
        "user_id": EVEROS_USER_ID,
        "app_id": EVEROS_APP_ID,
        "project_id": EVEROS_PROJECT_ID,
        "query": "memory count",
        "method": "keyword",
    })
    if resp and "data" in resp:
        d = resp["data"]
        log.info(f"     Episodes: {len(d.get('episodes', []))}")
        log.info(f"     Profiles: {len(d.get('profiles', []))}")
        log.info(f"     Agent Cases: {len(d.get('agent_cases', []))}")

    # 本地文件
    log.info(f"\n  📝 Claude Memory:")
    log.info(f"     Dir: {CLAUDE_MEMORY_DIR}")
    if os.path.isdir(CLAUDE_MEMORY_DIR):
        files = [f for f in os.listdir(CLAUDE_MEMORY_DIR) if f.endswith(".md") and f != "MEMORY.md"]
        log.info(f"     文件数: {len(files)}")
        for f in files:
            fpath = os.path.join(CLAUDE_MEMORY_DIR, f)
            size = os.path.getsize(fpath)
            log.info(f"     - {f} ({size} bytes)")
    else:
        log.info(f"     目录不存在")

    # 本地 EverMem markdown
    log.info(f"\n  📄 EverMem 本地文件:")
    log.info(f"     Dir: {EVERMEM_USER_DIR}")
    if os.path.isdir(EVERMEM_USER_DIR):
        for root, dirs, files in os.walk(EVERMEM_USER_DIR):
            for f in files:
                if f.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, f), EVERMEM_USER_DIR)
                    log.info(f"     - {rel}")
    else:
        log.info(f"     目录不存在")


# ── Watch 模式（文件变化监听） ──────────────────────────────────────────

def watch() -> None:
    """持续监听 Claude Memory 目录变化"""
    import subprocess

    log.info(f"\n  ── Watch 模式 ──")
    log.info(f"  监听: {CLAUDE_MEMORY_DIR}")
    log.info(f"  Ctrl+C 停止\n")

    try:
        subprocess.run([
            sys.executable, "-m", "watchfiles",
            __file__, "push",
            CLAUDE_MEMORY_DIR,
        ], cwd=os.path.dirname(__file__))
    except FileNotFoundError:
        log.warning("  watchfiles 未安装，用轮询代替（每 30s）")
        last_mtime = 0
        while True:
            try:
                time.sleep(30)
                current = max(
                    (os.path.getmtime(os.path.join(CLAUDE_MEMORY_DIR, f))
                     for f in os.listdir(CLAUDE_MEMORY_DIR)
                     if f.endswith(".md") and f != "MEMORY.md"),
                    default=0,
                )
                if current > last_mtime:
                    log.info("  🔄 检测到变更，推回 EverMem...")
                    push()
                    last_mtime = current
            except KeyboardInterrupt:
                break


# ── Cron 定时同步 ─────────────────────────────────────────────────────────

_CRON_DIR = os.path.expanduser("~/.claude/evermem-sync")
_CRON_LOG = os.path.join(_CRON_DIR, "sync.log")
_CRON_PID = os.path.join(_CRON_DIR, "sync.pid")


def _cron_log_path() -> str:
    os.makedirs(_CRON_DIR, exist_ok=True)
    return _CRON_LOG


def cron(interval: int = 300, quiet: bool = False) -> None:
    """定时拉取模式（守护进程），默认每 300s 同步一次"""
    log_path = _cron_log_path()
    pid = str(os.getpid())

    # 写入 PID 文件（防重跑）
    if os.path.exists(_CRON_PID):
        try:
            with open(_CRON_PID) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            print(f"⚠️  已有同步进程在跑 (PID {old_pid})，退出")
            sys.exit(1)
        except (OSError, ValueError):
            pass  # 旧进程已死
    with open(_CRON_PID, "w") as f:
        f.write(pid)

    # 写入日志头
    with open(log_path, "a") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{datetime.now().isoformat()}] 🚀 cron 启动 (PID {pid}, 间隔 {interval}s)\n")
        f.write(f"{'='*60}\n")

    # 启动时立即执行一次
    _cron_tick(log_path, quiet)

    try:
        while True:
            time.sleep(interval)
            _cron_tick(log_path, quiet)
    except KeyboardInterrupt:
        print("\n  ⏹  cron 已停止")
    finally:
        if os.path.exists(_CRON_PID):
            try:
                os.remove(_CRON_PID)
            except OSError:
                pass


def _cron_tick(log_path: str, quiet: bool) -> None:
    """执行一次同步并记日志"""
    timestamp = datetime.now().isoformat()
    try:
        # 重定向 stdout 到日志
        old_stdout = sys.stdout
        with open(log_path, "a") as f:
            sys.stdout = f
            f.write(f"\n[{timestamp}] 🔄 开始同步...\n")
            try:
                n = pull_api()
                f.write(f"[{datetime.now().isoformat()}] ✨ 同步完成: {n} 条记忆\n")
            except Exception as e:
                f.write(f"[{datetime.now().isoformat()}] ❌ 同步异常: {e}\n")
        sys.stdout = old_stdout
        if not quiet:
            print(f"  [{timestamp}] ✅ cron 同步完成 (see {log_path})")
    except Exception as e:
        if not quiet:
            print(f"  [{timestamp}] ❌ cron 异常: {e}")


# ── 安装/卸载 launchd 服务（macOS 持久化） ───────────────────────────────

_LAUNCHD_LABEL = "com.user.evermem-sync"
_LAUNCHD_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{_LAUNCHD_LABEL}.plist")


def _launchd_plist(interval_seconds: int) -> str:
    """生成 launchd plist 内容"""
    script_path = os.path.abspath(__file__)
    log_path = _cron_log_path()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{script_path}</string>
        <string>cron</string>
        <string>--quiet</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:{os.path.dirname(sys.executable)}</string>
    </dict>
    <key>KeepAlive</key>
    <false/>
    <key>ThrottleInterval</key>
    <integer>{max(interval_seconds, 60)}</integer>
</dict>
</plist>"""


def install(interval: int = 300) -> None:
    """安装 launchd 服务（macOS 后台定时同步）"""
    plist_content = _launchd_plist(interval)

    # 写入 plist
    os.makedirs(os.path.dirname(_LAUNCHD_PATH), exist_ok=True)
    with open(_LAUNCHD_PATH, "w") as f:
        f.write(plist_content)
    os.chmod(_LAUNCHD_PATH, 0o644)

    # 卸载旧版
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{_LAUNCHD_LABEL}"],
                   capture_output=True, timeout=5)

    # 加载新版
    result = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", _LAUNCHD_PATH],
                           capture_output=True, text=True, timeout=5)

    if result.returncode == 0:
        print(f"  ✅ launchd 服务已安装 (间隔 {interval}s)")
        print(f"     plist: {_LAUNCHD_PATH}")
        print(f"     日志: {_CRON_LOG}")
    else:
        print(f"  ⚠️  launchctl 结果: {result.stderr.strip()}")
        print(f"     尝试: launchctl bootstrap gui/{os.getuid()} {_LAUNCHD_PATH}")


def uninstall() -> None:
    """卸载 launchd 服务"""
    result = subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{_LAUNCHD_LABEL}"],
        capture_output=True, text=True, timeout=5,
    )
    if os.path.exists(_LAUNCHD_PATH):
        os.remove(_LAUNCHD_PATH)
    if os.path.exists(_CRON_PID):
        os.remove(_CRON_PID)

    if result.returncode == 0:
        print(f"  ✅ launchd 服务已卸载")
    else:
        print(f"  ⚠️  卸载结果: {result.stderr.strip()}")


def service_status() -> None:
    """查看 launchd 服务状态"""
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{_LAUNCHD_LABEL}"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode == 0:
        print(f"  ✅ launchd 服务: 已加载")
        print(f"     plist: {_LAUNCHD_PATH}")
        # 提取状态信息
        for line in result.stdout.split("\n"):
            line = line.strip()
            if any(k in line for k in ["pid", "state", "last", "exit"]):
                print(f"     {line}")
    else:
        print(f"  ⚪ launchd 服务: 未安装")
        print(f"     安装: python3 scripts/sync-evermem.py install")


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="EverMem ↔ Claude Memory 桥接同步工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/sync-evermem.py pull         从 EverMem 拉取到 Claude Memory
  python3 scripts/sync-evermem.py status       查看两端状态
  python3 scripts/sync-evermem.py cron         每5分钟自动同步（前台进程）
  python3 scripts/sync-evermem.py install      安装后台定时服务（重启后也有效）
  python3 scripts/sync-evermem.py uninstall    卸载后台服务
        """,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("pull", help="从 EverMem 拉取到 Claude Memory")
    sub.add_parser("push", help="从 Claude Memory 推回 EverMem")
    sub.add_parser("sync", help="双向同步")
    sub.add_parser("status", help="查看状态")
    sub.add_parser("watch", help="持续监听文件变化")
    p_cron = sub.add_parser("cron", help="定时拉取（守护进程）")
    p_cron.add_argument("--interval", type=int, default=300, help="间隔秒数（默认300=5分钟）")
    p_cron.add_argument("--quiet", action="store_true", help="静默模式（仅写日志）")
    p_install = sub.add_parser("install", help="安装 launchd 后台服务（macOS）")
    p_install.add_argument("--interval", type=int, default=300, help="间隔秒数（默认300=5分钟）")
    sub.add_parser("uninstall", help="卸载 launchd 后台服务")
    sub.add_parser("service-status", help="查看 launchd 服务状态")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 检查 Claude Memory 目录
    os.makedirs(CLAUDE_MEMORY_DIR, exist_ok=True)

    if args.command == "pull":
        n = pull_api()
        log.info(f"\n  ✨ 完成: 同步了 {n} 条记忆")

    elif args.command == "push":
        n = push()
        log.info(f"\n  ✨ 完成: 推回了 {n} 条")

    elif args.command == "sync":
        n1 = pull_api()
        n2 = push()
        log.info(f"\n  ✨ 完成: 拉取 {n1} 条，推回 {n2} 条")

    elif args.command == "cron":
        cron(interval=args.interval, quiet=args.quiet)

    elif args.command == "install":
        install(interval=args.interval)

    elif args.command == "uninstall":
        uninstall()

    elif args.command == "service-status":
        service_status()

    elif args.command == "status":
        status()

    elif args.command == "watch":
        watch()


if __name__ == "__main__":
    main()
