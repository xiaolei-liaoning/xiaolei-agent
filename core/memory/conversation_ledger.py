"""ConversationLedger — 全量对话账本（Hermes 模式）

定位（与 STM/向量库的分工）：
  - STM 短期记忆: 本次会话的"工作台"，可压缩可撕页（B1 会话边界管注入）
  - 向量库:       LLM 提炼后的"有用知识"（偏好/事实/经验）
  - 账本(本文件):  对话原文的"档案室"，append-only 永不删改——
                  STM 撕掉的页、向量库提炼漏掉的细节，这里都翻得回来

存储格式:
  ~/.小雷版小龙虾/history/{user_id}/YYYY-MM.jsonl
  一行一条 JSON: {"ts","session_id","role","content","task"}
  只增不删。按月分文件避免单文件无限膨胀。

读路径:
  search(query, user_id)  → 关键词搜索账本，返回命中条目（含时间/会话/角色）
  recent(user_id, limit)  → 最近 N 条（跨会话回看）

工具入口: tool_registry.search_history → _handle_search_history
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

HISTORY_ROOT = Path(os.path.expanduser("~/.小雷版小龙虾/history"))

# 单条 content 截断上限——账本是"指路牌"不是"全文转储"，
# 太长的条目（如 2 万字文件写入的 echo）截断存储，需要全文 agent 再 read_file 原产物
MAX_ENTRY_CHARS = 2000


def _safe_user_id(user_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-.@]+", "_", user_id)[:64]


def _ledger_dir(user_id: str) -> Path:
    return HISTORY_ROOT / _safe_user_id(user_id)


def _month_file(user_id: str, dt: Optional[datetime] = None) -> Path:
    dt = dt or datetime.now()
    return _ledger_dir(user_id) / f"{dt.strftime('%Y-%m')}.jsonl"


def _all_ledger_files(user_id: str) -> List[Path]:
    d = _ledger_dir(user_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.jsonl"))


def append_entry(user_id: str, session_id: str, role: str,
                 content: str, task: str = "") -> None:
    """追加一条对话记录到账本（append-only，永不删改）

    失败静默——账本是兜底设施，绝不能因为它挡住主流程。
    """
    if not user_id or not content:
        return
    try:
        d = _ledger_dir(user_id)
        d.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "role": role,
            "content": str(content)[:MAX_ENTRY_CHARS],
            "task": str(task)[:200],
        }
        with open(_month_file(user_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"账本写入失败: {e}")


def _iter_entries(user_id: str, newest_first: bool = False):
    """遍历账本全部条目（按月文件顺序，文件内按行序）"""
    files = _all_ledger_files(user_id)
    if newest_first:
        files = list(reversed(files))
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def search(query: str, user_id: str, limit: int = 10,
           role: str = "") -> List[Dict]:
    """关键词搜索账本（大小写不敏感，多词 AND）

    这是 agent "翻老账本" 的主入口——被问"上次说了什么/之前给过什么建议"
    时调 search_history 工具，返回带时间戳和会话 id 的原文条目。
    """
    if not query.strip():
        return []
    terms = [t.lower() for t in query.split() if t.strip()]
    hits: List[Dict] = []
    for e in _iter_entries(user_id, newest_first=True):
        text = f"{e.get('content','')} {e.get('task','')}".lower()
        if role and e.get("role", "") != role:
            continue
        if all(t in text for t in terms):
            hits.append(e)
            if len(hits) >= limit:
                break
    return hits


def recent(user_id: str, limit: int = 20, session_id: str = "") -> List[Dict]:
    """最近 N 条（可按会话过滤）——"上次我们聊到哪了"场景

    修复: 取的是"最新 N 条"——先全量收集再取尾部（同月文件内行序是
    时间正序，仅倒月文件序不够）。
    """
    out: List[Dict] = []
    for e in _iter_entries(user_id):
        if session_id and e.get("session_id", "") != session_id:
            continue
        out.append(e)
    return out[-limit:] if limit and len(out) > limit else out


def stats(user_id: str) -> Dict:
    files = _all_ledger_files(user_id)
    total = sum(1 for _ in _iter_entries(user_id))
    span = f"{files[0].stem} ~ {files[-1].stem}" if files else "空"
    return {"files": len(files), "entries": total, "span": span}


def format_hits(hits: List[Dict]) -> str:
    """把搜索结果格式化成 agent 可读的文本块"""
    if not hits:
        return "(账本中未找到相关记录)"
    lines = [f"找到 {len(hits)} 条历史记录:"]
    for e in hits:
        lines.append(
            f"[{e.get('ts','')}] 会话{str(e.get('session_id',''))[-8:]} "
            f"[{e.get('role','?')}] {e.get('content','')[:400]}"
        )
    return "\n".join(lines)
